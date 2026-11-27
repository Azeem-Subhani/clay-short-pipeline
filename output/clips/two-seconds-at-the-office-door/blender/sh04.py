"""sh04 - the theft in plain sight (office, noon): the stranger strolls down the aisle with his coffees past a working floor, closes the
unlocked laptop on the victim's desk and slides it into his open leather bag beside it, waves at the receptionist on her phone on his way out,
and the whole floor keeps its head down.

Views (plan): strolls (track_with beside him down the aisle; behind him a woman on the phone, a man reading a printout, an intern with a mug
crossing) -> into_bag (ONE high framing over the desk that holds the open laptop and the open bag standing beside it, mouth up to the lens:
the lid shuts, his hand grips the closed laptop and never lets go until it is down inside the bag, then the flap drops on "bag"; the camera
only leans down a little with it) -> waves (from behind the end of the front desk, close past the receptionist's right shoulder: her
three-quarter profile on the phone, eyes down on her monitor, a hand up without looking; he comes in from the right, waves with a raised
open hand and a smile, and the camera pans right with him to the open west door) -> nobody (a true high corner view from the south-west,
tilted down 30-40 degrees and rising, over a floor of people with their heads down; his coffees left on the victim's desk by the empty spot).

Staging notes:
  * The aisle chairs of the second row stand at y -2.06, so he walks the clear lane at y -2.62 (the plan's aisle line is y -2.2).
  * The cut to into_bag compresses a second: he is at the desk, the coffees already set down, the bag already open on the desk beside the
    laptop. The cut to waves compresses the walk back: he comes past the front desk heading for the door. The bag rides on his left shoulder
    as in sh02 and sh03: the shoulder bag and the bag on the desk are two copies of the same asset, each shown only where it is.
  * Background extras (plan cast extra_1..extra_7) fill the floor: one seated typist (the only unused body whose limits allow seating), the
    rest standing at desks with printouts or phones, one walking with a mug. Every one is seen from the front, the side or at a wide distance.
  * The receptionist stands at the east end of her counter and her monitor is moved to that end (shot-level dressing move), so the waves
    camera, just past her right shoulder, sees her face three-quarter on.
"""
import math
import random

import bpy
from mathutils import Matrix, Vector

import set_office as sp
from stagekit import aj_clips, assets, build, camera, cast, core, furnish, lights

LANE_Y = -2.62
AT_DESK = (-3.22, -1.47)                 # where he stands at the victim's desk, at its front edge
LAP_AT = (-3.38, -0.95)                 # the laptop (origin at its back edge), its front edge at the desk's front edge (y -1.19), in his reach
BAG_AT = (-2.9, -0.98)                  # the open bag stands on the desk beside it, mouth up
CARRIER_AT = (-3.62, -0.55)             # his coffees, set down at the desk's west end, beside the laptop's spot
POP = 1.0 / 24.0                        # a cut-pop: the change lands on one frame (zero-blend keys are avoided mid-shot)
DOOR = (-8.0, -1.9)
WAVE_AT = (-6.8, -3.02)                 # he passes the counter's aisle side here and waves


def cast_prop(ob):
    for o in [ob, *ob.children_recursive]:
        for k in ("sk_type", "sk_kind", "sk_layer", "sk_on"):
            if k in o.keys():
                del o[k]


def own(actor, ob):
    """A prop the actor carries counts as part of the actor for the ground and visibility checks."""
    for o in [ob, *ob.children_recursive]:
        if o.name not in actor.coll.all_objects:
            actor.coll.objects.link(o)


def point_on(parent, local, name):
    e = core.empty(name, (0, 0, 0), size=0.02)
    e.parent = parent
    e.matrix_parent_inverse.identity()
    e.location = local
    e.hide_render = True
    return e


