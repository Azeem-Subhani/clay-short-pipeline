"""Build a synthetic clip that uses every shot-to-shot transition, so the assembly can be tested without Blender.

    py -3 tools/tests/integration/make_transition_test.py [--run] [--clean] [--word-over-cut]

Makes output/clips/_itest-transitions/ with a shot plan (seven shots, six transitions: whip, dissolve, dip, flash, wipe, match),
a timing.json shaped like a real one, coloured test frames with large moving shapes (so direction and blur are visible) written as
render/<shot>/final/NNNN.png + render.json, and a narration track of tone bursts on the word times.
--run   also sets the clip to autonomous mode, assembles and QAs it, and writes a contact sheet around every boundary
--clean deletes the clip folder
--word-over-cut   puts a word across the wipe boundary, to check that QA warns about it
Standard library and FFmpeg only.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from common import FPS, which_ffmpeg  # noqa: E402

SLUG = "_itest-transitions"
CLIP = ROOT / "output" / "clips" / SLUG
W, H = 540, 960                       # source frames; assemble scales them up to 1080x1920
SHOT_FRAMES = 72
GAP = 0.45                            # quiet seconds around each boundary
COLOURS = ["0x2a6f97", "0xc1121f", "0x2d6a4f", "0xe9c46a", "0x6a4c93", "0xe76f51", "0x264653"]
TRANSITIONS = [None,
               {"type": "whip", "dur": 0.4, "dir": "left"},
               {"type": "dissolve", "dur": 0.5},
               {"type": "dip", "dur": 0.4},
               {"type": "flash", "dur": 0.12},
               {"type": "wipe", "dur": 0.4, "dir": "right"},
               {"type": "match"}]
FONT = "C\\:/Windows/Fonts/arialbd.ttf"


def make_frames(i: int, sid: str, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    col = COLOURS[i]
    vf = (f"drawgrid=w=90:h=90:t=3:c=black@0.45,"
          f"drawbox=x='mod(t*220,{W})':y=0:w=60:h={H}:color=white@0.85:t=fill,"
          f"drawbox=x=0:y='mod(t*150,{H})':w={W}:h=40:color=black@0.7:t=fill,"
          f"drawtext=fontfile='{FONT}':text='{i + 1}':fontsize=520:fontcolor=white:borderw=14:bordercolor=black:x=(w-tw)/2:y=(h-th)/2-230")
    subprocess.run([which_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={col}:s={W}x{H}:r={FPS}", "-vf", vf, "-frames:v", str(SHOT_FRAMES),
                    "-start_number", "1", str(out / "%04d.png")], check=True)
    (out / "render.json").write_text(json.dumps({"shot": sid, "frames": SHOT_FRAMES, "fps": FPS, "step": 1, "quality": "final", "views": ["v"], "rendered": SHOT_FRAMES,
                                                 "expected": SHOT_FRAMES, "width": W, "height": H, "complete": True}, indent=1), encoding="utf-8")


def build(word_over_cut: bool):
    if CLIP.exists():
        shutil.rmtree(CLIP)
    ids = [f"sh{i + 1:02d}" for i in range(len(COLOURS))]
    plan = {"slug": SLUG, "world": {"era": "synthetic"}, "cast": [], "sets": [],
            "transitions": {"default": "cut"},
            "shots": [{"id": sid, **({"transition_in": TRANSITIONS[i]} if TRANSITIONS[i] else {})} for i, sid in enumerate(ids)]}
    (CLIP).mkdir(parents=True)
    (CLIP / "shotplan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    shots, words = {}, []
    for i, sid in enumerate(ids):
        start = i * SHOT_FRAMES / FPS
        end = (i + 1) * SHOT_FRAMES / FPS
        shots[sid] = {"index": i, "start_s": round(start, 3), "end_s": round(end, 3), "vo_start_s": round(start, 3), "vo_end_s": round(end, 3), "hold_after_s": 0.0,
                      "start_frame": i * SHOT_FRAMES, "frames": SHOT_FRAMES, "seconds": round(SHOT_FRAMES / FPS, 4)}
        a, b = start + (GAP if i else 0.1), end - GAP
        if word_over_cut and i == 4:          # the last word of shot 5 runs across the wipe into shot 6
            b = end + 0.4
        n = 3
        step = (b - a) / n
        for k in range(n):
            words.append({"i": len(words), "text": f"word{len(words)}", "start": round(a + k * step, 3), "end": round(a + (k + 1) * step - 0.06, 3), "shot": sid})
    total = len(ids) * SHOT_FRAMES
    timing = {"fps": FPS, "source": "mock", "total_seconds": round(total / FPS, 3), "total_frames": total, "speech_seconds": 14.0, "words_per_minute": 170.0,
              "lead_in_s": 0.1, "tail_s": 0.0, "notes": [], "voice": {"provider": "mock", "voice": "tone"}, "shots": shots, "words": words}
    (CLIP / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")
    for i, sid in enumerate(ids):
        make_frames(i, sid, CLIP / "render" / sid / "final")
    # narration: tone bursts on the words, so QA's speech-onset check has something real to measure
    (CLIP / "audio").mkdir()
    sr = 48000
    n = int(total / FPS * sr)
    pcm = [0] * n
    for w in words:
        for s in range(int(w["start"] * sr), min(n, int(w["end"] * sr))):
            ramp = min(1.0, (s - w["start"] * sr) / 240, (w["end"] * sr - s) / 240)
            pcm[s] = int(9000 * max(0.0, ramp) * math.sin(2 * math.pi * 220 * s / sr))
    with wave.open(str(CLIP / "audio" / "narration.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(struct.pack(f"<{n}h", *pcm))
    print(f"built {CLIP}")


def py(*args):
    return subprocess.run(["py", "-3", *map(str, args)] if sys.platform == "win32" else ["python3", *map(str, args)], cwd=ROOT)


def sheet():
    """One strip per boundary: the frames from 7 before to 7 after, scaled down, tiled 5 wide."""
    ff = which_ffmpeg()
    film = CLIP / "final" / f"{SLUG}.mp4"
    out = CLIP / "final" / "contact"
    out.mkdir(exist_ok=True)
    for i in range(1, len(COLOURS)):
        b = i * SHOT_FRAMES
        f0 = b - 8
        vf = f"select='between(n,{f0},{f0 + 15})',scale=216:384,tile=8x2:padding=4:color=white"
        subprocess.run([ff, "-y", "-v", "error", "-i", str(film), "-vf", vf, "-frames:v", "1", str(out / f"boundary{i}.png")], check=True)
    print(f"contact sheets in {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--word-over-cut", action="store_true")
    a = ap.parse_args()
    if a.clean:
        shutil.rmtree(CLIP, ignore_errors=True)
        print(f"removed {CLIP}")
        return 0
    build(a.word_over_cut)
    if a.run:
        py("tools/clip.py", "gate", SLUG, "--autonomous", "--reason", "synthetic transition test")
        py("tools/clip.py", "assemble", SLUG)
        py("tools/clip.py", "qa", SLUG)
        sheet()
    return 0


if __name__ == "__main__":
    sys.exit(main())
