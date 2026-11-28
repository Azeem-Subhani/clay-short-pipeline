"""Shot plan, format 2: the rules for sets and for camera work. Called by tools/plan.py; the `shot-plan` skill describes the same rules
and must agree with this file (change one, change the other in the same edit; tools/tests/test_plan_schema.py checks the skill's example).

Why these rules exist: a set that is only `description` and `layout` is built as the minimum the script needs, and a view that is only a
size class is shot as a static cut. Format 2 makes the plan ask for a complete place and a designed camera, so the builder cannot skip them.

  sets    kind, theme, size_m, architecture (walls with openings and what is seen through them, floor, ceiling, features), four depth
          layers, typed dressing, practicals, atmosphere, readable details, the angles it must survive, and the marks (blocking)
  views   move, framing, angle, side, lens_mm, enter, still_reason, hero, separate
  shots   transition_in (read by tools/assemble.py), line_of_action, light {motivation, source}

A plan is format 2 when it says "plan_version": 2 or any set or view already uses a format 2 field. An older plan gets one warning and
keeps the older checks, so finished clips stay readable. New plans must be format 2.
The light fields (shot.light, view.hero, view.separate) are optional so that finished plans stay valid; a plan that uses any of them is
asked to use them everywhere it matters (warnings). They carry intention only, in words: no Kelvin and no watts, those live in the mood
(stagekit/lights.py) and in style.json > look. tools/blender/planlink.py viewlight_options() hands hero and separate to the per-view step.
Levels: a contradiction is an error; a matter of judgment against a measured number is a warning.
"""
from __future__ import annotations

import ast
import re

from common import ROOT, STYLE

KINDS = ("interior", "exterior", "mixed")
ANGLES = ("front", "reverse", "left", "right", "high", "low")             # the directions a set is seen from (set.must_survive, view.side)
OPPOSITE = {"front": "reverse", "reverse": "front", "left": "right", "right": "left"}
LAYERS = ("foreground", "midground", "background", "beyond")
WALLS = ("N", "S", "E", "W")
OPENING_KINDS = ("door", "window", "gap", "arch")
MOVES = ("static", "drift", "dolly", "truck", "pan", "tilt", "orbit", "crane", "follow", "track_with", "whip", "through", "rack_focus",
         "dolly_zoom", "handheld", "reveal")                               # tools/blender/stagekit/camera.py (cam.moves) plus the two holds
HOLDS = ("static", "drift")
NEEDS_TARGET = ("whip", "through", "follow", "track_with", "rack_focus", "reveal", "orbit")   # their camera methods cannot run without one
EASES = ("linear", "ease_in", "ease_out", "ease_in_out", "settle", "whip")
FRAMINGS = ("ots", "two_shot", "reverse", "low_hero", "top_down", "establish", "insert", "profile")
VIEW_ANGLES = ("eye", "low", "high", "top")
ENTERS = ("cut", "travel", "whip", "through")
TRANSITIONS = ("cut", "whip", "dissolve", "dip", "flash", "wipe", "match")  # tools/assemble.py TRANSITION_TYPES
DIRECTIONS = ("left", "right", "up", "down")
CAMERA_EVENT_TRANSITIONS = ("whip",)
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_THEMES: dict | None = None


def themes() -> dict:
    """The dressing themes of tools/blender/stagekit/dress.py: name -> {era, kind: interior|exterior}. Read from the source (the decorators), so the
    validator needs no Blender."""
    global _THEMES
    if _THEMES is None:
        out = {}
        src = (ROOT / "tools" / "blender" / "stagekit" / "dress.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.FunctionDef):
                continue
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, "id", "") == "theme" and len(d.args) >= 2:
                    kind = ast.literal_eval(d.args[2]) if len(d.args) > 2 else "room"
                    for kw in d.keywords:
                        if kw.arg == "kind":
                            kind = ast.literal_eval(kw.value)
                    out[ast.literal_eval(d.args[0])] = {"era": ast.literal_eval(d.args[1]), "kind": "interior" if kind == "room" else "exterior"}
        _THEMES = out
    return _THEMES


def _era_ok(eras, era) -> bool:
    return "any" in eras or era in eras or (era == "fantasy" and bool({"medieval", "renaissance"} & set(eras)))


