"""sh01 - the hook and the game: the ring is lost on frame one, the pond swallows it, the queen makes her offer,
gives the one rule, and the camera quietly shows the gate the ending will need. Noon."""
import set_pond_garden as sp
from stagekit import build, camera, cast, core, fx


def build_shot(shot):
    S = sp.build_set("day_clear")
    M, P = S["mark"], S["pond"]
    queen = cast.from_plan("queen", at=M["queen"], face="left", view="3q")
    soldier = cast.from_plan("soldier", at=M["soldier"], face="right")
    rich = cast.from_plan("rich_man", at=M["rich_man"], face="right")
    gardener = cast.from_plan("gardener", at=M["gardener"], face="right")
    build.halberd("halberd", at=(M["soldier"][0] - 0.55, M["soldier"][1] + 0.15, 1.0))       # the guard's weapon, planted beside him
    ring = build.ring("ring")
    shot.subject("ring", ring, moments=["ring_slips", "ring_sinks"])
    water = (M["ring_in"][0], M["ring_in"][1], S["water_z"])

    # --- words -> times
    t_sink = shot.t("into the deep")
    t_offer = shot.t("Bring it back")
    t_three = shot.t("my best horse")
    t_rule = shot.t("She gave one rule")
    t_gate = shot.t("At the far end")

    # --- the loss: already happening on frame one
    queen.lean(26, 0.0, 0.0)
    queen.arm("R", 74, 6, 0.0, 0.0)                       # hand out over the water
    queen.hand("R", "open", 0.0, 0.0)
    queen.eyes(0.6, -0.8, 0.0, 0.0)
    queen.hold(ring, "R", 0.0, offset=(0.07, 0.0, -0.06))
    t_drop = 0.38
    start = queen.release(ring, t_drop)
    core.move(ring, t_drop, t_drop + 0.62, location=(start.x - 0.12, start.y, S["water_z"] - 0.5))
    core.ease(ring, "location", "QUAD")
    for fc in core.fcurves(ring):                          # falling: slow start, fast end
        for kp in fc.keyframe_points:
            kp.easing = "EASE_IN"
    core.key(ring, "rotation_euler", t_drop)
    core.key(ring, "rotation_euler", t_drop + 0.62, (4.0, 1.2, 2.0))
    queen.expr("surprised", t_drop + 0.2, 0.08)           # the face knows first
    queen.squash(t_drop + 0.28, -0.1)                     # a start
    queen.pose("gasp", t_drop + 0.5, 0.2)
    queen.eyes(0.5, -1.0, t_drop + 0.3)
    queen.lean(10, t_drop + 0.55, 0.25)

    # --- the pond swallows it (the fall is staged again for the close view)
    t_plop = t_sink + 0.5
    f = shot.f(t_sink)
    core.at_frame(f - 1)                                   # it stays where the first fall left it until the cut ...
    core.key_frame(ring, "location", f - 1, tuple(ring.matrix_world.translation), interp="CONSTANT")
    ring.location = (water[0], water[1], water[2] + 1.05)  # ... then starts again above the water for the close view
    core.key_frame(ring, "location", f, interp="QUAD")
    ring.location = (water[0], water[1], water[2] - 0.05)
    core.key_frame(ring, "location", shot.f(t_plop))
    ring.location = (M["ring_rest"][0], M["ring_rest"][1], M["ring_rest"][2])
    core.key_frame(ring, "location", shot.f(t_plop + 1.2))
    fx.splash(water, t_plop, size=0.42, drops=9)
    fx.sparkle(ring, t_sink + 0.1, count=2, size=0.16, gap=0.2)

    # --- the offer: she straightens and speaks; three people hear it, each in their own way
    queen.pose("offer", t_offer + 0.15, 0.3)
    queen.lean(0, t_offer + 0.1, 0.3)
    queen.eyes(1.0, 0.0, t_offer)
    queen.expr("neutral", t_offer, 0.2)
    queen.speak("Bring it back", "is yours")
    soldier.pose("proud", t_three + 0.15, 0.25)
    soldier.expr("happy", t_three + 0.1)
    soldier.squash(t_three + 0.2, -0.06)
    rich.pose("think", t_three + 0.7, 0.3)
    rich.expr("happy", t_three + 0.75)
    gardener.eyes(1.0, 0.5, t_three + 1.2, 0.2)            # she is the only one looking at the far end
    gardener.tilt_head(-6, t_three + 1.3, 0.3)
    gardener.expr("happy", t_three + 1.7, 0.3, amount=0.6)

    # --- the rule
    queen.pose("rest", t_rule - 0.2, 0.2)
    queen.expr("angry", t_rule, 0.15, amount=0.55)         # stern, not furious
    queen.pose("point_up", shot.t("one rule") - 0.1, 0.22)
    queen.speak("Do not touch", "the water")
    t_water = shot.t("the water")
    queen.arm("R", 46, -6, t_water + 0.05, 0.22)           # the finger comes down to point at the pond
    queen.eyes(0.6, -0.9, t_water)
    queen.lean(8, t_water + 0.05, 0.25)

    for a in (queen, soldier, rich, gardener):
        a.idle()

    # --- camera: always from the south, so the queen stays screen right and the hopefuls screen left
    cam = camera.Camera()
    cam.view("ring_slips", 0.0, on=[queen], size="medium", side=-20, high=3, fill=0.5, place=0.42, shift=0.13,
             why="a person, a loss, in motion on the first frame")
    cam.push(0.0, t_sink, 0.07)
    cam.view("ring_sinks", t_sink, on=[(water[0], water[1], water[2] + 0.25)], size="insert", fill=0.12, side=0, high=50, lens=50, place=0.44,
             why="the pond swallows it")
    cam.push(t_sink, t_offer, 0.1)
    cam.view("the_offer", t_offer, pos=sp.WIDE[0], aim=sp.WIDE[1], lens=sp.WIDE[2], size="wide",
             why="geography: who stands where, the branch, the gate")
    cam.push(t_offer, t_three, 0.05)
    cam.view("the_three", t_three, on=[soldier, rich, gardener], size="full", side=38, high=9, lens=40, fill=0.62, place=0.42,
             why="three attitudes in one glance")
    cam.push(t_three, t_rule, 0.05)
    cam.view("one_rule", t_rule, on=[queen], size="close", side=-16, high=2, place=0.38, fill=0.4, why="the rule, unmissable")
    cam.push(t_rule, t_gate - 0.5, 0.06)
    cam.view("the_gate", t_gate + 0.15, pos=(0.95, 0.6, 3.1), aim=(-0.05, 6.6, 0.1), lens=35, travel=0.6, size="full",
             why="the setup: the gate holds the water in")
    cam.push(t_gate + 0.2, shot.seconds, 0.12)
    shot.subject("gate", P["gate_grab"]["mid"], moments=["the_gate"])
    fx.sparkle(P["gate_grab"]["mid"], shot.t("wooden gate"), count=2, size=0.2)
