"""Shelter matching (§15.2) and volunteer selection (§15.3)."""

from app.services.shelters import rank_shelters
from app.services.volunteers import rank_volunteers


def _res(residents, rid):
    return next(r for r in residents if r["resident_id"] == rid)


def test_wheelchair_users_never_get_s2(residents, shelters_seed):
    for r in residents:
        if r["mobility"] in ("wheelchair", "bedridden"):
            ids = [c["shelter_id"] for c in rank_shelters(r, [], shelters_seed)]
            assert "S-2" not in ids


def test_wheelchair_need_excludes_s2(residents, shelters_seed):
    r = _res(residents, "R-002")
    ids = [c["shelter_id"] for c in rank_shelters(r, ["wheelchair"], shelters_seed)]
    assert "S-2" not in ids


def test_oxygen_user_gets_s3_first(residents, shelters_seed):
    oxy = next(r for r in residents if "oxygen" in r["medical_flags"])
    assert rank_shelters(oxy, ["oxygen"], shelters_seed)[0]["shelter_id"] == "S-3"


def test_full_or_closed_shelter_excluded(residents, shelters_seed):
    sh = [dict(s) for s in shelters_seed]
    sh[0]["occupied"] = sh[0]["capacity"]
    sh[2]["open"] = False
    ids = [c["shelter_id"] for c in rank_shelters(_res(residents, "R-001"), [], sh)]
    assert ids == ["S-2"]


def test_shared_language_preferred(residents, volunteers_seed):
    r = _res(residents, "R-001")  # zh speaker
    top = rank_volunteers(r, volunteers_seed)
    assert "zh" in top[0]["languages"]


def test_unavailable_volunteers_excluded(residents, volunteers_seed):
    vols = [dict(v, available=False) if "zh" in v["languages"] else v for v in volunteers_seed]
    top = rank_volunteers(_res(residents, "R-001"), vols)
    assert all("zh" not in v["languages"] for v in top)
    assert len(top) == 3
