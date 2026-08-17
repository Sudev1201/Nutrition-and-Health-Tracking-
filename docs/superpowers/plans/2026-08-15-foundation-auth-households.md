# Foundation, Auth & Households Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the project skeleton and ship the first working slice — a user signs in with Google, gets a session, creates a household, invites another member, and lands on a protected app shell.

**Architecture:** Two services in one repository. A FastAPI backend (synchronous SQLAlchemy 2.0 over Postgres) owns all data and issues its own session cookie after verifying a Google ID token; a React + TypeScript frontend built with Vite talks to it over `fetch` with credentials. Sync SQLAlchemy is deliberate — this is a family-sized app whose hard work is CPU-bound nutrient math, so async adds footguns without buying throughput.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, psycopg 3, pydantic-settings, google-auth, PyJWT, pytest, uv. React 18, TypeScript, Vite, React Router, TanStack Query, Tailwind. Postgres 16 via docker-compose. GitHub Actions for CI.

**Spec:** `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`

## Global Constraints

These apply to every task in this plan and every plan that follows.

- **Google sign-in is the only authentication method.** No password fields, no email/password fallback, no magic links.
- **English only** for all dish and ingredient names and all UI copy. No i18n layer.
- **Responsive from phone to desktop.** The same components serve both; wide screens get multi-column layouts, not a stretched phone view.
- **Health data is private by default.** Conditions, thyroid labs, medications, weight and cycle data are never visible to other household members unless that member explicitly opts in. Nutrition *progress* is shared by default and can be switched off.
- **Every food and reference row is source-tagged** (IFCT / USDA / INDB / ICMR-NIN / IOM / EFSA). Nothing enters the database without recording where the number came from.
- **The app is not medical advice.** Any surface that presents condition-based guidance carries that statement.
- **Timezone:** all user-facing day boundaries are computed in the user's timezone, defaulting to `Asia/Kolkata`. Store timestamps as `timestamptz`.
- **Primary keys are UUIDs**, generated application-side with `uuid.uuid4()`.

---

## File Structure

**Backend** (`backend/`)

| File | Responsibility |
|---|---|
| `pyproject.toml` | Dependencies and pytest/ruff configuration |
| `app/config.py` | Typed settings loaded from environment |
| `app/main.py` | FastAPI application, CORS, router registration |
| `app/db.py` | Engine, session factory, `get_db` dependency |
| `app/models/base.py` | Declarative base and the shared id/created_at mixin |
| `app/models/user.py` | `User` |
| `app/models/household.py` | `Household`, `HouseholdMember`, `HouseholdInvite` |
| `app/auth/google.py` | Google ID token verification → `GoogleIdentity` |
| `app/auth/session.py` | Session token minting and reading |
| `app/auth/service.py` | Upsert a user from a verified identity |
| `app/auth/deps.py` | `get_current_user` FastAPI dependency |
| `app/auth/router.py` | `/auth/google`, `/auth/me`, `/auth/logout` |
| `app/households/service.py` | Household creation, invites, membership, visibility |
| `app/households/router.py` | `/households` endpoints |
| `alembic/` | Migrations |

**Frontend** (`frontend/`)

| File | Responsibility |
|---|---|
| `src/lib/api.ts` | Typed fetch wrapper that always sends credentials |
| `src/auth/useSession.ts` | TanStack Query hook exposing the signed-in user |
| `src/auth/SignInScreen.tsx` | Google Identity Services button and sign-in call |
| `src/auth/RequireAuth.tsx` | Route guard |
| `src/households/HouseholdScreen.tsx` | Create/view household, invite, visibility toggles |
| `src/AppShell.tsx` | Responsive layout frame |
| `src/App.tsx` | Router |

Split by responsibility rather than by layer: each feature owns its models, service and router together, so a change to households touches one directory.

---

### Task 1: Repository scaffold, Postgres, and a health endpoint

**Files:**
- Create: `.gitignore`
- Create: `docker-compose.yml`
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.config.settings` (a `Settings` instance with `database_url: str`, `test_database_url: str`, `google_client_id: str`, `session_secret: str`, `session_cookie_name: str`, `session_ttl_hours: int`, `frontend_origin: str`, `cookie_secure: bool`); `app.main.app` (the `FastAPI` instance).

- [ ] **Step 1: Initialise the repository**

```bash
cd /Users/sudev-20602/Sudev/healthMonitor
git init
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
.env
.pytest_cache/
.ruff_cache/
node_modules/
dist/
.DS_Store
```

- [ ] **Step 3: Write `docker-compose.yml`**

Two databases on one server: the app database and a separate test database, so a test run can never truncate development data.

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: healthmonitor
      POSTGRES_PASSWORD: healthmonitor
      POSTGRES_DB: healthmonitor
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U healthmonitor"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
```

- [ ] **Step 4: Start Postgres and create the test database**

```bash
docker compose up -d db
until docker compose exec -T db pg_isready -U healthmonitor; do sleep 1; done
docker compose exec -T db psql -U healthmonitor -d healthmonitor -c "CREATE DATABASE healthmonitor_test;"
```

Expected: `CREATE DATABASE`.

- [ ] **Step 5: Write `backend/pyproject.toml`**

```toml
[project]
name = "healthmonitor-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0.36",
    "alembic>=1.14",
    "psycopg[binary]>=3.2",
    "pydantic-settings>=2.6",
    "google-auth>=2.36",
    "pyjwt>=2.10",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "httpx>=0.28",
    "ruff>=0.8",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
```

- [ ] **Step 6: Install dependencies**

```bash
cd backend
uv sync
```

Expected: a `.venv` is created and the packages resolve.

- [ ] **Step 7: Write the failing test**

Create `backend/tests/__init__.py` (empty) and `backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
```

Create `backend/tests/test_health.py`:

```python
def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 9: Write `backend/app/config.py`**

Create `backend/app/__init__.py` (empty), then:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor"
    )
    test_database_url: str = (
        "postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test"
    )

    google_client_id: str = ""

    session_secret: str = "dev-only-insecure-secret-change-me"
    session_cookie_name: str = "hm_session"
    session_ttl_hours: int = 720
    cookie_secure: bool = False

    frontend_origin: str = "http://localhost:5173"


settings = Settings()
```

- [ ] **Step 10: Write `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(title="healthMonitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 12: Write the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: healthmonitor
          POSTGRES_PASSWORD: healthmonitor
          POSTGRES_DB: healthmonitor_test
        ports:
          - 5433:5432
        options: >-
          --health-cmd "pg_isready -U healthmonitor"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
        working-directory: backend
      - run: uv run ruff check .
        working-directory: backend
      - run: uv run pytest -v
        working-directory: backend
```

