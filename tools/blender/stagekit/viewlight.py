"""Place motivated character lighting for the camera's views.

    viewlight.shape(shot, cam, hero=, edge=, key_side=, scale=, meter=True)
                                                                   # run_shot calls it after build_shot; one key, fill, low fill per view,
                                                                   # then meter() corrects them on a small render
    viewlight.meter(shot, cam, report=None)                        # measure each view's face (or an insert's grey card) and correct
    viewlight.stand_in(camera, aim, mood=None, level=1.0, room=None, name="standin", white_balance=True, ceiling_check=True)
                                                                   # the same key and fills for a person standing at `aim`, no shot needed
    viewlight.face_range(palette) / cheek_range(palette) / object_range(palette) / ceiling_wall(scene, camera, img)
    viewlight.view(report, view_id) / viewlight.hero_of(report, view_id)
    viewlight.clear()                                              # remove every light this module placed

The key's level and the fill ratio come from the mood (lights.mood_look: "face", "cheek", "pool"), scaled from the approved training
room; a night mood ("pool") keys from a declared practical or screen near the people, close (about POOL_NEAR), narrow, set for the
hero alone and aimed at the heads, so the others fall off and the room stays dark.
The formula only places the light; meter() then reads the picture as the film will have it (a small render of each view's key frame)
and scales the key and fills until the hero's face sits in the mood's range, the way a cameraman reads a meter. A view with nobody to
key lights its first declared subject as a face there would be lit and meters a grey card. A key whose beam washes the ceiling (ceiling
above CEILING_MAX of the walls in the picture) is narrowed so its top edge meets the far wall under the ceiling line.
The camera white balance belongs with the warm key: shape() and stand_in() set the mood's; a shot that keeps its hand-made rig, or
opted out, keeps the view as it was.
"""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from types import ModuleType

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

from . import core

_SOURCES = "viewlight_sources"
_KINDS = {"window", "practical", "screen", "sky"}
_UP = Vector((0, 0, 1))
_VIEW = "vl_view"
_ROLE = "vl_role"


def sources():
    """Return the light source declarations in the current scene, in declaration order."""
    return json.loads(bpy.context.scene.get(_SOURCES, "[]"))


def source(kind, at, toward=None, kelvin=None, name=None, strength=1.0):
    """Declare a motivated source in world space. A direction points into the light's beam."""
    if kind not in _KINDS:
        raise ValueError(f"unknown light source kind {kind!r}")
    at = Vector(at).to_3d()
    if toward is not None:
        toward = Vector(toward).to_3d()
        if not toward.length_squared:
            raise ValueError("a light source direction must be nonzero")
        toward.normalize()
    declarations = sources()
    item = {"kind": kind, "at": list(at), "toward": list(toward) if toward is not None else None,
            "kelvin": kelvin, "name": name or f"{kind}_{len(declarations) + 1}", "strength": float(strength)}
    declarations.append(item)
    bpy.context.scene[_SOURCES] = json.dumps(declarations)
    return item


@contextmanager
def _watch_set(shot, module):
    """Remember the lights that belong to the set, including untagged legacy fixtures."""
    patches = []

    def recording(build_set):
        def build(*args, **kwargs):
            result = build_set(*args, **kwargs)
            shot._viewlight_set_lights = {o.name for o in bpy.context.scene.objects if o.type == "LIGHT"}
            if isinstance(result, dict):
                shot._viewlight_room = result.get("room")
            return result
        return build

    for name, value in list(vars(module).items()):
        if isinstance(value, ModuleType) and callable(getattr(value, "build_set", None)):
            build = value.build_set
            if any(owner is value for owner, _, _ in patches):
                continue
            patches.append((value, "build_set", build))
            value.build_set = recording(build)
        elif callable(value) and getattr(value, "__name__", None) == "build_set":
            patches.append((module, name, value))
            setattr(module, name, recording(value))
    try:
        yield
    finally:
        for owner, name, value in reversed(patches):
            setattr(owner, name, value)


def _legacy_lights(shot, scene):
    fixtures = getattr(shot, "_viewlight_set_lights", None)
    found = []
    for ob in scene.objects:
        if ob.type != "LIGHT" or ob.hide_render or ob.get(_ROLE) or ob.name.startswith("VL_"):
            continue
        if ob.get("sk_role") in {"practical", "atmosphere"}:
            continue
        if fixtures is not None:
            if ob.name not in fixtures:
                found.append(ob.name)
        elif ob.name.startswith(("KEY_", "FILL_", "RIM_", "EDGE_", "GLOW_")):
            if ob.get("sk_role") != "key" or not ob.name.lower().startswith("key_win"):
                found.append(ob.name)
    return sorted(found)


def _option(value, view, default=None):
    if isinstance(value, dict):
        return value.get(view, default)
    return default if value is None else value


def _horizontal(direction):
    return Vector((direction.x, direction.y, 0))


def _visible(scene, camera, point, margin=0.08):
    p = world_to_camera_view(scene, camera, point)
    return p.z > 0 and -margin <= p.x <= 1 + margin and -margin <= p.y <= 1 + margin


def _position(subject):
    ob = getattr(subject, "ob", subject)
    return ob.matrix_world.translation.copy() if hasattr(ob, "matrix_world") else core.point_of(subject)


def _seen_heads(shot, scene, camera, frames):
    seen = set()
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for name, actor in shot.actors.items():
            if getattr(actor, "head", None) is not None and _visible(scene, camera, _position(actor.head)):
                seen.add(name)
    return seen


def _subjects(shot, view, first, last, scene, camera, seen):
    heads = {name: getattr(actor, "head", None) for name, actor in shot.actors.items()}
    objects = {getattr(anchor, "ob", anchor): name for name, anchor in heads.items() if anchor is not None}
    declared, scoped, props, included = {}, {}, [], set()
    for name, subject in shot.subjects.items():
        moments = shot.subject_moments.get(name)
        if moments and not any(m == view or m.startswith(f"{view}.") or
                               (m in shot.moments and first <= shot.f(shot.moments[m]) <= last)
                               for m in moments):
            continue
        ob = getattr(subject, "ob", subject)
        actor_name = objects.get(ob) if isinstance(ob, bpy.types.Object) else None
        position = _position(subject)
        if actor_name or isinstance(ob, bpy.types.Object) and ob.get("sk_type") == "head":
            if actor_name in seen or _visible(scene, camera, position):
                (scoped if moments else declared)[name] = position
                if actor_name:
                    included.add(actor_name)
        else:
            props.append((name, ob))
    visible = {name: _position(anchor) for name, anchor in heads.items()
               if anchor is not None and name not in included and name in seen}
    return {**scoped, **declared}, visible, props


class _Geometry:
    def __init__(self, scene, room):
        self.scene = scene
        self.depsgraph = bpy.context.evaluated_depsgraph_get()
        self.room = room if hasattr(room, "lo") and hasattr(room, "hi") else None

    def in_room(self, point):
        return self.room is not None and all(self.room.lo[i] < point[i] < self.room.hi[i] for i in range(2))

    def hit(self, origin, direction, limit):
        distance = 0.0
        while distance < limit:
            ok, point, normal, _, ob, _ = self.scene.ray_cast(
                self.depsgraph, origin + direction * distance, direction, distance=limit - distance)
            if not ok:
                break
            offset = (point - origin).length
            if not ob.hide_render:
                return offset, normal, ob
            distance = offset + 0.005
        return limit, None, None

    def reach(self, origin, direction, limit, margin=0.4):
        room = self.room
        enclosed = self.in_room(origin)
        if enclosed:
            for i in range(2):
                if abs(direction[i]) > 1e-5:
                    wall = room.hi[i] if direction[i] > 0 else room.lo[i]
                    limit = min(limit, (wall - origin[i]) / direction[i])
        distance, _, ob = self.hit(origin, direction, limit)
        return max(0.0, distance - margin if ob or enclosed else distance)

    def clear(self, a, b, near=0.03, far=0.23):
        direction = b - a
        distance = direction.length - near - far
        if distance <= 0:
            return True
        direction.normalize()
        return self.hit(a + direction * near, direction, distance)[2] is None

    def panel_clear(self, pos, aim, size):
        rot = (aim - pos).to_track_quat("-Z", "Y")
        right = rot @ Vector((size[0] * 0.5, 0, 0))
        up = rot @ Vector((0, size[1] * 0.5, 0))
        for offset in (right, -right, up, -up, right + up, right - up, -right + up, -right - up):
            point = pos + offset
            room = self.room
            if self.in_room(aim) and any(point[i] < room.lo[i] + 0.05 or point[i] > room.hi[i] - 0.05
                                       for i in range(2)):
                return False
            if not self.clear(pos, point, far=0):
                return False
        return True

    def back_wall(self, head, camera):
        behind = _horizontal(head - camera).normalized()
        distance, normal, ob = self.hit(head + behind * 0.23, behind, 1.27)
        if ob is not None and abs(normal.z) < 0.35 and (
            ob.get("sk_type") in {"wall", "house_wall"} or "wall" in ob.name.lower()
        ):
            return behind, distance + 0.23
        return behind, None


POOL_REACH = 4.5         # m: in a night mood a practical or screen this near the hero is the key's motivation before any window
POOL_THROW = 2.2         # m: a night key stands at most about this far from the hero (a lamp's pool, not a stage light)
KEY_THROW = 6.0          # m: a day key indoors stands at most this far (a 14 m key in a deep office lit the room, not the face)
GROUP_BOOST = 1.25       # the key set for a group gives the hero at most this much more than the hero's own level
POOL_NEAR = 1.4         # m: and prefers this distance, so little power is needed and the room past the people stays dark
POOL_HEIGHTS = (0.4, 0.25, 0.12)    # m above the hero's head a night key tries, highest first (a day key tries 0.82, 0.6, 0.33)
POOL_SPREAD = 36.0       # degrees: a night key's beam, narrower than the day key's look.key.spread_deg (75), aimed at the heads
POOL_SIZE = 0.65         # a night key's panel is this share of the day key's size
POOL_FILL_SPREAD = 60.0  # degrees: the fills' beams at night, so they lift the faces and not the floor
POOL_FRONT = 0.5         # the low front fill's share at night: the camera side stays dark, the pool is the light
HEAD_CLEAR = 0.35        # m: rays that look for room round a head start this far out, past the head and hair they start in
REF_MOOD = "office_day" # the approved room: key and fill powers are calibrated on it and scale by the mood's face and cheek numbers


def _motivator(declarations, hero, geometry, pool=False):
    """The nearest declared source that can plausibly light the hero. In a night mood (pool) a practical or a screen within POOL_REACH
    wins over a window, however near the window is: at night the light on a face comes from the lamp or the screen beside it."""
    plausible = []
    kinds = {"window", "practical", "screen"} if pool else {"window", "practical"}
    for item in declarations:
        if item["kind"] not in kinds or item["strength"] <= 0:
            continue
        pos = Vector(item["at"])
        ray = hero - pos
        if ray.length < 1e-6:
            continue
        if item["toward"] is not None and Vector(item["toward"]).dot(ray.normalized()) < 0.2:
            continue
        if geometry.clear(pos, hero, near=min(0.35, ray.length * 0.25)):
            near_lamp = pool and item["kind"] != "window" and ray.length <= POOL_REACH
            plausible.append((0 if near_lamp else 1, ray.length, item))
    return min(plausible, key=lambda t: (t[0], t[1]))[2] if plausible else None


def _key_position(geometry, hero, heads, eye, cam_pos, aim, direction, side, angles, size, pool=False):
    low, high = angles
    middle = (low + high) * 0.5
    direction = _horizontal(direction).normalized()
    source_angle = math.degrees(eye.angle(direction, math.radians(middle)))
    # Keep a margin for the camera and actors to move while the light stays fixed.
    preferred = middle
    if low <= source_angle <= high:
        preferred = middle * 0.75 + source_angle * 0.25
    # A few angles in the cone let a key use an alcove, clear a post or cover a deeper group.
    best = None
    # A night key is a lamp beside the people: lower and closer, so its pool falls on them and not on the room.
    heights = POOL_HEIGHTS if pool else (0.82, 0.6, 0.33)
    height = hero.z + heights[0]
    for angle in dict.fromkeys((preferred, middle, low, high, (low + middle) * 0.5, (high + middle) * 0.5)):
        ray = Matrix.Rotation(side * math.radians(angle), 3, "Z") @ eye
        for z in (hero.z + h for h in heights):
            origin = Vector((hero.x, hero.y, z))
            limit = KEY_THROW if geometry.in_room(origin) else max(4.3, min(9.0, 2.5 * (hero - aim).length + 3))
            if pool:
                limit = min(limit, POOL_THROW + 0.4)
            # start the ray clear of the hero's own head and hair (a low night key starts inside them)
            reach = HEAD_CLEAR + geometry.reach(origin + ray * HEAD_CLEAR, ray, limit - HEAD_CLEAR)
            for inset in (0, 0.25, 0.55, 0.95, 1.5, 2.3, 3.2):
                if reach - inset < 0.45:
                    continue
                pos = origin + ray * (reach - inset)
                if not geometry.panel_clear(pos, aim, size) or not geometry.clear(pos, hero):
                    continue
                distance = (hero - pos).length
                coverage = sum(min(1, (distance / (head - pos).length) ** 2)
                               for head in heads if geometry.clear(pos, head))
                actual_angle = math.degrees((cam_pos - hero).angle(pos - hero, eye.angle(ray)))
                # Horizontal angles select screen side. Elevation can push a marginal choice out of range.
                penalty = max(0, actual_angle - high, low - actual_angle)
                if pool:     # a lamp's pool: near the hero (POOL_NEAR), the others may fall off
                    score = (1.0 * coverage / len(heads) - abs(distance - POOL_NEAR) * 0.4
                             - abs(angle - preferred) * 0.035 - penalty * 0.3 - abs(z - height) * 0.6)
                else:
                    score = (2.0 * coverage / len(heads) + min(distance, 12.0) * 0.16
                             - abs(angle - preferred) * 0.035 - penalty * 0.3 - abs(z - height) * 0.6)
                if best is None or score > best[0]:
                    best = score, pos
                if not pool:     # a day key takes the farthest clear spot; a night key also weighs the nearer ones
                    break
    return best[1] if best else None


