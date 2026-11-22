"""Build one shot inside Blender and render review stills or the final frames.

    blender -b --factory-startup --python tools/blender/run_shot.py -- --clip output/clips/<slug> --shot sh01 --mode stills
    (tools/clip.py stills|render wraps this and finds Blender for you.)

The shot script is <clip>/blender/<shot>.py and defines build_shot(shot). Set builders live in <clip>/blender/set_<id>.py.
A shot is one staged take in one set; its camera views (cam.view) are checked against the plan's views.
Frames are resumable: an existing PNG is never rendered again unless --force.
"""
import argparse
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import bpy  # noqa: E402

import stagekit  # noqa: E402
from stagekit import core, review  # noqa: E402


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="run_shot")
    ap.add_argument("--clip", required=True)
    ap.add_argument("--shot", required=True)
    ap.add_argument("--mode", choices=("stills", "render", "blend"), default="stills")
    ap.add_argument("--quality", choices=("draft", "preview", "final"), default=None)
    ap.add_argument("--seconds", type=float, default=None, help="override the shot length (otherwise timing.json, then the plan estimate)")
    ap.add_argument("--frames", default=None, help="a-b (render mode)")
    ap.add_argument("--step", type=int, default=1, help="render every Nth frame (draft animatics)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--save-blend", action="store_true")
    ap.add_argument("--percent", type=int, default=None, help="override the resolution percentage")
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--views", default=None, help="stills mode: only these view ids, comma separated (a quick look at one framing)")
    return ap.parse_args(argv)


def shot_seconds(clip: Path, shot_id: str, override):
    if override:
        return float(override), "override"
    t = clip / "timing.json"
    if t.exists():
        d = json.loads(t.read_text(encoding="utf-8"))
        s = d.get("shots", {}).get(shot_id)
        if s:
            return float(s["seconds"]), "timing.json"
    p = clip / "shotplan.json"
    if p.exists():
        for s in json.loads(p.read_text(encoding="utf-8")).get("shots", []):
            if s["id"] == shot_id and s.get("est_seconds"):
                return float(s["est_seconds"]), "shotplan estimate (no voice timing yet)"
    raise SystemExit(f"no length for {shot_id}: run the voice step first (timing.json) or pass --seconds")


def shot_words(clip: Path, shot_id: str, seconds: float):
    """Narration words of the shot with times relative to the shot start (from the voice take, else spread evenly)."""
    t = clip / "timing.json"
    if t.exists():
        d = json.loads(t.read_text(encoding="utf-8"))
        if shot_id in d.get("shots", {}):
            s0 = d["shots"][shot_id]["start_s"]
            return [{"text": w["text"], "start": round(w["start"] - s0, 3), "end": round(w["end"] - s0, 3)} for w in d["words"] if w["shot"] == shot_id]
    p = clip / "shotplan.json"
    if p.exists():
        for s in json.loads(p.read_text(encoding="utf-8")).get("shots", []):
            if s["id"] == shot_id:
                ws = [w for w in s.get("vo_text", "").split() if any(c.isalnum() for c in w)]
                step = max(0.1, (seconds - 0.6) / max(1, len(ws)))
                return [{"text": w, "start": round(0.1 + i * step, 3), "end": round(0.1 + (i + 0.85) * step, 3)} for i, w in enumerate(ws)]
    return []


def plan_of(clip: Path) -> dict:
    p = clip / "shotplan.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def plan_entry(clip: Path, shot_id: str) -> dict:
    return next((s for s in plan_of(clip).get("shots", []) if s["id"] == shot_id), {})