def is_new(plan: dict) -> bool:
    if plan.get("plan_version") is not None:
        return int(plan.get("plan_version") or 1) >= 2
    if any(k in st for st in plan.get("sets", []) or [] for k in ("kind", "theme", "architecture", "layers", "must_survive")):
        return True
    return any(k in v for s in plan.get("shots", []) or [] for v in s.get("views", []) or [] for k in ("move", "angle", "enter", "framing"))


def _name(x) -> str:
    """The name of a thing listed as a string or as {what|name|text: ...}."""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, dict):
        for k in ("what", "name", "text", "id"):
            if isinstance(x.get(k), str):
                return x[k].strip()
    return ""


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ============================================================================= sets
def check_sets(plan: dict, err: list, warn: list):
    era = (plan.get("world") or {}).get("era")
    th = STYLE.get("sets", {})
    marks_seen = {}
    used = {s.get("set") for s in plan.get("shots", [])}
    for st in plan.get("sets", []) or []:
        sid = st.get("id", "?")
        p = f"set '{sid}'"
        if sid not in used:
            warn.append(f"{p}: no shot uses it; remove it or it will be built for nothing")
        kind = st.get("kind")
        if kind not in KINDS:
            err.append(f"{p}: kind must be one of {', '.join(KINDS)} (got {kind!r}): it decides whether the builder makes walls and a ceiling or a ground and a skyline")
            kind = None
        theme = st.get("theme")
        T = themes()
        if theme != "custom" and theme not in T:
            err.append(f"{p}: theme must be 'custom' or one of the dressing themes: {', '.join(T)} (got {theme!r})")
        elif theme in T:
            if era and not _era_ok(T[theme]["era"], era):
                err.append(f"{p}: theme '{theme}' belongs to {T[theme]['era']}, not to a {era} story")
            if kind in ("interior", "exterior") and T[theme]["kind"] != kind:
                err.append(f"{p}: theme '{theme}' dresses an {T[theme]['kind']}, but the set is an {kind}")
        _check_size(st, p, kind, err)
        _check_architecture(st, p, kind, err, warn)
        _check_layers_and_dressing(st, p, th, err, warn)
        interior = kind in ("interior", "mixed")
        for key, need, why in (("practicals", th.get("min_practicals_interior", 3) if interior else 0, "visible light sources: lamps, windows, candles, screens"),
                               ("atmosphere", th.get("min_atmosphere", 1), "haze, dust, smoke, steam or particles in the light"),
                               ("details", th.get("min_details", 3), "readable in-world things: signs, banners, papers, labels")):
            v = st.get(key)
            if not isinstance(v, list):
                err.append(f"{p}: '{key}' is missing: a list of {why}" + (f" (at least {need})" if need else ""))
                continue
            names = [_name(x) for x in v]
            if any(not n for n in names):
                err.append(f"{p}: every '{key}' entry needs a name ({why}); entries are strings or objects with 'what'")
            elif key == "practicals" and any(not (isinstance(x, dict) and x.get("where")) for x in v):
                err.append(f"{p}: every practical says where it is: {{\"what\": \"brass chandelier\", \"where\": \"above the dais\"}}")
            if len([n for n in names if n]) < need:
                err.append(f"{p}: {len([n for n in names if n])} {key}, need at least {need} (style.json > sets): {why}")
        ms = st.get("must_survive")
        if not isinstance(ms, list) or not ms:
            err.append(f"{p}: must_survive is missing: the angles this set will be seen from across all its shots, from {', '.join(ANGLES)}")
        else:
            bad = [m for m in ms if m not in ANGLES]
            if bad:
                err.append(f"{p}: must_survive has {bad}; use {', '.join(ANGLES)}")
            if "front" not in ms:
                err.append(f"{p}: must_survive must include 'front' (the main camera side)")
        marks = st.get("marks")
        if not isinstance(marks, dict) or not marks:
            err.append(f"{p}: marks is missing: {{\"queen\": [x, y, z], ...}} the named standing points and object positions the shots use (the set file's MARK must contain every name)")
        else:
            for k, v in marks.items():
                if not (isinstance(v, (list, tuple)) and len(v) in (2, 3) and all(_num(x) for x in v)):
                    err.append(f"{p}: mark '{k}' must be [x, y] or [x, y, z] in metres (got {v!r})")
            marks_seen[sid] = set(marks)
        if st.get("time_of_day") is not None or st.get("times") is not None:
            warn.append(f"{p}: the light is chosen per shot ('time'); remove 'times'/'time_of_day' from the set")


