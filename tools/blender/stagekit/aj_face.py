"""aj_face - the Aj face driven from the actor's control empty, baked once the shot is built.

The actor API keys plain numbers on its control empty while the shot is written (exactly like the fig3d cast):
x_<expression> (0..1, one per expression in config/aj_face.json), viseme_A/E/I/O/U/MBP (speak, ctrl_pulse), blink,
look_x, look_z. bake() then turns them into the body's shape keys (brows, lids, eye look) and the drawn mouth cell
(Mouth_Index of the skin material's 'Aj_Mouth_Controller' group), one key per frame. The mouth cell is keyed with
constant interpolation, so it switches like a drawn mouth. Jaw_Drop and the other mouth shape keys are never keyed.

    aj_face.setup(actor)          # control properties, and the skin material made the actor's own
    aj_face.bake(actor, frames)   # at _finalize
"""
from __future__ import annotations

import json

import bpy

from . import core

_CFG = None


def config() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = json.loads((core.PROJECT / "config" / "aj_face.json").read_text(encoding="utf-8"))
    return _CFG


def names() -> tuple:
    return tuple(config()["expressions"])


def setup(actor):
    """Control properties for the face on actor.ctrl."""
    c = actor.ctrl
    for e in names():
        c[f"x_{e}"] = 1.0 if e == "neutral" else 0.0
    return c


def mouth_socket(actor):
    cfg = config()["node"]
    mat = actor._skin_mat
    node = mat.node_tree.nodes.get(cfg["group"])
    if node is None:
        raise RuntimeError(f"{actor.id}: the skin material has no '{cfg['group']}' node")
    return node.inputs[cfg["input"]]


def _curve_of(ob, path):
    for fc in core.fcurves(ob):
        if fc.data_path == path and fc.array_index == 0:
            return fc
    return None


def _sampler(ctrl, prop):
    fc = _curve_of(ctrl, f'["{prop}"]')
    v = float(ctrl.get(prop, 0.0))
    return (lambda f: fc.evaluate(f)) if fc is not None else (lambda f: v)


def _set_dense(id_block, path, frames, values, constant=False):
    """One key per frame on a datablock channel (replaces what was there)."""
    ad = id_block.animation_data
    for fc in list(core.fcurves(id_block)):
        if fc.data_path == path:
            fc.keyframe_points.clear()
    id_block.keyframe_insert(path, frame=frames[0])
    fc = next(fc for fc in core.fcurves(id_block) if fc.data_path == path)
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(frames))
    co = []
    for f, v in zip(frames, values):
        co += [float(f), float(v)]
    fc.keyframe_points.foreach_set("co", co)
    for kp in fc.keyframe_points:
        kp.interpolation = "CONSTANT" if constant else "LINEAR"
    fc.update()
    return ad


def bake(actor, frames):
    """Shape keys and mouth cell for every frame in `frames` (sorted ints)."""
    cfg = config()
    ex = cfg["expressions"]
    ctrl = actor.ctrl
    w = {e: _sampler(ctrl, f"x_{e}") for e in ex}
    vis = {v: _sampler(ctrl, f"viseme_{v}") for v in cfg["visemes"]}
    blink = _sampler(ctrl, "blink")
    lx, lz = _sampler(ctrl, "look_x"), _sampler(ctrl, "look_z")
    eyes = cfg["eyes"]
    key = actor.mesh.data.shape_keys
    kb = key.key_blocks
    used = sorted({k for e in ex.values() for k in e["keys"]} | {eyes["left"], eyes["right"], eyes["up"], eyes["down"]} | set(eyes["blink"]))
    used = [k for k in used if k in kb and k not in cfg["never_key"]]
    series = {k: [] for k in used}
    cells = []
    thr = cfg["viseme_threshold"]
    for f in frames:
        ws = {e: max(0.0, min(1.0, s(f))) for e, s in w.items()}
        vals = {k: 0.0 for k in used}
        for e, we in ws.items():
            if we <= 1e-4:
                continue
            for k, v in ex[e]["keys"].items():
                if k in vals:
                    vals[k] += we * v
        x, z = max(-1.0, min(1.0, lx(f))), max(-1.0, min(1.0, lz(f)))
        vals[eyes["left"]] = max(0.0, x) * eyes["gain_x"]
        vals[eyes["right"]] = max(0.0, -x) * eyes["gain_x"]
        vals[eyes["up"]] = max(0.0, z) * eyes["gain_up"]
        vals[eyes["down"]] = max(0.0, -z) * eyes["gain_down"]
        b = max(0.0, min(1.0, blink(f)))
        for k in eyes["blink"]:
            if k in vals:
                vals[k] = max(vals[k], b)
        for k in used:
            series[k].append(max(kb[k].slider_min, min(kb[k].slider_max, vals[k])))
        # the mouth: a viseme while speaking, otherwise the strongest expression
        vb, vv = max(((s(f), v) for v, s in vis.items()), default=(0.0, None))
        if vv is not None and vb >= thr:
            cells.append(cfg["visemes"][vv])
        else:
            eb, en = max(((we, e) for e, we in ws.items() if e != "neutral"), default=(0.0, "neutral"))
            cells.append(ex[en]["mouth"] if eb >= 0.5 else cfg["rest_cell"])
    for k in used:
        vs = series[k]
        path = f'key_blocks["{k}"].value'
        if max(vs) - min(vs) < 1e-5:
            for fc in list(core.fcurves(key)):
                if fc.data_path == path:
                    fc.keyframe_points.clear()
            kb[k].value = vs[0]
            continue
        _set_dense(key, path, frames, vs)
    sock = mouth_socket(actor)
    nt = actor._skin_mat.node_tree
    path = sock.path_from_id("default_value")
    # keep only the frames where the cell changes (constant keys)
    kf, kv, last = [], [], None
    for f, c in zip(frames, cells):
        if c != last:
            kf.append(f)
            kv.append(c)
            last = c
    if len(kf) == 1:
        sock.default_value = float(kv[0])
    else:
        _set_dense(nt, path, kf, kv, constant=True)
    return {"keys": len(used), "mouth_changes": len(kf)}