def seat(a, chair, until):
    """Seated on `chair` from frame one (the end of Stand_To_Sit at the chair's seat height), then Sitting_Idle to `until`."""
    name = "Stand_To_Sit"
    c = aj_clips.require(name)
    top = furnish.tops(chair)[0][1]
    bd = aj_clips.body(a)
    clip_seat = (c["analysis"]["hips_end_per_leg"] - aj_clips.SEAT_UNDER) * bd.leg
    dz = (top - a.stage.matrix_world.translation.z) / a.scale - clip_seat
    a._seat_dz = dz
    aj_clips.play(a, name, 0.0, start=c["duration_s"] - 0.04, blend=0.0, state="sitting", hips_dz=lambda f, u, dz=dz: dz)
    a.do("sit_idle", t=0.04, until=until)


def typing(a, kx, ky, kz, t0, t1, seed=1):
    """Both hands on a keyboard at (kx, ky, kz), fingers going: small alternating dips, a pause now and then."""
    rnd = random.Random(seed)
    a.hand("L", "open", t0, 0.0)
    a.hand("R", "open", t0, 0.0)
    a.reach("L", (kx - 0.11, ky, kz + 0.03), t0, 0.0)
    a.reach("R", (kx + 0.11, ky, kz + 0.03), t0, 0.0)
    t = t0 + 0.2
    i = 0
    while t < t1 - 0.2:
        side = "L" if i % 2 else "R"
        dx = (-0.11 if side == "L" else 0.11) + rnd.uniform(-0.03, 0.03)
        a.reach(side, (kx + dx, ky + rnd.uniform(-0.02, 0.02), kz + 0.012), t, 0.07)
        a.reach(side, (kx + dx, ky, kz + 0.035), t + 0.09, 0.07)
        t += rnd.uniform(0.14, 0.2) if rnd.random() > 0.12 else 0.55
        i += 1


def printout(name):
    """A sheet or two of white A4, held."""
    p = build.box(name, (0.21, 0.297, 0.003), (0, 0, 0), surface="painted_wall", tint="#F4F2EC", bevel=0.0)
    q = build.box(name + "_2", (0.21, 0.297, 0.002), (0, 0, 0), surface="painted_wall", tint="#E9E6DE", bevel=0.0)
    q.parent = p
    q.location = (0.012, -0.008, -0.003)
    q.rotation_euler = (0, 0, math.radians(4))
    return p


def shoulder_bag(st, t0=0.0):
    """As sh02 and sh03: the brown leather bag on his left shoulder, riding at his hip (rigid with his upper body)."""
    bag = assets.use("prop_messenger_bag", name="messenger_bag", at=(0, 0, 0))
    cast_prop(bag)
    core.at_frame(st._f(t0))
    ch = st.chest.ob
    bpy.context.view_layer.update()
    Mw = ch.matrix_world
    fwd = (Mw.to_3x3() @ Vector((0.0, -1.0, 0.0)))
    fwd.z = 0.0
    fwd = fwd.normalized() if fwd.length > 1e-4 else Vector((1.0, 0.0, 0.0))
    left = Vector((-fwd.y, fwd.x, 0.0))
    chest = Mw.translation.copy()
    yaw = math.atan2(fwd.y, fwd.x)
    bag.location = chest + left * 0.2 * st.scale + Vector((0.0, 0.0, -0.62 * st.scale))
    bag.rotation_euler = (math.radians(-14.0), 0.0, yaw)
    bag.scale = (0.85, 0.85, 0.85)
    bpy.context.view_layer.update()
    wm = bag.matrix_world.copy()
    bag.parent = ch
    bag.matrix_world = wm
    own(st, bag)
    return bag


def local_bbox(root):
    """The bounding box of a piece's meshes in the root's own coordinates."""
    bpy.context.view_layer.update()
    inv = root.matrix_world.inverted()
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in [root, *root.children_recursive]:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            q = inv @ (o.matrix_world @ Vector(c))
            lo = Vector(map(min, lo, q))
            hi = Vector(map(max, hi, q))
    return lo, hi


