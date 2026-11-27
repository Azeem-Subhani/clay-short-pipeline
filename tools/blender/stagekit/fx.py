"""stagekit.fx - small effects that make an action read: water answers, things glint, impacts kick up dust.

    fx.ripple((x, y, water_z), t)                 # rings spreading where something touched the water
    fx.splash((x, y, water_z), t, size=1.0)       # drops thrown up, a crown, then rings
    fx.sparkle(ring, t, count=3)                  # a glint so a small important thing is found by the eye
    fx.puff((x, y, 0), t)                         # dust or spray at a landing, a snap, a footfall
    fx.drips(actor.chest, t0, t1)                 # water running off someone who fell in
    fx.rain(area, intensity=1.5, wind=(0.12, 0))  # pouring rain with splash rings on the ground (the RAIN section at the end)
    fx.window_rain(glass_front)                   # beads and running streaks on glass, seen from inside
    fx.drips_edge(p0, p1)                         # drops falling off a canopy edge

All times are shot seconds. Effects live in the "FX" collection and are hidden before and after they play.
"""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Vector

from . import core, mat


def _flat_mat(color, alpha=1.0, strength=1.0):
    name = f"FX_{color}_{alpha}_{strength}"
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = core.hex_rgba(color)
    e.inputs["Strength"].default_value = strength
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    if alpha < 1.0:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        mx.inputs[0].default_value = alpha
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(e.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], o.inputs["Surface"])
        try:
            m.surface_render_method = "BLENDED"
        except AttributeError:
            pass
    else:
        nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


def _window(ob, t0, t1):
    """Visible only between two times."""
    shot = core.current()
    f0, f1 = shot.f(t0), min(shot.frames, shot.f(t1))
    for o in [ob, *ob.children_recursive]:
        o.hide_render = o.hide_viewport = True
        o.keyframe_insert("hide_render", frame=max(1, f0 - 1))
        o.hide_render = o.hide_viewport = False
        o.keyframe_insert("hide_render", frame=f0)
        o.keyframe_insert("hide_render", frame=f1)
        o.hide_render = o.hide_viewport = True
        o.keyframe_insert("hide_render", frame=f1 + 1)
        o.visible_shadow = False
    if f0 <= 1:
        ob.hide_render = False
        ob.keyframe_insert("hide_render", frame=1)


def _ring_mesh(name, r=1.0, width=0.06):
    bm = bmesh.new()
    seg = 40
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        v = [bm.verts.new(((r - width) * math.cos(a0), (r - width) * math.sin(a0), 0)), bm.verts.new((r * math.cos(a0), r * math.sin(a0), 0)),
             bm.verts.new((r * math.cos(a1), r * math.sin(a1), 0)), bm.verts.new(((r - width) * math.cos(a1), (r - width) * math.sin(a1), 0))]
        bm.faces.new(v)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def ripple(at, t: float, size: float = 0.9, rings: int = 3, dur: float = 1.4, color="#DCEFE6"):
    """Rings spreading on water from a touch. `at` is a point on the water surface. Returns the time the last ring fades."""
    shot = core.current()
    p = core.point_of(at)
    for i in range(rings):
        ob = bpy.data.objects.new(f"ripple_{shot.f(t)}_{i}", _ring_mesh("ripple", 1.0, 0.07))
        core.link(ob, "FX")
        ob.data.materials.append(_flat_mat(color, 0.55, 1.1))
        ob.location = (p.x, p.y, p.z + 0.012 + 0.002 * i)
        t0 = t + i * dur * 0.22
        t1 = t0 + dur
        ob.scale = (0.08, 0.08, 1)
        ob.keyframe_insert("scale", frame=shot.f(t0))
        ob.scale = (size, size, 1)
        ob.keyframe_insert("scale", frame=shot.f(t1))
        for fc in core.fcurves(ob):
            for kp in fc.keyframe_points:
                kp.interpolation = "QUAD"
                kp.easing = "EASE_OUT"
        _window(ob, t0, t1)
    return t + rings * dur * 0.22 + dur


