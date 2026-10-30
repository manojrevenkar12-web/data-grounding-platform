"""What the platform team can see in production, and nothing more: MCP sessions (queries, what was
fetched, the client), metered calls (cost, latency, status), support tickets about wrong numbers,
analysts' audit of a random sample of answers, and the delivery log at the door.

`observe` stores them (build/telemetry.duckdb); `metrics` turns them into the metrics tree a
platform PM reports: the North Star estimated from the audit, its drivers, and the guardrails."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from .. import settings

SCHEMA = """
create table if not exists usage (ts timestamp, account_id varchar, plan varchar, tool varchar, cost_eur double,
  latency_ms double, cached boolean, status varchar, stat_id varchar, query varchar, results integer);
create table if not exists sessions (session varchar, account_id varchar, client varchar, ts timestamp,
  query varchar, results varchar, fetched varchar, fetch_status varchar, status varchar);
create table if not exists tickets (ts timestamp, account_id varchar, stat_id varchar, kind varchar, query varchar);
create table if not exists audit (ts timestamp, account_id varchar, stat_id varchar, version integer, correct boolean);
"""


def path() -> Path:
    return settings.BUILD / "telemetry.duckdb"


def observe(
    events: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    tickets: list[dict[str, Any]],
    audit: list[dict[str, Any]],
    clients: dict[str, str],
    target: Path | None = None,
) -> None:
    target = target or path()
    if target.exists():
        target.unlink()
    con = duckdb.connect(str(target))
    con.execute(SCHEMA)
    tables = {
        "usage": [
            {
                "ts": e["ts"],
                "account_id": e["account_id"],
                "plan": e["plan"],
                "tool": e["tool"],
                "cost_eur": e["cost_eur"],
                "latency_ms": e["latency_ms"],
                "cached": e["cached"],
                "status": e.get("status"),
                "stat_id": e.get("stat_id") or e.get("top"),
                "query": e.get("query"),
                "results": e.get("results"),
            }
            for e in events
        ],
        "sessions": [
            {
                "session": s["session"],
                "account_id": s["account_id"],
                "client": clients.get(s["session"], ""),
                "ts": s["ts"],
                "query": s["query"],
                "results": json.dumps(s["results"]),
                "fetched": s.get("fetched"),
                "fetch_status": s.get("fetch_status"),
                "status": s["status"],
            }
            for s in sessions
        ],
        "tickets": [{k: t[k] for k in ("ts", "account_id", "stat_id", "kind", "query")} for t in tickets],
        "audit": [{k: a[k] for k in ("ts", "account_id", "stat_id", "version", "correct")} for a in audit],
    }
    for name, rows in tables.items():
        if not rows:
            continue
        tmp = target.with_suffix(f".{name}.jsonl")
        tmp.write_text("\n".join(json.dumps(r, default=str) for r in rows))
        con.execute(
            f"insert into {name} select * from read_json('{tmp}', format='newline_delimited', "
            f"columns={{{', '.join(f"'{c}': '{t}'" for c, t in _types(con, name))}}})"
        )
        tmp.unlink()
    con.close()


def _types(con: duckdb.DuckDBPyConnection, table: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(f"describe {table}").fetchall()]


def wilson(k: int, n: int, z: float = 1.645) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def metrics(telemetry: Path | None = None, warehouse: Path | None = None, scale: float = 1.0) -> dict[str, Any]:
    """`scale`: how many real events one record stands for (1 in production; the simulation samples)."""
    con = duckdb.connect(str(telemetry or path()), read_only=True)
    weeks = con.execute("select (max(ts)::date - min(ts)::date) / 7.0 from usage").fetchone()[0] or 1.0
    weeks = max(1.0, round(float(weeks)))
    rep = scale
    q = lambda sql, *a: con.execute(sql, list(a)).fetchall()  # noqa: E731
    searches = q("select count(*) from usage where tool='search'")[0][0]
    fetches = q("select count(*) from usage where tool='get_statistic'")[0][0]
    zero = q("select count(*) from usage where tool='search' and results=0")[0][0]
    status = dict(q("select status, count(*) from usage where tool='get_statistic' group by 1"))
    ok = status.get("ok", 0)
    sess = q("select count(distinct session), count(*) from sessions")[0]
    rephrased = q("select count(*) from (select session from sessions group by 1 having count(*) > 1)")[0][0]
    lat = [r[0] for r in q("select latency_ms from usage")]
    cost = q("select sum(cost_eur) from usage")[0][0] or 0.0
    audited, right = q("select count(*), coalesce(sum(case when correct then 1 else 0 end), 0) from audit")[0]
    acc = right / audited if audited else None
    lo, hi = wilson(int(right), int(audited))
    tickets = q("select count(*) from tickets")[0][0]
    top_ticketed = q("select stat_id, count(*) n from tickets group by 1 order by n desc, stat_id limit 5")
    clients = dict(q("select client, count(distinct session) from sessions group by 1 order by 2 desc"))
    budget = q("select count(*) from sessions where status='budget_exhausted'")[0][0]
    con.close()
    out = {
        "weeks": weeks,
        "north_star": {
            "estimate_per_week": round(ok * acc / weeks * rep) if acc is not None else None,
            "interval_per_week": [round(ok * lo / weeks * rep), round(ok * hi / weeks * rep)],
            "audited": int(audited),
            "audited_correct": int(right),
            "accuracy_estimate": round(acc, 4) if acc else None,
            "accuracy_interval": [lo, hi],
        },
        "drivers": {
            "sessions_per_week": round(sess[0] / weeks * rep),
            "searches_per_week": round(searches / weeks * rep),
            "zero_result_share": round(zero / max(1, searches), 4),
            "rephrased_share": round(rephrased / max(1, sess[0]), 4),
            "fetch_ok_share": round(ok / max(1, fetches), 4),
            "fetch_status": status,
        },
        "guardrails": {
            "latency_p95_ms": round(float(np.percentile(lat, 95)), 1) if lat else None,
            "cost_per_week_eur": round(cost / weeks * rep, 2),
            "cost_per_fetch_eur": round(cost / max(1, fetches), 5),
            "wrong_number_tickets_per_week": round(tickets / weeks * rep, 1),
            "budget_exhausted_sessions": round(budget * rep),
        },
        "top_ticketed_statistics": [{"stat_id": s, "tickets": n} for s, n in top_ticketed],
        "clients": clients,
    }
    if warehouse:
        out["producers"] = producers(warehouse)
    return out


def producers(warehouse: Path) -> dict[str, Any]:
    """The door: deliveries refused, and how long a refused revision took to go live (the next
    accepted delivery of the same statistics at the same version)."""
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        "select delivery_id, topic, accepted, problems, stat_ids, version, delivered_at "
        "from deliveries order by delivered_at"
    ).fetchall()
    con.close()
    refused = [r for r in rows if not r[2]]
    waits = []
    for _did, topic, _a, _p, sids, version, at in refused:
        fix = next(
            (
                r
                for r in rows
                if r[2]
                and r[1] == topic
                and r[5] == version
                and r[6] > at
                and set(json.loads(r[4])) >= set(json.loads(sids))
            ),
            None,
        )
        if fix:
            waits.append((fix[6] - at).total_seconds() / 86400)
    problems = Counter(p.split(":")[0] for r in refused for p in json.loads(r[3]))
    return {
        "deliveries": len(rows),
        "refused": len(refused),
        "refusal_reasons": dict(problems.most_common(5)),
        "fixed_after_refusal": len(waits),
        "days_refused_to_live_median": round(float(np.median(waits)), 1) if waits else None,
    }
