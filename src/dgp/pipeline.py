"""`dgp run`: build the world and the warehouse, run twelve weeks of production, evaluate the bets on
the last four weeks, turn the evidence into a roadmap, write the reports and end with the gate."""

from __future__ import annotations

import json
import operator
import shutil
from datetime import timedelta
from typing import Any

from . import settings
from .evals import variants as V
from .platform import glossary, ingest, warehouse
from .platform.catalog import Catalog
from .product import scoring, telemetry
from .settings import u
from .sim import catalogue, world

OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq}
TRAIN_WEEKS = 8


def build_world(log: Any = print) -> dict[str, Any]:
    """Producers deliver; the platform checks, loads and models. Twice: with today's manual contract
    review, and with self-serve contract checks (a bet, built into its own warehouse)."""
    shutil.rmtree(settings.BUILD, ignore_errors=True)
    stats = catalogue.build()
    out = {}
    for name, selfserve in (("production", False), ("selfserve", True)):
        root = settings.BUILD if name == "production" else settings.BUILD / "variants" / name
        dels = catalogue.deliveries(stats, selfserve)
        catalogue.write_landing(dels, root / "landing")
        con = ingest.connect(root / "warehouse.duckdb")
        res = ingest.ingest_all(con, root / "landing")
        con.close()
        dbt = warehouse.build(root / "warehouse.duckdb")
        out[name] = {
            "deliveries": len(dels),
            "breaking": [d["delivery_id"] for d in dels if d["breaking"]],
            "refused": [r["delivery_id"] for r in res if not r["accepted"]],
            "dbt": dbt,
        }
        ok = "ok" if dbt["success"] else "FAILED"
        log(f"{name}: {len(dels)} deliveries, {len(out[name]['refused'])} refused, dbt {ok}")
    settings.truth().mkdir(parents=True, exist_ok=True)
    (settings.truth() / "deliveries.json").write_text(json.dumps(out, default=str))
    return out


def production(qs: list[world.Question], stats: dict[str, Any]) -> tuple[world.Run, Any]:
    """Twelve weeks with today's platform; what it logs becomes the telemetry."""
    run, meter = V.run_variant(V.Variant("today", {}), qs, stats)
    share = settings.load("product")["north_star"]["audit_share"]
    audit = [
        {
            "ts": o.ts,
            "account_id": o.account_id,
            "stat_id": o.answered_stat,
            "version": o.version or 0,
            "correct": o.result == "correct",
        }  # an analyst who knows the right number checks the answer
        for o in run.outcomes
        if o.cited and u("audit", o.qid, o.attempt) < share
    ]
    telemetry.observe(meter.events, run.sessions, run.tickets, audit, {s["session"]: s["client"] for s in run.sessions})
    return run, meter


def evaluate_bets(qs: list[world.Question], stats: dict[str, Any], prod: world.Run) -> dict[str, Any]:
    p = settings.load("product")
    t0 = world.start()
    cut = t0 + timedelta(weeks=TRAIN_WEEKS)
    learned = glossary.mine([s for s in prod.sessions if s["ts"] < cut], Catalog.load())
    test = V.window(qs, TRAIN_WEEKS, settings.load("world")["weeks"])
    weeks = settings.load("world")["weeks"] - TRAIN_WEEKS
    selfserve = settings.BUILD / "variants" / "selfserve" / "warehouse.duckdb"

    def variant(name: str, flags: dict[str, Any]) -> V.Variant:
        flags = dict(flags)
        wh = selfserve if flags.pop("producers", None) == "selfserve" else None
        return V.Variant(name, flags, wh, learned if flags.get("glossary") else None)

    def flags_of(bid: str) -> dict[str, Any]:
        b = p["bets"][bid]
        out: dict[str, Any] = {}
        for need in b.get("needs", []):
            out.update(flags_of(need))
        return {**out, **b.get("variant", {})}

    runs: dict[str, tuple[world.Run, Any]] = {"today": V.run_variant(variant("today", {}), test, stats)}
    runs["no_platform"] = V.run_variant(V.Variant("no_platform", None), test, stats)
    base_of: dict[str, str] = {}
    for bid, b in p["bets"].items():
        if "variant" in b:
            runs[bid] = V.run_variant(variant(bid, flags_of(bid)), test, stats)
            base_of[bid] = b["needs"][-1] if b.get("needs") else "today"  # measured on top of what it needs
    for sid, sh in p["shipped"].items():
        runs[f"without_{sid}"] = V.run_variant(variant(f"without_{sid}", sh["variant"]), test, stats)
    w = p["value"]["wrong_number_weight"]
    out = {"window_weeks": weeks, "glossary": learned, "variants": {}}
    for name, (r, meter) in runs.items():
        base = runs[base_of.get(name, "today")][0]
        s = V.summarise(r, meter, weeks)
        s["weeks"] = weeks
        s["premium_leaks"] = premium_leaks(r, stats)
        out["variants"][name] = {
            "summary": s,
            "measured_against": base_of.get(name, "today"),
            "delta": {
                "correct": V.paired_delta(base, r, test, weeks, "correct"),
                "wrong_number": V.paired_delta(base, r, test, weeks, "wrong_number"),
                "stale": V.paired_delta(base, r, test, weeks, "stale"),
                "value": V.paired_delta(base, r, test, weeks, {"correct": 1.0, "wrong_number": -w, "stale": -w}),
            },
        }
    return out


