"""Transactional services for Stage 3 assignments and review delegation.

The service layer is deliberately the only place that changes assignment or
delegation lifecycle state.  API routes remain investigation-scoped and only
translate persisted records into the public schemas.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.governance.contracts import (
    ContractStatus,
    MANUAL_INPUT_CONTRACT,
    MANUAL_OUTPUT_CONTRACTS,
    MANUAL_REVIEW_ROLES,
    ROLE_MAX_MODEL_CALLS,
    list_role_contracts,
    resolve_contract,
    resolve_role_contract,
)
from reprolab.models.governance import (
    AssignmentDeliverable,
    AssignmentEvent,
    DelegationEvent,
    ReviewDelegation,
    RoleAssignment,
)
from reprolab.models.records import FindingVersion, ScientistConstitutionSnapshot
from reprolab.models.research import Investigation
from reprolab.schemas.governance import (
    AssignmentCreate,
    AssignmentBudget,
    AssignmentEventRead,
    AssignmentEventType,
    AssignmentRead,
    AssignmentStatus,
    AssignmentTransitionRead,
    AssignmentTransitionRequest,
    DeliverableCreate,
    DeliverableRead,
    ManualDeliverableContent,
    AbstentionOutput,
    HandoffOutput,
    DisagreementOutput,
    ReviewDelegationIssue,
    ReviewDelegationRead,
    ReviewDelegationRedeem,
    ReviewDelegationStatus,
    ReviewDelegationTarget,
    ReviewDelegationRevoke,
    canonical_json_hash,
    parse_deliverable_content,
)
from reprolab.schemas.records import RecordReviewCreate
from reprolab.scientists.registry import get_constitutions
from reprolab.services.governance_references import validate_references
from reprolab.services.record_integrity import (
    create_attribution as _create_record_attribution,
    create_review,
)


_ALLOWED_ASSIGNMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "assigned": frozenset({"in_progress", "blocked", "not_required"}),
    "in_progress": frozenset(
        {"completed", "revoked", "blocked", "abstained", "handed_off", "disputed"}
    ),
    "completed": frozenset({"revoked"}),
    "revoked": frozenset(),
    "blocked": frozenset(),
    "not_required": frozenset(),
    "abstained": frozenset(),
    "handed_off": frozenset(),
    "disputed": frozenset(),
}

_ASSIGNMENT_EVENT_TYPES: dict[str, str] = {
    "in_progress": "started",
    "completed": "completed",
    "revoked": "revoked",
    "blocked": "blocked",
    "not_required": "not_required",
    "abstained": "abstained",
    "handed_off": "handed_off",
    "disputed": "disputed",
}

_ZERO_BUDGET = {"max_model_calls": 0, "max_input_tokens": 0, "max_output_tokens": 0}


def _atomic_mutation(operation):
    """Own the entire transaction, including validation, autoflush and failures.

    Services are transaction boundaries, not composable commit=False helpers.
    Refresh return values before commit so a failed refresh also rolls back.
    """

    @wraps(operation)
    async def wrapped(db, *args, **kwargs):
        try:
            result = await operation(db, *args, **kwargs)
            await db.commit()
            return result
        except IntegrityError as exc:
            await db.rollback()
            raise _conflict("Governance mutation conflicts with stored record integrity.") from exc
        except (ValidationError, ValueError) as exc:
            await db.rollback()
            raise _conflict("Governance record or request failed bounded contract validation.") from exc
        except BaseException:
            await db.rollback()
            raise

    return wrapped


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _investigation_or_404(db: AsyncSession, investigation_id: str) -> Investigation:
    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("Investigation not found.")
    return investigation


async def _assignment_or_404(
    db: AsyncSession,
    investigation_id: str,
    assignment_id: str,
    *,
    lock: bool = False,
) -> RoleAssignment:
    statement = select(RoleAssignment).where(
        RoleAssignment.id == assignment_id,
        RoleAssignment.investigation_id == investigation_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    assignment = await db.scalar(statement)
    if assignment is None:
        raise _not_found("Assignment not found in this investigation.")
    return assignment


async def _delegation_or_404(
    db: AsyncSession,
    investigation_id: str,
    delegation_id: str,
    *,
    lock: bool = False,
) -> ReviewDelegation:
    statement = select(ReviewDelegation).where(
        ReviewDelegation.id == delegation_id,
        ReviewDelegation.investigation_id == investigation_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    delegation = await db.scalar(statement)
    if delegation is None:
        raise _not_found("Review delegation not found in this investigation.")
    return delegation


async def _registered_snapshot(
    db: AsyncSession,
    role_id: str,
    constitution_version: str | None,
    constitution_hash: str | None,
):
    constitution = get_constitutions().get(role_id)
    if constitution is None:
        raise _conflict("Assignment role is not a registered scientist role.")
    content = constitution.model_dump(mode="json")
    current_hash = canonical_json_hash(content)
    if constitution_version is not None and constitution_version != constitution.version:
        raise _conflict("Assignment constitution_version does not match the registered constitution.")
    if constitution_hash is not None and constitution_hash != current_hash:
        raise _conflict("Assignment constitution_hash does not match the registered constitution.")

    snapshot = await db.scalar(
        select(ScientistConstitutionSnapshot).where(
            ScientistConstitutionSnapshot.role_id == role_id,
            ScientistConstitutionSnapshot.constitution_version == constitution.version,
            ScientistConstitutionSnapshot.constitution_hash == current_hash,
        ).execution_options(populate_existing=True)
    )
    if snapshot is None:
        snapshot = ScientistConstitutionSnapshot(
            id=str(uuid4()),
            role_id=role_id,
            constitution_version=constitution.version,
            constitution_json=content,
            constitution_hash=current_hash,
        )
        db.add(snapshot)
        await db.flush()
    _check_snapshot(snapshot)
    return snapshot


def _check_snapshot(snapshot):
    content = snapshot.constitution_json
    if (
        not isinstance(content, dict)
        or canonical_json_hash(content) != snapshot.constitution_hash
        or content.get("role_id") != snapshot.role_id
        or content.get("version") != snapshot.constitution_version
    ):
        raise _conflict("Pinned constitution snapshot canonical integrity is invalid.")


async def create_attribution(db, investigation_id, payload):
    if payload.associated_role_id is not None:
        if not list_role_contracts(payload.associated_role_id):
            raise _conflict("Attribution role is outside the static governance registry.")
        await _registered_snapshot(db, payload.associated_role_id, None, None)
    return await _create_record_attribution(db, investigation_id, payload)


async def _validate_assignment(db, assignment, *, require_unexpired=True):
    """Use the pinned historical snapshot, never substitute current YAML."""

    contract = resolve_role_contract(assignment.role_id, assignment.task_kind)
    if contract.status is not ContractStatus.AVAILABLE:
        raise _conflict("Assignment does not have an available manual task contract.")
    if assignment.input_contract not in {None, MANUAL_INPUT_CONTRACT}:
        raise _conflict("Assignment input contract is not a manual reference contract.")
    if assignment.output_contract is not None and assignment.output_contract not in MANUAL_OUTPUT_CONTRACTS:
        raise _conflict("Assignment output contract is not a manual output contract.")
    snapshot = await db.scalar(
        select(ScientistConstitutionSnapshot).where(
            ScientistConstitutionSnapshot.role_id == assignment.role_id,
            ScientistConstitutionSnapshot.constitution_version == assignment.constitution_version,
            ScientistConstitutionSnapshot.constitution_hash == assignment.constitution_hash,
        ).execution_options(populate_existing=True)
    )
    if snapshot is None:
        raise _conflict("Pinned constitution snapshot is missing.")
    _check_snapshot(snapshot)
    _validate_budget(assignment.role_id, assignment.budget)
    if require_unexpired and assignment.expires_at is not None and _as_utc(assignment.expires_at) <= _now():
        raise _conflict("Assignment has expired.")
    await validate_references(db, assignment.investigation_id, assignment.input_references)


def _validate_budget(role_id, budget):
    parsed = AssignmentBudget.model_validate(budget or _ZERO_BUDGET)
    if parsed.max_model_calls > ROLE_MAX_MODEL_CALLS[role_id]:
        raise _conflict("Requested model-call ceiling exceeds the static role maximum.")
    return parsed.model_dump(mode="json")


def _resolve_assignment_contracts(payload: AssignmentCreate) -> tuple[Any, list[str]]:
    """Resolve the reviewed role/task mapping and any capability blocks."""

    if payload.task_kind is None:
        role_contracts = list_role_contracts(payload.role_id)
        if len(role_contracts) != 1:
            raise _conflict("Assignment requires an explicit registered role/task contract mapping.")
        role_contract = role_contracts[0]
    else:
        role_contract = resolve_role_contract(payload.role_id, payload.task_kind)

    if role_contract.status is ContractStatus.UNSUPPORTED_CONTRACT:
        raise _conflict(
            f"No registered governance contract exists for role {payload.role_id!r} "
            f"and task {payload.task_kind!r}."
        )

    blocked: list[str] = []
    if role_contract.status is ContractStatus.BLOCKED_CAPABILITY:
        blocked.append(
            f"role/task contract {role_contract.contract_id!r} requires blocked capability "
            f"{role_contract.capability or 'unknown'}"
        )

    resolved_role_contract = resolve_contract(role_contract.contract_id)
    if resolved_role_contract.status is ContractStatus.UNSUPPORTED_CONTRACT:
        raise _conflict(f"Assignment role/task contract {role_contract.contract_id!r} is unknown.")
    if resolved_role_contract.status is ContractStatus.BLOCKED_CAPABILITY:
        blocked.append(
            f"governance contract {resolved_role_contract.contract_id!r} is blocked because "
            f"capability {resolved_role_contract.capability or 'unknown'} is unavailable"
        )

    for field_name in ("input_contract", "output_contract"):
        contract_id = getattr(payload, field_name)
        if contract_id is None:
            continue
        contract = resolve_contract(contract_id)
        if contract.status is ContractStatus.UNSUPPORTED_CONTRACT:
            raise _conflict(f"Unknown governance contract {contract_id!r}.")
        if contract.status is ContractStatus.BLOCKED_CAPABILITY:
            blocked.append(
                f"{field_name} {contract_id!r} is blocked because capability "
                f"{contract.capability or 'unknown'} is unavailable"
            )
        elif (
            field_name == "input_contract" and contract.contract_id != MANUAL_INPUT_CONTRACT
        ) or (
            field_name == "output_contract" and contract.contract_id not in MANUAL_OUTPUT_CONTRACTS
        ):
            raise _conflict(f"{field_name} must describe bounded manual records, not API operations.")

    return role_contract, blocked


def _assignment_event_hash(
    *,
    assignment_id: str,
    investigation_id: str,
    sequence_number: int,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    actor_role_id: str | None,
    attribution_id: str,
    reason: str | None,
    payload: dict[str, Any],
    previous_event_hash: str | None,
    occurred_at: datetime,
) -> str:
    return canonical_json_hash(
        {
            "assignment_id": assignment_id,
            "investigation_id": investigation_id,
            "sequence_number": sequence_number,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "actor_role_id": actor_role_id,
            "attribution_id": attribution_id,
            "reason": reason,
            "payload": payload,
            "previous_event_hash": previous_event_hash,
            "occurred_at": _as_utc(occurred_at).isoformat(),
        }
    )


async def _append_assignment_event(
    db: AsyncSession,
    assignment: RoleAssignment,
    *,
    event_type: str,
    attribution_id: str,
    from_status: str | None,
    to_status: str | None,
    actor_role_id: str | None,
    reason: str | None,
    payload: dict[str, Any],
) -> AssignmentEvent:
    previous_event_hash = assignment.last_event_hash
    sequence_number = int(
        await db.scalar(
            select(func.max(AssignmentEvent.sequence_number)).where(
                AssignmentEvent.assignment_id == assignment.id
            )
        )
        or 0
    ) + 1
    occurred_at = _now()
    event_hash = _assignment_event_hash(
        assignment_id=assignment.id,
        investigation_id=assignment.investigation_id,
        sequence_number=sequence_number,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_role_id=actor_role_id,
        attribution_id=attribution_id,
        reason=reason,
        payload=payload,
        previous_event_hash=previous_event_hash,
        occurred_at=occurred_at,
    )
    event = AssignmentEvent(
        id=str(uuid4()),
        assignment_id=assignment.id,
        investigation_id=assignment.investigation_id,
        sequence_number=sequence_number,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_role_id=actor_role_id,
        attribution_id=attribution_id,
        reason=reason,
        payload=payload,
        event_hash=event_hash,
        previous_event_hash=previous_event_hash,
        occurred_at=occurred_at,
    )
    db.add(event)
    assignment.last_event_hash = event_hash
    await db.flush()
    return event


@_atomic_mutation
async def create_assignment(
    db: AsyncSession,
    investigation_id: str,
    payload: AssignmentCreate,
) -> RoleAssignment:
    await _investigation_or_404(db, investigation_id)
    if payload.investigation_id is not None and payload.investigation_id != investigation_id:
        raise _conflict("Assignment investigation_id does not match the route investigation.")
    role_contract, blocked_reasons = _resolve_assignment_contracts(payload)
    budget = _validate_budget(payload.role_id, payload.budget)
    if payload.expires_at is not None and _as_utc(payload.expires_at) <= _now():
        raise _conflict("Assignment expires_at must be in the future.")
    await validate_references(db, investigation_id, payload.input_references)
    snapshot = await _registered_snapshot(
        db,
        payload.role_id,
        payload.constitution_version,
        payload.constitution_hash,
    )
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    assignment = RoleAssignment(
        id=str(uuid4()),
        investigation_id=investigation_id,
        role_id=payload.role_id,
        task_kind=role_contract.task_kind,
        constitution_version=snapshot.constitution_version,
        constitution_hash=snapshot.constitution_hash,
        objective=payload.objective,
        input_contract=resolve_contract(payload.input_contract or MANUAL_INPUT_CONTRACT).contract_id,
        output_contract=resolve_contract(payload.output_contract or "deliverable").contract_id,
        input_references=[reference.model_dump(mode="json") for reference in payload.input_references],
        requested_by=payload.requested_by,
        budget=budget,
        status=AssignmentStatus.ASSIGNED.value,
        lifecycle_version=1,
        created_by_attribution_id=attribution.id,
        expires_at=_as_utc(payload.expires_at) if payload.expires_at else None,
    )
    db.add(assignment)
    await db.flush()

    await _append_assignment_event(
        db,
        assignment,
        event_type=AssignmentEventType.CREATED.value,
        attribution_id=attribution.id,
        from_status=None,
        to_status=AssignmentStatus.ASSIGNED.value,
        actor_role_id=payload.attribution.associated_role_id,
        reason=None,
        payload={
            "task_kind": role_contract.task_kind,
            "resolved_contract_id": role_contract.contract_id,
            "resolved_input_schema": role_contract.input_schema,
            "resolved_output_schema": role_contract.output_schema,
            "capability": role_contract.capability,
            "contract_status": role_contract.status.value,
            "input_contract": assignment.input_contract,
            "output_contract": assignment.output_contract,
            "requested_budget": budget,
            "effective_runtime_budget": dict(_ZERO_BUDGET),
            "role_max_model_calls": ROLE_MAX_MODEL_CALLS[payload.role_id],
            "entry_method": "manual_entry",
        },
    )

    if blocked_reasons:
        blocked_reason = "; ".join(blocked_reasons)
        assignment.status = AssignmentStatus.BLOCKED.value
        assignment.blocked_reason = blocked_reason
        assignment.lifecycle_version = 2
        await _append_assignment_event(
            db,
            assignment,
            event_type=AssignmentEventType.BLOCKED.value,
            attribution_id=attribution.id,
            from_status=AssignmentStatus.ASSIGNED.value,
            to_status=AssignmentStatus.BLOCKED.value,
            actor_role_id=payload.attribution.associated_role_id,
            reason=blocked_reason,
            payload={"capabilities": blocked_reasons},
        )

    await db.refresh(assignment)
    return assignment


async def _validate_output(db, assignment, schema_name, content, content_hash, references):
    parsed = parse_deliverable_content(schema_name, content)
    schema_id = resolve_contract(schema_name).contract_id
    if assignment.output_contract not in {None, "deliverable", schema_id}:
        raise _conflict("Deliverable does not match the assignment output contract.")
    if canonical_json_hash(content) != content_hash:
        raise _conflict("Deliverable content_hash does not match canonical content.")
    if isinstance(parsed, ManualDeliverableContent):
        if parsed.kind != assignment.task_kind:
            raise _conflict("Deliverable kind does not match the assignment task.")
    elif parsed.assignment_id != assignment.id or parsed.role_id != assignment.role_id:
        raise _conflict("Typed output must match the assignment and its role.")
    await validate_references(db, assignment.investigation_id, references)
    await validate_references(db, assignment.investigation_id, parsed.input_references)
    if isinstance(parsed, AbstentionOutput):
        await validate_references(db, assignment.investigation_id, parsed.missing_references)
    if isinstance(parsed, DisagreementOutput):
        await validate_references(db, assignment.investigation_id, parsed.basis_references)
        if parsed.requested_review_role_id is not None and parsed.requested_review_role_id not in MANUAL_REVIEW_ROLES:
            raise _conflict("Disagreement review requires a statically allowed manual review role.")
    if isinstance(parsed, HandoffOutput):
        if not any(
            item.status is ContractStatus.AVAILABLE
            for item in list_role_contracts(parsed.target_role_id)
        ):
            raise _conflict("Handoff target requires a statically available manual role.")
        if len(set(parsed.preserved_disagreement_ids)) != len(parsed.preserved_disagreement_ids):
            raise _conflict("Preserved disagreement IDs must be unique.")
        for record_id in parsed.preserved_disagreement_ids:
            record = await db.scalar(select(AssignmentDeliverable).where(
                AssignmentDeliverable.id == record_id,
                AssignmentDeliverable.investigation_id == assignment.investigation_id,
            ).execution_options(populate_existing=True))
            if record is None or record.status != "submitted" or resolve_contract(record.schema_name).contract_id != "disagreement":
                raise _conflict("Preserved disagreement must identify a submitted disagreement deliverable.")
            owner = await _assignment_or_404(db, assignment.investigation_id, record.assignment_id)
            await _validate_output(db, owner, record.schema_name, record.content, record.content_hash, record.input_references)
    return parsed


@_atomic_mutation
async def transition_assignment(
    db: AsyncSession,
    investigation_id: str,
    assignment_id: str,
    payload: AssignmentTransitionRequest,
) -> AssignmentEvent:
    await _investigation_or_404(db, investigation_id)
    if payload.assignment_id is not None and payload.assignment_id != assignment_id:
        raise _conflict("Transition assignment_id does not match the route assignment.")
    assignment = await _assignment_or_404(db, investigation_id, assignment_id, lock=True)
    request = payload.model_dump(mode="json")
    request["assignment_id"] = assignment_id
    fingerprint = canonical_json_hash(request)
    if payload.idempotency_key is not None:
        prior_events = await db.scalars(select(AssignmentEvent).where(
            AssignmentEvent.assignment_id == assignment_id,
            AssignmentEvent.investigation_id == investigation_id,
        ).execution_options(populate_existing=True))
        for prior in prior_events:
            if prior.payload.get("idempotency_key") == payload.idempotency_key:
                if prior.payload.get("request_fingerprint") != fingerprint:
                    raise _conflict("Transition idempotency key was already used for a different request.")
                return prior
    actual_status = assignment.status
    requested_from = payload.from_status.value
    requested_to = payload.to_status.value
    if actual_status != requested_from:
        raise _conflict(
            f"Assignment is {actual_status!r}; expected transition from {requested_from!r}."
        )
    if assignment.lifecycle_version != payload.expected_lifecycle_version:
        raise _conflict("Assignment lifecycle version is stale; reload before transitioning.")
    if requested_to not in _ALLOWED_ASSIGNMENT_TRANSITIONS.get(actual_status, frozenset()):
        raise _conflict(f"Invalid assignment transition: {actual_status} -> {requested_to}.")
    if payload.actor_role_id is not None and not list_role_contracts(payload.actor_role_id):
        raise _conflict("Transition actor_role_id is not a registered scientist role.")

    await _validate_assignment(db, assignment, require_unexpired=requested_to != "revoked")
    outcome = None
    required_schema = {
        "completed": "deliverable", "abstained": "abstention",
        "handed_off": "handoff", "disputed": "disagreement",
    }.get(requested_to)
    if required_schema is not None:
        deliverables = await db.scalars(
            select(AssignmentDeliverable).where(
                AssignmentDeliverable.assignment_id == assignment.id,
                AssignmentDeliverable.investigation_id == investigation_id,
                AssignmentDeliverable.status == "submitted",
            ).order_by(AssignmentDeliverable.created_at.desc(), AssignmentDeliverable.id)
            .execution_options(populate_existing=True)
        )
        for deliverable in deliverables.all():
            if resolve_contract(deliverable.schema_name).contract_id != required_schema:
                continue
            await _validate_output(db, assignment, deliverable.schema_name, deliverable.content,
                                   deliverable.content_hash, deliverable.input_references)
            outcome = {"deliverable_id": deliverable.id, "content_hash": deliverable.content_hash,
                       "schema_name": required_schema}
            break
        if outcome is None:
            raise _conflict(f"{requested_to} requires a valid submitted {required_schema} deliverable.")

    attribution = await create_attribution(db, investigation_id, payload.attribution)
    next_version = assignment.lifecycle_version + 1
    assignment.status = requested_to
    assignment.lifecycle_version = next_version
    assignment.updated_at = _now()
    if requested_to == AssignmentStatus.BLOCKED.value:
        assignment.blocked_reason = payload.reason
    elif requested_to == AssignmentStatus.NOT_REQUIRED.value:
        assignment.not_required_reason = payload.reason
    elif requested_to == AssignmentStatus.REVOKED.value:
        assignment.revoked_reason = payload.reason

    event = await _append_assignment_event(
        db,
        assignment,
        event_type=_ASSIGNMENT_EVENT_TYPES[requested_to],
        attribution_id=attribution.id,
        from_status=actual_status,
        to_status=requested_to,
        actor_role_id=payload.actor_role_id,
        reason=payload.reason,
        payload={
            "expected_lifecycle_version": payload.expected_lifecycle_version,
            "lifecycle_version": next_version,
            "idempotency_key": payload.idempotency_key,
            "request_fingerprint": fingerprint,
            "outcome": outcome,
        },
    )
    await db.refresh(event)
    return event


@_atomic_mutation
async def create_deliverable(
    db: AsyncSession,
    investigation_id: str,
    payload: DeliverableCreate,
) -> AssignmentDeliverable:
    await _investigation_or_404(db, investigation_id)
    assignment = await _assignment_or_404(db, investigation_id, payload.assignment_id, lock=True)
    if assignment.status != AssignmentStatus.IN_PROGRESS.value:
        raise _conflict("Deliverables may only be submitted for in_progress assignments.")
    await _validate_assignment(db, assignment)
    await _validate_output(db, assignment, payload.schema_name, payload.content,
                           payload.content_hash, payload.input_references)

    attribution = await create_attribution(db, investigation_id, payload.attribution)
    deliverable = AssignmentDeliverable(
        id=str(uuid4()),
        assignment_id=assignment.id,
        investigation_id=investigation_id,
        kind=payload.kind.value,
        schema_name=resolve_contract(payload.schema_name).contract_id,
        status="submitted",
        content=payload.content,
        content_hash=payload.content_hash,
        input_references=[reference.model_dump(mode="json") for reference in payload.input_references],
        limitations=[limitation for limitation in payload.limitations],
        created_by_attribution_id=attribution.id,
    )
    db.add(deliverable)
    await db.flush()
    await _append_assignment_event(
        db,
        assignment,
        event_type=AssignmentEventType.DELIVERABLE_SUBMITTED.value,
        attribution_id=attribution.id,
        from_status=AssignmentStatus.IN_PROGRESS.value,
        to_status=AssignmentStatus.IN_PROGRESS.value,
        actor_role_id=payload.attribution.associated_role_id,
        reason=None,
        payload={
            "deliverable_id": deliverable.id,
            "content_hash": deliverable.content_hash,
            "schema_name": deliverable.schema_name,
        },
    )
    assignment.updated_at = _now()
    await db.flush()
    await db.refresh(deliverable)
    return deliverable


def _delegation_event_hash(
    *,
    delegation: ReviewDelegation,
    sequence_number: int,
    event_type: str,
    actor_role_id: str | None,
    reviewer_role_id: str | None,
    attribution_id: str,
    reason: str | None,
    payload: dict[str, Any],
    previous_event_hash: str | None,
    occurred_at: datetime,
) -> str:
    return canonical_json_hash(
        {
            "delegation_id": delegation.id,
            "assignment_id": delegation.assignment_id,
            "investigation_id": delegation.investigation_id,
            "delegation_hash": delegation.delegation_hash,
            "sequence_number": sequence_number,
            "event_type": event_type,
            "actor_role_id": actor_role_id,
            "reviewer_role_id": reviewer_role_id,
            "attribution_id": attribution_id,
            "reason": reason,
            "payload": payload,
            "previous_event_hash": previous_event_hash,
            "occurred_at": _as_utc(occurred_at).isoformat(),
        }
    )


async def _append_delegation_event(
    db: AsyncSession,
    delegation: ReviewDelegation,
    *,
    event_type: str,
    attribution_id: str,
    actor_role_id: str | None,
    reviewer_role_id: str | None,
    reason: str | None,
    payload: dict[str, Any],
) -> DelegationEvent:
    previous = await db.scalar(
        select(DelegationEvent)
        .where(DelegationEvent.delegation_id == delegation.id)
        .order_by(DelegationEvent.sequence_number.desc())
    )
    sequence_number = (previous.sequence_number if previous is not None else 0) + 1
    previous_event_hash = previous.event_hash if previous is not None else None
    occurred_at = _now()
    event_hash = _delegation_event_hash(
        delegation=delegation,
        sequence_number=sequence_number,
        event_type=event_type,
        actor_role_id=actor_role_id,
        reviewer_role_id=reviewer_role_id,
        attribution_id=attribution_id,
        reason=reason,
        payload=payload,
        previous_event_hash=previous_event_hash,
        occurred_at=occurred_at,
    )
    event = DelegationEvent(
        id=str(uuid4()),
        delegation_id=delegation.id,
        assignment_id=delegation.assignment_id,
        investigation_id=delegation.investigation_id,
        delegation_hash=delegation.delegation_hash,
        sequence_number=sequence_number,
        event_type=event_type,
        actor_role_id=actor_role_id,
        reviewer_role_id=reviewer_role_id,
        attribution_id=attribution_id,
        reason=reason,
        payload=payload,
        event_hash=event_hash,
        previous_event_hash=previous_event_hash,
        occurred_at=occurred_at,
    )
    db.add(event)
    await db.flush()
    return event


async def _finding_target_or_404(
    db: AsyncSession,
    investigation_id: str,
    target: ReviewDelegationTarget,
) -> FindingVersion:
    version = await db.scalar(
        select(FindingVersion).where(
            FindingVersion.id == target.finding_version_id,
            FindingVersion.investigation_id == investigation_id,
        ).execution_options(populate_existing=True)
    )
    if version is None:
        raise _not_found("Finding version not found in this investigation.")
    if version.finding_id != target.finding_id:
        raise _conflict("Review delegation target finding_id does not match the finding version.")
    if canonical_json_hash(version.canonical_content_json) != version.content_hash:
        raise _conflict("Stored finding version hash does not match its canonical contents.")
    if version.content_hash != target.content_hash:
        raise _conflict("Review delegation target hash does not match the stored finding version.")
    return version


async def _eligible_assignment_for_delegation(
    db: AsyncSession,
    investigation_id: str,
    assignment_id: str,
    reviewer_role_id: str,
    *,
    lock: bool,
) -> RoleAssignment:
    assignment = await _assignment_or_404(
        db,
        investigation_id,
        assignment_id,
        lock=lock,
    )
    if assignment.status not in {
        AssignmentStatus.ASSIGNED.value,
        AssignmentStatus.IN_PROGRESS.value,
    }:
        raise _conflict("The assignment is not eligible for review delegation.")
    if reviewer_role_id not in MANUAL_REVIEW_ROLES:
        raise _conflict("reviewer_role_id must be a statically allowed manual review role.")
    await _validate_assignment(db, assignment)
    return assignment


def _check_issuer(assignment, actor_role_id, attribution_role_id=None):
    # Caller-asserted role consistency only; authentication remains deferred.
    allowed = {"atlas", assignment.role_id}
    if any(role is not None and role not in allowed for role in (actor_role_id, attribution_role_id)):
        raise _conflict("Delegation issuer must be the coordinator or assignment role.")
    if actor_role_id is not None and attribution_role_id is not None and actor_role_id != attribution_role_id:
        raise _conflict("Delegation actor and attribution roles must agree.")


async def _lock_delegation_assignment(db, investigation_id, delegation_id):
    """Global order: assignment first, then delegation; refresh both identities."""

    assignment_id = await db.scalar(select(ReviewDelegation.assignment_id).where(
        ReviewDelegation.id == delegation_id,
        ReviewDelegation.investigation_id == investigation_id,
    ))
    if assignment_id is None:
        raise _not_found("Review delegation not found in this investigation.")
    assignment = await _assignment_or_404(db, investigation_id, assignment_id, lock=True)
    delegation = await _delegation_or_404(db, investigation_id, delegation_id, lock=True)
    if delegation.assignment_id != assignment.id:
        raise _conflict("Delegation assignment changed while acquiring locks.")
    return assignment, delegation


def _delegation_hash(delegation):
    return canonical_json_hash({
        "id": delegation.id,
        "assignment_id": delegation.assignment_id,
        "investigation_id": delegation.investigation_id,
        "reviewer_role_id": delegation.reviewer_role_id,
        "scope_hash": delegation.scope_hash,
        "target": delegation.scope_json,
        "issued_by_role_id": delegation.issued_by_role_id,
        "issued_by_attribution_id": delegation.issued_by_attribution_id,
        "issued_at": _as_utc(delegation.issued_at).isoformat(),
        "expires_at": _as_utc(delegation.expires_at).isoformat(),
        "max_uses": delegation.max_uses,
        "token_hash": delegation.token_hash,
    })


async def _validate_delegation_envelope(db, delegation):
    target = ReviewDelegationTarget.model_validate(delegation.scope_json)
    if (
        target.model_dump(mode="json") != delegation.scope_json
        or canonical_json_hash(delegation.scope_json) != delegation.scope_hash
        or _delegation_hash(delegation) != delegation.delegation_hash
        or target.kind != delegation.target_kind
        or target.finding_version_id != delegation.target_finding_version_id
        or target.content_hash != delegation.target_content_hash
        or not 1 <= delegation.max_uses <= 10
        or not 0 <= delegation.use_count <= delegation.max_uses
        or _as_utc(delegation.expires_at) <= _as_utc(delegation.issued_at)
    ):
        raise _conflict("Stored review delegation scope or envelope integrity is invalid.")
    issued_event = await db.scalar(select(DelegationEvent).where(
        DelegationEvent.delegation_id == delegation.id,
        DelegationEvent.sequence_number == 1,
        DelegationEvent.event_type == "issued",
    ).execution_options(populate_existing=True))
    if issued_event is None or issued_event.delegation_hash != delegation.delegation_hash:
        raise _conflict("Review delegation envelope does not match its immutable issuance event.")
    return target


@dataclass(frozen=True, slots=True)
class IssuedReviewDelegation:
    delegation: ReviewDelegation
    token: str


@dataclass(frozen=True, slots=True)
class RedeemedReviewDelegation:
    delegation: ReviewDelegation
    review: Any


@_atomic_mutation
async def issue_review_delegation(
    db: AsyncSession,
    investigation_id: str,
    payload: ReviewDelegationIssue,
) -> IssuedReviewDelegation:
    await _investigation_or_404(db, investigation_id)
    assignment = await _eligible_assignment_for_delegation(
        db,
        investigation_id,
        payload.assignment_id,
        payload.reviewer_role_id,
        lock=True,
    )
    _check_issuer(assignment, payload.issued_by_role_id, payload.attribution.associated_role_id)
    await _finding_target_or_404(db, investigation_id, payload.target)
    issued_at = _now()
    expires_at = _as_utc(payload.expires_at)
    if expires_at <= issued_at:
        raise _conflict("Review delegation expires_at must be in the future.")
    if assignment.expires_at is not None and expires_at > _as_utc(assignment.expires_at):
        raise _conflict("Review delegation cannot outlive its assignment.")

    token = secrets.token_urlsafe(48)
    token_hash = _sha256_text(token)
    scope_json = payload.target.model_dump(mode="json")
    scope_hash = canonical_json_hash(scope_json)
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    delegation = ReviewDelegation(
        id=str(uuid4()),
        assignment_id=payload.assignment_id,
        investigation_id=investigation_id,
        reviewer_role_id=payload.reviewer_role_id,
        scope_json=scope_json,
        scope_hash=scope_hash,
        token_hash=token_hash,
        target_kind=payload.target.kind,
        target_finding_version_id=payload.target.finding_version_id,
        target_content_hash=payload.target.content_hash,
        status=ReviewDelegationStatus.ISSUED.value,
        issued_by_role_id=payload.issued_by_role_id,
        issued_at=issued_at,
        expires_at=expires_at,
        max_uses=payload.max_uses,
        use_count=0,
        issued_by_attribution_id=attribution.id,
        lifecycle_version=1,
    )
    delegation.delegation_hash = _delegation_hash(delegation)
    db.add(delegation)
    await db.flush()
    await _append_delegation_event(
        db,
        delegation,
        event_type="issued",
        attribution_id=attribution.id,
        actor_role_id=payload.issued_by_role_id,
        reviewer_role_id=payload.reviewer_role_id,
        reason=None,
        payload={
            "target_content_hash": payload.target.content_hash,
            "scope_hash": scope_hash,
            "expires_at": expires_at.isoformat(),
            "max_uses": payload.max_uses,
        },
    )
    await db.refresh(delegation)
    return IssuedReviewDelegation(delegation=delegation, token=token)


@_atomic_mutation
async def revoke_review_delegation(
    db: AsyncSession,
    investigation_id: str,
    delegation_id: str,
    payload: ReviewDelegationRevoke,
) -> ReviewDelegation:
    await _investigation_or_404(db, investigation_id)
    if payload.delegation_id != delegation_id:
        raise _conflict("Revoke delegation_id does not match the route delegation.")
    assignment, delegation = await _lock_delegation_assignment(db, investigation_id, delegation_id)
    await _validate_delegation_envelope(db, delegation)
    await _validate_assignment(db, assignment, require_unexpired=False)
    _check_issuer(assignment, payload.revoked_by_role_id, payload.attribution.associated_role_id)
    if delegation.lifecycle_version != payload.expected_lifecycle_version:
        raise _conflict("Review delegation lifecycle version is stale; reload before revoking.")
    if delegation.status != ReviewDelegationStatus.ISSUED.value:
        raise _conflict("Only an issued review delegation can be revoked.")
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    delegation.status = ReviewDelegationStatus.REVOKED.value
    delegation.revoked_at = _now()
    delegation.lifecycle_version += 1
    await _append_delegation_event(
        db,
        delegation,
        event_type="revoked",
        attribution_id=attribution.id,
        actor_role_id=payload.revoked_by_role_id,
        reviewer_role_id=delegation.reviewer_role_id,
        reason=payload.reason,
        payload={"lifecycle_version": delegation.lifecycle_version},
    )
    await db.refresh(delegation)
    return delegation


@_atomic_mutation
async def redeem_review_delegation(
    db: AsyncSession,
    investigation_id: str,
    delegation_id: str,
    payload: ReviewDelegationRedeem,
) -> RedeemedReviewDelegation:
    await _investigation_or_404(db, investigation_id)
    if payload.delegation_id != delegation_id:
        raise _conflict("Redeem delegation_id does not match the route delegation.")
    assignment, delegation = await _lock_delegation_assignment(db, investigation_id, delegation_id)
    if delegation.status != ReviewDelegationStatus.ISSUED.value:
        raise _conflict("Review delegation is no longer redeemable.")
    if not hmac.compare_digest(_sha256_text(payload.token), delegation.token_hash):
        raise _conflict("Review delegation token is invalid.")
    target = await _validate_delegation_envelope(db, delegation)
    _check_issuer(assignment, delegation.issued_by_role_id)
    if payload.attribution.associated_role_id not in {None, delegation.reviewer_role_id}:
        raise _conflict("Review attribution role must match the delegated reviewer role.")

    now = _now()
    if _as_utc(delegation.expires_at) <= now:
        raise _conflict("Review delegation token has expired.")
    if delegation.use_count >= delegation.max_uses:
        raise _conflict("Review delegation has exhausted its allowed uses.")
    if payload.expected_content_hash != delegation.target_content_hash:
        raise _conflict("Review redemption target hash does not match the delegation scope.")

    assignment = await _eligible_assignment_for_delegation(
        db,
        investigation_id,
        delegation.assignment_id,
        delegation.reviewer_role_id,
        lock=False,  # already locked before the delegation
    )
    if assignment.expires_at is not None and _as_utc(delegation.expires_at) > _as_utc(assignment.expires_at):
        raise _conflict("Review delegation cannot outlive its assignment.")
    version = await _finding_target_or_404(db, investigation_id, target)
    if payload.attribution.associated_role_id is not None:
        await _registered_snapshot(db, payload.attribution.associated_role_id, None, None)

    review_payload = RecordReviewCreate(
        attribution=payload.attribution,
        expected_content_hash=payload.expected_content_hash,
        review_method="manual_review",
        outcome=payload.outcome,
        notes=payload.notes,
        citations_checked=payload.citations_checked,
        numeric_transcription_checked=payload.numeric_transcription_checked,
        limitations_checked=payload.limitations_checked,
        execution_wording_checked=payload.execution_wording_checked,
        dependency_disclosures=payload.dependency_disclosures,
    )
    # create_review retains all of its exact-target and manual-review checks;
    # commit=False keeps this review in the same transaction as redemption.
    review = await create_review(
        db,
        investigation_id,
        version.id,
        review_payload,
        commit=False,
    )
    delegation.use_count += 1
    delegation.redeemed_by_attribution_id = review.reviewer_attribution_id
    if delegation.use_count >= delegation.max_uses:
        delegation.status = ReviewDelegationStatus.REDEEMED.value
        delegation.redeemed_at = now
    delegation.lifecycle_version += 1
    await _append_delegation_event(
        db,
        delegation,
        event_type="redeemed",
        attribution_id=review.reviewer_attribution_id,
        actor_role_id=payload.attribution.associated_role_id,
        reviewer_role_id=delegation.reviewer_role_id,
        reason=None,
        payload={
            "review_id": review.id,
            "target_content_hash": payload.expected_content_hash,
            "use_count": delegation.use_count,
            "max_uses": delegation.max_uses,
            "lifecycle_version": delegation.lifecycle_version,
            "assignment_id": assignment.id,
        },
    )
    await db.refresh(delegation)
    await db.refresh(review)
    return RedeemedReviewDelegation(delegation=delegation, review=review)


def assignment_read(assignment: RoleAssignment) -> AssignmentRead:
    return AssignmentRead.model_validate(assignment, from_attributes=True)


def deliverable_read(deliverable: AssignmentDeliverable) -> DeliverableRead:
    return DeliverableRead.model_validate(deliverable, from_attributes=True)


def assignment_transition_read(event: AssignmentEvent) -> AssignmentTransitionRead:
    return AssignmentTransitionRead(
        id=event.id,
        assignment_id=event.assignment_id,
        from_status=event.from_status,
        to_status=event.to_status,
        lifecycle_version=(event.payload.get("lifecycle_version") or 1),
        reason=event.reason,
        actor_role_id=event.actor_role_id,
        attribution_id=event.attribution_id,
        event_hash=event.event_hash,
        previous_event_hash=event.previous_event_hash,
        occurred_at=event.occurred_at,
    )


def assignment_event_read(event: AssignmentEvent) -> AssignmentEventRead:
    return AssignmentEventRead(
        id=event.id,
        assignment_id=event.assignment_id,
        sequence_number=event.sequence_number,
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        actor_role_id=event.actor_role_id,
        attribution_id=event.attribution_id,
        reason=event.reason,
        payload=event.payload,
        event_hash=event.event_hash,
        previous_event_hash=event.previous_event_hash,
        occurred_at=event.occurred_at,
    )


def review_delegation_read(
    delegation: ReviewDelegation,
) -> ReviewDelegationRead:
    target = ReviewDelegationTarget.model_validate(delegation.scope_json)
    return ReviewDelegationRead(
        id=delegation.id,
        assignment_id=delegation.assignment_id,
        reviewer_role_id=delegation.reviewer_role_id,
        target=target,
        delegation_hash=delegation.delegation_hash,
        status=delegation.status,
        issued_by_role_id=delegation.issued_by_role_id,
        issued_at=delegation.issued_at,
        expires_at=delegation.expires_at,
        redeemed_at=delegation.redeemed_at,
        revoked_at=delegation.revoked_at,
        lifecycle_version=delegation.lifecycle_version,
        max_uses=delegation.max_uses,
        use_count=delegation.use_count,
    )


__all__ = [
    "IssuedReviewDelegation",
    "RedeemedReviewDelegation",
    "assignment_event_read",
    "assignment_transition_read",
    "assignment_read",
    "create_assignment",
    "create_deliverable",
    "deliverable_read",
    "issue_review_delegation",
    "redeem_review_delegation",
    "review_delegation_read",
    "revoke_review_delegation",
    "transition_assignment",
]
