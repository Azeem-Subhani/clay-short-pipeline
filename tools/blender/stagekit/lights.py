"""stagekit.lights - one light rig per place and time of day: a sky, a sun or moon, and how the 2D cast sits in it.

    R = lights.rig("day_clear", sun_from=40)        # in the set file, once
    lights.practical("lantern", at=(1, 2, 2.1))     # visible warm sources add depth
    R2 = lights.rig("golden_hour", sun_from=-60)    # a later time of day = another call in that shot's set options

A rig sets the sky (gradient, clouds, sun disc), the key light, the ambient fill that keeps shadows coloured, and
cast.look() so the flat characters take the colour of the hour. The same mood gives the same light in every shot of a set.

Flat characters throw cut-out shadows. Light them from 30-60 degrees to one side of the camera (sun_from): the shadow then
falls across the ground beside them and pins them to it. Light from straight behind the camera hides the shadow; light from
straight sideways squeezes it to a line.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import cast as cast_mod
from . import core

MOODS = {
    # sky: (zenith, horizon), sun: (colour, strength, elevation deg, softness deg), ambient: world strength, clouds 0..1,
    # cast: (tint on the characters, lit, gain)
    "day_clear": {"sky": ("#3F7FD6", "#BFE0F7"), "sun": ("#FFF1DC", 4.2, 46, 2.5), "ambient": 1.0, "clouds": 0.55, "cast": ("#FFFAF0", 0.22, 0.96)},
    "day_soft": {"sky": ("#7F9DBE", "#D9E3EA"), "sun": ("#FFF6EA", 2.4, 52, 14), "ambient": 1.25, "clouds": 0.9, "cast": ("#F6F6F2", 0.18, 0.94)},
    "morning": {"sky": ("#5C97DE", "#FBE3C4"), "sun": ("#FFE2B8", 3.6, 22, 3), "ambient": 0.9, "clouds": 0.4, "cast": ("#FFF1DC", 0.24, 0.95)},
    "golden_hour": {"sky": ("#5D79B8", "#FFB36B"), "sun": ("#FFB470", 3.8, 13, 3), "ambient": 0.8, "clouds": 0.5, "cast": ("#FFDDB8", 0.28, 0.92)},
    "sunset": {"sky": ("#4F5A9E", "#FF9E66"), "sun": ("#FF9C5C", 3.6, 11, 4), "ambient": 1.0, "clouds": 0.6, "cast": ("#FFD2AC", 0.28, 0.9)},
    "dusk": {"sky": ("#232B55", "#C96F5A"), "sun": ("#9FB0FF", 0.9, 30, 10), "ambient": 0.55, "clouds": 0.4, "cast": ("#C9C6E8", 0.26, 0.74)},
    "night_moon": {"sky": ("#0A1230", "#27345E"), "sun": ("#AFC3FF", 1.1, 42, 3), "ambient": 0.35, "clouds": 0.35, "cast": ("#B7C4EA", 0.3, 0.66)},
    "storm": {"sky": ("#3B4654", "#7C8894"), "sun": ("#D5DEE8", 1.4, 50, 20), "ambient": 0.9, "clouds": 1.0, "cast": ("#DDE3EA", 0.2, 0.82)},
    # interiors and underground: no sun through the roof; the key is a window or lamp you place with key_from / practicals
    "interior_day": {"sky": ("#BFD4E8", "#E8EEF2"), "sun": ("#FFF0D8", 3.0, 35, 6), "ambient": 0.35, "clouds": 0.0, "cast": ("#FFF3E2", 0.26, 0.9)},
    "interior_warm": {"sky": ("#1A1410", "#2A1E16"), "sun": ("#FFC48A", 0.0, 40, 6), "ambient": 0.5, "clouds": 0.0, "cast": ("#FFD9B0", 0.3, 0.84)},
    "cave": {"sky": ("#0C0A09", "#17120E"), "sun": ("#FFC48A", 0.0, 40, 6), "ambient": 0.6, "clouds": 0.0, "cast": ("#FFD3A6", 0.32, 0.8)},
}


class Rig:
    def __init__(self, mood, sun, world, rim=None):
        self.mood, self.sun, self.world, self.rim = mood, sun, world, rim


def _sky(zenith, horizon, sun_dir, sun_col, strength, clouds, name="SKY"):
    """World shader: horizon-to-zenith gradient, a warm glow and disc around the sun, drifting soft clouds."""
    w = bpy.data.worlds.get(name) or bpy.data.worlds.new(name)
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = 0.0, core.hex_rgba(horizon)
    el[1].position, el[1].color = 0.6, core.hex_rgba(zenith)
    mp = nt.nodes.new("ShaderNodeMapRange")
    mp.inputs["From Min"].default_value = -0.02
    mp.inputs["From Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], mp.inputs["Value"])
    nt.links.new(mp.outputs["Result"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    # sun glow + disc
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nrm = nt.nodes.new("ShaderNodeVectorMath")
    nrm.operation = "NORMALIZE"
    nt.links.new(tc.outputs["Generated"], nrm.inputs[0])
    nt.links.new(nrm.outputs[0], dot.inputs[0])
    dot.inputs[1].default_value = tuple(sun_dir)
    glow = nt.nodes.new("ShaderNodeValToRGB")
    g = glow.color_ramp.elements
    g[0].position, g[0].color = 0.80, (0, 0, 0, 1)
    g[1].position, g[1].color = 0.9995, (1, 1, 1, 1)
    mid = g.new(0.985)
    mid.color = (0.22, 0.22, 0.22, 1)
    nt.links.new(dot.outputs["Value"], glow.inputs["Fac"])
    add = nt.nodes.new("ShaderNodeMix")
    add.data_type = "RGBA"
    add.blend_type = "ADD"
    sc = core.hex_rgba(sun_col)
    add.inputs["B"].default_value = (sc[0] * 2.2, sc[1] * 2.2, sc[2] * 2.2, 1)
    nt.links.new(col, add.inputs["A"])
    nt.links.new(glow.outputs["Color"], add.inputs["Factor"])
    col = add.outputs["Result"]
    if clouds > 0:
        mpv = nt.nodes.new("ShaderNodeMapping")
        mpv.inputs["Scale"].default_value = (1.0, 1.0, 3.2)
        nt.links.new(nrm.outputs[0], mpv.inputs["Vector"])
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.noise_dimensions = "4D"
        nz.inputs["Scale"].default_value = 2.6
        nz.inputs["Detail"].default_value = 6.0
        nz.inputs["Roughness"].default_value = 0.58
        nt.links.new(mpv.outputs[0], nz.inputs["Vector"])
        s = bpy.context.scene
        nz.inputs["W"].default_value = 0.0
        nz.inputs["W"].keyframe_insert("default_value", frame=1)
        nz.inputs["W"].default_value = 0.012 * max(1, s.frame_end) / s.render.fps
        nz.inputs["W"].keyframe_insert("default_value", frame=max(2, s.frame_end))
        cr = nt.nodes.new("ShaderNodeValToRGB")
        ce = cr.color_ramp.elements
        ce[0].position, ce[0].color = 0.62 - 0.16 * clouds, (0, 0, 0, 1)
        ce[1].position, ce[1].color = 0.80 - 0.1 * clouds, (1, 1, 1, 1)
        nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
        up = nt.nodes.new("ShaderNodeMapRange")           # no clouds on the horizon line or straight overhead
        up.inputs["From Min"].default_value = 0.03
        up.inputs["From Max"].default_value = 0.22
        nt.links.new(sep.outputs["Z"], up.inputs["Value"])
        mask = nt.nodes.new("ShaderNodeMath")
        mask.operation = "MULTIPLY"
        nt.links.new(cr.outputs["Color"], mask.inputs[0])
        nt.links.new(up.outputs["Result"], mask.inputs[1])
        cm = nt.nodes.new("ShaderNodeMix")
        cm.data_type = "RGBA"
        cm.inputs["B"].default_value = core.hex_rgba(_mix_hex("#FFFFFF", horizon, 0.3 if clouds < 0.95 else 0.75))
        nt.links.new(col, cm.inputs["A"])
        nt.links.new(mask.outputs[0], cm.inputs["Factor"])
        col = cm.outputs["Result"]
    nt.links.new(col, bg.inputs["Color"])
    bpy.context.scene.world = w
    return w


def _mix_hex(a: str, b: str, k: float) -> str:
    ha, hb = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(int(ha[i:i + 2], 16) * (1 - k) + int(hb[i:i + 2], 16) * k):02X}" for i in (0, 2, 4))


def rig(mood: str = "day_clear", sun_from: float = 40.0, sun_elevation: float | None = None, strength: float = 1.0, ambient: float | None = None,
        rim: float | None = None, clouds: float | None = None, look: bool = True) -> Rig:
    """Build the light for a set. sun_from: where the light comes from, in degrees around the stage measured from the
    camera side (-Y): 0 = from behind the camera, 40 = from behind-right, -60 = from behind-left, 150 = backlight from
    far right. rim is a weak shadowless back light that separates the cast from the set (default 0.55; 0 = off). Returns Rig(sun, world)."""
    if mood not in MOODS:
        raise KeyError(f"unknown mood {mood!r}: use one of {', '.join(MOODS)}")
    m = MOODS[mood]
    col, power, elev, soft = m["sun"]
    elev = elev if sun_elevation is None else sun_elevation
    az = math.radians(sun_from)
    e = math.radians(elev)
    to_sun = Vector((math.sin(az) * math.cos(e), -math.cos(az) * math.cos(e), math.sin(e)))
    world = _sky(m["sky"][0], m["sky"][1], to_sun, col, (m["ambient"] if ambient is None else ambient), m["clouds"] if clouds is None else clouds)
    sun = None
    if power > 0:
        ld = bpy.data.lights.new("SUN", "SUN")
        ld.energy = power * strength
        ld.color = core.hex_rgba(col)[:3]
        ld.angle = math.radians(soft)
        sun = bpy.data.objects.new("SUN", ld)
        core.link(sun, "LIGHTS")
        sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    rim_ob = None
    if rim is None:                                         # a soft back light lifts the 3D cast off the set; rim=0 turns it off
        rim = 0.55
    if rim > 0:
        rd = bpy.data.lights.new("RIM", "SUN")
        rd.energy = rim
        rd.color = core.hex_rgba(m["sky"][1])[:3]
        rd.use_shadow = False
        rim_ob = bpy.data.objects.new("RIM", rd)
        core.link(rim_ob, "LIGHTS")
        back = Vector((-to_sun.x, -to_sun.y, 0.5)).normalized()
        rim_ob.rotation_euler = (-back).to_track_quat("-Z", "Y").to_euler()
    if look:
        cast_mod.look(*m["cast"])
    bpy.context.scene["light_rig"] = f"{mood} sun_from={sun_from} elev={elev}"
    return Rig(mood, sun, world, rim_ob)


def practical(name: str, at, color="#FFC477", power: float = 60.0, radius: float = 0.1, kind: str = "POINT", aim=None, size: float | None = None, shadow: bool = True):
    """A visible source: lantern, candle, fire, lit window (pair it with something that glows: mat.emit). power in watts."""
    ld = bpy.data.lights.new(name, kind)
    ld.energy = power
    ld.color = core.hex_rgba(color)[:3]
    ld.use_shadow = shadow
    if kind == "AREA":
        ld.size = size or 1.0
    else:
        ld.shadow_soft_size = radius
        if kind == "SPOT":
            ld.spot_size = math.radians(size or 60)
            ld.spot_blend = 0.4
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, "LIGHTS")
    ob.location = at
    if aim is not None:
        d = core.point_of(aim) - Vector(at)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def change(light, t0: float, t1: float, power: float | None = None, color=None):
    """Ease a light to a new power / colour between two times (a fire catching, a cloud passing, a lamp turned down)."""
    shot = core.current()
    d = light.data
    d.keyframe_insert("energy", frame=shot.f(t0))
    d.keyframe_insert("color", frame=shot.f(t0))
    if power is not None:
        d.energy = power
    if color is not None:
        d.color = core.hex_rgba(color)[:3]
    d.keyframe_insert("energy", frame=shot.f(t1))
    d.keyframe_insert("color", frame=shot.f(t1))


def flicker(light, t0: float = 0.0, t1: float | None = None, amount: float = 0.25, rate: float = 9.0, seed: int = 3):
    """Fire and candle light breathes. Keys small random changes in power."""
    import random
    shot = core.current()
    t1 = shot.seconds if t1 is None else t1
    rnd = random.Random(seed)
    base = light.data.energy
    n = max(2, int((t1 - t0) * rate))
    for i in range(n + 1):
        light.data.energy = base * (1.0 + rnd.uniform(-amount, amount))
        light.data.keyframe_insert("energy", frame=shot.f(t0 + (t1 - t0) * i / n))
    light.data.energy = base


def haze(density: float = 0.012, color="#C9D6E6", anisotropy: float = 0.5):
    """Thin air you can see: sun shafts, depth, dust. It costs render time: use it where the story is about the air."""
    bm = bpy.data.meshes.new("HAZE")
    import bmesh
    b = bmesh.new()
    bmesh.ops.create_cube(b, size=120.0)
    b.to_mesh(bm)
    b.free()
    ob = bpy.data.objects.new("HAZE", bm)
    core.link(ob, "FX")
    ob.location.z = 55
    m = bpy.data.materials.new("HAZE")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Color"].default_value = core.hex_rgba(color)
    v.inputs["Density"].default_value = density
    v.inputs["Anisotropy"].default_value = anisotropy
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(v.outputs[0], o.inputs["Volume"])
    bm.materials.append(m)
    ob.visible_shadow = False
    return ob