def _light(view, role, first, last, pos, aim, watts, kelvin, *, size=None, spread=None, shadow=False):
    name = f"VL_{view}_{role}"
    kind = "AREA" if size else "SPOT"
    data = bpy.data.lights.new(name, kind)
    ob = bpy.data.objects.new(name, data)
    core.link(ob, "LIGHTS")
    ob[_VIEW], ob[_ROLE] = view, role
    # The set audit counts a light with no sk_role as a practical, and limit_shadows ranks casters by sk_role: say what this is.
    ob["sk_role"] = "key" if role == "key" else "rim" if role.startswith("edge") else "bounce" if role.startswith("bounce") else "fill"
    ob.location = pos
    ob.rotation_euler = (aim - pos).to_track_quat("-Z", "Y").to_euler()
    required = {"use_temperature": True, "temperature": kelvin, "use_shadow": shadow}
    if size:
        required.update(shape="RECTANGLE", size=size[0], size_y=size[1])
        if spread is not None:
            required["spread"] = math.radians(spread)
    else:
        required.update(spot_size=math.radians(spread), spot_blend=0.55)
    if shadow:
        required.update(shadow_maximum_resolution=core.shadow_res(),
                        use_shadow_jitter=core.look("shadow.jitter", True))
    for attr, value in required.items():
        if attr not in data.bl_rna.properties:
            raise RuntimeError(f"{name}: Blender does not support light setting {attr}")
        setattr(data, attr, value)
    if first is None:                                   # a stand-in: on for as long as it exists
        data.energy = watts
        return ob
    for frame, energy in ((first - 1, 0.0), (first, watts), (last + 1, 0.0)):
        core.key_frame(data, "energy", frame, energy, interp="CONSTANT")
    return ob


def clear(scene=None):
    """Remove every light shape() or stand_in() placed (the white balance stays as it is)."""
    _remove(scene or bpy.context.scene)


def _remove(scene):
    for ob in list(scene.objects):
        if ob.type == "LIGHT" and ob.get(_VIEW) is not None and ob.get(_ROLE):
            data = ob.data
            action = data.animation_data.action if data.animation_data else None
            bpy.data.objects.remove(ob, do_unlink=True)
            if not data.users:
                bpy.data.lights.remove(data)
            if action is not None and not action.users:
                bpy.data.actions.remove(action)


def _emissive(ob):
    for slot in ob.material_slots:
        tree = slot.material.node_tree if slot.material and slot.material.use_nodes else None
        if tree is None:
            continue
        for node in tree.nodes:
            strength = node.inputs.get("Emission Strength") if node.type == "BSDF_PRINCIPLED" else (
                node.inputs.get("Strength") if node.type == "EMISSION" else None)
            if strength is not None and (strength.is_linked or strength.default_value > 0):
                return True
    return False


def _screen_sources(declarations, props, scene, camera, aim):
    found = [item for item in declarations if item["kind"] == "screen" and item["strength"] > 0
             and _visible(scene, camera, Vector(item["at"]))]
    for name, ob in props:
        if not isinstance(ob, bpy.types.Object):
            continue
        for part in (ob, *ob.children_recursive):
            if part.type != "MESH" or part.hide_render or not _emissive(part):
                continue
            pos = part.matrix_world @ (sum((Vector(p) for p in part.bound_box), Vector()) / 8)
            if not _visible(scene, camera, pos) or any((pos - Vector(s["at"])).length < 0.35 for s in found):
                continue
            toward = part.matrix_world.to_3x3() @ part.data.polygons[0].normal if len(part.data.polygons) == 1 else aim - pos
            if toward.dot(aim - pos) <= 0:
                continue
            found.append({"at": list(pos), "toward": list(toward.normalized()), "name": name, "kelvin": None,
                          "strength": min(1.0, max(part.dimensions) / 1.6)})
    return found


def _mood(shot, scene):
    from . import lights

    plan = getattr(shot, "plan", None) or {}
    mood = plan.get("time") or scene.get("sk_mood") or scene.get("light_rig", "").partition(" ")[0]
    return mood, _palette(mood)


def _palette(mood):
    from . import lights

    return lights.mood_look(mood) if mood in lights.MOODS else {}


def _lin(v):
    """Display value (sRGB, 0-1) to linear light."""
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _mid(pair, default):
    try:
        lo, hi = pair
        return (float(lo) + float(hi)) * 0.5
    except (TypeError, ValueError):
        return default


def levels(palette):
    """How the mood's numbers scale the approved room's key and fills: {"key", "fill", "face", "cheek", "pool", "soft"}.
    key = the hero's face level in linear light over the approved room's; fill = the fill-to-key ratio that gives the mood's shadow
    cheek (shadow / lit = F / (K + F), so F / K = c / (1 - c)) over the approved room's, times key. An unknown mood is the approved room."""
    from . import lights

    ref = {"mood": REF_MOOD, **lights.MOODS[REF_MOOD]["look"]}
    # the table may be on the harness's scale (as at 53f40f0) or already on the look checks' and meter's: read both ends on one scale
    face0, cheek0 = _mid(face_range(ref), 0.523), _mid([meter_to_patch(v) for v in cheek_range(ref)], 0.425)
    face = _mid(face_range(palette), face0) if palette.get("face") else face0
    cheek = _mid([meter_to_patch(v) for v in cheek_range(palette)], cheek0) if palette.get("cheek") else cheek0
    key = _lin(face) / _lin(face0)
    fill = key * (cheek / (1 - cheek)) / (cheek0 / (1 - cheek0))
    return {"key": key, "fill": fill, "face": face, "cheek": cheek, "pool": bool(palette.get("pool", False)), "soft": cheek >= 0.5}


def _sky(declarations, hero, geometry):
    for item in declarations:
        if item["kind"] == "sky" and item["toward"] is not None and item["strength"] > 0:
            toward = Vector(item["toward"])
            if geometry.hit(hero - 0.24 * toward, -toward, 40.0)[2] is None:
                return item
    return None


def _edge(geometry, head, camera, right, side, aim, size, is_explicit):
    behind, wall = geometry.back_wall(head, camera)
    if wall is None and not is_explicit:
        return None, None
    start = head + Vector((0, 0, 0.55))
    offset = min(0.8, max(0.22, wall - 0.4)) if wall is not None else 0.8
    for lateral in (side, -side):
        for height in (0.45, 0.2, 0):
            pos = start + behind * offset + right * (0.85 * lateral) + _UP * height
            if geometry.clear(start, pos, far=0) and geometry.clear(pos, head):
                if geometry.room is None or geometry.panel_clear(pos, aim, size):
                    return pos, wall
    return None, wall


def _view_rig(shot, cam, scene, view, first, last, declarations, options, mood, palette):
    vid = view["id"]
    frame = (first + last) // 2
    camera = cam.ob
    # The widest part of a move may show people who are cropped out by its end.
    seen = _seen_heads(shot, scene, camera, (first, last, frame))
    cam_pos = camera.matrix_world.translation.copy()
    geometry = _Geometry(scene, getattr(shot, "_viewlight_room", None))
    declared, others, props = _subjects(shot, vid, first, last, scene, camera, seen)
    heads = {**others, **declared}
    if view["size"] == "insert" and props:
        # A moving insert can catch a cropped actor as it settles onto a prop.
        # Keep that framing on the prop unless there is a face in the settled composition.
        declared = {name: head for name, head in declared.items() if _visible(scene, camera, head, margin=0)}
    report = {"view": vid, "frames": [first, last], "sample_frame": frame, "hero": None, "source": None,
              "key_position": None, "angle_off_lens": None, "key_distance": None, "key_power": None,
              "fill_powers": {}, "edge_lights": [], "screen_bounces": [], "compromises": []}
    compromises = report["compromises"]
    hero_name = _option(options.get("hero"), vid) or next(iter(declared), None)
    if hero_name is not None and hero_name not in heads:
        if hero_name not in shot.actors:
            compromises.append(f"hero {hero_name!r} was not found")
            hero_name = next(iter(declared), None)
        else:
            heads[hero_name] = _position(shot.actors[hero_name].head)
    if hero_name is None and not props and heads:
        hero_name = min(heads, key=lambda name: (heads[name] - cam_pos).length)
        compromises.append("no declared head, using the nearest visible actor")

    scale = float(_option(options.get("scale"), vid, 1.0))
    if not math.isfinite(scale) or scale < 0:
        raise ValueError(f"{vid}: viewlight scale must be finite and nonnegative")
    report["scale"] = scale                     # meter() applies it again on what it measured: a multiplier on the result
    seed = float(MOOD_SEED.get(mood, 1.0))
    if seed != 1.0:
        report["seed"] = seed                   # the formula starts where the meter usually ends for this mood (MOOD_SEED)
    scale = scale * seed
    fill_kelvin = palette.get("fill", core.look("fill.kelvin", 6500))
    lv = levels(palette)
    aim = cam_pos.copy()
    if hero_name is not None:
        hero = heads[hero_name]
        # An actor on the edge of frame should contribute to the aim. A figure posed offscreen should not.
        light_heads = [head for name, head in heads.items()
                       if name == hero_name or name in seen or _visible(scene, camera, head)]
        report["hero"] = hero_name
        hero_d = (heads[hero_name] - cam_pos).length
        near = []
        for name, actor in shot.actors.items():
            anchor = getattr(actor, "head", None)
            if name == hero_name or anchor is None:
                continue
            p = _position(anchor)
            if (p - cam_pos).length < hero_d - 0.3 and any(_visible(scene, camera, q, margin=0.3) for q in (p, p - _UP * 0.45)):
                near.append(name)
        if near:
            report["near_bodies"] = sorted(near)
        sun, side, right, aim = _key_and_fills(report, vid, first, last, camera, hero, light_heads, declarations, geometry,
                                               palette, scale, _option(options.get("key_side"), vid))

        edge_names = _option(options.get("edge"), vid, ()) or ()
        if isinstance(edge_names, str):
            edge_names = [edge_names]
        for name, head in (heads.items() if not sun else ()):
            if name not in edge_names and (name == hero_name or not _visible(scene, camera, head)):
                continue
            target = head - _UP * 0.22
            pos, wall = _edge(geometry, head, cam_pos, right, side, target, (0.1, 0.1), name in edge_names)
            if pos is None:
                if wall is not None or name in edge_names:
                    compromises.append(f"no clear edge placement for {name}")
                continue
            cone = math.radians(8)
            beam = (target - pos).normalized()
            if any((other - pos).angle(beam, 0) < cone + 0.07 and (other - pos).length < 4
                   for other_name, other in heads.items() if other_name != name):
                compromises.append(f"edge for {name} would spill on another head")
                continue
            watts = 300 * ((target - pos).length / 1.7) ** 2 * scale * min(1.0, lv["key"])
            _light(vid, f"edge_{name}", first, last, pos, target, watts, fill_kelvin, spread=16)
            report["edge_lights"].append({"subject": name, "position": list(pos), "power": watts, "wall_distance": wall})
    else:
        compromises.append("view has no character head to key")
        subject = _insert_subject(props, scene, camera)
        if subject is not None:
            # Nobody to key (an insert of a bag, a laptop, a door): light the view's subject the way a face there would be lit, in
            # the mood's colours; meter() then sets it to a grey card's level, not a face's.
            name, centre, size = subject
            point = centre + _UP * 0.26                       # _key_and_fills aims 0.26 m under the head point: at the subject's centre
            report.update(subject=name, subject_centre=list(centre), subject_size=size)
            glow = _subject_glows(dict(props).get(name), centre, size, declarations)
            if glow:
                # A screen or a lamp is its own key (sh05: a card-metered key at the night face level gave 96% of the light on the
                # laptop, lit the back wall an even beige and the desk top near white). At most a low shaping key, narrow and aimed
                # down at the surface the subject stands on, so the room stays as dark as its set made it and the subject stays the
                # brightest thing; no fills, no screen bounces.
                report["subject_emits"] = glow
                # its light is the screen's or the lamp's, not the mood's warm key: review's colour_lean reads the view's lean from here
                report["lean_intended"] = _glow_lean(dict(props).get(name), glow)
                _emitter_key(report, vid, first, last, camera, centre, size, geometry, palette, scale)
                return report
            _key_and_fills(report, vid, first, last, camera, point, [point], declarations, geometry, palette, scale,
                           _option(options.get("key_side"), vid))
            # a screen in the insert still throws its light toward the camera side (aim stays the camera), not into itself
    return _bounces(report, vid, first, last, declarations, props, scene, camera, aim, scale, fill_kelvin)


CEILING_MARGIN = 0.3     # m: the key's top edge meets the far wall at least this far under the ceiling line
FACE_INSIDE = 12.0       # degrees: the tops of the heads stay at least this far inside the key's top edge (the edge is soft, not a line)


def _ceiling_spread(geometry, pos, target, heads, spread):
    """The key's spread (degrees) narrowed so the top edge of its beam reaches the far wall under the ceiling (CEILING_MARGIN), the
    heads FACE_INSIDE inside it. Returns (spread, info or None); no ceiling over the heads (outdoors) leaves it as it is. info["note"]
    says when the room is too low or the key too far for both (the heads win: the spread stays wide enough for them)."""
    top = max(h.z for h in heads)
    centre = sum(heads, Vector()) / len(heads)
    up, normal, ob = geometry.hit(Vector((centre.x, centre.y, top + 0.3)), _UP, 15.0)
    if ob is None or normal is None or normal.z > -0.5:
        return spread, None
    ceiling = top + 0.3 + up
    beam = target - pos
    flat = _horizontal(beam)
    if flat.length < 0.05:
        return spread, None
    direction = flat.normalized()
    # the far wall along the beam, looked for near the ceiling (past people and furniture)
    probe = Vector((target.x, target.y, ceiling - 0.35))
    wall, _, hit = geometry.hit(probe, direction, 40.0)
    if hit is None:
        return spread, None
    far = flat.length + wall
    axis = math.atan2(beam.z, flat.length)
    edge = math.atan2(ceiling - CEILING_MARGIN - pos.z, far)
    head = max(math.atan2(h.z + 0.14 - pos.z, max(0.05, _horizontal(h - pos).length)) for h in heads)
    allowed = math.degrees(edge - axis)                    # half-spread that puts the top edge on the ceiling line
    needed = math.degrees(head - axis) + FACE_INSIDE        # half-spread the heads need
    info = {"height": round(ceiling, 2), "far_wall": round(far, 2), "spread": round(spread, 1)}
    if allowed >= spread / 2:
        info["limit"] = round(spread, 1)
        return spread, info
    half = max(allowed, needed)
    new = min(spread, 2 * half)
    info["limit"] = round(new, 1)
    if allowed < needed:
        info["note"] = (f"the room is too low or the key too far ({ceiling:.1f} m ceiling, far wall {far:.1f} m) to keep the key's top "
                        f"edge under the ceiling: {needed - allowed:.0f} degrees of it reach the ceiling")
    return new, info


