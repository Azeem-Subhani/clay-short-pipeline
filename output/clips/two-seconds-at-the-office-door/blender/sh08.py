"""sh08 - the ending image: some time later, on a bright orientation morning, the lobby clip of Maya holding the door plays on the training
room's big screen to rows of new hires; the trainer points at it. Her two seconds have become the lesson.

Views (plan): new_hires (the reverse, from beside the screen: the front-row faces lit by it, new teal lanyards, eyes past the lens; a slow
truck along the row) -> the_clip (the far wide from the back of the room over the hires' heads: the screen with the CCTV frame, the trainer
pointing; a gentle push that settles as "orientation morning" ends, then the 2.8 s hold the film ends on).

Staging notes:
  * The screen shows assets/cctv_frame.png (rendered from the lobby camera in sh03 with the footage card burned in: grey-green veil,
    scanlines, "LOBBY CAM 2   MON 08:47" bar and REC dot). The screen's own look is set to "clean", so its built-in stamp text is hidden and
    the bar is not doubled.
  * The hires are seated from frame one (the end pose of Stand_To_Sit at the seat height, then Sitting_Idle), as sh04 seats its workers.
  * A soft cool area light in front of the screen stands in for its glow on the front-row faces (a shot light; the set's rig is untouched).
  * Costume limits (casting.json): the T-shirted hires are seen from behind only in the far wide; the trainer is never framed tight.
"""
import math

import bpy
from mathutils import Vector

import set_training_room as sp
from stagekit import aj_clips, build, camera, cast, core, furnish

CLIP_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent
CCTV = CLIP_DIR / "assets" / "cctv_frame.png"
CCTV_ZOOM = CLIP_DIR / "assets" / "cctv_frame_zoom.png"          # render_cctv_zoom.py: the same lobby camera, x4 on the door, her hand ringed
DOOR_UV = (0.634, 0.646)                                          # where Maya and the stranger stand in the wide frame (u, v from bottom left)
HAND_UV = (0.457, 0.541)                                          # her hand on the door leaf in the zoomed frame (the red ring)
WATCH_AT = (-0.8, 7.45)                                           # where the hires look: the left half of the screen, 15-25 deg off the lens
HIRES = (("hire_1", "seat_2"), ("hire_2", "seat_3"), ("hire_3", "seat_6"), ("hire_4", "seat_7"), ("hire_5", "seat_10"))


def chair_at(mark):
    """The training seat whose sitter sits on `mark` (seat origins stand at the back of the chair, 0.33 m short of the mark)."""
    best, bd = None, 1e9
    for o in bpy.data.objects:
        if o.get("sk_type") == "training_seat":
            p = o.matrix_world.translation
            d = (Vector((p.x, p.y)) - Vector((mark[0], mark[1] - 0.33))).length
            if d < bd:
                best, bd = o, d
    return best


def seat(a, chair, until, arms=True):
    """Seated on `chair` from frame one (the end of Stand_To_Sit at the chair's seat height), then Sitting_Idle to `until` (as sh04)."""
    name = "Stand_To_Sit"
    c = aj_clips.require(name)
    top = 0.425                                                       # the training seat's shell top (its kit top is the tablet arm)
    bd = aj_clips.body(a)
    clip_seat = (c["analysis"]["hips_end_per_leg"] - aj_clips.SEAT_UNDER) * bd.leg
    dz = (top - a.stage.matrix_world.translation.z) / a.scale - clip_seat
    a._seat_dz = dz
    groups = aj_clips.ALL_GROUPS if arms else ("legs", "spine", "head")     # arms=False: the hands are free for reach()
    aj_clips.play(a, name, 0.0, start=c["duration_s"] - 0.04, blend=0.0, state="sitting", hips_dz=lambda f, u, dz=dz: dz, groups=groups)
    if arms:
        a.do("sit_idle", t=0.04, until=until)
    else:
        aj_clips.play(a, "Sitting_Idle", 0.04, loop=True, until=until, state="sitting", blend=0.4, hips_dz=lambda f, u, dz=dz: dz, groups=groups)


