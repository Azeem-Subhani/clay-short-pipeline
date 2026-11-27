"""The training room at NORTHLINE: bright, tidy, a dozen chairs facing a big screen: where new hires are shown the clip of the open door.

A worked example of a bright modern interior with a lit screen as its focus:

    marks first       MARK = twelve seats (seat_1..seat_4 the front row nearest the screen, seat_5..8 the middle row, seat_9..12 the back row, each
                      left to right as the camera at the back sees them), the trainer beside the lectern, the lectern, the flipchart, the door
    then the place    arch.room 9 x 7.5 x 3 m: carpet tile, white walls, tiled ceiling; three office windows with venetian blinds in the east wall looking on
                      a city (arch.vista), a glass door in the south wall; dress.room(R, "training_room"): a 2.9 m wall screen on the north wall (the picture
                      is an image slot: furnish.screen_set_image(refs["screen"], path); the default is a paused security-camera frame with its timestamp),
                      twelve tablet-arm chairs with laptops, cups and papers on them, a lectern, a flipchart, a whiteboard, a notice board, a clock, a ceiling
                      projector, a side table with a water set, plants, a coat stand, posters, an extinguisher, an exit sign and a camera
    then the light    six ceiling panels with real lights, a window key through each east window (soft daylight) and a fill

Camera side is -Y. WIDE is from the south-west corner (the back of the room), over the chairs to the screen. Times: "office_day".
"""
from mathutils import Vector

from stagekit import arch, core, dress, furnish, lights

THEME = "training_room"
SIZE = (9.0, 7.5, 3.0)
_ROWS = (4.4, 3.15, 1.9)                              # front row first
_COLS = (-1.95, -0.65, 0.65, 1.95)
MARK = {f"seat_{r * 4 + c + 1}": (_COLS[c], _ROWS[r], 0.0) for r in range(3) for c in range(4)}
MARK.update({
    "trainer": (-1.45, 5.85, 0.0),             # standing beside the lectern, facing the room
    "lectern": (-2.6, 6.5, 0.0),               # the lectern's own place
    "flipchart": (3.1, 6.4, 0.0),              # beside the flipchart
    "door": (-3.4, 0.7, 0.0),                  # just inside the glass door at the back
})
WIDE = ((-3.9, 0.45, 1.9), (0.9, 6.0, 1.45), 16.0)
LIGHT = {"office_day": {}}


def build_set(time: str = "office_day"):
    ops = [dict(wall="E", kind="window", type="office", w=2.1, h=1.6, sill=0.9, at=a, id=f"win_E{i}") for i, a in enumerate((-2.4, 0.0, 2.4))]
    ops.append(dict(wall="S", kind="door", type="glass", w=1.0, h=2.2, at=-3.4, id="door", open=25))
    R = arch.room(SIZE, at=(0.0, 3.75), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile", openings=ops, name="training", thick=0.25,
                  skirting="brushed_metal", cornice="plaster_clean", floor_tint="#C4CACF")
    arch.vista(R, "E", "city_day", distance=16, seed=5)
    lights.rig("office_day", look=False, rim=0.0, ambient=0.2)
    for oid, hd in R.openings.items():
        if hd["kind"] == "window":
            lights.window_key(hd, color="#F2F6FF", power=520, shaft=False, pitch=16, shadow=False, name=f"KEY_{oid}")
    lights.window_sun(R, "E", elevation=34.0, yaw=-20.0, power=1.4)
    lights.ambient_fill((0, 3.75, 2.8), (7.5, 6.0), power=28, color="#F4F6FF")
    inv = dress.room(R, "training_room", marks=MARK, density=1.0, seed=3, keep_clear=0.3)
    refs = R.refs
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "refs": refs, "screen": refs.get("screen"), "seats": refs.get("seats"),
            "lectern": refs.get("lectern"), "flipchart": refs.get("flipchart"), "projector": refs.get("projector")}
