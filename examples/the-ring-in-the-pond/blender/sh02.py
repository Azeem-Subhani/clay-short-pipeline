"""sh02 - strength fails: the proud soldier swings out on the oak branch, it cracks, and he goes in. Noon."""
import math

import set_pond_garden as sp
from stagekit import build, camera, cast, core, fx

HANDS = 1.43            # how far above the feet the hands are when the arms are straight up


def build_shot(shot):
    S = sp.build_set("day_clear")
    M, T = S["mark"], S["tree"]
    soldier = cast.from_plan("soldier", at=M["soldier"], face="right")
    queen = cast.from_plan("queen", at=M["queen"], face="left")
    build.halberd("halberd", at=(M["soldier"][0] - 0.55, M["soldier"][1] + 0.15, 1.0))
    branch, grip = T["branch"], T["branch_grip"]
    soldier.floating = True                                  # he spends this shot in the air and in the water

    t_swing = shot.t("He swung")
    t_break = shot.t("The branch broke")
    t_crack = shot.t("broke")
    t_fall = shot.t("and he fell")

    # --- pride
    soldier.pose("proud", 0.0, 0.0)
    soldier.expr("happy", 0.0, 0.0)
    soldier.squash(shot.t("proud"), -0.07)
    soldier.tilt_head(-8, shot.t("proud") + 0.1, 0.2)

    # --- the idea working for one second: he is already out on the branch (the climb is skipped)
    def under_grip(t):
        core.at_frame(shot.f(t))
        g = grip.matrix_world.translation
        return (g.x, g.y - 0.06, g.z - HANDS)

    def sag(deg, t, quick=False):
        branch.rotation_euler.y = math.radians(deg)
        core.key_frame(branch, "rotation_euler", shot.f(t), index=1, interp="CONSTANT" if quick else None)

    sag(0, 0.0)
    sag(0, t_swing)
    f = shot.f(t_swing)
    soldier.stage.location = M["soldier"]
    core.key_frame(soldier.stage, "location", f - 1, interp="CONSTANT")
    soldier.view("front", t_swing)
    soldier.pose("hang", t_swing, 0.0)
    soldier.expr("happy", t_swing, 0.0)
    soldier.eyes(0.0, -1.0, t_swing, 0.0)
    soldier.stage.location = under_grip(t_swing)
    core.key_frame(soldier.stage, "location", f)
    soldier.rock(-13, t_swing, 0.0, pivot=HANDS)
    for i, (dt, deg, dz) in enumerate(((0.55, 15, 2.5), (1.1, -11, 4.0), (1.65, 9, 6.0), (2.2, -5, 7.5))):
        t = t_swing + dt
        if t >= t_crack:
            break
        soldier.rock(deg, t, 0.5)
        sag(dz, t)
        soldier.stage.location = under_grip(t)
        core.key_frame(soldier.stage, "location", shot.f(t))
    soldier.legs(18, 30, t_swing + 0.5, 0.4)

    # --- he knows before he falls
    soldier.eyes(0.0, 1.0, t_break + 0.1, 0.12)
    soldier.expr("worried", t_break + 0.15, 0.1)
    sag(9, t_crack - 0.04)
    sag(21, t_crack + 0.04)                                 # the crack
    soldier.rock(0, t_crack + 0.05, 0.1)
    soldier.stage.location = under_grip(t_crack + 0.06)
    core.key_frame(soldier.stage, "location", shot.f(t_crack + 0.06))
    soldier.expr("surprised", t_crack + 0.05, 0.05)
    soldier.squash(t_crack + 0.06, -0.08)
    core.at_frame(shot.f(t_crack))
    fx.puff(branch.matrix_world.translation, t_crack, size=0.7, color="#CDB892")

    # --- and in he goes
    t_drop = t_fall + 0.12
    t_hit = t_drop + 0.42
    here = under_grip(t_drop)
    soldier.stage.location = here
    core.key_frame(soldier.stage, "location", shot.f(t_drop), interp="QUAD")
    soldier.stage.location = (here[0], here[1], -1.9)
    core.key_frame(soldier.stage, "location", shot.f(t_hit + 0.1))
    for fc in core.fcurves(soldier.stage):
        for kp in fc.keyframe_points:
            if abs(kp.co.x - shot.f(t_drop)) < 0.5:
                kp.easing = "EASE_IN"
    soldier.pose("hands_up", t_drop + 0.1, 0.1)
    sag(21, t_drop)
    sag(78, t_hit)
    branch.keyframe_insert("location", frame=shot.f(t_drop))
    branch.location.z -= 2.3
    branch.keyframe_insert("location", frame=shot.f(t_hit + 0.05))
    splash_at = (here[0], here[1], S["water_z"])
    fx.splash(splash_at, t_hit, size=1.7, drops=34)
    soldier.stage.location = (here[0], here[1], -1.9)       # under ...
    core.key_frame(soldier.stage, "location", shot.f(t_hit + 0.35))
    soldier.stage.location = (here[0], here[1], -0.98)      # ... and up to his chin, furious
    core.key_frame(soldier.stage, "location", shot.f(t_hit + 0.75))
    soldier.expr("angry", t_hit + 0.5, 0.05)
    soldier.pose("rest", t_hit + 0.4, 0.1)
    soldier.eyes(0, 0, t_hit + 0.4, 0.0)
    fx.ripple(splash_at, t_hit + 0.8, size=1.3, rings=2)
    queen.expr("worried", t_hit + 0.2)
    queen.pose("facepalm", t_hit + 0.5, 0.3)
    queen.idle()

    cam = camera.Camera()
    cam.view("proud_soldier", 0.0, on=[soldier], size="medium", side=14, high=-7, place=0.4, why="one pose says who he is")
    cam.push(0.0, t_swing, 0.06)
    hang = under_grip(t_swing)
    cam.view("the_swing", t_swing, on=[(hang[0], hang[1], hang[2] + 0.2), (hang[0] + 0.9, hang[1], hang[2] + 1.75), (hang[0], hang[1], S["water_z"] - 0.1)],
             size="full", fill=0.6, side=-10, high=3, lens=32, place=0.47, why="the idea working, high over the water")
    cam.push(t_swing, t_break, 0.05)
    cam.view("uh_oh", t_break, on=[soldier.head, grip], size="close", fill=0.5, side=-8, high=-6, place=0.42, why="the moment he knows")
    cam.follow(soldier.head, t_break, t_fall - 0.05)         # the branch sags; stay with his face
    cam.view("splash", t_fall, on=[(hang[0], hang[1], hang[2] + 1.5), (hang[0], hang[1], -0.2)], size="full", fill=0.66, side=-10, high=8, lens=32, place=0.5,
             why="the result")
    cam.shake(t_hit, 0.07, 0.35)
    cam.move(t_hit + 0.45, shot.seconds, on=[(hang[0], hang[1], 1.25), (hang[0], hang[1], -0.35)], size="medium", fill=0.5, side=-10, high=10, lens=32, place=0.34)
    shot.moment("crack", t_crack + 0.1)
    shot.moment("soaked", shot.seconds - 0.15)
