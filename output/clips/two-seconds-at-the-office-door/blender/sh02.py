"""sh02 - the trigger, Monday morning in pouring rain: the badge-locked door works for Maya (red, then green for her card), a charming
stranger with two coffees runs up behind her shouting "Hold on, thanks!", and she smiles and holds the door for him.

Blocking (sh03 continues it with a match cut): Maya pushes the right leaf open INTO the lobby (as sh03 has it), walks in round its free end and
turns beside it on its lobby side, just past its free end (1.3, 0.95; sh03 opens on her at the lobby's hold_door, 1.35, 0.7), her right hand
round the leaf's free edge holding it wide; the stranger runs along the pavement from approach, stops in the rain at the canopy edge to call
out, then walks in through the doorway to just inside (sh03 finds him at (0.18, 0.78)). The carrier rides on his right palm; his bag hangs
on his left shoulder (the plan), so his left hand is free to wave on the shout.

Every camera stays on the street side of the line between them (camera_side front).
"""
import math

import bmesh
import bpy
from mathutils import Vector

import set_entrance as sp
import sh01 as s1
from stagekit import assets, build, camera, cast, core, furnish, fx

HOLD_SPOT = (1.3, 0.95)                   # Maya, beside the open right leaf on its lobby side, just past its free end (sh03: hold_door 1.35, 0.7)
READER_SPOT = (1.42, -1.62)               # where she stands to tap the reader
PUSH_SPOT = (0.38, -0.62)                 # in front of the right leaf, hand on its handle
IN_SPOT = (0.62, 1.45)                    # inside, past the open leaf's free end
CALL_SPOT = (-0.9, -3.0)                  # where the stranger stops in the rain at the canopy edge to call out (left of the doors)
IN_WAY = (0.25, -0.6)                     # he angles in to the open right half of the doorway
IN_END = (0.38, 0.92)                     # just inside, where he is when the shot ends
LEAF_HOLD = -80.0                         # the leaf as she holds it: its glass face turned to the street-left camera
LEAF_WIDE = -89.0                         # as he passes she swings it wide (sh03 opens with it at -90)


def stranger_kit(st, t0=0.0):
    """Two coffees in a carrier on the right palm; the brown leather bag on his left shoulder, riding at his hip (rigid with his upper body).
    Returns (carrier, bag)."""
    carrier = assets.use("prop_cup_carrier", name="cup_carrier", at=(0, 0, 0))
    bag = assets.use("prop_messenger_bag", name="messenger_bag", at=(0, 0, 0))
    s1.cast_prop(carrier)
    s1.cast_prop(bag)
    st.arm("R", 18, 82, t0, 0.0)
    st.hand("R", "open", t0, 0.0)
    st.hold(carrier, "R", t0, offset=(0.02, 0.0, 0.03))
    # the bag: its body against the left hip, its long side along his front, the strap arch leaning in over the left shoulder
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
    """Her access card: white, a teal NORTHLINE band, held flat in the palm."""
    card = build.box(name, (0.086, 0.054, 0.0016), (0, 0, 0), surface="painted_wall", tint="#F4F6F7", bevel=0.0008)
    band = build.box(name + "_band", (0.086, 0.014, 0.0018), (0, 0, 0), surface="painted_wall", tint="#1F7A80", bevel=0.0)
    band.parent = card
    band.location = (0.0, 0.02, 0.0002)
    return card


def clear_door_rain(x0=0.0, x1=1.03, z1=2.22):
    """The rain-on-glass card runs across the whole glass front, door leaves included: with the right leaf swung open its beads would hang
    in the empty doorway. Cut the card away over the open leaf's doorway (same as sh03)."""
    for ob in [o for o in bpy.data.objects if o.get("sk_atmo") == "rain on glass" and o.type == "MESH"]:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        mw = ob.matrix_world
        inv = mw.inverted()
        for co, no in (((x0, 0, 0), (1, 0, 0)), ((x1, 0, 0), (1, 0, 0)), ((0, 0, z1), (0, 0, 1))):
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=inv @ Vector(co), plane_no=(inv.to_3x3() @ Vector(no)).normalized(), clear_inner=False, clear_outer=False)
        kill = [fc for fc in bm.faces if x0 < (mw @ fc.calc_center_median()).x < x1 and (mw @ fc.calc_center_median()).z < z1]
        if kill:
            bmesh.ops.delete(bm, geom=kill, context="FACES")
        bm.to_mesh(ob.data)
        bm.free()


