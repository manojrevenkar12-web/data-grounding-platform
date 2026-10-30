"""Search, facets, the glossary, and what a client gets back."""

from __future__ import annotations

from datetime import datetime

import pytest

from dgp import settings
from dgp.platform.catalog import Catalog
from dgp.platform.glossary import mine
from dgp.platform.grounding import Account, Grounding
from tests.conftest import small

NOW = datetime(2026, 3, 1, 10)
ENT, TEAM = Account("e1", "enterprise"), Account("t1", "team")


def test_search_ranks_by_the_question(catalog):
    hits = catalog.search("EV sales in Germany 2024")
    assert hits[0]["stat_id"] == "ev_sales-DE"
    assert catalog.search("gross domestic product")[0]["stat_id"] == "gdp-US"
    assert catalog.search("zzz qqq") == []


def test_without_facets_a_neighbour_can_win_and_facets_stop_it():
    plain = Catalog(small(), features={"facets": False})
    faceted = Catalog(small(), features={"facets": True})
    q = "electric vehicle sales French 2024"  # 'French' is in the reference names for FR
    assert faceted.search(q)[0]["stat_id"] == "ev_sales-FR"
    assert all(h["geo"] == "FR" for h in faceted.search(q))
    assert {h["geo"] for h in plain.search(q)} >= {"DE", "FR"}
    assert faceted.search("EV sales in Liechtenstein 2024") == []  # not covered: nothing, not a neighbour
    assert plain.search("EV sales in Liechtenstein 2024")  # without facets it guesses
    assert faceted.search("EV sales Germany 1999") == []  # outside every series


def test_parse_names_geographies_and_years(catalog):
    assert catalog.parse("EV sales in Germany and France, 2023 vs 2024") == {
        "years": [2023, 2024],
        "geos": ["DE", "FR"],
        "not_covered": [],
    }
    assert catalog.parse("beer in Andorra")["not_covered"] == ["andorra"]
    assert catalog.parse("Germanyx")["geos"] == []  # whole words only


def test_glossary_adds_customers_words_only_when_switched_on():
    gl = {"metrics": {"ev_sales": ["e-car"]}, "geos": {"DE": ["deutschland"]}}
    off = Catalog(small(), glossary=gl, features={"glossary": False, "facets": True})
    on = Catalog(small(), glossary=gl, features={"glossary": True, "facets": True})
    assert off.search("e-car registrations Deutschland") == []
    hits = on.search("e-car registrations Deutschland")
    assert hits[0]["stat_id"] == "ev_sales-DE" and all(h["geo"] == "DE" for h in hits)


def test_mining_learns_from_rephrased_sessions_only():
    cat = Catalog(small())
    sessions = []
    for k, geo_word in enumerate(["deutschland", "deutschland", "deutschland"]):
        for metric_id, term in (
            ("ev_sales-DE", "e-car registrations"),
            ("beer_sales-DE", "lager"),
            ("ev_sales-DE", "e-car"),
        ):
            sid = f"s{k}-{metric_id}-{term}"
            sessions.append(
                {"session": sid, "ts": NOW, "query": f"{term} {geo_word} 2024", "fetched": None, "fetch_status": None}
            )
            sessions.append(
                {
                    "session": sid,
                    "ts": NOW.replace(minute=1),
                    "query": f"{cat.stats[metric_id].keywords[0]} Germany 2024",
                    "fetched": metric_id,
                    "fetch_status": "ok",
                }
            )
    sessions.append({"session": "lonely", "ts": NOW, "query": "quux", "fetched": "gdp-US", "fetch_status": "ok"})
    g = mine(sessions, cat)
    assert "e-car" in g["metrics"]["ev_sales"] and "lager" in g["metrics"]["beer_sales"]
    assert "registrations" in g["metrics"]["ev_sales"]
    assert "quux" not in str(g)  # one-step sessions teach nothing
    assert all("germany" not in ws for ws in g["metrics"].values())  # catalogue words are not new names


def test_answers_carry_value_version_and_citation(catalog):
    g = Grounding(catalog)
    out = g.get(ENT, "ev_sales-DE", 2024, NOW)
    assert out["status"] == "ok" and out["version"] == 2 and out["value"] == pytest.approx(108 * 1.1)
    c = out["citation"]
    assert c["publisher"] == settings.load("platform")["citation"]["publisher"]
    assert c["url"].endswith("ev_sales-DE?version=2") and "e1" in c["licence"] and c["version"] == 2


def test_as_of_answers_the_version_live_then_and_announces_the_revision(catalog):
    g = Grounding(catalog)
    out = g.get(ENT, "ev_sales-DE", 2024, NOW, as_of=datetime(2026, 1, 20))
    assert out["version"] == 1 and out["value"] == 108.0
    assert out["revision_notice"]["version"] == 2 and out["revision_notice"]["value"] == pytest.approx(108 * 1.1)
    off = Grounding(Catalog(small(), features={"as_of": False}))
    assert off.get(ENT, "ev_sales-DE", 2024, NOW, as_of=datetime(2026, 1, 20))["version"] == 2
    assert g.get(ENT, "ev_sales-DE", 2024, datetime(2025, 1, 1))["status"] == "not_yet_published"


def test_entitlements_are_enforced_and_explained(catalog):
    g = Grounding(catalog)
    assert g.get(ENT, "beer_sales-DE", 2024, NOW)["status"] == "ok"
    out = g.get(TEAM, "beer_sales-DE", 2024, NOW)
    assert out["status"] == "not_entitled" and "enterprise" in out["message"] and "value" not in out
    bare = Grounding(Catalog(small(), features={"entitlement_answers": False}))
    assert bare.get(TEAM, "beer_sales-DE", 2024, NOW) == {
        "status": "error",
        "message": "403",
        "latency_ms": bare.meter.events[-1]["latency_ms"],
    }
    hits = g.search(TEAM, "beer sales Germany", NOW)["results"]
    assert hits[0]["entitled"] is False


def test_unknown_statistics_and_years_get_no_number(catalog):
    g = Grounding(catalog)
    assert g.get(ENT, "nope", 2024, NOW)["status"] == "not_found"
    out = g.get(ENT, "gdp-US", 2005, NOW)
    assert out["status"] == "no_such_year" and out["years"] == [2016, 2029]
    assert g.get(ENT, "gdp-US", None, NOW)["year"] == 2025  # default: the latest actual year


def test_metering_budget_and_cache():
    g = Grounding(Catalog(small(), features={"cache": True}))
    first = g.get(ENT, "gdp-US", 2024, NOW)
    second = g.get(ENT, "gdp-US", 2024, NOW)
    costs = [e["cost_eur"] for e in g.meter.events]
    m = settings.load("platform")["metering"]
    assert costs == [m["get_statistic_eur"], m["cached_eur"]] and second["latency_ms"] <= first["latency_ms"] + 25
    budget = settings.load("platform")["plans"]["api_starter"]["monthly_budget_eur"]
    poor = Account("p1", "api_starter")
    g.meter.spend[("p1", NOW.strftime("%Y-%m"))] = budget
    assert g.get(poor, "gdp-US", 2024, NOW) == {"status": "budget_exhausted"}
    assert g.search(poor, "gdp", NOW) == {"status": "budget_exhausted", "results": []}
