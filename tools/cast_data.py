"""cast_data - what the cast, the wardrobe and the hair library say, and the rules that join them (standard library only).

One place for what plan.py (check_cast), cast_registry.py (check), casting.py and `clip.py cast` all need, so they cannot disagree:

  - a character is {family "aj", body, face, hair {style, color}, facial_hair, outfit, addons [{item, color?}], palette {slot: hex},
    skin, era, looks, height_m, status, approved}; a base may also be a bare body id ('Male_Teen' or 'Aj_Male_Teen')
  - it may wear an outfit or add-on only if its fit on that body is `pass` and review `accept` (rigid add-ons: review `none` is fine)
    in library/wardrobe/index.json, its licence is cc0, royalty_free or own, and it is allowed in the story's period
  - palette slots, piece names and hide patterns come from the outfit's `pieces` and the add-ons' entries
The stagekit side (stagekit/aj_wardrobe.py) applies the same rules when it builds the figure.
"""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENCES_OK = ("cc0", "royalty_free", "own")
SEXES = ("Male", "Female")
AGES = ("Kid", "Teen", "Adult", "Senior")
EXTRA_SLOTS = ("hair", "facial_hair", "skin")


def _read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def cast() -> dict:
    return _read(ROOT / "config" / "cast.json")


def wardrobe() -> dict:
    return _read(ROOT / "library" / "wardrobe" / "index.json")


def hair_index() -> dict:
    return _read(ROOT / "library" / "characters" / "aj" / "hair" / "index.json")


def era_ok(eras, era) -> bool:
    return "any" in eras or era in eras or (era == "fantasy" and bool({"medieval", "renaissance"} & set(eras)))


def canonical(reg: dict, name: str) -> str:
    """An old name ('TeenBoy') becomes the character that replaced it."""
    return (reg.get("aliases") or {}).get(name, name)


def body_id(name: str) -> str | None:
    n = name[3:] if name.startswith("Aj_") else name
    s, _, a = n.partition("_")
    return n if s in SEXES and a in AGES else None


def resolve(reg: dict, name: str) -> tuple[str, dict | None, str | None]:
    """(canonical name, character entry, bare body id): a registered character, or a body id, or neither."""
    c = canonical(reg, name)
    ch = (reg.get("characters") or {}).get(c)
    if ch:
        return c, ch, None
    b = body_id(name)
    if b and b in (reg.get("bodies") or {}):
        return name, None, b
    return name, None, None


def fit_ok(fit: dict | None, rigid: bool = False) -> bool:
    return bool(fit) and fit.get("status") == "pass" and (fit.get("review") == "accept" or (rigid and fit.get("review") == "none"))


def outfit_check(ward: dict, outfit: str, body: str) -> str | None:
    """None when `body` may wear `outfit`, else why not."""
    o = (ward.get("outfits") or {}).get(outfit)
    if o is None:
        return f"the wardrobe has no outfit '{outfit}' (it has {', '.join(ward.get('outfits', {}))})"
    f = (o.get("fits") or {}).get(body)
    if not fit_ok(f):
        have = [b for b, x in (o.get("fits") or {}).items() if fit_ok(x)]
        return (f"outfit '{outfit}' is not fit-accepted on {body} (fit {f and f.get('status')}, review {f and f.get('review')}); "
                f"accepted on: {', '.join(have) or 'no body'}")
    if o.get("licence") not in LICENCES_OK:
        return f"outfit '{outfit}' has licence '{o.get('licence')}' (allowed: {', '.join(LICENCES_OK)})"
    if not f.get("file"):
        return f"outfit '{outfit}' on {body} has no file in the registry"
    return None


def addon_check(ward: dict, item: str, body: str) -> str | None:
    a = (ward.get("addons") or {}).get(item)
    if a is None:
        return f"the wardrobe has no add-on '{item}' (it has {', '.join(ward.get('addons') or {}) or 'none yet'})"
    f = (a.get("fits") or {}).get(body)
    if not fit_ok(f, rigid=(a.get("kind") == "rigid")):
        return f"add-on '{item}' is not fit-accepted on {body} (fit {f and f.get('status')}, review {f and f.get('review')})"
    if a.get("licence") not in LICENCES_OK:
        return f"add-on '{item}' has licence '{a.get('licence')}' (allowed: {', '.join(LICENCES_OK)})"
    return None


def outfit_era(ward: dict, outfit: str) -> list[str]:
    return list(((ward.get("outfits") or {}).get(outfit) or {}).get("era", []))


def addon_era(ward: dict, item: str) -> list[str]:
    return list(((ward.get("addons") or {}).get(item) or {}).get("era", []))