- [ ] **Step 13: Commit**

```bash
git add .gitignore docker-compose.yml backend/ .github/
git commit -m "feat: scaffold backend with health endpoint and CI"
```

---

### Task 2: Database session, User model, and migrations

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/user.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_user_model.py`

**Interfaces:**
- Consumes: `app.config.settings`.
- Produces: `app.db.engine`, `app.db.SessionLocal`, `app.db.get_db() -> Iterator[Session]`; `app.models.base.Base`, `app.models.base.TimestampedBase` (supplying `id: uuid.UUID` and `created_at: datetime`); `app.models.user.User` with columns `id`, `google_sub`, `email`, `name`, `timezone`, `created_at`. New `db` pytest fixture yielding a transaction-scoped `Session`.

- [ ] **Step 1: Write `backend/app/db.py`**

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 2: Write the model base**

Create `backend/app/models/__init__.py` (empty) and `backend/app/models/base.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampedBase(Base):
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Write the failing test**

Create `backend/tests/test_user_model.py`:

```python
from app.models.user import User


def test_user_defaults_to_india_timezone(db):
    user = User(google_sub="sub-123", email="a@example.com", name="Test Person")

    db.add(user)
    db.flush()

    assert user.id is not None
    assert user.timezone == "Asia/Kolkata"


def test_google_sub_is_unique(db):
    import pytest
    from sqlalchemy.exc import IntegrityError

    db.add(User(google_sub="dup", email="one@example.com", name="One"))
    db.flush()
    db.add(User(google_sub="dup", email="two@example.com", name="Two"))

    with pytest.raises(IntegrityError):
        db.flush()
```

- [ ] **Step 4: Add the `db` fixture**

Replace `backend/tests/conftest.py` with:

```python
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
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_user_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.user'`.

- [ ] **Step 6: Write `backend/app/models/user.py`**

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class User(TimestampedBase):
    __tablename__ = "users"

    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_user_model.py -v`
Expected: PASS — both tests.

- [ ] **Step 8: Initialise Alembic**

```bash
cd backend && uv run alembic init alembic
```

- [ ] **Step 9: Point Alembic at the settings and models**

In `backend/alembic.ini`, delete the `sqlalchemy.url = ...` line entirely — the URL comes from settings instead.

Replace the configuration block near the top of `backend/alembic/env.py` (everything from `config = context.config` down to and including the `target_metadata = None` line) with:

```python
from app.config import settings
from app.models.base import Base
from app.models import user  # noqa: F401  — imported so Alembic sees the table

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
```

- [ ] **Step 10: Generate and apply the first migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "create users table"
uv run alembic upgrade head
```

Expected: a migration file appears under `alembic/versions/` containing `op.create_table("users", ...)`, and `upgrade` completes.

- [ ] **Step 11: Verify the migration matches the models**

```bash
cd backend && uv run alembic check
```

Expected: `No new upgrade operations detected.`

- [ ] **Step 12: Add the migration check to CI**

In `.github/workflows/ci.yml`, insert these two steps immediately before the `uv run pytest` step:

```yaml
      - run: uv run alembic upgrade head
        working-directory: backend
        env:
          DATABASE_URL: postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test
      - run: uv run alembic check
        working-directory: backend
        env:
          DATABASE_URL: postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test
```

This catches the classic failure where a model changes and nobody generates the migration.

- [ ] **Step 13: Commit**

```bash
git add backend/app/db.py backend/app/models/ backend/alembic.ini backend/alembic/ backend/tests/ .github/workflows/ci.yml
git commit -m "feat: add database session, User model, and Alembic migrations"
```

---

### Task 3: Google ID token verification

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/google.py`
- Test: `backend/tests/test_google_verification.py`

**Interfaces:**
- Consumes: `app.config.settings.google_client_id`.
- Produces: `app.auth.google.GoogleIdentity` (frozen dataclass with `google_sub: str`, `email: str`, `name: str`); `app.auth.google.InvalidGoogleToken(Exception)`; `app.auth.google.verify_google_id_token(raw_token: str) -> GoogleIdentity`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_google_verification.py`. The tests patch Google's network call, so no live token is needed.

```python
import pytest

from app.auth import google as google_auth
from app.auth.google import InvalidGoogleToken, verify_google_id_token


def _patch_claims(monkeypatch, claims):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: claims,
    )


def test_returns_identity_for_a_valid_token(monkeypatch):
    _patch_claims(
        monkeypatch,
        {
            "sub": "google-sub-1",
            "email": "person@example.com",
            "email_verified": True,
            "name": "A Person",
        },
    )

    identity = verify_google_id_token("any-token")

    assert identity.google_sub == "google-sub-1"
    assert identity.email == "person@example.com"
    assert identity.name == "A Person"


def test_falls_back_to_email_when_google_sends_no_name(monkeypatch):
    _patch_claims(
        monkeypatch,
        {"sub": "google-sub-2", "email": "noname@example.com", "email_verified": True},
    )

    identity = verify_google_id_token("any-token")

    assert identity.name == "noname@example.com"


def test_rejects_an_unverified_email(monkeypatch):
    _patch_claims(
        monkeypatch,
        {
            "sub": "google-sub-3",
            "email": "unverified@example.com",
            "email_verified": False,
            "name": "Unverified",
        },
    )

    with pytest.raises(InvalidGoogleToken):
        verify_google_id_token("any-token")


def test_rejects_a_token_google_will_not_validate(monkeypatch):
    def explode(token, request, audience):
        raise ValueError("Token has wrong audience")

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", explode)

    with pytest.raises(InvalidGoogleToken):
        verify_google_id_token("tampered-token")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_google_verification.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/auth/__init__.py` (empty) and `backend/app/auth/google.py`:

