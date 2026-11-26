# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/garments.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: the armature and the body can be chosen with use(arm, body) (or the
# arm=/body= arguments of arm_obj/body_obj) instead of only the fixed names "Armature" / "Aj_Base_Body", so the body
# info cache is kept per body; cull_feet() works on the chosen body; the two hair-library folders come from
# ajkit.paths. Without use() the old names are used. No algorithm or constant is changed.
"""Garment toolkit for the Aj hybrid rig (run inside Blender 5.3).

Clothing is grown from Aj_Base_Body itself: a region of the body surface is copied,
pushed out along its normals, and keeps the body's exact bone weights, so it follows any
Mixamo animation. Generated parts (coat tails, capes, cuffs) get blended weights.
Props imported from BlenderKit are bone-parented to the right Mixamo bone.
"""
import bpy, bmesh, math
from mathutils import Vector, Matrix

ARM = "Armature"
BODY = "Aj_Base_Body"
P = "mixamorig:"

TORSO = {"Hips", "Spine", "Spine1", "Spine2"}
SHOULDER = {"LeftShoulder", "RightShoulder"}
UPPERARM = {"LeftArm", "RightArm"}
FOREARM = {"LeftForeArm", "RightForeArm"}
UPLEG = {"LeftUpLeg", "RightUpLeg"}
LEG = {"LeftLeg", "RightLeg"}
FOOT = {"LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase"}
HEADNECK = {"Head", "Neck"}


_TARGET = {"arm": None, "body": None}


def use(arm=None, body=None):
    """Work on this armature and body (objects or names) from now on; None goes back to the pack's fixed names."""
    _TARGET["arm"] = bpy.data.objects[arm] if isinstance(arm, str) else arm
    _TARGET["body"] = bpy.data.objects[body] if isinstance(body, str) else body
    _INFO_CACHE.clear()


def arm_obj(arm=None):
    return arm if arm is not None else (_TARGET["arm"] or bpy.data.objects[ARM])


def body_obj(body=None):
    return body if body is not None else (_TARGET["body"] or bpy.data.objects[BODY])


