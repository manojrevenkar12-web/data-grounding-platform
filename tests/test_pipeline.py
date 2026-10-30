"""The whole run: world, warehouse, production, bets, roadmap, documents and the gate (~70 s, once)."""

from __future__ import annotations

import json
from datetime import timedelta

import duckdb
import pytest

from dgp import pipeline, settings
from dgp.sim import world

pytestmark = pytest.mark.slow


@pytest.fixture(scope="session")
def results():
    assert "test" in str(settings.BUILD), "pipeline tests must not overwrite the committed reports"
    return pipeline.run(log=lambda *_: None)


def test_gate_passes(results):
    assert [c for c in results["gate"] if not c["passed"]] == []


def test_the_door_refuses_exactly_what_would_break_and_dbt_tests_pass(results):
    d = results["truth"]["deliveries"]
    assert d["production"]["refused_exactly_the_breaking"] and d["production"]["refused"] >= 5
    assert d["production"]["dbt_ok"] and d["selfserve"]["dbt_ok"]
    assert d["selfserve"]["refused"] < d["production"]["refused"]


def test_marts_keep_every_version_with_its_live_window(results):
    con = duckdb.connect(str(settings.warehouse()), read_only=True)
    live = con.execute("select count(*) from fct_statistic_versions where is_live").fetchone()[0]
    stats = con.execute("select count(*) from dim_statistic").fetchone()[0]
    revised = con.execute("select count(distinct stat_id) from fct_statistic_versions where version > 1").fetchone()[0]
    con.close()
    assert live == stats == 320 and revised > 20


def test_the_audit_estimate_covers_the_truth(results):
    lo, hi = results["observed"]["north_star"]["interval_per_week"]
    assert lo <= results["truth"]["north_star_per_week"] <= hi


def test_bets_are_measured_on_weeks_the_glossary_never_saw(results):
    assert results["evaluation"]["window_weeks"] == settings.load("world")["weeks"] - pipeline.TRAIN_WEEKS
    con = duckdb.connect(str(settings.BUILD / "telemetry.duckdb"), read_only=True)
    first = con.execute("select min(ts) from sessions").fetchone()[0]
    con.close()
    assert first < world.start() + timedelta(weeks=pipeline.TRAIN_WEEKS)
    g = results["glossary"]
    assert g["metrics"] and g["geos"]


def test_roadmap_plans_prerequisites_first_and_the_plan_adds_up(results):
    now = [b["id"] for b in results["roadmap"]["now"]]
    assert now.index("facets") < now.index("glossary")
    plan = results["plan"]
    assert plan["delta"]["value"]["low"] > 0 and plan["breaches"] == []
    assert abs(plan["delta"]["value"]["per_week"] - plan["parts_sum"]) <= 0.1 * abs(plan["parts_sum"])


def test_shipped_features_still_earn_their_keep(results):
    v = results["evaluation"]["variants"]
    assert v["without_as_of"]["delta"]["stale"]["low"] > 0
    assert v["without_entitlement_answers"]["delta"]["wrong_number"]["low"] > 0
    assert results["truth"]["premium_leaks"] == 0


def test_documents_quote_the_results(results):
    rm = (settings.REPORTS / "product" / "ROADMAP.md").read_text()
    for b in results["roadmap"]["now"]:
        assert b["title"] in rm
    brief = (settings.REPORTS / "product" / "EXEC_BRIEF.md").read_text()
    assert f"{results['observed']['north_star']['estimate_per_week']:,}" in brief
    prd = (settings.REPORTS / "product" / "PRD.md").read_text()
    assert "## Acceptance criteria" in prd and "## Kill criterion" in prd
    saved = json.loads((settings.REPORTS / "results.json").read_text())
    assert saved["gate"] == results["gate"]


def test_gate_fails_when_a_bound_is_broken(results):
    broken = json.loads(json.dumps(results, default=str))
    broken["truth"]["premium_leaks"] = 1
    assert not next(c for c in pipeline.gate(broken) if "premium" in c["name"])["passed"]


def test_heldout_harness_records_a_first_run_once(results, monkeypatch, tmp_path):
    from dgp.evals import heldout

    folder = tmp_path / "heldout" / "sample"
    folder.mkdir(parents=True)
    (folder / "questions.yaml").write_text(
        "- {id: a, question: GDP of the United States in 2024, plan: team, expect: value, stat_id: gdp-US,"
        " year: 2024}\n"
        "- {id: b, question: EV sales in Liechtenstein 2024, plan: team, expect: no_data}\n"
    )
    monkeypatch.setattr(settings, "HELDOUT", tmp_path / "heldout")
    out = heldout.run("sample", {"today": {}}, None)
    assert out["first_run"] and out["configs"]["today"]["right"] >= 1
    first = (settings.REPORTS / "heldout" / "sample" / "first_run.json").read_text()
    assert "first_run" not in heldout.run("sample", {"today": {}}, None)
    assert (settings.REPORTS / "heldout" / "sample" / "first_run.json").read_text() == first
