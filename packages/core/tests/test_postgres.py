"""Postgres-only behaviour that SQLite hides (owner A3). Skipped unless TEST_DATABASE_URL points
at Postgres; CI sets it and also sets REQUIRE_POSTGRES=1 so a silent fall-back to SQLite fails."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.migrate import downgrade, upgrade
from edgefront_core.models import (
    CliProduct,
    DailyHighEvent,
    DsmProduct,
    MetarReport,
    ModelRun,
    ModelRunStation,
    ModelValue,
    Station,
    StationVenue,
)

IS_PG = (os.environ.get("TEST_DATABASE_URL") or "").startswith("postgresql")
pytestmark = pytest.mark.skipif(not IS_PG, reason="needs TEST_DATABASE_URL=postgresql+psycopg://…")
NOW = datetime(2026, 11, 24, 17, 0, tzinfo=UTC)


def test_ci_really_uses_postgres(engine: Engine) -> None:
    assert engine.dialect.name == "postgresql"


def _station(s: Session, sid: str = "KTST") -> None:
    s.add(Station(id=sid, name=sid, city="x", state="TX", tz="America/Chicago"))
    s.flush()  # no ORM relationships, so the unit of work does not order the parent first


def test_session_timezone_is_utc_and_timestamptz_roundtrips(
    engine: Engine, session_factory: sessionmaker[Session]
) -> None:
    with engine.connect() as c:
        assert c.execute(text("SHOW timezone")).scalar() == "UTC"
    cdt = timezone(timedelta(hours=-5))
    with session_scope(session_factory) as s:
        _station(s)
        s.add(
            MetarReport(
                station_id="KTST", report_type="METAR",
                observed_at=datetime(2026, 7, 15, 9, 53, tzinfo=cdt),  # = 14:53Z
                raw_text="x", raw_hash="h", source="t", fetched_at=NOW,
            )
        )  # fmt: skip
    with session_scope(session_factory) as s:
        r = s.scalars(select(MetarReport)).one()
        assert r.observed_at.utcoffset() == timedelta(0)
        assert r.observed_at == datetime(2026, 7, 15, 14, 53, tzinfo=UTC)


def test_json_columns_are_jsonb(engine: Engine) -> None:
    cols = {c["name"]: c for c in inspect(engine).get_columns("metar_reports")}
    assert cols["sky"]["type"].__class__.__name__ == "JSONB"
    cols = {c["name"]: c for c in inspect(engine).get_columns("dsm_products")}
    assert cols["decode_errors"]["type"].__class__.__name__ == "JSONB"


def test_jsonb_roundtrip_and_query(session_factory: sessionmaker[Session]) -> None:
    sky = [{"cover": "BKN", "base_ft": 2500, "type": None}]
    with session_scope(session_factory) as s:
        _station(s)
        s.add(
            MetarReport(
                station_id="KTST", report_type="METAR", observed_at=NOW, raw_text="x",
                raw_hash="h", source="t", fetched_at=NOW, sky=sky,
            )
        )  # fmt: skip
    with session_scope(session_factory) as s:
        assert s.scalars(select(MetarReport.sky)).one() == sky
        n = s.execute(
            text('SELECT count(*) FROM metar_reports WHERE sky @> \'[{"cover": "BKN"}]\'')
        )
        assert n.scalar() == 1


def test_native_enums_reject_unknown_values(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        _station(s)
    with pytest.raises((IntegrityError, DataError)), session_scope(session_factory) as s:
        s.execute(
            text(
                "INSERT INTO station_venues (station_id, venue, market_kind) "
                "VALUES ('KTST', 'betfair', 'high')"
            )
        )


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE stations SET day_basis = 'UTC'",
        "INSERT INTO metar_reports (station_id, report_type, observed_at, raw_text, raw_hash, "
        "source, fetched_at) VALUES ('KTST', 'TAF', now(), 'x', 'h', 't', now())",
        "INSERT INTO dsm_products (station_id, product_id, source, issued_at, issue_key, raw_text, "
        "raw_hash, fetched_at) VALUES ('KTST', 'p', 'tgftp', now(), 'FINAL', 'x', 'h', now())",
        "INSERT INTO cli_products (station_id, product_id, issued_at, report_kind, raw_text, "
        "raw_hash, source, fetched_at) VALUES ('KTST', 'p', now(), 'draft', 'x', 'h', 's', now())",
    ],
)
def test_check_constraints_enforced(session_factory: sessionmaker[Session], sql: str) -> None:
    with session_scope(session_factory) as s:
        _station(s)
    with pytest.raises(IntegrityError), session_scope(session_factory) as s:
        s.execute(text(sql))


def test_unique_constraints(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        _station(s)
    row = {
        "station_id": "KTST", "report_type": "METAR", "observed_at": NOW, "raw_text": "x",
        "raw_hash": "h", "source": "t", "fetched_at": NOW,
    }  # fmt: skip
    with session_scope(session_factory) as s:
        s.add(MetarReport(**row))
    with pytest.raises(IntegrityError), session_scope(session_factory) as s:
        s.add(MetarReport(**row))
    dsm = {
        "station_id": "KTST", "source": "iem", "issued_at": NOW, "climate_date": date(2026, 11, 23),
        "issue_key": "FINAL", "raw_text": "x", "raw_hash": "h", "fetched_at": NOW,
    }  # fmt: skip
    with session_scope(session_factory) as s:
        s.add(DsmProduct(product_id="a", **dsm))
    with pytest.raises(IntegrityError), session_scope(session_factory) as s:
        s.add(DsmProduct(product_id="b", **dsm))  # same day + issue + body hash
    with session_scope(session_factory) as s:
        s.add(CliProduct(product_id="c1", station_id="KTST", issued_at=NOW, raw_text="x",
                         raw_hash="h", source="s", fetched_at=NOW))  # fmt: skip
    with pytest.raises(IntegrityError), session_scope(session_factory) as s:
        s.add(CliProduct(product_id="c1", station_id="KTST", issued_at=NOW, raw_text="y",
                         raw_hash="h2", source="s", fetched_at=NOW))  # fmt: skip


def test_fk_cascades(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        _station(s)
        s.add(StationVenue(station_id="KTST", venue="kalshi", market_kind="high"))
        r = MetarReport(
            station_id="KTST", report_type="METAR", observed_at=NOW, raw_text="x",
            raw_hash="h", source="t", fetched_at=NOW,
        )  # fmt: skip
        s.add(r)
        s.flush()
        s.add(
            DailyHighEvent(
                station_id="KTST", climate_date=date(2026, 11, 24), from_c=Decimal("1.0"),
                to_c=Decimal("2.0"), report_id=r.id, observed_at=NOW,
            )
        )  # fmt: skip
        run = ModelRun(model="gfs", cycle_time=NOW, available_at=NOW)
        s.add(run)
        s.flush()
        s.add(ModelRunStation(run_id=run.id, station_id="KTST", status="ok"))
        s.add(
            ModelValue(
                run_id=run.id, station_id="KTST", valid_time=NOW,
                variable="temp", value=1.0, unit="degC",
            )
        )  # fmt: skip
    with session_scope(session_factory) as s:
        s.execute(text("DELETE FROM metar_reports"))
        s.execute(text("DELETE FROM model_runs"))
        s.execute(text("DELETE FROM stations"))
    with session_scope(session_factory) as s:
        for table in ("daily_high_events", "model_values", "model_run_stations", "station_venues"):
            assert s.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0  # noqa: S608


def test_migrations_down_to_base_and_up_again(db_url: str, engine: Engine) -> None:
    downgrade("base", database_url=db_url)
    left = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert left == set()
    with engine.connect() as c:
        enums = c.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).scalars().all()
    assert enums == []  # venue / market_kind enum types dropped too
    upgrade("head", database_url=db_url)
    assert "dsm_products" in inspect(engine).get_table_names()


def test_worker_lock_admits_exactly_one_worker(engine: Engine) -> None:
    """Phase 6 B2: a second worker waits instead of running every job twice."""
    from edgefront_worker.lock import hold_worker_lock

    first = hold_worker_lock(engine)
    try:
        with pytest.raises(TimeoutError):
            hold_worker_lock(
                engine, poll_seconds=0.01, sleep=lambda _s: None, max_wait_seconds=0.03
            )
    finally:
        first.close()
    second = hold_worker_lock(engine, poll_seconds=0.01, sleep=lambda _s: None, max_wait_seconds=1)
    second.close()  # free once the first worker is gone


def test_auth_schema_tables_and_cascade(db_url: str, engine: Engine) -> None:
    """v2 Phase 7: Better Auth's tables live in schema `auth`; deleting a user removes its
    sessions and accounts; downgrading 0007 removes the schema."""
    insp = inspect(engine)
    assert set(insp.get_table_names(schema="auth")) == {
        "user", "session", "account", "verification", "rateLimit",
    }  # fmt: skip
    cols = {c["name"]: c for c in insp.get_columns("session", schema="auth")}
    assert cols["expiresAt"]["type"].__class__.__name__ == "TIMESTAMP"
    assert getattr(cols["expiresAt"]["type"], "timezone", None) is True
    with engine.begin() as c:
        c.execute(text(
            'INSERT INTO auth."user" (id, name, email, "emailVerified", "createdAt", "updatedAt") '
            "VALUES ('u1', 'A', 'a@example.org', false, now(), now())"
        ))  # fmt: skip
        c.execute(text(
            'INSERT INTO auth.session (id, "expiresAt", token, "createdAt", "updatedAt", "userId") '
            "VALUES ('s1', now(), 't1', now(), now(), 'u1')"
        ))  # fmt: skip
        c.execute(text(
            'INSERT INTO auth.account (id, "accountId", "providerId", "userId", "createdAt", '
            "\"updatedAt\") VALUES ('a1', 'u1', 'credential', 'u1', now(), now())"
        ))  # fmt: skip
        c.execute(text("DELETE FROM auth.\"user\" WHERE id = 'u1'"))
        assert c.execute(text("SELECT count(*) FROM auth.session")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM auth.account")).scalar() == 0
    downgrade("0006", database_url=db_url)
    with engine.connect() as c:
        assert c.execute(text(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'auth'"
        )).scalar() == 0  # fmt: skip
    upgrade("head", database_url=db_url)


def test_billing_schema_tables_constraints_and_cascade(db_url: str, engine: Engine) -> None:
    """v2 Phase 8: the Stripe mirror lives in schema `billing`; one Stripe customer per user,
    event ids are unique, a deleted account takes its billing rows with it; downgrading 0008
    removes the schema and leaves `auth` in place."""
    insp = inspect(engine)
    assert set(insp.get_table_names(schema="billing")) == {
        "customers", "subscriptions", "webhook_events",
    }  # fmt: skip
    cols = {c["name"]: c for c in insp.get_columns("subscriptions", schema="billing")}
    assert cols["current_period_end"]["type"].__class__.__name__ == "TIMESTAMP"
    assert cols["cancel_at_period_end"]["type"].__class__.__name__ == "BOOLEAN"
    with engine.begin() as c:
        c.execute(text(
            'INSERT INTO auth."user" (id, name, email, "emailVerified", "createdAt", "updatedAt") '
            "VALUES ('u1', 'A', 'a@example.org', true, now(), now())"
        ))  # fmt: skip
        c.execute(text(
            "INSERT INTO billing.customers (user_id, stripe_customer_id, created_at) "
            "VALUES ('u1', 'cus_1', now())"
        ))  # fmt: skip
        c.execute(text(
            "INSERT INTO billing.subscriptions (stripe_subscription_id, user_id, "
            "stripe_customer_id, status, updated_at) "
            "VALUES ('sub_1', 'u1', 'cus_1', 'trialing', now())"
        ))  # fmt: skip
        c.execute(text(
            "INSERT INTO billing.webhook_events (stripe_event_id, type, received_at) "
            "VALUES ('evt_1', 'customer.subscription.created', now())"
        ))  # fmt: skip
        flag = c.execute(text("SELECT cancel_at_period_end FROM billing.subscriptions")).scalar()
        assert flag is False
    for dup in (
        "INSERT INTO billing.webhook_events (stripe_event_id, type, received_at) "
        "VALUES ('evt_1', 'x', now())",
        "INSERT INTO billing.customers (user_id, stripe_customer_id, created_at) "
        "VALUES ('u2', 'cus_1', now())",
    ):
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text(dup))
    with engine.begin() as c:
        c.execute(text("DELETE FROM auth.\"user\" WHERE id = 'u1'"))
        assert c.execute(text("SELECT count(*) FROM billing.customers")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM billing.subscriptions")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM billing.webhook_events")).scalar() == 1
    downgrade("0007", database_url=db_url)
    with engine.connect() as c:
        q = text("SELECT schema_name FROM information_schema.schemata")
        schemas = set(c.execute(q).scalars())
    assert "billing" not in schemas
    assert "auth" in schemas
    upgrade("head", database_url=db_url)


def test_hf_observations_types_cascade_and_downgrade(db_url: str, engine: Engine) -> None:
    """v2 Phase 9 B4: qc is jsonb, values numeric, PK (station_id, observed_at); deleting a
    station removes its 5-minute rows; downgrading 0010 drops both tables (up → down → up)."""
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("hf_observations")}
    assert cols["qc"]["type"].__class__.__name__ == "JSONB"
    assert cols["temp_c"]["type"].__class__.__name__ == "NUMERIC"
    assert getattr(cols["observed_at"]["type"], "timezone", None) is True
    assert insp.get_pk_constraint("hf_observations")["constrained_columns"] == [
        "station_id", "observed_at",
    ]  # fmt: skip
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO stations (id, name, city, state, tz) "
            "VALUES ('KTST', 'T', 'x', 'TX', 'America/Chicago')"
        ))  # fmt: skip
        c.execute(text(
            "INSERT INTO hf_observations (station_id, observed_at, temp_c, qc, source_file, "
            "fetched_at, ingested_at, updated_at, row_hash) VALUES ('KTST', now(), 17, "
            "'{\"temperature\": {\"dd\": \"V\"}}', 'f', now(), now(), now(), 'h')"
        ))  # fmt: skip
        dd = c.execute(text("SELECT qc->'temperature'->>'dd' FROM hf_observations")).scalar()
        assert dd == "V"
        assert c.execute(text("SELECT revision FROM hf_observations")).scalar() == 0
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text(
            "INSERT INTO hf_observations (station_id, observed_at, source_file, fetched_at, "
            "ingested_at, updated_at, row_hash) SELECT station_id, observed_at, 'f', now(), "
            "now(), now(), 'h' FROM hf_observations"
        ))  # fmt: skip
    with engine.begin() as c:
        c.execute(text("DELETE FROM stations WHERE id = 'KTST'"))
        assert c.execute(text("SELECT count(*) FROM hf_observations")).scalar() == 0
    downgrade("0009", database_url=db_url)
    left = set(inspect(engine).get_table_names())
    assert "hf_observations" not in left
    assert "hf_files" not in left
    assert "stations" in left
    upgrade("head", database_url=db_url)
    assert "hf_files" in inspect(engine).get_table_names()
