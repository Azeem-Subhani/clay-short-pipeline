"""stagekit.core - scene setup, locked render settings, time and keyframe helpers.

Everything here runs inside Blender 5.3 (`blender -b --python ...`) or the `bpy` wheel.
One shot = one staged take in one set = one scene = frames 1..N at the project frame rate.
The camera shows the take through one or more views (camera.Camera.view).
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

PROJECT = Path(os.environ.get("SHORTS_PROJECT") or os.environ.get("CLAY_PROJECT") or Path(__file__).resolve().parents[3])
STYLE = json.loads((PROJECT / "style" / "style.json").read_text(encoding="utf-8"))
PACK_DIR = "characters_beta_0_4"


def pack_blend() -> Path:
    """The character library .blend of the 2D pack (packs/characters_beta_0_4/**/character-library*.blend).
    CAST_PACK in .env may point at another pack folder or straight at a .blend."""
    root = Path(os.environ.get("CAST_PACK") or PROJECT / "packs" / PACK_DIR)
    if root.suffix == ".blend" and root.exists():
        return root
    hits = sorted(root.rglob("character-library*.blend"), key=lambda q: q.stat().st_mtime) if root.exists() else []
    if not hits:
        raise FileNotFoundError(
            f"Character pack not found under {root}. Put characters_beta_0_4.zip in packs/ and run `python tools/clip.py setup`, "
            "or set CAST_PACK to the folder that holds character-library_*.blend.")
    return hits[-1]


# ----------------------------------------------------------------------------- shot context
class Shot:
    """Time base of one shot. Times are seconds from the start of the shot; frames start at 1."""

    def __init__(self, shot_id: str, seconds: float, fps: int | None = None, quality: str = "final"):
        self.id = shot_id
        self.fps = int(fps or STYLE["video"]["fps"])
        self.seconds = float(seconds)
        self.frames = max(1, int(round(self.seconds * self.fps)))
        self.quality = quality
        self.notes: list[str] = []          # free-form notes the builder leaves for the reviewer
        self.subjects: dict[str, object] = {}  # name -> object the frame must keep readable (used by checks)
        self.subject_moments: dict[str, set] = {}  # name -> the only moments in which that subject is checked
        self.moments: dict[str, float] = {}    # name -> time in seconds worth a review still
        self.words: list[dict] = []            # narration words of this shot: {"text", "start", "end"} in shot seconds
        self.plan: dict = {}                   # this shot's entry in shotplan.json
        self.world: dict = {}                  # the plan's world bible (period, place, palette)
        self.cast_plan: dict = {}              # cast id -> plan entry
        self.actors: dict = {}                 # cast id -> Actor, filled by cast.actor()
        self.props: dict = {}                  # name -> object the story handles (checked for grounding)
        self.airborne: list = []               # (name, t0, t1) spans where an actor or prop is meant to be off the ground
        self.actions: list = []                # every actor.do(...) of the shot: {"actor", "action", "t0", "t1"} (for the reviewer)

    def f(self, t: float) -> int:
        """Seconds -> frame number, clamped to the shot."""
        return max(1, min(self.frames, 1 + int(round(float(t) * self.fps))))

    def t(self, phrase: str, nth: int = 1, edge: str = "start", offset: float = 0.0) -> float:
        """When the narrator says `phrase` in this shot, in shot seconds. Key actions to words, not to guessed numbers:
        shot.t("lights went out", edge="end") is the moment the last of those words finishes.
        A move should START a little before the word it lands on: use offset=-0.4."""
        import re

        def norm(w):
            return re.sub(r"[^a-z0-9']", "", w.lower().replace("\u2019", "'")).strip("'")

        want = [norm(w) for w in phrase.split() if norm(w)]
        have = [norm(w["text"]) for w in self.words]
        hits = [i for i in range(len(have) - len(want) + 1) if have[i:i + len(want)] == want]
        if not hits:
            raise KeyError(f"shot {self.id}: the narration has no phrase {phrase!r}. Words: {' '.join(w['text'] for w in self.words)}")
        i = hits[min(len(hits), nth) - 1]
        w = self.words[i + len(want) - 1] if edge == "end" else self.words[i]
        return max(0.0, min(self.seconds, (w["end"] if edge == "end" else w["start"]) + offset))

    def span(self, phrase: str, nth: int = 1) -> tuple[float, float]:
        """(start, end) of a spoken phrase in shot seconds: for speech, gestures that last as long as the words."""
        return self.t(phrase, nth, "start"), self.t(phrase, nth, "end")

    def said(self, t0: float, t1: float) -> str:
        """The narration words spoken between two times (labels on review sheets)."""
        return " ".join(w["text"] for w in self.words if w["end"] > t0 and w["start"] < t1)

    def moment(self, name: str, t: float):
        """Mark a story moment; review stills are rendered here."""
        self.moments[name] = float(t)

    def subject(self, name: str, obj, moments=None):
        """Register what the viewer must be able to read (a character head, a clue prop, a point).
        moments=["reach", "end"] limits the checks to those review moments (a hand that only matters at the end)."""
        self.subjects[name] = obj
        if moments:
            self.subject_moments[name] = set(moments)
        else:
            self.subject_moments.pop(name, None)


_SHOT: Shot | None = None


def current() -> Shot:
    if _SHOT is None:
        raise RuntimeError("no shot: call stagekit.begin(...) first (run_shot.py does this for you)")
    return _SHOT


def stable_seed(name: str, mod: int = 9973) -> int:
    """A seed from a name that is the same in every run. Python's own hash() of a string changes each time Blender starts, so an idle
    seeded with it swayed and blinked differently in the review stills, in the render, and in each chunk of one render (Blender is
    restarted every --chunk frames)."""
    import zlib
    return zlib.crc32(str(name).encode("utf-8")) % mod


def begin(shot_id: str, seconds: float, quality: str = "final", fps: int | None = None) -> Shot:
    """Empty scene with the locked project render settings."""
    global _SHOT
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _SHOT = Shot(shot_id, seconds, fps, quality)
    sc = bpy.context.scene
    sc.name = shot_id
    sc.frame_start, sc.frame_end = 1, _SHOT.frames
    sc.frame_set(1)
    apply_render_settings(sc, quality)
    prefs = bpy.context.preferences.edit
    prefs.keyframe_new_interpolation_type = "BEZIER"
    prefs.keyframe_new_handle_type = "AUTO_CLAMPED"     # every move eases in and out by default
    return _SHOT


# What the last apply_render_settings call did: every setting it set, and every one that Blender refused.
# stagekit/review.py puts this into checks.json, so a wrong property name shows up in the review instead of passing silently.
RENDER_REPORT: dict = {"quality": None, "applied": [], "failed": [], "white_balance_k": None, "grade": None}


def look(key: str, default=None):
    """A value under `look` in style/style.json, by dotted key: core.look("cloth.sheen", 0.7).
    Returns `default` when the key is missing, so code keeps working with an older style file."""
    node = STYLE.get("look", {})
    for part in str(key).split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def quality() -> str:
    """The quality name of the shot being built or rendered: "final", "preview" or "draft" ("final" before a shot exists)."""
    return _SHOT.quality if _SHOT is not None else "final"


_SHADOW_RES_FALLBACK = {"final": 0.004, "preview": 0.008, "draft": 0.016}


def shadow_res(scale: float = 1.0) -> float:
    """Metres per shadow texel for the quality being rendered (look.shadow.res_m), times `scale`.
    Pass it to a light's shadow_maximum_resolution; `scale` is for a light that is bigger or softer than a key."""
    q = quality()
    table = look("shadow.res_m", None) or _SHADOW_RES_FALLBACK
    base = float(table.get(q, _SHADOW_RES_FALLBACK.get(q, 0.004)))
    return base * float(scale)


