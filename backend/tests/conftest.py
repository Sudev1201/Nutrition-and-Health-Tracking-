from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from app.auth import google as google_auth
from app.config import settings
from app.main import app
from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit

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


from app.db import get_db

"""
The test database carries the migrated schema but no seed data — the ETL fills
the development database, not this one. These tests therefore build the small
reference set they assert against, which also keeps them independent of whether
the ETL has been run.

The values are the real ICMR-NIN ones for an adult man, and the compensation
policy per nutrient mirrors the seeded `nutrients` table.
"""

NUTRIENTS = [
    # code, display, unit, category, compensable, days, excess_sensitive
    ("energy", "Energy", "kcal", "macro", True, 2, True),
    ("protein", "Protein", "g", "macro", False, 0, False),
    ("fibre", "Dietary fibre", "g", "macro", True, 2, False),
    ("carbohydrate", "Carbohydrate", "g", "macro", True, 2, False),
    ("fat", "Total fat", "g", "macro", True, 2, False),
    ("saturated_fat", "Saturated fat", "g", "macro", False, 0, True),
    ("free_sugar", "Free sugar", "g", "macro", False, 0, True),
    ("calcium", "Calcium", "mg", "mineral", True, 2, True),
    ("sodium", "Sodium", "mg", "mineral", False, 0, True),
    ("potassium", "Potassium", "mg", "mineral", True, 2, False),
    ("vitamin_b12", "Vitamin B12", "ug", "vitamin", True, 2, False),
    ("thiamine", "Thiamine (B1)", "mg", "vitamin", True, 2, False),
]

# (code, activity_level, ear, rda, ai)
REFERENCE_ROWS = [
    ("calcium", None, 800, 1000, None),
    ("sodium", None, None, None, 2000),
    ("potassium", None, None, None, 3510),
    ("vitamin_b12", None, 2, 2.2, None),
    # Energy-scaled, so stored per activity level.
    ("thiamine", "sedentary", 1.2, 1.4, None),
    ("thiamine", "heavy", 1.9, 2.3, None),
]

# Calcium has an ICMR limit; B12 deliberately has none.
UPPER_LIMIT_ROWS = [("calcium", 2500.0)]


@pytest.fixture
def reference_data(db) -> Dish:
    """Seed the reference tables and one authored dish, returning the dish."""
    nutrients = {}
    for code, display, unit, category, compensable, days, excess in NUTRIENTS:
        nutrient = Nutrient(
            code=code,
            display_name=display,
            unit=unit,
            category=category,
            is_compensable=compensable,
            compensation_days=days,
            is_excess_sensitive=excess,
        )
        db.add(nutrient)
        nutrients[code] = nutrient
    db.flush()

    for sex in ("male", "female"):
        for code, activity, ear, rda, ai in REFERENCE_ROWS:
            db.add(
                RdaReference(
                    nutrient_id=nutrients[code].id,
                    sex=sex,
                    age_band="18-59",
                    activity_level=activity,
                    ear=ear,
                    rda=rda,
                    ai=ai,
                    source="ICMR-NIN-2020",
                )
            )

    for code, value in UPPER_LIMIT_ROWS:
        db.add(
            UpperLimit(
                nutrient_id=nutrients[code].id,
                value=value,
                supplemental_only=False,
                source="ICMR-2018-TUL",
            )
        )

    # A deliberately thin dish: 100 g carries far less calcium than a day needs,
    # so a small portion produces the shortfall the carry-forward tests rely on.
    ingredient = Ingredient(code="test:rice", name="Rice, cooked", source="IFCT")
    db.add(ingredient)
    db.flush()
    for code, per_100g in (("energy", 150.0), ("protein", 4.0), ("calcium", 30.0)):
        db.add(
            IngredientNutrient(
                ingredient_id=ingredient.id,
                nutrient_id=nutrients[code].id,
                per_100g=per_100g,
                source="IFCT",
            )
        )

    dish = Dish(
        code="test:plain-rice",
        name="Plain rice",
        source="authored",
        is_editable=True,
        yield_factor=1.0,
    )
    db.add(dish)
    db.flush()
    db.add(DishIngredient(dish_id=dish.id, ingredient_id=ingredient.id, grams=100.0))
    db.flush()

    return dish


@pytest.fixture
def iron_reference(db, reference_data) -> Nutrient:
    """Iron as the seed carries it for women: ICMR's 29 mg up to 59, and the IOM
    figure of 8 mg stored as the female 60+ row -- the value the spec falls back to
    after menopause, since ICMR-NIN 2020 publishes no postmenopausal category."""
    iron = Nutrient(
        code="iron",
        display_name="Iron",
        unit="mg",
        category="mineral",
        is_compensable=True,
        compensation_days=2,
        is_excess_sensitive=True,
    )
    db.add(iron)
    db.flush()
    for sex, band, ear, rda, source in (
        ("female", "18-59", 15, 29, "ICMR-NIN-2020"),
        ("female", "60+", 5, 8, "IOM"),
        ("male", "18-59", 11, 19, "ICMR-NIN-2020"),
    ):
        db.add(
            RdaReference(
                nutrient_id=iron.id,
                sex=sex,
                age_band=band,
                activity_level=None,
                ear=ear,
                rda=rda,
                ai=None,
                source=source,
            )
        )
    db.add(
        UpperLimit(
            nutrient_id=iron.id, value=45.0, supplemental_only=False, source="ICMR-2018-TUL"
        )
    )
    db.flush()
    return iron


@pytest.fixture
def api_client(db) -> TestClient:
    """A client whose requests run inside the test transaction."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def signed_in(api_client, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": "sub-track",
            "email": "track@example.com",
            "email_verified": True,
            "name": "Tracker",
        },
    )
    api_client.post("/auth/google", json={"credential": "t"})
    return api_client


