"""The publisher's statistics and how they change: every statistic is a series (one metric, one
geography, 2016 to 2029 with forecasts), published by the analyst team that owns its topic, then
revised now and then. Producers deliver dataset files to the landing zone; some deliveries would
break consumers (a renamed column, a changed unit, missing values) and the platform must stop them.

Everything written here is what the platform would really receive. The world's other facts (how
people ask, what an assistant says without tools) are in dgp.sim.world."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .. import settings
from ..settings import u

SOURCES = [
    "national statistics office",
    "industry association",
    "central bank",
    "trade body survey",
    "company filings",
    "ministry report",
    "regulator",
    "consumer survey",
]


@dataclass
class Statistic:
    stat_id: str
    metric: str
    geo: str
    topic: str
    unit: str
    title: str
    keywords: list[str]
    premium: bool
    source: str
    years: list[int]
    forecast_from: int
    versions: list[dict[str, Any]] = field(default_factory=list)  # {version, published_at, values{year: v}}

    def at(self, when: datetime) -> dict[str, Any] | None:
        live = [v for v in self.versions if v["published_at"] <= when]
        return live[-1] if live else None


def _start() -> datetime:
    return datetime.combine(date.fromisoformat(str(settings.load("world")["start"])), datetime.min.time())


def build() -> dict[str, Statistic]:
    w = settings.load("world")
    c = w["catalogue"]
    y0 = c["years"][0]
    f0, f1 = c["forecast_years"]
    years = list(range(y0, f1 + 1))
    out: dict[str, Statistic] = {}
    start = _start()
    for metric, (topic, unit, title, keywords, _vocab, base, growth) in c["metrics"].items():
        for geo, (name, _aliases) in c["geographies"].items():
            sid = f"{metric}-{geo}"
            scale = (8.0 if geo == "WW" else 0.4 + 2.0 * u("scale", sid)) if unit not in ("percent",) else 1.0
            level = float(base) * scale * (0.6 + 0.8 * u("level", sid))
            values = {}
            for i, yr in enumerate(years):
                drift = (1 + float(growth) * (0.6 + 0.8 * u("g", sid))) ** i
                noise = 1 + c["noise"] * (2 * u("n", sid, yr) - 1)
                v = level * drift * noise
                if unit == "percent":
                    v = max(0.1, min(95.0, float(base) * (0.6 + 0.8 * u("level", sid)) * noise * (1 + growth * i)))
                values[yr] = _round(v)
            st = Statistic(
                stat_id=sid,
                metric=metric,
                geo=geo,
                topic=topic,
                unit=unit,
                title=f"{title} in {name} from {y0} to {f1}",
                keywords=list(keywords),
                premium=u("premium", sid) < c["premium_share"],
                source=SOURCES[int(u("src", sid) * len(SOURCES))],
                years=years,
                forecast_from=f0,
            )
            first = start - timedelta(days=30 + int(400 * u("first", sid)))
            st.versions.append({"version": 1, "published_at": first, "values": values})
            out[sid] = st
    _revise(out)
    return out


def _round(v: float) -> float:
    if v == 0:
        return 0.0
    digits = 3 - int(math.floor(math.log10(abs(v))))
    return round(v, max(1, digits))


def _revise(stats: dict[str, Statistic]) -> None:
    """Revisions during the simulated weeks: the last actual year is corrected, forecasts move."""
    w = settings.load("world")
    r = w["revisions"]
    y_last = w["catalogue"]["years"][1]
    start = _start()
    for sid, st in stats.items():
        if u("revised", sid) >= r["share_revised"]:
            continue
        lo, hi = r["relative_change"]
        values = dict(st.versions[-1]["values"])
        sign = 1 if u("sign", sid) < 0.5 else -1
        values[y_last] = _round(values[y_last] * (1 + sign * (lo + (hi - lo) * u("size", sid))))
        if u("fc", sid) < r["forecast_share_revised"]:
            for yr in range(st.forecast_from, st.years[-1] + 1):
                values[yr] = _round(values[yr] * (1 + sign * 0.5 * (lo + (hi - lo) * u("fsize", sid, yr))))
        when = start + timedelta(days=int(7 * w["weeks"] * (0.1 + 0.8 * u("when", sid))), hours=9)
        st.versions.append({"version": 2, "published_at": when, "values": values})


def rows(st: Statistic, version: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "stat_id": st.stat_id,
            "metric": st.metric,
            "geo": st.geo,
            "topic": st.topic,
            "title": st.title,
            "keywords": st.keywords,
            "unit": st.unit,
            "premium": st.premium,
            "source": st.source,
            "year": yr,
            "value": v,
            "is_forecast": yr >= st.forecast_from,
            "version": version["version"],
            "published_at": version["published_at"].isoformat(),
        }
        for yr, v in version["values"].items()
    ]


def deliveries(stats: dict[str, Statistic], selfserve: bool = False) -> list[dict[str, Any]]:
    """Dataset files as producers deliver them, in time order. A delivery is one topic's statistics
    at one version. Some updates would break consumers; the platform must refuse them at the door,
    and the producer fixes and re-delivers after a review (days). With self-serve contract checks
    in the producers' own CI most breaks are caught before delivery and fixed the same day."""
    w = settings.load("world")["producers"]
    by_topic: dict[tuple[str, datetime, int], list[dict[str, Any]]] = {}
    for st in stats.values():
        for v in st.versions:
            when = v["published_at"] if v["version"] > 1 else _start() - timedelta(days=1)
            by_topic.setdefault((st.topic, when, v["version"]), []).extend(rows(st, v))
    out = []
    for (topic, when, version), batch in sorted(by_topic.items(), key=lambda x: (x[0][1], x[0][0])):
        did = f"{topic}-{when:%Y%m%d%H%M}-v{version}"
        broken = version > 1 and u("break", topic, when) < w["breaking_change_share"]
        if not broken:
            out.append(
                {
                    "delivery_id": did,
                    "topic": topic,
                    "delivered_at": when,
                    "rows": batch,
                    "breaking": None,
                    "intended_at": when,
                }
            )
            continue
        kind = ["rename", "unit", "nulls"][int(3 * u("kind", topic, when))]
        caught_in_ci = selfserve and u("ci", topic, when) >= w["selfserve_still_needs_review"]
        lo, hi = w["review_days_selfserve"] if selfserve else w["review_days_manual"]
        fixed_at = when + timedelta(days=lo + (hi - lo) * u("review", topic, when, selfserve))
        if not caught_in_ci:  # the broken file reaches the platform and is refused
            out.append(
                {
                    "delivery_id": did,
                    "topic": topic,
                    "delivered_at": when,
                    "rows": [_break(r, kind) for r in batch],
                    "breaking": kind,
                    "intended_at": when,
                }
            )
        fixed = [{**r, "published_at": fixed_at.isoformat()} for r in batch]
        out.append(
            {
                "delivery_id": f"{topic}-{fixed_at:%Y%m%d%H%M}-v{version}fix",
                "topic": topic,
                "delivered_at": fixed_at,
                "rows": fixed,
                "breaking": None,
                "intended_at": when,
                "fixes": did,
                "caught_in_ci": caught_in_ci,
            }
        )
    return sorted(out, key=lambda d: d["delivered_at"])


def _break(row: dict[str, Any], kind: str) -> dict[str, Any]:
    r = dict(row)
    if kind == "rename":
        r["val"] = r.pop("value")
    elif kind == "unit":
        r["unit"] = "units" if r["unit"] != "percent" else "share"
        r["value"] = r["value"] * 1000
    else:
        r["value"] = None
    return r


def write_landing(dels: list[dict[str, Any]], root: Path) -> list[Path]:
    paths = []
    for d in dels:
        p = root / d["topic"] / f"{d['delivery_id']}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(r) for r in d["rows"]) + "\n")
        paths.append(p)
    return paths