def _put(target, attr: str, value, label: str | None = None, fallback=None) -> bool:
    """Set one property and record the result in RENDER_REPORT. A wrong name or value is reported (and printed as a
    WARNING), never swallowed. `fallback` is tried, and recorded as its own setting, when the wanted value is refused."""
    name = label or attr
    try:
        setattr(target, attr, value)
    except (AttributeError, TypeError, ValueError) as ex:
        err = f"{type(ex).__name__}: {ex}"
        RENDER_REPORT["failed"].append({"name": name, "wanted": str(value), "error": err})
        print(f"WARNING render setting {name} = {value!r} could not be applied: {err}", flush=True)
        if fallback is not None:
            _put(target, attr, fallback, f"{name} (fallback)")
        return False
    RENDER_REPORT["applied"].append({"name": name, "value": value if isinstance(value, (int, float, str, bool)) or value is None else str(value)})
    return True


def set_white_balance(kelvin: float | None) -> None:
    """Camera-style white balance in the view settings. `kelvin` is the light colour that should render as white:
    a lower number cools the picture. None or 6500 switches it off. The value is kept on the scene (custom property
    "look_white_balance_k", 0 = off) and in RENDER_REPORT["white_balance_k"] for the review."""
    vs = bpy.context.scene.view_settings
    on = kelvin is not None and abs(float(kelvin) - 6500.0) > 1e-6
    _put(vs, "use_white_balance", bool(on), "view_settings.use_white_balance")
    if on:
        _put(vs, "white_balance_temperature", float(kelvin), "view_settings.white_balance_temperature")
        _put(vs, "white_balance_tint", 0.0, "view_settings.white_balance_tint")
    bpy.context.scene["look_white_balance_k"] = float(kelvin) if on else 0.0
    RENDER_REPORT["white_balance_k"] = float(kelvin) if on else None


