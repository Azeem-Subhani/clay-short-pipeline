"""Where the shot plan and a set file must agree, and the set audit of a built shot. Shared by run_shot.py (stills mode) and set_preview.py.

The plan (shotplan.json > sets[]) declares, for each set: its theme, the marks (named standing points) the shots use, and the light moods
(the `time` of each shot that uses it). The set file (blender/set_<id>.py) must declare the same: module-level MARK with every planned
name, THEME equal to the plan's theme, LIGHT with every mood the plan asks for. `agreement()` compares them without building anything.

`audit_items()` runs stagekit.audit on a BUILT shot (the cameras of its views are known by then) and returns checks.json items
{level, code, source: "set", ...} plus the inventory, so a shot staged in a poor or broken set is blocked the same way as a broken camera.

Items are plain dicts: {"level": "block"|"warn", "code": ..., "source": "set", "view": None, "frame": None, "text": ...}. The text says what to change.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOMS: list = []                                   # every arch.Room built since install_recorder(), in order


def _item(level: str, code: str, text: str, view=None) -> dict:
    return {"level": level, "code": code, "source": "set", "view": view, "frame": None, "text": text}


def install_recorder():
    """Remember the rooms arch.room() builds, so the audit can use the Room object (a shot script does not hand it to run_shot)."""
    from stagekit import arch
    if getattr(arch.room, "_planlink", False):
        ROOMS.clear()
        return
    orig = arch.room

    def room(*a, **k):
        R = orig(*a, **k)
        ROOMS.append(R)
        return R
    room._planlink = True
    arch.room = room


def is_new_plan(plan: dict) -> bool:
    """A plan whose sets declare marks, a theme or architecture (format 2). Older plans have nothing to agree with and are not audited."""
    return any(k in s for s in plan.get("sets", []) or [] for k in ("marks", "theme", "architecture", "layers"))


def plan_set(plan: dict, set_id: str) -> dict:
    return next((s for s in plan.get("sets", []) or [] if s.get("id") == set_id), {})


def times_of(plan: dict, set_id: str) -> list[str]:
    """The light moods the plan's shots use for a set, in order of first use."""
    out: list[str] = []
    for s in plan.get("shots", []) or []:
        if s.get("set") == set_id and s.get("time") and s["time"] not in out:
            out.append(s["time"])
    return out


def viewlight_options(shot_plan: dict | None) -> dict:
    """The plan's light intention as options for the per-view step: {"hero": {view: cast id}, "edge": {view: [cast ids]}} from each view's
    `hero` and `separate`. Only cast ids of the shot are passed (a hero that is a mark of the set is a prop, which the key finds by itself).
    The step lights one rig per unbroken camera move, from the view that was cut to, so a later view of the same run does not change it.
    A shot file hands it over with one line at the end of build_shot, and may add key_side= or scale= (viewlight.shape takes dicts keyed by view id):

        shot.viewlight = planlink.viewlight_options(getattr(shot, "plan", None))      # run_shot then calls viewlight.shape with these

    Returns {} for a plan with neither field (the step then picks the hero itself)."""
    plan = shot_plan or {}
    cast = set(plan.get("cast") or [])
    hero, edge = {}, {}
    for v in plan.get("views") or []:
        vid = v.get("id")
        if not vid:
            continue
        if isinstance(v.get("hero"), str) and v["hero"] in cast:
            hero[vid] = v["hero"]
        sep = v.get("separate")
        names = [sep] if isinstance(sep, str) else list(sep or [])
        names = [n for n in names if isinstance(n, str) and n in cast]
        if names:
            edge[vid] = names
    out = {}
    if hero:
        out["hero"] = hero
    if edge:
        out["edge"] = edge
    return out


def set_file(clip: Path, set_id: str) -> Path:
    return Path(clip) / "blender" / f"set_{set_id}.py"


