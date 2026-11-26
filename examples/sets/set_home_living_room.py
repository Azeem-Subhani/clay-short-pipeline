"""The family living room: 6.8 x 5.4 m, 2.6 m, a sofa and armchairs round a rug, a television, bookcases, a case clock, windows onto the garden.

A worked example of the set-file contract for a domestic interior:

    marks first       MARK = a parent on the sofa, a child on the rug, a visitor in the doorway, someone by the window
    then the place    arch.room: parquet, wallpaper, plaster ceiling; two sash windows in the east wall, a door in the south wall, one window
                      in the west wall; arch.vista: a garden by day or night
    then the light    day: window light and a sun patch on the rug; night: the lamps, a ceiling light
    then the dressing dress.room(R, "home_living_room", marks=MARK): sofa, armchairs, coffee table with things, television on a sideboard,
                      bookcases, side tables with lamp and photographs, case clock, plants, pictures, radiator, sconces

Camera side is -Y. WIDE is from the south-west corner across the sofa to the television wall. Times: "living_day", "living_night".
"""
from stagekit import arch, core, dress, lights

SIZE = (7.6, 6.0, 2.6)
MARK = {
    "parent": (-0.9, -0.95, 0.0),       # on the sofa
    "child": (0.1, 0.9, 0.0),           # on the rug
    "visitor": (2.6, -2.2, 0.0),        # in the doorway
    "window": (3.1, 1.0, 0.0),          # by the window
}
WIDE = ((-3.4, -2.6, 1.8), (0.8, 2.0, 1.0), 12.0)
LIGHT = {"living_day": {}, "living_night": {}}


def build_set(time: str = "living_day"):
    night = time == "living_night"
    ops = [dict(wall="S", kind="door", type="panel", w=0.95, h=2.05, at=2.7, id="door", open=30),
           dict(wall="E", kind="window", type="sash", w=1.3, h=1.5, sill=0.9, at=-0.8, id="win_E1"),
           dict(wall="E", kind="window", type="sash", w=1.3, h=1.5, sill=0.9, at=1.4, id="win_E2"),
           dict(wall="W", kind="window", type="sash", w=1.1, h=1.4, sill=1.0, at=0.5, id="win_W")]
    R = arch.room(SIZE, at=(0, 0), floor="parquet", walls="wallpaper", ceiling="plaster_clean", openings=ops, name="living", thick=0.25, skirting="plaster_clean", cornice="plaster_clean")
    arch.vista(R, "E", "garden", distance=10, seed=3, night=night)
    arch.vista(R, "W", "street", distance=8, seed=5, night=night)
    arch.vista(R, "S", "garden", distance=8, seed=7, night=night)
    arch.vista(R, "N", "garden", distance=8, seed=9, night=night)
    if night:
        lights.rig("candlelit", look=False, rim=0.0, ambient=0.05)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#9FB4FF", power=45, shaft=False, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 2.4), (6.4, 5.0), power=165, color="#FFD2A0")
        lights.rim_light(MARK["parent"], from_deg=170, distance=3.0, power=220, color="#BFD4FF")
    else:
        lights.rig("interior_day", look=False, rim=0.0, strength=0.0, ambient=0.1)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#FFF0DC", power=300, shaft=hd["wall"] == "E", shaft_strength=0.06, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 2.4), (6.4, 5.0), power=85, color="#FFF2E0")
        lights.window_sun(R, "E", elevation=30, yaw=15, power=7.0, color="#FFE8C4")
        lights.rim_light(MARK["parent"], from_deg=170, distance=3.0, power=250)
    inv = dress.room(R, "home_living_room", marks=MARK, density=2.8, seed=8, keep_clear=0.4)
    lights.limit_shadows()
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
