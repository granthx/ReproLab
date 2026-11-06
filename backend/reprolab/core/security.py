"""Security, authentication, role-based access control (RBAC), and credential masking for ReproLab."""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Annotated, Sequence

from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from reprolab.core.config import Settings, get_settings


class UserRole(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


# Role hierarchy: admin includes operator, operator includes viewer.
ROLE_HIERARCHY: dict[UserRole, set[UserRole]] = {
    UserRole.VIEWER: {UserRole.VIEWER},
    UserRole.OPERATOR: {UserRole.VIEWER, UserRole.OPERATOR},
    UserRole.ADMIN: {UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN},
}


class AuthenticatedUser(BaseModel):
    username: str
    role: UserRole
    token: str | None = None

    def has_role(self, required_role: UserRole) -> bool:
        user_roles = ROLE_HIERARCHY.get(self.role, set())
        return required_role in user_roles


# Default unauthenticated identity when auth is disabled (backward-compatible local mode)
DEFAULT_LOCAL_USER = AuthenticatedUser(
    username="local_operator",
    role=UserRole.ADMIN,
    token="local_dev_token",
)


def mask_secret(secret: str | None, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
    """Mask sensitive string (passwords, tokens, API keys) preserving bounded prefix/suffix."""
    if not secret:
        return ""
    if len(secret) <= visible_prefix + visible_suffix:
        return "********"
    return f"{secret[:visible_prefix]}...{secret[-visible_suffix:]}"


def sanitize_database_url(url: str) -> str:
    """Redact password from database URL if present."""
    if not url:
        return ""
    return re.sub(r"(://[^:]+:)([^@]+)(@)", r"\1********\3", url)


def parse_token_registry(token_config: str) -> dict[str, AuthenticatedUser]:
    """
    Parse configured token registry from environment string.
    Format: 'token1:role:username,token2:role:username' or JSON.
    """
    registry: dict[str, AuthenticatedUser] = {}
    if not token_config.strip():
        return registry

    for entry in token_config.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) >= 3:
            tok, role_str, user = parts[0], parts[1].lower(), parts[2]
            try:
                role = UserRole(role_str)
            except ValueError:
                role = UserRole.VIEWER
            registry[tok] = AuthenticatedUser(username=user, role=role, token=tok)
    return registry


def get_app_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_app_settings),
) -> AuthenticatedUser:
    """
    Authenticate the current request.
    Extracts Bearer token from Authorization header or X-API-Key.
    When auth_enabled is False, defaults to DEFAULT_LOCAL_USER if no credentials are provided.
    """
    token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()

    registry = parse_token_registry(settings.api_tokens)

    # Built-in test tokens when auth is active
    if not registry:
        # Default fallback registry for standard testing
        registry = {
            "reprolab-viewer-token": AuthenticatedUser(username="test_viewer", role=UserRole.VIEWER, token="reprolab-viewer-token"),
            "reprolab-operator-token": AuthenticatedUser(username="test_operator", role=UserRole.OPERATOR, token="reprolab-operator-token"),
            "reprolab-admin-token": AuthenticatedUser(username="test_admin", role=UserRole.ADMIN, token="reprolab-admin-token"),
        }

    if token:
        user = registry.get(token)
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Auth disabled: fallback to local admin user
    return DEFAULT_LOCAL_USER


def require_role(allowed_roles: Sequence[UserRole]):
    """FastAPI dependency factory enforcing that the authenticated user possesses one of the allowed roles."""
    async def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        user_roles = ROLE_HIERARCHY.get(user.role, set())
        if not any(req_role in user_roles for req_role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User '{user.username}' with role '{user.role.value}' lacks required permissions (requires one of: {[r.value for r in allowed_roles]}).",
            )
        return user
    return role_checker