def lift_soles(a, dz=0.015):
    """Raise a standing figure 15 mm: the feet check steps 1 cm past its last hit, so soles within a centimetre of the floor read as floating
    over what lies under the floor (same work-around as sh01-sh03)."""
    e = core.empty(f"{a.stage.name}_lift", (0, 0, dz), size=0.05)
    e.hide_render = True
    a.stage.parent = e


def screen_zoom(scr, t0, t1, t_cut, k_end=0.42):
    """The wall screen's picture: the wide lobby frame, a digital push-in on the doorway from t0 to t1 (the crop shrinks to k_end of the frame),
    then a hard cut to the x4 zoom frame at t_cut (a security operator's "zoom"). All in the screen's material, keyed per frame."""
    sh = core.current()
    s = furnish.screen(scr)
    nt = s.data.materials[0].node_tree
    tx = nt.nodes["image"]
    uv = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeUVMap")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.vector_type = "POINT"
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], tx.inputs["Vector"])
    tz = nt.nodes.new("ShaderNodeTexImage")
    tz.image = bpy.data.images.load(str(CCTV_ZOOM), check_existing=True)
    tz.image.colorspace_settings.name = "sRGB"
    tz.interpolation, tz.extension = "Linear", "EXTEND"
    nt.links.new(uv.outputs["UV"], tz.inputs["Vector"])
    sw = nt.nodes.new("ShaderNodeMix")
    sw.data_type = "RGBA"
    for l in list(tx.outputs["Color"].links):
        to = l.to_socket
        nt.links.remove(l)
        nt.links.new(sw.outputs["Result"], to)
    nt.links.new(tx.outputs["Color"], sw.inputs["A"])
    nt.links.new(tz.outputs["Color"], sw.inputs["B"])
    fac = sw.inputs["Factor"]
    cu, cv = DOOR_UV

    def crop(f, k):
        mp.inputs["Scale"].default_value = (k, k, 1.0)
        mp.inputs["Location"].default_value = (cu * (1 - k), cv * (1 - k), 0.0)
        mp.inputs["Scale"].keyframe_insert("default_value", frame=f)
        mp.inputs["Location"].keyframe_insert("default_value", frame=f)
    f0, f1 = sh.f(t0), sh.f(t1)
    crop(1, 1.0)
    for f in range(f0, f1 + 1):
        u = (f - f0) / max(1, f1 - f0)
        e = u * u * (3 - 2 * u)
        crop(f, 1.0 / (1.0 + (1.0 / k_end - 1.0) * e))          # the scale grows smoothly: 1x -> 1/k_end x
    fc = sh.f(t_cut)
    for f, v in ((1, 0.0), (fc - 1, 0.0), (fc, 1.0)):
        fac.default_value = v
        fac.keyframe_insert("default_value", frame=f)
    ad = nt.animation_data
    if ad and ad.action:
        for c in core.fcurves(nt):
            for kp in c.keyframe_points:
                kp.interpolation = "LINEAR" if "Mapping" in c.data_path else "CONSTANT"
    return s


def glow_light(name, at, size, energy, color):
    gl = bpy.data.lights.new(name, "AREA")
    gl.shape, gl.size, gl.size_y, gl.energy, gl.use_shadow = "RECTANGLE", size[0], size[1], energy, False
    gl.color = color
    ob = bpy.data.objects.new(name, gl)
    core.link(ob, "LIGHTS")
    ob.location = at
    ob.rotation_euler = (math.radians(90.0), 0.0, 0.0)              # area lights shine down -Z: turned to shine toward -Y
    return ob


