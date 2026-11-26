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
    "candlelit": {"sky": ("#0E0A08", "#1B130E"), "sun": ("#FFC48A", 0.0, 40, 6), "ambient": 0.45, "clouds": 0.0, "cast": ("#FFD0A0", 0.32, 0.82)},
    "office_day": {"sky": ("#C7D6E4", "#EEF1F2"), "sun": ("#FFF4E4", 0.0, 40, 6), "ambient": 0.7, "clouds": 0.0, "cast": ("#FFF8EE", 0.2, 0.94)},
    "office_night": {"sky": ("#0B1226", "#1E2A4A"), "sun": ("#B8C6FF", 0.0, 40, 6), "ambient": 0.22, "clouds": 0.0, "cast": ("#DCE4FF", 0.22, 0.84)},
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
    if power * strength > 0:                                  # no sun at all (not a dark one) when it is switched off: a sun is the costliest shadow caster
        ld = bpy.data.lights.new("SUN", "SUN")
        ld.energy = power * strength
        ld.color = core.hex_rgba(col)[:3]
        ld.angle = math.radians(soft)
        _coarse_shadow(ld, _pool_res(0.08))
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


def _pool_res(fine: float) -> float:
    """The shadow resolution limit for a big light (a sun over a whole open set) given the locked shadow pool of the quality in use: the finest
    the pool can hold at final (512 MB), coarser at preview (256 MB) and draft (128 MB), where a sun over an open set would overflow it."""
    try:
        mb = int(bpy.context.scene.eevee.shadow_pool_size)
    except (AttributeError, ValueError, TypeError):
        mb = 512
    return fine * (1.0 if mb >= 512 else 3.0 if mb >= 256 else 6.0)


def _coarse_shadow(ld, res: float):
    """Limit a light's shadow resolution (metres per texel): the shadow pool is shared and locked, and a 1 mm default asks for hundreds of
    tiles from one sun or lantern. 2-3 cm is plenty for shadows that fall on a floor or a wall."""
    for k, v in (("shadow_maximum_resolution", res), ("shadow_cascade_max_distance", 90.0), ("shadow_cascade_count", 3)):
        try:
            setattr(ld, k, v)
        except (AttributeError, TypeError):
            pass


def practical(name: str, at, color="#FFC477", power: float = 60.0, radius: float = 0.1, kind: str = "POINT", aim=None, size: float | None = None, shadow: bool = True):
    """A visible source: lantern, candle, fire, lit window (pair it with something that glows: mat.emit). power in watts.
    Returns the light OBJECT (tagged sk_role=practical) so recipes and the set audit can count it."""
    ld = bpy.data.lights.new(name, kind)
    ld.energy = power
    ld.color = core.hex_rgba(color)[:3]
    ld.use_shadow = shadow
    _coarse_shadow(ld, 0.03)
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
    ob["sk_role"] = "practical"                              # the set audit counts these; fill, key and rim lights carry other roles
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


# ----------------------------------------------------------------------------- interiors: window keys, rims, shafts, dust
def _opening_frame(opening, aim=None):
    """(centre, inward direction, width, height) from an arch opening dict, or from a bare point plus aim=."""
    if isinstance(opening, dict):
        return Vector(opening["centre"]), Vector(opening["normal"]).normalized(), float(opening["w"]), float(opening["h"])
    c = core.point_of(opening)
    if aim is None:
        raise ValueError("key_from=<point> needs aim=<point> so the light knows which way into the room")
    d = core.point_of(aim) - c
    return c, d.normalized(), 1.2, 1.6


def window_key(opening, color="#FFEBCB", power: float = 900.0, aim=None, pitch: float = 24.0, soft: float = 0.9, shaft: bool = True,
               reach: float = 7.0, shaft_strength: float = 0.05, name: str = "KEY_window", shadow: bool = True):
    """The key light of an interior: a soft rectangular area light standing just outside a window or door, shining in, tilted
    down by `pitch` degrees. Mullions and frames cast real window shadows. `opening` is an arch.window / arch.door handle
    (or a point with aim=). shaft=True adds a visible fake light shaft (a faded glowing prism, no volume cost).
    Returns {"light", "shaft"}."""
    c, n, w, h = _opening_frame(opening, aim)
    flat = Vector((n.x, n.y, 0)).normalized()
    d = (flat * math.cos(math.radians(pitch)) + Vector((0, 0, -math.sin(math.radians(pitch))))).normalized()
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = max(0.3, w * soft), max(0.3, h * soft)
    ld.energy = power
    ld.color = core.hex_rgba(color)[:3]
    ld.use_shadow = shadow
    _coarse_shadow(ld, 0.05)
    try:
        ld.spread = math.radians(100)
    except AttributeError:
        pass
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, "LIGHTS")
    ob.location = c - d * 0.25
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    ob["sk_role"] = "key"
    out = {"light": ob, "shaft": None}
    if shaft:
        out["shaft"] = light_shaft(c, d, w, h, reach, color, shaft_strength, name=f"{name}.shaft")
    return out


