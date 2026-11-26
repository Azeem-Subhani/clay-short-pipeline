# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/base.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: the base-file paths come from ajkit.paths (01_Base_Characters), the body
# is an argument of body_obj()/restore_feet() (default: the old name), and `import garments` reads ajkit.garments.
# No algorithm or constant is changed.
"""The Aj base body itself: feet and the female chest (run inside Blender).

    import base
    base.restore_feet()        # put back the foot faces garments.cull_feet() deleted (from Aj_Base.blend)
    base.add_chest_key()       # (re)write the "Female_Chest" shape key on Aj_Base_Body
    base.set_female(True)      # chest key 1.0 = female base, 0.0 = male base
    base.write_base_files()    # save Aj_Base.blend / Aj_Female_Base.blend from the open base file

One mesh serves both sexes: the female base is Aj_Base_Body with the `Female_Chest` shape key at 1.
The key only moves front-torso skin, so the head (hair and facial hair are fitted to it), the limbs,
the weights and the Mixamo rig are untouched. It is computed from rest-pose positions, not vertex
indices, so it can be rewritten on any copy of the body (with or without feet).
"""
import os
import bpy, bmesh
from mathutils import Vector, kdtree

BODY = "Aj_Base_Body"
P = "mixamorig:"
CHEST_KEY = "Female_Chest"
from . import paths as _paths
ROOT = _paths.ROOT
BASE_FILE = _paths.BASE_FILE
FEMALE_FILE = _paths.FEMALE_FILE

# Rest-pose world metres (character faces -Y, 1.80 m tall, chest half-width 0.13, armpit z ~1.22).
# Sized 2026-11-26 from the reference model reference/Ch03_nonPBR/Ch03_nonPBR.fbx: at key value 1.0 on the adult
# female body the bust stands forward of the torso front below it by 0.39 of the torso depth there, and the body
# is 1.5 times as deep at the bust as at the waist (work/variants/measure_chest.py). The key was 0.043 m, a narrower
# cone, before; old value 1.0 is about new value 0.6.
CHEST = dict(
    cx=0.064, cz=1.150,          # centre of each breast
    rx=0.078, rz_up=0.115, rz_dn=0.085,   # reach sideways / up (long, gradual slope) / down (short, fuller)
    amp=0.063,                   # forward projection at the apex
    out=0.15, sag=0.12,          # fraction of the projection that also goes outwards / downwards
    plate=0.012, plate_rx=0.115, plate_rz_up=0.085, plate_rz_dn=0.12, plate_cz=1.170,   # soft lift between the two
    dome_p=1.6, dome_q=1.1, dome_tilt=0.35,   # dome profile: full and round, not a cone
)


def body_obj(body=None):
    return body if body is not None else bpy.data.objects[BODY]


def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def chest_delta(p, n, c=CHEST):
    """World displacement of the chest key for a rest-pose world point p with world normal n."""
    front = _smooth((-n.y - 0.05) / 0.45)
    if front <= 0.0:
        return None
    dx = (abs(p.x) - c["cx"]) / c["rx"]
    dz = (p.z - c["cz"]) / (c["rz_up"] if p.z > c["cz"] else c["rz_dn"])
    r2 = dx * dx + dz * dz
    f = 0.0
    if r2 < 1.0:
        # broad rounded top to the dome (the torso has one vertex per ~3 cm), gradual upper slope, fuller underside
        # dome_p up / dome_q down = a fuller, rounder dome (flatter top, steeper sides) instead of a cone
        f = (1.0 - r2 ** c.get("dome_p", 1.2)) ** (c.get("dome_q", 1.5) + c.get("dome_tilt", 0.4) * max(-1.0, min(1.0, dz)))
    px = p.x / c["plate_rx"]
    pz = (p.z - c["plate_cz"]) / (c["plate_rz_up"] if p.z > c["plate_cz"] else c["plate_rz_dn"])
    pr2 = px * px + pz * pz
    g = (1.0 - pr2) ** 2 if pr2 < 1.0 else 0.0
    if f <= 0.0 and g <= 0.0:
        return None
    a = c["amp"] * f * front
    sx = 1.0 if p.x > 0 else (-1.0 if p.x < 0 else 0.0)
    return Vector((sx * c["out"] * a, -(a + c["plate"] * g * front), -c["sag"] * a))


