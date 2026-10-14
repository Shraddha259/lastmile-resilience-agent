"""FR-5 / AC-5.1: deterministic risk scoring (PRD §10)."""

from app.models import Priority
from app.services.risk import rank_residents, score_resident

# Hand-checked against PRD §10 (R-001 matches the §9.1 example).
EXPECTED = {
    "R-001": (73, Priority.P1),
    "R-002": (36, Priority.P2),
    "R-005": (75, Priority.P1),
    "R-018": (60, Priority.P1),
    "R-003": (55, Priority.P2),
}


def test_AC_5_1_all_40_residents_at_risk(residents, scenario_template):
    ranked = rank_residents(
        residents, scenario_template["polygon"], scenario_template["river_line"]
    )
    assert len(ranked) == 40


def test_FR_5_fixed_scores(residents, scenario_template):
    ranked = {
        r.resident_id: r
        for r in rank_residents(
            residents, scenario_template["polygon"], scenario_template["river_line"]
        )
    }
    for rid, (score, prio) in EXPECTED.items():
        assert (ranked[rid].risk_score, ranked[rid].priority) == (score, prio), rid


def test_FR_5_reproducible(residents, scenario_template):
    a = rank_residents(residents, scenario_template["polygon"], scenario_template["river_line"])
    b = rank_residents(residents, scenario_template["polygon"], scenario_template["river_line"])
    assert [(x.resident_id, x.risk_score) for x in a] == [(x.resident_id, x.risk_score) for x in b]


def test_FR_5_r001_reasons(residents, scenario_template):
    r1 = next(
        r
        for r in rank_residents(
            residents, scenario_template["polygon"], scenario_template["river_line"]
        )
        if r.resident_id == "R-001"
    )
    assert r1.risk_reasons[:5] == [
        "Age 82 (+18)",
        "Lives alone (+15)",
        "Uses walker (+10)",
        "Hypertension (+5)",
        "Ground floor (+15)",
    ]


def test_FR_5_ordering_ties_by_age_then_id(residents, scenario_template):
    ranked = rank_residents(
        residents, scenario_template["polygon"], scenario_template["river_line"]
    )
    keys = [(-r.risk_score, -r.age, r.resident_id) for r in ranked]
    assert keys == sorted(keys)


def test_FR_5_caps_and_hearing_need():
    r = {
        "resident_id": "X",
        "age": 90,
        "lives_alone": True,
        "mobility": "bedridden",
        "medical_flags": [
            "oxygen",
            "dialysis",
            "diabetes",
            "dementia",
            "heart_condition",
            "hearing_impaired",
        ],
        "floor": 0,
    }
    res = score_resident(r, river_dist_m=10)
    assert res.risk_score == 100
    assert "slow_clear_speech" in res.extra_needs
    assert sum("(+5)" in x for x in res.risk_reasons) == 2  # other flags capped at 10