GRADE_GROUP = "look_grade"


def grade(enabled: bool = True, **overrides) -> None:
    """The grade, in Blender's compositor: a colour-neutral contrast (ASC-CDL power, slope 1, offset 0) and a bloom on the
    brightest values only. Defaults come from look.grade; overrides: contrast_power, bloom_threshold, bloom_strength,
    bloom_size. enabled=False takes it out and switches the compositor off."""
    sc = bpy.context.scene
    old = bpy.data.node_groups.get(GRADE_GROUP)
    if not enabled:
        _put(sc, "compositing_node_group", None, "scene.compositing_node_group")
        _put(sc.render, "use_compositing", False, "render.use_compositing")
        if old is not None:
            bpy.data.node_groups.remove(old)
        RENDER_REPORT["grade"] = None
        return
    g = dict(look("grade", {}) or {})
    g.update(overrides)
    power = float(g.get("contrast_power", 1.03))
    thr, strength, size = float(g.get("bloom_threshold", 3.0)), float(g.get("bloom_strength", 0.5)), float(g.get("bloom_size", 0.5))
    if old is not None:
        bpy.data.node_groups.remove(old)
    ng = bpy.data.node_groups.new(GRADE_GROUP, "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    out = ng.nodes.new("NodeGroupOutput")
    last = rl.outputs["Image"]
    if abs(power - 1.0) > 1e-9:
        cb = ng.nodes.new("CompositorNodeColorBalance")
        cb.inputs["Type"].default_value = "Offset/Power/Slope (ASC-CDL)"
        for sock, rgb in (("Offset", (0.0, 0.0, 0.0)), ("Power", (power,) * 3), ("Slope", (1.0, 1.0, 1.0))):
            for i in cb.inputs:
                if i.name == sock and hasattr(i.default_value, "__len__"):
                    i.default_value = (*rgb, 1.0) if len(i.default_value) == 4 else rgb
        ng.links.new(last, cb.inputs["Image"])
        last = cb.outputs["Image"]
    if strength > 0:
        gl = ng.nodes.new("CompositorNodeGlare")
        gl.inputs["Type"].default_value = "Bloom"
        gl.inputs["Threshold"].default_value = thr
        gl.inputs["Strength"].default_value = strength
        gl.inputs["Size"].default_value = size
        ng.links.new(last, gl.inputs["Image"])
        last = gl.outputs["Image"]
    ng.links.new(last, out.inputs["Image"])
    _put(sc, "compositing_node_group", ng, "scene.compositing_node_group")
    _put(sc.render, "use_compositing", True, "render.use_compositing")
    RENDER_REPORT["grade"] = {"contrast_power": power, "bloom_threshold": thr, "bloom_strength": strength, "bloom_size": size}


def apply_render_settings(sc, quality: str = "final"):
    """The look is locked here, never per shot. `quality`: final | preview | draft (draft = fast review stills).
    Flat 2D characters keep their true colours under 'Khronos PBR Neutral'; the 3D world still gets soft highlights.
    Every setting is recorded in RENDER_REPORT (applied, or failed with the error) and a summary is printed once."""
    v, e = STYLE["video"], STYLE["eevee"]
    q = e["quality"][quality]
    RENDER_REPORT.update({"quality": quality, "applied": [], "failed": [], "white_balance_k": None, "grade": None})
    r = sc.render
    r.engine = "BLENDER_EEVEE"
    r.resolution_x, r.resolution_y = v["width"], v["height"]
    r.resolution_percentage = int(q["resolution_percent"])
    r.fps = v["fps"]
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    r.use_motion_blur = bool(e.get("motion_blur", False))
    vs = sc.view_settings
    _put(vs, "view_transform", e["view_transform"], "view_settings.view_transform", fallback="Standard")
    _put(vs, "look", e.get("look", "None"), "view_settings.look", fallback="None")
    vs.exposure = float(e.get("exposure", 0.0))
    vs.gamma = 1.0
    ev = sc.eevee

    def put(name, value):
        _put(ev, name, value, f"eevee.{name}")

    put("taa_render_samples", int(q["samples"]))
    put("use_shadows", True)
    put("shadow_ray_count", int(q["shadow_rays"]))
    put("shadow_step_count", int(q["shadow_steps"]))
    put("shadow_pool_size", str(q.get("shadow_pool_mb", "512")))
    put("light_threshold", float(e["light_threshold"]))
    put("use_raytracing", bool(q["raytracing"]))
    put("ray_tracing_method", "SCREEN")
    put("use_fast_gi", bool(q.get("fast_gi", True)))        # horizon scan: soft bounce + contact shade that grounds things
    put("fast_gi_method", "GLOBAL_ILLUMINATION")
    put("fast_gi_distance", float(e["ao_distance"]))
    put("fast_gi_quality", float(q.get("gi_quality", 0.25)))
    put("use_bokeh_jittered", bool(q["jittered_dof"]))
    put("bokeh_max_size", float(e["bokeh_max_size"]))
    put("bokeh_overblur", float(e.get("bokeh_overblur", 5.0)))
    put("use_overscan", True)
    put("overscan_size", 3.0)
    put("volumetric_tile_size", str(q.get("volumetric_tile", "8")))
    put("volumetric_samples", int(q.get("volumetric_samples", 64)))
    put("use_volumetric_shadows", True)
    # the look: white balance (a light rig may call set_white_balance again) and the compositor grade
    set_white_balance(look("white_balance_k", 6500))
    if look("grade.enabled", False):
        grade(True)
    bad = RENDER_REPORT["failed"]
    print(f"[core] render settings ({quality}): {len(RENDER_REPORT['applied'])} applied, {len(bad)} failed"
          + (": " + ", ".join(b["name"] for b in bad) if bad else "")
          + f"; white balance {RENDER_REPORT['white_balance_k'] or 'off'}; grade {'on' if RENDER_REPORT['grade'] else 'off'}", flush=True)
    return sc


# ----------------------------------------------------------------------------- small helpers
def hex_rgba(h, alpha: float = 1.0):
    """'#RRGGBB' (sRGB) -> linear RGBA tuple."""
    if isinstance(h, (tuple, list)):
        return (*h[:3], alpha) if len(h) < 4 else tuple(h)
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, alpha)


