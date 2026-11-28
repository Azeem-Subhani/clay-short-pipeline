"""stagekit.lights - one light rig per place and time of day: a sky, a sun or moon, the room's own fixtures and windows.

    R = lights.rig("day_clear", sun_from=40)        # an exterior, in the set file, once
    lights.interior("office_day", room=R)           # an enclosed room: low world, white balance, cool window light, sources declared
    lights.practicals(scale=0.6)                    # every fixture in the scene dimmer, light and glowing surface together
    lights.practical("lantern", at=(1, 2, 2.1))     # visible warm sources add depth

The room owns its fixtures, the view owns its key. A set lights the PLACE: practical fixtures at the mood's practical
temperature, weak cool window light, a low world, and it declares where motivated light comes from (viewlight.source; window_key,
window_sun, the exterior sun and the strong practicals do that for you). The character key, fill and edge light are placed per
view by stagekit.viewlight after the cast and the cameras exist; a set no longer types a character key and a shot no longer
rescales lights by hand.

Every mood (time of day) has a colour identity (MOODS[m]["look"], lights.mood_look(m)): the camera white balance, the key,
fill and practical temperatures, the window light. Warmth is the house default (a warm key and warm practicals against cooler
daylight and fill, with a camera white balance so whites stay white); night and rain keep their mood with warm practical pools
against cooler ambient light.

Shadows are on by default at core.shadow_res() (fine at final), and limit_shadows() fits them into the shadow pool by a budget.
"""
from __future__ import annotations

import json
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
    # rain_day: a low grey overcast. Cool, very soft key from high up, almost no cast shadow, low contrast; windows and doors that are lit from
    # inside (warm practicals) read warm against it. Keep `tools/plan.py` MOODS in step with this table.
    "rain_day": {"sky": ("#7C8A98", "#B5BEC6"), "sun": ("#D6E2F0", 1.5, 58, 26), "ambient": 1.05, "clouds": 1.0, "cast": ("#E4EAF2", 0.18, 0.9)},
    "storm": {"sky": ("#3B4654", "#7C8894"), "sun": ("#D5DEE8", 1.4, 50, 20), "ambient": 0.9, "clouds": 1.0, "cast": ("#DDE3EA", 0.2, 0.82)},
    # interiors and underground: no sun through the roof; the key is a window or lamp you place with key_from / practicals
    "interior_day": {"sky": ("#BFD4E8", "#E8EEF2"), "sun": ("#FFF0D8", 3.0, 35, 6), "ambient": 0.35, "clouds": 0.0, "cast": ("#FFF3E2", 0.26, 0.9)},
    "interior_warm": {"sky": ("#1A1410", "#2A1E16"), "sun": ("#FFC48A", 0.0, 40, 6), "ambient": 0.5, "clouds": 0.0, "cast": ("#FFD9B0", 0.3, 0.84)},
    "candlelit": {"sky": ("#0E0A08", "#1B130E"), "sun": ("#FFC48A", 0.0, 40, 6), "ambient": 0.45, "clouds": 0.0, "cast": ("#FFD0A0", 0.32, 0.82)},
    "office_day": {"sky": ("#C7D6E4", "#EEF1F2"), "sun": ("#FFF4E4", 0.0, 40, 6), "ambient": 0.7, "clouds": 0.0, "cast": ("#FFF8EE", 0.2, 0.94)},
    "office_night": {"sky": ("#0B1226", "#1E2A4A"), "sun": ("#B8C6FF", 0.0, 40, 6), "ambient": 0.22, "clouds": 0.0, "cast": ("#DCE4FF", 0.22, 0.84)},
    "cave": {"sky": ("#0C0A09", "#17120E"), "sun": ("#FFC48A", 0.0, 40, 6), "ambient": 0.6, "clouds": 0.0, "cast": ("#FFD3A6", 0.32, 0.8)},
}

