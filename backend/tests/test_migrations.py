"""Alembic migration tests.

Offline (SQL-generation) tests always run. The online upgrade/downgrade
round trip runs when TEST_DATABASE_URL points at a Postgres database, e.g.
``postgresql+asyncpg://<user>:<password>@127.0.0.1:55432/stockdb``.
"""

import io
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]


def _cfg(buffer: io.StringIO | None = None) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"), output_buffer=buffer)
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


def test_revision_chain_is_linear_and_ends_at_scan_unit_value() -> None:
    script = ScriptDirectory.from_config(_cfg())
    assert script.get_heads() == ["20260927_0005"]
    revs = [r.revision for r in script.walk_revisions()]
    assert revs == [
        "20260927_0005",
        "20260925_0004",
        "20260510_0003",
        "20260315_0002",
        "20260201_0001",
    ]


def _offline_sql(rng: str, monkeypatch) -> str:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    buf = io.StringIO()
    command.upgrade(_cfg(buf), rng, sql=True)
    return buf.getvalue()


def test_agent_steps_migration_sql(monkeypatch) -> None:
    sql = _offline_sql("20260510_0003:20260925_0004", monkeypatch)
    assert "CREATE TABLE agent_steps" in sql
    assert "CREATE INDEX ix_agent_steps_scan_id" in sql
    for col in (
        "parent_scan_id",
        "attempt",
        "agent_decision",
        "approved_by",
        "approved_at",
    ):
        assert f"ALTER TABLE scan_sessions ADD COLUMN {col}" in sql


def test_orm_matches_migration(monkeypatch) -> None:
    from app.models.agent import AgentStep
    from app.models.truth import ScanSession

    sql = _offline_sql("20260510_0003:20260925_0004", monkeypatch)
    for col in AgentStep.__table__.columns:
        assert col.name in sql, col.name
    agent_cols = {
        "parent_scan_id",
        "attempt",
        "agent_run_id",
        "agent_decision",
        "agent_count",
        "agent_reason",
        "approved_by",
        "approved_at",
    }
    assert agent_cols <= {c.name for c in ScanSession.__table__.columns}


def test_scan_unit_value_migration_backfills(monkeypatch) -> None:
    from app.models.truth import ScanSession

    sql = _offline_sql("20260925_0004:20260927_0005", monkeypatch)
    assert "ALTER TABLE scan_sessions ADD COLUMN unit_value" in sql
    assert "ALTER TABLE scan_sessions ADD COLUMN reviewed_at" in sql
    assert (
        "ALTER TABLE scan_sessions ADD COLUMN version INTEGER DEFAULT '1' NOT NULL"
        in sql
    )
    assert "SET reviewed_at = (" in sql and "'SCAN_REVIEWED'" in sql
    assert "SET unit_value = variance_value / variance_count" in sql
    assert "variance_count <> 0" in sql  # never divides by zero
    # only rows whose variance was never changed after it was priced
    assert "manual_count IS NULL AND approved_by IS NULL" in sql
    assert "reviewed_at IS NULL" in sql and "COUNT(DISTINCT s.run_id)" in sql
    assert "payload_json ->> 'variance_count'" in sql  # single shot, re-run since
    assert {"unit_value", "reviewed_at", "version"} <= {
        c.name for c in ScanSession.__table__.columns
    }


def test_full_offline_upgrade_generates(monkeypatch) -> None:
    sql = _offline_sql("head", monkeypatch)
    assert "CREATE TABLE scan_sessions" in sql and "CREATE TABLE agent_steps" in sql


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="no TEST_DATABASE_URL"
)
def test_online_round_trip(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    cfg = _cfg()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "20260510_0003")
    command.upgrade(cfg, "head")
