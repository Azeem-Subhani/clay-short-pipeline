"""casting - turn the characters a story needs into dressed, approved characters (plain Python, standard library only).

    py -3 tools/casting.py <clip dir> [--apply]          (clip.py casting <clip> [--apply])

Reads the clip's shotplan.json (cast[]: id, base, role, reads_as, costume, optional wants {sex, age, era, tags [...], hair,
facial_hair, palette_hint}) and script.json (context), and for every character decides:

  EXISTING  the named base exists in config/cast.json and satisfies `wants` (its body's sex and age, the story's period, the
            outfit and add-on words, the hair and beard asked for) and its costume passes the plan check
  ADAPT     the closest body (sex and age are hard filters) dressed from items that are fit-accepted on that body: the exact delta is
            returned (outfit, add-ons, palette, hair style and colour, beard, face preset, skin) and `--apply` registers it in
            config/cast.json as a draft (so later stories reuse it) and points the plan's `base` at it
  MISSING   a requirement nothing satisfies, written as an explicit ask: a wardrobe item (outfit or add-on fit-accepted on that body: where to
            get it and how to fit it), a hairstyle, the missing facts (wants.sex / wants.age), or a Mixamo animation (the text of
            tools/chars_aj/clips.py --ask)

Writes <clip>/casting.json and <clip>/casting.md; exit 0 when everything resolves, 2 when anything is MISSING. The same input gives the
same bytes (no clock, no randomness: where the rules leave a free choice, a CRC of the character id picks).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cast_data as cd  # noqa: E402

GARMENT_WORDS = {"tunic", "armour", "armor", "dress", "robe", "gown", "uniform", "suit", "coat", "jacket", "trousers", "jeans", "shirt", "polo",
                 "hoodie", "skirt", "overalls", "jumper", "sweater", "tshirt", "t-shirt", "top", "tank", "chainmail", "doublet", "kimono"}
ADDON_WORDS = {"crown", "hat", "cap", "helmet", "apron", "cloak", "cape", "belt", "scarf", "glasses", "spectacles", "bag", "backpack",
               "hood", "shawl", "tie", "bandana", "headband", "mask"}
PROP_WORDS = {"sword", "scepter", "sceptre", "staff", "shield", "lantern", "cane", "umbrella", "book", "key"}
SYN = {"armor": "armour", "spectacles": "glasses", "sceptre": "scepter", "t-shirt": "tshirt"}
FEMALE = {"woman", "girl", "queen", "mother", "mum", "mom", "grandmother", "grandma", "lady", "princess", "wife", "daughter", "sister", "aunt", "she", "her", "female"}
MALE = {"man", "boy", "king", "father", "dad", "grandfather", "grandpa", "prince", "husband", "son", "brother", "uncle", "he", "his", "male", "farmer",
        "knight", "pirate", "soldier", "wizard", "innkeeper"}
KID = {"boy", "girl", "child", "kid", "little", "toddler", "son", "daughter"}
TEEN = {"teen", "teenager", "teenage", "adolescent"}
SENIOR = {"old", "elderly", "grandmother", "grandma", "grandfather", "grandpa", "aged", "senior", "ancient"}
HAIR_COLOURS = {"black": "#1b1512", "dark": "#3a2417", "brown": "#5a3620", "chestnut": "#5a3620", "auburn": "#8a3b1d", "red": "#a8431c", "ginger": "#b5541f",
                "blond": "#d2b06a", "blonde": "#d2b06a", "grey": "#9c9c9c", "gray": "#9c9c9c", "white": "#e4e1da"}
PLEASANT = ["#C0392B", "#2E7D5B", "#F2C230", "#2E86C1", "#7D3C98", "#E67E22", "#1ABC9C", "#E86A92", "#8E4A3A", "#4A6FA5"]
COLOUR_NAMES = {"red": "#C0392B", "orange": "#E67E22", "yellow": "#F2C230", "green": "#3E8E5A", "teal": "#1ABC9C", "blue": "#2E6DB4", "navy": "#1F2F4F",
                "purple": "#7D3C98", "pink": "#E86A92", "brown": "#6B4A32", "tan": "#B79B72", "khaki": "#8C7A5B", "cream": "#F1EAD6", "white": "#F2F2F2",
                "grey": "#8A8A8A", "gray": "#8A8A8A", "charcoal": "#33373D", "black": "#161616", "maroon": "#6E2230", "gold": "#D4AF37", "silver": "#B8B8C0"}
FACES = {"Kid": ("Kid Round", "Kid Bright"), "Teen": ("Teen Classic", "Teen Tapered"), "Adult": ("Adult Broad", "Adult Sculpted"),
         "Senior": ("Senior Strong", "Senior Soft")}
FETCH_ADDON = ("search BlenderKit (py -3 tools/clip.py bk-search \"{q}\" --type model) for a single clean mesh, CC0 or Royalty Free (nothing else); "
               "put it in library/wardrobe/addons/{item}.blend (rigid: bone-parented, or skinned to the Aj armature), check its fit on {body} "
               "with tools/chars_aj/fit.py, and register it in library/wardrobe/index.json > addons.{item} with kind, bone, covers, era, licence "
               "and fits.{body} status pass + review accept (review none is allowed for a rigid item)")
FETCH = ("search BlenderKit (py -3 tools/clip.py bk-search \"{q}\" --type model) for a clothed character, CC0 or Royalty Free (nothing else), with the clothes "
         "as separate meshes on a rigged character; then fit it to {body} with `py -3 tools/chars_aj/fit.py custom ...` (or build the garment with fit.py custom), "
         "and register it in library/wardrobe/index.json with fits.{body} status pass + review accept (licence recorded)")


def words(s) -> list[str]:
    return [SYN.get(w, w) for w in re.split(r"[^a-z0-9]+", str(s or "").lower()) if w]


def crc(*parts) -> int:
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))


def pick(options: list, *key):
    return options[crc(*key) % len(options)] if options else None


def colour_hex(c: str | None) -> str | None:
    if not c:
        return None
    c = str(c).strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
        return c.upper()
    return COLOUR_NAMES.get(c.lower())


# ----------------------------------------------------------------------------------------------- what is wanted
def infer(entry: dict) -> dict:
    text = words(" ".join(str(entry.get(k, "")) for k in ("id", "role", "reads_as")))
    t = set(text)
    sex = "Female" if t & FEMALE else ("Male" if t & MALE else None)
    if t & FEMALE and t & MALE:                       # "grandmother and his dog": the role words come first
        first = next(w for w in text if w in FEMALE | MALE)
        sex = "Female" if first in FEMALE else "Male"
    age = "Senior" if t & SENIOR else ("Kid" if t & KID else ("Teen" if t & TEEN else None))
    if age is None and sex is not None:
        age = "Adult"
    return {"sex": sex, "age": age}


def effective_wants(entry: dict, reg: dict, era: str | None) -> dict:
    w = dict(entry.get("wants") or {})
    name, ch, bare = cd.resolve(reg, entry.get("base") or "")
    body = (ch or {}).get("body") or bare
    if body:                                          # an explicit `wants` beats what the base says
        sx, ag = body.split("_")
        w.setdefault("sex", sx)
        w.setdefault("age", ag)
    guess = infer(entry)
    for k in ("sex", "age"):
        if not w.get(k) and guess.get(k):
            w[k] = guess[k]
            w.setdefault("_inferred", []).append(k)
    w["era"] = w.get("era") or era or "any"
    w["tags"] = sorted({SYN.get(t, t) for tag in (w.get("tags") or []) for t in words(tag)})
    w["hair"] = w.get("hair")
    w["facial_hair"] = w.get("facial_hair")
    w["palette_hint"] = w.get("palette_hint")
    return w


# ----------------------------------------------------------------------------------------------- the wardrobe
def outfit_words(ward: dict, oid: str) -> set[str]:
    o = ward["outfits"][oid]
    return set(words(oid + " " + o.get("title", "") + " " + " ".join(o.get("tags", [])) + " " + " ".join(cd.pieces(ward, oid))))


def addon_words(ward: dict, item: str) -> set[str]:
    a = ward["addons"][item]
    return set(words(item + " " + a.get("title", "") + " " + " ".join(a.get("tags", []))))


def satisfies(ch: dict, ward: dict, w: dict) -> tuple[bool, list[str]]:
    """Does an existing character already meet `wants`? -> (yes, why not)"""
    why = []
    sex, age = ch["body"].split("_")
    if w.get("sex") and w["sex"] != sex:
        why.append(f"{ch['body']} is {sex}, wanted {w['sex']}")
    if w.get("age") and w["age"] != age:
        why.append(f"{ch['body']} is {age}, wanted {w['age']}")
    if w.get("era") and w["era"] != "any" and not cd.era_ok(ch.get("era", []), w["era"]):
        why.append(f"{', '.join(ch.get('era', []))} is not {w['era']}")
    have = set(words(ch.get("looks", "")))
    if ch.get("outfit"):
        have |= outfit_words(ward, ch["outfit"])
    for a in ch.get("addons") or []:
        have |= addon_words(ward, a["item"]) if a["item"] in (ward.get("addons") or {}) else set(words(a["item"]))
    for t in w.get("tags", []):
        if t not in have:
            why.append(f"no '{t}'")
    if w.get("hair"):
        hw = set(words(ch.get("hair", {}).get("style", ""))) | set(words(ch.get("looks", "")))
        if not set(words(w["hair"])) & hw:
            why.append(f"hair '{w['hair']}' not matched")
    if w.get("facial_hair") and w["facial_hair"] not in ("none", "no"):
        fh = ch.get("facial_hair")
        if not fh or not set(words(w["facial_hair"])) & (set(words(fh["style"])) | {"beard", "moustache", "facial"}):
            why.append(f"facial hair '{w['facial_hair']}' not matched")
    return not why, why


# ----------------------------------------------------------------------------------------------- hair
def hair_pool(body: str, hair_idx: dict, kind: str = "hair") -> list[str]:
    sex, age = body.split("_")
    styles = sorted(hair_idx.get(kind, {}))
    if kind == "facial":
        return styles if sex == "Male" and age in ("Adult", "Senior") else []
    if age == "Kid":
        return [s for s in styles if s.startswith("kid_")]
    return [s for s in styles if s.startswith("male_" if sex == "Male" else "female_")]


def choose_hair(cid: str, body: str, want: str | None, hair_idx: dict) -> tuple[str | None, str | None]:
    """(style, problem)"""
    pool = hair_pool(body, hair_idx)
    if want and want.lower() in ("none", "no"):
        return None, None
    if want:
        ww = set(words(want))
        if "bald" in ww or "balding" in ww:
            ww |= {"balding"}
        if "pony" in ww:
            ww |= {"ponytail"}
        if "plait" in ww or "plaits" in ww:
            ww |= {"braid", "braids"}
        scored = sorted(((-len(ww & set(words(s))), s) for s in pool))
        if scored and scored[0][0] < 0:
            return scored[0][1], None
        return None, f"hairstyle '{want}' for {body}: none of the {len(pool)} styles for this body matches ({', '.join(pool)})"
    return pick(pool, cid, body, "hair"), None


def hair_colour(cid: str, age: str, want_text: str | None, role_text: str) -> str:
    for wd in words(want_text) + words(role_text):
        if wd in HAIR_COLOURS:
            return HAIR_COLOURS[wd]
    pool = ["white", "grey"] if age == "Senior" else ["black", "dark", "brown", "auburn", "ginger", "blond"]
    return HAIR_COLOURS[pick(pool, cid, "hair colour")]


# ----------------------------------------------------------------------------------------------- the match
def ask_outfit(word: str, era: str, body: str) -> str:
    q = f"{era} {word}" if era not in ("any", "modern") else word
    return f"a {q} outfit fit-accepted on {body}: " + FETCH.format(q=q, body=body)


def ask_addon(word: str, era: str, body: str) -> str:
    q = f"{era} {word}" if era not in ("any", "modern") else word
    return f"a {q} add-on fit-accepted on {body}: " + FETCH_ADDON.format(q=q, item=word, body=body)


def adapt(entry: dict, w: dict, reg: dict, ward: dict, hair_idx: dict, name0: str | None) -> tuple[dict | None, list[dict], list[str]]:
    """-> (new character entry or None, missing asks, notes)"""
    cid = entry["id"]
    miss, notes = [], []
    if not (w.get("sex") in cd.SEXES and w.get("age") in cd.AGES):
        miss.append({"kind": "spec", "ask": f"say who '{cid}' is: wants.sex (Male | Female) and wants.age (Kid | Teen | Adult | Senior) in the plan's cast entry "
                                            f"(could not be read from role {entry.get('role')!r} and reads_as {entry.get('reads_as')!r})"})
        return None, miss, notes
    body = f"{w['sex']}_{w['age']}"
    era = w["era"]
    tags = w["tags"]
    # the outfit: era is a hard filter, tags are the score
    cands = [o for o in cd.accepted_outfits(ward, body) if era == "any" or cd.era_ok(cd.outfit_era(ward, o), era)]
    garments = [t for t in tags if t in GARMENT_WORDS]
    addons_wanted = [t for t in tags if t in ADDON_WORDS]
    props = [t for t in tags if t in PROP_WORDS]
    other = [t for t in tags if t not in GARMENT_WORDS | ADDON_WORDS | PROP_WORDS]
    outfit = None
    if cands:
        def score(o):
            ow = outfit_words(ward, o)
            return (-(10 * len([t for t in tags if t in ow]) + (3 if o == (reg.get("characters", {}).get(name0 or "", {}) or {}).get("outfit") else 0)), o)
        outfit = sorted(cands, key=score)[0]
        have = outfit_words(ward, outfit)
        for g in garments:
            if g not in have:
                miss.append({"kind": "outfit", "body": body, "ask": ask_outfit(g, era, body)})
    else:
        word = garments[0] if garments else "casual outfit"
        miss.append({"kind": "outfit", "body": body, "ask": ask_outfit(word, era, body) + f" (nothing in the wardrobe is fit-accepted on {body} for a {era} story)"})
    have_o = outfit_words(ward, outfit) if outfit else set()
    for t in other:
        if t not in have_o:
            notes.append(f"word '{t}' is a description only (no wardrobe item is named that); not matched")
    for p in props:
        notes.append(f"'{p}' is a prop, not a garment: take it from the asset library (py -3 tools/clip.py assets find {p})")
    adds = []
    for t in addons_wanted:
        found = [a for a in cd.accepted_addons(ward, body) if t in addon_words(ward, a) and (era == "any" or cd.era_ok(cd.addon_era(ward, a), era))]
        if found:
            adds.append({"item": found[0]})
        else:
            miss.append({"kind": "addon", "body": body, "ask": ask_addon(t, era, body)})
    # hair and beard
    style, prob = choose_hair(cid, body, w.get("hair"), hair_idx)
    if prob:
        miss.append({"kind": "hair", "body": body, "ask": prob + ". Add a style to library/characters/aj/hair (index.json) or relax wants.hair"})
    role_text = " ".join(str(entry.get(k, "")) for k in ("role", "reads_as"))
    hc = hair_colour(cid, w["age"], w.get("hair"), role_text)
    fh = None
    if w.get("facial_hair") and str(w["facial_hair"]).lower() not in ("none", "no"):
        fpool = hair_pool(body, hair_idx, "facial")
        if not fpool:
            miss.append({"kind": "hair", "body": body, "ask": f"facial hair '{w['facial_hair']}' for {body}: the library only has beards and moustaches for Male Adult and Senior bodies; "
                                                              f"change wants.facial_hair or the body"})
        else:
            ww = set(words(w["facial_hair"]))
            sc = sorted(((-len(ww & set(words(s))), s) for s in fpool))
            fs = sc[0][1] if sc[0][0] < 0 else pick(fpool, cid, "beard")
            fh = {"style": fs, "color": hc}
    # palette: hints (names or hex, in the order top, bottom) > the signature colour > the base character's palette > a pleasant colour by CRC
    pal = {}
    if outfit:
        pc = cd.pieces(ward, outfit)
        order = [p["palette_slot"] for p in sorted(pc.values(), key=lambda p: (p["slot"] != "top", p["slot"], p["palette_slot"]))]
        hints = w.get("palette_hint")
        hints = list(hints.values()) if isinstance(hints, dict) else ([hints] if isinstance(hints, str) else list(hints or []))
        cols = [colour_hex(h) for h in hints]
        cols = [c for c in cols if c]
        if not cols and entry.get("color"):
            cols = [colour_hex(entry["color"])]
        base_pal = (reg.get("characters", {}).get(name0 or "", {}) or {}).get("palette") or {}
        for i, slot in enumerate(order):
            if i < len(cols):
                pal[slot] = cols[i]
            elif slot in base_pal and not cols:
                pal[slot] = base_pal[slot]
        if order and order[0] not in pal:
            pal[order[0]] = pick(PLEASANT, cid, "palette")
    if miss:
        return None, miss, notes
    face = pick(FACES[w["age"]], cid, "face")
    new = {"family": "aj", "body": body, "face": face, "hair": {"style": style, "color": hc} if style else None, "facial_hair": fh, "outfit": outfit,
           "addons": adds, "palette": pal, "era": sorted(set(cd.outfit_era(ward, outfit))) if outfit else [era], "height_m": None,
           "status": "draft", "approved": False, "adapted_for": cid,
           "licence_note": "hair from library/characters/aj/hair, used under the project owner's approved plan (registry licence 'unknown' pending confirmation)"}
    if w.get("skin"):
        new["skin"] = w["skin"]
    new["looks"] = looks_of(new, ward)
    return new, miss, notes


WHO = {("Male", "Kid"): "boy", ("Female", "Kid"): "girl", ("Male", "Teen"): "teenage boy", ("Female", "Teen"): "teenage girl",
       ("Male", "Adult"): "man", ("Female", "Adult"): "woman", ("Male", "Senior"): "elderly man", ("Female", "Senior"): "elderly woman"}


def looks_of(ch: dict, ward: dict) -> str:
    sex, age = ch["body"].split("_")
    parts = [WHO[(sex, age)]]
    if ch.get("hair"):
        parts.append(ch["hair"]["style"].split("_", 1)[1].replace("_", " ") + " hair")
    if ch.get("facial_hair"):
        parts.append(ch["facial_hair"]["style"].replace("facial_", "").replace("_", " "))
    parts.append(ch["outfit"] + (" with " + ", ".join(a["item"] for a in ch["addons"]) if ch.get("addons") else ""))
    if ch.get("palette"):
        parts.append("colours " + " / ".join(ch["palette"].values()))
    return ", ".join(parts)


def recipe_name(ch: dict) -> str:
    """A role-neutral look name for a character built here: body, hair, outfit (the same recipe always gets the same name)."""
    sex, age = ch["body"].split("_")
    base = {("Male", "Kid"): "Boy", ("Female", "Kid"): "Girl", ("Male", "Teen"): "TeenBoy", ("Female", "Teen"): "TeenGirl", ("Male", "Adult"): "Man",
            ("Female", "Adult"): "Woman", ("Male", "Senior"): "ElderMan", ("Female", "Senior"): "ElderWoman"}[(sex, age)]
    hair = "".join(p.capitalize() for p in ch["hair"]["style"].split("_")[1:]) if ch.get("hair") else "NoHair"
    outfit = "".join(p.capitalize() for p in ch["outfit"].split("_"))
    add = "".join(p.capitalize() for p in sorted(a["item"] for a in ch.get("addons") or []))
    return f"{base}{hair}{outfit}{add}"


def registered_twin(reg: dict, ch: dict) -> str | None:
    keys = ("body", "face", "hair", "facial_hair", "outfit", "addons", "palette", "skin")
    for n, c in sorted(reg["characters"].items()):
        if all(c.get(k) == ch.get(k) for k in keys if not (k == "skin" and not ch.get(k) and not c.get(k))):
            return n
    return None


# ----------------------------------------------------------------------------------------------- animations
def animations(clip: Path) -> dict:
    tool = ROOT / "tools" / "chars_aj" / "clips.py"
    if not tool.exists():
        return {"checked": False, "note": "tools/chars_aj/clips.py does not exist yet; Mixamo clips were not checked"}
    r = subprocess.run([sys.executable, str(tool), "--need", str(clip), "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        j = json.loads(r.stdout)
    except ValueError:
        return {"checked": False, "note": f"clips.py --need gave no JSON (exit {r.returncode})"}
    asks = {}
    for c in j.get("missing", []):
        a = subprocess.run([sys.executable, str(tool), "--ask", c], capture_output=True, text=True, encoding="utf-8", errors="replace")
        asks[c] = a.stdout.strip()
    return {"checked": True, "required": {k: sorted(v) for k, v in sorted(j.get("required", {}).items())}, "missing": sorted(j.get("missing", [])), "asks": asks}


# ----------------------------------------------------------------------------------------------- the run
def run(clip: Path, apply: bool = False) -> tuple[dict, int]:
    plan = json.loads((clip / "shotplan.json").read_text(encoding="utf-8"))
    script = json.loads((clip / "script.json").read_text(encoding="utf-8")) if (clip / "script.json").exists() else {}
    reg, ward, hair_idx = cd.cast(), cd.wardrobe(), cd.hair_index()
    era = (plan.get("world") or {}).get("era")
    results, new_chars = [], {}
    for entry in plan.get("cast", []):
        cid = entry.get("id", "?")
        w = effective_wants(entry, reg, era)
        name, ch, bare = cd.resolve(reg, entry.get("base") or "")
        res = {"id": cid, "base": entry.get("base"), "role": entry.get("role"), "wants": {k: v for k, v in sorted(w.items()) if v not in (None, [], "")}}
        ok, why = (False, [f"base '{entry.get('base')}' is not a registered character"])
        if ch is not None:
            ok, why = satisfies(ch, ward, w)
            if ok:
                errs = cd.check_costume(reg, ward, ch, entry.get("costume"), era, cid, name)
                if errs:
                    ok, why = False, errs
        if ok:
            res.update(status="EXISTING", character=name, reasons=["the base exists and satisfies what the story wants"], missing=[],
                       avoid=list(ch.get("avoid") or []))
        else:
            new, miss, notes = adapt(entry, w, reg, ward, hair_idx, name if ch is not None else None)
            res["reasons"] = list(why) + notes
            if miss:
                res.update(status="MISSING", missing=miss)
            else:
                twin = registered_twin(reg, new)
                nm = twin or recipe_name(new)
                if not twin:
                    n, k = nm, 2
                    while n in reg["characters"] or n in new_chars:
                        n, k = f"{nm}{k}", k + 1
                    nm = n
                    new_chars[nm] = new
                res.update(status="ADAPT", missing=[], character=nm, avoid=cd.avoid_union(ward, new["body"], new.get("outfit"), new.get("addons")), adapt={"name": nm, "registered": bool(twin), **{k: new[k] for k in sorted(new) if k not in ("licence_note",)}})
        results.append(res)
    anim = animations(clip)
    for c in anim.get("missing", []):
        results.append({"id": f"animation:{c}", "base": None, "role": None, "status": "MISSING", "reasons": [], "wants": {},
                        "missing": [{"kind": "animation", "ask": anim["asks"].get(c, f"the Mixamo clip {c}")}]})
    summary = {k: sum(1 for r in results if r["status"] == k) for k in ("EXISTING", "ADAPT", "MISSING")}
    out = {"clip": clip.name, "era": era, "title": script.get("title") or plan.get("logline"), "results": results, "animations": anim, "summary": summary,
           "exit": 2 if summary["MISSING"] else 0}
    applied = []
    if apply:
        applied = apply_casting(clip, plan, reg, new_chars, results)
    out["applied"] = applied
    return out, out["exit"]


def apply_casting(clip: Path, plan: dict, reg: dict, new_chars: dict, results: list[dict]) -> list[str]:
    cfg_path = ROOT / "config" / "cast.json"
    raw = cfg_path.read_text(encoding="utf-8")
    cfg = json.loads(raw)
    done = []
    for nm, ch in sorted(new_chars.items()):
        cfg["characters"][nm] = ch
        done.append(f"registered {nm} (draft)")
    if new_chars:
        eol = "\r\n" if "\r\n" in raw else "\n"
        cfg_path.write_bytes(json.dumps(cfg, indent=1, ensure_ascii=False).replace("\n", eol).encode("utf-8"))
    by_id = {r["id"]: r for r in results}
    changed = False
    for c in plan["cast"]:
        r = by_id.get(c.get("id"))
        if r and r["status"] == "ADAPT" and c.get("base") != r["character"]:
            done.append(f"plan cast '{c['id']}': base {c.get('base')} -> {r['character']}")
            c["base"] = r["character"]
            changed = True
    if changed:
        (clip / "shotplan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return done


def markdown(out: dict) -> str:
    L = [f"# Casting: {out['clip']}", "", f"Period: {out['era']}. " + ", ".join(f"{k} {v}" for k, v in out["summary"].items()), ""]
    for r in out["results"]:
        L.append(f"## {r['id']}: {r['status']}" + (f" ({r['character']})" if r.get("character") else ""))
        if r.get("role"):
            L.append(f"Role: {r['role']}. Base in the plan: {r['base']}.")
        if r.get("wants"):
            L.append("Wants: " + json.dumps(r["wants"], sort_keys=True))
        for t in r.get("reasons", []):
            L.append(f"- {t}")
        a = r.get("adapt")
        if a:
            L.append(f"- dress {a['body']} as {a['name']}{' (already registered)' if a['registered'] else ' (new draft)'}: face {a['face']}, outfit {a['outfit']}, "
                     f"add-ons {', '.join(x['item'] for x in a['addons']) or 'none'}, hair {json.dumps(a['hair'])}, facial hair {json.dumps(a['facial_hair'])}, "
                     f"palette {json.dumps(a['palette'], sort_keys=True)}")
        for t in r.get("avoid", []):
            L.append(f"- AVOID: {t}")
        for m in r.get("missing", []):
            L.append(f"- MISSING ({m['kind']}): {m['ask']}")
        L.append("")
    if out["animations"].get("checked") is False:
        L.append(f"Animations: {out['animations'].get('note')}")
    if out.get("applied"):
        L += ["Applied:"] + [f"- {x}" for x in out["applied"]]
    return "\n".join(L).rstrip() + "\n"


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    if not args:
        print(__doc__)
        return 1
    clip = Path(args[0])
    if not clip.is_absolute() and not clip.exists():
        clip = ROOT / "output" / "clips" / args[0]
    out, code = run(clip.resolve(), apply)
    (clip / "casting.json").write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    (clip / "casting.md").write_text(markdown(out), encoding="utf-8")
    for r in out["results"]:
        print(f"  {r['id']:<22} {r['status']:<9} {r.get('character') or ''}")
        for m in r.get("missing", []):
            print(f"      MISSING ({m['kind']}): {m['ask']}")
        for t in r.get("avoid", []):
            print(f"      avoid: {t}")
    for a in out.get("applied", []):
        print("  " + a)
    print(f"casting: {out['summary']} -> {clip / 'casting.json'}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