def _key_and_fills(report, vid, first, last, camera, hero, light_heads, declarations, geometry, palette, scale, override=None):
    """The key, the side fill and the low front fill for a hero at `hero` (a head point) with `light_heads` (the hero's included) seen
    from `camera`, at the mood's levels. Fills in `report` and returns (sun or None, key side +1/-1, camera right, aim)."""
    compromises = report["compromises"]
    cam_pos = camera.matrix_world.translation.copy()
    lv = levels(palette)
    key_kelvin = palette.get("key", core.look("key.kelvin", 4300))
    fill_kelvin = palette.get("fill", core.look("fill.kelvin", 6500))
    low_kelvin = palette.get("fill_low", core.look("fill.low_front_kelvin", 4800))
    centre = sum(light_heads, Vector()) / len(light_heads)
    aim = centre - _UP * 0.26
    report["aim"] = list(aim)
    report["levels"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in lv.items()}
    report["face_target"] = palette.get("face")
    report["cheek_ratio_target"] = palette.get("cheek") or core.look("key.cheek_ratio", [0.35, 0.50])
    eye = _horizontal(cam_pos - hero)
    if eye.length_squared < 1e-6:
        eye = _horizontal(camera.matrix_world.to_3x3() @ Vector((0, 0, 1)))
    if eye.length_squared < 1e-6:
        eye = Vector((0, -1, 0))
    eye.normalize()
    right = _UP.cross(eye)
    sun = _sky(declarations, hero, geometry)
    motivated = sun or _motivator(declarations, hero, geometry, pool=lv["pool"])
    direction = -Vector(sun["toward"]) if sun else (Vector(motivated["at"]) - hero if motivated else right)
    side = 1 if direction.dot(right) >= 0 else -1
    if override is not None and not sun:
        if override not in ("right", "left", 1, -1):
            raise ValueError(f"{vid}: key_side must be 'right', 'left', +1 or -1")
        side = 1 if override in ("right", 1) else -1
        if direction.dot(right) * side < 0:
            motivated = None
            direction = side * right
            compromises.append("requested key side differs from the nearest motivated source")
    report["source"] = motivated["name"] if motivated else None
    report["source_kind"] = motivated["kind"] if motivated else None

    fill_factor = lv["fill"]
    pool = lv["pool"] and not sun
    fill_spread = POOL_FILL_SPREAD if pool else None
    if sun:
        report["key_role"] = "sun"
        report["angle_off_lens"] = math.degrees((cam_pos - hero).angle(direction))
        report["key_power"] = sun["strength"]
    else:
        if not motivated and override is None:
            compromises.append("no declared source could light the hero, using camera right")
        report["key_role"] = "pool" if pool else "area"
        size = core.look("key.size_m", [1.4, 1.1])
        if lv["soft"]:
            size = [m * 1.35 for m in size]
        if pool:
            size = [m * POOL_SIZE for m in size]
        angles = core.look("key.off_lens_deg", [45, 60])
        pos = _key_position(geometry, hero, light_heads, eye, cam_pos, aim, direction, side, angles, size, pool=pool)
        if pos is None:
            # A tight spot (a desk under shelves, a wall close behind the camera): a smaller panel in a wider cone, then the other side.
            # An unlit view is worse than a compromised key (sh04's insert and wide went to Y 32 without one).
            wide = [max(25, angles[0] - 15), min(80, angles[1] + 15)]
            small = [m * 0.5 for m in size]
            for try_side in (side, -side):
                pos = _key_position(geometry, hero, light_heads, eye, cam_pos, aim, direction, try_side, wide, small, pool=pool)
                if pos is not None:
                    size = small
                    compromises.append("no room for the standard key: a half-size panel in a wider cone"
                                       + (" on the other side" if try_side != side else ""))
                    break
        if pos is None:
            compromises.append("no clear placement for the key on its chosen side")
        else:
            distance = (pos - hero).length
            angle = math.degrees((cam_pos - hero).angle(pos - hero, eye.angle(pos - hero)))
            # Match the reference irradiance across the group so a farther hero
            # does not drive the nearer people or foreground into clipping.
            # A night pool is set for the hero and falls off on the others; that falloff is the look.
            inverse_squares = [1 / max(0.25, (head - pos).length_squared) for head in (light_heads if not pool else [hero])]
            distance_squared = min(len(inverse_squares) / sum(inverse_squares), GROUP_BOOST * (hero - pos).length_squared)
            power = 760 * distance_squared / 4.3 ** 2 * scale * lv["key"]
            spread = POOL_SPREAD if pool else core.look("key.spread_deg", 75)
            target = (sum(light_heads, Vector()) / len(light_heads) - _UP * 0.08) if pool else aim
            # The key stands above the heads and points down at the chests: what reaches the ceiling is the top of its beam. The
            # spread that keeps the top edge under the ceiling line at the far wall is worked out here; meter() (and stand_in) narrow
            # the key to it when the picture shows the ceiling brighter than CEILING_MAX of the walls (the approved room, 0.82, keeps 75).
            limit, ceiling = _ceiling_spread(geometry, pos, target, light_heads, spread)
            if ceiling:
                report["ceiling"] = ceiling
            _light(vid, "key", first, last, pos, target, power, key_kelvin, size=size, spread=spread, shadow=True)
            report.update(key_position=list(pos), angle_off_lens=angle, key_distance=distance, key_power=power)
            if not angles[0] <= angle <= angles[1]:
                compromises.append(f"key angle is outside {angles[0]}-{angles[1]} degrees")
            if distance < (1.0 if pool else 2):
                compromises.append(f"geometry limits key throw to less than {1.0 if pool else 2} m")
            geometric_ratio = min((distance / max(0.1, (head - pos).length)) ** 2 for head in light_heads)
            report["min_relative_key"] = geometric_ratio
            if geometric_ratio < 0.6:
                compromises.append("inverse-square falloff leaves a visible head below 60% of the hero's key")
            direction = pos - hero

    opposite = -_horizontal(direction).normalized()
    if opposite.length_squared < 1e-6:
        opposite = -side * right
    fill_start = Vector((centre.x, centre.y, max(head.z for head in light_heads)))
    reach = HEAD_CLEAR + geometry.reach(fill_start + opposite * HEAD_CLEAR, opposite, 3.35 - HEAD_CLEAR, margin=0.55)
    if reach >= 0.5:
        pos = fill_start + opposite * reach
        watts = 25 * fill_factor * scale * min(1.35, ((pos - aim).length / 3.35) ** 2)
        _light(vid, "fill", first, last, pos, aim, watts, fill_kelvin, size=(2.5, 1.8), spread=fill_spread)
        report["fill_powers"]["side"] = watts
    else:
        compromises.append("opposite-side fill has no clear placement")
    low = Vector((cam_pos.x, cam_pos.y, min(0.9, hero.z - 0.2)))
    if report.get("near_bodies"):
        # An over-the-shoulder view: a low front fill at the lens washes the shoulder in front (sh01 locked_out: 0.76 m from it) before
        # it reaches the face behind. Dropped; the side fill and the room hold the shadow side.
        compromises.append(f"no low front fill: {', '.join(report['near_bodies'])} stands nearer the lens than the hero")
    elif (low - aim).length >= 0.25:
        watts = 35 * fill_factor * scale * min(1, ((low - aim).length / 2.6) ** 2) * (POOL_FRONT if pool else 1.0)
        ob = _light(vid, "front", first, last, low, aim, watts, low_kelvin, size=(2.0, 1.5), spread=fill_spread)
        _follow_camera(ob, camera, first, last, low, aim)
        report["fill_powers"]["front"] = watts
    return sun, side, right, aim


EDGE_SHARE = 0.25        # an edge light at most this share of its view's metered key (sh04/sh06: 171 W unmetered beside a metered key)
FOLLOW_STEP = 4          # frames between the low front fill's position keys: it rides with the camera through the run


def _follow_camera(ob, camera, first, last, pos, aim):
    """Key a light's position and aim over its run so it keeps where it stands relative to the camera (placed at the run's middle frame):
    a follow move does not walk its subject into a fill left behind (sh01 box_out: Maya blew out at f49-61). The height stays as placed."""
    if first is None or last is None or last <= first:
        return
    scene = bpy.context.scene
    keep = scene.frame_current
    inv = camera.matrix_world.inverted()
    rel_pos, rel_aim = inv @ pos, inv @ aim
    frames = sorted(set(list(range(first, last + 1, FOLLOW_STEP)) + [last]))
    moved = False
    for f in frames:
        scene.frame_set(f)
        m = camera.matrix_world
        p, a = m @ rel_pos, m @ rel_aim
        p.z = pos.z
        moved = moved or (p - pos).length > 0.02
        ob.location = p
        ob.rotation_euler = (a - p).to_track_quat("-Z", "Y").to_euler()
        ob.keyframe_insert("location", frame=f)
        ob.keyframe_insert("rotation_euler", frame=f)
    if not moved:                               # a still camera: one placement, no keys
        ob.animation_data_clear()
        ob.location = pos
        ob.rotation_euler = (aim - pos).to_track_quat("-Z", "Y").to_euler()
    scene.frame_set(keep)


def _bounces(report, vid, first, last, declarations, props, scene, camera, aim, scale, fill_kelvin):
    """A restrained bounce from each screen in the view (declared, or a glowing subject prop)."""
    screens = _screen_sources(declarations, props, scene, camera, aim)
    bounce_budget = max(1.0, sum(min(1.0, item["strength"]) for item in screens))
    for i, item in enumerate(screens):
        pos = Vector(item["at"])
        toward = Vector(item["toward"]) if item["toward"] is not None else (aim - pos).normalized()
        if not toward.length_squared:
            continue
        pos += toward * 0.16
        watts = 25 * scale * min(1.0, item["strength"]) / bounce_budget
        role = "bounce" if i == 0 else f"bounce_{i + 1}"
        _light(vid, role, first, last, pos, pos + toward, watts, item["kelvin"] or fill_kelvin,
               size=(5 * max(0.15, item["strength"]), 2.4 * max(0.15, item["strength"])))
        report["screen_bounces"].append({"source": item["name"], "power": watts})
    return report


EMITTER_KEY_W = 12.0     # W at 1.2 m: the low shaping key over a glowing subject (a screen, a lamp), before the mood's key level
EMITTER_SPREAD = 28.0    # degrees: narrow, aimed down at the surface the subject stands on, off the walls behind
EMITTER_LEVEL = 0.6      # meter(): the card at a glowing subject is metered to at most this share of the object level, never up


def _subject_glows(ob, centre, size, declarations):
    """What makes an insert's subject its own light: "emissive" (a glowing material on it or its parts, a screen) or the kind of a
    declared source (practical, screen) within its size. None when it does not glow."""
    if isinstance(ob, bpy.types.Object):
        for part in (ob, *ob.children_recursive):
            if part.type == "MESH" and not part.hide_render and _emissive(part):
                return "emissive"
            if part.type == "LIGHT" and not part.hide_render and part.data.energy > 0:
                return "light"
    for item in declarations:
        if item.get("kind") in ("screen", "practical") and item.get("strength", 1) > 0 and \
                (Vector(item["at"]) - centre).length <= max(0.3, size * 0.6):
            return item["kind"]
    return None


def _glow_lean(ob, glow):
    """The colour a view lit by its own glowing subject should lean: "cool" for a screen (lights.SCREEN_K, 7000 K), else from the glow's
    light colour (a lamp under 4500 K is "very_warm", under 5600 K "warm")."""
    if glow in ("emissive", "screen"):
        return "cool"
    kelvin = None
    if isinstance(ob, bpy.types.Object):
        for part in (ob, *ob.children_recursive):
            if part.type == "LIGHT" and getattr(part.data, "use_temperature", False):
                kelvin = part.data.temperature
                break
    if kelvin is None:
        return "warm"
    return "very_warm" if kelvin < 4500 else "warm" if kelvin < 5600 else "cool" if kelvin >= 6500 else "neutral"


def _emitter_key(report, vid, first, last, camera, centre, size, geometry, palette, scale):
    """The low shaping key over a glowing subject: a narrow spot from above and a little toward the camera, aimed at the surface under
    the subject, far under the mood's key level. No fills."""
    cam_pos = camera.matrix_world.translation
    toward = _horizontal(cam_pos - centre)
    toward = toward.normalized() if toward.length > 1e-6 else Vector((0, -1, 0))
    down = geometry.hit(centre, -_UP, 3.0)
    base = centre - _UP * (down[0] if down and down[0] is not None else size * 0.35)
    up = geometry.hit(centre, _UP, 3.0)
    rise = min(1.2, (up[0] - 0.25) if up and up[0] is not None else 1.2)
    pos = centre + _UP * max(0.5, rise) + toward * 0.35
    dist = (pos - base).length
    lv = levels(palette)
    watts = EMITTER_KEY_W * (dist / 1.2) ** 2 * scale * min(1.0, lv["key"])
    _light(vid, "key", first, last, pos, base, watts, palette.get("key", core.look("key.kelvin", 4300)), spread=EMITTER_SPREAD,
           shadow=True)
    report.update(key_position=list(pos), key_power=watts, key_distance=dist, key_role="emitter_shape",
                  source="the subject (it glows)")
    report["compromises"].append("the subject glows: it is its own key; only a low narrow shaping key from above, no fills")


def _insert_subject(props, scene, camera):
    """The subject a view with nobody to key is about: the first declared non-head subject in frame (else the first), as
    (name, centre, size in m). None when the view declares none."""
    found = []
    for name, ob in props:
        if isinstance(ob, bpy.types.Object):
            parts = [p for p in (ob, *ob.children_recursive) if p.type == "MESH" and not p.hide_render]
            if parts:
                lo, hi = core.world_bbox(parts)
                centre, size = (lo + hi) * 0.5, (hi - lo).length
            else:
                centre, size = ob.matrix_world.translation.copy(), 0.3
        else:
            try:
                centre, size = Vector(core.point_of(ob)).to_3d(), 0.3
            except (TypeError, ValueError):
                continue
        found.append((name, centre, float(size)))
    for item in found:
        if _visible(scene, camera, item[1], margin=0):
            return item
    return found[0] if found else None


