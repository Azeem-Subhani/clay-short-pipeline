"""apply_generated.py - put the generated hair and beards of config/cast3d_generated.json into config/cast3d.json.

    python tools/chars3d/apply_generated.py            # write the sheets
    python tools/chars3d/apply_generated.py --check    # only say what would change
    python tools/chars3d/apply_generated.py --clear    # take every generated hair and beard out again (sculpted hair comes back)

For each listed character: "hair": "<model>" becomes the sheet's "hair": {"model": ..., "color": <the character's drawn hair
colour, or "color" from the file>}; "beard": "<model>" becomes "beard": {"model": ...} (the builder takes the drawn beard's
colour). A model that is not in library/hair/index.json is an error. convert_pack.py reads the same file, so a rebuild
of the cast from the pack keeps the assignments.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def assignments(root=ROOT):
    return json.loads((root / "config" / "cast3d_generated.json").read_text(encoding="utf-8"))["characters"]


def drawn_hair_color(sheet):
    for p in sheet.get("parts", []):
        if str(p.get("name", "")).lower().startswith("hair") and p.get("color"):
            return p["color"]
    return "#6B4428"


def entries(name, sheet, a):
    """The sheet's "hair" and "beard" entries for one assignment (None = leave that one alone)."""
    hair = {"model": a["hair"], "color": a.get("color") or drawn_hair_color(sheet)} if a.get("hair") else None
    beard = {"model": a["beard"]} if a.get("beard") else None
    return hair, beard


def main(argv):
    check, clear = "--check" in argv, "--clear" in argv
    lib = json.loads((ROOT / "library" / "hair" / "index.json").read_text(encoding="utf-8"))
    f = ROOT / "config" / "cast3d.json"
    cast = json.loads(f.read_text(encoding="utf-8"))
    changed = []
    for name, a in assignments().items():
        sheet = cast["characters"].get(name)
        if sheet is None:
            raise SystemExit(f"cast3d_generated.json: no character '{name}' in cast3d.json")
        if a.get("hair") and a["hair"] not in lib.get("hair", {}):
            raise SystemExit(f"{name}: hair model '{a['hair']}' is not in library/hair/index.json")
        if a.get("beard") and a["beard"] not in lib.get("facial", {}):
            raise SystemExit(f"{name}: beard model '{a['beard']}' is not in library/hair/index.json")
        hair, beard = entries(name, sheet, a)
        for key, new in (("hair", hair), ("beard", beard)):
            if new is None:
                continue
            old = sheet.get(key)
            if clear:
                if isinstance(old, dict) and old.get("model"):
                    del sheet[key]
                    changed.append(f"{name}: {key} model removed")
            elif old != new:
                sheet[key] = new
                changed.append(f"{name}: {key} -> {new['model']}")
    print("\n".join(changed) or "nothing to change")
    if changed and not check:
        f.write_text(json.dumps(cast, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
        print(f"wrote {f} ({len(changed)} changes)")


if __name__ == "__main__":
    main(sys.argv[1:])
