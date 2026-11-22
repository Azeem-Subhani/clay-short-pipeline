#!/usr/bin/env python3
"""clip.py - one entry point for every mechanical step of the Shorts pipeline (2D cast, 3D world).

    python tools/clip.py setup                      unpack the character pack, install Remotion packages, check tools
    python tools/clip.py doctor                     what is installed and reachable (pack, Blender, FFmpeg, Node, ElevenLabs, ambientCG sets)
    python tools/clip.py cast [Name] [--era medieval]   the characters of the pack: who they are, their period, colours and parts
    python tools/clip.py materials [fetch|search|add|list] ...   surfaces from ambientCG (see tools/materials.py)
    python tools/clip.py voices [--pick N=ID] [--add N=ID]   check the voice shortlist on your ElevenLabs account
    python tools/clip.py new --script <script.json> [--format f]     create output/clips/<slug>/
    python tools/clip.py plan-check <clip>          shot plan vs script, character pack, period, surfaces, view lengths, setups
    python tools/clip.py voice <clip> [--mock | --from-media file]   narration take -> timing.json (the film's clock)
    python tools/clip.py sound <clip> [--mock]      music, ambience, sound effects -> cues.json
    python tools/clip.py stills <clip> [shots..] [--views a,b]   build shots in Blender, render review stills + measured checks
    python tools/clip.py render <clip> [shots..]    final frames (resumable)   [--quality draft --step 3 for an animatic]
    python tools/clip.py assemble <clip>            Remotion + FFmpeg -> final MP4 (writes final/captions.json)
    python tools/clip.py qa <clip>                  measure the final file: format, loudness, captions placed and on time
    python tools/clip.py sample <clip>              frames from the final file for a last look
    python tools/clip.py status <clip>              which stages are done, and the next one
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

PACK_NAME = "characters_beta_0_3"
PACK = ROOT / "packs" / PACK_NAME


# ----------------------------------------------------------------------------- setup / doctor
def pack_blend():
    """The character library .blend of the 2D pack, or None. CAST_PACK (.env) may point at another folder or .blend."""
    root = Path(os.environ.get("CAST_PACK") or PACK)
    if root.suffix == ".blend":
        return root if root.exists() else None
    hits = sorted(root.rglob("character-library*.blend"), key=lambda q: q.stat().st_mtime) if root.exists() else []
    return hits[-1] if hits else None


def pack_ok() -> bool:
    return pack_blend() is not None


def pack_zip():
    zs = sorted((ROOT / "packs").glob("character*.zip"), key=lambda q: q.stat().st_mtime)
    return zs[-1] if zs else None


def cmd_setup(a):
    load_env()
    z = pack_zip()
    if pack_ok():
        print(f"character pack: ok ({pack_blend()})")
    elif z:
        print(f"character pack: extracting {z.name} ...")
        PACK.mkdir(parents=True, exist_ok=True)
        root = PACK.resolve()
        with zipfile.ZipFile(z) as zf:
            for m in zf.infolist():                              # the pack ZIP was made on Windows: its paths use backslashes
                name = m.filename.replace("\\", "/")
                if m.is_dir() or name.endswith("/"):
                    continue
                target = (root / name).resolve()
                if not target.is_relative_to(root):
                    raise SystemExit(f"refusing to extract {m.filename!r}: outside the pack folder")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(m))
        print("character pack:", f"ok ({pack_blend()})" if pack_ok() else "EXTRACTED BUT NO character-library*.blend FOUND inside")
    else:
        print(f"character pack: MISSING. Put characters_beta_0_3.zip in {ROOT / 'packs'} and run setup again "
              f"(or unzip it yourself so that {PACK}/**/character-library_v3d.blend exists).")
    if not (ROOT / ".env").exists() and (ROOT / ".env.example").exists():
        shutil.copyfile(ROOT / ".env.example", ROOT / ".env")
        print(".env: created from .env.example - add your ELEVENLABS_API_KEY")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm and (ROOT / "remotion" / "package.json").exists() and not (ROOT / "remotion" / "node_modules" / "remotion").exists():
        run([npm, "install", "--no-audit", "--no-fund"], cwd=ROOT / "remotion")
    (ROOT / "library" / "assets").mkdir(parents=True, exist_ok=True)
    (ROOT / "library" / "materials" / "ambientcg").mkdir(parents=True, exist_ok=True)
    return cmd_doctor(a)


def cmd_doctor(a):
    load_env()
    ok = True

    def line(name, good, detail):
        nonlocal ok
        ok = ok and (good or good is None)
        print(f"  [{'ok' if good else ('--' if good is None else 'MISSING')}] {name}: {detail}")

    print("shorts pipeline doctor")
    line("character pack (2D)", pack_ok(), str(pack_blend()) if pack_ok() else f"put characters_beta_0_3.zip in {ROOT / 'packs'} and run: python tools/clip.py setup")
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
    cat = read_json(ROOT / "library" / "materials" / "catalog.json")["surfaces"]
    acg = ROOT / "library" / "materials" / "ambientcg"
    got = [n for n, e in cat.items() if any((acg / i).is_dir() for i in e.get("ambientcg", []))]
    line("ambientCG surfaces", None, f"{len(got)} of {len(cat)} catalog surfaces have scanned textures; the rest use procedural stand-ins "
         "(python tools/clip.py materials fetch)")
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
            msg = " ".join(line.strip() for line in str(e).splitlines())
            print(f"  script-{fmt:<20} PENDING: {msg}")
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
    env = dict(os.environ, SHORTS_PROJECT=str(ROOT))
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
    """Build the shots and render their review stills. If Blender is stopped part-way (usually for memory on a small
    machine), the shot is done again a few views at a time; the sheet and the checks come out the same."""
    load_env()
    clip = clip_dir(a.clip)
    plan = read_json(clip / "shotplan.json")
    rc = 0
    for sid in _shots(clip, a.shots):
        base = ["--clip", str(clip), "--shot", sid, "--mode", "stills", "--quality", a.quality]
        if a.seconds:
            base += ["--seconds", str(a.seconds)]
        if a.save_blend:
            base.append("--save-blend")
        wanted = getattr(a, "views", None)
        r = _blender(ROOT / "tools" / "blender" / "run_shot.py", base + (["--views", wanted] if wanted else []))
        if r not in (0, 3):                                     # not a build error: Blender itself was stopped
            ids = wanted.split(",") if wanted else [v["id"] for x in plan["shots"] if x["id"] == sid for v in x.get("views", [])]
            size = max(1, int(getattr(a, "batch", 0) or 2))
            print(f"== {sid}: Blender stopped (exit {r}); doing the stills again {size} view(s) at a time", flush=True)
            if not wanted:
                for old in (clip / "review" / sid).glob("*"):
                    if old.suffix in (".png", ".json") and old.name != "verdict.json":
                        old.unlink()
            r = 0
            for i in range(0, len(ids), size):
                r = _blender(ROOT / "tools" / "blender" / "run_shot.py", base + ["--views", ",".join(ids[i:i + size])]) or r
        rc = rc or r
        rep = clip / "review" / sid / "checks.json"
        if r == 0 and rep.exists():
            issues = read_json(rep).get("issues", [])
            print(f"== {sid}: sheet {rep.parent / 'sheet.png'}; {len(read_json(rep).get('views', []))} view(s), {len(issues)} measured issue(s)")
    return rc


def cmd_render(a):
    """Render every frame of the chosen shots (existing frames are never rendered twice). Blender is restarted every
    --chunk frames, which keeps memory flat on long takes. If Blender stops early (a crash, or the system ending it for
    using too much memory), the rest is picked up straight away in smaller chunks, so one command finishes the job."""
    import time
    load_env()
    clip = clip_dir(a.clip)
    if not (clip / "timing.json").exists():
        raise SystemExit("no timing.json: run the voice step first, shot lengths come from the narration")
    timing = read_json(clip / "timing.json")
    step = max(1, a.step)
    chunk = a.chunk if a.chunk is not None else int(os.environ.get("RENDER_CHUNK") or os.environ.get("CLAY_RENDER_CHUNK") or "120")
    started = time.time()
    rc = 0
    for sid in _shots(clip, a.shots):
        n = timing["shots"][sid]["frames"]
        if a.frames:
            f0, f1 = (int(x) for x in a.frames.split("-"))
        else:
            f0, f1 = 1, n
        frames = [f for f in range(1, n + 1, step) if f0 <= f <= f1]
        out = clip / "render" / sid / a.quality

        def done(f):
            p = out / f"{f:04d}.png"
            return p.exists() and p.stat().st_size > 0 and (not a.force or p.stat().st_mtime >= started)

        pending = [f for f in frames if not done(f)]
        if not pending:
            print(f"== {sid}: all {len(frames)} frame(s) already rendered")
            pending = frames[:1]                                 # still run once so render.json is refreshed
        size = chunk if chunk > 0 else len(pending)
        stalls = 0
        while pending:
            g = pending[:size]
            args = ["--clip", str(clip), "--shot", sid, "--mode", "render", "--quality", a.quality, "--step", str(step), "--frames", f"{g[0]}-{g[-1]}"]
            if a.force and not all(done(f) for f in g):
                args.append("--force")
            if a.percent:
                args += ["--percent", str(a.percent)]
            if a.samples:
                args += ["--samples", str(a.samples)]
            r = _blender(ROOT / "tools" / "blender" / "run_shot.py", args)
            left = [f for f in g if not done(f)]
            if r == 0 and (not left or len(g) == 1):
                pending = pending[len(g):]
                continue
            if r == 3:                                           # the shot script itself failed: smaller chunks will not help
                print(f"== {sid}: the shot did not build; fix blender/{sid}.py and run the same command again")
                rc = rc or r
                break
            got = len(g) - len(left)
            stalls = 0 if got else stalls + 1
            if stalls >= 3:
                print(f"== {sid}: Blender stopped three times without rendering a frame (exit {r}); run the same command again to resume")
                rc = rc or r or 1
                break
            size = max(2, min(size // 2, got) if got else size // 2)
            print(f"== {sid}: Blender stopped after {got} of {len(g)} frame(s) (exit {r}); carrying on in chunks of {size}. "
                  f"To start that way next time: --chunk {size} or RENDER_CHUNK={size} in .env", flush=True)
            pending = left + pending[len(g):]
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
        rows[-1] = ("shot plan", not err, f"{len(plan['shots'])} shot(s), {sum(len(x.get('views', [])) for x in plan['shots'])} views, world: {(plan.get('world') or {}).get('era', '?')}"
                    + (f", {len(err)} error(s)" if err else ""))
    timing = read_json(clip / "timing.json") if has("timing.json") else None
    premixed = bool(timing and timing.get("premixed"))        # voice --from-media: narration, music and effects arrive as one finished track
    rows.append(("audio plan", has("audio/plan.json") or premixed, "not needed: finished soundtrack imported" if premixed and not has("audio/plan.json") else ""))
    rows.append(("voice + timing", bool(timing), f"{timing['total_seconds']}s, source {timing['source']}" if timing else ""))
    rows.append(("sound cues", has("audio/cues.json") or premixed, f"{len(read_json(clip / 'audio/cues.json')['cues'])} cue(s)" if has("audio/cues.json")
                 else ("premixed track: audio/imported_mix.wav" if premixed else "")))
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
    # the first unfinished stage, so a new session knows where to pick up
    ids = [s["id"] for s in plan["shots"]]
    if not has("shotplan.json") or plan_mod.check(plan, read_json(clip / "script.json"))[0]:
        nxt = "direction: write or fix shotplan.json (director agent; python tools/clip.py plan-check prints what is wrong)"
    elif not timing or not (has("audio/cues.json") or premixed):
        nxt = "voice and sound (sound-designer agent): " + ("narration take" if not timing else "music, ambience, effects")
    elif [i for i in ids if not has(f"blender/{i}.py") or not has(f"review/{i}/checks.json")]:
        todo = [i for i in ids if not has(f"blender/{i}.py") or not has(f"review/{i}/checks.json")]
        nxt = f"build shots {', '.join(todo)} (one shot-builder agent per set: the set file first, then its shots)"
    elif [i for i in ids if not has(f"review/{i}/verdict.json") or read_json(clip / "review" / i / "verdict.json").get("verdict") != "pass"]:
        todo = [i for i in ids if not has(f"review/{i}/verdict.json") or read_json(clip / "review" / i / "verdict.json").get("verdict") != "pass"]
        nxt = f"review shots {', '.join(todo)} (frame-reviewer agent; apply fixes, at most two rounds)"
    elif [r for r in rows if r[0].startswith("shot ") and not r[1]]:
        nxt = f"animatic first (render --quality draft --step 3, assemble --tag animatic, watch it), then: python tools/clip.py render {clip.name}"
    elif not (clip / "final" / f"{clip.name}.mp4").exists():
        nxt = f"assemble: python tools/clip.py assemble {clip.name}, then qa and sample"
    else:
        nxt = "done: " + str((clip / "final" / f"{clip.name}.mp4").relative_to(ROOT) if clip.is_relative_to(ROOT) else clip / "final" / f"{clip.name}.mp4")
    if timing and timing.get("source") not in ("elevenlabs", "imported"):
        nxt += f"   [note: narration is '{timing.get('source')}', not a real take]"
    print(f"  next: {nxt}")
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
    for sid, s in timing["shots"].items():                   # the middle of every view (or start, middle, end of a shot without view data)
        a0, n = s["start_frame"], s["frames"]
        rep = clip / "review" / sid / "checks.json"
        views = read_json(rep).get("views", []) if rep.exists() else []
        if views:
            for i, v in enumerate(views):
                f1 = views[i + 1]["frame"] if i + 1 < len(views) else n
                times.append((a0 + (v["frame"] + f1) / 2) / fps)
        else:
            times += [(a0 + 3) / fps, (a0 + n // 2) / fps, (a0 + n - 4) / fps]
    ff = which_ffmpeg()
    for i, t in enumerate(times):
        run([ff, "-y", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", src, "-frames:v", "1", "-vf", "scale=360:-2", out / f"{i:02d}_{t:05.1f}s.png"], quiet=True)
    cols = 6
    rows = -(-len(times) // cols)
    lst = out / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\nduration 1\n" for p in sorted(out.glob("*.png"))), encoding="utf-8")
    run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf", f"tile={cols}x{rows}:padding=4", "-frames:v", "1", out / "sheet.png"], quiet=True)
    lst.unlink()
    print(f"samples: {len(times)} frames (one per view, in order, captions burnt in) -> {out / 'sheet.png'}")
    return 0


def cmd_cast(a):
    """What the character pack offers. With a name: that character's colours and parts (for costume recolor / hide)."""
    reg = read_json(ROOT / "config" / "cast.json")
    if a.rescan:
        load_env()
        return _blender(ROOT / "tools" / "blender" / "scan_pack.py", [])
    if a.name:
        ch = reg["characters"].get(a.name)
        if not ch:
            raise SystemExit(f"no '{a.name}' in the pack: {', '.join(reg['characters'])}")
        print(f"{a.name}: {ch['looks']}\n  period: {', '.join(ch['era'])}   height {ch['height_m']} m   robe: {ch['robe']}")
        print(f"  colours (costume.recolor keys): {', '.join(ch['colors'])}")
        print(f"  parts (costume.hide patterns): {', '.join(ch['parts'])}")
        for era, ad in ch.get("adapt", {}).items():
            print(f"  as {era}: hide {ad.get('hide')}; recolor {ad.get('recolor_hint')}. {ad.get('note', '')}")
        return 0
    for name, ch in reg["characters"].items():
        eras = ch["era"] + [f"({e})" for e in ch.get("adapt", {})]
        if a.era and not ("any" in ch["era"] or a.era in ch["era"] or a.era in ch.get("adapt", {})):
            continue
        print(f"  {name:<16} {', '.join(eras):<58} {ch['looks']}")
    print("\nwardrobe (costume.wear):")
    for name, w in reg["wardrobe"].items():
        if a.era and not ("any" in w["era"] or a.era in w["era"]):
            continue
        print(f"  {name:<12} {', '.join(w['era']):<58} {w['what']}")
    print("\n(period) = usable in that period with the costume recipe shown by `clip.py cast <Name>`. Pictures: packs/" + PACK_NAME + "/**/character-lineup*.png")
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
    sub.add_parser("doctor")
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
    for name in ("voice", "sound", "assemble", "qa", "materials"):
        p = sub.add_parser(name, add_help=False)
        p.add_argument("rest", nargs=argparse.REMAINDER)
    p = sub.add_parser("cast")
    p.add_argument("name", nargs="?")
    p.add_argument("--era")
    p.add_argument("--rescan", action="store_true", help="re-read part and colour names from the pack .blend into config/cast.json")
    p = sub.add_parser("stills")
    p.add_argument("clip")
    p.add_argument("shots", nargs="*")
    p.add_argument("--quality", choices=("draft", "preview", "final"), default="draft")
    p.add_argument("--seconds", type=float)
    p.add_argument("--save-blend", action="store_true")
    p.add_argument("--views", help="only these view ids (comma separated): a quick look at one framing")
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
    if a.cmd in ("voice", "sound", "assemble", "qa", "materials"):
        if a.cmd == "materials":
            import materials as m
        elif a.cmd == "voice":
            from audio import voice as m
        elif a.cmd == "sound":
            from audio import sound as m
        elif a.cmd == "assemble":
            import assemble as m
        else:
            import qa as m
        return m.main(a.rest)
    return {"setup": cmd_setup, "doctor": cmd_doctor, "voices": cmd_voices, "new": cmd_new, "plan-check": cmd_plan_check, "stills": cmd_stills,
            "render": cmd_render, "status": cmd_status, "assets": cmd_assets, "asset": cmd_asset, "sample": cmd_sample, "cast": cmd_cast, "bk-search": cmd_bk, "bk-fetch": cmd_bk}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