# The colour identity of each time of day, as a lighting cameraman would set it. Kelvin throughout.
#   wb          the camera's white balance: light of this temperature renders white (6500 = off; lower cools the picture)
#   key         the temperature a character key has in this mood (stagekit.viewlight places the key)
#   fill        the fill on the shadow side; fill_low = the low soft fill from the camera side
#   practical   lamps, ceiling panels, downlights (the fixtures in furnish take it unless they name their own)
#   window      the sky light through a window; window_w_m2 = its power per square metre of opening (window_key mode="sky")
#   world       the world strength an enclosed room uses (lights.interior): low, so the fixtures and windows shape the room
# Calibration: office_day is the approved training room (docs/LOOK_AUDIT_PHASE1.md section 10; look_phase3/ROUND2.md):
# white balance 5000, key 4300, cool fill 6500, low front fill 4800, practicals 3400, window 5800 at about 27 W a window, world 0.12.
# The rule for the others: the key sits 600-1000 K under the white balance (skin reads warm, paper stays near white); fill and
# window sit above it (cool counterweight); practicals sit well under it (warm pools). Golden hour, sunset and the fire-lit moods
# lean warmer on purpose; night and rain keep cool ambient light with warm practicals, and the key stays close enough to the
# white balance that faces read as skin, not orange.
_MOOD_LOOK = {
    #                 wb    key   fill  fill_low practical window window_w_m2 world
    "day_clear":     (5600, 5000, 7500, 5400, 3300, 6500, 10.0, 0.15),
    "day_soft":      (5800, 5200, 7000, 5500, 3300, 6800, 9.0, 0.15),
    "morning":       (5200, 4300, 7200, 4900, 3200, 5600, 8.0, 0.13),
    "golden_hour":   (5200, 3400, 7500, 4500, 3000, 4200, 8.0, 0.12),
    "sunset":        (5000, 3100, 8000, 4300, 2900, 3800, 6.0, 0.10),
    "dusk":          (4900, 3800, 8500, 4400, 3000, 8000, 2.5, 0.07),
    "night_moon":    (5000, 3900, 8000, 4500, 3000, 8500, 1.2, 0.05),
    "rain_day":      (5700, 4700, 7500, 5200, 3200, 7000, 6.0, 0.12),
    "storm":         (5800, 4900, 8000, 5400, 3100, 7500, 4.0, 0.10),
    "interior_day":  (4900, 4100, 6200, 4600, 3000, 5800, 8.0, 0.12),
    "interior_warm": (4000, 3300, 5800, 3900, 2800, 7500, 1.5, 0.07),
    "candlelit":     (3400, 2700, 5200, 3200, 2100, 7500, 0.8, 0.05),
    "office_day":    (5000, 4300, 6500, 4800, 3400, 5800, 8.2, 0.12),
    "office_night":  (4900, 3900, 7000, 4400, 3300, 8000, 1.5, 0.05),
    "cave":          (3600, 2900, 5600, 3300, 2300, 7000, 0.5, 0.06),
}
for _m, _v in _MOOD_LOOK.items():
    MOODS[_m]["look"] = dict(zip(("wb", "key", "fill", "fill_low", "practical", "window", "window_w_m2", "world"), _v))

PANEL_W_M2 = 11.1          # a ceiling panel's light per m2 of panel: 8 W for a 1.2 x 0.6 m panel, the approved room
PANEL_SPREAD = 55.0        # degrees; a narrower spread keeps the panel's light on the floor below it, not on the walls and faces
DOWNLIGHT_W = 3.0          # a recessed downlight
SCREEN_K = 7000.0          # the light a monitor or wall screen throws: cool white, never a saturated blue
SOURCE_MIN_W = 15.0        # a practical this strong (or a screen) is declared as a motivated source for the per-view key
MAX_CASTERS = 24           # local shadow casters at most: 25 at 2 mm fitted the 2048 MB pool (look_phase2/PART_A.md); render time grows with each


def mood_look(mood: str) -> dict:
    """The colour identity of a time of day: {"wb", "key", "fill", "fill_low", "practical", "window", "window_w_m2", "world"} (Kelvin,
    W per m2, world strength), plus "mood". For the per-view step (stagekit.viewlight), the checks and the docs."""
    if mood not in MOODS:
        raise KeyError(f"unknown mood {mood!r}: use one of {', '.join(MOODS)}")
    return {"mood": mood, **MOODS[mood]["look"]}


def current_mood() -> str | None:
    """The mood of the last rig() built in this scene (None before any)."""
    m = bpy.context.scene.get("sk_mood")
    return m if m in MOODS else None


def practical_kelvin() -> float:
    """The temperature a fixture takes when it names none: the current mood's, else style look.practical.kelvin."""
    m = current_mood()
    return float(MOODS[m]["look"]["practical"]) if m else float(core.look("practical.kelvin", 3400))


_BB: dict = {}


def kelvin_rgb(kelvin: float):
    """Blender's own blackbody colour for a temperature (luminance 1: 3400 K is about (1.60, 0.88, 0.38)), the colour a light gets
    with use_temperature. Used for the glowing surface of a fixture so it matches its light."""
    k = round(float(kelvin))
    if k not in _BB:
        d = bpy.data.lights.new("_sk_bb", "POINT")
        d.use_temperature, d.temperature = True, float(k)
        _BB[k] = tuple(d.temperature_color)
        bpy.data.lights.remove(d)
    return _BB[k]


def _set_kelvin(ld, kelvin: float):
    ld.use_temperature = True
    ld.temperature = float(kelvin)
    ld.color = (1.0, 1.0, 1.0)