def premium_leaks(r: world.Run, stats: dict[str, Any]) -> int:
    """Premium values the platform returned to a plan without premium (truth: must be zero)."""
    return sum(
        1
        for o in r.outcomes
        if o.cited and o.answered_stat and stats[o.answered_stat].premium and o.plan != "enterprise"
    )


def plan_variant(
    qs: list[world.Question], stats: dict[str, Any], plan: dict[str, Any], learned: dict[str, Any]
) -> dict[str, Any]:
    """The Now column shipped together: does the combination deliver what the parts promised?"""
    bets = settings.load("product")["bets"]
    flags: dict[str, Any] = {}
    for r in plan["now"]:
        flags.update(bets[r["id"]].get("variant", {}))
    wh = settings.BUILD / "variants" / "selfserve" / "warehouse.duckdb" if flags.pop("producers", None) else None
    test = V.window(qs, TRAIN_WEEKS, settings.load("world")["weeks"])
    weeks = settings.load("world")["weeks"] - TRAIN_WEEKS
    w = settings.load("product")["value"]["wrong_number_weight"]
    base, _ = V.run_variant(V.Variant("today", {}), test, stats)
    r, meter = V.run_variant(V.Variant("plan", flags, wh, learned if flags.get("glossary") else None), test, stats)
    s = V.summarise(r, meter, weeks)
    s["weeks"] = weeks
    s["premium_leaks"] = premium_leaks(r, stats)
    return {
        "flags": flags,
        "selfserve": wh is not None,
        "summary": s,
        "delta": {
            "correct": V.paired_delta(base, r, test, weeks, "correct"),
            "wrong_number": V.paired_delta(base, r, test, weeks, "wrong_number"),
            "value": V.paired_delta(base, r, test, weeks, {"correct": 1.0, "wrong_number": -w, "stale": -w}),
        },
        "parts_sum": sum(x["value"] for x in plan["now"] if x["bucket"] == "north_star"),
        "parts": {x["id"]: x["value"] for x in plan["now"]},
        "breaches": scoring.guardrail_breaches(s),
    }


def get(data: dict[str, Any], path: str) -> Any:
    x: Any = data
    for part in path.split("."):
        x = x[part]
    return x


def gate(results: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for c in settings.load("release")["checks"]:
        left = get(results, c["left"])
        right = get(results, c["right"]) if isinstance(c["right"], str) else c["right"]
        bound = right * c.get("factor", 1) if right is not None else None
        ok = left is not None and bound is not None and OPS[c["op"]](left, bound)
        out.append({"name": c["name"], "passed": bool(ok), "value": left, "op": c["op"], "bound": bound})
    return out


def run(log: Any = print) -> dict[str, Any]:
    built = build_world(log)
    stats = catalogue.build()
    qs = world.questions(stats)
    log(f"{len(qs)} questions over {settings.load('world')['weeks']} weeks")
    prod, _meter = production(qs, stats)
    weeks = settings.load("world")["weeks"]
    rep = settings.load("world")["consumers"]["represents"]
    observed = telemetry.metrics(warehouse=settings.warehouse(), scale=rep)
    observed["producers_selfserve"] = telemetry.producers(
        settings.BUILD / "variants" / "selfserve" / "warehouse.duckdb"
    )
    truth_prod = V.summarise(prod, _meter, weeks)
    truth_prod["weeks"] = weeks
    log("production simulated; evaluating bets")
    ev = evaluate_bets(qs, stats, prod)
    scored = scoring.score({k: v for k, v in ev["variants"].items()}, ev["variants"]["today"]["summary"])
    plan = scoring.roadmap(scored)
    combined = plan_variant(qs, stats, plan, ev["glossary"])
    results = {
        "observed": observed,
        "truth": {
            "production": truth_prod,
            "north_star_per_week": round(sum(1 for o in prod.outcomes if o.result == "correct") * rep / weeks),
            "deliveries": {
                k: {
                    "breaking": len(v["breaking"]),
                    "refused": len(v["refused"]),
                    "refused_exactly_the_breaking": sorted(v["refused"]) == sorted(v["breaking"]),
                    "dbt_ok": v["dbt"]["success"],
                }
                for k, v in built.items()
            },
            "premium_leaks": premium_leaks(prod, stats),
        },
        "evaluation": {k: v for k, v in ev.items() if k != "glossary"},
        "glossary": ev["glossary"],
        "scored": scored,
        "roadmap": plan,
        "plan": combined,
        "represents": rep,
        "accounts": len(world.accounts()),
    }
    ns = results["truth"]["north_star_per_week"]
    lo, hi = observed["north_star"]["interval_per_week"]
    results["truth"]["audit_interval_covers_truth"] = lo <= ns <= hi
    results["gate"] = gate(results)
    settings.REPORTS.mkdir(parents=True, exist_ok=True)
    (settings.REPORTS / "results.json").write_text(json.dumps(results, indent=2, default=str))
    from .product import docs

    docs.write(results)
    return results