def collection(name: str):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def link(ob, coll: str = "SET"):
    c = collection(coll)
    for old in list(ob.users_collection):
        old.objects.unlink(ob)
    c.objects.link(ob)
    return ob


def empty(name: str, location=(0, 0, 0), coll: str = "RIG", size: float = 0.1):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = size
    ob.location = location
    return link(ob, coll)


def point_of(target) -> Vector:
    """World position of a point, an object, or anything with a `.point` (character anchors)."""
    if target is None:
        raise ValueError("target is None")
    if hasattr(target, "point"):
        return Vector(target.point())
    if hasattr(target, "matrix_world"):
        bpy.context.view_layer.update()
        return target.matrix_world.translation.copy()
    return Vector(target)


def key(ob, path: str, t: float, value=None, linear: bool = False, index: int = -1):
    """Set (optionally) and keyframe a property at time t (seconds)."""
    shot = current()
    if value is not None:
        setattr_path(ob, path, value)
    prefs = bpy.context.preferences.edit
    old = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "LINEAR" if linear else "BEZIER"
    try:
        ob.keyframe_insert(path, frame=shot.f(t), index=index)
    finally:
        prefs.keyframe_new_interpolation_type = old


def setattr_path(ob, path: str, value):
    parts = path.split(".")
    for p in parts[:-1]:
        ob = getattr(ob, p)
    setattr(ob, parts[-1], value)


