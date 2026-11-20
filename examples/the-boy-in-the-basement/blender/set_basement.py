"""Set: the bare basement, open toward the camera (-Y). One high window on the back wall; a hard cold pool of
moonlight falls on the mattress, so the boy is the brightest thing in the room."""
import math

from stagekit import assets, build, lights


def build_set():
    build.room("basement", 5.2, 4.6, 3.3, wall_color="#5C636E", floor_color="#474B52", ceiling=True, baseboard=False,
               openings={"back": [(1.3, 2.25, 0.9, 0.55)]})
    build.window("high_window", 0.9, 0.55, at=(1.3, 2.3, 2.25), frame_color="#3B4048", lit="#9DB7FF", lit_strength=3.0)
    build.box("mattress", (1.9, 0.9, 0.16), (-0.4, -0.3, 0), "#8E8778", bevel=0.05)      # long side to camera; head end on the left
    build.box("pillow", (0.4, 0.6, 0.09), (-0.98, -0.3, 0.16), "#C9C4B8", bevel=0.04)
    build.crate("crate", 0.5, (1.9, 1.5, 0), rot_z=12, color="#6A5540")
    build.cup("cup", (0.75, -0.95, 0), "#B9B4A8")
    assets.use("prop_school_bag", at=(-2.1, 1.7, 0), rot_z=-25)       # a quiet, fair clue for the last line ("from school")
    for i, z in enumerate((2.75, 2.95)):                              # pipes along the back wall
        p = build.cyl(f"pipe{i}", 0.05, 5.2, (0, 0, 0), "#3E444C", segments=14, bevel=0)
        p.rotation_euler.y = math.radians(90)
        p.location = (-2.6, 2.2 - i * 0.02, z)
    rig = lights.rig("interior_night", subject=(-0.6, -0.3, 0.4), key_azimuth=62, key_elevation=58, distance=3.0, fill=1.3)
    moon = lights.practical("moon_shaft", (1.6, 3.4, 3.2), "#A9C1FF", 4600, kind="SPOT", aim=(-0.6, -0.3, 0.1), size=0.12, rig_=rig)
    moon.data.spot_size = math.radians(40)
    return {"rig": rig, "moon": moon, "mattress_top": 0.16}