def _hex_kelvin(color) -> float | None:
    """A rough colour temperature of an sRGB hex or linear tuple (McCamy); None for a saturated colour that has none."""
    try:
        r, g, b = core.hex_rgba(color)[:3]
    except Exception:
        return None
    X, Y, Z = 0.4124 * r + 0.3576 * g + 0.1805 * b, 0.2126 * r + 0.7152 * g + 0.0722 * b, 0.0193 * r + 0.1192 * g + 0.9505 * b
    s = X + Y + Z
    if s <= 0:
        return None
    x, y = X / s, Y / s
    n = (x - 0.3320) / (0.1858 - y) if abs(0.1858 - y) > 1e-6 else 0.0
    k = 449 * n ** 3 + 3525 * n ** 2 + 6823.3 * n + 5520.33
    return round(k) if 1500 <= k <= 20000 else None


def _light_kelvin(ld) -> float | None:
    return float(ld.temperature) if getattr(ld, "use_temperature", False) else _hex_kelvin(tuple(ld.color))


def _cast(ld, scale: float = 1.0):
    """Shadows on, at the resolution of the quality being built (core.shadow_res, metres per texel, times `scale` for a big or
    soft light), with jitter when style look.shadow.jitter (soft, correct penumbras; the pool budget is in limit_shadows)."""
    ld.use_shadow = True
    ld.shadow_maximum_resolution = core.shadow_res(scale)
    ld.use_shadow_jitter = bool(core.look("shadow.jitter", True))


def _declare(kind: str, at, toward=None, kelvin=None, name=None, strength: float = 1.0):
    """Declare a motivated source for the per-view key (stagekit.viewlight). strength: 1.0 = one window of the approved room
    (about 27 W of sky light); a practical's is its watts / 27."""
    from . import viewlight                                   # imported here: viewlight may import lights
    return viewlight.source(kind, tuple(at), tuple(toward) if toward is not None else None, kelvin, name, round(float(strength), 3))


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


SUN_RES_SCALE = 8.0         # a sun's shadow texel is this many times a key's (3.2 cm at final): a sun covers the whole set
WINDOW_SUN_RES_SCALE = 4.0  # a sun that reaches the room only through its windows: finer patches, smaller area


def rig(mood: str = "day_clear", sun_from: float = 40.0, sun_elevation: float | None = None, strength: float = 1.0, ambient: float | None = None,
        rim: float | None = None, clouds: float | None = None, look: bool = True, white_balance: bool = True) -> Rig:
    """Build the light for a set. sun_from: where the light comes from, in degrees around the stage measured from the
    camera side (-Y): 0 = from behind the camera, 40 = from behind-right, -60 = from behind-left, 150 = backlight from
    far right. rim is a weak shadowless back light that separates the cast from the set (default 0.55; 0 = off). Returns Rig(sun, world).
    It also sets the mood's camera white balance (core.set_white_balance; white_balance=False leaves the view alone), gives every
    fixture that names no temperature the mood's practical temperature (light and glowing surface), and declares the sun as a
    "sky" source for the per-view key. An exterior author types:

        lights.rig("rain_day", sun_from=-35, rim=0.0, look=False)       # sky, sun, white balance; dress.exterior adds the lamps
    For an enclosed room use lights.interior(...)."""
    if mood not in MOODS:
        raise KeyError(f"unknown mood {mood!r}: use one of {', '.join(MOODS)}")
    m = MOODS[mood]
    bpy.context.scene["sk_mood"] = mood
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
        _cast(ld, SUN_RES_SCALE)
        _coarse_shadow(ld, ld.shadow_maximum_resolution)
        sun = bpy.data.objects.new("SUN", ld)
        core.link(sun, "LIGHTS")
        sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
        sun["sk_role"] = "sun"
        _declare("sky", to_sun * 100.0, -to_sun, _hex_kelvin(col), "SUN", power * strength / 3.0)
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
    if white_balance:
        core.set_white_balance(m["look"]["wb"])
    _retemp_auto(m["look"]["practical"])
    bpy.context.scene["light_rig"] = f"{mood} sun_from={sun_from} elev={elev}"
    return Rig(mood, sun, world, rim_ob)


def _pool_res(fine: float) -> float:
    """Kept for old callers: the finest resolution the pool of the quality in use allows a big light. Shadow resolution now comes
    from core.shadow_res(), and limit_shadows() fits the casters into the pool."""
    mb = int(bpy.context.scene.eevee.shadow_pool_size)
    return fine * (1.0 if mb >= 512 else 3.0 if mb >= 256 else 6.0)


