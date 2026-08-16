from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app

BACKEND_ROOT = Path(__file__).resolve().parents[1]

MIGRATE_HINT = (
    f"    DATABASE_URL={settings.test_database_url} uv run alembic upgrade head\n"
    "(run from backend/; alembic reads DATABASE_URL, so without the prefix it "
    "would migrate the development database instead)"
)


def _expected_head() -> str:
    """The revision `alembic upgrade head` would land on, read from the scripts."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


def _require_migrated_schema(engine: Engine) -> None:
    """Fail with an instruction, not a mystery, when the test database is not
    at the migration head.

    This fixture used to call `Base.metadata.drop_all` / `create_all`, which
    meant the suite never once ran against the schema the migrations actually
    produce -- a migration could be wrong in any way `alembic check` does not
    model (a missing backfill, a wrong server default, a column left nullable)
    and every test would still pass. It also made two concurrent pytest
    sessions destroy each other's tables mid-run, which is where this plan's
    spurious `UndefinedTable` failures came from.

    So the migrated schema now stands untouched. Per-test isolation comes from
    the `db` fixture's outer transaction, which is rolled back either way.
    """
    head = _expected_head()
    with engine.connect() as connection:
        if not inspect(connection).has_table("alembic_version"):
            raise pytest.UsageError(
                f"the test database {settings.test_database_url} has no schema "
                "(no alembic_version table). The suite runs against the migrated "
                "schema and no longer creates tables itself. Run:\n" + MIGRATE_HINT
            )
        applied = list(connection.scalars(text("select version_num from alembic_version")))

    if applied != [head]:
        raise pytest.UsageError(
            f"the test database {settings.test_database_url} is at "
            f"{applied or 'no revision'} but the migrations head is {head}. Run:\n"
            + MIGRATE_HINT
        )


@pytest.fixture(scope="session")
def engine():
    test_engine = create_engine(settings.test_database_url, pool_pre_ping=True)
    try:
        _require_migrated_schema(test_engine)
    except BaseException:
        test_engine.dispose()
        raise
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine) -> Session:
    """A session wrapped in a transaction that is rolled back after each test.

    `join_transaction_mode="create_savepoint"` is what makes this work for API
    tests: the routers call `db.commit()`, and without it that commit would end
    the outer transaction and defeat the rollback. With it, the session commits
    a SAVEPOINT while the outer transaction stays open and still rolls back.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