def accepted_outfits(ward: dict, body: str) -> list[str]:
    return sorted(o for o in ward.get("outfits", {}) if outfit_check(ward, o, body) is None)


def accepted_addons(ward: dict, body: str) -> list[str]:
    return sorted(a for a in ward.get("addons", {}) or {} if addon_check(ward, a, body) is None)


SIT_ACTIONS = ("sit_down", "sit_idle")


def fit_avoid(ward: dict, kind: str, item: str, body: str) -> list[str]:
    """The reviewer's `avoid` limits recorded on one outfit or add-on fit (kind 'outfits' or 'addons')."""
    f = ((((ward.get(kind) or {}).get(item) or {}).get("fits") or {}).get(body)) or {}
    return list(f.get("avoid") or [])


def avoid_union(ward: dict, body: str, outfit: str | None, addons: list[dict]) -> list[str]:
    """What the reviewers say not to do with this body in this outfit and these add-ons, each limit once, in order."""
    out: list[str] = []
    lists = ([fit_avoid(ward, "outfits", outfit, body)] if outfit else []) + [fit_avoid(ward, "addons", a.get("item"), body) for a in addons or []]
    for lim in lists:
        out += [x for x in lim if x not in out]
    return out


def seat_limits(avoid: list[str] | None) -> list[str]:
    """The limits that say something about seating (the word 'seat' in the text, so 'seated' counts)."""
    return [x for x in (avoid or []) if "seat" in x.lower()]


def pieces(ward: dict, outfit: str) -> dict:
    """{role: {object, slot, palette_slot}} with role the garment's name without 'D_', lower case (hide patterns and recolor use it)."""
    out = {}
    for obj, p in ((ward.get("outfits") or {}).get(outfit) or {}).get("pieces", {}).items():
        out[(obj[2:] if obj.startswith("D_") else obj).lower()] = dict(p, object=obj)
    return out


def worn(ch: dict, costume: dict | None) -> tuple[str | None, list[dict]]:
    """(outfit, add-ons) of a character as the plan dresses it: the entry's own plus costume.wear."""
    adds = [dict(a) for a in (ch.get("addons") or [])]
    for w in (costume or {}).get("wear", []) or []:
        if not any(a["item"] == w.get("item") for a in adds):
            adds.append(dict(w))
    return ch.get("outfit"), adds


def palette_slots(ward: dict, outfit: str | None, addons: list[dict]) -> set[str]:
    s = set(EXTRA_SLOTS)
    if outfit:
        pc = pieces(ward, outfit)
        s |= {p["palette_slot"] for p in pc.values()} | set(pc)
    for a in addons:
        s.add(((ward.get("addons") or {}).get(a.get("item")) or {}).get("palette_slot", "accent"))
    return s


def hide_labels(ward: dict, ch: dict, costume: dict | None) -> dict[str, dict]:
    """label -> info for everything that can be hidden on this character as dressed: hair, facial_hair, '<outfit>.<piece>', '<piece>', 'addon:<item>'."""
    out = {}
    if ch.get("hair"):
        out["hair"] = {"kind": "hair"}
    if ch.get("facial_hair"):
        out["facial_hair"] = {"kind": "facial_hair"}
    outfit, adds = worn(ch, costume)
    if outfit:
        for role, p in pieces(ward, outfit).items():
            info = {"kind": "outfit", "role": role, "slot": p["slot"]}
            out[role] = info
            out[f"{outfit}.{role}"] = info
    for a in adds:
        out[f"addon:{a['item']}"] = {"kind": "addon", "item": a["item"]}
        out[a["item"]] = {"kind": "addon", "item": a["item"]}
    return out