def main():
    a = parse()
    clip = Path(a.clip).resolve()
    script = clip / "blender" / f"{a.shot}.py"
    if not script.exists():
        raise SystemExit(f"missing shot script {script}")
    quality = a.quality or ("draft" if a.mode == "stills" else "final")
    seconds, src = shot_seconds(clip, a.shot, a.seconds)
    shot = stagekit.begin(a.shot, seconds, quality)
    shot.clip_dir = clip
    shot.words = shot_words(clip, a.shot, seconds)
    shot.plan = plan_entry(clip, a.shot)
    whole = plan_of(clip)
    shot.world = whole.get("world", {})
    shot.cast_plan = {c["id"]: c for c in whole.get("cast", [])}
    sc = bpy.context.scene
    if a.percent:
        sc.render.resolution_percentage = a.percent
    if a.samples:
        sc.eevee.taa_render_samples = a.samples
    print(f"[run_shot] {a.shot}: {seconds:.2f}s = {shot.frames} frames ({src}), quality={quality}, blender {bpy.app.version_string}")
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location(f"shot_{a.shot}", script)
    mod = importlib.util.module_from_spec(spec)
    t0 = time.perf_counter()
    try:
        spec.loader.exec_module(mod)
        if not hasattr(mod, "build_shot"):
            raise SystemExit(f"{script.name} must define build_shot(shot)")
        mod.build_shot(shot)
    except Exception:
        traceback.print_exc()
        print("[run_shot] BUILD FAILED")
        sys.exit(3)
    sc.frame_start, sc.frame_end = 1, shot.frames
    if sc.camera is None:
        print("[run_shot] BUILD FAILED: the shot has no camera")
        sys.exit(3)
    cam = getattr(shot, "camera", None)
    built = [v["id"] for v in getattr(cam, "views", [])]
    planned = [v.get("id") for v in shot.plan.get("views", [])]
    for vid in planned:
        if vid not in built:
            shot.notes.append(f"PLAN: the plan lists view '{vid}' but the shot script has no cam.view('{vid}', ...)")
    for vid in built:
        if planned and vid not in planned:
            shot.notes.append(f"PLAN: the shot script adds view '{vid}' that the plan does not list (fine if it serves the story: say why in the return note)")
    print(f"[run_shot] built in {time.perf_counter() - t0:.1f}s: {len(bpy.data.objects)} objects, views={built}, moments={list(shot.moments)}")
    if a.save_blend or a.mode == "blend":
        out = clip / "blender" / f"{a.shot}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
        print(f"[run_shot] saved {out}")
    if a.mode == "stills":
        rep = review.stills(shot, clip / "review" / a.shot, only=set(a.views.split(",")) if a.views else None)
        print(f"[run_shot] stills: {len(rep['stills'])} frames -> {clip / 'review' / a.shot}")
        for n in shot.notes:
            print(f"[note] {n}")
        for i in rep["issues"]:
            print(f"[check] {i}")
        print(f"[run_shot] CHECKS {'CLEAN' if not rep['issues'] else str(len(rep['issues'])) + ' ISSUE(S)'}")
    elif a.mode == "render":
        out = clip / "render" / a.shot / quality
        out.mkdir(parents=True, exist_ok=True)
        f0, f1 = 1, shot.frames
        if a.frames:
            f0, f1 = (int(x) for x in a.frames.split("-"))
        st = max(1, a.step)
        todo = [f for f in range(1, shot.frames + 1, st) if f0 <= f <= f1]
        done = 0
        t1 = time.perf_counter()
        for f in todo:
            p = out / f"{f:04d}.png"
            if p.exists() and p.stat().st_size > 0 and not a.force:
                continue
            sc.frame_set(f)
            sc.render.filepath = str(p)
            bpy.ops.render.render(write_still=True)
            done += 1
            if done % 10 == 0 or f == todo[-1]:
                el = time.perf_counter() - t1
                print(f"[run_shot] {a.shot} frame {f}/{f1}  {el / done:.2f}s/frame", flush=True)
        sc.render.use_stamp = False
        meta = {"shot": a.shot, "frames": shot.frames, "fps": shot.fps, "step": a.step, "quality": quality, "views": built, "rendered": len(list(out.glob('*.png'))),
                "expected": len(range(1, shot.frames + 1, max(1, a.step))), "width": sc.render.resolution_x * sc.render.resolution_percentage // 100,
                "height": sc.render.resolution_y * sc.render.resolution_percentage // 100}
        meta["complete"] = meta["rendered"] >= meta["expected"]
        (out / "render.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        print(f"[run_shot] render: {done} new frame(s), {meta['rendered']}/{meta['expected']} present -> {out}")
    print("[run_shot] OK")


if __name__ == "__main__":
    main()