def move(ob, t0: float, t1: float, location=None, rotation_deg=None, scale=None, linear: bool = False):
    """Animate an object from its current transform (held at t0) to the given one at t1, eased."""
    if location is not None:
        key(ob, "location", t0, linear=linear)
        key(ob, "location", t1, Vector(location), linear=linear)
    if rotation_deg is not None:
        key(ob, "rotation_euler", t0, linear=linear)
        key(ob, "rotation_euler", t1, tuple(math.radians(a) for a in rotation_deg), linear=linear)
    if scale is not None:
        key(ob, "scale", t0, linear=linear)
        key(ob, "scale", t1, (scale,) * 3 if isinstance(scale, (int, float)) else scale, linear=linear)
    return ob


def show(ob, t: float, visible: bool = True):
    """Pop an object (and its children) in or out at time t."""
    shot = current()
    f = shot.f(t)
    for o in [ob, *ob.children_recursive]:
        o.hide_render = o.hide_viewport = visible
        if f > 1:
            o.keyframe_insert("hide_render", frame=f - 1)
            o.keyframe_insert("hide_viewport", frame=f - 1)
        o.hide_render = o.hide_viewport = not visible
        o.keyframe_insert("hide_render", frame=f)
        o.keyframe_insert("hide_viewport", frame=f)


def world_bbox(obs):
    """(min, max) world-space corners of meshes in `obs` (objects or one object), evaluated."""
    if hasattr(obs, "matrix_world"):
        obs = [obs]
    bpy.context.view_layer.update()
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    found = False
    for o in obs:
        for c in getattr(o, "bound_box", []):
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
            found = True
    if not found:
        raise ValueError("no geometry")
    return lo, hi


# ----------------------------------------------------------------------------- keyframe plumbing (Blender 5 layered actions)
def fcurves(ob):
    """All F-curves of an object's (or datablock's) active action, whatever the action layout."""
    ad = getattr(ob, "animation_data", None)
    if not ad or not ad.action:
        return []
    act = ad.action
    out = []
    try:
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    if ad.action_slot is None or bag.slot_handle == ad.action_slot.handle:
                        out.extend(bag.fcurves)
    except AttributeError:
        out = list(getattr(act, "fcurves", []))
    return out


def key_frame(ob, path: str, frame: int, value=None, index: int = -1, interp: str | None = None):
    """Keyframe `path` at an exact frame. interp: None (eased) | "CONSTANT" (a cut / a switch) | "LINEAR"."""
    if value is not None:
        if path.startswith("["):
            ob[path[2:-2]] = value
        else:
            setattr_path(ob, path, value)
    ob.keyframe_insert(path, frame=frame, index=index)
    if interp:
        for fc in fcurves(ob):
            if fc.data_path == path and (index < 0 or fc.array_index == index):
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - frame) < 0.5:
                        kp.interpolation = interp


def ease(ob, path: str, kind: str = "SINE", index: int = -1):
    """Set the easing of every eased key on a channel ("SINE", "BACK", "BOUNCE", "ELASTIC", "CUBIC", ...)."""
    for fc in fcurves(ob):
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            for kp in fc.keyframe_points:
                if kp.interpolation not in ("CONSTANT", "LINEAR"):
                    kp.interpolation = kind
                    kp.easing = "EASE_IN_OUT" if kind in ("SINE", "CUBIC", "QUAD") else "EASE_OUT"


def at_frame(frame: int):
    """Evaluate the scene at a frame (animated parents, constraints, drivers) and return the depsgraph."""
    sc = bpy.context.scene
    sc.frame_set(int(frame))
    bpy.context.view_layer.update()
    return bpy.context.evaluated_depsgraph_get()
