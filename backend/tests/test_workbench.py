"""ReproLab Unified Workbench & Scientific Engine Test Suite.

Consolidated verification of:
1. Hardened Pydantic Contracts & Schema Invariants
2. Document Parsing, Extraction & Canonical Protocol Freezing
3. Wilson 95% Score Confidence Intervals & Categorical Scorer
4. 14-Node LangGraph Deliberation & 12 Constitutional Personas
5. Bilingual Dual-Lens API & SSE Execution Streaming
6. Cryptographic System Backup & Disaster Recovery
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from httpx import ASGITransport, AsyncClient

from reprolab.schemas.contracts import (
    CONSTITUTIONAL_ROLES,
    DeliberationCritiqueContract,
    EmpiricalClaimContract,
    ExecutionRunContract,
    InvestigationCaseContract,
    ProtocolSpecificationContract,
    Stage7HumanGateContract,
)
from reprolab.scoring.statistical_engine import (
    StatisticalVerificationEngine,
    VerificationAssessment,
)
from reprolab.workflow.deliberation_dispatcher import (
    PersonaDeliberationDispatcher,
    calculate_persona_entropy,
)
from reprolab.services.doc_parser import (
    AcademicDocumentParser,
    DocumentParsingError,
    DocumentSecurityError,
    ParsedDocument,
)
from reprolab.services.protocol_freezer import ProtocolFreezerEngine
from reprolab.models.execution import AttemptRecord, ExecutionEvent, ExperimentJob, ProductionMeasurement
from reprolab.models.records import RecordAttribution
from reprolab.models.research import Claim, Investigation, ProtocolVersion
from reprolab.models.evaluation import ScientificEvaluation, SystemBackupRecord
from reprolab.models.paper import Artifact, Paper
from reprolab.services.backup import (
    BackupIntegrityError,
    create_system_backup,
    restore_system_backup,
)


FORBIDDEN_METAPHORS = [
    "kisan", "farmer", "crop", "harvest", "mandi", "fertilizer",
    "soil", "patwari", "krishi", "khet", "fasal", "agriculture",
    "shetkari", "panchayat", "village", "bhoomi", "gramin"
]


# =============================================================================
# 1. Hardened Contracts & Schema Validation
# =============================================================================

class TestContractSchemas:
    """Tests Pydantic validation and strict numeric invariants."""

    def test_empirical_claim_valid(self):
        claim = EmpiricalClaimContract(
            id="c1111111-1111-1111-1111-111111111111",
            case_id="a1111111-1111-1111-1111-111111111111",
            metric_name="accuracy",
            claimed_mean=0.894,
            claimed_ci_low=0.881,
            claimed_ci_high=0.907,
            baseline_value=0.862,
            baseline_model="XGBoost",
            p_value=0.004,
            sample_size=1000,
            direction="maximize",
        )
        assert claim.claimed_mean == 0.894
        assert claim.direction == "maximize"

    def test_empirical_claim_p_value_bounds(self):
        with pytest.raises(ValidationError):
            EmpiricalClaimContract(
                id="c1111111-1111-1111-1111-111111111111",
                case_id="a1111111-1111-1111-1111-111111111111",
                metric_name="accuracy",
                claimed_mean=0.894,
                p_value=1.05,
            )

    def test_empirical_claim_ci_ordering(self):
        with pytest.raises(ValueError, match="claimed_ci_low .* cannot exceed claimed_ci_high"):
            EmpiricalClaimContract(
                id="c1111111-1111-1111-1111-111111111111",
                case_id="a1111111-1111-1111-1111-111111111111",
                metric_name="accuracy",
                claimed_mean=0.894,
                claimed_ci_low=0.92,
                claimed_ci_high=0.88,
            )

    def test_protocol_specification_hash(self):
        dummy_hash = hashlib.sha256(b"canonical_protocol_data").hexdigest()
        spec = ProtocolSpecificationContract(
            spec_hash=dummy_hash,
            case_id="a1111111-1111-1111-1111-111111111111",
            environment_name="reprolab-py313",
            python_version="3.13",
            dependencies={"scikit-learn": "1.6.0", "numpy": "2.1.0"},
            hyperparameters={"learning_rate": 0.01, "batch_size": 32},
            seed_list=[42, 1337, 2026],
        )
        assert spec.spec_hash == dummy_hash
        assert len(spec.seed_list) == 3

    def test_deliberation_critique_12_roles(self):
        assert len(CONSTITUTIONAL_ROLES) == 12
        for role in CONSTITUTIONAL_ROLES:
            critique = DeliberationCritiqueContract(
                critique_id="d1111111-1111-1111-1111-111111111111",
                case_id="a1111111-1111-1111-1111-111111111111",
                persona_role=role,
                critique_markdown=f"Critique from {role}",
                verdict_sentiment="reproduced",
                confidence_score=0.95,
            )
            assert critique.persona_role == role

    def test_stage7_human_gate_contract(self):
        gate = Stage7HumanGateContract(
            case_id="a1111111-1111-1111-1111-111111111111",
            reviewer_id="prof-alice-lab-pi",
            reviewer_role="Principal Investigator",
            decision="approved",
            review_notes="Replication confirmed within claimed 95% Wilson CI bounds.",
            signature_hash=hashlib.sha256(b"pi_signature").hexdigest(),
            reviewed_at=datetime.now(timezone.utc),
        )
        assert gate.decision == "approved"
        assert len(gate.signature_hash) == 64


# =============================================================================
# 2. Document Parser & Protocol Freezing
# =============================================================================

class TestDocumentParserAndProtocol:
    """Tests intake validation and deterministic canonical freezing."""

    def test_magic_byte_validation_success(self):
        parser = AcademicDocumentParser()
        valid_pdf_stream = b"%PDF-1.7\nSample scientific paper content"
        assert parser.validate_magic_bytes(valid_pdf_stream) is True

    def test_magic_byte_validation_failure(self):
        parser = AcademicDocumentParser()
        malicious_stream = b"<html><script>alert('not a pdf')</script></html>"
        with pytest.raises(DocumentSecurityError):
            parser.validate_magic_bytes(malicious_stream)

    def test_size_limit_enforcement(self):
        parser = AcademicDocumentParser(max_bytes=1024)
        oversized = b"%PDF-1.7\n" + (b"X" * 2000)
        with pytest.raises(DocumentSecurityError):
            parser.validate_magic_bytes(oversized)

    def test_academic_text_section_parsing(self):
        parser = AcademicDocumentParser()
        raw_text = """
        ResTabNet: Robust Verification

        Abstract
        This paper presents ResTabNet for robust table verification.

        Methodology
        The model was trained using AdamW with learning rate 1e-4.

        Results
        On benchmark X, our model achieves 89.4% accuracy (p=0.004).
        """
        parsed: ParsedDocument = parser.parse_text(raw_text)
        assert "ResTabNet" in parsed.title
        assert "table verification" in parsed.abstract
        assert "AdamW" in parsed.methodology
        assert "89.4%" in parsed.results

    def test_protocol_freeze_deterministic_hash(self):
        freezer = ProtocolFreezerEngine()
        spec1 = freezer.freeze_protocol(
            case_id="case-1111-1111",
            environment_name="tabular-benchmark-v1",
            python_version="3.13.12",
            dependencies={"numpy": "2.2.0", "scikit-learn": "1.6.0"},
            hyperparameters={"lr": 0.0001, "batch_size": 64},
            seed_list=[42, 1337],
            entrypoint="reproduce.py",
        )
        spec2 = freezer.freeze_protocol(
            case_id="case-1111-1111",
            environment_name="tabular-benchmark-v1",
            python_version="3.13.12",
            dependencies={"scikit-learn": "1.6.0", "numpy": "2.2.0"},
            hyperparameters={"batch_size": 64, "lr": 0.0001},
            seed_list=[42, 1337],
            entrypoint="reproduce.py",
        )
        assert spec1.spec_hash == spec2.spec_hash
        assert len(spec1.spec_hash) == 64


# =============================================================================
# 3. Wilson 95% CI Statistical Verification Engine
# =============================================================================

class TestStatisticalEngine:
    """Tests analytical Wilson score confidence intervals and verdicts."""

    def test_wilson_ci_accuracy_against_analytical_ground_truth(self):
        engine = StatisticalVerificationEngine()
        # Case: 894 successes out of 1000 trials
        low, high = engine.calculate_wilson_95_ci(successes=894, sample_size=1000)
        assert 0.870 <= low <= 0.880
        assert 0.905 <= high <= 0.915
        assert low < high

    def test_wilson_boundary_conditions(self):
        engine = StatisticalVerificationEngine()
        low_zero, high_zero = engine.calculate_wilson_95_ci(successes=0, sample_size=100)
        assert low_zero == 0.0
        assert high_zero > 0.0

        low_full, high_full = engine.calculate_wilson_95_ci(successes=100, sample_size=100)
        assert low_full < 1.0
        assert high_full == 1.0

    def test_classify_verified_reproduced(self):
        engine = StatisticalVerificationEngine()
        claim = EmpiricalClaimContract(
            id="c1",
            case_id="case-1",
            metric_name="accuracy",
            claimed_mean=0.894,
            claimed_ci_low=0.881,
            claimed_ci_high=0.907,
            baseline_value=0.862,
            baseline_model="XGBoost",
            p_value=0.004,
            sample_size=1000,
            direction="maximize",
        )
        assessment: VerificationAssessment = engine.assess_reproduction(
            claim=claim,
            replicated_mean=0.891,
            replicated_sample_size=1000,
            execution_exit_code=0,
        )
        assert assessment.verdict == "VERIFIED_REPRODUCED"
        assert assessment.rail_gauge_score >= 85.0
        assert assessment.replicated_within_ci is True

    def test_classify_execution_failed_on_nonzero_exit(self):
        engine = StatisticalVerificationEngine()
        claim = EmpiricalClaimContract(
            id="c3",
            case_id="case-3",
            metric_name="accuracy",
            claimed_mean=0.894,
            direction="maximize",
        )
        assessment = engine.assess_reproduction(
            claim=claim,
            replicated_mean=0.0,
            replicated_sample_size=1000,
            execution_exit_code=137,
            error_message="OOM Killed",
        )
        assert assessment.verdict == "EXECUTION_FAILED"
        assert assessment.rail_gauge_score == 0.0


# =============================================================================
# 4. 14-Node LangGraph Deliberation & Personas
# =============================================================================

class TestDeliberationDispatcher:
    """Tests multi-agent consensus and anti-sycophancy metrics."""

    def test_shannon_entropy_calculation(self):
        unanimous = [
            DeliberationCritiqueContract(
                critique_id=f"c-{i}",
                case_id="case-1",
                persona_role=CONSTITUTIONAL_ROLES[i],
                critique_markdown="I agree completely.",
                verdict_sentiment="reproduced",
                confidence_score=0.9,
            )
            for i in range(12)
        ]
        entropy_unanimous = calculate_persona_entropy(unanimous)
        assert entropy_unanimous == 0.0

        diverse = [
            DeliberationCritiqueContract(
                critique_id=f"c-{i}",
                case_id="case-1",
                persona_role=CONSTITUTIONAL_ROLES[i],
                critique_markdown=f"Critique from {CONSTITUTIONAL_ROLES[i]}",
                verdict_sentiment=["reproduced", "partially_reproduced", "failed_to_reproduce", "flawed_methodology"][i % 4],
                confidence_score=0.8,
            )
            for i in range(12)
        ]
        entropy_diverse = calculate_persona_entropy(diverse)
        assert entropy_diverse > 1.0


# =============================================================================
# 5. Bilingual Dual-Lens API & SSE Execution Streaming
# =============================================================================

@pytest.mark.asyncio
async def test_investigation_summary_bilingual_api(app):
    """Verify dual-lens English & Hindi summary synthesis with Wilson intervals."""
    inv_id = "inv-wb-test-1"
    async with app.state.session_factory() as session:
        inv = Investigation(
            id=inv_id,
            name="Milestone 5 Bilingual Synthesis Test",
            source_kind="synthetic_framework_test",
            status="approved",
            execution_status="completed",
            claim_assessment="reproduced",
        )
        session.add(inv)
        await session.flush()

        attr = RecordAttribution(
            id="attr-wb-1",
            investigation_id=inv_id,
            recorder_id="rec-wb-1",
            recorder_label="Workbench Operator",
        )
        claim = Claim(
            id="claim-wb-1",
            investigation_id=inv_id,
            statement="Model achieves 85% accuracy on benchmark test split.",
            metric_name="accuracy",
            metric_direction="maximize",
            reported_value=0.85,
            source_kind="synthetic_framework_test",
        )
        protocol = ProtocolVersion(
            id="prot-wb-1",
            investigation_id=inv_id,
            version_number=1,
            status="frozen",
            protocol_hash="hash-wb-proto",
            canonical_protocol_json={"dataset": "synth", "model": "classifier"},
        )
        session.add_all([attr, claim, protocol])
        await session.flush()

        job = ExperimentJob(
            id="job-wb-1",
            investigation_id=inv_id,
            protocol_version_id="prot-wb-1",
            submission_key="sub-wb-1",
            status="completed",
            lifecycle_version=1,
            execution_bundle_hash="bundle-wb-hash",
            created_by_attribution_id="attr-wb-1",
        )
        session.add(job)
        await session.flush()

        attempt = AttemptRecord(
            id="att-wb-1",
            job_id="job-wb-1",
            investigation_id=inv_id,
            attempt_number=1,
            status="completed",
            exit_code=0,
            stdout_excerpt="Initializing isolated evaluation container...\nEvaluating test split (N=100)...\nCalculated accuracy: 0.880\nCompleted successfully.",
            stderr_excerpt=None,
            resource_usage_json={"wall_time_seconds": 1.25, "peak_memory_bytes": 10485760},
        )
        session.add(attempt)
        await session.flush()

        measurement = ProductionMeasurement(
            id="meas-wb-1",
            investigation_id=inv_id,
            job_id="job-wb-1",
            attempt_id="att-wb-1",
            metric_name="accuracy",
            value=0.880,
            unit="proportion",
            sample_size=100,
            analysis_unit="row",
            confidence_level=0.95,
            interval_lower=0.802,
            interval_upper=0.931,
            scoring_method="wilson_score_interval",
            scorer_version="1.0.0",
            prediction_artifact_sha256="pred_sha_wb",
            manifest_artifact_sha256="manifest_sha_wb",
            protocol_hash="hash-wb-proto",
            recorded_at=datetime.now(timezone.utc),
        )
        session.add(measurement)

        eval_rec = ScientificEvaluation(
            id="eval-wb-1",
            investigation_id=inv_id,
            job_id="job-wb-1",
            claim_id="claim-wb-1",
            evaluation_version="1.0.0",
            status="completed",
            verdict="reproduced",
            extraction_quality_score=1.0,
            technical_reproducibility_score=1.0,
            claim_verification_score=1.0,
            summary_notes="Milestone 5 verified evaluation",
        )
        session.add(eval_rec)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/v1/investigations/{inv_id}/summary")
        assert res.status_code == 200, res.text
        data = res.json()

        assert data["investigation_id"] == inv_id
        assert data["reproduction_verdict"] == "reproduced"
        assert data["rail_metrics"]["claimed_mean"] == 0.85
        assert data["rail_metrics"]["replicated_mean"] == 0.88

        # Assert English and Hindi summaries exist without forbidden metaphors
        assert "85.0%" in data["plain_english_summary"]
        assert "88.0%" in data["plain_english_summary"]
        combined = (data["plain_english_summary"] + " " + data["plain_hindi_summary"]).lower()
        for forbidden in FORBIDDEN_METAPHORS:
            assert forbidden not in combined, f"Forbidden metaphor '{forbidden}' found!"


@pytest.mark.asyncio
async def test_sse_job_log_streaming_api(app):
    """Verify Server-Sent Events (SSE) streaming for real-time sandbox execution."""
    inv_id = "inv-wb-sse-1"
    job_id = "job-wb-sse-1"

    async with app.state.session_factory() as session:
        inv = Investigation(
            id=inv_id,
            name="SSE Stream Test",
            source_kind="synthetic_framework_test",
            status="executing",
        )
        session.add(inv)
        await session.flush()

        attr = RecordAttribution(
            id="attr-wb-sse-1",
            investigation_id=inv_id,
            recorder_id="rec-wb-sse-1",
            recorder_label="Workbench Operator",
        )
        protocol = ProtocolVersion(
            id="prot-wb-sse-1",
            investigation_id=inv_id,
            version_number=1,
            status="frozen",
            protocol_hash="hash-wb-sse-proto",
            canonical_protocol_json={"dataset": "synth", "model": "classifier"},
        )
        session.add_all([attr, protocol])
        await session.flush()

        job = ExperimentJob(
            id=job_id,
            investigation_id=inv_id,
            protocol_version_id="prot-wb-sse-1",
            submission_key="sub-wb-sse-1",
            status="completed",
            lifecycle_version=1,
            execution_bundle_hash="bundle-wb-sse-hash",
            created_by_attribution_id="attr-wb-sse-1",
        )
        session.add(job)
        await session.flush()

        attempt = AttemptRecord(
            id="att-wb-sse-1",
            job_id=job_id,
            investigation_id=inv_id,
            attempt_number=1,
            status="completed",
            exit_code=0,
            stdout_excerpt="Initializing isolated evaluation container...\nEvaluating test split (N=100)...\nCalculated accuracy: 0.880\nCompleted successfully.",
            stderr_excerpt=None,
            resource_usage_json={"wall_time_seconds": 1.25, "peak_memory_bytes": 10485760},
        )
        session.add(attempt)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/v1/investigations/{inv_id}/experiment-jobs/{job_id}/stream")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        body = res.text
        assert "event: connected" in body
        assert "event: attempt" in body
        assert "event: log" in body
        assert "event: done" in body


# =============================================================================
# 6. Coordinated System Backup & Disaster Recovery
# =============================================================================

@pytest.mark.asyncio
async def test_create_and_restore_system_backup(app, tmp_path: Path):
    """Verify cryptographic backup generation and referential restore."""
    session_factory = app.state.session_factory
    storage = app.state.storage
    storage_root = storage.root
    backup_root = tmp_path / "backups"

    test_content = b"%PDF-1.4 test paper content"
    sha = hashlib.sha256(test_content).hexdigest()
    storage_key = f"papers/{sha[:2]}/{sha}.pdf"
    file_path = storage.resolve(storage_key)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(test_content)

    async with session_factory() as session:
        paper = Paper(
            id="test-paper-1",
            title="Test Synthetic Paper",
            original_filename="paper.pdf",
            storage_key=storage_key,
            sha256=sha,
            file_size=len(test_content),
            content_type="application/pdf",
        )
        artifact = Artifact(
            id="art-1",
            paper_id="test-paper-1",
            kind="pdf",
            storage_key=storage_key,
            sha256=sha,
            size_bytes=len(test_content),
            content_type="application/pdf",
        )
        session.add(paper)
        await session.flush()
        session.add(artifact)
        await session.commit()

        # Create coordinated backup
        record, manifest_path = await create_system_backup(session, storage, backup_root)
        assert record.status == "created"
        assert record.artifact_count == 1
        assert manifest_path.exists()

    # Simulate disaster: wipe storage
    for p in storage_root.rglob("*"):
        if p.is_file():
            p.unlink()
    assert not file_path.exists()

    # Restore system backup
    restore_res = await restore_system_backup(manifest_path, session_factory, storage)
    assert restore_res["status"] == "success"
    assert restore_res["restored_artifacts"] == 1
    assert file_path.exists()
    assert file_path.read_bytes() == test_content
