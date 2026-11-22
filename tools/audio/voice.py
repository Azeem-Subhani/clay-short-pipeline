"""Narration: one ElevenLabs take with timestamps -> word timings -> shot lengths.

The voice take is the clock of the whole film: every shot's frame count comes from where its words actually land.
Pauses the plan asks for (hold_after_s) are inserted as real silence between shots, so they are exact.

    python tools/clip.py voice <clip>            real take (needs ELEVENLABS_API_KEY)
    python tools/clip.py voice <clip> --mock     offline placeholder with plausible timing (for dry runs and tests)

Writes <clip>/audio/narration_raw.mp3, narration.wav, alignment_raw.json and <clip>/timing.json.
An approved take is kept: re-running does not call the API again unless --retake is given.
"""
from __future__ import annotations

import argparse
import array
import base64
import datetime
import math
import re
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (FPS, ROOT, STYLE, clip_dir, display_words, load_env, norm_word, read_json, run, strip_tags, which_ffmpeg,  # noqa: E402
                    words_of, write_json)

from audio import eleven  # noqa: E402

SR = STYLE["audio"]["sample_rate"]
LEAD_IN = 0.10
PAUSE_TAGS = {"[pause]": 0.5, "[short pause]": 0.3, "[long pause]": 1.0}


# ----------------------------------------------------------------------------- voice choice
def voices_config() -> dict:
    cfg = read_json(ROOT / "config" / "voices.json")
    local = ROOT / "config" / "voices.local.json"
    if local.exists():
        for name, v in read_json(local).get("voices", {}).items():
            cfg["voices"].setdefault(name, {}).update(v)
    return cfg


def pick_voice(cfg: dict, fmt: str, want: str | None = None, today: datetime.date | None = None) -> tuple[str, dict]:
    """First usable voice of the format's shortlist (standardized on Alex). Default voices past retirement fall to their replacement."""
    today = today or datetime.date.today()
    default_voice = cfg.get("tts", {}).get("default_voice", "Alex")
    names = [want] if want else cfg.get("formats", {}).get(fmt, {}).get("voices") or [default_voice]
    tried = []
    for name in names:
        v = cfg["voices"].get(name)
        if v is None:
            if want and re.fullmatch(r"[A-Za-z0-9]{16,32}", want):
                return want, {"voice_id": want, "kind": "explicit id"}
            tried.append(f"{name}: not in config/voices.json")
            continue
        if v.get("expires") and today > datetime.date.fromisoformat(v["expires"]) and v.get("replacement"):
            tried.append(f"{name}: retired by ElevenLabs on {v['expires']}, using {v['replacement']}")
            name, v = v["replacement"], cfg["voices"][v["replacement"]]
        if v.get("unavailable"):
            tried.append(f"{name}: marked unavailable on this account")
            continue
        if v.get("voice_id"):
            if tried:
                print("voice:", "; ".join(tried))
            return name, v
        tried.append(f"{name}: no voice_id yet (library voice - run `python tools/clip.py voices`)")
    raise SystemExit("no usable voice for format '%s':\n  " % fmt + "\n  ".join(tried))


# ----------------------------------------------------------------------------- text for the model
def for_model(text: str, caps: dict) -> str:
    """Adapt tagged narration to what the chosen model understands."""
    if caps.get("audio_tags"):
        return re.sub(r"<break[^>]*>", "[pause]", text)
    out = text
    for tag, sec in PAUSE_TAGS.items():
        out = out.replace(tag, f'<break time="{sec:.1f}s" />' if caps.get("ssml_break") else " ... ")
    return re.sub(r"\s+", " ", re.sub(r"\[[^\[\]]*\]", " ", out)).strip()


def alignment_to_words(al: dict) -> list[dict]:
    """ElevenLabs character timings -> spoken words. Audio tags [..] and SSML <..> are not words."""
    chars, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, depth = [], None, 0

    def flush():
        nonlocal cur
        if cur and norm_word(cur["text"]):
            words.append(cur)
        cur = None

    for c, a, b in zip(chars, st, en):
        for ch in c:                       # a "character" entry can hold more than one code point
            if ch in "[<":
                flush()
                depth += 1
                continue
            if ch in "]>":
                depth = max(0, depth - 1)
                continue
            if depth:
                continue
            if ch.isspace():
                flush()
                continue
            if cur is None:
                cur = {"text": ch, "start": float(a), "end": float(b)}
            else:
                cur["text"] += ch
                cur["end"] = float(b)
    flush()
    return words