def _coarse_shadow(ld, res: float):
    """A light's shadow resolution limit (metres per texel); for a sun also its cascade reach."""
    ld.shadow_maximum_resolution = res
    if ld.type == "SUN":
        ld.shadow_cascade_max_distance = 90.0
        ld.shadow_cascade_count = 3


def _retemp_auto(kelvin: float):
    """Fixtures that named no temperature take the mood's practical temperature: their lights and their glowing surfaces."""
    for o in bpy.data.objects:
        if o.type == "LIGHT" and o.get("sk_auto_k"):
            _set_kelvin(o.data, kelvin)
            o["sk_kelvin"] = float(kelvin)
    for m in bpy.data.materials:
        if m.get("sk_fixture") and m.get("sk_auto_k"):
            _fixture_mat_set(m, kelvin=kelvin)


def practical(name: str, at, color="#FFC477", power: float = 60.0, radius: float = 0.1, kind: str = "POINT", aim=None, size: float | None = None,
              shadow: bool = True, kelvin: float | None = None, spread: float | None = None):
    """A visible source: lantern, candle, fire, lit window (pair it with something that glows: mat.emit). power in watts.
    Returns the light OBJECT (tagged sk_role=practical) so recipes and the set audit can count it.
    A FIXTURE (a modern lamp, panel or downlight) is a practical whose colour is a temperature: color=None (the mood's practical
    temperature, or style look.practical.kelvin before any rig; it follows a rig built later), a number (Kelvin), or kelvin=.
    Fixtures answer to lights.practicals() / lights.fixture(), which dim or recolour the light and its glowing surface together.
    A hex colour is a period or coloured source (fire, candle, an EXIT sign) and keeps its colour. spread: degrees, area lights only
    (a fixture's area light defaults to PANEL_SPREAD).
    Shadows (shadow=True) are cast at core.shadow_res(); limit_shadows() keeps the pool from overflowing."""
    fixture = color is None or isinstance(color, (int, float)) or kelvin is not None
    ld = bpy.data.lights.new(name, kind)
    ld.energy = power
    if kind == "AREA":
        ld.size = size or 1.0
        if spread is None and fixture:
            spread = PANEL_SPREAD                              # a fixture's area light lights the floor under it, not the walls and faces
        if spread is not None:
            ld.spread = math.radians(spread)
    else:
        ld.shadow_soft_size = radius
        if kind == "SPOT":
            ld.spot_size = math.radians(size or 60)
            ld.spot_blend = 0.4
    if shadow:
        _cast(ld, 2.0 if kind == "POINT" else 1.0)              # a point light fills a cube of shadow maps: half the resolution
    else:
        ld.use_shadow = False
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, "LIGHTS")
    ob.location = at
    ob["sk_role"] = "practical"                              # the set audit counts these; fill, key and rim lights carry other roles
    ob["sk_base_energy"] = float(power)
    if fixture:
        k = float(kelvin if kelvin is not None else color if color is not None else practical_kelvin())
        _set_kelvin(ld, k)
        ob["sk_fixture"] = 1
        ob["sk_kelvin"] = k
        if color is None and kelvin is None:
            ob["sk_auto_k"] = 1
    else:
        ld.color = core.hex_rgba(color)[:3]
    low = name.lower()
    if "glow" in low or "screen" in low:
        ob["sk_source"] = "screen"
    elif power >= SOURCE_MIN_W:
        ob["sk_source"] = "practical"
    if aim is not None:
        d = core.point_of(aim) - Vector(at)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


# ----------------------------------------------------------------------------- fixtures: light and glowing surface together
def fixture_material(kind: str, kelvin: float | None = None, emission: float | None = None, base: str = "#EEEAE2"):
    """The glowing surface of a modern fixture (panel diffuser, downlight lens, lamp shade, bulb): an off-white diffuser that emits
    at the fixture's temperature. kelvin=None follows the mood (as the fixture's light does); emission defaults to style
    look.practical.panel_emission (2.0: a panel reads warm and lit, not a white slab). Shared by every fixture of the same kind and
    temperature; lights.fixture(piece, ...) gives one piece its own copy when it is changed alone."""
    auto = kelvin is None
    k = float(practical_kelvin() if auto else kelvin)
    em = float(core.look("practical.panel_emission", 2.0) if emission is None else emission)
    name = f"SK_emit_fixture_{kind}_{'auto' if auto else int(k)}_{em:g}"
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = core.hex_rgba(base)
    b.inputs["Roughness"].default_value = 0.6
    m["sk_fixture"] = 1
    m["sk_base_emission"] = em
    m["sk_scale"] = 1.0
    if auto:
        m["sk_auto_k"] = 1
    _fixture_mat_set(m, kelvin=k)
    return m


