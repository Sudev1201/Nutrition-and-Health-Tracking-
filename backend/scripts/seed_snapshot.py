"""Export the reference data to a snapshot, and load a snapshot into an empty database.

The ETL (`python -m etl.run_all`) builds the nine reference tables from three
downloads. A first deploy should not depend on those hosts being up, so the
snapshot carries the ETL's output instead: one CSV per table and a manifest.

Take it from a scratch database built fresh at HEAD (`alembic upgrade head`, then
`python -m etl.run_all`), never from the development database, which holds e2e
users and possibly rows from before the ETL's advisory lock.

    uv run python -m scripts.seed_snapshot export --out seed-snapshot
    uv run python -m scripts.seed_snapshot import --from seed-snapshot
    uv run python -m scripts.seed_snapshot fingerprint

DATABASE_URL picks the database, as it does for the app.

- The export keeps the source's UUIDs and leaves out every user-created dish and
  the rows hanging off one.
- The manifest records each file's row count and SHA-256, a fingerprint of each
  table over its natural keys, the alembic revision and the git commit.
- The import runs in one transaction. It refuses a database at another alembic
  revision, or one whose reference tables are not empty, and a file whose hash
  has changed. It then loads parents first, runs ANALYZE, and compares every
  table's fingerprint with the manifest before anything is committed.
- It is a one-time load. Refreshing a database that already has users goes
  through `etl.run_all`, which updates rows in place by code, so the ids that
  meal logs and plans point at are kept.

The snapshot is derived from IFCT, which has no open licence: keep it out of git
and out of any public release.
"""

import argparse
import contextlib
import datetime
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg
from sqlalchemy import Connection, text

from app.db import engine
from app.models.base import Base
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

SNAPSHOT_FORMAT = 1
MANIFEST = "manifest.json"

# A dish some user created is theirs, not reference data.
_SEED_DISH_IDS = "SELECT id FROM dishes WHERE created_by_user_id IS NULL"


def _fingerprint(fields: Sequence[str], rows: str) -> str:
    """A table's row count, and an md5 over its rows as natural keys and values.

    It names each row by codes rather than ids, so it compares across any two
    loads of the same data, and it reads references through their joins, so a
    row pointing at the wrong parent changes it. `quote_nullable` keeps NULL
    apart from '' and a '|' inside a value apart from the separator. The rows are
    sorted by their own text under the "C" collation, so the order does not
    depend on the server's locale or on duplicate rows.
    """
    line = "concat_ws('|', " + ", ".join(f"quote_nullable({field})" for field in fields) + ")"
    return (
        "SELECT count(*) AS rows,"
        " md5(coalesce(string_agg(line, E'\\n' ORDER BY line COLLATE \"C\"), '')) AS md5"
        f" FROM (SELECT {line} AS line FROM {rows}) AS lines"
    )


@dataclass(frozen=True)
class SeedTable:
    name: str
    model: type[Base]  # columns come from model.__table__.columns, in table order
    where: str | None  # SQL filter on the export, None for every row
    fingerprint_sql: str  # SELECT count(*) AS rows, md5(string_agg(... ORDER BY line COLLATE "C"))