def splash(at, t: float, size: float = 1.0, drops: int = 16, color="#DDF1F4", seed: int = 0):
    """Water thrown up by something heavy going in: drops fly out and fall back, rings spread. Returns when it has settled."""
    shot = core.current()
    rnd = random.Random(seed or shot.f(t))
    p = core.point_of(at)
    m = _flat_mat(color, 1.0, 1.0)
    for i in range(drops):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=rnd.uniform(0.014, 0.032) * min(size, 1.3))
        for fc in bm.faces:
            fc.smooth = True
        me = bpy.data.meshes.new("drop")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"drop_{shot.f(t)}_{i}", me)
        core.link(ob, "FX")
        me.materials.append(m)
        a = rnd.uniform(0, 6.28)
        reach = rnd.uniform(0.25, 0.95) * size
        peak = rnd.uniform(0.5, 1.35) * size
        dur = rnd.uniform(0.45, 0.75)
        end = Vector((p.x + reach * math.cos(a), p.y + reach * math.sin(a), p.z))
        steps = 6
        for k in range(steps + 1):
            u = k / steps
            ob.location = (p.x + (end.x - p.x) * u, p.y + (end.y - p.y) * u, p.z + 4 * peak * u * (1 - u))
            ob.keyframe_insert("location", frame=shot.f(t + dur * u))
        ob.scale = (1, 1, 1.6)
        _window(ob, t, t + dur)
    crown = bpy.data.objects.new(f"crown_{shot.f(t)}", _ring_mesh("crown", 1.0, 0.22))
    core.link(crown, "FX")
    crown.data.materials.append(_flat_mat(color, 0.8, 1.0))
    crown.location = (p.x, p.y, p.z + 0.02)
    crown.scale = (0.15 * size, 0.15 * size, 1)
    crown.keyframe_insert("scale", frame=shot.f(t))
    crown.scale = (0.75 * size, 0.75 * size, 1)
    crown.keyframe_insert("scale", frame=shot.f(t + 0.3))
    _window(crown, t, t + 0.3)
    return ripple(p, t + 0.12, size=1.9 * size, rings=3, dur=1.5)


def sparkle(target, t: float, count: int = 3, size: float = 0.12, color="#FFF6C8", gap: float = 0.28, follow: bool = True):
    """Four-point glints popping on a small important thing (a ring, a key, a coin) so the eye finds it."""
    shot = core.current()
    cam = getattr(shot, "camera", None)
    m = _flat_mat(color, 1.0, 4.0)
    out = []
    for i in range(count):
        bm = bmesh.new()
        pts = []
        for k in range(8):
            r = 1.0 if k % 2 == 0 else 0.16
            pts.append((r * math.cos(k * math.pi / 4), 0.0, r * math.sin(k * math.pi / 4)))
        bm.faces.new([bm.verts.new(q) for q in pts])
        me = bpy.data.meshes.new("sparkle")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"sparkle_{shot.f(t)}_{i}", me)
        core.link(ob, "FX")
        me.materials.append(m)
        off = Vector((0.05 * math.cos(i * 2.4), 0, 0.05 * math.sin(i * 2.4) + 0.02))
        if follow and hasattr(target, "matrix_world"):
            c = ob.constraints.new("COPY_LOCATION")
            c.target = target
            ob.delta_location = off
        else:
            ob.location = core.point_of(target) + off
        if cam is not None:
            tr = ob.constraints.new("TRACK_TO")
            tr.target = cam.ob
            tr.track_axis = "TRACK_NEGATIVE_Y"
            tr.up_axis = "UP_Z"
        t0 = t + i * gap
        for tt, s in ((t0, 0.01), (t0 + 0.08, size), (t0 + 0.22, 0.01)):
            ob.scale = (s, s, s)
            ob.keyframe_insert("scale", frame=shot.f(tt))
        ob.rotation_euler.y = 0.0
        _window(ob, t0, t0 + 0.22)
        out.append(ob)
    return out


