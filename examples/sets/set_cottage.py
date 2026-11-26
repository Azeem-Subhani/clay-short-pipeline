"""The peasant cottage: one warm room 6.6 x 5.4 m, 2.7 m under bare beams, a stone hearth, a bed in the corner, a table by the window, a garden outside.

A worked example of the set-file contract for a small period interior:

    marks first       MARK = the mother at the hearth, a child at the table, the father at the door, the old woman by the bed
    then the place    arch.room: worn plank floor, limewashed walls, beams; a plank door in the south wall, small windows west, east and north;
                      arch.vista: a kitchen garden and the lane
    then the light    day: window light and a low sun patch across the boards, a bounce for the whitewash; night: the fire is the key, candles,
                      a lantern from the beam, a sconce
    then the dressing dress.room(R, "peasant_cottage", marks=MARK): hearth with cauldron and wood, bed and chest, table with stools and bench,
                      spinning wheel, shelves of jars, baskets, sacks, bucket, broom, herbs and game from the beams, a rag rug

Camera side is -Y. WIDE is from the south-west corner across the table to the hearth and the bed. Times: "cottage_day", "cottage_night".
"""
from stagekit import arch, core, dress, lights

SIZE = (6.6, 5.4, 2.7)
MARK = {
    "mother": (0.2, 1.3, 0.0),          # at the hearth
    "child": (-1.3, -1.0, 0.0),         # beside the table
    "father": (1.9, -2.0, 0.0),         # just inside the door
    "grandmother": (-2.0, 0.6, 0.0),    # by the bed
}
WIDE = ((-2.9, -2.3, 1.7), (0.5, 1.7, 1.0), 14.0)
LIGHT = {"cottage_day": {}, "cottage_night": {}}


def build_set(time: str = "cottage_day"):
    night = time == "cottage_night"
    ops = [dict(wall="S", kind="door", type="plank", w=1.0, h=2.0, at=1.9, id="door", open=35, surround="dark_timber"),
           dict(wall="W", kind="window", type="lattice", w=0.8, h=0.9, sill=1.2, at=-1.4, id="win_W", shutters=True),
           dict(wall="E", kind="window", type="lattice", w=0.8, h=0.9, sill=1.2, at=0.4, id="win_E", shutters=True),
           dict(wall="N", kind="window", type="lattice", w=0.5, h=0.7, sill=1.4, at=-2.2, id="win_N")]
    R = arch.room(SIZE, at=(0, 0), floor="wood_floor", floor_tint="#6A5642", walls="plaster_white", ceiling="dark_timber", ceiling_kind="beams", openings=ops, name="cottage",
                  thick=0.4, skirting="dark_timber", beams="dark_timber")
    arch.vista(R, "S", "garden", distance=8, seed=2, night=night)
    arch.vista(R, "W", "garden", distance=9, seed=4, night=night)
    arch.vista(R, "E", "hills", distance=14, seed=5, night=night)
    arch.vista(R, "N", "garden", distance=8, seed=6, night=night)
    if night:
        lights.rig("candlelit", look=False, rim=0.0, ambient=0.05)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#9FB4FF", power=45, shaft=False, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 2.5), (5.2, 4.2), power=105, color="#FFB878")
        lights.rim_light(MARK["mother"], from_deg=0, distance=2.6, power=200, color="#FF9A50")
    else:
        lights.rig("interior_day", look=False, rim=0.0, strength=0.0, ambient=0.08)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#FFEBCB", power=180, shaft=hd["wall"] == "E", shaft_strength=0.08, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 2.5), (5.2, 4.2), power=70, color="#FFE8CC")
        lights.window_sun(R, "E", elevation=26, yaw=10, power=7.0, color="#FFE8C4")
        lights.rim_light(MARK["child"], from_deg=160, distance=3.0, power=250)
    inv = dress.room(R, "peasant_cottage", marks=MARK, density=2.6, seed=6, keep_clear=0.4)
    lights.limit_shadows()
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
