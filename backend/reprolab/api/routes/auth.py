"""Authentication and user session routes."""

from typing import Any

from fastapi import APIRouter, Depends

from reprolab.core.security import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me")
async def get_current_user_info(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return currently authenticated operator credentials and assigned role."""
    return {
        "username": user.username,
        "role": user.role.value,
        "authenticated": True,
    }
