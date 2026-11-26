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


def prop_kind(prop) -> str:
    """power for a rod (a handle, a stick, a bottle), pinch for a small thin thing, otherwise none."""
    meshes = [o for o in [prop, *prop.children_recursive] if o.type == "MESH"]
    if not meshes:
        return "none"
    lo, hi = core.world_bbox(meshes)
    dims = sorted(hi - lo, reverse=True)
    if dims[0] < 1e-6:
        return "none"
    if dims[0] > 2.6 * max(dims[1], 1e-6) and dims[1] < 0.07:
        return "power"
    if dims[0] < 0.07 and dims[2] < 0.025:
        return "pinch"
    return "none"


def solve_grip(actor, prop, side, frame):
    """Run the pack's grip solver on the real prop with the hand where it is at `frame`, in a sandbox: the prop's
    parent, transform and constraints are restored afterwards. Returns (angles, report) with angles = bone -> (x, y, z)
    and the prop's pose relative to the Hand bone, or (None, reason)."""
    from ajkit import grips
    kind = prop_kind(prop)
    if kind == "none":
        return None, f"no grip type fits {prop.name} (only handles / rods and small thin things are solved)"
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
        rep = grips.hold(prop, side=_side_name(side), grip=kind, parent=False, arm=actor.rig, body=actor.mesh)
        bpy.context.view_layer.update()
        got = {n: tuple(pb[n].rotation_euler) for n in old}
        hb = actor.rig.matrix_world @ pb[f"{P}{_side_name(side)}Hand"].matrix
        rel = hb.inverted() @ prop.matrix_world
        rep["rel"] = rel
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