_OUTWARD = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}


def window_sun(room_, wall: str, elevation: float = 34.0, yaw: float = 0.0, power: float = 3.2, color="#FFEBCB", soft: float = 1.5, name: str = "SUN_window"):
    """Real sun patches: one sun standing outside `wall` (N, S, E or W), `elevation` degrees up, turned `yaw` degrees along the wall. The
    walls and the roof of the room block it, so it reaches the floor only as the shapes of the windows (with their mullions). Gives the
    crisp bright patches that an area light through a window does not. Use it with the set's own rig (sun strength 0) and window_key
    for the soft sky light."""
    ox, oy = _OUTWARD[wall]
    a = math.atan2(ox, -oy) + math.radians(yaw)               # azimuth in the same convention as rig(): 0 = from -Y
    e = math.radians(elevation)
    to_sun = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = power
    ld.color = core.hex_rgba(color)[:3]
    ld.angle = math.radians(soft)
    _coarse_shadow(ld, 0.03)
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, "LIGHTS")
    ob.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    ob["sk_role"] = "key"
    return ob


def limit_shadows(max_local: int = 8) -> int:
    """Keep the shadow pool from overflowing ("Shadow buffer full"): every shadow-casting point, spot or area light costs a cube or a
    tile set. Keeps shadows on the `max_local` strongest local lights (window keys always stay) and turns them off on the rest, which are
    small practicals whose shadows nobody reads. Call it once at the end of the set. Returns how many lights lost their shadow."""
    cands = []
    for o in bpy.data.objects:
        if o.type != "LIGHT" or o.data.type == "SUN" or not o.data.use_shadow or o.get("sk_role") in ("key",):
            continue
        cands.append(o)
    cands.sort(key=lambda o: -o.data.energy)
    off = 0
    for o in cands[max_local:]:
        o.data.use_shadow = False
        off += 1
    return off


def light_shaft(centre, direction, w: float, h: float, reach: float = 7.0, color="#FFEBCB", strength: float = 0.05, name: str = "SHAFT"):
    """A visible beam: a prism from a w x h opening along `direction`, widening a little, with a glow that fades along its
    length and at its edges. Blended emission, no volume: cheap at any quality."""
    import bmesh
    c, d = Vector(centre), Vector(direction).normalized()
    side = d.cross(Vector((0, 0, 1)))
    side = side.normalized() if side.length > 1e-4 else Vector((1, 0, 0))
    up = side.cross(d).normalized()

    def quad(k, grow):
        return [c + d * k + side * sx * w / 2 * grow + up * sz * h / 2 * grow for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

    bm = bmesh.new()
    near, far = [bm.verts.new(p) for p in quad(0.0, 1.0)], [bm.verts.new(p) for p in quad(reach, 1.0 + reach * 0.04)]
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((near[i], near[j], far[j], far[i]))
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uv].uv = (0.0, 0.0 if lp.vert in near else 1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, "FX")
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    fade = nt.nodes.new("ShaderNodeMapRange")                 # bright near the window, gone by the far end
    fade.inputs["From Min"].default_value, fade.inputs["From Max"].default_value = 0.0, 1.0
    fade.inputs["To Min"].default_value, fade.inputs["To Max"].default_value = 1.0, 0.0
    nt.links.new(sep.outputs["Y"], fade.inputs["Value"])
    lw = nt.nodes.new("ShaderNodeLayerWeight")                # soft edges: strongest where the surface faces the camera
    lw.inputs["Blend"].default_value = 0.5
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(fade.outputs["Result"], mul.inputs[0])
    nt.links.new(lw.outputs["Facing"], mul.inputs[1])
    sc = nt.nodes.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    sc.inputs[1].default_value = strength
    nt.links.new(mul.outputs[0], sc.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = core.hex_rgba(color)
    em.inputs["Strength"].default_value = 1.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(sc.outputs[0], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass
    try:
        m.use_backface_culling = False
    except AttributeError:
        pass
    me.materials.append(m)
    ob.visible_shadow = False
    ob["sk_role"] = "atmosphere"
    ob["sk_atmo"] = "light shaft"
    return ob


def rim_light(target, from_deg: float = 150.0, elevation: float = 28.0, distance: float = 4.0, color="#BFD4FF", power: float = 350.0, name: str = "RIM_char"):
    """A shadowless back light for characters: it hangs behind `target` (a mark or point) as seen from the camera side (-Y),
    from_deg round the stage like lights.rig's sun_from, so the figure gets a bright edge and lifts off the set."""
    t = core.point_of(target)
    az, el = math.radians(from_deg), math.radians(elevation)
    off = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * distance
    ld = bpy.data.lights.new(name, "SPOT")
    ld.energy = power
    ld.color = core.hex_rgba(color)[:3]
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(48), 0.6, 0.3
    ld.use_shadow = False
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, "LIGHTS")
    ob.location = t + off
    ob.rotation_euler = (-off).to_track_quat("-Z", "Y").to_euler()
    ob["sk_role"] = "rim"
    return ob


def ambient_fill(at, size=(6.0, 6.0), power: float = 300.0, color="#FFF2E0", name: str = "FILL"):
    """A big, soft, shadowless area light facing down: the bounce an enclosed room would get and EEVEE does not compute."""
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = size
    ld.energy = power
    ld.color = core.hex_rgba(color)[:3]
    ld.use_shadow = False
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, "LIGHTS")
    ob.location = at
    ob["sk_role"] = "fill"
    return ob


