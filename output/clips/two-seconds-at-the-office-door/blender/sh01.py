"""sh01 - the hook: Friday dusk, Maya is walked out of her own glass building with her desk in a box, the guard goes back in and
locks the door on her, and the camera ends on the door handle with the red reader lamp: the door is the thing that did it.

Blocking (sh07 continues it exactly): Maya ends at box_spot facing the doors; the guard ends just inside, at GUARD_IN, facing her.
"""
import math

import bmesh
import bpy
from mathutils import Vector, geometry

import set_entrance as sp
from stagekit import actions, assets, build, camera, cast, core, furnish

GUARD_IN = (0.36, 0.30)                   # where the guard stands inside to lock the door: right up to the glass
GUARD_OUT = (0.2, -2.45)                  # a step behind her, at her shoulder, as she stops (closer than the plan's guard mark: he stays in frame)
GUARD_AWAY = (1.15, 2.4)                  # on "for two seconds" he turns and walks off into the lobby; sh07 picks him up here


def leaf_point(leaf, local, name):
    """An empty riding on a door leaf at a leaf-local point (the leaf's origin is its hinge)."""
    e = core.empty(name, (0, 0, 0), size=0.03)
    e.parent = leaf
    e.location = local
    e.hide_render = True
    return e


def door_lock(leaf):
    """A patch lock clamped on the right leaf's glass at handle height, 10 cm in from the meeting stile (a brushed-metal box on both faces
    of the glass): a thumb-turn on the lobby face, a key cylinder on the street face. Returns the thumb-turn."""
    inner = build.box("door_lock_in", (0.07, 0.024, 0.12), (0, 0, 0), surface="brushed_metal", bevel=0.005)
    outer = build.box("door_lock_outbox", (0.07, 0.024, 0.12), (0, 0, 0), surface="brushed_metal", bevel=0.005)
    knob = build.box("door_lock_turn", (0.014, 0.03, 0.055), (0, 0, 0), surface="brushed_metal", tint="#C9CED3", bevel=0.004)
    cyl = build.cyl("door_lock_out", 0.016, 0.012, (0, 0, 0), surface="brushed_metal", tint="#C9A23A", seg=16)
    for ob, loc, rot in ((inner, (-0.80, 0.017, 1.19), (0, 0, 0)), (outer, (-0.80, -0.017, 1.19), (0, 0, 0)),
                         (knob, (-0.80, 0.044, 1.25), (0, 0, 0)), (cyl, (-0.80, -0.031, 1.25), (math.radians(90), 0, 0))):
        ob.parent = leaf
        ob.location = loc
        ob.rotation_euler = rot
    return knob


def lower_bands(doors, dz=-0.45):
    """The doors' frosted manifestation bands, for the entrance shots, at the lower standard height (0.95-1.05 m) instead of 1.40-1.50 m: at
    1.4 m the band crosses the guard's mouth wherever the camera stands, as he works the lock right behind the glass. sh01, sh02 and sh07
    all call this, so the doors are the same in every shot of the set (a set-file change would be the clean fix)."""
    for nm in ("leaf_L", "leaf_R"):
        lf = furnish.part(doors, nm)
        for ob in lf.children:
            if ob.type == "MESH" and ob.data.materials and ob.data.materials[0].name.startswith("SK_solid_#E4ECF1"):
                ob.location.z += dz


def lift_soles(a, dz=0.012):
    """Raise a figure 12 mm. His shoe soles sit 6 mm over the stage origin; the feet check steps 1 cm past its last hit on the figure, so on
    the lobby's stone floor (top at z = 0) it starts below the floor's face and reports him floating over the apron under it. 12 mm is invisible
    and well inside the 6 cm grounding tolerance."""
    e = core.empty(f"{a.stage.name}_lift", (0, 0, dz), size=0.05)
    e.hide_render = True
    a.stage.parent = e


def northline_sign():
    """The NORTHLINE logo on the first spandrel above the canopy (the set's wall_logo at about z 4.8)."""
    best = None
    for ob in bpy.data.objects:
        if ob.get("sk_type") == "wall_logo" and ob.location.y < -0.2 and ob.location.z > 4.0:
            best = ob
    return best


