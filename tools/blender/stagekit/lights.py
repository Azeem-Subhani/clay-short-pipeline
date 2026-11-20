"""stagekit.lights - one motivated light rig per location and time of day.

A rig is always the same four ideas, so every shot of the channel reads the same way:
  key      the motivated source (sun, moon, window, lamp) - gives direction and shape
  fill     soft ambient: world colour + a huge weak area light from the camera side - no crushed blacks
  rim      a thin edge from behind that separates the subject from the background
  practicals  visible sources in frame (lamp, window, siren) added with practical()

Angles: azimuth is measured around the subject from the camera side (-Y). 0 = light from the camera,
-90 = from screen-left, +90 = from screen-right, 180 = from behind. Elevation is degrees above the horizon.
Shape comes from the side: keep the key between 35 and 80 degrees off the camera axis.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import core

# key: colour, power (W for AREA at 6 m, W/m2 for SUN), kind, size (m) or sun angle (deg), default azimuth/elevation
# fill/rim: colour and power as a fraction of the key.  world: colour, strength.
MOODS = {
    "day_soft": dict(key=("#FFF0DA", 3.2, "SUN", 9.0, -50, 48), fill=("#BFD7FF", 0.20), rim=("#FFF6E8", 0.25),
                     world=("#8FB6EE", 0.55), note="calm, safe, open: soft sun, blue sky fill"),
    "golden_hour": dict(key=("#FFAE66", 3.6, "SUN", 6.0, -62, 16), fill=("#8EA2E0", 0.16), rim=("#FFC38A", 0.45),
                        world=("#6C7FC4", 0.40), note="warm, nostalgic, hopeful: low sun, long shadows, cool fill"),
    "overcast": dict(key=("#E6EDF5", 900, "AREA", 9.0, -30, 70), fill=("#D5DEE8", 0.45), rim=("#FFFFFF", 0.12),
                     world=("#B9C4D0", 0.75), note="flat sadness, waiting: big soft top light, weak shadows"),
    "night_moon": dict(key=("#8FAEFF", 2.2, "SUN", 3.0, 125, 48), fill=("#5A74D8", 0.30), rim=("#A9C1FF", 0.60),
                       world=("#1B2A6B", 1.3), note="secrecy, dread: cool moon from behind-side; add one warm practical"),
    "interior_warm": dict(key=("#FFC58A", 800, "AREA", 2.2, -55, 38), fill=("#C99A7A", 0.22), rim=("#9DB7FF", 0.40),
                          world=("#2B211E", 0.50), note="home, safety: warm lamp key, cool window edge"),
    "interior_cold": dict(key=("#D8E8FF", 760, "AREA", 3.0, -25, 72), fill=("#A9BFD6", 0.30), rim=("#E8F1FF", 0.20),
                          world=("#1C232C", 0.55), note="office, hospital, unease: cold top light"),
    "interior_night": dict(key=("#7F9CF2", 560, "AREA", 1.6, 70, 40), fill=("#39479A", 0.16), rim=("#9FB8FF", 0.50),
                           world=("#070B1E", 0.50), note="dark room, moon through a window; pools of light and darkness"),
    "dread": dict(key=("#C4D2FF", 950, "SPOT", 0.25, -78, 22), fill=("#2A3566", 0.07), rim=("#8EA6FF", 0.85),
                  world=("#04060F", 0.35), note="the strike: one hard low side light, faces half lit, highest contrast"),
    "candle": dict(key=("#FF9A4A", 300, "POINT", 0.06, -40, 15), fill=("#5A2E1A", 0.12), rim=("#6B7FD6", 0.30),
                   world=("#0A0706", 0.40), note="intimate, fragile: one small warm source close to the subject"),
    "relief": dict(key=("#FFD9A8", 3.0, "SUN", 12.0, -45, 30), fill=("#D8E2FF", 0.34), rim=("#FFE9C8", 0.30),
                   world=("#A9C2EE", 0.70), note="the truth, release: light opens up, warm and lifted"),
}


class Rig:
    """Handles to the lights of a rig. Tweak (rig.key.data.energy *= 0.8) or animate (lights.change)."""

    def __init__(self, mood, subject, key, fill, rim, world):
        self.mood, self.subject = mood, Vector(subject)
        self.key, self.fill, self.rim, self.world = key, fill, rim, world
        self.practicals: list = []

    def all(self):
        return [o for o in (self.key, self.fill, self.rim, *self.practicals) if o is not None]


def _polar(subject, azimuth, elevation, distance):
    a, e = math.radians(azimuth), math.radians(elevation)
    s = Vector(subject)
    return s + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * distance


def _aim(ob, target):
    ob.rotation_euler = (Vector(target) - ob.location).to_track_quat("-Z", "Y").to_euler()


def _light(name, kind, color, power, at, aim=None, size=1.0, soft=True, coll="LIGHTS"):
    ld = bpy.data.lights.new(name, kind)
    ld.color = core.hex_rgba(color)[:3]
    ld.energy = power
    if kind == "AREA":
        ld.shape = "DISK"
        ld.size = size
    elif kind == "SUN":
        ld.angle = math.radians(size)
    elif kind == "SPOT":
        ld.spot_size = math.radians(60)
        ld.spot_blend = 0.7
        ld.shadow_soft_size = size
    else:
        ld.shadow_soft_size = size
    ld.use_shadow = True
    ld.use_shadow_jitter = bool(soft)          # real soft penumbra instead of a filtered hard edge
    ld.shadow_jitter_overblur = 10.0
    ld.shadow_filter_radius = 1.5
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, coll)
    ob.location = at
    if aim is not None:
        _aim(ob, aim)
    return ob


def set_world(color="#0A1232", strength: float = 0.5):
    """Ambient colour of everything the lights do not reach. Shadows take this colour, so never leave it grey."""
    w = bpy.data.worlds.get("STAGE_World") or bpy.data.worlds.new("STAGE_World")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = core.hex_rgba(color)
    bg.inputs["Strength"].default_value = strength
    bpy.context.scene.world = w
    return w


def rig(mood: str = "day_soft", subject=(0, 0, 1.2), key_azimuth: float | None = None, key_elevation: float | None = None,
        distance: float | None = None, strength: float = 1.0, fill: float = 1.0, rim: float = 1.0, ambient: float = 1.0) -> Rig:
    """Build the rig for one location and time of day. Call it ONCE per set; every shot in that set reuses it.
    subject: the point the light is shaped around (usually the main character's chest/head).
    distance: how far the key sits from the subject. Indoors keep it inside the room (default 3.2 m) or the walls shadow it.
    strength / fill / rim / ambient: multipliers on the mood's own balance (fill=0.5 = more drama, 1.5 = gentler)."""
    if mood not in MOODS:
        raise KeyError(f"unknown mood {mood!r}; choose from {sorted(MOODS)}")
    m = MOODS[mood]
    if distance is None:
        distance = 3.2 if mood.startswith(("interior", "candle")) else 6.0   # interior lights must fit inside the room
    kc, kp, kind, ksize, kaz, kel = m["key"]
    az = kaz if key_azimuth is None else key_azimuth
    el = kel if key_elevation is None else key_elevation
    scale = (distance / 6.0) ** 2
    if kind == "SUN":
        key = _light(f"key_{mood}", "SUN", kc, kp * strength, _polar(subject, az, el, 30.0), subject, ksize)
        kw = kp * 250.0            # rough watt-equivalent so fill and rim keep their ratio to a sun key
    else:
        key = _light(f"key_{mood}", kind, kc, kp * strength * scale, _polar(subject, az, el, distance), subject, ksize)
        kw = kp
    fc, fr = m["fill"]
    # the fill sits on the camera side, opposite the key, big and close to the lens axis: it lifts shadows without a second shadow
    f_az = -math.copysign(25.0, az if abs(az) <= 180 else -az) if abs(az) < 120 else 0.0
    fl = _light(f"fill_{mood}", "AREA", fc, kw * fr * fill * strength * scale * 2.2, _polar(subject, f_az, 28, distance * 1.1), subject, distance * 1.4)
    fl.data.use_shadow = False
    fl.data.specular_factor = 0.25
    rc, rr = m["rim"]
    r_az = az + 180 - math.copysign(40.0, az) if abs(az) < 100 else -az * 0.55
    rm = _light(f"rim_{mood}", "SPOT", rc, kw * rr * rim * strength * scale * 2.4, _polar(subject, r_az, 38, distance * 0.8), Vector(subject) + Vector((0, 0, 0.25)), 0.35)
    rm.data.spot_size = math.radians(75)
    wc, ws = m["world"]
    w = set_world(wc, ws * ambient)
    r = Rig(mood, subject, key, fl, rm, w)
    bpy.context.scene["light_rig"] = mood
    return r


def practical(name: str, at, color="#FFC477", power: float = 40.0, radius: float = 0.08, kind: str = "POINT", aim=None, size: float | None = None,
              shadow: bool = True, rig_: Rig | None = None):
    """A source the viewer can SEE or infer: table lamp, bulb, window, fire, screen, siren.
    kind POINT for bulbs; AREA with `aim` and `size` for a window or a screen; SPOT for a torch or headlight."""
    ob = _light(name, kind, color, power, at, aim, size if size is not None else radius)
    ob.data.use_shadow = shadow
    if rig_ is not None:
        rig_.practicals.append(ob)
    return ob


def eye_light(cam, subject, power: float = 8.0):
    """Tiny camera-mounted catchlight so eyes look alive in medium and close shots. Scaled for the distance at frame 1."""
    d = max(0.5, (core.point_of(cam) - core.point_of(subject)).length)
    s = d / 1.65
    ob = _light("eye_light", "AREA", "#FFF7EA", power * s * s, (0, 0, 0), None, 0.18 * s, soft=False)
    ob.data.use_shadow = False
    ob.data.diffuse_factor = 0.35             # a glint, not a second key
    ob.parent = cam
    ob.location = (0.30 * s, 0.38 * s, 0.10 * s)
    ob.rotation_euler = (0, 0, 0)
    return ob


def change(light, t0: float, t1: float, power: float | None = None, color=None):
    """Animate a light between t0 and t1 (seconds): lights going out, a door opening, dawn arriving.
    A light change needs a story reason; say it in the shot plan."""
    ld = light.data
    if power is not None:
        core.key(ld, "energy", t0)
        core.key(ld, "energy", t1, power)
    if color is not None:
        core.key(ld, "color", t0)
        core.key(ld, "color", t1, core.hex_rgba(color)[:3])
    return light


def switch(light, t: float, on: bool, power: float | None = None):
    """Hard on/off at time t (a switch, a blackout). Uses a 2-frame ramp so it never strobes."""
    target = (power if power is not None else light.data.energy) if on else 0.0
    if on and power is None and light.data.energy == 0.0:
        target = float(light.get("on_power", 40.0))
    if not on:
        light["on_power"] = light.data.energy
    change(light, max(0.0, t - 2.0 / core.current().fps), t, power=target)
    return light


def flash(name: str, at, colors=("#FF2B2B", "#2B5BFF"), power: float = 400.0, t0: float = 0.0, t1: float | None = None, period: float = 0.9,
          radius: float = 0.3):
    """Alternating emergency lights (police, ambulance) between t0 and t1. Returns the two lights."""
    shot = core.current()
    t1 = shot.seconds if t1 is None else t1
    out = []
    for i, c in enumerate(colors):
        ob = _light(f"{name}_{i}", "POINT", c, 0.0, Vector(at) + Vector((0.25 * (i * 2 - 1), 0, 0)), None, radius)
        t = t0
        k = 0
        while t <= t1:
            on = (k % len(colors)) == i
            core.key(ob.data, "energy", t, power if on else power * 0.04)
            t += period / len(colors)
            k += 1
        if t0 > 0:
            core.key(ob.data, "energy", max(0.0, t0 - 0.05), 0.0)
        out.append(ob)
    return out


def haze(density: float = 0.015, color="#8FA3D6", anisotropy: float = 0.4):
    """Thin atmosphere so light beams and depth layers show (night exteriors, dusty rooms). Keep it subtle: 0.005-0.03.
    Costs render time; leave it out of shots that do not need it."""
    w = bpy.context.scene.world or set_world()
    nt = w.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    vol = nt.nodes.get("Haze") or nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.name = "Haze"
    vol.inputs["Color"].default_value = core.hex_rgba(color)
    vol.inputs["Density"].default_value = density
    vol.inputs["Anisotropy"].default_value = anisotropy
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    sc = bpy.context.scene
    sc.eevee.volumetric_start = 0.1
    sc.eevee.volumetric_end = 60.0
    return vol
