"""The front of the NORTHLINE office building on a city street: a glazed lobby behind a pair of glass doors, under a canopy, the street in front.

A worked example of a modern exterior with a lit interior behind glass, for the story "Two Seconds at the Office Door":

    marks first       MARK = in front of the doors (door_out), inside them (door_in), where someone runs up from (approach), the kerb, where Maya stands
                      with her box when she is escorted out (box_spot), and the guard's place
    then the place    dress.exterior(AREA, "office_entrance"): paving and a kerb, a road with parking lanes, a zebra crossing, and the front of the building:
                      the lobby (the same lobby as set_office_lobby, lit, seen through the glass: reception desk, speed gates, lifts, plants, logo), the glass
                      front and double doors, the canopy with drips, the card reader post, nine storeys of curtain wall rising out of frame with the NORTHLINE
                      sign on the first spandrel, a totem sign, planters, benches, bollards, a bike rack with two bikes, street lamps, a bus stop, parked cars,
                      neighbouring fronts left and right, a row across the road with a glass tower behind, tall blocks closing the street and a skyline
    then the light    rain_day: a cool grey overcast, rain on everything, wet pavement and road, warm light in the lobby; day_clear (also "office_day"): a
                      bright sun; dusk: lamps, lit windows, the sign glowing
    the story's gear  returned in the dict: the doors (furnish.swing_door), the card reader's lamp (furnish.lamp_state), the glass front, the canopy

Camera side is -Y. WIDE is from the far pavement across the road, low, looking at the doors. Times: "rain_day", "day_clear" ("office_day"), "dusk".
"""
import math

from stagekit import arch, core, dress, furnish, fx, lights

THEME = "office_entrance"
AREA = dict(lo=(-17.0, -17.0), hi=(17.0, 0.8))
MARK = {
    "door_out": (0.0, -1.55, 0.0),         # on the pavement in front of the doors
    "door_in": (0.0, 1.6, 0.0),            # just inside, in the lobby
    "approach": (-9.0, -3.6, 0.0),         # where someone runs up from along the pavement
    "kerb": (2.2, -5.35, 0.0),             # at the edge of the kerb
    "box_spot": (-0.6, -3.3, 0.0),         # Maya, escorted out, holding her box
    "guard": (0.9, -2.3, 0.0),             # the guard at her side
}
WIDE = ((-10.5, -10.2, 3.0), (3.2, -0.5, 2.5), 17.0)
LIGHT = {"rain_day": {}, "day_clear": {}, "office_day": {}, "dusk": {}}


def build_set(time: str = "rain_day"):
    t = {"office_day": "day_clear"}.get(time, time)
    rain = t == "rain_day"
    night = t == "dusk"
    if rain:
        lights.rig("rain_day", sun_from=-35, sun_elevation=58, look=False, rim=0.0)
    elif night:
        lights.rig("dusk", sun_from=-60, sun_elevation=12, look=False, rim=0.0, ambient=0.5)
    else:
        lights.rig("day_clear", sun_from=-45, sun_elevation=40, look=False, rim=0.0)
    inv = dress.exterior(AREA, "office_entrance", marks=MARK, density=1.0, seed=11, keep_clear=0.7, night=night, wet=rain)
    refs = inv.get("refs", {})
    if rain:
        fx.rain(dict(lo=(-30.0, -24.0), hi=(30.0, -0.3)), intensity=1.5, wind=(0.14, 0.0), ground=0.0, near=(0.0, -5.0, 9.0),
                exclude=[(-3.55, -2.9, 3.55, -0.25, 3.3), (-14.7, -5.3, -10.5, -2.1, 2.7)], height=14.0)
        fx.window_rain(refs["front"], density=1.0)
        fx.drips_edge((-3.4, -2.86, 3.28), (3.4, -2.86, 3.28), n=22, fall=3.25)
        fx.rain_splashes((-12.0, -14.0, 12.0, -5.8), count=190, ground=-0.14, seed=21)
    reader = refs.get("reader")
    reader_lamp = furnish.part(reader, "lamp") if reader is not None else None
    return {"mark": MARK, "inventory": inv, "time": t, "wide": WIDE, "exterior": True, "refs": refs, "doors": refs.get("doors"), "front": refs.get("front"),
            "reader_post": reader, "reader_lamp": reader_lamp, "canopy": refs.get("canopy")}
