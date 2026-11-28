"""Place motivated character lighting for the camera's views."""
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


def _motivator(declarations, hero, geometry):
    plausible = []
    for item in declarations:
        if item["kind"] not in {"window", "practical"} or item["strength"] <= 0:
            continue
        pos = Vector(item["at"])
        ray = hero - pos
        if item["toward"] is not None and Vector(item["toward"]).dot(ray.normalized()) < 0.2:
            continue
        if geometry.clear(pos, hero, near=min(0.35, ray.length * 0.25)):
            plausible.append((ray.length, item))
    return min(plausible, key=lambda pair: pair[0])[1] if plausible else None


def _key_position(geometry, hero, heads, eye, cam_pos, aim, direction, side, angles, size):
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
    elevation = 0.82
    height = hero.z + elevation
    for angle in dict.fromkeys((preferred, middle, low, high, (low + middle) * 0.5, (high + middle) * 0.5)):
        ray = Matrix.Rotation(side * math.radians(angle), 3, "Z") @ eye
        for z in (height, hero.z + 0.6, hero.z + 0.33):
            origin = Vector((hero.x, hero.y, z))
            limit = 20.0 if geometry.in_room(origin) else max(4.3, min(9.0, 2.5 * (hero - aim).length + 3))
            reach = geometry.reach(origin, ray, limit)
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
                score = (2.0 * coverage / len(heads) + min(distance, 12.0) * 0.16
                         - abs(angle - preferred) * 0.035 - penalty * 0.3 - abs(z - height) * 0.6)
                if best is None or score > best[0]:
                    best = score, pos
                break
    return best[1] if best else None


