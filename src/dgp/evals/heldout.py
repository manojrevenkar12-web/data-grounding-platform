"""Held-out questions, written blind from heldout/WRITING_QUESTIONS.md and the public catalogue
listing by someone who has not seen how the platform searches. Each is asked once (no rephrasing)
through today's platform and through the platform with the planned bets, by the same stand-in
client as the simulation, and scored against the catalogue.

The first run of a set is written once to reports/heldout/<set>/first_run.json and never rewritten.
Never change the platform to pass a set; if its failures are studied, write `regression` to
heldout/<set>/STATUS and have a new set written blind."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import yaml

from .. import settings
from ..platform.catalog import Catalog
from ..platform.grounding import Account, Grounding
from ..sim import catalogue, world

KIND = {"value": "plain", "no_data": "uncovered", "not_entitled": "premium"}


def load(name: str) -> list[dict[str, Any]]:
    return yaml.safe_load((settings.HELDOUT / name / "questions.yaml").read_text())


def status(name: str) -> str:
    p = settings.HELDOUT / name / "STATUS"
    return p.read_text().strip() if p.exists() else "heldout"


def to_question(k: int, c: dict[str, Any], stats: dict[str, catalogue.Statistic], ts: datetime) -> world.Question:
    as_of = datetime.fromisoformat(str(c["as_of"])) if c.get("as_of") else None
    sid = c.get("stat_id") or next(iter(stats))
    year = int(c.get("year") or 0)
    if c["expect"] == "value":
        gold = world.gold_for(stats[sid], year, as_of or ts)
    else:
        gold = {"answer": c["expect"]}
    acc = Account(f"heldout-{c['plan']}", c["plan"])
    return world.Question(100_000 + k, ts, acc, "heldout", KIND[c["expect"]], sid, year, c["question"], as_of, gold,
                          f"h{k}", attempt=2)  # attempt 2: the stand-in client does not rephrase


def run(name: str, flags_by_config: dict[str, dict[str, Any]], glossary: dict[str, Any] | None) -> dict[str, Any]:
    stats = catalogue.build()
    ts = world.start() + timedelta(weeks=settings.load("world")["weeks"]) - timedelta(hours=1)
    cases = load(name)
    out: dict[str, Any] = {"set": name, "status": status(name), "cases": len(cases), "configs": {}}
    for config, flags in flags_by_config.items():
        g = Grounding(Catalog.load(features=flags, glossary=glossary if flags.get("glossary") else None))
        r = world.Run()
        rows = []
        for k, c in enumerate(cases):
            q = to_question(k, c, stats, ts)
            o = world.ask(q, g, stats, r)
            right = o.result in ("correct", "declined_right")
            rows.append({"id": c["id"], "expect": c["expect"], "result": o.result, "right": right,
                         "answered": o.answered_stat, "why": c.get("why", "")})
        by = {e: {"cases": sum(1 for x in rows if x["expect"] == e),
                  "right": sum(1 for x in rows if x["expect"] == e and x["right"])} for e in KIND}
        out["configs"][config] = {"right": sum(x["right"] for x in rows), "share": round(
            sum(x["right"] for x in rows) / len(rows), 3), "by_expect": by,
            "results": dict(Counter(x["result"] for x in rows)), "rows": rows}
    folder = settings.REPORTS / "heldout" / name
    folder.mkdir(parents=True, exist_ok=True)
    first = folder / "first_run.json"
    if not first.exists():
        first.write_text(json.dumps(out, indent=2))
        out["first_run"] = True
    (folder / "latest.json").write_text(json.dumps(out, indent=2))
    return out
