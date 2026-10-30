"""The door: every delivery in the landing zone is checked against its topic's contract. Accepted rows
land in `raw_statistic_values`; refused deliveries go to `quarantine` with their reasons and never
reach a consumer. Each newly published (statistic, version) is written to the `outbox` in the same
transaction, and the revision stream (Kafka in production) is fed from the outbox, so a revision is
announced if and only if it was stored."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from . import contracts

SCHEMA = """
create table if not exists raw_statistic_values (
  delivery_id varchar, stat_id varchar, metric varchar, geo varchar, topic varchar, title varchar,
  keywords varchar[], unit varchar, premium boolean, source varchar, year integer, value double,
  is_forecast boolean, version integer, published_at timestamp, ingested_at timestamp);
create table if not exists deliveries (delivery_id varchar primary key, topic varchar, file varchar,
  rows integer, accepted boolean, problems varchar, contract_version varchar, checked_at timestamp,
  stat_ids varchar, version integer, delivered_at timestamp);
create table if not exists outbox (seq bigint primary key, event varchar, stat_id varchar, version integer,
  published_at timestamp, payload varchar, shipped boolean default false);
create sequence if not exists outbox_seq;
"""


def connect(path: Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    if not read_only:
        con.execute(SCHEMA)
    return con


def live_versions(con: duckdb.DuckDBPyConnection, topic: str) -> dict[str, int]:
    rows = con.execute(
        "select stat_id, max(version) from raw_statistic_values where topic=? group by 1", [topic]
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def ingest_file(
    con: duckdb.DuckDBPyConnection, path: Path, contract: dict[str, Any], now: datetime | None = None
) -> contracts.Verdict:
    delivery_id, topic = path.stem, path.parent.name
    if con.execute("select 1 from deliveries where delivery_id=?", [delivery_id]).fetchone():
        return contracts.Verdict(True, ["already ingested"], 0)  # idempotent: a re-sent file is a no-op
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    verdict = contracts.validate(contract, rows, live_versions(con, topic))
    now = now or datetime.now(UTC).replace(tzinfo=None)
    con.execute("begin")
    try:
        sids = sorted({str(r.get("stat_id")) for r in rows})
        versions = [r.get("version") for r in rows if isinstance(r.get("version"), int)]
        con.execute(
            "insert into deliveries values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                delivery_id,
                topic,
                str(path.name),
                len(rows),
                verdict.accepted,
                json.dumps(verdict.problems),
                str(contract["version"]),
                now,
                json.dumps(sids),
                max(versions) if versions else None,
                delivered_at(delivery_id),
            ],
        )
        if verdict.accepted:
            con.executemany(
                "insert into raw_statistic_values values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        delivery_id,
                        r["stat_id"],
                        r["metric"],
                        r["geo"],
                        r["topic"],
                        r["title"],
                        r.get("keywords") or [],
                        r["unit"],
                        r["premium"],
                        r["source"],
                        r["year"],
                        r["value"],
                        r["is_forecast"],
                        r["version"],
                        datetime.fromisoformat(r["published_at"]),
                        now,
                    ]
                    for r in rows
                ],
            )
            published = sorted({(r["stat_id"], r["version"], r["published_at"]) for r in rows})
            for sid, version, at in published:
                event = "statistic.published" if version == 1 else "statistic.revised"
                con.execute(
                    "insert into outbox (seq, event, stat_id, version, published_at, payload) values "
                    "(nextval('outbox_seq'), ?, ?, ?, ?, ?)",
                    [
                        event,
                        sid,
                        version,
                        datetime.fromisoformat(at),
                        json.dumps({"stat_id": sid, "version": version, "topic": topic}),
                    ],
                )
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    return verdict


def delivered_at(delivery_id: str) -> datetime:
    """Producers name files <topic>-<YYYYmmddHHMM>-v<version>[fix]."""
    return datetime.strptime(delivery_id.split("-")[-2], "%Y%m%d%H%M")


def ingest_all(con: duckdb.DuckDBPyConnection, landing: Path, root: Path | None = None) -> list[dict[str, Any]]:
    cs = contracts.all_contracts(root)
    out = []
    files = sorted(landing.glob("*/*.jsonl"), key=lambda p: (p.stem.split("-")[-2], p.stem))
    for path in files:
        topic = path.parent.name
        if topic not in cs:
            out.append({"delivery_id": path.stem, "accepted": False, "problems": [f"no contract for {topic}"]})
            continue
        v = ingest_file(con, path, cs[topic])
        out.append({"delivery_id": path.stem, "accepted": v.accepted, "problems": v.problems})
    return out


class Outbox:
    """Ships outbox events in order to subscribers (the revision stream); at-least-once, so consumers
    deduplicate by (stat_id, version)."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self.con = con

    def ship(self, publish: Any, batch: int = 500) -> int:
        rows = self.con.execute(
            "select seq, event, stat_id, version, published_at, payload from outbox "
            "where not shipped order by seq limit ?",
            [batch],
        ).fetchall()
        for seq, event, sid, version, at, payload in rows:
            publish(
                {
                    "seq": seq,
                    "event": event,
                    "stat_id": sid,
                    "version": version,
                    "published_at": at,
                    **json.loads(payload),
                }
            )
            self.con.execute("update outbox set shipped=true where seq=?", [seq])
        return len(rows)
