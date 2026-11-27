"""entrance - the front of the NORTHLINE building on a wet city street ("Two Seconds at the Office Door": sh01, sh02, sh07).

Adapted from examples/sets/set_office_entrance.py for this clip:

    marks first       MARK = the plan's six marks: in front of the doors (door_out), inside them (door_in), where the stranger runs up from (approach),
                      the kerb, where Maya stands with her box on Friday (box_spot) and the guard at her side (guard)
    then the place    dress.exterior(AREA, "office_entrance"): the lit lobby behind the glass front and the badge-locked double doors, the canopy, the
                      card reader post right of the doors, nine storeys of curtain wall with the NORTHLINE sign, totem, planters, benches, bollards,
                      bike rack, lamps, bus stop, parked cars, neighbouring fronts, the row across the road, a glass tower and the skyline
    then the light    dusk (Friday, sh01/sh07): an OVERCAST dusk - a slate-blue cloud sky that is lighter at the horizon, a weak cool skylight,
                      the warm lobby and lit windows glowing against it, street lamps on, a cool haze down the street; the ground is just wet.
                      rain_day (Monday, sh02): the worked file's grey rain - rain, splashes, rain on the glass, drips off the canopy edge.
    the story's gear  returned in the dict: the doors (furnish.swing_door), the card reader post and its lamp (furnish.lamp_state), the glass
                      front, the canopy

Camera side is -Y (the street). WIDE is the plan's front wide from the far side of the road, low, the doors and the reader in the middle third.
HIGH is the plan's high crane position over the near parking lane in front of the canopy (sh02 rain_morning starts there, sh07 career_gone
ends there): it is checked clear of geometry and void.
"""
import math

from mathutils import Vector

from stagekit import arch, core, dress, furnish, fx, lights

THEME = "office_entrance"
AREA = dict(lo=(-17.0, -17.0), hi=(17.0, 0.8))
MARK = {
    "door_out": (0.0, -1.55, 0.0),         # on the pavement in front of the doors
    "door_in": (0.0, 1.6, 0.0),            # just inside, in the lobby
    "approach": (-9.0, -3.6, 0.0),         # where the stranger runs up from along the pavement
    "kerb": (2.2, -5.35, 0.0),             # at the edge of the kerb
    "box_spot": (-0.6, -3.3, 0.0),         # Maya, escorted out, holding her box
    "guard": (0.9, -2.3, 0.0),             # the guard at her side
}
# the front wide: from the far pavement behind a parked car (its roof is the foreground), three-quarter on the doors, the street running off right
WIDE = ((-6.8, -15.3, 2.2), (4.5, -2.5, 4.3), 17.0)
# the high crane (sh02 starts here and cranes down; sh07 cranes up to here): over the near parking lane, in front of the canopy, clear of lamps and trees
HIGH = ((0.4, -10.8, 7.2), (0.0, -1.8, 1.6), 20.0)
LIGHT = {"dusk": dict(sky=("#262C3A", "#6E7584"), ambient=0.62), "rain_day": {}, "day_clear": {}, "office_day": {}}


def _overcast_dusk(rig):
    """Replace the kit's dusk sky (a clear orange-magenta horizon) with an overcast one: slate-blue cloud, a paler band at the horizon, a cool
    diffuse skylight, the sun only a weak soft glow behind the cloud. The warm windows and lamps then read warm against cool air."""
    zen, hor = LIGHT["dusk"]["sky"]
    to_sun = Vector((math.sin(math.radians(-60)) * math.cos(math.radians(8)), -math.cos(math.radians(-60)) * math.cos(math.radians(8)), math.sin(math.radians(8))))
    lights._sky(zen, hor, to_sun, "#8E9AB2", LIGHT["dusk"]["ambient"], 0.95)
    if rig.sun is not None:
        rig.sun.data.energy = 0.45
        rig.sun.data.color = core.hex_rgba("#AEBBD6")[:3]
        rig.sun.data.angle = math.radians(30.0)