def build_shot(shot):
    S = sp.build_set("office_day")
    M = S["mark"]
    scr = S["screen"]
    furnish.screen_set_image(scr, str(CCTV))
    furnish.screen_look(scr, "clean", gain=3.4)                      # the brightest surface in the room
    core.at_frame(1)
    quad = furnish.screen(scr)
    lo, hi = core.world_bbox([quad])
    scr_c = (lo + hi) / 2
    door_pt = Vector((lo.x + (hi.x - lo.x) * 0.63, lo.y, lo.z + (hi.z - lo.z) * 0.55))       # Maya at the door, in the picture

    hand_pt = Vector((lo.x + (hi.x - lo.x) * HAND_UV[0], lo.y, lo.z + (hi.z - lo.z) * HAND_UV[1]))   # her hand on the door, zoomed

    # the screen's glow on the faces: a soft cool sheet in front of the picture, and a cool kick from the screen side on the front row
    glow_light("GLOW_screen", (scr_c.x, scr_c.y - 0.25, scr_c.z), (2.8, 1.5), 1400.0, (0.62, 0.78, 1.0))
    glow_light("GLOW_screen_low", (scr_c.x - 0.4, scr_c.y - 0.3, 1.25), (1.6, 0.5), 450.0, (0.62, 0.78, 1.0))
    sp_d = bpy.data.lights.new("GLOW_screen_faces", "SPOT")           # the screen's light on the front two rows' faces: cool, soft-edged
    sp_d.energy, sp_d.spot_size, sp_d.spot_blend, sp_d.shadow_soft_size, sp_d.use_shadow = 1800.0, math.radians(55.0), 0.8, 1.2, False
    sp_d.color = (0.5, 0.68, 1.0)
    sp_o = bpy.data.objects.new("GLOW_screen_faces", sp_d)
    core.link(sp_o, "LIGHTS")
    sp_o.location = (scr_c.x - 0.6, scr_c.y - 0.35, 1.85)
    sp_o.rotation_euler = (Vector((0.0, 3.7, 1.15)) - Vector(sp_o.location)).to_track_quat("-Z", "Y").to_euler()

    # dressing moved for this shot (nothing hidden, so the set's count stands): the bin in the front-row aisle goes to the side wall's
    # corner by the flipchart, out of the new_hires lane; the ceiling projector slides west, out of the screen's line (the wall screen is
    # the room's display, the projector is dressing), so the end of the push has nothing hanging over the picture; the bin by the trainer
    # (a black blob beside the front row in the end frame) goes east, short of the flipchart (still in the set WIDE)
    for o in bpy.data.objects:
        if o.get("sk_type") == "bin" and o.parent is None:
            p = o.matrix_world.translation
            if abs(p.x - 0.12) < 0.4 and abs(p.y - 3.87) < 0.4:
                o.location.x, o.location.y = 2.8, 4.55
            elif abs(p.x - 0.85) < 0.4 and abs(p.y - 6.05) < 0.4:
                o.location.x, o.location.y = 2.45, 6.2
            elif abs(p.x - 1.29) < 0.4 and abs(p.y - 2.22) < 0.4:       # the one between the back rows, mid-frame in new_hires: to the west aisle
                o.location.x, o.location.y = -3.0, 3.6
            elif abs(p.x + 0.5) < 0.4 and abs(p.y - 0.81) < 0.4:        # the one against the back wall, mid-frame behind the rows in new_hires
                o.location.x, o.location.y = 2.9, 0.6
    pj = S.get("projector")
    if pj is not None:
        pj.location.x, pj.location.y = -1.6, 2.7

    # --- words -> times
    t_every = shot.t("every single")
    t_hire = shot.t("new hire", edge="end")
    t_watch = shot.t("watches")
    t_clip = shot.t("ten-second clip")
    t_orient = shot.t("orientation")
    t_morning = shot.t("morning.", edge="end")
    t_end = shot.seconds

    # --- cast: five hires seated facing the screen, the trainer standing by the lectern
    hires = {}
    for hid, mk in HIRES:
        p = M[mk]
        a = cast.from_plan(hid, at=(p[0], p[1] - 0.06, 0.0), face="right")
        a.heading(WATCH_AT, 0.0, turn=0.0)                           # the screen's left half: never into the lens beside it
        ch = chair_at(p)
        seat(a, ch, t_end, arms=(hid != "hire_1"))
        a.floating = True                                             # seated: the chair carries them
        hires[hid] = a
    h1, h2, h3, h4, h5 = (hires[k] for k in ("hire_1", "hire_2", "hire_3", "hire_4", "hire_5"))
    tr = cast.from_plan("trainer", at=M["trainer"], face="left")
    lift_soles(tr)
    tr.heading((0.6, 2.4), 0.0, turn=0.0)                            # to the room, a little toward the screen

    cam = camera.Camera()
    cam.line(h1, tr)

    # --- the hires watch: eyes up on the screen, small heads, one glance at a neighbour, a wince, a note
    for k, a in enumerate((h1, h2, h3, h4, h5)):
        a.expr("neutral", 0.0, 0.0)
        a.eyes(0.0, 0.25, 0.0, 0.0)
        a.blink(0.5 + 0.9 * k)
        a.blink(3.4 + 0.7 * k)
    # hire_1: takes a note on the pad on her tablet arm, eyes flicking up to the screen
    p1 = M["seat_2"]
    ch1 = chair_at(p1)
    tc, tz = furnish.tops(ch1)[0][:2]
    for o in list(bpy.data.objects):                                  # her tablet is cleared of the dressing's books for her notes
        if o.get("sk_on") == ch1.name and o.parent is None:
            for k in [o, *o.children_recursive]:
                k.hide_render = k.hide_viewport = True
    pad = furnish.make("papers_stack", at=(tc.x + 0.02, tc.y + 0.02, tz), rot_z=-8)
    pad["sk_on"] = ch1.name
    pen = build.box("pen_hire_1", (0.008, 0.13, 0.008), (0, 0, 0), surface="painted_wall", tint="#1B2A44", bevel=0.002)
    h1.hold(pen, "R", 0.0)
    for o in (pen,):
        if o.name not in h1.coll.all_objects:
            h1.coll.objects.link(o)
    pad_pt = Vector((tc.x + 0.06, tc.y + 0.0, tz + 0.03))
    # the note, by hand (the kit's write pose loses to the seated clip): the pen hand on the pad in small strokes, the other hand flat on
    # the tablet, eyes down on the page; on "every single" she looks up at the screen with the pen still on the pad
    import random
    rnd = random.Random(11)
    h1.hand("L", "open", 0.0, 0.0)
    h1.reach("L", (tc.x - 0.15, tc.y - 0.04, tz + 0.02), 0.0, 0.0)
    h1.hand("R", "pinch", 0.0, 0.0)
    h1.reach("R", pad_pt, 0.0, 0.0)
    h1.eyes(0.0, -0.8, 0.0, 0.0)
    tw = 0.15
    while tw < t_every - 0.25:
        h1.reach("R", pad_pt + Vector((rnd.uniform(-0.035, 0.035), rnd.uniform(-0.015, 0.015), 0.006)), tw, 0.09)
        tw += rnd.uniform(0.13, 0.2)
    h1.reach("R", pad_pt + Vector((0.0, 0.0, 0.03)), t_every, 0.15)
    h1.eyes(0.0, 0.45, t_every, 0.2)                                   # up at the screen on "every single"
    h1.tilt_head(-4, t_hire + 0.3, 0.4)
    # hire_2: watching; a glance at her neighbour on "new hire", back to the screen
    h2.eyes(0.0, 0.25, 0.0, 0.0)
    h2.eyes(0.9, 0.0, t_hire - 0.2, 0.2)
    h2.head_turn(0.35, t_hire, 0.35)
    h2.expr("worried", t_hire + 0.05, 0.2, amount=0.4)
    h2.eyes(0.0, 0.25, t_watch + 0.5, 0.2)
    h2.head_turn(0.0, t_watch + 0.7, 0.4)
    # hire_3: winces at the clip
    h3.expr("worried", t_every - 0.1, 0.2, amount=0.7)
    h3.tilt_head(6, t_every, 0.3)
    h3.lean(-4, t_every + 0.05, 0.3)
    # hire_4: a small nod-tilt, eyes narrowing on the screen
    h4.tilt_head(-5, 1.3, 0.4)
    h4.expr("surprised", t_clip - 0.1, 0.2, amount=0.35)
    h4.tilt_head(2, t_clip + 0.4, 0.5)
    # hire_5: leans in a little to see
    h5.lean(6, 1.6, 0.6)
    h5.head_turn(-0.15, t_clip, 0.4)

    # --- the trainer: eyes to the screen, then the point on "every single new hire", held through the clip
    tr.expr("neutral", 0.0, 0.0)
    tr.eyes(0.8, 0.15, t_every - 0.3, 0.2)                            # eyes to the screen at his side first
    tr.head_turn(0.45, t_every - 0.05, 0.3)
    tr.hand("L", "point", t_every + 0.05, 0.1)
    tr.aim("L", door_pt, t_every + 0.25, 0.3)                         # the presenter's point: face to the room, arm out to the screen
    tr.lean(3, t_every + 0.25, 0.3)
    tr.head_turn(0.0, t_hire + 0.4, 0.4)
    tr.expr("sad", t_hire, 0.3, amount=0.25)
    tr.eyes(0.0, 0.0, t_clip + 0.3, 0.25)                             # back to the room: "this is why"
    tr.aim("L", hand_pt, t_clip + 0.45, 0.35)                         # the point follows the zoom onto her hand on the door
    tr.blink(1.0)
    tr.blink(4.2)

    for a in (h1, h2, h3, h4, h5):
        a.idle()
    tr.idle(0.0, t_every - 0.3)                                       # the standing idle clip owns the arms: it stops before the point
    tr.idle(t_every - 0.3, t_end, clip=None, seed=7)                  # blinks and breath carry on

    # --- camera
    # new_hires: the reverse from beside the screen, at seated eye height: the front row's faces, the middle row between them, the back
    # wall and glass door behind; a slow truck along the row
    n_pos = Vector((0.95, 6.75, 1.3))
    n_aim = Vector((0.3, 4.1, 1.02))
    cam.view("new_hires", 0.0, framing=camera.Framing(n_pos, n_aim, 40.0, fstop=2.8), size="medium",
             why="'every single new hire': the faces of the people being taught by her mistake, one after another")
    cam.truck(0.0, t_watch - 0.05, right=0.7, ease="ease_in_out")     # stops short of the screen's centre: their eyes stay off the lens

    # the_clip: the far wide from the back of the room, over the heads, the screen big and above the captions; the push settles on
    # "morning", then the frame holds on the clip
    w_pos = Vector((-0.25, 0.4, 2.12))
    w_aim = Vector((-0.33, 7.45, 1.15))
    cam.view("the_clip", t_watch, framing=camera.Framing(w_pos, w_aim, 28.0, fstop=5.6), size="wide",
             why="the last line earns the last image: her two seconds on a screen, being watched, for good")
    # the push goes to the SCREEN: a dolly up and in with the lens going 28 -> 40 mm, ending with the screen ~87% of the frame width, its
    # centre 40% from the top, the trainer's pointing hand at the left edge, the hires a low row of heads under the caption band
    lens1 = 35.0                                                       # 40 mm leaves the front row in the caption band; 35 puts it under
    d1 = (hi.x - lo.x) * lens1 / (0.83 * camera.SENSOR * 9.0 / 16.0)     # the picture 83% wide: with its bezel about 88%
    e_pos = Vector((-0.06, scr_c.y - d1, 2.65))                         # high, 0.35 m under the ceiling: the rows drop low
    to_c = scr_c - e_pos
    pitch = math.atan2(to_c.z, Vector((to_c.x, to_c.y)).length) - math.atan(0.2 * camera.SENSOR / 2.0 / lens1)
    yaw = math.atan2(to_c.y, to_c.x)
    e_aim = e_pos + Vector((math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch))) * to_c.length
    tp0, tp1 = t_watch + 0.02, t_morning - 0.05

    def push_build(p0, f0):
        p1 = camera.Pose(e_pos, e_aim, lens1, 5.6, 0.0, scr_c)
        return lambda s_, f_: p0.lerp(p1, s_)
    cam._run("push", tp0, tp1, push_build, "settle")
    cam.hold(t_end)
    shot.notes.append(f"the_clip end: pos {tuple(round(c, 2) for c in e_pos)} lens {lens1} (screen {hi.x - lo.x:.2f} m at {d1:.2f} m)")
    screen_zoom(scr, t_clip - 0.12, t_clip + 0.28, t_clip + 0.3)

    shot.subject("hire_1", h1.head, moments=["new_hires"])
    shot.subject("hire_2", h2.head, moments=["new_hires"])
    shot.subject("screen", quad, moments=["the_clip", "final_hold"])
    shot.subject("trainer", tr.head, moments=["the_clip"])
    shot.moment("final_hold", t_end - 0.3)
    shot.notes.append(f"truck 0-{t_watch:.2f}s, push {t_watch:.2f}-{t_morning:.2f}s, hold to {t_end:.2f}s; trainer points {t_every:.2f}s")