def _fixture_mat_set(m, kelvin: float | None = None, scale: float | None = None, emission: float | None = None):
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    if kelvin is not None:
        b.inputs["Emission Color"].default_value = (*kelvin_rgb(kelvin), 1.0)
        m["sk_kelvin"] = float(kelvin)
    if emission is not None:
        m["sk_base_emission"] = float(emission)
    if scale is not None:
        m["sk_scale"] = float(scale)
    b.inputs["Emission Strength"].default_value = float(m.get("sk_base_emission", 2.0)) * float(m.get("sk_scale", 1.0))


def _piece_of(ob):
    """The piece a light belongs to: the nearest ancestor that is a registered piece (sk_type), else the top ancestor, else itself."""
    p, top = ob.parent, ob
    while p is not None:
        if p.get("sk_type"):
            return p
        top, p = p, p.parent
    return top


def _fixture_groups():
    """[(piece, [practical lights], [fixture materials])] for every piece that carries a practical light."""
    groups: dict = {}
    for o in bpy.data.objects:
        if o.type == "LIGHT" and o.get("sk_role") == "practical":
            groups.setdefault(_piece_of(o).name, [_piece_of(o), [], []])[1].append(o)
    for root, lts, mats in groups.values():
        seen = set()
        for c in [root, *root.children_recursive]:
            if c.type == "MESH":
                for s in c.material_slots:
                    if s.material and s.material.get("sk_fixture") and s.material.name not in seen:
                        seen.add(s.material.name)
                        mats.append(s.material)
    return list(groups.values())


def _matches(root, lts, match) -> bool:
    if match is None:
        return True
    if callable(match):
        return bool(match(root))
    words = [match] if isinstance(match, str) else list(match)
    hay = [str(root.get("sk_type", "")), root.name] + [o.name for o in lts]
    return any(w in h for w in words for h in hay)


def _adjust(groups, scale, kelvin, emission, all_groups):
    """Apply a change to these fixture groups; a material shared with a group outside them is copied first."""
    chosen = {id(g[0]) for g in groups}
    shared_out = {m.name for g in all_groups if id(g[0]) not in chosen for m in g[2]}
    copies: dict = {}
    n_l = n_m = 0
    for root, lts, mats in groups:
        mine = []
        for m in mats:
            if m.name in shared_out and (kelvin is not None or scale is not None or emission is not None):
                if m.name not in copies:
                    copies[m.name] = m.copy()
                    copies[m.name].pop("sk_auto_k", None)        # a piece changed by hand no longer follows the mood
                cp = copies[m.name]
                for c in [root, *root.children_recursive]:
                    if c.type == "MESH":
                        for s in c.material_slots:
                            if s.material is m:
                                s.material = cp
                m = cp
            mine.append(m)
        for o in lts:
            if scale is not None:
                o.data.energy = float(o.get("sk_base_energy", o.data.energy)) * float(scale)
                o["sk_scale"] = float(scale)
            if kelvin is not None and o.get("sk_fixture"):
                _set_kelvin(o.data, kelvin)
                o["sk_kelvin"] = float(kelvin)
                o.pop("sk_auto_k", None)
            n_l += 1
        for m in mine:
            if kelvin is not None:
                m.pop("sk_auto_k", None)
            _fixture_mat_set(m, kelvin=kelvin, scale=scale, emission=emission)
            n_m += 1
    return {"pieces": len(groups), "lights": n_l, "surfaces": n_m}


def practicals(scale: float | None = None, kelvin: float | None = None, emission: float | None = None, match=None) -> dict:
    """Change every fixture in the scene together, light AND glowing surface, so nobody multiplies `energy` by hand:
        lights.practicals(scale=0.6)                  # the room a step dimmer (0 = every lamp off: dark lights, unlit diffusers)
        lights.practicals(kelvin=3000)                # warmer lamps (fixtures only: fire, candles and coloured signs keep their colour)
        lights.practicals(emission=1.2, match="ceiling_light_panel")    # the panels' surfaces only, by piece type or name
    scale is relative to each light's power when it was built (calling it twice does not compound). match: a piece type or name
    (or a list of them, or a function of the piece's root object). Returns {"pieces", "lights", "surfaces"} changed."""
    allg = _fixture_groups()
    return _adjust([g for g in allg if _matches(g[0], g[1], match)], scale, kelvin, emission, allg)


def fixture(piece, scale: float | None = None, kelvin: float | None = None, emission: float | None = None) -> dict:
    """The same as practicals() for one piece (the object furnish or dress returned, or one of its lights): its light and its
    glowing surface dim or recolour together; a surface it shared with other pieces is copied so they stay as they were."""
    allg = _fixture_groups()
    root = _piece_of(piece) if piece.type == "LIGHT" else piece
    return _adjust([g for g in allg if g[0] == root], scale, kelvin, emission, allg)


