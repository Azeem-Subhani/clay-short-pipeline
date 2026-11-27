"""sh05 - the damage, that same night: in a dark room across the city the stolen laptop lies open beside the stranger's brown leather bag,
its screen a list of client folders under CLIENTS (200); on the monitor beside it the same files are lots on an auction page whose prices tick up.

Views (plan): records (seated eye height, close: the open bag sharp in the near left, the focus racks to the laptop screen on "that single
laptop", and a slow push carries "private financial records for two hundred major clients") -> auction (the push runs straight on into a truck
right from the laptop to the monitor: the auction page, the prices stepping up on "every file ... up for auction").

Staging notes:
  * Nobody is in the room (the plan's cast is empty): the thief is never seen.
  * The set's monitor shows the auction page at step 0. The price ticks are extra copies of its screen quad, each with its own material and the
    set's screen_picture("auction", step), popped in one after another (an image node cannot be keyed).
  * The shot enters on a dip to dark: frame one is already composed on the bag.
  * Fix round 1 (frame-reviewer): the bag (the same messenger_bag he carries in sh02-sh04) is turned so its lifted flap with the brass buckle
    and the open, empty mouth face the lens; its shoulder strap is laid down flat behind it instead of arching over the frame; a small warm
    kick picks out the leather. No cut between records and auction: one spline move pushes in on the laptop and runs on, without stopping,
    into the truck to the monitor (the auction view begins mid-move on "Before dinner"). The monitor (with its keyboard and cables) slides
    20 cm toward the laptop for this shot so the truck crosses no bare wall; a phone propped on the papers in the gap lights up with
    notifications as the bids come in. A cool shot fill on the back wall keeps the room deep blue; the orange is left to the street shaft.
  * Fix round 2 (final-film review: the room read pink-mauve): night_grade() turns the set's orange bag spill off, the violet LED strip
    down to a faint blue, the fills and the sky to a deep navy; the screens are the brightest, coolest things; one warm streetlight spot
    from the window side slants across the desk, and its bounce picks the bag's leather out in brown.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

import set_dim_room as sp
from stagekit import arch, camera, core, furnish, mat

MONITOR_SHIFT = -0.20                  # metres along x: the monitor (and its keyboard, cables) toward the laptop, for this shot only
BAG_AT, BAG_ROT, BAG_FLAP = (-1.2, 2.66), 152.0, 150.0     # the bag turned so its lifted flap and open mouth face the lens


def screen_centre(piece):
    s = furnish.screen(piece)
    lo, hi = core.world_bbox([s])
    return (lo + hi) / 2


def piece_box(piece):
    """World bbox of a kit piece (its root is an empty: measure its meshes)."""
    obs = [o for o in [piece, *piece.children_recursive] if o.type == "MESH" and not o.hide_render]
    return core.world_bbox(obs)


def marker(name, at):
    e = core.empty(name, tuple(at), size=0.02)
    e.hide_render = True
    return e


def price_steps(monitor, times):
    """Pop in a fresh copy of the monitor's screen for each price step (step k at times[k-1])."""
    base = furnish.screen(monitor)
    prev = base
    for k, t in enumerate(times, start=1):
        ob = base.copy()
        ob.animation_data_clear()                            # a copy shares the original's action: give it its own keys
        ob.data = base.data.copy()
        m = base.data.materials[0].copy()
        m.node_tree.nodes["image"].image = sp.screen_picture("auction", k)
        ob.data.materials[0] = m
        for c in base.users_collection:
            c.objects.link(ob)
        ob.name = f"{base.name}.step{k}"
        core.show(ob, 0.0, False)
        core.show(ob, t, True)
        core.show(prev, t, False)
        prev = ob


def area_light(name, at, target, energy, color, size=0.4):
    lt = bpy.data.lights.new(name, "AREA")
    lt.size, lt.energy, lt.use_shadow = size, energy, False
    lt.color = core.hex_rgba(color)[:3]
    ob = bpy.data.objects.new(name, lt)
    core.link(ob, "LIGHTS")
    ob.location = at
    ob.rotation_euler = (Vector(target) - Vector(at)).to_track_quat("-Z", "Y").to_euler()
    return ob


