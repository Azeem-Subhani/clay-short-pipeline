"""sh03 - cleverness fails slowly: the rich man fishes until sunset, and the ring keeps falling through his net. Sunset."""
import math

import set_pond_garden as sp
from stagekit import build, camera, cast, core, fx


def build_shot(shot):
    S = sp.build_set("sunset")
    M = S["mark"]
    rich = cast.from_plan("rich_man", at=M["fisher"], face="left", view="3q")
    net = build.pole_net("net", pole=2.5, hoop=0.3)
    pole, hoop = net["root"], net["hoop"]
    ring = build.ring("ring", at=M["ring_rest"])
    shot.subject("ring", ring, moments=["through_the_net"])
    shot.subject("net", hoop, moments=["fishing", "through_the_net"])

    t_fish = shot.t("He fished")
    t_ring = shot.t("But the ring")
    t_slip = shot.t("It slipped")
    t_every = shot.t("every time")

    def aim(pitch, yaw, t, cut=False):
        """The pole points to screen-left (he faces left): pitch = degrees below level, yaw = swing toward the camera."""
        pole.rotation_euler = (0.0, math.radians(pitch), math.radians(180 + yaw))
        core.key_frame(pole, "rotation_euler", shot.f(t), interp="CONSTANT" if cut else None)

    # --- pleased with himself: the net upright like a staff, a finger to the temple
    aim(-82, 0, 0.0)
    rich.hold(pole, "L", 0.0, offset=(0.02, 0.0, 0.0))
    rich.arm("L", 52, 46, 0.0, 0.0)
    rich.expr("happy", 0.0, 0.0)
    rich.pose("think", shot.t("clever") - 0.25, 0.25)
    rich.tilt_head(-5, shot.t("clever"), 0.2)

    # --- the method: both hands on the pole, sweeping the water against the low sun
    aim(-82, 0, t_fish - 0.04, cut=True)
    rich.view("side", t_fish)
    rich.pose("hold_pole", t_fish, 0.0)
    rich.hold(pole, "R", t_fish, offset=(0.0, 0.0, 0.0))
    rich.lean(14, t_fish, 0.0)
    rich.expr("neutral", t_fish, 0.0)
    aim(30, -10, t_fish, cut=False)
    aim(36, 12, t_fish + 0.9)
    aim(33, -6, t_fish + 1.7)
    aim(10, 0, t_ring - 0.1)                                # ... and up it comes
    rich.lean(2, t_ring - 0.1, 0.4)
    core.at_frame(shot.f(t_fish + 0.9))
    fx.ripple((hoop.matrix_world.translation.x, hoop.matrix_world.translation.y, S["water_z"]), t_fish + 0.5, size=0.8, rings=2)

    # --- why it fails: the ring sits in the mesh for a breath, then drops through
    aim(9, 0, t_ring, cut=True)
    rich.expr("happy", t_ring, 0.0)
    c = ring.constraints.new("COPY_LOCATION")
    c.target = hoop
    c.influence = 0.0
    c.keyframe_insert("influence", frame=max(1, shot.f(t_ring) - 1))
    c.influence = 1.0
    c.keyframe_insert("influence", frame=shot.f(t_ring))
    c.keyframe_insert("influence", frame=shot.f(t_slip) - 1)
    c.influence = 0.0
    c.keyframe_insert("influence", frame=shot.f(t_slip))
    for fc in core.fcurves(ring):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
    core.at_frame(shot.f(t_ring))
    h = hoop.matrix_world.translation.copy()
    ring.location = h
    core.key_frame(ring, "location", shot.f(t_slip), interp="QUAD")
    ring.location = (h.x, h.y, S["water_z"] - 0.3)
    core.key_frame(ring, "location", shot.f(t_slip + 0.42))
    for fc in core.fcurves(ring):
        for kp in fc.keyframe_points:
            if fc.data_path == "location" and abs(kp.co.x - shot.f(t_slip)) < 0.5:
                kp.easing = "EASE_IN"
    fx.sparkle(ring, t_ring + 0.15, count=2, size=0.14)
    fx.drips(hoop, t_ring, t_slip + 0.2, rate=6)
    fx.splash((h.x, h.y, S["water_z"]), t_slip + 0.4, size=0.36, drops=7)
    rich.expr("surprised", t_slip + 0.2, 0.06)

    # --- a day gone
    rich.view("3q", t_every)
    rich.pose("slump", t_every, 0.0)
    rich.expr("sad", t_every, 0.0)
    aim(48, 0, t_every, cut=True)
    rich.tilt_head(22, t_every + 0.35, 0.3)
    rich.idle(0.0, t_ring)

    cam = camera.Camera()
    cam.view("clever_rich", 0.0, on=[rich], size="medium", side=-12, high=-2, place=0.4, why="his idea is in his head and his tool")
    cam.push(0.0, t_fish, 0.06)
    core.at_frame(shot.f(t_fish + 0.9))
    cam.view("fishing", t_fish, on=[rich, hoop], size="full", side=-38, high=7, lens=32, fill=0.56, place=0.42,
             why="the method, and the low sun: a whole day. Seen along the pole, so the net is near us and large")
    cam.push(t_fish, t_ring, 0.05)
    cam.view("through_the_net", t_ring, on=[(h.x, h.y, h.z + 0.5), (h.x, h.y, S["water_z"] - 0.05)], size="insert", fill=0.7, side=-14, high=14, lens=60, place=0.46,
             why="the reason must be seen: the ring is smaller than the hole")
    cam.view("every_time", t_every, on=[rich], size="medium", side=-12, high=2, place=0.4, why="what the wasted day cost him")
    cam.push(t_every, shot.seconds, 0.05)
    shot.moment("slips", t_slip + 0.2)
