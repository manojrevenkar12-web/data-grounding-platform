"""What an AI client gets back: a statistic's value for a year, from the version that was live at a
given date, with a citation it can show, or a plain reason why not.

- Entitlements are enforced on every call: a premium statistic is never returned to a plan without
  premium. With `entitlement_answers` the reason is explicit ("not in your plan"); without it the
  client only sees a generic refusal and has to guess what that means.
- With `as_of`, the answer comes from the version that was published at that date, and a newer
  revision is announced, not silently substituted.
- Every call is metered (cost, latency, cache) against the account's monthly budget; past the budget
  calls are refused with `budget_exhausted` rather than billed.
- Years outside the series, unknown statistics and dates before first publication are answered as
  such: no number is better than a made-up one."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .. import settings
from ..settings import u
from .catalog import Catalog


@dataclass
class Account:
    account_id: str
    plan: str


@dataclass
class Meter:
    events: list[dict[str, Any]] = field(default_factory=list)
    spend: dict[tuple[str, str], float] = field(default_factory=dict)  # (account, month) -> eur
    cache: set[tuple[str, int]] = field(default_factory=set)

    def charge(self, account: Account, tool: str, at: datetime, key: Any, cached: bool, **extra: Any) -> dict[str, Any]:
        cfg = settings.load("platform")
        m = cfg["metering"]
        cost = m["cached_eur"] if cached else m[f"{tool}_eur"]
        lo, hi = cfg["latency_ms"]["cached" if cached else tool]
        latency = lo + (hi - lo) * u("lat", tool, key, at.isoformat()) ** 2  # a long right tail
        month = at.strftime("%Y-%m")
        self.spend[(account.account_id, month)] = self.spend.get((account.account_id, month), 0.0) + cost
        e = {
            "ts": at,
            "account_id": account.account_id,
            "plan": account.plan,
            "tool": tool,
            "cost_eur": cost,
            "latency_ms": round(latency, 1),
            "cached": cached,
            **extra,
        }
        self.events.append(e)
        return e

    def over_budget(self, account: Account, at: datetime) -> bool:
        budget = settings.load("platform")["plans"][account.plan]["monthly_budget_eur"]
        return self.spend.get((account.account_id, at.strftime("%Y-%m")), 0.0) >= budget


class Grounding:
    def __init__(self, catalog: Catalog, meter: Meter | None = None) -> None:
        self.c = catalog
        self.meter = meter or Meter()
        self.cfg = settings.load("platform")

    def entitled(self, account: Account, stat_id: str) -> bool:
        plan = self.cfg["plans"][account.plan]
        return plan["premium"] or not self.c.stats[stat_id].premium

    def search(self, account: Account, query: str, at: datetime, limit: int | None = None) -> dict[str, Any]:
        if self.meter.over_budget(account, at):
            return {"status": "budget_exhausted", "results": []}
        hits = self.c.search(query, limit)
        for h in hits:
            h["entitled"] = self.entitled(account, h["stat_id"])
        self.meter.charge(
            account,
            "search",
            at,
            query,
            False,
            query=query,
            results=len(hits),
            top=hits[0]["stat_id"] if hits else None,
        )
        return {"status": "ok" if hits else "no_match", "results": hits}

    def get(
        self, account: Account, stat_id: str, year: int | None, at: datetime, as_of: datetime | None = None
    ) -> dict[str, Any]:
        if self.meter.over_budget(account, at):
            return {"status": "budget_exhausted"}
        s = self.c.stats.get(stat_id)
        if s is None:
            return self._log(account, at, stat_id, {"status": "not_found", "stat_id": stat_id})
        if not self.entitled(account, stat_id):
            if self.c.features["entitlement_answers"]:
                out = {
                    "status": "not_entitled",
                    "stat_id": stat_id,
                    "title": s.title,
                    "message": "This statistic is not included in your plan; it is available on the enterprise plan.",
                }
            else:
                out = {"status": "error", "message": "403"}
            return self._log(account, at, stat_id, out)
        when = as_of if (as_of is not None and self.c.features["as_of"]) else at
        v = s.version_at(when)
        if v is None:
            return self._log(account, at, stat_id, {"status": "not_yet_published", "stat_id": stat_id})
        years = s.values[v["version"]]
        if year is None:
            year = max(y for y, (_, fc) in years.items() if not fc)
        if year not in years:
            return self._log(
                account,
                at,
                stat_id,
                {"status": "no_such_year", "stat_id": stat_id, "title": s.title, "years": [s.first_year, s.last_year]},
            )
        value, forecast = years[year]
        latest = s.version_at(at)
        out = {
            "status": "ok",
            "stat_id": stat_id,
            "title": s.title,
            "year": year,
            "value": value,
            "unit": s.unit,
            "is_forecast": forecast,
            "version": v["version"],
            "published_at": v["published_at"].isoformat(),
            "citation": self.cite(account, s.stat_id, v["version"], v["published_at"], at),
        }
        if latest is not None and latest["version"] > v["version"]:
            newer = s.values[latest["version"]].get(year)
            out["revision_notice"] = {
                "version": latest["version"],
                "published_at": latest["published_at"].isoformat(),
                "value": newer[0] if newer else None,
            }
        cached = self.c.features["cache"] and (stat_id, v["version"]) in self.meter.cache
        if self.c.features["cache"]:
            self.meter.cache.add((stat_id, v["version"]))
        return self._log(account, at, stat_id, out, cached=cached)

    def cite(self, account: Account, stat_id: str, version: int, published: datetime, at: datetime) -> dict[str, Any]:
        c = self.cfg["citation"]
        s = self.c.stats[stat_id]
        return {
            "title": s.title,
            "publisher": c["publisher"],
            "source": s.source,
            "url": c["url"].format(stat_id=stat_id, version=version),
            "version": version,
            "published": published.date().isoformat(),
            "retrieved": at.date().isoformat(),
            "licence": c["licence"].format(account=account.account_id),
        }

    def _log(
        self, account: Account, at: datetime, stat_id: str, out: dict[str, Any], cached: bool = False
    ) -> dict[str, Any]:
        e = self.meter.charge(account, "get_statistic", at, stat_id, cached, stat_id=stat_id, status=out["status"])
        out["latency_ms"] = e["latency_ms"]
        return out
