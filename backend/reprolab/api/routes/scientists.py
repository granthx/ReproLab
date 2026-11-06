from fastapi import APIRouter, HTTPException

from reprolab.scientists.registry import get_constitutions

router = APIRouter(prefix="/api/v1/scientists", tags=["scientists"])


@router.get("")
async def list_scientists() -> list[dict]:
    return [
        {**constitution.model_dump(), "availability": "registered"}
        for constitution in get_constitutions().values()
    ]


@router.get("/{role_id}")
async def get_scientist(role_id: str) -> dict:
    constitution = get_constitutions().get(role_id)
    if constitution is None:
        raise HTTPException(status_code=404, detail="Scientist role not found.")
    return {**constitution.model_dump(), "availability": "registered"}
