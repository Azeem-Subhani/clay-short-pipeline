"""sh03 - the turn: the man with no badge walks in through the door Maya holds, walks through the speed gates beside her as she badges,
his chest bare of any lanyard, and the lobby camera high on the west wall sees all of it. Rain day.

Views (plan): through_doors (from the wet forecourt behind him, through the open glass door; the path runs left of him so Maya, holding the
right leaf wide exactly as sh02 leaves her, stays in the right third) -> past_gate (the through lands in the lobby and swings round east of
the gates into a two-shot: Maya taps her card at the reader, teal lanyard on, as he walks through the lane beside her with nothing round his
neck; then a ~25 degree tilt up, the lens no longer than 45 mm, to the security dome on the west wall, their heads still at the bottom) ->
cctv_pov (the locked security-camera picture, unchanged: the door still swinging shut top right, Maya at the lifts with her back three-quarter
to the lens, the stranger crossing the lower half of the frame and out at its right edge toward the office opening beside the camera).

Staging notes:
  * Continuity with sh02 is read from sh02.py itself (HOLD_SPOT, LEAF_WIDE, IN_END) so the match cut holds when that shot changes.
  * The bag rides on his left shoulder at the hip, as sh02 has it.
  * The set's own dome hangs in the alcove between the lift core and the west wall (behind the 3.4 m core): from the gates it is hidden. This
    shot hangs a second dome (the same kit piece) high on the west wall just south of the core: it is the camera the tilt finds and the camera
    whose picture cctv_pov shows. A set fix would move the set's dome there; the shot does it without editing the set.
  * CCTV_LOOK is the security-footage look as a card in front of the lens, shown only in cctv_pov. render_cctv_frame.py uses the same card
    and the same camera at 16:9 for assets/cctv_frame.png (the frame sh06 and sh08 put on screens).
"""
import math

import bpy
from mathutils import Vector

import set_lobby as sp
from stagekit import assets, build, camera, cast, core, furnish

CCTV_TEXT = "LOBBY CAM 2   MON 08:47"
T_FRAME = 0.30           # the moment of the saved CCTV frame: Maya holds the door wide, the stranger steps in past her
DOME_AT = (-6.99, 6.75, 3.62)          # the shot's dome: on the west wall, just south of the lift core's front (the corner by the lifts)
DOME_SCALE = 1.35
DOME_PT = (-6.99 + 0.15 * DOME_SCALE, 6.75, 3.62 + 0.10 * DOME_SCALE)        # the smoked half-sphere
CCTV_POS = (-6.35, 6.70, 3.70)                                                 # its picture: just in front of the dome
_yaw, _pitch = math.radians(-24.0), math.radians(-26.0)
CCTV_AIM = (CCTV_POS[0] + 8 * math.cos(_yaw) * math.cos(_pitch), CCTV_POS[1] + 8 * math.sin(_yaw) * math.cos(_pitch), CCTV_POS[2] + 8 * math.sin(_pitch))
CCTV_LENS = 18.0


# ----------------------------------------------------------------------------------------------- the security-footage card
def _veil_image(name, w, h):
    """RGBA picture for the card: grey-green wash, scanlines, a darker rim, a dark bar along the top, a red REC dot."""
    import numpy as np
    im = bpy.data.images.get(name)
    if im is not None:
        bpy.data.images.remove(im)
    im = bpy.data.images.new(name, w, h, alpha=True)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / (w - 1), yy / (h - 1)                       # v = 0 at the bottom
    rgb = np.zeros((h, w, 3), np.float32)
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = 0.36, 0.44, 0.38
    a = np.full((h, w), 0.13, np.float32)                   # the wash: takes the colour down toward grey-green
    lines = (np.floor(yy / 2.0) % 2 == 0)
    a = np.where(lines, a + 0.12, a)                        # scanlines
    rgb[lines] *= 0.35
    r = np.sqrt((u - 0.5) ** 2 * 1.2 + (v - 0.5) ** 2 * 1.2)
    vig = np.clip((r - 0.38) / 0.4, 0, 1) * 0.45
    rgb = rgb * (1 - vig[..., None])
    a = np.clip(a + vig, 0, 1)
    bar_h = 0.045 if h > w else 0.085
    top = 0.905 if h > w else 1.0                           # portrait: the bar sits below the Shorts UI at the top
    bar = (v > top - bar_h) & (v <= top)
    rgb[bar] = (0.02, 0.025, 0.03)
    a[bar] = 0.62
    # the REC dot, right inside the bar
    cx, cy = (0.86 if h > w else 0.955), top - bar_h / 2
    rad = bar_h * 0.28
    d = np.sqrt(((u - cx) * w) ** 2 + ((v - cy) * h) ** 2) / h
    dot = d < rad
    rgb[dot] = (1.0, 0.16, 0.12)
    a[dot] = 1.0
    px = np.dstack([rgb, a[..., None]]).astype(np.float32)
    im.pixels.foreach_set(px.ravel())
    im.pack()
    return im, bar_h, (cx, cy)