def collection(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def remove_obj(name):
    o = bpy.data.objects.get(name)
    if o:
        me = o.data if o.type == "MESH" else None
        bpy.data.objects.remove(o, do_unlink=True)
        if me and me.users == 0:
            bpy.data.meshes.remove(me)


def vert_info(body):
    """Per-vertex world rest position, weights by short bone name and dominant bone."""
    mw = body.matrix_world
    names = {g.index: g.name.replace(P, "") for g in body.vertex_groups}
    info = []
    for v in body.data.vertices:
        w = {}
        for g in v.groups:
            if g.weight > 0:
                w[names[g.group]] = g.weight
        dom = max(w, key=w.get) if w else None
        info.append({"p": mw @ v.co, "w": w, "dom": dom})
    return info


_INFO_CACHE = {}


def body_info():
    key = "info:" + body_obj().name
    if key not in _INFO_CACHE:
        _INFO_CACHE[key] = vert_info(body_obj())
    return _INFO_CACHE[key]


def from_body(name, pred, offset, col, keep_keys=("Arms_Thicker", "Arms_Thinner", "Legs_Thicker", "Legs_Thinner"),
              offset_fn=None, thickness=0.004, subsurf=1, smooth_iter=0, edge_taper=0.0, largest_only=False,
              relax_edges=0):
    """Copy the faces of Aj_Base_Body whose vertices all satisfy pred(info) and push them out.

    offset: metres along the vertex normal (offset_fn(info) -> extra metres, optional).
    """
    remove_obj(name)
    body = body_obj()
    info = body_info()
    me = body.data.copy()
    me.name = name
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob.matrix_world = body.matrix_world.copy()
    s = body.matrix_world.to_scale()[0]
    # vertex groups
    for g in body.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    # shape keys: keep only limb sizing keys
    if me.shape_keys:
        for kb in list(me.shape_keys.key_blocks)[1:]:
            if kb.name not in keep_keys:
                ob.shape_key_remove(kb)
    me.materials.clear()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    keep = [pred(info[v.index]) for v in bm.verts]
    dead = [f for f in bm.faces if not all(keep[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=dead, context="FACES_ONLY")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    if largest_only:
        seen = set(); comps = []
        for f in bm.faces:
            if f in seen:
                continue
            stack = [f]; comp = []
            seen.add(f)
            while stack:
                g = stack.pop(); comp.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h not in seen:
                            seen.add(h); stack.append(h)
            comps.append(comp)
        comps.sort(key=len, reverse=True)
        dead = [f for c in comps[1:] for f in c]
        if dead:
            bmesh.ops.delete(bm, geom=dead, context="FACES")
        # fill inner holes (keep only the outer boundary open)
        bnd = [e for e in bm.edges if e.is_boundary]
        loops = []; used = set()
        for e in bnd:
            if e in used:
                continue
            loop = []; stack = [e]; used.add(e)
            while stack:
                g = stack.pop(); loop.append(g)
                for v in g.verts:
                    for h in v.link_edges:
                        if h.is_boundary and h not in used:
                            used.add(h); stack.append(h)
            loops.append(loop)
        loops.sort(key=lambda l: sum(x.calc_length() for x in l), reverse=True)
        for l in loops[1:]:
            bmesh.ops.holes_fill(bm, edges=l, sides=0)
    bm.normal_update()
    shape_layers = list(bm.verts.layers.shape.values())
    orig = bm.verts.layers.int.get("orig") or bm.verts.layers.int.new("orig")
    for v in bm.verts:
        v[orig] = v.index  # indices still original before any further op? (not after delete) -> recompute below
    # offset along normals (local units); optionally taper towards open edges
    ring1 = set(v for v in bm.verts if v.is_boundary)
    ring2 = set(e.other_vert(v) for v in ring1 for e in v.link_edges) - ring1
    for v in bm.verts:
        d = offset
        if offset_fn:
            d += offset_fn(v, ob.matrix_world @ v.co)
        if edge_taper:
            if v in ring1:
                d *= (1 - edge_taper)
            elif v in ring2:
                d *= (1 - edge_taper * 0.5)
        delta = v.normal * (d / s)
        v.co += delta
        for L in shape_layers:
            v[L] += delta
    # optional relax to smooth out fine body detail (fingers of geometry, ribs...)
    for _ in range(smooth_iter):
        bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    # optional: relax the open edges along themselves so face-level selection does not leave
    # a staircase (shape-key layers get the same delta so the sizing sliders still match)
    for _ in range(relax_edges):
        moves = {}
        for v in bm.verts:
            if not v.is_boundary:
                continue
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) == 2:
                moves[v] = (nb[0].co + nb[1].co) * 0.25 - v.co * 0.5
        for v, d in moves.items():
            v.co += d
            for L in shape_layers:
                v[L] += d
    bm.to_mesh(me)
    bm.free()
    if me.shape_keys:
        for kb in me.shape_keys.key_blocks[1:]:
            fc = kb.driver_add("value")
            fc.driver.type = "AVERAGE"
            var = fc.driver.variables.new()
            var.targets[0].id_type = "KEY"
            var.targets[0].id = body.data.shape_keys
            var.targets[0].data_path = f'key_blocks["{kb.name}"].value'
    rig(ob, thickness=thickness, subsurf=subsurf, parent_matrix=None)
    return ob


def rig(ob, thickness=0.004, subsurf=1, parent_matrix=None):
    arm = arm_obj()
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.matrix_parent_inverse = arm.matrix_world.inverted()
    ob.matrix_world = mw
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    am = ob.modifiers.new("Armature", "ARMATURE")
    am.object = arm
    s = ob.matrix_world.to_scale()[0]
    if thickness:
        so = ob.modifiers.new("Solidify", "SOLIDIFY")
        so.thickness = thickness / s
        so.offset = 1.0
        # even offset / high-quality normals throw vertices metres away where the cloth folds in an animation
        # (raised arm): plain offset only
        so.use_even_offset = False
        so.use_quality_normals = False
    if subsurf:
        ss = ob.modifiers.new("Subdivision", "SUBSURF")
        ss.levels = subsurf
        ss.render_levels = subsurf
    for p in ob.data.polygons:
        p.use_smooth = True


def mesh_from_grid(name, rows, col, closed=True, cap_top=False):
    """rows: list of lists of world points (each row same length). Returns object at identity."""
    remove_obj(name)
    verts = [p for r in rows for p in r]
    n = len(rows[0])
    faces = []
    for i in range(len(rows) - 1):
        for j in range(n if closed else n - 1):
            a = i * n + j
            b = i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    # outward normals: make consistent
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    return ob


def set_weights(ob, fn):
    """fn(world_point) -> {short_bone: weight}"""
    for v in ob.data.vertices:
        w = fn(ob.matrix_world @ v.co)
        tot = sum(w.values()) or 1
        for b, x in w.items():
            if x <= 0:
                continue
            g = ob.vertex_groups.get(P + b) or ob.vertex_groups.new(name=P + b)
            g.add([v.index], x / tot, "REPLACE")


def transfer_weights(ob, smooth=2):
    """Copy weights from the body surface to an arbitrary mesh (nearest face interpolated).
    `smooth` is accepted for compatibility but not used (the smoothing operator cannot run
    from the MCP timer context; face-interpolated transfer is already smooth)."""
    body = body_obj()
    arm = arm_obj()
    old_pp = arm.data.pose_position
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    for g in body.vertex_groups:
        if not ob.vertex_groups.get(g.name):
            ob.vertex_groups.new(name=g.name)
    dt = ob.modifiers.new("WT", "DATA_TRANSFER")
    dt.object = body
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    bpy.context.view_layer.objects.active = ob
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_move_to_index(modifier="WT", index=0)
        bpy.ops.object.modifier_apply(modifier="WT")
    # normalise (manual: operator polls fail under the MCP timer context)
    for v in ob.data.vertices:
        tot = sum(g.weight for g in v.groups)
        if tot > 1e-6:
            for g in v.groups:
                g.weight = g.weight / tot
    # drop empty groups
    used = set()
    for v in ob.data.vertices:
        for g in v.groups:
            if g.weight > 1e-4:
                used.add(g.group)
    dead = [g.name for g in ob.vertex_groups if g.index not in used]
    for n in dead:
        ob.vertex_groups.remove(ob.vertex_groups[n])
    arm.data.pose_position = old_pp


def bone_parent(ob, bone, keep_world=True):
    arm = arm_obj()
    bpy.context.view_layer.update()
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = P + bone
    bpy.context.view_layer.update()
    if keep_world:
        ob.matrix_world = mw


def bone_matrix(bone):
    """World matrix of the bone tail in rest pose (what BONE parenting is relative to)."""
    arm = arm_obj()
    b = arm.data.bones[P + bone]
    m = arm.matrix_world @ b.matrix_local
    return m, arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local


def cube_uv(ob, size=0.35):
    """World-scale box projection UVs so fabric textures repeat every `size` metres."""
    me = ob.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    uv = me.uv_layers.new(name="UVMap")
    mw = ob.matrix_world
    nm = mw.to_3x3()
    for p in me.polygons:
        n = (nm @ p.normal)
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = mw @ me.vertices[me.loops[li].vertex_index].co
            if ax == 0:
                u, v = co.y, co.z
            elif ax == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            uv.data[li].uv = (u / size, v / size)


def tube_uv(ob, axis_pt, axis_dir, size=0.35):
    """Cylindrical UVs around an axis (good for skirts / capes / sleeves - no box seams)."""
    me = ob.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    uv = me.uv_layers.new(name="UVMap")
    mw = ob.matrix_world
    ad = Vector(axis_dir).normalized()
    ref = Vector((0, -1, 0)) if abs(ad.y) < 0.9 else Vector((1, 0, 0))
    e1 = (ref - ad * ref.dot(ad)).normalized(); e2 = ad.cross(e1)
    for p in me.polygons:
        us = []
        for li in p.loop_indices:
            co = mw @ me.vertices[me.loops[li].vertex_index].co - Vector(axis_pt)
            h = co.dot(ad)
            r = co - ad * h
            a = math.atan2(r.dot(e2), r.dot(e1))
            us.append((li, a, h, r.length))
        # avoid wrap seam stretching
        amin = min(x[1] for x in us); amax = max(x[1] for x in us)
        for li, a, h, rr in us:
            if amax - amin > math.pi and a < 0:
                a += 2 * math.pi
            uv.data[li].uv = (a * max(rr, 0.08) / size, h / size)


def assign(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


WARNINGS = []


def find_bsdf(nt, make_local=True):
    """(node_tree, principled) of a material tree, looking inside node groups too.
    A group that holds the shader is made single-user so edits stay on this material."""
    b = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if b is not None:
        return nt, b
    for g in nt.nodes:
        if g.bl_idname == "ShaderNodeGroup" and g.node_tree:
            sub, b = find_bsdf(g.node_tree, make_local=False)
            if b is not None:
                if make_local:
                    g.node_tree = g.node_tree.copy()
                    sub, b = find_bsdf(g.node_tree, make_local=False)
                return sub, b
    return nt, None


def opaque(m):
    """Mixamo FBX wants opaque materials: cut every Alpha link and set alpha 1."""
    if not m or not m.use_nodes:
        return m
    trees = [m.node_tree] + [n.node_tree for n in m.node_tree.nodes
                             if n.bl_idname == "ShaderNodeGroup" and n.node_tree]
    for t in trees:
        for b in (n for n in t.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"):
            for l in list(b.inputs["Alpha"].links):
                t.links.remove(l)
            b.inputs["Alpha"].default_value = 1.0
    for attr, val in (("blend_method", "OPAQUE"), ("surface_render_method", "DITHERED")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    return m


def mat_variant(src_name, new_name, tint=None, tint_mix=1.0, roughness=None, metallic=None, emission_off=True):
    """Copy a BlenderKit material; optionally multiply its base colour with a tint.
    Works when the Principled shader is wrapped in a node group; always made opaque."""
    src = bpy.data.materials[src_name]
    m = bpy.data.materials.get(new_name)
    if m:
        bpy.data.materials.remove(m)
    m = src.copy()
    m.name = new_name
    nt = m.node_tree
    # neutralise displacement for clean EEVEE (bump only)
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    for l in list(out.inputs["Displacement"].links):
        nt.links.remove(l)
    want = tint is not None or roughness is not None or metallic is not None
    t, bsdf = find_bsdf(nt, make_local=want)
    if bsdf is None:
        # procedural BlenderKit groups (felt, velvet) expose their colour as a group input
        grp = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeGroup"), None)
        cin = None if grp is None else next(
            (i for i in grp.inputs if i.type == "RGBA" and "color" in i.name.lower() and not i.is_linked), None)
        if tint is not None and cin is not None:
            c = list(cin.default_value)
            cin.default_value = [c[k] * (1 - tint_mix + tint_mix * tint[k]) for k in range(3)] + [c[3]]
        elif tint is not None:
            WARNINGS.append(f"{new_name}: no Principled BSDF or colour input, tint not applied")
        if roughness is not None or metallic is not None:
            WARNINGS.append(f"{new_name}: procedural shader, roughness/metallic not applied")
        return opaque(m)
    if tint is not None:
        bc = bsdf.inputs["Base Color"]
        mix = t.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = tint_mix
        mix.inputs["B"].default_value = (*tint, 1)
        if bc.is_linked:
            t.links.new(bc.links[0].from_socket, mix.inputs["A"])
        else:
            mix.inputs["A"].default_value = bc.default_value
        t.links.new(mix.outputs["Result"], bc)
    if roughness is not None:
        for l in list(bsdf.inputs["Roughness"].links):
            t.links.remove(l)
        bsdf.inputs["Roughness"].default_value = roughness
    if metallic is not None:
        for l in list(bsdf.inputs["Metallic"].links):
            t.links.remove(l)
        bsdf.inputs["Metallic"].default_value = metallic
    return opaque(m)


def hair_mat(src_name, new_name, color, value=1.0):
    """Recolour a BlenderKit hair material: grey-scale its texture then tint."""
    src = bpy.data.materials[src_name]
    m = bpy.data.materials.get(new_name)
    if m:
        bpy.data.materials.remove(m)
    m = src.copy(); m.name = new_name
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    bc = bsdf.inputs["Base Color"]
    hs = nt.nodes.new("ShaderNodeHueSaturation")
    hs.inputs["Saturation"].default_value = 0.0
    hs.inputs["Value"].default_value = value
    if bc.is_linked:
        nt.links.new(bc.links[0].from_socket, hs.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    mix.inputs["B"].default_value = (*color, 1)
    nt.links.new(hs.outputs["Color"], mix.inputs["A"])
    nt.links.new(mix.outputs["Result"], bc)
    return opaque(m)


def flat_mat(name, color, roughness=0.6, metallic=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    return m


def ring_rows(z_list, radii_fn, center_fn, n=48, gap=None, mod=None):
    """Build rows of points around Z. radii_fn(z, t)->(rx, ry); center_fn(z,t)->(cx, cy).
    gap: (angle_center, half_width) radians to leave open (front opening).
    mod(a, t, j) -> radial multiplier (folds)."""
    rows = []
    for i, z in enumerate(z_list):
        t = i / max(1, len(z_list) - 1)
        rx, ry = radii_fn(z, t)
        cx, cy = center_fn(z, t)
        row = []
        for j in range(n):
            if gap:
                a0 = gap[0] + gap[1]
                a = a0 + (2 * math.pi - 2 * gap[1]) * j / (n - 1)
            else:
                a = 2 * math.pi * j / n
            k = mod(a, t, j) if mod else 1.0
            row.append(Vector((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a), z)))
        rows.append(row)
    return rows


def body_slice(z, band=0.012, xmax=0.30, filt=None):
    """Ellipse-ish fit of the body cross-section at height z: (cx, cy, rx, ry)."""
    pts = [i["p"] for i in body_info() if abs(i["p"].z - z) < band and abs(i["p"].x) < xmax
           and (filt is None or filt(i))]
    if not pts:
        return (0, 0, 0.1, 0.1)
    xs = [p.x for p in pts]; ys = [p.y for p in pts]
    return ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2)


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def knee_z():
    arm = arm_obj()
    return (arm.matrix_world @ arm.data.bones[P + "LeftLeg"].head_local).z


def leg_blend(p, zt, zb, follow, knee, side_w=0.07):
    """Weights for hanging cloth: Hips at the waist, sliding to the thighs going down, with a
    smooth left/right blend across the centre line and shin influence below the knee."""
    t = min(1.0, max(0.0, (zt - p.z) / max(1e-6, zt - min(zb, 0.80))))
    f = follow * t
    wl = smoothstep((p.x + side_w) / (2 * side_w))      # 1 = fully on the character's left
    g = 0.55 * smoothstep((knee + 0.06 - p.z) / 0.16)   # share of the leg weight on the shin
    w = {"Hips": 1 - f}
    for s, k in (("Left", wl), ("Right", 1 - wl)):
        if k > 0:
            w[s + "UpLeg"] = f * k * (1 - g)
            if g > 0:
                w[s + "Leg"] = f * k * g
    return w


def skirt(name, col, z_top, z_bot, flare=0.06, ease=0.02, rings=12, n=56, gap=None, back_extra=0.0,
          leg_follow=0.75, thickness=0.004, mod=None):
    """Coat tails / tunic skirt from the waist down, weighted Hips -> UpLeg."""
    cx, cy, rx, ry = body_slice(z_top, xmax=0.25, filt=lambda i: i["dom"] in TORSO | UPLEG)
    z_list = [z_top + (z_bot - z_top) * i / (rings - 1) for i in range(rings)]
    hip = body_slice(0.80, xmax=0.25, filt=lambda i: i["dom"] in TORSO | UPLEG)

    def radii(z, t):
        bx = max(rx, hip[2]) if z < 0.86 else rx
        by = max(ry, hip[3]) if z < 0.86 else ry
        return (bx + ease + flare * t ** 1.2, by + ease + flare * 0.8 * t ** 1.2)

    def center(z, t):
        return (cx, cy + back_extra * t)

    rows = ring_rows(z_list, radii, center, n=n, gap=gap, mod=mod)
    ob = mesh_from_grid(name, rows, col, closed=gap is None)
    zt, zb = z_top, z_bot

    knee = knee_z()

    def w(p):
        d = leg_blend(p, zt, zb, leg_follow, knee)
        # the top rings meet a spine-weighted tunic under the belt: share some Spine so a
        # torso twist does not open a gap there
        s = 0.5 * smoothstep((p.z - (zt - 0.06)) / 0.06)
        if s > 0:
            d = {k: v * (1 - s) for k, v in d.items()}
            d["Spine"] = d.get("Spine", 0) + s
        return d
    set_weights(ob, w)
    rig(ob, thickness=thickness, subsurf=1)
    return ob


def trim_mesh(ob, keep_world, cuts=2):
    """Subdivide (linear) then delete faces having any vertex where keep_world(p) is False.
    Gives a much smoother cut line than face-level region selection."""
    me = ob.data
    mw = ob.matrix_world
    bm = bmesh.new(); bm.from_mesh(me)
    if cuts:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    keep = {v: keep_world(mw @ v.co) for v in bm.verts}
    dead = [f for f in bm.faces if not all(keep[v] for v in f.verts)]
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # relax the new open edge so it is not stair-stepped
    for _ in range(4):
        bnd = [v for v in bm.verts if v.is_boundary]
        for v in bnd:
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) == 2:
                v.co = v.co * 0.5 + (nb[0].co + nb[1].co) * 0.25
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True


def scalp_cap(name, col, mat, front_z=1.695, side_z=1.60, back_z=1.48, offset=0.0075, ear_cut=True):
    """Painted-hair cap grown from the head surface (covers bald skull under hair cards)."""
    cy = -0.027

    def zlim(p):
        fy = max(0.0, min(1.0, (cy - p.y) / 0.20))   # 1 at the face, 0 at centre/back
        by = max(0.0, min(1.0, (p.y - cy) / 0.18))   # 1 at the back
        return side_z + (front_z - side_z) * fy ** 1.5 - (side_z - back_z) * by ** 1.2

    def fine(p):
        if ear_cut:
            # tight clearance around the ear itself (measured ear: y -0.041..0.001,
            # z 1.524..1.645, |x| > 0.172) so the hair still covers the head above and
            # in front of / behind the ear
            ey = (p.y + 0.020) / 0.028; ez = (p.z - 1.585) / 0.066
            if ey * ey + ez * ez < 1.0 and abs(p.x) > 0.162:
                return False
        return p.z > zlim(p)

    def loose(i):
        p, d = i["p"], i["dom"]
        return d == "Head" and p.z > zlim(p) - 0.06 and p.y > -0.24
    ob = from_body(name, loose, offset, col, keep_keys=(), thickness=0.0, subsurf=0, smooth_iter=0,
                   largest_only=False)
    trim_mesh(ob, fine, cuts=2)
    sub = ob.modifiers.new("Subdivision", "SUBSURF"); sub.levels = 1; sub.render_levels = 1
    cube_uv(ob, 0.1)
    assign(ob, mat)
    return ob


def surface_ribbon(name, col, path_xz, width, offset, sides=("front", "back"), samples=60, across=5):
    """A strap that follows the body surface: a polyline in the XZ plane is ray-cast onto
    the rest-pose body from the front and/or back, pushed out by `offset`, then skinned."""
    from mathutils.bvhtree import BVHTree
    body = body_obj()
    arm = arm_obj()
    old = arm.data.pose_position; arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    be = body.evaluated_get(dg)
    bme = bmesh.new(); bme.from_mesh(be.to_mesh()); bme.transform(body.matrix_world)
    bme.normal_update()
    be.to_mesh_clear()
    tree = BVHTree.FromBMesh(bme)
    arm.data.pose_position = old
    # resample the path
    pts = [Vector(p) for p in path_xz]
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum((b - a).length for a, b in segs)
    verts, faces = [], []
    for side in sides:
        sgn = -1 if side == "front" else 1
        base = len(verts)
        for s in range(samples + 1):
            d = total * s / samples
            for a, b in segs:
                L = (b - a).length
                if d <= L + 1e-9:
                    c = a + (b - a) * (d / max(L, 1e-9)); tan = (b - a).normalized(); break
                d -= L
            nrm2 = Vector((-tan.y, tan.x))
            for k in range(across):
                u = (k / (across - 1) - 0.5) * width
                q = c + nrm2 * u
                origin = Vector((q.x, sgn * 1.0, q.y))
                hit, n, fi, dist = tree.ray_cast(origin, Vector((0, -sgn, 0)))
                if hit is None:
                    hit = Vector((q.x, 0, q.y)); n = Vector((0, sgn, 0))
                verts.append(hit + n.normalized() * offset)
        for s in range(samples):
            for k in range(across - 1):
                a = base + s * across + k
                faces.append((a, a + 1, a + 1 + across, a + across))
    bme.free()
    remove_obj(name)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0015)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=0.0015)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    transfer_weights(ob)
    restrict_weights(ob, {"Hips", "Spine", "Spine1", "Spine2", "Neck"})
    rig(ob, thickness=0.004, subsurf=1)
    so = ob.modifiers.get("Solidify")
    if so:
        so.use_even_offset = False
        so.use_quality_normals = False
    return ob


def restrict_weights(ob, allowed_short):
    """Keep only the given bones' influence (renormalised); verts left empty get Spine2."""
    allowed = {P + b for b in allowed_short}
    for g in list(ob.vertex_groups):
        if g.name not in allowed:
            ob.vertex_groups.remove(g)
    fallback = ob.vertex_groups.get(P + "Spine2") or ob.vertex_groups.new(name=P + "Spine2")
    for v in ob.data.vertices:
        tot = sum(g.weight for g in v.groups)
        if tot < 1e-5:
            fallback.add([v.index], 1.0, "REPLACE")
        else:
            for g in v.groups:
                g.weight /= tot


def take_asset(root_name, col, new_name=None, copy=True):
    """Duplicate (or move) an imported BlenderKit hierarchy into a costume collection."""
    root = bpy.data.objects[root_name]
    objs = [root] + list(root.children_recursive)
    if not copy:
        for o in objs:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            col.objects.link(o)
        return root
    mp = {}
    for o in objs:
        n = o.copy()
        if o.data is not None and o.type == "MESH":
            n.data = o.data.copy()
        col.objects.link(n)
        mp[o] = n
    for o, n in mp.items():
        if o.parent in mp:
            n.parent = mp[o.parent]
            n.matrix_parent_inverse = o.matrix_parent_inverse.copy()
    r = mp[root]
    if new_name:
        r.name = new_name
    return r


def asset_bbox(root):
    from mathutils import Vector as V
    bpy.context.view_layer.update()
    objs = [root] + list(root.children_recursive)
    mn = V((1e9,) * 3); mx = V((-1e9,) * 3)
    for o in objs:
        if o.type != "MESH" or o.hide_render:
            continue
        for c in o.bound_box:
            w = o.matrix_world @ V(c)
            mn = V(map(min, mn, w)); mx = V(map(max, mx, w))
    return mn, mx


def fit_asset(root, center=None, size=None, rot=None, bottom=None, mirror_x=False):
    """Rotate root (euler degrees), scale so bbox == size (tuple, None entries keep uniform),
    then move so bbox centre == center (or bbox bottom == bottom z)."""
    root.rotation_mode = "XYZ"
    if rot is not None:
        root.rotation_euler = [math.radians(a) for a in rot]
    if mirror_x:
        root.scale.x *= -1
    if size is not None:
        mn, mx = asset_bbox(root)
        d = mx - mn
        fac = [None if s is None else s / max(d[i], 1e-6) for i, s in enumerate(size)]
        u = [f for f in fac if f is not None]
        uf = sum(u) / len(u)
        fac = [uf if f is None else f for f in fac]
        # bbox axes are world axes; apply scale in world by scaling the root matrix
        S = Matrix.Diagonal((*fac, 1.0))
        mw = root.matrix_world.copy()
        loc = mw.translation.copy()
        m = S @ Matrix.Translation(-loc) @ mw
        m.translation += loc
        root.matrix_world = m
    mn, mx = asset_bbox(root)
    c = (mn + mx) / 2
    if center is not None:
        tgt = Vector(center)
        if bottom is not None:
            tgt.z = bottom + (mx.z - mn.z) / 2
        root.matrix_world.translation += tgt - c
    bpy.context.view_layer.update()
    return asset_bbox(root)


def asset_material(root, mat):
    for o in [root] + list(root.children_recursive):
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(mat)


def bind_asset_to_bone(root, bone):
    """Rigidly attach a whole hierarchy by bone-parenting its root."""
    bone_parent(root, bone)


def bind_asset_skinned(root, smooth=1, thickness=0.0):
    """Join an asset's meshes into one, transfer body weights and add an armature modifier
    (for things that must bend: boots, sleeves...). Returns the mesh object."""
    objs = [o for o in [root] + list(root.children_recursive) if o.type == "MESH"]
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    # bake modifiers (mirror etc.) and transforms into the mesh data
    for o in objs:
        mw = o.matrix_world.copy()
        newme = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        for m in list(o.modifiers):
            o.modifiers.remove(m)
        o.data = newme
        o.parent = None
        o.data.transform(mw)
        if mw.determinant() < 0:
            o.data.flip_normals()
        o.matrix_world = Matrix.Identity(4)
    main = objs[0]
    if len(objs) > 1:
        with bpy.context.temp_override(active_object=main, selected_editable_objects=objs, object=main):
            bpy.ops.object.join()
    for o in [root] + list(root.children_recursive):
        if o != main and o.name in bpy.data.objects and o.type == "EMPTY":
            bpy.data.objects.remove(o, do_unlink=True)
    for m in list(main.modifiers):
        main.modifiers.remove(m)
    main.vertex_groups.clear()
    transfer_weights(main, smooth=smooth)
    arm = arm_obj()
    main.parent = arm
    main.matrix_parent_inverse = arm.matrix_world.inverted()
    am = main.modifiers.new("Armature", "ARMATURE")
    am.object = arm
    bpy.context.view_layer.objects.active = main
    return main


def widen_pair(ob, center=0.088, factor=1.2, below=0.6):
    """For a joined (world-space) pair of boots: re-centre each boot on x=+-center and
    widen it about its own axis (only verts below `below` m)."""
    me = ob.data
    xs = [v.co.x for v in me.vertices]
    cl = sum(x for x in xs if x > 0) / max(1, sum(1 for x in xs if x > 0))
    for v in me.vertices:
        if v.co.z > below:
            continue
        s = 1 if v.co.x > 0 else -1
        ax = abs(v.co.x)
        v.co.x = s * (center + (ax - cl) * factor)
    me.update()


def fit_pair_to_legs(ob, margin=0.010, zmax=0.62, bin_h=0.02):
    """Per height slice: centre each boot of a world-space pair on the leg and make sure it is
    at least leg-size + margin wide/deep, so the skin never pokes through."""
    me = ob.data
    info = body_info()
    nb = int(zmax / bin_h) + 2

    def stats(pts):
        if not pts:
            return None
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return ((min(xs) + max(xs)) / 2, (max(xs) - min(xs)), min(ys), max(ys))
    leg_b = [[] for _ in range(nb)]
    for i in info:
        p = i["p"]
        if p.x > 0.015 and p.z < zmax + bin_h and i["dom"] in UPLEG | LEG | FOOT:
            leg_b[int(p.z / bin_h)].append((p.x, p.y))
    boot_b = [[] for _ in range(nb)]
    for v in me.vertices:
        if 0 <= v.co.z < zmax + bin_h:
            boot_b[int(v.co.z / bin_h)].append((abs(v.co.x), v.co.y))
    ls = [stats(b) for b in leg_b]
    bs = [stats(b) for b in boot_b]
    # fill missing leg slices from neighbours
    for k in range(nb):
        if ls[k] is None:
            for d in range(1, nb):
                for kk in (k - d, k + d):
                    if 0 <= kk < nb and ls[kk] is not None:
                        ls[k] = ls[kk]; break
                if ls[k] is not None:
                    break
    for v in me.vertices:
        if not (0 <= v.co.z < zmax):
            continue
        k = int(v.co.z / bin_h)
        if bs[k] is None or ls[k] is None:
            continue
        bcx, bw, bymin, bymax = bs[k]
        lcx, lw, lymin, lymax = ls[k]
        kx = max(1.0, (lw + 2 * margin) / max(bw, 1e-4))
        s = 1 if v.co.x > 0 else -1
        v.co.x = s * (lcx + (abs(v.co.x) - bcx) * kx)
        nymin = min(bymin, lymin - margin); nymax = max(bymax, lymax + margin)
        if bymax - bymin > 1e-4:
            v.co.y = nymin + (v.co.y - bymin) * (nymax - nymin) / (bymax - bymin)
    me.update()


def trim_asset(root, keep_world):
    """Delete the vertices of an imported asset where keep_world(world_point) is False
    (e.g. hair strands that would poke through a hat)."""
    n = 0
    for o in [root] + list(root.children_recursive):
        if o.type != "MESH":
            continue
        if o.data.users > 1:
            o.data = o.data.copy()
        mw = o.matrix_world
        bm = bmesh.new(); bm.from_mesh(o.data)
        dead = [v for v in bm.verts if not keep_world(mw @ v.co)]
        n += len(dead)
        bmesh.ops.delete(bm, geom=dead, context="VERTS")
        bm.to_mesh(o.data); bm.free()
    return n


# --- the project's own hair library (Tripo3D models baked by work/tools3d/bake_hair.py) -------------
from . import paths as _paths
HAIR_LIB = str(_paths.OLD_HAIR_LIB)
SKULL_C = Vector((0.0, -0.0246, 1.6112))   # centre of a sphere fitted to Aj's cranium (rest pose)
SKULL_R = 0.198                            # its radius: one "head radius" of the library models
EAR = dict(y=-0.019, z=1.584, ry=0.030, rz=0.064, x=0.165)   # measured ear: y -0.048..0.010, z 1.522..1.646
_SKULL = {}


def _skull_map(NE=48, NA=96):
    """Distance from SKULL_C to Aj's head surface for every direction, on an (elevation, azimuth) grid.
    Rays go to the head and neck skin with the ears left out (holes are filled from round about), then the map is
    smoothed, so hair follows the egg shape of the skull but not the nose, lips or ears."""
    if "map" in _SKULL:
        return _SKULL["map"]
    import numpy as np
    from mathutils.bvhtree import BVHTree
    info = body_info()
    me = body_obj().data

    def ear(p):
        return abs(p.x) > EAR["x"] - 0.01 and ((p.y - EAR["y"]) / (EAR["ry"] + 0.012)) ** 2 + \
            ((p.z - EAR["z"]) / (EAR["rz"] + 0.012)) ** 2 < 1.0
    keep = [all(info[k]["dom"] in HEADNECK and not ear(info[k]["p"]) for k in poly.vertices) for poly in me.polygons]
    verts = [i["p"] for i in info]
    polys = [tuple(poly.vertices) for poly, k in zip(me.polygons, keep) if k]
    bvh = BVHTree.FromPolygons(verts, polys)
    R = np.full((NE, NA), np.nan)
    for i in range(NE):
        el = math.radians(-90 + 180 * (i + 0.5) / NE)
        for j in range(NA):
            az = math.radians(-180 + 360 * (j + 0.5) / NA)
            d = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
            hit = bvh.ray_cast(SKULL_C, d, 0.5)
            if hit[0] is not None and el > math.radians(-75):
                R[i, j] = (hit[0] - SKULL_C).length
    for _ in range(200):                      # fill the holes (ears, below the neck) from their neighbours
        miss = np.isnan(R)
        if not miss.any():
            break
        P = np.pad(R, ((1, 1), (0, 0)), mode="edge")
        nb = np.stack([P[:-2], P[2:], np.roll(R, 1, 1), np.roll(R, -1, 1)])
        fill = np.nanmean(np.where(np.isnan(nb), np.nan, nb), axis=0)
        R[miss] = fill[miss]
    R = np.nan_to_num(R, nan=SKULL_R)
    for _ in range(3):                        # smooth away nose / lips / chin detail
        P = np.pad(R, ((1, 1), (0, 0)), mode="edge")
        R = (2 * R + P[:-2] + P[2:] + np.roll(R, 1, 1) + np.roll(R, -1, 1)) / 6.0
    _SKULL["map"] = R
    return R


def library_hair(name, col, model, mat, thick=0.8, lift=0.003, decimate=0.45, ear_clear=True,
                 press=None, hat_lift=0.0):
    """Put a hair (or beard) from the project's own library on Aj's head.
    The library stores the hair round a ball of radius 1 (points in head radii from the head centre, triangles, and a
    root-to-tip value g). Every point is laid along its own direction from Aj's skull centre: the shell that sat on the
    ball lands on Aj's skin (+lift), the rest of the hair stands off it by (r - 1) head radii x thick.
    ear_clear: the hair thins down to the skin round the ears and is opened just over the ear itself, so the cut is
    not a thick wall.
    press=(z0, z1): hat hair. Above z0 the hair is pressed flat onto the skull (fully by z1), so it stays inside a hat
    without a cut edge; hat_lift adds a constant to the lift there."""
    import numpy as np
    d = np.load(f"{HAIR_LIB}\\{model}.npz")
    V = d["v"].astype(float); F = d["f"].astype(np.int64); g = d["g"].astype(float)
    r = np.linalg.norm(V, axis=1)
    D = V / r[:, None]
    el = np.degrees(np.arcsin(np.clip(D[:, 2], -1, 1)))
    az = np.degrees(np.arctan2(D[:, 0], -D[:, 1]))
    Rm = _skull_map()
    NE, NA = Rm.shape
    fe = np.clip((el + 90) / 180 * NE - 0.5, 0, NE - 1.001); fa = (az + 180) / 360 * NA - 0.5
    y0, x0 = np.floor(fe).astype(int), np.floor(fa).astype(int); ty, tx = fe - y0, fa - x0
    s = lambda yy, xx: Rm[np.clip(yy, 0, NE - 1), xx % NA]
    rs = (s(y0, x0) * (1 - tx) + s(y0, x0 + 1) * tx) * (1 - ty) + (s(y0 + 1, x0) * (1 - tx) + s(y0 + 1, x0 + 1) * tx) * ty
    stand = np.maximum(r - 0.985, 0.0) * SKULL_R * thick
    C0 = np.array(SKULL_C)[None, :]
    W0 = C0 + D * (rs + lift + stand)[:, None]          # where the point would be without pressing
    f = np.ones(len(W0)); base = np.full(len(W0), lift)
    sm = lambda x: (lambda t: t * t * (3 - 2 * t))(np.clip(x, 0.0, 1.0))
    drop = np.zeros(len(W0), dtype=bool)
    if ear_clear:
        ey = (W0[:, 1] - EAR["y"]) / (EAR["ry"] + 0.014); ez = (W0[:, 2] - EAR["z"]) / (EAR["rz"] + 0.012)
        e = np.sqrt(ey * ey + ez * ez)
        side = sm((np.abs(W0[:, 0]) - (EAR["x"] - 0.06)) / 0.03)
        f *= 1 - side * (1 - sm((e - 1.0) / 0.7))       # thin to the skin within 0.7 ellipse radii of the opening
        # hair left practically on the skin there would fight the skin (it bends with the neck): drop it
        drop = (side > 0.3) & (stand * f < 0.004) & (e < 1.7)
    if press:
        z0, z1 = press
        k = sm((W0[:, 2] - z0) / (z1 - z0))
        f *= 1 - k * 0.92
        base = base + k * hat_lift
    W = C0 + D * (rs + base + stand * f)[:, None]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(W)); me.vertices.foreach_set("co", W.astype(np.float32).ravel())
    me.loops.add(F.size); me.loops.foreach_set("vertex_index", F.ravel().astype(np.int32))
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", (np.arange(len(F)) * 3).astype(np.int32))
    me.update(calc_edges=True); me.validate()
    at = me.attributes.new("hair_g", "FLOAT", "POINT"); at.data.foreach_set("value", g.astype(np.float32))
    ob = bpy.data.objects.new(name, me); col.objects.link(ob)
    if ear_clear:
        bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()

        def opening(p):
            ey = (p.y - EAR["y"]) / (EAR["ry"] + 0.014); ez = (p.z - EAR["z"]) / (EAR["rz"] + 0.012)
            return abs(p.x) > EAR["x"] - 0.03 and ey * ey + ez * ez < 1.0
        dead = [f_ for f_ in bm.faces if any(drop[v.index] or opening(v.co) for v in f_.verts)]
        bmesh.ops.delete(bm, geom=dead, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(me); bm.free()
    if decimate and decimate < 1.0:
        md = ob.modifiers.new("thin", "DECIMATE"); md.ratio = decimate
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get(); dg.update()
        ev = ob.evaluated_get(dg)
        new = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        if len(new.polygons) == 0:            # evaluation not ready: keep the full mesh rather than nothing
            bpy.data.meshes.remove(new)
            WARNINGS.append(f"{name}: decimate gave an empty mesh, kept the full one")
        else:
            ob.modifiers.clear(); old = ob.data; ob.data = new; bpy.data.meshes.remove(old); new.name = name
        ob.modifiers.clear()
    for p in ob.data.polygons:
        p.use_smooth = True
    assign(ob, mat)
    return ob


HYBRID_HAIR_LIB = str(_paths.HAIR)


def hybrid_hair(name, col, model, mat, decimate=0.45, press=None, floor=0.002):
    """Put a hair from the hybrid hair library (already sculpted round Aj_Hybrid_Base, stored in rest-pose world
    metres) on Aj as it is. press=(z0, z1): hat hair; above z0 the hair's stand-off from the skull is squashed
    (fully by z1) so it stays inside the hat without a cut edge, but never closer than `floor` to the skin."""
    import numpy as np
    d = np.load(f"{HYBRID_HAIR_LIB}\\{model}.npz")
    W = d["v"].astype(float); F = d["f"].astype(np.int64); g = d["g"].astype(float)
    if press:
        z0, z1 = press
        C0 = np.array(SKULL_C)[None, :]
        R = W - C0; r = np.linalg.norm(R, axis=1); D = R / r[:, None]
        el = np.degrees(np.arcsin(np.clip(D[:, 2], -1, 1))); az = np.degrees(np.arctan2(D[:, 0], -D[:, 1]))
        Rm = _skull_map(); NE, NA = Rm.shape
        fe = np.clip((el + 90) / 180 * NE - 0.5, 0, NE - 1.001); fa = (az + 180) / 360 * NA - 0.5
        y0, x0 = np.floor(fe).astype(int), np.floor(fa).astype(int); ty, tx = fe - y0, fa - x0
        s = lambda yy, xx: Rm[np.clip(yy, 0, NE - 1), xx % NA]
        rs = (s(y0, x0) * (1 - tx) + s(y0, x0 + 1) * tx) * (1 - ty) + \
             (s(y0 + 1, x0) * (1 - tx) + s(y0 + 1, x0 + 1) * tx) * ty
        sm = lambda x: (lambda t: t * t * (3 - 2 * t))(np.clip(x, 0.0, 1.0))
        k = sm((W[:, 2] - z0) / (z1 - z0))
        stand = r - rs
        new = np.where(stand > floor, floor + (stand - floor) * (1 - k * 0.92), stand)
        W = C0 + D * (rs + new)[:, None]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(W)); me.vertices.foreach_set("co", W.astype(np.float32).ravel())
    me.loops.add(F.size); me.loops.foreach_set("vertex_index", F.ravel().astype(np.int32))
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", (np.arange(len(F)) * 3).astype(np.int32))
    me.update(calc_edges=True); me.validate()
    at = me.attributes.new("hair_g", "FLOAT", "POINT"); at.data.foreach_set("value", g.astype(np.float32))
    ob = bpy.data.objects.new(name, me); col.objects.link(ob)
    if decimate and decimate < 1.0:
        md = ob.modifiers.new("thin", "DECIMATE"); md.ratio = decimate
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get(); dg.update()
        new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        if len(new_me.polygons) == 0:
            bpy.data.meshes.remove(new_me)
            WARNINGS.append(f"{name}: decimate gave an empty mesh, kept the full one")
        else:
            old = ob.data; ob.data = new_me; bpy.data.meshes.remove(old); new_me.name = name
        ob.modifiers.clear()
    for p in ob.data.polygons:
        p.use_smooth = True
    assign(ob, mat)
    return ob


def library_hair_mat(name, color, root=0.55, roughness=0.62, specular=0.3):
    """Flat sculpted-hair material: darker at the roots, lighter toward the tips (from the hair_g attribute,
    which reaches about 0.8 at the tips)."""
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Specular IOR Level"].default_value = specular
    at = nt.nodes.new("ShaderNodeAttribute"); at.attribute_name = "hair_g"; at.attribute_type = "GEOMETRY"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (color[0] * root, color[1] * root, color[2] * root, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (*color, 1)
    nt.links.new(at.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def cull_feet(zmax=0.13, foot_top=0.16):
    """Delete body faces fully hidden inside the boots (all three costumes wear boots).
    Shape keys are kept; only the costume files get this, never the base file."""
    body = body_obj()
    me = body.data
    info = body_info()
    bm = bmesh.new(); bm.from_mesh(me)
    def hidden(i):
        # everything below zmax, plus the whole foot (heel included) up to the ankle; the lowest
        # boot top (King, 0.215) is well above `foot_top`
        return (i["p"].z < zmax and i["dom"] in FOOT | LEG) or (i["dom"] in FOOT and i["p"].z < foot_top)
    kill = [f for f in bm.faces if all(hidden(info[v.index]) for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(me); bm.free(); me.update()
    _INFO_CACHE.clear()
    return len(kill)


def cover_feet(ob, margin=0.008, zmax=0.16, bz=0.02, by=0.02):
    """Second boot pass: in each (height, depth) cell make the boot's |x| span cover the foot's
    |x| span + margin (heel and ankle corners that a whole-slice fit misses). The remap is
    interpolated bilinearly between cells so the surface stays smooth."""
    me = ob.data
    info = body_info()
    feet = [i["p"] for i in info if i["p"].x > 0.015 and i["p"].z < zmax + bz and i["dom"] in FOOT | LEG]
    ys = [p.y for p in feet]
    y0 = min(ys) - by; ny = int((max(ys) - y0) / by) + 2
    nz = int(zmax / bz) + 2
    f = [[None] * ny for _ in range(nz)]
    b = [[None] * ny for _ in range(nz)]

    def put(g, z, y, x):
        k, j = int(z / bz), int((y - y0) / by)
        if 0 <= k < nz and 0 <= j < ny:
            c = g[k][j]
            g[k][j] = (x, x) if c is None else (min(c[0], x), max(c[1], x))
    for p in feet:
        put(f, max(p.z, 0), p.y, p.x)
    for v in me.vertices:
        if v.co.z < zmax + bz:
            put(b, max(v.co.z, 0), v.co.y, abs(v.co.x))
    # per-cell remap (old lo, old hi, new lo, new hi); identity where nothing to fix
    R = [[None] * ny for _ in range(nz)]
    for k in range(nz):
        for j in range(ny):
            fc, bc = f[k][j], b[k][j]
            if fc and bc and bc[1] - bc[0] > 1e-4:
                R[k][j] = (bc[0], bc[1], min(bc[0], fc[0] - margin), max(bc[1], fc[1] + margin))

    def remap(k, j, x):
        if 0 <= k < nz and 0 <= j < ny and R[k][j]:
            lo, hi, nlo, nhi = R[k][j]
            return nlo + (x - lo) * (nhi - nlo) / (hi - lo)
        return x
    for v in me.vertices:
        if not (v.co.z < zmax):
            continue
        z = max(v.co.z, 0); ax = abs(v.co.x)
        fz = z / bz - 0.5; fy = (v.co.y - y0) / by - 0.5
        k0, j0 = int(fz // 1), int(fy // 1); tz, ty = fz - k0, fy - j0
        acc = 0.0
        for dk, wz in ((0, 1 - tz), (1, tz)):
            for dj, wy in ((0, 1 - ty), (1, ty)):
                acc += wz * wy * remap(k0 + dk, j0 + dj, ax)
        # fade out over the top cell so the boot shaft is untouched
        t = min(1.0, max(0.0, (zmax - v.co.z) / bz))
        nx = ax + (acc - ax) * t
        v.co.x = nx if v.co.x > 0 else -nx
    me.update()


def refit_weights(ob):
    """Re-transfer body weights after the mesh was reshaped (boot fitting), so the weights
    match the final vertex positions."""
    ob.vertex_groups.clear()
    transfer_weights(ob)


def plane_ribbon(name, col, plane_pts, width, offset, face_filter, center=None, skip=None,
                 samples=180, across=4, thickness=0.004, bone=None, allowed=None, smooth=3):
    """A closed (or, with `skip`, open) band where a plane cuts the rest-pose body surface:
    rays are cast inside the plane towards `center` onto the body faces passing face_filter.
    Used for straps that wrap round the head or diagonally over a shoulder.
    bone: weight everything to one bone; else transfer + restrict to `allowed` short names."""
    from mathutils.bvhtree import BVHTree
    info = body_info()
    body = body_obj()
    a, b, c = (Vector(p) for p in plane_pts)
    n = (b - a).cross(c - a).normalized()
    C = Vector(center) if center is not None else (a + b + c) / 3
    C = C - n * (C - a).dot(n)
    e1 = (a - C); e1 = (e1 - n * e1.dot(n)).normalized()
    e2 = n.cross(e1)
    # BVH of the selected rest-pose faces
    verts = [i["p"] for i in info]
    polys = [tuple(p.vertices) for p in body.data.polygons
             if all(face_filter(info[k]) for k in p.vertices)]
    tree = BVHTree.FromPolygons(verts, polys)
    rows = []
    for s in range(samples):
        ang = 2 * math.pi * s / samples
        d = e1 * math.cos(ang) + e2 * math.sin(ang)
        row = []
        for k in range(across):
            u = (k / (across - 1) - 0.5) * width
            hit, nrm, fi, dist = tree.ray_cast(C + n * u + d * 0.8, -d)
            row.append(None if hit is None else (hit, nrm.normalized()))
        rows.append(row)
    # fill misses from the nearest good sample on the loop
    good = [i for i, r in enumerate(rows) if all(x is not None for x in r)]
    if not good:
        raise RuntimeError(f"{name}: ribbon plane misses the body")
    for i, r in enumerate(rows):
        if any(x is None for x in r):
            j = min(good, key=lambda g: min(abs(g - i), samples - abs(g - i)))
            rows[i] = rows[j]
    pts = [[h + nm * offset for h, nm in r] for r in rows]
    return _ribbon_object(name, col, pts, True, C, skip, smooth, thickness, bone, allowed)


def _ribbon_object(name, col, pts, closed, C, skip, smooth, thickness, bone, allowed):
    """pts: list of cross-section rows (each `across` points). Builds, weights and rigs."""
    samples = len(pts); across = len(pts[0])
    for _ in range(smooth):
        new = []
        for i in range(samples):
            if not closed and i in (0, samples - 1):
                new.append(pts[i]); continue
            a, b = pts[i - 1], pts[(i + 1) % samples]
            new.append([(a[k] + pts[i][k] * 2 + b[k]) / 4 for k in range(across)])
        pts = new
    keep = [not (skip and skip((pts[i][0] + pts[i][-1]) / 2)) for i in range(samples)]
    vs, fs = [], []
    idx = {}
    for i in range(samples):
        if keep[i]:
            idx[i] = len(vs)
            vs.extend(pts[i])
    for i in range(samples if closed else samples - 1):
        j = (i + 1) % samples
        if keep[i] and keep[j]:
            for k in range(across - 1):
                p0 = idx[i] + k; p1 = idx[j] + k
                fs.append((p0, p0 + 1, p1 + 1, p1))
    if not fs:
        raise RuntimeError(f"{name}: ribbon has no faces")
    remove_obj(name)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in vs], [], fs)
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # make normals point away from the body
    out = sum(((f.calc_center_median() - C).dot(f.normal) for f in bm.faces))
    if out < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free()
    if bone:
        set_weights(ob, lambda p: {bone: 1.0})
    else:
        transfer_weights(ob)
        if allowed:
            restrict_weights(ob, allowed)
    rig(ob, thickness=thickness, subsurf=1)
    so = ob.modifiers.get("Solidify")
    if so:
        so.use_even_offset = False
    return ob


def path_ribbon(name, col, guide, width, offset, face_filter, center, closed=False, skip=None,
                 samples=120, across=4, thickness=0.003, bone=None, allowed=None, smooth=2, over=()):
    """A strap through guide points (Catmull-Rom), projected radially towards `center` onto the
    rest-pose body faces passing face_filter. Good for head straps.
    over: extra mesh objects the strap lies on top of (e.g. hair)."""
    from mathutils.bvhtree import BVHTree
    info = body_info()
    body = body_obj()
    verts = [i["p"] for i in info]
    polys = [tuple(p.vertices) for p in body.data.polygons
             if all(face_filter(info[k]) for k in p.vertices)]
    for o in over:
        n0 = len(verts)
        verts += [o.matrix_world @ v.co for v in o.data.vertices]
        polys += [tuple(n0 + k for k in p.vertices) for p in o.data.polygons]
    tree = BVHTree.FromPolygons(verts, polys)
    C = Vector(center)
    G = [Vector(p) for p in guide]
    m = len(G)

    def cr(t):
        seg = min(int(t), (m if closed else m - 1) - 1)
        u = t - seg
        idx = [seg - 1, seg, seg + 1, seg + 2]
        if closed:
            P0, P1, P2, P3 = (G[k % m] for k in idx)
        else:
            P0, P1, P2, P3 = (G[max(0, min(m - 1, k))] for k in idx)
        return 0.5 * ((2 * P1) + (-P0 + P2) * u + (2 * P0 - 5 * P1 + 4 * P2 - P3) * u * u
                      + (-P0 + 3 * P1 - 3 * P2 + P3) * u ** 3)
    span = m if closed else m - 1
    curve = [cr(span * s / (samples if closed else samples - 1)) for s in range(samples)]
    rows = []
    for s, c in enumerate(curve):
        nxt = curve[(s + 1) % samples] if (closed or s < samples - 1) else c + (c - curve[s - 1])
        prv = curve[s - 1] if (closed or s > 0) else c - (nxt - c)
        tan = (nxt - prv).normalized()
        radial = (c - C).normalized()
        side = tan.cross(radial).normalized()
        row = []
        for k in range(across):
            u = (k / (across - 1) - 0.5) * width
            q = c + side * u
            d = (q - C).normalized()
            hit, nrm, fi, dist = tree.ray_cast(C + d * 0.6, -d)
            row.append(None if hit is None else hit + nrm.normalized() * offset)
        rows.append(row)
    good = [i for i, r in enumerate(rows) if all(x is not None for x in r)]
    if not good:
        raise RuntimeError(f"{name}: ribbon misses the body")
    rows = [r if all(x is not None for x in r) else rows[min(good, key=lambda g: abs(g - i))]
            for i, r in enumerate(rows)]
    if over:
        # lying on lumpy hair: ride the outer envelope (running max of the distance from C, then
        # smoothed) so the strap bridges the gaps between locks instead of dipping into them
        n = len(rows)
        rad = [sum((p - C).length for p in r) / len(r) for r in rows]
        w = max(2, samples // 30)
        idx = (lambda i, j: (i + j) % n) if closed else (lambda i, j: max(0, min(n - 1, i + j)))
        env = [max(rad[idx(i, j)] for j in range(-w, w + 1)) for i in range(n)]
        for _ in range(4):
            env = [(env[idx(i, -1)] + 2 * env[i] + env[idx(i, 1)]) / 4 for i in range(n)]
        env = [max(e, r0) for e, r0 in zip(env, rad)]
        rows = [[C + (p - C) * (env[i] / rad[i]) for p in r] for i, r in enumerate(rows)]
    return _ribbon_object(name, col, rows, closed, C, skip, smooth, thickness, bone, allowed)


def fist_socket(side="Right"):
    """World point in the hollow of a posed, curled fist (where a handle should pass)."""
    arm = arm_obj()
    pb = arm.pose.bones
    mw = arm.matrix_world
    fingers = ("Index", "Middle", "Ring", "Pinky")
    base = [mw @ pb[f"{P}{side}Hand{f}1"].head for f in fingers if f"{P}{side}Hand{f}1" in pb]
    mid = [mw @ pb[f"{P}{side}Hand{f}3"].head for f in fingers if f"{P}{side}Hand{f}3" in pb]
    b = sum(base, Vector()) / len(base)
    m = sum(mid, Vector()) / len(mid)
    # the hollow sits close to the knuckle line, inside the curl (not at the finger tips)
    return b.lerp(m, 0.35)


def align_shaft_to(root, target, band=0.03):
    """Shift a prop horizontally so its shaft (cross-section at the target's height) is
    centred on target. Returns the shift."""
    objs = [o for o in [root] + list(root.children_recursive) if o.type == "MESH" and not o.hide_render]
    dg = bpy.context.evaluated_depsgraph_get()
    xs, ys = [], []
    z = target.z
    for o in objs:
        e = o.evaluated_get(dg); me = e.to_mesh()
        W = [o.matrix_world @ v.co for v in me.vertices]
        # cross-section = where edges cross the plane z (long shafts have no vertices there)
        for ed in me.edges:
            a, b = W[ed.vertices[0]], W[ed.vertices[1]]
            if (a.z - z) * (b.z - z) <= 0 and abs(a.z - b.z) > 1e-9:
                t = (z - a.z) / (b.z - a.z)
                q = a.lerp(b, t)
                xs.append(q.x); ys.append(q.y)
        e.to_mesh_clear()
    if not xs:
        WARNINGS.append(f"{root.name}: nothing crosses z={z:.3f}, grip not aligned")
        return Vector()
    c = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, target.z))
    d = Vector((target.x - c.x, target.y - c.y, 0))
    root.matrix_world.translation += d
    bpy.context.view_layer.update()
    return d


def boundary_extrude(ob, sel_fn, steps):
    """Extrude the boundary loop(s) whose verts satisfy sel_fn(world_co) through steps:
    list of (scale_about_centroid, axis_offset_vector_world). Weights copied from boundary."""
    me = ob.data
    mw = ob.matrix_world; imw = mw.inverted()
    bm = bmesh.new(); bm.from_mesh(me)
    dl = bm.verts.layers.deform.verify()
    edges = [e for e in bm.edges if e.is_boundary and all(sel_fn(mw @ v.co) for v in e.verts)]
    if not edges:
        bm.free(); return 0
    cur = edges
    for sc, off in steps:
        res = bmesh.ops.extrude_edge_only(bm, edges=cur)
        nv = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        ne = [g for g in res["geom"] if isinstance(g, bmesh.types.BMEdge)]
        c = sum((v.co for v in nv), Vector()) / len(nv)
        offl = imw.to_3x3() @ Vector(off)
        for v in nv:
            v.co = c + (v.co - c) * sc + offl
        cur = [e for e in ne if all(v in set(nv) for v in e.verts)]
    bm.to_mesh(me); bm.free()
    return len(edges)
