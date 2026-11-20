#!/usr/bin/env python3
"""clip.py - one entry point for every mechanical step of the clay Shorts pipeline.

    python tools/clip.py setup                      unpack the character pack, install Remotion packages, check tools
    python tools/clip.py doctor [--pack]            what is installed and reachable (Blender, FFmpeg, Node, ElevenLabs)
    python tools/clip.py voices [--pick N=ID] [--add N=ID]   check the voice shortlist on your ElevenLabs account
    python tools/clip.py new --script <script.json> [--format f]     create output/clips/<slug>/
    python tools/clip.py plan-check <clip>          shot plan vs script and style numbers
    python tools/clip.py voice <clip> [--mock]      narration take -> timing.json (the film's clock)
    python tools/clip.py sound <clip> [--mock]      music, ambience, sound effects -> cues.json
    python tools/clip.py stills <clip> [shots..]    build shots in Blender, render review stills + measured checks
    python tools/clip.py render <clip> [shots..]    final frames (resumable)   [--quality draft --step 6 for an animatic]
    python tools/clip.py assemble <clip>            Remotion + FFmpeg -> final MP4
    python tools/clip.py qa <clip>                  measure the final file
    python tools/clip.py sample <clip>              frames from the final file for a last look
    python tools/clip.py status <clip>              which stages are done
    python tools/clip.py assets find <words> | list | bk-local <words>
    python tools/clip.py asset <script.py> [--no-save]   build a reusable asset, render its preview, file it in the library
    python tools/clip.py bk-search "<words>" | bk-fetch <id or url>

<clip> is a slug under output/clips/ or a path. Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan as plan_mod  # noqa: E402
from common import (FORMATS, ROOT, STYLE, blender_cmd, clip_dir, load_env, read_json, run, slugify, which_ffmpeg, write_json)  # noqa: E402

PACK = ROOT / "packs" / "release_1"
PACK_ZIP = ROOT / "packs" / "release_1.zip"


# ----------------------------------------------------------------------------- setup / doctor
def pack_ok() -> bool:
    return (PACK / "blender" / "py" / "character_factory.py").exists() and (PACK / "library" / "registry.json").exists()


def cmd_setup(a):
    load_env()
    if pack_ok():
        print(f"character pack: ok ({PACK})")
    elif PACK_ZIP.exists():
        print(f"character pack: extracting {PACK_ZIP.name} ...")
        PACK.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(PACK_ZIP) as z:
            root = PACK.resolve()
            for m in z.infolist():
                if not (root / m.filename).resolve().is_relative_to(root):
                    raise SystemExit(f"refusing to extract {m.filename!r}: outside the pack folder")
            z.extractall(PACK)
        inner = [p for p in PACK.iterdir() if p.is_dir() and (p / "library").exists() and not (PACK / "library").exists()]
        if inner:                                        # the zip had a single top-level folder: lift its contents
            for child in inner[0].iterdir():
                shutil.move(str(child), PACK / child.name)
            inner[0].rmdir()
        print("character pack:", "ok" if pack_ok() else "EXTRACTED BUT NOT RECOGNISED (expected library/ and blender/ inside packs/release_1/)")
    else:
        print(f"character pack: MISSING. Put release_1.zip at {PACK_ZIP} and run setup again (or unzip it yourself into {PACK}).")
    if not (ROOT / ".env").exists() and (ROOT / ".env.example").exists():
        shutil.copyfile(ROOT / ".env.example", ROOT / ".env")
        print(".env: created from .env.example - add your ELEVENLABS_API_KEY")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm and (ROOT / "remotion" / "package.json").exists() and not (ROOT / "remotion" / "node_modules" / "remotion").exists():
        run([npm, "install", "--no-audit", "--no-fund"], cwd=ROOT / "remotion")
    (ROOT / "library" / "assets").mkdir(parents=True, exist_ok=True)
    return cmd_doctor(a)


def cmd_doctor(a):
    load_env()
    ok = True

    def line(name, good, detail):
        nonlocal ok
        ok = ok and (good or good is None)
        print(f"  [{'ok' if good else ('--' if good is None else 'MISSING')}] {name}: {detail}")

    print("clay-shorts doctor")
    line("character pack", pack_ok(), str(PACK) if pack_ok() else f"unzip release_1.zip into {PACK} (python tools/clip.py setup)")
    try:
        cmd = blender_cmd()
        if len(cmd) == 1:
            v = subprocess.run([cmd[0], "-c", "import bpy;print(bpy.app.version_string)"], capture_output=True, text=True).stdout.strip().splitlines()[-1]
            line("Blender", v.startswith("5.3"), f"bpy module {v} (python {cmd[0]})" + ("" if v.startswith("5.3") else " - the pack is built for 5.3"))
        else:
            v = subprocess.run([cmd[0], "--version"], capture_output=True, text=True).stdout.splitlines()[0]
            line("Blender", "5.3" in v, f"{v} ({cmd[0]})" + ("" if "5.3" in v else " - the pack is built for 5.3"))
    except SystemExit as e:
        line("Blender", False, str(e))
    try:
        v = subprocess.run([which_ffmpeg(), "-version"], capture_output=True, text=True).stdout.splitlines()[0]
        line("FFmpeg", True, v[:60])
    except SystemExit as e:
        line("FFmpeg", False, str(e))
    node = shutil.which("node")
    line("Node.js", bool(node), subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip() if node else "install Node 20+")
    line("Remotion packages", (ROOT / "remotion" / "node_modules" / "remotion").exists(), "remotion/node_modules" if (ROOT / "remotion" / "node_modules").exists() else "run: python tools/clip.py setup")
    idx = ROOT / "library" / "assets" / "index.json"
    line("asset library", None, f"{len(read_json(idx)['assets'])} asset(s)" if idx.exists() else "empty (it fills as Shorts are made)")
    from audio import eleven
    if eleven.has_key():
        try:
            sub = eleven.subscription()
            ids = {m["model_id"] for m in eleven.models()}
            cfg = read_json(ROOT / "config" / "voices.json")
            want = [cfg["tts"]["model_id"], cfg["sfx"]["model_id"], cfg["music"]["model_id"]]
            line("ElevenLabs", True, f"tier {sub.get('tier')}, {sub.get('character_count')}/{sub.get('character_limit')} credits used")
            line("ElevenLabs TTS model", cfg["tts"]["model_id"] in ids, f"{cfg['tts']['model_id']}" + ("" if cfg["tts"]["model_id"] in ids else f" not listed for this account; fallbacks {cfg['tts']['fallback_models']}"))
            print(f"       sound/music models are not in /v1/models; configured: {want[1]}, {want[2]}")
            print("       run `python tools/clip.py voices` to check the voice shortlist")
        except Exception as e:  # noqa: BLE001
            line("ElevenLabs", False, str(e))
    else:
        line("ElevenLabs", None, "no ELEVENLABS_API_KEY in .env (steps can still run with --mock)")
    if getattr(a, "pack", False) and pack_ok():
        print("running the pack's own smoke test (a few minutes) ...")
        cmd = blender_cmd()
        r = subprocess.run([*cmd, str(PACK / "blender" / "smoke_test.py"), "--", "--out", str(ROOT / "output" / "pack_smoke.png")], capture_output=True, text=True)
        passed = r.stdout.count("SMOKE PASS")
        line("pack smoke test", r.returncode == 0, f"{passed} checks passed" if r.returncode == 0 else (r.stdout + r.stderr)[-400:])
    return 0 if ok else 1


# ----------------------------------------------------------------------------- voices
def cmd_voices(a):
    load_env()
    from audio import eleven
    from audio.voice import pick_voice, voices_config
    cfg = voices_config()
    local_path = ROOT / "config" / "voices.local.json"
    local = read_json(local_path) if local_path.exists() else {"voices": {}}
    changed = False
    for spec in a.pick or []:
        name, vid = spec.split("=", 1)
        local["voices"].setdefault(name, {})["voice_id"] = vid
        cfg["voices"].setdefault(name, {})["voice_id"] = vid
        changed = True
    today = datetime.date.today()
    if not eleven.has_key():
        print("no ELEVENLABS_API_KEY: showing the configured shortlist without checking the account\n")
    else:
        for spec in a.add or []:
            name, vid = spec.split("=", 1)
            hit = next((v for v in eleven.shared_voices(cfg["voices"].get(name, {}).get("search", name), 30) if v.get("voice_id") == vid), None)
            if not hit:
                print(f"add {name}: {vid} not found in the Voice Library search for '{name}'")
                continue
            eleven.add_shared_voice(hit["public_owner_id"], vid, hit.get("name", name))
            local["voices"].setdefault(name, {})["voice_id"] = vid
            cfg["voices"].setdefault(name, {})["voice_id"] = vid
            changed = True
            print(f"added '{hit.get('name')}' to My Voices as {name}")
        for name, v in cfg["voices"].items():
            note = ""
            if v.get("voice_id"):
                try:
                    info = eleven.voice(v["voice_id"])
                    status = f"ok  '{info.get('name')}' [{info.get('category')}]"
                    if local["voices"].get(name, {}).get("unavailable"):
                        local["voices"][name].pop("unavailable")
                        changed = True
                except eleven.ElevenError as e:
                    status = f"NOT AVAILABLE on this account ({e.status})"
                    local["voices"].setdefault(name, {})["unavailable"] = True
                    changed = True
            else:
                mine = [m for m in eleven.my_voices(v.get("search", name)) if name.lower().split(" (")[0] in m.get("name", "").lower()]
                if len(mine) == 1:
                    local["voices"].setdefault(name, {})["voice_id"] = mine[0]["voice_id"]
                    v["voice_id"] = mine[0]["voice_id"]
                    changed = True
                    status = f"ok  found in My Voices: '{mine[0]['name']}' -> {mine[0]['voice_id']}"
                elif len(mine) > 1:
                    status = "several matches in My Voices; choose one with --pick " + name.replace(" ", "\\ ") + "=<id>:"
                    note = "\n".join(f"        {m['voice_id']}  {m['name']}" for m in mine[:8])
                else:
                    lib = eleven.shared_voices(v.get("search", name), 6)
                    status = "not in My Voices. Voice Library matches (add one with --add \"" + name + "=<id>\", or in the app):"
                    note = "\n".join(f"        {m['voice_id']}  {m.get('name')} - {m.get('descriptive', '')} {m.get('accent', '')} {m.get('use_case', '')}" for m in lib) or "        (none found)"
            if v.get("expires"):
                d = datetime.date.fromisoformat(v["expires"])
                status += f"  | default voice, retired by ElevenLabs on {v['expires']}" + (f" ({(d - today).days} days left)" if d >= today else " (GONE)") + f" -> then {v.get('replacement')}"
            print(f"  {name:<18} {status}")
            if note:
                print(note)
    if changed:
        write_json(local_path, local)
        print(f"\nsaved {local_path.relative_to(ROOT)}")
    print("\nvoice each format will use today:")
    cfg = voices_config()
    for fmt in FORMATS:
        try:
            name, v = pick_voice(cfg, fmt)
            print(f"  script-{fmt:<20} {name}  ({v['voice_id']})   shortlist: {', '.join(cfg['formats'][fmt]['voices'])}")
        except SystemExit as e:
            print(f"  script-{fmt:<20} NONE USABLE: {str(e).splitlines()[0]}")
    return 0


# ----------------------------------------------------------------------------- clip lifecycle
def cmd_new(a):
    src = Path(a.script).resolve()
    script = read_json(src)
    fmt = a.format or next((p for p in src.parts if p in FORMATS), None)
    if fmt not in FORMATS:
        raise SystemExit(f"--format is required (one of {', '.join(FORMATS)})")
    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "validate_script.py"), "--format", fmt, str(src)], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        raise SystemExit("the script does not pass scripts/validate_script.py: fix it before production")
    slug = a.slug or slugify(script["title"])
    d = ROOT / "output" / "clips" / slug
    if d.exists() and not a.force:
        k = 2
        while (ROOT / "output" / "clips" / f"{slug}-{k}").exists():
            k += 1
        slug = f"{slug}-{k}"
        d = ROOT / "output" / "clips" / slug
    for sub in ("audio", "blender", "review", "render", "final"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    write_json(d / "script.json", script)
    write_json(d / "state.json", {"slug": slug, "title": script["title"], "format": fmt, "created": datetime.datetime.now().isoformat(timespec="seconds"),
                                  "source_script": str(src.relative_to(ROOT)) if src.is_relative_to(ROOT) else str(src), "idea": a.idea or ""})
    print(f"clip: {d.relative_to(ROOT)}")
    return 0


def cmd_plan_check(a):
    return plan_mod.main([a.clip])


def _blender(script: Path, args: list[str], factory: bool = True) -> int:
    cmd = blender_cmd()
    if not factory and len(cmd) > 1:
        cmd = [c for c in cmd if c != "--factory-startup"]
    env = dict(os.environ, CLAY_PROJECT=str(ROOT))
    full = [*cmd, str(script), "--", *args]
    print("$", " ".join(full), flush=True)
    return subprocess.run(full, env=env).returncode


def _shots(clip: Path, wanted: list[str]) -> list[str]:
    plan = read_json(clip / "shotplan.json")
    ids = [s["id"] for s in plan["shots"]]
    if not wanted or wanted == ["all"]:
        return ids
    bad = [w for w in wanted if w not in ids]
    if bad:
        raise SystemExit(f"unknown shot(s) {bad}; the plan has {ids}")
    return wanted


def cmd_stills(a):
    load_env()
    clip = clip_dir(a.clip)
    rc = 0
    for sid in _shots(clip, a.shots):
        args = ["--clip", str(clip), "--shot", sid, "--mode", "stills", "--quality", a.quality]
        if a.seconds:
            args += ["--seconds", str(a.seconds)]
        if a.save_blend:
            args.append("--save-blend")
        r = _blender(ROOT / "tools" / "blender" / "run_shot.py", args)
        rc = rc or r
        rep = clip / "review" / sid / "checks.json"
        if r == 0 and rep.exists():
            issues = read_json(rep).get("issues", [])
            print(f"== {sid}: sheet {rep.parent / 'sheet.png'}; {len(issues)} measured issue(s)")
    return rc


def cmd_render(a):
    """Render every frame of the chosen shots. Blender is restarted every --chunk frames: it keeps memory flat on
    long takes and means a crash only costs one chunk (existing frames are never rendered twice)."""
    load_env()
    clip = clip_dir(a.clip)
    if not (clip / "timing.json").exists():
        raise SystemExit("no timing.json: run the voice step first, shot lengths come from the narration")
    timing = read_json(clip / "timing.json")
    step = max(1, a.step)
    chunk = a.chunk if a.chunk is not None else int(os.environ.get("CLAY_RENDER_CHUNK", "120"))
    rc = 0
    for sid in _shots(clip, a.shots):
        n = timing["shots"][sid]["frames"]
        if a.frames:
            f0, f1 = (int(x) for x in a.frames.split("-"))
        else:
            f0, f1 = 1, n
        frames = [f for f in range(1, n + 1, step) if f0 <= f <= f1]
        out = clip / "render" / sid / a.quality
        if not a.force:
            todo = [f for f in frames if not (out / f"{f:04d}.png").exists()]
        else:
            todo = frames
        if not todo:
            print(f"== {sid}: all {len(frames)} frame(s) already rendered")
            todo = frames[:1]                                    # still run once so render.json is refreshed
        groups = [todo[i:i + chunk] for i in range(0, len(todo), chunk)] if chunk > 0 else [todo]
        for g in groups:
            args = ["--clip", str(clip), "--shot", sid, "--mode", "render", "--quality", a.quality, "--step", str(step), "--frames", f"{g[0]}-{g[-1]}"]
            if a.force:
                args.append("--force")
            if a.percent:
                args += ["--percent", str(a.percent)]
            if a.samples:
                args += ["--samples", str(a.samples)]
            r = _blender(ROOT / "tools" / "blender" / "run_shot.py", args)
            if r != 0:
                print(f"== {sid}: Blender exited with {r} on frames {g[0]}-{g[-1]}; run the same command again to resume")
                rc = rc or r
                break
    return rc


def cmd_status(a):
    clip = clip_dir(a.clip)
    st = read_json(clip / "state.json") if (clip / "state.json").exists() else {}
    print(f"{clip.name}: '{st.get('title', '?')}' ({st.get('format', '?')})")

    def has(p):
        return (clip / p).exists()

    rows = [("script", has("script.json")), ("shot plan", has("shotplan.json"))]
    plan = read_json(clip / "shotplan.json") if has("shotplan.json") else {"shots": []}
    if has("shotplan.json"):
        err, warn = plan_mod.check(plan, read_json(clip / "script.json"))
        rows[-1] = ("shot plan", not err, f"{len(plan['shots'])} shots" + (f", {len(err)} error(s)" if err else ""))
    timing = read_json(clip / "timing.json") if has("timing.json") else None
    rows.append(("audio plan", has("audio/plan.json")))
    rows.append(("voice + timing", bool(timing), f"{timing['total_seconds']}s, source {timing['source']}" if timing else ""))
    rows.append(("sound cues", has("audio/cues.json"), f"{len(read_json(clip / 'audio/cues.json')['cues'])} cue(s)" if has("audio/cues.json") else ""))
    for s in plan["shots"]:
        sid = s["id"]
        parts = []
        parts.append("script" if has(f"blender/{sid}.py") else "no script")
        if has(f"review/{sid}/checks.json"):
            parts.append(f"stills ({len(read_json(clip / 'review' / sid / 'checks.json').get('issues', []))} issues)")
        if has(f"review/{sid}/verdict.json"):
            parts.append("review: " + read_json(clip / "review" / sid / "verdict.json").get("verdict", "?"))
        done = False
        for q in ("final", "preview", "draft"):
            m = clip / "render" / sid / q / "render.json"
            if m.exists():
                j = read_json(m)
                parts.append(f"{q} render {j['rendered']}/{j['expected']}" + (f" step {j['step']}" if j.get("step", 1) > 1 else ""))
                done = q == "final" and bool(j.get("complete"))
                break
        rows.append((f"shot {sid}", done, ", ".join(parts)))
    finals = sorted((clip / "final").glob("*.mp4")) if has("final") else []
    rows.append(("final video", bool(finals), ", ".join(f.name for f in finals)))
    for r in rows:
        print(f"  [{'x' if r[1] else ' '}] {r[0]:<16} {r[2] if len(r) > 2 else ''}")
    return 0


# ----------------------------------------------------------------------------- assets
def cmd_assets(a):
    idx = ROOT / "library" / "assets" / "index.json"
    assets = read_json(idx)["assets"] if idx.exists() else []
    if a.action == "list":
        for x in assets:
            print(f"{x['id']:<32} {x['kind']:<10} {x.get('size_m')}  {x.get('source')}  {', '.join(x.get('tags', []))}")
        print(f"{len(assets)} asset(s) in library/assets")
    elif a.action == "find":
        import re
        q = {t for t in re.split(r"[^a-z0-9]+", " ".join(a.words).lower()) if len(t) > 1}
        hits = []
        for x in assets:
            hay = {t for t in re.split(r"[^a-z0-9]+", (x["id"] + " " + x.get("name", "") + " " + " ".join(x.get("tags", []))).lower()) if t}
            s = len(q & hay) + 0.25 * sum(1 for t in q for h in hay if t in h and t != h)
            if s > 0:
                hits.append((s, x))
        for s, x in sorted(hits, key=lambda h: -h[0])[:10]:
            print(json.dumps({k: x[k] for k in ("id", "name", "kind", "tags", "size_m", "source", "notes") if k in x}))
        if not hits:
            print("no library asset matches: next try BlenderKit (bk-search), then build it")
    elif a.action == "bk-local":
        root = Path(os.environ.get("BLENDERKIT_DATA_DIR") or Path.home() / "blenderkit_data")
        import re
        q = {t for t in re.split(r"[^a-z0-9]+", " ".join(a.words).lower()) if len(t) > 1}
        n = 0
        for sub in ("models", "scenes", "materials"):
            d = root / sub
            if d.is_dir():
                for folder in sorted(d.iterdir()):
                    blends = sorted(folder.glob("*.blend"), key=lambda p: p.stat().st_size)
                    if blends and (not q or q & {t for t in re.split(r"[^a-z0-9]+", folder.name.lower()) if t}):
                        print(json.dumps({"name": folder.name, "type": sub[:-1], "blend": str(blends[-1])}))
                        n += 1
        print(f"{n} downloaded BlenderKit asset(s) under {root}")
    return 0


def cmd_sample(a):
    """Frames from the finished film for a last look: one per caption-sized step, tiled into a sheet."""
    clip = clip_dir(a.clip)
    slug = clip.name + (f"_{a.tag}" if a.tag else "")
    src = clip / "final" / f"{slug}.mp4"
    if not src.exists():
        raise SystemExit(f"no {src.name}: run assemble first")
    out = clip / "final" / "samples"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    timing = read_json(clip / "timing.json")
    fps = timing["fps"]
    times = []
    for s in timing["shots"].values():                       # start, middle and end of every shot
        a0, n = s["start_frame"], s["frames"]
        times += [(a0 + 3) / fps, (a0 + n // 2) / fps, (a0 + n - 4) / fps]
    ff = which_ffmpeg()
    for i, t in enumerate(times):
        run([ff, "-y", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", src, "-frames:v", "1", "-vf", "scale=360:-2", out / f"{i:02d}_{t:05.1f}s.png"], quiet=True)
    cols = 3                                                 # one row per shot: start, middle, end
    rows = -(-len(times) // cols)
    lst = out / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\nduration 1\n" for p in sorted(out.glob("*.png"))), encoding="utf-8")
    run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf", f"tile={cols}x{rows}:padding=4", "-frames:v", "1", out / "sheet.png"], quiet=True)
    lst.unlink()
    print(f"samples: {len(times)} frames (start, middle, end of each shot, in order) -> {out / 'sheet.png'}")
    return 0


def cmd_asset(a):
    load_env()
    args = [str(Path(a.script).resolve()), "--quality", a.quality] + (["--no-save"] if a.no_save else [])
    return _blender(ROOT / "tools" / "blender" / "run_asset.py", args)


def cmd_bk(a):
    load_env()
    args = ["search", a.query, "--type", a.type, "--limit", str(a.limit)] if a.cmd == "bk-search" else ["fetch", *a.ids]
    return _blender(ROOT / "tools" / "blender" / "bk_fetch.py", args, factory=False)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(prog="clip.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    p = sub.add_parser("doctor")
    p.add_argument("--pack", action="store_true", help="also run the character pack's smoke test")
    p = sub.add_parser("voices")
    p.add_argument("--pick", action="append", metavar="NAME=VOICE_ID")
    p.add_argument("--add", action="append", metavar="NAME=VOICE_ID")
    p = sub.add_parser("new")
    p.add_argument("--script", required=True)
    p.add_argument("--format", choices=FORMATS)
    p.add_argument("--slug")
    p.add_argument("--idea", default="")
    p.add_argument("--force", action="store_true", help="reuse an existing clip folder")
    p = sub.add_parser("plan-check")
    p.add_argument("clip")
    for name in ("voice", "sound", "assemble", "qa"):
        p = sub.add_parser(name, add_help=False)
        p.add_argument("rest", nargs=argparse.REMAINDER)
    p = sub.add_parser("stills")
    p.add_argument("clip")
    p.add_argument("shots", nargs="*")
    p.add_argument("--quality", choices=("draft", "preview", "final"), default="draft")
    p.add_argument("--seconds", type=float)
    p.add_argument("--save-blend", action="store_true")
    p = sub.add_parser("render")
    p.add_argument("clip")
    p.add_argument("shots", nargs="*")
    p.add_argument("--quality", choices=("draft", "preview", "final"), default="final")
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--frames")
    p.add_argument("--percent", type=int)
    p.add_argument("--samples", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--chunk", type=int, help="frames per Blender process (default 120, 0 = one process per shot)")
    p = sub.add_parser("status")
    p.add_argument("clip")
    p = sub.add_parser("assets")
    p.add_argument("action", choices=("list", "find", "bk-local"))
    p.add_argument("words", nargs="*")
    p = sub.add_parser("sample")
    p.add_argument("clip")
    p.add_argument("--tag", default="")
    p = sub.add_parser("asset")
    p.add_argument("script")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--quality", choices=("draft", "preview", "final"), default="preview")
    p = sub.add_parser("bk-search")
    p.add_argument("query")
    p.add_argument("--type", default="model")
    p.add_argument("--limit", type=int, default=8)
    p = sub.add_parser("bk-fetch")
    p.add_argument("ids", nargs="+")
    a = ap.parse_args()
    if a.cmd in ("voice", "sound", "assemble", "qa"):
        if a.cmd == "voice":
            from audio import voice as m
        elif a.cmd == "sound":
            from audio import sound as m
        elif a.cmd == "assemble":
            import assemble as m
        else:
            import qa as m
        return m.main(a.rest)
    return {"setup": cmd_setup, "doctor": cmd_doctor, "voices": cmd_voices, "new": cmd_new, "plan-check": cmd_plan_check, "stills": cmd_stills,
            "render": cmd_render, "status": cmd_status, "assets": cmd_assets, "asset": cmd_asset, "sample": cmd_sample, "bk-search": cmd_bk, "bk-fetch": cmd_bk}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
