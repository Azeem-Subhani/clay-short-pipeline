"""aj_hands - the six hand shapes of the actor API on Aj's real finger bones, and grips that close on a held prop.

Shapes (fig3d.HAND_SHAPES): mitten (relaxed, the rest), open, fist, point, pinch, grip. Each is a table of finger
angles in the grips solver's own convention (ajkit.grips.Hand): fingers flex about their local +X (toward the palm,
both hands), spread about local Z (mirrored on the left), the thumb is [lift, twist, swing, bend2, bend3].

The actor keys hand_<side>_<shape> weights on its control empty while the shot is written; bake() turns them into
finger-bone rotations once per frame. A hold with a solved grip adds a layer of its own angles over a frame range.

    aj_hands.bake(actor, frames)
    aj_hands.solve_grip(actor, prop, side, frame) -> (angles, report) or (None, reason)
"""
from __future__ import annotations

import math

import bpy
from mathutils import Euler, Vector

from . import core

RAD = math.radians
FINGERS = ("Index", "Middle", "Ring", "Pinky")
P = "mixamorig:"

# flex (joint1, joint2, joint3) per finger, spread per finger, thumb [lift, twist, swing, bend2, bend3]; degrees
SHAPES = {
    "mitten": {"flex": {"Index": (10, 14, 8), "Middle": (12, 16, 9), "Ring": (14, 18, 10), "Pinky": (16, 20, 12)},
               "spread": {"Index": -2, "Middle": 0, "Ring": 2, "Pinky": 4}, "thumb": (8, 0, 8, 8, 8)},
    "open": {"flex": {F: (2, 3, 2) for F in FINGERS}, "spread": {"Index": -8, "Middle": -1, "Ring": 6, "Pinky": 13},
             "thumb": (12, 0, -18, 0, 0)},
    "fist": {"flex": {F: (80, 100, 60) for F in FINGERS}, "spread": {F: 0 for F in FINGERS}, "thumb": (30, 0, 25, 35, 45)},
    "point": {"flex": {"Index": (0, 3, 0), "Middle": (80, 100, 60), "Ring": (84, 100, 60), "Pinky": (86, 100, 60)},
              "spread": {"Index": -3, "Middle": 0, "Ring": 0, "Pinky": 0}, "thumb": (28, 0, 30, 30, 40)},
    "pinch": {"flex": {"Index": (38, 42, 26), "Middle": (28, 32, 20), "Ring": (36, 46, 30), "Pinky": (42, 52, 36)},
              "spread": {"Index": -2, "Middle": 0, "Ring": 2, "Pinky": 4}, "thumb": (36, 0, 32, 22, 22)},
    "grip": {"flex": {F: (56, 66, 44) for F in FINGERS}, "spread": {F: 0 for F in FINGERS}, "thumb": (40, 0, 34, 26, 26)},
}
NAMES = ("mitten", "open", "pinch", "fist", "point", "grip")


def _side_name(s):
    return "Left" if s == "L" else "Right"


def angles(shape: str, side: str) -> dict:
    """bone name -> (x, y, z) radians for a shape on one side (the grips solver's mapping, exactly)."""
    sp = SHAPES[shape]
    sgn = 1.0 if side == "R" else -1.0
    sn = _side_name(side)
    out = {}
    for F in FINGERS:
        for j, a in enumerate(sp["flex"][F], 1):
            n = f"{P}{sn}Hand{F}{j}"
            out[n] = (RAD(a), 0.0, RAD(sp["spread"][F]) * sgn if j == 1 else 0.0)
    x = [RAD(v) for v in sp["thumb"]]
    t = [f"{P}{sn}HandThumb{j}" for j in (1, 2, 3)]
    out[t[0]] = (x[0], x[1] * sgn, x[2] * sgn)
    out[t[1]] = (-x[3], 0.0, 0.0)
    out[t[2]] = (-x[4], 0.0, 0.0)
    return out


def _sampler(ctrl, prop):
    for fc in core.fcurves(ctrl):
        if fc.data_path == f'["{prop}"]':
            return lambda f, fc=fc: fc.evaluate(f)
    v = float(ctrl.get(prop, 0.0))
    return lambda f: v


