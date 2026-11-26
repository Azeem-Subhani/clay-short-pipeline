"""The village square: a green and cobbled square 26 x 16 m ringed by houses, a church in a gap on the north side, a fountain in the middle.

A worked example of the set-file contract for an open place built with the kit (stagekit.arch / furnish / dress / lights):

    marks first       MARK = two villagers talking on the cobbles, a merchant at his stall, a child by the fountain
    then the place    dress.exterior(area, "village_square"): the paved square with a fountain and benches, rows of houses of varied style and
                      height on all four sides (so every direction is a place: church and trees to the north, lanes east and west, a low row
                      and a road to the south), lit windows at night, chimneys with smoke, hills and a far town beyond, mist on the grass
    then the light    day: a bright morning sun from behind-right; night: a moon, lit windows, gas lamps and torches
    then the dressing market stalls with goods, carts, hay, barrels and crates, a pump, a signpost, a washing line, fences, trees and bushes,
                      grass, flowers, stones, puddles, straw and leaves on the ground

Camera side is -Y. WIDE is from the south-west of the square, looking up to the fountain, the stalls and the church tower. Times: "village_day",
"village_night".
"""
from stagekit import arch, core, dress, lights

AREA = dict(lo=(-13.0, -9.0), hi=(13.0, 7.0))
MARK = {
    "villager_a": (-4.5, -3.0, 0.0),
    "villager_b": (-3.2, -2.4, 0.0),
    "merchant": (4.6, 2.6, 0.0),
    "child": (0.5, -4.2, 0.0),
}
WIDE = ((-9.0, -8.3, 2.0), (1.0, 3.4, 3.0), 14.0)
LIGHT = {"village_day": {}, "village_night": {}}


def build_set(time: str = "village_day"):
    night = time == "village_night"
    if night:
        lights.rig("night_moon", sun_from=-55, sun_elevation=48, look=False, rim=0.0, ambient=0.9)
    else:
        lights.rig("day_clear", sun_from=45, look=False, rim=0.0)
    inv = dress.exterior(AREA, "village_square", marks=MARK, density=1.3, seed=11, keep_clear=0.8, night=night)
    lights.limit_shadows(0)
    return {"mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "exterior": True}