```python
from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings


class InvalidGoogleToken(Exception):
    """Raised when a Google ID token cannot be trusted."""


@dataclass(frozen=True)
class GoogleIdentity:
    google_sub: str
    email: str
    name: str


def verify_google_id_token(raw_token: str) -> GoogleIdentity:
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_token, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:
        raise InvalidGoogleToken(str(exc)) from exc

    if not claims.get("email_verified", False):
        raise InvalidGoogleToken("Google account email is not verified")

    return GoogleIdentity(
        google_sub=claims["sub"],
        email=claims["email"],
        name=claims.get("name") or claims["email"],
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_google_verification.py -v`
Expected: PASS — all four tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/ backend/tests/test_google_verification.py
git commit -m "feat: verify Google ID tokens into a GoogleIdentity"
```

---

### Task 4: Session tokens

**Files:**
- Create: `backend/app/auth/session.py`
- Test: `backend/tests/test_session_token.py`

**Interfaces:**
- Consumes: `app.config.settings.session_secret`, `settings.session_ttl_hours`.
- Produces: `app.auth.session.InvalidSession(Exception)`; `app.auth.session.create_session_token(user_id: str, *, now: datetime | None = None) -> str`; `app.auth.session.read_session_token(token: str) -> str` returning the user id.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_session_token.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.session import InvalidSession, create_session_token, read_session_token


def test_round_trips_the_user_id():
    token = create_session_token("11111111-1111-1111-1111-111111111111")

    assert read_session_token(token) == "11111111-1111-1111-1111-111111111111"


def test_rejects_an_expired_token():
    long_ago = datetime.now(timezone.utc) - timedelta(days=400)
    token = create_session_token("some-user", now=long_ago)

    with pytest.raises(InvalidSession):
        read_session_token(token)


def test_rejects_a_tampered_token():
    token = create_session_token("some-user")
    tampered = token[:-4] + "abcd"

    with pytest.raises(InvalidSession):
        read_session_token(tampered)


def test_rejects_a_token_signed_with_another_secret():
    import jwt

    forged = jwt.encode(
        {"sub": "intruder", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
        "not-our-secret",
        algorithm="HS256",
    )

    with pytest.raises(InvalidSession):
        read_session_token(forged)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_session_token.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.session'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/auth/session.py`:

```python
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

_ALGORITHM = "HS256"


class InvalidSession(Exception):
    """Raised when a session cookie is missing, expired, or untrustworthy."""


def create_session_token(user_id: str, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(hours=settings.session_ttl_hours)
    payload = {
        "sub": user_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm=_ALGORITHM)


def read_session_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidSession(str(exc)) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise InvalidSession("Session token carries no subject")
    return user_id
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_session_token.py -v`
Expected: PASS — all four tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/session.py backend/tests/test_session_token.py
git commit -m "feat: mint and read signed session tokens"
```

---

### Task 5: Sign-in endpoints and the current-user dependency

**Files:**
- Create: `backend/app/auth/service.py`
- Create: `backend/app/auth/deps.py`
- Create: `backend/app/auth/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_api.py`

**Interfaces:**
- Consumes: `verify_google_id_token`, `GoogleIdentity`, `InvalidGoogleToken`, `create_session_token`, `read_session_token`, `InvalidSession`, `User`, `get_db`.
- Produces: `app.auth.service.upsert_user_from_identity(db: Session, identity: GoogleIdentity) -> User`; `app.auth.deps.get_current_user(request: Request, db: Session) -> User`; router mounted at `/auth` exposing `POST /auth/google` (body `{"credential": str}` → `{"id", "email", "name"}` plus a session cookie), `GET /auth/me`, `POST /auth/logout`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.auth import google as google_auth
from app.auth.deps import get_current_user
from app.db import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def api(db) -> TestClient:
    """A client whose requests run inside the test transaction."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _accept_google_token(monkeypatch, sub="sub-1", email="person@example.com", name="A Person"):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": name,
        },
    )


def test_sign_in_creates_a_user_and_sets_a_cookie(api, db, monkeypatch):
    _accept_google_token(monkeypatch)

    response = api.post("/auth/google", json={"credential": "google-token"})

    assert response.status_code == 200
    assert response.json()["email"] == "person@example.com"
    assert "hm_session" in response.cookies
    assert db.query(User).filter_by(google_sub="sub-1").one().name == "A Person"


def test_signing_in_twice_reuses_the_same_user(api, db, monkeypatch):
    _accept_google_token(monkeypatch)
    first = api.post("/auth/google", json={"credential": "t"}).json()

    _accept_google_token(monkeypatch, name="A Renamed Person")
    second = api.post("/auth/google", json={"credential": "t"}).json()

    assert first["id"] == second["id"]
    assert db.query(User).count() == 1
    assert second["name"] == "A Renamed Person"


def test_rejects_an_untrusted_google_token(api, monkeypatch):
    def explode(token, request, audience):
        raise ValueError("bad audience")

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", explode)

    response = api.post("/auth/google", json={"credential": "nope"})

    assert response.status_code == 401


def test_me_returns_the_signed_in_user(api, monkeypatch):
    _accept_google_token(monkeypatch)
    api.post("/auth/google", json={"credential": "t"})

    response = api.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "person@example.com"


def test_me_requires_a_session(api):
    response = api.get("/auth/me")

    assert response.status_code == 401


def test_logout_clears_the_session(api, monkeypatch):
    _accept_google_token(monkeypatch)
    api.post("/auth/google", json={"credential": "t"})

    api.post("/auth/logout")

    assert api.get("/auth/me").status_code == 401
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.deps'`.

- [ ] **Step 3: Write the user upsert service**

Create `backend/app/auth/service.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.google import GoogleIdentity
from app.models.user import User


def upsert_user_from_identity(db: Session, identity: GoogleIdentity) -> User:
    """Find the user behind a Google identity, creating them on first sign-in.

    Google is the source of truth for email and name, so both are refreshed on
    every sign-in; `google_sub` is the stable key and never changes.
    """
    user = db.scalar(select(User).where(User.google_sub == identity.google_sub))

    if user is None:
        user = User(
            google_sub=identity.google_sub,
            email=identity.email,
            name=identity.name,
        )
        db.add(user)
    else:
        user.email = identity.email
        user.name = identity.name

    db.flush()
    return user
```

- [ ] **Step 4: Write the current-user dependency**

Create `backend/app/auth/deps.py`:

```python
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.session import InvalidSession, read_session_token
from app.config import settings
from app.db import get_db
from app.models.user import User

_UNAUTHORISED = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _UNAUTHORISED

    try:
        user_id = uuid.UUID(read_session_token(token))
    except (InvalidSession, ValueError) as exc:
        raise _UNAUTHORISED from exc

    user = db.get(User, user_id)
    if user is None:
        raise _UNAUTHORISED
    return user
```

- [ ] **Step 5: Write the auth router**

Create `backend/app/auth/router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.google import InvalidGoogleToken, verify_google_id_token
from app.auth.service import upsert_user_from_identity
from app.auth.session import create_session_token
from app.config import settings
from app.db import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleSignInRequest(BaseModel):
    credential: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    timezone: str


@router.post("/google", response_model=UserOut)
def sign_in_with_google(
    payload: GoogleSignInRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    try:
        identity = verify_google_id_token(payload.credential)
    except InvalidGoogleToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in failed") from exc

    user = upsert_user_from_identity(db, identity)
    db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_token(str(user.id)),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
    )
    return user


@router.get("/me", response_model=UserOut)
def read_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name)
```

- [ ] **Step 6: Register the router**