def bake(actor, frames):
    """Finger rotations per frame from the hand weights and the solved grips."""
    arm = actor.rig
    tables = {s: {h: angles(h, s) for h in NAMES} for s in "LR"}
    pb = arm.pose.bones
    for s in "LR":
        ws = {h: _sampler(actor.ctrl, f"hand_{s}_{h}") for h in NAMES[1:]}
        bones = list(tables[s]["mitten"])
        series = {n: ([], [], []) for n in bones}
        layers = [g for g in actor._grip_layers if g["side"] == s]
        for f in frames:
            w = {h: max(0.0, min(1.0, fn(f))) for h, fn in ws.items()}
            tot = sum(w.values())
            if tot > 1.0:
                w = {h: v / tot for h, v in w.items()}
                tot = 1.0
            w["mitten"] = 1.0 - tot
            g = 0.0
            lay = None
            for L in layers:
                if L["f0"] - L["ramp"] <= f <= L["f1"] + L["ramp"]:
                    if f < L["f0"]:
                        g = (f - (L["f0"] - L["ramp"])) / max(1, L["ramp"])
                    elif f > L["f1"]:
                        g = 1.0 - (f - L["f1"]) / max(1, L["ramp"])
                    else:
                        g = 1.0
                    lay = L
            for n in bones:
                v = [0.0, 0.0, 0.0]
                for h, wh in w.items():
                    if wh > 0:
                        a = tables[s][h][n]
                        v = [v[i] + wh * a[i] for i in range(3)]
                if lay is not None and g > 0 and n in lay["angles"]:
                    a = lay["angles"][n]
                    v = [v[i] * (1 - g) + a[i] * g for i in range(3)]
                for i in range(3):
                    series[n][i].append(v[i])
        for n in bones:
            b = pb[n]
            b.rotation_mode = "XYZ"
            path = f'pose.bones["{n}"].rotation_euler'
            for fc in list(core.fcurves(arm)):
                if fc.data_path == path:
                    fc.keyframe_points.clear()
            arm.keyframe_insert(path, frame=frames[0])
            fcs = {fc.array_index: fc for fc in core.fcurves(arm) if fc.data_path == path}
            for i in range(3):
                fc = fcs[i]
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(frames))
                co = []
                for f, v in zip(frames, series[n][i]):
                    co += [float(f), float(v)]
                fc.keyframe_points.foreach_set("co", co)
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
                fc.update()


def set_static(actor, side, shape):
    """Put one hand in a shape now (no keys): used before a grip is solved and for stills."""
    for n, e in angles(shape, side).items():
        b = actor.rig.pose.bones[n]
        b.rotation_mode = "XYZ"
        b.rotation_euler = e


def asset_entry(prop) -> dict:
    """The library index entry of a prop made with assets.use (its root carries asset_id), else {}."""
    o = prop
    while o is not None:
        aid = o.get("asset_id")
        if aid:
            try:
                from . import assets
                return assets.get(aid)
            except Exception:
                return {}
        o = o.parent
    return {}


def _bounds(prop):
    meshes = [o for o in [prop, *prop.children_recursive] if o.type == "MESH"]
    return core.world_bbox(meshes) if meshes else None


def _dims(prop):
    b = _bounds(prop)
    return None if b is None else sorted(b[1] - b[0], reverse=True)


WIDE = 0.30                                              # an object wider than this takes both hands


def prop_kind(prop) -> str:
    """The grip a prop gets: the library entry's `grip` when it has one, else by shape. power: a rod or handle (stick,
    broom, hammer); pinch: a small thin thing (key, card); palm: the object rests against the palm with the fingers
    closed onto it (box, ball, book, plate, bag, cup); palm2: the same with both hands on opposite faces, for things
    wider than WIDE."""
    g = asset_entry(prop).get("grip")
    if g:
        return g
    dims = _dims(prop)
    if dims is None or dims[0] < 1e-6:
        return "none"
    if dims[0] > 2.2 * max(dims[1], 1e-6) and dims[0] > 0.25 and dims[1] < 0.15:
        return "power"
    if dims[0] < 0.12 and dims[2] < 0.025:
        return "pinch"
    if dims[0] > WIDE:
        return "palm2"
    return "palm"