def add_chest_key(body=None, params=None):
    """Create or rewrite the Female_Chest shape key (value left as it was; 0 on first creation)."""
    body = body or body_obj()
    c = dict(CHEST, **(params or {}))
    me = body.data
    if not me.shape_keys:
        body.shape_key_add(name="Basis", from_mix=False)
    keys = me.shape_keys.key_blocks
    kb = keys.get(CHEST_KEY)
    if kb is None:
        kb = body.shape_key_add(name=CHEST_KEY, from_mix=False)
        kb.value = 0.0
    kb.slider_min, kb.slider_max = 0.0, 1.5
    basis = keys[0].data
    mw = body.matrix_world
    rot = mw.to_3x3()
    inv = rot.inverted()
    names = {g.index: g.name.replace(P, "") for g in body.vertex_groups}
    moved = 0; peak = 0.0
    for v in me.vertices:
        co = basis[v.index].co
        d = None
        skip = 0.0
        for g in v.groups:
            nm = names.get(g.group, "")
            if nm.endswith(("Arm", "ForeArm")) or "Hand" in nm or nm in ("Neck", "Head"):
                skip += g.weight
        if skip < 1.0:
            n = (rot @ v.normal).normalized()
            d = chest_delta(mw @ co, n, c)
        if d is None:
            kb.data[v.index].co = co
            continue
        d *= (1.0 - min(1.0, skip))
        kb.data[v.index].co = co + inv @ d
        moved += 1; peak = max(peak, d.length)
    me.update()
    return {"moved": moved, "peak_m": round(peak, 4)}


def set_female(on=True, body=None):
    body = body or body_obj()
    kb = body.data.shape_keys.key_blocks[CHEST_KEY]
    kb.value = float(on)
    return kb.value


# ----------------------------------------------------------------------------------------------- feet

_KINDS = ("objects", "meshes", "armatures", "materials", "images", "actions", "node_groups", "textures")


def restore_feet(source=None, tol=2e-3, body=None):
    """Put back the faces missing from Aj_Base_Body (the feet garments.cull_feet() deleted), copied from
    the same body in `source` (Aj_Base.blend): positions, every shape key, weights, UVs and materials.

    Existing vertices keep their indices (the new ones are appended), so shape-key drivers and cached
    vertex indices stay valid. Idempotent: returns zeros when nothing is missing."""
    source = source or BASE_FILE
    body = body_obj(body)
    me = body.data
    before = {k: set(d.name for d in getattr(bpy.data, k)) for k in _KINDS}
    with bpy.data.libraries.load(source, link=False) as (src, dst):
        if BODY not in src.objects:
            raise RuntimeError(f"{BODY} not found in {source}")
        dst.objects = [BODY]
    so = dst.objects[0]
    sm = so.data
    try:
        skeys = {k.name: k.data for k in sm.shape_keys.key_blocks} if sm.shape_keys else {}
        sbasis = sm.shape_keys.key_blocks[0].data if sm.shape_keys else None
        sgroups = {g.index: g.name for g in so.vertex_groups}
        suv = sm.uv_layers.active.data if sm.uv_layers.active else None

        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        kd = kdtree.KDTree(len(bm.verts))
        for v in bm.verts:
            kd.insert(v.co, v.index)
        kd.balance()

        def sco(i):
            return sbasis[i].co if sbasis else sm.vertices[i].co
        vmap = {}
        for v in sm.vertices:
            co, idx, dist = kd.find(sco(v.index))
            if dist is not None and dist <= tol:
                vmap[v.index] = bm.verts[idx]

        shape = {name: lay for name, lay in bm.verts.layers.shape.items()}
        dl = bm.verts.layers.deform.verify()
        uvl = bm.loops.layers.uv.verify() if suv else None
        gidx = {}
        for i, nm in sgroups.items():
            g = body.vertex_groups.get(nm) or body.vertex_groups.new(name=nm)
            gidx[i] = g.index
        mats = [m.name if m else None for m in me.materials]

        def mat_index(p):
            sm_mat = sm.materials[p.material_index] if sm.materials else None
            nm = sm_mat.name.split(".0")[0] if sm_mat else None      # appended copies are "Name.001"
            return mats.index(nm) if nm in mats else p.material_index

        new_v = new_f = 0
        for p in sm.polygons:
            vs = [vmap.get(i) for i in p.vertices]
            if all(vs) and len(set(vs)) == len(vs) and bm.faces.get(vs) is not None:
                continue
            for k, i in enumerate(p.vertices):
                if vs[k] is None:
                    nv = bm.verts.new(sco(i))
                    for name, lay in shape.items():
                        nv[lay] = skeys[name][i].co if name in skeys else sco(i)
                    for g in sm.vertices[i].groups:
                        if g.weight > 0:
                            nv[dl][gidx[g.group]] = g.weight
                    vmap[i] = vs[k] = nv
                    new_v += 1
            if len(set(vs)) != len(vs) or bm.faces.get(vs) is not None:
                continue
            f = bm.faces.new(vs)
            f.smooth = p.use_smooth
            f.material_index = mat_index(p)
            if uvl:
                for loop, li in zip(f.loops, p.loop_indices):
                    loop[uvl].uv = suv[li].uv
            new_f += 1
        if new_f:
            bm.normal_update()
            bm.to_mesh(me)
            me.update()
        bm.free()
    finally:
        for k in _KINDS:
            col = getattr(bpy.data, k)
            for d in [d for d in col if d.name not in before[k]]:
                col.remove(d)
    try:
        from . import garments
        garments._INFO_CACHE.clear()
    except Exception:
        pass
    if new_f and me.shape_keys and CHEST_KEY in me.shape_keys.key_blocks and CHEST_KEY not in skeys:
        add_chest_key(body)
    m = body.modifiers.get(FEET_MOD)
    if new_f and m and m.show_render:
        _mark_boot_faces(body)          # the new faces are not flagged yet
    return {"verts_added": new_v, "faces_added": new_f, "verts": len(me.vertices), "faces": len(me.polygons)}