def declare_sources(min_power: float = SOURCE_MIN_W) -> int:
    """Declare the scene's strong practicals and screens as motivated sources (viewlight.source), once each, where they now are.
    dress.room and dress.exterior call it at the end; call it again after placing lamps by hand. Returns how many were declared."""
    n = 0
    bpy.context.view_layer.update()
    for o in bpy.data.objects:
        kind = o.get("sk_source")
        if o.type != "LIGHT" or not kind or o.get("sk_declared") or o.hide_render:
            continue
        if kind == "practical" and o.data.energy < min_power:
            continue
        mw = o.matrix_world
        toward = None if o.data.type == "POINT" else (mw.to_3x3() @ Vector((0, 0, -1))).normalized()
        _declare(kind, mw.translation, toward, _light_kelvin(o.data), o.name, o.data.energy / 27.0)
        o["sk_declared"] = 1
        n += 1
    return n


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


def window_key(opening, color=None, power: float | None = None, aim=None, pitch: float = 24.0, soft: float = 0.9, shaft: bool | None = None,
               reach: float = 7.0, shaft_strength: float = 0.05, name: str = "KEY_window", shadow: bool = True, mode: str = "key",
               kelvin: float | None = None):
    """Light through a window or door: a soft rectangular area light standing just outside the opening, shining in, tilted down
    by `pitch` degrees, casting real shadows of mullions, chairs and people. `opening` is an arch.window / arch.door handle (or a
    point with aim=). It is declared as a "window" source for the per-view key. Two modes:
      mode="sky"  the room's cool reference, the way the approved room has it: weak sky light at the mood's window temperature,
                  mood window_w_m2 watts per m2 of opening (about 27 W for a 2.1 x 1.6 m office window by day), shadows on, no
                  shaft. Use this when the per-view step gives the characters their key (lights.interior does).
      mode="key"  the old strong key: 900 W of #FFEBCB unless power / color say otherwise, with a shaft. Sets that ask for it keep it.
    shaft=True adds a visible fake light shaft (a faded glowing prism, no volume cost). Returns {"light", "shaft"}."""
    if mode not in ("key", "sky"):
        raise ValueError(f"window_key mode {mode!r}: use 'key' or 'sky'")
    if mode == "sky" and name == "KEY_window":
        name = "WIN_window"                                      # room light, not a character key (KEY_* names are keys to the per-view step)
    c, n, w, h = _opening_frame(opening, aim)
    flat = Vector((n.x, n.y, 0)).normalized()
    d = (flat * math.cos(math.radians(pitch)) + Vector((0, 0, -math.sin(math.radians(pitch))))).normalized()
    ml = MOODS[current_mood() or "office_day"]["look"]
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = max(0.3, w * soft), max(0.3, h * soft)
    if mode == "sky":
        ld.energy = float(power) if power is not None else ml["window_w_m2"] * w * h
        k = kelvin if kelvin is not None else (color if isinstance(color, (int, float)) else None)
        if k is None and color is not None:
            ld.color = core.hex_rgba(color)[:3]
            k = _hex_kelvin(color)
        else:
            k = float(ml["window"] if k is None else k)
            _set_kelvin(ld, k)
        shaft = False if shaft is None else shaft
        glow = color if isinstance(color, str) else "#E8EEF6"
    else:
        ld.energy = 900.0 if power is None else float(power)
        color = "#FFEBCB" if color is None else color
        if kelvin is not None or isinstance(color, (int, float)):
            k = float(kelvin if kelvin is not None else color)
            _set_kelvin(ld, k)
            glow = "#FFEBCB"
        else:
            ld.color = core.hex_rgba(color)[:3]
            k, glow = _hex_kelvin(color), color
        shaft = True if shaft is None else shaft
    if shadow:
        _cast(ld, 1.0)
    else:
        ld.use_shadow = False
    ld.spread = math.radians(100)
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, "LIGHTS")
    ob.location = c - d * 0.25
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    ob["sk_role"] = "key" if mode == "key" else "window"
    ob["sk_window_mode"] = mode
    _declare("window", c, d, k, name, ld.energy / 27.0)
    out = {"light": ob, "shaft": None}
    if shaft:
        out["shaft"] = light_shaft(c, d, w, h, reach, glow, shaft_strength, name=f"{name}.shaft")
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
    _cast(ld, WINDOW_SUN_RES_SCALE)
    _coarse_shadow(ld, ld.shadow_maximum_resolution)
    ob = bpy.data.objects.new(name, ld)
    core.link(ob, "LIGHTS")
    ob.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    ob["sk_role"] = "key"
    at = room_.wall_point(wall, 0.0, 1.5) if hasattr(room_, "wall_point") else Vector((0, 0, 1.5))
    _declare("window", at, -to_sun, _hex_kelvin(color), name, power * 3.0)
    return ob


