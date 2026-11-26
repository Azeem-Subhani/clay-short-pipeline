"""Write the clips that prove the format 2 plan, the set agreement and `clip.py setpreview` (no characters, no downloads, no ElevenLabs):

    py -3 tools/tests/integration/make_plan_clip.py

    output/_staging/itest_plan/            the good clip: plan_new_format.json (an office and a shop), both set files, three shots, timing, autonomous gates
    output/_staging/itest_plan_nomark/     the same, but blender/set_office.py lacks the mark 'kitchen' that the plan names
    output/_staging/itest_plan_bare/       the same, but blender/set_office.py is stripped to a floor and a desk
    output/_staging/itest_plan_bad1..5/    only shotplan.json + script.json, each with one deliberate plan fault (for `clip.py plan-check`)

The set files: examples/sets/set_office.py (copied, with the THEME line the agreement check reads) and tools/tests/fixtures/plan_clip/blender/set_shop.py.
The shot scripts stage no characters: they only place the camera, which is all the set audit and the camera checks need.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from common import FPS, words_of  # noqa: E402

OUT = ROOT / "output" / "_staging"
FIX = ROOT / "tools" / "tests" / "fixtures"
PY = sys.executable

SH01 = '''"""sh01 (stand-in): the camera moves of the plan on the office, no characters. A real shot follows the plan's move for every view."""
import set_office
from stagekit import camera


def build_shot(shot):
    S = set_office.build_set("office_day")
    a = S["mark"]["worker_a"]
    t_busy, t_note, t_says = shot.t("in a busy open office"), shot.t("Today a tiny note"), shot.t("It says")
    cam = camera.Camera()
    cam.view("sam_stares", 0.0, pos=(a[0] - 0.5, a[1] - 1.7, 1.3), aim=(a[0], a[1] + 0.4, 1.15), lens=45, size="medium")
    cam.dolly(0.0, t_busy, 0.1)
    w = set_office.WIDE
    cam.view("busy_office", t_busy, pos=w[0], aim=w[1], lens=w[2], size="wide")
    cam.crane(t_busy, t_note, rise=0.4)
    cam.view("tiny_note", t_note, pos=(a[0] + 0.2, a[1] - 1.1, 1.2), aim=(a[0], a[1] + 0.2, 1.05), lens=55, size="insert")
    cam.handheld(t_note, t_says)
    cam.view("go_to_shop", t_says, pos=(a[0] - 0.4, a[1] - 1.9, 1.3), aim=(a[0], a[1] + 0.4, 1.2), lens=60, size="close", still=True)
'''
SH02 = '''"""sh02 (stand-in): the shop wide, a truck along the counter, an orbit over it."""
import set_shop
from stagekit import camera


def build_shot(shot):
    S = set_shop.build_set("interior_day")
    c = S["mark"]["counter"]
    t_slide, t_key = shot.t("She slides a small box"), shot.t("Inside a key marked")
    cam = camera.Camera()
    w = set_shop.WIDE
    cam.view("shop_wide", 0.0, pos=w[0], aim=w[1], lens=w[2], size="wide")
    cam.view("box_slides", t_slide, pos=(c[0] - 2.0, c[1] - 2.4, 1.4), aim=(c[0], c[1], 1.05), lens=40, size="medium")
    cam.truck(t_slide, t_key, right=0.3)
    cam.view("key_inside", t_key, pos=(c[0] - 0.2, c[1] - 0.9, 2.2), aim=(c[0], c[1], 1.0), lens=60, size="insert")
    cam.orbit(t_key, shot.seconds - 0.3, (c[0], c[1], 1.0), deg=25)
'''
SH03 = '''"""sh03 (stand-in): the office at night: a pan across the wide, a low tilt at the desk, a push to the screen."""
import set_office
from stagekit import camera


def build_shot(shot):
    S = set_office.build_set("office_night")
    a = S["mark"]["worker_a"]
    t_key, t_screen = shot.t("Sam turns the key"), shot.t("and the screen finally")
    cam = camera.Camera()
    w = set_office.WIDE
    cam.view("empty_office", 0.0, pos=w[0], aim=w[1], lens=w[2], size="wide")
    cam.pan(0.0, t_key, 18)
    cam.view("key_turns", t_key, pos=(a[0] + 0.9, a[1] - 1.5, 0.8), aim=(a[0], a[1], 0.6), lens=45, size="close")
    cam.tilt(t_key, t_screen, 8)
    cam.view("screen_lights", t_screen, pos=(a[0] - 0.4, a[1] - 1.9, 1.3), aim=(a[0], a[1] + 0.4, 1.2), lens=50, size="medium")
    cam.dolly(t_screen, shot.seconds - 0.3, 0.08)
'''
BARE_OFFICE = '''"""A set stripped to a floor and one desk: the same file contract (MARK, THEME, LIGHT, WIDE) as set_office.py, nothing else."""
from stagekit import build, furnish, lights

THEME = "office_open_plan"
MARK = {"worker_a": (-5.0, -2.55, 0.0), "worker_b": (-1.6, 0.25, 0.0), "kitchen": (6.6, -2.6, 0.0), "visitor": (-4.7, -4.45, 0.0), "manager": (5.2, 2.2, 0.0), "glass_door": (3.4, -0.3, 0.0)}
WIDE = ((-7.5, -5.2, 2.15), (2.2, 2.3, 0.15), 16.0)
LIGHT = {"office_day": {}, "office_night": {}}