def night_grade(bag_pt):
    """Shot-level relight of the set's office_night rig for this close: the orange bag spill off, the violet LED strip down to a faint deep
    blue, the room fill a darker navy, the screen glows kept; a narrow warm 'streetlight' spot from the window side (high, right, outside
    the frame) laid across the desk so the bag's leather reads brown in a slanted beam while the wall behind stays navy."""
    for o in bpy.data.objects:
        if o.type != "LIGHT":
            continue
        d = o.data
        if o.name.startswith("SPILL_bag"):
            d.energy = 0.0
        elif o.name == "led" or o.name.startswith("led") and d.type == "AREA":
            d.energy = 2.0
            d.color = (0.12, 0.2, 1.0)
        elif o.get("sk_role") == "fill" and o.name.startswith("FILL"):
            d.energy = 6.0
            d.color = (0.16, 0.24, 0.75)
        elif o.name == "KEY_street":
            d.energy = 4.0
    w = bpy.context.scene.world
    if w is not None and w.use_nodes:
        for n in w.node_tree.nodes:
            if n.type == "BACKGROUND":
                n.inputs["Strength"].default_value = 0.03
    # the streetlight shaft: a narrow, fairly hard-edged spot from the window side, slanting down across the desk top in front of the
    # screens (aimed away from the back wall, so the wall stays navy)
    sp_d = bpy.data.lights.new("STREET_beam", "SPOT")
    sp_d.energy, sp_d.spot_size, sp_d.spot_blend, sp_d.shadow_soft_size = 120.0, math.radians(20.0), 0.2, 0.04
    sp_d.color = core.hex_rgba("#FF7428")[:3]
    sp_d.use_shadow = True
    so = bpy.data.objects.new("STREET_beam", sp_d)
    core.link(so, "LIGHTS")
    so.location = (1.1, 2.95, 1.85)                                   # just inside the window (north wall, right of the desk), high
    tgt = Vector((-0.45, 2.62, 0.74))
    so.rotation_euler = (tgt - Vector(so.location)).to_track_quat("-Z", "Y").to_euler()
    # the beam's spill off the desk top, low and tight on the bag's face toward the lens (shadowed, so the wall behind the bag stays navy)
    k_d = bpy.data.lights.new("STREET_bounce_bag", "SPOT")
    k_d.energy, k_d.spot_size, k_d.spot_blend, k_d.shadow_soft_size = 30.0, math.radians(30.0), 0.6, 0.1
    k_d.color = core.hex_rgba("#FF8A3A")[:3]
    k_d.use_shadow = True
    ko = bpy.data.objects.new("STREET_bounce_bag", k_d)
    core.link(ko, "LIGHTS")
    ko.location = (bag_pt.x + 0.45, bag_pt.y - 0.6, bag_pt.z + 0.12)
    ko.rotation_euler = (Vector(bag_pt) - Vector(ko.location)).to_track_quat("-Z", "Y").to_euler()
    return so


def restage_bag(bag):
    """Turn the bag so its flap and open mouth face the lens, take the arched shoulder strap away and lay a strap flat on the desk behind it."""
    bag.location.x, bag.location.y = BAG_AT
    bag.rotation_euler.z = math.radians(BAG_ROT)
    furnish.part(bag, "flap").rotation_euler.x = math.radians(-BAG_FLAP)
    strap_mat = None
    for c in bag.children_recursive:
        if c.type == "MESH" and c.name.endswith("body.4"):          # the shoulder strap arch (14 rods)
            strap_mat = c.data.materials[0]
            c.hide_render = c.hide_viewport = True
    core.at_frame(1)
    body = next(c for c in bag.children_recursive if c.get("sk_part") == "body") if any(c.get("sk_part") == "body" for c in bag.children_recursive) else bag
    # the strap, lying slack on the desk behind the bag (local -Y is the side away from the lens once turned): from one side gusset, down,
    # a loose loop on the desk, up to the other
    loc = [(-0.215, 0.0, 0.09), (-0.24, -0.04, 0.03), (-0.21, -0.11, 0.009), (-0.08, -0.155, 0.009), (0.07, -0.165, 0.009), (0.2, -0.12, 0.009),
           (0.24, -0.045, 0.03), (0.215, 0.0, 0.09)]
    mw = bag.matrix_world
    pts = [mw @ Vector(p) for p in loc]
    cb = arch.Parts("bag_strap_down", "SET", None, kind="prop")
    m = strap_mat or mat.solid("#3E2814", 0.5)
    for a_, b_ in zip(pts, pts[1:]):
        cb.rod(tuple(a_), tuple(b_), 0.009, m, seg=6)
    so = cb.build(at=(0, 0, 0), recentre=False)
    for k_ in [k for k in so.keys() if k.startswith("sk_")]:
        del so[k_]
    w = so.matrix_world.copy()
    so.parent = body
    so.matrix_world = w
    return so


