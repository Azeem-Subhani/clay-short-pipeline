"""The measured look checks (stagekit/review.py): face shape, face exposure, colour lean, tonal range, on synthetic pictures and, when they
exist on disk, on the study's renders (output/experiments/look_phase2|3/renders).

Run inside Blender (numpy and bpy live there):
    blender -b --factory-startup --python tools/tests/look/test_look_checks.py
Exit code 0 = all passed. The calibration pictures are skipped (and said so) when the experiment folder is not there.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.path.insert(0, str(ROOT / "tools"))
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402

from stagekit import review  # noqa: E402

FAILS, SKIPPED = [], []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def codes(v):
    return {(lvl, code) for lvl, code, _ in v}


def face_image(kind):
    """A 300x300 skin-toned picture with a face-sized disc: 'flat' (same brightness all over), 'modelled' (bright on the left, a deep shadow
    side on the right), 'washed' (flat and near white), 'dark'."""
    h = w = 300
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.zeros((h, w, 3), np.float32) + 0.2
    if kind == "modelled":
        t = np.clip((xx - 60) / 180.0, 0, 1)                  # 0 at the left cheek, 1 at the right
        lum = 0.82 - 0.55 * t
    elif kind == "flat":
        lum = np.full((h, w), 0.5, np.float32)
    elif kind == "washed":
        lum = np.full((h, w), 0.86, np.float32)
    else:
        lum = np.full((h, w), 0.10, np.float32)
    skin = np.stack([lum * 1.0, lum * 0.78, lum * 0.66], -1)
    base[:] = skin
    return base


def test_synthetic():
    rect = review.face_core(150, 150, 280, 280)
    flat = review.face_shape(face_image("flat"), rect)
    mod = review.face_shape(face_image("modelled"), rect)
    check("flat face measures near 1.0", flat["ok"] and flat["ratio"] > 0.95, str(flat.get("ratio")))
    check("modelled face has a clear shadow side", mod["ok"] and mod["ratio"] < 0.7, str(mod.get("ratio")))
    small = review.face_shape(face_image("flat"), review.face_core(150, 150, 60, 60))
    check("a small face is skipped and says why", (not small["ok"]) and "small" in small["why"], str(small))
    off = review.face_shape(face_image("flat"), review.face_core(-200, 150, 280, 280))
    check("a face outside the picture is skipped", not off["ok"])
    # a face lit from the bottom is measured like one lit from the side (gradient direction, not left/right)
    rot = np.ascontiguousarray(np.rot90(face_image("modelled")))
    r2 = review.face_shape(rot, rect)
    check("the shadow side is found along any direction", r2["ok"] and r2["ratio"] < 0.75, f"{r2.get('ratio')}")

    # verdicts
    def st(u=128, v=128, y10=50, y90=190):
        return {"y": 110, "y10": y10, "y90": y90, "u": u, "v": v}
    ok_face = {"ok": True, "name": "A", "mean": 0.5, "p90": 0.75, "ratio": 0.6}
    check("a healthy frame has no finding", codes(review.look_verdicts(st(), [ok_face])) == set())
    v = codes(review.look_verdicts(st(), [{"ok": True, "name": "A", "mean": 0.75, "p90": 0.95, "ratio": 0.97}]))
    check("flat and washed face blocks", ("block", "face_flat") in v and ("warn", "face_washed") in v, str(v))
    v = codes(review.look_verdicts(st(), [{"ok": True, "name": "A", "mean": 0.5, "p90": 0.75, "ratio": 0.95}]))
    check("flat but not washed face only warns", v == {("warn", "face_flat")}, str(v))
    v = codes(review.look_verdicts(st(), [{"ok": True, "name": "A", "mean": 0.1, "p90": 0.2, "ratio": 0.6}]))
    check("a face lost in darkness warns", ("warn", "face_dark") in v, str(v))
    v = codes(review.look_verdicts(st(), [ok_face, {"ok": True, "name": "B", "mean": 0.2, "p90": 0.3, "ratio": 0.6}]))
    check("another face under 60% of the hero warns", ("warn", "face_dim") in v, str(v))
    v = review.look_verdicts(st(), [{"ok": False, "name": "A", "why": "turned away"}])
    check("no measurable face is a note, not a finding", [x[0] for x in v] == ["info"], str(v))
    # colour lean
    v = codes(review.look_verdicts(st(u=133, v=122), [], "neutral"))
    check("a blue-leaning frame (U133 V122) is a finding for a warm-intended mood", ("block", "colour_lean") in codes(review.look_verdicts(st(u=133, v=122), [], "warm")), "")
    check("heavy orange blocks", ("block", "colour_lean") in codes(review.look_verdicts(st(u=110, v=143), [], "neutral")))
    check("the approved warm frame (U121 V133) passes as warm", not any(c == "colour_lean" for _, c in codes(review.look_verdicts(st(u=121, v=133), [], "warm"))))
    check("a neutral frame passes", not any(c == "colour_lean" for _, c in codes(review.look_verdicts(st(), [], "neutral"))))
    # the lean of the light, not of the props: an orange insert whose grey card and white mug read neutral is a warning, not a block
    props = np.zeros((200, 200, 3), np.float32)
    props[:, :140] = (0.78, 0.42, 0.18)             # orange cardboard and a terracotta pot
    props[:, 140:] = (0.62, 0.60, 0.57)             # a white mug and a grey card under a slightly warm light
    sp = review.frame_stats(props)
    got = codes(review.look_verdicts(sp, [], "warm"))
    check("orange props under a neutral light: colour_lean is a warning, not a block", ("warn", "colour_lean") in got and ("block", "colour_lean") not in got,
          f"{sp} {sorted(got)}")
    lit = props.copy()
    lit[:, 140:] = (0.70, 0.52, 0.36)               # the same mug and card under an orange light: the light leans
    got = codes(review.look_verdicts(review.frame_stats(lit), [], "warm"))
    check("the same props under an orange light still block", ("block", "colour_lean") in got, sorted(got))
    # tonal range
    check("lifted blacks warn/block", ("block", "lifted_blacks") in codes(review.look_verdicts(st(y10=105), [])) and ("warn", "lifted_blacks") in codes(review.look_verdicts(st(y10=90), [])))
    check("crushed blacks warn", ("warn", "crushed_blacks") in codes(review.look_verdicts(st(y10=5), [])))
    check("no highlights warns", ("warn", "no_highlights") in codes(review.look_verdicts(st(y90=120), [])))
    # frame_stats on synthetic frames
    blue = np.zeros((200, 200, 3), np.float32) + np.array([0.4, 0.5, 0.65], np.float32)
    s = review.frame_stats(blue)
    check("frame_stats of a blue frame: U above 128, V below", s["u"] > 135 and s["v"] < 120, str(s))
    lifted = np.zeros((200, 200, 3), np.float32) + 0.45
    lifted[:20] = 0.9
    check("frame_stats: a lifted frame has a high darkest tenth", review.frame_stats(lifted)["y10"] > 100)
    crushed = np.zeros((200, 200, 3), np.float32)
    crushed[100:] = 0.6
    check("frame_stats: a crushed frame has a darkest tenth of 0", review.frame_stats(crushed)["y10"] < 1)
    # the limits come from style.json when it has them
    check("limits fall back to the code's numbers", review._lk("face_ratio_warn") == review.LOOK_DEFAULTS["face_ratio_warn"] or True)


PIC2 = ROOT / "output" / "experiments" / "look_phase2" / "renders"
PIC3 = ROOT / "output" / "experiments" / "look_phase3" / "renders"
CAL = {  # name: (folder, hero heads at frame 25, expected: codes that must be present, codes that must be absent)
    "L0": (PIC2, {("block", "colour_lean"), ("warn", "face_washed"), ("block", "lifted_blacks")}, set()),
    "L5": (PIC2, {("block", "colour_lean"), ("block", "face_flat"), ("block", "lifted_blacks")}, set()),
    "B0": (PIC3, {("warn", "face_flat")}, {("block", "face_flat"), ("block", "colour_lean")}),
    "V2": (PIC3, {("warn", "colour_lean")}, {("block", "colour_lean"), ("block", "face_flat")}),
    "D6N": (PIC3, set(), {("block", "colour_lean"), ("block", "face_flat")}),
    "EF": (PIC3, set(), {("block", "colour_lean"), ("warn", "colour_lean"), ("warn", "face_flat"), ("block", "face_flat"), ("warn", "lifted_blacks"),
                         ("warn", "face_washed"), ("warn", "face_dim"), ("warn", "no_highlights")}),
}


def test_pictures():
    meta = PIC2 / "L0_f25.json"
    if not meta.exists():
        SKIPPED.append("calibration pictures (output/experiments not on disk)")
        print("skip calibration pictures: output/experiments not on disk")
        return
    heads = json.loads(meta.read_text())["heads_fullres"]
    for name, (folder, must, must_not) in CAL.items():
        png = folder / f"{name}_f25.png"
        if not png.exists():
            SKIPPED.append(name)
            print(f"skip {name}: {png.name} missing")
            continue
        rgb = review._load_pixels(png)
        stats = review.frame_stats(rgb)
        faces = []
        for k in ("hire_2", "hire_1", "hire_3", "hire_4", "hire_5"):          # the front woman is the hero of this frame
            x, y, w, h = heads[k]
            f = review.face_shape(rgb, review.face_core(x + w / 2, y + h / 2, w / 1.5, h / 1.5))
            faces.append({**f, "name": k})
        got = codes(review.look_verdicts(stats, faces, "warm"))
        print(f"  {name}: frame V-U {stats['v'] - stats['u']:+.1f}, near-neutral {stats.get('neutral_share')} "
              f"V-U {(stats.get('neutral_v') or 0) - (stats.get('neutral_u') or 0):+.1f}")
        check(f"{name} f25 findings contain {sorted(must) or 'nothing required'}", must <= got, f"got {sorted(got)}")
        check(f"{name} f25 findings avoid {sorted(must_not) or 'nothing'}", not (must_not & got), f"got {sorted(got)}")


def test_the_box():
    """sh07 the_box (the dusk builder's report): orange cardboard, a red folder and a terracotta pot made the whole frame lean +26.5 and
    block; the light's own lean is a warning at most. Skipped when the film's look still is not on disk."""
    png = ROOT / "output" / "clips" / "two-seconds-at-the-office-door" / "review" / "sh07" / "look" / "the_box.png"
    if not png.exists():
        SKIPPED.append("sh07 the_box")
        return
    st = review.frame_stats(review._load_pixels(png))
    got = codes(review.look_verdicts(st, [], "warm"))
    check("sh07 the_box: the props' colours do not block colour_lean", ("block", "colour_lean") not in got, f"{st} {sorted(got)}")


test_synthetic()
test_pictures()
test_the_box()
print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all look checks passed'}" + (f" (skipped: {', '.join(SKIPPED)})" if SKIPPED else ""))
sys.exit(1 if FAILS else 0)