def grip_at(prop) -> float:
    """Where along a rod it is held, 0 = lower end .. 1 = upper end: the library entry's grip_at, else 0.35."""
    return float(asset_entry(prop).get("grip_at", 0.35))


def hold_point(prop):
    """The world point the palm goes to when this prop is picked up: on the handle for a rod (at grip_at), otherwise the
    middle of the prop."""
    from ajkit import grips
    if prop_kind(prop) == "power":
        try:
            return grips.shaft(prop, at=grip_at(prop))["g"]
        except Exception:
            pass
    b = _bounds(prop)
    return prop.matrix_world.translation.copy() if b is None else (b[0] + b[1]) / 2


def two_hand_points(prop, left_dir, gap=0.012):
    """World points just outside the two opposite faces of a wide prop at its middle height: (left hand, right hand). Found
    by shooting a ray at the real mesh from each side (a bag or basket is not its bounding box); gap: metres the palm
    stays off the surface. left_dir: the horizontal unit vector toward the figure's left."""
    from mathutils.bvhtree import BVHTree
    lo, hi = _bounds(prop)
    c = (lo + hi) / 2
    reach = (abs(left_dir.x) * (hi.x - lo.x) + abs(left_dir.y) * (hi.y - lo.y)) / 2 + 0.2
    dg = bpy.context.evaluated_depsgraph_get()
    trees = []
    for o in [prop, *prop.children_recursive]:
        if o.type != "MESH":
            continue
        e = o.evaluated_get(dg)
        m = e.to_mesh()
        m.calc_loop_triangles()
        verts = [e.matrix_world @ v.co for v in m.vertices]
        trees.append(BVHTree.FromPolygons(verts, [tuple(t.vertices) for t in m.loop_triangles]))
        e.to_mesh_clear()
    out = []
    for sgn in (1.0, -1.0):
        start = c + left_dir * sgn * reach
        best = None
        for tr in trees:
            hit = tr.ray_cast(start, -left_dir * sgn)
            if hit[0] is not None and (best is None or hit[3] < best[3]):
                best = hit
        p = best[0] if best is not None else c + left_dir * sgn * (reach - 0.2)
        out.append(p + left_dir * sgn * gap)
    return out[0], out[1]


def _palm_grip(h, prop, col, move=True, margin=0.0):
    """Rest the prop against the palm and close the fingers onto it. move=True: the prop is carried to the palm (along the
    palm's normal, centred on the palm and a little toward the fingers); move=False: the hand stays and so does the prop
    (the second hand on a wide prop). The fingers close joint by joint until their skin meets the prop (the solver's own
    closing routine); the thumb rests open at the side. Any penetration is pushed out along the palm normal (move=True).
    Returns the grips.check report."""
    import numpy as np
    from ajkit import grips
    for F in grips.FINGERS:
        h.set_flex(F, (8, 8, 5), 0.0)
    h.thumb_axis = (1.0, 0.0)
    h.thumb_set([math.radians(a) for a in (38, 0, 0, 6, 6)])
    M = h.fk()
    fr = h.frame(M)
    n = np.array(fr["n"])
    X = h.skin(M, h.palm)
    if move:
        lo, hi = _bounds(prop)
        aim = Vector(X.mean(0)) + fr["f"] * 0.015
        up = aim + fr["n"] * 0.30 - (lo + hi) / 2
        prop.matrix_world.translation += up
        col.shift += up
        a, b = 0.0, 0.30
        for _ in range(28):                               # how far the palm must come up to touch the prop
            m = (a + b) / 2
            if col.min_sd(X + n * m) > 0.0004:
                a = m
            else:
                b = m
        down = -fr["n"] * a
        prop.matrix_world.translation += down
        col.shift += down
        bpy.context.view_layer.update()
    rep = None
    for _ in range(5):
        for F in grips.FINGERS:
            h.set_flex(F, (8, 8, 5), 0.0)
            grips.close_finger(h, F, col, margin=margin)
        rep = grips.check(prop, "Right" if h.side == "Right" else "Left", _hand=h, _col=col, max_pen_mm=1.5)
        pen = rep["penetration_mm"] / 1000.0
        if pen <= 0.0012 or not move:
            break
        out = fr["n"] * (pen + 0.0004)                    # pushed off the palm
        prop.matrix_world.translation += out
        col.shift += out
        bpy.context.view_layer.update()
    h.apply()
    return rep