def slide_monitor(monitor, dx):
    monitor.location.x += dx
    for o in bpy.data.objects:
        if o.parent is None and o.name.startswith("cable_monitor"):
            o.location.x += dx


def phone_picture():
    """A phone's lock screen lit by a stack of bid notifications: dark blue ground, three white cards with green and red tags."""
    W, H = 128, 276
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.05, 0.08, 0.16)
    sp._text(img, "21:14", 26, 22, 3, (0.9, 0.93, 1.0))
    for k in range(3):
        y0 = 80 + k * 58
        img[y0:y0 + 48, 8:W - 8] = (0.9, 0.92, 0.95)
        img[y0 + 8:y0 + 22, 16:40] = (0.92, 0.7, 0.2)
        img[y0 + 28:y0 + 40, 16:84] = (0.12, 0.55, 0.28) if k != 1 else (0.75, 0.18, 0.15)
        sp._text(img, "BID", 46, y0 + 9, 2, (0.15, 0.17, 0.2))
    img = img[::-1]
    rgba = np.ones((H, W, 4), np.float32)
    rgba[..., :3] = img
    im = bpy.data.images.new("SK_phone_bids", W, H, alpha=False)
    im.colorspace_settings.name = "Non-Color"
    im.pixels.foreach_set(rgba.ravel())
    try:
        im.pack()
    except Exception:
        pass
    return im


def phone_in_gap(papers, times):
    """A phone propped on the papers in the gap between laptop and monitor; its screen dark until the first bid, then a pulse per bid."""
    pz = piece_box(papers)[1].z
    ph = furnish.make("smartphone", at=(-0.42, 2.55, pz), rot_z=-14)
    ph["sk_on"] = papers.name
    scr = furnish.screen(ph)
    nt = scr.data.materials[0].node_tree
    nt.nodes["image"].image = phone_picture()
    g = nt.nodes["gain"].inputs["Strength"]
    sh = core.current()
    keys = [(1, 0.03), (sh.f(times[0]) - 1, 0.03)]
    for t in times:
        f = sh.f(t)
        keys += [(f, 2.4), (f + 3, 1.3)]
    for f, v in sorted(set(keys)):
        g.default_value = v
        g.keyframe_insert("default_value", frame=f)
    for c in core.fcurves(nt):
        for kp in c.keyframe_points:
            kp.interpolation = "CONSTANT"
    glow = area_light("GLOW_phone", (-0.42, 2.47, 0.83), (-0.42, 2.0, 0.9), 0.0, "#BFD4FF", size=0.08)
    for f, v in sorted(set(keys)):
        glow.data.energy = v * 0.6
        glow.data.keyframe_insert("energy", frame=f)
    return ph


def hermite(keys, t):
    """keys: [(t, value)], value a Vector or float; a C1 spline through them (zero speed at both ends, Catmull-Rom tangents inside)."""
    ts = [k[0] for k in keys]
    if t <= ts[0]:
        return keys[0][1]
    if t >= ts[-1]:
        return keys[-1][1]
    i = max(j for j in range(len(ts) - 1) if ts[j] <= t)
    (t0, p0), (t1, p1) = keys[i], keys[i + 1]

    def tan(j):
        if j == 0 or j == len(keys) - 1:
            return p0 * 0.0
        (ta, pa), (tb, pb) = keys[j - 1], keys[j + 1]
        return (pb - pa) / (tb - ta)
    m0, m1 = tan(i), tan(i + 1)
    h = t1 - t0
    u = (t - t0) / h
    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    return p0 * h00 + m0 * (h10 * h) + p1 * h01 + m1 * (h11 * h)