def _emit_mat(name, col, strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*col, 1.0)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def set_light_for_stills():
    """The security-camera stills (render_cctv_frame.py, render_cctv_zoom.py) show the lobby in the set's own light: undo this shot's
    through_doors dimming of the glass front's key and its fill on Maya."""
    kf = bpy.data.objects.get("KEY_front")
    if kf is not None and "e_set" in kf.keys():
        kf.data.animation_data_clear()
        kf.data.energy = float(kf["e_set"])
    mf = bpy.data.objects.get("FILL_maya_door")
    if mf is not None:
        mf.data.animation_data_clear()
        mf.data.energy = 0.0


def cctv_look(cam_ob, lens, res_w, res_h, frames=None, name="CCTV_LOOK"):
    """The footage card in front of the lens of cam_ob (lens in mm, the render's width and height in pixels). frames=(f0, f1): visible in
    the render only on those frames (None: always). It is hidden from the viewport depsgraph, so the camera checks do not see it."""
    d = 0.12
    big = d * camera.SENSOR / lens
    W, H = (big, big * res_h / res_w) if res_w >= res_h else (big * res_w / res_h, big)
    root = bpy.data.objects.new(name, None)
    core.link(root, "FX")
    root.parent = cam_ob
    root.matrix_parent_inverse.identity()
    root.location = (0, 0, -d)
    im, bar_h, (cx, cy) = _veil_image(f"{name}_img", 270 if res_w < res_h else 640, 480 if res_w < res_h else 360)
    me = bpy.data.meshes.new(f"{name}_card")
    me.from_pydata([(-W / 2, -H / 2, 0), (W / 2, -H / 2, 0), (W / 2, H / 2, 0), (-W / 2, H / 2, 0)], [], [(0, 1, 2, 3)])
    uvl = me.uv_layers.new(name="UVMap")
    for lp, uv in zip(me.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        uvl.data[lp.index].uv = uv
    m = bpy.data.materials.new(f"{name}_mat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = im
    tx.interpolation = "Closest"
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tx.outputs["Color"], em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tx.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass
    me.materials.append(m)
    card = bpy.data.objects.new(f"{name}_card", me)
    core.link(card, "FX")
    card.parent = root
    obs = [card]
    white = _emit_mat(f"{name}_white", (0.93, 0.96, 0.92), 1.6)
    red = _emit_mat(f"{name}_red", (1.0, 0.25, 0.2), 2.0)
    th = bar_h * H * 0.55
    for body, x, align, mt in ((CCTV_TEXT, -W / 2 + W * 0.035, "LEFT", white),
                               ("REC", (cx - 0.5) * W - th * 0.9, "RIGHT", red)):
        cu = bpy.data.curves.new(f"{name}_{body[:3]}", "FONT")
        cu.body = body
        cu.size = th
        cu.align_x = align
        cu.align_y = "CENTER"
        cu.materials.append(mt)
        ob = bpy.data.objects.new(f"{name}_{body[:3]}", cu)
        core.link(ob, "FX")
        ob.parent = root
        ob.location = (x, (cy - 0.5) * H, 0.0004)
        obs.append(ob)
    for o in [root, *obs]:
        o.hide_viewport = True
        try:
            o.visible_shadow = False
        except (AttributeError, TypeError):
            pass
        if frames is not None:
            f0, f1 = frames
            for f, hid in ((1, True), (f0, False), (f1 + 1, True)):
                if f < 1:
                    continue
                o.hide_render = hid
                o.keyframe_insert("hide_render", frame=f)
            if f0 <= 1:
                o.hide_render = False
                o.keyframe_insert("hide_render", frame=1)
            for fc in core.fcurves(o):
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"
    return root


# ----------------------------------------------------------------------------------------------- helpers
def cast_prop(ob):
    """A prop the cast handles is not set dressing: keep it out of the set audit's piece count (it is checked as a held prop)."""
    for o in [ob, *ob.children_recursive]:
        for k in ("sk_type", "sk_kind", "sk_layer"):
            if k in o.keys():
                del o[k]


def leaf_point(leaf, local, name):
    """An empty riding on a door leaf at a leaf-local point (the leaf's origin is its hinge)."""
    e = core.empty(name, (0, 0, 0), size=0.03)
    e.parent = leaf
    e.location = local
    e.hide_render = True
    return e


def stranger_kit(st, t0=0.0):
    """Two coffees in a carrier on the right palm, the brown leather bag by its strap in the left hand. Returns (carrier, bag)."""
    carrier = assets.use("prop_cup_carrier", name="cup_carrier", at=(0, 0, 0))
    bag = assets.use("prop_messenger_bag", name="messenger_bag", at=(0, 0, 0))
    cast_prop(carrier)
    cast_prop(bag)
    st.arm("R", 18, 82, t0, 0.0)
    st.hand("R", "open", t0, 0.0)
    st.hold(carrier, "R", t0, offset=(0.02, 0.0, 0.03))
    st.arm("L", 6, 12, t0, 0.0)
    st.hand("L", "fist", t0, 0.0)
    st.hold(bag, "L", t0, offset=(0.0, 0.0, -0.6), grip=False)       # hangs from the strap: follows the fist, stays upright
    for o in [carrier, *carrier.children_recursive, bag, *bag.children_recursive]:      # carried: his own, not the floor under him
        if o.name not in st.coll.objects:
            st.coll.objects.link(o)
    return carrier, bag


def bag_yaw(bag, t, compass, blend=0.0):
    """The bag hangs at his left side with its flap outward: turn it with him (compass = his heading, 0 toward -Y, 90 toward +X)."""
    z = math.radians(compass + 90.0)
    if blend > 0:
        core.key(bag, "rotation_euler", t - blend)
    core.key(bag, "rotation_euler", t, (0.0, 0.0, z))


def clear_door_rain(x0=0.0, x1=1.03, z1=2.22):
    """The set's rain-on-glass card runs across the whole glass front, door leaves included, as one flat card: with the right leaf swung
    open its beads would hang in the empty doorway. Cut the card away over the open leaf's doorway (the shut left leaf keeps its beads)."""
    import bmesh
    for ob in [o for o in bpy.data.objects if o.get("sk_atmo") == "rain on glass" and o.type == "MESH"]:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        mw = ob.matrix_world
        inv = mw.inverted()
        for co, no in (((x0, 0, 0), (1, 0, 0)), ((x1, 0, 0), (1, 0, 0)), ((0, 0, z1), (0, 0, 1))):
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=inv @ Vector(co), plane_no=(inv.to_3x3() @ Vector(no)).normalized(), clear_inner=False, clear_outer=False)
        kill = []
        for fc in bm.faces:
            c = mw @ fc.calc_center_median()
            if x0 < c.x < x1 and c.z < z1:
                kill.append(fc)
        if kill:
            bmesh.ops.delete(bm, geom=kill, context="FACES")
        bm.to_mesh(ob.data)
        bm.free()




# ----------------------------------------------------------------------------------------------- continuity with sh02
def sh02_ending():
    """HOLD_SPOT, LEAF_WIDE and IN_END as sh02.py has them now (read from the file, not imported: sh02 pulls in another set)."""
    import ast
    import re
    from pathlib import Path
    vals = {"HOLD_SPOT": (1.3, 0.95), "LEAF_WIDE": -89.0, "IN_END": (0.38, 0.92)}
    try:
        txt = (Path(__file__).parent / "sh02.py").read_text(encoding="utf-8")
        for k in vals:
            m = re.search(rf"^{k}\s*=\s*([^#\n]+)", txt, re.M)
            if m:
                vals[k] = ast.literal_eval(m.group(1).strip())
    except Exception:
        pass
    return vals


def stranger_kit_shoulder(st, t0=0.0):
    """As sh02: the coffees in a carrier on the right palm; the brown leather bag on his left shoulder, riding at his hip (rigid with his upper
    body). Returns (carrier, bag)."""
    carrier = assets.use("prop_cup_carrier", name="cup_carrier", at=(0, 0, 0))
    bag = assets.use("prop_messenger_bag", name="messenger_bag", at=(0, 0, 0))
    cast_prop(carrier)
    cast_prop(bag)
    st.arm("R", 18, 82, t0, 0.0)
    st.hand("R", "open", t0, 0.0)
    st.hold(carrier, "R", t0, offset=(0.02, 0.0, 0.03))
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
    for o in [carrier, *carrier.children_recursive, bag, *bag.children_recursive]:
        if o.name not in st.coll.all_objects:
            st.coll.objects.link(o)
    return carrier, bag


def keycard(name="maya_keycard"):
    """Her access card (as sh02): white, a teal NORTHLINE band."""
    card = build.box(name, (0.086, 0.054, 0.0016), (0, 0, 0), surface="painted_wall", tint="#F4F6F7", bevel=0.0008)
    band = build.box(name + "_band", (0.086, 0.014, 0.0018), (0, 0, 0), surface="painted_wall", tint="#1F7A80", bevel=0.0)
    band.parent = card
    band.location = (0.0, 0.02, 0.0002)
    return card


def clear_door_glass(doors, alpha=0.045):
    """The door leaves' glass a little clearer for this shot (as sh02 does at the entrance): Maya stands behind the open right leaf and her
    face must read through it."""
    for leaf in [c for c in doors.children_recursive if str(c.get("sk_part", "")).startswith("leaf")]:
        for ob in [leaf, *leaf.children_recursive]:
            if ob.type != "MESH":
                continue
            for i, sl in enumerate(ob.material_slots):
                if sl.material is None or "glass" not in sl.material.name.lower():
                    continue
                m = bpy.data.materials.get(sl.material.name + "_door_clear")
                if m is None:
                    m = sl.material.copy()
                    m.name = sl.material.name + "_door_clear"
                    for n in m.node_tree.nodes:
                        if n.type == "BSDF_PRINCIPLED":
                            n.inputs["Alpha"].default_value = alpha
                            n.inputs["Roughness"].default_value = 0.02
                if ob.data.users > 1:
                    ob.data = ob.data.copy()
                ob.material_slots[i].material = m


POP = 1.0 / 24.0                       # a cut-pop: lands on one frame (zero-blend keys are avoided mid-shot)
WAIT = (0.36, 2.72)                    # where he slows in front of the middle lane
THROUGH = (0.36, 4.55)                 # through the middle lane, on toward the lifts and the office opening
TAP_LANE = (1.13, 3.0)                 # Maya: the right-hand lane, at its reader


def build_shot(shot):
    S = sp.build_set("rain_day")
    M = S["mark"]
    doors, gate, lifts = S["doors"], S["gate"], S["lifts"]
    leaf = furnish.part(doors, "leaf_R")
    end2 = sh02_ending()
    HOLD = tuple(end2["HOLD_SPOT"])
    LEAF0 = float(end2["LEAF_WIDE"])
    IN0 = tuple(end2["IN_END"])

    # the lobby camera that sees it all (see the notes above)
    dome = furnish.make("security_camera", at=DOME_AT, rot_z=90)
    dome.scale = (DOME_SCALE,) * 3
    cast_prop(dome)

    # --- words -> times
    t_work = shot.t("work")                       # past_gate: the through move lands here
    t_cctv = shot.t("While Maya waited")
    t_elev = shot.t("elevator")
    t_end = shot.seconds

    # --- the door: wide open into the lobby (as sh02 ends); Maya lets it go, the closer swings it shut (still moving as cctv_pov opens)
    core.key(leaf, "rotation_euler", 0.0, (0.0, 0.0, math.radians(LEAF0)))
    edge = leaf_point(leaf, (-0.935, -0.02, 1.05), "leaf_R_edge")          # its free edge, where sh02 has her hand
    clear_door_rain()
    clear_door_glass(doors)
    core.at_frame(1)

    # --- cast
    maya = cast.from_plan("maya", at=(HOLD[0], HOLD[1], 0.0), face="left")
    st = cast.from_plan("stranger", at=(IN0[0], IN0[1], 0.0), face="right")
    maya.heading((0.15, -0.6), 0.0, turn=0.0)                                # as sh02 ends: turned back to the doorway
    st.heading(WAIT, 0.0, turn=0.0)

    cam = camera.Camera()
    cam.line(maya, st)

    carrier, bag = stranger_kit_shoulder(st, 0.0)

    # Maya holds the door wide and watches him in, polite
    maya.hand("R", "grip", 0.0, 0.0)
    maya.reach("R", edge, 0.0, 0.0)
    maya.reach("R", edge, 0.5, 0.2)
    maya.expr("happy", 0.0, 0.0, amount=0.6)
    maya.eyes(0.45, 0.0, 0.0, 0.0)
    maya.eyes(0.2, 0.0, 0.5, 0.3)                                            # her eyes follow him past
    maya.blink(0.7)
    t_let = 0.8
    maya.hand("R", "open", t_let, 0.1)
    maya.pose("rest", t_let + 0.3, 0.3)
    # the closer: slow to start, then the leaf swings home (it is still closing as the CCTV view opens)
    core.key(leaf, "rotation_euler", t_let + 0.25, (0.0, 0.0, math.radians(LEAF0)))
    core.key(leaf, "rotation_euler", t_cctv + 0.55, (0.0, 0.0, math.radians(-4.0)))
    core.key(leaf, "rotation_euler", t_cctv + 0.85, (0.0, 0.0, 0.0))

    # her card, out of her cardigan pocket as she walks to the gates
    card = keycard()
    cast_prop(card)
    core.show(card, 0.0, False)
    core.show(card, t_let + 0.35, True)
    maya.hold(card, "R", t_let + 0.35)
    for o in (card, *card.children_recursive):
        if o.name not in maya.coll.all_objects:
            maya.coll.objects.link(o)

    # to the right-hand lane, card to the reader: the middle lane's flaps fold away for him (lane 2 is the one beside her)
    maya.eyes(-0.6, 0.0, t_let - 0.2)
    reach_gate = maya.walk(t_let + 0.05, to=TAP_LANE, speed=2.8)
    shot.notes.append(f"maya at the reader at {reach_gate:.2f}s")
    reader = Vector((1.605, 3.53, 1.04))
    t_tap = reach_gate + 0.15
    maya.do("press", reader, hit=t_tap, palm=True)
    lamp2 = furnish.part(gate, "lamp_2")
    furnish.lamp_state(lamp2, "green", t=t_tap + 0.05)
    for nm, deg in (("flap_2_L", 90), ("flap_2_R", -90)):
        core.move(furnish.part(gate, nm), t_tap + 0.1, t_tap + 0.45, rotation_deg=(0, 0, deg))
    maya.expr("happy", t_tap - 0.3, 0.2, amount=0.4)

    # he strolls in to the gates with his coffees, a pleased little smile, slows at the middle lane as she taps, and walks through beside her
    st.expr("happy", 0.0, 0.0, amount=0.55)
    st.eyes(0.0, 0.05, 0.0, 0.0)
    at_gate = st.walk(0.05, to=WAIT, speed=1.5, arms=False)
    shot.notes.append(f"stranger at the gates at {at_gate:.2f}s")
    st.eyes(0.7, -0.1, max(at_gate - 0.2, t_tap - 0.45))                    # a glance at her card on the reader
    st.head_turn(0.35, t_tap - 0.15, 0.25)
    st.expr("grin", t_tap, 0.2, amount=0.55)
    t_thru = st.walk(max(at_gate + 0.05, t_tap + 0.2), to=THROUGH, speed=2.0, arms=False)
    st.head_turn(0.0, t_tap + 0.9, 0.35)
    shot.notes.append(f"stranger through the lane {t_tap + 0.2:.2f}-{t_thru:.2f}s")

    # --- the cut compresses time: she is at the lifts, he is through behind her and on his way out under the camera to the office opening
    call = furnish.part(lifts, "call0")
    cp = Vector(call.matrix_world.translation)
    m_at = Vector((cp.x - 0.42, cp.y - 0.62, 0.0))
    maya.place((m_at.x, m_at.y, 0.0), t_cctv)
    maya.heading((cp.x, cp.y), t_cctv, turn=POP)                          # facing the lifts: her back three-quarter to the lens
    maya.pose("rest", t_cctv, POP)
    maya.expr("neutral", t_cctv, POP)
    core.show(card, t_cctv, False)
    maya.do("press", Vector(call.matrix_world.translation) + Vector((0, -0.02, 0)), hit=t_cctv + 0.45)
    try:
        furnish.lamp_state(call, "amber", t=t_cctv + 0.47)
    except Exception:
        pass
    maya.eyes(0.0, 0.25, t_cctv + 0.9, 0.3)                              # up at the floor numbers
    # (fix round 2) he crosses the lower half of the security picture, from beyond the gates (centre) down to its right edge: the west
    # opening to the office lies just off frame right, under the camera's right shoulder, so he leaves toward the office, not at the lens
    s0 = (-2.8, 5.6)                                                       # beyond the gates, west of the lanes, mid-frame
    goal = (-7.25, 4.35)                                                   # through the south half of the west opening, into the office
    st.place((s0[0], s0[1], 0.0), t_cctv)
    st.heading(goal, t_cctv, turn=POP)
    st.head_turn(0.0, t_cctv, POP)
    st.expr("happy", t_cctv, POP, amount=0.35)
    t_off = st.walk(t_cctv, to=goal, speed=2.4, arms=False)
    shot.notes.append(f"cctv_pov: stranger walks {s0} -> {goal}, {t_cctv:.2f}-{t_off:.2f}s ('elevator' at {t_elev:.2f}s)")

    for a in (maya, st):
        a.idle()

    # --- camera
    # through_doors: from the forecourt, left of his line: him left of centre ahead, Maya and the open leaf in the right third
    START = ((-0.06, -2.6, 1.98), (0.84, 1.05, 1.3), 28.0)               # 1.98 m high: the leaf's frosted band (1.4 m) projects below her face
    # past_gate's two-shot pose, which is also where the trip through the door lands: east of the gates on the line from her place at
    # the reader back away from the dome, a little to the south so he stands clear of her, high: the dome is straight up the frame
    mt = Vector((TAP_LANE[0], TAP_LANE[1], 0.0))
    u = (Vector(DOME_PT) - mt)
    u.z = 0.0
    u.normalize()
    perp = Vector((u.y, -u.x, 0.0))                                      # to the south-east of the line
    cpos = mt - u * 1.95 + perp * 0.28
    cpos.z = 2.22
    mid2 = (mt + Vector((WAIT[0], WAIT[1], 0.0))) / 2
    dd = mid2 - cpos
    yaw2 = math.atan2(dd.y, dd.x)
    p2 = math.radians(-28.0)
    TWO = (tuple(cpos), tuple(cpos + Vector((math.cos(yaw2) * math.cos(p2), math.sin(yaw2) * math.cos(p2), math.sin(p2))) * 3.0), 36.0)
    # (fix round 2) through_doors read over-exposed, his charcoal suit washed pale blue: the glass front's cool window key (620 W, just
    # inside the glass, shining in) lands square on his back and on everything the camera sees from the forecourt. For the trip through
    # the door it is held at an eighth and eases back to the set's level just after the camera lands inside; a small warm fill from the lobby side
    # keeps Maya's face and her hand on the leaf readable meanwhile.
    from stagekit import lights
    kf = bpy.data.objects.get("KEY_front")
    t_land0 = t_work - 0.2
    if kf is not None:
        e0 = kf.data.energy
        kf["e_set"] = e0                                                # the set's own level: render_cctv_*.py restore it for the stills
        kf.data.energy = e0 * 0.12
        kf.data.keyframe_insert("energy", frame=1)
        lights.change(kf, t_land0, t_land0 + 0.6, power=e0)
    mf_d = bpy.data.lights.new("FILL_maya_door", "SPOT")
    mf_d.energy, mf_d.spot_size, mf_d.spot_blend, mf_d.use_shadow = 38.0, math.radians(26.0), 0.7, False
    mf_d.color = (1.0, 0.9, 0.78)
    mf = bpy.data.objects.new("FILL_maya_door", mf_d)
    core.link(mf, "LIGHTS")
    mf.location = (2.35, 0.45, 1.85)
    mf.rotation_euler = (Vector((HOLD[0], HOLD[1], 1.3)) - Vector(mf.location)).to_track_quat("-Z", "Y").to_euler()
    lights.change(mf, t_land0, t_land0 + 0.4, power=0.0)
    cam.view("through_doors", 0.0, pos=START[0], aim=START[1], lens=START[2], size="full",
             why="behind him on the wet forecourt: the door Maya holds is the threshold the story turns on; she stays in the right third")
    # through the door: START, the doorway point (0.42, -0.1) and LAND lie on one straight line, so the trip is one eased straight
    # move through the opening (the spline of cam.through kinked at this length and gave acceleration spikes), landing inside on a
    # high look up the lanes with both of them walking up; then round to the two-shot.
    t_land = t_work - 0.2
    LAND = ((0.58, 0.85, 1.95), (mid2.x, mid2.y, 1.0), 30.0)           # just inside, west of the open right leaf (x 0.93), level with its tip: both of them 1.5 m ahead, full figure
    cam.move(0.08, t_land, pos=LAND[0], aim=LAND[1], lens=LAND[2], ease="SINE")
    cam.view("past_gate", t_land, pos=LAND[0], aim=LAND[1], lens=LAND[2], size="full", drift=False,
             why="through the threshold with him, past Maya at the door, into the lobby: the gates, him, her and her card")
    cam.move(t_land + 0.02, t_tap - 0.02, pos=TWO[0], aim=TWO[1], lens=TWO[2], ease="SINE")
    t_two = t_tap
    # then the tilt up to the dome: lens no longer than 45 mm, the dome in the upper third, their heads at the bottom
    d = (Vector(DOME_PT) - cpos)
    horiz = math.hypot(d.x, d.y)
    pitch_dome = math.degrees(math.atan2(d.z, horiz))
    lens1 = 45.0
    half_v = math.degrees(math.atan(camera.SENSOR / 2 / lens1))
    off = math.degrees(math.atan(math.tan(math.radians(half_v)) * 0.40))      # the dome 30% from the top
    p1 = math.radians(pitch_dome - off)
    yaw = math.atan2(d.y, d.x)
    aim1 = cpos + Vector((math.cos(yaw) * math.cos(p1), math.sin(yaw) * math.cos(p1), math.sin(p1))) * 6.0
    t_u0 = t_tap + 0.28
    t_u1 = t_cctv - 0.04
    cam.move(t_u0, t_u1, pos=tuple(cam._pose.pos), aim=tuple(aim1), lens=lens1, ease="SINE")
    d0 = Vector(TWO[1]) - cpos
    p0 = math.degrees(math.atan2(d0.z, math.hypot(d0.x, d0.y)))
    shot.notes.append(f"past_gate: two-shot from {t_two:.2f}s, tilt {p0:.1f} -> {math.degrees(p1):.1f} deg ({math.degrees(p1) - p0:.1f}) "
                      f"{t_u0:.2f}-{t_u1:.2f}s, lens 35 -> {lens1:.0f}")
    cam.view("cctv_pov", t_cctv, pos=CCTV_POS, aim=CCTV_AIM, lens=CCTV_LENS, size="wide", still=True,
             why="the security camera's own locked picture: she waits at the lifts, he walks off to the office")
    cam.hold(t_end)

    sc = bpy.context.scene
    cctv_look(cam.ob, CCTV_LENS, sc.render.resolution_x, sc.render.resolution_y, frames=(shot.f(t_cctv), shot.frames + 1))
    # a security camera has everything sharp: no depth of field in cctv_pov (the footage card 12 cm in front of the lens, with its
    # "LOBBY CAM 2" bar, rendered soft in the final frames)
    dof = cam.data.dof
    for f, on in ((1, True), (shot.f(t_cctv), False)):
        dof.use_dof = on
        dof.keyframe_insert("use_dof", frame=f)
    for c in core.fcurves(cam.data):
        if "use_dof" in c.data_path:
            for kp in c.keyframe_points:
                kp.interpolation = "CONSTANT"

    shot.subject("stranger", st.head, moments=["through_doors", "past_gate.a", "beside_her", "cctv_pov.a"])
    # (Maya is read through the open leaf's clear glass in through_doors: the stills check counts any glass as a wall, so she is a subject
    # from past_gate on; the reviewer judges her through the glass from the strip)
    shot.subject("maya", maya.head, moments=["past_gate.a", "beside_her", "cctv_pov"])
    shot.subject("dome", dome, moments=["past_gate.b", "dome_in_frame"])
    shot.subject("speed_gates", furnish.part(gate, "lamp_1") or gate, moments=["through_doors.b"])
    shot.moment("beside_her", t_tap + 0.35)
    shot.moment("dome_in_frame", t_u1)
    shot.moment("maya_at_door", 0.75)
    shot.moment("cctv_frame_moment", T_FRAME)
    shot.notes.append(f"badge tap at {t_tap:.2f}s")
