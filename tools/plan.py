"""Check a shot plan against its script and the style numbers. The director skill and this file must agree:
change a rule in one, change the other in the same edit."""
from __future__ import annotations

from common import STYLE, read_json, words_of, script_voiceover

BLURS = ("none", "light", "medium", "strong", "macro")
WPS = 2.45          # narration words per second used for estimates (about 147 wpm)


def estimate_seconds(vo_text: str) -> float:
    return round(len(words_of(vo_text)) / WPS, 2)


def check(plan: dict, script: dict) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings)."""
    err, warn = [], []
    S = STYLE["shots"]
    shots = plan.get("shots") or []
    if not shots:
        return ["plan has no shots"], warn
    for k in ("logline", "look", "sets", "cast", "shots"):
        if k not in plan:
            err.append(f"missing top-level field '{k}'")
    n = len(shots)
    lo, hi = S["target_count"]
    if n > S["hard_max"]:
        err.append(f"{n} shots: the hard limit is {S['hard_max']}. Merge shots: let a camera move, a focus shift or the action carry the change.")
    elif not lo <= n <= hi:
        warn.append(f"{n} shots (aim is {lo}-{hi}). Fine if every cut has a story reason in why_cut.")
    ids = [s.get("id") for s in shots]
    if len(set(ids)) != len(ids):
        err.append("shot ids are not unique")
    sets = {s.get("id") for s in plan.get("sets", [])}
    cast = {c.get("id") for c in plan.get("cast", [])}
    # narration coverage: every word once, in order
    want = words_of(script_voiceover(script))
    got = [w for s in shots for w in words_of(s.get("vo_text", ""))]
    if got != want:
        i = next((k for k, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
        ctx_w = " ".join(want[max(0, i - 4):i + 4])
        ctx_g = " ".join(got[max(0, i - 4):i + 4])
        err.append(f"vo_text of all shots must equal the script voiceover word for word. First difference at word {i + 1}: script '...{ctx_w}...' vs plan '...{ctx_g}...' ({len(got)} vs {len(want)} words)")
    holds = 0.0
    for i, s in enumerate(shots):
        sid = s.get("id", f"#{i + 1}")
        for k in ("vo_text", "purpose", "staging", "camera", "set"):
            if not s.get(k):
                err.append(f"{sid}: missing '{k}'")
        if s.get("set") and s["set"] not in sets:
            err.append(f"{sid}: set '{s['set']}' is not defined in sets")
        for c in s.get("cast", []):
            if c not in cast:
                err.append(f"{sid}: cast '{c}' is not defined in cast")
        cam = s.get("camera") or {}
        if cam.get("blur", "medium") not in BLURS:
            err.append(f"{sid}: camera.blur must be one of {BLURS}")
        if not cam.get("start"):
            err.append(f"{sid}: camera.start (the opening framing) is missing")
        for m in cam.get("moves", []):
            if not m.get("why"):
                err.append(f"{sid}: camera move '{m.get('move', '?')}' has no 'why' (a move needs a story reason; otherwise hold)")
        if i > 0 and not s.get("why_cut"):
            err.append(f"{sid}: why_cut is missing (what does cutting here give the viewer that a move or focus shift inside the previous shot could not?)")
        est = estimate_seconds(s.get("vo_text", ""))
        if est < S["min_seconds"]:
            warn.append(f"{sid}: only about {est}s of narration; a shot this short rarely has time to read. Merge it or give it a hold.")
        h = float(s.get("hold_after_s", 0) or 0)
        if h < 0 or h > 2.5:
            err.append(f"{sid}: hold_after_s must be between 0 and 2.5")
        holds += h
    est_total = estimate_seconds(script_voiceover(script)) + holds + STYLE["audio"]["tail_seconds"]
    if holds > 4.0:
        err.append(f"holds add up to {holds:.1f}s; keep the total at 4s or less")
    if est_total > STYLE["video"]["max_seconds"]:
        warn.append(f"estimated length {est_total:.1f}s is over {STYLE['video']['max_seconds']}s; holds will be shortened after the voice take")
    # clues: every script clue is given to a shot that actually speaks it
    for clue in script.get("clues", []) or []:
        cw = words_of(clue)
        owners = [s for s in shots if clue in (s.get("clues") or [])]
        if not owners:
            err.append(f"clue '{clue}' is not assigned to any shot (add it to that shot's clues and make it clearly visible)")
            continue
        for s in owners:
            sw = words_of(s.get("vo_text", ""))
            if not any(sw[j:j + len(cw)] == cw for j in range(len(sw) - len(cw) + 1)):
                warn.append(f"{s['id']}: carries clue '{clue}' but its vo_text does not contain those words")
    for m in (plan.get("look") or {}).get("must_not_show", []) or []:
        if m.get("until_shot") not in ids:
            err.append(f"must_not_show '{m.get('what')}': until_shot '{m.get('until_shot')}' is not a shot id")
    pal = (plan.get("look") or {}).get("palette") or []
    if not 3 <= len(pal) <= 6:
        warn.append("look.palette should name 3-5 colours")
    for st in plan.get("sets", []):
        if not st.get("mood"):
            err.append(f"set '{st.get('id')}': missing mood (a lights.MOODS name) - one light rig per set and time of day")
    return err, warn


def main(argv):
    import sys
    from common import clip_dir
    d = clip_dir(argv[0])
    plan, script = read_json(d / "shotplan.json"), read_json(d / "script.json")
    err, warn = check(plan, script)
    for w in warn:
        print("warn:", w)
    for e in err:
        print("ERROR:", e)
    n = len(plan.get("shots", []))
    if not err:
        est = sum(estimate_seconds(s["vo_text"]) + float(s.get("hold_after_s", 0) or 0) for s in plan["shots"])
        print(f"plan ok: {n} shots, about {est:.1f}s before the tail")
    return 1 if err else 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
