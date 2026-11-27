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


def apply_render_settings(sc, quality: str = "final"):
    """The look is locked here, never per shot. `quality`: final | preview | draft (draft = fast review stills).
    Flat 2D characters keep their true colours under 'Khronos PBR Neutral'; the 3D world still gets soft highlights."""
    v, e = STYLE["video"], STYLE["eevee"]
    q = e["quality"][quality]
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
    try:
        sc.view_settings.view_transform = e["view_transform"]
    except TypeError:
        sc.view_settings.view_transform = "Standard"
    try:
        sc.view_settings.look = e.get("look", "None")
    except TypeError:
        sc.view_settings.look = "None"
    sc.view_settings.exposure = float(e.get("exposure", 0.0))
    sc.view_settings.gamma = 1.0
    ev = sc.eevee

    def put(name, value):
        try:
            setattr(ev, name, value)
        except (AttributeError, TypeError):
            pass

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