def _check_size(st, p, kind, err):
    sz = st.get("size_m")
    ok = isinstance(sz, (list, tuple)) and all(_num(x) and x > 0 for x in sz)
    if kind == "interior" and not (ok and len(sz) == 3):
        err.append(f"{p}: an interior needs size_m = [width, depth, height] in metres (got {sz!r})")
    elif kind in ("exterior", "mixed") and not (ok and len(sz) in (2, 3)):
        err.append(f"{p}: size_m = [width, depth] (or [w, d, h]) in metres is needed: the extent of the walkable stage (got {sz!r})")
    elif kind is None and sz is None:
        err.append(f"{p}: size_m is missing")
    elif kind == "interior" and ok and not 2.0 <= sz[2] <= 40:
        err.append(f"{p}: the height {sz[2]} m is not a room height (2 to 40 m)")


def _check_architecture(st, p, kind, err, warn):
    a = st.get("architecture")
    if not isinstance(a, dict):
        err.append(f"{p}: architecture is missing: what encloses the place. {{\"floor\": ..., \"ceiling\": ..., \"walls\": [{{\"side\": \"N\", \"what\": ..., \"openings\": [{{\"kind\": \"window\", \"vista\": ...}}]}}], \"features\": [...]}}")
        return
    outdoor = kind == "exterior"
    ground = a.get("ground") if outdoor else (a.get("floor") or a.get("ground"))
    if not (isinstance(ground, str) and ground.strip()):
        err.append(f"{p}: architecture.{'ground' if outdoor else 'floor'} is missing: what the people stand on")
    if kind in ("interior", "mixed"):
        c = a.get("ceiling")
        if not (isinstance(c, str) and c.strip()) and not (isinstance(c, dict) and c.get("kind")):
            err.append(f"{p}: architecture.ceiling is missing: an enclosed place has a ceiling (beamed, vaulted, flat, tiled...) even if a view never shows it")
    walls = a.get("walls")
    if walls is not None and not isinstance(walls, list):
        err.append(f"{p}: architecture.walls must be a list of {{side, what, openings}}")
        walls = []
    sides = set()
    for w in walls or []:
        if not isinstance(w, dict) or w.get("side") not in WALLS:
            err.append(f"{p}: every wall needs a 'side' from {', '.join(WALLS)} (N is the far wall, S the camera side, as in arch.room): got {w!r}")
            continue
        sides.add(w["side"])
        if not (isinstance(w.get("what"), str) and w["what"].strip()):
            err.append(f"{p}: wall {w['side']} says nothing about what it is made of or looks like ('what')")
        for k, o in enumerate(w.get("openings") or []):
            who = f"{p}: wall {w['side']} opening {k + 1}" + (f" '{o.get('id')}'" if isinstance(o, dict) and o.get("id") else "")
            if not isinstance(o, dict) or o.get("kind") not in OPENING_KINDS:
                err.append(f"{who}: kind must be one of {', '.join(OPENING_KINDS)}")
                continue
            if not (isinstance(o.get("vista"), str) and o["vista"].strip()):
                err.append(f"{who} ({o['kind']}): 'vista' is missing: say what is seen through it (a street, a courtyard, a lit room, the night sky). A door or window with nothing behind it renders as a void")
    if kind in ("interior", "mixed"):
        missing = [s for s in WALLS if s not in sides] if kind == "interior" else []
        if missing:
            err.append(f"{p}: architecture.walls describes {sorted(sides) or 'no wall'}; an interior needs all four ({', '.join(missing)} missing) so a reverse angle shows a real wall, not the void")
        elif kind == "mixed" and not sides and not a.get("features"):
            err.append(f"{p}: a mixed place needs at least one wall or a feature that encloses part of it")
    feats = a.get("features")
    if feats is not None and not (isinstance(feats, list) and all(isinstance(x, str) and x.strip() for x in feats)):
        err.append(f"{p}: architecture.features is a list of short strings (columns, beams, stairs, a dais...)")
    elif kind == "interior" and not feats:
        warn.append(f"{p}: architecture.features is empty: columns, beams, stairs, a dais or a mezzanine are what make an enclosed place read as built")


