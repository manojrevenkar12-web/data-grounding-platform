"""From evidence to a roadmap.

Each bet is scored as  value x confidence / effort, inside its investment bucket:

- value: for North Star bets, the change in verified answers per week, minus three times the
  change in wrong or stale numbers given (config/product.yaml: value.wrong_number_weight). It is
  measured by running the bet as a variant on the same questions (on top of what it needs), or
  derived from a stated reach and impact for bets only backed by demand. For efficiency bets it is
  euro saved per week.
- confidence: by how the evidence was obtained (config/product.yaml: evidence_confidence). It is
  halved when the measured interval includes zero.
- effort: engineer-weeks, from the team's estimate.

A bet that breaks a guardrail is "not now" whatever it scores. A bet whose prerequisite is not
planned waits for it. Each bucket is filled up to its capacity: what fits is Now, the rest Next.
Demand-only bets get a discovery task (the cheapest test of the hypothesis), not a build slot."""

from __future__ import annotations

from typing import Any

from .. import settings


def guardrail_breaches(summary: dict[str, Any]) -> list[str]:
    g = settings.load("product")["guardrails"]
    out = []
    if summary["wrong_number_share"] > g["wrong_number_share_max"]:
        out.append(f"wrong-number share {summary['wrong_number_share']:.1%} > {g['wrong_number_share_max']:.0%}")
    if summary["latency_p95_ms"] and summary["latency_p95_ms"] > g["latency_p95_ms_max"]:
        out.append(f"p95 latency {summary['latency_p95_ms']} ms > {g['latency_p95_ms_max']} ms")
    if summary["cost_per_correct_eur"] > g["cost_per_correct_eur_max"]:
        out.append(f"cost per verified answer EUR {summary['cost_per_correct_eur']} > {g['cost_per_correct_eur_max']}")
    if summary.get("premium_leaks", 0) > g["premium_leaks_max"]:
        out.append(f"{summary['premium_leaks']} premium values leaked")
    return out


def score(evidence: dict[str, dict[str, Any]], today: dict[str, Any]) -> list[dict[str, Any]]:
    p = settings.load("product")
    conf_of = p["evidence_confidence"]
    out = []
    for bid, b in p["bets"].items():
        e = evidence.get(bid)
        conf = conf_of[b["evidence"]]
        row: dict[str, Any] = {
            "id": bid,
            "title": b["title"],
            "bucket": b["bucket"],
            "evidence": b["evidence"],
            "effort_weeks": b["effort_weeks"],
            "needs": b.get("needs", []),
            "kill": b["kill"],
            "problem": b["problem"],
            "hypothesis": b["hypothesis"],
        }
        if e is None:  # demand only
            value = b["reach_questions_per_week"] * b["impact_per_question"]
            row.update(
                {
                    "value": round(value),
                    "unit": "verified answers/week (stated, not measured)",
                    "interval": None,
                    "breaches": [],
                }
            )
        elif b["bucket"] == "efficiency":
            saved = today["cost_eur"] / today["weeks"] - e["summary"]["cost_eur"] / e["summary"]["weeks"]
            row.update(
                {
                    "value": round(saved, 2),
                    "unit": "EUR saved/week",
                    "latency_p95_ms": [today["latency_p95_ms"], e["summary"]["latency_p95_ms"]],
                    "interval": None,
                    "breaches": guardrail_breaches(e["summary"]),
                    "side_effect_correct_per_week": e["delta"]["correct"]["per_week"],
                }
            )
        else:
            d = e["delta"]["value"]
            if d["low"] <= 0 <= d["high"]:
                conf /= 2
            row.update(
                {
                    "value": d["per_week"],
                    "unit": "trust-weighted answers/week",
                    "interval": [d["low"], d["high"]],
                    "correct_per_week": e["delta"]["correct"]["per_week"],
                    "wrong_numbers_per_week": e["delta"]["wrong_number"]["per_week"],
                    "measured_against": e.get("measured_against", "today"),
                    "breaches": guardrail_breaches(e["summary"]),
                }
            )
        row["confidence"] = round(conf, 2)
        row["score"] = round(row["value"] * conf / b["effort_weeks"], 1)
        out.append(row)
    return sorted(out, key=lambda r: (r["bucket"], -r["score"]))


def roadmap(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """Highest score first. A bet that needs another is planned together with it (the bundle must
    fit), so a strong bet is not pushed out by weaker ones while its prerequisite waits."""
    cap = dict(settings.load("product")["capacity_engineer_weeks"])
    by_id = {r["id"]: r for r in scored}
    now: list[dict[str, Any]] = []
    nxt: list[dict[str, Any]] = []
    not_now: list[dict[str, Any]] = []
    discovery: list[dict[str, Any]] = []
    planned: set[str] = set()
    decided: set[str] = set()

    def viable(r: dict[str, Any]) -> bool:
        return not r["breaches"] and r["value"] > 0 and r["evidence"] != "demand_signal"

    def chain(r: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for need in r["needs"]:
            if need not in planned and need in by_id:
                out += [x for x in chain(by_id[need]) if x not in out]
        return [*out, r]

    for r in sorted(scored, key=lambda r: -r["score"]):
        if r["id"] in decided:
            continue
        if r["breaches"] or r["value"] <= 0:
            not_now.append({**r, "why": r["breaches"] or ["no measured gain"]})
            decided.add(r["id"])
            continue
        if r["evidence"] == "demand_signal":
            why = ["impact not measured: run the cheapest test first"]
            if cap["discovery"] >= 1:
                cap["discovery"] -= 1
                why = ["one week of discovery this quarter: " + r["kill"]]
            discovery.append({**r, "why": why})
            decided.add(r["id"])
            continue
        bundle = chain(r)
        effort = sum(x["effort_weeks"] for x in bundle)
        if (
            all(viable(x) for x in bundle)
            and all(x["bucket"] == r["bucket"] for x in bundle)
            and effort <= cap[r["bucket"]]
        ):
            cap[r["bucket"]] -= effort
            for x in bundle:
                why = [] if x is r else [f"needed by: {r['title']}"]
                now.append({**x, "why": why})
                planned.add(x["id"])
                decided.add(x["id"])
        else:
            missing = [x["id"] for x in bundle if x is not r]
            why = (
                [f"no capacity left in {r['bucket'].replace('_', ' ')}"]
                if all(viable(x) for x in bundle)
                else [f"waits for {', '.join(missing)}"]
            )
            nxt.append({**r, "why": why})
            decided.add(r["id"])
    return {"now": now, "next": nxt, "discovery": discovery, "not_now": not_now, "capacity_left": cap}