# Load order: every table after the tables it points at.
#
# In the four dish tables the user-dish filter is written twice: once in `where`, which
# picks the rows the export writes, and once in the fingerprint's WHERE, which picks the
# rows the manifest's fingerprint covers and the import re-checks. The two must agree,
# or a correct file could never match its own fingerprint. They are written separately
# because the export reads the bare table while the fingerprint reads through aliased
# joins; export_snapshot compares their row counts, so a change to one alone fails at
# export rather than at import.
SEED_TABLES: tuple[SeedTable, ...] = (
    SeedTable(
        "nutrients",
        Nutrient,
        None,
        _fingerprint(
            [
                "n.code",
                "n.display_name",
                "n.unit",
                "n.category",
                "n.is_compensable",
                "n.compensation_days",
                "n.is_excess_sensitive",
            ],
            "nutrients AS n",
        ),
    ),
    SeedTable(
        "ingredients",
        Ingredient,
        None,
        _fingerprint(
            [
                "i.code",
                "i.name",
                "i.source",
                "i.food_group",
                "i.diet_tags",
                "i.oxalate_class",
                "i.search_aliases",
            ],
            "ingredients AS i",
        ),
    ),
    SeedTable(
        "dishes",
        Dish,
        "created_by_user_id IS NULL",
        _fingerprint(
            [
                "d.code",
                "d.name",
                "d.source",
                "d.is_editable",
                "d.slot_tags",
                "d.diet_tags",
                "d.yield_factor",
            ],
            "dishes AS d WHERE d.created_by_user_id IS NULL",
        ),
    ),
    SeedTable(
        "ingredient_nutrients",
        IngredientNutrient,
        None,
        _fingerprint(
            ["i.code", "n.code", "x.per_100g", "x.source"],
            "ingredient_nutrients AS x"
            " JOIN ingredients AS i ON i.id = x.ingredient_id"
            " JOIN nutrients AS n ON n.id = x.nutrient_id",
        ),
    ),
    SeedTable(
        "rda_reference",
        RdaReference,
        None,
        _fingerprint(
            [
                "n.code",
                "r.sex",
                "r.age_band",
                "r.activity_level",
                "r.ear",
                "r.rda",
                "r.ai",
                "r.source",
            ],
            "rda_reference AS r JOIN nutrients AS n ON n.id = r.nutrient_id",
        ),
    ),
    SeedTable(
        "upper_limits",
        UpperLimit,
        None,
        _fingerprint(
            ["n.code", "u.value", "u.supplemental_only", "u.source"],
            "upper_limits AS u JOIN nutrients AS n ON n.id = u.nutrient_id",
        ),
    ),
    SeedTable(
        "dish_ingredients",
        DishIngredient,
        f"dish_id IN ({_SEED_DISH_IDS})",
        _fingerprint(
            ["d.code", "i.code", "x.grams"],
            "dish_ingredients AS x"
            " JOIN dishes AS d ON d.id = x.dish_id"
            " JOIN ingredients AS i ON i.id = x.ingredient_id"
            " WHERE d.created_by_user_id IS NULL",
        ),
    ),
    SeedTable(
        "dish_nutrients",
        DishNutrient,
        f"dish_id IN ({_SEED_DISH_IDS})",
        _fingerprint(
            ["d.code", "n.code", "x.per_100g"],
            "dish_nutrients AS x"
            " JOIN dishes AS d ON d.id = x.dish_id"
            " JOIN nutrients AS n ON n.id = x.nutrient_id"
            " WHERE d.created_by_user_id IS NULL",
        ),
    ),
    SeedTable(
        "portion_measures",
        PortionMeasure,
        f"dish_id IS NULL OR dish_id IN ({_SEED_DISH_IDS})",
        _fingerprint(
            ["d.code", "i.code", "p.measure_name", "p.grams", "p.is_default"],
            "portion_measures AS p"
            " LEFT JOIN dishes AS d ON d.id = p.dish_id"
            " LEFT JOIN ingredients AS i ON i.id = p.ingredient_id"
            " WHERE p.dish_id IS NULL OR d.created_by_user_id IS NULL",
        ),
    ),
)


class SnapshotError(RuntimeError):
    """A snapshot that cannot be written or loaded, and why, in plain words."""


def fingerprints(conn: Connection) -> dict[str, dict[str, object]]:
    """Every seed table's row count and md5, keyed by table name, in load order."""
    result: dict[str, dict[str, object]] = {}
    for table in SEED_TABLES:
        row = conn.execute(text(table.fingerprint_sql)).one()
        result[table.name] = {"rows": row.rows, "md5": row.md5}
    return result


