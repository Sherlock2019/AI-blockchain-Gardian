"""Mock authentication, real authorisation.

The caller's identity is whatever `X-User-Id` says. That is a stand-in for an
identity provider and is trivially spoofable: see docs/SECURITY.md. What
happens *after* identity is established (role checks, approval limits,
four-eyes) is enforced for real.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends, Header, Request

from app.container import AppContainer, Services
from app.errors import ForbiddenError, UnauthenticatedError
from app.models.db import UserRow


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[no-any-return]


def get_services(container: AppContainer = Depends(get_container)) -> Iterator[Services]:
    session = container.db.new_session()
    try:
        yield container.services(session)
    finally:
        session.close()


def current_user(
    container: AppContainer = Depends(get_container),
    services: Services = Depends(get_services),
    x_user_id: str | None = Header(default=None, max_length=64),
) -> UserRow:
    if not x_user_id:
        raise UnauthenticatedError("X-User-Id header is required.")
    user = services.session.get(UserRow, x_user_id)
    if user is None or not user.active:
        raise UnauthenticatedError("Unknown or inactive user.")
    container.rate_limiter.check(user.id)
    return user


def require_roles(*roles: str) -> Callable[[UserRow], UserRow]:
    def dependency(user: UserRow = Depends(current_user)) -> UserRow:
        if user.role not in roles:
            raise ForbiddenError(f"Role {user.role} may not perform this operation.")
        return user

    return dependency