def puff(at, t: float, size: float = 0.5, count: int = 6, color="#D9CDB8", dur: float = 0.6, seed: int = 0):
    """Soft round puffs that swell and fade: dust at a landing, spray, a snapped branch, breath of effort."""
    shot = core.current()
    rnd = random.Random(seed or shot.f(t))
    p = core.point_of(at)
    m = _flat_mat(color, 0.6, 0.9)
    for i in range(count):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
        me = bpy.data.meshes.new("puff")
        bm.to_mesh(me)
        bm.free()
        for poly in me.polygons:
            poly.use_smooth = True
        ob = bpy.data.objects.new(f"puff_{shot.f(t)}_{i}", me)
        core.link(ob, "FX")
        me.materials.append(m)
        a = rnd.uniform(0, 6.28)
        d = rnd.uniform(0.1, 0.5) * size
        ob.location = p + Vector((0, 0, 0.05))
        ob.scale = (0.02,) * 3
        ob.keyframe_insert("location", frame=shot.f(t))
        ob.keyframe_insert("scale", frame=shot.f(t))
        ob.location = p + Vector((d * math.cos(a), d * math.sin(a) * 0.6, rnd.uniform(0.05, 0.3) * size))
        s = rnd.uniform(0.12, 0.22) * size
        ob.scale = (s, s, s * 0.8)
        ob.keyframe_insert("location", frame=shot.f(t + dur * 0.5))
        ob.keyframe_insert("scale", frame=shot.f(t + dur * 0.5))
        ob.scale = (0.01,) * 3
        ob.keyframe_insert("scale", frame=shot.f(t + dur))
        _window(ob, t, t + dur)


def drips(target, t0: float, t1: float, rate: float = 7.0, color="#CFEAF0", seed: int = 0):
    """Drops falling from someone or something wet."""
    shot = core.current()
    rnd = random.Random(seed or shot.f(t0))
    m = _flat_mat(color, 1.0, 1.0)
    n = max(1, int((t1 - t0) * rate))
    for i in range(n):
        tt = t0 + (t1 - t0) * i / n
        core.at_frame(shot.f(tt))
        p = core.point_of(target) + Vector((rnd.uniform(-0.3, 0.3), 0, rnd.uniform(-0.2, 0.3)))
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.03)
        me = bpy.data.meshes.new("drip")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"drip_{i}", me)
        core.link(ob, "FX")
        me.materials.append(m)
        ob.scale = (1, 1, 1.8)
        ob.location = p
        ob.keyframe_insert("location", frame=shot.f(tt))
        ob.location = (p.x, p.y, p.z - 0.9)
        ob.keyframe_insert("location", frame=shot.f(tt + 0.32))
        for fc in core.fcurves(ob):
            for kp in fc.keyframe_points:
                kp.interpolation = "QUAD"
                kp.easing = "EASE_IN"
        _window(ob, tt, tt + 0.32)


def lines(at, t: float, direction=(0, 0, -1), count: int = 3, length: float = 0.35, color="#FFFFFF", dur: float = 0.25):
    """Short speed lines beside a falling or flying thing (cartoon motion marks). Billboarded strokes."""
    shot = core.current()
    cam = getattr(shot, "camera", None)
    p = core.point_of(at)
    d = Vector(direction).normalized()
    m = _flat_mat(color, 0.85, 1.2)
    for i in range(count):
        bm = bmesh.new()
        w = 0.012
        vs = [bm.verts.new((-w, 0, 0)), bm.verts.new((w, 0, 0)), bm.verts.new((w * 0.3, 0, length)), bm.verts.new((-w * 0.3, 0, length))]
        bm.faces.new(vs)
        me = bpy.data.meshes.new("line")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"line_{shot.f(t)}_{i}", me)
        core.link(ob, "FX")
        me.materials.append(m)
        side = Vector((1, 0, 0)) * (i - (count - 1) / 2) * 0.07
        ob.location = p - d * (0.12 + 0.05 * (i % 2)) + side
        ob.rotation_euler = (-d).to_track_quat("Z", "Y").to_euler()
        _window(ob, t, t + dur)


# ============================================================================= RAIN (cheap, deterministic, loops at 24 fps)
#   fx.rain(area, intensity=1.0, wind=(0.12, 0), t0=0, t1=None)     falling streaks over a rectangle + splash rings on the ground
#   fx.window_rain(front_or_opening)                                 beads and running streaks on glass, seen from inside
#   fx.drips_edge((x0, y0, z), (x1, y1, z), fall=1.6)                drops falling from a canopy or awning edge
# No particle systems and no simulation: one mesh of streaks that slides down one period and loops (an F-curve with a Cycles modifier),
# and one mesh of rings whose rise and fade is a shader driven by the frame number. Same frame, same picture, in every shot of a set.
RAIN_PERIOD = 2.4          # m between repeats of a streak down its column: the mesh slides this far and starts again
RAIN_LOOP = 6              # frames for that slide: 2.4 m in 6 frames = 9.6 m/s, what pouring rain looks like at 24 fps