def build_set(time: str = "office_day"):
    build.box("floor", size=(16, 11, 0.2), at=(0, 0, -0.1), surface="carpet_grey")
    furnish.make("desk_office", at=(-5.0, -2.0, 0.0), rot_z=0)
    lights.rig(time, look=False)
    return {"mark": MARK, "time": time, "wide": WIDE}
'''


def load_plan():
    return json.loads((FIX / "plan_new_format.json").read_text(encoding="utf-8")), json.loads((FIX / "plan_new_format_script.json").read_text(encoding="utf-8"))


def timing_for(plan: dict) -> dict:
    """A hand-made time base (not a voice take): even word spacing, a short pause after each shot."""
    wps = 177 / 60
    t, f0, shots, words = 0.0, 0, {}, []
    for s in plan["shots"]:
        ws = words_of(s["vo_text"])
        secs = round(len(ws) / wps + 0.8, 2)
        frames = round(secs * FPS)
        shots[s["id"]] = {"seconds": secs, "start_s": round(t, 3), "frames": frames, "start_frame": f0}
        step = (secs - 0.8) / max(1, len(ws))
        words += [{"text": w, "start": round(t + 0.1 + i * step, 3), "end": round(t + 0.1 + (i + 0.85) * step, 3), "shot": s["id"]} for i, w in enumerate(ws)]
        t += secs
        f0 += frames
    return {"fps": FPS, "total_seconds": round(t, 2), "source": "test (hand-made, not a voice take)", "shots": shots, "words": words}


def write_clip(folder: str, plan: dict, script: dict, full: bool = True, office_py: str | None = None) -> Path:
    d = OUT / folder
    if d.exists():
        shutil.rmtree(d)
    (d / "blender").mkdir(parents=True)
    plan = copy.deepcopy(plan)
    plan["clip"] = folder
    (d / "shotplan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    (d / "script.json").write_text(json.dumps(script, indent=1, ensure_ascii=False), encoding="utf-8")
    if not full:
        return d
    for sub in ("review", "render", "final", "audio"):
        (d / sub).mkdir()
    (d / "state.json").write_text(json.dumps({"slug": folder, "title": plan["title"], "format": plan["format"], "idea": "format 2 plan test"}, indent=1), encoding="utf-8")
    (d / "timing.json").write_text(json.dumps(timing_for(plan), indent=1), encoding="utf-8")
    office = (ROOT / "examples" / "sets" / "set_office.py").read_text(encoding="utf-8")
    office = office.replace('SIZE = (16.0, 11.0, 2.8)', 'THEME = "office_open_plan"\nSIZE = (16.0, 11.0, 2.8)', 1)
    (d / "blender" / "set_office.py").write_text(office_py if office_py is not None else office, encoding="utf-8")
    shutil.copy(FIX / "plan_clip" / "blender" / "set_shop.py", d / "blender" / "set_shop.py")
    for name, src in (("sh01", SH01), ("sh02", SH02), ("sh03", SH03)):
        (d / "blender" / f"{name}.py").write_text(src, encoding="utf-8")
    subprocess.run([PY, str(ROOT / "tools" / "clip.py"), "gate", str(d), "--autonomous", "--reason", "integration test clip: no characters to approve; gate B is exercised by setpreview"], check=True, capture_output=True)
    return d


def bad_variants(plan: dict) -> dict:
    def sh(p, i):
        return p["shots"][i]

    out = {}
    p = copy.deepcopy(plan)
    del p["sets"][0]["architecture"]
    out["bad1"] = p                                                                   # a set with no architecture
    p = copy.deepcopy(plan)
    p["sets"][1]["layers"]["foreground"] = []
    p["sets"][1]["layers"]["beyond"] = []
    out["bad2"] = p                                                                   # empty depth layers
    p = copy.deepcopy(plan)
    sh(p, 0)["views"][0]["move"] = {"type": "static"}
    out["bad3"] = p                                                                   # a long static view with no reason
    p = copy.deepcopy(plan)
    p["sets"][1]["must_survive"].append("reverse")
    sh(p, 1)["views"][1]["side"] = "reverse"
    out["bad4"] = p                                                                   # the camera crosses the line of action
    p = copy.deepcopy(plan)
    sh(p, 0)["views"][2]["move"] = {"type": "whip"}
    sh(p, 0)["views"][3]["enter"] = "whip"
    del p["sets"][0]["architecture"]["walls"][0]["openings"][0]["vista"]
    out["bad5"] = p                                                                   # a whip with no target, and a window with nothing behind it
    return out


def main():
    plan, script = load_plan()
    made = [write_clip("itest_plan", plan, script)]
    office = (made[0] / "blender" / "set_office.py").read_text(encoding="utf-8")
    nomark = office.replace('    "kitchen": (6.6, -2.6, 0.0),           # at the kitchenette counter\n', "", 1)
    assert nomark != office, "the kitchen mark line was not found in set_office.py"
    made.append(write_clip("itest_plan_nomark", plan, script, office_py=nomark))
    made.append(write_clip("itest_plan_bare", plan, script, office_py=BARE_OFFICE))
    for k, p in bad_variants(plan).items():
        made.append(write_clip(f"itest_plan_{k}", p, script, full=False))
    for d in made:
        print(d)


if __name__ == "__main__":
    main()
