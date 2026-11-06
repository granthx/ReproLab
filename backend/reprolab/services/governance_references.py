"""Investigation-scoped, exact-ID reference resolution for manual governance.

finding/report/protocol refer to version rows, never their parent or latest
version. Their hashes (and deliverable hashes) are mandatory and recomputed
from canonical JSON. Paper/artifact/evidence hashes mean stored source SHA-256,
not a hash of mutable metadata; this service does not read artifact bytes.
investigation/claim/assignment/review have no canonical content digest, so a
supplied hash is rejected. review means RecordReview, not EvidenceReview.
Paper ownership follows Investigation.paper_id. Paper artifacts must belong to
that paper or be explicitly linked by this investigation's evidence. Research
artifacts/references have their own investigation_id; bare blobs are not refs.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.models.artifact import ResearchArtifact, ResearchArtifactReference
from reprolab.models.governance import AssignmentDeliverable, RoleAssignment
from reprolab.models.paper import Artifact, Paper
from reprolab.models.records import FindingVersion, RecordReview
from reprolab.models.reports import ReportVersion
from reprolab.models.research import Claim, EvidenceItem, Investigation, ProtocolVersion
from reprolab.schemas.governance import GovernanceReference, canonical_json_hash


_MODELS = {
    "investigation": Investigation, "paper": Paper, "claim": Claim,
    "evidence": EvidenceItem, "protocol": ProtocolVersion,
    "finding": FindingVersion, "report": ReportVersion,
    "assignment": RoleAssignment, "deliverable": AssignmentDeliverable,
    "review": RecordReview,
}
_CANONICAL = {
    "protocol": ("canonical_protocol_json", "protocol_hash"),
    "finding": ("canonical_content_json", "content_hash"),
    "report": ("canonical_content_json", "content_hash"),
    "deliverable": ("content", "content_hash"),
}


async def _fresh(db, model, record_id):
    return await db.scalar(
        select(model).where(model.id == record_id).execution_options(populate_existing=True)
    )


async def validate_references(
    db: AsyncSession,
    investigation_id: str,
    references: list[GovernanceReference] | list[dict],
) -> None:
    parsed = [GovernanceReference.model_validate(item) for item in references]
    keys = [(item.kind, item.id) for item in parsed]
    if len(keys) != len(set(keys)):
        raise HTTPException(409, "Governance references must be unique.")
    investigation = await _fresh(db, Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(404, "Investigation not found.")
    for reference in parsed:
        kind = reference.kind.value
        if kind == "artifact":
            matches = []
            for model in (Artifact, ResearchArtifact, ResearchArtifactReference):
                record = await _fresh(db, model, reference.id)
                if record is not None:
                    matches.append(record)
            if len(matches) > 1:
                raise HTTPException(409, "Artifact reference identity is ambiguous.")
            record = matches[0] if matches else None
        else:
            record = await _fresh(db, _MODELS[kind], reference.id)
        if record is None:
            raise HTTPException(404, "Governance reference not found (version IDs are required).")

        if kind == "investigation":
            owned = record.id == investigation_id
        elif kind == "paper":
            owned = record.id == investigation.paper_id
        elif isinstance(record, Artifact):
            owned = record.paper_id == investigation.paper_id or await db.scalar(
                select(EvidenceItem.id).where(
                    EvidenceItem.investigation_id == investigation_id,
                    EvidenceItem.artifact_id == record.id,
                ).limit(1)
            ) is not None
        else:
            owned = record.investigation_id == investigation_id
        if not owned:
            raise HTTPException(409, "Governance reference is outside the investigation.")

        digest = None
        if kind in _CANONICAL:
            content_field, hash_field = _CANONICAL[kind]
            digest = getattr(record, hash_field)
            if canonical_json_hash(getattr(record, content_field)) != digest:
                raise HTTPException(409, "Stored reference canonical content hash is invalid.")
        elif kind in {"paper", "artifact", "evidence"}:
            digest = record.sha256
        if reference.content_hash is not None:
            if digest is None:
                raise HTTPException(409, "This reference has no canonical digest to verify.")
            if reference.content_hash != digest:
                raise HTTPException(409, "Governance reference content_hash does not match.")