# Shadow pool cost model, in pool tiles (EEVEE: 4 tiles per MB of shadow_pool_size). Measured on sh08 at final quality
# (output/experiments/look_phase4/lights/budget_measure.json): its 15 fixtures and 2 suns at 4 mm wanted under 1024 tiles; every light
# of the shot casting (29 local lights at 4 mm and 2 suns) wanted 2280-2365. The model below estimates about 1.8 times that, and only
# 70% of the pool is spent, so a view the set cannot know (a close shot under many lights) still fits. A light's cost grows as its
# texels get finer and is larger for a light that fills a cube of maps (point) than for a spot or an area light.
_TILE_COST = {"AREA": 120.0, "SPOT": 120.0, "POINT": 240.0, "SUN": 400.0}     # tiles at the reference resolution below
_TILE_REF_RES = 0.004
_TILE_EXP = 0.7               # cost ~ (ref / res) ** 0.7: from 2892 tiles at 5 mm to about 8770 at 1 mm for the same 25 lights
_POOL_SAFETY = 0.7            # use at most this share of the pool
_ROLE_RANK = {"key": 0, "sun": 0, "window": 1, None: 2, "practical": 3, "fill": 4, "rim": 4, "bounce": 4}


def _tile_cost(ob) -> float:
    d = ob.data
    res = max(1e-4, float(d.shadow_maximum_resolution))
    return _TILE_COST.get(d.type, 260.0) * (_TILE_REF_RES / res) ** _TILE_EXP


def _stage_centre() -> Vector:
    """Where the action is: the middle of the room shells (floor, walls) at head height, else of every mesh in the scene."""
    shells = [o for o in bpy.data.objects if o.type == "MESH" and o.get("sk_kind") == "shell" and not o.hide_render]
    obs = shells or [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render]
    if not obs:
        return Vector((0, 0, 1.2))
    lo, hi = core.world_bbox(obs)
    c = (Vector(lo) + Vector(hi)) / 2
    return Vector((c.x, c.y, 1.2))


def _importance(ob, centre: Vector) -> float:
    """How much a light puts on the stage: its power over the square of its distance to the stage centre."""
    dist = (ob.matrix_world.translation - centre).length
    return float(ob.data.energy) / (1.0 + dist * dist)


def shadow_budget(pool_mb: int | None = None) -> dict:
    """The pool budget without changing anything: {"pool_mb", "tiles", "budget", "casters": [(name, role, cost)], "estimate"}."""
    sc = bpy.context.scene
    mb = int(pool_mb or sc.eevee.shadow_pool_size)
    cast = [o for o in sc.objects if o.type == "LIGHT" and o.data.use_shadow and not o.hide_render and o.data.energy > 0]
    est = sum(_tile_cost(o) for o in cast)
    return {"pool_mb": mb, "tiles": mb * 4, "budget": round(mb * 4 * _POOL_SAFETY), "estimate": round(est),
            "casters": [(o.name, o.get("sk_role"), round(_tile_cost(o))) for o in cast]}