def _sandbox(actor, prop, side, frame, run):
    """Run a grip routine on the real prop with the hand where it is at `frame` and the fingers open, in a sandbox: the
    prop's parent, transform and constraints are restored afterwards. run(h) -> report; returns (angles, report) with angles
    = bone -> (x, y, z) and, in the report, the prop's pose relative to the Hand bone ("rel"), or (None, reason)."""
    from ajkit import grips
    sc = bpy.context.scene
    sc.frame_set(int(frame))
    bpy.context.view_layer.update()
    saved = (prop.parent, prop.parent_type, prop.parent_bone, prop.matrix_parent_inverse.copy(), prop.matrix_world.copy(),
             [(c, c.mute) for c in prop.constraints])
    ad = prop.animation_data
    act = ad.action if ad else None
    if ad:
        ad.action = None
    for c, _m in saved[5]:
        c.mute = True
    pb = actor.rig.pose.bones
    old = {n: tuple(pb[n].rotation_euler) for n in angles("mitten", side)}
    for n in old:
        pb[n].rotation_mode = "XYZ"
    set_static(actor, side, "open")
    bpy.context.view_layer.update()
    try:
        rep = run(grips.Hand(_side_name(side), actor.rig, actor.mesh))
        bpy.context.view_layer.update()
        got = {n: tuple(pb[n].rotation_euler) for n in old}
        hb = actor.rig.matrix_world @ pb[f"{P}{_side_name(side)}Hand"].matrix
        rep["rel"] = hb.inverted() @ prop.matrix_world
        rep["moved_cm"] = (prop.matrix_world.translation - saved[4].translation).length * 100.0
    except Exception as ex:                                   # the solver raises on shapes it cannot read
        got, rep = None, f"grip solver: {type(ex).__name__}: {ex}"
    finally:
        prop.parent = saved[0]
        prop.parent_type = saved[1]
        prop.parent_bone = saved[2]
        prop.matrix_parent_inverse = saved[3]
        prop.matrix_world = saved[4]
        for c, m in saved[5]:
            c.mute = m
        if ad:
            ad.action = act
        for n, e in old.items():
            pb[n].rotation_euler = e
        bpy.context.view_layer.update()
    if got is None:
        return None, rep
    if not rep.get("ok"):
        return None, f"grip solver: {'; '.join(rep.get('fail_reasons', ['failed']))}"
    return got, rep


def solve_grip(actor, prop, side, frame, second=False):
    """Solve the grip this prop gets (prop_kind) with the hand where it is at `frame`: power / pinch with the pack's solver
    (grips.hold, the library's `grip_at`), palm / palm2 with _palm_grip. second=True: the other hand of a two-handed hold
    (the prop stays where it is). Returns (angles, report) or (None, reason)."""
    from ajkit import grips
    kind = prop_kind(prop)
    if kind == "none":
        return None, f"no grip type fits {prop.name}"
    second = second or kind == "palm2"                    # both palms are put on the faces by the action; the prop stays
    if kind in ("power", "pinch"):
        kw = {"at": grip_at(prop)} if kind == "power" else {}

        def run(h):
            return grips.hold(prop, side=_side_name(side), grip=kind, parent=False, arm=actor.rig, body=actor.mesh, **kw)
    else:
        def run(h):
            col = grips.Collider(grips._meshes(prop))
            rep = _palm_grip(h, prop, col, move=not second)
            rep["grip"] = kind
            return rep
    ang, rep = _sandbox(actor, prop, side, frame, run)
    if ang is not None:
        rep["grip"] = kind
    return ang, rep