# ----------------------------------------------------------------------------- the meter
# A cameraman lights by the formula and then reads a meter. meter() renders each lit view's key frame small, with the white balance,
# grade and view transform the film has, measures the hero's face the way the look checks do (review.look_faces rectangle,
# review.face_shape mean), and scales the key and fills until the face sits in the mood's range. Nothing but light powers changes.
METER_PERCENT = 33        # % of 1080x1920 the meter renders (356x634): a face the look checks measure (100 px) is 33 px here
METER_SAMPLES = 4         # a face mean within about 0.005 of 8 samples; each render costs ~1.1 s of set-up whatever its size
METER_PASSES = 5          # verification renders at most after the first solve (3 left a bright set's face over the ceiling, 0.642)
METER_SCALE = (0.04, 3.0) # the meter moves the (seeded) formula's key at most this far; 0.2 stopped dusk views short of their range
                          # (sh07 held_door at the floor with fill x0.086; sh01 box_out 0.524 against 0.411-0.486)
# Where the meter ends, per mood, as the formula's starting point (key, fills, edges and bounces together), so few passes are spent and the
# floor is not reached: dusk on the entrance came out about 5x hot (sh01 box_out, sh07 held_door). A mood not listed starts at 1.
MOOD_SEED = {"dusk": 0.2}
METER_FILL = (0.3, 3.0)   # the step's fills relative to the key: down to 0.3 for the cheek ratio (the ratio comes first), up to 3x
OBJECT_GREY = (0.42, 0.50)  # display Y an 18% grey card at an insert's subject reads in the approved room (office_day)
GREY_ALBEDO = 0.18
KEY_SHARE_MIN = 0.2       # the step's key (a face) or lights (a card) must give at least this share of the subject's light to be metered
TYPICAL_KEY_SCALE = 0.45  # an unreadable hero with no metered view in the shot: the meter's typical cut of the formula key (film: x0.2-0.5; sh03 past_gate's builder typed 0.45)
# The face and cheek numbers in lights.MOODS as committed at 53f40f0 were written on the harness's scale (look_phase3/ROUND2.md: the
# wide face crop, and two cheek patches on the front woman). The look checks use review.face_shape; on the approved picture
# (look_phase3/renders/EF_f25.png) the hero hire_1 reads 0.523 there against the table's 0.485 (office_day mid), so a face value is
# converted in linear light by FACE_GAIN. Values that are not the old ones are taken as already converted (see face_range()).
FACE_GAIN = 0.2363 / 0.2002   # lin(0.523) / lin(0.485)
_OLD_FACE = {"day_clear": (0.47, 0.52), "day_soft": (0.46, 0.50), "morning": (0.45, 0.50), "golden_hour": (0.42, 0.48),
             "sunset": (0.40, 0.46), "dusk": (0.38, 0.45), "night_moon": (0.30, 0.38), "rain_day": (0.42, 0.48),
             "storm": (0.38, 0.45), "interior_day": (0.47, 0.50), "interior_warm": (0.40, 0.46), "candlelit": (0.30, 0.38),
             "office_day": (0.47, 0.50), "office_night": (0.32, 0.40), "cave": (0.28, 0.36)}


def _srgb(v):
    return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


# The face levels were read on hire_1 of the approved picture (0.523), who is not the one its key is set for; the keyed front woman, the
# hero the meter reads, is at 0.571 there. Metered to hire_1's level, sh08 new_hires came out a stop dark and flat (hire_2 0.486, frame Y
# 64 against EF's 121, no_highlights). A hero's face is held to the keyed level: lin(0.571) / lin(0.523). Set it to 1 if the table
# (lights._MOOD_LEVEL) is moved onto the keyed scale instead (office_day would read 0.555-0.589).
HERO_FACE_GAIN = 1.211


def face_range(palette):
    """The hero's face level a mood asks for, on review.face_shape's scale (the look checks'), as [lo, hi]."""
    pair = palette.get("face") or lights_ref_face()
    lo, hi = float(pair[0]), float(pair[1])
    mood = palette.get("mood")
    if mood in _OLD_FACE and all(abs(a - b) < 1e-6 for a, b in zip((lo, hi), _OLD_FACE[mood])) or not palette:
        lo, hi = (round(_srgb(min(1.0, _lin(v) * FACE_GAIN)), 3) for v in (lo, hi))
    if HERO_FACE_GAIN != 1.0:
        lo, hi = (round(_srgb(min(1.0, _lin(v) * HERO_FACE_GAIN)), 3) for v in (lo, hi))
    return [lo, hi]


def lights_ref_face():
    from . import lights
    return lights.MOODS[REF_MOOD]["look"].get("face", (0.47, 0.50))


# The cheek scale. review.face_shape's "ratio" cannot carry it: it drops blocks darker than a quarter of the face's bright end as hair, so a
# hard key's black shadow side vanishes from it (key alone 0.89, the approved room 0.76, the film's flat light 0.77 on the front woman).
# The meter reads the lighting ratio instead (_cheek: light on the quarter of the face the key reaches least over the quarter it reaches
# most, from the key-alone, fill and set renders), which moves monotonically with the fill. Measured against the harness's two cheek
# patches on the same renders of sh08 frame 25 (front woman hire_2, fill swept 0.2x-2.5x; key alone; look_phase4/meter/shots/sh08.json):
_PATCH_TO_METER = ((0.0, 0.0), (0.064, 0.010), (0.229, 0.054), (0.328, 0.107), (0.457, 0.197), (0.558, 0.290), (0.679, 0.467),
                   (0.841, 0.880), (0.90, 0.925), (1.0, 1.0))
_OLD_CHEEK = {"day_clear": (0.35, 0.50), "day_soft": (0.50, 0.65), "morning": (0.35, 0.50), "golden_hour": (0.30, 0.45),
              "sunset": (0.30, 0.45), "dusk": (0.30, 0.45), "night_moon": (0.25, 0.40), "rain_day": (0.55, 0.70), "storm": (0.55, 0.70),
              "interior_day": (0.35, 0.50), "interior_warm": (0.30, 0.45), "candlelit": (0.25, 0.40), "office_day": (0.35, 0.50),
              "office_night": (0.25, 0.40), "cave": (0.25, 0.40)}


def patch_to_meter(p):
    """A cheek ratio on the harness's patch scale (the scale lights.MOODS was written on at 53f40f0) to the meter's scale."""
    p = min(1.0, max(0.0, float(p)))
    for (a, x), (b, y) in zip(_PATCH_TO_METER, _PATCH_TO_METER[1:]):
        if a <= p <= b:
            return round(x + (y - x) * (p - a) / (b - a), 3)
    return p


def meter_to_patch(m):
    """The inverse of patch_to_meter: levels() sizes the formula's fill on the patch scale whichever scale the table is on."""
    m = min(1.0, max(0.0, float(m)))
    for (a, x), (b, y) in zip(_PATCH_TO_METER, _PATCH_TO_METER[1:]):
        if x <= m <= y:
            return round(a + (b - a) * (m - x) / (y - x), 3)
    return m


def cheek_range(palette):
    """The shadow-to-lit ratio a mood asks for, on the meter's scale (see _PATCH_TO_METER). The values lights.MOODS held at 53f40f0 (patch
    scale) are converted; any other values are taken as already on the meter's scale. style look.key.cheek_ratio is on the patch scale."""
    pair = palette.get("cheek")
    mood = palette.get("mood")
    if not pair:
        pair = core.look("key.cheek_ratio", [0.35, 0.50])
        return [patch_to_meter(pair[0]), patch_to_meter(pair[1])]
    lo, hi = float(pair[0]), float(pair[1])
    if mood in _OLD_CHEEK and abs(lo - _OLD_CHEEK[mood][0]) < 1e-6 and abs(hi - _OLD_CHEEK[mood][1]) < 1e-6:
        return [patch_to_meter(lo), patch_to_meter(hi)]
    return [lo, hi]


def object_range(palette):
    """The level a grey card at an insert's subject should read in this mood: OBJECT_GREY scaled like the face (the mood's key level)."""
    k = levels(palette)["key"]
    return [round(_srgb(min(1.0, _lin(v) * k)), 3) for v in OBJECT_GREY]


def _np_lin(a):
    import numpy as np
    return np.where(a <= 0.04045, a / 12.92, ((np.clip(a, 0, None) + 0.055) / 1.055) ** 2.4)


def _np_srgb(a):
    import numpy as np
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


