"""The orchestrator's concurrency guard.

`main()` used to take no lock and commit once at the end, so two runs
overlapping interleaved their writes and left orphan rows behind -- an
inconsistency that was mistaken for a loader bug on this plan and cost a
wasted investigation.

The load itself is stubbed out here: what is under test is the lock around it,
and these run against the test database rather than the developer's real one.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import text

from etl import run_all


def _lock_holders(connection) -> int:
    return connection.execute(
        text(
            "select count(*) from pg_locks where locktype = 'advisory' "
            "and objid = :key and granted"
        ),
        {"key": run_all.ETL_LOCK_KEY},
    ).scalar_one()


@pytest.fixture
def etl_engine(engine):
    """`run_all` reads its engine at module scope, so it is patchable."""
    with patch.object(run_all, "engine", engine):
        yield engine


def test_the_load_runs_holding_an_advisory_lock(etl_engine):
    """Held for the whole load, not merely acquired: the lock has to outlive
    the commit, or a waiting run could start reading a half-written database
    the moment the first one's last write lands."""
    observed = {}

    def fake_load():
        with etl_engine.connect() as watcher:
            observed["during"] = _lock_holders(watcher)

    with patch.object(run_all, "_load_everything", fake_load):
        run_all.main()

    with etl_engine.connect() as watcher:
        assert _lock_holders(watcher) == 0
    assert observed["during"] == 1


def test_the_lock_is_released_even_when_the_load_fails(etl_engine):
    def exploding_load():
        raise RuntimeError("boom")

    with (
        patch.object(run_all, "_load_everything", exploding_load),
        pytest.raises(RuntimeError),
    ):
        run_all.main()

    with etl_engine.connect() as watcher:
        assert _lock_holders(watcher) == 0
