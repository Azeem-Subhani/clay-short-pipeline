# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/fitreview.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: fitcheck, stage and sheetutil are imported from ajkit (sheetutil sat in
# work/grip_tests, outside the pack). The views, framing and rules are unchanged.
"""Side-by-side close-ups of the source asset and the fitted result, for the review step (scripts/FITCHECK.md).

The views are found from the garments themselves, so nobody chooses them: each whole garment from the front and the
back, then every opening (neckline, armholes, waistband, hems: each closed run of open edge longer than 15 cm)
from the front and the back. Left picture: the garment as it sat on the asset's own body. Right: on ours.

Needs what the fitter leaves in the file: the vertex attribute `fit_asset_co` on each garment and the collection
`Fit_Reference` (the asset's body in the pose it was fitted from).

    import fitreview; fitreview.sheets(arm, body, garments, r"...\\prefix")      # inside a session
    blender --background dressed.blend --python fitreview.py -- <out_prefix>         # on a saved file
"""
import bpy, sys, os, math
import numpy as np
from mathutils import Vector

REF_COL = "Fit_Reference"


def store_reference(asset_body_co, asset_body_tris, garments):
    """Keep the asset's body and the garments as they sat on it, hidden, inside the dressed file."""
    col = bpy.data.collections.get(REF_COL)
    if col is None:
        col = bpy.data.collections.new(REF_COL)
        bpy.context.scene.collection.children.link(col)
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    me = bpy.data.meshes.new("REF_Body")
    me.from_pydata([tuple(p) for p in asset_body_co], [], [tuple(int(i) for i in t) for t in asset_body_tris])
    for p in me.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.get("REF_Body_MAT") or bpy.data.materials.new("REF_Body_MAT")
    mat.diffuse_color = (0.62, 0.62, 0.64, 1.0)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get("Principled BSDF")
    if bs:
        bs.inputs["Base Color"].default_value = (0.62, 0.62, 0.64, 1.0); bs.inputs["Roughness"].default_value = 0.7
    me.materials.append(mat)
    ob = bpy.data.objects.new("REF_Body", me); col.objects.link(ob)
    for g in garments:
        a = g.data.attributes.get("fit_asset_co")
        if a is None:
            continue
        m2 = g.data.copy(); m2.name = "REF_" + g.name
        v = np.empty(len(m2.vertices) * 3, dtype=np.float32); a.data.foreach_get("vector", v)
        m2.vertices.foreach_set("co", v); m2.update()
        o2 = bpy.data.objects.new("REF_" + g.name, m2); col.objects.link(o2)
    for o in col.objects:
        o.hide_render = True; o.hide_viewport = True
    return col


def _loops(ob, ref_co, min_len=0.15):
    """Closed runs of open edge (welded), as lists of vertex indices, longest first."""
    from ajkit import fitcheck
    edges = fitcheck.open_edges(ob, ref_co)
    rep = fitcheck.weld_map(ref_co)
    nb = {}
    for a, b in edges:
        a, b = int(rep[a]), int(rep[b])
        nb.setdefault(a, set()).add(b); nb.setdefault(b, set()).add(a)
    seen = set(); out = []
    for s in nb:
        if s in seen:
            continue
        comp = []; st = [s]; seen.add(s)
        while st:
            j = st.pop(); comp.append(j)
            for q in nb[j]:
                if q not in seen:
                    seen.add(q); st.append(q)
        ln = sum(float(np.linalg.norm(ref_co[a] - ref_co[b])) for a in comp for b in nb[a]) / 2
        if ln >= min_len:
            out.append((ln, comp))
    out.sort(key=lambda x: -x[0])
    return [c for _, c in out[:6]]


def sheets(arm, body, garments, prefix, res=560):
    from ajkit import fitcheck, stage, sheetutil
    col = bpy.data.collections.get(REF_COL)
    if col is None:
        raise RuntimeError("this file has no Fit_Reference collection (the fitter stores it)")
    sc = bpy.context.scene
    keep_pp = arm.data.pose_position
    arm.data.pose_position = 'REST'
    fitcheck.set_mask(body, True)
    stage.setup_stage()
    for nme, en in (("Key", 70), ("Fill", 30), ("Rim", 50)):
        bpy.data.objects[nme].data.energy = en
    fl = bpy.data.objects.get("Stage_Floor")
    if fl:
        fl.hide_render = True
    cam = sc.camera
    cam.data.type = 'ORTHO'
    where = fitcheck.Where(body, arm)
    refs = {o.name: o for o in col.objects}
    ours = [body] + list(garments)

    def show(reference):
        for o in col.objects:
            o.hide_render = not reference
        for o in ours:
            o.hide_render = reference

    def shot(centre, size, front, path):
        d = Vector((0, -1, 0)) if front else Vector((0, 1, 0))
        cam.location = Vector(centre) + d * 4.0
        stage.look_at(cam, tuple(centre))
        cam.data.ortho_scale = max(size, 0.08) * 1.35
        sc.render.resolution_x = sc.render.resolution_y = res
        sc.render.resolution_percentage = 100
        return stage.render(path)

    made = []
    for g in garments:
        gm = fitcheck._eval(g); co = gm["co"]
        aco = fitcheck._attr(g, "fit_asset_co", 3)
        if aco is None:
            continue
        views = [("whole garment", np.arange(len(co)))]
        for k, loop in enumerate(_loops(g, aco)):
            w = where(co[loop].mean(axis=0))
            views.append((f"opening {k + 1} near {w['body_part']}", np.array(loop)))
        files = []; labels = []
        for vi, (label, idx) in enumerate(views):
            for front in (True, False):
                pair = []
                for reference, C in ((True, aco), (False, co)):
                    lo, hi = C[idx].min(axis=0), C[idx].max(axis=0)
                    show(reference)
                    p = f"{prefix}_{g.name}_{vi}_{'front' if front else 'back'}_{'asset' if reference else 'fitted'}.png"
                    pair.append(shot((lo + hi) / 2, float(max(hi[0] - lo[0], hi[2] - lo[2])), front, p))
                files += pair
                labels.append(f"{label}, {'front' if front else 'back'}")
        out = f"{prefix}_{g.name}.png"
        sheetutil.sheet(files, out, cols=4)
        made.append({"garment": g.name, "sheet": out, "rows": [labels[i:i + 2] for i in range(0, len(labels), 2)],
                     "layout": "each row: two views; each view is a pair, asset on the left, fitted on the right"})
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass
    show(False)
    for o in col.objects:
        o.hide_render = True
    cam.data.type = 'PERSP'
    if fl:
        fl.hide_render = False
    arm.data.pose_position = keep_pp
    return made


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ajkit.fitreview import sheets
    a = sys.argv[sys.argv.index("--") + 1:]
    arm = bpy.data.objects["Armature"]; body = bpy.data.objects["Aj_Base_Body"]
    gs = [o for o in bpy.data.objects if o.type == 'MESH' and o.data.attributes.get("fit_asset_co") and not o.name.startswith("REF_")]
    import json
    print("REVIEW " + json.dumps(sheets(arm, body, gs, a[0])))
