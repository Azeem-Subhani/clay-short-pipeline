"""The village shop: 8 x 7 m, 3.3 m under beams, a counter with scales and a till, wall shelving of bottles and jars, display stands, goods everywhere.

A worked example of the set-file contract for a trading interior:

    marks first       MARK = the shopkeeper behind the counter, a customer at it, a child by the display, someone at the door
    then the place    arch.room: boards, plaster, beams; a shop-front in the south wall (two big windows and a glazed door onto the street),
                      a window in each side wall, a back door; arch.vista: the street (day or night), gardens behind
    then the light    day: a daylit shop-front with a sun patch on the boards; night: lamps and candles, the street through the window
    then the dressing dress.room(R, "shop_interior", marks=MARK): the counter with scales, till, baskets and a scroll; back shelves of bottles
                      and jars; display stands of cloth and fruit; barrels, sacks, crates; herbs and pots from the beams; signs and notices

Camera side is -Y. WIDE is from the south-east corner across the counter to the back shelves. Times: "shop_day", "shop_night".
"""
from stagekit import arch, core, dress, lights

SIZE = (8.0, 7.0, 3.3)
MARK = {
    "keeper": (0.0, 1.0, 0.0),          # behind the counter
    "customer": (-0.8, -0.1, 0.0),      # in front of it
    "child": (2.8, -0.4, 0.0),          # at the display stand
    "door": (-2.6, -2.8, 0.0),          # inside the door
}
WIDE = ((3.4, -3.0, 1.9), (-0.4, 2.2, 1.0), 13.0)
LIGHT = {"shop_day": {}, "shop_night": {}}


def build_set(time: str = "shop_day"):
    night = time == "shop_night"
    ops = [dict(wall="S", kind="door", type="glass", w=1.1, h=2.2, at=-2.6, id="shop_door", open=30),
           dict(wall="S", kind="window", type="shop", w=2.4, h=1.7, sill=0.7, at=0.2, id="shopfront_1"),
           dict(wall="S", kind="window", type="shop", w=1.6, h=1.7, sill=0.7, at=2.9, id="shopfront_2"),
           dict(wall="E", kind="window", type="sash", w=1.0, h=1.3, sill=1.1, at=-1.0, id="win_E"),
           dict(wall="W", kind="window", type="sash", w=1.0, h=1.3, sill=1.1, at=-1.0, id="win_W"),
           dict(wall="N", kind="door", type="plank", w=0.9, h=2.0, at=3.2, id="back_door", open=0)]
    R = arch.room(SIZE, at=(0, 0), floor="wood_floor", floor_tint="#7A6450", walls="plaster_warm", ceiling="dark_timber", ceiling_kind="beams", openings=ops, name="shop",
                  thick=0.4, skirting="dark_timber", beams="dark_timber")
    arch.vista(R, "S", "street", distance=8, seed=3, night=night)
    arch.vista(R, "E", "garden", distance=8, seed=4, night=night)
    arch.vista(R, "W", "garden", distance=9, seed=5, night=night)
    arch.vista(R, "N", "garden", distance=7, seed=6, night=night)
    if night:
        lights.rig("candlelit", look=False, rim=0.0, ambient=0.05)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#FFC980", power=110 if hd["wall"] == "S" else 40, shaft=False, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 3.0), (6.5, 5.5), power=200, color="#FFC890")
        lights.rim_light(MARK["keeper"], from_deg=170, distance=3.2, power=260, color="#FFB070")
    else:
        lights.rig("interior_day", look=False, rim=0.0, strength=0.0, ambient=0.08)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, color="#FFF0DC", power=420 if hd["wall"] == "S" else 160, shaft=hd["wall"] == "S", shaft_strength=0.07, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 3.0), (6.5, 5.5), power=110, color="#FFEBD0")
        lights.window_sun(R, "S", elevation=28, yaw=-30, power=7.0, color="#FFE8C4")
        lights.rim_light(MARK["keeper"], from_deg=170, distance=3.2, power=300)
    inv = dress.room(R, "shop_interior", marks=MARK, density=1.8, seed=3, keep_clear=0.4)
    lights.limit_shadows()
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
