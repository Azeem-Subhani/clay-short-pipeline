"""sh07 - closing the loop: back at Friday dusk, Maya alone with her box in front of the door that is now locked to her. The camera cranes up and
back until she is small under the lit tower, looks down into the box (a whole job in a few objects and the lanyard she no longer wears), and
ends on her face as she turns her head back over her shoulder to the door she once held.

Continuity with sh01 (same dusk rig, same lamp red, the door shut and locked, the lock on the right leaf, the same carry from below, the same
street-lamp key on her): Maya stands at box_spot with the box; the guard, who turned away from the glass at the end of sh01, walks off across
the lobby from where sh01 left him (sh01.GUARD_AWAY).
"""
import math

import bpy
from mathutils import Vector

import set_entrance as sp
import sh01 as s1
from stagekit import assets, build, camera, cast, core, furnish


def lanyard_loop(box, name="teal_lanyard_strap"):
    """Her teal lanyard strap laid in a loose loop across the folders, from the badge: a flat ribbon (a curve with a thin rectangular
    section), bright enough to read from above as a lanyard and not just a card."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp_ = cu.splines.new("BEZIER")
    pts = [(0.02, -0.035, 0.0), (0.095, 0.005, 0.006), (0.085, 0.075, 0.01), (-0.01, 0.085, 0.008), (-0.07, 0.03, 0.004), (-0.02, -0.03, 0.0)]
    sp_.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp_.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    cu.bevel_mode = "ROUND"
    cu.bevel_depth = 0.0
    cu.extrude = 0.0
    prof = bpy.data.curves.new(name + "_sec", "CURVE")         # a flat ribbon section: 12 mm wide, 1.5 mm thick
    prof.dimensions = "2D"
    ps = prof.splines.new("POLY")
    ps.points.add(3)
    for q, (x, y) in zip(ps.points, ((-0.006, -0.0008), (0.006, -0.0008), (0.006, 0.0008), (-0.006, 0.0008))):
        q.co = (x, y, 0.0, 1.0)
    ps.use_cyclic_u = True
    pob = bpy.data.objects.new(name + "_sec", prof)
    core.link(pob, "FX")
    pob.hide_render = pob.hide_viewport = True
    cu.bevel_mode = "OBJECT"
    cu.bevel_object = pob
    cu.use_fill_caps = True
    from stagekit import mat
    cu.materials.append(mat.surface("painted_wall", tint="#14A3B4"))
    ob = bpy.data.objects.new(name, cu)
    core.link(ob, "FX")
    ob.parent = box
    return ob


def framed_photo(box, name="framed_photo_flat"):
    """A small framed photo lying face up beside the mug: a dark wood frame, a white mat, a picture of two people at the sea."""
    fr = build.box(name, (0.13, 0.1, 0.014), (0, 0, 0), surface="painted_wall", tint="#3A2F26", bevel=0.003)
    mat_ = build.box(name + "_mat", (0.112, 0.082, 0.002), (0, 0, 0), surface="painted_wall", tint="#F2EFE6", bevel=0.0)
    sky = build.box(name + "_sky", (0.094, 0.036, 0.002), (0, 0, 0), surface="painted_wall", tint="#8EC3E6", bevel=0.0)
    sea = build.box(name + "_sea", (0.094, 0.028, 0.002), (0, 0, 0), surface="painted_wall", tint="#2F7FA8", bevel=0.0)
    for ob, loc in ((mat_, (0, 0, 0.0138)), (sky, (0, 0.014, 0.0152)), (sea, (0, -0.018, 0.0152))):
        ob.parent = fr
        ob.location = loc
    for k, (x, col) in enumerate(((-0.014, "#E0A070"), (0.014, "#C98B5E"))):          # two small figures on the shore
        hd = build.cyl(f"{name}_fig{k}", 0.008, 0.002, (0, 0, 0), surface="painted_wall", tint=col, seg=12)
        hd.parent = fr
        hd.location = (x, -0.004, 0.0165)
    fr.parent = box
    return fr


def build_shot(shot):
    S = sp.build_set("dusk")
    M = S["mark"]
    doors, lamp = S["doors"], S["reader_lamp"]
    leaf_R = furnish.part(doors, "leaf_R")
    furnish.lamp_state(lamp, "red")                                     # still red: the door is shut to her
    s1.door_lock(leaf_R)
    s1.clear_door_glass()                                               # the guard reads through the door as he walks off inside
    s1.lower_bands(doors)                                               # the doors as in sh01
    h_out = s1.leaf_point(leaf_R, (-0.903, -0.075, 1.05), "handle_R_out")
    h_top = s1.leaf_point(leaf_R, (-0.903, -0.13, 1.38), "handle_R_top")     # the top of the pull bar: what shows of the handle over her shoulder

    # --- words -> times
    t_career = shot.t("career")
    t_van = shot.t("vanished")
    t_no = shot.t("No second")
    t_box = shot.t("cardboard")
    t_shed = shot.t("She'd")
    t_held = shot.t("held")
    t_door = shot.t("door")

    # --- cast: Maya at box_spot, turned a little to the street, the box at her chest; the guard walking off across the lobby
    bx, by = M["box_spot"][0], M["box_spot"][1]
    maya = cast.from_plan("maya", at=(bx, by, 0.0), face="right")
    maya.heading((bx - 0.25, by - 4.0), 0.0, 0.0)
    guard = cast.from_plan("guard", at=(s1.GUARD_AWAY[0], s1.GUARD_AWAY[1], 0.0), face="right")
    s1.lift_soles(guard)
    guard.heading((6.0, 2.5), 0.0, 0.0)
    box = assets.use("prop_cardboard_box_desk", name="desk_box", at=(bx, by - 0.3, 1.0))
    s1.cast_prop(box)
    lan, stapler = s1.box_contents(box)
    lan.location = (0.0, -0.045, 0.262)                                 # the badge face up on the folders, its strap looping out from it
    lan.rotation_euler = (math.radians(-88.0), 0.0, math.radians(8.0))
    strap = lanyard_loop(box)
    strap.location = (0.0, -0.02, 0.268)
    photo = framed_photo(box)
    photo.location = (-0.1, -0.085, 0.252)
    photo.rotation_euler = (math.radians(4.0), 0.0, math.radians(-14.0))
    for o in box.children_recursive:                                    # the asset's photo stands on edge (unreadable from above): it lies flat now
        if o.type == "MESH" and o.data.materials and o.data.materials[0].name in ("SK_solid_#3A2F26_0.5_0.0_0.0", "SK_solid_#9FBFD6_0.5_0.0_0.0"):
            o.hide_render = True
            o.hide_viewport = True
    maya.hide("addon:lanyard_badge")                                   # handed in: it lies in the box (as in sh01)
    box_top = s1.leaf_point(box, (0.0, -0.03, 0.26), "desk_box_top")     # the badge, in the middle of what is in the box
    s1.street_key(M["box_spot"])

    cam = camera.Camera()
    cam.line(maya, guard)

    s1.carry_box(maya, box, 0.0)
    # Maya: numb, eyes low; a breath in on "career" and out on "vanished" with the shoulders and head dropping to the box; eyes into the box
    # on "No second chance"; the last look back over her shoulder to the door on "held"
    maya.expr("sad", 0.0, 0.0, amount=0.55)
    maya.eyes(0.15, -0.35, 0.0, 0.0)
    maya.blink(0.45)
    t_s = t_career - 0.15
    maya.tilt_head(4, t_s + 0.3, 0.3)                                   # in: the head comes up a little
    maya.lean(-2, t_s + 0.3, 0.3)
    maya.ctrl_pulse("viseme_U", t_van - 0.05, t_van + 0.45)              # the breath out
    maya.eyes(0.0, -0.8, t_van - 0.15, 0.2)
    maya.tilt_head(-16, t_van + 0.35, 0.45)                             # out: the head drops to the box, the shoulders round
    maya.lean(7, t_van + 0.4, 0.5)
    maya.heading((bx - 0.6, by - 4.0), t_van + 0.9, 0.6)                # a small shift of weight
    maya.blink(t_van + 0.6)
    maya.tilt_head(-12, t_no - 0.1, 0.4)
    maya.blink(t_no + 1.1)
    maya.expr("sad", t_box - 0.1, 0.4, amount=0.85)
    maya.blink(t_box + 0.4)
    # held_door: she faces the lens three-quarter, then the eyes go first, the head follows over her left shoulder to the door behind her
    maya.lean(2, t_shed - 0.1, 0.3)
    maya.tilt_head(-3, t_shed - 0.05, 0.3)
    maya.eyes(0.0, -0.1, t_shed, 0.2)
    maya.heading((bx + 2.4, by - 3.2), t_shed, 0.0)
    maya.eyes(1.0, 0.05, t_held - 0.3, 0.15)
    maya.head_turn(0.95, t_held + 0.15, 0.45)                           # over her left shoulder toward the door behind her
    maya.expr("worried", t_held - 0.05, 0.3, amount=0.7)
    maya.blink(t_door + 0.35)
    maya.expr("sad", t_door + 0.55, 0.5, amount=0.9)

    # the guard: already turned away, he walks off between the queue posts and the reception desk, out across the lobby
    guard.expr("neutral", 0.0, 0.0)
    t_g = guard.walk(0.0, (-1.75, 2.95), speed=2.4)                     # right to left behind her, through the glass, away from the door
    guard.heading((-3.0, 6.0), t_g + 0.2, 0.4)
    shot.notes.append(f"guard reaches the far side of the lobby at {t_g:.2f}s")

    shot.subject("maya", maya.head, moments=["career_gone", "held_door"])
    shot.subject("guard", guard.head, moments=["behind_glass"])          # only ever seen through the lobby glass (the sight check stops at glass)
    shot.subject("box", box, moments=["career_gone"])
    shot.subject("box_contents", box_top, moments=["the_box"])
    shot.subject("lanyard", strap, moments=["the_box"])

    # --- camera
    # career_gone: in front of her on the forecourt, the locked doors and the lit lobby behind; the crane rises and backs away over the near
    # parking lane, the pitch easing up at the end, until she is small in the lower third and the lit tower closes the top of the frame
    cam.view("career_gone", 0.0, pos=(-0.9, -6.5, 1.75), aim=(-0.45, -2.0, 1.55), lens=28, size="wide",
             why="her career vanished: a woman getting smaller in front of the building that has shut her out")
    cam.crane(0.0, t_no - 0.1, rise=6.0, back=4.9, tilt_to=-28.0, ease="ease_in_out")

    # the_box: steeply down into the box from in front of her (her hands under it, out of frame; the box's back wall near the top edge); the
    # camera arcs 25 degrees round the badge, sinking a little toward it
    core.at_frame(shot.f(t_no))
    bc = box_top.matrix_world.translation.copy()
    mw = box.matrix_world
    bx_axis = (mw.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()     # her left
    fwd = Vector((bx_axis.y, -bx_axis.x, 0.0))                           # her front
    to_cam = (fwd * 0.5 + Vector((0.0, 0.0, 0.87))).normalized()
    aim = bc + fwd * 0.03
    cpos = aim + to_cam * 0.66
    shot.notes.append(f"the_box: badge {tuple(round(v, 2) for v in bc)}, camera {tuple(round(v, 2) for v in cpos)}")
    cam.view("the_box", t_no, pos=tuple(cpos), aim=tuple(aim), lens=50, size="insert",
             why="just a cardboard box: the whole job reduced to a few objects, and the lanyard she no longer gets to wear")
    cam.orbit(t_no + 0.05, t_shed - 0.4, aim.copy(), deg=25.0, rise=-0.06, ease="ease_in_out")

    # held_door: a medium close of her face three-quarter front, the shut door and its handle soft behind her on the side she will look to;
    # a slow push in; she turns her head back to the door on "held"; the focus racks from her to the handle on "door"
    core.at_frame(shot.f(t_shed))
    hp = maya.head.point()
    hd = h_out.matrix_world.translation.copy()
    back = Vector((hp.x - hd.x, hp.y - hd.y, 0)).normalized()
    right = Vector((-back.y, back.x, 0))                                 # screen right as seen from the camera (camera looks along -back)
    cpos = hp + back * 2.05 + right * 0.2
    cpos.z = hp.z - 0.04
    aim = hp + (hd - hp) * 0.18
    aim.z = hp.z - 0.15
    cam.view("held_door", t_shed, pos=tuple(cpos), aim=tuple(aim), lens=65, fstop=2.4, size="close",
             why="the line repeats the trigger: her look back at the door is where the viewer feels the cost")
    cam.dolly(t_shed + 0.05, shot.seconds - 0.05, 0.2, ease="ease_out")
    cam.rack_focus(t_shed, t_shed + 0.1, maya.head)
    cam.rack_focus(t_door + 0.15, t_door + 0.85, h_top, fstop=2.4)
    shot.subject("door_handle", h_top, moments=["held_door.b"])

    for a in (maya, guard):
        a.idle()
    cam.finish()
    for o in [box, *box.children_recursive]:                            # the box is hers while she holds it (feet and sight checks)
        if o.name not in maya.coll.all_objects:
            maya.coll.objects.link(o)
    s1.clear_haze_path(cam.ob, shot.frames)
