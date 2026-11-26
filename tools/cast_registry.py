"""cast_registry.py - put character notes into config/cast.json and check the registry (stdlib only).

    python tools/cast_registry.py merge <fragment.json> [<fragment.json> ...]     # one file per batch of new characters
    python tools/cast_registry.py check                                           # every character against bodies, hair, wardrobe, eras

A fragment is {"Name": {family "aj", body, face, hair {style, color}, facial_hair {style, color} | null, outfit, addons [{item, color?}],
palette {slot: "#hex"}, skin, era [...], looks, height_m, status "draft"|"approved", approved, licence_note, ...}}. A new character starts
as {"family": "aj", "status": "draft", "approved": false} plus what the fragment says; fields not mentioned stay as they were.

`check` validates every character (tools/cast_data.py): its body is registered and measured, the face preset exists, hair and beard styles
are in library/characters/aj/hair, the outfit and every add-on are fit `pass` + `accept` on that body (registry library/wardrobe/index.json),
licences are cc0 | royalty_free | own, palette slots exist, eras are known and belong to the outfit, `looks` is written. Aliases (old names)
must point at a character. Exit 1 on any problem.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cast_data  # noqa: E402

CFG = ROOT / "config" / "cast.json"
ERAS = {"ancient", "medieval", "renaissance", "age_of_sail", "victorian", "modern", "east_asia_feudal", "fantasy", "any"}


def _write(cfg: dict, raw: str):
    eol = "\r\n" if "\r\n" in raw else "\n"
    CFG.write_bytes(json.dumps(cfg, indent=1, ensure_ascii=False).replace("\n", eol).encode("utf-8"))


def merge(paths):
    raw = CFG.read_text(encoding="utf-8")
    cfg = json.loads(raw)
    chars = cfg["characters"]
    n = 0
    for p in paths:
        frag = json.loads(Path(p).read_text(encoding="utf-8"))
        for name, e in frag.items():
            if not isinstance(e, dict) or name.startswith("_"):
                continue
            cur = chars.setdefault(name, {"family": "aj", "status": "draft", "approved": False})
            for k, v in e.items():
                cur[k] = v
            n += 1
    _write(cfg, raw)
    print(f"merged {n} character entries into {CFG}")
    return check()


def check():
    reg = cast_data.cast()
    ward, hair = cast_data.wardrobe(), cast_data.hair_index()
    chars = reg["characters"]
    problems = []
    for name, e in chars.items():
        problems += cast_data.check_character(reg, ward, hair, name, e)
    for b, rec in (reg.get("bodies") or {}).items():
        if not (ROOT / rec.get("measured", f"library/characters/aj/bodies/{b}.json")).exists():
            problems.append(f"body {b}: measured file missing (py -3 tools/chars_aj/measure_bodies.py)")
    for old, new in (reg.get("aliases") or {}).items():
        if new not in chars:
            problems.append(f"alias '{old}' points at '{new}', which is not a character")
        if old in chars:
            problems.append(f"alias '{old}' is also a character name")
    for p in problems:
        print("  " + p)
    draft = sum(1 for e in chars.values() if e.get("status") != "approved")
    print(f"registry check: {len(chars)} characters ({draft} draft), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "merge":
        sys.exit(merge(sys.argv[2:]))
    if len(sys.argv) == 2 and sys.argv[1] == "check":
        sys.exit(check())
    print(__doc__)
    sys.exit(2)
