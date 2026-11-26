"""The army camp: two columns of tents receding down a lit central lane to a command pavilion, a palisade and watchtowers, a horse line, smoke from other camps.

A worked example of the set-file contract for a large outdoor set:

    marks first       MARK = a sentry by the fire, a messenger on the lane, a knight at the weapon rack, a cook at the cauldron
    then the place    dress.exterior(area, "army_camp"): trodden ground with relief beyond the stage, tents in receding rows, fires with log seats
                      and rising smoke, a red pavilion under banners at the far end, a palisade and two timber watchtowers behind it, a forest
                      line, ridges all round and columns of smoke from far camps
    then the light    morning: a low gold sun and mist; dusk: a deep orange sky, the fires and torches carry the camp
    then the dressing weapon racks, shields, spears, arrows, carts, barrels, crates, sacks, hay and wood, a hitching rail with two horses,
                      banner poles, standing torches, stakes, straw, mud, stones, puddles and grass

Camera side is -Y. WIDE is from the south-west corner low over the first fire, down the lane to the pavilion. Times: "camp_morning", "camp_dusk".
"""
from stagekit import arch, core, dress, lights

AREA = dict(lo=(-14.0, -6.0), hi=(14.0, 10.0))
MARK = {
    "sentry": (-1.0, -1.2, 0.0),
    "messenger": (1.2, 4.6, 0.0),
    "knight": (-7.6, 1.4, 0.0),
    "cook": (5.4, 3.2, 0.0),
}
WIDE = ((-5.6, -5.4, 1.9), (1.2, 12.0, 1.6), 14.0)
LIGHT = {"camp_morning": {}, "camp_dusk": {}}


def build_set(time: str = "camp_morning"):
    night = time == "camp_dusk"
    if night:
        lights.rig("dusk", sun_from=-80, sun_elevation=10, look=False, rim=0.0, ambient=1.2)
    else:
        lights.rig("golden_hour", sun_from=-50, sun_elevation=16, look=False, rim=0.0)
    inv = dress.exterior(AREA, "army_camp", marks=MARK, density=1.2, seed=7, keep_clear=0.8, night=night)
    lights.limit_shadows(0)
    return {"mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "exterior": True}