def _check_layers_and_dressing(st, p, th, err, warn):
    lay = st.get("layers")
    names: list[str] = []
    if not isinstance(lay, dict):
        err.append(f"{p}: layers is missing: {{foreground, midground, background, beyond}}, each a list of named things, so the wide has depth")
        lay = {}
    for k in LAYERS:
        v = lay.get(k)
        if not isinstance(v, list) or not [x for x in v if _name(x)]:
            err.append(f"{p}: layers.{k} is empty: " + {"foreground": "something near the camera that partly covers the frame edge (a column, a hanging banner, a table corner)",
                                                       "midground": "the working stage where the action happens",
                                                       "background": "the far wall or far side, with its own dressing",
                                                       "beyond": "what is seen past the set: sky, a vista, a room through a door"}[k])
        else:
            names += [_name(x).lower() for x in v if _name(x)]
    dr = st.get("dressing")
    count = len(names)
    typed = True
    if dr is None:
        err.append(f"{p}: dressing is missing: [{{\"what\": \"barrel\", \"where\": \"against the east wall\", \"count\": 6}}, ...]")
    elif not isinstance(dr, list):
        err.append(f"{p}: dressing must be a list of {{what, where, count?}}")
    else:
        for k, d in enumerate(dr):
            if isinstance(d, str):
                typed = False
                names.append(d.strip().lower())
                count += 1
                continue
            if not (isinstance(d, dict) and isinstance(d.get("what"), str) and d["what"].strip() and isinstance(d.get("where"), str) and d["where"].strip()):
                err.append(f"{p}: dressing[{k}] needs 'what' and 'where' (got {d!r})")
                continue
            if "count" in d and not (isinstance(d["count"], int) and not isinstance(d["count"], bool) and d["count"] >= 1):
                err.append(f"{p}: dressing[{k}] '{d['what']}': count must be a whole number of 1 or more")
            names.append(d["what"].strip().lower())
            count += d["count"] if isinstance(d.get("count"), int) and not isinstance(d.get("count"), bool) else 1
        if not typed:
            warn.append(f"{p}: dressing is the old free-text list; write it as [{{\"what\", \"where\", \"count\"}}] so the builder knows how much of what, and where")
    need_types, need_objs = th.get("min_prop_types_wide", 14), th.get("min_objects_wide", 60)
    types = len(set(names))
    if types < need_types:
        err.append(f"{p}: {types} distinct things across layers and dressing, need at least {need_types} (style.json > sets.min_prop_types_wide): a wide of a lived-in place shows that many kinds of thing")
    if typed and dr and count < need_objs:
        warn.append(f"{p}: about {count} objects counted across layers and dressing (give 'count' to the dressing); a wide shows at least {need_objs}")


# ============================================================================= camera
def _loa_error(s, sid, sets, err, new):
    """Validate shot.line_of_action; returns its camera_side or None."""
    loa = s.get("line_of_action")
    cast = list(s.get("cast") or [])
    if loa is None:
        if len(cast) >= 2 and new:
            err.append(f"{sid}: line_of_action is missing. Two or more characters share this shot: name the pair that defines the line and the side the camera stays on: "
                       f"{{\"between\": [\"{cast[0]}\", \"{cast[1]}\"], \"camera_side\": \"front\"}}")
        return None
    if not isinstance(loa, dict) or not (isinstance(loa.get("between"), list) and len(loa["between"]) == 2):
        err.append(f"{sid}: line_of_action must be {{\"between\": [a, b], \"camera_side\": one of front|reverse|left|right}}")
        return None
    marks = set((sets.get(s.get("set")) or {}).get("marks") or {})
    for x in loa["between"]:
        if x not in cast and x not in marks:
            err.append(f"{sid}: line_of_action names '{x}', which is neither in this shot's cast nor a mark of set '{s.get('set')}'")
    side = loa.get("camera_side")
    if side not in OPPOSITE:
        err.append(f"{sid}: line_of_action.camera_side must be one of front, reverse, left, right (got {side!r})")
        return None
    return side


