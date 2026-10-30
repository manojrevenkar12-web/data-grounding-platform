"""Pipeline tests build into build/test, so pytest never touches the committed reports. Unit tests
use a small catalogue built in memory."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DGP_BUILD", str(ROOT / "build" / "test"))
os.environ.setdefault("DGP_REPORTS", str(ROOT / "build" / "test" / "reports"))

import pytest  # noqa: E402

from dgp.platform.catalog import Catalog, Stat  # noqa: E402

T0 = datetime(2026, 1, 5)


def stat(
    sid: str,
    metric: str,
    geo: str,
    title: str,
    keywords: list[str],
    premium: bool = False,
    revised: datetime | None = None,
) -> Stat:
    s = Stat(
        sid,
        metric,
        geo,
        "mobility",
        title,
        keywords,
        "thousand units",
        premium,
        "industry association",
        1,
        2016,
        2029,
        2026,
    )
    s.versions.append({"version": 1, "published_at": datetime(2025, 6, 1), "superseded_at": revised})
    s.values[1] = {y: (100.0 + y - 2016, y >= 2026) for y in range(2016, 2030)}
    if revised:
        s.versions.append({"version": 2, "published_at": revised, "superseded_at": None})
        s.values[2] = {y: (v * 1.1, fc) for y, (v, fc) in s.values[1].items()}
        s.live_version = 2
    return s


def small() -> dict[str, Stat]:
    return {
        "ev_sales-DE": stat(
            "ev_sales-DE",
            "ev_sales",
            "DE",
            "Electric car sales in Germany from 2016 to 2029",
            ["electric vehicle sales", "EV sales"],
            revised=datetime(2026, 2, 1),
        ),
        "ev_sales-FR": stat(
            "ev_sales-FR",
            "ev_sales",
            "FR",
            "Electric car sales in France from 2016 to 2029",
            ["electric vehicle sales", "EV sales"],
        ),
        "beer_sales-DE": stat(
            "beer_sales-DE",
            "beer_sales",
            "DE",
            "Beer sales volume in Germany from 2016 to 2029",
            ["beer sales", "beer volume"],
            premium=True,
        ),
        "gdp-US": stat(
            "gdp-US",
            "gdp",
            "US",
            "Gross domestic product in United States from 2016 to 2029",
            ["GDP", "gross domestic product"],
        ),
    }


@pytest.fixture
def catalog() -> Catalog:
    return Catalog(small())
