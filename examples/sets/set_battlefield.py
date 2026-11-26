"""The battlefield: churned ground with a trench, craters and ridges, a broken palisade, abandoned shields and weapons, wrecked engines, smoke on the horizon.

A worked example of the set-file contract for a large outdoor set with relief:

    marks first       MARK = a survivor sitting among the shields, a rider on the ridge path, a herald with a fallen banner, a scavenger at the cart
    then the place    dress.exterior(area, "battlefield"): ground with relief (arch.terrain: trenches, craters, mounds, a ridge) around a level
                      stage, a broken palisade and stakes, dead trees, rubble, a castle on the far ridge, two hosts in the distance, columns of
                      smoke and low haze, ridges all round
    then the light    overcast: a heavy grey sky and soft light; sunset: the sun low through smoke, long shadows, orange sky
    then the dressing planted and fallen banners, stuck shields with arrows, spear stands, bundles of arrows, a standing and a wrecked siege
                      engine, a wrecked cart, burning wreckage with smoke, a riderless horse, mud, stones, puddles and litter

Camera side is -Y. WIDE is from the south-west corner of the stage looking across the field to the palisade and the castle. Times: "battle_overcast",
"battle_sunset".
"""
from stagekit import arch, core, dress, lights

AREA = dict(lo=(-16.0, -6.0), hi=(16.0, 12.0))
MARK = {
    "survivor": (-2.0, -1.5, 0.0),
    "rider": (6.5, 5.0, 0.0),
    "herald": (-7.5, 3.4, 0.0),
    "scavenger": (11.0, -0.5, 0.0),
}
WIDE = ((-9.5, -8.0, 2.1), (1.5, 10.0, 0.5), 13.0)
LIGHT = {"battle_overcast": {}, "battle_sunset": {}}


def build_set(time: str = "battle_overcast"):
    sunset = time == "battle_sunset"
    if sunset:
        lights.rig("sunset", sun_from=-70, sun_elevation=9, look=False, rim=0.0, clouds=1.0)
    else:
        lights.rig("storm", sun_from=-30, look=False, rim=0.0, clouds=1.0)
    inv = dress.exterior(AREA, "battlefield", marks=MARK, density=1.2, seed=3, keep_clear=0.8, night=False)
    lights.limit_shadows(0)
    return {"mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "exterior": True}