def _blend(m):
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass
    try:
        m.use_backface_culling = False
    except AttributeError:
        pass


def _node(nt, kind, **kw):
    n = nt.nodes.new(kind)
    for k, v in kw.items():
        if k == "op":
            n.operation = v
        else:
            setattr(n, k, v)
    return n


def _math(nt, op, a=None, b=None):
    """A math node; a and b are sockets (linked) or numbers. Returns its output socket."""
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if hasattr(v, "is_linked"):
            nt.links.new(v, n.inputs[i])
        else:
            n.inputs[i].default_value = v
    return n.outputs[0]


def _rain_mat(color: str, strength: float, alpha: float, top: float, fade: float):
    """Streak material: bright at the head (lower end), gone at the tail and at the sides, and fading out toward the top of the rain volume
    in WORLD height, so the sliding mesh never shows its upper edge. Three more things make it read as rain and not as snow or wire:
    streaks fade out inside about 2.5 m of the lens (a card that close would be a fat white bar), grow fainter with distance (haze), and
    each carries a random brightness in its second UV map, so most are faint and a few are bright, as where drops cross a light."""
    name = f"FX_rain_{color}_{strength}_{alpha}_{top:.1f}"
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    uv = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])
    rn = nt.nodes.new("ShaderNodeUVMap")
    rn.uv_map = "RND"
    rsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(rn.outputs["UV"], rsep.inputs[0])
    along = _math(nt, "POWER", sep.outputs["Y"], 1.8)                       # v: 0 tail .. 1 head
    side = _math(nt, "MULTIPLY", _math(nt, "PINGPONG", sep.outputs["X"], 0.5), 2.0)    # 0 at the edge, 1 in the middle
    side = _math(nt, "POWER", side, 0.6)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    gz = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], gz.inputs[0])
    up = nt.nodes.new("ShaderNodeMapRange")
    up.inputs["From Min"].default_value, up.inputs["From Max"].default_value = top - fade, top
    up.inputs["To Min"].default_value, up.inputs["To Max"].default_value = 1.0, 0.0
    nt.links.new(gz.outputs["Z"], up.inputs["Value"])
    cd = nt.nodes.new("ShaderNodeCameraData")
    near = nt.nodes.new("ShaderNodeMapRange")                                # 0 inside 0.8 m of the lens .. 1 beyond 4 m
    near.inputs["From Min"].default_value, near.inputs["From Max"].default_value = 0.8, 4.0
    near.clamp = True
    nt.links.new(cd.outputs["View Distance"], near.inputs["Value"])
    haze = nt.nodes.new("ShaderNodeMapRange")                                # 1 near .. 0.35 at 40 m
    haze.inputs["From Min"].default_value, haze.inputs["From Max"].default_value = 4.0, 40.0
    haze.inputs["To Min"].default_value, haze.inputs["To Max"].default_value = 1.0, 0.35
    haze.clamp = True
    nt.links.new(cd.outputs["View Distance"], haze.inputs["Value"])
    bright = _math(nt, "ADD", 0.45, _math(nt, "MULTIPLY", _math(nt, "POWER", rsep.outputs["X"], 5.0), 3.2))   # 0.45 .. 3.65, mostly low
    a = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", along, side), up.outputs["Result"])
    a = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", a, near.outputs["Result"]), haze.outputs["Result"])
    a = _math(nt, "MULTIPLY", a, alpha)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = core.hex_rgba(color)
    nt.links.new(_math(nt, "MULTIPLY", bright, strength), em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(_math(nt, "MINIMUM", a, 1.0), mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    _blend(m)
    return m


def _loop(ob, path: str, a, b, frames: int, start: float = 1.0):
    """Key `path` linearly from a to b over `frames` and repeat for ever (a Cycles modifier): a seamless loop at any shot length."""
    for frame, val in ((start, a), (start + frames, b)):
        core.setattr_path(ob, path, val)
        ob.keyframe_insert(path, frame=frame)
    for fc in core.fcurves(ob):
        if fc.data_path == path:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            fc.modifiers.new("CYCLES")


def _area(area):
    """((x0, y0), (x1, y1)) from dict(lo=, hi=) or (x0, y0, x1, y1)."""
    if isinstance(area, dict):
        return tuple(area["lo"]), tuple(area["hi"])
    return (area[0], area[1]), (area[2], area[3])


def rain(area, intensity: float = 1.0, wind=(0.12, 0.0), t0: float = 0.0, t1=None, height: float = 13.0, ground=0.0, splashes: bool = True,
         near=None, streak: float = 0.9, width: float = 0.0055, seed: int = 11, color="#C9D8E6", strength: float = 1.0, alpha: float = 0.42, name: str = "rain",
         exclude=()):
    """Pouring rain over a rectangle of the ground. area = dict(lo=(x, y), hi=(x, y)) or (x0, y0, x1, y1), metres.
    intensity  1.0 = steady rain (0.8 streak columns per m2), 2.0 = a downpour; wind = (wx, wy) metres of slant per metre of fall;
    t0..t1     seconds the rain is on (default: the whole shot); height: the top of the rain volume; ground: z of the ground (a number),
    splashes   small crowns on the ground inside `near` = (x, y, radius) (default: the whole area, capped): put it round the camera
               (`near` is also the camera hint for streak length: streaks far from it are drawn longer, as motion blur stretches them);
    exclude    sheltered places, [(x0, y0, x1, y1, z_roof)]: no rain falls below z_roof inside those rectangles (a canopy, a bus shelter).
    The streaks are thin crossed cards (seen from any side) that slide one period down their column and loop; the camera can go anywhere.
    They read as rain, not snow: thin, fast, slanted, semi-transparent; faint with distance and gone within 2.5 m of the lens (so no white bars
    close up); most are dim and a few bright (a per-card random brightness in the second UV map).
    Returns {"streaks": object, "splashes": object or None, "period_frames": int}."""
    (x0, y0), (x1, y1) = _area(area)
    rnd = random.Random(seed)
    wx, wy = wind
    s = Vector((wx, wy, -1.0)).normalized()                  # the way a drop travels
    ref = Vector((1, 0, 0)) if abs(s.x) < 0.9 else Vector((0, 1, 0))
    a = s.cross(ref).normalized()
    b = s.cross(a).normalized()
    cols = min(9000, max(40, int((x1 - x0) * (y1 - y0) * 0.8 * intensity)))
    K = int(math.ceil(height / RAIN_PERIOD)) + 1
    top = ground + height
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    rdl = bm.loops.layers.uv.new("RND")
    for _ in range(cols):
        gx, gy = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        phase = rnd.uniform(0.0, RAIN_PERIOD)
        ln = streak * rnd.uniform(0.7, 1.25)
        if near is not None:                                                  # longer with distance from the lens, never more than one period
            ln = min(RAIN_PERIOD * 0.92, ln * (0.8 + 0.045 * math.hypot(gx - near[0], gy - near[1])))
        bright = rnd.random()
        for k in range(K):
            z = phase + k * RAIN_PERIOD
            c = Vector((gx - wx * z, gy - wy * z, ground + z))
            if c.z + ln > top:
                continue
            if any(ex[0] <= c.x <= ex[2] and ex[1] <= c.y <= ex[3] and c.z - ground < ex[4] + RAIN_PERIOD for ex in exclude):
                continue                                                  # under cover (a copy slides down one period before it is replaced)
            head, tail = c + s * ln * 0.5, c - s * ln * 0.5
            for axis in (a, b):
                vs = [bm.verts.new(tail - axis * width), bm.verts.new(tail + axis * width), bm.verts.new(head + axis * width), bm.verts.new(head - axis * width)]
                f = bm.faces.new(vs)
                for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                    lp[uvl].uv = uv
                    lp[rdl].uv = (bright, 0.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, "FX")
    me.materials.append(_rain_mat(color, strength, alpha, top, 3.5))
    ob.visible_shadow = False
    ob["sk_role"] = "atmosphere"
    ob["sk_atmo"] = "rain"
    ob.location = (0, 0, 0)
    _loop(ob, "location", (0.0, 0.0, 0.0), tuple(s * RAIN_PERIOD), RAIN_LOOP)
    out = {"streaks": ob, "splashes": None, "period_frames": RAIN_LOOP}
    if splashes:
        sa = (x0, y0, x1, y1)
        if near is not None:                                                         # round the camera, but never outside the rain's own rectangle
            sa = (max(x0, near[0] - near[2]), max(y0, near[1] - near[2]), min(x1, near[0] + near[2]), min(y1, near[1] + near[2]))
        out["splashes"] = rain_splashes(sa, count=int(min(520, 90 + 150 * intensity)), ground=ground, seed=seed + 3, exclude=exclude)
    if t0 > 0 or t1 is not None:
        end = t1 if t1 is not None else core.current().seconds
        for o in (ob, out["splashes"]):
            if o is not None:
                _window(o, t0, end)
    return out


def _splash_mat():
    """A small splash crown on wet ground: a bright dot where the drop lands, a thin ring that opens and fades over the first 60% of a 9-frame
    beat, then nothing until the next drop. Each quad has its own phase in its second UV map; the frame number drives the clock."""
    name = "FX_rain_splash"
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    uv = nt.nodes.new("ShaderNodeUVMap")
    ph = nt.nodes.new("ShaderNodeUVMap")
    ph.uv_map = "PHASE"
    phs = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(ph.outputs["UV"], phs.inputs[0])
    clock = nt.nodes.new("ShaderNodeValue")
    clock.name = "clock"
    d = clock.outputs[0].driver_add("default_value")
    d.driver.type = "SCRIPTED"
    d.driver.expression = "frame / 9.0"
    fr = _math(nt, "FRACT", _math(nt, "ADD", clock.outputs[0], phs.outputs["X"]))
    life = _math(nt, "MINIMUM", _math(nt, "DIVIDE", fr, 0.6), 1.0)           # 0 at the hit .. 1 at the end of the splash, then it waits
    dead = _math(nt, "LESS_THAN", fr, 0.6)
    dist = nt.nodes.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    dist.inputs[1].default_value = (0.5, 0.5, 0.0)
    nt.links.new(uv.outputs["UV"], dist.inputs[0])
    rad = _math(nt, "ADD", _math(nt, "MULTIPLY", _math(nt, "POWER", life, 0.6), 0.34), 0.03)   # opens fast, then slows: 0.03 -> 0.37 uv
    off = _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", dist.outputs["Value"], rad))
    ring = nt.nodes.new("ShaderNodeMapRange")                                # 1 on the ring line, 0 beyond 0.022 uv from it
    ring.inputs["From Min"].default_value, ring.inputs["From Max"].default_value = 0.0, 0.022
    ring.inputs["To Min"].default_value, ring.inputs["To Max"].default_value = 1.0, 0.0
    nt.links.new(off, ring.inputs["Value"])
    fade = _math(nt, "POWER", _math(nt, "SUBTRACT", 1.0, life), 1.6)
    dot = nt.nodes.new("ShaderNodeMapRange")                                 # the bead of the crown at the hit, gone by 25% of the life
    dot.inputs["From Min"].default_value, dot.inputs["From Max"].default_value = 0.07, 0.02
    dot.inputs["To Min"].default_value, dot.inputs["To Max"].default_value = 0.0, 1.0
    dot.clamp = True
    nt.links.new(dist.outputs["Value"], dot.inputs["Value"])
    dot_a = _math(nt, "MULTIPLY", dot.outputs["Result"], _math(nt, "MAXIMUM", _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", life, 4.0)), 0.0))
    a = _math(nt, "ADD", _math(nt, "MULTIPLY", ring.outputs["Result"], fade), dot_a)
    a = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", a, dead), 0.4)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = core.hex_rgba("#B9CAD8")
    em.inputs["Strength"].default_value = 0.8
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(_math(nt, "MINIMUM", a, 1.0), mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    _blend(m)
    return m


def rain_splashes(area, count: int = 200, ground=0.0, size=(0.1, 0.24), seed: int = 14, name: str = "rain_splashes", exclude=()):
    """Small short-lived splash crowns where raindrops hit the ground: `count` flat quads scattered over the rectangle, each on its own beat. One mesh,
    one material, no animation data (the shader clock follows the frame number). ground: z, or a function (x, y) -> z."""
    (x0, y0), (x1, y1) = _area(area)
    rnd = random.Random(seed)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    phl = bm.loops.layers.uv.new("PHASE")
    for _ in range(count):
        x, y = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        if any(ex[0] <= x <= ex[2] and ex[1] <= y <= ex[3] for ex in exclude):
            continue
        r = rnd.uniform(*size) * 0.5
        z = ground(x, y) if callable(ground) else ground
        ph = rnd.random()
        vs = [bm.verts.new((x + sx * r, y + sy * r, z + 0.006)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        f = bm.faces.new(vs)
        for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = uv
            lp[phl].uv = (ph, 0.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, "FX")
    me.materials.append(_splash_mat())
    ob.visible_shadow = False
    ob["sk_role"] = "atmosphere"
    ob["sk_atmo"] = "rain splashes"
    return ob


def _glass_rain_mat(density: float, seed: float):
    """Water on a window: small clear beads of two sizes (voronoi cells, a share of them carrying a drop) and a few thin rivulets that run down
    (stretched noise scrolling with the frame number). Clear water is seen as a faint dark rim round a bright pinpoint of reflected light, so the
    layer is a dark, glossy, mostly transparent film with a bump (rim stronger than body): it darkens and glints, it does not glow white."""
    name = f"FX_glass_rain_{density:.2f}_{seed}"
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    beads = []
    for scale, rad, keep in ((24.0 * density, 0.2, 0.45), (8.0 * density, 0.2, 0.8)):
        vo = nt.nodes.new("ShaderNodeTexVoronoi")
        vo.voronoi_dimensions = "3D"
        vo.inputs["Scale"].default_value = scale
        nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
        cut = nt.nodes.new("ShaderNodeMapRange")
        cut.inputs["From Min"].default_value, cut.inputs["From Max"].default_value = rad, rad * 0.5
        nt.links.new(vo.outputs["Distance"], cut.inputs["Value"])
        wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "3D"
        nt.links.new(vo.outputs["Position"], wn.inputs["Vector"])
        has = _math(nt, "GREATER_THAN", wn.outputs["Value"], keep)
        beads.append(_math(nt, "MULTIPLY", cut.outputs["Result"], has))
    bead = _math(nt, "MAXIMUM", beads[0], beads[1])
    mp2 = nt.nodes.new("ShaderNodeMapping")
    mp2.inputs["Scale"].default_value = (34.0 * density, 34.0 * density, 1.4)
    nt.links.new(tc.outputs["Object"], mp2.inputs["Vector"])
    d = mp2.inputs["Location"].driver_add("default_value", 2)
    d.driver.type = "SCRIPTED"
    d.driver.expression = "frame * 0.04"
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 1.0
    nt.links.new(mp2.outputs[0], nz.inputs["Vector"])
    st = nt.nodes.new("ShaderNodeMapRange")
    st.inputs["From Min"].default_value, st.inputs["From Max"].default_value = 0.715, 0.75
    nt.links.new(nz.outputs["Fac"], st.inputs["Value"])
    wet = _math(nt, "MAXIMUM", bead, _math(nt, "MULTIPLY", st.outputs["Result"], 0.7))
    rim = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", wet, _math(nt, "SUBTRACT", 1.0, wet)), 4.0)       # 0 dry and in the middle of a drop, 1 on its edge
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Base Color"].default_value = core.hex_rgba("#1E2933")
    bs.inputs["Roughness"].default_value = 0.03
    bs.inputs["Specular IOR Level"].default_value = 0.03
    nt.links.new(_math(nt, "ADD", _math(nt, "MULTIPLY", wet, 0.3), _math(nt, "MULTIPLY", rim, 0.6)), bs.inputs["Alpha"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(wet, bump.inputs["Height"])
    nt.links.new(bump.outputs[0], bs.inputs["Normal"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bs.outputs[0], out.inputs["Surface"])
    _blend(m)
    return m


def _minus_rect(rects, hole):
    """Rectangles (u0, u1, v0, v1) with `hole` cut out of each: up to four pieces per rectangle."""
    h0, h1, g0, g1 = hole
    out = []
    for u0, u1, v0, v1 in rects:
        if h1 <= u0 or h0 >= u1 or g1 <= v0 or g0 >= v1:
            out.append((u0, u1, v0, v1))
            continue
        a0, a1 = max(u0, h0), min(u1, h1)
        if h0 > u0:
            out.append((u0, h0, v0, v1))
        if h1 < u1:
            out.append((h1, u1, v0, v1))
        if g0 > v0:
            out.append((a0, a1, v0, g0))
        if g1 < v1:
            out.append((a0, a1, g1, v1))
    return [r for r in out if r[1] - r[0] > 1e-4 and r[3] - r[2] > 1e-4]


def window_rain(target, density: float = 1.0, offset: float = 0.03, seed: float = 3.0, name: str = "window_rain", holes="auto"):
    """Rain on glass, seen from inside: beads of water and streaks that run down, on a card laid just in front of the glass. One card, one
    material; the running is a shader scrolling with the frame number. `target` is whatever carries glass:
      * a furnish.glass_front or glass_doors piece (it records its glass in sk_glass_local),
      * an arch.window / room opening handle (dict with centre, normal, w, h: `normal` points into the room),
      * a plain dict(centre=(x, y, z), normal=(nx, ny, nz), w=, h=).
    The card faces the room side; `offset` is how far in front of the glass it stands. Returns the card object.
    holes   places the card leaves dry: "auto" (default) = the holes the piece recorded (a glass front's door gap: the door leaves swing there,
            and a card across the opening would hang beads in the empty doorway), None = none, or a list of world boxes ((x0, y0, z0), (x1, y1, z1))
            (any glass whose plane crosses the box loses that part of the card)."""
    import json
    sheets = []                                                    # (centre, normal, w, h, [(u0, u1, v0, v1)] holes about the centre)
    if not isinstance(target, dict) and target.get("sk_glass_local"):
        ms = target.matrix_world
        for g in json.loads(target["sk_glass_local"]):
            sheets.append((ms @ Vector(g["centre"]), (ms.to_3x3() @ Vector(g["normal"])).normalized(), g["w"], g["h"], [tuple(x) for x in g.get("holes", ())] if holes == "auto" else []))
    else:
        sheets.append((Vector(target.get("inner_centre", target["centre"])), Vector(target["normal"]).normalized(), float(target["w"]), float(target["h"]), []))
    if holes not in ("auto", None):
        extra = []
        for lo, hi in holes:
            extra.append((Vector(lo), Vector(hi)))
        grown = []
        for c, n, w, h, hl in sheets:
            side = n.cross(Vector((0, 0, 1))).normalized()
            hl = list(hl)
            for lo, hi in extra:
                corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
                d = [(q - c).dot(n) for q in corners]
                if min(d) > 0.35 or max(d) < -0.35:                  # the box is nowhere near this sheet's plane
                    continue
                us = [(q - c).dot(side) for q in corners]
                vs = [(q - c).z for q in corners]
                hl.append((min(us), max(us), min(vs), max(vs)))
            grown.append((c, n, w, h, hl))
        sheets = grown
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for c, n, w, h, hl in sheets:
        up = Vector((0, 0, 1))
        side = n.cross(up).normalized()
        c = c + n * offset
        rects = [(-w / 2, w / 2, -h / 2, h / 2)]
        for hole in hl:
            rects = _minus_rect(rects, hole)
        for u0, u1, v0, v1 in rects:
            vs = [bm.verts.new(c + side * u + up * v) for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
            f = bm.faces.new(vs)
            for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                lp[uvl].uv = uv
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, "FX")
    me.materials.append(_glass_rain_mat(round(density, 2), seed))
    ob.visible_shadow = False
    ob["sk_role"] = "atmosphere"
    ob["sk_atmo"] = "rain on glass"
    return ob


def drips_edge(p0, p1, n: int = 14, fall: float = 1.7, seed: int = 5, color="#DCE8F2", name: str = "edge_drips"):
    """Drops falling off a canopy, awning or gutter edge between two points, each looping on its own beat (a Cycles F-curve per drop).
    `fall` is how far a drop falls before it starts again (down to the pavement)."""
    rnd = random.Random(seed)
    A, B = Vector(p0), Vector(p1)
    m = _flat_mat(color, 1.0, 1.6)
    out = []
    for i in range(n):
        p = A.lerp(B, (i + rnd.uniform(0.1, 0.9)) / n)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.016)
        me = bpy.data.meshes.new("edge_drip")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"{name}_{i}", me)
        core.link(ob, "FX")
        me.materials.append(m)
        ob.scale = (1, 1, 2.6)
        ob.visible_shadow = False
        dur = rnd.randint(8, 12)
        ph = rnd.randint(0, dur - 1)
        for frame, z in ((1 - ph, p.z), (1 - ph + dur, p.z - fall)):
            ob.location = (p.x, p.y, z)
            ob.keyframe_insert("location", frame=frame)
        for fc in core.fcurves(ob):
            if fc.data_path == "location":
                for kp in fc.keyframe_points:
                    kp.interpolation = "QUAD"
                    kp.easing = "EASE_IN"
                fc.modifiers.new("CYCLES")
        out.append(ob)
    return out
