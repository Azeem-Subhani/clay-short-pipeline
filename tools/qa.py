"""Measure the finished file against the delivery spec. Everything here is a number; taste is the reviewer's job.

    python tools/clip.py qa <clip> [--tag animatic] [--listen]

Format, length, loudness, cuts between words - and the captions, measured on the finished picture and sound:
  placement   frames are taken from the final MP4 at caption times; the caption's box is found by its white fill and dark
              outline and must be centred on the frame, on the caption line, inside the Shorts safe area, on one line
  timing      the narration track's own silences are detected (FFmpeg) and every speech onset after a pause is compared
              with the word the captions show there; with --listen the final file's audio is also recognised word by
              word (tools/audio/align.py, optional) and every caption is compared with when its word is really spoken
Exit code 0 = deliverable, 1 = at least one failure. Writes <clip>/final/<name>.qa.json.
"""
from __future__ import annotations

import argparse
import re
import statistics
import subprocess
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


def window_luma(path, f0: int, f1: int) -> list[float]:
    """Mean grey level (0-255) of each film frame f0..f1-1, measured on the finished file."""
    r = subprocess.run([which_ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"select='between(n,{f0},{f1 - 1})',scale=1:1:flags=area,format=gray",
                        "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True)
    return [float(b) for b in r.stdout]


def check_transitions(clip, path, plan, timing, asm, facts, fails, warns):
    """Every transition the plan declares was applied (recorded by assemble, and for a dip or flash seen in the picture), and sits
    in a gap between words or within 0.15 s of one, unless it is a cut or a match cut."""
    import assemble
    declared = assemble.resolve_transitions(plan, timing)
    done = {t["shot"]: t for t in asm.get("transitions", [])}
    facts["transitions"] = [{"shot": t["shot"], "type": t["type"], "frames": t["dur_frames"], "boundary_s": round(t["boundary"] / FPS, 3)} for t in declared]
    if not declared:
        return
    words = timing["words"]
    for t in declared:
        got = done.get(t["shot"])
        if not got or got.get("type") != t["type"] or got.get("boundary") != t["boundary"] or got.get("dur_frames") != t["dur_frames"]:
            fails.append(f"transition into {t['shot']} ({t['type']}) is declared in the plan but was not recorded as applied in the assembly: assemble again")
            continue
        cut_t = t["boundary"] / FPS
        if t["type"] != "match":
            inside = [w for w in words if w["start"] + 0.15 < cut_t < w["end"] - 0.15]
            if inside:
                w = inside[0]
                warns.append(f"{t['type']} into {t['shot']} at {cut_t:.2f}s runs over the word '{w['text']}' ({w['start']:.2f}-{w['end']:.2f}s): move the cut to a gap in the narration")
        if t["type"] in ("dip", "flash"):
            lum = window_luma(path, t["boundary"] - t["before"], t["boundary"] + t["after"])
            ref = window_luma(path, max(0, t["boundary"] - t["before"] - 3), max(1, t["boundary"] - t["before"]))
            if not lum:
                warns.append(f"could not measure the {t['type']} into {t['shot']}")
            elif t["type"] == "flash" and max(lum) < 0.82 * 255 and max(lum) < max(ref or [0]) + 60:
                fails.append(f"flash into {t['shot']} never gets bright (peak grey {max(lum):.0f}/255): it was not drawn")
            elif t["type"] == "dip":
                c = t["color"].lstrip("#")
                target = 0.299 * int(c[0:2], 16) + 0.587 * int(c[2:4], 16) + 0.114 * int(c[4:6], 16)
                if min(abs(v - target) for v in lum) > 40 and min(lum) > (min(ref) if ref else 255) - 20:
                    fails.append(f"dip into {t['shot']} never reaches its colour {t['color']} (closest grey {min(lum, key=lambda v: abs(v - target)):.0f}, wanted {target:.0f}): it was not drawn")


def _enclosed_glyphs(white: bytearray, dark: bytearray, width: int, h: int, reach: int = 8) -> list[dict]:
    """Connected white regions whose edge is ringed by the dark outline. Returns one dict per region: x0, x1, y0, y1, area.
    A caption glyph is white fill with a dark outline all round it; a frosted window, a sheet of paper or a cloud is white
    too, but its edge meets the picture, not the outline, so it is left out and can never widen the caption's box."""
    seen = bytearray(width * h)
    out = []
    for start in range(width * h):
        if not white[start] or seen[start]:
            continue
        stack, region = [start], []
        seen[start] = 1
        while stack:
            i = stack.pop()
            region.append(i)
            x = i % width
            if x > 0 and white[i - 1] and not seen[i - 1]:
                seen[i - 1] = 1
                stack.append(i - 1)
            if x < width - 1 and white[i + 1] and not seen[i + 1]:
                seen[i + 1] = 1
                stack.append(i + 1)
            if i >= width and white[i - width] and not seen[i - width]:
                seen[i - width] = 1
                stack.append(i - width)
            if i + width < width * h and white[i + width] and not seen[i + width]:
                seen[i + width] = 1
                stack.append(i + width)
        if len(region) < 25:
            continue
        edge = ringed = 0
        for i in region:
            x, y = i % width, i // width
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < h and white[ny * width + nx]:
                    continue
                edge += 1                                        # a white pixel facing something that is not white
                for k in range(1, reach + 1):                    # walk outwards: the outline must come before any other white
                    fx, fy = x + dx * k, y + dy * k
                    if not (0 <= fx < width and 0 <= fy < h) or white[fy * width + fx]:
                        break
                    if dark[fy * width + fx]:
                        ringed += 1
                        break
        if edge and ringed / edge >= 0.8:
            xs = [i % width for i in region]
            ys = [i // width for i in region]
            out.append({"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys), "area": len(region)})
    return out


def caption_box_in_pixels(px: bytes, width: int, h: int, y0: int, font_px: float):
    """The caption inside one cropped band of RGB pixels: (x0, x1, y0, y1) in frame pixels, or None. Only white fill that is
    enclosed by the dark outline counts, it must be no bigger than a letter can be, and the words are the cluster of such
    glyphs that holds the most fill (a stray white-and-dark object elsewhere in the band does not stretch the box)."""
    n = width * h
    if len(px) < n * 3:
        return None
    lo = bytes(map(min, px[0:n * 3:3], px[1:n * 3:3], px[2:n * 3:3]))
    hi = bytes(map(max, px[0:n * 3:3], px[1:n * 3:3], px[2:n * 3:3]))
    white = bytearray(lo.translate(bytes(0 if v <= 238 else 1 for v in range(256))))
    dark = bytearray(hi.translate(bytes(1 if v < 52 else 0 for v in range(256))))
    glyphs = [g for g in _enclosed_glyphs(white, dark, width, h) if g["y1"] - g["y0"] <= 1.3 * font_px and g["x1"] - g["x0"] <= 0.8 * width]
    if not glyphs:
        return None
    glyphs.sort(key=lambda g: g["x0"])
    clusters, gap = [[glyphs[0]]], 0.9 * font_px                 # a space is about a third of the font size; a new object is further off
    for g in glyphs[1:]:
        if g["x0"] - max(k["x1"] for k in clusters[-1]) > gap:
            clusters.append([])
        clusters[-1].append(g)
    best = max(clusters, key=lambda c: sum(g["area"] for g in c))
    if sum(g["area"] for g in best) < 0.05 * font_px * font_px:
        return None
    return min(g["x0"] for g in best), max(g["x1"] for g in best), y0 + min(g["y0"] for g in best), y0 + max(g["y1"] for g in best)


def caption_box(path, t: float, band: tuple[float, float], width: int, height: int, font_px: float = 84):
    """Find the caption in one frame of the film: (x0, x1, y0, y1) in pixels, or None. Frame is cropped to the expected line's
    band and only white fill enclosed by the dark outline is counted (caption_box_in_pixels)."""
    y0, y1 = int(band[0] * height), int(band[1] * height)
    h = y1 - y0
    r = subprocess.run([which_ffmpeg(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"crop={width}:{h}:0:{y0}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return caption_box_in_pixels(r.stdout, width, h, y0, font_px)


def check_caption_placement(path, caps, st, facts, fails, warns):
    """Where the captions really sit in the finished picture: centred, on one line, inside the safe area."""
    W, H = V["width"], V["height"]
    sa = STYLE["safe_area"]
    cy = st["centerYFraction"]
    half = st["fontSizePx"] * 1.25 / H
    picks = [c for c in caps if c["end"] - c["start"] >= 0.2]
    step = max(1, len(picks) // 24)
    boxes = []
    for c in picks[::step]:
        t = (c["start"] + c["end"]) / 2
        b = caption_box(path, t, (cy - half, cy + half), W, H, st["fontSizePx"])
        if b:
            boxes.append((c, b))
    if len(boxes) < max(3, len(picks[::step]) // 3):
        warns.append(f"captions were found in only {len(boxes)} of {len(picks[::step])} sampled frames: they may be hard to see against the picture, or missing")
    if boxes:
        cxs = [(b[0] + b[1]) / 2 / W for _c, b in boxes]
        cys = [(b[2] + b[3]) / 2 / H for _c, b in boxes]
        ws = [(b[1] - b[0]) / W for _c, b in boxes]
        facts["caption_placement"] = {"sampled": len(boxes), "centre_x_mean": round(statistics.mean(cxs), 4), "centre_x_worst": round(max(cxs, key=lambda v: abs(v - st["centerXFraction"])), 4),
                                      "centre_y_mean": round(statistics.mean(cys), 4), "centre_y_spread": round(max(cys) - min(cys), 4), "widest": round(max(ws), 3)}
        off = [abs(v - st["centerXFraction"]) for v in cxs]
        if statistics.median(off) > 0.012:
            fails.append(f"captions are off centre: measured centre x = {statistics.mean(cxs):.3f} of the frame width, expected {st['centerXFraction']}")
        # one fixed line: letters with tails or tall strokes shift the measured box a little, so the test is whether every
        # caption stays inside the band of a single line and is no taller than one line
        fpx = st["fontSizePx"]
        tall = max((b[3] - b[2]) / fpx for _c, b in boxes)
        facts["caption_placement"]["tallest_in_font_heights"] = round(tall, 2)
        odd = [(c, b) for c, b in boxes if (b[3] - b[2]) > 1.5 * fpx or b[2] < cy * H - 0.85 * fpx or b[3] > cy * H + 0.85 * fpx]
        if len(odd) >= max(2, len(boxes) // 8):                  # several: the captions really wrap or wander
            c, b = odd[0]
            fails.append(f"{len(odd)} of {len(boxes)} measured captions do not sit on one line (first: '{c['text']}', y {b[2] / H:.3f}-{b[3] / H:.3f}, "
                         f"{(b[3] - b[2]) / fpx:.1f} font heights tall; line centre {cy}): captions must stay on one fixed line")
        elif odd:                                                # one: usually something white in the picture right at the caption
            c, b = odd[0]
            warns.append(f"caption '{c['text']}' measured {(b[3] - b[2]) / fpx:.1f} font heights tall: probably a white object in the picture touching it; look at that frame")
        for c, b in boxes:
            if b[0] / W < sa["left"] - 0.005 or b[1] / W > 1 - sa["right"] + 0.005:
                fails.append(f"caption '{c['text']}' reaches outside the Shorts safe area (x {b[0] / W:.2f}-{b[1] / W:.2f})")
                break
        if statistics.mean(cys) > 1 - sa["bottom"]:
            fails.append(f"the caption line (y={statistics.mean(cys):.2f}) is under the Shorts UI (below {1 - sa['bottom']:.2f})")


def check_captions(clip, path, slug, facts, fails, warns, listen: bool):
    cj = clip / "final" / f"{slug}.captions.json"
    if not cj.exists():
        warns.append("no captions.json next to the film (assembled with --no-captions?)")
        return
    data = read_json(cj)
    caps = data["captions"]
    st = data["style"]
    facts["captions"] = data.get("summary", {})
    if not caps:
        return
    check_caption_placement(path, caps, st, facts, fails, warns)
    # --- timing, against the narration's own pauses
    timing = read_json(clip / "timing.json")
    words = timing["words"]
    nar = clip / "audio" / "narration.wav"
    lead = STYLE["captions"]["lead_s"]
    if nar.exists() and not timing.get("premixed"):
        r = run([which_ffmpeg(), "-hide_banner", "-nostats", "-i", nar, "-af", "silencedetect=noise=-38dB:d=0.22", "-f", "null", "-"], capture=True, quiet=True)
        onsets = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
        diffs = []
        for o in onsets:
            w = min(words, key=lambda w: abs(w["start"] - o))
            if abs(w["start"] - o) < 0.5:
                diffs.append(w["start"] - o)
        if diffs:
            facts["caption_timing_vs_pauses"] = {"speech_onsets_checked": len(diffs), "median_s": round(statistics.median(diffs), 3),
                                                 "worst_s": round(max(diffs, key=abs), 3), "captions_lead_words_by_s": lead}
            if abs(statistics.median(diffs)) > 0.1:
                fails.append(f"word times are {statistics.median(diffs):+.2f}s away from where speech starts after pauses in narration.wav: captions will look early or late")
            late = [d for d in diffs if abs(d) > 0.25]
            if len(late) > max(1, len(diffs) // 8):
                warns.append(f"{len(late)} of {len(diffs)} speech onsets are more than 0.25s from their word time")
    if listen:
        from audio import align
        ok, why = align.available()
        if not ok:
            warns.append(f"--listen skipped: {why}")
        else:
            heard = align.transcribe(path)
            mapped, stats = align.map_words([w["text"] for w in words], heard)
            diffs = [m["start"] - w["start"] for m, w in zip(mapped, words)]
            # caption by caption: when is its first word really spoken, when does the caption appear
            cap_d = []
            k = 0
            starts = {round(w["start"], 3): i for i, w in enumerate(words)}
            for c in caps:
                i = min(range(len(words)), key=lambda j: abs(words[j]["start"] - (c["start"] + lead)))
                cap_d.append(mapped[i]["start"] - c["start"])
            facts["caption_timing_heard"] = {"words_heard": stats["matched"], "of": stats["script_words"], "word_time_error_median_s": round(statistics.median(diffs), 3),
                                             "word_time_error_p90_s": round(sorted(abs(d) for d in diffs)[int(len(diffs) * 0.9)], 3),
                                             "caption_appears_before_its_word_median_s": round(statistics.median(cap_d), 3),
                                             "captions_late_over_0.15s": sum(1 for d in cap_d if d < -0.15), "captions_early_over_0.35s": sum(1 for d in cap_d if d > 0.35)}
            if stats["match_ratio"] < 0.9:
                warns.append(f"only {stats['matched']} of {stats['script_words']} narration words were recognised in the final audio: the timing figures are less certain")
            if abs(statistics.median(diffs)) > 0.12:
                fails.append(f"captions and voice are out of step: recognised words sit {statistics.median(diffs):+.2f}s from their caption times (median)")
            if sum(1 for d in cap_d if d < -0.15) > len(cap_d) * 0.1:
                fails.append(f"{sum(1 for d in cap_d if d < -0.15)} captions appear more than 0.15s after their word is spoken")


def opening_motion_seconds(clip, shot_id: str, view_id: str) -> float:
    """How long the camera keeps moving from the start of a shot's first view (camera path record of the stills run): a follow,
    push or crane that runs through the view gives the eye something new as surely as a cut does. Moves are chained, a gap of
    up to 0.4 s between them still counts as continuous. 0 when there is no record or no move in that view."""
    rec = clip / "review" / shot_id / "campath.json"
    if not rec.exists():
        return 0.0
    try:
        moves = sorted((m for m in read_json(rec).get("moves", []) if m.get("view") == view_id), key=lambda m: m["t0"])
    except (ValueError, KeyError):
        return 0.0
    end = 0.0
    for m in moves:
        if m["t0"] > end + 0.4:
            break
        end = max(end, m["t1"])
    return end


def look_across_shots(clip) -> tuple[list[dict], list[str]]:
    """Shot against shot, from the look stills the stills run wrote (review/<shot>/checks.json > look): per shot the hero face brightness
    (mean over its views, 0-100), the whole-frame colour lean (V minus U), the darkest tenth and the brightest tenth (0-100). A warning where
    neighbouring shots of the same time of day differ by more than the limits below; different times of day are allowed to differ.
    Reports only: nothing is changed. Returns (rows, warnings)."""
    plan = read_json(clip / "shotplan.json")
    rows = []
    for sh in plan["shots"]:
        rp = clip / "review" / sh["id"] / "checks.json"
        if not rp.exists():
            continue
        stills = (read_json(rp).get("look") or {}).get("stills") or []
        if not stills:
            continue
        heroes = [next((f["mean"] for f in e["faces"] if f.get("ok")), None) for e in stills]
        heroes = [h for h in heroes if h is not None]
        st = [e["stats"] for e in stills]
        avg = lambda k: sum(x[k] for x in st) / len(st)
        rows.append({"shot": sh["id"], "time": sh.get("time"), "set": sh.get("set"), "views": len(stills),
                     "face": round(100 * sum(heroes) / len(heroes), 0) if heroes else None,
                     "warmth": round(avg("v") - avg("u"), 1), "dark10": round(avg("y10") / 2.55, 0), "bright10": round(avg("y90") / 2.55, 0)})
    warns = []
    for a, b in zip(rows, rows[1:]):
        if a["time"] != b["time"]:
            continue
        why = []
        if a["face"] is not None and b["face"] is not None and abs(a["face"] - b["face"]) > LOOK_JUMP["face"]:
            why.append(f"hero face brightness {a['face']:.0f} to {b['face']:.0f}")
        if abs(a["warmth"] - b["warmth"]) > LOOK_JUMP["warmth"]:
            why.append(f"colour lean (V minus U) {a['warmth']:+.0f} to {b['warmth']:+.0f}")
        if abs(a["dark10"] - b["dark10"]) > LOOK_JUMP["dark10"]:
            why.append(f"darkest tenth {a['dark10']:.0f} to {b['dark10']:.0f}")
        if abs(a["bright10"] - b["bright10"]) > LOOK_JUMP["bright10"]:
            why.append(f"brightest tenth {a['bright10']:.0f} to {b['bright10']:.0f}")
        if why:
            warns.append(f"{a['shot']} -> {b['shot']} (both '{a['time']}'): " + "; ".join(why))
    return rows, warns


LOOK_JUMP = {"face": 12, "warmth": 8, "dark10": 10, "bright10": 12}      # what two shots of one time of day may differ by before it is a warning


def print_look_table(clip) -> int:
    rows, warns = look_across_shots(clip)
    if not rows:
        print("no look stills yet: run `clip.py stills` first")
        return 0
    print(f"{'shot':6} {'time':14} {'views':5} {'face':>5} {'warmth':>7} {'dark10':>7} {'bright10':>8}")
    for r in rows:
        print(f"{r['shot']:6} {str(r['time']):14} {r['views']:5} {r['face'] if r['face'] is not None else '-':>5} {r['warmth']:>+7} {r['dark10']:>7.0f} {r['bright10']:>8.0f}")
    for w in warns:
        print("WARN", w)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clip.py qa")
    ap.add_argument("clip")
    ap.add_argument("--tag", default="")
    ap.add_argument("--look", action="store_true", help="only the shot-against-shot table of the look stills (hero face, colour lean, tonal range); needs no final file")
    ap.add_argument("--listen", action="store_true", help="recognise the final audio and check every caption against it (needs tools/audio/align.py set up)")
    a = ap.parse_args(argv)
    clip = clip_dir(a.clip)
    if a.look:
        return print_look_table(clip)
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
    views = []
    for sid in shots:
        rep = clip / "review" / sid / "checks.json"
        if rep.exists():
            views += [(sid, v["id"], v.get("seconds", 0)) for v in read_json(rep).get("views", [])]
    if views:
        VW = STYLE["views"]
        facts["views"] = len(views)
        facts["seconds_per_view_median"] = round(statistics.median(v[2] for v in views), 2)
        facts["longest_view"] = max(views, key=lambda v: v[2])
        idle = views[0][2] - opening_motion_seconds(clip, views[0][0], views[0][1])
        facts["first_view"] = {"seconds": views[0][2], "camera_moving_for_s": round(views[0][2] - idle, 2), "still_after_move_s": round(idle, 2)}
        if idle > VW["first_view_max_seconds"] + 1.0:
            warns.append(f"the first view lasts {views[0][2]}s and the camera is still for the last {idle:.1f}s of it: the opening should give the eye something new within about {VW['first_view_max_seconds']}s")
        if not VW["per_short"][0] <= len(views) <= VW["per_short"][1]:
            warns.append(f"{len(views)} views (the reference Shorts use {VW['per_short'][0]}-{VW['per_short'][1]})")
    words = timing["words"]
    ids = list(shots)
    plan = read_json(clip / "shotplan.json")
    check_transitions(clip, path, plan, timing, asm, facts, fails, warns)
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
    if timing.get("source") == "imported":
        warns.append("the soundtrack was imported from an existing file; word times come from speech recognition, not from ElevenLabs")
    elif timing.get("source") != "elevenlabs":
        warns.append(f"narration is '{timing.get('source')}', not an ElevenLabs take")
    check_captions(clip, path, slug, facts, fails, warns, a.listen)
    cues = read_json(clip / "audio" / "cues.json") if (clip / "audio" / "cues.json").exists() else {}
    if cues.get("provider") == "mock":
        warns.append("music and sound effects are mock placeholders")
    fi, fo = STYLE["finish"]["fade_in_frames"] / FPS, STYLE["finish"]["fade_out_frames"] / FPS
    dips = [((t["boundary"] - t["before"]) / FPS, (t["boundary"] + t["after"]) / FPS) for t in asm.get("transitions", []) if t["type"] == "dip"]
    spans_black = black_spans(path)
    for b0, b1 in spans_black:
        if any(b0 < d1 + 0.1 and b1 > d0 - 0.1 for d0, d1 in dips):       # a dip to black is a declared transition, not a fault
            continue
        if b0 > fi + 0.2 and b1 < dur - fo - 0.2:
            warns.append(f"black picture from {b0:.2f}s to {b1:.2f}s: intended?")
    facts["black_spans"] = spans_black
    ok = not fails
    write_json(clip / "final" / f"{slug}.qa.json", {"file": path.name, "ok": ok, "failures": fails, "warnings": warns, "facts": facts})
    print(f"QA {'PASS' if ok else 'FAIL'}: {path.name}  {facts['width']}x{facts['height']} {facts['fps']}fps {facts['seconds']}s  "
          f"{facts.get('loudness', {}).get('integrated_lufs')} LUFS  {n} shots, {facts.get('views', '?')} views, {facts.get('captions', {}).get('captions', 0)} captions")
    if "caption_placement" in facts:
        cp = facts["caption_placement"]
        print(f"  captions on screen: centre x {cp['centre_x_mean']} (worst {cp['centre_x_worst']}), line y {cp['centre_y_mean']} (moves {cp['centre_y_spread']}), widest {cp['widest']} of the frame, {cp['sampled']} frames measured")
    for k in ("caption_timing_vs_pauses", "caption_timing_heard"):
        if k in facts:
            print(f"  {k}: {facts[k]}")
    for f in fails:
        print("  FAIL:", f)
    for w in warns:
        print("  warn:", w)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
