"""sh04 - the simple answer as cause and effect: gate up, water out, ring on the mud; the queen laughs. Morning."""
import set_pond_garden as sp
from stagekit import build, camera, cast, core, fx


GATE_CAM = ((0.9, 1.5, 2.15), (-0.85, 5.6, 0.95))      # from over the water: gardener, bar, board and the channel beyond


def build_shot(shot):
    S = sp.build_set("morning")
    M, P = S["mark"], S["pond"]
    mud = S["mud_z"]
    gardener = cast.from_plan("gardener", at=M["gardener"], face="right", view="3q")
    queen = cast.from_plan("queen", at=M["queen"], face="left")
    soldier = cast.from_plan("soldier", at=M["onlooker_a"], face="left")
    rich = cast.from_plan("rich_man", at=M["onlooker_b"], face="left")
    ring = build.ring("ring", at=M["ring_rest"])
    shot.subject("ring", ring, moments=["across_the_mud", "the_ring", "never_said"])
    shot.subject("gate", P["gate_grab"]["mid"], moments=["lifts_the_gate"])
    shot.subject("queen", shot.subjects["queen"], moments=["water_runs_out", "never_said"])
    for name in ("soldier", "rich_man"):                    # the losers are background: they only matter in the wide
        shot.subject(name, shot.subjects[name], moments=["water_runs_out"])

    t_walk = shot.t("She walked to the gate")
    t_at = shot.t("gate")
    t_lift = shot.t("lifted")
    t_out = shot.t("The water ran out")
    t_mud = shot.t("She walked across")
    t_pick = shot.t("and picked up")
    t_ring = shot.t("the ring")
    t_last = shot.t("The queen had never")

    # --- the first views come before the action: flat figures turn to the camera, so hands are solved for the real view
    cam = camera.Camera()
    cam.view("the_gardener", 0.0, on=[gardener], size="medium", side=12, high=2, place=0.4, why="eyes lead the idea")
    cam.push(0.0, t_walk, 0.07)
    cam.view("lifts_the_gate", t_walk, pos=GATE_CAM[0], aim=GATE_CAM[1], lens=35, size="full",
             why="cause: hands on the bar, the board rising, water leaving, in one frame")
    cam.push(t_lift, t_out, 0.08)
    cam.view("water_runs_out", t_out, pos=sp.WIDE[0], aim=sp.WIDE[1], lens=sp.WIDE[2], size="wide",
             why="effect, in the framing of the opening wide so the change is obvious")
    cam.push(t_out, t_mud, 0.07)                             # a slow lean in as the level falls

    # --- she looks where the others did not
    gardener.eyes(1.0, 0.5, 0.75, 0.2)
    gardener.tilt_head(-5, 0.85, 0.25)
    gardener.expr("happy", 1.3, 0.25, amount=0.7)

    # --- cause: to the gate, hands on the bar, up it goes
    stand = P["gate_stand"]["left"].matrix_world.translation.copy()
    gardener.place((stand.x - 1.3, stand.y, 0.0), t_walk)
    gardener.eyes(1.0, 0.0, t_walk, 0.0)
    arrive = gardener.walk(t_walk, to=(stand.x - 0.45, stand.y), speed=2.8)
    hop = gardener.move(arrive, arrive + 0.22, (stand.x, stand.y, stand.z), arc=0.16)
    gardener.view("3q", hop)
    grab = P["gate_grab"]["left"]
    t_grip = max(hop + 0.1, t_lift - 0.12)
    gardener.reach("R", grab, t_grip, blend=0.2)
    gardener.reach("L", grab, t_grip, blend=0.2)
    gardener.lean(10, t_grip, 0.2)
    gardener.squash(t_grip + 0.06, 0.07)                    # she sets herself ...
    up = P["open_gate"](t_grip + 0.12, t_grip + 0.55)       # ... and heaves
    gardener.lean(-9, up, 0.4)
    gardener.reach("R", grab, up, blend=0.42)
    gardener.reach("L", grab, up, blend=0.42)
    gardener.expr("happy", up + 0.1)
    P["drain"](t_grip + 0.3, t_out + 0.85)                  # the level is falling as we cut wide, and gone a second later
    core.at_frame(shot.f(up))
    gp = P["gate"].matrix_world.translation
    fx.splash((gp.x, gp.y + 0.7, -0.55), t_grip + 0.4, size=0.7, drops=10)

    # --- effect: everyone watches the pond go down; one glint of gold on the mud
    for a, dt in ((queen, 0.15), (soldier, 0.3), (rich, 0.45)):
        a.expr("surprised", t_out + dt)
        a.eyes(0.8, -0.9, t_out + dt)
    queen.pose("gasp", t_out + 0.3, 0.25)
    soldier.lean(12, t_out + 0.4, 0.3)
    soldier.eyes(-0.6, -0.8, t_out + 0.3)
    rich.eyes(-0.6, -0.8, t_out + 0.45)
    rich.pose("think", t_out + 0.5, 0.3)
    fx.sparkle(ring, t_out + 0.95, count=3, size=0.34, gap=0.22)

    # --- she simply walks to it
    cam.view("across_the_mud", t_mud, pos=(-0.15, -0.72, -0.42), aim=(0.3, 0.75, -0.42), lens=26, size="full",
             why="she does what the rule made impossible for the others")
    cam.move(t_mud, t_pick, pos=(0.35, -0.72, -0.45), aim=(0.75, 0.75, -0.5), lens=26)
    gardener.place((-0.5, 0.74, mud), t_mud)
    gardener.pose("rest", t_mud, 0.0)
    gardener.lean(0, t_mud, 0.0)
    there = gardener.walk(t_mud, to=(M["ring_rest"][0] - 0.62, 0.74, mud), speed=2.9, view="side", face="right")
    fx.sparkle(ring, t_mud + 0.3, count=3, size=0.2, gap=0.4)

    # --- the ring: first alone and large on the mud, then in her hand, held out where she and we can see it
    cam.view("the_ring", t_pick, on=[ring], size="insert", fill=0.15, side=8, high=16, lens=45, place=0.46, why="the prize, large; a hand comes for it")
    gardener.view("3q", there)
    gardener.pose("reach_down", max(there, t_pick) + 0.15, 0.25)
    gardener.eyes(0.8, -1.0, t_pick)
    t_take = max(there + 0.4, t_ring - 0.15)
    gardener.reach("R", ring, t_take, blend=0.18)
    gardener.hand("R", "pinch", t_take, 0.05)
    gardener.hold(ring, "R", t_take, offset=(0.05, 0.0, 0.02))
    gardener.lean(-3, t_take + 0.5, 0.38)
    gardener.tilt_head(-4, t_take + 0.5, 0.35)
    gardener.arm("R", 78, 18, t_take + 0.5, 0.38)           # held out in front of her chest, clear of her face
    gardener.arm("L", 24, 30, t_take + 0.5, 0.3)
    gardener.eyes(1.0, 0.1, t_take + 0.4)
    gardener.expr("happy", t_take + 0.35)
    fx.sparkle(ring, t_take + 0.62, count=3, size=0.15, gap=0.25)
    cam.move(t_take + 0.08, t_take + 0.58, on=[gardener.head, gardener.chest, ring], size="medium", fill=0.5, side=10, high=-5, lens=40, place=0.4)

    # --- the queen, outsmarted and delighted
    queen.pose("rest", t_last - 0.3, 0.2)
    queen.expr("happy", t_last + 0.2, 0.15)
    queen.eyes(0.9, -0.6, t_last)
    t_laugh = shot.t("said")
    queen.pose("laugh", t_laugh, 0.3)
    queen.shake(t_laugh + 0.25, shot.seconds - 0.5, amount=2.2, rate=8)
    queen.speak(t_laugh + 0.2, shot.seconds - 0.6, strength=0.8)
    soldier.pose("gasp", t_last + 0.4, 0.25)
    soldier.lean(0, t_last + 0.4, 0.2)
    rich.pose("facepalm", t_last + 0.9, 0.3)
    rich.expr("sad", t_last + 0.9)
    fx.sparkle(ring, t_last + 0.6, count=4, size=0.15, gap=0.7)
    gardener.shake(shot.t("must"), shot.t("must") + 0.6, amount=1.5, rate=6)    # a small happy wiggle
    for a in (gardener, queen, soldier, rich):
        a.idle()

    cam.view("never_said", t_last, pos=(-0.8, -0.7, -0.5), aim=(1.7, 0.85, 0.2), lens=27, size="full",
             why="the winner and the delighted queen in one frame")
    cam.push(t_last, shot.seconds - 0.6, 0.1)
    cam.hold(shot.seconds)
    shot.moment("gate_up", up + 0.2)
    shot.moment("drained", t_out + 1.1)
    shot.moment("ring_up", t_take + 0.8)
    shot.moment("last", shot.seconds - 0.3)
