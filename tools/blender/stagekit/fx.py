"""stagekit.fx - small effects that make an action read: water answers, things glint, impacts kick up dust.

    fx.ripple((x, y, water_z), t)                 # rings spreading where something touched the water
    fx.splash((x, y, water_z), t, size=1.0)       # drops thrown up, a crown, then rings
    fx.sparkle(ring, t, count=3)                  # a glint so a small important thing is found by the eye
    fx.puff((x, y, 0), t)                         # dust or spray at a landing, a snap, a footfall
    fx.drips(actor.chest, t0, t1)                 # water running off someone who fell in

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