def _luma(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


class _MeterRender:
    """Small renders of the scene as the film will look (white balance, grade, view transform and final-quality light settings, few
    samples, small size), with every setting it touches put back on exit: frame, size, samples, output path and format, stamp, camera,
    and the render visibility of any light it switched off."""

    def __init__(self, shot, percent, samples, final=True):
        import tempfile
        from pathlib import Path
        self.shot, self.samples, self.final = shot, int(samples), bool(final)
        self.percent = int(percent) if percent is not None else None      # None: the size the scene renders at now
        self.path = Path(tempfile.gettempdir()) / f"sk_meter_{id(self)}.png"
        self.renders, self.seconds, self.times = 0, 0.0, []

    def __enter__(self):
        from . import review
        sc = bpy.context.scene
        r = sc.render
        self.old = {"frame": (sc.frame_current, sc.frame_subframe), "camera": sc.camera, "filepath": r.filepath,
                    "use_stamp": r.use_stamp, "format": (r.image_settings.file_format, r.image_settings.color_mode,
                                                         r.image_settings.color_depth)}
        self.hidden = {}
        self.old["build"] = (r.resolution_percentage, sc.eevee.taa_render_samples)
        self.fq = review.final_quality(self.shot) if self.final else None     # final=False: the quality the shot was built at
        if self.fq is not None:
            self.fq.__enter__()
        if self.percent is None:
            self.percent = r.resolution_percentage
        r.resolution_percentage = self.percent
        sc.eevee.taa_render_samples = self.samples
        r.use_stamp = False
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGB"
        r.image_settings.color_depth = "8"       # as the look stills: an 8-bit PNG loads as display values (16-bit loads linear)
        r.filepath = str(self.path)
        self.size = (int(r.resolution_x * self.percent / 100), int(r.resolution_y * self.percent / 100))
        return self

    def hide(self, obs, hidden=True):
        for ob in obs:
            self.hidden.setdefault(ob.name, (ob, ob.hide_render))
            ob.hide_render = hidden

    def show_all(self):
        for ob, was in self.hidden.values():
            ob.hide_render = was

    def render(self, frame):
        import time
        from . import review
        sc = bpy.context.scene
        sc.frame_set(int(frame))
        t0 = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        self.times.append(round(time.perf_counter() - t0, 2))
        self.seconds += self.times[-1]
        self.renders += 1
        return review._load_pixels(self.path)

    def __exit__(self, *exc):
        sc = bpy.context.scene
        r = sc.render
        try:
            self.show_all()
            r.filepath, r.use_stamp = self.old["filepath"], self.old["use_stamp"]
            r.image_settings.file_format, r.image_settings.color_mode, r.image_settings.color_depth = self.old["format"]
            sc.camera = self.old["camera"]
        finally:
            if self.fq is not None:
                self.fq.__exit__(*exc)
            r.resolution_percentage, sc.eevee.taa_render_samples = self.old["build"]
            sc.frame_set(self.old["frame"][0], subframe=self.old["frame"][1])
            try:
                self.path.unlink()
            except OSError:
                pass
        return False


def _rig_lights(scene, vid):
    out = {}
    for ob in scene.objects:
        if ob.type == "LIGHT" and ob.get(_VIEW) == vid and ob.get(_ROLE) in ("key", "fill", "front"):
            out[ob[_ROLE]] = ob
    return out


def _scale_energy(ob, k):
    """Multiply a light's power, keyed (a view's switch keys) or not."""
    d = ob.data
    for fc in core.fcurves(d):
        if fc.data_path == "energy":
            for kp in fc.keyframe_points:
                kp.co.y *= k
                kp.handle_left.y *= k
                kp.handle_right.y *= k
            fc.update()
    d.energy *= k


def _power(ob):
    """A view light's power while it is on (its switch keys hold it at this value)."""
    keys = [kp.co.y for fc in core.fcurves(ob.data) if fc.data_path == "energy" for kp in fc.keyframe_points]
    return max(keys) if keys else ob.data.energy


def _see_through(ob):
    """True for glass and other surfaces the camera sees through (a glass door leaf, a window): every material on it transmits (Principled
    Transmission Weight 0.5 or more, a Glass or Transparent BSDF) or is mostly transparent (alpha under 0.5). The meter reads a face behind
    glass (sh01 locked_out, sh03 through_doors); a solid leaf still hides it."""
    mats = [slot.material for slot in getattr(ob, "material_slots", ()) if slot.material is not None]
    if not mats:
        return False
    for mat in mats:
        tree = mat.node_tree if mat.use_nodes else None
        clear = False
        for node in (tree.nodes if tree is not None else ()):
            if node.type in ("BSDF_GLASS", "BSDF_TRANSPARENT", "BSDF_REFRACTION"):
                clear = True
            elif node.type == "BSDF_PRINCIPLED":
                tw = node.inputs.get("Transmission Weight") or node.inputs.get("Transmission")
                alpha = node.inputs.get("Alpha")
                if tw is not None and (tw.is_linked or tw.default_value >= 0.5) or alpha is not None and not alpha.is_linked and alpha.default_value < 0.5:
                    clear = True
        if not clear:
            return False
    return True


def _face_hidden(scene, actor, cam_pos, point):
    """The name of what stands between the camera and a head (the actor's own parts and glass do not count), or None."""
    own = {o.name for o in actor.coll.all_objects} if getattr(actor, "coll", None) is not None else set()
    direction = point - cam_pos
    limit = direction.length - float(getattr(actor, "head_r", 0.12)) * float(getattr(actor, "scale", 1.0)) * 1.1
    if limit <= 0:
        return None
    direction.normalize()
    dg = bpy.context.evaluated_depsgraph_get()
    travelled = 0.0
    while travelled < limit:
        ok, hit, _, _, ob, _ = scene.ray_cast(dg, cam_pos + direction * travelled, direction, distance=limit - travelled)
        if not ok:
            return None
        if not ob.hide_render and ob.name not in own and ob.type == "MESH" and not _see_through(ob):
            return ob.name
        travelled = (hit - cam_pos).length + 0.005
    return None


def _hero_rect(shot, hero, vid, frame, size, cam_pos, min_px):
    """The hero's face rectangle at the meter's size (the look stills' rectangle, scaled), or (None, why)."""
    from . import review
    scene = bpy.context.scene
    if hero not in shot.actors:
        return None, "the hero is not a cast member (no face to measure)"
    faces = review.look_faces(shot, vid, frame, size[0], size[1])
    face = next((f for f in faces if f["name"] == hero), None)
    if face is None:
        return None, "the hero's head is outside the picture"
    if not face.get("rect"):
        return None, face.get("why") or "the face cannot be measured"
    actor = shot.actors.get(hero)
    point = core.point_of(shot.subjects.get(hero, actor))
    blocker = _face_hidden(scene, actor, cam_pos, point) if actor is not None else None
    if blocker:
        return None, f"the face is hidden behind {blocker}"
    x0, y0, x1, y1 = face["rect"]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(size[0], x1), min(size[1], y1)
    if x1 - x0 < min_px or y1 - y0 < min_px * 0.8:
        return None, f"the face is too small to measure ({x1 - x0} px at the meter's size, {min_px:.0f} needed)"
    return (x0, y0, x1, y1), None


def _cheek(K, F, B, s, g, skin, lit, shade):
    """Shadow-cheek light over lit-cheek light (linear luma) for key scale s and fill scale s*g: the cameraman's lighting ratio, read on
    the face where the key alone is weakest (the shadow cheek) and strongest (the lit cheek)."""
    total = s * (K + g * F) + B
    return float(total[shade].mean() / max(1e-6, total[lit].mean()))


LEVEL_SLACK = 0.06       # face_shape mean: how far over its range the ratio-first meter may lift a face (then the level wins)
# The meter reads the cheek on the run's look frame with its own scale (_PATCH_TO_METER, fitted on frame 25). On sh08 new_hires it read
# 0.20 (in range) where the harness patch on hire_2 read 0.325 against the approved 0.464; fills x1.5 gave 0.40 (face 0.588, face_shape
# ratio 0.87, no findings), x2 0.467 but face_flat (0.882); aiming at 1.5x the range overshot (fill 3x the key, patch 0.507, face_flat
# 0.90); 1.28 gave patch 0.407 but face_flat at the look frame (0.901). 1.2: patch 0.361, face 0.573 (EF 0.571), no findings.
# The meter aims at the middle of the mood's cheek range scaled by this.
CHEEK_GAIN = 1.2


def _face_meter(ctx, shot, rig, frames, palette, lights_):
    """Meter one view's face. Changes the rig's key and fill powers; returns the report entry."""
    import numpy as np
    from . import review
    vid, hero = rig["view"], rig["hero"]
    min_px = max(8, int(review._lk("face_min_px") * ctx.percent / 100))
    rect, why, frame, first_why = None, "no key frame", None, None
    for f in frames:                          # the key frame first, then the run's other frames (a face turned away at the key frame)
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        cam_pos = shot.camera.ob.matrix_world.translation.copy()
        rect, why = _hero_rect(shot, hero, vid, f, ctx.size, cam_pos, min_px)
        first_why = first_why or why
        if rect:
            frame = f
            break
    target, cheek_t = face_range(palette), [round(c * CHEEK_GAIN, 3) for c in cheek_range(palette)]
    out = {"subject": hero, "kind": "face", "target": target, "cheek_target": cheek_t, "frame": frame or (frames[0] if frames else None)}
    if frame is not None and frames and frame != frames[0]:
        out["note_frame"] = f"measured at frame {frame}: at the key frame {frames[0]} {first_why}"
    if rect is None:
        out["skipped"], out["unmeasured"] = f"kept the formula's key: {first_why or why} (at every frame of the run tried)", True
        return out
    x0, y0, x1, y1 = rect
    local = (0, 0, x1 - x0, y1 - y0)
    final = ctx.render(frame)                 # the picture with the powers as they end up (the ceiling check reads it)
    on = final[y0:y1, x0:x1]
    m0 = review.face_shape(on, local, min_px=min_px)
    if not m0.get("ok"):
        out["skipped"], out["unmeasured"] = f"kept the formula's key: {m0.get('why')}", True
        return out
    key, fills = lights_.get("key"), [lights_[r] for r in ("fill", "front") if r in lights_]
    ctx.hide([key])
    off = ctx.render(frame)[y0:y1, x0:x1]
    ctx.hide(fills)
    base = ctx.render(frame)[y0:y1, x0:x1]
    ctx.show_all()
    Lon, Loff, Lb = _np_lin(on), _np_lin(off), _np_lin(base)
    K, F, B = Lon - Loff, Loff - Lb, Lb
    Ky = _luma(K)
    skin = (_luma(on) > 0.25 * np.percentile(_luma(on), 90)) | (_luma(off) > 0.25 * np.percentile(_luma(off), 90))
    skin &= _luma(on) > 0.02
    ratio_ok = skin.sum() >= 20 and Ky[skin].mean() > 0.05 * _luma(Lon)[skin].mean()
    lit = shade = None
    if ratio_ok:
        hi_k, lo_k = np.percentile(Ky[skin], 75), np.percentile(Ky[skin], 25)
        lit, shade = skin & (Ky >= hi_k), skin & (Ky <= lo_k)
        ratio_ok = lit.sum() >= 5 and shade.sum() >= 5
    Kl, Fl, Bl = _luma(K), _luma(F), _luma(B)
    key_share = float(Kl[skin].mean() / max(1e-6, _luma(Lon)[skin].mean())) if skin.any() else 0.0
    dim_only = key_share < KEY_SHARE_MIN and m0["mean"] > target[1]
    if key_share < KEY_SHARE_MIN and not dim_only:
        # Scaling a key that does not light the face only brightens everything else (sh03: a back-lit hero, key x3, frame Y 122 -> 144).
        # A face already too bright is still metered down (dimming the step's lights is safe); the set's own light limits how far.
        out.update(before={"face": m0["mean"], "key_share": round(key_share, 3)},
                   skipped=f"kept the formula's key: it gives the hero's face only {key_share * 100:.0f}% of its light (the set lights it)",
                   _final=final)
        return out

    def level(s, g, bias=0.0):
        pred = _np_srgb(s * (K + g * F) + B)
        r = review.face_shape(pred, local, min_px=min_px)
        return (r["mean"] if r.get("ok") else float(_luma(pred)[skin].mean())) + bias

    def solve(fn, goal, lo, hi):
        # fn increases with its argument; bisection in log space
        a, b = math.log(lo), math.log(hi)
        if fn(lo) >= goal:
            return lo
        if fn(hi) <= goal:
            return hi
        for _ in range(16):
            mid = (a + b) * 0.5
            if fn(math.exp(mid)) < goal:
                a = mid
            else:
                b = mid
        return math.exp((a + b) * 0.5)

    ratio0 = _cheek(Kl, Fl, Bl, 1, 1, skin, lit, shade) if ratio_ok else None
    out.update(before={"face": m0["mean"], "cheek": round(ratio0, 3) if ratio0 is not None else None,
                       "face_shape_ratio": m0["ratio"],
                       "key_alone": round(float(Kl[shade].mean() / max(1e-6, Kl[lit].mean())), 3) if ratio_ok else None},
               set_share=round(float(_luma(B)[skin].mean() / max(1e-6, _luma(Lon)[skin].mean())), 3))
    s, g = 1.0, 1.0
    level_t, ratio_t = sum(target) / 2, sum(cheek_t) / 2
    notes = []
    if dim_only:
        notes.append(f"the step's key gives the face only {key_share * 100:.0f}% of its light: metered down only, the set's own light "
                     "sets the floor")
    if not ratio_ok:
        notes.append("the key barely reaches the face: only the level is metered")
    passes, measured = 0, m0["mean"]
    # Ratio first, then level (sh08 new_hires, hire_2: the room gave 0.54 of a 0.66 face; scaling key and fills together x0.48 left her
    # flat, 0.88). Every (key scale s, fill scale g) pair on a grid is predicted from the three renders; the pick puts the cheek ratio in
    # its range (fills down, key up) and, among the pairs that do, the level nearest its range. When the room alone holds the face at or
    # over the level, the key stays at the strength the ratio needs and the brighter face is reported as a compromise.
    s_lo, s_hi = (METER_SCALE[0], 1.0) if dim_only else METER_SCALE
    g_lo, g_hi = (METER_FILL[0], 1.0) if dim_only else METER_FILL
    s_grid = [math.exp(math.log(s_lo) + (math.log(s_hi) - math.log(s_lo)) * i / 31) for i in range(32)]
    g_grid = [math.exp(math.log(g_lo) + (math.log(g_hi) - math.log(g_lo)) * i / 13) for i in range(14)] + [1e-3]
    # g ~ 0: the step's fills off (1e-3 keeps the scaling invertible), the last thing tried before a face goes over the ceiling (sh04 waves: a key held for the ratio in a
    # bright room went to 1140-1825 W and washed the face, 0.71)
    table = {}
    for sv in s_grid:
        for gv in g_grid:
            table[(sv, gv)] = (level(sv, gv), _cheek(Kl, Fl, Bl, sv, gv, skin, lit, shade) if ratio_ok else None)

    def dist(v, lo, hi):
        return 0.0 if lo <= v <= hi else (lo - v if v < lo else v - hi)

    # the ratio may lift the face over its range only this far, and never to a washed-out face (review face_washed_mean)
    cap = min(target[1] + LEVEL_SLACK, float(review._lk("face_washed_mean")) - 0.02)
    cap = max(cap, target[1])

    def pick(bias):
        def cost(item):
            (sv, gv), (lv, rv) = item
            over = max(0.0, lv + bias - cap) / max(1e-6, target[1] - target[0])
            rd = dist(rv, *cheek_t) / max(1e-6, cheek_t[1] - cheek_t[0]) if rv is not None else 0.0
            ld = dist(lv + bias, *target) / max(1e-6, target[1] - target[0])
            return (round(over, 2), round(rd, 2), round(ld, 2),
                    abs(lv + bias - level_t) + (3.0 * abs(rv - ratio_t) if rv is not None else 0.0)
                    + 0.02 * abs(math.log(sv)) + 0.01 * abs(math.log(max(gv, 0.05))))
        return min(table.items(), key=cost)[0]

    bias = 0.0
    s, g = pick(bias)
    need = (s, g) != (1.0, 1.0) and (not target[0] <= m0["mean"] <= target[1] or (ratio_ok and not cheek_t[0] <= ratio0 <= cheek_t[1]))
    while need:
        _apply(rig, lights_, s, g)
        passes += 1
        final = ctx.render(frame)
        mv = review.face_shape(final[y0:y1, x0:x1], local, min_px=min_px)
        _apply(rig, lights_, 1 / s, 1 / g)     # back to the formula's powers; the final s, g are applied once below
        if not mv.get("ok"):
            notes.append(f"the metered render could not be measured ({mv.get('why')}): kept the formula's key")
            s, g, measured, final = 1.0, 1.0, m0["mean"], None
            break
        measured = mv["mean"]
        if target[0] <= measured <= target[1] or passes >= METER_PASSES:
            break
        new_bias = measured - level(s, g)      # the tone curve's departure from the linear model, carried into the next pick
        s2, g2 = pick(new_bias)
        if (s2, g2) == (s, g):
            break
        bias, s, g = new_bias, s2, g2
    _apply(rig, lights_, s, g)
    if measured > target[1] + 0.015 and ratio_ok and cheek_t[0] - 0.02 <= _cheek(Kl, Fl, Bl, s, g, skin, lit, shade) <= cheek_t[1] + 0.02:
        notes.append(f"compromise: the face ends at {measured:.3f}, over {target[1]}: the room's own light on its shadow side needs a key this "
                     "strong for the cheek ratio, and the key is kept there rather than dimmed into a flat face")
    if s in METER_SCALE:
        notes.append(f"the key needed more than the meter may move it ({METER_SCALE[0]}-{METER_SCALE[1]}x)")
    if not target[0] <= measured <= target[1]:
        notes.append(f"the face ends at {measured:.3f}, outside {target[0]}-{target[1]}")
    ratio1 = _cheek(Kl, Fl, Bl, s, g, skin, lit, shade) if ratio_ok else None
    if ratio_ok and not cheek_t[0] - 0.02 <= ratio1 <= cheek_t[1] + 0.02:
        notes.append(f"the cheek ratio ends at {ratio1:.2f}, outside {cheek_t[0]}-{cheek_t[1]} (the set's own light on the shadow side"
                     " limits it)" if g in METER_FILL else f"the cheek ratio ends at {ratio1:.2f}")
    out.update(after={"face": measured, "cheek": round(ratio1, 3) if ratio1 is not None else None},
               key_scale=round(s, 3), fill_scale=round(s * g, 3), passes=passes, notes=notes, _final=final, _rect=rect, _min_px=min_px)
    return out


def _hero_card(ctx, shot, rig, frames, palette, lights_, face_entry):
    """A hero whose face cannot be read anywhere in the run (turned away, behind glass, too small): an incident reading instead, an 18%
    grey card at the head facing the camera, metered to object_range like an insert. When the card cannot be read either, the entry is
    marked for the shot's typical correction (meter() applies it after the other views are metered)."""
    hero = rig["hero"]
    actor = shot.actors.get(hero)
    f = frames[0] if frames else bpy.context.scene.frame_current
    bpy.context.scene.frame_set(f)
    bpy.context.view_layer.update()
    head = core.point_of(shot.subjects.get(hero, actor)) if actor is not None else None
    if head is None:
        return {**face_entry, "estimate_later": True, "card": "no head to place a card at"}
    size = 2.6 * float(getattr(actor, "head_r", 0.12)) * float(getattr(actor, "scale", 1.0))
    card_rig = dict(rig, subject_centre=tuple(head), subject_size=size, subject=f"{hero} (head)")
    e = _object_meter(ctx, shot, card_rig, [f], palette, lights_)
    if "after" in e:
        e.update(kind="grey card at the hero's head", subject=hero, face=face_entry.get("skipped"),
                 notes=e.get("notes", []) + [f"the face could not be read ({face_entry.get('skipped')}): metered on a grey card at the head"])
        return e
    return {**face_entry, "estimate_later": True, "card": e.get("skipped")}


def _apply(rig, lights_, s, g):
    if "key" in lights_:
        _scale_energy(lights_["key"], s)
    for role in ("fill", "front"):
        if role in lights_:
            _scale_energy(lights_[role], s * g)


def _grey_card(centre, size, camera, scene, extra=0.0):
    """A temporary 18% grey card at a subject, facing the camera, in front of it (an incident reading). Returns the object."""
    import bmesh
    cam_pos = camera.matrix_world.translation
    to_cam = (cam_pos - centre).normalized()
    distance = (cam_pos - centre).length
    pos = centre + to_cam * (min(0.5 * size + 0.03, 0.6, distance * 0.5) + extra * distance)
    side = max(0.05, min(0.5, distance * 0.08))
    me = bpy.data.meshes.new("SK_meter_card")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=side * 0.5)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("SK_meter_card", me)
    scene.collection.objects.link(ob)
    ob.location = pos
    ob.rotation_euler = to_cam.to_track_quat("Z", "Y").to_euler()
    mat = bpy.data.materials.new("SK_meter_grey")
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (GREY_ALBEDO, GREY_ALBEDO, GREY_ALBEDO, 1)
    bsdf.inputs["Roughness"].default_value = 1.0
    for name in ("Specular IOR Level", "Specular"):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = 0.0
            break
    me.materials.append(mat)
    bpy.context.view_layer.update()
    return ob