def check_camera(plan: dict, secs: dict, err: list, warn: list):
    """secs: (shot id, view id) -> estimated seconds on screen."""
    C = STYLE["camera"]
    shots = plan.get("shots") or []
    sets = {s.get("id"): s for s in plan.get("sets", []) or []}
    must_not = plan.get("world", {}).get("must_not_show") or []
    all_views = []
    static_sec = total_sec = 0.0
    types: dict[str, int] = {}
    first_wide: dict = {}
    seen_set_wide: dict = {}
    for si, s in enumerate(shots):
        sid = s.get("id", f"#{si + 1}")
        st = sets.get(s.get("set")) or {}
        survive = set(st.get("must_survive") or [])
        line_side = _loa_error(s, sid, sets, err, True)
        tin = s.get("transition_in")
        tin_type = (tin.get("type", "cut") if isinstance(tin, dict) else tin) if tin else None
        vids = [v.get("id") for v in s.get("views") or []]
        views = s.get("views") or []
        for j, v in enumerate(views):
            vid = v.get("id", f"view{j + 1}")
            loc = f"{sid}/{vid}"
            sec = secs.get((sid, vid), 0.0)
            all_views.append((sid, vid))
            total_sec += sec
            # ---- the move
            mv = v.get("move")
            if not isinstance(mv, dict) or "type" not in mv:
                err.append(f"{loc}: move is missing: {{\"type\": one of {', '.join(MOVES)}, \"amount\"?, \"duration_s\"?, \"ease\"?, \"target\"?}}. A view is a framing plus what the camera does in it")
                mtype = None
            else:
                mtype = mv["type"]
                if mtype not in MOVES:
                    err.append(f"{loc}: move.type '{mtype}' is not in the camera library ({', '.join(MOVES)})")
                    mtype = None
            if mtype:
                types[mtype] = types.get(mtype, 0) + 1
                mv = v["move"]
                if mtype in NEEDS_TARGET and not (isinstance(mv.get("target"), str) and mv["target"].strip()):
                    err.append(f"{loc}: a {mtype} needs a 'target': " + {"whip": "the view id it whips to", "through": "the opening it passes through, and (in 'to') the view it arrives at",
                                                                       "orbit": "the cast id or mark it circles", "follow": "the cast id it follows", "track_with": "the cast id it travels beside",
                                                                       "rack_focus": "what focus moves to", "reveal": "what is revealed"}[mtype])
                for k in ("amount", "duration_s"):
                    if k in mv and not (_num(mv[k]) and (mv[k] > 0 or k == "amount")):
                        err.append(f"{loc}: move.{k} must be a number" + (" above 0" if k == "duration_s" else ""))
                if "ease" in mv and mv["ease"] not in EASES:
                    err.append(f"{loc}: move.ease '{mv['ease']}' is not one of {', '.join(EASES)}")
                dur = mv.get("duration_s")
                if _num(dur):
                    if mtype == "whip" and not C["whip_dur_s"][0] <= dur <= C["whip_dur_s"][1]:
                        warn.append(f"{loc}: a whip lasts {C['whip_dur_s'][0]}-{C['whip_dur_s'][1]} s (it is {dur} s); longer reads as a slow pan, shorter as a glitch")
                    if sec and dur > sec + 0.5:
                        warn.append(f"{loc}: the move lasts {dur} s but the view is about {sec:.1f} s on screen; it would be cut off")
                if mtype == "static":
                    if sec > 1.2 and not (isinstance(v.get("still_reason"), str) and v["still_reason"].strip()):
                        err.append(f"{loc}: a static view of about {sec:.1f} s. A held frame feels dead after 1.2 s: use a drift or a real move, or say why the camera must be still in 'still_reason' (a held reaction, a tension beat)")
                if mtype in HOLDS:
                    static_sec += sec
            # ---- framing, angle, side, lens
            if v.get("framing") is not None and v["framing"] not in FRAMINGS:
                err.append(f"{loc}: framing '{v['framing']}' is not a camera helper ({', '.join(FRAMINGS)})")
            ang = v.get("angle")
            if ang not in VIEW_ANGLES:
                err.append(f"{loc}: angle must be one of {', '.join(VIEW_ANGLES)} (eye level, low, high, or straight down). Wides are low or eye level for people, high or top-down for geography")
            side = v.get("side")
            if side not in ANGLES:
                err.append(f"{loc}: side must be one of {', '.join(ANGLES)}: the direction the camera looks from, relative to the set's front")
            if "lens_mm" in v and not (_num(v["lens_mm"]) and 10 <= v["lens_mm"] <= 200):
                err.append(f"{loc}: lens_mm must be a number from 10 to 200")
            fr = v.get("framing")
            if fr == "top_down" and ang not in (None, "top"):
                warn.append(f"{loc}: framing top_down looks straight down; set angle to 'top'")
            if fr == "low_hero" and ang not in (None, "low"):
                warn.append(f"{loc}: framing low_hero is a low angle; set angle to 'low'")
            if fr == "establish" and v.get("size") not in (None, "wide"):
                warn.append(f"{loc}: framing establish shows the place: its size should be 'wide'")
            if fr == "insert" and v.get("size") not in (None, "insert"):
                warn.append(f"{loc}: framing insert is a close look at an object: its size should be 'insert'")
            # ---- set must survive the angle
            need = set()
            if side in ANGLES:
                need.add(side)
            if ang == "low":
                need.add("low")
            if ang in ("high", "top"):
                need.add("high")
            if survive and need - survive:
                err.append(f"{loc}: the camera sees set '{s.get('set')}' from the {', '.join(sorted(need - survive))}, which its must_survive ({', '.join(sorted(survive))}) does not cover. "
                           "Either add the angle to must_survive (the builder then makes walls, ceiling and dressing that hold up from there) or change the view")
            # ---- line of action
            if line_side and side in OPPOSITE and side == OPPOSITE[line_side] and not v.get("cross_line"):
                err.append(f"{loc}: the camera is on the {side} but the line of action ({' / '.join(s['line_of_action']['between'])}) is shot from the {line_side}. "
                           "Crossing it flips who is left and who is right: stay on the declared side, or say \"cross_line\": true if the flip is the point (and show it)")
            # ---- how the view is reached
            enter = v.get("enter", "cut")
            if enter not in ENTERS:
                err.append(f"{loc}: enter must be one of {', '.join(ENTERS)}")
            elif j == 0:
                if enter != "cut" and not (enter == tin_type and enter in CAMERA_EVENT_TRANSITIONS and si > 0):
                    err.append(f"{loc}: the first view of a shot is reached by a 'cut', or by the shot's own transition_in ({tin_type or 'none'}): enter is {enter!r}")
            else:
                pm = (views[j - 1].get("move") or {}) if isinstance(views[j - 1].get("move"), dict) else {}
                if enter in ("whip", "through") and pm.get("type") != enter:
                    err.append(f"{loc}: enter is '{enter}' but the view before ({views[j - 1].get('id')}) has move '{pm.get('type')}': the {enter} is that view's move, with this view as its target")
                if pm.get("type") in ("whip", "through") and enter != pm["type"]:
                    err.append(f"{loc}: the view before ({views[j - 1].get('id')}) ends in a {pm['type']} into this one, so enter must be '{pm['type']}' (got {enter!r})")
            if mtype in NEEDS_TARGET and isinstance(mv.get("target"), str) and mv["target"].strip():
                known = set(vids) | set(s.get("cast") or []) | set(st.get("marks") or {}) | {o.get("id") for w_ in (st.get("architecture") or {}).get("walls", []) if isinstance(w_, dict) for o in w_.get("openings") or [] if isinstance(o, dict)}
                if mv["target"] not in known:
                    warn.append(f"{loc}: {mtype} target '{mv['target']}' is not a view of this shot, a cast id, a mark or an opening of set '{s.get('set')}'; the builder will not know what it is")
            if mtype in ("whip", "through") and isinstance(mv.get("target"), str) and mv["target"] in vids:
                if j + 1 >= len(vids) or vids[j + 1] != mv["target"]:
                    err.append(f"{loc}: its {mtype} target '{mv['target']}' is not the next view of the shot (the next is '{vids[j + 1] if j + 1 < len(vids) else 'none'}')")
            elif mtype in ("whip", "through") and j + 1 >= len(views) and isinstance(mv.get("target"), str):
                warn.append(f"{loc}: a {mtype} on the last view of the shot has nowhere to land in this shot; end the shot with a transition_in on the next shot instead")
            # ---- the set shown wide
            if v.get("size") == "wide" or fr == "establish":
                seen_set_wide.setdefault(s.get("set"), []).append(sid)
        first_wide.setdefault(s.get("set"), sid)
    # ---- wide coverage per set
    for setid, first_sid in first_wide.items():
        if any(m.get("set") == setid for m in must_not if isinstance(m, dict)):
            continue
        if setid not in seen_set_wide:
            err.append(f"set '{setid}' is never shown in a wide or establishing view. Show the place once (size 'wide' or framing 'establish') so the viewer knows where the people are; "
                       "or list it in world.must_not_show with {\"set\": ...} if hiding it is the point")
        elif first_sid not in seen_set_wide[setid]:
            warn.append(f"set '{setid}': its first shot ({first_sid}) never shows it wide; the first wide comes in {seen_set_wide[setid][0]}. Establish the place before or in the shot that first uses it")
    # ---- the film as a whole
    n = len(all_views)
    if n:
        moving = {t for t in types if t != "static"}
        if len(moving) < 3:
            warn.append(f"only {len(moving)} different camera move type(s) in the film ({', '.join(sorted(moving)) or 'none'}); use at least 3 (a push, a track, an orbit, a crane, a whip...)")
        top = max(types.items(), key=lambda kv: kv[1])
        if top[1] / n > 0.5:
            warn.append(f"'{top[0]}' is {top[1]} of {n} views ({top[1] / n:.0%}); no single move should be more than half of the film")
        if total_sec and static_sec / total_sec > C["max_static_share"]:
            warn.append(f"held views (static or drift) take {static_sec / total_sec:.0%} of the screen time; style.json > camera > max_static_share is {C['max_static_share']:.0%}. Give more views a move")


