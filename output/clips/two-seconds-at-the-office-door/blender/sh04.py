"""sh04 - the theft in plain sight (office, noon): the stranger strolls down the aisle with his coffees past a working floor, closes the
unlocked laptop on the victim's desk and slides it into his open leather bag beside it, waves at the receptionist on her phone on his way out,
and the whole floor keeps its head down.

Views (plan): strolls (track_with beside him down the aisle; behind him people at their desks, a woman on the phone, an intern with a
mug crossing) -> into_bag (ONE high framing over the desk: the open laptop near, the open bag beyond it with its back to the lens and its
flap up on the far side, so its dark mouth is seen from above; the lid shuts, his hand grips the closed laptop and never lets go while it
turns square to the bag and goes down its own axis into the mouth, hidden once it is all the way in; the flap drops on "bag") -> waves
(past the receptionist's right shoulder at the end of the counter, level and a little down: her profile, phone at her ear, head bowed
over her notes; he passes beyond the counter with an easy half-wave and a smile; she lifts two fingers off the page without looking;
the camera pans with him to the open west door) -> nobody (high over the front desk in the south-west corner, rising while it tilts
down to 32 degrees: the receptionist bowed at the bottom, then a floor of people heads-down at screens, papers and a phone; his coffees
left on the victim's desk by the empty spot). sh06 opens on nobody's end pose (NOBODY_END) at night.

Staging notes:
  * The aisle chairs of the second row stand at y -2.06, so he walks the clear lane at y -2.62 (the plan's aisle line is y -2.2).
  * The cut to into_bag compresses a second: he is at the desk, the coffees already set down, the bag already open on the desk beside the
    laptop. The cut to waves compresses the walk back: he comes past the front desk heading for the door. The bag rides on his left shoulder
    as in sh02 and sh03: the shoulder bag and the bag on the desk are two copies of the same asset, each shown only where it is.
  * The bag asset's body is a closed block, so a dark mouth is laid on its top and its carry handle is laid forward (away from the lens)
    so the laptop goes in between the handle's ends.
  * The floor (plan cast extra_1..extra_7): seated typists (bodies whose limits allow a seated back view at this distance), a standing
    reader and a standing phone reader, all heads down (tilt_head + is down). Time is compressed at the cuts: the intern sits at his desk
    from the cut to into_bag, worker_2 moves to the middle row's west desk (a chair added there) at the cut to nobody.
"""
import math
import random

import bpy
from mathutils import Matrix, Vector

import set_office as sp
from stagekit import aj_clips, assets, build, camera, cast, core, furnish, lights, mat

LANE_Y = -2.62
AT_DESK = (-3.22, -1.47)                 # where he stands at the victim's desk, at its front edge
LAP_AT = (-3.38, -0.95)                 # the laptop (origin at its back edge), its front edge at the desk's front edge (y -1.19), in his reach
BAG_AT = (-3.0, -0.98)                  # the open bag stands on the desk beside it, mouth up (the bag's centre)
BAG_YAW = -90.0                         # its back toward the into_bag camera (west), its front and the raised flap away from it
CARRIER_AT = (-3.62, -0.55)             # his coffees, set down at the desk's west end, beside the laptop's spot
POP = 1.0 / 24.0                        # a cut-pop: the change lands on one frame (zero-blend keys are avoided mid-shot)
DOOR = (-8.0, -1.9)
WAVE_AT = (-6.8, -3.02)                 # he passes the counter's aisle side here and waves
NOTES_AT = (-5.95, -4.19)
REC_AT = (-6.1, -4.38, 0.0)             # front_desk_staff, a step nearer the counter so her writing arm bends
FRONT_MONITOR_AT = (-5.3, -3.76)        # her counter monitor, moved to the counter's east end (shot dressing; sh06 does the same): it no
                                        # longer stands between the waves camera and the stranger               # the receptionist's notes on the counter's near edge, under her free hand
