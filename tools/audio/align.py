"""Word times from finished audio: an independent ear for the captions, and a way to reuse an existing soundtrack.

    python tools/clip.py voice <clip> --from-media <film.mp4|take.wav>   reuse the audio of a finished Short (voice, or the whole
                                                                         mix): its words are found by speech recognition and
                                                                         become timing.json. No ElevenLabs call, no credits.
    python tools/clip.py qa <clip> --listen                              recognise the FINAL file's audio and compare every caption
                                                                         with the moment its word is actually spoken

Both need the optional speech recogniser (not needed for a normal run, where ElevenLabs returns the timestamps):

    pip install sherpa-onnx numpy
    python tools/clip.py voice <clip> --asr-setup          downloads the model once (about 480 MB) to library/_models/

Model: NVIDIA Parakeet TDT 0.6b v2 (English), int8, run by sherpa-onnx on the CPU. Word starts from this model sit about
0.07 s before the audible onset (measured against energy onsets after pauses); START_BIAS corrects that.
"""
from __future__ import annotations

import array
import difflib
import math
import os
import shutil
import sys
import tarfile
import urllib.request
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import FPS, ROOT, STYLE, display_words, norm_word, run, which_ffmpeg, write_json  # noqa: E402

MODEL = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL}.tar.bz2"
START_BIAS = 0.07
SR = 16000


def model_dir() -> Path:
    return Path(os.environ.get("ASR_MODEL_DIR") or ROOT / "library" / "_models" / MODEL)


def available() -> tuple[bool, str]:
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False, "the speech recogniser is not installed: pip install sherpa-onnx numpy"
    if not (model_dir() / "tokens.txt").exists():
        return False, f"the recognition model is missing: python tools/clip.py voice <clip> --asr-setup (downloads {MODEL}, about 480 MB)"
    return True, "ok"


def setup() -> int:
    d = model_dir()
    if (d / "tokens.txt").exists():
        print(f"asr model: ok ({d})")
        return 0
    d.parent.mkdir(parents=True, exist_ok=True)
    tmp = d.parent / (MODEL + ".tar.bz2")
    print(f"asr model: downloading {MODEL_URL}")
    with urllib.request.urlopen(MODEL_URL, timeout=600) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    root = d.parent.resolve()
    with tarfile.open(tmp, "r:bz2") as t:
        for m in t.getmembers():
            if not (root / m.name).resolve().is_relative_to(root) or m.issym() or m.islnk():
                raise SystemExit(f"refusing to extract {m.name!r}")
        t.extractall(root)
    tmp.unlink()
    ok, why = available()
    print("asr:", why if not ok else f"ready ({d})")
    return 0 if ok else 1


def _pcm16k(media: Path) -> list[float]:
    tmp = Path(str(media) + ".asr16k.wav")
    run([which_ffmpeg(), "-y", "-v", "error", "-i", media, "-vn", "-ac", "1", "-ar", SR, "-c:a", "pcm_s16le", tmp], quiet=True)
    with wave.open(str(tmp), "rb") as w:
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
    tmp.unlink(missing_ok=True)
    return a


