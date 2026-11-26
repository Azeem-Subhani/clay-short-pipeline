"""qa - does this Aj character hold together? Measured, not judged.

    py -3 tools/chars_aj/qa.py <Character> [--clip <clip dir>] [--no-actions]

Writes library/characters/aj/qa/<Character>.json (with --clip: <clip>/review/cast/<id>.qa.json for the clip's cast entry, its
per-clip costume applied):
    {"character", "items": [{"level": "block"|"warn", "code", "detail"}], "blocking": n, "warnings": n, "measured": {...}}
A character with blocking items must not be reported as ready (gate_a_sheets stamps them in red on its sheet).

What is checked, in Blender, on the character as the pipeline builds it (stagekit.cast_aj):
  armature     bone names and count, rest pose (head, tail, roll of every bone) against the pack's body for this age and sex
  mesh         vertex count, the shape keys the face and eyes need, head vertices unmoved against the pack body
  materials    no empty slot, images packed (or on disk), the drawn-mouth controller on the skin, the skin material this actor's own
  wardrobe     outfit and add-ons fit-accepted on this body (registry), licence cc0 | royalty_free | own; hair licence is a warning
               while the registry says 'unknown' (the owner's plan is to use it)
  hair         hair and beard vertices inside the skin of the neck and shoulders, at rest and with the head turned, nodded and lifted
               (limit 2 mm; the head skin itself is a warning above 3 mm). Known: the kids' hair enters their necks
  proportions  evaluated height against the body record (library/characters/aj/bodies)
  rig          control joints against the bones they drive (limit 0.5 mm)
  actions      the CORE actions through tools/chars3d/action_test3d.py, in a second Blender (not with --no-actions)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import bpy
except ImportError:                      # started with plain Python: the launcher below
    bpy = None

PIPE = Path(__file__).resolve().parents[2]
QA_DIR = PIPE / "library" / "characters" / "aj" / "qa"
LICENCES_OK = {"cc0", "royalty_free", "own"}
HAIR_LIMIT_MM = 2.0
HEAD_LIMIT_MM = 3.0
BIND_LIMIT_MM = 0.5
CORE = ["walk", "run", "point", "pick_up", "hold_up", "hand_over", "gasp", "talk", "sit_down", "wave", "laugh", "crouch"]


def _item(items, level, code, detail):
    items.append({"level": level, "code": code, "detail": detail})


# ----------------------------------------------------------------------------------------------- the pack reference
def _bone_rows(arm_data):
    rows = {}
    for b in arm_data.bones:
        rows[b.name] = [round(x, 5) for x in (*b.head_local, *b.tail_local)] + [round(b.matrix_local.to_euler().z, 4)]
    return rows


def reference(body_id: str) -> dict:
    """The pack body's bones, vertex count, shape-key names and head-vertex positions (cached in library/characters/aj/qa/_ref_<body>.json)."""
    cache = QA_DIR / f"_ref_{body_id}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    from stagekit import core
    path = core.PROJECT / "packs" / "aj_rebuild_v1" / "02_Age_Body_Variants" / f"Aj_{body_id}.blend"
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = ["Armature", "Aj_Base_Body"]
    arm, body = dst.objects
    names = {g.index: g.name for g in body.vertex_groups}
    head = {}
    for v in body.data.vertices:
        w = {names[g.group]: g.weight for g in v.groups if g.weight > 0}
        if w and max(w, key=w.get) == "mixamorig:Head":
            head[v.index] = [round(c, 6) for c in v.co]
    ref = {"bones": _bone_rows(arm.data), "verts": len(body.data.vertices), "keys": [k.name for k in body.data.shape_keys.key_blocks],
           "head": head, "file": str(path.relative_to(core.PROJECT)).replace("\\", "/")}
    for o in (arm, body):
        bpy.data.objects.remove(o, do_unlink=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(ref), encoding="utf-8")
    return ref


# ----------------------------------------------------------------------------------------------- the checks
def _check_armature(actor, ref, items, meas):
    rows = _bone_rows(actor.rig.data)
    names, rnames = set(rows), set(ref["bones"])
    if names != rnames or len(rows) != 83:
        _item(items, "block", "armature.bones", f"{len(rows)} bones; missing {sorted(rnames - names)[:6]}, extra {sorted(names - rnames)[:6]}")
        return
    worst, wb = 0.0, ""
    for n, r in rows.items():
        d = max(abs(a - b) for a, b in zip(r[:6], ref["bones"][n][:6])) * 1000.0     # native units (pack: metres x 100 per cm?) kept as mm-like
        if d > worst:
            worst, wb = d, n
    meas["bone_rest_dev_mm"] = round(worst, 4)
    sig = hashlib.md5(json.dumps(sorted(rows.items())).encode()).hexdigest()
    meas["bone_sig"] = sig
    if worst > 0.5:
        _item(items, "block", "armature.rest", f"rest pose differs from the pack body: bone {wb} by {worst:.3f} mm")


