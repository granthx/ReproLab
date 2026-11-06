from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.db.session import get_db
from reprolab.models.records import Finding, FindingRelation, FindingVersion, RecordReview
from reprolab.schemas.records import (
    FindingCreate,
    FindingRead,
    FindingRelationCreate,
    FindingRelationRead,
    FindingSummary,
    FindingVersionCreate,
    FindingVersionRead,
    RecordReviewCreate,
    RecordReviewRead,
)
from reprolab.services.record_integrity import (
    _not_found,
    create_finding,
    create_finding_version,
    create_relation,
    create_review,
    finding_read,
    finding_summary,
    finding_version_read,
    relation_read,
    review_read,
)


router = APIRouter(prefix="/api/v1/investigations", tags=["findings"])


async def _investigation_or_404(db: AsyncSession, investigation_id: str):
    from reprolab.models.research import Investigation

    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("Investigation not found.")
    return investigation


async def _finding_version_or_404(
    db: AsyncSession,
    investigation_id: str,
    finding_id: str,
    version_id: str,
) -> FindingVersion:
    version = await db.get(FindingVersion, version_id)
    if (
        version is None
        or version.investigation_id != investigation_id
        or version.finding_id != finding_id
    ):
        raise _not_found("Finding version not found in this investigation.")
    return version


@router.post(
    "/{investigation_id}/findings",
    response_model=FindingRead,
    status_code=201,
)
async def create_finding_route(
    investigation_id: str,
    payload: FindingCreate,
    db: AsyncSession = Depends(get_db),
) -> FindingRead:
    finding = await create_finding(db, investigation_id, payload)
    return await finding_read(db, finding)


@router.get(
    "/{investigation_id}/findings",
    response_model=list[FindingSummary],
)
async def list_findings(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[FindingSummary]:
    await _investigation_or_404(db, investigation_id)
    findings = await db.scalars(
        select(Finding)
        .where(Finding.investigation_id == investigation_id)
        .order_by(Finding.created_at.asc())
    )
    return [await finding_summary(db, finding) for finding in findings.all()]


@router.get(
    "/{investigation_id}/findings/{finding_id}",
    response_model=FindingRead,
)
async def get_finding(
    investigation_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
) -> FindingRead:
    await _investigation_or_404(db, investigation_id)
    finding = await db.get(Finding, finding_id)
    if finding is None or finding.investigation_id != investigation_id:
        raise _not_found("Finding not found in this investigation.")
    return await finding_read(db, finding)


@router.post(
    "/{investigation_id}/findings/{finding_id}/versions",
    response_model=FindingVersionRead,
    status_code=201,
)
async def create_finding_version_route(
    investigation_id: str,
    finding_id: str,
    payload: FindingVersionCreate,
    db: AsyncSession = Depends(get_db),
) -> FindingVersionRead:
    version = await create_finding_version(db, investigation_id, finding_id, payload)
    return await finding_version_read(db, version)


@router.get(
    "/{investigation_id}/findings/{finding_id}/versions/{version_id}",
    response_model=FindingVersionRead,
)
async def get_finding_version(
    investigation_id: str,
    finding_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
) -> FindingVersionRead:
    version = await _finding_version_or_404(db, investigation_id, finding_id, version_id)
    return await finding_version_read(db, version)


@router.post(
    "/{investigation_id}/findings/{finding_id}/versions/{version_id}/reviews",
    response_model=RecordReviewRead,
    status_code=201,
)
async def create_finding_review(
    investigation_id: str,
    finding_id: str,
    version_id: str,
    payload: RecordReviewCreate,
    db: AsyncSession = Depends(get_db),
) -> RecordReviewRead:
    await _finding_version_or_404(db, investigation_id, finding_id, version_id)
    review = await create_review(db, investigation_id, version_id, payload)
    return await review_read(db, review)


@router.get(
    "/{investigation_id}/findings/{finding_id}/versions/{version_id}/reviews",
    response_model=list[RecordReviewRead],
)
async def list_finding_reviews(
    investigation_id: str,
    finding_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[RecordReviewRead]:
    await _finding_version_or_404(db, investigation_id, finding_id, version_id)
    reviews = await db.scalars(
        select(RecordReview)
        .where(
            RecordReview.investigation_id == investigation_id,
            RecordReview.finding_version_id == version_id,
        )
        .order_by(RecordReview.reviewed_at.asc())
    )
    return [await review_read(db, review) for review in reviews.all()]


@router.post(
    "/{investigation_id}/finding-relations",
    response_model=FindingRelationRead,
    status_code=201,
)
async def create_finding_relation(
    investigation_id: str,
    payload: FindingRelationCreate,
    db: AsyncSession = Depends(get_db),
) -> FindingRelationRead:
    await _investigation_or_404(db, investigation_id)
    relation = await create_relation(db, investigation_id, payload)
    return await relation_read(db, relation)


@router.get(
    "/{investigation_id}/finding-relations",
    response_model=list[FindingRelationRead],
)
async def list_finding_relations(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[FindingRelationRead]:
    await _investigation_or_404(db, investigation_id)
    relations = await db.scalars(
        select(FindingRelation)
        .where(FindingRelation.investigation_id == investigation_id)
        .order_by(FindingRelation.created_at.asc())
    )
    return [await relation_read(db, relation) for relation in relations.all()]