def transcribe(media: Path) -> list[dict]:
    """[{"text", "start", "end"}] for every recognised word, in seconds from the start of the file."""
    ok, why = available()
    if not ok:
        raise SystemExit(why)
    import numpy as np
    import sherpa_onnx
    d = str(model_dir())
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(encoder=d + "/encoder.int8.onnx", decoder=d + "/decoder.int8.onnx", joiner=d + "/joiner.int8.onnx",
                                                       tokens=d + "/tokens.txt", model_type="nemo_transducer", num_threads=max(1, (os.cpu_count() or 2)))
    pcm = np.frombuffer(_pcm16k(media).tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
    total = len(pcm) / SR
    # cut long audio at quiet moments so no word is split between two passes
    hop = int(0.02 * SR)
    rms = np.sqrt(np.convolve(pcm ** 2, np.ones(hop) / hop, mode="same"))[::hop]
    cuts, t = [0.0], 0.0
    while total - t > 30.0:
        lo, hi = int((t + 18.0) / 0.02), int((t + 28.0) / 0.02)
        k = lo + int(np.argmin(rms[lo:hi]))
        t = k * 0.02
        cuts.append(t)
    cuts.append(total)
    words = []
    for a, b in zip(cuts, cuts[1:]):
        st = rec.create_stream()
        st.accept_waveform(SR, pcm[int(a * SR):int(b * SR)])
        rec.decode_stream(st)
        cur = None
        for tok, ts in zip(st.result.tokens, st.result.timestamps):
            if tok.startswith(" ") or cur is None:
                if cur:
                    words.append(cur)
                cur = {"text": tok.strip(), "start": a + ts + START_BIAS, "end": a + ts + START_BIAS}
            else:
                cur["text"] += tok
            cur["end"] = a + ts + START_BIAS + 0.09
        if cur:
            words.append(cur)
    words = [w for w in words if norm_word(w["text"])]
    for i, w in enumerate(words):                    # an end that is useful for captions: until the next word, within reason
        nxt = words[i + 1]["start"] if i + 1 < len(words) else total
        w["end"] = round(min(nxt - 0.02, max(w["end"], w["start"] + 0.06 + 0.055 * len(norm_word(w["text"])))), 3)
        w["start"] = round(w["start"], 3)
    return words


def _num_words(n: str) -> list[str]:
    """'10' -> ['ten']: recognisers write digits, scripts write words."""
    small = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    tens = "twenty thirty forty fifty sixty seventy eighty ninety".split()
    try:
        v = int(n.replace(",", ""))
    except ValueError:
        return [n]
    if v < 20:
        return [small[v]]
    if v < 100:
        return [tens[v // 10 - 2]] + ([small[v % 10]] if v % 10 else [])
    return [n]


def map_words(expected: list[str], heard: list[dict]) -> tuple[list[dict], dict]:
    """Give every expected (script) word a time from the recognised words. Unheard words are spaced between their neighbours.
    Returns (words, stats)."""
    flat = []
    for h in heard:
        for part in _num_words(norm_word(h["text"])):
            flat.append({"n": norm_word(part), "start": h["start"], "end": h["end"]})
    a = [norm_word(w) for w in expected]
    b = [h["n"] for h in flat]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    times: list = [None] * len(a)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = (flat[j1 + k]["start"], flat[j1 + k]["end"])
        elif tag == "replace" and (i2 - i1) == (j2 - j1):            # misheard but still one-for-one
            for k in range(i2 - i1):
                times[i1 + k] = (flat[j1 + k]["start"], flat[j1 + k]["end"])
    matched = sum(t is not None for t in times)
    i = 0
    while i < len(times):
        if times[i] is None:
            j = i
            while j < len(times) and times[j] is None:
                j += 1
            lo = times[i - 1][1] if i > 0 else 0.0
            hi = times[j][0] if j < len(times) else lo + 0.3 * (j - i)
            step = (hi - lo) / (j - i + 1) if hi > lo else 0.12
            for k in range(i, j):
                s = lo + step * (k - i + 0.5)
                times[k] = (s, s + step * 0.9)
            i = j
        else:
            i += 1
    words = [{"text": w, "start": round(t[0], 3), "end": round(max(t[1], t[0] + 0.05), 3)} for w, t in zip(expected, times)]
    return words, {"script_words": len(a), "heard_words": len(b), "matched": matched, "match_ratio": round(matched / max(1, len(a)), 3)}


def import_media(clip: Path, media: Path, plan: dict) -> dict:
    """Use the audio of `media` as this clip's soundtrack and build timing.json from where its words are spoken.
    The audio is not re-cut: shots change in the gaps between words. If the file is a finished mix (voice + music +
    effects), the assembly uses it as it is and adds nothing."""
    from audio.voice import SR as OUT_SR
    shots = plan["shots"]
    expected, owner = [], []
    for s in shots:
        ws = display_words(s["vo_text"])
        expected += ws
        owner += [s["id"]] * len(ws)
    heard = transcribe(media)
    words, stats = map_words(expected, heard)
    if stats["match_ratio"] < 0.85:
        raise SystemExit(f"only {stats['matched']} of {stats['script_words']} script words were heard in {media.name}: is this the right audio for this script?")
    adir = clip / "audio"
    adir.mkdir(exist_ok=True)
    out = adir / "narration.wav"
    run([which_ffmpeg(), "-y", "-v", "error", "-i", media, "-vn", "-ac", "1", "-ar", OUT_SR, "-c:a", "pcm_s16le", out], quiet=True)
    with wave.open(str(out), "rb") as w:
        total = w.getnframes() / w.getframerate()
    stereo = adir / "imported_mix.wav"
    run([which_ffmpeg(), "-y", "-v", "error", "-i", media, "-vn", "-ar", OUT_SR, "-c:a", "pcm_s16le", stereo], quiet=True)
    total_frames = int(math.ceil(total * FPS - 1e-6))
    bounds = [0.0]
    k = 0
    for s in shots[:-1]:
        k += len(display_words(s["vo_text"]))
        bounds.append((words[k - 1]["end"] + words[k]["start"]) / 2)
    bounds.append(total)
    tshots, tw = {}, []
    k = 0
    for i, s in enumerate(shots):
        n = len(display_words(s["vo_text"]))
        sf = int(round(bounds[i] * FPS))
        ef = total_frames if i == len(shots) - 1 else int(round(bounds[i + 1] * FPS))
        ws = words[k:k + n]
        tshots[s["id"]] = {"index": i, "start_s": round(sf / FPS, 3), "end_s": round(ef / FPS, 3), "vo_start_s": ws[0]["start"], "vo_end_s": ws[-1]["end"],
                           "hold_after_s": 0.0, "start_frame": sf, "frames": ef - sf, "seconds": round((ef - sf) / FPS, 4)}
        for j, w in enumerate(ws):
            tw.append({"i": k + j, "text": w["text"], "start": w["start"], "end": w["end"], "shot": s["id"]})
        k += n
    speech = sum(w["end"] - w["start"] for w in tw)
    timing = {"fps": FPS, "source": "imported", "premixed": True, "total_seconds": round(total_frames / FPS, 3), "total_frames": total_frames,
              "speech_seconds": round(speech, 2), "words_per_minute": round(len(tw) / max(1e-6, tw[-1]["end"] - tw[0]["start"]) * 60, 1),
              "lead_in_s": 0.0, "tail_s": round(total - tw[-1]["end"], 3),
              "notes": [f"audio and word times imported from {media.name} by speech recognition ({stats['matched']}/{stats['script_words']} words heard)"],
              "voice": {"provider": "imported", "file": media.name, "alignment": "sherpa-onnx parakeet-tdt-0.6b-v2", **stats}, "shots": tshots, "words": tw}
    lo, hi = STYLE["video"]["target_seconds"]
    if total > STYLE["video"]["max_seconds"]:
        timing["notes"].append(f"total {total:.1f}s is over the {STYLE['video']['max_seconds']}s limit")
    write_json(clip / "timing.json", timing)
    return timing
