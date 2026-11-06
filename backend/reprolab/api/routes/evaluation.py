"""Scientific evaluation API routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.core.security import AuthenticatedUser, UserRole, require_role
from reprolab.db.session import get_db
from reprolab.evaluation.engine import run_scientific_evaluation
from reprolab.models.evaluation import ScientificEvaluation

router = APIRouter(prefix="/api/v1/investigations/{investigation_id}/evaluations", tags=["evaluations"])


class EvaluationCreateRequest(BaseModel):
    job_id: str | None = None
    claim_id: str | None = None
    summary_notes: str | None = None


def _serialize_evaluation(record: ScientificEvaluation) -> dict[str, Any]:
    return {
        "id": record.id,
        "investigation_id": record.investigation_id,
        "job_id": record.job_id,
        "claim_id": record.claim_id,
        "evaluation_version": record.evaluation_version,
        "status": record.status,
        "verdict": record.verdict,
        "extraction_quality_score": record.extraction_quality_score,
        "extraction_quality_breakdown": record.extraction_quality_breakdown,
        "technical_reproducibility_score": record.technical_reproducibility_score,
        "technical_reproducibility_breakdown": record.technical_reproducibility_breakdown,
        "claim_verification_score": record.claim_verification_score,
        "claim_verification_breakdown": record.claim_verification_breakdown,
        "summary_notes": record.summary_notes,
        "evaluated_at": record.evaluated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    investigation_id: str,
    payload: EvaluationCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role([UserRole.OPERATOR, UserRole.ADMIN])),
) -> dict[str, Any]:
    """Run tri-partite scientific evaluation for the investigation."""
    try:
        evaluation = await run_scientific_evaluation(
            investigation_id=investigation_id,
            db=db,
            job_id=payload.job_id,
            claim_id=payload.claim_id,
            summary_notes=payload.summary_notes,
        )
        return _serialize_evaluation(evaluation)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("")
async def list_evaluations(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role([UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN])),
) -> list[dict[str, Any]]:
    """List all scientific evaluations recorded for an investigation."""
    stmt = (
        select(ScientificEvaluation)
        .where(ScientificEvaluation.investigation_id == investigation_id)
        .order_by(ScientificEvaluation.evaluated_at.desc())
    )
    records = (await db.execute(stmt)).scalars().all()
    return [_serialize_evaluation(r) for r in records]


@router.get("/{evaluation_id}")
async def get_evaluation(
    investigation_id: str,
    evaluation_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role([UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN])),
) -> dict[str, Any]:
    """Get detailed scientific evaluation record."""
    evaluation = await db.get(ScientificEvaluation, evaluation_id)
    if not evaluation or evaluation.investigation_id != investigation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scientific evaluation not found.")
    return _serialize_evaluation(evaluation)