def load_set_module(path: Path):
    """Import a set file without building anything (build_set is only defined, not called)."""
    path = Path(path)
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(f"planlink_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(path.parent))


def agreement(plan: dict, set_id: str, clip: Path, times: list[str] | None = None, mod=None) -> list[dict]:
    """Compare the plan's entry for a set with its set file. Returns items (block or warn)."""
    ps = plan_set(plan, set_id)
    f = set_file(clip, set_id)
    rel = f"blender/set_{set_id}.py"
    if not ps:
        return [_item("block", "set_not_in_plan", f"set '{set_id}' is not in the plan's sets; add it (with its marks) or fix the shot's 'set'")]
    if not f.exists():
        return [_item("block", "set_file_missing", f"{rel} does not exist: the plan declares set '{set_id}' (theme {ps.get('theme')}, {ps.get('size_m')} m); build it (the set file comes before the shots)")]
    items: list[dict] = []
    try:
        mod = mod or load_set_module(f)
    except Exception as e:                                       # a set file that cannot even be imported
        return [_item("block", "set_file_broken", f"{rel} cannot be loaded: {type(e).__name__}: {e}")]
    marks = ps.get("marks") or {}
    have = getattr(mod, "MARK", None)
    if not isinstance(have, dict):
        if marks:
            items.append(_item("block", "set_no_mark", f"{rel} defines no module-level MARK = {{name: (x, y, z)}}, but the plan names {len(marks)} mark(s): {', '.join(marks)}"))
    else:
        missing = [k for k in marks if k not in have]
        for k in missing:
            at = marks[k]
            items.append(_item("block", "set_mark_missing", f"the plan's mark '{k}' (at {list(at)}) is not in MARK of {rel}: add MARK['{k}'] = ({', '.join(str(x) for x in at)}"
                               f"{'' if len(at) == 3 else ', 0.0'}) or take the mark out of the plan (it is where a character or object will be staged)"))
        for k, at in marks.items():
            if k in have and isinstance(at, (list, tuple)) and len(at) >= 2:
                dx, dy = float(have[k][0]) - float(at[0]), float(have[k][1]) - float(at[1])
                if (dx * dx + dy * dy) ** 0.5 > 0.5:
                    items.append(_item("warn", "set_mark_moved", f"mark '{k}' is at ({have[k][0]:.1f}, {have[k][1]:.1f}) in {rel} but the plan puts it at ({at[0]}, {at[1]}); update the plan or the set so they say the same"))
    theme = ps.get("theme")
    if theme and theme != "custom":
        decl = getattr(mod, "THEME", None)
        if decl is None:
            items.append(_item("warn", "set_theme_undeclared", f"{rel} does not declare THEME = '{theme}' (the plan's theme); add it so the agreement can be checked"))
        elif decl != theme:
            items.append(_item("block", "set_theme_mismatch", f"{rel} is dressed as '{decl}' but the plan's theme for set '{set_id}' is '{theme}': rebuild the set or change the plan"))
    light = getattr(mod, "LIGHT", None)
    if isinstance(light, dict):
        for t in (times if times is not None else times_of(plan, set_id)):
            if t not in light:
                items.append(_item("block", "set_time_missing", f"the plan lights set '{set_id}' as '{t}' but LIGHT in {rel} has only {', '.join(light) or 'nothing'}: add that mood to LIGHT and make build_set handle it (the same rig for every shot at that time)"))
    elif times_of(plan, set_id):
        items.append(_item("warn", "set_light_undeclared", f"{rel} defines no LIGHT = {{mood: options}}: declare the moods it can be built in ({', '.join(times_of(plan, set_id))})"))
    return items


def preflight(clip: Path, shot_id: str, plan: dict):
    """Agreement items for the set of a shot, and the set module (for WIDE). Never raises."""
    try:
        sh = next((s for s in plan.get("shots", []) or [] if s.get("id") == shot_id), {})
        sid = sh.get("set")
        if not sid or not plan.get("sets"):
            return [], None
        if not is_new_plan(plan):
            return [], None                                      # a plan in the old format: nothing declared to agree with
        mod = None
        f = set_file(clip, sid)
        if f.exists():
            try:
                mod = load_set_module(f)
            except Exception:
                mod = None
        return agreement(plan, sid, clip, [sh["time"]] if sh.get("time") else [], mod), mod
    except Exception as e:                                       # the check must never stop a build
        return [_item("warn", "set_check_failed", f"the plan/set agreement check failed: {type(e).__name__}: {e}")], None


def audit_items(shot, mod=None, plan: dict | None = None) -> dict:
    """Run stagekit.audit on the built shot: the set's WIDE (else the first wide view) is the camera the thresholds are judged on; every view's camera
    (at its first and last frame) is checked for the void. Returns {"items": [...], "inventory": {...}, "issues": n} ; {} when it cannot run."""
    import bpy
    from stagekit import audit as audit_mod
    cam_ob = bpy.context.scene.camera
    cams = []
    wide = getattr(mod, "WIDE", None) if mod is not None else None
    views = list(getattr(getattr(shot, "camera", None), "views", []))
    sc = bpy.context.scene
    f_now = sc.frame_current
    poses = []
    for v in views:
        for tag, f in (("start", v["frame"]), ("end", v.get("end_frame") or v["frame"])):
            sc.frame_set(int(f))
            bpy.context.view_layer.update()
            m = cam_ob.matrix_world
            from mathutils import Vector
            if tag == "end" and poses and poses[-1]["name"].startswith(f"view {v['id']} ") and (Vector(poses[-1]["pos"]) - m.translation).length < 0.05:
                continue                                          # a held view: the end pose says nothing the start did not
            poses.append({"name": f"view {v['id']} ({tag})", "pos": tuple(m.translation), "aim": tuple(m.translation + (m.to_3x3() @ Vector((0, 0, -1)))), "lens": float(cam_ob.data.lens), "size": v.get("size")})
    sc.frame_set(f_now)
    if wide is not None:
        cams.append({"name": "set WIDE", "pos": tuple(wide[0]), "aim": tuple(wide[1]), "lens": float(wide[2])})
    else:
        w = next((p for p in poses if p.get("size") == "wide"), None)
        if w is None:
            return {"items": [_item("warn", "set_no_wide", "the set file defines no WIDE and the shot has no wide view, so the set's density was judged from a close view; define WIDE = (pos, aim, lens) in the set file")]}
        cams.append(dict(w, name=w["name"] + " as wide"))
    cams += poses
    room = ROOMS[0] if ROOMS else None
    if mod is not None and getattr(mod, "AREA", None) is not None and getattr(mod, "SIZE", None) is None:
        room = None                                               # an exterior set (AREA, no SIZE): a room built inside it (a lobby behind glass) is
                                                                  # not its bounds; judge it as setpreview does, as an exterior
    hidden = []
    for a in list(getattr(shot, "actors", {}).values()):         # the cast is not part of the set: it must not hide pieces from the audit's rays
        top = getattr(a, "stage", None) or getattr(a, "root", None)
        if top is None:
            continue
        for ob in [top, *top.children_recursive]:
            if not ob.hide_render:
                ob.hide_render = True
                hidden.append(ob)
    try:
        res = audit_mod.audit(cams, room=room, exterior=(room is None), interior=(room is not None), wide_index=0)
    finally:
        for ob in hidden:
            ob.hide_render = False
    items = []
    for i in res["issues"]:
        items.append(_item(i["level"], "set_" + i["code"], f"{i['object']}: {i['detail']}" + _advice(i["code"])))
    return {"items": items, "inventory": res["inventory"], "ok": res["ok"], "thresholds": res.get("thresholds")}


ADVICE = {
    "few_prop_types": " (dress the set with more kinds of thing: stagekit.dress / furnish; the plan's layers and dressing list what is wanted)",
    "few_objects": " (add objects in every depth layer, not duplicates of one kind)",
    "layers_missing": " (a wide needs a foreground occluder, the midground stage, a background and something beyond: sky, a vista, a room through a door)",
    "few_practicals": " (add lamps, candles, screens or window light the viewer can see)",
    "no_atmosphere": " (add dust, haze, smoke or a light shaft)",
    "few_details": " (add signs, banners, papers, labels the viewer can read)",
    "void": " (close the gap: a wall, a vista behind the opening, or move the camera inside the set)",
    "opening_void": " (add arch.vista or a room behind the door or window)",
    "floating": " (set it on its support)",
    "sunk": " (lift it out of what it stands on)",
}


def _advice(code: str) -> str:
    return ADVICE.get(code, "")


def summary_line(items: list[dict]) -> str:
    b = sum(1 for i in items if i["level"] == "block")
    w = sum(1 for i in items if i["level"] == "warn")
    return json.dumps({"blocking": b, "warnings": w})
