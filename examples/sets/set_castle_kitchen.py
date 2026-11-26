"""The castle kitchen: 10 x 8.5 m, 4.6 m under dark beams, stone walls 0.7 m thick, a great hearth, work tables, a pump, a door to the yard.

A worked example of the set-file contract for a working medieval interior:

    marks first       MARK = the cook at the hearth, a scullion at the long table, the steward in the doorway, a page by the pump
    then the place    arch.room: flagstone floor, castle-stone walls, a beamed ceiling; a plank door to the yard in the south wall, tall
                      arched windows in the east wall, a small window each side of the hearth; arch.vista gives the yard and the hills
    then the light    day: a low sun through the east windows lands on the flags as patches, a soft window key, a bounce for the
                      stone; night: the hearth and its embers are the key, candles, torches, lanterns and a chandelier carry the rest
    then the dressing dress.room(R, "castle_kitchen", marks=MARK): the hearth with its spit, cauldron and wood, work tables with food, shelves of
                      bottles and jars, a sideboard, a pump and bucket, barrels, sacks, crates, game, herbs and pots hung from the beams

Camera side is -Y. WIDE is from the south-west corner across the work tables to the hearth. Times: "kitchen_day", "kitchen_night".
"""
from stagekit import arch, core, dress, lights

SIZE = (10.0, 8.5, 4.6)
MARK = {
    "cook": (0.0, 2.9, 0.0),            # in front of the fire
    "scullion": (-0.6, -0.55, 0.0),     # at the long table, near side
    "steward": (2.5, -3.3, 0.0),        # in the yard doorway
    "page": (-3.2, 0.0, 0.0),           # by the pump
}
WIDE = ((-4.6, -4.0, 2.1), (0.6, 2.4, 0.9), 12.0)
LIGHT = {"kitchen_day": {}, "kitchen_night": {}}


def build_set(time: str = "kitchen_day"):
    night = time == "kitchen_night"
    ops = [dict(wall="S", kind="door", type="plank", w=1.4, h=2.5, at=2.5, id="yard_door", open=40, arched=True, surround="castle_stone"),
           dict(wall="E", kind="window", type="arched", w=1.1, h=2.2, sill=1.7, at=-1.6, arched=True, id="win_E1", surround="castle_stone"),
           dict(wall="E", kind="window", type="arched", w=1.1, h=2.2, sill=1.7, at=1.4, arched=True, id="win_E2", surround="castle_stone"),
           dict(wall="W", kind="window", type="arched", w=0.9, h=1.9, sill=1.9, at=-2.6, arched=True, id="win_W1", surround="castle_stone"),
           dict(wall="N", kind="window", type="lattice", w=0.6, h=0.9, sill=2.0, at=-3.5, id="win_N1"),
           dict(wall="N", kind="window", type="lattice", w=0.6, h=0.9, sill=2.0, at=3.5, id="win_N2")]
    R = arch.room(SIZE, at=(0, 0), floor="flagstone", floor_tint="#8E887E", walls="castle_stone", ceiling="dark_timber", ceiling_kind="beams", openings=ops, name="kitchen",
                  thick=0.7, skirting="castle_stone", beams="dark_timber")
    arch.vista(R, "S", "garden", distance=9, seed=4, night=night)
    arch.vista(R, "E", "hills", distance=16, seed=6, night=night)
    arch.vista(R, "W", "garden", distance=9, seed=7, night=night)
    arch.vista(R, "N", "hills", distance=14, seed=9, night=night)
    if night:
        lights.rig("candlelit", look=False, rim=0.0, ambient=0.05)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#9FB4FF", power=80, shaft=False, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 4.2), (8, 7), power=420, color="#FFB878")         # the fire and its embers bouncing off beams and stone
        lights.rim_light(MARK["cook"], from_deg=0, distance=3.0, power=320, color="#FF9A50")
    else:
        lights.rig("interior_day", sun_from=90, sun_elevation=34, look=False, rim=0.0, strength=0.0, ambient=0.08)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#FFEBCB", power=260, shaft=hd["wall"] == "E", shaft_strength=0.10, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 4.2), (8, 7), power=210, color="#FFE8CC")
        lights.window_sun(R, "E", elevation=36, yaw=0, power=7.5, color="#FFE8C4")
        lights.rim_light(MARK["scullion"], from_deg=160, distance=4.0, power=420)
    inv = dress.room(R, "castle_kitchen", marks=MARK, density=2.0, seed=4, keep_clear=0.55)
    lights.limit_shadows()
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
