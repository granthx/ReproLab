from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from reprolab.api.routes import (
    assignments,
    auth,
    capabilities,
    evaluation,
    execution,
    findings,
    health,
    investigations,
    operations,
    papers,
    reports,
    review_delegations,
    scientists,
    workflows,
)
from reprolab.core.config import Settings, get_settings
from reprolab.db.base import Base
from reprolab.db.session import create_engine_and_session
from reprolab.models import (  # noqa: F401 - register metadata
    Artifact,
    AssignmentDeliverable,
    AssignmentEvent,
    Claim,
    EvidenceItem,
    Finding,
    FindingEvidenceLink,
    FindingRelation,
    FindingVersion,
    DelegationEvent,
    Investigation,
    Paper,
    ProtocolVersion,
    RecordAttribution,
    RecordReview,
    Report,
    ReportEvent,
    ReportExport,
    ReportFindingLink,
    ReportVersion,
    ResearchArtifact,
    ReviewDelegation,
    ReviewDelegationEvent,
    RoleAssignment,
    ScientistConstitutionSnapshot,
    WorkflowCheckpoint,
    WorkflowEvent,
    WorkflowModelCall,
    WorkflowRun,
    ExperimentJob,
    AttemptRecord,
    ExecutionEvent,
    ProductionMeasurement,
    ScientificEvaluation,
    SystemBackupRecord,
)
from reprolab.scientists.registry import get_constitutions
from reprolab.storage.local import LocalPrivateStorage


def create_app(
    settings: Settings | None = None,
    engine: AsyncEngine | None = None,
    storage: LocalPrivateStorage | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    owned_engine = engine is None
    if engine is None:
        engine, session_factory = create_engine_and_session(settings)
    else:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = storage or LocalPrivateStorage(Path(settings.storage_root), settings.max_upload_bytes)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.auto_create_schema:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        # Loading this registry at startup validates that the 12-role foundation is intact.
        get_constitutions()
        yield
        if owned_engine:
            await engine.dispose()

    app = FastAPI(
        title="ReproLab API",
        version="0.1.0",
        description="Evidence-first paper intake for the ReproLab research institute.",
        lifespan=lifespan,
    )
    app.state.session_factory = session_factory
    app.state.settings = settings
    app_storage = storage
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"]
    )
    app.state.storage = app_storage
    app.include_router(health.router)
    app.include_router(capabilities.router)
    app.include_router(scientists.router)
    app.include_router(papers.router)
    app.include_router(investigations.router)
    app.include_router(investigations.protocol_router)
    app.include_router(findings.router)
    app.include_router(reports.router)
    app.include_router(assignments.router)
    app.include_router(review_delegations.router)
    app.include_router(workflows.router)
    app.include_router(execution.router)
    app.include_router(evaluation.router)
    app.include_router(operations.router)
    app.include_router(auth.router)

    from fastapi.responses import Response
    from reprolab.core.telemetry import generate_prometheus_metrics

    @app.get("/metrics", tags=["observability"], response_class=Response)
    def prometheus_metrics():
        return Response(
            content=generate_prometheus_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


app = create_app()
