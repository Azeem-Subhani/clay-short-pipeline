"""make_starter_cast - the starter characters of config/cast.json, built from accepted outfit fits only.

    py -3 tools/chars_aj/make_starter_cast.py [--dry]

Plain Python, deterministic (same registry in, same cast out). For every recipe below (a person: body, face preset, hair, beard, outfit,
add-ons, palette, skin, tags) it takes the first outfit of the recipe's preference list that is fit-accepted on that body
(library/wardrobe/index.json: status pass, review accept) and writes the character into config/cast.json with status "draft", its
`tags`, and `avoid`: the union of the independent reviewers' limits on its outfit and every add-on it wears (tools/cast_data.py
avoid_union), so the limits travel with the character into `clay-short cast`, casting.json and the plan check. A recipe whose body
has no accepted outfit gets nothing (it is listed as skipped). Characters already in cast.json that are not starters are left alone.

Cast rules behind the choices: no two characters share a silhouette and colour scheme (hair style, hair colour, face, skin, outfit and
palette differ), every body has several people, office and uniform looks use shirt_trousers / blouse_trousers / blouse_skirt with
tie, belt, blazer, cardigan, lanyard_badge, glasses, wrist_watch, and children wear the child cuts.

The hair library's licence is still `unknown` in the registry; the project owner's approved plan is to use it, so every character
with hair carries a `licence_note` saying so.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cast_data as cd  # noqa: E402

CAST = ROOT / "config" / "cast.json"
WARD = ROOT / "library" / "wardrobe" / "index.json"
HAIR_NOTE = ("hair and beards come from library/characters/aj/hair (Tripo3D output made by the project owner); the registry marks them "
             "licence 'unknown' pending the owner's confirmation of the generator's plan terms; used under the owner's approved plan")

HAIR = {"black": "#1b1512", "dark brown": "#3a2417", "brown": "#5a3620", "light brown": "#7a4a22", "auburn": "#8a3b1d", "ginger": "#b5541f",
        "blond": "#d2b06a", "grey": "#9c9c9c", "white": "#e4e1da"}
# What each outfit looks like when the recipe gives no palette colour: (top word, bottom word, top colour, bottom colour, shoe colour)
OUTFIT_TEXT = {
    "jeans_shirt": ("polo shirt", "jeans", None, "blue", None),
    "pants_top": ("strap top", "wide trousers", None, None, None),
    "casual_tshirt_trousers": ("t-shirt", "jeans", "coral", "blue", "white"),
    "shirt_trousers": ("shirt", "trousers", "light blue", "grey", "brown"),
    "kid_tshirt_shorts": ("t-shirt", "shorts", "yellow", "olive", "blue"),
    "blouse_skirt": ("blouse", "skirt", "white", "navy", "brown"),
    "blouse_trousers": ("blouse", "trousers", "white", "navy", "brown"),
}
ADDON_WORD = {"tie": "tie", "belt": "belt", "blazer": "blazer", "cardigan": "cardigan", "lanyard_badge": "lanyard badge",
              "glasses": "glasses", "wrist_watch": "wrist watch"}
STYLE_WORDS = {"male_spiky": "spiky hair", "male_messy": "messy hair", "male_curly_short": "short curly hair", "male_side_part": "side-parted hair",
               "male_swept_back": "swept-back hair", "male_balding_ring": "balding hair", "male_short_tidy": "short tidy hair",
               "male_parted_fringe": "parted fringe", "male_curtains": "curtain hair",
               "kid_pigtails": "pigtails", "kid_bowl_cut": "bowl-cut hair", "kid_messy": "messy hair", "female_ponytail": "ponytail",
               "female_pixie": "pixie cut", "female_side_braid": "side braid", "female_bun_updo": "bun", "female_long_fringe": "long hair with a fringe",
               "female_layered_locks": "short layered hair", "female_long_straight": "long straight hair", "female_royal_bob": "sleek bob", "female_twin_braids": "twin braids",
               "female_curly_short": "short curly hair", "female_fringe_bob": "fringe bob", "facial_moustache_classic": "classic moustache",
               "facial_beard_short": "short beard", "facial_beard_full": "full beard", "facial_goatee": "goatee"}
NAMED = {"red": "#C0392B", "orange": "#E67E22", "yellow": "#F2C230", "green": "#3E8E5A", "dark green": "#2D5A3D", "teal": "#1ABC9C",
         "blue": "#2E6DB4", "sky blue": "#5DADE2", "navy": "#1F2F4F", "purple": "#7D3C98", "pink": "#E86A92", "brown": "#6B4A32",
         "tan": "#B79B72", "khaki": "#8C7A5B", "cream": "#F1EAD6", "white": "#F2F2F2", "grey": "#8A8A8A", "charcoal": "#33373D",
         "black": "#161616", "maroon": "#6E2230", "sage": "#A3B18A", "dusty rose": "#B5838D", "terracotta": "#B5654A",
         "light blue": "#BCD3EC", "pale green": "#CFE3DC", "lilac": "#C9B6D9", "olive": "#6B7A4F", "coral": "#F08A75",
         "slate": "#4A4F5A", "slate blue": "#3A4A63", "steel blue": "#3A5F8F", "dark slate": "#5D5A66", "pale blue": "#DDE8F3"}
STARTER_FIELDS = ("family", "body", "face", "hair", "facial_hair", "outfit", "addons", "palette", "era", "looks", "height_m", "status",
                  "approved", "starter", "licence_note", "tags", "avoid")


def R(cid, body, face, hair, hair_name, beard, outfits, addons, palette, skin, tags):
    """One recipe. beard: (style, colour name) | None. addons: [(item, hex | None)]."""
    return dict(id=cid, body=body, face=face, hair=hair, hair_name=hair_name, beard=beard, outfits=outfits, addons=addons,
                palette=palette, skin=skin, tags=tags)


# id, body, face preset, hair style, hair colour, facial hair, outfit preference, add-ons, palette {slot: hex}, skin, tags
RECIPES = [
    # --- men, adult: casual, office, uniform
    R("ManBrownHair", "Male_Adult", "Adult Broad", "male_short_tidy", "brown", None, ["casual_tshirt_trousers"], [],
      {"primary": "#3E6FA8", "secondary": "#4A4F5A", "shoes": "#F2F2F2"}, None, ["casual", "everyday"]),
    R("ManGingerBeard", "Male_Adult", "Adult Sculpted", "male_side_part", "ginger", ("facial_beard_short", "ginger"), ["casual_tshirt_trousers"], [],
      {"primary": "#6B8E4E", "secondary": "#6B4A32", "shoes": "#2B2B2B"}, "light", ["casual", "everyday"]),
    R("ManBalding", "Male_Adult", "Adult Broad", "male_balding_ring", "grey", ("facial_moustache_classic", "grey"), ["shirt_trousers"],
      [("tie", "#1F2F4F"), ("glasses", None)], {"primary": "#E9EEF3", "secondary": "#3A3F4A", "shoes": "#2B2B2B"}, "tan",
      ["office", "smart", "clerk"]),
    R("OfficeManBadge", "Male_Adult", "Adult Sculpted", "male_parted_fringe", "black", None, ["shirt_trousers"],
      [("lanyard_badge", "#2E86C1"), ("wrist_watch", None)], {"primary": "#CFE3DC", "secondary": "#4B4F58", "shoes": "#3A2417"}, "olive",
      ["office", "staff"]),
    R("ManagerBlazer", "Male_Adult", "Adult Broad", "male_swept_back", "dark brown", ("facial_goatee", "dark brown"), ["shirt_trousers"],
      [("blazer", "#3A3F4A"), ("tie", "#6E2230"), ("wrist_watch", None)], {"primary": "#F2F2F2", "secondary": "#2C2F36", "shoes": "#161616"}, "fair",
      ["office", "smart", "manager"]),
    R("SecurityGuard", "Male_Adult", "Adult Broad", "male_short_tidy", "black", None, ["shirt_trousers"],
      [("lanyard_badge", "#F2C230"), ("belt", "#8C7A5B")], {"primary": "#1F2F4F", "secondary": "#15181D", "shoes": "#111111"}, "deep",
      ["security", "uniform", "office"]),
    # --- women, adult
    R("WomanBunUpdo", "Female_Adult", "Adult Sculpted", "female_bun_updo", "brown", None, ["casual_tshirt_trousers"], [],
      {"primary": "#2E86C1", "secondary": "#3A5F8F", "shoes": "#F2F2F2"}, None,
      ["casual", "everyday"]),
    R("WomanLayeredLocks", "Female_Adult", "Adult Broad", "female_layered_locks", "black", None, ["kid_tshirt_shorts"], [],
      {"primary": "#C0392B", "secondary": "#1C2833", "shoes": "#F2F2F2"}, "tan", ["casual", "everyday"]),
    R("WomanCurlyShort", "Female_Adult", "Adult Sculpted", "female_curly_short", "auburn", None, ["blouse_skirt"], [],
      {"primary": "#F5EEDC", "secondary": "#5D4037", "shoes": "#3A2417"}, None, ["smart", "everyday"]),
    R("OfficeWomanCardigan", "Female_Adult", "Adult Sculpted", "female_ponytail", "brown", None, ["blouse_trousers"],
      [("cardigan", "#A3B18A"), ("lanyard_badge", "#E67E22")], {"primary": "#F2F2F2", "secondary": "#3A4A63", "shoes": "#3A2417"}, "fair",
      ["office", "staff", "smart"]),
    R("Receptionist", "Female_Adult", "Adult Broad", "female_royal_bob", "black", None, ["blouse_trousers"],
      [("lanyard_badge", "#F2F2F2"), ("belt", "#8C7A5B")], {"primary": "#1F2F4F", "secondary": "#1B1F27", "shoes": "#111111"}, "tan",
      ["office", "receptionist", "smart"]),
    R("ManagerWomanBlazer", "Female_Adult", "Adult Sculpted", "female_fringe_bob", "auburn", None, ["blouse_skirt"],
      [("blazer", "#1C2833"), ("glasses", None), ("wrist_watch", None)], {"primary": "#F5EEDC", "secondary": "#6E2230", "shoes": "#161616"}, "light",
      ["office", "smart", "manager"]),
    # --- seniors
    R("ElderManGreyHair", "Male_Senior", "Senior Strong", "male_side_part", "grey", ("facial_moustache_classic", "grey"), ["shirt_trousers"], [],
      {"primary": "#4A6FA5", "secondary": "#6B5A45", "shoes": "#3A2417"}, None, ["smart", "everyday"]),
    R("ElderManBalding", "Male_Senior", "Senior Soft", "male_balding_ring", "white", ("facial_beard_short", "white"), ["casual_tshirt_trousers"], [],
      {"primary": "#8E4A3A", "secondary": "#3A5F8F", "shoes": "#F2F2F2"}, None, ["casual", "everyday"]),
    R("ElderManLongBeard", "Male_Senior", "Senior Strong", "male_swept_back", "white", ("facial_beard_full", "white"), ["kid_tshirt_shorts"], [],
      {"primary": "#2F5D50", "secondary": "#B79B72", "shoes": "#8E4A3A"}, "tan", ["casual", "summer"]),
    R("ElderManCardigan", "Male_Senior", "Senior Soft", "male_short_tidy", "white", None, ["shirt_trousers"],
      [("cardigan", "#6B5A45"), ("glasses", None), ("tie", "#6E2230")], {"primary": "#F1EAD6", "secondary": "#4A4F5A", "shoes": "#3A2417"}, "fair",
      ["smart", "retired", "teacher"]),
    R("GrandmaWhiteBob", "Female_Senior", "Senior Soft", "female_fringe_bob", "white", None, ["casual_tshirt_trousers"], [],
      {"primary": "#A3B18A", "secondary": "#4F6D7A", "shoes": "#F2F2F2"}, None, ["casual", "everyday"]),
    R("GrandmaGreyBun", "Female_Senior", "Senior Strong", "female_bun_updo", "grey", None, ["blouse_trousers"], [],
      {"primary": "#B5838D", "secondary": "#4F6D7A", "shoes": "#3A2417"}, "olive", ["smart", "everyday"]),
    R("GrandmaCardigan", "Female_Senior", "Senior Soft", "female_curly_short", "white", None, ["blouse_trousers"],
      [("cardigan", "#B5838D"), ("glasses", None)], {"primary": "#C9B6D9", "secondary": "#5D5A66", "shoes": "#3A2417"}, "porcelain",
      ["smart", "retired", "warm"]),
    # --- teens
    R("TeenBoyDarkHair", "Male_Teen", "Teen Classic", "male_spiky", "dark brown", None, ["casual_tshirt_trousers"], [],
      {"primary": "#EAEDED", "secondary": "#3A5F8F", "shoes": "#F2F2F2"}, None,
      ["casual", "teen"]),
    R("TeenBoyRedHair", "Male_Teen", "Teen Tapered", "male_messy", "ginger", None, ["kid_tshirt_shorts"], [],
      {"primary": "#2E7D5B", "secondary": "#8C7A5B", "shoes": "#C0392B"}, "light", ["casual", "teen", "summer"]),
    R("TeenBoyCurlyBlack", "Male_Teen", "Teen Tapered", "male_curly_short", "black", None, ["casual_tshirt_trousers"], [],
      {"primary": "#F2C230", "secondary": "#3A3F4A", "shoes": "#F2F2F2"}, "deep", ["casual", "teen"]),
    R("TeenGirlPonytail", "Female_Teen", "Teen Classic", "female_ponytail", "dark brown", None, ["casual_tshirt_trousers"], [],
      {"primary": "#7D3C98", "secondary": "#3A5F8F", "shoes": "#F2F2F2"}, None,
      ["casual", "teen"]),
    R("TeenGirlPixie", "Female_Teen", "Teen Tapered", "female_pixie", "blond", None, ["kid_tshirt_shorts"], [],
      {"primary": "#1ABC9C", "secondary": "#34495E", "shoes": "#E86A92"}, None, ["casual", "teen", "summer"]),
    R("TeenGirlSideBraid", "Female_Teen", "Teen Classic", "female_side_braid", "black", None, ["casual_tshirt_trousers"], [],
      {"primary": "#E67E22", "secondary": "#2C2C2C", "shoes": "#F2F2F2"}, "brown", ["casual", "teen"]),
    R("TeenGirlSchool", "Female_Teen", "Teen Tapered", "female_twin_braids", "black", None, ["blouse_skirt"], [("cardigan", "#B5838D")],
      {"primary": "#F2F2F2", "secondary": "#2D3E5E", "shoes": "#161616"}, "olive", ["school", "smart", "teen"]),
    # --- kids
    R("BoyBowlCut", "Male_Kid", "Kid Round", "kid_bowl_cut", "dark brown", None, ["casual_tshirt_trousers"], [],
      {"primary": "#E74C3C", "secondary": "#3A5F8F", "shoes": "#F2F2F2"}, None, ["casual", "kid"]),
    R("BoyMessyBlond", "Male_Kid", "Kid Bright", "kid_messy", "blond", None, ["kid_tshirt_shorts"], [],
      {"primary": "#27AE60", "secondary": "#8C7A5B", "shoes": "#E67E22"}, "light", ["casual", "kid", "summer"]),
    R("BoySchoolShirt", "Male_Kid", "Kid Bright", "kid_messy", "black", None, ["shirt_trousers"], [("tie", "#1F2F4F")],
      {"primary": "#DDE8F3", "secondary": "#2C2F36", "shoes": "#161616"}, "brown", ["school", "smart", "kid"]),
    R("GirlPigtails", "Female_Kid", "Kid Bright", "kid_pigtails", "light brown", None, ["kid_tshirt_shorts"], [],
      {"primary": "#E86A92", "secondary": "#5DADE2", "shoes": "#F2F2F2"}, None,
      ["casual", "kid"]),
    R("GirlBowlCut", "Female_Kid", "Kid Round", "kid_bowl_cut", "black", None, ["casual_tshirt_trousers"], [],
      {"primary": "#F4D03F", "secondary": "#2D6A4F", "shoes": "#E74C3C"}, "fair",
      ["casual", "kid"]),
    R("GirlMessyRed", "Female_Kid", "Kid Round", "kid_messy", "ginger", None, ["blouse_skirt"], [],
      {"primary": "#5DADE2", "secondary": "#2D3E5E", "shoes": "#161616"}, "light",
      ["school", "smart", "kid"]),
]
# the first starters' short names keep working through these aliases
ALIASES = {"TeenBoy": "TeenBoyDarkHair", "TeenGirl": "TeenGirlPonytail", "Woman": "WomanBunUpdo", "Grandpa": "ElderManGreyHair",
           "Grandma": "GrandmaWhiteBob", "Girl": "GirlPigtails", "Man": "ManBrownHair", "Boy": "BoyBowlCut"}
OLD = ("Boy", "Girl", "TeenBoy", "TeenGirl", "Man", "Woman", "Grandpa", "Grandma")


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


def accepted_addons(idx: dict, body: str) -> list[str]:
    return cd.accepted_addons(idx, body)


def looks_line(r: dict, outfit: str, slots: dict, pal: dict) -> str:
    """The `looks` line, written from the recipe in the words of the render: who, hair, beard, top, bottom, shoes, add-ons, skin."""
    sex, age = r["body"].split("_")
    who = ("boy" if sex == "Male" else "girl") if age == "Kid" else ("teenage boy" if sex == "Male" else "teenage girl") if age == "Teen" \
        else ("man" if sex == "Male" else "woman") if age == "Adult" else ("elderly man" if sex == "Male" else "elderly woman")
    tw, bw, tc, bc, sc = OUTFIT_TEXT[outfit]
    top_slot = next((s for s, sl in slots.items() if sl == "top"), "primary")
    bot_slot = next((s for s, sl in slots.items() if sl == "bottom"), "secondary")
    top = f"{colour_name(pal[top_slot]) if top_slot in pal else tc} {tw}".replace("None ", "")
    bottom = f"{colour_name(pal[bot_slot]) if bot_slot in pal else bc} {bw}".replace("None ", "")
    shoes = f"{colour_name(pal['shoes']) if 'shoes' in pal else sc} shoes" if "feet" in slots.values() else ""
    hair = f"{r['hair_name']} {STYLE_WORDS.get(r['hair'], r['hair'].split('_', 1)[1].replace('_', ' ') + ' hair')}"
    beard = f" and a {r['beard'][1]} {STYLE_WORDS.get(r['beard'][0], r['beard'][0])}" if r["beard"] else ""
    adds = []
    for item, col in r["addons"]:
        adds.append(f"{colour_name(col) + ' ' if col and item not in ('glasses', 'wrist_watch') else ''}{ADDON_WORD[item]}")
    parts = [who, hair + beard, top, bottom]
    if shoes and "None" not in shoes:
        parts.append(shoes)
    parts += adds
    if r["skin"]:
        parts.append(f"{r['skin']} skin")
    return ", ".join(parts)


def build(r: dict, idx: dict):
    have = accepted_outfits(idx, r["body"])
    outfit = next((p for p in r["outfits"] if p in have), have[0] if have else None)
    if outfit is None:
        return None
    o = idx["outfits"][outfit]
    slots = {p["palette_slot"]: p["slot"] for p in o["pieces"].values()}
    pal = {k: v for k, v in r["palette"].items() if k in slots}
    fits_ok = accepted_addons(idx, r["body"])
    for item, _col in r["addons"]:
        if item not in fits_ok:
            raise SystemExit(f"{r['id']}: add-on {item} is not fit-accepted on {r['body']}")
    adds = [{"item": item, **({"color": col} if col else {})} for item, col in r["addons"]]
    eras = set(o["era"])
    for a in adds:
        eras &= set(idx["addons"][a["item"]]["era"])
    ent = {"family": "aj", "body": r["body"], "face": r["face"], "hair": {"style": r["hair"], "color": HAIR[r["hair_name"]]},
           "facial_hair": {"style": r["beard"][0], "color": HAIR[r["beard"][1]]} if r["beard"] else None, "outfit": outfit, "addons": adds,
           "palette": pal, "era": sorted(eras), "looks": looks_line(r, outfit, slots, pal), "height_m": None, "status": "draft",
           "approved": False, "starter": True, "licence_note": HAIR_NOTE, "tags": list(r["tags"]),
           "avoid": cd.avoid_union(idx, r["body"], outfit, adds)}
    if r["skin"]:
        ent["skin"] = r["skin"]
    return ent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    idx = json.loads(WARD.read_text(encoding="utf-8"))
    raw = CAST.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    cfg = json.loads(raw)
    keep = {k: v for k, v in cfg.get("characters", {}).items() if not v.get("starter") and k not in OLD}
    chars = {}
    made, skipped = [], []
    for r in RECIPES:
        ent = build(r, idx)
        if ent is None:
            skipped.append(f"{r['id']} ({r['body']}: no accepted outfit yet)")
        else:
            chars[r["id"]] = ent
            made.append(r["id"])
    chars.update(keep)
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
