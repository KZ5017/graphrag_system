from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, status


async def require_service_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    expected = request.app.state.settings.service_token.get_secret_value()
    scheme, _, supplied = (authorization or "").partition(" ")
    valid = scheme.lower() == "bearer" and secrets.compare_digest(supplied, expected)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid service token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
