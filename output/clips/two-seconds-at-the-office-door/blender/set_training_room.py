"""training_room - the NORTHLINE training room on a bright orientation morning ("Two Seconds at the Office Door": sh08).

Adapted from examples/sets/set_training_room.py for this clip: MARK holds only the plan's marks (the five new hires' seats, the trainer, the
lectern); the light is a step softer than the worked file (its reverse angle was over-exposed: window keys, sun patches, sky ambient and fill
lowered) with a rim on the front row; the wall screen (returned as "screen") shows the lobby CCTV frame by default and the shot sets its picture.

The training room at NORTHLINE: bright, tidy, a dozen chairs facing a big screen: where new hires are shown the clip of the open door.

A worked example of a bright modern interior with a lit screen as its focus:

    marks first       MARK = the seats the plan uses (seat_N counts seat_1..seat_4 the front row nearest the screen, seat_5..8 the middle, seat_9..12 the back, each
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
_SEATS = {f"seat_{r * 4 + c + 1}": (_COLS[c], _ROWS[r], 0.0) for r in range(3) for c in range(4)}       # where the twelve chairs stand
MARK = {k: _SEATS[k] for k in ("seat_2", "seat_3", "seat_6", "seat_7", "seat_10")}                    # the five hires (front, middle, back row)
MARK.update({
    "trainer": (-1.45, 5.85, 0.0),             # standing beside the lectern, facing the room
    "lectern": (-2.6, 6.5, 0.0),               # the lectern's own place
})
WIDE = ((-3.9, 0.45, 1.9), (0.9, 6.0, 1.45), 16.0)
LIGHT = {"office_day": {}}


def build_set(time: str = "office_day"):
    ops = [dict(wall="E", kind="window", type="office", w=2.1, h=1.6, sill=0.9, at=a, id=f"win_E{i}") for i, a in enumerate((-2.4, 0.0, 2.4))]
    ops.append(dict(wall="S", kind="door", type="glass", w=1.0, h=2.2, at=-3.4, id="door", open=25))
    R = arch.room(SIZE, at=(0.0, 3.75), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile", openings=ops, name="training", thick=0.25,
                  skirting="brushed_metal", cornice="plaster_clean", floor_tint="#C4CACF")
    arch.vista(R, "E", "city_day", distance=16, seed=5)
    lights.rig("office_day", look=False, rim=0.0, ambient=0.13)
    for oid, hd in R.openings.items():
        if hd["kind"] == "window":
            lights.window_key(hd, color="#F2F6FF", power=380, shaft=False, pitch=16, shadow=False, name=f"KEY_{oid}")
    lights.window_sun(R, "E", elevation=34.0, yaw=-20.0, power=1.0)
    lights.ambient_fill((0, 3.75, 2.8), (7.5, 6.0), power=18, color="#F4F6FF")
    lights.rim_light(MARK["seat_2"], from_deg=200, elevation=28, distance=4.0, power=160.0, color="#E4ECFF", name="RIM_front_row")
    inv = dress.room(R, "training_room", marks=MARK, density=1.0, seed=3, keep_clear=0.3)
    refs = R.refs
    import bpy
    for ob in bpy.data.objects:                              # the ceiling panels a step down: the white walls of the reverse angle read, not glare
        if ob.get("sk_type") == "ceiling_light_panel":
            for c in ob.children_recursive:
                if c.type == "LIGHT":
                    c.data.energy *= 0.7
    lights.limit_shadows(10)
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "refs": refs, "screen": refs.get("screen"), "seats": refs.get("seats"),
            "lectern": refs.get("lectern"), "flipchart": refs.get("flipchart"), "projector": refs.get("projector")}
