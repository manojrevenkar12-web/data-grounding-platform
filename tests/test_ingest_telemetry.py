"""The door (ingest and outbox), and what the platform team can measure from its own logs."""

from __future__ import annotations

import json
from datetime import datetime

import duckdb

from dgp.platform import contracts, ingest
from dgp.product import telemetry
from tests.test_contracts import row


def write(tmp, name, rows):
    p = tmp / "landing" / "mobility" / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def test_ingest_accepts_refuses_is_idempotent_and_announces_in_order(tmp_path):
    con = ingest.connect(tmp_path / "w.duckdb")
    write(tmp_path, "mobility-202601040000-v1", [row(version=1, year=y) for y in (2023, 2024)])
    write(tmp_path, "mobility-202602010900-v2", [row(version=2, value=None)])
    write(tmp_path, "mobility-202602050900-v2fix", [row(version=2, published_at="2026-02-05T09:00:00")])
    res = ingest.ingest_all(con, tmp_path / "landing")
    assert [r["accepted"] for r in res] == [True, False, True]
    assert con.execute("select count(*) from raw_statistic_values").fetchone()[0] == 3
    events = []
    shipped = ingest.Outbox(con).ship(events.append)
    assert shipped == 2 and [e["event"] for e in events] == ["statistic.published", "statistic.revised"]
    assert ingest.Outbox(con).ship(events.append) == 0  # shipped once
    again = ingest.ingest_file(
        con, tmp_path / "landing" / "mobility" / "mobility-202602050900-v2fix.jsonl", contracts.load("mobility")
    )
    assert again.problems == ["already ingested"]
    assert con.execute("select count(*) from outbox").fetchone()[0] == 2
    con.close()
    prod = telemetry.producers(tmp_path / "w.duckdb")
    assert prod["refused"] == 1 and prod["fixed_after_refusal"] == 1 and prod["days_refused_to_live_median"] == 4.0
    assert prod["refusal_reasons"] == {"value is required and missing": 1}


def test_a_topic_without_a_contract_is_refused(tmp_path):
    con = ingest.connect(tmp_path / "w.duckdb")
    p = tmp_path / "landing" / "pets" / "pets-202601040000-v1.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(row()) + "\n")
    assert ingest.ingest_all(con, tmp_path / "landing") == [
        {"delivery_id": "pets-202601040000-v1", "accepted": False, "problems": ["no contract for pets"]}
    ]


def test_wilson_interval():
    lo, hi = telemetry.wilson(80, 100)
    assert lo < 0.8 < hi and hi - lo < 0.15
    assert telemetry.wilson(0, 0) == (0.0, 1.0)


def test_metrics_from_the_logs(tmp_path):
    t = datetime(2026, 1, 5, 10)
    later = datetime(2026, 1, 19, 10)
    events = [
        {
            "ts": t,
            "account_id": "a",
            "plan": "team",
            "tool": "search",
            "cost_eur": 0.001,
            "latency_ms": 50,
            "cached": False,
            "query": "ev de",
            "results": 0,
        },
        {
            "ts": t,
            "account_id": "a",
            "plan": "team",
            "tool": "search",
            "cost_eur": 0.001,
            "latency_ms": 60,
            "cached": False,
            "query": "ev sales germany",
            "results": 3,
            "top": "ev_sales-DE",
        },
        {
            "ts": later,
            "account_id": "a",
            "plan": "team",
            "tool": "get_statistic",
            "cost_eur": 0.0004,
            "latency_ms": 10,
            "cached": False,
            "status": "ok",
            "stat_id": "ev_sales-DE",
        },
    ]
    sessions = [
        {"session": "s1", "account_id": "a", "ts": t, "query": "ev de", "results": [], "status": "no_match"},
        {
            "session": "s1",
            "account_id": "a",
            "ts": t,
            "query": "ev sales germany",
            "results": ["ev_sales-DE"],
            "fetched": "ev_sales-DE",
            "fetch_status": "ok",
            "status": "ok",
        },
    ]
    tickets = [{"ts": t, "account_id": "a", "stat_id": "ev_sales-DE", "kind": "wrong_number", "query": "x"}]
    audit = [{"ts": t, "account_id": "a", "stat_id": "ev_sales-DE", "version": 1, "correct": True}]
    telemetry.observe(events, sessions, tickets, audit, {"s1": "claude"}, tmp_path / "t.duckdb")
    m = telemetry.metrics(tmp_path / "t.duckdb", scale=10)
    assert m["weeks"] == 2.0
    assert m["drivers"]["zero_result_share"] == 0.5 and m["drivers"]["rephrased_share"] == 1.0
    assert m["drivers"]["searches_per_week"] == 10 and m["guardrails"]["wrong_number_tickets_per_week"] == 5.0
    assert m["north_star"]["estimate_per_week"] == 5 and m["clients"] == {"claude": 1}
    assert m["top_ticketed_statistics"] == [{"stat_id": "ev_sales-DE", "tickets": 1}]
    con = duckdb.connect(str(tmp_path / "t.duckdb"), read_only=True)
    assert con.execute("select count(*) from usage").fetchone()[0] == 3
    con.close()
