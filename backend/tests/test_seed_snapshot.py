"""The seed snapshot: export the reference tables, and load them into an empty database.

Everything runs on the test transaction's own connection (`db.connection()`), so
COPY reads and writes rows that the fixture's rollback takes away again. The
round trip empties the nine tables inside that transaction, children first, and
loads the snapshot back into them.
"""

import contextlib
import datetime
import hashlib
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.food import (
    Dish,
    DishIngredient,
    DishNutrient,
    Ingredient,
    IngredientNutrient,
    PortionMeasure,
)
from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit
from app.models.user import User
from scripts import seed_snapshot
from scripts.seed_snapshot import (
    SEED_TABLES,
    SNAPSHOT_FORMAT,
    SnapshotError,
    export_snapshot,
    fingerprints,
    import_snapshot,
)

# What the fixture exports: every seed row, and none of the cook's own dish.
EXPORTED = {
    "nutrients": 2,
    "ingredients": 2,
    "dishes": 2,
    "ingredient_nutrients": 3,
    "rda_reference": 2,
    "upper_limits": 1,
    "dish_ingredients": 1,
    "dish_nutrients": 1,
    "portion_measures": 3,
}
EMPTY = dict.fromkeys(EXPORTED, 0)


@pytest.fixture
def seeded(db) -> dict[str, uuid.UUID]:
    """A few rows in each of the nine tables, and one user's own dish with its rows.

    The values probe the CSV round trip: a comma, a quote and a newline inside a
    value, NULL beside an empty string, a float with no short decimal form, a
    NULL activity level, and two identical portion rows (the table has no
    unique constraint, and the ETL has written such pairs before).
    """
    energy = Nutrient(
        code="snap:energy",
        display_name="Energy",
        unit="kcal",
        category="macro",
        is_compensable=True,
        compensation_days=2,
        is_excess_sensitive=True,
    )
    calcium = Nutrient(
        code="snap:calcium",
        display_name='Calcium, "total"',
        unit="mg",
        category="mineral",
        is_compensable=True,
        compensation_days=2,
        is_excess_sensitive=False,
    )
    rice = Ingredient(
        code="snap:rice",
        name="Rice, parboiled, milled",
        source="IFCT",
        food_group="Cereals and Millets",
        diet_tags="vegetarian veg",
        search_aliases="arisi\nakki | chawal",
    )
    curd = Ingredient(code="snap:curd", name="Curd", source="USDA", food_group=None, diet_tags="")
    cook = User(google_sub="snap-cook", email="cook@example.com", name="Cook")
    db.add_all([energy, calcium, rice, curd, cook])
    db.flush()

    idli = Dish(
        code="snap:idli",
        name="Idli",
        source="authored",
        is_editable=True,
        slot_tags="breakfast dinner",
        diet_tags="vegetarian",
        yield_factor=1.4,
    )
    payasam = Dish(code="snap:indb-payasam", name="Payasam", source="INDB", yield_factor=1.0)
    own = Dish(
        code="snap:user-rasam",
        name="Amma's rasam",
        source="user",
        is_editable=True,
        yield_factor=1.0,
        created_by_user_id=cook.id,
    )
    db.add_all([idli, payasam, own])
    db.flush()

    db.add_all(
        [
            IngredientNutrient(
                ingredient_id=rice.id, nutrient_id=energy.id, per_100g=346.0, source="IFCT"
            ),
            IngredientNutrient(
                ingredient_id=rice.id, nutrient_id=calcium.id, per_100g=0.1 + 0.2, source="IFCT"
            ),
            IngredientNutrient(
                ingredient_id=curd.id, nutrient_id=calcium.id, per_100g=121.0, source=None
            ),
            RdaReference(
                nutrient_id=calcium.id,
                sex="female",
                age_band="18-59",
                activity_level=None,
                ear=800.0,
                rda=1000.0,
                ai=None,
                source="ICMR-NIN-2020",
            ),
            RdaReference(
                nutrient_id=energy.id,
                sex="male",
                age_band="60+",
                activity_level="sedentary",
                ear=None,
                rda=None,
                ai=1800.0,
                source="ICMR-NIN-2020",
            ),
            UpperLimit(
                nutrient_id=calcium.id, value=2500.0, supplemental_only=False, source="ICMR-TUL"
            ),
            DishIngredient(dish_id=idli.id, ingredient_id=rice.id, grams=60.0),
            DishNutrient(dish_id=payasam.id, nutrient_id=energy.id, per_100g=133.3),
            PortionMeasure(dish_id=idli.id, measure_name="1 idli", grams=40.0, is_default=True),
            PortionMeasure(dish_id=idli.id, measure_name="1 idli", grams=40.0, is_default=True),
            PortionMeasure(ingredient_id=curd.id, measure_name="1 katori", grams=100.0),
            # The cook's own dish, and every row hanging off it: none of these is exported.
            DishIngredient(dish_id=own.id, ingredient_id=curd.id, grams=50.0),
            DishNutrient(dish_id=own.id, nutrient_id=energy.id, per_100g=40.0),
            PortionMeasure(dish_id=own.id, measure_name="1 bowl", grams=150.0),
        ]
    )
    db.flush()
    return {"idli": idli.id, "own": own.id, "cook": cook.id}


