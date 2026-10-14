"""Generate the synthetic LastMile seed data (PRD §19). Deterministic: random seed 42.

Usage:  uv run --project backend python seed/generate_seed.py
Writes: seed/scenario_flood_demo.json, residents.json, shelters.json, volunteers.json,
        dialogues.json (cached simulated calls, docs/DECISIONS.md D-002).

All people, names, phone numbers and addresses are fictional.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).parent
rng = random.Random(42)

# ------------------------------------------------------------------ scenario (§9.1, §19.1)
# Firestore can't store nested arrays, so geometry is a list of {lat, lng} points
# instead of GeoJSON coordinates (docs/DECISIONS.md D-007).
def _pts(coords: list[list[float]]) -> list[dict]:
    return [{"lat": lat, "lng": lng} for lng, lat in coords]


POLYGON = {
    "type": "Polygon",
    "points": _pts([[101.500, 3.048], [101.522, 3.048], [101.522, 3.062], [101.500, 3.062],
                    [101.500, 3.048]]),
}
RIVER = {"type": "LineString", "points": _pts([[101.498, 3.050], [101.525, 3.058]])}
FACTS = [
    "Water is expected to rise 0.5 to 1 metre by 18:00.",
    "Shelters are open: S-1 SK Sungai Indah Hall, S-2 Dewan Komuniti Taman Indah, "
    "S-3 Civic Care Centre.",
    "Do not walk or drive through moving water.",
    "Bring your ID, phone and medicines if you leave home.",
    "Turn off the electricity if water enters your home.",
]
OFFICIAL_TEXT = {
    "en": "Flash flood warning for Sungai Indah. Water may rise 0.5 to 1 metre by 6 pm. "
    "Shelters S-1, S-2 and S-3 are open. Do not walk through moving water. "
    "Bring your ID, phone and medicines.",
    "zh": "双溪英达山洪警报。下午6点前水位可能上涨0.5至1米。S-1、S-2和S-3避难所已开放。"
    "请勿涉过流动的水。请携带身份证、手机和药物。",
    "ms": "Amaran banjir kilat untuk Sungai Indah. Air mungkin naik 0.5 hingga 1 meter "
    "menjelang 6 petang. Pusat pemindahan S-1, S-2 dan S-3 dibuka. Jangan berjalan "
    "dalam air yang mengalir. Bawa kad pengenalan, telefon dan ubat-ubatan.",
    "ta": "சுங்கை இண்டாவுக்கு திடீர் வெள்ள எச்சரிக்கை. மாலை 6 மணிக்குள் நீர் 0.5 முதல் "
    "1 மீட்டர் வரை உயரலாம். S-1, S-2, S-3 தங்குமிடங்கள் திறந்துள்ளன. ஓடும் நீரில் "
    "நடக்க வேண்டாம். அடையாள அட்டை, தொலைபேசி, மருந்துகளை எடுத்துச் செல்லுங்கள்.",
    "yue": "雙溪英達山洪警告。下晝6點前水位可能上升0.5至1米。S-1、S-2同S-3避難中心已經開放。"
    "唔好行過流動嘅水。記得帶身份證、電話同藥物。",
}
SCENARIO = {
    "scenario_id": "flood_demo",
    "type": "FLOOD",
    "severity": "SEVERE",
    "title": "Flash flood warning — Sungai Indah (fictional)",
    "polygon": POLYGON,
    "river_line": RIVER,
    "official_text": OFFICIAL_TEXT,
    "official_text_machine_translated": True,
    "official_facts": FACTS,
    "map_label": "Illustrative scenario",
}

# ------------------------------------------------------------------ shelters (§19.4)
SHELTERS = [
    {"shelter_id": "S-1", "name": "SK Sungai Indah Hall (fictional)",
     "location": {"lat": 3.0602, "lng": 101.5150}, "capacity": 30, "occupied": 0,
     "wheelchair_accessible": True, "medical_support": False, "open": True},
    {"shelter_id": "S-2", "name": "Dewan Komuniti Taman Indah (fictional)",
     "location": {"lat": 3.0598, "lng": 101.5035}, "capacity": 20, "occupied": 0,
     "wheelchair_accessible": False, "medical_support": False, "open": True},
    {"shelter_id": "S-3", "name": "Civic Care Centre (fictional)",
     "location": {"lat": 3.0632, "lng": 101.5205}, "capacity": 10, "occupied": 0,
     "wheelchair_accessible": True, "medical_support": True, "open": True},
]

# ------------------------------------------------------------------ volunteers (§19.5)
_V = [
    ("V-1", "Aisyah", ["ms", "en"], ["first_aid"], True),
    ("V-2", "Wei Jie", ["zh", "en"], ["driver"], False),
    ("V-3", "Kavitha", ["ta", "en"], ["first_aid"], False),
    ("V-4", "Ka Ho", ["yue", "zh"], [], False),
    ("V-5", "Faizal", ["ms"], ["driver"], False),
    ("V-6", "Mei Xin", ["zh", "ms"], ["first_aid"], False),
    ("V-7", "Daniel", ["en", "ta"], ["driver"], False),
    ("V-8", "Siew Ling", ["zh", "yue"], [], False),
]


def _point(lat_lo=3.0495, lat_hi=3.0610, lng_lo=101.5015, lng_hi=101.5205) -> dict:
    return {"lat": round(rng.uniform(lat_lo, lat_hi), 5), "lng": round(rng.uniform(lng_lo, lng_hi), 5)}


VOLUNTEERS = [
    {"volunteer_id": vid, "display_name": name, "languages": langs, "skills": skills,
     "location": _point(), "available": True, "synthetic": True, "is_live_demo": live}
    for vid, name, langs, skills, live in _V
]

# ------------------------------------------------------------------ residents (§19.2, §19.3)
NAMES = {
    "zh": [("Mdm Wong Mei Ling", "F"), ("Mr Chua Kim Seng", "M"), ("Mdm Lee Siew Hoon", "F"),
           ("Mr Goh Ah Kow", "M"), ("Mdm Ng Bee Choo", "F"), ("Mr Teo Chin Hock", "M"),
           ("Mdm Ong Gek Lan", "F"), ("Mr Koh Ah Huat", "M"), ("Mdm Yap Swee Lian", "F"),
           ("Mr Low Teck Meng", "M"), ("Mdm Sim Ah Moi", "F"), ("Mr Foo Chee Keong", "M"),
           ("Mdm Toh Geok Eng", "F")],
    "ms": [("Pn Siti Aminah", "F"), ("En Ahmad Zaki", "M"), ("Pn Rohani Ismail", "F"),
           ("En Hashim Omar", "M"), ("Pn Fatimah Yusof", "F"), ("En Ismail Bakar", "M"),
           ("Pn Zainab Hassan", "F"), ("En Razak Ali", "M"), ("Pn Mariam Salleh", "F"),
           ("En Kamal Idris", "M")],
    "ta": [("Mdm Lakshmi Raman", "F"), ("Mr Muthu Krishnan", "M"), ("Mdm Kamala Devi", "F"),
           ("Mr Subramaniam Pillai", "M"), ("Mdm Parvathi Nair", "F"), ("Mr Ganesan Rajoo", "M")],
    "en": [("Mrs Mary D'Cruz", "F"), ("Mr Joseph Fernandez", "M"), ("Mrs Grace Thomas", "F"),
           ("Mr Peter Gomez", "M"), ("Mrs Rita Pereira", "F")],
    "yue": [("Mdm Leung Siu Wah", "F"), ("Mr Cheung Kwok Keung", "M"), ("Mdm Lau Yuk Ying", "F"),
            ("Mr Wong Chi Ming", "M")],
}
STREETS = ["Jalan Sungai", "Lorong Indah", "Jalan Tebing", "Lorong Damai", "Jalan Bakti"]
KIN = [("son", "M"), ("daughter", "F"), ("nephew", "M"), ("niece", "F"), ("neighbour", "X")]
OTHER_MED = ["hypertension", "diabetes", "heart_condition", "dementia", "recent_surgery",
             "hearing_impaired"]

# One row per simulated resident: (outcome, mobility, floor, lives_alone, age_band, extras).
# age_band: "old" 70+, "mid" 60-69, "dis" 45-59 with a disability.
SLOTS = [
    # NEEDS_EVACUATION x6: two wheelchair users, the oxygen user, the dialysis user (§19.3)
    ("NEEDS_EVACUATION", "wheelchair", 0, False, "old", {}),
    ("NEEDS_EVACUATION", "wheelchair", 0, True, "dis", {}),
    ("NEEDS_EVACUATION", "independent", 0, True, "old", {"med": ["oxygen"]}),
    ("NEEDS_EVACUATION", "walker", 0, False, "old", {"med": ["dialysis"]}),
    ("NEEDS_EVACUATION", "walker", 0, True, "old", {"pet": True}),
    ("NEEDS_EVACUATION", "independent", 0, False, "mid", {}),
    # NEEDS_HELP x2
    ("NEEDS_HELP", "walker", 0, True, "old", {}),
    ("NEEDS_HELP", "independent", 0, False, "mid", {}),
    # MEDICAL x2: self (chest tight), household (husband fell)
    ("MEDICAL", "independent", 1, True, "old", {"med": ["heart_condition"], "medical": "self"}),
    ("MEDICAL", "independent", 2, False, "old", {"medical": "household"}),
    # SAFE ambiguous x1
    ("SAFE_IN_PLACE", "independent", 1, True, "old", {"ambiguous": True, "med": ["dementia"]}),
    # NO_ANSWER then answers on attempt 2
    ("SAFE_IN_PLACE", "independent", 3, False, "mid", {"answers_on": 2}),
    ("NEEDS_EVACUATION", "walker", 0, False, "old", {"answers_on": 2}),
    # Never answers
    ("SAFE_IN_PLACE", "independent", 0, True, "old", {"answers_on": None}),
    ("SAFE_IN_PLACE", "independent", 0, True, "old",
     {"answers_on": None, "volunteer_outcome": "CANNOT_LOCATE"}),
    # SAFE_IN_PLACE x23
    ("SAFE_IN_PLACE", "bedridden", 4, False, "old", {}),
    ("SAFE_IN_PLACE", "wheelchair", 5, False, "old", {}),
    ("SAFE_IN_PLACE", "wheelchair", 6, False, "dis", {}),
    ("SAFE_IN_PLACE", "walker", 3, False, "dis", {}),
    ("SAFE_IN_PLACE", "walker", 2, False, "dis", {}),
    ("SAFE_IN_PLACE", "walker", 1, True, "old", {}),
    ("SAFE_IN_PLACE", "independent", 0, False, "old", {}),
    ("SAFE_IN_PLACE", "independent", 0, False, "old", {}),
    ("SAFE_IN_PLACE", "independent", 0, False, "mid", {}),
    ("SAFE_IN_PLACE", "independent", 0, False, "mid", {}),
    ("SAFE_IN_PLACE", "independent", 0, True, "old", {}),
    ("SAFE_IN_PLACE", "independent", 1, False, "old", {}),
    ("SAFE_IN_PLACE", "independent", 1, False, "old", {}),
    ("SAFE_IN_PLACE", "independent", 1, False, "mid", {}),
    ("SAFE_IN_PLACE", "independent", 1, True, "old", {}),
    ("SAFE_IN_PLACE", "independent", 2, False, "old", {}),
    ("SAFE_IN_PLACE", "independent", 3, False, "old", {}),
    ("SAFE_IN_PLACE", "independent", 4, False, "old", {}),
    ("SAFE_IN_PLACE", "independent", 5, False, "mid", {}),
    ("SAFE_IN_PLACE", "independent", 6, False, "mid", {}),
    ("SAFE_IN_PLACE", "independent", 8, False, "mid", {}),
    ("SAFE_IN_PLACE", "independent", 10, False, "old", {}),
    ("SAFE_IN_PLACE", "independent", 0, False, "mid", {}),
]
assert len(SLOTS) == 38

LANG_NAME = {"zh": "Mandarin", "ms": "Malay", "ta": "Tamil", "en": "English", "yue": "Cantonese"}
STYLES = ["polite, short answers", "chatty, a little anxious", "calm and matter-of-fact",
          "slow, repeats themselves", "cheerful, slightly hard of hearing"]


def _age(band: str) -> int:
    return {"old": rng.randint(70, 93), "mid": rng.randint(60, 69), "dis": rng.randint(45, 59)}[band]


def _phone() -> str:
    return f"+60 1X-XXX {rng.randint(1000, 9999)}"


def _where(floor: int) -> str:
    return "home, ground floor" if floor == 0 else f"home, floor {floor}"


def _facts(outcome: str, mobility: str, floor: int, alone: bool, ex: dict) -> dict:
    with_ = "alone" if alone else rng.choice(["with spouse", "with adult son", "with daughter"])
    mob = {"independent": "walks fine", "walker": "uses a walker, knees are bad",
           "wheelchair": "uses a wheelchair", "bedridden": "bedridden, needs carer"}[mobility]
    medical = ", ".join(ex.get("med", [])) or "no major issues"
    extra = ""
    if outcome == "NEEDS_EVACUATION":
        extra = "water is starting to come in the door"
    elif outcome == "NEEDS_HELP":
        extra = "needs help moving belongings and rice upstairs"
    elif ex.get("medical") == "self":
        extra = "chest feels tight since this morning"
    elif ex.get("medical") == "household":
        with_, extra = "with husband", "husband fell in the kitchen and cannot get up"
    elif ex.get("ambiguous"):
        extra = "confused, says safe but also says water is in the house"
    if ex.get("pet"):
        extra += "; worried about her cat"
    return {"where": _where(floor), "with": with_, "mobility_detail": mob, "medical": medical,
            "extra": extra.strip("; ")}


def _needs(mobility: str, med: list[str], ex: dict) -> list[str]:
    needs = []
    if mobility in ("wheelchair", "bedridden"):
        needs.append("wheelchair")
    if mobility == "walker":
        needs.append("walking_aid")
    for m in ("oxygen", "dialysis"):
        if m in med:
            needs.append(m)
    if "hearing_impaired" in med:
        needs.append("slow_clear_speech")
    if ex.get("pet"):
        needs.append("pet")
    return needs


def _dialogue(r: dict, outcome: str, ex: dict) -> dict:
    """Template dialogue + expected classification (D-002). English text; real dialogues
    in the resident's language come from seed/generate_dialogues.py."""
    name, f = r["display_name"], r["persona"]["facts"]
    lang = LANG_NAME[r["preferred_language"]]
    lines = [
        ("agent", f"Hello {name}, I am an automated assistant from the community flood "
                  f"response, speaking {lang}. There is a flash flood warning for your area."),
        ("resident", "Oh. Yes, I heard something on the TV."),
        ("agent", "Are you safe right now, and where are you?"),
    ]
    summary = ""
    if ex.get("ambiguous"):
        lines += [("resident", "I am fine, fine. The water... is it in the house? Maybe."),
                  ("agent", "Is water inside your home now?"),
                  ("resident", "No. Yes. I don't know, my son usually handles this.")]
        summary = "Says safe but contradicts herself about water in the home; seems confused."
    elif outcome == "SAFE_IN_PLACE":
        lines += [("resident", f"I am at {f['where']}, {f['with']}. Water is not near us."),
                  ("agent", "Do you need medicine, care, or help leaving?"),
                  ("resident", "No, we are fine. We have food and medicine.")]
        summary = f"Safe at {f['where']} {f['with']}; no urgent needs."
    elif outcome == "NEEDS_EVACUATION":
        lines += [("resident", f"I am at {f['where']}, {f['with']}. {f['extra'].capitalize()}."),
                  ("agent", "Can you leave home on your own?"),
                  ("resident", f"Not easily, I {f['mobility_detail']}. Please send someone.")]
        summary = f"Ground floor, water entering; {f['mobility_detail']}; needs escort to shelter."
    elif outcome == "NEEDS_HELP":
        lines += [("resident", "We can stay, the water is low. But I " + f["extra"] + "."),
                  ("agent", "Are you hurt or do you need medicine?"),
                  ("resident", "No, nobody is hurt. Just need some hands.")]
        summary = "Can stay home but needs practical help moving belongings upstairs."
    elif ex.get("medical") == "self":
        lines += [("resident", "I am at home. My chest feels tight since this morning."),
                  ("agent", "I am connecting you to a person who can help right away."),
                  ("resident", "Okay. Please hurry.")]
        summary = "Resident reports chest tightness since morning; lives alone."
    elif ex.get("medical") == "household":
        lines += [("resident", "I'm okay but my husband fell in the kitchen. He can't get up."),
                  ("agent", "I am connecting you to a person who can help right away."),
                  ("resident", "Thank you, please come quickly.")]
        summary = "Resident fine but husband fell and cannot get up; household medical."
    lines.append(("agent", "Thank you. Please stay safe. Goodbye."))

    flag = ex.get("medical") is not None
    cls = {
        "status": "SAFE_IN_PLACE" if ex.get("ambiguous") else outcome,
        "confidence": 0.55 if ex.get("ambiguous") else 0.92,
        "needs": r["persona"]["needs"],
        "household_others_at_risk": ex.get("medical") == "household",
        "medical_flag": flag,
        "location_now": "upper_floor" if r["floor"] > 0 else "home",
        "language_detected": r["preferred_language"],
        "summary_en": summary[:200],
        "requires_human_review": bool(ex.get("ambiguous")),
        "review_reason": "Contradictory answers, possible confusion" if ex.get("ambiguous") else None,
    }
    return {
        "source": "template",
        "lines": [{"role": role, "text": text, "text_en": text} for role, text in lines],
        "live_status": "SAFE_IN_PLACE" if ex.get("ambiguous") else outcome,
        "classification": cls,
    }