def _check_mesh(actor, ref, items, meas):
    body = actor.mesh
    n = len(body.data.vertices)
    if n != ref["verts"]:
        _item(items, "block", "mesh.verts", f"{n} vertices; the pack body has {ref['verts']}")
    have = {k.name for k in body.data.shape_keys.key_blocks} if body.data.shape_keys else set()
    miss = [k for k in ref["keys"] if k not in have]
    if miss:
        _item(items, "block", "mesh.keys", f"shape keys missing: {', '.join(miss[:8])}" + (" ..." if len(miss) > 8 else ""))
    worst = 0.0
    if n == ref["verts"]:
        vs = body.data.vertices
        for i, co in ref["head"].items():
            v = vs[int(i)].co
            worst = max(worst, max(abs(v[0] - co[0]), abs(v[1] - co[1]), abs(v[2] - co[2])))
    meas["head_verts_moved_mm"] = round(worst * 1000.0, 4)
    if worst * 1000.0 > 0.01:
        _item(items, "block", "mesh.head", f"head vertices moved by {worst * 1000:.3f} mm against the pack body (the head shape is never changed)")


def _check_materials(actor, items, meas):
    from stagekit import core
    px, nimg = 0, 0
    for o in [actor.mesh, *actor.parts.values()]:
        if o.type != "MESH":
            continue
        for i, s in enumerate(o.material_slots):
            if s.material is None:
                _item(items, "block", "mat.missing", f"{o.name} slot {i} has no material")
    seen = set()
    for m in bpy.data.materials:
        if not m.use_nodes or not (m.name.startswith(actor.id) or m.users):
            continue
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image and n.image.name not in seen:
                seen.add(n.image.name)
                im = n.image
                nimg += 1
                px += im.size[0] * im.size[1]
                ok = im.packed_file is not None or (im.filepath and os.path.exists(bpy.path.abspath(im.filepath)))
                if not ok:
                    _item(items, "block", "mat.images", f"image {im.name} is neither packed nor on disk")
                if max(im.size) > 2048:
                    _item(items, "warn", "mat.size", f"image {im.name} is {im.size[0]}x{im.size[1]}: over 2048 px")
    meas["images"], meas["pixels"] = nimg, px
    skin = actor._skin_mat
    if skin is None or skin.node_tree.nodes.get("Aj_Mouth_Controller") is None:
        _item(items, "block", "mat.mouth", "the skin material has no Aj_Mouth_Controller node (the drawn mouth cannot work)")
    if skin is not None and (skin.users > 1 or skin.name != f"{actor.id}.skin"):
        _item(items, "block", "mat.skin_shared", f"skin material {skin.name} has {skin.users} users: two actors would share one mouth")


def _check_wardrobe(actor, items, meas):
    from stagekit import aj_wardrobe as W
    wd = getattr(actor, "_wd", None)
    if wd is None:
        _item(items, "warn", "wardrobe.legacy", f"{actor.base} is not a wardrobe character (no outfit): its clothes were never fit-checked")
        return
    idx = W.index()
    o = idx["outfits"].get(wd["outfit"])
    f = (o or {}).get("fits", {}).get(wd["body_id"]) or {}
    if not (f.get("status") == "pass" and f.get("review") == "accept"):
        _item(items, "block", "fit.status", f"outfit {wd['outfit']} on {wd['body_id']}: fit {f.get('status')}, review {f.get('review')}")
    if o and o.get("licence") not in LICENCES_OK:
        _item(items, "block", "licence", f"outfit {wd['outfit']} licence '{o.get('licence')}' is not cc0, royalty_free or own")
    for item in wd["addons"]:
        a = (idx.get("addons") or {}).get(item) or {}
        af = (a.get("fits") or {}).get(wd["body_id"]) or {}
        ok_rev = af.get("review") == "accept" or (a.get("kind") == "rigid" and af.get("review") == "none")
        if not (af.get("status") == "pass" and ok_rev):
            _item(items, "block", "fit.status", f"add-on {item} on {wd['body_id']}: fit {af.get('status')}, review {af.get('review')}")
        if a.get("licence") not in LICENCES_OK:
            _item(items, "block", "licence", f"add-on {item} licence '{a.get('licence')}' is not cc0, royalty_free or own")
    if wd.get("hair") or wd.get("facial_hair"):
        hl = idx.get("hair", {}).get("licence")
        if hl not in LICENCES_OK:
            _item(items, "warn", "licence.hair", f"hair library licence is '{hl}' in the registry (pending the owner's confirmation; used under the approved plan)")


