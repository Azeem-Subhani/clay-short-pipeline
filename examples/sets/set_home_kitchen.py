"""The family kitchen: 5.2 x 4.6 m, 2.6 m, two runs of units, a cooker and fridge, a table laid for breakfast, a window over the sink.

A worked example of the set-file contract for a small domestic interior:

    marks first       MARK = someone cooking, someone at the table, someone at the fridge, a child in the doorway
    then the place    arch.room: tile floor, painted walls; a window in the north wall over the units, one in the west wall, a door south
    then the light    day: window light with a sun patch on the tiles; night: the ceiling lights and a lamp
    then the dressing dress.room(R, "home_kitchen", marks=MARK): counters with sink, hob, kettle, mugs, bread; cooker; fridge; dining table with
                      four chairs and a laid breakfast; shelves of jars; clock; radiator; plants; pictures; bin

Camera side is -Y. WIDE is from the south-east corner across the table to the units. Times: "kitchen_home_day", "kitchen_home_night".
"""
from stagekit import arch, core, dress, lights

SIZE = (6.6, 5.4, 2.6)
MARK = {
    "cook": (-1.1, 1.4, 0.0),           # at the counter
    "diner": (-2.0, -0.9, 0.0),         # beside the table
    "fridge": (2.0, 1.4, 0.0),          # at the fridge
    "child": (2.0, -1.9, 0.0),          # in the doorway
}
WIDE = ((3.0, -2.4, 1.8), (-0.6, 1.8, 1.0), 12.0)
LIGHT = {"kitchen_home_day": {}, "kitchen_home_night": {}}


def build_set(time: str = "kitchen_home_day"):
    night = time == "kitchen_home_night"
    ops = [dict(wall="N", kind="window", type="sash", w=1.2, h=1.1, sill=1.1, at=-0.9, id="win_N"),
           dict(wall="W", kind="window", type="sash", w=1.0, h=1.3, sill=1.0, at=0.2, id="win_W"),
           dict(wall="S", kind="door", type="panel", w=0.9, h=2.05, at=2.0, id="door", open=30)]
    R = arch.room(SIZE, at=(0, 0), floor="floor_tile", walls="painted_wall", ceiling="plaster_clean", openings=ops, name="home_kitchen", thick=0.25, skirting="plaster_clean")
    arch.vista(R, "N", "garden", distance=8, seed=2, night=night)
    arch.vista(R, "W", "garden", distance=8, seed=4, night=night)
    arch.vista(R, "S", "garden", distance=8, seed=6, night=night)
    arch.vista(R, "E", "street", distance=8, seed=8, night=night)
    if night:
        lights.rig("candlelit", look=False, rim=0.0, ambient=0.05)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#9FB4FF", power=35, shaft=False, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 2.4), (5.4, 4.4), power=125, color="#FFE0B8")
        lights.rim_light(MARK["cook"], from_deg=170, distance=2.6, power=200, color="#FFE0C0")
    else:
        lights.rig("interior_day", look=False, rim=0.0, strength=0.0, ambient=0.1)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#FFF0DC", power=230, shaft=hd["wall"] == "N", shaft_strength=0.06, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 2.4), (5.4, 4.4), power=65, color="#FFF4E6")
        lights.window_sun(R, "W", elevation=32, yaw=-10, power=7.0, color="#FFE8C4")
        lights.rim_light(MARK["cook"], from_deg=170, distance=2.6, power=220)
    inv = dress.room(R, "home_kitchen", marks=MARK, density=3.0, seed=5, keep_clear=0.4)
    lights.limit_shadows()
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
