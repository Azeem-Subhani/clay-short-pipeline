"""sh06 - the floor that night (office, night): sh04's last frame exactly (the high south-west corner looking down over the floor), now dark
and torn apart; the camera cranes down and in to a three-quarter view of investigator_1 at the victim's desk as he yanks its top drawer on
"tearing" and pulls out a stack of white files, while investigator_2, printout in hand, keeps pointing at the bare patch where the laptop
sat. A desk lamp on the victim's desk is the key. Cut to pulled_clip: past investigator_1's profile (glasses, moustache, eyes on the screen) to
the laptop the guard holds out from the right, his hands under its base: the lobby CCTV frame for a beat, then on "ten-second lobby clip" the
zoomed clip of Maya's hand on the door, and the camera pushes in centred on her hand, the LOBBY CAM 2 label still in frame.

Views (plan): tearing_apart (crane down 1.2 m and in, landing on the drawer coming out) -> pulled_clip (insert on the screen, a push).

Staging notes:
  * The set leaves the victim's top drawer pulled out; here it starts pushed in and investigator_1 yanks it out on "tearing".
  * The coffees the stranger left on the victim's desk in sh04 are still there, where sh04 put them (evidence stays).
  * The screen shows assets/cctv_frame.png, then assets/cctv_frame_zoom.png (made by the sh08 builder), with the look "clean": the footage
    look is burned into the pictures. The switch is a keyed mix in the screen's material.
  * The guard is only in pulled_clip (he comes in on the cut); the laptop is keyed in the world and his hands go under its base.
"""
import math

import bpy
from mathutils import Matrix, Vector

import set_office as sp
from stagekit import assets, build, camera, cast, core, furnish, lights