def _light(view, role, first, last, pos, aim, watts, kelvin, *, size=None, spread=None, shadow=False):
    name = f"VL_{view}_{role}"
    kind = "AREA" if size else "SPOT"
    data = bpy.data.lights.new(name, kind)
    ob = bpy.data.objects.new(name, data)
    core.link(ob, "LIGHTS")
    ob[_VIEW], ob[_ROLE] = view, role
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
    for frame, energy in ((first - 1, 0.0), (first, watts), (last + 1, 0.0)):
        core.key_frame(data, "energy", frame, energy, interp="CONSTANT")
    return ob


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

    mood = shot.plan.get("time") or scene.get("sk_mood") or scene.get("light_rig", "").partition(" ")[0]
    mood_look = getattr(lights, "mood_look", None)
    palette = mood_look(mood) if mood_look and mood in lights.MOODS else {}
    return mood, palette


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

    overcast = any(word in mood for word in ("overcast", "rain", "fog"))
    night = any(word in mood for word in ("night", "moon"))
    scale = float(_option(options.get("scale"), vid, 1.0))
    if not math.isfinite(scale) or scale < 0:
        raise ValueError(f"{vid}: viewlight scale must be finite and nonnegative")
    key_kelvin = palette.get("key", core.look("key.kelvin", 4300))
    fill_kelvin = palette.get("fill", core.look("fill.kelvin", 6500))
    low_kelvin = palette.get("fill_low", core.look("fill.low_front_kelvin", 4800))
    aim = cam_pos.copy()
    if hero_name is not None:
        hero = heads[hero_name]
        # An actor on the edge of frame should contribute to the aim. A figure posed offscreen should not.
        light_heads = [head for name, head in heads.items()
                       if name == hero_name or name in seen or _visible(scene, camera, head)]
        centre = sum(light_heads, Vector()) / len(light_heads)
        aim = centre - _UP * 0.26
        report["hero"] = hero_name
        report["aim"] = list(aim)
        report["cheek_ratio_target"] = ([0.55, 0.65] if overcast else core.look("key.cheek_ratio", [0.35, 0.50]))
        eye = _horizontal(cam_pos - hero)
        if eye.length_squared < 1e-6:
            eye = _horizontal(camera.matrix_world.to_3x3() @ Vector((0, 0, 1)))
        if eye.length_squared < 1e-6:
            eye = Vector((0, -1, 0))
        eye.normalize()
        right = _UP.cross(eye)
        sun = _sky(declarations, hero, geometry)
        motivated = sun or _motivator(declarations, hero, geometry)
        direction = -Vector(sun["toward"]) if sun else (Vector(motivated["at"]) - hero if motivated else right)
        side = 1 if direction.dot(right) >= 0 else -1
        override = _option(options.get("key_side"), vid)
        if override is not None and not sun:
            if override not in ("right", "left", 1, -1):
                raise ValueError(f"{vid}: key_side must be 'right', 'left', +1 or -1")
            side = 1 if override in ("right", 1) else -1
            if direction.dot(right) * side < 0:
                motivated = None
                direction = side * right
                compromises.append("requested key side differs from the nearest motivated source")
        report["source"] = motivated["name"] if motivated else None

        fill_factor = 1.6 if overcast else 0.6 if night else 1
        if sun:
            report["key_role"] = "sun"
            report["angle_off_lens"] = math.degrees((cam_pos - hero).angle(direction))
            report["key_power"] = sun["strength"]
        else:
            if not motivated and override is None:
                compromises.append("no declared source could light the hero, using camera right")
            report["key_role"] = "area"
            size = core.look("key.size_m", [1.4, 1.1])
            if overcast:
                size = [m * 1.35 for m in size]
            angles = core.look("key.off_lens_deg", [45, 60])
            pos = _key_position(geometry, hero, light_heads, eye, cam_pos, aim, direction, side, angles, size)
            if pos is None:
                compromises.append("no clear placement for the key on its chosen side")
            else:
                distance = (pos - hero).length
                angle = math.degrees((cam_pos - hero).angle(pos - hero, eye.angle(pos - hero)))
                # Match the reference irradiance across the group so a farther hero
                # does not drive the nearer people or foreground into clipping.
                inverse_squares = [1 / max(0.25, (head - pos).length_squared) for head in light_heads]
                distance_squared = len(inverse_squares) / sum(inverse_squares)
                power = 760 * distance_squared / 4.3 ** 2 * scale
                if night or overcast:
                    power *= 0.4 if night else 0.55
                spread = core.look("key.spread_deg", 75)
                _light(vid, "key", first, last, pos, aim, power, key_kelvin, size=size, spread=spread, shadow=True)
                report.update(key_position=list(pos), angle_off_lens=angle, key_distance=distance, key_power=power)
                if not angles[0] <= angle <= angles[1]:
                    compromises.append(f"key angle is outside {angles[0]}-{angles[1]} degrees")
                if distance < 2:
                    compromises.append("geometry limits key throw to less than 2 m")
                geometric_ratio = min((distance / max(0.1, (head - pos).length)) ** 2 for head in light_heads)
                report["min_relative_key"] = geometric_ratio
                if geometric_ratio < 0.6:
                    compromises.append("inverse-square falloff leaves a visible head below 60% of the hero's key")
                direction = pos - hero

        opposite = -_horizontal(direction).normalized()
        if opposite.length_squared < 1e-6:
            opposite = -side * right
        fill_start = Vector((centre.x, centre.y, max(head.z for head in light_heads)))
        reach = geometry.reach(fill_start, opposite, 3.35, margin=0.55)
        if reach >= 0.5:
            pos = fill_start + opposite * reach
            watts = 25 * fill_factor * scale * min(1.35, ((pos - aim).length / 3.35) ** 2)
            _light(vid, "fill", first, last, pos, aim, watts, fill_kelvin, size=(2.5, 1.8))
            report["fill_powers"]["side"] = watts
        else:
            compromises.append("opposite-side fill has no clear placement")
        low = Vector((cam_pos.x, cam_pos.y, min(0.9, hero.z - 0.2)))
        if (low - aim).length >= 0.25:
            watts = 35 * fill_factor * scale * min(1, ((low - aim).length / 2.6) ** 2)
            _light(vid, "front", first, last, low, aim, watts, low_kelvin, size=(2.0, 1.5))
            report["fill_powers"]["front"] = watts

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
            watts = 300 * ((target - pos).length / 1.7) ** 2 * scale * (0.6 if night else 1)
            _light(vid, f"edge_{name}", first, last, pos, target, watts, fill_kelvin, spread=16)
            report["edge_lights"].append({"subject": name, "position": list(pos), "power": watts, "wall_distance": wall})
    else:
        compromises.append("view has no character head to key")

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


def shape(shot, cam, **options):
    """Set a fixed, camera-relative rig for each unbroken camera move and return its report.

    hero and edge name shot subjects. key_side is left/right from camera and scale
    multiplies power. Each option may also be a dict keyed by view id.
    """
    scene = bpy.context.scene
    automatic = options.pop("_automatic", False)
    unknown = options.keys() - {"hero", "edge", "key_side", "scale"}
    if unknown:
        raise TypeError(f"unknown viewlight option(s): {', '.join(sorted(unknown))}")
    legacy = _legacy_lights(shot, scene)
    warnings = ["Shot has existing character lights: " + ", ".join(legacy)] if legacy else []
    mood, palette = _mood(shot, scene)
    report = {"mood": mood, "views": [], "warnings": warnings}
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
            rig = _view_rig(shot, cam, scene, group[0], first, last, declarations, options, mood, palette)
            report["views"].append(rig)
            for v in group[1:]:
                report["views"].append({**rig, "view": v["id"], "held_from": rig["view"]})
    except Exception:
        _remove(scene)
        raise
    finally:
        scene.frame_set(frame, subframe=subframe)
    # Review uses the view id directly when it needs that view's hero.
    for rig in report["views"]:
        report.setdefault(rig["view"], rig)
    shot.viewlight = report
    return report
