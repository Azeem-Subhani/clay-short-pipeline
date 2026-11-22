"""Check a shot plan against its script, the character pack, the surface catalog and the style numbers.
The `shot-plan` skill and this file must agree: change a rule in one, change the other in the same edit.

What it protects:
  - the narration: every script word is covered once, in order
  - one world: every character, wardrobe piece and surface belongs to the story's period
  - readable action: every view starts on words that exist, says what it shows and why, and lasts long enough to read
  - fair payoffs: anything the ending depends on (a gate, a hidden key) is shown before it is used
"""
from __future__ import annotations

import fnmatch
import json

from common import ROOT, STYLE, read_json, script_voiceover, words_of

SIZES = ("insert", "close", "medium", "full", "wide")
_VOICE_CFG = read_json(ROOT / "config" / "voices.json")
WPS = float(_VOICE_CFG.get("tts", {}).get("pacing", {}).get("target_wps", 230 / 60))  # narration words per second (~230 wpm, target 220-240 wpm)
MOODS = ("day_clear", "day_soft", "morning", "golden_hour", "sunset", "dusk", "night_moon", "storm", "interior_day", "interior_warm", "cave")


def estimate_seconds(vo_text: str) -> float:
    return round(len(words_of(vo_text)) / WPS, 2)


def _registry() -> dict:
    return read_json(ROOT / "config" / "cast.json")


def _catalog() -> dict:
    return read_json(ROOT / "library" / "materials" / "catalog.json")["surfaces"]


def _era_ok(eras, era) -> bool:
    return "any" in eras or era in eras or (era == "fantasy" and bool({"medieval", "renaissance"} & set(eras)))


def _find(words: list[str], phrase: list[str], start: int = 0) -> int:
    n = len(phrase)
    for i in range(start, len(words) - n + 1):
        if words[i:i + n] == phrase:
            return i
    return -1


def check_cast(plan: dict, err: list, warn: list):
    reg = _registry()
    era = (plan.get("world") or {}).get("era")
    seen_colors = {}
    for c in plan.get("cast", []):
        cid = c.get("id", "?")
        base = c.get("base")
        if base not in reg["characters"]:
            err.append(f"cast '{cid}': base '{base}' is not in the character pack. Choose from: {', '.join(reg['characters'])}")
            continue
        ch = reg["characters"][base]
        cos = c.get("costume") or {}
        for k in cos.get("recolor", {}):
            if k not in ch["colors"]:
                err.append(f"cast '{cid}': {base} has no colour '{k}' (it has {', '.join(ch['colors'])})")
        for pat in cos.get("hide", []):
            if not any(fnmatch.fnmatchcase(p, pat) for p in ch["parts"]):
                err.append(f"cast '{cid}': hide '{pat}' matches no part of {base}")
        for w in cos.get("wear", []):
            item = w.get("item")
            if item not in reg["wardrobe"]:
                err.append(f"cast '{cid}': wardrobe has no '{item}' (it has {', '.join(reg['wardrobe'])})")
            elif era and not _era_ok(reg["wardrobe"][item]["era"], era):
                err.append(f"cast '{cid}': '{item}' belongs to {reg['wardrobe'][item]['era']}, not to a {era} story")
        if era and not _era_ok(ch["era"], era):
            ad = ch.get("adapt", {}).get(era)
            if ad is None:
                err.append(f"cast '{cid}': {base} ({ch['looks']}) belongs to {ch['era']} and has no costume recipe for a {era} story. "
                           f"Cast a character of that period, or one with an 'adapt' entry for it in config/cast.json.")
            else:
                missing = [h for h in ad.get("hide", []) if h not in cos.get("hide", [])]
                if missing:
                    err.append(f"cast '{cid}': to pass as {era}, {base} must hide {missing} ({ad.get('note', '')})")
                unre = [k for k in ad.get("recolor_hint", []) if k not in cos.get("recolor", {})]
                if unre:
                    warn.append(f"cast '{cid}': {base} in a {era} story usually needs new colours for {unre} ({ad.get('note', '')})")
        if not c.get("role"):
            err.append(f"cast '{cid}': missing 'role' (who they are in the story)")
        if not c.get("reads_as"):
            warn.append(f"cast '{cid}': add 'reads_as' - the three things that tell a viewer who this is at a glance (silhouette, colour, one prop)")
        sig = c.get("color")
        if sig:
            if sig.lower() in seen_colors:
                warn.append(f"cast '{cid}' and '{seen_colors[sig.lower()]}' share the signature colour {sig}: give each character its own")
            seen_colors[sig.lower()] = cid


