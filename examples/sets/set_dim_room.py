"""A dim room at night: one desk, one glowing screen, the page where the stolen files are for sale. A close insert set, 4.2 x 3.4 x 2.6 m.

A worked example of a small, deliberately dark interior that still reads as a place:

    marks first       MARK = the desk, the chair turned toward it, the window, the door
    then the place    arch.room: dark carpet, plain walls, a window (a night city with a streetlight glow) and a door; dress.room(R, "dim_room"): a desk with a
                      monitor showing the market page (an image slot: furnish.screen_set_image(refs["monitor"], path)), an open laptop on the same page, a
                      chair, mugs, papers, a lamp that is OFF, a router and a power strip with their status lights, two bookcases, a filing cabinet, wall shelves
                      with boxes and books, posters, a notice board, cables on the floor, a bin, a plant, litter and an LED strip
    then the light    no ceiling light. The only real lights are the monitor's glow, the little status lamps, the LED strip and a faint blue window key

Camera side is -Y. WIDE is from just inside the door, at the height of a seated person's eyes, looking at the screen. Times: "office_night".
The wide audit's thresholds are the ones for a whole room; this insert meets them (see the report).
"""
from stagekit import arch, core, dress, furnish, lights

THEME = "dim_room"
SIZE = (4.2, 3.4, 2.6)
MARK = {
    "desk": (-0.55, 2.55, 0.0),              # the desk's front
    "chair": (-0.6, 1.85, 0.0),            # the chair, turned toward the desk
    "window": (1.4, 2.7, 0.0),             # in front of the window (north wall, right of the desk)
    "door": (-1.6, 0.45, 0.0),             # just inside the door (south wall)
}
WIDE = ((1.7, 0.3, 1.45), (-0.7, 2.9, 1.0), 15.0)
LIGHT = {"office_night": {}}


def build_set(time: str = "office_night"):
    ops = [dict(wall="N", kind="window", type="office", w=1.1, h=1.2, sill=1.1, at=1.4, id="window"),
           dict(wall="S", kind="door", type="panel", w=0.9, h=2.05, at=-1.6, id="door", open=0)]
    R = arch.room(SIZE, at=(0.0, 1.7), floor="carpet_grey", walls="plaster_clean", ceiling="ceiling_tile", openings=ops, name="dim_room", thick=0.2,
                  skirting="brushed_metal", cornice="plaster_clean", floor_tint="#7F8790", wall_tint="#8E8A86")
    arch.vista(R, "N", "night_city", distance=10, seed=12, night=True)
    lights.rig("office_night", look=False, rim=0.0, ambient=0.03)
    lights.window_key(R.openings["window"], color="#FF9A4A", power=16, shaft=True, shaft_strength=0.035, pitch=12, shadow=False, name="KEY_street")
    inv = dress.room(R, "dim_room", marks=MARK, density=1.0, seed=5, keep_clear=0.3, night=True)
    refs = R.refs
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "refs": refs, "monitor": refs.get("monitor"), "laptop": refs.get("laptop"),
            "desk": refs.get("desk")}
