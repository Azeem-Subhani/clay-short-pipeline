"""cast_registry.py - put hand-written character notes into config/cast.json (stdlib only).

    python tools/cast_registry.py merge <fragment.json> [<fragment.json> ...]     # one file per batch of new characters
    python tools/cast_registry.py check                                           # eras valid, stand-ins and props exist

A fragment is {"Name": {"looks": ..., "era": [...], "group": ..., "stand_in": [...], "adapt": "text", "props": [...],
"body": {...}, "sheet": ..., "decisions": ...}}. Run `python tools/clip.py cast --rescan` afterwards: it fills in parts,
colours, height and headwear from the pack file and keeps everything written here.
`adapt` given as plain text is stored as `adapt_note` (the `adapt` field of the registry is the per-era costume recipe dict).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "cast.json"
ERAS = {"ancient", "medieval", "renaissance", "age_of_sail", "victorian", "modern", "east_asia_feudal", "fantasy", "any"}


def merge(paths):
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    chars = cfg["characters"]
    n = 0
    for p in paths:
        frag = json.loads(Path(p).read_text(encoding="utf-8"))
        for name, e in frag.items():
            if not isinstance(e, dict) or name.startswith("_"):
                continue
            cur = chars.setdefault(name, {"looks": "", "era": ["any"], "group": "", "height_m": 1.6, "robe": False, "colors": [],
                                          "headwear_parts": [], "parts": [], "adapt": {}})
            for k, v in e.items():
                if k == "adapt" and isinstance(v, str):
                    cur["adapt_note"] = v
                else:
                    cur[k] = v
            n += 1
    CFG.write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"merged {n} character entries into {CFG}")
    return check()


def check():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    chars = cfg["characters"]
    idx = ROOT / "library" / "assets" / "index.json"
    assets = {a["id"] for a in json.loads(idx.read_text(encoding="utf-8")).get("assets", [])} if idx.exists() else set()
    bad = 0
    for name, e in chars.items():
        for era in e.get("era", []):
            if era not in ERAS:
                print(f"  {name}: unknown era '{era}'")
                bad += 1
        if not e.get("looks") or e["looks"].startswith("NEW in this pack"):
            print(f"  {name}: no 'looks' line yet")
            bad += 1
        for s in e.get("stand_in", []):
            if s not in chars:
                print(f"  {name}: stand_in '{s}' is not a character")
                bad += 1
        for pid in e.get("props", []):
            if assets and pid not in assets:
                print(f"  {name}: prop '{pid}' is not in library/assets/index.json")
                bad += 1
    print(f"registry check: {len(chars)} characters, {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "merge":
        sys.exit(merge(sys.argv[2:]))
    if len(sys.argv) == 2 and sys.argv[1] == "check":
        sys.exit(check())
    print(__doc__)
    sys.exit(2)