# ============================================================================= light
GENERIC_SOURCES = ("sun", "sunlight", "daylight", "sky", "moon", "moonlight")   # natural light: allowed where the set has an opening or no roof
_FILLER = {"light", "lights", "glow", "from", "with", "through", "above", "over", "that", "this", "the", "and"}


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 4 and w.endswith("s") else w


def _words(text: str) -> set:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) >= 3 and w not in _FILLER}


def light_sources(st: dict) -> dict:
    """What a set lists that a light can come from: its practicals (by 'what') and its openings (by id). name -> kind."""
    out = {}
    for x in st.get("practicals") or []:
        n = _name(x)
        if n:
            out[n] = "practical"
    for w in ((st.get("architecture") or {}).get("walls") or []):
        for o in (w.get("openings") or []) if isinstance(w, dict) else []:
            if isinstance(o, dict) and o.get("kind") in ("window", "door", "arch", "gap"):
                out[str(o.get("id") or f"{w.get('side')} {o['kind']}")] = o["kind"]
    return out


def source_matches(source: str, st: dict) -> bool:
    """A source names something the set lists: a practical (substring either way, or a shared meaningful word), an opening id, the word
    window or door where the set has one, or natural light (sun, sky, moon) where the set has an opening or is open to the sky."""
    src = source.strip().lower()
    if not src:
        return False
    cand = light_sources(st)
    for name in cand:
        n = name.lower()
        if src == n or src in n or n in src or (_words(src) & _words(n)):
            return True
    opening = any(k in ("window", "door", "arch", "gap") for k in cand.values())
    if (src in GENERIC_SOURCES or _words(src) & {_stem(w) for w in GENERIC_SOURCES}) and (st.get("kind") in ("exterior", "mixed") or opening):
        return True
    return bool(_words(src) & {"window", "door", "doorway"}) and opening


