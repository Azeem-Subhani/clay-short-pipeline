"""The corner shop: 13 x 9 m, 3.4 m to a plain ceiling, a shop window on the street (north) and a glazed door in the south wall.

The second set of the plan_new_format fixture (tools/tests/fixtures/plan_new_format.json). Built with the architecture kit and the
shop_interior theme, the same way as examples/sets/set_office.py: marks first, then the room, then the light, then the dressing.
Camera side is -Y. Times: "interior_day" and "candlelit" (the shop at night, lit by its own lamps).
"""
from stagekit import arch, dress, lights

THEME = "shop_interior"
SIZE = (13.0, 9.0, 3.4)
MARK = {
    "counter": (3.4, 2.0, 0.0),         # where the shopkeeper stands
    "shelves": (-3.6, 3.2, 0.0),        # the customer, at the shelves
    "door": (-4.4, -3.6, 0.0),          # just inside the door
}
WIDE = ((-5.9, -4.1, 1.8), (1.2, 2.6, 1.2), 15.0)
LIGHT = {"interior_day": dict(), "candlelit": dict()}


def build_set(time: str = "interior_day"):
    w, d, h = SIZE
    ops = [dict(wall="S", kind="door", type="plank", w=1.0, h=2.1, at=-4.4, id="shop_door", open=30),
           dict(wall="N", kind="window", type="sash", w=1.8, h=1.6, sill=0.8, at=-2.4, id="win_a"),
           dict(wall="N", kind="window", type="sash", w=1.8, h=1.6, sill=0.8, at=2.6, id="win_b"),
           dict(wall="E", kind="window", type="sash", w=1.2, h=1.4, sill=1.0, at=0.0, id="win_c")]
    R = arch.room(SIZE, floor="wood_floor", walls="plaster_warm", ceiling="dark_timber", ceiling_kind="beams", openings=ops, name="shop", thick=0.25)
    night = time == "candlelit"
    arch.vista(R, "N", "street", distance=10, night=night, seed=3)
    arch.vista(R, "E", "rooftops", distance=14, night=night, seed=5)
    arch.vista(R, "S", "street", distance=8, night=night, seed=7)
    lights.rig(time, look=False, rim=0.0, ambient=0.08 if night else 0.2, strength=0.0)
    for oid, hd in R.openings.items():
        if hd["kind"] == "window":
            lights.window_key(hd, power=120 if night else 520, shaft=not night, shaft_strength=0.06, name=f"KEY_{oid}")
    lights.ambient_fill((0, 0, h - 0.3), (w * 0.8, d * 0.8), power=40 if night else 70, color="#FFE9CC")
    lights.rim_light(MARK["counter"], from_deg=170, distance=4.0, power=200, color="#CFE0FF")
    inv = dress.room(R, THEME, marks=MARK, density=3.2, seed=11, keep_clear=0.6)
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