def export_snapshot(conn: Connection, out_dir: Path, *, git_commit: str) -> dict:
    """Write one CSV per seed table and a manifest into `out_dir`. Returns the manifest.

    The manifest is written last, so an export that fails partway leaves a
    directory that the import refuses.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir / MANIFEST).exists():
        raise SnapshotError(f"{out_dir} already holds a snapshot; export into a new directory")

    expected = fingerprints(conn)
    tables: dict[str, dict[str, object]] = {}
    for table in SEED_TABLES:
        path = out_dir / f"{table.name}.csv"
        rows, sha256 = _copy_out(conn, table, path)
        if rows != expected[table.name]["rows"]:
            raise SnapshotError(
                f"{table.name}: the export wrote {rows} rows but the fingerprint counts "
                f"{expected[table.name]['rows']}; the export filter and the fingerprint disagree"
            )
        tables[table.name] = {
            "rows": rows,
            "sha256": sha256,
            "file": path.name,
            "fingerprint": expected[table.name],
        }

    manifest = {
        "format": SNAPSHOT_FORMAT,
        "alembic_revision": _revision(conn),
        "git_commit": git_commit,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "tables": tables,
    }
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def import_snapshot(conn: Connection, src: Path) -> None:
    """Load a snapshot into a database whose reference tables are empty.

    Every check that needs no write runs first. The load itself runs under a
    savepoint, so a fingerprint that does not match takes every loaded row back
    out, whether the caller then commits or not.
    """
    manifest = _read_manifest(src)
    revision = _revision(conn)
    if manifest["alembic_revision"] != revision:
        raise SnapshotError(
            f"The snapshot was taken at alembic revision {manifest['alembic_revision']}, but "
            f"the target database is at {revision}. Migrate the target, or export a new "
            "snapshot from a database at the same revision."
        )
    occupied = [
        table.name
        for table in SEED_TABLES
        if conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {table.name})")).scalar_one()
    ]
    if occupied:
        raise SnapshotError(
            f"The target database already holds reference data ({', '.join(occupied)}). "
            "A snapshot loads only into empty tables; refresh a live database with "
            "`python -m etl.run_all` instead."
        )
    contents = {table.name: _verified_file(src, table, manifest) for table in SEED_TABLES}

    with conn.begin_nested():
        for table in SEED_TABLES:
            _copy_in(conn, table, contents[table.name])
        for table in SEED_TABLES:
            # Without statistics the planner's dish-nutrient join has been seen to
            # take 28 s per dish instead of 0.09 s (tests/test_dish_coverage.py).
            conn.execute(text(f"ANALYZE {table.name}"))
        _check_fingerprints(fingerprints(conn), manifest)


def _columns(table: SeedTable) -> str:
    return ", ".join(f'"{column.name}"' for column in table.model.__table__.columns)


def _copy_out(conn: Connection, table: SeedTable, path: Path) -> tuple[int, str]:
    """COPY one table's rows to `path`; returns (rows, sha256)."""
    where = f" WHERE {table.where}" if table.where else ""
    sql = (
        f"COPY (SELECT {_columns(table)} FROM {table.name}{where} ORDER BY id)"
        " TO STDOUT WITH (FORMAT csv, HEADER true)"
    )
    digest = hashlib.sha256()
    raw = conn.connection.driver_connection
    with path.open("wb") as handle, raw.cursor() as cursor:
        with cursor.copy(sql) as copy:
            for block in copy:
                handle.write(block)
                digest.update(block)
        rows = cursor.rowcount
    return rows, digest.hexdigest()


def _copy_in(conn: Connection, table: SeedTable, data: bytes) -> None:
    """COPY one CSV into its table. HEADER MATCH refuses a file whose columns differ."""
    sql = f"COPY {table.name} ({_columns(table)}) FROM STDIN WITH (FORMAT csv, HEADER MATCH)"
    raw = conn.connection.driver_connection
    try:
        with raw.cursor() as cursor, cursor.copy(sql) as copy:
            copy.write(data)
    except psycopg.Error as exc:
        raise SnapshotError(
            f"{table.name}.csv could not be loaded: {type(exc).__name__}: "
            f"{exc.diag.message_primary}"
        ) from exc


