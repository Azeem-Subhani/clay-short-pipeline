"""Write the casting test clip: output/_staging/itest_cast/

    py -3 tools/tests/cast/make_itest_cast.py

Four people in one short story (modern period):
    ana    TeenGirlPonytail   a starter, as it is                                  -> EXISTING
    ben    ElderManGreyHair   a starter, with a per-clip costume (recolour)        -> EXISTING
    lena   no such character  an adult woman with long hair in teal and navy       -> ADAPT  (dressed from accepted items)
    king   no such character  the school-play king: a medieval tunic and a crown   -> MISSING (nothing medieval is fit-accepted on Male_Adult)
The plan is a small but complete one (it passes the plan check apart from the warnings it names), so `clip.py plan-check`,
`clip.py casting` and `clip.py cast-sheets` all work on it.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output" / "_staging" / "itest_cast"

VO = [
    "Ana and her grandfather Ben sat in the school hall.",
    "Lena, the drama teacher, clapped her hands for the play to start.",
    "Then the king walked in wearing a golden crown and everybody laughed.",
]


def plan() -> dict:
    return {
        "logline": "A school play where the king arrives late and the whole hall cheers.",
        "format": "twist",
        "world": {"era": "modern", "place": "a school hall with a small wooden stage", "rules": ["only modern clothes in the audience", "the king's costume is a play costume"],
                  "palette": ["#2E7D5B", "#F2C230", "#2E86C1"], "surfaces": []},
        "cast": [
            {"id": "ana", "base": "TeenGirlPonytail", "role": "the granddaughter who watches", "reads_as": "purple polo, dark ponytail, jeans"},
            {"id": "ben", "base": "ElderManGreyHair", "role": "her grandfather", "reads_as": "grey hair and moustache, a blue polo",
             "costume": {"recolor": {"primary": "#6B8E4E"}}},
            {"id": "lena", "base": "NewTeacher", "role": "the drama teacher, a woman", "reads_as": "long hair, teal top, navy trousers",
             "wants": {"sex": "Female", "age": "Adult", "tags": ["jeans"], "hair": "long", "palette_hint": ["teal", "navy"]}},
            {"id": "king", "base": "KingActor", "role": "the school-play king, a man", "reads_as": "golden crown, long medieval tunic",
             "wants": {"sex": "Male", "age": "Adult", "era": "medieval", "tags": ["tunic", "crown"], "facial_hair": "beard"}},
        ],
        "sets": [{"id": "hall", "description": "a school hall with a stage at one end", "layout": "camera side: the audience seats; the stage is across from the camera",
                  "surfaces": [], "dressing": ["curtains", "benches"]}],
        "shots": [{
            "id": "sh01", "set": "hall", "time": "interior_day", "cast": ["ana", "ben", "lena", "king"],
            "vo_text": " ".join(VO), "purpose": "set the scene and land the joke", "action": "the people in the hall; the king arrives",
            "views": [
                {"id": "audience", "on": "start", "size": "medium", "shows": "Ana and Ben on the bench", "why": "who is watching"},
                {"id": "teacher", "on": "Lena the", "size": "medium", "shows": "Lena claps", "why": "the play starts"},
                {"id": "king", "on": "Then the king", "size": "full", "shows": "the king enters with a crown", "why": "the payoff", "inside": "the king bows and the hall laughs"},
            ],
        }],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "shotplan.json").write_text(json.dumps(plan(), indent=1) + "\n", encoding="utf-8")
    (OUT / "script.json").write_text(json.dumps({"title": "The Late King", "beats": [{"voiceover": v} for v in VO]}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
