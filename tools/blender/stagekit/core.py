"""stagekit.core - scene setup, locked render settings, time and keyframe helpers.

Everything here runs inside Blender 5.3 (`blender -b --python ...`) or the `bpy` wheel.
One shot = one scene = frames 1..N at the project frame rate.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

PROJECT = Path(os.environ.get("CLAY_PROJECT", Path(__file__).resolve().parents[3]))
STYLE = json.loads((PROJECT / "style" / "style.json").read_text(encoding="utf-8"))


def pack_root() -> Path:
    """Folder of the extracted character pack (contains library/, blender/, docs/)."""
    root = Path(os.environ.get("CLAY_PACK", PROJECT / "packs" / "release_1"))
    if not (root / "blender" / "py" / "character_factory.py").exists():
        raise FileNotFoundError(
            f"Character pack not found at {root}. Unzip release_1.zip so that {root}/library and {root}/blender exist "
            "(python tools/clip.py setup does this)."
        )
    return root


def pack_modules():
    """Import the pack's own modules (clay_look, character_factory, mixamo_retarget)."""
    sys.dont_write_bytecode = True          # never leave __pycache__ inside the pack
    p = str(pack_root() / "blender" / "py")
    if p not in sys.path:
        sys.path.insert(0, p)
    import character_factory as cf
    import clay_look as cl
    import mixamo_retarget as mr
    return cl, cf, mr


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
    """The look is locked here, never per shot: EEVEE, AgX, soft ray-traced shadows, ambient occlusion,
    jittered depth of field. `quality`: final | preview | draft (draft = fast review stills)."""
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
    sc.view_settings.view_transform = e["view_transform"]
    try:
        sc.view_settings.look = e["look"]
    except TypeError:
        sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    ev = sc.eevee
    ev.taa_render_samples = int(q["samples"])
    ev.use_shadows = True
    ev.shadow_ray_count = int(q["shadow_rays"])
    ev.shadow_step_count = int(q["shadow_steps"])
    ev.shadow_resolution_scale = float(q.get("shadow_resolution_scale", 1.0))
    ev.shadow_pool_size = str(q.get("shadow_pool_mb", "512"))
    ev.light_threshold = float(e["light_threshold"])
    ev.use_raytracing = bool(q["raytracing"])
    ev.ray_tracing_method = "SCREEN"
    ev.use_fast_gi = True                               # horizon scan: soft bounce + ambient occlusion that grounds objects
    ev.fast_gi_method = "GLOBAL_ILLUMINATION"
    ev.fast_gi_distance = float(e["ao_distance"])
    ev.fast_gi_quality = float(q.get("gi_quality", 0.25))
    ev.use_bokeh_jittered = bool(q["jittered_dof"])     # accurate blur edges; needs the sample count above
    ev.bokeh_max_size = float(e["bokeh_max_size"])
    ev.bokeh_overblur = float(e.get("bokeh_overblur", 5.0))
    ev.use_overscan = True
    ev.overscan_size = 3.0
    ev.volumetric_tile_size = str(q.get("volumetric_tile", "8"))
    ev.volumetric_samples = int(q.get("volumetric_samples", 64))
    ev.use_volumetric_shadows = True
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