def wipe(conn) -> None:
    """Empty the nine tables inside the test's transaction, children first."""
    for table in reversed(SEED_TABLES):
        conn.execute(text(f"DELETE FROM {table.name}"))


def row_counts(conn) -> dict[str, int]:
    return {name: fingerprint["rows"] for name, fingerprint in fingerprints(conn).items()}


def edit_manifest(snapshot: Path, change) -> None:
    path = snapshot / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- the round trip ---------------------------------------------------------------------


def test_a_snapshot_loads_back_exactly_into_an_empty_database(db, seeded, tmp_path):
    conn = db.connection()
    before = fingerprints(conn)
    export_snapshot(conn, tmp_path, git_commit="abc123")
    wipe(conn)
    assert row_counts(conn) == EMPTY

    import_snapshot(conn, tmp_path)

    assert fingerprints(conn) == before
    # The source's ids come across, so anything that points at a dish still finds it.
    idli = conn.execute(text("SELECT id FROM dishes WHERE code = 'snap:idli'")).scalar_one()
    assert idli == seeded["idli"]


def test_the_manifest_records_each_file_and_where_it_came_from(db, seeded, tmp_path):
    conn = db.connection()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    manifest = export_snapshot(conn, tmp_path, git_commit="abc123")

    assert manifest == json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == SNAPSHOT_FORMAT
    assert manifest["alembic_revision"] == revision
    assert manifest["git_commit"] == "abc123"
    created = datetime.datetime.fromisoformat(manifest["created_at"])
    assert created.utcoffset() == datetime.timedelta(0)
    # Load order, parents first.
    assert list(manifest["tables"]) == [table.name for table in SEED_TABLES]
    source = fingerprints(conn)
    for name, entry in manifest["tables"].items():
        assert entry["file"] == f"{name}.csv"
        assert entry["sha256"] == sha256_of(tmp_path / entry["file"])
        assert entry["fingerprint"] == source[name]
        assert entry["rows"] == source[name]["rows"]


def test_user_dishes_and_their_rows_stay_out_of_the_snapshot(db, seeded, tmp_path):
    manifest = export_snapshot(db.connection(), tmp_path, git_commit="abc123")

    assert {name: entry["rows"] for name, entry in manifest["tables"].items()} == EXPORTED
    exported = "".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.csv"))
    assert str(seeded["own"]) not in exported
    assert str(seeded["cook"]) not in exported
    assert "snap:user-rasam" not in exported


def test_an_export_never_writes_over_an_earlier_snapshot(db, seeded, tmp_path):
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")

    with pytest.raises(SnapshotError, match="already holds a snapshot"):
        export_snapshot(conn, tmp_path, git_commit="def456")


