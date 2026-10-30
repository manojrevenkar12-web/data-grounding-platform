"""The same questions through different versions of the platform (common random numbers), scored
against the truth. This is how a platform bet's impact is measured before anyone builds it for
real: the variant is a feature flag or a producer workflow, and the difference is paired by account.

Bets are scored on the last four weeks; the glossary is mined from the first eight weeks of the
production logs only, so it is never evaluated on the sessions it was learned from."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .. import settings
from ..platform.catalog import Catalog
from ..platform.grounding import Grounding, Meter
from ..sim import world
from ..sim.catalogue import Statistic

RESULTS = ("correct", "wrong_number", "stale", "missed", "declined_right")


@dataclass
class Variant:
    name: str
    features: dict[str, bool] | None  # None: no platform at all (the assistant answers from memory)
    warehouse: Path | None = None
    glossary: dict[str, Any] | None = None


def run_variant(v: Variant, qs: list[world.Question], stats: dict[str, Statistic]) -> tuple[world.Run, Meter | None]:
    if v.features is None:
        return world.run(qs, None, stats), None
    meter = Meter()
    g = Grounding(Catalog.load(v.warehouse, features=v.features, glossary=v.glossary), meter)
    return world.run(qs, g, stats), meter


def summarise(r: world.Run, meter: Meter | None, weeks: float) -> dict[str, Any]:
    rep = settings.load("world")["consumers"]["represents"]
    first = [o for o in r.outcomes if o.attempt == 1]
    c = Counter(o.result for o in r.outcomes)
    answered = [o for o in r.outcomes if o.result in ("correct", "wrong_number", "stale") and o.cited]
    lat = [o.latency_ms for o in r.outcomes if o.calls]
    cost = sum(e["cost_eur"] for e in meter.events) if meter else 0.0
    n = len(r.outcomes)
    return {
        "questions": len(first) * rep,
        "answers": n * rep,
        "correct_per_week": round(c["correct"] * rep / weeks),
        "correct_share": round(c["correct"] / max(1, len(first)), 4),
        "wrong_number_share": round(c["wrong_number"] / max(1, n), 4),
        "stale_share": round(c["stale"] / max(1, n), 4),
        "missed_share": round(c["missed"] / max(1, n), 4),
        "declined_right": c["declined_right"] * rep,
        "rephrased": sum(1 for o in r.outcomes if o.attempt == 2) * rep,
        "cited_wrong_numbers": sum(1 for o in answered if o.result != "correct") * rep,
        "latency_p95_ms": round(float(np.percentile(lat, 95)), 1) if lat else None,
        "cost_eur": round(cost * rep, 2),
        "cost_per_correct_eur": round(cost / max(1, c["correct"]), 5),
        "tickets": len(r.tickets) * rep,
        "by_kind": {k: dict(v) for k, v in _by_kind(r).items()},
    }


def _by_kind(r: world.Run) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for o in r.outcomes:
        out[o.kind][o.result] += 1
    return out


def paired_delta(
    base: world.Run,
    other: world.Run,
    qs: list[world.Question],
    weeks: float,
    metric: str | dict[str, float] = "correct",
    draws: int = 2000,
) -> dict[str, Any]:
    """Change in `metric` answers per week (or a weighted sum of results), with a 90% interval from
    resampling accounts: both runs answered the same questions, so the difference is paired."""
    rep = settings.load("world")["consumers"]["represents"]
    acc_of = {q.qid: q.account.account_id for q in qs}
    weights = {metric: 1.0} if isinstance(metric, str) else metric

    def per_account(r: world.Run) -> Counter:
        c: Counter = Counter()
        for o in r.outcomes:
            if o.result in weights:
                c[acc_of[o.qid]] += weights[o.result]
        return c

    a, b = per_account(base), per_account(other)
    ids = sorted({q.account.account_id for q in qs})
    diff = np.array([b[i] - a[i] for i in ids], dtype=float)
    rng = np.random.default_rng(7)
    boots = [diff[rng.integers(0, len(diff), len(diff))].sum() for _ in range(draws)]
    scale = rep / weeks
    return {
        "per_week": round(diff.sum() * scale),
        "low": round(float(np.percentile(boots, 5)) * scale),
        "high": round(float(np.percentile(boots, 95)) * scale),
    }


def window(qs: list[world.Question], from_week: int, to_week: int) -> list[world.Question]:
    t0 = world.start()
    lo, hi = t0 + timedelta(weeks=from_week), t0 + timedelta(weeks=to_week)
    return [q for q in qs if lo <= q.ts < hi]
