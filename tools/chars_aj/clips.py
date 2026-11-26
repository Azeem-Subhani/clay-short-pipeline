"""clips.py - the Mixamo clip registry of the Aj cast: what is registered, what is on disk, what a clip needs.

    py -3 tools/chars_aj/clips.py --check                 # registry against the files: present, size, sha256, analysis
    py -3 tools/chars_aj/clips.py --register [names]      # run the Blender analysis and write config/mixamo_clips.json
    py -3 tools/chars_aj/clips.py --need output/clips/<slug>   # clips the clip's shots need; exit 2 if any is missing
    py -3 tools/chars_aj/clips.py --ask Standard_Walk     # the download request for one clip

Plain Python (standard library only). stagekit.aj_clips (inside Blender) loads this file for the registry and the asks,
and tools/blender/run_shot.py uses scan() to list every missing clip of a clip folder when a build stops on one.

Exit codes: 0 fine, 2 clips missing (--need, --check), 1 anything else.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(os.environ.get("SHORTS_PROJECT") or Path(__file__).resolve().parents[2])
REGISTRY = PROJECT / "config" / "mixamo_clips.json"
UPLOAD = "packs/aj_rebuild_v1/09_Animations/Aj_upload.fbx"
CLIP_DIR = "library/characters/aj/mixamo"

# what each named action (stagekit.actions) and each cycle of ActorAj.walk() plays on an Aj actor
CYCLES = {"walk": "Standard_Walk", "run": "Standard_Run", "sneak": "Sneak_Walk"}
EXIT_IDLE = "Standing_Idle"          # every locomotion eases out to its first pose


def load(path: Path = REGISTRY) -> dict:
    if not path.exists():
        return {"clips": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save(reg: dict, path: Path = REGISTRY):
    path.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8")


def clip_path(reg: dict, name: str) -> Path:
    c = reg["clips"].get(name, {})
    return PROJECT / reg.get("dir", CLIP_DIR) / c.get("file", f"{name}.fbx")


def ask(name: str, reg: dict | None = None) -> str:
    """The exact request for the owner: where to find the clip on Mixamo and how to download it."""
    reg = reg or load()
    c = reg["clips"].get(name)
    target = f"{reg.get('dir', CLIP_DIR)}/{(c or {}).get('file', name + '.fbx')}"
    if c is None:
        return (f"{name}: not in the registry (config/mixamo_clips.json). Pick a Mixamo animation for it, add an entry "
                f"(file, mixamo_title, search, in_place, loop, kind, owns, actions) and download it to {target} with the "
                f"settings below.\n" + settings(True))
    lines = [f"{name}: on mixamo.com search \"{c.get('search', c.get('mixamo_title', name))}\" and pick \"{c['mixamo_title']}\""
             + (f" ({c['note']})" if c.get("note") else "") + "."]
    lines.append(settings(c.get("in_place_option", c.get("in_place", False)), c.get("mirror", False)))
    lines.append(f"  Save it as {target}  (then run: py -3 tools/chars_aj/clips.py --register {name})")
    return "\n".join(lines)


def settings(in_place: bool, mirror: bool = False) -> str:
    s = (f"  Character: upload {UPLOAD} (Upload Character, once per account).\n"
         "  Download: Format FBX Binary (.fbx), Skin: Without Skin, Frames per Second: 30, Keyframe Reduction: none")
    s += ", In Place: ticked" if in_place else ", In Place: ticked when the option is offered"
    if mirror:
        s += ", Mirror: ticked on the animation panel"
    return s + "."


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def check(reg: dict | None = None) -> dict:
    """Every registry entry against its file: present, hash as registered, analysed. Returns a report dict."""
    reg = reg or load()
    out = {"ok": [], "missing": [], "changed": [], "unanalysed": [], "unregistered": []}
    for name, c in reg["clips"].items():
        p = clip_path(reg, name)
        if not p.exists():
            out["missing"].append(name)
            continue
        if c.get("sha256") and sha256(p) != c["sha256"]:
            out["changed"].append(name)
        elif not c.get("analysis"):
            out["unanalysed"].append(name)
        else:
            out["ok"].append(name)
    d = PROJECT / reg.get("dir", CLIP_DIR)
    if d.exists():
        known = {c.get("file", n + ".fbx").lower() for n, c in reg["clips"].items()}
        out["unregistered"] = sorted(p.name for p in d.glob("*.fbx") if p.name.lower() not in known)
    return out


# ------------------------------------------------------------------------------------------- what a clip folder needs
def by_action(reg: dict) -> dict:
    """action name -> the clips it plays on an Aj actor"""
    out = {}
    for name, c in reg["clips"].items():
        for a in c.get("actions", []):
            out.setdefault(a, []).append(name)
    return out


_DO = re.compile(r"""\.do\(\s*["']([a-z_]+)["']""")
_WALK = re.compile(r"""\.walk\(([^\n]*)""")          # the rest of the line: the goal tuple has its own brackets
_CYCLE = re.compile(r"""cycle\s*=\s*["']([a-z]+)["']""")
_PLAY = re.compile(r"""\.play_clip\(\s*["']([A-Za-z0-9_]+)["']""")


def scan(clip_dir: Path, reg: dict | None = None) -> dict:
    """The clips a clip folder's shots will play on Aj actors: from the plan's shot `do` lists and blender/sh*.py
    (.do("name", walk(..., cycle=...), play_clip("Name")). Returns {"required": {clip: [why]}, "missing": [clip]}."""
    reg = reg or load()
    acts = by_action(reg)
    need: dict[str, list] = {}

    def want(clip, why):
        need.setdefault(clip, [])
        if why not in need[clip]:
            need[clip].append(why)

    def action(name, why):
        for c in acts.get(name, []):
            want(c, why)
        if name in ("walk", "run", "sneak", "tiptoe", "pace", "step_forward", "chase", "slip_banana", "haul"):
            want(EXIT_IDLE, why)

    plan = clip_dir / "shotplan.json"
    if plan.exists():
        p = json.loads(plan.read_text(encoding="utf-8"))
        for s in p.get("shots", []):
            for d in s.get("do", []) or []:
                nm = d.get("action") if isinstance(d, dict) else (d.split()[0] if isinstance(d, str) and d else None)
                if nm:
                    action(nm, f"{s.get('id')}: plan do {nm}")
    bdir = clip_dir / "blender"
    for f in sorted(bdir.glob("sh*.py")) if bdir.exists() else []:
        src = f.read_text(encoding="utf-8", errors="replace")
        for m in _DO.finditer(src):
            action(m.group(1), f"{f.name}: .do(\"{m.group(1)}\")")
        for m in _WALK.finditer(src):
            cy = _CYCLE.search(m.group(1))
            c = CYCLES.get(cy.group(1) if cy else "walk", CYCLES["walk"])
            want(c, f"{f.name}: walk(cycle={cy.group(1) if cy else 'walk'})")
            want(EXIT_IDLE, f"{f.name}: walk")
        for m in _PLAY.finditer(src):
            want(m.group(1), f"{f.name}: play_clip(\"{m.group(1)}\")")
    missing = [c for c in need if c not in reg["clips"] or not clip_path(reg, c).exists()]
    return {"required": need, "missing": missing}


def missing_report(clip_dir: Path, first: str | None = None, first_ask: str | None = None, reg: dict | None = None) -> str:
    """The text of <clip>/MISSING_DOWNLOADS.md: every clip the folder needs that is not on disk, with its ask."""
    reg = reg or load()
    sc = scan(clip_dir, reg)
    names = list(dict.fromkeys(([first] if first else []) + sc["missing"]))
    lines = ["# Missing Mixamo downloads", "",
             f"The build of `{clip_dir.name}` stopped: these motion clips are needed and not in `{reg.get('dir', CLIP_DIR)}/`.",
             "Download each one as described, then run `py -3 tools/chars_aj/clips.py --register` and build again.", ""]
    for n in names:
        lines.append(f"## {n}")
        why = sc["required"].get(n)
        if why:
            lines.append("Needed by: " + "; ".join(why[:6]) + (" ..." if len(why) > 6 else ""))
        lines.append("")
        lines.append("```")
        lines.append(first_ask if (n == first and first_ask) else ask(n, reg))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------------- CLI
def _blender() -> list:
    sys.path.insert(0, str(PROJECT / "tools"))
    from common import blender_cmd                       # tools/common.py finds Blender: [exe, -b, ..., --python]
    return list(blender_cmd())


def _register_in_blender(names) -> int:
    """Inside Blender: import every clip once, check it, analyse it and write the registry."""
    sys.path.insert(0, str(PROJECT / "tools" / "blender"))
    from stagekit import aj_clips
    rep = aj_clips.register(names or None)
    bad = [n for n, r in rep.items() if r.get("problems")]
    for n, r in rep.items():
        print(f"CLIP {n}: {'OK' if not r.get('problems') else 'PROBLEMS: ' + '; '.join(r['problems'])}"
              f"  {r.get('summary', '')}", flush=True)
    print(f"REGISTER {len(rep) - len(bad)}/{len(rep)} clean -> {REGISTRY}", flush=True)
    return 1 if bad else 0


def main(argv=None) -> int:
    if argv is None and "--" in sys.argv and "bpy" in sys.modules:      # run by Blender (--register)
        argv = sys.argv[sys.argv.index("--") + 1:]
        if argv[:1] == ["--register-in-blender"]:
            return _register_in_blender(argv[1:])
    ap = argparse.ArgumentParser(prog="clips", description="the Mixamo clip registry of the Aj cast")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="registry against the files (present, sha256, analysed)")
    g.add_argument("--register", nargs="*", metavar="NAME", help="analyse the clips in Blender and update the registry (all when no names)")
    g.add_argument("--need", metavar="CLIP_DIR", help="clips the clip folder's shots need; exit 2 if any is missing")
    g.add_argument("--ask", metavar="NAME", help="print the download request for one clip")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)
    reg = load()
    if a.ask:
        print(ask(a.ask, reg))
        return 0
    if a.check:
        r = check(reg)
        if a.json:
            print(json.dumps(r, indent=1))
        else:
            print(f"{len(r['ok'])} clip(s) registered, on disk and analysed")
            for k in ("missing", "changed", "unanalysed", "unregistered"):
                if r[k]:
                    print(f"{k}: {', '.join(r[k])}")
            for n in r["missing"]:
                print()
                print(ask(n, reg))
        return 2 if r["missing"] else (1 if r["changed"] or r["unanalysed"] else 0)
    if a.need:
        d = Path(a.need).resolve()
        r = scan(d, reg)
        if a.json:
            print(json.dumps(r, indent=1))
        else:
            print(f"{d.name}: {len(r['required'])} clip(s) required")
            for c, why in r["required"].items():
                print(f"  {'MISSING ' if c in r['missing'] else 'ok      '}{c:24s} {why[0]}{' ...' if len(why) > 1 else ''}")
            for c in r["missing"]:
                print()
                print(ask(c, reg))
        return 2 if r["missing"] else 0
    cmd = _blender() + [str(Path(__file__).resolve()), "--", "--register-in-blender", *(a.register or [])]
    env = dict(os.environ, SHORTS_PROJECT=str(PROJECT))
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in r.stdout.splitlines():
        if line.startswith(("[clips]", "CLIP ", "REGISTER")):
            print(line)
    if r.returncode != 0 and not any(l.startswith("REGISTER") for l in r.stdout.splitlines()):
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
    return r.returncode


if __name__ == "__main__":
    code = main()
    if "bpy" in sys.modules:
        import bpy
        bpy.ops.wm.quit_blender() if code == 0 else sys.exit(code)
    sys.exit(code)
