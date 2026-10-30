"""Data contracts at the door and in producers' CI."""

from __future__ import annotations

import copy
import json

import pytest
from typer.testing import CliRunner

from dgp.cli import app
from dgp.platform import contracts


def row(**over):
    r = {
        "stat_id": "ev_sales-DE",
        "metric": "ev_sales",
        "geo": "DE",
        "topic": "mobility",
        "title": "EV sales",
        "keywords": ["EV sales"],
        "unit": "thousand units",
        "premium": False,
        "source": "x",
        "year": 2024,
        "value": 12.5,
        "is_forecast": False,
        "version": 2,
        "published_at": "2026-02-01T09:00:00",
    }
    r.update(over)
    return r


@pytest.fixture
def mobility():
    return contracts.load("mobility")


def test_every_contract_in_the_repo_is_complete():
    assert all(not contracts.structural(c) for c in contracts.all_contracts().values())
    assert len(contracts.all_contracts()) == 10


def test_a_good_delivery_is_accepted(mobility):
    v = contracts.validate(mobility, [row(), row(year=2025, value=13.0)], {"ev_sales-DE": 1})
    assert v.accepted and v.rows == 2 and v.problems == []


@pytest.mark.parametrize(
    "bad, problem",
    [
        (row(value=None), "value is required and missing"),
        ({**{k: x for k, x in row().items() if k != "value"}, "val": 1.0}, "unknown properties: val"),
        (row(unit="units"), "ev_sales is registered in 'thousand units', delivered in 'units'"),
        (row(geo="Germany"), "geo does not match ^[A-Z]{2}$"),
        (row(year=1990), "year out of range [2000, 2040]"),
        (row(premium="no"), "premium must be a boolean"),
        (row(value=True), "value must be a number"),
        (row(metric="tea_sales"), "metric 'tea_sales' is not registered in this contract"),
    ],
)
def test_breaking_deliveries_are_refused(mobility, bad, problem):
    v = contracts.validate(mobility, [bad])
    assert not v.accepted and problem in v.problems


def test_a_revision_must_be_newer_than_what_is_live(mobility):
    v = contracts.validate(mobility, [row(version=1)], {"ev_sales-DE": 1})
    assert not v.accepted and "not newer than the live version 1" in v.problems[0]


def test_compatibility(mobility):
    same = contracts.compatibility(mobility, mobility)
    assert same == {"breaking": [], "additive": [], "allowed": True, "reason": "compatible"}
    new = copy.deepcopy(mobility)
    new["schema"][0]["properties"].append({"name": "note", "logicalType": "string", "required": False})
    assert contracts.compatibility(mobility, new)["additive"] == ["added optional note"]
    gone = copy.deepcopy(mobility)
    gone["schema"][0]["properties"] = [p for p in gone["schema"][0]["properties"] if p["name"] != "source"]
    out = contracts.compatibility(mobility, gone)
    assert out["breaking"] == ["removed source"] and not out["allowed"]
    unit = copy.deepcopy(mobility)
    contracts.units(unit)["ev_sales"] = "units"
    assert not contracts.compatibility(mobility, unit)["allowed"]
    unit["version"] = "2.0.0"
    assert contracts.compatibility(mobility, unit)["allowed"]  # a new major version admits it


def test_structural_problems_are_named():
    assert "kind must be DataContract" in contracts.structural({"kind": "x", "apiVersion": "v3.1.0"})
    assert any("units" in p for p in contracts.structural({"apiVersion": "v3.1.0", "kind": "DataContract"}))


def test_cli_validate_lint_and_diff(tmp_path, mobility):
    runner = CliRunner()
    good = tmp_path / "good.jsonl"
    good.write_text(json.dumps(row()) + "\n")
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(row(value=None)) + "\n")
    assert runner.invoke(app, ["contract", "validate", "mobility", str(good)]).exit_code == 0
    r = runner.invoke(app, ["contract", "validate", "mobility", str(bad)])
    assert r.exit_code == 1 and "value is required" in r.output
    assert runner.invoke(app, ["contract", "lint"]).exit_code == 0
    import yaml

    gone = copy.deepcopy(mobility)
    gone["schema"][0]["properties"].pop()
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text(yaml.safe_dump(mobility))
    b.write_text(yaml.safe_dump(gone))
    assert runner.invoke(app, ["contract", "diff", str(a), str(b)]).exit_code == 1
    assert runner.invoke(app, ["contract", "diff", str(a), str(a)]).exit_code == 0
