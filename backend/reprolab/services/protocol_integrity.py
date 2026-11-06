from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.models.research import Claim, EvidenceItem, EvidenceReview, Investigation, ProtocolVersion
from reprolab.schemas.research import ProtocolDefinition
from reprolab.services.protocols import canonical_protocol, protocol_hash


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


async def validate_protocol_record(
    db: AsyncSession,
    protocol_record: ProtocolVersion,
    *,
    require_accepted_evidence: bool,
) -> tuple[ProtocolDefinition, Investigation, Claim, list[EvidenceItem]]:
    stored_hash = protocol_hash(protocol_record.canonical_protocol_json)
    if stored_hash != protocol_record.protocol_hash:
        raise _conflict("Stored protocol hash does not match canonical protocol contents.")
    try:
        definition = ProtocolDefinition.model_validate(protocol_record.canonical_protocol_json)
    except Exception as exc:
        raise _conflict("Stored protocol contents are invalid.") from exc
    if canonical_protocol(definition) != protocol_record.canonical_protocol_json:
        raise _conflict("Stored protocol is not in canonical form.")

    investigation = await db.get(Investigation, protocol_record.investigation_id)
    if investigation is None:
        raise _conflict("Protocol investigation no longer exists.")
    if definition.source_kind != investigation.source_kind or definition.paper_id != investigation.paper_id:
        raise _conflict("Protocol source does not match its investigation.")

    claim = await db.get(Claim, definition.claim_id)
    if claim is None or claim.investigation_id != investigation.id:
        raise _conflict("Protocol claim does not belong to its investigation.")
    if claim.statement != definition.claim_text:
        raise _conflict("Protocol claim text does not match the stored claim.")
    if claim.metric_name != definition.primary_metric.name:
        raise _conflict("Protocol metric does not match the stored claim metric.")
    if claim.metric_direction != definition.primary_metric.direction:
        raise _conflict("Protocol metric direction does not match the stored claim.")
    if claim.reported_value != definition.reported_result.value:
        raise _conflict("Protocol reported result does not match the stored claim.")
    if claim.source_kind != definition.source_kind:
        raise _conflict("Protocol source kind does not match the stored claim.")

    evidence_result = await db.scalars(
        select(EvidenceItem).where(EvidenceItem.id.in_(definition.evidence_reference_ids))
    )
    evidence_items = list(evidence_result.all())
    if len(evidence_items) != len(set(definition.evidence_reference_ids)):
        raise _conflict("One or more protocol evidence references do not exist.")
    if any(item.investigation_id != investigation.id for item in evidence_items):
        raise _conflict("Protocol evidence references must belong to its investigation.")
    if any(item.claim_id not in {None, claim.id} for item in evidence_items):
        raise _conflict("Protocol evidence references another claim.")

    if require_accepted_evidence:
        reviews = await db.scalars(
            select(EvidenceReview)
            .where(EvidenceReview.evidence_item_id.in_(definition.evidence_reference_ids))
            .order_by(EvidenceReview.reviewed_at.desc())
        )
        latest: dict[str, EvidenceReview] = {}
        for review in reviews.all():
            latest.setdefault(review.evidence_item_id, review)
        if any(
            latest.get(item.id) is None or latest[item.id].outcome != "accepted_for_protocol"
            for item in evidence_items
        ):
            raise _conflict("All protocol evidence requires a latest accepted review before approval.")

    return definition, investigation, claim, evidence_items
