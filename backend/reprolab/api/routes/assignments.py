from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.db.session import get_db
from reprolab.models.governance import AssignmentDeliverable, AssignmentEvent, RoleAssignment
from reprolab.models.research import Investigation
from reprolab.schemas.governance import (
    AssignmentCreate,
    AssignmentEventRead,
    AssignmentRead,
    AssignmentTransitionRead,
    AssignmentTransitionRequest,
    DeliverableCreate,
    DeliverableRead,
)
from reprolab.services.governance import (
    assignment_event_read,
    assignment_read,
    assignment_transition_read,
    create_assignment,
    create_deliverable,
    deliverable_read,
    transition_assignment,
)


router = APIRouter(prefix="/api/v1/investigations", tags=["assignments"])


async def _investigation_or_404(db: AsyncSession, investigation_id: str) -> Investigation:
    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    return investigation


async def _assignment_or_404(
    db: AsyncSession,
    investigation_id: str,
    assignment_id: str,
) -> RoleAssignment:
    assignment = await db.get(RoleAssignment, assignment_id)
    if assignment is None or assignment.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Assignment not found in this investigation.")
    return assignment


@router.post(
    "/{investigation_id}/assignments",
    response_model=AssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment_route(
    investigation_id: str,
    payload: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
) -> AssignmentRead:
    assignment = await create_assignment(db, investigation_id, payload)
    return assignment_read(assignment)


@router.get(
    "/{investigation_id}/assignments",
    response_model=list[AssignmentRead],
)
async def list_assignments(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[AssignmentRead]:
    await _investigation_or_404(db, investigation_id)
    assignments = await db.scalars(
        select(RoleAssignment)
        .where(RoleAssignment.investigation_id == investigation_id)
        .order_by(RoleAssignment.created_at.asc())
    )
    return [assignment_read(assignment) for assignment in assignments.all()]


@router.get(
    "/{investigation_id}/assignments/{assignment_id}",
    response_model=AssignmentRead,
)
async def get_assignment(
    investigation_id: str,
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
) -> AssignmentRead:
    assignment = await _assignment_or_404(db, investigation_id, assignment_id)
    return assignment_read(assignment)


@router.post(
    "/{investigation_id}/assignments/{assignment_id}/transition",
    response_model=AssignmentTransitionRead,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{investigation_id}/assignments/{assignment_id}/transitions",
    response_model=AssignmentTransitionRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def transition_assignment_route(
    investigation_id: str,
    assignment_id: str,
    payload: AssignmentTransitionRequest,
    db: AsyncSession = Depends(get_db),
) -> AssignmentTransitionRead:
    event = await transition_assignment(db, investigation_id, assignment_id, payload)
    return assignment_transition_read(event)


@router.post(
    "/{investigation_id}/assignments/{assignment_id}/deliverables",
    response_model=DeliverableRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment_deliverable(
    investigation_id: str,
    assignment_id: str,
    payload: DeliverableCreate,
    db: AsyncSession = Depends(get_db),
) -> DeliverableRead:
    if payload.assignment_id != assignment_id:
        raise HTTPException(status_code=409, detail="Deliverable assignment_id does not match the route assignment.")
    deliverable = await create_deliverable(db, investigation_id, payload)
    return deliverable_read(deliverable)


@router.post(
    "/{investigation_id}/deliverables",
    response_model=DeliverableRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_deliverable_route(
    investigation_id: str,
    payload: DeliverableCreate,
    db: AsyncSession = Depends(get_db),
) -> DeliverableRead:
    deliverable = await create_deliverable(db, investigation_id, payload)
    return deliverable_read(deliverable)


@router.get(
    "/{investigation_id}/assignments/{assignment_id}/deliverables",
    response_model=list[DeliverableRead],
)
async def list_assignment_deliverables(
    investigation_id: str,
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[DeliverableRead]:
    await _assignment_or_404(db, investigation_id, assignment_id)
    deliverables = await db.scalars(
        select(AssignmentDeliverable)
        .where(
            AssignmentDeliverable.assignment_id == assignment_id,
            AssignmentDeliverable.investigation_id == investigation_id,
        )
        .order_by(AssignmentDeliverable.created_at.asc())
    )
    return [deliverable_read(deliverable) for deliverable in deliverables.all()]


@router.get(
    "/{investigation_id}/assignments/{assignment_id}/events",
    response_model=list[AssignmentEventRead],
)
async def list_assignment_events(
    investigation_id: str,
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[AssignmentEventRead]:
    await _assignment_or_404(db, investigation_id, assignment_id)
    events = await db.scalars(
        select(AssignmentEvent)
        .where(
            AssignmentEvent.assignment_id == assignment_id,
            AssignmentEvent.investigation_id == investigation_id,
        )
        .order_by(AssignmentEvent.sequence_number.asc())
    )
    return [assignment_event_read(event) for event in events.all()]