# ----------------------------------------------------------------------------- mock take
def mock_take(shot_texts: list[str], seed: int = 7) -> tuple[list[dict], array.array]:
    """Offline stand-in for the narrator: soft tone blips, one per word, at the target energetic pace (about 230 wpm, 220-240 wpm range)."""
    import random
    rnd = random.Random(seed)
    t = 0.20
    words, samples = [], array.array("h")
    for text in shot_texts:
        for w in display_words(text):
            core = norm_word(w)
            d = 0.079 + 0.034 * len(core) + rnd.uniform(-0.01, 0.01)
            words.append({"text": w, "start": round(t, 3), "end": round(t + d, 3)})
            t += d + 0.026
            if w[-1:] in ".!?\"":
                t += 0.17
            elif w[-1:] in ",;:—":
                t += 0.075
    total = t + 0.25
    n = int(total * SR)
    buf = [0.0] * n
    for k, w in enumerate(words):
        a, b = int(w["start"] * SR), int(w["end"] * SR)
        f = 150 + (hash(norm_word(w["text"])) % 90)
        for i in range(a, min(b, n)):
            x = (i - a) / max(1, b - a)
            env = math.sin(math.pi * x) ** 0.6
            ph = 2 * math.pi * f * (i - a) / SR
            buf[i] += 0.22 * env * (math.sin(ph) + 0.35 * math.sin(2 * ph) + 0.15 * math.sin(3 * ph))
    samples.extend(int(max(-1, min(1, v)) * 32000) for v in buf)
    return words, samples


# ----------------------------------------------------------------------------- pcm helpers
def read_wav(path) -> array.array:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2, "expected 48 kHz mono 16-bit"
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
    return a


def write_wav(path, samples: array.array):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(samples.tobytes())


