"""End to end: stills (levels, campath section, motion strips, exit code 3 on blocking issues) and preview (MP4 + path diagram, Gate C ready
only when nothing blocks) on two small clips made by make_itest_clip.py. Needs Blender; takes about two minutes.

    py -3 tools/tests/integration/test_camera_review.py
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import make_itest_clip  # noqa: E402

CLIP = [sys.executable, str(ROOT / "tools" / "clip.py")]


def run(*args) -> int:
    return subprocess.run([*CLIP, *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace").returncode


def gate_c(clip: Path) -> str:
    out = subprocess.run([*CLIP, "gate", str(clip), "C", "--json"], capture_output=True, text=True, encoding="utf-8").stdout
    return json.loads(out)["gates"]["C"]["status"]


def check(cond, what):
    print(("ok    " if cond else "FAIL  ") + what)
    if not cond:
        check.failed += 1


check.failed = 0

good = make_itest_clip.make("itest_clip", make_itest_clip.GOOD_SHOT, 9.5)
bad = make_itest_clip.make("itest_clip_bad", make_itest_clip.BAD_SHOT, 5.0)

check(gate_c(good) == "pending", "gate C starts pending")
check(run("stills", good) == 0, "stills on the clean shot exit 0")
rep = json.loads((good / "review" / "sh01" / "checks.json").read_text(encoding="utf-8"))
check(rep["blocking"] == 0 and "items" in rep and "campath" in rep and rep["motion"], "checks.json has blocking/warnings, items, campath and motion")
check((good / "review" / "sh01" / "campath.json").exists(), "campath.json written")
check(all((good / "review" / "sh01" / m["file"]).exists() for m in rep["motion"]), "every listed motion strip exists")
check(run("preview", good) == 0, "preview on the clean shot exits 0")
check((good / "review" / "sh01" / "camera" / "preview.mp4").exists() and (good / "review" / "sh01" / "camera" / "path.png").exists(), "preview.mp4 and path.png written")
check(gate_c(good) == "ready", "gate C is ready after a clean preview")

check(run("stills", bad) == 3, "stills on the faulty shot exit 3")
rep = json.loads((bad / "review" / "sh01" / "checks.json").read_text(encoding="utf-8"))
check(rep["blocking"] > 0 and any(i["code"] == "camera_through_geometry" and i["level"] == "block" for i in rep["items"]), "the wall is a blocking camera_through_geometry item")
check(run("stills", bad, "--allow-blocking") == 0, "--allow-blocking exits 0")
check(run("preview", bad) != 0, "preview on the faulty shot exits non-zero")
check(gate_c(bad) == "pending", "gate C is not marked ready for the faulty shot")

print("FAILED" if check.failed else "all ok")
sys.exit(1 if check.failed else 0)
