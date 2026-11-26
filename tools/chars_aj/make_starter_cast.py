"""make_starter_cast - the starter characters of config/cast.json, built from accepted outfit fits only.

    py -3 tools/chars_aj/make_starter_cast.py [--dry]

Plain Python, deterministic. For every recipe below (a look: body, face preset, hair, beard, palette, skin) it takes the first outfit
in the recipe's preference list that is fit-accepted on that body (library/wardrobe/index.json: status pass, review accept) and
writes the character into config/cast.json with status "draft". A body with no accepted outfit gets nothing (it is listed as
skipped): run this again when the garment work delivers one. Characters already in cast.json that are not starters are left alone.

The hair library's licence is still `unknown` in the registry; the project owner's approved plan is to use it, so every character
with hair carries a `licence_note` saying so.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAST = ROOT / "config" / "cast.json"
WARD = ROOT / "library" / "wardrobe" / "index.json"
HAIR_NOTE = ("hair and beards come from library/characters/aj/hair (Tripo3D output made by the project owner); the registry marks them "
             "licence 'unknown' pending the owner's confirmation of the generator's plan terms; used under the owner's approved plan")

HAIR = {"black": "#1b1512", "dark brown": "#3a2417", "brown": "#5a3620", "light brown": "#7a4a22", "auburn": "#8a3b1d", "ginger": "#b5541f",
        "blond": "#d2b06a", "grey": "#9c9c9c", "white": "#e4e1da"}
AGE_WORD = {"Kid": "child", "Teen": "teenage", "Adult": "adult", "Senior": "elderly"}
# What each outfit looks like with no palette colour given: (top, bottom) as written in `looks`
OUTFIT_TEXT = {"jeans_shirt": ("polo shirt", "jeans", "blue"), "pants_top": ("strap top", "wide trousers", None)}
PREFER = ["jeans_shirt", "pants_top"]

# id, body, face preset, hair style, hair colour name, facial hair (style, colour name) | None, outfit preference, palette, skin
R = [
    ("TeenBoyDarkHair", "Male_Teen", "Teen Classic", "male_spiky", "dark brown", None, ["jeans_shirt"], {"primary": "#C0392B"}, None),
    ("TeenBoyRedHair", "Male_Teen", "Teen Tapered", "male_messy", "ginger", None, ["jeans_shirt"], {"primary": "#2E7D5B", "secondary": "#8C7A5B"}, "light"),
    ("TeenBoyCurlyBlack", "Male_Teen", "Teen Tapered", "male_curly_short", "black", None, ["jeans_shirt"], {"primary": "#F2C230", "secondary": "#3A3F4A"}, "deep"),
    ("ElderManGreyHair", "Male_Senior", "Senior Strong", "male_side_part", "grey", ("facial_moustache_classic", "grey"), ["jeans_shirt"], {"primary": "#4A6FA5", "secondary": "#6B5A45"}, None),
    ("ElderManBalding", "Male_Senior", "Senior Soft", "male_balding_ring", "white", ("facial_beard_short", "white"), ["jeans_shirt"], {"primary": "#8E4A3A"}, None),
    ("ElderManLongBeard", "Male_Senior", "Senior Strong", "male_swept_back", "white", ("facial_beard_full", "white"), ["jeans_shirt"], {"primary": "#2F5D50", "secondary": "#3B3B3B"}, "tan"),
    ("GirlPigtails", "Female_Kid", "Kid Bright", "kid_pigtails", "light brown", None, ["jeans_shirt"], {"primary": "#E86A92"}, None),
    ("GirlBowlCut", "Female_Kid", "Kid Round", "kid_bowl_cut", "black", None, ["jeans_shirt"], {"primary": "#F4D03F", "secondary": "#2D6A4F"}, "fair"),
    ("GirlMessyRed", "Female_Kid", "Kid Round", "kid_messy", "ginger", None, ["jeans_shirt"], {"primary": "#5DADE2"}, "light"),
    ("TeenGirlPonytail", "Female_Teen", "Teen Classic", "female_ponytail", "dark brown", None, ["jeans_shirt"], {"primary": "#7D3C98"}, None),
    ("TeenGirlPixie", "Female_Teen", "Teen Tapered", "female_pixie", "blond", None, ["pants_top"], {"primary": "#1ABC9C", "secondary": "#34495E"}, None),
    ("TeenGirlSideBraid", "Female_Teen", "Teen Classic", "female_side_braid", "black", None, ["pants_top"], {"primary": "#E67E22", "secondary": "#2C2C2C"}, "brown"),
    ("WomanBunUpdo", "Female_Adult", "Adult Sculpted", "female_bun_updo", "brown", None, ["jeans_shirt"], {"primary": "#2E86C1"}, None),
    ("WomanLayeredLocks", "Female_Adult", "Adult Broad", "female_layered_locks", "black", None, ["pants_top"], {"primary": "#C0392B", "secondary": "#1C2833"}, "tan"),
    ("WomanCurlyShort", "Female_Adult", "Adult Sculpted", "female_curly_short", "auburn", None, ["pants_top"], {"primary": "#F5EEDC", "secondary": "#5D4037"}, None),
    ("GrandmaWhiteBob", "Female_Senior", "Senior Soft", "female_fringe_bob", "white", None, ["jeans_shirt"], {"primary": "#A3B18A"}, None),
    ("GrandmaGreyBun", "Female_Senior", "Senior Strong", "female_bun_updo", "grey", None, ["jeans_shirt"], {"primary": "#B5838D", "secondary": "#4F6D7A"}, "olive"),
    # bodies with no accepted outfit yet: these appear when the garment work delivers one
    ("ManBrownHair", "Male_Adult", "Adult Broad", "male_short_tidy", "brown", None, PREFER, {"primary": "#3E6FA8"}, None),
    ("ManGingerBeard", "Male_Adult", "Adult Sculpted", "male_side_part", "ginger", ("facial_beard_short", "ginger"), PREFER, {"primary": "#6B8E4E"}, "light"),
    ("ManBalding", "Male_Adult", "Adult Broad", "male_balding_ring", "grey", ("facial_moustache_classic", "grey"), PREFER, {"primary": "#8A5A44"}, "tan"),
    ("BoyBowlCut", "Male_Kid", "Kid Round", "kid_bowl_cut", "dark brown", None, PREFER, {"primary": "#E74C3C"}, None),
    ("BoyMessyBlond", "Male_Kid", "Kid Bright", "kid_messy", "blond", None, PREFER, {"primary": "#27AE60"}, "light"),
]
# the first starters (jumpers that were never fit-checked) are gone; their names keep working through these aliases
ALIASES = {"TeenBoy": "TeenBoyDarkHair", "TeenGirl": "TeenGirlPonytail", "Woman": "WomanBunUpdo", "Grandpa": "ElderManGreyHair",
           "Grandma": "GrandmaWhiteBob", "Girl": "GirlPigtails", "Man": "ManBrownHair", "Boy": "BoyBowlCut"}
OLD = ("Boy", "Girl", "TeenBoy", "TeenGirl", "Man", "Woman", "Grandpa", "Grandma")

STYLE_WORDS = {"male_spiky": "spiky hair", "male_messy": "messy hair", "male_curly_short": "short curly hair", "male_side_part": "side-parted hair",
               "male_swept_back": "swept-back hair", "male_balding_ring": "balding hair", "male_short_tidy": "short tidy hair",
               "kid_pigtails": "pigtails", "kid_bowl_cut": "bowl-cut hair", "kid_messy": "messy hair", "female_ponytail": "ponytail",
               "female_pixie": "pixie cut", "female_side_braid": "side braid", "female_bun_updo": "bun", "female_long_fringe": "long hair with a fringe", "female_layered_locks": "short layered hair",
               "female_curly_short": "short curly hair", "female_fringe_bob": "fringe bob", "facial_moustache_classic": "classic moustache",
               "facial_beard_short": "short beard", "facial_beard_full": "full beard", "facial_goatee": "goatee"}
NAMED = {"red": "#C0392B", "orange": "#E67E22", "yellow": "#F2C230", "green": "#3E8E5A", "dark green": "#2D5A3D", "teal": "#1ABC9C",
         "blue": "#2E6DB4", "sky blue": "#5DADE2", "navy": "#1F2F4F", "purple": "#7D3C98", "pink": "#E86A92", "brown": "#6B4A32",
         "tan": "#B79B72", "khaki": "#8C7A5B", "cream": "#F1EAD6", "white": "#F2F2F2", "grey": "#8A8A8A", "charcoal": "#33373D",
         "black": "#161616", "maroon": "#6E2230", "sage": "#A3B18A", "dusty rose": "#B5838D", "terracotta": "#B5654A"}


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def colour_name(h: str) -> str:
    c = _rgb(h)
    return min(NAMED, key=lambda n: sum((a - b) ** 2 for a, b in zip(c, _rgb(NAMED[n]))))


def accepted_outfits(idx: dict, body: str) -> list[str]:
    out = []
    for oid, o in idx["outfits"].items():
        f = (o.get("fits") or {}).get(body) or {}
        if f.get("status") == "pass" and f.get("review") == "accept" and o.get("usable", True) and f.get("file"):
            out.append(oid)
    return sorted(out)


def build(r, idx: dict):
    cid, body, face, hair, hair_name, beard, prefs, palette, skin = r
    have = accepted_outfits(idx, body)
    outfit = next((p for p in prefs if p in have), have[0] if have else None)
    if outfit is None:
        return None
    o = idx["outfits"][outfit]
    slots = {p["palette_slot"]: p["slot"] for p in o["pieces"].values()}
    pal = {k: v for k, v in palette.items() if k in slots}
    sex, age = body.split("_")
    top_slot = next((s for s, sl in slots.items() if sl == "top"), "primary")
    bot_slot = next((s for s, sl in slots.items() if sl == "bottom"), "secondary")
    tt, bt, bdef = OUTFIT_TEXT.get(outfit, ("top", "trousers", None))
    top = f"{colour_name(pal[top_slot])} {tt}" if top_slot in pal else tt
    bottom = f"{colour_name(pal[bot_slot])} {bt}" if bot_slot in pal else (f"{bdef} {bt}" if bdef else bt)
    who = ("boy" if sex == "Male" else "girl") if age == "Kid" else ("teenage boy" if sex == "Male" else "teenage girl") if age == "Teen" \
        else ("man" if sex == "Male" else "woman") if age == "Adult" else ("elderly man" if sex == "Male" else "elderly woman")
    hair_txt = f"{hair_name} {STYLE_WORDS.get(hair, hair.split('_', 1)[1].replace('_', ' ') + ' hair')}"
    beard_txt = f" and a {beard[1]} {STYLE_WORDS.get(beard[0], beard[0])}" if beard else ""
    looks = f"{who}, {hair_txt}{beard_txt}, {top}, {bottom}" + (f", {skin} skin" if skin else "")
    ent = {"family": "aj", "body": body, "face": face, "hair": {"style": hair, "color": HAIR[hair_name]},
           "facial_hair": {"style": beard[0], "color": HAIR[beard[1]]} if beard else None, "outfit": outfit, "addons": [], "palette": pal,
           "era": list(o["era"]), "looks": looks, "height_m": None, "status": "draft", "approved": False, "starter": True,
           "licence_note": HAIR_NOTE}
    if skin:
        ent["skin"] = skin
    return ent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    idx = json.loads(WARD.read_text(encoding="utf-8"))
    raw = CAST.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    cfg = json.loads(raw)
    chars = {k: v for k, v in cfg.get("characters", {}).items() if not v.get("starter") and k not in OLD}
    made, skipped = [], []
    for r in R:
        ent = build(r, idx)
        if ent is None:
            skipped.append(f"{r[0]} ({r[1]}: no accepted outfit yet)")
        else:
            chars[r[0]] = ent
            made.append(r[0])
    cfg["characters"] = chars
    cfg["aliases"] = {old: new for old, new in ALIASES.items() if new in chars}
    cfg["bodies"] = {k: {kk: vv for kk, vv in v.items()} for k, v in cfg["bodies"].items()}
    print(f"{len(made)} starter character(s): {', '.join(made)}")
    if skipped:
        print("skipped: " + "; ".join(skipped))
    if a.dry:
        return 0
    CAST.write_bytes(json.dumps(cfg, indent=1, ensure_ascii=False).replace("\n", eol).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