def _fade(seg: array.array, ms: float = 6.0):
    n = min(len(seg) // 2, int(SR * ms / 1000))
    for i in range(n):
        k = i / n
        seg[i] = int(seg[i] * k)
        seg[-1 - i] = int(seg[-1 - i] * k)
    return seg


# ----------------------------------------------------------------------------- timing
def build_timing(raw_words: list[dict], raw: array.array, shots: list[dict], source: str, meta: dict) -> tuple[dict, array.array]:
    """Cut the take at shot boundaries, insert the planned holds as silence, and derive frame-accurate shot lengths."""
    V, A = STYLE["video"], STYLE["audio"]
    counts = [len(words_of(s["vo_text"])) for s in shots]
    if sum(counts) != len(raw_words):
        raise SystemExit(f"timing: {len(raw_words)} aligned words but the plan has {sum(counts)}")
    idx, k = [], 0
    for c in counts:
        idx.append((k, k + c))
        k += c
    raw_dur = len(raw) / SR
    start = max(0.0, raw_words[0]["start"] - 0.06)
    end = min(raw_dur, raw_words[-1]["end"] + 0.30)
    bounds = [start]
    for i in range(1, len(shots)):
        a, b = raw_words[idx[i][0] - 1]["end"], raw_words[idx[i][0]]["start"]
        bounds.append((a + b) / 2 if b > a else a)
    bounds.append(end)
    seg = [bounds[i + 1] - bounds[i] for i in range(len(shots))]
    holds = [max(0.0, float(s.get("hold_after_s", 0) or 0)) for s in shots]
    tail = float(A["tail_seconds"]) + holds[-1]
    holds[-1] = 0.0
    speech = sum(seg)
    budget = V["max_seconds"] - 0.05
    notes = []
    total = LEAD_IN + speech + sum(holds) + tail
    if total > budget:
        over = total - budget
        room = sum(holds) + max(0.0, tail - 0.4)
        if room >= over:
            k = 1.0 - over / room
            holds = [h * k for h in holds]
            tail = 0.4 + max(0.0, tail - 0.4) * k
            notes.append(f"holds shortened by {over:.2f}s to stay under {V['max_seconds']}s")
        else:
            raise SystemExit(
                f"narration alone runs {LEAD_IN + speech + 0.4:.1f}s: over the {V['max_seconds']}s limit even with no holds.\n"
                "Trim pauses/tags, tighten the script (target 170-198 words for 220-240 wpm), or try another energetic take.")
        total = LEAD_IN + speech + sum(holds) + tail
    out = array.array("h", bytes(2 * int(LEAD_IN * SR)))
    timing_shots, words = {}, []
    t = 0.0
    for i, s in enumerate(shots):
        a0, a1 = int(bounds[i] * SR), int(bounds[i + 1] * SR)
        vo_start = len(out) / SR
        out.extend(_fade(array.array("h", raw[a0:a1])))
        vo_end = len(out) / SR
        gap = holds[i] if i < len(shots) - 1 else tail
        out.extend(array.array("h", bytes(2 * int(gap * SR))))
        shot_end = len(out) / SR
        for j in range(*idx[i]):
            w = raw_words[j]
            words.append({"i": j, "text": w["text"], "start": round(w["start"] - bounds[i] + vo_start, 3),
                          "end": round(w["end"] - bounds[i] + vo_start, 3), "shot": s["id"]})
        timing_shots[s["id"]] = {"index": i, "start_s": round(t, 3), "end_s": round(shot_end, 3), "vo_start_s": round(vo_start, 3),
                                 "vo_end_s": round(vo_end, 3), "hold_after_s": round(gap, 3)}
        t = shot_end
    total = len(out) / SR
    total_frames = int(math.ceil(total * FPS - 1e-6))
    ids = [s["id"] for s in shots]
    for i, sid in enumerate(ids):
        sf = int(round(timing_shots[sid]["start_s"] * FPS))
        ef = total_frames if i == len(ids) - 1 else int(round(timing_shots[ids[i + 1]]["start_s"] * FPS))
        timing_shots[sid].update(start_frame=sf, frames=ef - sf, seconds=round((ef - sf) / FPS, 4))
    wpm = len(words) / max(1e-6, speech) * 60
    lo, hi = V["target_seconds"]
    if not lo <= total <= hi:
        notes.append(f"total {total:.1f}s is outside the {lo}-{hi}s target (limit {V['max_seconds']}s)")
    wpm_lo, wpm_hi = voices_config().get("tts", {}).get("pacing", {}).get("target_wpm", [220, 240])
    if not wpm_lo <= wpm <= wpm_hi:
        notes.append(f"pace {wpm:.1f} wpm is outside the {wpm_lo}-{wpm_hi} wpm target")
    timing = {"fps": FPS, "source": source, "total_seconds": round(total_frames / FPS, 3), "total_frames": total_frames, "speech_seconds": round(speech, 2),
              "words_per_minute": round(wpm, 1), "lead_in_s": LEAD_IN, "tail_s": round(tail, 3), "notes": notes, "voice": meta,
              "shots": timing_shots, "words": words}
    return timing, out


def estimate_words(shot_texts: list[str]) -> list[dict]:
    words, _ = mock_take(shot_texts)
    return words


# ----------------------------------------------------------------------------- main
def narration_texts(clip: Path, plan: dict) -> list[str]:
    """Per-shot narration as it is sent to the model: the sound designer's tagged text if present, else the plain words."""
    ap = clip / "audio" / "plan.json"
    tagged = {}
    if ap.exists():
        for n in read_json(ap).get("narration", []):
            tagged[n["shot"]] = n["text"]
    out = []
    for s in plan["shots"]:
        t = tagged.get(s["id"], s["vo_text"])
        if words_of(t) != words_of(s["vo_text"]):
            raise SystemExit(f"audio/plan.json narration for {s['id']} changes the words. Tags and punctuation may change; the words may not.\n"
                             f"  plan : {strip_tags(s['vo_text'])}\n  audio: {strip_tags(t)}")
        out.append(t)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clip.py voice")
    ap.add_argument("clip", nargs="?")
    ap.add_argument("--mock", action="store_true", help="offline placeholder narration")
    ap.add_argument("--from-media", metavar="FILE", help="reuse the audio of a finished film or take; word times come from speech recognition (tools/audio/align.py)")
    ap.add_argument("--asr-setup", action="store_true", help="download the speech recognition model used by --from-media and `qa --listen`")
    ap.add_argument("--estimate", action="store_true", help="timing only, no audio (dry run before a voice exists)")
    ap.add_argument("--voice", help="voice name from config/voices.json, or a raw voice id")
    ap.add_argument("--model")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--retake", action="store_true", help="generate a new take even if one exists")
    a = ap.parse_args(argv)
    load_env()
    if a.asr_setup:
        from audio import align
        return align.setup()
    if not a.clip:
        ap.error("clip is required")
    clip = clip_dir(a.clip)
    plan, script = read_json(clip / "shotplan.json"), read_json(clip / "script.json")
    if a.from_media:
        from audio import align
        media = Path(a.from_media).resolve()
        if not media.exists():
            raise SystemExit(f"no such file: {media}")
        timing = align.import_media(clip, media, plan)
        print(f"timing: {timing['total_seconds']}s, {timing['total_frames']} frames, imported from {media.name} ({timing['voice']['matched']}/{timing['voice']['script_words']} words heard)")
        for sid, s in timing["shots"].items():
            print(f"  {sid}: {s['seconds']:6.2f}s  frames {s['start_frame']}..{s['start_frame'] + s['frames'] - 1}")
        return 0
    fmt = plan.get("format") or read_json(clip / "state.json").get("format")
    shots = plan["shots"]
    texts = narration_texts(clip, plan)
    adir = clip / "audio"
    adir.mkdir(exist_ok=True)
    raw_mp3, raw_wav = adir / "narration_raw.mp3", adir / "narration_raw.wav"
    expected = [w for s in shots for w in words_of(s["vo_text"])]
    if a.mock or a.estimate:
        raw_words, raw = mock_take(texts)
        meta = {"provider": "mock", "note": "placeholder tones, not a voice"}
        source = "estimate" if a.estimate else "mock"
    else:
        cfg = voices_config()
        audio_plan = read_json(adir / "plan.json") if (adir / "plan.json").exists() else {}
        vp = audio_plan.get("voice", {})
        name, v = pick_voice(cfg, fmt, a.voice or vp.get("voice"))
        fcfg = cfg.get("formats", {}).get(fmt, {})
        std_defaults = cfg.get("standard_voice", {}).get("default_settings", {})
        model = a.model or vp.get("model_id") or cfg["tts"]["model_id"]
        al_path = adir / "alignment_raw.json"
        if raw_mp3.exists() and al_path.exists() and not a.retake:
            print(f"voice: keeping the existing take ({raw_mp3.name}); use --retake for a new one")
            saved = read_json(al_path)
            raw_words, meta = saved["words"], saved["meta"]
        else:
            raw_words, meta = None, None
            chain = [model] + [m for m in cfg["tts"]["fallback_models"] if m != model]
            last = None
            for m in chain:
                caps = cfg["tts"]["models"].get(m, {"audio_tags": False, "ssml_break": False, "settings": ["stability", "similarity_boost"]})
                text = " ".join(for_model(t, caps) for t in texts)
                allowed = caps["settings"]
                settings = {k: vp.get(k, fcfg.get(k, std_defaults.get(k))) for k in allowed if vp.get(k, fcfg.get(k, std_defaults.get(k))) is not None}
                seed = a.seed if a.seed is not None else vp.get("seed")
                try:
                    try:
                        r = eleven.tts_with_timestamps(v["voice_id"], text, m, settings, seed, cfg["tts"]["output_format"])
                        route = "text-to-speech/with-timestamps"
                    except eleven.ElevenError as e:
                        if e.status in (400, 404, 422) and "model" in str(e).lower():
                            r = eleven.dialogue_with_timestamps(v["voice_id"], text, m, {"stability": settings.get("stability", 0.5)}, seed, cfg["tts"]["output_format"])
                            route = "text-to-dialogue/with-timestamps"
                        else:
                            raise
                except eleven.ElevenError as e:
                    last = e
                    print(f"voice: {m} failed ({e}); trying the next model")
                    continue
                audio = base64.b64decode(r["audio_base64"])
                raw_mp3.write_bytes(audio)
                al = r.get("alignment") or r.get("normalized_alignment")
                words = alignment_to_words(al) if al else []
                how = "character timestamps"
                if [norm_word(w["text"]) for w in words] != expected:
                    fa = eleven.forced_alignment(audio, " ".join(strip_tags(t) for t in texts))
                    words = [{"text": w["text"].strip(), "start": float(w["start"]), "end": float(w["end"])} for w in fa["words"] if norm_word(w["text"])]
                    how = "forced alignment"
                    if [norm_word(w["text"]) for w in words] != expected:
                        raise SystemExit(f"voice: could not match the take to the script ({len(words)} aligned vs {len(expected)} script words). Try --retake.")
                raw_words = words
                meta = {"provider": "elevenlabs", "voice": name, "voice_id": v["voice_id"], "model_id": m, "route": route, "alignment": how,
                        "settings": settings, "seed": seed, "characters": len(text), "created": datetime.datetime.now().isoformat(timespec="seconds")}
                write_json(al_path, {"meta": meta, "text": text, "words": raw_words, "alignment": al})
                print(f"voice: {name} on {m} via {route}; words from {how}")
                break
            if raw_words is None:
                raise SystemExit(f"voice: every model failed. Last error: {last}")
        run([which_ffmpeg(), "-y", "-v", "error", "-i", raw_mp3, "-ac", "1", "-ar", SR, "-c:a", "pcm_s16le", raw_wav], quiet=True)
        raw = read_wav(raw_wav)
        source = "elevenlabs"
    timing, out = build_timing(raw_words, raw, shots, source, meta)
    if not a.estimate:
        write_wav(adir / "narration.wav", out)
    write_json(clip / "timing.json", timing)
    print(f"timing: {timing['total_seconds']}s, {timing['total_frames']} frames, {timing['words_per_minute']} wpm ({source})")
    for sid, s in timing["shots"].items():
        print(f"  {sid}: {s['seconds']:6.2f}s  frames {s['start_frame']}..{s['start_frame'] + s['frames'] - 1}  hold {s['hold_after_s']}s")
    for n in timing["notes"]:
        print("note:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