def _mote_material(color: str, strength: float):
    """A blended emission whose strength falls off from the middle of the quad: a soft round speck, not a hard triangle."""
    name = f"SK_mote_{color}_{strength}"
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    uv = nt.nodes.new("ShaderNodeUVMap")
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "DISTANCE"
    sub.inputs[1].default_value = (0.5, 0.5, 0.0)
    nt.links.new(uv.outputs["UV"], sub.inputs[0])
    rmp = nt.nodes.new("ShaderNodeMapRange")                  # 0 at the middle -> 1, 0.5 at the edge -> 0
    rmp.inputs["From Min"].default_value, rmp.inputs["From Max"].default_value = 0.0, 0.5
    rmp.inputs["To Min"].default_value, rmp.inputs["To Max"].default_value = 1.0, 0.0
    nt.links.new(sub.outputs["Value"], rmp.inputs["Value"])
    sq = nt.nodes.new("ShaderNodeMath")
    sq.operation = "POWER"
    sq.inputs[1].default_value = 2.0
    nt.links.new(rmp.outputs["Result"], sq.inputs[0])
    sc = nt.nodes.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    sc.inputs[1].default_value = min(1.0, 0.45 * strength)
    nt.links.new(sq.outputs[0], sc.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = core.hex_rgba(color)
    em.inputs["Strength"].default_value = 1.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(sc.outputs[0], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass
    try:
        m.use_backface_culling = False
    except AttributeError:
        pass
    return m


def dust(lo, hi, count: int = 260, size: float = 0.012, color="#FFE2B0", strength: float = 0.8, seed: int = 1, name: str = "DUST"):
    """Cheap floating motes: a cloud of faint, soft, round specks filling the box lo..hi (put it where a light shaft falls).
    One mesh, one blended material, no volume and no particle system. They are small, warm and dim: against a bright daylit
    wall they show as a faint haze of speckle, never as white sparkle."""
    import random

    import bmesh
    rnd = random.Random(seed)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for _ in range(count):
        p = Vector([rnd.uniform(lo[i], hi[i]) for i in range(3)])
        s = size * rnd.uniform(1.0, 2.2)
        a, b = rnd.uniform(0, 6.28), rnd.uniform(0, 3.14)
        ax = Vector((math.cos(a), math.sin(a), 0.0))
        ay = Vector((-math.sin(a) * math.cos(b), math.cos(a) * math.cos(b), math.sin(b)))
        vs = [bm.verts.new(p + ax * sx * s + ay * sy * s) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        f = bm.faces.new(vs)
        for lp, uvv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = uvv
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, "FX")
    me.materials.append(_mote_material(color, strength))
    ob.visible_shadow = False
    ob["sk_role"] = "atmosphere"
    ob["sk_atmo"] = "dust motes"
    return ob


def interior(mood: str = "interior_day", key_from=None, aim=None, key_color="#FFEBCB", key_power: float = 900.0, rim: float | None = None,
             shaft: bool = True, fill=None, **kw):
    """Light for an enclosed place in one call: the mood's world (ambient), a real window key from key_from (an arch opening
    or a point with aim=), a rim for the cast (rim = strength of the soft back sun, default 0), an optional fill
    (a dict: at=, size=, power=). Returns {"rig", "key", "fill"}. Sets with no window key (candlelit, office night) pass
    key_from=None and light themselves with practicals."""
    R = rig(mood, rim=0.0 if rim is None else rim, look=False, **kw)
    out = {"rig": R, "key": None, "fill": None}
    if key_from is not None:
        out["key"] = window_key(key_from, key_color, key_power, aim=aim, shaft=shaft)
    if fill:
        out["fill"] = ambient_fill(**fill)
    return out
