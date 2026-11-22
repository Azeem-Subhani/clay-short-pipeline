"""Captions: what is shown, when, and the checks that they sit where they should and arrive with the voice.

Built from the word times in timing.json (the same clock that set every shot's length), so text and voice cannot drift.
One short caption at a time on one fixed line, centred on the frame:

    A queen | dropped | her gold | ring | into | the deep | castle | pond.

Rules (numbers in style/style.json > captions):
  - small words (a, the, of, her, is ...) wait for the next word, so nothing ends on "the"
  - a caption closes on punctuation, at max_words / max_chars, and before a pause
  - it appears lead_s before its first word is spoken and stays until the next caption (no flicker); after the end of a
    sentence followed by a real pause it clears, so a silent beat has a clean picture
  - one line only: a long caption is scaled down, never wrapped (wrapping makes the text jump up and down)

    python tools/captions.py <clip>            print the caption list of a clip
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FPS, STYLE, norm_word  # noqa: E402

C = STYLE["captions"]
END = re.compile(r"[.!?…][\"”')\]]*$")
SOFT = re.compile(r"[,;:—–-][\"”')\]]*$")
CHAR_EM = 0.635                      # average glyph advance of Montserrat 800-900 in em, measured on mixed-case English


def _clean(t: str) -> str:
    return t.strip().strip('"“”')


def est_width_px(text: str, font_px: float | None = None) -> float:
    font_px = font_px or C["font_size_px"]
    wide = sum(1 for ch in text if ch in "mwMWQOGD@")
    thin = sum(1 for ch in text if ch in "iljtfI.,'!:; ")
    n = len(text) + 0.35 * wide - 0.45 * thin
    return n * CHAR_EM * font_px + 2 * C["stroke_px"] * 0.5


def build(words: list[dict], fps: int = FPS) -> list[dict]:
    """words: [{"text", "start", "end", "shot"}] in film seconds -> captions [{"text", "start", "end", "from", "to", "words", "scale"}]."""
    keep = {norm_word(w) for w in C["keep_together"]}
    max_w, max_c = int(C["max_words"]), int(C["max_chars"])
    groups, cur = [], []

    def close():
        nonlocal cur
        if cur:
            groups.append(cur)
        cur = []

    n = len(words)
    for i, w in enumerate(words):
        text = _clean(w["text"])
        if not text:
            continue
        item = {"text": text, "start": float(w["start"]), "end": float(w["end"]), "shot": w.get("shot")}
        if cur:
            length = len(" ".join(x["text"] for x in cur)) + 1 + len(text)
            pause = item["start"] - cur[-1]["end"] > 0.32
            if len(cur) >= max_w or length > max_c or pause:
                close()
        cur.append(item)
        last = i == n - 1
        gap_next = (float(words[i + 1]["start"]) - item["end"]) if not last else 9.0
        small = norm_word(text) in keep
        if last or END.search(text) or SOFT.search(text) or gap_next > 0.32:
            close()
        elif not small:
            close()                                  # a content word completes the caption: small words lead into it
    # a caption left holding only small words joins the next one when it fits ("of the" + "mine")
    merged = []
    i = 0
    while i < len(groups):
        g = groups[i]
        if (i + 1 < len(groups) and all(norm_word(x["text"]) in keep for x in g) and not END.search(g[-1]["text"]) and not SOFT.search(g[-1]["text"])
                and groups[i + 1][0]["start"] - g[-1]["end"] <= 0.32
                and len(g) + len(groups[i + 1]) <= max_w and len(" ".join(x["text"] for x in g + groups[i + 1])) <= max_c + 2):
            groups[i + 1] = g + groups[i + 1]
            i += 1
            continue
        merged.append(g)
        i += 1
    caps = []
    for k, g in enumerate(merged):
        start = max(0.0, g[0]["start"] - C["lead_s"])
        if k + 1 < len(merged):
            nxt = max(0.0, merged[k + 1][0]["start"] - C["lead_s"])
            sentence_end = bool(END.search(g[-1]["text"]))
            if nxt - g[-1]["end"] > C["gap_blank_s"] or (sentence_end and nxt - g[-1]["end"] > C["hold_after_sentence_s"] + 0.15):
                end = g[-1]["end"] + C["hold_after_sentence_s"]
            else:
                end = nxt
        else:
            end = g[-1]["end"] + C["hold_after_sentence_s"] + 0.25
        caps.append({"text": " ".join(x["text"] for x in g), "start": round(start, 3), "end": round(max(end, start + C["min_show_s"]), 3), "words": g})
    max_px = C["max_width_fraction"] * STYLE["video"]["width"]
    for k, c in enumerate(caps):
        if k + 1 < len(caps):
            c["end"] = min(c["end"], caps[k + 1]["start"])
        c["from"] = int(round(c["start"] * fps))
        c["to"] = max(c["from"] + 2, int(round(c["end"] * fps)))
        if k + 1 < len(caps):
            c["to"] = min(c["to"], max(c["from"] + 1, int(round(caps[k + 1]["start"] * fps))))
        w = est_width_px(c["text"].upper() if C.get("uppercase") else c["text"])
        c["scale"] = round(min(1.0, max_px / max(w, 1.0)), 3)
        c["words"] = [{"text": x["text"], "from": int(round(x["start"] * fps)), "to": int(round(x["end"] * fps)), "start": x["start"]} for x in c["words"]]
    return caps


def describe(caps: list[dict]) -> dict:
    import collections
    n = collections.Counter(len(c["words"]) for c in caps)
    dur = [c["end"] - c["start"] for c in caps]
    return {"captions": len(caps), "words_per_caption": dict(sorted(n.items())), "median_seconds": round(sorted(dur)[len(dur) // 2], 2) if dur else 0,
            "shortest_seconds": round(min(dur), 2) if dur else 0, "longest_text": max((c["text"] for c in caps), key=len, default=""),
            "scaled_down": [c["text"] for c in caps if c["scale"] < 0.999]}


if __name__ == "__main__":
    from common import clip_dir, read_json
    d = clip_dir(sys.argv[1])
    caps = build(read_json(d / "timing.json")["words"])
    for c in caps:
        print(f"{c['start']:6.2f}-{c['end']:6.2f}  {c['text']}" + (f"   (scaled {c['scale']})" if c["scale"] < 1 else ""))
    print(describe(caps))
