"""sh04 - the lock. The object acts: a key turns on 'locked'. His shadow leaves the door; we never see the hand."""
import math

import set_upstairs_door
from stagekit import camera, cast, core


def build_shot(shot):
    S = set_upstairs_door.build_set()
    key = S["key"]
    shot.subject("key", key)
    t_lock = shot.t("locked")
    core.key(key, "rotation_euler", t_lock - 0.05)
    core.key(key, "rotation_euler", t_lock + 0.30, (0.0, math.radians(90), 0.0))    # a quarter turn: the bow goes from upright to flat

    # he stands just out of frame between the stairwell light and the door, so his shadow lies on it; then he leaves
    man = cast.from_plan("man", at=(-0.75, -0.75), facing=150)
    shot.subjects.pop("man", None)
    man.walk(t_lock + 0.7, to=(-3.4, -1.6), speed=0.8)
    man.idle(blinks=False)

    cam = camera.Camera(lens=70, blur="strong")
    cam.at(0.0, pos=(0.62, -1.25, 0.98), aim=(0.30, 0.0, 0.88), focus=key)
    cam.hold(t_lock + 0.5)
    cam.at(shot.seconds - 0.2, pos=(0.75, -2.5, 0.80), aim=(0.12, 0.0, 0.62), blur="medium")  # leaving: the warm gap under the door comes into frame
    cam.hold(shot.seconds)

    shot.moment("key", max(0.0, t_lock - 0.4))
    shot.moment("turned", t_lock + 0.45)