def box_contents(box):
    """Friday: her badge is handed in. The plan's sh07 insert wants a stapler and her teal lanyard lying on top of the desk things: a lanyard laid flat across the contents and a
    small black stapler beside the mug, both riding on the box."""
    lan = furnish.make("keycard_lanyard", at=(0, 0, 0))
    cast_prop(lan)
    lan.parent = box
    lan.location = (0.02, -0.03, 0.262)
    lan.rotation_euler = (math.radians(-82.0), 0.0, math.radians(28.0))
    st = build.box("stapler_base", (0.16, 0.04, 0.012), (0, 0, 0), surface="brushed_metal", tint="#2A2D31", bevel=0.003)
    top = build.box("stapler_arm", (0.15, 0.036, 0.022), (0, 0, 0), surface="brushed_metal", tint="#17191C", bevel=0.006)
    top.parent = st
    top.location = (0.003, 0.0, 0.017)
    st.parent = box
    st.location = (-0.1, 0.075, 0.245)
    st.rotation_euler = (math.radians(14.0), 0.0, math.radians(-12.0))
    return lan, st


def cast_prop(ob):
    """A prop the cast handles is not set dressing: keep it out of the set audit's piece count (it is checked as a held prop)."""
    for o in [ob, *ob.children_recursive]:
        for k in ("sk_type", "sk_kind", "sk_layer"):
            if k in o.keys():
                del o[k]


def carry_box(a, box, t):
    """The kit's carry, re-gripped from below: both palms turned up under the box's bottom, inside its short ends, and the box
    sitting on them against her chest. The forearms run under the box, never through its sides (the hands in the end slots put
    the forearms through the side walls)."""
    tt = t
    pr = actions.aj_front(a, tt, "carry", "R", -0.125) + Vector((0, 0, -0.12))
    pl = actions.aj_front(a, tt, "carry", "L", 0.125) + Vector((0, 0, -0.12))
    for side, p in (("R", pr), ("L", pl)):
        a._want[side] = Vector((0.0, 0.0, 1.0))                        # the palm faces up, under the bottom
        a.reach(side, p, tt, 0.0)
        a._want[side] = None
    for side in "RL":
        a.hand(side, "grip", tt, 0.0)                                   # the fingers curl up round the bottom edge
        a.wrist(side, 55, tt, 0.0)
    core.at_frame(a._f(tt))
    mid = (pr + pl) / 2
    box.location = (mid.x, mid.y, mid.z + 0.03)                         # the bottom rests on the palms
    box.rotation_euler = (0.0, 0.0, math.atan2(pl.y - pr.y, pl.x - pr.x))
    a.hold(box, "R", tt, grip=False, turn=True)                         # held after the hand is shaped: the box stays level


def street_key(target, name="KEY_streetlamp"):
    """A soft cool key from the street lamps on the camera side (about 40 degrees off axis, high): at box_spot, outside the canopy's
    downlights, her face would otherwise take only the warm lobby rim and read darker than under the canopy. sh01 and sh07 share it,
    so her skin is the same in both."""
    from stagekit import lights
    k = lights.rim_light(target, from_deg=40.0, elevation=32.0, distance=3.6, power=210.0, color="#DCE6F4", name=name)
    k["sk_role"] = "key"
    return k


def clear_door_glass(alpha=0.045):
    """The door leaves' glass, for this shot only, a little clearer than the set's shared glass (alpha 0.16, pale blue): through two
    panes of it a face behind the door reads as a grey ghost. The fixed glass front keeps the set's glass."""
    src = bpy.data.materials.get("SURF_glass")
    if src is None:
        return
    m = src.copy()
    m.name = "SURF_glass_door_clear"
    for n in m.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["Alpha"].default_value = alpha
            n.inputs["Roughness"].default_value = 0.02
    for nm in ("glass_doors.leaf_L.1", "glass_doors.leaf_R.1"):
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            ob.data = ob.data.copy()
            ob.data.materials[0] = m