# --- what the import refuses, leaving nothing loaded ----------------------------------


def test_the_import_refuses_a_database_that_already_holds_reference_data(db, seeded, tmp_path):
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")
    before = fingerprints(conn)

    with pytest.raises(SnapshotError, match="already holds reference data"):
        import_snapshot(conn, tmp_path)

    assert fingerprints(conn) == before


def test_the_import_refuses_a_snapshot_taken_at_another_revision(db, seeded, tmp_path):
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")
    wipe(conn)
    edit_manifest(tmp_path, lambda manifest: manifest.update(alembic_revision="0123456789ab"))

    with pytest.raises(SnapshotError, match="alembic revision 0123456789ab"):
        import_snapshot(conn, tmp_path)

    assert row_counts(conn) == EMPTY


def test_the_import_refuses_a_file_edited_after_the_export(db, seeded, tmp_path):
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")
    wipe(conn)
    path = tmp_path / "ingredient_nutrients.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("346", "364"), encoding="utf-8")

    with pytest.raises(SnapshotError, match=r"ingredient_nutrients\.csv does not match"):
        import_snapshot(conn, tmp_path)

    assert row_counts(conn) == EMPTY


def test_the_import_undoes_every_table_when_a_fingerprint_does_not_match(db, seeded, tmp_path):
    """A file edited and re-hashed passes the hash check. The fingerprints are
    compared after all nine tables are loaded, and the whole load goes back out."""
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")
    wipe(conn)
    path = tmp_path / "dishes.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("Idli", "Dosa"), encoding="utf-8")
    edit_manifest(
        tmp_path, lambda manifest: manifest["tables"]["dishes"].update(sha256=sha256_of(path))
    )

    with pytest.raises(SnapshotError, match=r"fingerprints \(dishes: the rows differ\)"):
        import_snapshot(conn, tmp_path)

    assert row_counts(conn) == EMPTY


def test_the_import_refuses_a_directory_with_no_manifest(db, tmp_path):
    with pytest.raises(SnapshotError, match="holds no manifest.json"):
        import_snapshot(db.connection(), tmp_path)


# --- the command line ---------------------------------------------------------------------


@pytest.fixture
def cli(db, monkeypatch):
    """main() on the test's connection. `_connection` is main's only way to a database,
    so nothing here can commit to one."""

    @contextlib.contextmanager
    def test_connection(**_options):
        yield db.connection()

    monkeypatch.setattr(seed_snapshot, "_connection", test_connection)
    monkeypatch.setattr(seed_snapshot, "_git_commit", lambda: "cli-commit")
    return db.connection()


def test_the_command_line_exports_imports_and_fingerprints(cli, seeded, tmp_path, capsys):
    before = fingerprints(cli)
    out = tmp_path / "seed-snapshot"

    assert seed_snapshot.main(["export", "--out", str(out)]) == 0
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["git_commit"] == (
        "cli-commit"
    )
    assert "dishes: 2 rows" in capsys.readouterr().out

    wipe(cli)
    assert seed_snapshot.main(["import", "--from", str(out)]) == 0
    assert "every table matches its fingerprint" in capsys.readouterr().out

    assert seed_snapshot.main(["fingerprint"]) == 0
    assert json.loads(capsys.readouterr().out) == before


def test_a_refused_import_exits_1_with_the_reason(cli, seeded, tmp_path, capsys):
    seed_snapshot.main(["export", "--out", str(tmp_path)])
    capsys.readouterr()

    assert seed_snapshot.main(["import", "--from", str(tmp_path)]) == 1
    assert "already holds reference data" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [[], ["export"], ["import"], ["import", "--out", "x"], ["restore", "--from", "x"]],
)
def test_the_command_line_rejects_incomplete_arguments(cli, argv, capsys):
    with pytest.raises(SystemExit) as exited:
        seed_snapshot.main(argv)

    assert exited.value.code == 2
    assert "usage:" in capsys.readouterr().err
