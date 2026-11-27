"""sh06 - the floor that night (office, night): sh04's last frame exactly (the high camera over the front desk looking down over the floor),
now dark and torn apart; the camera cranes down and in to a three-quarter view of investigator_1 at the victim's desk. Grim, head down, he
yanks its top drawer on "tearing", lifts out a stack of files, puts them down on the desk and goes back into the drawer with both hands,
while investigator_2, eyes on a printout, keeps pointing at the bare patch where the laptop sat. A desk lamp on the victim's desk is the key.
Cut to pulled_clip: the laptop stands at desk height in the aisle, square to the camera; the guard holds it from its right end (both hands
under the base); investigator_1 bends in at its left, glasses and moustache in profile, eyes on the screen. The lobby CCTV frame shows for a
beat, then on "ten-second lobby clip" the zoomed clip of Maya's hand on the door's pull handle, and the camera pushes in centred on her hand.

Views (plan): tearing_apart (crane down and in, landing on the drawer coming out) -> pulled_clip (insert on the screen, a push).

Staging notes:
  * The set leaves the victim's top drawer pulled out; here it starts pushed in and investigator_1 yanks it out on "tearing". The files
    are keyed in world space with the drawer, then held, then put down at FILES_DROP.
  * The coffees the stranger left in sh04 are still where sh04 put them, and the counter monitor is moved as in sh04 (continuity).
  * The screen shows assets/cctv_frame.png, then assets/cctv_frame_zoom.png (made by the sh08 builder), with the look "clean": the footage
    look is burned into the pictures. The switch is a keyed mix in the screen's material. MAYA_HAND_UV must match the zoom picture.
  * The guard is only in pulled_clip (he comes in on the cut); held figures idle with breath and blinks only (clip=None) so the idle
    clip does not drop their posed arms.
"""
import math

import bpy
from mathutils import Matrix, Vector

import set_office as sp
from stagekit import assets, build, camera, cast, core, furnish, lights

import sh04  # noqa: E402  (continuity: the opening frame, the coffees and the counter monitor are read from sh04)

POP = 1.0 / 24.0
INV1_AT = (-3.05, -1.66)            # standing at the front of the victim's desk, just east of its drawer pedestal
INV2_AT = (-1.8, -1.55)             # at the desk's east end, beyond the shoved-back chair
EMPTY_SPOT = (-3.38, -0.85, 0.76)   # where the laptop sat in sh04 (the charger cable lies there)
CARRIER_AT = sh04.CARRIER_AT
FILES_DROP = (-3.03, -1.0)          # where investigator_1 slaps the files down: on the desk, clear of the empty spot and the keyboard
SCREEN_AT = (-4.4, -2.05, 1.22)     # pulled_clip: the centre of the laptop screen the guard holds out in the aisle
MAYA_HAND_UV = (0.416, 0.420)       # Maya's hand on the door in cctv_frame_zoom.png (from the left, from the top)
SH04_END = sh04.NOBODY_END          # sh04's last frame (nobody's end pose): pos, pitch, yaw, lens


def cast_prop(ob):
    for o in [ob, *ob.children_recursive]:
        for k in ("sk_type", "sk_kind", "sk_layer", "sk_on"):
            if k in o.keys():
                del o[k]


def own(actor, ob):
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


def point_at_world(parent, world, name):
    """An empty that rides on `parent`, placed at a world point (the parent's current pose)."""
    bpy.context.view_layer.update()
    e = core.empty(name, (0, 0, 0), size=0.02)
    e.parent = parent
    e.matrix_parent_inverse.identity()
    e.location = parent.matrix_world.inverted() @ Vector(world)
    e.hide_render = True
    return e


def printout(name):
    """A few sheets of white A4, held."""
    p = build.box(name, (0.21, 0.297, 0.003), (0, 0, 0), surface="painted_wall", tint="#F6F4EE", bevel=0.0)
    for k, (dx, dy, rz) in enumerate(((0.012, -0.008, 4), (-0.01, 0.006, -3))):
        q = build.box(f"{name}_{k}", (0.21, 0.297, 0.002), (0, 0, 0), surface="painted_wall", tint="#ECE9E1", bevel=0.0)
        q.parent = p
        q.location = (dx, dy, -0.003 * (k + 1))
        q.rotation_euler = (0, 0, math.radians(rz))
    return p


