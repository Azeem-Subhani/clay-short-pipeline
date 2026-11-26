"""The market street: a cobbled street 7 m wide between two rows of shops and houses, stalls on the pavements, bunting across, a church at one end.

A worked example of the set-file contract for a built-up outdoor set:

    marks first       MARK = a stallholder, a customer, two people talking mid-street, someone by the well
    then the place    dress.exterior(area, "market_street"): street and pavements, timber, stone and brick shopfronts (awnings, hanging signs,
                      flower boxes, chimneys with smoke) 92 m long on both sides, a church tower closing one end and a gate the other,
                      ridges and a far town beyond, mist low on the cobbles
    then the light    day: a late-morning sun; dusk: the sky going orange, windows lit, gas lamps on
    then the dressing five stalls with goods, carts, a hitching rail and a horse, a well, barrels, crates and sacks, lamp posts, bunting,
                      a signpost, a bench, puddles, straw and litter on the cobbles

Camera side is -Y. WIDE is from the south-west end of the street, low, looking along it to the church. Times: "market_day", "market_dusk".
"""
from stagekit import arch, core, dress, lights

AREA = dict(lo=(-14.0, -6.2), hi=(14.0, 6.2))
MARK = {
    "stallholder": (-6.2, 2.4, 0.0),
    "customer": (-4.9, 1.6, 0.0),
    "talker_a": (2.0, -1.2, 0.0),
    "talker_b": (3.0, -0.6, 0.0),
    "well": (-8.8, -3.6, 0.0),
}
WIDE = ((-13.0, -3.6, 2.0), (4.0, 2.0, 2.8), 14.0)
LIGHT = {"market_day": {}, "market_dusk": {}}


def build_set(time: str = "market_day"):
    night = time == "market_dusk"
    if night:
        lights.rig("dusk", sun_from=-70, sun_elevation=14, look=False, rim=0.0, ambient=1.1)
    else:
        lights.rig("day_clear", sun_from=-40, sun_elevation=38, look=False, rim=0.0)
    inv = dress.exterior(AREA, "market_street", marks=MARK, density=1.3, seed=5, keep_clear=0.7, night=night)
    lights.limit_shadows(0)
    return {"mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "exterior": True}