def build_residents() -> tuple[list[dict], dict]:
    live = [
        {"resident_id": "R-001", "display_name": "Mdm Tan Ah Lian", "synthetic": True, "age": 82,
         "gender": "F", "languages": ["zh"], "dialect_hint": "Hokkien", "preferred_language": "zh",
         "location": {"lat": 3.0541, "lng": 101.5102},
         "address_label": "Blk 12, Jalan Sungai 3 (fictional)", "floor": 0, "lives_alone": True,
         "mobility": "walker", "medical_flags": ["hypertension"],
         "next_of_kin": {"name": "Tan Wei Ming", "relation": "son", "phone_masked": "+60 1X-XXX 4821"},
         "is_live_demo": True, "persona": None},
        {"resident_id": "R-002", "display_name": "Mr Lim Boon Huat", "synthetic": True, "age": 76,
         "gender": "M", "languages": ["en", "zh"], "dialect_hint": None, "preferred_language": "en",
         "location": {"lat": 3.0566, "lng": 101.5138},
         "address_label": "No. 8, Lorong Indah 2 (fictional)", "floor": 1, "lives_alone": False,
         "mobility": "independent", "medical_flags": ["diabetes"],
         "next_of_kin": {"name": "Lim Hui Min", "relation": "daughter", "phone_masked": "+60 1X-XXX 1937"},
         "is_live_demo": True, "persona": None},
    ]
    langs = (["zh"] * 13 + ["ms"] * 10 + ["ta"] * 6 + ["en"] * 5 + ["yue"] * 4)
    rng.shuffle(langs)
    hokkien_left = 2
    names = {k: list(v) for k, v in NAMES.items()}
    for v in names.values():
        rng.shuffle(v)

    residents, dialogues = list(live), {}
    for i, (slot, lang) in enumerate(zip(SLOTS, langs, strict=True)):
        outcome, mobility, floor, alone, band, ex = slot
        rid = f"R-{i + 3:03d}"
        name, gender = names[lang].pop()
        if ex.get("medical") == "household":
            gender = "F"
            name = name.replace("Mr ", "Mdm ").replace("En ", "Pn ")
        med = list(ex.get("med", []))
        if not med and rng.random() < 0.6:
            med = rng.sample(OTHER_MED, k=rng.choice([1, 1, 2]))
        if ex.get("ambiguous") and "dementia" not in med:
            med.append("dementia")
        dialect = None
        if lang == "zh" and hokkien_left:
            dialect, hokkien_left = "Hokkien", hokkien_left - 1
        relation, _ = rng.choice(KIN)
        surname = name.split()[1]
        r = {
            "resident_id": rid, "display_name": name, "synthetic": True, "age": _age(band),
            "gender": gender, "languages": [lang] if lang != "en" else ["en"],
            "dialect_hint": dialect, "preferred_language": lang, "location": _point(),
            "address_label": f"No. {rng.randint(1, 80)}, {rng.choice(STREETS)} {rng.randint(1, 9)} "
                             f"(fictional)",
            "floor": floor, "lives_alone": alone, "mobility": mobility, "medical_flags": med,
            "next_of_kin": {"name": f"{surname} {rng.choice(['Wei', 'Aina', 'Ravi', 'Ken', 'Mei'])}",
                            "relation": relation, "phone_masked": _phone()},
            "is_live_demo": False,
        }
        persona = {
            "scripted_outcome": outcome,
            "answers_on_attempt": ex.get("answers_on", 1),
            "facts": _facts(outcome, mobility, floor, alone, ex),
            "speech_style": rng.choice(STYLES),
            "ambiguous": bool(ex.get("ambiguous")),
            "volunteer_outcome": ex.get("volunteer_outcome"),
            "needs": _needs(mobility, med, ex),
        }
        r["persona"] = persona
        if ex.get("answers_on", 1) is not None:
            dialogues[rid] = _dialogue(r, outcome, ex)
        persona.pop("needs")
        residents.append(r)
    return residents, dialogues


def main() -> None:
    residents, dialogues = build_residents()
    files = {
        "scenario_flood_demo.json": SCENARIO,
        "residents.json": residents,
        "shelters.json": SHELTERS,
        "volunteers.json": VOLUNTEERS,
        "dialogues.json": dialogues,
    }
    for fname, data in files.items():
        (OUT / fname).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(residents)} residents, {len(dialogues)} dialogues")


if __name__ == "__main__":
    main()