def check_light(plan: dict, err: list, warn: list):
    """shot.light {motivation, source}, view.hero, view.separate. Optional, but a plan that starts must carry them through (warnings)."""
    shots = plan.get("shots") or []
    sets = {s.get("id"): s for s in plan.get("sets", []) or []}
    used = any(s.get("light") is not None or any(v.get("hero") is not None or v.get("separate") is not None for v in s.get("views") or []) for s in shots)
    for si, s in enumerate(shots):
        sid = s.get("id", f"#{si + 1}")
        st = sets.get(s.get("set")) or {}
        cast = list(s.get("cast") or [])
        marks = set(st.get("marks") or {})
        lt = s.get("light")
        if lt is None:
            if used:
                warn.append(f"{sid}: no light note. Add \"light\": {{\"motivation\": one sentence in the story's words, \"source\": a window, lamp or screen of set '{s.get('set')}'}}: "
                            "the builder lights the place from that source, so a shot without one is lit by whatever the set has nearest")
        elif not isinstance(lt, dict) or not (isinstance(lt.get("motivation"), str) and lt["motivation"].strip()) or not (isinstance(lt.get("source"), str) and lt["source"].strip()):
            err.append(f"{sid}: light must be {{\"motivation\": why the light is there, in one sentence, \"source\": what it comes from}} (got {lt!r}); "
                       "for example {\"motivation\": \"cold rain light through the glass, warm lamps inside\", \"source\": \"lobby ceiling lights\"}")
        else:
            n_words = len(lt["motivation"].split())
            if n_words > 30:
                warn.append(f"{sid}: light.motivation is {n_words} words; one sentence a cameraman could act on is enough")
            if st and not source_matches(lt["source"], st):
                have = sorted(light_sources(st))
                err.append(f"{sid}: light.source '{lt['source']}' is not something set '{s.get('set')}' lists. Name one of its practicals or openings ({', '.join(have) or 'none listed'}), "
                           "or natural light (sun, sky, moon) where the set has an opening; if the story needs another source, add it to the set's practicals first")
        for j, v in enumerate(s.get("views") or []):
            loc = f"{sid}/{v.get('id', f'view{j + 1}')}"
            hero = v.get("hero")
            if hero is not None:
                if not (isinstance(hero, str) and hero.strip()):
                    err.append(f"{loc}: hero must be one cast id (or a mark of the set): the subject this view's key light is for")
                elif hero not in cast and hero not in marks:
                    err.append(f"{loc}: hero '{hero}' is not in this shot's cast ({', '.join(cast) or 'empty'}) nor a mark of set '{s.get('set')}'")
            elif used and len(cast) >= 2 and v.get("size") in ("close", "medium", "full"):
                warn.append(f"{loc}: no hero. Two or more people share this shot: say whom the light is for (\"hero\": a cast id), or the key goes to the nearest face")
            sep = v.get("separate")
            if sep is not None:
                names = [sep] if isinstance(sep, str) else sep
                if not (isinstance(names, list) and names and all(isinstance(n, str) and n.strip() for n in names)):
                    err.append(f"{loc}: separate must be a cast id or a list of them: who must come off the background (an edge light is added for them)")
                    continue
                for n in names:
                    if n not in cast:
                        err.append(f"{loc}: separate '{n}' is not in this shot's cast ({', '.join(cast) or 'empty'})")
                    elif n == hero:
                        warn.append(f"{loc}: separate '{n}' is the hero; the key already models them, name someone else or drop it")