In `backend/app/main.py`, add the import below the existing `from app.config import settings` line:

```python
from app.auth.router import router as auth_router
```

and add this line immediately after the `add_middleware(...)` call:

```python
app.include_router(auth_router)
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_auth_api.py -v`
Expected: PASS — all six tests.

- [ ] **Step 8: Run the whole suite**

Run: `cd backend && uv run pytest -v`
Expected: PASS — every test from Tasks 1–5.

- [ ] **Step 9: Commit**

```bash
git add backend/app/auth/ backend/app/main.py backend/tests/test_auth_api.py
git commit -m "feat: add Google sign-in, session cookie, and current-user dependency"
```

---

### Task 6: Household models

**Files:**
- Create: `backend/app/models/household.py`
- Modify: `backend/alembic/env.py`
- Test: `backend/tests/test_household_models.py`

**Interfaces:**
- Consumes: `TimestampedBase`, `User`.
- Produces: `app.models.household.Household` (`name`, `created_by_user_id`); `app.models.household.HouseholdMember` (`household_id`, `user_id`, `share_progress: bool = True`, `share_health: bool = False`, unique on the pair); `app.models.household.HouseholdInvite` (`household_id`, `email`, `token`, `expires_at`, `accepted_at`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_household_models.py`:

```python
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.household import Household, HouseholdMember
from app.models.user import User


def _user(db, email):
    user = User(google_sub=f"sub-{email}", email=email, name=email)
    db.add(user)
    db.flush()
    return user


def test_membership_defaults_share_progress_but_not_health(db):
    owner = _user(db, "owner@example.com")
    household = Household(name="Home", created_by_user_id=owner.id)
    db.add(household)
    db.flush()

    membership = HouseholdMember(household_id=household.id, user_id=owner.id)
    db.add(membership)
    db.flush()

    assert membership.share_progress is True
    assert membership.share_health is False


def test_a_user_cannot_join_the_same_household_twice(db):
    owner = _user(db, "twice@example.com")
    household = Household(name="Home", created_by_user_id=owner.id)
    db.add(household)
    db.flush()

    db.add(HouseholdMember(household_id=household.id, user_id=owner.id))
    db.flush()
    db.add(HouseholdMember(household_id=household.id, user_id=owner.id))

    with pytest.raises(IntegrityError):
        db.flush()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_household_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.household'`.

- [ ] **Step 3: Write the models**

Create `backend/app/models/household.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class Household(TimestampedBase):
    __tablename__ = "households"

    name: Mapped[str] = mapped_column(String(120))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class HouseholdMember(TimestampedBase):
    __tablename__ = "household_members"
    __table_args__ = (UniqueConstraint("household_id", "user_id", name="uq_household_member"),)

    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Nutrition progress is shared by default so whoever cooks can see it.
    share_progress: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Conditions, labs, medications, weight and cycle data stay private until opted in.
    share_health: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class HouseholdInvite(TimestampedBase):
    __tablename__ = "household_invites"

    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Make Alembic aware of the new models**

In `backend/alembic/env.py`, extend the models import line to:

```python
from app.models import household, user  # noqa: F401  — imported so Alembic sees the tables
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_household_models.py -v`
Expected: PASS — both tests.

- [ ] **Step 6: Generate and apply the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "create household tables"
uv run alembic upgrade head
uv run alembic check
```

Expected: the migration creates `households`, `household_members`, `household_invites`; `alembic check` reports no new operations.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/household.py backend/alembic/ backend/tests/test_household_models.py
git commit -m "feat: add household, membership, and invite models"
```

---

### Task 7: Household service

**Files:**
- Create: `backend/app/households/__init__.py`
- Create: `backend/app/households/service.py`
- Test: `backend/tests/test_household_service.py`

**Interfaces:**
- Consumes: `Household`, `HouseholdMember`, `HouseholdInvite`, `User`.
- Produces, all in `app.households.service`:
  - `create_household(db: Session, owner: User, name: str) -> Household` — also adds the owner as a member.
  - `get_household_for_user(db: Session, user: User) -> Household | None`
  - `list_members(db: Session, household_id: uuid.UUID) -> list[HouseholdMember]`
  - `invite_member(db: Session, household: Household, email: str, *, now: datetime | None = None) -> HouseholdInvite`
  - `accept_invite(db: Session, user: User, token: str, *, now: datetime | None = None) -> HouseholdMember`
  - `update_visibility(db: Session, user: User, *, share_progress: bool | None = None, share_health: bool | None = None) -> HouseholdMember`
  - Exceptions: `AlreadyInHousehold`, `InviteNotFound`, `InviteExpired`, `NotInHousehold`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_household_service.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.households.service import (
    AlreadyInHousehold,
    InviteExpired,
    InviteNotFound,
    NotInHousehold,
    accept_invite,
    create_household,
    get_household_for_user,
    invite_member,
    list_members,
    update_visibility,
)
from app.models.user import User


def _user(db, email):
    user = User(google_sub=f"sub-{email}", email=email, name=email)
    db.add(user)
    db.flush()
    return user


def test_creating_a_household_enrols_the_owner(db):
    owner = _user(db, "owner@example.com")

    household = create_household(db, owner, "Sudev's Home")

    assert household.name == "Sudev's Home"
    assert get_household_for_user(db, owner).id == household.id
    assert [m.user_id for m in list_members(db, household.id)] == [owner.id]


def test_a_user_cannot_create_a_second_household(db):
    owner = _user(db, "owner2@example.com")
    create_household(db, owner, "First")

    with pytest.raises(AlreadyInHousehold):
        create_household(db, owner, "Second")


def test_an_invited_user_joins_the_household(db):
    owner = _user(db, "owner3@example.com")
    guest = _user(db, "guest@example.com")
    household = create_household(db, owner, "Home")
    invite = invite_member(db, household, "guest@example.com")

    membership = accept_invite(db, guest, invite.token)

    assert membership.household_id == household.id
    assert get_household_for_user(db, guest).id == household.id
    assert len(list_members(db, household.id)) == 2


def test_an_invite_cannot_be_used_twice(db):
    owner = _user(db, "owner4@example.com")
    guest = _user(db, "guest4@example.com")
    household = create_household(db, owner, "Home")
    invite = invite_member(db, household, "guest4@example.com")
    accept_invite(db, guest, invite.token)

    other = _user(db, "other4@example.com")
    with pytest.raises(InviteNotFound):
        accept_invite(db, other, invite.token)


def test_an_expired_invite_is_refused(db):
    owner = _user(db, "owner5@example.com")
    guest = _user(db, "guest5@example.com")
    household = create_household(db, owner, "Home")
    long_ago = datetime.now(timezone.utc) - timedelta(days=30)
    invite = invite_member(db, household, "guest5@example.com", now=long_ago)

    with pytest.raises(InviteExpired):
        accept_invite(db, guest, invite.token)


def test_an_unknown_token_is_refused(db):
    guest = _user(db, "guest6@example.com")

    with pytest.raises(InviteNotFound):
        accept_invite(db, guest, "no-such-token")


def test_health_sharing_can_be_switched_on(db):
    owner = _user(db, "owner7@example.com")
    create_household(db, owner, "Home")

    membership = update_visibility(db, owner, share_health=True)

    assert membership.share_health is True
    assert membership.share_progress is True


def test_visibility_requires_a_household(db):
    loner = _user(db, "loner@example.com")

    with pytest.raises(NotInHousehold):
        update_visibility(db, loner, share_progress=False)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_household_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.households'`.

- [ ] **Step 3: Write the service**

Create `backend/app/households/__init__.py` (empty) and `backend/app/households/service.py`:

```python
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdInvite, HouseholdMember
from app.models.user import User

INVITE_TTL = timedelta(days=14)


class AlreadyInHousehold(Exception):
    """The user already belongs to a household."""


class NotInHousehold(Exception):
    """The user belongs to no household."""


class InviteNotFound(Exception):
    """No usable invite matches the token."""


class InviteExpired(Exception):
    """The invite is past its expiry."""


def get_membership(db: Session, user: User) -> HouseholdMember | None:
    return db.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))


def get_household_for_user(db: Session, user: User) -> Household | None:
    membership = get_membership(db, user)
    return db.get(Household, membership.household_id) if membership else None


def create_household(db: Session, owner: User, name: str) -> Household:
    if get_membership(db, owner) is not None:
        raise AlreadyInHousehold(f"{owner.email} already belongs to a household")

    household = Household(name=name, created_by_user_id=owner.id)
    db.add(household)
    db.flush()

    db.add(HouseholdMember(household_id=household.id, user_id=owner.id))
    db.flush()
    return household


def list_members(db: Session, household_id: uuid.UUID) -> list[HouseholdMember]:
    return list(
        db.scalars(
            select(HouseholdMember)
            .where(HouseholdMember.household_id == household_id)
            .order_by(HouseholdMember.created_at)
        )
    )


def invite_member(
    db: Session, household: Household, email: str, *, now: datetime | None = None
) -> HouseholdInvite:
    issued_at = now or datetime.now(timezone.utc)
    invite = HouseholdInvite(
        household_id=household.id,
        email=email.lower(),
        token=secrets.token_urlsafe(32),
        expires_at=issued_at + INVITE_TTL,
    )
    db.add(invite)
    db.flush()
    return invite


def accept_invite(
    db: Session, user: User, token: str, *, now: datetime | None = None
) -> HouseholdMember:
    invite = db.scalar(
        select(HouseholdInvite).where(
            HouseholdInvite.token == token, HouseholdInvite.accepted_at.is_(None)
        )
    )
    if invite is None:
        raise InviteNotFound("That invitation is not valid")

    moment = now or datetime.now(timezone.utc)
    if invite.expires_at < moment:
        raise InviteExpired("That invitation has expired")

    if get_membership(db, user) is not None:
        raise AlreadyInHousehold(f"{user.email} already belongs to a household")

    invite.accepted_at = moment
    membership = HouseholdMember(household_id=invite.household_id, user_id=user.id)
    db.add(membership)
    db.flush()
    return membership


def update_visibility(
    db: Session,
    user: User,
    *,
    share_progress: bool | None = None,
    share_health: bool | None = None,
) -> HouseholdMember:
    membership = get_membership(db, user)
    if membership is None:
        raise NotInHousehold(f"{user.email} belongs to no household")

    if share_progress is not None:
        membership.share_progress = share_progress
    if share_health is not None:
        membership.share_health = share_health

    db.flush()
    return membership
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_household_service.py -v`
Expected: PASS — all eight tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/households/ backend/tests/test_household_service.py
git commit -m "feat: add household service with invites and visibility settings"
```

---

### Task 8: Household endpoints

**Files:**
- Create: `backend/app/households/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_household_api.py`

**Interfaces:**
- Consumes: everything from `app.households.service`, plus `get_current_user`.
- Produces: router mounted at `/households` exposing `POST /households` (body `{"name": str}`), `GET /households/me`, `POST /households/invites` (body `{"email": str}`), `POST /households/invites/accept` (body `{"token": str}`), `PATCH /households/visibility` (body `{"share_progress": bool | null, "share_health": bool | null}`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_household_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.auth import google as google_auth
from app.db import get_db
from app.main import app


@pytest.fixture
def api(db) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def sign_in(api, monkeypatch, sub, email):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": email,
        },
    )
    api.post("/auth/google", json={"credential": "t"})


def test_create_and_read_a_household(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-a", "a@example.com")

    created = api.post("/households", json={"name": "Home"})
    assert created.status_code == 201

    mine = api.get("/households/me")
    assert mine.status_code == 200
    assert mine.json()["name"] == "Home"
    assert len(mine.json()["members"]) == 1
    assert mine.json()["members"][0]["share_health"] is False


def test_household_endpoints_require_sign_in(api):
    assert api.post("/households", json={"name": "Home"}).status_code == 401
    assert api.get("/households/me").status_code == 401


def test_me_returns_404_before_a_household_exists(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-b", "b@example.com")

    assert api.get("/households/me").status_code == 404


def test_creating_a_second_household_is_rejected(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-c", "c@example.com")
    api.post("/households", json={"name": "First"})

    assert api.post("/households", json={"name": "Second"}).status_code == 409


def test_an_invited_user_can_join(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-d", "d@example.com")
    api.post("/households", json={"name": "Home"})
    invite = api.post("/households/invites", json={"email": "guest@example.com"})
    assert invite.status_code == 201
    token = invite.json()["token"]

    api.post("/auth/logout")
    sign_in(api, monkeypatch, "sub-guest", "guest@example.com")
    accepted = api.post("/households/invites/accept", json={"token": token})

    assert accepted.status_code == 200
    assert len(api.get("/households/me").json()["members"]) == 2


def test_an_unknown_invite_token_is_rejected(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-e", "e@example.com")

    response = api.post("/households/invites/accept", json={"token": "nonsense"})

    assert response.status_code == 404


def test_visibility_can_be_updated(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-f", "f@example.com")
    api.post("/households", json={"name": "Home"})

    response = api.patch("/households/visibility", json={"share_health": True})

    assert response.status_code == 200
    assert response.json()["share_health"] is True
    assert response.json()["share_progress"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_household_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.households.router'`.

- [ ] **Step 3: Write the router**

Create `backend/app/households/router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.households import service
from app.models.household import Household
from app.models.user import User

router = APIRouter(prefix="/households", tags=["households"])


class CreateHouseholdRequest(BaseModel):
    name: str


class InviteRequest(BaseModel):
    email: EmailStr


class AcceptInviteRequest(BaseModel):
    token: str


class VisibilityRequest(BaseModel):
    share_progress: bool | None = None
    share_health: bool | None = None


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    share_progress: bool
    share_health: bool


class HouseholdOut(BaseModel):
    id: uuid.UUID
    name: str
    members: list[MemberOut]


class InviteOut(BaseModel):
    token: str
    email: str


class MembershipOut(BaseModel):
    share_progress: bool
    share_health: bool


def _to_household_out(db: Session, household) -> HouseholdOut:
    members = []
    for membership in service.list_members(db, household.id):
        member_user = db.get(User, membership.user_id)
        members.append(
            MemberOut(
                user_id=membership.user_id,
                name=member_user.name,
                email=member_user.email,
                share_progress=membership.share_progress,
                share_health=membership.share_health,
            )
        )
    return HouseholdOut(id=household.id, name=household.name, members=members)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=HouseholdOut)
def create_household(
    payload: CreateHouseholdRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HouseholdOut:
    try:
        household = service.create_household(db, user, payload.name)
    except service.AlreadyInHousehold as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return _to_household_out(db, household)


@router.get("/me", response_model=HouseholdOut)
def read_my_household(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> HouseholdOut:
    household = service.get_household_for_user(db, user)
    if household is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not in a household yet")
    return _to_household_out(db, household)


@router.post("/invites", status_code=status.HTTP_201_CREATED, response_model=InviteOut)
def create_invite(
    payload: InviteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteOut:
    household = service.get_household_for_user(db, user)
    if household is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not in a household yet")

    invite = service.invite_member(db, household, payload.email)
    db.commit()
    return InviteOut(token=invite.token, email=invite.email)


@router.post("/invites/accept", response_model=HouseholdOut)
def accept_invite(
    payload: AcceptInviteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HouseholdOut:
    try:
        membership = service.accept_invite(db, user, payload.token)
    except service.InviteNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except service.InviteExpired as exc:
        raise HTTPException(status.HTTP_410_GONE, str(exc)) from exc
    except service.AlreadyInHousehold as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    return _to_household_out(db, db.get(Household, membership.household_id))


@router.patch("/visibility", response_model=MembershipOut)
def update_visibility(
    payload: VisibilityRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipOut:
    try:
        membership = service.update_visibility(
            db,
            user,
            share_progress=payload.share_progress,
            share_health=payload.share_health,
        )
    except service.NotInHousehold as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    db.commit()
    return MembershipOut(
        share_progress=membership.share_progress, share_health=membership.share_health
    )
```

- [ ] **Step 4: Add the `email-validator` dependency**

`EmailStr` needs it.

```bash
cd backend && uv add "pydantic[email]"
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add the import beside the auth router import:

```python
from app.households.router import router as households_router
```

and the registration beside the existing `include_router` call:

```python
app.include_router(households_router)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_household_api.py -v`
Expected: PASS — all seven tests.

- [ ] **Step 7: Run the whole suite**

Run: `cd backend && uv run pytest -v`
Expected: PASS — everything so far.

- [ ] **Step 8: Commit**

```bash
git add backend/app/households/router.py backend/app/main.py backend/pyproject.toml backend/uv.lock backend/tests/test_household_api.py
git commit -m "feat: expose household, invite, and visibility endpoints"
```

---

### Task 9: Frontend scaffold and Google sign-in

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/.env.local`
- Create: `frontend/src/main.tsx`, `frontend/src/index.css`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/auth/useSession.ts`
- Create: `frontend/src/auth/SignInScreen.tsx`
- Test: `frontend/src/lib/api.test.ts`

**Interfaces:**
- Consumes: the backend's `/auth/*` endpoints.
- Produces: `api.get<T>(path)`, `api.post<T>(path, body)`, `api.patch<T>(path, body)`, and `ApiError` (with a `status` field) from `src/lib/api.ts`; `useSession()` returning `{ user, isLoading }` and `useSignIn()` from `src/auth/useSession.ts`; `<SignInScreen />`.

- [ ] **Step 1: Scaffold the Vite project**

```bash
cd /Users/sudev-20602/Sudev/healthMonitor
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install @tanstack/react-query react-router-dom
npm install -D tailwindcss @tailwindcss/vite vitest jsdom @testing-library/react @testing-library/jest-dom
```

- [ ] **Step 2: Configure Tailwind and Vitest**

Replace `frontend/vite.config.ts` with:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

Replace the contents of `frontend/src/index.css` with:

```css
@import "tailwindcss";
```

- [ ] **Step 3: Record the backend origin and Google client id**

Create `frontend/.env.local`:

```
VITE_API_BASE=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=replace-with-your-oauth-client-id
```

Add `.env.local` to `.gitignore` if it is not already covered by the `.env` entry — add the line `.env.local` to `/Users/sudev-20602/Sudev/healthMonitor/.gitignore`.

- [ ] **Step 4: Write the failing test**

Create `frontend/src/lib/api.test.ts`:

```typescript
import { afterEach, expect, test, vi } from 'vitest'
import { ApiError, api } from './api'

afterEach(() => vi.unstubAllGlobals())

test('sends credentials so the session cookie travels', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), { status: 200 }),
  )
  vi.stubGlobal('fetch', fetchMock)

  await api.get('/auth/me')

  const [, init] = fetchMock.mock.calls[0]
  expect(init.credentials).toBe('include')
})

test('throws an ApiError carrying the status code', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response('nope', { status: 401 })),
  )

  await expect(api.get('/auth/me')).rejects.toBeInstanceOf(ApiError)
  await expect(api.get('/auth/me')).rejects.toMatchObject({ status: 401 })
})

test('returns null for an empty 204 response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))

  await expect(api.post('/auth/logout', {})).resolves.toBeNull()
})
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: FAIL — cannot resolve `./api`.

- [ ] **Step 6: Write the API client**

Create `frontend/src/lib/api.ts`:

```typescript
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    throw new ApiError(response.status, await response.text())
  }
  if (response.status === 204) {
    return null as T
  }
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: PASS — all three tests.

- [ ] **Step 8: Write the session hook**

Create `frontend/src/auth/useSession.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../lib/api'

export interface SessionUser {
  id: string
  email: string
  name: string
  timezone: string
}

export function useSession() {
  const query = useQuery({
    queryKey: ['session'],
    queryFn: async () => {
      try {
        return await api.get<SessionUser>('/auth/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
    retry: false,
  })

  return { user: query.data ?? null, isLoading: query.isLoading }
}

export function useSignIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credential: string) =>
      api.post<SessionUser>('/auth/google', { credential }),
    onSuccess: (user) => queryClient.setQueryData(['session'], user),
  })
}

export function useSignOut() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/auth/logout', {}),
    onSuccess: () => queryClient.setQueryData(['session'], null),
  })
}
```

- [ ] **Step 9: Write the sign-in screen**

Create `frontend/src/auth/SignInScreen.tsx`. Google Identity Services renders its own button; we hand the returned credential straight to the backend.

```tsx
import { useEffect, useRef } from 'react'
import { useSignIn } from './useSession'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (r: { credential: string }) => void }) => void
          renderButton: (parent: HTMLElement, options: Record<string, string>) => void
        }
      }
    }
  }
}

export function SignInScreen() {
  const buttonRef = useRef<HTMLDivElement>(null)
  const signIn = useSignIn()

  useEffect(() => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.onload = () => {
      if (!window.google || !buttonRef.current) return
      window.google.accounts.id.initialize({
        client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
        callback: (response) => signIn.mutate(response.credential),
      })
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: 'outline',
        size: 'large',
      })
    }
    document.body.appendChild(script)
    return () => {
      script.remove()
    }
  }, [signIn])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="max-w-md text-center">
        <h1 className="text-2xl font-semibold">Nutrient Tracker</h1>
        <p className="mt-2 text-sm text-gray-600">
          Track macros and micronutrients on a South Indian diet.
        </p>
      </div>
      <div ref={buttonRef} />
      {signIn.isError && (
        <p className="text-sm text-red-600">Sign-in failed. Please try again.</p>
      )}
    </main>
  )
}
```

- [ ] **Step 10: Wire up the query client**

Replace `frontend/src/main.tsx` with:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 11: Add the frontend to CI**

Append this job to `.github/workflows/ci.yml`:

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: npm ci
        working-directory: frontend
      - run: npx tsc --noEmit
        working-directory: frontend
      - run: npx vitest run
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
```

- [ ] **Step 12: Commit**

```bash
git add frontend/ .github/workflows/ci.yml .gitignore
git commit -m "feat: scaffold React frontend with API client and Google sign-in"
```

---

### Task 10: Protected shell and household screen

**Files:**
- Create: `frontend/src/auth/RequireAuth.tsx`
- Create: `frontend/src/AppShell.tsx`
- Create: `frontend/src/households/useHousehold.ts`
- Create: `frontend/src/households/HouseholdScreen.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/households/HouseholdScreen.test.tsx`

**Interfaces:**
- Consumes: `useSession`, `useSignOut`, `api`.
- Produces: `<RequireAuth>` (renders `SignInScreen` when signed out); `<AppShell>` (responsive frame with header and sign-out); `useHousehold()`, `useCreateHousehold()`, `useInvite()`, `useUpdateVisibility()`; `<HouseholdScreen />`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/households/HouseholdScreen.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { HouseholdScreen } from './HouseholdScreen'

afterEach(() => vi.unstubAllGlobals())

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <HouseholdScreen />
    </QueryClientProvider>,
  )
}

test('offers to create a household when the user has none', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('none', { status: 404 })))

  renderScreen()

  expect(await screen.findByRole('button', { name: /create household/i })).toBeDefined()
})

test('lists members and their sharing state', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'h1',
          name: 'Sudev Home',
          members: [
            {
              user_id: 'u1',
              name: 'Sudev',
              email: 'sudev@example.com',
              share_progress: true,
              share_health: false,
            },
          ],
        }),
        { status: 200 },
      ),
    ),
  )

  renderScreen()

  expect(await screen.findByText('Sudev Home')).toBeDefined()
  expect(await screen.findByText('sudev@example.com')).toBeDefined()
})
```

Add `import '@testing-library/jest-dom'` to a new `frontend/src/setupTests.ts`, and register it by adding `setupFiles: './src/setupTests.ts'` inside the `test` block of `vite.config.ts`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/households/HouseholdScreen.test.tsx`
Expected: FAIL — cannot resolve `./HouseholdScreen`.

- [ ] **Step 3: Write the household hooks**

Create `frontend/src/households/useHousehold.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../lib/api'

export interface Member {
  user_id: string
  name: string
  email: string
  share_progress: boolean
  share_health: boolean
}

export interface Household {
  id: string
  name: string
  members: Member[]
}

export function useHousehold() {
  return useQuery({
    queryKey: ['household'],
    queryFn: async () => {
      try {
        return await api.get<Household>('/households/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    retry: false,
  })
}

export function useCreateHousehold() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.post<Household>('/households', { name }),
    onSuccess: (household) => queryClient.setQueryData(['household'], household),
  })
}

export function useInvite() {
  return useMutation({
    mutationFn: (email: string) =>
      api.post<{ token: string; email: string }>('/households/invites', { email }),
  })
}

export function useUpdateVisibility() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: { share_progress?: boolean; share_health?: boolean }) =>
      api.patch('/households/visibility', changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['household'] }),
  })
}
```

- [ ] **Step 4: Write the household screen**

Create `frontend/src/households/HouseholdScreen.tsx`:

```tsx
import { useState } from 'react'
import {
  useCreateHousehold,
  useHousehold,
  useInvite,
  useUpdateVisibility,
} from './useHousehold'

export function HouseholdScreen() {
  const { data: household, isLoading } = useHousehold()
  const createHousehold = useCreateHousehold()
  const invite = useInvite()
  const updateVisibility = useUpdateVisibility()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')

  if (isLoading) return <p className="p-6 text-sm text-gray-600">Loading…</p>

  if (!household) {
    return (
      <section className="mx-auto max-w-md p-6">
        <h2 className="text-xl font-semibold">Create your household</h2>
        <p className="mt-1 text-sm text-gray-600">
          Household members share the dishes you add, but health details stay private.
        </p>
        <input
          className="mt-4 w-full rounded border p-2"
          placeholder="Household name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button
          className="mt-3 w-full rounded bg-emerald-700 p-2 text-white disabled:opacity-50"
          disabled={!name.trim() || createHousehold.isPending}
          onClick={() => createHousehold.mutate(name.trim())}
        >
          Create household
        </button>
      </section>
    )
  }

  const me = household.members[0]

  return (
    <section className="mx-auto max-w-3xl p-6">
      <h2 className="text-xl font-semibold">{household.name}</h2>

      <ul className="mt-4 divide-y rounded border">
        {household.members.map((member) => (
          <li key={member.user_id} className="flex items-center justify-between p-3">
            <div>
              <p className="font-medium">{member.name}</p>
              <p className="text-sm text-gray-600">{member.email}</p>
            </div>
            <p className="text-sm text-gray-600">
              {member.share_progress ? 'Progress shared' : 'Progress private'}
            </p>
          </li>
        ))}
      </ul>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="font-medium">Invite someone</h3>
          <input
            className="mt-2 w-full rounded border p-2"
            placeholder="their@email.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button
            className="mt-2 w-full rounded border p-2 disabled:opacity-50"
            disabled={!email.trim() || invite.isPending}
            onClick={() => invite.mutate(email.trim())}
          >
            Create invite link
          </button>
          {invite.data && (
            <p className="mt-2 break-all text-sm text-gray-600">
              Share this token with {invite.data.email}: <code>{invite.data.token}</code>
            </p>
          )}
        </div>

        <div>
          <h3 className="font-medium">What you share</h3>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={me?.share_progress ?? true}
              onChange={(event) =>
                updateVisibility.mutate({ share_progress: event.target.checked })
              }
            />
            Share my daily progress with the household
          </label>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={me?.share_health ?? false}
              onChange={(event) =>
                updateVisibility.mutate({ share_health: event.target.checked })
              }
            />
            Share my health details (conditions, weight)
          </label>
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/households/HouseholdScreen.test.tsx`
Expected: PASS — both tests.

- [ ] **Step 6: Write the auth guard and shell**

Create `frontend/src/auth/RequireAuth.tsx`:

```tsx
import type { ReactNode } from 'react'
import { SignInScreen } from './SignInScreen'
import { useSession } from './useSession'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useSession()

  if (isLoading) return <p className="p-6 text-sm text-gray-600">Loading…</p>
  if (!user) return <SignInScreen />
  return <>{children}</>
}
```

Create `frontend/src/AppShell.tsx`:

```tsx
import type { ReactNode } from 'react'
import { useSession, useSignOut } from './auth/useSession'

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useSession()
  const signOut = useSignOut()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between p-4">
          <span className="font-semibold">Nutrient Tracker</span>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-gray-600 sm:inline">{user?.email}</span>
            <button className="rounded border px-3 py-1" onClick={() => signOut.mutate()}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl">{children}</main>
      <footer className="mx-auto max-w-5xl p-6 text-xs text-gray-500">
        This app is not medical advice and does not replace a clinician or dietitian.
      </footer>
    </div>
  )
}
```

- [ ] **Step 7: Wire the router**

Replace `frontend/src/App.tsx` with:

```tsx
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'
import { RequireAuth } from './auth/RequireAuth'
import { HouseholdScreen } from './households/HouseholdScreen'

export default function App() {
  return (
    <RequireAuth>
      <AppShell>
        <Routes>
          <Route path="/household" element={<HouseholdScreen />} />
          <Route path="*" element={<Navigate to="/household" replace />} />
        </Routes>
      </AppShell>
    </RequireAuth>
  )
}
```

- [ ] **Step 8: Verify types and the full frontend suite**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: no type errors; all tests pass.

- [ ] **Step 9: Manual end-to-end check**

1. Create the OAuth client — see **Prerequisite: Google OAuth client** in the spec for the full walkthrough. In short: [console.cloud.google.com/auth/clients](https://console.cloud.google.com/auth/clients) → *Create client* → **Web application**, and add **both** `http://localhost` and `http://localhost:5173` as authorised JavaScript origins (Google treats the bare host and the port-qualified host as different origins, and the sign-in button fails silently if only one is listed). Leave redirect URIs empty and ignore the client secret — this flow doesn't use one. Put the client id in `frontend/.env.local` as `VITE_GOOGLE_CLIENT_ID` and in `backend/.env` as `GOOGLE_CLIENT_ID`. While the app's publishing status is *Testing*, add every Google account that will sign in as a test user.
2. Run `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload`.
3. Run `cd frontend && npm run dev` in a second terminal.
4. Open `http://localhost:5173`, sign in with Google, create a household named "Home".
5. Confirm your name and email appear in the member list, that "Share my daily progress" is **on** and "Share my health details" is **off** by default.
6. Create an invite for a second Google account, sign out, sign in as that account, and accept the token — confirm the member list now shows two people.
7. Narrow the browser to phone width and confirm the layout reflows to a single column rather than overflowing horizontally.

- [ ] **Step 10: Commit**

```bash
git add frontend/src .github/workflows/ci.yml
git commit -m "feat: add protected app shell and household management screen"
```

---

## Self-Review

**Spec coverage for this plan's slice.** Google-only sign-in (Tasks 3–5), multiple users each with their own profile record (Task 2), households with shared dishes and per-member visibility (Tasks 6–8), progress shared by default and health private by default (Task 6 defaults, verified in Tasks 7–8), responsive phone-to-desktop layout (Task 10), not-medical-advice notice (Task 10 footer). Food data, nutrient engine, onboarding, logging, planner, weight, cycle, reports and reminders are explicitly out of scope here and belong to plans 2–9 in `docs/superpowers/plans/README.md`.

**Deliberate deferrals, recorded so they are not mistaken for oversights.** Invite tokens are returned in the API response and copied by hand rather than emailed — email delivery is not needed until the app leaves the family, and adding a mail provider now would be scope creep. There is no household-leave or member-removal endpoint yet; nobody can hit that path before there is data worth moving. `cookie_secure` defaults to false for local HTTP and must be flipped to true at deploy time, which is called out in plan 9.

**Type consistency check.** `GoogleIdentity` fields (`google_sub`, `email`, `name`) match `upsert_user_from_identity`'s usage and the `User` columns. `create_session_token` takes and `read_session_token` returns a `str`, which `get_current_user` converts to `uuid.UUID` — the one place that conversion happens. The service functions named in Task 7's Interfaces block are exactly the ones Task 8 imports (`create_household`, `get_household_for_user`, `list_members`, `invite_member`, `accept_invite`, `update_visibility`) and the exceptions match (`AlreadyInHousehold`, `InviteNotFound`, `InviteExpired`, `NotInHousehold`). The backend's `MemberOut` fields are mirrored by the frontend's `Member` interface field-for-field, including snake_case, since the API is not camel-cased.

**Two bugs caught in review and fixed inline.** The `db` fixture originally created a plain `Session` bound to the connection; because the routers call `db.commit()`, that would have ended the outer transaction and left rows behind between tests. It now passes `join_transaction_mode="create_savepoint"`. And `accept_invite` imported `Household` inside the function body; the import moved to the top of the module.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-15-foundation-auth-households.md`. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, reviewed between tasks, fast iteration.

**2. Inline Execution** — tasks executed in this session using executing-plans, batched with checkpoints for review.