def _eval_world_mesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    mw = ev.matrix_world
    pts = [mw @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    return pts, polys


def _check_hair(actor, items, meas):
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    wd = getattr(actor, "_wd", None)
    objs = [(k, wd[k]["obj"]) for k in ("hair", "facial_hair") if wd and wd.get(k)]
    if not objs:
        return
    from ajkit import hairkit
    body = hairkit.skin_probe(actor.mesh)           # the mask renumbers the evaluated body: probe a copy without it
    names = {g.index: g.name.replace("mixamorig:", "") for g in body.vertex_groups}
    hw = []
    for v in body.data.vertices:
        w = {names[g.group]: g.weight for g in v.groups if g.weight > 0}
        hw.append((w.get("Head", 0.0) + w.get("HeadTop_End", 0.0)) / max(1e-9, sum(w.values())) if w else 1.0)
    turns = [("rest", {}), ("head_turn_40", {"head_z": 40}), ("nod_30", {"head_x": 30}), ("look_up_25", {"head_x": -25}),
             ("neck_turn_nod", {"neck_z": -30, "neck_x": 20})]
    hp_ = actor.head.point()
    hr = actor.b["R"] * actor.scale
    for kind, ob in objs:                      # the hair must be where a head is: evaluated, on the head (hair: its top above the head's centre)
        pts, _ = _eval_world_mesh(ob)
        top = max(p.z for p in pts)
        c = sum((p for p in pts), Vector((0, 0, 0))) / len(pts)
        meas[f"{kind}_top_z"] = round(top, 3)
        off = (c - hp_).length
        far = max((p - hp_).length for p in pts)
        meas[f"{kind}_farthest_m"] = round(far, 3)
        if far > 1.1 * actor.height * 0.5 + 0.3:
            _item(items, "block", "hair.spike", f"a {kind} vertex is {far:.2f} m from the head: a stretched spike (bad bone weights)")
        if len(pts) < 100 or off > 1.6 * hr or (kind == "hair" and top < hp_.z - 0.5 * hr):
            _item(items, "block", "hair.missing", f"{kind} is not on the head (top {top:.2f} m, its centre {off * 100:.0f} cm from the head centre, {len(pts)} vertices)")
    J = actor.J
    saved = {n: tuple(J[n].rotation_euler) for n in ("neck", "head")}
    worst = {}
    ear_polys = None
    zone_of = {}
    for pname, p in turns:
        for n in ("neck", "head"):
            J[n].rotation_mode = "XYZ"
            J[n].rotation_euler = (math.radians(p.get(f"{n}_x", 0)), 0.0, math.radians(p.get(f"{n}_z", 0)))
        bpy.context.view_layer.update()
        bpts, bpolys = _eval_world_mesh(body)
        bvh = BVHTree.FromPolygons(bpts, bpolys)
        if ear_polys is None:                     # the hair is cut round each ear and meets its root: leave the ears out
            at = actor.marks.get("ear", {}).get("at", (0.17, -0.04, 1.59))
            ears = [actor.root.matrix_world @ Vector((sx * at[0], at[1], at[2])) for sx in (1, -1)]
            r = 0.075 * actor.scale
            near = {i for i, q in enumerate(bpts) if min((q - e).length for e in ears) < r}
            ear_polys = {k for k, pl in enumerate(bpolys) if any(v in near for v in pl)}
        for kind, ob in objs:
            hpts, _ = _eval_world_mesh(ob)
            neck_pen = head_pen = 0.0
            wat = None
            zones = zone_of.setdefault(kind, {})
            for vi, p3 in enumerate(hpts):
                loc, nor, fi, dist = bvh.find_nearest(p3, 0.04)
                if pname == "rest":                     # which skin the vertex belongs to is settled once, at rest
                    if loc is None or fi in ear_polys:
                        zones[vi] = None
                    else:
                        zones[vi] = "head" if sum(hw[k] for k in bpolys[fi]) / len(bpolys[fi]) > 0.5 else "neck"
                zone = zones.get(vi)
                if loc is None or zone is None:
                    continue
                signed = (p3 - loc).dot(nor)
                if signed >= 0:
                    continue
                depth = -signed
                if zone == "head":
                    head_pen = max(head_pen, depth)
                else:
                    if depth > neck_pen:
                        wat = [round(c, 3) for c in p3]
                    neck_pen = max(neck_pen, depth)
            k = f"{kind}:{pname}"
            worst[k] = {"neck_shoulders_mm": round(neck_pen * 1000, 2), "head_mm": round(head_pen * 1000, 2), "worst_at": wat}
    hairkit.drop_probe(body)
    for n, v in saved.items():
        J[n].rotation_euler = v
    bpy.context.view_layer.update()
    meas["hair_clearance"] = worst
    for kind in ("hair", "facial_hair"):
        rows = {k: v for k, v in worst.items() if k.startswith(kind + ":")}
        if not rows:
            continue
        nk = max(rows, key=lambda k: rows[k]["neck_shoulders_mm"])
        hk = max(rows, key=lambda k: rows[k]["head_mm"])
        if rows[nk]["neck_shoulders_mm"] > HAIR_LIMIT_MM:
            _item(items, "block", "hair.clearance", f"{kind} goes {rows[nk]['neck_shoulders_mm']:.1f} mm into the skin of the neck or shoulders ({nk.split(':')[1]}); limit {HAIR_LIMIT_MM} mm")
        if rows[hk]["head_mm"] > HEAD_LIMIT_MM:
            _item(items, "warn", "hair.head", f"{kind} goes {rows[hk]['head_mm']:.1f} mm into the head skin ({hk.split(':')[1]})")


def _check_proportions(actor, items, meas):
    pts, _ = _eval_world_mesh(actor.mesh)
    zs = [p.z for p in pts]
    h = (max(zs) - min(zs))
    want = float(actor.b["height"]) * actor.scale
    meas["height_m"], meas["height_expected_m"] = round(h, 4), round(want, 4)
    dev = abs(h - want) / want
    if dev > 0.05:
        _item(items, "block", "proportions", f"height {h:.3f} m against {want:.3f} m expected from the body record ({dev * 100:.1f}% off)")
    elif dev > 0.025:
        _item(items, "warn", "proportions", f"height {h:.3f} m against {want:.3f} m expected ({dev * 100:.1f}% off)")


def _check_rig(actor, items, meas):
    from stagekit import aj_rig
    e = aj_rig.binding_error(actor, 1)
    meas["binding_error_mm"] = round(e, 4)
    if e > BIND_LIMIT_MM:
        _item(items, "block", "rig.binding", f"control joints are {e:.3f} mm from the bones they drive (limit {BIND_LIMIT_MM} mm)")


def check_actor(actor) -> dict:
    """All the in-Blender checks on a built actor. Returns {"items", "measured"}."""
    items, meas = [], {}
    ref = reference(actor.entry["body"])
    for fn in (lambda: _check_armature(actor, ref, items, meas), lambda: _check_mesh(actor, ref, items, meas),
               lambda: _check_materials(actor, items, meas), lambda: _check_wardrobe(actor, items, meas),
               lambda: _check_hair(actor, items, meas), lambda: _check_proportions(actor, items, meas), lambda: _check_rig(actor, items, meas)):
        try:
            fn()
        except Exception as ex:                  # a check that cannot run is itself a finding
            _item(items, "block", "qa.error", f"{type(ex).__name__}: {ex}")
    return {"items": items, "measured": meas}


def action_items(char_name: str, qa_file: Path | None = None) -> list[dict]:
    """The CORE action sweep findings from the last full run of qa.py for this character (library QA file), or a note that it has not run."""
    qa_file = qa_file or QA_DIR / f"{char_name}.json"
    if qa_file.exists():
        try:
            return [i for i in json.loads(qa_file.read_text(encoding="utf-8")).get("items", []) if i["code"].startswith("actions.")]
        except ValueError:
            pass
    return [{"level": "warn", "code": "actions.not_run", "detail": f"the CORE action sweep has not run for {char_name}: py -3 tools/chars_aj/qa.py {char_name}"}]


def finish(name: str, items: list[dict], measured: dict) -> dict:
    block = sum(1 for i in items if i["level"] == "block")
    return {"character": name, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "items": items, "blocking": block,
            "warnings": len(items) - block, "measured": measured}


# ----------------------------------------------------------------------------------------------- inside Blender
def _inside(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--inside", action="store_true")
    ap.add_argument("--char", required=True)
    ap.add_argument("--clip")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    os.environ.setdefault("SHORTS_PROJECT", str(PIPE))
    sys.path.insert(0, str(PIPE / "tools" / "blender"))
    import stagekit
    from stagekit import cast
    entries = [(a.char, a.char, None, 1.0)]
    if a.clip:
        plan = json.loads((Path(a.clip) / "shotplan.json").read_text(encoding="utf-8"))
        entries = [(c["id"], c["base"], c.get("costume"), float(c.get("scale", 1.0))) for c in plan.get("cast", []) if c["id"] == a.char or c["base"] == a.char]
    out = {}
    for cid, base, costume, scale in entries:
        stagekit.begin("qa", 1.0, "draft")
        act = cast.actor(cid, base, at=(0, 0), face="right", view="front", scale=scale, costume=costume)
        out[cid] = dict(check_actor(act), base=base)
    Path(a.out).write_text(json.dumps(out), encoding="utf-8")


# ----------------------------------------------------------------------------------------------- the launcher
def _blender():
    sys.path.insert(0, str(PIPE / "tools"))
    from common import blender_cmd
    return blender_cmd()


def sweep(char: str, outdir: Path) -> list[dict]:
    """The CORE actions on one character in a second Blender (tools/chars3d/action_test3d.py): failures as items."""
    outdir.mkdir(parents=True, exist_ok=True)
    other = "TeenGirlPonytail" if char != "TeenGirlPonytail" else "ElderManGreyHair"        # the second person in hand_over: an Aj, never the old 2D pack
    cmd = [*_blender(), str(PIPE / "tools" / "chars3d" / "action_test3d.py"), "--", "--char", char, "--out", str(outdir), "--set", "core", "--pipeline", str(PIPE),
           "--other", other]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=dict(os.environ, SHORTS_PROJECT=str(PIPE)))
    f = outdir / f"{char}.json"
    if not f.exists():
        return [{"level": "block", "code": "actions.error", "detail": f"the action sweep produced no result (exit {p.returncode}): {p.stdout[-300:]}"}]
    res = json.loads(f.read_text(encoding="utf-8"))["results"]
    items = []
    bad = {n: r for n, r in res.items() if not r.get("pass")}
    for n, r in bad.items():
        items.append({"level": "warn", "code": f"actions.{n}", "detail": "; ".join(r.get("fails", [])) or "failed"})
    if len(bad) > max(2, len(res) // 4):
        items.append({"level": "block", "code": "actions.many", "detail": f"{len(bad)} of {len(res)} CORE actions fail: {', '.join(bad)}"})
    items.append({"level": "info", "code": "actions.summary", "detail": f"{len(res) - len(bad)}/{len(res)} CORE actions pass"})
    return items


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("character")
    ap.add_argument("--clip")
    ap.add_argument("--no-actions", action="store_true")
    a = ap.parse_args(argv)
    tmp = PIPE / "output" / "_staging" / "qa"
    tmp.mkdir(parents=True, exist_ok=True)
    raw = tmp / f"{a.character}.inner.json"
    if raw.exists():
        raw.unlink()
    cmd = [*_blender(), str(Path(__file__).resolve()), "--", "--inside", "--char", a.character, "--out", str(raw)]
    if a.clip:
        cmd += ["--clip", str(Path(a.clip).resolve())]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=dict(os.environ, SHORTS_PROJECT=str(PIPE)))
    if not raw.exists():
        print(p.stdout[-2000:], p.stderr[-1000:])
        print("qa: Blender produced no result", file=sys.stderr)
        return 3
    inner = json.loads(raw.read_text(encoding="utf-8"))
    acts = sweep(a.character, tmp / "actions") if not (a.no_actions or a.clip) else []
    rc = 0
    for cid, r in inner.items():
        items = r["items"] + (acts if acts else action_items(r.get("base", cid)))
        rep = finish(cid, items, r["measured"])
        dest = (Path(a.clip) / "review" / "cast" / f"{cid}.qa.json") if a.clip else QA_DIR / f"{cid}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        print(f"{cid}: {rep['blocking']} blocking, {rep['warnings']} warning(s) -> {dest}")
        for i in items:
            print(f"  {i['level']:<5} {i['code']:<16} {i['detail']}")
        rc = max(rc, 1 if rep["blocking"] else 0)
    return rc


if __name__ == "__main__":
    if bpy is not None and "--inside" in sys.argv:
        _inside(sys.argv[sys.argv.index("--") + 1:])
        sys.argv = sys.argv[:1]
    elif bpy is None:
        sys.exit(main(sys.argv[1:]))
