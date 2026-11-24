"""mkqueue.py - write job queues for jobrun.py (stdlib only).

    py -3 mkqueue.py build  <queue.jsonl> [--names A,B] [--out-dir work/out/v4/chars]
    py -3 mkqueue.py poses  <queue.jsonl> --pack <blend> --out <dir> --names A,B [--poses a,b] [--faces right,left]
"""
import argparse
import sys
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charpaths as P  # noqa: E402

W = P.TOOLS.parent
BL = P.BL
SCRIPTS = P.SCRIPTS


def all_names():
    """Character names the build script knows, read from its text and the costume files (no Blender needed)."""
    txt = (SCRIPTS / "build_character_library_v4.py").read_text(encoding="utf-8")
    names = re.findall(r'dict\(name="(\w+)"', txt) + re.findall(r'T_[AB]\(name="(\w+)"', txt)
    for f in sorted((SCRIPTS / "costumes_v4").glob("*.py")):
        names += re.findall(r'^\s*(?:T_[A-Z]\w*|NEW)\(name="(\w+)"', f.read_text(encoding="utf-8"), re.M)
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def plugin_of(name):
    """["--plugins", file] if a plug-in costume file defines the character (so one broken plug-in cannot stop the others)"""
    for f in sorted((SCRIPTS / "costumes_v4").glob("*.py")):
        if f.name not in ("modern_a.py", "modern_b.py", "fantasy_a.py", "fantasy_b.py") and f'name="{name}"' in f.read_text(encoding="utf-8"):
            return ["--plugins", f.name]
    return ["--plugins", "none"]


def blender(script, *args, threads=2):
    return [BL, "-b", "--factory-startup", "--threads", str(threads), "--python", str(script), "--", *[str(x) for x in args]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("build", "poses", "verify"))
    ap.add_argument("queue")
    ap.add_argument("--names", default=None)
    ap.add_argument("--out-dir", default=str(P.CHARS))
    ap.add_argument("--pack", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--poses", default=None)
    ap.add_argument("--faces", default="right,left")
    a = ap.parse_args()
    names = a.names.split(",") if a.names else all_names()
    jobs = []
    if a.what == "build":
        for n in names:
            out = Path(a.out_dir) / f"{n}.blend"
            jobs.append({"id": f"build:{n}", "kind": "build", "outputs": [str(out)], "min_bytes": 20000, "cwd": str(SCRIPTS),
                         "fail_if": ["Traceback (most recent call last)", "Error in PyDriver"],
                         "cmd": blender(SCRIPTS / "build_character_library_v4.py", "--names", n, "--out", out, "--overwrite", *plugin_of(n))})
    elif a.what == "verify":
        vdir = P.OUT / "verify"
        for n in names:
            blend = Path(a.out_dir) / f"{n}.blend"
            jobs.append({"id": f"verify:{n}", "kind": "verify", "outputs": [str(vdir / f"{n}.json")], "min_bytes": 50,
                         "fail_if": ["Traceback (most recent call last)", "FAIL " + n],
                         "cmd": [BL, "-b", "--threads", "2", str(blend), "--python", str(SCRIPTS / "verify_character_library_v4.py"), "--",
                                 "--names", n, "--json", str(vdir / f"{n}.json")]})
    elif a.what == "poses":
        for n in names:
            args = ["--pipeline", str(P.PIPELINE), "--char", n, "--pack", a.pack, "--out", a.out, "--faces", a.faces]
            if a.poses:
                args += ["--poses", a.poses]
            jobs.append({"id": f"poses:{n}", "kind": "strip", "outputs": [], "fail_if": ["Traceback (most recent call last)"],
                         "cmd": blender(P.TOOLS / "bl" / "pose_sheet.py", *args)})
    Path(a.queue).parent.mkdir(parents=True, exist_ok=True)
    Path(a.queue).write_text("\n".join(json.dumps(j) for j in jobs) + "\n", encoding="utf-8")
    print(f"{len(jobs)} jobs -> {a.queue}")


if __name__ == "__main__":
    main()
