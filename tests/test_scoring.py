"""From evidence to a roadmap: guardrails, confidence, prerequisites and capacity."""

from __future__ import annotations

from dgp import settings
from dgp.product import scoring

GOOD = {
    "wrong_number_share": 0.05,
    "latency_p95_ms": 90.0,
    "cost_per_correct_eur": 0.0005,
    "premium_leaks": 0,
    "cost_eur": 100.0,
    "weeks": 4,
}


def ev(value, low, high, **summary):
    return {
        "summary": {**GOOD, **summary},
        "measured_against": "today",
        "delta": {
            "value": {"per_week": value, "low": low, "high": high},
            "correct": {"per_week": value // 2},
            "wrong_number": {"per_week": -value // 6},
        },
    }


def evidence():
    return {
        "facets": ev(1000, 800, 1200),
        "glossary": ev(14000, 12000, 16000),
        "selfserve_contracts": ev(30, 10, 60),
        "cache": ev(0, 0, 0, cost_eur=80.0),
    }


def test_guardrails_name_what_broke():
    assert scoring.guardrail_breaches(GOOD) == []
    bad = scoring.guardrail_breaches({**GOOD, "wrong_number_share": 0.3, "premium_leaks": 2, "latency_p95_ms": 400})
    assert len(bad) == 3 and any("premium" in b for b in bad)


def test_score_uses_evidence_and_halves_confidence_when_the_interval_spans_zero():
    rows = {r["id"]: r for r in scoring.score({**evidence(), "facets": ev(100, -50, 250)}, GOOD)}
    assert rows["glossary"]["confidence"] == 0.9 and rows["glossary"]["score"] == round(14000 * 0.9 / 4, 1)
    assert rows["facets"]["confidence"] == 0.45
    assert rows["selfserve_contracts"]["confidence"] == 0.6  # modelled
    assert rows["a2a"]["confidence"] == 0.3 and "stated" in rows["a2a"]["unit"]
    assert rows["cache"]["value"] == 5.0 and rows["cache"]["unit"] == "EUR saved/week"


def test_roadmap_plans_a_strong_bet_with_its_prerequisite_before_weaker_ones():
    plan = scoring.roadmap(scoring.score(evidence(), GOOD))
    now = [r["id"] for r in plan["now"]]
    assert now.index("facets") < now.index("glossary")
    assert "selfserve_contracts" in [r["id"] for r in plan["next"]]  # 3 + 4 of 8 weeks used; 3 more do not fit
    assert {r["id"] for r in plan["discovery"]} == {"a2a", "charts"}
    cap = settings.load("product")["capacity_engineer_weeks"]
    assert plan["capacity_left"]["north_star"] == cap["north_star"] - 7


def test_a_bet_that_breaks_a_guardrail_is_not_now():
    e = {**evidence(), "glossary": ev(14000, 12000, 16000, wrong_number_share=0.5)}
    plan = scoring.roadmap(scoring.score(e, GOOD))
    assert [r["id"] for r in plan["not_now"]] == ["glossary"]
    assert "wrong-number share" in plan["not_now"][0]["why"][0]
