"""The tavern: 11 x 9 m, 3.6 m under dark beams, a bar with a back-bar of bottles, a hearth, a gallery with a stair and a back door, a street outside.

A worked example of the set-file contract for a period interior (stagekit.arch / furnish / dress / lights):

    marks first       MARK = the bartender behind the bar, a patron at the bar, two tables, the hearth chair, the front door
    then the place    arch.room: plank floor, plaster walls, a beamed ceiling; the front door and two lattice windows in the south wall
                      (the street at night or by day beyond), two windows in the west wall by the hearth, a back door in the east wall
                      under the gallery; arch.vista gives each wall its view
    then the light    night: a faint moon through the windows, a warm bounce standing for the light of the hearth and a dozen candles,
                      the practicals (hearth, lanterns, candles, sconces, chandelier) do the rest; day: window light and a low sun patch
    then the dressing dress.room(R, "tavern", marks=MARK): the bar with bottles, tankards and candles, three shelves of bottles, kegs and barrels,
                      six tables with stools, a bench, the hearth with chairs and wood, the gallery on posts with its stair and rail,
                      a dartboard, notices, a painting, a shield, a tapestry, lanterns hung from the beams, straw on the floor

Camera side is -Y. WIDE is from the south-west corner across the floor to the bar and the gallery. Times: "tavern_night", "tavern_day".
"""
from stagekit import arch, core, dress, lights

SIZE = (11.0, 9.0, 3.6)
MARK = {
    "bartender": (-0.9, 3.65, 0.0),       # behind the bar
    "patron": (0.4, 2.1, 0.0),            # leaning on the bar
    "table_a": (-0.7, -1.0, 0.0),         # between the near tables
    "table_b": (3.0, 0.2, 0.0),           # the table by the stair
    "hearth": (-3.3, 0.7, 0.0),           # in the chair by the fire
    "door": (3.6, -3.3, 0.0),             # just inside the front door
}
WIDE = ((-5.0, -4.1, 1.6), (1.6, 2.8, 1.0), 15.0)
LIGHT = {"tavern_night": {}, "tavern_day": {}}


def build_set(time: str = "tavern_night"):
    night = time == "tavern_night"
    ops = [dict(wall="S", kind="door", type="plank", w=1.2, h=2.2, at=3.5, id="front_door", open=30, surround="dark_timber"),
           dict(wall="S", kind="window", type="lattice", w=1.3, h=1.3, sill=1.0, at=-3.6, id="win_S1", shutters=True),
           dict(wall="S", kind="window", type="lattice", w=1.3, h=1.3, sill=1.0, at=-0.4, id="win_S2", shutters=True),
           dict(wall="W", kind="window", type="lattice", w=1.1, h=1.3, sill=1.1, at=-3.3, id="win_W1"),
           dict(wall="W", kind="window", type="lattice", w=1.1, h=1.3, sill=1.1, at=3.4, id="win_W2"),
           dict(wall="E", kind="door", type="plank", w=1.1, h=2.15, at=1.9, id="back_door", open=0),
           dict(wall="N", kind="window", type="lattice", w=1.0, h=1.0, sill=1.5, at=3.7, id="win_N1")]
    R = arch.room(SIZE, at=(0, 0), floor="wood_floor", floor_tint="#6E5A46", walls="plaster_warm", ceiling="dark_timber", ceiling_kind="beams", openings=ops, name="tavern",
                  thick=0.4, skirting="dark_timber", cornice="dark_timber", beams="dark_timber")
    arch.vista(R, "S", "street", distance=9, seed=3, night=night)
    arch.vista(R, "W", "garden", distance=10, seed=2, night=night)
    arch.vista(R, "E", "garden", distance=8, seed=5, night=night)
    arch.vista(R, "N", "street", distance=9, seed=8, night=night)
    # ---- light
    if night:
        lights.rig("candlelit", look=False, rim=0.0, ambient=0.05)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#9FB4FF", power=70, shaft=False, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 3.2), (9, 7.5), power=330, color="#FFC890")      # the glow of a fire and a dozen candles on beams and plaster
        lights.rim_light(MARK["patron"], from_deg=170, distance=3.5, power=260, color="#FFB070")
    else:
        lights.rig("interior_warm", look=False, rim=0.0, ambient=0.09)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#FFEBCB", power=320, shaft=hd["wall"] == "S", shaft_strength=0.08, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 3.2), (9, 7.5), power=170, color="#FFE2BE")
        lights.window_sun(R, "S", elevation=30, yaw=-25, power=7.0, color="#FFE8C4")
        lights.rim_light(MARK["patron"], from_deg=170, distance=3.5, power=300, color="#FFE0C0")
    # ---- the dressing
    inv = dress.room(R, "tavern", marks=MARK, density=1.45, seed=5, keep_clear=0.55)
    lights.limit_shadows()
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
