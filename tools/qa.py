"""Measure the finished file against the delivery spec. Everything here is a number; taste is the reviewer's job.

    python tools/clip.py qa <clip> [--tag animatic]
Exit code 0 = deliverable, 1 = at least one failure. Writes <clip>/final/<name>.qa.json.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FPS, STYLE, clip_dir, ffprobe_json, read_json, run, which_ffmpeg, write_json  # noqa: E402

V, A, S = STYLE["video"], STYLE["audio"], STYLE["shots"]


def loudness(path) -> dict:
    r = run([which_ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-vn", "-f", "null", "-"], capture=True, quiet=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    tp = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    lra = re.search(r"LRA:\s+(-?[\d.]+) LU", tail)
    return {"integrated_lufs": float(i.group(1)) if i else None, "true_peak_db": float(tp.group(1)) if tp else None, "lra": float(lra.group(1)) if lra else None}


def black_spans(path) -> list[tuple[float, float]]:
    r = run([which_ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-vf", "blackdetect=d=0.4:pix_th=0.06", "-an", "-f", "null", "-"], capture=True, quiet=True)
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clip.py qa")
    ap.add_argument("clip")
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    clip = clip_dir(a.clip)
    slug = clip.name + (f"_{a.tag}" if a.tag else "")
    path = clip / "final" / f"{slug}.mp4"
    if not path.exists():
        raise SystemExit(f"no final file at {path}: run assemble first")
    timing = read_json(clip / "timing.json")
    asm = read_json(clip / "final" / f"{slug}.assembly.json") if (clip / "final" / f"{slug}.assembly.json").exists() else {}
    fails, warns, facts = [], [], {}
    p = ffprobe_json(path)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    au = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    dur = float(p["format"]["duration"])
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    facts.update(width=v["width"], height=v["height"], fps=round(num / den, 3), seconds=round(dur, 3), video_codec=v["codec_name"], pix_fmt=v.get("pix_fmt"),
                 size_mb=round(int(p["format"]["size"]) / 1e6, 2))
    if (v["width"], v["height"]) != (V["width"], V["height"]):
        fails.append(f"size is {v['width']}x{v['height']}, expected {V['width']}x{V['height']}")
    if abs(num / den - FPS) > 0.01:
        fails.append(f"frame rate is {num / den:.3f}, expected {FPS}")
    if dur > V["max_seconds"] + 0.05:
        fails.append(f"duration {dur:.2f}s is over the {V['max_seconds']}s limit")
    lo, hi = V["target_seconds"]
    if not lo <= dur <= hi:
        warns.append(f"duration {dur:.1f}s is outside the {lo}-{hi}s target")
    if v["codec_name"] != "h264" or v.get("pix_fmt") != "yuv420p":
        fails.append(f"video is {v['codec_name']}/{v.get('pix_fmt')}, expected h264/yuv420p")
    if abs(dur - timing["total_seconds"]) > 0.1:
        fails.append(f"duration {dur:.2f}s does not match the timing ({timing['total_seconds']}s)")
    if au is None:
        fails.append("no audio stream")
    else:
        facts.update(audio_codec=au["codec_name"], sample_rate=int(au["sample_rate"]), channels=au.get("channels"))
        if au["codec_name"] != "aac" or int(au["sample_rate"]) != A["sample_rate"]:
            fails.append(f"audio is {au['codec_name']} {au['sample_rate']} Hz, expected aac {A['sample_rate']} Hz")
        ln = loudness(path)
        facts["loudness"] = ln
        if ln["integrated_lufs"] is None or ln["integrated_lufs"] < -60:
            fails.append("audio is silent")
        else:
            if abs(ln["integrated_lufs"] - A["loudness_lufs"]) > 1.0:
                fails.append(f"loudness {ln['integrated_lufs']} LUFS, target {A['loudness_lufs']} +/- 1")
            if ln["true_peak_db"] is not None and ln["true_peak_db"] > A["true_peak_db"] + 0.5:
                fails.append(f"true peak {ln['true_peak_db']} dBFS, limit {A['true_peak_db']}")
    # shots and cuts
    shots = timing["shots"]
    n = len(shots)
    facts["shots"] = n
    facts["seconds_per_shot"] = [s["seconds"] for s in shots.values()]
    if n > S["hard_max"]:
        fails.append(f"{n} shots: over the hard limit {S['hard_max']}")
    elif not S["target_count"][0] <= n <= S["target_count"][1]:
        warns.append(f"{n} shots (aim {S['target_count'][0]}-{S['target_count'][1]})")
    words = timing["words"]
    ids = list(shots)
    for i in range(1, n):
        cut = shots[ids[i]]["start_frame"] / FPS
        before = max(w["end"] for w in words if w["shot"] == ids[i - 1])
        after = min(w["start"] for w in words if w["shot"] == ids[i])
        if not (before - 1.5 / FPS <= cut <= after + 1.5 / FPS):
            fails.append(f"cut into {ids[i]} at {cut:.2f}s lands inside a word ({before:.2f}-{after:.2f}s is the gap)")
    if sum(s["frames"] for s in shots.values()) != timing["total_frames"]:
        fails.append("shot frame counts do not add up to the film length")
    # what the picture is made of
    for s in asm.get("shots", []):
        if s.get("placeholder"):
            fails.append(f"{s['id']}: placeholder card, not a rendered shot")
        elif s.get("quality") != "final" or not s.get("complete"):
            warns.append(f"{s['id']}: {s.get('quality')} render" + (f", every {s.get('step')}th frame" if s.get("step", 1) > 1 else "") + " - not the final-quality render")
    if timing.get("source") != "elevenlabs":
        warns.append(f"narration is '{timing.get('source')}', not an ElevenLabs take")
    cues = read_json(clip / "audio" / "cues.json") if (clip / "audio" / "cues.json").exists() else {}
    if cues.get("provider") == "mock":
        warns.append("music and sound effects are mock placeholders")
    fi, fo = STYLE["finish"]["fade_in_frames"] / FPS, STYLE["finish"]["fade_out_frames"] / FPS
    for b0, b1 in black_spans(path):
        if b0 > fi + 0.2 and b1 < dur - fo - 0.2:
            warns.append(f"black picture from {b0:.2f}s to {b1:.2f}s: intended?")
    facts["black_spans"] = black_spans(path)
    ok = not fails
    write_json(clip / "final" / f"{slug}.qa.json", {"file": path.name, "ok": ok, "failures": fails, "warnings": warns, "facts": facts})
    print(f"QA {'PASS' if ok else 'FAIL'}: {path.name}  {facts['width']}x{facts['height']} {facts['fps']}fps {facts['seconds']}s  "
          f"{facts.get('loudness', {}).get('integrated_lufs')} LUFS  {n} shots")
    for f in fails:
        print("  FAIL:", f)
    for w in warns:
        print("  warn:", w)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
