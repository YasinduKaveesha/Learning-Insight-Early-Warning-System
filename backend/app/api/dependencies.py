"""FastAPI dependencies (work order B6.1) -- the one place a request becomes a Principal.

Every route except `/health/*` depends on :func:`current_principal`. There is deliberately
no "optional auth" variant and no default teacher: an unauthenticated or unresolvable caller
is a 401/403, never a downgraded read of somebody's class list.

The two-step shape mirrors `app/domain/principal.py` and must not be collapsed:
`verify_bearer_token` proves the token was signed by Supabase and has not expired;
`resolve_principal` decides whether that subject may act as a teacher. A verified signature
is not an authorization decision -- an anonymous Supabase session carries a perfectly valid
one and identifies no teacher at all.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, AsyncIterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.principal_resolution import resolve_principal
from app.domain.errors import (
    AuthenticationError,
    DemoPoolExhaustedError,
    PrincipalNotAuthorizedError,
)
from app.domain.principal import Principal
from app.infrastructure import auth
from app.infrastructure.db import engine as db_engine
from app.infrastructure.settings import Settings, get_settings


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in db_engine.get_session():
        yield session


async def current_principal(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """401 for a token problem, 403 for an identity problem, 409 for an exhausted demo pool.

    The distinction matters: 401 means "your token is bad, get another"; 403 means "your
    token is fine and you are still not a teacher here". Collapsing them would tell an
    unauthorized caller to go and refresh a token that was never the problem.

    Nothing here echoes the token, the subject, or the driver error -- see the no-logging
    rule in `app/infrastructure/auth.py`.
    """

    try:
        # `verify_bearer_token` is synchronous -- `jwt.decode` and the JWKS fetch both block
        # -- so it goes to a worker thread rather than stalling the event loop for every
        # request that happens to miss the JWKS cache.
        claims = await asyncio.to_thread(auth.verify_bearer_token, authorization)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"stage": "authentication", "error": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        return await resolve_principal(session, claims, settings)
    except PrincipalNotAuthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"stage": "authorization", "error": str(exc)},
        ) from exc
    except DemoPoolExhaustedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"stage": "demo_pool", "error": str(exc)},
        ) from exc


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
DbSession = Annotated[AsyncSession, Depends(db_session)]