def _remove_card(ob):
    me, mats = ob.data, [m for m in ob.data.materials if m]
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    for m in mats:
        if not m.users:
            bpy.data.materials.remove(m)


def _card_rect(card, camera, scene, size):
    pts = [world_to_camera_view(scene, camera, card.matrix_world @ v.co) for v in card.data.vertices]
    if any(p.z <= 0 for p in pts):
        return None
    xs = [p.x * size[0] for p in pts]
    ys = [(1 - p.y) * size[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    rect = (int(x0 + 0.25 * w), int(y0 + 0.25 * h), int(x1 - 0.25 * w), int(y1 - 0.25 * h))
    rect = (max(0, rect[0]), max(0, rect[1]), min(size[0], rect[2]), min(size[1], rect[3]))
    return rect if rect[2] - rect[0] >= 3 and rect[3] - rect[1] >= 3 else None


def _object_meter(ctx, shot, rig, frames, palette, lights_):
    """Meter a view with nobody to key: an 18% grey card at the subject, read like an incident meter, set to object_range()."""
    import numpy as np
    scene = bpy.context.scene
    camera = shot.camera.ob
    target = object_range(palette)
    emits = bool(rig.get("subject_emits"))
    if emits:                                   # a glowing subject: its card well under the object level, the key only ever dimmed
        target = [round(_srgb(_lin(t) * EMITTER_LEVEL), 3) for t in target]
    out = {"subject": rig.get("subject"), "kind": "grey card", "target": target, "frame": None}
    centre, size = Vector(rig["subject_centre"]), float(rig.get("subject_size") or 0.3)
    card = None
    try:
        frame, rect = None, None
        # at the subject first; when a hand or an arm covers it there, a little nearer the camera (still in the key's beam)
        for f, extra in ((f, e) for f in frames for e in (0.0, 0.15, 0.3)):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            if card is not None:
                _remove_card(card)
            card = _grey_card(centre, size, camera, scene, extra)
            rect = _card_rect(card, camera, scene, ctx.size)
            cam_pos = camera.matrix_world.translation.copy()
            direction = card.matrix_world.translation - cam_pos
            dg = bpy.context.evaluated_depsgraph_get()
            ok, _, _, _, hit, _ = scene.ray_cast(dg, cam_pos, direction.normalized(), distance=direction.length + 0.01)
            if rect and ok and hit is not None and hit.name == card.name:
                frame = f
                break
            rect = None
        out["frame"] = frame
        if rect is None:
            out["skipped"] = "kept the formula's key: the subject is outside the picture or hidden"
            return out
        x0, y0, x1, y1 = rect

        def read(img):
            return float(_luma(_np_lin(img[y0:y1, x0:x1])).mean())
        final = ctx.render(frame)
        on = read(final)
        ctx.hide([lights_[r] for r in ("key", "fill", "front") if r in lights_])
        base = read(ctx.render(frame))
        ctx.show_all()
        before = round(_srgb(on), 3)
        out.update(before={"card": before}, set_share=round(base / max(1e-6, on), 3))
        if 1 - base / max(1e-6, on) < KEY_SHARE_MIN:
            out.update(skipped=f"kept the formula's key: the step's lights give the subject only {(1 - base / max(1e-6, on)) * 100:.0f}% "
                               "of its light (the set lights it)", _final=final)
            return out
        s, passes, measured, notes = 1.0, 0, before, []
        goal = _lin(sum(target) / 2)
        vl = max(1e-6, on - base)
        while not target[0] <= measured <= target[1] and passes < METER_PASSES:
            s = min(1.0 if emits else METER_SCALE[1], max(METER_SCALE[0], s * max(1e-6, goal - base) / vl if passes else (goal - base) / vl))
            if emits and measured <= target[1]:
                break
            _apply(rig, lights_, s, 1.0)
            passes += 1
            final = ctx.render(frame)
            got = read(final)
            _apply(rig, lights_, 1 / s, 1.0)
            measured = round(_srgb(got), 3)
            vl = max(1e-6, got - base)
            if s in METER_SCALE:
                break
        _apply(rig, lights_, s, 1.0)
        if not target[0] <= measured <= target[1]:
            notes.append(f"the card ends at {measured:.3f}, outside {target[0]}-{target[1]}"
                         + (" (the set's own light alone is brighter)" if base > goal else ""))
        out.update(after={"card": measured}, key_scale=round(s, 3), fill_scale=round(s, 3), passes=passes, notes=notes, _final=final)
        return out
    finally:
        if card is not None:
            _remove_card(card)


CEILING_MAX = 0.95       # the approved look keeps the ceiling under the walls (training room 0.82): a key that lifts it above this is narrowed


def ceiling_wall(scene, camera, img, step=14):
    """Mean display Y (0-1) of the ceiling and of the walls seen in `img` (a render through `camera`), found by casting a ray through
    every step-th pixel: a surface facing down above 1.9 m is ceiling, a vertical shell surface (sk_kind "shell" or a "wall" name,
    not a door or window) is wall. {"ceiling", "wall", "ratio", "n"}; a value is None with fewer than 12 samples."""
    H, W = img.shape[:2]
    Y = _luma(img)
    mw = camera.matrix_world
    tr, br, bl, tl = (mw @ v for v in camera.data.view_frame(scene=scene))
    origin = mw.translation.copy()
    dg = bpy.context.evaluated_depsgraph_get()
    ceil, wall = [], []
    for py in range(step // 2, H, step):
        for px in range(step // 2, W, step):
            fx, fy = px / W, py / H
            d = (tl.lerp(tr, fx).lerp(bl.lerp(br, fx), fy) - origin).normalized()
            o = origin.copy()
            for _ in range(6):
                ok, hit, n, _, ob, _ = scene.ray_cast(dg, o, d, distance=80.0)
                if not ok:
                    break
                if ob.hide_render:
                    o = hit + d * 0.005
                    continue
                if n.z < -0.7 and hit.z > 1.9:
                    ceil.append(float(Y[py, px]))
                elif abs(n.z) < 0.3 and (ob.get("sk_kind") == "shell" or "wall" in ob.name.lower()) \
                        and ob.get("sk_type") not in ("door", "window"):
                    wall.append(float(Y[py, px]))
                break
    c = sum(ceil) / len(ceil) if len(ceil) >= 12 else None
    w = sum(wall) / len(wall) if len(wall) >= 12 else None
    return {"ceiling": round(c, 3) if c else None, "wall": round(w, 3) if w else None,
            "ratio": round(c / w, 3) if c and w else None, "n": [len(ceil), len(wall)]}


def _ceiling_pass(ctx, rig, key, camera, frame, img=None):
    """Read the ceiling against the walls in the view's picture; when the ceiling is brighter than CEILING_MAX of the walls and the key
    can be narrowed (rig["ceiling"]["limit"]), narrow it and read again. Returns the entry for the report."""
    scene = bpy.context.scene
    img = ctx.render(frame) if img is None else img
    before = ceiling_wall(scene, camera, img)
    out = {"before": before["ratio"], "ceiling_y": before["ceiling"], "wall_y": before["wall"]}
    info = rig.get("ceiling") or {}
    if before["ratio"] is None:
        out["skipped"] = "no ceiling and walls to compare in the picture"
        return out, img
    spread = math.degrees(key.data.spread) if key.data.type == "AREA" else None
    limit = info.get("limit")
    if before["ratio"] <= CEILING_MAX or spread is None or limit is None or limit >= spread - 0.5:
        out["after"] = before["ratio"]
        if before["ratio"] > CEILING_MAX:
            out["note"] = ("the ceiling is brighter than the walls and the key is not what lights it (its beam already stays under the "
                           "ceiling line): look at the fixtures and the fills" if limit is None or limit >= (spread or 0) - 0.5
                           else "the ceiling is brighter than the walls")
        return out, img
    key.data.spread = math.radians(limit)
    narrow = ctx.render(frame)
    after = ceiling_wall(scene, camera, narrow)
    if after["ratio"] is None or after["ratio"] > before["ratio"] - 0.02:
        # narrowing did not move the ceiling: the key is not what lights it (the set's fixtures, sky or world): keep the key as it was
        key.data.spread = math.radians(spread)
        out.update(after=before["ratio"], tried_spread=limit, tried_ratio=after["ratio"],
                   note="the ceiling is brighter than the walls but the key is not what lights it (narrowing it to "
                        f"{limit:.0f} degrees changed the ratio {before['ratio']} -> {after['ratio']}): look at the set's fixtures, sky and world")
        return out, img
    out.update(after=after["ratio"], spread=[round(spread, 1), limit])
    info["applied"] = limit
    rig["ceiling"] = info
    if after["ratio"] > CEILING_MAX:
        out["note"] = info.get("note") or "the ceiling stays brighter than the walls with the key narrowed: the fixtures or fills light it too"
    return out, narrow


def _refit_face(ctx, rig, lights_, entry, frame, img, rect, min_px):
    """After the key was narrowed for the ceiling: read the face again and, if it left its range, one proportional correction of the
    key and fills, verified."""
    from . import review
    x0, y0, x1, y1 = rect
    local = (0, 0, x1 - x0, y1 - y0)
    lo, hi = entry["target"]
    m = review.face_shape(img[y0:y1, x0:x1], local, min_px=min_px)
    if not m.get("ok"):
        return
    entry["after"]["face_narrowed"] = m["mean"]
    if lo <= m["mean"] <= hi:
        entry["after"]["face"] = m["mean"]
        return
    k = _lin((lo + hi) / 2) / max(1e-4, _lin(m["mean"]))
    k = min(2.0, max(0.5, k))
    _apply(rig, lights_, k, 1.0)
    v = review.face_shape(ctx.render(frame)[y0:y1, x0:x1], local, min_px=min_px)
    entry["passes"] += 1
    entry["key_scale"] = round(entry["key_scale"] * k, 3)
    entry["fill_scale"] = round(entry["fill_scale"] * k, 3)
    if v.get("ok"):
        entry["after"]["face"] = v["mean"]


def meter(shot, cam, report=None, percent=None, samples=None):
    """Measure each lit view's subject on a small render of its key frame and correct the key and fills to the mood's levels.

    The render is METER_PERCENT of the frame at METER_SAMPLES with the final quality's light settings and the white balance, grade and
    view transform as set (style look.meter.percent / .samples override), so draft stills and the final render get the same light.
    A face: the hero's review.face_shape mean (look_faces rectangle) to face_range(mood), the cheek ratio (key-alone and fill renders)
    to cheek_range(mood) by the fills. A view keyed on an insert's subject: an 18% grey card there to object_range(mood). A face
    turned away, hidden or too small keeps the formula's powers and says why. Each view's report gets "meter": {target, before, after,
    key_scale, fill_scale, passes, seconds, ...}; the scene is left as it was apart from the light powers. Returns the report."""
    import time
    from . import review
    report = report if report is not None else getattr(shot, "viewlight", None)
    if not isinstance(report, dict) or not report.get("views"):
        return report
    scene = bpy.context.scene
    palette = _palette(report.get("mood"))
    percent = int(percent or core.look("meter.percent", METER_PERCENT))
    samples = int(samples or core.look("meter.samples", METER_SAMPLES))
    views = list(cam.views)
    look_frames = {}
    for i, v in enumerate(views):
        look_frames[v["id"]] = review.look_frame(shot, v, views[i + 1]["frame"] if i + 1 < len(views) else None)
    if getattr(shot, "camera", None) is None:
        shot.camera = cam
    t_all = time.perf_counter()
    summary = {"enabled": True, "percent": percent, "samples": samples, "views": 0, "renders": 0}
    later = []                                  # heroes neither the face nor a card at the head could read: the shot's typical correction
    with _MeterRender(shot, percent, samples) as ctx:
        for rig in report["views"]:
            if rig.get("held_from"):
                continue
            vid = rig["view"]
            lights_ = _rig_lights(scene, vid)
            run = [vid] + [r["view"] for r in report["views"] if r.get("held_from") == vid]
            frames = [look_frames[v] for v in run if v in look_frames]
            span = rig.get("frames") or []
            if len(span) == 2 and None not in span:   # then the run's other frames, every quarter second, for a face the key frame misses
                frames += [f for f in range(int(span[0]), int(span[1]) + 1, 6) if f not in frames]
            t0, r0 = time.perf_counter(), ctx.renders
            if "key" not in lights_:
                entry = {"skipped": "no key of the step's to meter" + (" (the sun is the key)" if rig.get("key_role") == "sun" else "")}
            elif rig.get("hero"):
                entry = _face_meter(ctx, shot, rig, frames, palette, lights_)
                if entry.get("unmeasured"):
                    entry = _hero_card(ctx, shot, rig, frames[:1], palette, lights_, entry)
                    if entry.get("estimate_later"):
                        later.append((rig, lights_, entry))
            elif rig.get("subject_centre"):
                entry = _object_meter(ctx, shot, rig, frames, palette, lights_)
            else:
                entry = {"skipped": "nothing to meter"}
            final, rect, min_px = entry.pop("_final", None), entry.pop("_rect", None), entry.pop("_min_px", None)
            if "key" in lights_ and rig.get("key_role") != "sun":
                frame = entry.get("frame") or (frames[0] if frames else None)
                if frame is not None:
                    entry["ceiling"], img = _ceiling_pass(ctx, rig, lights_["key"], shot.camera.ob, frame, final)
                    if entry["ceiling"].get("spread") and rect and "after" in entry:
                        _refit_face(ctx, rig, lights_, entry, frame, img, rect, min_px)
            entry["renders"], entry["seconds"] = ctx.renders - r0, round(time.perf_counter() - t0, 2)
            view_scale = float(rig.get("scale", 1.0))
            if entry.get("key_scale") is not None and abs(view_scale - 1.0) > 1e-6:
                # the view's scale= is a multiplier on what the meter arrived at (applied before metering it was metered away)
                _apply(rig, lights_, view_scale, 1.0)
                entry["view_scale"] = view_scale
                entry.setdefault("notes", []).append(f"the view's scale x{view_scale:g} applied on the metered powers")
            edges = [o for o in scene.objects if o.type == "LIGHT" and o.get(_VIEW) == vid and str(o.get(_ROLE, "")).startswith("edge")]
            if edges and entry.get("key_scale") is not None and "key" in lights_:
                # the edge is not in the approved recipe (key, fills, bounce): it follows the metered key and stays under EDGE_SHARE of it
                k_after = _power(lights_["key"])
                for o in edges:
                    _scale_energy(o, float(entry["key_scale"]) * (view_scale if entry.get("view_scale") else 1.0))
                    if _power(o) > EDGE_SHARE * k_after:
                        _scale_energy(o, EDGE_SHARE * k_after / max(1e-6, _power(o)))
                by_name = {o.name: o for o in edges}
                for e in rig.get("edge_lights", []):
                    o = by_name.get(f"VL_{vid}_edge_{e['subject']}")
                    if o is not None:
                        e["formula_power"], e["power"] = e.get("power"), round(_power(o), 1)
            if entry.get("key_scale") is not None:
                entry["formula_key_power"] = rig.get("key_power")
                entry["formula_fill_powers"] = dict(rig["fill_powers"])
                rig["key_power"] = _power(lights_["key"])
                rig["fill_powers"] = {k: _power(lights_[{"side": "fill"}.get(k, k)]) for k in rig["fill_powers"]
                                      if {"side": "fill"}.get(k, k) in lights_}
            rig["meter"] = entry
            summary["views"] += 1
            for held in report["views"]:
                if held.get("held_from") == vid:
                    held.update({k: rig[k] for k in ("key_power", "fill_powers", "meter", "ceiling") if k in rig})
            tag = (f"{entry['before']} -> {entry['after']} x{entry['key_scale']} fill x{entry['fill_scale']} ({entry['passes']} passes)"
                   if "after" in entry else entry.get("skipped"))
            if entry.get("ceiling"):
                c = entry["ceiling"]
                tag += f"; ceiling/wall {c.get('before')} -> {c.get('after')}" + (f" (key spread {c['spread'][0]} -> {c['spread'][1]})" if c.get("spread") else "")
            print(f"[viewlight] meter {shot.id} {vid}: {tag}, {entry['renders']} renders, {entry['seconds']} s", flush=True)
        metered = sorted(r["meter"]["key_scale"] for r in report["views"] if not r.get("held_from") and isinstance(r.get("meter"), dict)
                         and r["meter"].get("key_scale") is not None and not r["meter"].get("estimated"))
        typical = metered[len(metered) // 2] if metered else float(core.look("meter.typical_key_scale", TYPICAL_KEY_SCALE))
        for rig, lights_, entry in later:
            _apply(rig, lights_, typical, 1.0)       # the formula already carries the view's scale: nothing metered it away
            entry.pop("estimate_later", None)
            entry.update(key_scale=round(typical, 3), fill_scale=round(typical, 3), estimated=True,
                         notes=entry.get("notes", []) + [f"neither the face nor a grey card at the head could be read: the key and fills take "
                                                         f"the shot's typical correction x{typical:.2f} ("
                                                         + (f"median of {len(metered)} metered view(s)" if metered else "the kit's default")
                                                         + "), not measured"])
            entry["formula_key_power"], entry["formula_fill_powers"] = rig.get("key_power"), dict(rig.get("fill_powers") or {})
            rig["key_power"] = _power(lights_["key"])
            rig["fill_powers"] = {k: _power(lights_[{"side": "fill"}.get(k, k)]) for k in rig.get("fill_powers", {})
                                  if {"side": "fill"}.get(k, k) in lights_}
            for held in report["views"]:
                if held.get("held_from") == rig["view"]:
                    held.update({k: rig[k] for k in ("key_power", "fill_powers", "meter") if k in rig})
            print(f"[viewlight] meter {shot.id} {rig['view']}: estimated x{typical:.2f} ({entry.get('face')}; {entry.get('card')})", flush=True)
        summary["renders"] = ctx.renders
        summary["render_seconds"] = round(ctx.seconds, 2)
        summary["each_render_s"] = ctx.times
    summary["seconds"] = round(time.perf_counter() - t_all, 2)
    report["meter"] = summary
    return report


def shape(shot, cam, **options):
    """Set a fixed, camera-relative rig for each unbroken camera move and return its report.

    hero and edge name shot subjects. key_side is left/right from camera and scale
    multiplies power. Each option may also be a dict keyed by view id.
    meter=True (default: style look.meter.enabled, else True) then measures the hero's face on a small render of each view's key frame
    and corrects the key and fills until the face sits in the mood's range (see meter()); meter=False keeps the formula's powers.
    """
    scene = bpy.context.scene
    automatic = options.pop("_automatic", False)
    metering = options.pop("meter", None)
    metering = bool(core.look("meter.enabled", True)) if metering is None else bool(metering)
    fitting = options.pop("fit_shadows", True)          # True: the tile model, then measured; "model": the model only; False: untouched
    unknown = options.keys() - {"hero", "edge", "key_side", "scale"}
    if unknown:
        raise TypeError(f"unknown viewlight option(s): {', '.join(sorted(unknown))}")
    legacy = _legacy_lights(shot, scene)
    warnings = ["Shot has existing character lights: " + ", ".join(legacy)] if legacy else []
    mood, palette = _mood(shot, scene)
    report = {"mood": mood, "views": [], "warnings": warnings, "legacy_lights": legacy}
    if legacy and automatic:
        report["skipped"] = "existing character lighting"
        print(f"[viewlight] {shot.id}: {warnings[0]}. Kept its existing rig.")
        shot.viewlight = report
        return report

    views = cam.views
    declarations = sources()
    frame, subframe = scene.frame_current, scene.frame_subframe
    _remove(scene)
    try:
        groups = []
        for view in views:
            if not groups or view["cut"]:
                groups.append([])
            groups[-1].append(view)
        for i, group in enumerate(groups):
            first = group[0]["frame"]
            last = groups[i + 1][0]["frame"] - 1 if i + 1 < len(groups) else shot.frames
            if last < first:
                continue
            run_options, taken = _run_options(options, [v["id"] for v in group])
            rig = _view_rig(shot, cam, scene, group[0], first, last, declarations, run_options, mood, palette)
            if taken:
                rig["options_from"] = taken
            report["views"].append(rig)
            for v in group[1:]:
                report["views"].append({**rig, "view": v["id"], "held_from": rig["view"]})
    except Exception:
        _remove(scene)
        raise
    finally:
        scene.frame_set(frame, subframe=subframe)
    # The warm key and the camera white balance belong together: set the mood's now that the shot is lit this way.
    if palette.get("wb"):
        core.set_white_balance(palette["wb"])
        report["white_balance"] = palette["wb"]
    shot.viewlight = report
    if fitting:
        report["shadows"] = fit_shadows(shot, report, measure=fitting != "model")
    else:
        report["shadows"] = {"fitted": False}
    if metering:
        meter(shot, cam, report)
    else:
        report["meter"] = {"enabled": False}
    return report


def _energy_frames(ob):
    """(max energy over the light's keys or its value, [(frame, energy)] keys) - a light switched per view is live only in its frames."""
    keys = []
    for fc in core.fcurves(ob.data):
        if fc.data_path == "energy":
            keys = [(kp.co[0], kp.co[1]) for kp in fc.keyframe_points]
    peak = max([e for _, e in keys], default=float(ob.data.energy))
    return peak, keys


PROBE_POOL_MB = "16"     # the smallest pool: every probe render overflows it, and EEVEE's message then states the tiles the frame asks for
POOL_TARGET = 0.85       # a fitted frame may ask for at most this share of the pool (a moving view asks a little more between samples)
FIT_ROUNDS = 4
POOL_STEP = {"final": 24, "build": 12}   # frames between measured samples inside a lit run (a moving camera's demand swings: sh02 draft
                                         # read 1426 tiles at the runs' first, key and last frames and 2108 between them)


def _c_flush():
    """Flush the C runtime's buffered streams: Blender prints its reports with printf, held in the C buffer when output is a pipe."""
    import ctypes
    import sys
    lib = ctypes.cdll.ucrtbase if sys.platform == "win32" else ctypes.CDLL(None)
    lib.fflush(None)


@contextmanager
def _output_to(path):
    """Send the process's stdout and stderr (file descriptors 1 and 2, where Blender's C code prints its reports) to a file for a
    moment, flushing the C and Python buffers on both sides so nothing printed before or after lands in the wrong place."""
    import os
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    _c_flush()
    saved = os.dup(1), os.dup(2)
    with open(path, "wb") as f:
        os.dup2(f.fileno(), 1)
        os.dup2(f.fileno(), 2)
        try:
            yield
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            _c_flush()
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            os.close(saved[0])
            os.close(saved[1])


def pool_demand(shot, frames, final=True):
    """The shadow tiles EEVEE asks for at each frame, measured: a one-sample render into the smallest pool, whose "Shadow buffer
    full ... (asked / pool)" message states the demand. final=True: full size at final quality (review.final_quality, with the final
    fit swapped in); final=False: the size, shadow resolution and lights of the quality the shot was built at. Returns {frame: tiles}
    (0 when it fits even the smallest pool) and the seconds spent. Every setting is put back (the _MeterRender context)."""
    import re
    import tempfile
    from pathlib import Path
    scene = bpy.context.scene
    log = Path(tempfile.gettempdir()) / f"sk_pool_{id(frames)}.log"
    out = {}
    from . import review
    # As built, the largest size the build renders at: the review's dense frames are at least review.DENSE_PERCENT (a draft stills run
    # at 25% overflowed the draft pool only in its 50% dense frames: sh01 and sh02)
    size = 100 if final else max(int(scene.render.resolution_percentage), int(review.DENSE_PERCENT))
    with _MeterRender(shot, size, 1, final=final) as ctx:
        old_pool = scene.eevee.shadow_pool_size
        scene.eevee.shadow_pool_size = PROBE_POOL_MB
        try:
            for f in sorted(set(int(x) for x in frames)):
                with _output_to(log):
                    ctx.render(f)
                text = log.read_text(encoding="utf-8", errors="replace")
                asked = [int(m) for m in re.findall(r"Shadow buffer full[^(]*\((\d+)\s*/\s*\d+\)", text)]
                out[f] = max(asked, default=0)
        finally:
            scene.eevee.shadow_pool_size = old_pool
            try:
                log.unlink()
            except OSError:
                pass
        seconds = round(ctx.seconds, 2)
    return out, seconds


def _run_frames(report, shot, step=None):
    """The frames to measure the pool on: each lit run's first, key (the meter's look frame) and last frame."""
    from . import review
    cam_views = getattr(getattr(shot, "camera", None), "views", None) or []
    starts = [v["frame"] for v in cam_views]
    frames = set()
    for rig in (report or {}).get("views", []):
        if rig.get("held_from"):
            continue
        span = rig.get("frames") or []
        if len(span) != 2 or None in span:
            continue
        first, last = span
        frames.update((int(first), int(last)))
        if step:
            frames.update(range(int(first), int(last) + 1, int(step)))
        v = next((v for v in cam_views if v["id"] == rig["view"]), None)
        if v is not None:
            i = cam_views.index(v)
            frames.add(review.look_frame(shot, v, starts[i + 1] if i + 1 < len(starts) else None))
    return sorted(frames) or [bpy.context.scene.frame_current]


def _drop_order(scene):
    """The set's casting lights a fit may take shadows from, weakest first by lights.limit_shadows' own ranking; never a key or sun."""
    from . import lights
    centre = lights._stage_centre()
    cands = [o for o in scene.objects if o.type == "LIGHT" and o.get(_VIEW) is None and o.data.use_shadow and not o.hide_render
             and o.data.type != "SUN" and lights._ROLE_RANK.get(o.get("sk_role"), 2) > 0]
    cands.sort(key=lambda o: (lights._ROLE_RANK.get(o.get("sk_role"), 2), -lights._importance(o, centre)), reverse=True)
    return cands


def _set_casters(scene):
    return [o for o in scene.objects if o.type == "LIGHT" and o.get(_VIEW) is None and not o.hide_render]


def _fit_once(shot, report, mb, measure, final, label):
    """One fit of the pool `mb` (MB): the tile model (lights.limit_shadows with the costliest view's keys reserved and every set light
    counted at its peak keyed power), then, when measure, EEVEE's own demand at each lit run's first, key and last frame (final=True: at
    final quality; False: as built), taking shadows from the weakest practicals until every frame asks at most POOL_TARGET of the pool."""
    from . import lights

    scene = bpy.context.scene
    budget = mb * 4 * lights._POOL_SAFETY
    keys = [o for o in scene.objects if o.type == "LIGHT" and o.get(_VIEW) is not None and o.data.use_shadow and not o.hide_render]
    per_view = {}
    for o in keys:
        per_view[o[_VIEW]] = per_view.get(o[_VIEW], 0.0) + lights._tile_cost(o)
    reserve_view, reserve = max(per_view.items(), key=lambda kv: kv[1], default=(None, 0.0))
    # Every set light that casts at any frame counts: a light keyed dark at the frame limit_shadows runs on is still live elsewhere.
    held = []
    for o in _set_casters(scene):
        if o.data.use_shadow:
            peak, keyed = _energy_frames(o)
            if keyed and o.data.energy <= 0 < peak:
                held.append((o, keyed))
    before = {o.name for o in _set_casters(scene) if not o.data.use_shadow}
    try:
        for o in keys:
            o.hide_render = True
        for o, keyed in held:                   # counted at its peak while the budget runs (its keys muted), put back below
            o["_sk_fit_energy"] = o.data.energy
            fc = next(fc for fc in core.fcurves(o.data) if fc.data_path == "energy")
            fc.mute = True
            o.data.energy = max(e for _, e in keyed)
        left_mb = max(1.0, (budget - reserve) / (4 * lights._POOL_SAFETY))
        lights.limit_shadows(pool_mb=left_mb, quiet=True)
        fit = json.loads(scene.get("sk_shadow_budget", "{}") or "{}")
    finally:
        for o in keys:
            o.hide_render = False
        for o, keyed in held:
            fc = next(fc for fc in core.fcurves(o.data) if fc.data_path == "energy")
            fc.mute = False
            o.data.energy = o["_sk_fit_energy"]
            del o["_sk_fit_energy"]
    out = {"quality": label, "pool_mb": mb, "budget_tiles": round(budget), "reserve_tiles": round(reserve), "reserve_view": reserve_view,
           "set_tiles": fit.get("estimate_tiles")}
    if fit.get("estimate_tiles", 0) + reserve > budget:
        out["note"] = "over budget with the set's keys and suns alone: nothing else is left to drop"
    if measure:
        # The tile model is a first guess; a view key lighting a whole wide room asks for far more than it says (sh03 cctv_pov: the
        # model ~3100 tiles, EEVEE 8891 of 8192). So measure what each lit run's frames ask for and drop until every frame fits.
        target = mb * 4 * POOL_TARGET
        demand, secs = pool_demand(shot, _run_frames(report, shot, POOL_STEP["final" if final else "build"]), final=final)
        rounds = [{"demand": dict(demand), "seconds": secs}]
        for _ in range(FIT_ROUNDS):
            over = {f: d for f, d in demand.items() if d > target}
            if not over:
                break
            order = _drop_order(scene)
            if not order:
                out["note"] = (f"frames {sorted(over)} ask for {max(over.values())} tiles of {mb * 4} with only keys and suns "
                               "casting: nothing left to drop")
                break
            peak = max(over.values())
            n = min(len(order), max(1, math.ceil(len(order) * 1.5 * (peak - target) / peak)))
            for o in order[:n]:
                o.data.use_shadow = False
            measured, secs = pool_demand(shot, list(over), final=final)
            demand.update(measured)
            rounds.append({"dropped": [o.name for o in order[:n]], "demand": measured, "seconds": secs})
        out.update(measured={str(f): d for f, d in sorted(demand.items())}, target_tiles=round(target), rounds=rounds,
                   renders=sum(len(r["demand"]) for r in rounds), seconds=round(sum(r["seconds"] for r in rounds), 1),
                   fits=all(d <= target for d in demand.values()))
        if not out["fits"] and "note" not in out:
            out["note"] = f"still over after {FIT_ROUNDS} rounds: {max(demand.values())} tiles of {mb * 4}"
    out["dropped"] = sorted(o.name for o in _set_casters(scene) if not o.data.use_shadow and o.name not in before)
    return out


def fit_shadows(shot, report=None, pool_mb=None, measure=True, final_mb=None):
    """Fit the shadow pool again once the per-view keys are in, so it holds at every frame of the shot and at the quality it is
    rendered at (EEVEE prints "Shadow buffer full" and drops tiles when it does not: the look check shadow_pool_full). The set's budget
    (lights.limit_shadows, run by dress.room at the end of the set) was spent before these keys existed, counts only lights live at the
    frame it ran on, and models tiles only roughly; here each fit reserves the costliest view's keys, counts every set light whenever it is
    live, then measures EEVEE's demand and takes shadows from the weakest practicals first (never a view key, a key or a sun).

    Two fits when the shot is built below final quality: the final one (final pool, measured at final quality) and the build's own
    (its pool, measured as built: a draft drops more practicals' shadows than a final build, which is fine for acting and camera). The
    build's is applied to the scene; review.final_quality (the look stills, the meter, a final frame inside a draft build) swaps the final
    one in and back. Stored as scene["sk_shadow_fit"] = {"quality", "build": [names without shadow], "final": [...]}. pool_mb overrides
    the build pool, final_mb the final pool (tests). Returns {"quality", "final": {...}, "build": {...}, "dropped": [build's names]}."""
    scene = bpy.context.scene
    q = str(getattr(shot, "quality", None) or core.quality())
    final_pool = int(final_mb or core.STYLE["eevee"]["quality"]["final"].get("shadow_pool_mb", 2048))
    build_pool = int(pool_mb or scene.eevee.shadow_pool_size)
    if "sk_shadow_fit" in scene:
        del scene["sk_shadow_fit"]              # a previous fit is not swapped in while this one measures
    set_fit = json.loads(scene.get("sk_shadow_budget", "{}") or "{}")
    if q != "final":
        # the set fitted itself to the build's (smaller) pool: give those lights their shadows back for the final fit
        for name in set_fit.get("dropped", []):
            ob = scene.objects.get(name)
            if ob is not None and ob.type == "LIGHT" and ob.get(_VIEW) is None:
                ob.data.use_shadow = True
    final_fit = _fit_once(shot, report, final_pool if (q != "final" or final_mb) else build_pool, measure, True, "final")
    final_off = sorted(o.name for o in _set_casters(scene) if not o.data.use_shadow)
    out = {"quality": q, "final": final_fit}
    if q != "final":
        out["build"] = _fit_once(shot, report, build_pool, measure, False, q)
    build_off = sorted(o.name for o in _set_casters(scene) if not o.data.use_shadow)
    out["dropped"] = sorted(set(final_fit["dropped"]) | set(out.get("build", {}).get("dropped", [])))
    scene["sk_shadow_fit"] = json.dumps({"quality": q, "build": build_off, "final": final_off})
    scene["sk_shadow_budget"] = json.dumps({**set_fit, "dropped": build_off, "fit": {k: v for k, v in out.items() if k != "dropped"}})
    for part in [final_fit] + ([out["build"]] if "build" in out else []):
        meas = (f", measured peak {max(part['measured'].values(), default=0)} of {part['target_tiles']} ({part['renders']} renders, "
                f"{part['seconds']} s)") if "measured" in part else ""
        print(f"[viewlight] shadows {shot.id} {part['quality']}: pool {part['pool_mb']} MB, view key reserve {part['reserve_tiles']} "
              f"({part['reserve_view']}){meas}; dropped {len(part['dropped'])}" + (f": {', '.join(part['dropped'][:10])}" if part["dropped"] else "")
              + (f"; {part['note']}" if part.get("note") else ""), flush=True)
    return out


def findings(report) -> list[dict]:
    """checks.json items (source "light") from a shape() report: a block when unknown lights switched the step off (light_step_skipped,
    naming them and the one way to make a story light); warns for each lit run whose key kept the formula's power (and why) or took an
    estimated correction, a meter compromise, and a shadow fit that did not hold."""
    out = []
    if not isinstance(report, dict):
        return out
    legacy = report.get("legacy_lights") or []
    if legacy:
        # A light the step does not know is either a hand-made character rig (removed: the step lights the people) or a story light
        # (a phone, a screen, a lamp in the story) that was made with plain bpy. The one way to make a story light is
        # lights.practical(name, at, color=..., power=...), which tags it sk_role="practical"; the step then leaves it alone.
        names = ", ".join(legacy)
        how = (f"make each story light with lights.practical(\"name\", at, color=lights.SCREEN_K, power=W) (a screen or phone glow; "
               f"another colour for a lamp), which tags it sk_role=\"practical\" and the step keeps it; delete a hand-made key, fill or rim "
               f"(the per-view step lights the people)")
        if report.get("skipped"):
            out.append({"level": "block", "code": "light_step_skipped", "source": "light", "view": None, "frame": None,
                        "lights": legacy,
                        "text": f"the per-view light step was switched off by lights it does not know ({names}): {how}"})
        else:
            out.append({"level": "warn", "code": "light_unknown", "source": "light", "view": None, "frame": None, "lights": legacy,
                        "text": f"lights the per-view step does not know stay in the shot on top of its rig ({names}): {how}"})
    for rig in report.get("views", []):
        if rig.get("held_from") or not isinstance(rig.get("meter"), dict):
            continue
        m, vid = rig["meter"], rig.get("view")
        frame = m.get("frame")
        if m.get("estimated"):
            out.append({"level": "warn", "code": "light_estimated", "source": "light", "view": vid, "frame": frame,
                        "text": f"the key was not measured: {'; '.join(m.get('notes', [])[-1:])} - check the look still"})
        elif m.get("skipped") and "no key" not in m["skipped"] and "nothing to meter" not in m["skipped"] and not rig.get("subject_emits"):
            out.append({"level": "warn", "code": "light_unmetered", "source": "light", "view": vid, "frame": frame,
                        "text": f"the key keeps the formula's power ({rig.get('key_power') and round(rig['key_power'])} W): "
                                f"{m['skipped'].replace(chr(39) + 's key: ', 's key, ', 1)} - check the look still"})
        for note in m.get("notes", []):
            if note.startswith("compromise"):
                out.append({"level": "warn", "code": "light_compromise", "source": "light", "view": vid, "frame": frame, "text": note})
    sh = report.get("shadows") or {}
    for part in (sh.get("final"), sh.get("build")):
        if isinstance(part, dict) and part.get("fits") is False:
            out.append({"level": "warn", "code": "shadow_fit", "source": "light", "view": None, "frame": None,
                        "text": f"the shadow pool fit ({part.get('quality')}) did not hold: {part.get('note')}"})
    return out


def json_safe(value, _depth=0):
    """The step's report as plain JSON (checks.json): Blender objects and datablocks become their names, vectors, colours and matrices
    lists of rounded numbers, sets and tuples lists, other objects their text; keys starting with "_" (the meter's working data) are
    left out. None stays None."""
    if _depth > 12:
        return str(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return round(value, 4) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v, _depth + 1) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(v, _depth + 1) for v in value]
    if isinstance(value, bpy.types.ID):
        return value.name
    if isinstance(value, Matrix):
        return [[round(float(x), 4) for x in row] for row in value]
    if hasattr(value, "__len__") and hasattr(value, "__getitem__"):
        try:
            return [json_safe(float(x), _depth + 1) for x in value]
        except (TypeError, ValueError):
            pass
    return str(value)


def _run_options(options, ids):
    """One rig lights an unbroken run of views, placed for the view that was cut to. An option keyed by view id that names only a later
    view of the run (a plan's hero or separate written on view b of a move) is used for the run: the first view of the run that names
    it wins. Returns (options for the run, {option: the view it came from})."""
    out, taken = dict(options), {}
    for key, value in options.items():
        if isinstance(value, dict) and ids[0] not in value:
            later = next((vid for vid in ids[1:] if vid in value), None)
            if later is not None:
                out[key] = {**value, ids[0]: value[later]}
                taken[key] = later
    return out, taken


def view(report, view_id):
    """One view's rig from a shape() report (a held view's entry carries its own id and "held_from"), or None."""
    if not isinstance(report, dict) or not isinstance(report.get("views"), list):
        return None
    return next((rig for rig in report["views"] if isinstance(rig, dict) and rig.get("view") == view_id), None)


def hero_of(report, view_id):
    """The hero of a view: from a shape() report, or from the options a shot set before shape ran (shot.viewlight = {"hero": name
    or {view_id: name}}). None when nobody is named (the review then takes the first subject)."""
    rig = view(report, view_id)
    if rig is not None:
        return rig.get("hero")
    hero = report.get("hero") if isinstance(report, dict) else None
    if isinstance(hero, dict):
        hero = hero.get(view_id)
    return hero if isinstance(hero, str) else None


def stand_in(camera, aim, mood=None, level=1.0, room=None, name="standin", white_balance=True, ceiling_check=True, meter=True):
    """Light a preview the way the film will be lit, with nobody in it: the key, side fill and low front fill shape() would place for a
    person whose head is at `aim` (a point, an object or anything core.point_of takes), seen from `camera` (the camera object), at the
    mood's levels and colours, plus the mood's camera white balance. mood=None: the scene's (lights.current_mood()); level multiplies
    every power. room (an arch.room, or anything with .lo and .hi) keeps the key and fill inside it. The lights are named
    VL_<name>_<role>; a second call with the same name replaces them, clear() removes every one. Returns the placement report."""
    from . import lights

    scene = bpy.context.scene
    mood = mood or lights.current_mood() or scene.get("sk_mood")
    palette = _palette(mood)
    level = float(level)
    if not math.isfinite(level) or level < 0:
        raise ValueError("stand_in level must be finite and nonnegative")
    for ob in list(scene.objects):
        if ob.type == "LIGHT" and ob.get(_VIEW) == name and ob.get(_ROLE):
            data = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if not data.users:
                bpy.data.lights.remove(data)
    bpy.context.view_layer.update()
    head = getattr(aim, "matrix_world", None)
    head = head.translation.copy() if head is not None else Vector(core.point_of(aim) if not isinstance(aim, (tuple, list, Vector)) else aim).to_3d()
    report = {"view": name, "mood": mood, "hero": "stand_in", "source": None, "key_position": None, "angle_off_lens": None,
              "key_distance": None, "key_power": None, "fill_powers": {}, "edge_lights": [], "screen_bounces": [], "compromises": []}
    geometry = _Geometry(scene, room)
    _key_and_fills(report, name, None, None, camera, head, [head], sources(), geometry, palette, level)
    if white_balance and palette.get("wb"):
        core.set_white_balance(palette["wb"])
        report["white_balance"] = palette["wb"]
    key = bpy.data.objects.get(f"VL_{name}_key")
    if meter and key is not None:
        # Metered like a view with nobody in it: an 18% grey card at the head, to the object level. The formula's power, unmetered,
        # was the views' before-meter power (about 2-5x what the meter leaves): in the 4.6 m lobby its floor bounce lifted the ceiling
        # from 0.44 to 0.81 (display Y) whatever the key's spread.
        from types import SimpleNamespace
        ns = SimpleNamespace(quality=core.quality(), id=name, camera=SimpleNamespace(ob=camera))
        lights_ = _rig_lights(scene, name)
        rig = {"view": name, "subject": "stand_in", "subject_centre": tuple(head), "subject_size": 0.35}
        with _MeterRender(ns, core.look("meter.percent", METER_PERCENT), core.look("meter.samples", METER_SAMPLES)) as ctx:
            scene.camera = camera
            entry = _object_meter(ctx, ns, rig, [scene.frame_current], palette, lights_)
        entry.pop("_final", None)
        if entry.get("key_scale") is None:
            _apply(rig, lights_, TYPICAL_KEY_SCALE, 1.0)
            entry.update(key_scale=TYPICAL_KEY_SCALE, estimated=True,
                         notes=entry.get("notes", []) + [f"the card could not be read ({entry.get('skipped')}): the typical correction"])
        report["meter"] = entry
        report["formula_key_power"] = report.get("key_power")
        report["key_power"] = _power(key)
        report["fill_powers"] = {k: _power(lights_[{"side": "fill"}.get(k, k)]) for k in report.get("fill_powers", {})
                                 if {"side": "fill"}.get(k, k) in lights_}
    info = report.get("ceiling") or {}
    if ceiling_check and key is not None and info.get("limit") is not None and info["limit"] < math.degrees(key.data.spread) - 0.5:
        # the same ceiling rule as meter(): read the picture small, narrow the key when the ceiling outshines the walls
        from types import SimpleNamespace
        with _MeterRender(SimpleNamespace(quality=core.quality(), id=name), core.look("meter.percent", METER_PERCENT),
                          core.look("meter.samples", METER_SAMPLES)) as ctx:
            scene.camera = camera
            report["ceiling_check"], _ = _ceiling_pass(ctx, report, key, camera, scene.frame_current)
    return report