def stage_xy(a, t):
    core.at_frame(a._f(t))
    p = a.stage.matrix_world.translation
    return Vector((p.x, p.y, 0.0))


def build_shot(shot):
    S = sp.build_set("rain_day")
    M = S["mark"]
    doors, lamp, post = S["doors"], S["reader_lamp"], S["reader_post"]
    leaf_R = furnish.part(doors, "leaf_R")
    furnish.lamp_state(lamp, "red")
    s1.door_lock(leaf_R)
    s1.lower_bands(doors)                                               # the doors as in sh01 and sh07
    s1.clear_door_glass()                                               # her face reads through the open leaf's glass
    h_out = s1.leaf_point(leaf_R, (-0.903, -0.075, 1.05), "handle_R_out")
    edge = s1.leaf_point(leaf_R, (-0.935, -0.02, 1.05), "leaf_R_edge")   # the leaf's free edge, where her hand holds it open
    core.at_frame(1)                                                    # the set's pieces were placed after creation: refresh their matrices
    pad = post.matrix_world @ Vector((0.0, -0.105, 0.965))                 # the tap ring on the reader's sloping head
    shot.notes.append(f"reader tap ring at {tuple(round(v, 3) for v in pad)}")

    # --- words -> times
    t_tapped = shot.t("tapped")
    t_key = shot.t("keycard")
    t_and = shot.t("and")                                               # the first "and": "and a sharp-dressed guy"
    t_sharp = shot.t("sharp-dressed")
    t_behind = shot.t("behind")
    t_yell = shot.t("yelling")
    t_hold = shot.t("Hold on")
    t_being = shot.t("Being")
    t_flash = shot.t("flashed")
    t_smile = shot.t("smile")
    t_held = shot.t("held the office")
    t_door = shot.t("door")

    # --- cast
    maya = cast.from_plan("maya", at=(2.25, -4.5, 0.0), face="right")
    st = cast.from_plan("stranger", at=(M["approach"][0] - 3.7, M["approach"][1], 0.0), face="right")    # off screen, a run-up before approach
    s1.lift_soles(maya)
    s1.lift_soles(st, 0.022)                                           # his soles sit lower than hers: a little more for the feet check
    maya.heading(READER_SPOT, 0.0, 0.0)
    st.heading(CALL_SPOT, 0.0, 0.0)
    carrier, bag = stranger_kit(st, 0.0)
    card = keycard()
    s1.cast_prop(card)
    maya.hold(card, "R", 0.0)                                         # pinched, ready
    for o in (card, *card.children_recursive):
        if o.name not in maya.coll.all_objects:
            maya.coll.objects.link(o)

    cam = camera.Camera()
    cam.line(maya, st)

    # ---------------- Maya: hurrying in from the kerb, shoulders up against the rain, the card ready; the tap; in through the door; the
    # turn, the smile, the held door
    maya.expr("worried", 0.0, 0.0, amount=0.35)                         # rain, Monday, late-ish
    maya.eyes(0.0, -0.15, 0.0, 0.0)
    maya.tilt_head(-8, 0.0, 0.0)                                        # head down into the rain
    t_rd = maya.walk(0.0, READER_SPOT, speed=2.4)
    maya.tilt_head(0, t_rd - 0.1, 0.3)
    shot.notes.append(f"maya at the reader at {t_rd:.2f}s (tap on 'keycard' {t_key:.2f}s)")
    maya.heading((1.55, 0.5), t_rd + 0.05, 0.2)
    maya.eyes(0.0, -0.4, t_rd - 0.2, 0.15)                              # eyes to the reader first
    # the tap, by hand so it reads: the card comes to the ring and rests there while the lamp goes from red to green
    pad_touch = pad + Vector((0.0, -0.035, 0.02))
    pad_near = pad + Vector((-0.06, -0.17, 0.06))
    maya.reach("R", pad_near, t_key - 0.14, 0.32)
    maya.reach("R", pad_touch, t_key, 0.14)
    maya.squash(t_key + 0.01, 0.02, 0.03, 0.08)
    maya.reach("R", pad_touch, t_key + 0.42, 0.42)
    furnish.lamp_state(lamp, "green", t=t_key + 0.1)                    # her card: green, the lock clicks
    maya.reach("R", pad_near, t_key + 0.62, 0.2)
    maya.expr("neutral", t_key + 0.15, 0.3)
    maya.blink(t_key + 0.5)
    # to the door, push the right leaf in, walk through past its free end, round to her spot beside it
    t_ps = maya.walk(t_key + 0.66, PUSH_SPOT, speed=2.6)
    core.show(card, t_ps - 0.05, False)                                 # the card back in her pocket, while the camera is down the pavement
    maya.heading((0.1, 1.0), t_ps + 0.02, 0.15)
    maya.hand("R", "open", t_ps + 0.05, 0.1)
    maya.reach("R", h_out, t_ps + 0.25, 0.22)
    t_o0, t_o1 = t_ps + 0.28, t_ps + 0.8
    core.key(leaf_R, "rotation_euler", t_o0, (0.0, 0.0, 0.0))
    core.move(leaf_R, t_o0, t_o1, rotation_deg=(0, 0, -42.0))           # she pushes it in...
    for k in range(1, 4):
        maya.reach("R", h_out, t_o0 + (t_o1 - t_o0) * k / 3, (t_o1 - t_o0) / 3)
    core.move(leaf_R, t_o1, t_o1 + 0.75, rotation_deg=(0, 0, LEAF_HOLD))  # ...and it swings on, wide
    maya.lean(5, t_o0 + 0.2, 0.25)
    maya.lean(0, t_o1 + 0.2, 0.3)
    maya.pose("rest", t_o1 + 0.1, 0.3)
    t_in = maya.walk(t_o1 - 0.05, IN_SPOT, speed=2.6)
    t_hd = maya.walk(t_in + 0.05, HOLD_SPOT, speed=2.4)
    shot.notes.append(f"maya through the door at {t_in:.2f}s, at her spot by the leaf at {t_hd:.2f}s")
    # she hears him: eyes, then head, then the turn back to the doorway; her right hand goes round the leaf's free edge and holds it wide
    t_hear = max(t_being - 0.25, t_hd + 0.15)
    maya.eyes(-0.8, 0.0, t_hear, 0.15)
    maya.expr("surprised", t_hear + 0.1, 0.15, amount=0.35)
    maya.heading((0.15, -0.6), t_hear + 0.4, 0.45)
    t_grab = t_hear + 0.55
    maya.hand("R", "grip", t_grab, 0.12)
    maya.reach("R", edge, t_grab, 0.3)
    maya.expr("neutral", t_grab + 0.2, 0.3)
    maya.eyes(-0.3, 0.0, t_grab + 0.1, 0.25)
    maya.expr("happy", t_flash - 0.1, 0.2, amount=0.6)
    maya.do("smile", hit=t_smile)                                       # the smile lands on "smile"
    maya.blink(t_smile + 0.7)
    # as he passes she swings the leaf wide for him: the hand rides on its edge
    t_w0, t_w1 = t_held - 0.25, t_held + 0.45
    core.key(leaf_R, "rotation_euler", t_w0, (0.0, 0.0, math.radians(LEAF_HOLD)))
    core.move(leaf_R, t_w0, t_w1, rotation_deg=(0, 0, LEAF_WIDE))
    for k in range(1, 4):
        maya.reach("R", edge, t_w0 + (t_w1 - t_w0) * k / 3, (t_w1 - t_w0) / 3)
    maya.reach("R", edge, shot.seconds - 0.05, 0.3)
    maya.eyes(-0.6, 0.0, t_held - 0.3, 0.3)                             # watches him go past
    maya.blink(t_door + 0.4)
    shot.notes.append(f"maya holds the door from {t_grab:.2f}s")

    # ---------------- the stranger: runs in from approach, coffees up at his shoulder; calls out with his free hand up; walks in past her
    st.expr("happy", 0.0, 0.0, amount=0.6)
    st.eyes(0.3, 0.05, 0.0, 0.0)
    st.arm("R", 62, 78, 0.0, 0.0, plane="out")                          # the carrier up at shoulder height, out to his side, clear of his face
    st.arm("L", 14, 26, 0.0, 0.0)
    run_dist = (Vector(CALL_SPOT) - Vector(M["approach"][:2])).length + 3.7
    t_go = 2.75                                                         # he arrives at the canopy edge just before "yelling"
    t_arr = st.walk(t_go, CALL_SPOT, speed=1.0, cycle="run", arms=False)
    shot.notes.append(f"stranger runs {t_go:.2f}-{t_arr:.2f}s ({run_dist:.1f} m); 'behind her' at {t_behind:.2f}s")
    st.squash(t_arr + 0.02, 0.08, 0.06, 0.16)                           # the stop
    # the call: eyes on her, face open, a lean in, the free hand up palm out, mouth on the quote
    st.heading((HOLD_SPOT[0] - 0.4, HOLD_SPOT[1] - 1.0), t_yell - 0.05, 0.3)   # turns to her on the cut, not before (no back-of-head hold)
    st.eyes(0.4, 0.15, t_yell - 0.3, 0.15)
    st.expr("excited", t_yell - 0.12, 0.12, amount=0.85)
    st.lean(8, t_yell + 0.05, 0.2)
    st.hand("L", "open", t_yell - 0.05, 0.1)
    st.arm("L", 128, 70, t_yell + 0.1, 0.25, plane="out")               # "Hold on!": the free hand up beside his face, palm out
    st.arm("R", 66, 80, t_yell + 0.1, 0.25, plane="out")                # the coffees held up level, out to the side
    st.squash(t_hold + 0.02, -0.05, 0.05, 0.12)
    st.speak("Hold on", "thanks")
    st.expr("grin", shot.t("thanks") + 0.25, 0.2, amount=0.8)
    st.lean(0, t_being - 0.1, 0.35)
    st.arm("L", 14, 26, t_being + 0.1, 0.35)
    st.arm("R", 30, 86, t_being + 0.2, 0.35)                            # the coffees back in front of him to walk in
    st.blink(t_being + 0.2)
    t_w = t_held - 1.2
    t_mid = st.walk(t_w, IN_WAY, speed=3.0, arms=False)
    t_end = st.walk(t_mid, IN_END, speed=3.0, arms=False)
    st.eyes(0.6, 0.05, t_w + 0.8, 0.2)                                  # a glance at her as he passes
    st.head_turn(0.6, t_held - 0.2, 0.3)
    st.expr("happy", t_held, 0.2, amount=0.75)
    shot.notes.append(f"stranger walks in {t_w:.2f}-{t_end:.2f}s")
    # wet pavement under his shoes
    for k in range(7):
        tk = t_go + 0.3 + k * (t_arr - t_go - 0.4) / 6
        p = stage_xy(st, tk)
        fx.splash(p + Vector((0, 0, 0.01)), tk, size=0.28, drops=9, seed=40 + k)

    shot.subject("maya", maya.head, moments=["rain_morning"])
    shot.subject("stranger", st.head, moments=["coffee_guy", "hold_on"])
    shot.subject("reader_lamp", lamp, moments=["taps_card"])
    shot.subject("keycard", card, moments=["card_on_reader"])
    shot.subject("maya_hand_on_door", edge, moments=["holds_door"])
    shot.moment("card_on_reader", t_key + 0.02)

    # ---------------- camera
    H = S["high"]
    # rain_morning: from over the near parking lane, crane down to the forecourt as she hurries to the doors (she lands left of centre)
    cam.view("rain_morning", 0.0, pos=H[0], aim=(1.05, -2.4, 1.2), lens=24, size="wide",
             why="the same front, now in pouring rain on a grey Monday: same place, a different day")
    t_cut1 = t_tapped - 0.52
    cam.crane(0.0, t_cut1 - 0.05, rise=-4.4, back=-2.3, ease="ease_out")

    # taps_card: past her right arm, onto the reader: the card on the ring, the lamp from red to green; then the whip down the pavement
    core.at_frame(shot.f(t_key))
    cam.view("taps_card", t_cut1, pos=(2.02, -2.42, 1.2), aim=(1.55, -1.06, 1.0), lens=55, size="close",
             why="the mechanism the story turns on: the door opens only for a badge, seen working before it is bypassed")
    cam.dolly(t_tapped - 0.2, t_and, 0.12, ease="ease_out")
    t_land = t_sharp + 0.12
    J = 1.0                                                             # the track's join: the whip lands half a join ahead of him
    sx = stage_xy(st, t_land + J * 0.5)
    shot.notes.append(f"stranger at x {sx.x:.2f} when the whip lands ({t_land:.2f}s)")
    # coffee_guy: the camera leads him on the kerb side, three-quarter front, backing away as he comes on: face, tie and coffees, the planters
    # and bollards sliding past; Maya and the doors come in behind him as he arrives
    side_deg, dist = 48.0, 2.7
    tr = Vector((1.0, 0.0, 0.0))
    out = Vector((math.cos(math.radians(-side_deg)), math.sin(math.radians(-side_deg)), 0.0))
    lead = 0.6
    land = (Vector((sx.x + out.x * dist, sx.y + out.y * dist, 1.3)), Vector((sx.x + lead, sx.y, 1.32)), 32.0)
    cam.whip(t_land - 0.27, to=land, dur=0.27, vid="coffee_guy",
             why="the man who changes everything, introduced as the narrator describes him")
    cam.track_with(st, t_land, t_arr - 0.1, side=side_deg, distance=dist, height=1.3, aim_height=1.32 - 0.0, lead=lead, smooth=0.08, join=J,
                   settle=0.5)

    # hold_on: his face three-quarter from the doorway side of the street, the coffees and his raised free hand beside it; a quick push on the shout
    core.at_frame(shot.f(t_hold))
    hp = st.head.point()
    fwd = Vector((HOLD_SPOT[0] - 0.4 - hp.x, HOLD_SPOT[1] - 1.0 - hp.y, 0)).normalized()
    side = Vector((fwd.x * math.cos(math.radians(-40)) - fwd.y * math.sin(math.radians(-40)),
                   fwd.x * math.sin(math.radians(-40)) + fwd.y * math.cos(math.radians(-40)), 0))
    cpos = hp + side * 1.75 + Vector((0, 0, -0.02))
    cam.view("hold_on", t_yell, pos=tuple(cpos), aim=(hp.x, hp.y, hp.z + 0.03), lens=45, size="close",
             why="a quoted line gets the face that says it")
    cam.dolly(t_yell + 0.05, t_yell + 0.95, 0.28, ease="ease_out")

    # holds_door: from street-left of the doorway, through the open doorway: the open leaf's glass face, Maya beside it holding its edge, her
    # smile; he slips past her into the lobby; the push lands on her hand on the door
    core.at_frame(shot.f(t_being + 0.6))
    ep = edge.matrix_world.translation.copy()
    cam.view("holds_door", t_being, pos=(-0.13, -2.62, 1.42), aim=(ep.x + 0.22, ep.y + 0.08, 1.3), lens=80, fstop=2.8, size="medium",
             why="the trigger itself, two seconds of courtesy, large and readable")
    cam.dolly(t_being + 0.1, shot.seconds - 0.05, 0.2, ease="ease_out")
    cam.rack_focus(t_being, t_being + 0.1, maya.head)
    cam.rack_focus(t_door - 0.2, t_door + 0.4, edge, fstop=2.8)

    maya.idle(0.0, t_grab - 0.4)                                        # no idle while she holds the leaf: it would take her arm off it
    st.idle()
    cam.finish()
    clear_door_rain()
    s1.clear_haze_path(cam.ob, shot.frames)
