"""The city street: a modern street 8 m of asphalt with markings and a crossing, pavements, shopfronts and flats three to six storeys high, towers beyond.

A worked example of the set-file contract for a modern outdoor set:

    marks first       MARK = a pedestrian waiting at the crossing, two people on the pavement, someone at the bus stop
    then the place    dress.exterior(area, "city_street"): the road with centre and edge lines and a zebra crossing, concrete pavements, shop
                      fronts with awnings and signs on both sides, skyline towers closing both ends of the street and over the roofs
    then the light    day: a bright afternoon sun; night: a moon, lit shop windows, street lamps and traffic lights
    then the dressing nine parked cars, street lamps, traffic lights, a bus stop, road and parking signs, hydrant, meters, a post box, bins,
                      a bench, trees in the pavement, a steaming manhole, litter, puddles and leaves

Camera side is -Y. WIDE is from the south-west end of the street at pavement height, looking along it. Times: "city_day", "city_night".
"""
from stagekit import arch, core, dress, lights

AREA = dict(lo=(-14.0, -7.6), hi=(14.0, 7.6))
MARK = {
    "pedestrian": (3.6, -4.9, 0.0),
    "talker_a": (-5.5, -5.2, 0.0),
    "talker_b": (-4.5, -5.0, 0.0),
    "bus_stop": (-4.0, 5.1, 0.0),
}
WIDE = ((-13.0, -5.1, 1.9), (4.0, 1.5, 2.0), 14.0)
LIGHT = {"city_day": {}, "city_night": {}}


def build_set(time: str = "city_day"):
    night = time == "city_night"
    if night:
        lights.rig("night_moon", sun_from=-60, sun_elevation=46, look=False, rim=0.0, ambient=0.9)
    else:
        lights.rig("day_clear", sun_from=-45, sun_elevation=42, look=False, rim=0.0)
    inv = dress.exterior(AREA, "city_street", marks=MARK, density=1.3, seed=8, keep_clear=0.7, night=night)
    lights.limit_shadows(0)
    return {"mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "exterior": True}