def _read_manifest(src: Path) -> dict:
    path = src / MANIFEST
    if not path.is_file():
        raise SnapshotError(f"{src} holds no {MANIFEST}, so it is not a finished snapshot")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        snapshot_format = manifest["format"]
        listed = set(manifest["tables"])
        entries_complete = isinstance(manifest["alembic_revision"], str) and all(
            {"sha256", "fingerprint"} <= set(entry) for entry in manifest["tables"].values()
        )
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise SnapshotError(f"{path} is not a snapshot manifest") from exc
    if not entries_complete:
        raise SnapshotError(f"{path} is not a snapshot manifest")
    if snapshot_format != SNAPSHOT_FORMAT:
        raise SnapshotError(
            f"{src} is snapshot format {snapshot_format}; this script reads format "
            f"{SNAPSHOT_FORMAT}"
        )
    expected = {table.name for table in SEED_TABLES}
    if listed != expected:
        raise SnapshotError(
            f"The manifest lists the tables {sorted(listed)}, not the seed tables "
            f"{sorted(expected)}"
        )
    return manifest


def _verified_file(src: Path, table: SeedTable, manifest: dict) -> bytes:
    """The table's CSV, read once, after its hash matched the manifest."""
    path = src / f"{table.name}.csv"
    if not path.is_file():
        raise SnapshotError(f"{path.name} is missing from {src}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["tables"][table.name]["sha256"]:
        raise SnapshotError(
            f"{path.name} does not match its manifest (its SHA-256 differs), so the "
            "snapshot is damaged or was edited after export"
        )
    return data


def _check_fingerprints(loaded: dict[str, dict[str, object]], manifest: dict) -> None:
    problems = []
    for table in SEED_TABLES:
        expected = manifest["tables"][table.name]["fingerprint"]
        got = loaded[table.name]
        if got["rows"] != expected["rows"]:
            problems.append(f"{table.name}: {got['rows']} rows loaded, {expected['rows']} expected")
        elif got["md5"] != expected["md5"]:
            problems.append(f"{table.name}: the rows differ")
    if problems:
        raise SnapshotError(
            "The loaded data does not match the manifest's fingerprints ("
            + "; ".join(problems)
            + "), so nothing was imported"
        )


def _revision(conn: Connection) -> str:
    """The database's one alembic revision."""
    if conn.execute(text("SELECT to_regclass('alembic_version')")).scalar() is None:
        raise SnapshotError(
            "The database has no alembic_version table. Run `alembic upgrade head` on it first."
        )
    revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if len(revisions) != 1:
        raise SnapshotError(f"The database's alembic_version holds {revisions}, not one revision")
    return revisions[0]


@contextlib.contextmanager
def _connection(*, repeatable_read: bool = False) -> Iterator[Connection]:
    """One connection in one transaction: committed if the block succeeds, else rolled back.

    The export reads under REPEATABLE READ, so every file and every fingerprint
    come from the same snapshot of the database.
    """
    options = {"isolation_level": "REPEATABLE READ"} if repeatable_read else {}
    with engine.connect().execution_options(**options) as conn, conn.begin():
        yield conn


def _git_commit() -> str:
    """The checkout's commit, so a snapshot can be traced to the ETL that built it."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_snapshot",
        description="Export the reference data to a snapshot, or load one into an empty database.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="write a snapshot of this database")
    export.add_argument("--out", type=Path, required=True, help="a new or empty directory")
    load = commands.add_parser("import", help="load a snapshot into this empty database")
    load.add_argument("--from", dest="source", type=Path, required=True, help="a snapshot")
    commands.add_parser("fingerprint", help="print each seed table's row count and md5")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "export":
            with _connection(repeatable_read=True) as conn:
                manifest = export_snapshot(conn, args.out, git_commit=_git_commit())
            for name, table in manifest["tables"].items():
                print(f"{name}: {table['rows']} rows")
            print(f"snapshot written to {args.out}")
        elif args.command == "import":
            with _connection() as conn:
                import_snapshot(conn, args.source)
            print(f"imported {args.source}: every table matches its fingerprint")
        else:
            with _connection() as conn:
                print(json.dumps(fingerprints(conn), indent=2))
    except SnapshotError as exc:
        print(f"seed snapshot: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
