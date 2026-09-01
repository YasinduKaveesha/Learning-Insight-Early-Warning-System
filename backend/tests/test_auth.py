"""JWKS verification (work order B2.3, gates 3 and 13a).

Fully self-contained -- no network, no database. Generates its own RSA keypair, signs tokens
with PyJWT directly, and stubs the JWKS lookup (`SigningKeyClient.get_signing_key_from_jwt`)
rather than reaching Supabase, so this suite runs anywhere the pinned `c3-ews` env runs.

Five separate 401 demonstrations (gate 3): bad signature, wrong issuer, wrong audience,
expired `exp`, and `alg: none`. Plus the header-level "unsigned token" case and the
"no usable sub" case, since both are also 401 by the same guard.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.domain.errors import AuthenticationError
from app.infrastructure.auth import SupabaseJwtVerifier, parse_bearer_token

ISSUER = "https://test-project.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KEY_ID = "test-key-1"


def _rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


_PRIVATE_KEY, _PUBLIC_KEY = _rsa_keypair()
_OTHER_PRIVATE_KEY, _ = _rsa_keypair()  # a different key -- for the bad-signature case


def _make_token(
    *,
    private_key=_PRIVATE_KEY,
    algorithm: str = "RS256",
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    subject: str = "11111111-1111-1111-1111-111111111111",
    exp_offset_seconds: int = 3600,
    is_anonymous: bool | None = None,
    key_id: str | None = KEY_ID,
    headers: dict | None = None,
) -> str:
    now = int(time.time())
    claims = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + exp_offset_seconds,
    }
    if is_anonymous is not None:
        claims["is_anonymous"] = is_anonymous
    header = {"alg": algorithm}
    if key_id is not None:
        header["kid"] = key_id
    if headers:
        header.update(headers)
    if algorithm == "none":
        # PyJWT refuses to encode alg=none with a key; encode the pieces by hand.
        import base64
        import json

        def _b64(payload: dict) -> str:
            raw = json.dumps(payload, separators=(",", ":")).encode()
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        return f"{_b64(header)}.{_b64(claims)}."
    return jwt.encode(claims, private_key, algorithm=algorithm, headers=header)


class _StubJwksClient:
    """Always returns the test RSA public key, regardless of `kid` -- the verifier's own
    header check (algorithm allow-list, `kid` presence) runs before this is ever consulted."""

    def __init__(self, key=_PUBLIC_KEY):
        self._key = key

    def get_signing_key_from_jwt(self, token: str):
        return SimpleNamespace(key=self._key)


def _verifier(jwks_client=None) -> SupabaseJwtVerifier:
    settings = SimpleNamespace(
        supabase_jwt_issuer=ISSUER,
        supabase_jwt_audience=AUDIENCE,
        supabase_jwks_url="https://test-project.supabase.co/auth/v1/.well-known/jwks.json",
        supabase_jwks_cache_ttl_seconds=300,
    )
    return SupabaseJwtVerifier(settings, jwks_client=jwks_client or _StubJwksClient())


# ==========================================================================================
# Gate 3 -- five separate rejection demonstrations, each 401 (AuthenticationError).
# ==========================================================================================


def test_gate3_valid_token_is_accepted() -> None:
    """Control case: proves the harness itself is not broken before trusting any rejection."""

    verifier = _verifier()
    claims = verifier.verify(_make_token())
    assert claims.subject == "11111111-1111-1111-1111-111111111111"
    assert claims.is_anonymous is False


def test_gate3_bad_signature_is_rejected() -> None:
    # Signed with a DIFFERENT private key; the stub JWKS client still serves the real public
    # key, so this fails signature verification, not "key not found".
    token = _make_token(private_key=_OTHER_PRIVATE_KEY)
    with pytest.raises(AuthenticationError):
        _verifier().verify(token)


def test_gate3_wrong_issuer_is_rejected() -> None:
    token = _make_token(issuer="https://an-attacker-project.supabase.co/auth/v1")
    with pytest.raises(AuthenticationError):
        _verifier().verify(token)


def test_gate3_wrong_audience_is_rejected() -> None:
    token = _make_token(audience="some-other-audience")
    with pytest.raises(AuthenticationError):
        _verifier().verify(token)


def test_gate3_expired_token_is_rejected() -> None:
    # Well past the verifier's 30s leeway.
    token = _make_token(exp_offset_seconds=-3600)
    with pytest.raises(AuthenticationError):
        _verifier().verify(token)


def test_gate3_alg_none_is_rejected() -> None:
    token = _make_token(algorithm="none")
    with pytest.raises(AuthenticationError):
        _verifier().verify(token)


# ==========================================================================================
# Additional header-level guards the same 401 path covers.
# ==========================================================================================


def test_unsupported_algorithm_is_rejected() -> None:
    # HS256 is a symmetric algorithm Supabase never issues; PyJWT would happily HMAC-sign it
    # with an arbitrary string, so this is the "attacker picks alg" downgrade case.
    token = jwt.encode(
        {
            "sub": "11111111-1111-1111-1111-111111111111",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": int(time.time()) + 3600,
        },
        "any-secret-an-attacker-could-guess",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        _verifier().verify(token)


def test_missing_kid_is_rejected() -> None:
    token = _make_token(key_id=None)
    with pytest.raises(AuthenticationError):
        _verifier().verify(token)


def test_missing_subject_is_rejected() -> None:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 3600}
    token = jwt.encode(
        claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": KEY_ID}
    )
    with pytest.raises(AuthenticationError):
        _verifier().verify(token)


def test_is_anonymous_claim_is_surfaced() -> None:
    token = _make_token(is_anonymous=True)
    claims = _verifier().verify(token)
    assert claims.is_anonymous is True


def test_is_anonymous_defaults_false_when_absent() -> None:
    token = _make_token()  # no is_anonymous claim at all
    claims = _verifier().verify(token)
    assert claims.is_anonymous is False


# ==========================================================================================
# parse_bearer_token -- header parsing, independent of signature verification.
# ==========================================================================================


def test_parse_bearer_token_missing_header() -> None:
    with pytest.raises(AuthenticationError):
        parse_bearer_token(None)


def test_parse_bearer_token_wrong_scheme() -> None:
    with pytest.raises(AuthenticationError):
        parse_bearer_token("Basic abc123")


def test_parse_bearer_token_accepts_bearer() -> None:
    assert parse_bearer_token("Bearer sometoken") == "sometoken"
