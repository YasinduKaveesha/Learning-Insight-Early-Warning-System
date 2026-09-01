"""Fail-closed Supabase access-token verification against JWKS (work order B2.3).

Ported from `Upadya/Dev/backend/app/infrastructure/auth.py` (read-only reference) rather than
inventing a second scheme (`plan/backend_plan.md` section 8 "Auth"). Adapted to this backend's
own conventions: settings live in `app.infrastructure.settings`, not `app.core.config`; errors
are `app.domain.errors.AuthenticationError`, not a FastAPI-coupled type, so this module has no
FastAPI dependency and can be unit-tested without a request object.

A verified signature is NOT an authorization decision. This module answers only "is this a
genuine, unexpired Supabase token, and whose is it" -- `VerifiedClaims.subject` /
`.is_anonymous`. Turning that into an authorized teacher is
`app.application.principal_resolution.resolve_principal`'s job, not this module's.

**Never log a raw token, a `sub`, or any claim value.** Every log line in this module (there
are none in the hot path) and every exception message stays claim-free by construction.
"""

from __future__ import annotations

from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient, PyJWKSet
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.domain.errors import AuthenticationError
from app.domain.principal import VerifiedClaims
from app.infrastructure.settings import Settings, get_settings

#: `alg: none` and every symmetric (HMAC) algorithm are excluded by construction -- listing
#: only the two asymmetric algorithms Supabase issues means an attacker who can choose the
#: `alg` header can never downgrade to something this verifier will accept.
ALLOWED_ALGORITHMS = frozenset({"RS256", "ES256"})

#: Supabase's own claim marking an anonymous sign-in session (`supabase.auth.signInAnonymously`).
#: An anonymous token is genuine and signature-verifiable; it identifies no teacher on its own
#: -- see `app.application.principal_resolution.resolve_principal`.
_ANONYMOUS_CLAIM = "is_anonymous"


class ControlledJwksClient(PyJWKClient):
    """TTL cache plus rate-limited forced refresh for safe key rotation.

    `lifespan` is `SUPABASE_JWKS_CACHE_TTL_SECONDS` -- the plan's named cache-TTL setting.
    """

    def __init__(self, uri: str, *, lifespan: int, timeout: float = 5) -> None:
        super().__init__(
            uri,
            cache_keys=False,
            cache_jwk_set=True,
            lifespan=lifespan,
            timeout=timeout,
        )
        self._refresh_lock = Lock()
        self._last_forced_refresh = 0.0
        self._refresh_cooldown = min(30.0, max(5.0, lifespan / 10))

    @staticmethod
    def _find_key(jwk_set: PyJWKSet, kid: str) -> Any | None:
        return next((key for key in jwk_set.keys if key.key_id == kid), None)

    def get_signing_key(self, kid: str) -> Any:
        key = self._find_key(self.get_jwk_set(), kid)
        if key is not None:
            return key
        with self._refresh_lock:
            key = self._find_key(self.get_jwk_set(), kid)
            now = monotonic()
            if key is None and now - self._last_forced_refresh >= self._refresh_cooldown:
                key = self._find_key(self.get_jwk_set(refresh=True), kid)
                self._last_forced_refresh = now
        if key is None:
            raise PyJWKClientError("Unable to find a signing key that matches the token")
        return key


class SigningKeyClient(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class SupabaseJwtVerifier:
    """Verifies signature, issuer, audience and expiry against `SUPABASE_JWKS_URL`.

    Explicitly rejects `alg: none` and any unsigned token (the header check below runs
    BEFORE any call to `jwt.decode`, so an attacker cannot rely on `jwt.decode` alone to
    enforce the algorithm allow-list -- PyJWT does enforce it too, but defense is not
    single-layered here on purpose).
    """

    def __init__(self, settings: Settings, jwks_client: SigningKeyClient | None = None) -> None:
        self._issuer = settings.supabase_jwt_issuer
        self._audience = settings.supabase_jwt_audience
        self._jwks_client = jwks_client or ControlledJwksClient(
            str(settings.supabase_jwks_url),
            lifespan=settings.supabase_jwks_cache_ttl_seconds,
            timeout=5,
        )

    def verify(self, token: str) -> VerifiedClaims:
        """Return `VerifiedClaims` for a genuine, unexpired token.

        Raises `AuthenticationError` (never anything else) for: a bad signature, a wrong
        issuer, a wrong audience, an expired `exp`, `alg: none` / any unsigned token, a
        missing/unresolvable `kid`, or a token with no usable `sub`. Every failure path is
        collapsed to the same exception type and a claim-free message -- a caller must not be
        able to distinguish "wrong audience" from "expired" by exception type, which would
        leak verification internals to an attacker probing the endpoint.
        """

        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            key_id = header.get("kid")
            if algorithm not in ALLOWED_ALGORITHMS or not isinstance(key_id, str) or not key_id:
                raise InvalidTokenError("unsupported or unsigned token header")
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            options = {
                "require": ["exp", "iss", "sub"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iss": True,
                "verify_aud": self._audience is not None,
                "verify_sub": True,
            }
            claims = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=[algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options=options,
                # Small clock-skew tolerance against exp/iat/nbf -- see the ported reference
                # implementation's docstring for the full rationale. 30s, not a security
                # boundary.
                leeway=30,
            )
        except (InvalidTokenError, PyJWKClientError, ValueError, TypeError) as exc:
            raise AuthenticationError(
                "invalid, expired, or unverifiable bearer token"
            ) from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError("token carries no usable subject")

        is_anonymous = claims.get(_ANONYMOUS_CLAIM) is True
        return VerifiedClaims(subject=subject, is_anonymous=is_anonymous)


@lru_cache
def get_jwt_verifier() -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(get_settings())


def parse_bearer_token(authorization_header: str | None) -> str:
    """Extract the bearer token from an `Authorization` header value.

    Raises `AuthenticationError` for a missing header, a non-`Bearer` scheme, or an empty
    token. Framework-agnostic on purpose -- no FastAPI `Request` here -- so it is usable from
    a route dependency, a test harness, or anywhere else without importing FastAPI.
    """

    if not authorization_header:
        raise AuthenticationError("missing Authorization header")
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise AuthenticationError("malformed Authorization header")
    return parts[1]


def verify_bearer_token(
    authorization_header: str | None, *, verifier: SupabaseJwtVerifier | None = None
) -> VerifiedClaims:
    """The one call a route dependency needs: header in, `VerifiedClaims` out.

    Synchronous -- `jwt.decode` and JWKS fetch are both blocking; callers on an async path
    should run this via `asyncio.to_thread` (as the ported reference implementation does)
    rather than block the event loop.
    """

    token = parse_bearer_token(authorization_header)
    return (verifier or get_jwt_verifier()).verify(token)
