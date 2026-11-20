"""Sound effects, ambience and music from ElevenLabs, placed on the voice timing.

Reads <clip>/audio/plan.json (written by the sound-designer agent) and <clip>/timing.json.
Writes audio/sfx/*.wav, audio/amb/*.wav, audio/music.wav and audio/cues.json (every sound with its start time and gain).
Generated files are kept: a sound is only generated again when its prompt changes or --retake is given.

    python tools/clip.py sound <clip> [--mock] [--retake] [--only sfx|ambience|music]
"""
from __future__ import annotations

import argparse
import array
import hashlib
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT, STYLE, clip_dir, load_env, norm_word, read_json, run, which_ffmpeg, words_of, write_json  # noqa: E402

from audio import eleven  # noqa: E402
from audio.voice import SR, write_wav  # noqa: E402

A = STYLE["audio"]


def _hash(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _to_wav(src: Path, dst: Path, stereo: bool = True):
    run([which_ffmpeg(), "-y", "-v", "error", "-i", src, "-ac", 2 if stereo else 1, "-ar", SR, "-c:a", "pcm_s16le", dst], quiet=True)


def _mock(kind: str, seconds: float, seed: int) -> array.array:
    """Placeholder audio so the mix can be assembled and checked without the API: noise burst, soft noise bed, or a pad."""
    rnd = random.Random(seed)
    n = int(seconds * SR)
    out = array.array("h", bytes(2 * n))
    if kind == "sfx":
        lp = 0.0
        for i in range(n):
            x = i / max(1, n)
            lp += 0.25 * (rnd.uniform(-1, 1) - lp)
            out[i] = int(26000 * lp * math.exp(-5 * x) * min(1.0, i / 200))
    elif kind == "ambience":
        lp = 0.0
        for i in range(n):
            lp += 0.02 * (rnd.uniform(-1, 1) - lp)
            edge = min(1.0, i / (0.5 * SR), (n - i) / (0.5 * SR))
            out[i] = int(30000 * lp * edge)
    else:
        notes = [110.0, 164.81, 220.0, 261.63]
        for i in range(n):
            t = i / SR
            v = sum(math.sin(2 * math.pi * f * t + k) * (0.6 + 0.4 * math.sin(2 * math.pi * (0.07 + 0.03 * k) * t)) for k, f in enumerate(notes))
            out[i] = int(4200 * v * min(1.0, t / 1.5))
    return out


def resolve_time(at: dict, timing: dict) -> float:
    """Where a cue starts on the film timeline (seconds)."""
    if "time" in at:
        return float(at["time"])
    if "shot" in at and "word" not in at:
        s = timing["shots"][at["shot"]]
        t = float(at.get("t", 0.0))
        return s["start_s"] + (t if t >= 0 else s["seconds"] + t)
    if "word" in at:
        target = words_of(at["word"])
        ws = [w for w in timing["words"] if not at.get("shot") or w["shot"] == at["shot"]]
        norm = [norm_word(w["text"]) for w in ws]
        hits = [i for i in range(len(norm) - len(target) + 1) if norm[i:i + len(target)] == target]
        if not hits:
            raise SystemExit(f"cue anchor word '{at['word']}' is not in the narration" + (f" of {at['shot']}" if at.get("shot") else ""))
        i = hits[min(len(hits), int(at.get("nth", 1))) - 1]
        w = ws[i + len(target) - 1] if at.get("edge") == "end" else ws[i]
        return max(0.0, (w["end"] if at.get("edge") == "end" else w["start"]) + float(at.get("offset_s", 0.0)))
    raise SystemExit(f"cue 'at' must have time, shot+t, or word: {at}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clip.py sound")
    ap.add_argument("clip")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--retake", action="store_true")
    ap.add_argument("--only", choices=("sfx", "ambience", "music"))
    a = ap.parse_args(argv)
    load_env()
    clip = clip_dir(a.clip)
    adir = clip / "audio"
    plan = read_json(adir / "plan.json") if (adir / "plan.json").exists() else {}
    timing = read_json(clip / "timing.json")
    cfg = read_json(ROOT / "config" / "voices.json")
    prev = {c["id"]: c for c in (read_json(adir / "cues.json").get("cues", []) if (adir / "cues.json").exists() else [])}
    cues, chars = [], 0
    total = timing["total_seconds"]

    def want(kind):
        return a.only in (None, kind)

    def make(kind, cid, prompt, seconds, loop, path: Path):
        nonlocal chars
        h = _hash(kind, prompt, round(seconds, 1), loop, "mock" if a.mock else "real")
        old = prev.get(cid)
        if path.exists() and old and old.get("hash") == h and not a.retake:
            return h, "kept"
        if not want(kind):
            if path.exists():
                return (old or {}).get("hash", h), "kept"
            return h, "skipped"
        path.parent.mkdir(parents=True, exist_ok=True)
        if a.mock:
            write_wav(path, _mock(kind, seconds, int(h[:6], 16)))
        else:
            tmp = path.with_suffix(".mp3")
            if kind == "music":
                tmp.write_bytes(eleven.music(prompt, int(seconds * 1000), cfg["music"]["model_id"], cfg["music"].get("instrumental", True)))
            else:
                tmp.write_bytes(eleven.sound_effect(prompt, seconds, loop, cfg["sfx"].get("prompt_influence", 0.4), cfg["sfx"]["model_id"]))
                chars += len(prompt)
            _to_wav(tmp, path)
        return h, "made"

    for s in plan.get("sfx", []):
        t = resolve_time(s["at"], timing)
        dur = float(s.get("duration_s", 1.5))
        p = adir / "sfx" / f"{s['id']}.wav"
        h, st = make("sfx", s["id"], s["prompt"], dur, False, p)
        if st != "skipped":
            cues.append({"id": s["id"], "kind": "sfx", "file": f"sfx/{s['id']}.wav", "start_s": round(t, 3), "duration_s": dur,
                         "gain_db": float(s.get("gain_db", A["sfx_gain_db"])), "loop": False, "fade_in_s": 0.0, "fade_out_s": float(s.get("fade_out_s", 0.08)),
                         "prompt": s["prompt"], "hash": h})
            print(f"sfx {s['id']:<22} {st:<5} at {t:6.2f}s")
    for am in plan.get("ambience", []):
        ids = [x for x in am.get("shots", []) if x in timing["shots"]] or list(timing["shots"])
        t0 = min(timing["shots"][x]["start_s"] for x in ids)
        t1 = max(timing["shots"][x]["end_s"] for x in ids)
        dur = min(30.0, max(8.0, float(am.get("seconds", 20.0))))
        p = adir / "amb" / f"{am['id']}.wav"
        h, st = make("ambience", am["id"], am["prompt"], dur, True, p)
        if st != "skipped":
            cues.append({"id": am["id"], "kind": "ambience", "file": f"amb/{am['id']}.wav", "start_s": round(t0, 3), "duration_s": round(t1 - t0, 3),
                         "gain_db": float(am.get("gain_db", A["ambience_gain_db"])), "loop": True, "fade_in_s": 0.5 if t0 > 0.01 else 0.15, "fade_out_s": 0.6,
                         "prompt": am["prompt"], "hash": h})
            print(f"amb {am['id']:<22} {st:<5} {t0:6.2f}-{t1:6.2f}s")
    mu = plan.get("music") or {}
    if mu.get("prompt") and mu.get("enabled", True):
        p = adir / "music.wav"
        h, st = make("music", "music", mu["prompt"], total + 1.0, False, p)
        if st != "skipped":
            cues.append({"id": "music", "kind": "music", "file": "music.wav", "start_s": float(mu.get("start_s", 0.0)), "duration_s": total,
                         "gain_db": float(mu.get("gain_db", A["music_gain_db"])), "loop": False, "fade_in_s": A["music_fade_in_s"], "fade_out_s": A["music_fade_out_s"],
                         "prompt": mu["prompt"], "hash": h})
            print(f"music {'':<20} {st:<5} {total + 1.0:.1f}s")
    write_json(adir / "cues.json", {"provider": "mock" if a.mock else "elevenlabs", "cues": cues})
    print(f"sound: {len(cues)} cue(s) -> {adir / 'cues.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
