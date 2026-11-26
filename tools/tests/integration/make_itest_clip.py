"""Write two tiny test clips for the build-and-review tooling (no characters, no downloads, no ElevenLabs):

    py -3 tools/tests/integration/make_itest_clip.py

    output/_staging/itest_clip/       a clean shot (sh01): dolly, whip, orbit, long held view, with stand-in figures
    output/_staging/itest_clip_bad/   the same clip, but sh01 pushes the camera straight through a wall (campath must block it)

Each folder has shotplan.json, timing.json, state.json, blender/set_yard.py and blender/sh01.py, and is put in autonomous gate mode
(`clip.py gate <clip> --autonomous`), so the stills step is not held by the approvals of characters and sets that do not exist here.
The stand-in set and figures come from tools/tests/camera/world.py.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output" / "_staging"
FPS = 24

SET_PY = '''"""The yard of tools/tests/camera/world.py as this clip's set file (stand-in figures, no cast)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ.get("SHORTS_PROJECT") or Path(__file__).resolve().parents[4]) / "tools" / "tests" / "camera"))
import world  # noqa: E402


def build_set(shot):
    return world.build_world(shot)
'''

GOOD_SHOT = '''"""sh01: dolly on Ana, whip to Ben, orbit round Ben, cut to a wide that is held (and drifts) for the last 3 s."""
import set_yard
from stagekit import camera


def build_shot(shot):
    wd = set_yard.build_set(shot)
    A, B = wd["A"], wd["B"]
    cam = camera.Camera()
    cam.view("a", 0.0, on=[A], size="medium", side=10)
    cam.dolly(shot.t("hello"), 2.6, 0.2)
    cam.whip(3.0, cam.frame(B, "medium", side=-10), dur=0.35, vid="b")
    cam.orbit(3.7, 6.2, B.stage, deg=28)
    cam.view("c", 6.5, pos=(0, -10, 6.0), aim=(0, 3, 1.0), lens=26, size="wide")
'''

BAD_SHOT = '''"""sh01 with a deliberate fault: the camera is dollied straight through the stone wall at y=5."""
import set_yard
from stagekit import camera


def build_shot(shot):
    wd = set_yard.build_set(shot)
    cam = camera.Camera()
    cam.view("w", 0.0, pos=(2.4, 2.5, 1.5), aim=(2.4, 5.5, 1.5), lens=30, size="manual")
    cam.dolly(0.5, 2.5, 1.5)
    cam.view("c", 3.0, pos=(0, -10, 6.0), aim=(0, 3, 1.0), lens=26, size="wide")
'''


def make(folder: str, shot_py: str, seconds: float) -> Path:
    d = OUT / folder
    if d.exists():
        shutil.rmtree(d)
    (d / "blender").mkdir(parents=True)
    for sub in ("review", "render", "final", "audio"):
        (d / sub).mkdir()
    frames = round(seconds * FPS)
    words = "hello and welcome to the yard where nothing at all can go wrong today".split()
    step = (seconds - 0.6) / len(words)
    plan = {"world": {"era": "any", "place": "test yard"}, "cast": [], "sets": [{"id": "yard", "marks": {}}],
            "shots": [{"id": "sh01", "set": "yard", "est_seconds": seconds, "vo_text": " ".join(words),
                       "views": [{"id": "a"}, {"id": "b"}, {"id": "c"}] if shot_py is GOOD_SHOT else [{"id": "w"}, {"id": "c"}]}]}
    timing = {"fps": FPS, "total_seconds": seconds, "source": "test (hand-made, not a voice take)",
              "shots": {"sh01": {"seconds": seconds, "start_s": 0.0, "frames": frames, "start_frame": 0}},
              "words": [{"text": w, "start": round(0.1 + i * step, 3), "end": round(0.1 + (i + 0.85) * step, 3), "shot": "sh01"} for i, w in enumerate(words)]}
    (d / "shotplan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    (d / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")
    (d / "state.json").write_text(json.dumps({"slug": folder, "title": "integration test clip", "format": "twist", "idea": "test"}, indent=1), encoding="utf-8")
    (d / "blender" / "set_yard.py").write_text(SET_PY, encoding="utf-8")
    (d / "blender" / "sh01.py").write_text(shot_py, encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "tools" / "clip.py"), "gate", str(d), "--autonomous", "--reason", "integration test clip: no characters or sets to approve"],
                   check=True, capture_output=True)
    return d


if __name__ == "__main__":
    print(make("itest_clip", GOOD_SHOT, 9.5))
    print(make("itest_clip_bad", BAD_SHOT, 5.0))