def build_shot(shot):
    S = sp.build_set("office_night")
    monitor, laptop, bag = S["monitor"], S["laptop"], S["bag"]
    slide_monitor(monitor, MONITOR_SHIFT)
    restage_bag(bag)
    papers = next((o for o in bpy.data.objects if o.get("sk_type") == "papers_stack" and o.parent is None
                   and abs(o.matrix_world.translation.y - 2.62) < 0.1), None)
    core.at_frame(1)

    # --- words -> times
    t_that = shot.t("that single")
    t_laptop = shot.t("laptop", edge="end")
    t_clients = shot.t("clients.", edge="end")
    t_before = shot.t("Before dinner")
    t_every = shot.t("every file")
    t_file = shot.t("file")
    t_up = shot.t("up for")
    t_auction = shot.t("auction")
    t_end = shot.seconds

    lap = screen_centre(laptop)
    mon = screen_centre(monitor)
    lo, hi = piece_box(bag)
    bag_pt = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + 0.17))
    shot.notes.append(f"bag box {tuple(round(v, 2) for v in lo)} - {tuple(round(v, 2) for v in hi)}")
    shot.notes.append(f"laptop screen {tuple(round(v, 2) for v in lap)}, monitor screen {tuple(round(v, 2) for v in mon)}, bag {tuple(round(v, 2) for v in bag_pt)}")

    # --- light for this shot (fix round 2: the room read pink-mauve: the set's orange bag spill and violet LED strip mixed with the blue fill
    # on the warm-grey wall). Now it is dark: deep navy shadow, the two screens the brightest and coolest things, and one warm streetlight
    # beam from the window side the only other source, raking low across the desk and catching the leather of the bag.
    night_grade(bag_pt)
    area_light("FILL_cool_wall", (-0.3, 1.9, 2.1), (-0.4, 3.4, 1.3), 30.0, "#2A3F9A", size=1.4)

    # --- the prices tick up on the auction words; the phone in the gap lights up with them
    steps = [t_every - 0.05, t_file + 0.1, t_up, t_auction + 0.1]
    price_steps(monitor, steps)
    if papers is not None:
        phone_in_gap(papers, [t_before + 0.15] + steps)

    cam = camera.Camera()

    # records: seated eye height in front of the desk at 40 mm: the open bag big in the near left, the laptop screen beyond it on the right
    lens = 40.0
    r_pos = Vector((-1.0, 1.72, 1.2))
    r_aim = bag_pt.lerp(lap, 0.6) + Vector((0.0, 0.0, -0.06))
    cam.view("records", 0.0, framing=camera.Framing(r_pos, r_aim, lens, fstop=1.4, focus=bag_pt), size="close",
             why="the same bag in the foreground says it is the same laptop; the screen says what it held")
    # one move: the push in on the laptop's folder rows (it lands on "clients" and keeps travelling), straight on into the truck right onto
    # the monitor's auction page, settling as the last prices tick
    k1_aim = lap + Vector((0.0, 0.0, -0.06))
    k1_pos = k1_aim + (r_pos - k1_aim).normalized() * 0.98
    k2_aim = mon + Vector((0.0, 0.0, -0.02))
    k2_pos = k2_aim + Vector((-0.07, -1.24, 0.16))
    t0, t1, t2 = 0.04, t_before, min(t_up + 0.1, t_end - 0.4)
    P = [(t0, r_pos), (t1, k1_pos), (t2, k2_pos)]
    A = [(t0, r_aim), (t1, k1_aim), (t2, k2_aim)]

    def focus_at(t):
        if t <= t_that:
            return bag_pt
        if t <= t_laptop:
            u = (t - t_that) / (t_laptop - t_that)
            return bag_pt.lerp(lap, u * u * (3 - 2 * u))
        if t <= t1:
            return lap
        u = min(1.0, (t - t1) / (t2 - t1))
        return lap.lerp(mon, u * u * (3 - 2 * u))

    def spline_build(ta, tb):
        def build(p0, f0):
            def fn(s, f):
                t = ta + s * (tb - ta)
                u = min(1.0, max(0.0, (t - t1) / (t2 - t1)))
                fs = 1.4 if t < t1 else 1.4 + (4.0 - 1.4) * u
                return camera.Pose(hermite(P, t), hermite(A, t), lens, fs, 0.0, focus_at(t))
            return fn
        return build
    cam._run("dolly", t0, t1, spline_build(t0, t1), "linear")
    cam.rack_focus(t_that, t_laptop, lap, fstop=1.4)
    cam._add_view("auction", t_before, shot.f(t_before), "insert", False,          # the view begins mid-move (no cut): the truck is its move
                  "'up for auction' seen as a listing with prices: the private files are goods now", None, None, None, False, "travel")
    cam._run("truck", t1, t2, spline_build(t1, t2), "linear")
    cam.finish()

    shot.subject("bag", bag, moments=["records.a"])
    shot.subject("laptop_screen", furnish.screen(laptop), moments=["records.b", "rack_done", "auction.a"])
    shot.subject("auction_page", marker("auction_page", mon + Vector((0.0, -0.03, 0.0))), moments=["auction.b", "prices_up"])
    shot.moment("rack_done", t_laptop + 0.1)
    shot.moment("prices_up", t_auction + 0.3)
    shot.notes.append(f"rack {t_that:.2f}-{t_laptop:.2f}s, push {t0:.2f}-{t1:.2f}s running on into the truck {t1:.2f}-{t2:.2f}s (one spline, no cut)")