def clear_haze_path(cam_ob, frames, margin=0.7):
    """The street's ground-haze cards are flat soft planes: a camera that flies through one shows a hard fade. Take out the few cards
    this shot's camera passes within `margin` of (they are atmosphere, not dressing; the haze down the street stays)."""
    pos = []
    for f in range(1, frames + 1, 2):
        core.at_frame(f)
        pos.append(cam_ob.matrix_world.translation.copy())
    for ob in [o for o in bpy.data.objects if o.get("sk_atmo") == "haze" and o.type == "MESH"]:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        mw = ob.matrix_world
        kill = []
        for fc in bm.faces:
            vs = [mw @ v.co for v in fc.verts]
            tris = [(vs[0], vs[i], vs[i + 1]) for i in range(1, len(vs) - 1)]
            for p in pos:
                if any((geometry.closest_point_on_tri(p, *tr) - p).length < margin for tr in tris):
                    kill.append(fc)
                    break
        if kill:
            bmesh.ops.delete(bm, geom=kill, context="FACES")
            bm.to_mesh(ob.data)
        bm.free()
        core.current().notes.append(f"haze: {len(kill)} card(s) of {ob.name} on the camera's path taken out")


def build_shot(shot):
    S = sp.build_set("dusk")
    M = S["mark"]
    doors, lamp = S["doors"], S["reader_lamp"]
    leaf_L, leaf_R = furnish.part(doors, "leaf_L"), furnish.part(doors, "leaf_R")
    furnish.lamp_state(lamp, "red")                                     # red all Friday: nobody's card opens it for her
    clear_door_glass()
    lower_bands(doors)

    # --- words -> times
    t_got = shot.t("got escorted")
    t_disaster = shot.t("The whole disaster")
    t_started = shot.t("started")
    t_because = shot.t("because")
    t_held = shot.t("held")
    t_door = shot.t("door")
    t_two = shot.t("two")

    # --- the door: both leaves open as they come out; the closer swings them shut behind them in the last second of box_out
    for lf, deg in ((leaf_L, -86.0), (leaf_R, 82.0)):            # swung wide open: both walk out clear of the leaves
        lf.rotation_euler.z = math.radians(deg)
        core.key(lf, "rotation_euler", 0.0)
    core.key(leaf_L, "rotation_euler", 2.1)
    core.key(leaf_R, "rotation_euler", 2.2)
    core.move(leaf_L, 2.1, 3.2, rotation_deg=(0, 0, 0))
    core.move(leaf_R, 2.2, 3.3, rotation_deg=(0, 0, 0))
    h_out = leaf_point(leaf_R, (-0.903, -0.075, 1.05), "handle_R_out")
    knob = door_lock(leaf_R)
    lock_pt = leaf_point(leaf_R, (-0.80, 0.075, 1.25), "lock_R_in")
    glass_pt = leaf_point(leaf_R, (-0.55, 0.05, 1.3), "glass_R_in")      # where his other palm presses on the inside of the glass

    # --- cast
    maya = cast.from_plan("maya", at=(-0.32, 0.35, 0.0), face="right")
    guard = cast.from_plan("guard", at=(0.18, 0.95, 0.0), face="right")       # a step behind her shoulder
    lift_soles(guard)
    maya.heading((M["box_spot"][0], M["box_spot"][1]), 0.0, 0.0)
    guard.heading(GUARD_OUT, 0.0, 0.0)
    box = assets.use("prop_cardboard_box_desk", name="desk_box", at=(-0.32, 0.0, 1.0))
    cast_prop(box)
    box_contents(box)
    maya.hide("addon:lanyard_badge")                                   # handed in: her badge lies in the box (sh07's insert shows it)
    shot.subject("box", box, moments=["box_out"])
    street_key(M["box_spot"])

    cam = camera.Camera()
    cam.line(maya, guard)

    # Maya: already walking out on frame one, the box against her chest, stunned
    carry_box(maya, box, 0.0)
    maya.expr("worried", 0.0, 0.0, amount=0.75)
    maya.eyes(0.0, -0.3, 0.0, 0.0)
    maya.blink(0.5)
    t_m = maya.walk(0.0, (M["box_spot"][0], M["box_spot"][1]), speed=2.5, arms=False)
    shot.notes.append(f"maya arrives at box_spot at {t_m:.2f}s")
    maya.eyes(0.0, -0.7, t_m - 0.2, 0.3)                                 # she stops and looks down at her box
    maya.expr("sad", t_m, 0.4, amount=0.65)
    # the door thuds behind her: the eyes go first, then the head, then she turns round with the box to look back at it
    t_turn = t_got + 1.55
    maya.eyes(-1.0, 0.1, t_turn - 0.3, 0.2)
    maya.head_turn(-0.5, t_turn - 0.1, 0.25)
    maya.heading((M["box_spot"][0] + 0.45, 4.0), t_turn + 0.6, 0.7)
    maya.head_turn(0.0, t_turn + 0.65, 0.3)
    maya.eyes(0.0, 0.05, t_turn + 0.55, 0.2)
    maya.expr("worried", t_started + 0.1, 0.25)                          # the lock clacks: dread
    maya.squash(t_started + 0.15, -0.04, 0.2, 0.3)

    # the guard: at her shoulder, then back to the door, pulls it open, goes in, and locks it from inside, his hand on the thumb-turn
    t_g = guard.walk(0.1, GUARD_OUT, speed=2.8)
    shot.notes.append(f"guard at her shoulder at {t_g:.2f}s")
    guard.expr("neutral", 0.0, 0.0)
    guard.eyes(-0.5, -0.2, t_g - 0.4, 0.3)                               # a glance at her
    stand = (0.06, -0.8)
    t_g2 = guard.walk(max(t_g + 0.2, t_got - 0.3), stand, speed=3.0)     # beside her to the end of box_out, then back to the door
    shot.notes.append(f"guard at the door at {t_g2:.2f}s")
    guard.heading((0.25, 3.0), t_g2 + 0.12, 0.2)
    t_reach = t_g2 + 0.22
    guard.hand("R", "fist", t_reach, 0.08)
    guard.reach("R", h_out, t_reach, 0.22)
    t_o0, t_o1 = t_reach + 0.04, t_reach + 0.6
    core.key(leaf_R, "rotation_euler", t_o0, (0.0, 0.0, 0.0))
    core.move(leaf_R, t_o0, t_o1, rotation_deg=(0, 0, 55.0))
    for k in range(1, 5):                                                # the hand stays on the handle as it swings
        guard.reach("R", h_out, t_o0 + (t_o1 - t_o0) * k / 4, (t_o1 - t_o0) / 4)
    guard.lean(-6, t_o0 + 0.3, 0.3)
    guard.lean(0, t_o1 + 0.3, 0.3)
    guard.pose("rest", t_o1 + 0.3, 0.3)
    t_in = guard.walk(t_o1 + 0.02, GUARD_IN, speed=3.0)
    shot.notes.append(f"guard inside at {t_in:.2f}s")
    t_shut = min(t_in + 0.25, max(t_disaster - 0.1, t_in - 0.1))
    core.move(leaf_R, t_in - 0.45, t_shut, rotation_deg=(0, 0, 0))      # the closer pulls it shut behind him
    guard.heading((0.36, -5.0), t_in + 0.3, 0.3)
    # the lock: eyes to it, the left palm flat on the glass to hold the leaf, the right hand up to the thumb-turn; the turn lands on
    # "started" (the knob turns a quarter with the wrist: the clack)
    guard.eyes(-0.35, -0.15, t_started - 0.75, 0.2)
    guard.reach("L", glass_pt, t_started - 0.45, 0.35)
    guard.hand("L", "open", t_started - 0.45, 0.2)
    guard.hand("R", "pinch", t_started - 0.3, 0.1)
    guard.reach("R", lock_pt, t_started - 0.12, 0.38)
    guard.wrist("R", -70, t_started + 0.08, 0.16)
    core.key(knob, "rotation_euler", t_started - 0.08)
    core.move(knob, t_started - 0.08, t_started + 0.08, rotation_deg=(0, 90.0, 0))
    guard.lean(3, t_started, 0.3)
    guard.reach("R", lock_pt, t_started + 0.9, 0.3)                      # holds it a beat
    guard.eyes(0.4, -0.2, t_started + 0.55, 0.3)                         # then he looks out at her through the glass
    guard.expr("sad", t_started + 0.8, 0.4, amount=0.3)                  # not unkind: a job
    t_away = shot.t("for")                                               # job done: he turns his back on her and walks off into the lobby
    guard.lean(0, t_away - 0.4, 0.3)
    guard.pose("rest", t_away - 0.1, 0.35)
    guard.eyes(0.8, 0.0, t_away - 0.25, 0.2)
    guard.walk(t_away, GUARD_AWAY, speed=2.6)

    # the guard is checked where he is in the open; in locked_out he stands behind the door's glass (the ray check cannot see through glass)
    shot.subject("guard", guard.head, moments=["box_out", "building.a"])

    # --- camera
    # box_out: she walks straight at the lens out of the doors, the camera backing away with her, the guard at her shoulder, the lit lobby behind
    cam.view("box_out", 0.0, pos=(-0.22, -2.45, 1.45), aim=(-0.12, 0.6, 1.06), lens=40, size="medium",
             why="the first second: a woman walked out of her building with her desk in a box, a guard at her shoulder")
    cam.follow(maya, 0.0, 2.6, smooth=0.3, settle=0.5)

    # building: low on the road, a lamp post at the right edge; the crane rises and backs away across the road until the two small figures
    # stand under the NORTHLINE sign (the sign settles near 0.40 from the top, the figures in the lower third above the captions)
    cam.view("building", t_got, pos=(2.3, -8.3, 0.45), aim=(0.4, -2.2, 2.3), lens=24, size="wide",
             why="her building and how small she is in front of it")
    cam.crane(t_got, t_disaster - 0.05, rise=2.0, back=4.5, tilt_to=1.5, ease="ease_in_out")     # between the parked cars, over their roofs
    sign = northline_sign()
    if sign is not None:
        shot.subject("northline_sign", sign, moments=["building.b"])

    # locked_out: past her right shoulder and the box corner (soft, lower left), through the door glass: the guard locks the door. The view
    # opens focused on her; the focus racks to his hand on the lock on "started"; on "because" the camera pushes in on the handle she will
    # be blamed for, then slides right along the glass until the red reader lamp stands beside the handle on "two seconds"
    core.at_frame(shot.f(t_disaster))
    sh_pt = maya.chest.point() + Vector((0.16, 0.0, 0.2))
    f0 = camera.Framing((-0.45, -4.3, 1.42), (0.22, -0.05, 1.42), 55.0, fstop=2.0, focus=sh_pt)
    cam.view("locked_out", t_disaster, framing=f0, size="close", why="the cause: the door, now shut to her")
    cam.rack_focus(t_disaster + 0.3, t_started + 0.02, lock_pt, fstop=2.0)
    cam.dolly(t_because - 0.15, t_held + 0.45, 0.28, ease="ease_in_out")
    cam.rack_focus(t_held - 0.1, t_door + 0.1, h_out, fstop=2.2)
    cam.move(t_held + 0.4, t_two + 0.6, pos=(2.55, -2.0, 1.22), aim=(0.25, -0.07, 1.08), lens=65.0, ease="SINE")
    cam.dolly(t_two + 0.6, shot.seconds - 0.05, 0.04, ease="ease_out")
    cam.rack_focus(t_two - 0.1, t_two + 0.6, lamp, fstop=2.4)
    shot.subject("door_handle", h_out, moments=["locked_out"])
    shot.subject("reader_lamp", lamp, moments=["locked_out.b"])

    maya.idle()
    guard.idle(0.0, t_started - 1.0)                                    # no idle over the lock: it would take his arms off the door
    cam.finish()
    for o in [box, *box.children_recursive]:                            # the box is hers while she holds it (feet and sight checks)
        if o.name not in maya.coll.all_objects:
            maya.coll.objects.link(o)
    clear_haze_path(cam.ob, shot.frames)
    for f in (150, 175, 200):
        core.at_frame(f)
        shot.notes.append(f"guard stage at f{f}: {tuple(round(v, 2) for v in guard.stage.matrix_world.translation)}")
