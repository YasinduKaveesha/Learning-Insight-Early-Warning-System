"""Principal types for JWT verification and identity resolution (work order B2.3).

Two distinct objects, deliberately not collapsed into one:

* :class:`VerifiedClaims` -- the output of signature verification
  (`app/infrastructure/auth.py`). Proves the token was signed by Supabase and has not
  expired. It is NOT an authorization decision.
* :class:`Principal` -- the output of `app.application.principal_resolution.resolve_principal`.
  The one and only thing that means "this caller may act as this teacher". A verified JWT
  signature is never treated as an authorized teacher by itself -- see `plan/backend_plan.md`
  section 8 ("Auth") and the B2.3 work order traps.

Neither type carries a raw token, and callers must not log ``subject`` -- see the module
docstring in `app/infrastructure/auth.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class VerifiedClaims:
    """A signature-, issuer-, audience- and expiry-verified token's identity claims.

    ``subject`` is the JWT ``sub`` -- durable but NOT a resolved teacher identity: an
    anonymous Supabase session has a real, verifiable ``sub`` that identifies no teacher at
    all. ``is_anonymous`` mirrors Supabase's own anonymous-session claim (`is_anonymous: true`
    at the top level of the token) so `resolve_principal` can route without re-deciding what
    "anonymous" means.
    """

    subject: str
    is_anonymous: bool


PrincipalResolution = Literal["real", "demo"]


@dataclass(frozen=True)
class Principal:
    """The resolved teacher identity -- the sole output of `resolve_principal`.

    ``resolution`` records which path produced it (`"real"` via `app_users` ->
    `teacher_profiles`, or `"demo"` via `t3_teacher_bindings`) purely for observability; no
    caller should branch on it -- a `teacher_profile_id` is a `teacher_profile_id` regardless
    of how it was resolved.
    """

    teacher_profile_id: uuid.UUID
    resolution: PrincipalResolution
