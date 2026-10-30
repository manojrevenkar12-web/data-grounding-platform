"""Words people use that the catalogue does not, learned from the platform's own logs.

When a search in an MCP session finds nothing, or a statistic the user then abandons, and the user
rephrases and fetches something else, the words of the first query that the second one dropped,
and that the catalogue does not already use, are candidates for what the user meant. Counted over
many sessions, a word that keeps pointing at the same metric is a metric synonym ("e-car" -> electric
car sales). A word that keeps pointing at the same geography across at least three metrics is a
geography name ("deutschland" -> DE).
Candidates below `min_support`, or without a clear winner, are dropped. The result goes to analysts
for review before it is served (dgp.product proposes it, a person approves it)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from .catalog import YEAR, Catalog, words


def mine(
    sessions: Iterable[dict[str, Any]], catalog: Catalog, min_support: int = 3, min_share: float = 0.6
) -> dict[str, Any]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in sessions:
        by_session[s["session"]].append(s)
    metric_votes: dict[str, Counter] = defaultdict(Counter)
    geo_votes: dict[str, Counter] = defaultdict(Counter)
    known = set(catalog.idf)
    for steps in by_session.values():
        if len(steps) < 2:
            continue
        steps.sort(key=lambda s: s["ts"])
        first, last = steps[0], steps[-1]
        if not last.get("fetched") or last.get("fetch_status") != "ok" or first.get("fetched") == last["fetched"]:
            continue
        target = catalog.stats.get(last["fetched"])
        if target is None:
            continue
        dropped = set(words(YEAR.sub(" ", first["query"]))) - set(words(last["query"]))
        for w in dropped:
            if w in known or len(w) < 3:  # the catalogue already uses it, or it is a fragment ("u" of "U.S.")
                continue
            metric_votes[w][target.metric] += 1
            geo_votes[w][target.geo] += 1
    metrics: dict[str, list[str]] = defaultdict(list)
    geos: dict[str, list[str]] = defaultdict(list)
    for w in sorted(metric_votes):
        m, n_m = metric_votes[w].most_common(1)[0]
        g, n_g = geo_votes[w].most_common(1)[0]
        total = sum(metric_votes[w].values())
        if total < min_support:
            continue
        if n_g / total >= min_share and n_g >= n_m and len(metric_votes[w]) >= 3:
            geos[g].append(w)
        elif n_m / total >= min_share:
            metrics[m].append(w)
    return {"metrics": dict(metrics), "geos": dict(geos)}