def screen_switch(scr, path2, t, shot):
    """Key the screen's picture from the image it shows to `path2` at time t (a constant switch in its material)."""
    m = scr.data.materials[0].copy()
    scr.data.materials[0] = m
    nt = m.node_tree
    a = nt.nodes["image"]
    b = nt.nodes.new("ShaderNodeTexImage")
    b.image = bpy.data.images.load(str(path2), check_existing=True)
    b.image.colorspace_settings.name = "sRGB"
    b.interpolation = a.interpolation
    b.extension = a.extension
    if a.inputs["Vector"].links:
        nt.links.new(a.inputs["Vector"].links[0].from_socket, b.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    for lk in list(a.outputs["Color"].links):
        to = lk.to_socket
        nt.links.remove(lk)
        nt.links.new(mix.outputs[2], to)
    nt.links.new(a.outputs["Color"], mix.inputs[6])
    nt.links.new(b.outputs["Color"], mix.inputs[7])
    fac = mix.inputs[0]
    f = shot.f(t)
    for fr, v in ((1, 0.0), (f - 1, 0.0), (f, 1.0)):
        fac.default_value = v
        fac.keyframe_insert("default_value", frame=max(1, fr))
    if nt.animation_data and nt.animation_data.action:
        for fc in core.fcurves(nt):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    return m


def build_shot(shot):
    S = sp.build_set("office_night")
    M = S["mark"]
    dk = S["victim_desk"]
    desk_top = furnish.tops(dk)[1][1]

    # --- words -> times
    t_tear = shot.t("tearing")
    t_apart = shot.t("apart")
    t_sec = shot.t("Security")                # pulled_clip
    t_ten = shot.t("ten-second")
    t_end = shot.seconds

    # --- evidence from noon: the coffees are still on the victim's desk where he set them down
    carrier = assets.use("prop_cup_carrier", name="cup_carrier_left", at=(CARRIER_AT[0], CARRIER_AT[1], desk_top))
    carrier.rotation_euler.z = math.radians(8.0)
    cast_prop(carrier)

    # (the search is the set's own night dressing: papers on the floor, the drawer pulled out; no extra stacks on other desks, they
    #  collided with the set's mugs)

    # --- the key: the victim's own desk lamp, switched on, aimed at the drawer pedestal (a warm pool on the desk front and on his face)
    lamp = furnish.make("desk_lamp", at=(-2.32, -0.47, desk_top), rot_z=222.0, power=34.0)
    lamp["sk_layer"] = "mid"
    lamp["sk_on"] = dk.name
    kd = bpy.data.lights.new("KEY_sh06_lamp", "SPOT")
    kd.energy = 120.0
    kd.color = core.hex_rgba("#FFD9A8")[:3]
    kd.spot_size = math.radians(70)
    kd.spot_blend = 0.6
    kd.shadow_soft_size = 0.12
    ko = bpy.data.objects.new("KEY_sh06_lamp", kd)
    core.link(ko, "LIGHTS")
    ko.location = (-2.3, -0.62, desk_top + 0.42)
    ko.rotation_euler = (Vector((-3.0, -1.75, 1.15)) - Vector(ko.location)).to_track_quat("-Z", "Y").to_euler()

    # --- sh04 moved the receptionist's counter monitor to the counter's east end: same here (the opening frame is sh04's last)
    fmon = next(o for o in S["monitors"] if o.location.z > 1.0)
    fmon.location.x, fmon.location.y = sh04.FRONT_MONITOR_AT

    # --- the drawer investigator_1 yanks: the set's open top drawer, pushed in until "tearing". The files inside ride with it (keyed in
    #     the world, not parented, so his hand can take them and set them down cleanly)
    drawer = bpy.data.objects.get(f"drawer_{dk.name}_2")
    if drawer is None:
        raise RuntimeError(f"no top drawer on {dk.name}")
    length, depth = float(dk["sk_size"][0]), float(dk["sk_size"][1])
    px = dk.location.x - length / 2 + 0.3
    face = dk.location.y - depth - 0.001
    handle_w = (px, face - 0.30 - 0.03, 0.46 + 0.11)
    handle = point_at_world(drawer, handle_w, "drawer_handle")
    shut = 0.28
    t_y0, t_y1 = t_tear - 0.04, t_tear + 0.22
    core.key(drawer, "location", 0.0, (0.0, shut, 0.0))
    core.key(drawer, "location", t_y0, (0.0, shut, 0.0))
    core.key(drawer, "location", t_y1, (0.0, 0.0, 0.0))
    files = assets.use("prop_file_stack", name="client_files", at=(px, face - 0.15 + shut, 0.478))
    cast_prop(files)
    files.rotation_euler.z = math.radians(90.0)
    core.key(files, "location", 0.0, (px, face - 0.15 + shut, 0.478))
    core.key(files, "location", t_y0, (px, face - 0.15 + shut, 0.478))
    core.key(files, "location", t_y1, (px, face - 0.15, 0.478))

    # --- cast
    i1 = cast.from_plan("investigator_1", at=(INV1_AT[0], INV1_AT[1], 0.0), face="right")
    i2 = cast.from_plan("investigator_2", at=(INV2_AT[0], INV2_AT[1], 0.0), face="left")
    gd = cast.from_plan("guard", at=(-9.6, -4.4, 0.0), face="right")              # down the corridor, out of sight until the cut
    yaw_drawer = math.degrees(math.atan2(handle_w[0] - INV1_AT[0], -(handle_w[1] - INV1_AT[1])))
    i1.heading(yaw_drawer, 0.0, turn=0.0)
    i2.heading((EMPTY_SPOT[0], EMPTY_SPOT[1]), 0.0, turn=0.0)

    cam = camera.Camera()
    cam.line(i1, i2)

    # ---------------------------------------------------------------- investigator_1: three-quarters to the lens, bent to the drawer, grim;
    # yanks it on "tearing", takes the files out, slaps them down on the desk on "apart", and goes back into the drawer with both hands
    i1.expr("angry", 0.0, 0.0, amount=0.18)
    i1.eyes(0.0, -0.8, 0.0, 0.0)
    i1.lean(24, 0.0, 0.0)
    i1.tilt_head(10, 0.0, 0.0)
    i1.hand("R", "grip", 0.0, 0.0)
    i1.reach("R", handle, 0.0, 0.0)
    i1.hand("L", "open", 0.0, 0.0)
    i1.reach("L", (INV1_AT[0] - 0.02, -1.22, desk_top + 0.01), 0.0, 0.0)          # his left hand braced on the desk edge
    f = shot.f(t_tear - 0.3)
    while f <= shot.f(t_tear + 0.3):
        i1.reach("R", handle, f / shot.fps, 1.0 / shot.fps)
        f += 1
    i1.reach("R", handle, 0.6, 0.3)
    i1.lean(30, t_tear - 0.14, 0.14)                             # the wind-up
    i1.lean(14, t_tear + 0.2, 0.15)                              # the yank throws him back
    i1.squash(t_tear + 0.05, 0.04, 0.03, 0.08)
    i1.expr("angry", t_tear - 0.12, 0.08, amount=0.3)
    # into the drawer: the files out
    grab = point_on(files, (0.0, 0.0, 0.05), "files_grip")
    t_g = t_tear + 0.42
    i1.hand("R", "open", t_g - 0.14, 0.08)
    i1.lean(26, t_g, 0.2)
    i1.reach("R", grab, t_g, 0.2)
    i1.hand("R", "grip", t_g + 0.04, 0.06)
    i1.hold(files, "R", t_g + 0.08)
    i1.arm("L", 14, 42, t_g + 0.1, 0.25)
    i1.lean(12, t_g + 0.4, 0.3)
    i1.eyes(0.1, -0.6, t_g + 0.2, 0.15)
    # set down hard on the desk, on "apart"
    t_pd = t_apart - 0.5 - 0.04
    t_up = i1.do("put_down", files, to=(FILES_DROP[0], FILES_DROP[1], desk_top), t=t_pd)
    i1.hand("L", "open", t_pd + 0.3, 0.1)
    i1.lean(22, t_pd + 0.45, 0.2)                                # bent over the desk as he slaps them down
    i1.reach("L", (INV1_AT[0] - 0.22, -1.22, desk_top + 0.01), t_pd + 0.35, 0.25)        # the other hand braced on the desk
    i1.squash(t_apart + 0.02, 0.05, 0.02, 0.08)
    i1.heading(yaw_drawer, t_up, turn=0.25)                      # back to the drawer
    # both hands rummaging in the open drawer to the cut
    dr_in = Vector((px, face - 0.17, 0.52))
    i1.lean(28, t_up + 0.15, 0.25)
    i1.hand("R", "open", t_up + 0.1, 0.1)
    i1.hand("L", "open", t_up + 0.1, 0.1)
    tt = t_up + 0.2
    k = 0
    while tt < t_sec - 0.2:
        i1.reach("R", dr_in + Vector((0.07 + 0.03 * (k % 2), -0.03 * (k % 3), 0.0)), tt, 0.16)
        i1.reach("L", dr_in + Vector((-0.08, 0.04 * ((k + 1) % 2), 0.02)), tt + 0.08, 0.16)
        tt += 0.24
        k += 1
    i1.eyes(0.0, -0.8, t_up + 0.1, 0.15)
    i1.tilt_head(12, t_up + 0.1, 0.2)
    for b in (0.7, 2.6):
        i1.blink(b)

    # ---------------------------------------------------------------- investigator_2: reading a printout, then pointing at the bare patch
    sheet = printout("printout_i2")
    cast_prop(sheet)
    own(i2, sheet)
    i2.expr("neutral", 0.0, 0.0)
    i2.hold(sheet, "L", 0.0, offset=(0.06, 0.0, 0.02))
    i2.hand("L", "grip", 0.0, 0.0)
    i2.arm("L", 34, 96, 0.0, 0.0)
    i2.arm("R", 8, 26, 0.0, 0.0)
    i2.tilt_head(14, 0.0, 0.0)
    i2.eyes(0.1, -0.8, 0.0, 0.0)
    i2.eyes(0.35, -0.75, 0.5, 0.2)
    spot = core.empty("empty_spot", EMPTY_SPOT, size=0.03)
    spot.hide_render = True
    t_pt = max(0.9, t_tear - 0.35)
    i2.tilt_head(8, t_pt - 0.3, 0.25)
    i2.eyes(-0.5, -0.5, t_pt - 0.3, 0.15)
    i2.hand("R", "point", t_pt - 0.05, 0.1)
    i2.aim("R", spot, t_pt + 0.15, 0.25)
    i2.lean(6, t_pt + 0.2, 0.2)
    tt = t_pt + 0.5
    while tt < t_sec + 0.2:                                      # and she keeps her point on it to the cut
        i2.aim("R", spot, tt, 0.25)
        tt += 0.5
    i2.expr("angry", t_pt + 0.1, 0.2, amount=0.15)
    for b in (1.2, 3.1):
        i2.blink(b)

    # ---------------------------------------------------------------- pulled_clip: the guard holds the open laptop out at chest height, both
    # hands under its base, standing just behind it; investigator_1 bends in at its left to read the clip
    lap = furnish.laptop_open(at=(0, 0, 0), rot_z=0.0, image="desktop")
    cast_prop(lap)
    cctv = shot.clip_dir / "assets" / "cctv_frame.png"
    zoom = shot.clip_dir / "assets" / "cctv_frame_zoom.png"
    if not cctv.exists():
        raise FileNotFoundError(f"{cctv}: render it first (render_cctv_frame.py)")
    scr = furnish.screen_set_image(lap, str(cctv))
    furnish.screen_look(lap, "clean", gain=1.35)
    if zoom.exists():
        screen_switch(scr, zoom, t_ten - 0.04, shot)
    else:
        shot.notes.append("cctv_frame_zoom.png is missing: the screen stays on the wide frame")
    # the camera axis first (screen centre to camera), then the laptop turned square to it
    cam_dir = Vector((-0.17, -0.985, 0.0)).normalized()
    rz = math.atan2(cam_dir.x, -cam_dir.y)                      # local -Y (its front) toward the camera
    lap.rotation_euler = (0.0, 0.0, rz)
    bpy.context.view_layer.update()
    lo, hi = core.world_bbox([scr])
    c0 = (lo + hi) / 2
    lap.location = Vector(SCREEN_AT) - (c0 - lap.location)
    for k in [lap, *lap.children_recursive]:
        core.show(k, 0.0, False)
        core.show(k, t_sec, True)
    bpy.context.view_layer.update()
    lid = furnish.part(lap, "lid")
    lo, hi = core.world_bbox([scr])
    c = (lo + hi) / 2
    n = (lid.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()
    up = (lid.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    right = up.cross(n).normalized()
    sw, sh = 0.29, 0.18
    maya = c + right * ((MAYA_HAND_UV[0] - 0.5) * sw) + up * ((0.5 - MAYA_HAND_UV[1]) * sh)
    body = furnish.part(lap, "body") or lap
    bmesh_ = [o for o in body.children_recursive if o.type == "MESH"] or [o for o in lap.children_recursive if o.type == "MESH"]
    blo, bhi = core.world_bbox(bmesh_)
    base_c = (blo + bhi) / 2
    fwd = Vector((cam_dir.x, cam_dir.y, 0.0)).normalized()        # toward the camera
    side = Vector((-fwd.y, fwd.x, 0.0))                           # to the camera's right... (screen right as seen from the camera)
    if side.dot(right) < 0:
        side = -side
    # the guard: at the laptop's right, holding it out to investigator_1 by its right end, both palms up under the base (front and back
    # corners), his head turned down to the screen in profile at the right edge
    g_at = base_c + side * 0.46 - fwd * 0.02
    gd.place((g_at.x, g_at.y, 0.0), t_sec)
    gd.heading((base_c.x, base_c.y), t_sec, turn=POP)
    gd.lean(10, t_sec, POP)
    dz = Vector((0.0, 0.0, 0.5 * (bhi.z - blo.z) + 0.012))
    under_f = point_at_world(lap, base_c + side * 0.11 + fwd * 0.07 - dz, "base_under_front")
    under_b = point_at_world(lap, base_c + side * 0.13 - fwd * 0.08 - dz, "base_under_back")
    gd.hand("R", "open", t_sec, POP)
    gd.hand("L", "open", t_sec, POP)
    # facing screen-left, his right hand is on the camera's side (front), his left behind
    gd.reach("R", under_f, t_sec, POP)
    gd.reach("L", under_b, t_sec, POP)
    gd.tilt_head(14, t_sec, POP)
    gd.eyes(0.2, -0.7, t_sec, POP)                               # on the screen
    gd.eyes(0.6, -0.3, t_ten + 0.25, 0.15)                       # then at investigator_1 as the clip zooms
    gd.expr("neutral", t_sec, POP)
    gd.blink(t_sec + 0.9)
    # investigator_1: bent in at the laptop's left, his face beside the screen, eyes on the clip (time compressed at the cut)
    head_at = c + right * -0.36 + n * 0.06 + Vector((0.0, 0.0, 0.2))
    i1_at = Vector((head_at.x, head_at.y, 0.0)) - right * 0.04 - fwd * 0.12
    i1.place((i1_at.x, i1_at.y, 0.0), t_sec)
    i1.heading((c.x + side.x * 0.05, c.y + side.y * 0.05), t_sec, turn=POP)
    i1.pose("rest", t_sec, POP)
    i1.lean(14, t_sec, POP)
    i1.arm("R", 16, 70, t_sec, POP)                              # his right hand up at his chin
    i1.hand("R", "fist", t_sec, POP)
    i1.arm("L", 10, 34, t_sec, POP)
    i1.tilt_head(8, t_sec, POP)
    i1.eyes(0.6, -0.4, t_sec, POP)
    i1.expr("worried", t_sec, POP, amount=0.25)
    i1.expr("angry", t_ten + 0.2, 0.2, amount=0.22)
    i1.blink(t_sec + 1.4)
    i1.tilt_head(12, t_ten - 0.1, 0.25)                          # bows to the zoomed clip
    gd.reach("R", under_f, t_sec + 1.2, 0.4)                     # re-settle the grip now and then (the laptop stays put)
    gd.reach("L", under_b, t_sec + 1.6, 0.4)
    gd.tilt_head(10, t_ten + 0.2, 0.25)
    # the screen's light on his face
    sl = bpy.data.lights.new("FILL_sh06_screen", "AREA")
    sl.size, sl.size_y = 0.3, 0.2
    sl.shape = "RECTANGLE"
    sl.energy = 14.0
    sl.color = core.hex_rgba("#B9D2FF")[:3]
    sl.use_shadow = False
    so = bpy.data.objects.new("FILL_sh06_screen", sl)
    core.link(so, "LIGHTS")
    so.location = c + n * 0.05
    so.rotation_euler = (Vector(head_at) - so.location).to_track_quat("-Z", "Y").to_euler()
    core.show(so, 0.0, False)
    core.show(so, t_sec, True)

    # held figures: the idle clip only where it does not take a posed arm. The guard's hands are on the laptop and investigator_1's
    # hand is at his chin in pulled_clip, so there they only breathe and blink (plus the small moves keyed above)
    i2.idle()
    i1.idle(0.0, t_sec - 0.05)
    i1.idle(t_sec, None, clip=None)
    gd.idle(t_sec, None, clip=None)
    # a cool monitor-side rim on investigator_1 at the desk
    lights.rim_light((INV1_AT[0], INV1_AT[1], 0.0), from_deg=150, elevation=32, distance=2.6, power=110, color="#9FC0FF", name="RIM_sh06_inv1")

    # ---------------------------------------------------------------- camera
    p0 = Vector(SH04_END[0])
    pitch, yawd = math.radians(SH04_END[1]), math.radians(SH04_END[2])
    a0 = p0 + Vector((math.cos(yawd) * math.cos(pitch), math.sin(yawd) * math.cos(pitch), math.sin(pitch))) * 6.0
    cam.view("tearing_apart", 0.0, pos=tuple(p0), aim=tuple(a0), lens=SH04_END[3], size="wide",
             why="the noon framing again, at night: the floor nobody looked up from is being torn apart, at the very desk")
    land = (Vector((-4.72, -3.08, 1.38)), Vector((-2.82, -1.36, 0.88)), 24.0)
    t_m0, t_m1 = 0.1, min(t_apart - 0.15, 0.1 + 2.8)
    cam.move(t_m0, t_m1, pos=tuple(land[0]), aim=tuple(land[1]), lens=land[2], ease="SINE")
    cam.dolly(t_m1 + 0.05, t_sec - 0.04, 0.05, ease="ease_in_out")
    shot.notes.append(f"tearing_apart crane down {p0.z - land[0].z:.2f} m and in, {t_m0:.2f}-{t_m1:.2f}s")

    # pulled_clip: the screen square on, his face at its left, the guard's hands under it; push in on Maya's hand, zooming to 50 mm
    cp0 = c + cam_dir * 1.28 + Vector((0.0, 0.0, 0.07))
    aim0 = c - up * 0.04
    cam.view("pulled_clip", t_sec, pos=tuple(cp0), aim=tuple(aim0), lens=32, size="insert",
             why="the planted security camera pays off: its frame on the guard's laptop, then the clip, the push picks out her hand on the door")
    cp1 = maya + (cp0 - maya).normalized() * 1.0
    cam.move(t_sec + 0.25, t_end, pos=tuple(cp1), aim=tuple(maya), lens=50, ease="SINE")
    shot.notes.append(f"screen centre {tuple(round(v, 2) for v in c)} normal {tuple(round(v, 2) for v in n)}; zoom picture from {t_ten - 0.04:.2f}s")

    shot.subject("investigator_1", i1.head, moments=["tearing_apart", "drawer_out", "files_down", "pulled_clip.a"])
    shot.subject("investigator_2", i2.head, moments=["tearing_apart"])
    shot.subject("screen", scr, moments=["pulled_clip", "zoomed"])
    shot.moment("drawer_out", t_tear + 0.35)
    shot.moment("files_down", t_apart + 0.12)
    shot.moment("zoomed", t_ten + 0.3)
