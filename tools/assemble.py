"""Final assembly: rendered shots + narration + sound + captions -> one loudness-normalised MP4.

    python tools/clip.py assemble <clip> [--quality final|preview|draft] [--allow-missing] [--safe-area] [--no-captions]

1. Each shot's PNG frames become one MP4 clip with exactly the frame count the voice timing asked for.
2. Remotion places the clips on the timeline, mixes narration / music (ducked under the voice) / ambience / SFX,
   draws word-by-word captions inside the Shorts safe area and applies one finish (vignette, grain, fades).
3. FFmpeg normalises loudness in two passes (-14 LUFS, -1 dBTP) and writes H.264 + AAC 48 kHz.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FPS, ROOT, STYLE, clip_dir, db, load_env, norm_word, read_json, run, which_ffmpeg, write_json  # noqa: E402

QUALITIES = ("final", "preview", "draft")
V, A, C = STYLE["video"], STYLE["audio"], STYLE["captions"]


def find_render(clip: Path, shot: str, quality: str | None):
    for q in ([quality] if quality else QUALITIES):
        d = clip / "render" / shot / q
        meta = d / "render.json"
        if meta.exists():
            m = read_json(meta)
            if m.get("rendered", 0) > 0:
                return d, m
    return None, None


def encode_shot(clip: Path, shot: str, frames: int, quality: str | None, pub: Path, allow_missing: bool) -> dict:
    """PNG sequence -> MP4 with exactly `frames` frames at the project size and frame rate."""
    ff = which_ffmpeg()
    out = pub / "shots" / f"{shot}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    d, meta = find_render(clip, shot, quality)
    enc = ["-r", str(FPS), "-frames:v", str(frames), "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", "-an"]
    scale = f"scale={V['width']}:{V['height']}:flags=lanczos,setsar=1"
    if d is None:
        if not allow_missing:
            raise SystemExit(f"{shot}: no rendered frames (run `python tools/clip.py render {clip.name} {shot}`), or pass --allow-missing for a placeholder card")
        run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x20222A:s={V['width']}x{V['height']}:r={FPS}", *enc, out], quiet=True)
        return {"id": shot, "placeholder": True, "quality": None, "complete": False}
    pngs = sorted(d.glob("[0-9][0-9][0-9][0-9].png"))
    nums = [int(p.stem) for p in pngs]
    lst = d / "frames.txt"
    lines = []
    for i, p in enumerate(pngs):
        nxt = nums[i + 1] if i + 1 < len(nums) else frames + 1
        hold = max(1, nxt - nums[i])
        lines.append(f"file '{p.as_posix()}'\nduration {hold / FPS:.6f}")
    lines.append(f"file '{pngs[-1].as_posix()}'")          # the concat demuxer needs the last file repeated
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf", f"fps={FPS},{scale},tpad=stop_mode=clone:stop_duration=2", *enc, out], quiet=True)
    complete = bool(meta.get("complete")) and meta.get("step", 1) == 1 and meta.get("frames") == frames
    if meta.get("frames") != frames:
        print(f"warn: {shot} was rendered for {meta.get('frames')} frames but the timing now needs {frames}: re-render it")
    return {"id": shot, "placeholder": False, "quality": meta.get("quality"), "step": meta.get("step", 1), "complete": complete,
            "source_size": [meta.get("width"), meta.get("height")]}


def caption_pages(words: list[dict]) -> list[dict]:
    """Group words into short pages that read at a glance; break at sentence ends and at silences."""
    pages, cur = [], []

    def close():
        nonlocal cur
        if cur:
            pages.append(cur)
        cur = []

    for i, w in enumerate(words):
        text = w["text"].strip('"“”')
        length = sum(len(x["text"]) for x in cur) + len(cur) + len(text)
        if cur and (length > C["max_chars_per_page"] or w["start"] - cur[-1]["end"] > C["combine_within_ms"] / 1000.0 or w["shot"] != cur[-1]["shot"]):
            close()
        cur.append({"text": text.upper() if C.get("uppercase") else text, "start": w["start"], "end": w["end"], "shot": w["shot"]})
        if re.search(r"[.!?][\"”']?$", w["text"]):
            close()
    close()
    out = []
    for k, pg in enumerate(pages):
        start = pg[0]["start"] - 0.03
        end = pg[-1]["end"] + 0.22
        if k + 1 < len(pages):
            end = min(end, pages[k + 1][0]["start"] - 0.03)
        f0, f1 = max(0, int(round(start * FPS))), int(round(end * FPS))
        ws = []
        for j, x in enumerate(pg):
            a = int(round(x["start"] * FPS))
            b = int(round((pg[j + 1]["start"] if j + 1 < len(pg) else x["end"]) * FPS))
            ws.append({"text": x["text"], "from": max(f0, a), "to": max(a + 1, b)})
        out.append({"from": f0, "to": max(f0 + 2, f1), "words": ws})
    return out


def music_gain(words: list[dict], total_frames: int) -> list[float]:
    """Per-frame music multiplier: full between phrases, pulled down while the narrator speaks."""
    low = db(A["music_duck_db"])
    att, rel = A["duck_attack_s"], A["duck_release_s"]
    act = [0.0] * total_frames
    for w in words:
        a, b = w["start"], w["end"]
        f0, f1 = int((a - att) * FPS) - 1, int((b + rel) * FPS) + 1
        for f in range(max(0, f0), min(total_frames, f1 + 1)):
            t = f / FPS
            v = 1.0 if a <= t <= b else (max(0.0, 1 - (a - t) / att) if t < a else max(0.0, 1 - (t - b) / rel))
            act[f] = max(act[f], v)
    return [round(1.0 - v * (1.0 - low), 4) for v in act]


def remotion_render(props_path: Path, public: Path, out: Path, concurrency: int | None):
    rdir = ROOT / "remotion"
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise SystemExit("Node.js (npx) not found: install Node 20+ for the Remotion assembly")
    if not (rdir / "node_modules" / "remotion").exists():
        run([npm, "install", "--no-audit", "--no-fund"], cwd=rdir)
    cmd = [npx, "remotion", "render", "src/index.ts", "Short", out, f"--props={props_path}", f"--public-dir={public}", "--codec=h264", "--crf=16",
           "--pixel-format=yuv420p", "--audio-codec=aac", "--audio-bitrate=256k", "--color-space=bt709", "--log=warn"]
    if os.environ.get("REMOTION_CHROME"):
        cmd.append(f"--browser-executable={os.environ['REMOTION_CHROME']}")
    if concurrency:
        cmd.append(f"--concurrency={concurrency}")
    run(cmd, cwd=rdir)


def loudnorm(src: Path, dst: Path) -> dict:
    """Two-pass EBU R128 normalisation; video stream is copied untouched."""
    ff = which_ffmpeg()
    tgt = f"I={A['loudness_lufs']}:TP={A['true_peak_db']}:LRA=11"
    r = run([ff, "-hide_banner", "-nostats", "-i", src, "-af", f"loudnorm={tgt}:print_format=json", "-vn", "-f", "null", "-"], capture=True, quiet=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise SystemExit("loudnorm: could not read the measurement pass")
    j = json.loads(m.group(0))
    if float(j["input_i"]) < -60:
        shutil.copyfile(src, dst)
        return {"skipped": "audio is silent", **j}
    af = (f"loudnorm={tgt}:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}"
          f":offset={j['target_offset']}:linear=true:print_format=summary")
    run([ff, "-y", "-v", "error", "-i", src, "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", A["sample_rate"], "-ac", "2",
         "-movflags", "+faststart", dst], quiet=True)
    return j


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clip.py assemble")
    ap.add_argument("clip")
    ap.add_argument("--quality", choices=QUALITIES, help="which render to use (default: best available per shot)")
    ap.add_argument("--allow-missing", action="store_true", help="use a dark card for shots that are not rendered yet")
    ap.add_argument("--safe-area", action="store_true", help="draw the Shorts safe area on the video (review copies only)")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--concurrency", type=int)
    ap.add_argument("--tag", default="", help="suffix for the output file, e.g. animatic")
    a = ap.parse_args(argv)
    load_env()
    clip = clip_dir(a.clip)
    timing = read_json(clip / "timing.json")
    plan = read_json(clip / "shotplan.json")
    fdir = clip / "final"
    pub = fdir / "public"
    if pub.exists():
        shutil.rmtree(pub)
    (pub / "audio").mkdir(parents=True)
    total = timing["total_frames"]
    shots, report = [], []
    for s in plan["shots"]:
        t = timing["shots"][s["id"]]
        info = encode_shot(clip, s["id"], t["frames"], a.quality, pub, a.allow_missing)
        report.append(info)
        shots.append({"id": s["id"], "src": f"shots/{s['id']}.mp4", "from": t["start_frame"], "frames": t["frames"], "placeholder": info["placeholder"]})
    adir = clip / "audio"
    narration = None
    if (adir / "narration.wav").exists():
        shutil.copyfile(adir / "narration.wav", pub / "audio" / "narration.wav")
        narration = {"src": "audio/narration.wav", "volume": round(db(A["voice_gain_db"]), 4)}
    cues = []
    if (adir / "cues.json").exists():
        for c in read_json(adir / "cues.json")["cues"]:
            src = adir / c["file"]
            if not src.exists():
                print(f"warn: cue {c['id']} has no audio file, skipped")
                continue
            dst = pub / "audio" / c["file"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            f0 = int(round(c["start_s"] * FPS))
            fr = min(total - f0, int(round(c["duration_s"] * FPS)) + (0 if c["loop"] or c["kind"] == "music" else int(0.5 * FPS)))
            if fr <= 0:
                continue
            cues.append({"id": c["id"], "kind": c["kind"], "src": f"audio/{c['file']}", "from": f0, "frames": fr, "volume": round(db(c["gain_db"]), 4),
                         "loop": bool(c["loop"]), "fadeInFrames": int(round(c.get("fade_in_s", 0) * FPS)), "fadeOutFrames": int(round(c.get("fade_out_s", 0) * FPS))})
    props = {
        "fps": FPS, "width": V["width"], "height": V["height"], "durationInFrames": total, "shots": shots, "narration": narration, "cues": cues,
        "musicGain": music_gain(timing["words"], total),
        "captions": [] if a.no_captions else caption_pages(timing["words"]),
        "captionStyle": {"enabled": bool(C["enabled"]) and not a.no_captions, "fontFamily": C["font_family"], "fontWeight": C["font_weight"],
                         "fontSizePx": C["font_size_px"], "centerYFraction": C["center_y_fraction"], "color": C["color"], "activeColor": C["active_color"],
                         "strokeColor": C["stroke_color"], "strokePx": C["stroke_px"], "uppercase": bool(C.get("uppercase"))},
        "safeArea": STYLE["safe_area"],
        "finish": {"vignette": STYLE["finish"]["vignette"], "grain": STYLE["finish"]["grain"], "fadeInFrames": STYLE["finish"]["fade_in_frames"],
                   "fadeOutFrames": STYLE["finish"]["fade_out_frames"]},
        "showSafeArea": bool(a.safe_area),
    }
    props_path = write_json(fdir / "props.json", props)
    slug = clip.name + (f"_{a.tag}" if a.tag else "")
    mix = fdir / f"{slug}_premix.mp4"
    out = fdir / f"{slug}.mp4"
    remotion_render(props_path, pub, mix, a.concurrency)
    ln = loudnorm(mix, out)
    mix.unlink(missing_ok=True)
    write_json(fdir / f"{slug}.assembly.json", {"output": out.name, "shots": report, "cues": [c["id"] for c in cues], "captions_pages": len(props["captions"]),
                                               "loudnorm_input": ln, "voice": timing.get("voice"), "timing_source": timing.get("source")})
    print(f"assembled: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