FEET_ATTR = "in_boots"            # face attribute: foot skin that sits inside the boots
FEET_MOD = "HideFeetInBoots"      # geometry-nodes modifier deleting those faces (display only)
_FOOT = {"LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase"}
_LEG = {"LeftLeg", "RightLeg"}


def _mark_boot_faces(body, zmax=0.13, foot_top=0.16):
    """Flag the faces garments.cull_feet() would delete (same rule), as a boolean face attribute."""
    me = body.data
    mw = body.matrix_world
    names = {g.index: g.name.replace(P, "") for g in body.vertex_groups}
    basis = me.shape_keys.key_blocks[0].data if me.shape_keys else me.vertices
    hidden = []
    for v in me.vertices:
        best, bw = None, 0.0
        for g in v.groups:
            if g.weight > bw:
                best, bw = names.get(g.group), g.weight
        z = (mw @ basis[v.index].co).z
        hidden.append((z < zmax and best in _FOOT | _LEG) or (best in _FOOT and z < foot_top))
    att = me.attributes.get(FEET_ATTR)
    if att is None or att.domain != "FACE" or att.data_type != "BOOLEAN":
        if att is not None:
            me.attributes.remove(att)
        att = me.attributes.new(FEET_ATTR, "BOOLEAN", "FACE")
    flags = [all(hidden[i] for i in p.vertices) for p in me.polygons]
    att.data.foreach_set("value", flags)
    me.update()
    return sum(flags)


def _feet_node_group():
    ng = bpy.data.node_groups.get(FEET_MOD)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(FEET_MOD, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    ng.is_modifier = True
    gi = ng.nodes.new("NodeGroupInput"); go = ng.nodes.new("NodeGroupOutput")
    na = ng.nodes.new("GeometryNodeInputNamedAttribute")
    na.data_type = "BOOLEAN"
    na.inputs["Name"].default_value = FEET_ATTR
    dl = ng.nodes.new("GeometryNodeDeleteGeometry")
    dl.domain = "FACE"; dl.mode = "ALL"
    gi.location, na.location, dl.location, go.location = (-400, 0), (-400, -140), (-150, 0), (100, 0)
    sel = next(o for o in na.outputs if o.enabled and o.name == "Attribute")
    ng.links.new(gi.outputs[0], dl.inputs["Geometry"])
    ng.links.new(sel, dl.inputs["Selection"])
    ng.links.new(dl.outputs[0], go.inputs[0])
    return ng


def hide_feet(hide=True, body=None):
    """Show the bare feet (base views) or hide the foot skin inside boots (booted costumes).

    Nothing is deleted: a face attribute marks the faces and a modifier drops them from display/render.
    The marked faces are exactly the ones garments.cull_feet() removes for a build."""
    body = body or body_obj()
    m = body.modifiers.get(FEET_MOD)
    if not hide:
        if m:
            m.show_viewport = m.show_render = False
        return 0
    n = _mark_boot_faces(body)
    if m is None:
        m = body.modifiers.new(FEET_MOD, "NODES")
        m.node_group = _feet_node_group()
    m.show_viewport = m.show_render = True
    return n


def has_feet(body=None):
    body = body or body_obj()
    basis = body.data.shape_keys.key_blocks[0].data if body.data.shape_keys else body.data.vertices
    mw = body.matrix_world
    return min((mw @ v.co).z for v in basis) < 0.02


# ------------------------------------------------------------------------------------------ base files

def write_base_files():
    """With a base file open (Armature + Aj_Base_Body, feet on): save the male and the female base."""
    body = body_obj()
    if not has_feet(body):
        raise RuntimeError("this body has no feet - run restore_feet() first")
    if CHEST_KEY not in body.data.shape_keys.key_blocks:
        add_chest_key(body)
    old = body.data.shape_keys.key_blocks[CHEST_KEY].value
    out = []
    for path, val in ((BASE_FILE, 0.0), (FEMALE_FILE, 1.0)):
        set_female(val, body)
        bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, compress=True)
        out.append(path)
    set_female(old, body)
    return out
