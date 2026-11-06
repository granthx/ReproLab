import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

# Load root .env for test suite (Gemini API key, test database URL)
for _p in [Path(__file__).resolve().parents[1] / ".env", Path(__file__).resolve().parents[2] / ".env"]:
    if _p.exists():
        load_dotenv(_p)
        break

import pytest
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from reprolab.core.config import Settings
from reprolab.db.base import Base
from reprolab.models import Artifact, Paper  # noqa: F401
from reprolab.storage.local import LocalPrivateStorage


def pytest_addoption(parser):
    parser.addoption(
        "--postgres",
        action="store_true",
        default=False,
        help="Run API fixtures against the Settings PostgreSQL database in isolated test schemas.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "postgres: live PostgreSQL integration test (requires --postgres)")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--postgres"):
        skipped = pytest.mark.skip(reason="Live PostgreSQL integration requires --postgres.")
        for item in items:
            if item.get_closest_marker("postgres") is not None:
                item.add_marker(skipped)


def _upgrade_postgres_schema(connection: Connection, schema: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    script = ScriptDirectory.from_config(config)

    def upgrade(revision, context):
        return script._upgrade_revs("head", revision)

    # env.py opens an independent engine. Run Alembic's revision runner on this
    # already isolated connection instead, including the real version table.
    with EnvironmentContext(config, script, fn=upgrade):
        from alembic import context

        context.configure(connection=connection, version_table_schema=schema)
        with context.begin_transaction():
            context.run_migrations()


def _postgres_result(function, action: str):
    failed = False
    diagnostic = ""
    try:
        result = function()
    except Exception as error:
        # Settings/driver exceptions can contain credentials or connection details.
        # Fail outside the exception handler so pytest cannot print that chain.
        failed = True
        diagnostic = type(error).__name__
        original = getattr(error, "orig", error)
        state = getattr(original, "sqlstate", None)
        if isinstance(state, str) and len(state) == 5 and state.isalnum():
            diagnostic += f", SQLSTATE {state}"
    if failed:
        pytest.fail(f"PostgreSQL test {action} failed ({diagnostic}); connection/error details withheld.", pytrace=False)
    return result


def _run_postgres(coroutine, action: str):
    return _postgres_result(lambda: asyncio.run(coroutine), action)


@dataclass
class _PostgresDatabase:
    settings: Settings = field(repr=False)
    schema: str
    engine: AsyncEngine | None = field(default=None, init=False, repr=False)
    _admin_engine: AsyncEngine | None = field(default=None, init=False, repr=False)
    _engines: list[AsyncEngine] = field(default_factory=list, init=False, repr=False)
    _schema_created: bool = field(default=False, init=False, repr=False)

    def _new_engine(self, search_path: str) -> AsyncEngine:
        url = make_url(self.settings.database_url).set(drivername="postgresql+asyncpg")
        return create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": search_path}},
            hide_parameters=True,
            echo=False,
        )

    async def initialize(self):
        self._admin_engine = self._new_engine("pg_catalog")
        self.engine = self.new_app_engine()
        # The identifier contains only a fixed prefix and uuid4 hex. No caller
        # supplied schema or IF NOT EXISTS can adopt an existing/shared schema.
        async with self._admin_engine.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        self._schema_created = True
        async with self.engine.begin() as connection:
            current_schema = await connection.exec_driver_sql("SELECT current_schema()")
            if current_schema.scalar_one() != self.schema:
                raise RuntimeError("Test schema isolation was not established.")
            await connection.run_sync(_upgrade_postgres_schema, self.schema)

    def new_app_engine(self) -> AsyncEngine:
        # Each checkout connects afresh: no asyncpg connection crosses the loops
        # used by asyncio.run(), async tests, and multiple TestClient lifespans.
        engine = self._new_engine(self.schema)
        self._engines.append(engine)
        return engine

    def create_app(self):
        return _postgres_result(self._create_app, "app creation")

    def _create_app(self):
        from reprolab.main import create_app

        return create_app(
            settings=self.settings,
            engine=self.new_app_engine(),
            storage=LocalPrivateStorage(self.settings.storage_root, self.settings.max_upload_bytes),
        )

    async def cleanup(self):
        try:
            for engine in self._engines:
                await engine.dispose()
        finally:
            if self._admin_engine is not None:
                try:
                    if self._schema_created:
                        async with self._admin_engine.begin() as connection:
                            await connection.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')
                        self._schema_created = False
                finally:
                    await self._admin_engine.dispose()


@pytest.fixture
def postgres_database(request, tmp_path: Path):
    if not request.config.getoption("--postgres"):
        pytest.skip("Live PostgreSQL integration requires --postgres.")

    invalid_settings = False
    try:
        settings = Settings(
            storage_root=tmp_path / "storage",
            auto_create_schema=False,
            cors_origins="http://testserver",
        )
        is_postgres = make_url(settings.database_url).get_backend_name() == "postgresql"
    except Exception:
        invalid_settings = True
    if invalid_settings:
        pytest.fail("Invalid PostgreSQL test settings; configuration details withheld.", pytrace=False)
    if not is_postgres:
        pytest.fail("--postgres requires a PostgreSQL Settings.database_url.", pytrace=False)

    database = _PostgresDatabase(settings=settings, schema=f"reprolab_pytest_{uuid4().hex}")
    try:
        _run_postgres(database.initialize(), "schema creation/migration")
        yield database
    finally:
        _run_postgres(database.cleanup(), "isolated-schema cleanup")


@pytest.fixture
def app(tmp_path: Path, request):
    if request.config.getoption("--postgres"):
        yield request.getfixturevalue("postgres_database").create_app()
        return

    from reprolab.main import create_app

    database_path = tmp_path / "test.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database_path}",
        storage_root=tmp_path / "storage",
        auto_create_schema=True,
        cors_origins="http://testserver",
    )

    async def create_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    test_app = create_app(settings=settings, engine=engine, storage=LocalPrivateStorage(settings.storage_root, settings.max_upload_bytes))
    yield test_app

    async def cleanup():
        await engine.dispose()

    asyncio.run(cleanup())