def limit_shadows(max_local: int | None = None, pool_mb: int | None = None, quiet: bool = False) -> int:
    """Fit the shadow casters into the shadow pool of the quality in use, so EEVEE never prints "Shadow buffer full" (an overflow
    drops shadow tiles and blows out patches of the picture). A budget, not a count: every casting light is first held to the
    resolution of the quality (core.shadow_res: a hand-made light at Blender's 1 mm default would ask for thousands of tiles), then
    the lights are ranked by what they do for the picture (keys and suns first, then window light, then lights made by hand, then
    practicals by the power they put on the stage) and keep their shadows while their estimated cost fits the pool (and at most
    MAX_CASTERS local casters, for render time). Only then are the weakest dropped. Fill, bounce and rim lights are shadowless by
    design. Call it once at the end of the set (dress.room and dress.exterior do), and again after adding lights to a shot.
    max_local is kept for old callers and no longer decides: the budget does. Prints and stores (scene["sk_shadow_budget"]) what
    it kept and dropped. Returns how many lights lost their shadow."""
    sc = bpy.context.scene
    mb = int(pool_mb or sc.eevee.shadow_pool_size)
    budget = mb * 4 * _POOL_SAFETY
    casters = [o for o in sc.objects if o.type == "LIGHT" and o.data.use_shadow and not o.hide_render]
    for o in casters:                                         # nothing finer than the quality allows
        scale = SUN_RES_SCALE if o.get("sk_role") == "sun" else (WINDOW_SUN_RES_SCALE if o.data.type == "SUN" else (2.0 if o.data.type == "POINT" else 1.0))
        floor = core.shadow_res(scale)
        if o.data.shadow_maximum_resolution < floor:
            o.data.shadow_maximum_resolution = floor
    live = [o for o in casters if o.data.energy > 0]
    suns = [o for o in live if o.data.type == "SUN"]
    local = [o for o in live if o.data.type != "SUN"]
    centre = _stage_centre()
    local.sort(key=lambda o: (_ROLE_RANK.get(o.get("sk_role"), 2), -_importance(o, centre)))
    used = sum(_tile_cost(o) for o in suns)
    kept, dropped = [o.name for o in suns], []
    n_local = 0
    for o in local:
        c = _tile_cost(o)
        must = _ROLE_RANK.get(o.get("sk_role"), 2) == 0
        if must or (used + c <= budget and n_local < MAX_CASTERS):
            used += c
            n_local += 1
            kept.append(o.name)
        else:
            o.data.use_shadow = False
            dropped.append(o.name)
    rep = {"pool_mb": mb, "budget_tiles": round(budget), "estimate_tiles": round(used), "kept": kept, "dropped": dropped,
           "asked_max_local": max_local}
    sc["sk_shadow_budget"] = json.dumps(rep)
    if not quiet:
        over = " OVER BUDGET (keys alone)" if used > budget else ""
        print(f"limit_shadows: pool {mb} MB = {mb * 4} tiles, budget {round(budget)}; kept {len(kept)} casters (~{round(used)} tiles){over}; "
              f"dropped {len(dropped)}" + (f": {', '.join(dropped[:12])}{' ...' if len(dropped) > 12 else ''}" if dropped else ""), flush=True)
    return len(dropped)


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
    from_deg round the stage like lights.rig's sun_from, so the figure gets a bright edge and lifts off the set.
    Kept for old sets. For characters the per-view step (stagekit.viewlight) replaces it: it puts the edge light where the real
    camera and the face are, which a mark and an angle from -Y cannot know."""
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
    """A big, soft, shadowless area light facing down: the bounce an enclosed room would get and EEVEE does not compute.
    Kept for old sets. For characters the per-view step (stagekit.viewlight) replaces it with a fill placed from the camera and
    the faces; a flood like this one flattens faces and washes out the shadows that ground the furniture."""
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


def interior(mood: str = "interior_day", key_from=None, aim=None, key_color=None, key_power: float | None = None, rim: float | None = None,
             shaft: bool | None = None, fill=None, room=None, windows: str | None = None, **kw):
    """Light for an enclosed place in one call, the approved way: the mood's world at a low level (mood_look(mood)["world"]
    unless ambient= is given), the mood's camera white balance, weak cool sky light through every window of `room` (an arch.room)
    or through key_from (window_key mode="sky", shadows on), the fixtures at their defaults in the mood's practical temperature,
    and every window declared as a source. No character key and no fill: the per-view step (stagekit.viewlight) places those.
    A set author types:

        R = arch.room(...)
        lights.interior("office_day", room=R)          # world, white balance, window light, sources
        dress.room(R, "training_room", marks=MARK)      # the fixtures (and their sources and the shadow budget)
        lights.practicals(scale=0.8)                    # only if the room should be dimmer: light and surface together

    The old strong window key is still there: pass key_color or key_power (or windows="key") and key_from gets
    window_key(mode="key") with a shaft, as before; fill= (a dict: at=, size=, power=) adds an ambient_fill; rim = the soft back
    sun of rig (default 0). Sets with no window (candlelit, office night) leave room and key_from out and light themselves with
    practicals. Returns {"rig", "key" (the first window's light), "windows" [window_key results], "fill"}."""
    legacy = windows == "key" or key_color is not None or key_power is not None
    if not legacy and "ambient" not in kw:
        kw["ambient"] = MOODS[mood]["look"]["world"] if mood in MOODS else None
    R = rig(mood, rim=0.0 if rim is None else rim, look=False, **kw)
    out = {"rig": R, "key": None, "windows": [], "fill": None}
    if legacy:
        if key_from is not None:
            out["key"] = window_key(key_from, key_color or "#FFEBCB", 900.0 if key_power is None else key_power, aim=aim,
                                    shaft=True if shaft is None else shaft)
            out["windows"].append(out["key"])
    else:
        ops = []
        if room is not None:
            ops += [(oid, hd) for oid, hd in getattr(room, "openings", {}).items() if hd.get("kind") == "window"]
        if key_from is not None:
            ops.append((None, key_from))
        for oid, hd in ops:
            out["windows"].append(window_key(hd, aim=aim, mode="sky", shaft=shaft, name=f"WIN_{oid}" if oid else "WIN_window"))
        out["key"] = out["windows"][0] if out["windows"] else None
    if fill:
        out["fill"] = ambient_fill(**fill)
    return out