POP = 1.0 / 24.0
INV1_AT = (-3.05, -1.66)            # standing at the front of the victim's desk, just east of its drawer pedestal
INV2_AT = (-1.8, -1.55)             # at the desk's east end, beyond the shoved-back chair
EMPTY_SPOT = (-3.38, -0.85, 0.76)   # where the laptop sat in sh04 (the charger cable lies there)
CARRIER_AT = (-3.62, -0.55)         # sh04's CARRIER_AT
SCREEN_AT = (-4.4, -2.05, 1.22)     # pulled_clip: the centre of the laptop screen the guard holds out
MAYA_HAND_UV = (0.457, 0.444)       # Maya's hand on the door in cctv_frame_zoom.png (from the left, from the top)
# sh04 ended on this frame (nobody's end pose): pos, pitch, yaw, lens
SH04_END = ((-7.5, -4.83, 2.42), -38.0, 46.0, 22.0)   # sh04 nobody end pose: pos, pitch, yaw, lens


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

    # --- the drawer investigator_1 yanks: the set's open top drawer, pushed in until "tearing"
    drawer = bpy.data.objects.get(f"drawer_{dk.name}_2")
    if drawer is None:
        raise RuntimeError(f"no top drawer on {dk.name}")
    length, depth = float(dk["sk_size"][0]), float(dk["sk_size"][1])
    px = dk.location.x - length / 2 + 0.3
    face = dk.location.y - depth - 0.001
    handle_w = (px, face - 0.30 - 0.03, 0.46 + 0.11)
    handle = point_at_world(drawer, handle_w, "drawer_handle")
    files = assets.use("prop_file_stack", name="client_files", at=(px, face - 0.15, 0.478))
    cast_prop(files)
    bpy.context.view_layer.update()
    mw = files.matrix_world.copy()
    files.parent = drawer
    files.matrix_parent_inverse = drawer.matrix_world.inverted()
    files.matrix_world = mw
    shut = 0.28
    core.key(drawer, "location", 0.0, (0.0, shut, 0.0))
    core.key(drawer, "location", t_tear - 0.04, (0.0, shut, 0.0))
    core.key(drawer, "location", t_tear + 0.22, (0.0, 0.0, 0.0))

    # --- cast
    i1 = cast.from_plan("investigator_1", at=(INV1_AT[0], INV1_AT[1], 0.0), face="right")
    i2 = cast.from_plan("investigator_2", at=(INV2_AT[0], INV2_AT[1], 0.0), face="left")
    gd = cast.from_plan("guard", at=(-9.6, -4.4, 0.0), face="right")              # down the corridor, out of sight until the cut
    yaw_drawer = math.degrees(math.atan2(handle_w[0] - INV1_AT[0], -(handle_w[1] - INV1_AT[1])))
    i1.heading(yaw_drawer, 0.0, turn=0.0)
    i2.heading((EMPTY_SPOT[0], EMPTY_SPOT[1]), 0.0, turn=0.0)

    cam = camera.Camera()
    cam.line(i1, i2)

    # ---------------------------------------------------------------- investigator_1: bent to the drawer, yanks it, lifts the files out
    i1.expr("angry", 0.0, 0.0, amount=0.4)
    i1.eyes(-0.2, -0.75, 0.0, 0.0)
    i1.lean(26, 0.0, 0.0)
    i1.hand("R", "grip", 0.0, 0.0)
    i1.reach("R", handle, 0.0, 0.0)
    i1.hand("L", "open", 0.0, 0.0)
    i1.reach("L", (INV1_AT[0] - 0.05, -1.21, desk_top + 0.01), 0.0, 0.0)          # his left hand braced on the desk edge
    f = shot.f(t_tear - 0.3)
    while f <= shot.f(t_tear + 0.3):
        i1.reach("R", handle, f / shot.fps, 1.0 / shot.fps)
        f += 1
    i1.reach("R", handle, 0.6, 0.3)
    i1.lean(30, t_tear - 0.12, 0.12)                             # the wind-up
    i1.lean(16, t_tear + 0.2, 0.15)                              # the yank throws him back
    i1.squash(t_tear + 0.05, 0.04, 0.03, 0.08)
    # into the drawer: the white files out, up to his chest, turned toward the camera as he flips through them
    grab = point_on(files, (0.0, 0.0, 0.06), "files_grip")
    t_g = t_tear + 0.5
    i1.hand("R", "open", t_g - 0.12, 0.08)
    i1.reach("R", grab, t_g, 0.2)
    i1.hand("R", "grip", t_g + 0.04, 0.06)
    i1.hold(files, "R", t_g + 0.1, offset=(0.0, 0.0, 0.01))
    i1.hand("L", "open", t_g + 0.2, 0.1)
    i1.lean(6, t_g + 0.5, 0.35)
    i1.arm("R", 55, 70, t_g + 0.55, 0.35)
    i1.arm("L", 50, 80, t_g + 0.7, 0.35)                         # the other hand comes up to thumb through them
    i1.heading(yaw_drawer + 40.0, t_g + 0.7, turn=0.45)           # turns three-quarters to the camera with them
    i1.eyes(0.15, -0.55, t_g + 0.45, 0.15)
    i1.tilt_head(-8, t_g + 0.6, 0.3)
    i1.expr("angry", t_g + 0.6, 0.2, amount=0.55)

    # ---------------------------------------------------------------- investigator_2: printout in her left hand, points at the bare patch
    sheet = printout("printout_i2")
    cast_prop(sheet)
    own(i2, sheet)
    i2.expr("neutral", 0.0, 0.0)
    i2.hold(sheet, "L", 0.0, offset=(0.06, 0.0, 0.02))
    i2.hand("L", "grip", 0.0, 0.0)
    i2.arm("L", 46, 92, 0.0, 0.0)
    i2.arm("R", 8, 20, 0.0, 0.0)
    i2.tilt_head(-10, 0.0, 0.0)
    i2.eyes(0.1, -0.6, 0.0, 0.0)
    i2.eyes(0.4, -0.6, 0.45, 0.2)
    spot = core.empty("empty_spot", EMPTY_SPOT, size=0.03)
    spot.hide_render = True
    t_pt = max(0.9, t_tear - 0.35)
    i2.tilt_head(0, t_pt - 0.3, 0.25)
    i2.eyes(-0.5, -0.3, t_pt - 0.3, 0.15)
    i2.hand("R", "point", t_pt - 0.05, 0.1)
    i2.aim("R", spot, t_pt + 0.15, 0.25)
    i2.lean(5, t_pt + 0.2, 0.2)
    tt = t_pt + 0.5
    while tt < t_sec + 0.2:                                      # and she keeps her point on it to the cut
        i2.aim("R", spot, tt, 0.25)
        tt += 0.5
    i2.expr("angry", t_pt + 0.1, 0.2, amount=0.3)
    i2.speak("fraud", "apart")

    # ---------------------------------------------------------------- pulled_clip: the laptop, keyed in the world; the guard's hands under it
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
    core.show(lap, 0.0, False)
    for k in lap.children_recursive:
        core.show(k, 0.0, False)
        core.show(k, t_sec, True)
    core.show(lap, t_sec, True)
    bpy.context.view_layer.update()
    lid = furnish.part(lap, "lid")
    lo, hi = core.world_bbox([scr])
    c = (lo + hi) / 2
    n = (lid.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()
    up = (lid.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    right = up.cross(n).normalized()
    sw, sh = 0.29, 0.18
    maya = c + right * ((MAYA_HAND_UV[0] - 0.5) * sw) + up * ((0.5 - MAYA_HAND_UV[1]) * sh)
    # the guard: to the right of the laptop, holding it out by the base, only his arms in frame
    blo, bhi = core.world_bbox([furnish.part(lap, "body") or lap])
    g_at = Vector((c.x, c.y, 0.0)) + right * 0.66 + n * 0.05
    gd.place((g_at.x, g_at.y, 0.0), t_sec)
    gd.heading((c.x, c.y), t_sec, turn=POP)
    under_r = point_at_world(lap, Vector((c.x, c.y, blo.z - 0.012)) + right * 0.07 + n * 0.02, "base_under_R")
    under_l = point_at_world(lap, Vector((c.x, c.y, blo.z - 0.012)) + right * 0.13 - n * 0.05, "base_under_L")
    gd.hand("R", "open", t_sec, POP)
    gd.hand("L", "open", t_sec, POP)
    gd.reach("R", under_r, t_sec, POP)
    gd.reach("L", under_l, t_sec, POP)
    gd.eyes(-0.6, -0.4, t_sec, POP)
    gd.expr("neutral", t_sec, POP)
    # investigator_1: at the left edge, in profile, leaning in to the screen (the cut compresses time: he has come to see it)
    # his head in the upper left of the safe area, a little toward the lens: the body turned ~30 deg toward the camera (a
    # three-quarter face), the eyes swung back to the screen. A true three-quarter with the eyes square on a screen that faces
    # the lens is not possible from one camera, so this is the compromise: face open to us, gaze on the clip.
    head_at = c + right * -0.25 + n * 0.22 + Vector((0.0, 0.0, 0.26))
    i1_at = Vector((head_at.x, head_at.y, 0.0)) - right * 0.06
    i1.heading(yaw_drawer + 40.0, t_sec - 0.08, turn=POP)          # hold the turn to the camera until the cut
    i1.place((i1_at.x, i1_at.y, 0.0), t_sec)
    turn_to = c + n * 0.15
    i1.heading((turn_to.x, turn_to.y), t_sec, turn=POP)
    i1.release(files, t_sec - 0.04)
    core.show(files, t_sec, False)
    for k in files.children_recursive:
        core.show(k, t_sec, False)
    i1.pose("rest", t_sec, POP)
    i1.arm("R", 8, 16, t_sec, POP)
    i1.arm("L", 8, 16, t_sec, POP)
    i1.lean(10, t_sec, POP)
    i1.tilt_head(-6, t_sec, POP)
    i1.eyes(1.0, -0.3, t_sec, POP)
    i1.expr("worried", t_sec, POP, amount=0.3)
    i1.expr("angry", t_ten + 0.2, 0.2, amount=0.45)
    i2.place((c.x - 1.3, c.y - 0.3, 0.0), t_sec)                 # out of the frame, to the left
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

    for a in (i1, i2, gd):
        a.idle()
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

    # pulled_clip: past his profile at the left edge to the screen; push in on Maya's hand, zooming to 50 mm
    cp0 = c + cam_dir * 1.28 + Vector((0.0, 0.0, 0.07))
    aim0 = c - up * 0.06
    cam.view("pulled_clip", t_sec, pos=tuple(cp0), aim=tuple(aim0), lens=32, size="insert",
             why="the planted security camera pays off: its frame on the guard's laptop, then the clip, the push picks out her hand on the door")
    cp1 = maya + (cp0 - maya).normalized() * 1.0
    cam.move(t_sec + 0.25, t_end, pos=tuple(cp1), aim=tuple(maya), lens=50, ease="SINE")
    shot.notes.append(f"screen centre {tuple(round(v, 2) for v in c)} normal {tuple(round(v, 2) for v in n)}; zoom picture from {t_ten - 0.04:.2f}s")

    shot.subject("investigator_1", i1.head, moments=["tearing_apart", "drawer_out", "pulled_clip.a"])
    shot.subject("investigator_2", i2.head, moments=["tearing_apart"])
    shot.subject("screen", scr, moments=["pulled_clip", "zoomed"])
    shot.moment("drawer_out", t_tear + 0.35)
    shot.moment("files_up", t_g + 0.9)
    shot.moment("zoomed", t_ten + 0.3)