def build_shot(shot):
    S = sp.build_set("office_day")
    M = S["mark"]
    desk, chair, laptop = S["victim_desk"], S["victim_chair"], S["laptop"]
    lid = furnish.part(laptop, "lid")
    desk_top = furnish.tops(desk)[1][1]

    # --- words -> times
    t_slid = shot.t("and slid")              # into_bag
    t_unlocked = shot.t("unlocked")
    t_laptop = shot.t("laptop")
    t_into = shot.t("into his leather")
    t_bag = shot.t("bag.")
    t_he = shot.t("He even waved")            # waves
    t_waved = shot.t("waved")
    t_nobody = shot.t("Nobody glanced up")    # nobody
    t_end = shot.seconds

    # --- the laptop: square to the desk, 23 cm in from its front edge
    laptop.rotation_euler = (0.0, 0.0, math.radians(4.0))
    laptop.location = (LAP_AT[0], LAP_AT[1], laptop.location.z)
    # dressing on the chair seats the extras use
    for o in list(bpy.data.objects):
        t_ = o.get("sk_type")
        if t_ in ("laptop", "mugs", "papers_stack") and o.matrix_world.translation.z < 0.6:
            p = o.matrix_world.translation
            if any(abs(p.x - x) < 0.35 and abs(p.y - y) < 0.4 for x, y in ((-1.0, -1.9), (0.9, -1.9))):
                for k in [o, *o.children_recursive]:
                    k.hide_render = k.hide_viewport = True
                shot.notes.append(f"hid {o.name}: dressing on a chair seat a worker uses")

    # --- cast
    st = cast.from_plan("stranger", at=(-5.65, LANE_Y, 0.0), face="right")
    rec = cast.from_plan("receptionist", at=M["front_desk_staff"], face="left")
    w1 = cast.from_plan("worker_1", at=(-1.0, -1.75, 0.0), face="right")
    w2 = cast.from_plan("worker_2", at=(-2.9, -4.55, 0.0), face="left")
    x1 = cast.from_plan("extra_1", at=(0.9, -1.75, 0.0), face="right")         # seated typist, mid row
    x2 = cast.from_plan("extra_2", at=(-0.02, -1.62, 0.0), face="right")       # standing at the mid row, reading a printout
    x3 = cast.from_plan("extra_3", at=(-5.75, 0.45, 0.0), face="left")         # standing in the middle aisle, on the phone
    x4 = cast.from_plan("extra_4", at=(-3.85, 1.0, 0.0), face="right")         # standing at the north row, reading a printout
    x5 = cast.from_plan("extra_5", at=(1.85, -1.62, 0.0), face="right")        # standing at the mid row, reading a printout
    x6 = cast.from_plan("extra_6", at=(-2.6, -0.1, 0.0), face="left")          # the intern with a mug, walking the middle aisle
    x7 = cast.from_plan("extra_7", at=(-1.95, 1.02, 0.0), face="right")        # standing at the north row, head down on her phone
    st.heading(90.0, 0.0, turn=0.0)
    rec.heading((-5.75, -3.76), 0.0, turn=0.0)                 # toward her monitor on the counter: profile to the waves camera
    for w in (w1, w2, x1):
        w.heading(180.0, 0.0, turn=0.0)
    for w, hd in ((x2, 180.0), (x4, 180.0), (x5, 180.0), (x7, 205.0), (x3, 330.0)):
        w.heading(hd, 0.0, turn=0.0)

    cam = camera.Camera()
    cam.line(st, rec)

    # --- the stranger's kit: coffees in the right hand, the bag on his left shoulder (as sh02/sh03)
    carrier = assets.use("prop_cup_carrier", name="cup_carrier", at=(0, 0, 0))
    cast_prop(carrier)
    st.arm("R", 18, 82, 0.0, 0.0)
    st.hand("R", "open", 0.0, 0.0)
    st.hold(carrier, "R", 0.0, offset=(0.02, 0.0, 0.03))
    own(st, carrier)
    bag_sh = shoulder_bag(st, 0.0)
    st.arm("L", 6, 14, 0.0, 0.0)
    # the coffees on the desk (a second copy, shown from the cut to into_bag on: evidence that stays)
    carrier_d = assets.use("prop_cup_carrier", name="cup_carrier_left", at=(CARRIER_AT[0], CARRIER_AT[1], desk_top))
    carrier_d.rotation_euler.z = math.radians(8.0)
    cast_prop(carrier_d)
    # the bag on the desk, open (a second copy, shown only in into_bag)
    bag_d = assets.use("prop_messenger_bag", name="messenger_bag_desk", at=(BAG_AT[0], BAG_AT[1], desk_top))
    cast_prop(bag_d)
    bag_d.rotation_euler.z = math.radians(-6.0)
    flap = furnish.part(bag_d, "flap")
    if flap is not None:
        core.key(flap, "rotation_euler", 0.0, (math.radians(-100.0), 0.0, 0.0))
    for ob, show in ((carrier, False), (carrier_d, True), (bag_sh, False), (bag_d, True)):
        for k in [ob, *ob.children_recursive]:
            core.show(k, 0.0, not show)
            core.show(k, t_slid, show)
    for k in [bag_sh, *bag_sh.children_recursive]:
        core.show(k, t_he, True)
    for k in [bag_d, *bag_d.children_recursive]:
        core.show(k, t_he, False)

    # ---------------------------------------------------------------- strolls: down the lane, easy, coffees up
    st.expr("happy", 0.0, 0.0, amount=0.4)
    st.eyes(0.3, 0.0, 0.0, 0.0)
    t_arr = st.walk(0.0, to=(-3.85, LANE_Y), speed=2.4, arms=False)
    shot.notes.append(f"stranger strolls until {t_arr:.2f}s (cut at {t_slid:.2f}s)")
    st.eyes(0.6, -0.2, 1.1)                                     # a sideways look at the desk he wants

    # ---------------------------------------------------------------- into_bag: lid shut, the laptop gripped all the way into the bag, flap down
    st.place((AT_DESK[0], AT_DESK[1], 0.0), t_slid)
    st.heading(180.0, t_slid, turn=POP)
    st.release(carrier, t_slid - 0.04)
    st.lean(24, t_slid, POP)
    st.expr("sly", t_slid, POP, amount=0.5)
    st.eyes(0.2, -0.8, t_slid, POP)
    st.arm("L", 20, 30, t_slid, POP)
    st.reach("L", (AT_DESK[0] - 0.24, -1.15, desk_top + 0.02), t_slid, POP)     # his left hand flat on the desk edge, weight on it
    st.hand("L", "open", t_slid, POP)
    # the lid: his right hand on its top edge, shut on "unlocked laptop"
    lid_edge = point_on(lid, (0.04, -0.006, 0.2), "lid_edge")
    t_l0 = max(t_slid + 0.3, t_unlocked - 0.05)
    t_l1 = t_laptop - 0.02
    st.hand("R", "mitten", t_slid, POP)
    st.reach("R", lid_edge, t_slid + 0.25, 0.25)
    core.key(lid, "rotation_euler", t_l0)
    core.key(lid, "rotation_euler", t_l1, (math.radians(90.0), 0.0, 0.0))
    f = shot.f(t_slid + 0.25)
    while f <= shot.f(t_l1):
        st.reach("R", lid_edge, f / shot.fps, 1.0 / shot.fps)
        f += 1
    # the laptop: shut, his fingers close on its front edge; tipped up on its back edge, lifted over and lowered into the bag's mouth. The
    # laptop is keyed and the hand rides its grip point every frame, so there is no frame where it leaves the hand.
    core.at_frame(shot.f(t_l1) + 1)
    lo, hi = local_bbox(laptop)
    grip = point_on(laptop, ((lo.x + hi.x) / 2 + 0.05, lo.y + 0.01, hi.z - 0.004), "laptop_grip")
    yaw = laptop.rotation_euler.z

    def lap_loc(rx_deg, x, y, z_bottom):
        """Where the laptop's origin goes for a tilt rx about its own X and its lowest point at z_bottom."""
        R = Matrix.Rotation(yaw, 3, "Z") @ Matrix.Rotation(math.radians(rx_deg), 3, "X")
        zs = [(R @ Vector((cx, cy, cz))).z for cx in (lo.x, hi.x) for cy in (lo.y, hi.y) for cz in (lo.z, hi.z)]
        return Vector((x, y, z_bottom - min(zs)))

    bag_top = desk_top + 0.28
    bag_in = desk_top + 0.025
    t_s0 = t_l1 + 0.08
    t_s1 = t_into - 0.05                        # tipped up on its back edge
    t_s2 = t_into + 0.3                          # vertical, lifted over the bag's mouth
    t_s3 = t_into + 0.42
    t_s4 = t_bag - 0.38                          # down inside
    lap0 = Vector(laptop.location)
    keys = [
        (t_s0, lap0, 0.0),
        (t_s1, lap_loc(-48.0, lap0.x + 0.04, lap0.y + 0.02, desk_top + 0.002), -48.0),
        (t_s2, lap_loc(-90.0, BAG_AT[0] - 0.06, BAG_AT[1] - 0.004, bag_top + 0.05), -90.0),
        (t_s3, lap_loc(-90.0, BAG_AT[0], BAG_AT[1] - 0.004, bag_top + 0.035), -90.0),
        (t_s4, lap_loc(-90.0, BAG_AT[0], BAG_AT[1] - 0.004, bag_in), -90.0),
    ]
    for t, loc, rx in keys:
        core.key(laptop, "location", t, tuple(loc))
        core.key(laptop, "rotation_euler", t, (math.radians(rx), 0.0, yaw))
    st.hand("R", "grip", t_s0, 0.06)
    f = shot.f(t_l1)
    while f <= shot.f(t_s4):
        st.reach("R", grip, f / shot.fps, 1.0 / shot.fps)
        f += 1
    st.lean(18, t_s2, 0.3)
    t_rel = t_s4 + 0.06
    st.hand("R", "open", t_rel, 0.06)
    core.show(laptop, t_bag + 0.3, False)                       # inside, under the flap
    # the flap: his hand takes its free edge and drops it shut on "bag"
    if flap is not None:
        core.at_frame(shot.f(t_rel))
        flo, fhi = core.world_bbox([flap])
        fg = point_on(flap, flap.matrix_world.inverted() @ Vector(((flo.x + fhi.x) / 2 + 0.06, (flo.y + fhi.y) / 2, fhi.z)), "flap_grip")
        t_c0, t_c1 = t_rel + 0.12, t_bag + 0.02
        st.reach("R", fg, t_c0, 0.12)
        st.hand("R", "pinch", t_c0, 0.06)
        core.key(flap, "rotation_euler", t_c0, (math.radians(-100.0), 0.0, 0.0))
        core.key(flap, "rotation_euler", t_c1, (0.0, 0.0, 0.0))
        f = shot.f(t_c0)
        while f <= shot.f(t_c1):
            st.reach("R", fg, f / shot.fps, 1.0 / shot.fps)
            f += 1
        st.hand("R", "open", t_c1 + 0.05, 0.06)
        st.reach("R", fg, t_c1 + 0.3, 0.2)                         # a pat on the shut flap
    st.eyes(-0.6, 0.1, t_s4 + 0.05)                             # a glance over his shoulder: nobody
    st.expr("grin", t_bag, 0.15, amount=0.6)
    shot.notes.append(f"lid {t_l0:.2f}-{t_l1:.2f}s, laptop gripped {t_s0:.2f}-{t_s4:.2f}s, flap shut on 'bag' {t_bag:.2f}s")

    # ---------------------------------------------------------------- waves: past the front desk, a raised-hand wave and a smile, out the door
    st.heading(180.0, t_he - 0.08, turn=POP)                    # hold him square to the desk until the cut (a POP key does not hold the old value)
    he_at = Vector((-6.1, -2.92, 0.0))                         # the cut compresses: he is already passing the counter, so the wave lands in frame
    st.place(tuple(he_at), t_he)
    yaw_out = math.degrees(math.atan2(WAVE_AT[0] - he_at.x, -(WAVE_AT[1] - he_at.y)))
    st.heading(yaw_out, t_he, turn=POP)
    st.lean(0, t_he, POP)
    st.pose("rest", t_he, POP)
    st.arm("R", 6, 14, t_he, POP)
    st.arm("L", 6, 14, t_he, POP)
    st.hand("R", "open", t_he, POP)
    st.hand("L", "open", t_he, POP)
    st.expr("happy", t_he, POP, amount=0.6)
    t_p = st.walk(t_he + 0.22, to=WAVE_AT, speed=2.2, arms=False)     # its 0.2 s turn-in starts after the cut, so it cannot reach back into into_bag
    shot.notes.append(f"stranger at the wave spot at {t_p:.2f}s")
    # the wave: head and eyes to her first, a smile, the left hand up at head height, palm out, two easy side-to-side beats
    t_w0 = t_waved - 0.15
    st.eyes(-0.8, -0.1, t_w0 - 0.25, 0.15)
    st.head_turn(-0.45, t_w0 - 0.1, 0.25)
    st.expr("grin", t_w0, 0.15, amount=0.8)
    st.hand("L", "open", t_w0, 0.1)
    st.arm("L", 128, 78, t_w0 + 0.3, 0.3, plane="out")
    tt = t_w0 + 0.3
    for i in range(4):
        tt += 0.15
        st._wag("L", 16 if i % 2 == 0 else -16, tt, 0.15)
    st._wag("L", 0, tt + 0.12, 0.1)
    st.arm("L", 6, 14, tt + 0.45, 0.3)
    st.head_turn(0.0, tt + 0.35, 0.3)
    t_out = st.walk(max(t_p + 0.05, tt - 0.35), to=(DOOR[0] - 0.7, DOOR[1]), speed=2.8, arms=False)
    shot.notes.append(f"wave {t_w0:.2f}-{tt:.2f}s; through the door at {t_out:.2f}s")
    # the receptionist: on the phone at her right ear, eyes down on her monitor, a hand up without looking
    phone = assets.use("prop_smartphone", name="rec_phone", at=(0, 0, 0))
    cast_prop(phone)
    own(rec, phone)
    rec.do("phone", phone, t=0.0, until=t_end, side="R")
    rec.eyes(0.35, -0.7, 0.0, 0.0)
    rec.tilt_head(-8, 0.0, 0.0)
    rec.expr("neutral", 0.0, 0.0)
    rec.speak("He", "out")
    rec.place((-5.25, -4.62, 0.0), t_nobody)                    # nobody: along her counter, out of the high corner's frame
    t_lift = t_waved + 0.35
    rec.arm("L", 66, 70, t_lift, 0.25)
    rec.hand("L", "open", t_lift, 0.1)
    rec.arm("L", 8, 12, t_lift + 0.8, 0.35)
    for b in (1.3, 4.1, 6.4, 8.3):
        rec.blink(b)

    # ---------------------------------------------------------------- the floor: heads down, the whole time
    w_chairs = {}
    for o in bpy.data.objects:
        if o.get("sk_type") == "chair_office":
            p = o.matrix_world.translation
            for key, (cx, cy) in (("w1", (-1.0, -2.061)), ("w2", (-2.9, -4.861)), ("x1", (0.9, -2.061))):
                if abs(p.x - cx) < 0.1 and abs(p.y - cy) < 0.1:
                    w_chairs[key] = o
    for key, w, ky, seed in (("w1", w1, -1.0, 3), ("w2", w2, -3.8, 5), ("x1", x1, -1.0, 9)):
        ch = w_chairs.get(key)
        if ch is not None:
            seat(w, ch, t_end)
            w.floating = True                                   # seated: the chair seat carries them, not the floor under the stage
        else:
            shot.notes.append(f"{key}: chair not found, standing")
        wx = w.stage.matrix_world.translation.x
        typing(w, wx, ky, 0.76, 0.0, t_end, seed=seed)
        w.eyes(0.0, -0.35, 0.0, 0.0)
        w.expr("neutral", 0.0, 0.0)
    w1.tilt_head(-6, 3.0, 0.5)
    w1.tilt_head(0, 6.0, 0.5)
    w2.head_turn(0.15, 2.4, 0.4)
    w2.head_turn(0.0, 5.0, 0.4)
    # standing readers: a printout up, head bent over it
    for k, a in enumerate((x2, x4, x5)):
        pr = printout(f"printout_{k}")
        cast_prop(pr)
        own(a, pr)
        a.do("read", pr, t=0.0, until=t_end)
        a.tilt_head(-10, 0.0, 0.0)
        a.expr("neutral", 0.0, 0.0)
    x7_phone = assets.use("prop_smartphone", name="x7_phone", at=(0, 0, 0))
    cast_prop(x7_phone)
    own(x7, x7_phone)
    x7.do("phone", x7_phone, t=0.0, until=t_end, side="R", screen=True)
    x3_phone = assets.use("prop_smartphone", name="x3_phone", at=(0, 0, 0))
    cast_prop(x3_phone)
    own(x3, x3_phone)
    x3.do("phone", x3_phone, t=0.0, until=t_end, side="L")
    x3.expr("happy", 0.0, 0.0, amount=0.3)
    x3.speak("he", "cubicles")
    x3.eyes(0.4, -0.3, 0.0, 0.0)
    # the intern with a mug: crosses behind the stranger in strolls, and along the middle aisle again under the high wide
    mug = furnish.make("mugs", at=(0, 0, 0), count=1, seed=2)
    cast_prop(mug)
    x6.hold(mug, "R", 0.0, offset=(0.0, 0.0, 0.0))
    own(x6, mug)
    x6.arm("R", 30, 95, 0.0, 0.0)
    x6.eyes(0.0, -0.4, 0.0, 0.0)
    x6.walk(0.0, to=(-6.7, -0.1), speed=1.8, arms=False)
    x6.place((-4.4, -0.1, 0.0), t_nobody - 0.4)
    x6.heading(90.0, t_nobody - 0.4, turn=POP)
    x6.walk(t_nobody - 0.36, to=(-0.4, -0.1), speed=2.0, arms=False)
    for a, bl in ((w1, (0.9, 5.2)), (w2, (2.2, 6.8)), (x1, (1.6, 7.4)), (x2, (2.9, 7.9)), (x3, (3.4,)), (x4, (1.1, 7.0)),
                  (x5, (4.4, 8.4)), (x7, (2.0, 6.1))):
        for b in bl:
            a.blink(b)

    for a in (st, rec, w1, w2, x1, x2, x3, x4, x5, x6, x7):
        a.idle()

    # a cool window-side rim on the stranger where he walks (he is charcoal against grey walls)
    lights.rim_light((-4.8, LANE_Y, 0.0), from_deg=160, elevation=28, distance=3.5, power=170, color="#DCE8FF", name="RIM_sh04_lane")
    lights.rim_light((WAVE_AT[0], WAVE_AT[1], 0.0), from_deg=150, elevation=28, distance=3.2, power=150, color="#DCE8FF", name="RIM_sh04_wave")

    # ---------------------------------------------------------------- camera
    cam.view("strolls", 0.0, pos=(-5.6, -4.92, 1.85), aim=(-5.2, LANE_Y, 1.2), lens=35, size="full",
             why="beside him down the aisle: an easy stroll, the monitors passing in front, people working behind him")
    cam.track_with(st, 0.0, t_slid, side="right", distance=2.3, height=1.85, aim_height=1.2, lens=35, lead=0.45, smooth=0.45, join=0.8, settle=0.6)

    # into_bag: one high framing that holds the open laptop and the open bag together; the camera only leans down with the laptop
    mid = Vector(((LAP_AT[0] + BAG_AT[0]) / 2, (LAP_AT[1] + BAG_AT[1]) / 2, desk_top + 0.14))
    v_pos = Vector((-4.05, -0.98, 2.2))                      # high off the desk's west end: laptop near, bag beyond, his arm from the right
    cam.view("into_bag", t_slid, pos=tuple(v_pos), aim=tuple(mid + Vector((0.02, -0.04, 0.0))), lens=32, size="insert",
             why="the theft is a small hand action: big, from above, the screen, the lid, the hand, the open bag beside it")
    cam.dolly(t_slid, t_l1, 0.06, ease="ease_in_out")
    bag_aim = Vector((BAG_AT[0] - 0.1, BAG_AT[1] - 0.02, desk_top + 0.06))
    cam.move(t_s1, t_s4 + 0.1, pos=tuple(cam._pose.pos), aim=tuple(bag_aim), lens=36, ease="SINE")

    # waves: just past her right shoulder at the end of the counter; pan right with him to the west door
    w_pos = Vector((-5.08, -4.76, 1.56))
    rs = Vector(M["front_desk_staff"])
    hp = Vector((rs.x, rs.y, 1.5))
    wp = Vector((WAVE_AT[0], WAVE_AT[1], 1.62))
    def az(v):
        return math.atan2(v.y - w_pos.y, v.x - w_pos.x)
    yaw0 = 0.4 * az(hp) + 0.6 * az(wp)                          # her at the left edge, where he waves right of centre
    a0 = w_pos + Vector((math.cos(yaw0), math.sin(yaw0), math.tan(math.radians(1.5)))) * 2.0
    cam.view("waves", t_he, pos=tuple(w_pos), aim=tuple(a0), lens=22, size="medium",
             why="past her shoulder, on the phone, eyes on her screen: he waves like he belongs")
    door_aim = Vector((DOOR[0], DOOR[1] - 0.05, 1.3))
    t_pan0 = min(tt - 0.25, t_nobody - 1.25)
    # the pan rises 0.4 m as it turns so the line to the door passes over her counter monitor
    cam.move(t_pan0, t_nobody - 0.04, pos=tuple(w_pos + Vector((0.12, 0.05, 0.4))), aim=tuple(door_aim), lens=33, ease="SINE")
    d0 = (a0 - w_pos)
    d1 = (door_aim - w_pos)
    pan = math.degrees(math.atan2(d1.y, d1.x) - math.atan2(d0.y, d0.x))
    shot.notes.append(f"waves pan {pan:.1f} deg {t_pan0:.2f}-{t_nobody:.2f}s")

    # nobody: the high south-west corner, tilted down over the floor, rising a metre while it tilts further down
    N0 = (Vector((-7.45, -4.78, 1.55)), -30.0)
    N1 = (Vector((-7.5, -4.83, 2.42)), -38.0)
    yaw_n = math.radians(46.0)                                  # the receptionist stays out at the right edge, the coffees near centre

    def aim_of(pos, pitch):
        p = math.radians(pitch)
        return tuple(pos + Vector((math.cos(yaw_n) * math.cos(p), math.sin(yaw_n) * math.cos(p), math.sin(p))) * 6.0)

    cam.view("nobody", t_nobody, pos=tuple(N0[0]), aim=aim_of(*N0), lens=22.0, size="wide",
             why="the result is invisible: a full floor, heads down, not one turned; his coffees by the empty spot on the desk")
    cam.move(t_nobody + 0.05, t_end - 0.05, pos=tuple(N1[0]), aim=aim_of(*N1), lens=22.0, ease="SINE")
    shot.notes.append(f"nobody: rise {N1[0].z - N0[0].z:.2f} m, tilt {N0[1]:.0f} -> {N1[1]:.0f} deg; end pose pos {tuple(round(v, 3) for v in N1[0])} aim {tuple(round(v, 3) for v in aim_of(*N1))}")

    shot.subject("stranger", st.head, moments=["strolls", "waves.a", "wave"])
    # (in into_the_bag the laptop is half inside the bag, so each hides the other by design: not checked there)
    shot.subject("laptop", laptop, moments=["into_bag.a", "lid_shut"])
    # the bag is read from its west face (toward this camera): its centre is behind the laptop once the laptop is inside it
    bag_face = core.empty("bag_west_face", (BAG_AT[0] - 0.205, BAG_AT[1], desk_top + 0.13), size=0.03)
    bag_face.hide_render = True
    shot.subject("bag", bag_face, moments=["into_bag.b", "into_the_bag"])
    shot.subject("receptionist", rec.head, moments=["waves.a", "wave"])
    door_pt = core.empty("west_door_pt", (DOOR[0] + 0.15, DOOR[1], 1.5), size=0.05)
    door_pt.hide_render = True
    shot.subject("west_door", door_pt, moments=["waves.b"])
    shot.subject("coffees", carrier_d, moments=["nobody"])
    shot.moment("lid_shut", t_l1 + 0.05)
    shot.moment("into_the_bag", (t_s3 + t_s4) / 2)
    shot.moment("wave", t_w0 + 0.55)