# ============================================================================= transitions
def check_transitions(plan: dict, err: list, warn: list):
    shots = plan.get("shots") or []
    default = (plan.get("transitions") or {}).get("default", "cut")
    default = default.get("type", "cut") if isinstance(default, dict) else default
    if default not in TRANSITIONS:
        err.append(f"transitions.default '{default}' is not one of {', '.join(TRANSITIONS)}")
        default = "cut"
    types = []
    for i, s in enumerate(shots):
        sid = s.get("id", f"#{i + 1}")
        raw = s.get("transition_in")
        if raw is None:
            if i:
                types.append(default)
            continue
        d = raw if isinstance(raw, dict) else {"type": raw}
        t = d.get("type", "cut")
        if t not in TRANSITIONS:
            err.append(f"{sid}: transition_in '{t}' is not one of {', '.join(TRANSITIONS)} (tools/assemble.py plays these)")
            continue
        if i == 0:
            warn.append(f"{sid}: transition_in on the first shot has nothing to come from and is ignored")
            continue
        if "dur" in d and not (_num(d["dur"]) and 0.05 <= d["dur"] <= 1.5):
            err.append(f"{sid}: transition_in.dur must be 0.05 to 1.5 seconds")
        if "dir" in d and d["dir"] not in DIRECTIONS:
            err.append(f"{sid}: transition_in.dir must be one of {', '.join(DIRECTIONS)}")
        if "color" in d and not (isinstance(d["color"], str) and _HEX.match(d["color"])):
            err.append(f"{sid}: transition_in.color must be a #rrggbb colour")
        types.append(t)
    if len(shots) >= 2 and all(t == "cut" for t in types):
        at = next((i for i in range(1, len(shots)) if shots[i].get("set") != shots[i - 1].get("set") or shots[i].get("time") != shots[i - 1].get("time")), 1)
        warn.append(f"every shot boundary is a plain cut. Reference Shorts change shot with a camera event more than half the time: the move into {shots[at].get('id', '#' + str(at + 1))} "
                    f"({'a new place' if shots[at].get('set') != shots[at - 1].get('set') else 'a new time'}) is where a whip (transition_in: {{\"type\": \"whip\", \"dur\": 0.4}}) or a dissolve fits")
