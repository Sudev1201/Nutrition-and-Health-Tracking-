import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.base import Base


@pytest.fixture(scope="session")
def engine():
    test_engine = create_engine(settings.test_database_url, pool_pre_ping=True)
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
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