def check_costume(reg: dict, ward: dict, ch: dict, costume: dict | None, era: str | None, who: str, base: str) -> list[str]:
    """Errors for one character's per-clip costume (and its own dressing) in a story of period `era`."""
    err = []
    costume = costume or {}
    body = ch.get("body")
    outfit, adds = worn(ch, costume)
    if outfit:
        why = outfit_check(ward, outfit, body)
        if why:
            err.append(f"cast '{who}': {base}: {why}")
        elif era and not era_ok(outfit_era(ward, outfit), era):
            err.append(f"cast '{who}': outfit '{outfit}' belongs to {outfit_era(ward, outfit)}, not to a {era} story")
    for a in adds:
        why = addon_check(ward, a.get("item"), body)
        if why:
            err.append(f"cast '{who}': {base}: {why}")
        elif era and not era_ok(addon_era(ward, a["item"]), era):
            err.append(f"cast '{who}': add-on '{a['item']}' belongs to {addon_era(ward, a['item'])}, not to a {era} story")
    slots = palette_slots(ward, outfit, adds)
    for k in (costume.get("recolor") or {}):
        if k not in slots:
            err.append(f"cast '{who}': {base} has no colour slot '{k}' (it has {', '.join(sorted(slots))})")
    labels = hide_labels(ward, ch, costume)
    hidden_roles, hidden_adds = set(), set()
    for pat in costume.get("hide", []) or []:
        hits = [l for l in labels if fnmatch.fnmatchcase(l, pat)]
        if not hits:
            err.append(f"cast '{who}': hide '{pat}' matches nothing on {base} (it has: {', '.join(sorted(labels)) or 'nothing to hide'})")
        for l in hits:
            info = labels[l]
            if info["kind"] == "outfit":
                hidden_roles.add(info["role"])
            elif info["kind"] == "addon":
                hidden_adds.add(info["item"])
    for role in sorted(hidden_roles):             # an outfit piece may only come off when another worn piece covers its slot
        slot = pieces(ward, outfit)[role]["slot"]
        covered = any(r != role and r not in hidden_roles and p["slot"] == slot for r, p in pieces(ward, outfit).items()) or any(
            a["item"] not in hidden_adds and slot in ((ward.get("addons") or {}).get(a["item"]) or {}).get("covers", []) for a in adds)
        if not covered:
            err.append(f"cast '{who}': hiding '{role}' would leave {base} bare at the '{slot}' slot: no other worn piece covers it")
    return err


def check_character(reg: dict, ward: dict, hair: dict, name: str, ch: dict) -> list[str]:
    """Problems in one config/cast.json character: body, face, hair, outfit, add-ons, palette, era, looks."""
    err = []
    eras = set(reg.get("eras", {})) | {"any"}
    if ch.get("family") != "aj":
        return [f"{name}: family '{ch.get('family')}' is not 'aj'"]
    body = ch.get("body")
    if body not in (reg.get("bodies") or {}):
        err.append(f"{name}: body '{body}' is not a registered body ({', '.join(reg.get('bodies', {}))})")
    for e in ch.get("era", []):
        if e not in eras:
            err.append(f"{name}: unknown era '{e}'")
    if not ch.get("era"):
        err.append(f"{name}: no era")
    if not ch.get("looks"):
        err.append(f"{name}: no 'looks' line")
    if ch.get("status") not in ("draft", "approved"):
        err.append(f"{name}: status must be 'draft' or 'approved' (got {ch.get('status')!r})")
    if ch.get("status") == "approved" and not ch.get("approved"):
        err.append(f"{name}: status 'approved' but `approved` is not true")
    if ch.get("face"):
        faces = ("Teen Classic", "Kid Round", "Kid Bright", "Teen Tapered", "Adult Broad", "Adult Sculpted", "Senior Strong", "Senior Soft")
        if ch["face"] not in faces:
            err.append(f"{name}: face '{ch['face']}' is not a face preset ({', '.join(faces)})")
    for key, kind in (("hair", "hair"), ("facial_hair", "facial")):
        h = ch.get(key)
        if h:
            if h.get("style") not in (hair.get(kind) or {}):
                err.append(f"{name}: {key} style '{h.get('style')}' is not in the hair library ({kind})")
            if not str(h.get("color", "")).startswith("#"):
                err.append(f"{name}: {key} needs a colour '#rrggbb'")
    if ch.get("outfit"):
        why = outfit_check(ward, ch["outfit"], body)
        if why:
            err.append(f"{name}: {why}")
        else:
            for e in ch.get("era", []):
                if e != "any" and not era_ok(outfit_era(ward, ch["outfit"]), e):
                    err.append(f"{name}: era '{e}' is not one the outfit '{ch['outfit']}' belongs to ({', '.join(outfit_era(ward, ch['outfit']))})")
    else:
        err.append(f"{name}: no outfit (a character is a dressed body; a bare body is a base id like 'Male_Teen')")
    for a in ch.get("addons") or []:
        why = addon_check(ward, a.get("item"), body)
        if why:
            err.append(f"{name}: {why}")
    slots = palette_slots(ward, ch.get("outfit"), ch.get("addons") or [])
    for k, v in (ch.get("palette") or {}).items():
        if k not in slots:
            err.append(f"{name}: palette slot '{k}' does not exist (slots: {', '.join(sorted(slots))})")
        if not str(v).startswith("#"):
            err.append(f"{name}: palette '{k}' needs '#rrggbb'")
    return err