# nobody: high over the front desk in the south-west corner, looking north-east down over the floor; it rises while it tilts down.
# sh06 (tearing_apart) opens on NOBODY_END at night: it reads these numbers from this file.
NOBODY_START = ((-6.35, -4.95, 2.08), -26.0, 50.0, 22.0)    # pos, pitch (deg, - looks down), yaw (deg from +X), lens
NOBODY_END = ((-6.35, -4.95, 2.48), -32.0, 50.0, 22.0)


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


def seat_at(a, chair, t0, until):
    """As seat(), from time t0 (a cut): the end of Stand_To_Sit on `chair`, then Sitting_Idle to `until`."""
    name = "Stand_To_Sit"
    c = aj_clips.require(name)
    top = furnish.tops(chair)[0][1]
    bd = aj_clips.body(a)
    clip_seat = (c["analysis"]["hips_end_per_leg"] - aj_clips.SEAT_UNDER) * bd.leg
    dz = (top - 0.0) / a.scale - clip_seat
    aj_clips.play(a, name, t0, start=c["duration_s"] - 0.04, blend=0.0, state="sitting", hips_dz=lambda f, u, dz=dz: dz)
    a.do("sit_idle", t=t0 + 0.04, until=until)


def head_bobs(a, t0, t1, base=12.0, seed=1):
    """Head down over the work, with small nods now and then (a reader's or a typist's rhythm, not a statue)."""
    rnd = random.Random(seed)
    a.tilt_head(base, t0, 0.0)
    t = t0 + rnd.uniform(0.6, 1.4)
    while t < t1 - 0.4:
        a.tilt_head(base + rnd.uniform(3.0, 7.0), t, 0.25)
        a.tilt_head(base + rnd.uniform(-2.0, 1.0), t + 0.45, 0.3)
        t += rnd.uniform(1.3, 2.4)


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
    fmon = next(o for o in S["monitors"] if o.location.z > 1.0)
    fmon.location.x, fmon.location.y = FRONT_MONITOR_AT

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
    rec = cast.from_plan("receptionist", at=REC_AT, face="left")
    w1 = cast.from_plan("worker_1", at=(-1.0, -1.75, 0.0), face="right")
    w2 = cast.from_plan("worker_2", at=(-2.9, -4.55, 0.0), face="left")
    x1 = cast.from_plan("extra_1", at=(0.9, -1.75, 0.0), face="right")         # seated typist, mid row
    x2 = cast.from_plan("extra_2", at=(-3.88, 0.98, 0.0), face="right")        # standing at the north row, head down over a printout
    x3 = cast.from_plan("extra_3", at=(-5.75, 0.45, 0.0), face="left")         # standing in the middle aisle, on the phone (strolls only)
    x4 = cast.from_plan("extra_4", at=(-2.9, 1.05, 0.0), face="right")         # seated typist, north row
    x5 = cast.from_plan("extra_5", at=(-1.0, 1.05, 0.0), face="right")         # seated typist, north row
    x6 = cast.from_plan("extra_6", at=(-2.6, -0.1, 0.0), face="left")          # the intern with a mug, crossing in strolls; then at his desk
    x7 = cast.from_plan("extra_7", at=(-1.95, 0.98, 0.0), face="right")        # standing at the north row, head down on her phone
    st.heading(90.0, 0.0, turn=0.0)
    rec.heading((NOTES_AT[0], NOTES_AT[1]), 0.0, turn=0.0)      # toward her notes on the counter: profile to the waves camera
    for w in (w1, w2, x1, x4, x5):
        w.heading(180.0, 0.0, turn=0.0)
    for w, hd in ((x2, 190.0), (x7, 168.0), (x3, 330.0)):
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
    bag_d.rotation_euler.z = math.radians(BAG_YAW)
    bpy.context.view_layer.update()
    flap = furnish.part(bag_d, "flap")
    if flap is None:
        flap = next((o for o in bag_d.children_recursive if o.type == "EMPTY" and "flap" in o.name.split(".")), None)
    if flap is not None:
        core.key(flap, "rotation_euler", 0.0, (math.radians(-100.0), 0.0, 0.0))
    # the bag's body is a closed block: give it a dark open mouth on top (seen while the flap is up), and lay the carry handle
    # forward, away from the mouth, so the laptop goes in between its ends instead of through it
    body_e = next((o for o in bag_d.children_recursive if o.type == "EMPTY" and "body" in o.name.split(".")), None)
    bpy.context.view_layer.update()

    def ztop(o):
        return max((o.matrix_world @ Vector(c)).z for c in o.bound_box)
    strap = max((o for o in bag_d.children_recursive if o.type == "MESH"), key=ztop)
    body_meshes = [o for o in (body_e.children if body_e is not None else []) if o.type == "MESH" and o is not strap]
    bag_top = max(ztop(o) for o in body_meshes) if body_meshes else desk_top + 0.27
    mouth = build.box("bag_mouth", (0.345, 0.088, 0.0012), (0, 0, 0), surface="painted_wall", tint="#120C08", bevel=0.0)
    bc = bag_d.matrix_world.translation
    mouth.matrix_world = Matrix.Translation(Vector((bc.x, bc.y, bag_top + 0.0003))) @ Matrix.Rotation(math.radians(BAG_YAW), 4, "Z")
    bpy.context.view_layer.update()
    wmm = mouth.matrix_world.copy()
    mouth.parent = bag_d
    mouth.matrix_parent_inverse = bag_d.matrix_world.inverted()
    mouth.matrix_world = wmm
    cast_prop(mouth)
    if body_e is not None and strap is not None:
        piv = core.empty("bag_handle_pivot", (0, 0, 0), size=0.02)
        piv.parent = body_e
        piv.matrix_parent_inverse.identity()
        piv.location = (0.0, 0.0, 0.2)
        bpy.context.view_layer.update()
        wm = strap.matrix_world.copy()
        strap.parent = piv
        strap.matrix_parent_inverse = piv.matrix_world.inverted()
        strap.matrix_world = wm
        piv.rotation_euler = (math.radians(52.0), 0.0, 0.0)          # + about X tips it toward the bag's front (local -Y)
        shot.notes.append(f"desk bag: handle {strap.name} laid forward 52 deg; mouth at z {bag_top:.3f}")
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
    # his fingers on the closed laptop's front edge, toward him once it is turned into the bag (local +X ends up facing south)
    grip = point_on(laptop, ((lo.x + hi.x) / 2 + 0.08, lo.y + 0.01, hi.z - 0.004), "laptop_grip")
    yaw = laptop.rotation_euler.z
    cl = (lo + hi) / 2

    def lap_loc(rx_deg, x, y, z_bottom, yaw_deg=None):
        """Where the laptop's origin goes for a tilt rx about its own X and its lowest point at z_bottom (origin at x, y)."""
        yw = yaw if yaw_deg is None else math.radians(yaw_deg)
        R = Matrix.Rotation(yw, 3, "Z") @ Matrix.Rotation(math.radians(rx_deg), 3, "X")
        zs = [(R @ Vector((cx, cy, cz))).z for cx in (lo.x, hi.x) for cy in (lo.y, hi.y) for cz in (lo.z, hi.z)]
        return Vector((x, y, z_bottom - min(zs)))

    def lap_centred(rx_deg, yaw_deg, cx, cy, z_bottom):
        """The origin that puts the laptop's middle over (cx, cy), lowest point at z_bottom: it goes down the bag's own axis."""
        R = Matrix.Rotation(math.radians(yaw_deg), 3, "Z") @ Matrix.Rotation(math.radians(rx_deg), 3, "X")
        off = R @ cl
        v = lap_loc(rx_deg, 0.0, 0.0, z_bottom, yaw_deg)
        return Vector((cx - off.x, cy - off.y, v.z))

    bag_in = desk_top + 0.022
    t_s0 = t_l1 + 0.08
    t_s1 = t_into - 0.05                        # tipped up on its back edge
    t_s2 = t_into + 0.3                          # vertical, turned square to the bag, held over its mouth
    t_s3 = t_into + 0.42
    t_s4 = t_bag - 0.38                          # down inside
    lap0 = Vector(laptop.location)
    keys = [
        (t_s0, lap0, 0.0, math.degrees(yaw)),
        (t_s1, lap_loc(-48.0, lap0.x + 0.04, lap0.y + 0.02, desk_top + 0.002), -48.0, math.degrees(yaw) + 20.0),
        (t_s2, lap_centred(-90.0, BAG_YAW, BAG_AT[0] - 0.03, BAG_AT[1], bag_top + 0.05), -90.0, BAG_YAW),
        (t_s3, lap_centred(-90.0, BAG_YAW, BAG_AT[0], BAG_AT[1], bag_top + 0.03), -90.0, BAG_YAW),
        (t_s4, lap_centred(-90.0, BAG_YAW, BAG_AT[0], BAG_AT[1], bag_in), -90.0, BAG_YAW),
    ]
    for t, loc, rx, yw in keys:
        core.key(laptop, "location", t, tuple(loc))
        core.key(laptop, "rotation_euler", t, (math.radians(rx), 0.0, math.radians(yw)))
    st.hand("R", "grip", t_s0, 0.06)
    f = shot.f(t_l1)
    while f <= shot.f(t_s4):
        st.reach("R", grip, f / shot.fps, 1.0 / shot.fps)
        f += 1
    st.lean(18, t_s2, 0.3)
    t_rel = t_s4 + 0.06
    st.hand("R", "open", t_rel, 0.06)
    for k in [laptop, *laptop.children_recursive]:              # all the way inside the bag's block: gone from view
        core.show(k, t_s4 + 0.05, False)
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
        core.show(mouth, t_c1 - 0.04, False)                        # the flap covers the mouth
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
    # the wave: a relaxed half-wave in passing. Eyes and head to her, an easy smile, the left forearm up to shoulder height, palm
    # out, two small beats, and down again as he walks on (a man who belongs here, not a greeting)
    t_w0 = t_waved - 0.15
    st.eyes(-0.8, -0.15, t_w0 - 0.25, 0.15)
    st.head_turn(-0.4, t_w0 - 0.1, 0.25)
    st.expr("happy", t_w0 - 0.1, 0.15, amount=0.75)
    st.hand("L", "open", t_w0, 0.1)
    st.arm("L", 62, 112, t_w0 + 0.28, 0.28, plane="out")
    tt = t_w0 + 0.28
    for i in range(2):
        tt += 0.17
        st._wag("L", 10 if i % 2 == 0 else -8, tt, 0.17)
    st._wag("L", 0, tt + 0.14, 0.12)
    st.arm("L", 6, 18, tt + 0.5, 0.32)
    st.head_turn(0.0, tt + 0.4, 0.3)
    st.eyes(0.2, -0.05, tt + 0.35, 0.15)
    t_out = st.walk(max(t_p + 0.05, tt - 0.35), to=(DOOR[0] - 0.7, DOOR[1]), speed=2.8, arms=False)
    shot.notes.append(f"wave {t_w0:.2f}-{tt:.2f}s; through the door at {t_out:.2f}s")
    # the receptionist: the whole shot at her counter, the phone at her right ear (the palm a little off the ear, so hand and phone
    # sit outside the bob, not in it), head bowed, eyes on the notes under her left hand. When he waves she lifts two fingers off
    # the page without looking up, and goes on writing. She is the same in nobody: nobody looked up.
    phone = assets.use("prop_smartphone", name="rec_phone", at=(0, 0, 0))
    cast_prop(phone)
    own(rec, phone)
    rec.tilt_head(13, 0.0, 0.0)
    rec.lean(6, 0.0, 0.0)
    rec.hold(phone, "R", 0.0)
    rec.pose({"R": ("to", "beside_face", 0.045, -0.085), "hands": {"R": "fist"}}, 0.0, 0.0)
    rec.eyes(0.15, -0.9, 0.0, 0.0)
    rec.expr("neutral", 0.0, 0.0)
    rec.speak("He", "out")
    pad = build.box("rec_notepad", (0.15, 0.21, 0.006), (NOTES_AT[0] - 0.01, NOTES_AT[1] + 0.03, 1.06), surface="painted_wall",
                    tint="#F3EFD8", rot_z=-12.0, bevel=0.0)
    pad.data.materials.clear()
    pad.data.materials.append(mat.solid("#F3EFD8", 0.7))
    pad["sk_type"] = "papers_stack"
    pad["sk_on"] = S["front_desk"].name
    notes = Vector((NOTES_AT[0], NOTES_AT[1], 1.075))
    rec.hand("L", "pinch", 0.0, 0.0)
    rec.reach("L", notes, 0.0, 0.0)
    rnd_w = random.Random(4)
    t_lift = t_waved + 0.4
    tw = 0.25
    while tw < t_end - 0.2:                                      # small writing strokes, except while the fingers are up
        if not (t_lift - 0.3 < tw < t_lift + 0.75):
            rec.reach("L", notes + Vector((rnd_w.uniform(-0.03, 0.03), rnd_w.uniform(-0.015, 0.015), 0.0)), tw, 0.12)
        tw += rnd_w.uniform(0.22, 0.36)
    rec.hand("L", "point", t_lift - 0.05, 0.1)
    rec.reach("L", notes + Vector((0.0, -0.03, 0.11)), t_lift, 0.18)
    rec.reach("L", notes, t_lift + 0.55, 0.2)
    rec.hand("L", "pinch", t_lift + 0.55, 0.12)
    head_bobs(rec, 0.3, t_end, base=13.0, seed=11)
    for b in (1.3, 4.1, 6.4, 8.3):
        rec.blink(b)

    # ---------------------------------------------------------------- the floor: heads down, the whole time
    def chair_at(x, y):
        for o in bpy.data.objects:
            if o.get("sk_type") == "chair_office":
                p = o.matrix_world.translation
                if abs(p.x - x) < 0.12 and abs(p.y - y) < 0.12:
                    return o
        return None
    # w2 moves at the cut to nobody (time compressed) from the first row, which the high corner does not see, to a chair added at the
    # west desk of the middle row, under its monitor (shown from the cut to into_bag on, so strolls keeps its clear lane)
    ch_w2b = furnish.chair_office(at=(-5.1, -2.0, 0.0), rot_z=180, color="#3A4A5A")
    ch_w2b["sk_layer"] = "mid"
    for k in [ch_w2b, *ch_w2b.children_recursive]:
        core.show(k, 0.0, False)
        core.show(k, t_slid, True)
    seated = [  # actor, chair (x, y), keyboard (x, y), seed, from
        (w1, (-1.0, -2.06), (-1.0, -1.0), 3, 0.0),
        (x1, (0.9, -2.06), (0.9, -1.0), 9, 0.0),
        (w2, (-2.9, -4.86), (-2.9, -3.8), 5, 0.0),
        (x4, (-2.9, 0.74), (-2.86, 1.8), 13, 0.0),
        (x5, (-1.0, 0.74), (-0.97, 1.8), 17, 0.0),
    ]
    for w, (cx, cy), (kx, ky), seed, t0 in seated:
        ch = chair_at(cx, cy)
        if ch is not None:
            seat(w, ch, t_end)
            w.floating = True                                   # seated: the chair seat carries them, not the floor under the stage
        else:
            shot.notes.append(f"{w.cid if hasattr(w, 'cid') else w}: no chair at {cx, cy}, standing")
        t1 = t_nobody - 0.05 if w is w2 else t_end
        typing(w, kx, ky, 0.76, t0, t1, seed=seed)
        w.eyes(0.0, -0.45, 0.0, 0.0)
        w.expr("neutral", 0.0, 0.0)
        head_bobs(w, 0.0, t_end, base=9.0, seed=seed + 1)
    # w2 at the middle row's west desk for nobody
    w2.place((-5.1, -1.69, 0.0), t_nobody)
    typing(w2, -5.1, -1.0, 0.76, t_nobody, t_end, seed=6)
    # the intern: crosses behind the stranger in strolls with his mug, then (from the cut to into_bag) at his own desk, typing
    mug = furnish.make("mugs", at=(0, 0, 0), count=1, seed=2)
    cast_prop(mug)
    x6.hold(mug, "R", 0.0, offset=(0.0, 0.0, 0.0))
    own(x6, mug)
    x6.arm("R", 30, 95, 0.0, 0.0)
    x6.arm("L", 8, 22, 0.0, 0.0)
    x6.eyes(0.0, -0.4, 0.0, 0.0)
    x6.walk(0.0, to=(-4.7, -0.1), speed=1.8, arms=False)
    x6.release(mug, t_slid - 0.04)
    for k in [mug, *mug.children_recursive]:
        core.show(k, t_slid, False)
    x6.place((-4.8, 1.05, 0.0), t_slid)
    x6.heading(180.0, t_slid, turn=POP)
    ch6 = chair_at(-4.8, 0.74)
    if ch6 is not None:
        seat_at(x6, ch6, t_slid, t_end)
        x6.floating = True
    typing(x6, -4.76, 1.8, 0.76, t_slid, t_end, seed=21)
    x6.eyes(0.0, -0.45, t_slid, 0.0)
    head_bobs(x6, t_slid, t_end, base=9.0, seed=22)
    # a standing reader, head bowed over the printout
    pr = printout("printout_0")
    cast_prop(pr)
    own(x2, pr)
    x2.do("read", pr, t=0.0, until=t_end)
    x2.expr("neutral", 0.0, 0.0)
    head_bobs(x2, 0.5, t_end, base=16.0, seed=31)
    # head down on her phone, the other arm easy
    x7_phone = assets.use("prop_smartphone", name="x7_phone", at=(0, 0, 0))
    cast_prop(x7_phone)
    own(x7, x7_phone)
    x7.do("phone", x7_phone, t=0.0, until=t_end, side="R", screen=True)
    x7.arm("L", 10, 38, 0.0, 0.0)
    x7.expr("neutral", 0.0, 0.0)
    head_bobs(x7, 0.8, t_end, base=18.0, seed=41)
    # (strolls only) on the phone in the middle aisle, behind him
    x3_phone = assets.use("prop_smartphone", name="x3_phone", at=(0, 0, 0))
    cast_prop(x3_phone)
    own(x3, x3_phone)
    x3.do("phone", x3_phone, t=0.0, until=t_end, side="L")
    x3.expr("happy", 0.0, 0.0, amount=0.3)
    x3.speak("he", "cubicles")
    x3.eyes(0.4, -0.5, 0.0, 0.0)
    x3.arm("R", 12, 40, 0.0, 0.0)
    for a, bl in ((w1, (0.9, 5.2)), (w2, (2.2, 6.8)), (x1, (1.6, 7.4)), (x2, (2.9, 7.9)), (x3, (3.4,)), (x4, (1.1, 7.0)),
                  (x5, (4.4, 8.4)), (x7, (2.0, 6.1))):
        for b in bl:
            a.blink(b)
    x6.blink(3.1)
    x6.blink(7.7)

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

    # waves: past her right shoulder at the end of the counter, level and a little down (the ceiling stays a strip); she is at the
    # left edge in profile, he passes beyond the counter and waves; the camera pans with him to the open west door
    w_pos = Vector((-5.08, -4.78, 1.46))
    rs = Vector((REC_AT[0], REC_AT[1], 0.0))
    hp = Vector((rs.x, rs.y, 1.45))
    wp = Vector((WAVE_AT[0], WAVE_AT[1], 1.55))
    def az(v):
        return math.atan2(v.y - w_pos.y, v.x - w_pos.x)
    yaw0 = 0.42 * az(hp) + 0.58 * az(wp)                        # her at the left edge, where he waves right of centre
    a0 = w_pos + Vector((math.cos(yaw0), math.sin(yaw0), math.tan(math.radians(-5.0)))) * 2.0
    cam.view("waves", t_he, pos=tuple(w_pos), aim=tuple(a0), lens=28, size="medium",
             why="past her shoulder, on the phone, eyes on her notes: he waves like he belongs, she does not look up")
    door_aim = Vector((DOOR[0], DOOR[1] - 0.05, 1.2))
    t_pan0 = min(tt - 0.25, t_nobody - 1.25)
    # the pan rises a little as it turns so the line to the door passes over her counter monitor
    cam.move(t_pan0, t_nobody - 0.04, pos=tuple(w_pos + Vector((0.1, 0.04, 0.3))), aim=tuple(door_aim), lens=30, ease="SINE")
    d0 = (a0 - w_pos)
    d1 = (door_aim - w_pos)
    pan = math.degrees(math.atan2(d1.y, d1.x) - math.atan2(d0.y, d0.x))
    shot.notes.append(f"waves pan {pan:.1f} deg {t_pan0:.2f}-{t_nobody:.2f}s")

    # nobody: high over the front desk in the south-west corner, looking down over the floor; it rises while it tilts further down,
    # so the floor of bowed heads opens up over the counter (the receptionist is the low near figure at the bottom)
    def aim_of(pos, pitch, yaw_deg):
        p = math.radians(pitch)
        yw = math.radians(yaw_deg)
        return tuple(Vector(pos) + Vector((math.cos(yw) * math.cos(p), math.sin(yw) * math.cos(p), math.sin(p))) * 6.0)

    (n0p, n0pitch, n0yaw, n0lens), (n1p, n1pitch, n1yaw, n1lens) = NOBODY_START, NOBODY_END
    cam.view("nobody", t_nobody, pos=n0p, aim=aim_of(n0p, n0pitch, n0yaw), lens=n0lens, size="wide",
             why="the result is invisible: a full floor, heads down, not one turned; his coffees by the empty spot on the desk")
    cam.move(t_nobody + 0.05, t_end - 0.05, pos=n1p, aim=aim_of(n1p, n1pitch, n1yaw), lens=n1lens, ease="QUAD")
    shot.notes.append(f"nobody: rise {n1p[2] - n0p[2]:.2f} m, tilt {n0pitch:.0f} -> {n1pitch:.0f} deg; end pose {NOBODY_END}")

    shot.subject("stranger", st.head, moments=["strolls", "waves.a", "wave"])
    # (in into_the_bag the laptop is half inside the bag, so each hides the other by design: not checked there)
    shot.subject("laptop", laptop, moments=["into_bag.a", "lid_shut"])
    # the bag is read from its west face (toward this camera): its centre is behind the laptop once the laptop is inside it
    bag_face = core.empty("bag_west_face", (BAG_AT[0] - 0.065, BAG_AT[1], desk_top + 0.13), size=0.03)
    bag_face.hide_render = True
    shot.subject("bag", bag_face, moments=["into_bag.b", "into_the_bag"])
    shot.subject("receptionist", rec.head, moments=["waves.a", "wave", "nobody"])
    door_pt = core.empty("west_door_pt", (DOOR[0] + 0.15, DOOR[1], 1.5), size=0.05)
    door_pt.hide_render = True
    shot.subject("west_door", door_pt, moments=["waves.b"])
    shot.subject("coffees", carrier_d, moments=["nobody"])
    shot.moment("lid_shut", t_l1 + 0.05)
    shot.moment("into_the_bag", (t_s3 + t_s4) / 2)
    shot.moment("wave", t_w0 + 0.55)
