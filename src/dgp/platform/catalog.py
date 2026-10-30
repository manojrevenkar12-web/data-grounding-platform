"""The statistics the platform serves, read from the dbt marts, and how they are found.

Search is BM25 over each statistic's title, analysts' keywords and its geography's names. Two
optional features (config/platform.yaml: features) change it:

- `facets`: a year and a geography named in the query become filters, so "EV sales in Germany 2023"
  cannot return France, and a query about a geography the catalogue does not cover returns nothing.
- `glossary`: words people use for a metric, mined from reformulated queries in the logs
  (dgp.platform.glossary), are added to the statistic's searchable text.

A search below `min_score` returns nothing rather than a guess."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from .. import settings

WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?")
YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")


def words(text: str) -> list[str]:
    stop = set(settings.load("reference")["stopwords"])
    return [w for w in WORD.findall(text.lower()) if w not in stop]


@dataclass
class Stat:
    stat_id: str
    metric: str
    geo: str
    topic: str
    title: str
    keywords: list[str]
    unit: str
    premium: bool
    source: str
    live_version: int
    first_year: int
    last_year: int
    forecast_from: int | None
    versions: list[dict[str, Any]] = field(default_factory=list)  # version, published_at, superseded_at
    values: dict[int, dict[int, tuple[float, bool]]] = field(default_factory=dict)  # version -> year -> (v, fc)

    def version_at(self, when: datetime | None) -> dict[str, Any] | None:
        if when is None:
            return self.versions[-1]
        live = [v for v in self.versions if v["published_at"] <= when]
        return live[-1] if live else None


class Catalog:
    def __init__(
        self,
        stats: dict[str, Stat],
        glossary: dict[str, dict[str, list[str]]] | None = None,
        features: dict[str, bool] | None = None,
    ) -> None:
        self.stats = stats
        self.features = {**settings.load("platform")["features"], **(features or {})}
        self.glossary = glossary or {"metrics": {}, "geos": {}}
        ref = settings.load("reference")["geographies"]
        self.geo_names = {code: [n.lower() for n in names] for code, names in ref.items()}
        if self.features["glossary"]:
            for code, extra in self.glossary.get("geos", {}).items():
                self.geo_names[code] = [*self.geo_names.get(code, []), *extra]
        self.not_covered = [n.lower() for n in settings.load("reference")["not_covered"]]
        self._memo: dict[tuple[str, int | None], list[dict[str, Any]]] = {}
        self._index()

    @classmethod
    def load(cls, path: Path | None = None, **kw: Any) -> Catalog:
        con = duckdb.connect(str(path or settings.warehouse()), read_only=True)
        stats: dict[str, Stat] = {}
        for r in con.execute(
            "select stat_id, metric, geo, topic, title, keywords, unit, premium, source, live_version, "
            "first_year, last_year, forecast_from from dim_statistic"
        ).fetchall():
            stats[r[0]] = Stat(*r[:6], *r[6:9], int(r[9]), int(r[10]), int(r[11]), r[12])
        for sid, version, at, until in con.execute(
            "select stat_id, version, published_at, superseded_at from fct_statistic_versions order by stat_id, version"
        ).fetchall():
            stats[sid].versions.append({"version": int(version), "published_at": at, "superseded_at": until})
        for sid, year, version, value, fc in con.execute(
            "select stat_id, year, version, value, is_forecast from fct_values"
        ).fetchall():
            stats[sid].values.setdefault(int(version), {})[int(year)] = (float(value), bool(fc))
        con.close()
        return cls(stats, **kw)

    # ------------------------------------------------------------------ search
    def _doc(self, s: Stat) -> list[str]:
        text = " ".join([s.title, " ".join(s.keywords), " ".join(self.geo_names.get(s.geo, []))])
        extra = " ".join(self.glossary.get("metrics", {}).get(s.metric, [])) if self.features["glossary"] else ""
        return words(text + " " + extra)

    def _index(self) -> None:
        self.docs = {sid: Counter(self._doc(s)) for sid, s in self.stats.items()}
        self.lengths = {sid: sum(c.values()) for sid, c in self.docs.items()}
        self.avg = sum(self.lengths.values()) / max(1, len(self.lengths))
        df: dict[str, int] = defaultdict(int)
        for c in self.docs.values():
            for w in c:
                df[w] += 1
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}

    def parse(self, query: str) -> dict[str, Any]:
        q = query.lower()
        years = [int(y) for y in YEAR.findall(q)]

        def named(n: str) -> bool:
            return re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", q) is not None

        geos = [code for code, names in self.geo_names.items() if any(named(n) for n in names)]
        uncovered = [n for n in self.not_covered if named(n)]
        return {"years": years, "geos": geos, "not_covered": uncovered}

    def search(self, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        key = (query, limit)
        if key not in self._memo:
            self._memo[key] = self._search(query, limit)
        return [dict(h) for h in self._memo[key]]

    def _search(self, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        cfg = settings.load("platform")["retrieval"]
        k1, b = cfg["bm25"]["k1"], cfg["bm25"]["b"]
        terms = words(query)
        facets = self.parse(query) if self.features["facets"] else {"years": [], "geos": [], "not_covered": []}
        if facets["not_covered"] and not facets["geos"]:
            return []  # the query is about a geography the catalogue does not have
        scored = []
        for sid, doc in self.docs.items():
            s = self.stats[sid]
            if facets["geos"] and s.geo not in facets["geos"]:
                continue
            if facets["years"] and not any(s.first_year <= y <= s.last_year for y in facets["years"]):
                continue
            score = 0.0
            for t in terms:
                if t in doc:
                    tf = doc[t]
                    score += self.idf[t] * tf * (k1 + 1) / (tf + k1 * (1 - b + b * self.lengths[sid] / self.avg))
            if score > 0:
                scored.append((score, sid))
        if not scored:
            return []
        top = max(sc for sc, _ in scored)
        norm = sum(self.idf.get(t, 0) for t in set(terms)) or 1.0
        out = []
        for sc, sid in sorted(scored, key=lambda x: (-x[0], x[1]))[: limit or cfg["top_k"]]:
            if sc / norm < cfg["min_score"]:
                continue
            s = self.stats[sid]
            out.append(
                {
                    "stat_id": sid,
                    "title": s.title,
                    "unit": s.unit,
                    "geo": s.geo,
                    "premium": s.premium,
                    "score": round(sc / norm, 3),
                    "relative": round(sc / top, 3),
                    "years": [s.first_year, s.last_year],
                    "facets": facets,
                }
            )
        return out
