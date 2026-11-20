"""Set: the hallway wall with the kidnappers' bedroom door, seen close. Camera on -Y.
Cool stairwell light rakes the door from screen-left; warm light lives only in the gap under the door."""
from stagekit import assets, build, lights


def build_set():
    build.slab("hall_floor", (6, 4), (0, -1.6, 0), "#5A4A3E")
    build.wall("hall_wall", 6.0, 3.4, (0, 0.08, 0), color="#6E7480", openings=[(0, 0, 0.92, 2.07)])
    door = build.door("door", at=(0, 0.04, 0), color="#5B4433", frame_color="#8B8478")
    build.box("hall_base_l", (2.5, 0.05, 0.12), (-1.8, -0.02, 0), "#4A4F58")
    build.box("hall_base_r", (2.5, 0.05, 0.12), (1.8, -0.02, 0), "#4A4F58")
    build.box("lock_plate", (0.08, 0.012, 0.22), (0.33, -0.008, 0.80), "#000", bevel=0.004, material=build.clay("#8A7A4E", rough=0.4, metallic=0.7, bump=0.004))
    key = assets.use("prop_door_key", at=(0.33, -0.016, 0.84), scale=1.6)      # a little oversized so it reads on a phone
    build.box("door_gap_glow", (0.9, 0.03, 0.022), (0, 0.0, 0.0), "#000", bevel=0, material=build.glow("#FFB866", 14.0, "gap_glow"))
    rig = lights.rig("interior_night", subject=(0.33, -0.1, 0.9), key_azimuth=-62, key_elevation=28, distance=2.6, strength=2.6, fill=1.6, rim=0.3)
    lights.practical("gap_spill", (0, -0.12, 0.05), "#FFB866", 16, kind="AREA", aim=(0, -1.2, 0), size=0.5, shadow=False, rig_=rig)
    return {"rig": rig, "key": key, "door": door}
