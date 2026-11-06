from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.db.session import get_db
from reprolab.models.governance import DelegationEvent, ReviewDelegation
from reprolab.models.research import Investigation
from reprolab.schemas.governance import (
    ReviewDelegationIssue,
    ReviewDelegationIssuedRead,
    ReviewDelegationRead,
    ReviewDelegationRedeem,
    ReviewDelegationRedeemRead,
    ReviewDelegationRevoke,
)
from reprolab.services.governance import (
    issue_review_delegation,
    redeem_review_delegation,
    review_delegation_read,
    revoke_review_delegation,
)
from reprolab.services.record_integrity import review_read


router = APIRouter(prefix="/api/v1/investigations", tags=["review delegations"])


async def _investigation_or_404(db: AsyncSession, investigation_id: str) -> Investigation:
    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    return investigation


async def _delegation_or_404(
    db: AsyncSession,
    investigation_id: str,
    delegation_id: str,
) -> ReviewDelegation:
    delegation = await db.get(ReviewDelegation, delegation_id)
    if delegation is None or delegation.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Review delegation not found in this investigation.")
    return delegation


@router.post(
    "/{investigation_id}/review-delegations",
    response_model=ReviewDelegationIssuedRead,
    status_code=status.HTTP_201_CREATED,
)
async def issue_review_delegation_route(
    investigation_id: str,
    payload: ReviewDelegationIssue,
    db: AsyncSession = Depends(get_db),
) -> ReviewDelegationIssuedRead:
    issued = await issue_review_delegation(db, investigation_id, payload)
    return ReviewDelegationIssuedRead(
        **review_delegation_read(issued.delegation).model_dump(),
        token=issued.token,
    )


@router.get(
    "/{investigation_id}/review-delegations",
    response_model=list[ReviewDelegationRead],
)
async def list_review_delegations(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ReviewDelegationRead]:
    await _investigation_or_404(db, investigation_id)
    delegations = await db.scalars(
        select(ReviewDelegation)
        .where(ReviewDelegation.investigation_id == investigation_id)
        .order_by(ReviewDelegation.issued_at.asc())
    )
    return [review_delegation_read(delegation) for delegation in delegations.all()]


@router.get(
    "/{investigation_id}/review-delegations/{delegation_id}",
    response_model=ReviewDelegationRead,
)
async def get_review_delegation(
    investigation_id: str,
    delegation_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReviewDelegationRead:
    delegation = await _delegation_or_404(db, investigation_id, delegation_id)
    return review_delegation_read(delegation)


@router.post(
    "/{investigation_id}/review-delegations/{delegation_id}/redeem",
    response_model=ReviewDelegationRedeemRead,
    status_code=status.HTTP_201_CREATED,
)
async def redeem_review_delegation_route(
    investigation_id: str,
    delegation_id: str,
    payload: ReviewDelegationRedeem,
    db: AsyncSession = Depends(get_db),
) -> ReviewDelegationRedeemRead:
    if payload.delegation_id != delegation_id:
        raise HTTPException(status_code=409, detail="delegation_id does not match the route delegation.")
    redeemed = await redeem_review_delegation(db, investigation_id, delegation_id, payload)
    return ReviewDelegationRedeemRead(
        delegation=review_delegation_read(redeemed.delegation),
        review=await review_read(db, redeemed.review),
    )


@router.post(
    "/{investigation_id}/review-delegations/{delegation_id}/revoke",
    response_model=ReviewDelegationRead,
    status_code=status.HTTP_201_CREATED,
)
async def revoke_review_delegation_route(
    investigation_id: str,
    delegation_id: str,
    payload: ReviewDelegationRevoke,
    db: AsyncSession = Depends(get_db),
) -> ReviewDelegationRead:
    if payload.delegation_id != delegation_id:
        raise HTTPException(status_code=409, detail="delegation_id does not match the route delegation.")
    delegation = await revoke_review_delegation(db, investigation_id, delegation_id, payload)
    return review_delegation_read(delegation)


@router.get(
    "/{investigation_id}/review-delegations/{delegation_id}/events",
    response_model=list[dict[str, Any]],
)
async def list_review_delegation_events(
    investigation_id: str,
    delegation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _delegation_or_404(db, investigation_id, delegation_id)
    events = await db.scalars(
        select(DelegationEvent)
        .where(
            DelegationEvent.delegation_id == delegation_id,
            DelegationEvent.investigation_id == investigation_id,
        )
        .order_by(DelegationEvent.sequence_number.asc())
    )
    return [
        {
            "id": event.id,
            "delegation_id": event.delegation_id,
            "sequence_number": event.sequence_number,
            "event_type": event.event_type,
            "actor_role_id": event.actor_role_id,
            "reviewer_role_id": event.reviewer_role_id,
            "reason": event.reason,
            "payload": event.payload,
            "event_hash": event.event_hash,
            "previous_event_hash": event.previous_event_hash,
            "occurred_at": event.occurred_at,
        }
        for event in events.all()
    ]