def check(plan: dict, script: dict) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings)."""
    err, warn = [], []
    S, V = STYLE["shots"], STYLE["views"]
    shots = plan.get("shots") or []
    if not shots:
        return ["plan has no shots"], warn
    for k in ("logline", "world", "cast", "sets", "shots"):
        if k not in plan:
            err.append(f"missing top-level field '{k}'")
    reg = _registry()
    world = plan.get("world") or {}
    era = world.get("era")
    if era not in reg["eras"]:
        err.append(f"world.era must be one of {', '.join(reg['eras'])} (got {era!r}). Everything on screen is checked against it.")
    for k in ("place", "rules"):
        if not world.get(k):
            err.append(f"world.{k} is missing: say where and when we are, and what does and does not belong there")
    pal = world.get("palette") or []
    if not 3 <= len(pal) <= 6:
        warn.append("world.palette should name 3-6 colours")
    cat = _catalog()
    for name in list(world.get("surfaces", [])) + [s for st in plan.get("sets", []) for s in st.get("surfaces", [])]:
        if name not in cat:
            err.append(f"surface '{name}' is not in library/materials/catalog.json (it has {', '.join(cat)})")
        elif era and not _era_ok(cat[name]["era"], era):
            err.append(f"surface '{name}' ({cat[name]['what']}) belongs to {cat[name]['era']}, not to a {era} story")
    check_cast(plan, err, warn)
    n = len(shots)
    if n > S["hard_max"]:
        err.append(f"{n} shots: a shot is one staged take in one set at one time of day. More than {S['hard_max']} means the story has too many places.")
    ids = [s.get("id") for s in shots]
    if len(set(ids)) != len(ids):
        err.append("shot ids are not unique")
    sets = {s.get("id"): s for s in plan.get("sets", [])}
    cast = {c.get("id") for c in plan.get("cast", [])}
    for st in plan.get("sets", []):
        for k in ("description", "layout"):
            if not st.get(k):
                err.append(f"set '{st.get('id')}': missing '{k}'" + (" (where the things the story uses stand in relation to each other and to the camera side)" if k == "layout" else ""))
    # narration coverage: every word once, in order
    want = words_of(script_voiceover(script))
    got = [w for s in shots for w in words_of(s.get("vo_text", ""))]
    if got != want:
        i = next((k for k, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
        err.append(f"vo_text of all shots must equal the script voiceover word for word. First difference at word {i + 1}: script "
                   f"'...{' '.join(want[max(0, i - 4):i + 4])}...' vs plan '...{' '.join(got[max(0, i - 4):i + 4])}...' ({len(got)} vs {len(want)} words)")
    holds = 0.0
    order = []                       # (shot id, view id) in screen order
    total_views = 0
    for i, s in enumerate(shots):
        sid = s.get("id", f"#{i + 1}")
        for k in ("vo_text", "purpose", "action", "set", "time", "views"):
            if not s.get(k):
                err.append(f"{sid}: missing '{k}'")
        if s.get("set") and s["set"] not in sets:
            err.append(f"{sid}: set '{s['set']}' is not defined in sets")
        if s.get("time") and s["time"] not in MOODS:
            err.append(f"{sid}: time '{s['time']}' is not a light mood ({', '.join(MOODS)})")
        for c in s.get("cast", []):
            if c not in cast:
                err.append(f"{sid}: cast '{c}' is not defined in cast")
        words = words_of(s.get("vo_text", ""))
        pos = 0
        starts = []
        vids = set()
        for j, v in enumerate(s.get("views") or []):
            vid = v.get("id", f"view{j + 1}")
            if vid in vids:
                err.append(f"{sid}/{vid}: view ids must be unique inside a shot")
            vids.add(vid)
            order.append((sid, vid))
            total_views += 1
            for k in ("shows", "why"):
                if not v.get(k):
                    err.append(f"{sid}/{vid}: missing '{k}'" + (" (what the viewer sees: who, doing what, with what)" if k == "shows" else " (what the viewer needs at this moment that the view before did not give)"))
            if v.get("size") not in SIZES:
                err.append(f"{sid}/{vid}: size must be one of {SIZES}")
            on = v.get("on", "")
            if j == 0 and on in ("", "start"):
                idx = 0
            else:
                ph = words_of(on)
                idx = _find(words, ph, pos) if ph else -1
                if idx < 0:
                    err.append(f"{sid}/{vid}: 'on' must be words from this shot's vo_text, in order after the previous view (got {on!r}). "
                               "A view starts on the first word it illustrates, or a beat before it.")
                    idx = pos
            if j == 0 and idx > 0:
                err.append(f"{sid}/{vid}: the first view of a shot starts with the shot (use \"on\": \"start\")")
            starts.append(idx)
            pos = idx
        for j, v in enumerate(s.get("views") or []):
            end = starts[j + 1] if j + 1 < len(starts) else len(words)
            sec = (end - starts[j]) / WPS
            vid = v.get("id", f"view{j + 1}")
            if sec < V["min_seconds"] and v.get("size") != "insert" and end > starts[j]:
                warn.append(f"{sid}/{vid}: about {sec:.1f}s ({end - starts[j]} words). Too short to read unless it is an insert: merge it or start it earlier.")
            if sec > V["max_seconds_without_change"] and not v.get("inside"):
                warn.append(f"{sid}/{vid}: about {sec:.1f}s on one framing. Say in 'inside' what changes during it (an action, a reaction, a camera travel), or give the viewer a closer view.")
        h = float(s.get("hold_after_s", 0) or 0)
        if h < 0 or h > 2.5:
            err.append(f"{sid}: hold_after_s must be between 0 and 2.5")
        holds += h
    lo, hi = V["per_short"]
    if total_views < lo:
        warn.append(f"{total_views} views in the whole Short. The reference Shorts use {lo}-{hi}: with fewer, check that no framing is left on screen after it has said everything it has to say.")
    elif total_views > hi:
        warn.append(f"{total_views} views. Over {hi} usually means cutting on every phrase: keep the framing while the action inside it carries the line.")
    first = (shots[0].get("views") or [{}])[0]
    if first.get("size") == "wide":
        warn.append("the first view is wide. The first second decides the swipe: open on the character and the event (the ring leaving her hand), then show the place.")
    est_total = estimate_seconds(script_voiceover(script)) + holds + STYLE["audio"]["tail_seconds"]
    if holds > 4.0:
        err.append(f"holds add up to {holds:.1f}s; keep the total at 4s or less")
    if est_total > STYLE["video"]["max_seconds"]:
        warn.append(f"estimated length {est_total:.1f}s is over {STYLE['video']['max_seconds']}s; holds will be shortened after the voice take")
    # setups: what the payoff needs must be seen first
    idx = {k: n for n, k in enumerate(order)}

    def ref(r):
        if not isinstance(r, str) or "/" not in r:
            return None
        a, b = r.split("/", 1)
        return idx.get((a, b))

    for su in plan.get("setups", []) or []:
        a, b = ref(su.get("shown_in")), ref(su.get("pays_off_in"))
        what = su.get("what", "?")
        if a is None or b is None:
            err.append(f"setup '{what}': shown_in and pays_off_in must be 'shot/view' ids that exist (got {su.get('shown_in')!r}, {su.get('pays_off_in')!r})")
        elif a >= b:
            err.append(f"setup '{what}': it pays off in {su['pays_off_in']} but is only shown in {su['shown_in']}. Show it earlier, clearly, as the subject of a view.")
    fmt = plan.get("format", "")
    if fmt in ("rule-of-three", "twist", "ticking-clock", "slow-burn") and not plan.get("setups"):
        warn.append("no 'setups': list what the ending depends on (the thing the clever answer uses) and the view that shows it before it is needed")
    # clues (twist formats): every script clue belongs to a view that speaks it
    for clue in script.get("clues", []) or []:
        owners = [(s, v) for s in shots for v in s.get("views", []) if clue in (v.get("clues") or [])]
        if not owners:
            err.append(f"clue '{clue}' is not assigned to any view (add it to that view's 'clues' and make it the subject of the frame)")
    for m in world.get("must_not_show", []) or []:
        if m.get("until") and ref(m["until"]) is None and m["until"] not in ids:
            err.append(f"must_not_show '{m.get('what')}': 'until' must be a shot id or 'shot/view'")
    return err, warn


def main(argv):
    from common import clip_dir
    d = clip_dir(argv[0])
    plan, script = read_json(d / "shotplan.json"), read_json(d / "script.json")
    err, warn = check(plan, script)
    for w in warn:
        print("warn:", w)
    for e in err:
        print("ERROR:", e)
    if not err:
        nv = sum(len(s.get("views", [])) for s in plan["shots"])
        est = sum(estimate_seconds(s["vo_text"]) + float(s.get("hold_after_s", 0) or 0) for s in plan["shots"])
        print(f"plan ok: {len(plan['shots'])} shot(s), {nv} views, about {est:.1f}s before the tail; world: {plan['world']['era']}, cast: "
              + ", ".join(f"{c['id']}={c['base']}" for c in plan["cast"]))
    return 1 if err else 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