def build_set(time: str = "rain_day"):
    t = {"office_day": "day_clear"}.get(time, time)
    rain = t == "rain_day"
    night = t == "dusk"
    if rain:
        lights.rig("rain_day", sun_from=-35, sun_elevation=58, look=False, rim=0.0)
    elif night:
        rig = lights.rig("dusk", sun_from=-60, sun_elevation=8, look=False, rim=0.0, ambient=0.6)
        _overcast_dusk(rig)
    else:
        lights.rig("day_clear", sun_from=-45, sun_elevation=40, look=False, rim=0.0)
    inv = dress.exterior(AREA, "office_entrance", marks=MARK, density=1.0, seed=11, keep_clear=0.7, night=night, wet=rain)
    refs = inv.get("refs", {})
    # the far-lane car parked opposite the doors moves 3 m west: a camera on the far pavement right of the doors (the cross angle, the reverse of
    # the guard's look out) then sees across the road instead of into its roof
    import bpy
    for ob in bpy.data.objects:
        if ob.get("sk_type") == "car" and abs(ob.location.x - 3.5) < 0.3 and abs(ob.location.y + 13.2) < 0.4:
            ob.location.x = 0.6
    # the city beyond: two tall towers down the street to the east rise over the neighbours' roofs on the right of the wide (in rain too)
    for k, (x, y, n, sty) in enumerate(((36.0, 16.0, 18, "glass"), (52.0, 30.0, 22, "panel"))):
        tw = arch.office_front(width=18.0, storeys=n, storey_h=3.6, style=sty, base=0.0, depth=14.0, at=(x, y, 0.0), rot_z=-20.0, seed=31 + k,
                               lit=0.75 if night else 0.3, night=night, name=f"far_tower_{k}")
        tw["sk_layer"] = "beyond"
    if rain:
        fx.rain(dict(lo=(-30.0, -24.0), hi=(30.0, -0.3)), intensity=1.5, wind=(0.14, 0.0), ground=0.0, near=(0.0, -5.0, 9.0),
                exclude=[(-3.55, -2.9, 3.55, -0.25, 3.3), (-14.7, -5.3, -10.5, -2.1, 2.7)], height=14.0)
        fx.window_rain(refs["front"], density=1.0)
        fx.drips_edge((-3.4, -2.86, 3.28), (3.4, -2.86, 3.28), n=22, fall=3.25)
        fx.rain_splashes((-12.0, -14.0, 12.0, -5.8), count=190, ground=-0.14, seed=21)
    if night:
        # just-wet Friday: a few dark puddles on the forecourt catch the lobby glow; a cool haze hangs down the street
        lights.ambient_fill((0.0, -9.5, 7.0), (34.0, 12.0), power=520.0, color="#9DB0D4", name="FILL_street")     # cool sky bounce on the street
        lights.ambient_fill((0.0, -2.6, 3.1), (7.0, 2.4), power=60.0, color="#FFD9A8", name="FILL_canopy")       # the lobby's spill under the canopy
        lights.rim_light(MARK["box_spot"], from_deg=165, elevation=24, distance=4.0, power=180.0, color="#FFCF96", name="RIM_box")   # warm lobby rim
    elif rain:
        lights.rim_light(MARK["door_out"], from_deg=160, elevation=26, distance=4.0, power=140.0, color="#FFE4C0", name="RIM_door")
    lights.limit_shadows()
    reader = refs.get("reader")
    reader_lamp = furnish.part(reader, "lamp") if reader is not None else None
    return {"mark": MARK, "inventory": inv, "time": t, "wide": WIDE, "high": HIGH, "exterior": True, "refs": refs, "doors": refs.get("doors"),
            "front": refs.get("front"), "reader_post": reader, "reader_lamp": reader_lamp, "canopy": refs.get("canopy")}
