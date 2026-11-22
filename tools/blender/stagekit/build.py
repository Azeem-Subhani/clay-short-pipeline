"""stagekit.build - the world kit: ground, stone, timber, water, plants and props for sets.

Everything here is real 3D with believable materials (stagekit.mat), sized in metres for the 2D cast (adults are about
1.7 m, heads about 0.55 m across). A set is a place built around its action: put the things the story uses where the
camera can connect them, then dress the edges.

    G = build.ground("lawn", 60, "grass_lawn", holes=P["holes"])
    build.stone_wall("curtain", length=18, height=5.2, at=(0, 9, 0))
    build.tower("keep", radius=2.4, height=9, at=(7, 10, 0))
    P = build.pond("pond", at=(0, 2), size=(5, 7), depth=1.1, sluice="north")      # P["gate"], P["drain"](t0, t1)
    T = build.tree("oak", at=(-3.4, 2.5), height=5.5, branch=(1.0, 0.0, 2.6, 3.0)) # T["branch"] can break

`at` is where a thing rests (bottom centre); z defaults to 0. `rot_z` in degrees. The camera side of a set is -Y.
Surfaces are names from library/materials/catalog.json ("castle_stone", "oak_planks", ...): scanned ambientCG textures
when downloaded, a matching procedural stand-in otherwise. Pass tint="#hex" to shift a surface's colour.
"""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import core, mat


# ----------------------------------------------------------------------------- small helpers
def _mat(surface, tint=None, **kw):
    if surface is None:
        return None
    if hasattr(surface, "node_tree"):
        return surface
    if isinstance(surface, str) and surface.startswith("#"):
        return mat.PROCEDURAL["plain"](f"SK_plain_{surface}", color=surface) if f"SK_plain_{surface}" not in bpy.data.materials else bpy.data.materials[f"SK_plain_{surface}"]
    return mat.surface(surface, tint=tint, **kw)


def _obj(name: str, bm, coll: str = "SET", surface=None, tint=None, smooth: bool = False, bevel: float = 0.0, uv: bool = True):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = smooth
    ob = bpy.data.objects.new(name, me)
    core.link(ob, coll)
    m = _mat(surface, tint)
    if m:
        me.materials.append(m)
    if uv:
        mat.uv_box(ob)
    if bevel > 0:
        b = ob.modifiers.new("bevel", "BEVEL")
        b.width = bevel
        b.segments = 2
        b.limit_method = "ANGLE"
        b.harden_normals = True
    return ob


def _xyz(at):
    return Vector((at[0], at[1], at[2] if len(at) > 2 else 0.0))


def _cube(bm, size, matrix):
    r = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=r["verts"])
    bmesh.ops.transform(bm, matrix=matrix, verts=r["verts"])
    return r["verts"]


def _cylv(bm, r1, r2, h, matrix, seg=20, caps=True):
    r = bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r1, radius2=r2, depth=h)
    bmesh.ops.transform(bm, matrix=matrix @ Matrix.Translation((0, 0, h / 2)), verts=r["verts"])
    return r["verts"]


def _place(ob, at, rot_z=0.0):
    ob.location = _xyz(at)
    ob.rotation_euler.z = math.radians(rot_z)
    return ob


def group(name: str, parts, at=(0, 0, 0), rot_z: float = 0.0, coll: str = "SET"):
    """Parent several objects to one empty so they move and turn together. Returns the empty."""
    e = core.empty(name, (0, 0, 0), coll, 0.2)
    for p in parts:
        if p is not None and p.parent is None:
            p.parent = e
    return _place(e, at, rot_z)


def box(name, size=(1, 1, 1), at=(0, 0, 0), surface="castle_stone", tint=None, rot_z=0.0, bevel=0.015, coll="SET"):
    bm = bmesh.new()
    _cube(bm, Vector(size), Matrix.Translation((0, 0, size[2] / 2)))
    return _place(_obj(name, bm, coll, surface, tint, bevel=bevel), at, rot_z)


def cyl(name, radius=0.5, height=1.0, at=(0, 0, 0), surface="oak_planks", tint=None, top_radius=None, seg=24, coll="SET"):
    bm = bmesh.new()
    _cylv(bm, radius, radius if top_radius is None else top_radius, height, Matrix.Identity(4), seg)
    return _place(_obj(name, bm, coll, surface, tint, smooth=True, uv=True), at)


def ball(name, radius=0.5, at=(0, 0, 0), surface="rock_face", tint=None, squash=(1, 1, 1), subdiv=2, coll="SET"):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    bmesh.ops.scale(bm, vec=squash, verts=bm.verts)
    ob = _obj(name, bm, coll, surface, tint, smooth=True, uv=False)
    return _place(ob, (at[0], at[1], (at[2] if len(at) > 2 else 0.0) + radius * squash[2]))


def lump(ob, strength: float = 0.2, size: float = 1.0, seed: int = 0):
    """Break up a too-perfect shape (crowns of trees, rocks, mud) with a cloud displacement."""
    tex = bpy.data.textures.new(f"lump_{size}_{seed}", "CLOUDS")
    tex.noise_scale = size
    tex.noise_depth = 2
    d = ob.modifiers.new("lump", "DISPLACE")
    d.texture = tex
    d.strength = strength
    d.texture_coords = "GLOBAL" if seed == 0 else "LOCAL"
    return ob


# ----------------------------------------------------------------------------- ground
def ground(name="ground", size=60.0, surface="grass_lawn", tint=None, holes=(), relief=0.0, flat_radius=8.0, seed=1, coll="SET"):
    """The floor of an outdoor set. holes: outlines (lists of (x, y)) cut out for ponds, channels, pits, moats; they must
    lie inside the flat middle and must not touch each other. relief: height of gentle hills beyond flat_radius metres
    from the origin. The acting area (a square of side 2 x flat_radius) is dead level, so marks and patches sit true."""
    h = size / 2
    f = min(flat_radius, h) if relief else h
    bm = bmesh.new()
    ring = [bm.verts.new(c) for c in ((-f, -f, 0), (f, -f, 0), (f, f, 0), (-f, f, 0))]
    edges = [bm.edges.new((ring[i], ring[(i + 1) % 4])) for i in range(4)]
    for hole in holes:
        vs = [bm.verts.new((x, y, 0)) for x, y in hole]
        edges += [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.triangle_fill(bm, edges=edges, use_beauty=True)
    for face in bm.faces:
        if face.normal.z < 0:
            face.normal_flip()
    inner = _obj(name, bm, coll, surface, tint)
    if holes:                                                # dark earth far below, so no gap in a pit ever shows sky
        bm = bmesh.new()
        _cube(bm, Vector((2 * f, 2 * f, 0.1)), Matrix.Translation((0, 0, -6.0)))
        under = _obj(f"{name}.under", bm, coll, "#17120E", bevel=0)
        under.parent = inner
        under.visible_shadow = False
    if relief and h > f:
        rnd = random.Random(seed)
        ph = [rnd.uniform(0, 6.28) for _ in range(3)]
        cell = f / 4
        n = int(math.ceil(h / cell))
        bm = bmesh.new()
        grid = {}

        def vert(i, j):
            if (i, j) not in grid:
                x, y = i * cell, j * cell
                d = max(abs(x), abs(y))
                k = max(0.0, min(1.0, (d - f) / (f * 1.4)))
                z = relief * k * k * (0.6 * math.sin(x * 0.11 + ph[0]) + 0.5 * math.sin(y * 0.13 + ph[1]) + 0.4 * math.sin((x + y) * 0.07 + ph[2]) + 0.7)
                grid[(i, j)] = bm.verts.new((x, y, z))
            return grid[(i, j)]

        for i in range(-n, n):
            for j in range(-n, n):
                if -4 <= i < 4 and -4 <= j < 4:
                    continue
                bm.faces.new((vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)))
        outer = _obj(f"{name}.hills", bm, coll, surface, tint, smooth=True)
        outer.parent = inner
    return inner


def patch(name, outline, surface="cobblestone", tint=None, z=0.012, coll="SET"):
    """A flat area of another surface laid on the ground: a paved terrace, a path, a flower bed. outline: [(x, y), ...]."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z)) for x, y in outline]
    f = bm.faces.new(vs)
    if f.normal.z < 0:
        f.normal_flip()
    return _obj(name, bm, coll, surface, tint)


def rect(cx, cy, w, l):
    return [(cx - w / 2, cy - l / 2), (cx + w / 2, cy - l / 2), (cx + w / 2, cy + l / 2), (cx - w / 2, cy + l / 2)]


def rounded_rect(cx, cy, w, l, r=0.8, seg=7):
    r = min(r, w / 2 - 0.01, l / 2 - 0.01)
    pts = []
    for (qx, qy, a0) in ((cx + w / 2 - r, cy + l / 2 - r, 0), (cx - w / 2 + r, cy + l / 2 - r, 90), (cx - w / 2 + r, cy - l / 2 + r, 180), (cx + w / 2 - r, cy - l / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((qx + r * math.cos(a), qy + r * math.sin(a)))
    return pts


# ----------------------------------------------------------------------------- stone architecture
def stone_wall(name="wall", length=10.0, height=4.5, thickness=0.9, at=(0, 0, 0), rot_z=0.0, surface="castle_stone", tint=None,
               crenels=True, walk=False, gap=None, coll="SET"):
    """A masonry wall along local X, centred. crenels: battlements on top. gap=(centre, width, height): a doorway or arch."""
    bm = bmesh.new()
    if gap:
        gc, gw, gh = gap
        left = (gc - gw / 2) + length / 2
        right = length / 2 - (gc + gw / 2)
        _cube(bm, Vector((left, thickness, height)), Matrix.Translation((-length / 2 + left / 2, 0, height / 2)))
        _cube(bm, Vector((right, thickness, height)), Matrix.Translation((length / 2 - right / 2, 0, height / 2)))
        _cube(bm, Vector((gw, thickness, height - gh)), Matrix.Translation((gc, 0, gh + (height - gh) / 2)))
    else:
        _cube(bm, Vector((length, thickness, height)), Matrix.Translation((0, 0, height / 2)))
    _cube(bm, Vector((length + 0.1, thickness + 0.16, 0.22)), Matrix.Translation((0, 0, height + 0.11)))        # string course
    if crenels:
        n = max(2, int(length / 1.5))
        w = length / n
        for i in range(n):
            _cube(bm, Vector((w * 0.56, thickness * 0.5, 0.75)), Matrix.Translation((-length / 2 + w * (i + 0.5), -thickness * 0.33, height + 0.22 + 0.375)))
    _cube(bm, Vector((length + 0.3, thickness + 0.36, 0.38)), Matrix.Translation((0, 0, 0.19)))                 # plinth
    return _place(_obj(name, bm, coll, surface, tint, bevel=0.025), at, rot_z)


def tower(name="tower", radius=2.2, height=9.0, at=(0, 0, 0), surface="castle_stone", tint=None, crenels=True, roof=None,
          slits=3, coll="SET"):
    """A round tower. roof: None (open battlements) or a surface name for a cone roof ("roof_slate", "roof_clay_tile")."""
    bm = bmesh.new()
    seg = 28
    _cylv(bm, radius * 1.04, radius, height, Matrix.Identity(4), seg)
    _cylv(bm, radius * 1.14, radius * 1.14, 0.42, Matrix.Translation((0, 0, height)), seg)
    if crenels and not roof:
        n = 10
        for i in range(n):
            a = 2 * math.pi * i / n
            _cube(bm, Vector((0.62, 0.36, 0.8)), Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((0, -radius * 1.0, height + 0.42 + 0.4)))
    for v in bm.verts:
        v.co.z = v.co.z
    ob = _obj(name, bm, coll, surface, tint, smooth=False, bevel=0.02, uv=False)
    me = ob.data
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if abs(poly.normal.z) > 0.7:
                uv.data[li].uv = (co.x, co.y)
            else:
                uv.data[li].uv = (math.atan2(co.y, co.x) * radius, co.z)
    parts = [ob]
    dark = _mat("#141210")
    for i in range(slits):
        a = math.radians(-90 + (i - (slits - 1) / 2) * 38)
        s = box(f"{name}.slit{i}", (0.16, 0.2, 0.95), (0, 0, 0), dark, bevel=0, coll=coll)
        s.location = (radius * 1.01 * math.cos(a), radius * 1.01 * math.sin(a), height * (0.45 + 0.18 * (i % 2)))
        s.rotation_euler.z = a + math.pi / 2
        s.parent = ob
    if roof:
        r = cyl(f"{name}.roof", radius * 1.28, radius * 1.7, (0, 0, height + 0.42), roof, top_radius=0.02, seg=seg, coll=coll)
        r.parent = ob
        parts.append(r)
    _place(ob, at)
    return ob


def arch_door(name="door", width=1.5, height=2.5, at=(0, 0, 0), rot_z=0.0, wood="oak_planks", stone="castle_stone", open_deg=0.0, coll="SET"):
    """A plank door with iron bands in a round stone arch, set against a wall face (it faces -Y at rot_z=0).
    Returns {"root", "leaf"} : rotate leaf (hinged at its left edge) to open it."""
    root = core.empty(name, (0, 0, 0), coll, 0.3)
    bm = bmesh.new()
    seg = 9
    r = width / 2 + 0.18
    for i in range(seg):
        a = math.pi * (i + 0.5) / seg
        _cube(bm, Vector((0.42, 0.5, 0.36)), Matrix.Translation((r * math.cos(a), 0, height - width / 2 + r * math.sin(a))) @ Matrix.Rotation(a - math.pi / 2, 4, "Y"))
    for sx in (-1, 1):
        n = max(2, int((height - width / 2) / 0.42))
        for j in range(n):
            _cube(bm, Vector((0.38, 0.5, (height - width / 2) / n - 0.02)), Matrix.Translation((sx * r, 0, (j + 0.5) * (height - width / 2) / n)))
    arch = _obj(f"{name}.arch", bm, coll, stone, bevel=0.03)
    arch.parent = root
    bm = bmesh.new()
    pts = [(-width / 2, 0)] + [(width / 2 * math.cos(math.pi * i / 14), height - width / 2 + width / 2 * math.sin(math.pi * i / 14)) for i in range(15)][::-1]
    pts = [(-width / 2, 0), (width / 2, 0)] + [(width / 2 * math.cos(math.pi * i / 14), height - width / 2 + width / 2 * math.sin(math.pi * i / 14)) for i in range(15)]
    front = [bm.verts.new((x + width / 2, -0.05, z)) for x, z in pts]
    back = [bm.verts.new((x + width / 2, 0.05, z)) for x, z in pts]
    bm.faces.new(front)
    bm.faces.new(back[::-1])
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((front[i], back[i], back[j], front[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    leaf = _obj(f"{name}.leaf", bm, coll, wood)
    leaf.parent = root
    leaf.location = (-width / 2, 0.08, 0)
    leaf.rotation_euler.z = math.radians(open_deg)
    for k, z in enumerate((0.45, height - width / 2 - 0.1)):
        b = box(f"{name}.band{k}", (width * 0.92, 0.03, 0.11), (width / 2, -0.07, z), "iron_dark", bevel=0.005, coll=coll)
        b.parent = leaf
    ring = cyl(f"{name}.ring", 0.09, 0.03, (width * 0.82, -0.09, height * 0.42), "iron_dark", seg=14, coll=coll)
    ring.rotation_euler.x = math.radians(90)
    ring.parent = leaf
    dark = box(f"{name}.dark", (width, 0.3, height), (0, 0.25, 0), _mat("#0E0C0B"), bevel=0, coll=coll)
    dark.parent = root
    _place(root, at, rot_z)
    return {"root": root, "leaf": leaf}


def steps(name="steps", width=2.0, count=4, rise=0.18, run=0.34, at=(0, 0, 0), rot_z=0.0, surface="flagstone", coll="SET"):
    bm = bmesh.new()
    for i in range(count):
        _cube(bm, Vector((width, run * (count - i), rise)), Matrix.Translation((0, run * (count - i) / 2, rise * (i + 0.5))))
    return _place(_obj(name, bm, coll, surface, bevel=0.02), at, rot_z)


def banner(name="banner", at=(0, 0, 3.0), rot_z=0.0, size=(0.9, 2.2), color="#A3231F", trim="#EDC04A", emblem="lion", coll="SET"):
    """A hanging cloth banner with a swallow tail, a gold border and a simple emblem ("lion", "sun", "tree", "star" or None).
    `at` is the top centre. It hangs flat against a wall facing -Y."""
    w, h = size
    root = core.empty(name, (0, 0, 0), coll, 0.2)
    rod = cyl(f"{name}.rod", 0.035, w + 0.3, (0, 0, 0), "dark_timber", seg=10, coll=coll)
    rod.rotation_euler.y = math.radians(90)
    rod.location = (-(w + 0.3) / 2, -0.08, 0)
    rod.parent = root
    for nm, inset, col, y in (("trim", 0.0, trim, -0.07), ("cloth", 0.07, color, -0.085)):
        bm = bmesh.new()
        ww, hh = w / 2 - inset, h - inset
        pts = [(-ww, -inset), (ww, -inset), (ww, -hh), (0, -hh + w * 0.32), (-ww, -hh)]
        f = bm.faces.new([bm.verts.new((x, y, z)) for x, z in pts])
        o = _obj(f"{name}.{nm}", bm, coll, "cloth", col)
        o.parent = root
    if emblem:
        shapes = {"sun": [(0.26 * (1 if i % 2 else 0.6) * math.cos(i * math.pi / 8), 0.26 * (1 if i % 2 else 0.6) * math.sin(i * math.pi / 8)) for i in range(16)],
                  "star": [(0.28 * (1 if i % 2 == 0 else 0.42) * math.sin(i * math.pi / 5), 0.28 * (1 if i % 2 == 0 else 0.42) * math.cos(i * math.pi / 5)) for i in range(10)],
                  "tree": [(-0.05, -0.3), (0.05, -0.3), (0.05, -0.05), (0.24, -0.02), (0.18, 0.18), (0.0, 0.32), (-0.18, 0.18), (-0.24, -0.02), (-0.05, -0.05)],
                  "lion": [(-0.2, -0.28), (-0.08, -0.28), (-0.06, -0.08), (0.06, -0.08), (0.08, -0.28), (0.2, -0.28), (0.2, 0.06), (0.3, 0.2), (0.22, 0.32), (0.08, 0.3), (0.0, 0.2), (-0.14, 0.2), (-0.26, 0.3), (-0.3, 0.18), (-0.2, 0.08)]}
        bm = bmesh.new()
        f = bm.faces.new([bm.verts.new((x * w / 0.9, -0.095, z * w / 0.9 - h * 0.42)) for x, z in shapes.get(emblem, shapes["sun"])])
        o = _obj(f"{name}.emblem", bm, coll, "cloth", trim)
        o.parent = root
    for o in root.children:
        for p in o.data.polygons if o.type == "MESH" else []:
            pass
    _place(root, at, rot_z)
    return root


# ----------------------------------------------------------------------------- plants
def _tube(name, points, radii, surface="bark", coll="SET"):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 1.0
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for bp, p, r in zip(sp.bezier_points, points, radii):
        bp.co = p
        bp.radius = r
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new(name, cu)
    core.link(ob, coll)
    m = _mat(surface)
    if m:
        cu.materials.append(m)
    return ob


def tree(name="tree", at=(0, 0, 0), height=5.5, crown=2.4, lean=0.3, surface="leaves", tint=None, branch=None, seed=0, coll="SET"):
    """A broadleaf tree: a leaning trunk and a crown of lumpy leaf masses.
    branch=(dx, dy, z, length): one stout limb leaving the trunk at height z toward (dx, dy) - returned as T["branch"],
    a separate object pivoted at the trunk, so it can sag, crack and fall. Returns {"root", "trunk", "crown", "branch", "branch_tip"}."""
    rnd = random.Random(seed)
    root = core.empty(name, (0, 0, 0), coll, 0.4)
    th = height * 0.62
    pts = [(0, 0, -0.1), (lean * 0.15, 0, th * 0.35), (lean * 0.6, 0.05, th * 0.75), (lean, 0.0, th)]
    trunk = _tube(f"{name}.trunk", pts, [0.34, 0.27, 0.21, 0.15])
    trunk.parent = root
    blobs = []
    cx, cz = lean, th + crown * 0.35
    n = 15
    for i in range(n):
        if i < 7:                                    # the big masses
            a = 2 * math.pi * i / 7 + rnd.uniform(-0.2, 0.2)
            rr, r = crown * rnd.uniform(0.38, 0.6), crown * rnd.uniform(0.40, 0.56)
            zz = cz + rnd.uniform(-0.28, 0.22) * crown
        elif i < 13:                                 # smaller clumps breaking the outline
            a = rnd.uniform(0, 6.28)
            rr, r = crown * rnd.uniform(0.7, 0.95), crown * rnd.uniform(0.22, 0.32)
            zz = cz + rnd.uniform(-0.38, 0.45) * crown
        else:                                        # top
            a = rnd.uniform(0, 6.28)
            rr, r = crown * 0.15, crown * 0.52
            zz = cz + crown * (0.42 if i == 13 else 0.1)
        b = ball(f"{name}.leaf{i}", r, (cx + rr * math.cos(a), rr * math.sin(a) * 0.9, zz - r), surface, tint, squash=(1, 1, 0.8), subdiv=3, coll=coll)
        lump(b, 0.5 * r, 0.3, seed=1)
        b.parent = root
        blobs.append(b)
    out = {"root": root, "trunk": trunk, "crown": blobs, "branch": None, "branch_tip": None}
    if branch:
        dx, dy, bz, bl = branch
        d = Vector((dx, dy, 0)).normalized()
        base = Vector((lean * min(1.0, bz / th) * 0.7, 0, bz))
        pivot = core.empty(f"{name}.branch", base, coll, 0.15)
        pivot.parent = root
        bp = [(0, 0, 0), tuple(d * bl * 0.4 + Vector((0, 0, bl * 0.10))), tuple(d * bl * 0.8 + Vector((0, 0, bl * 0.13))), tuple(d * bl + Vector((0, 0, bl * 0.10)))]
        limb = _tube(f"{name}.branch.wood", bp, [0.17, 0.14, 0.11, 0.07])
        limb.parent = pivot
        tip = core.empty(f"{name}.branch.tip", bp[-1], coll, 0.08)
        tip.parent = pivot
        grip = core.empty(f"{name}.branch.grip", tuple(d * bl * 0.78 + Vector((0, 0, bl * 0.125 - 0.11))), coll, 0.08)
        grip.parent = pivot
        # leaves only past the tip and back at the trunk: the middle of the limb stays bare, so hands on it can be seen
        tuft = ball(f"{name}.branch.leaves", crown * 0.19, (0, 0, 0), surface, tint, squash=(1.25, 1, 0.75), subdiv=3, coll=coll)
        lump(tuft, 0.08, 0.5, seed=1)
        tuft.parent = pivot
        tuft.location = Vector(d * bl * 1.1) + Vector((0, 0, bl * 0.10 + 0.22))
        twig = ball(f"{name}.branch.leaves2", crown * 0.13, (0, 0, 0), surface, tint, squash=(1.2, 1, 0.8), subdiv=3, coll=coll)
        lump(twig, 0.07, 0.5, seed=2)
        twig.parent = pivot
        twig.location = Vector(d * bl * 0.3) + Vector((0, 0.15, bl * 0.08 + 0.3))
        out.update(branch=pivot, branch_tip=tip, branch_grip=grip, branch_wood=limb)
    _place(root, at)
    return out


def bush(name="bush", at=(0, 0, 0), size=0.9, surface="leaves", tint=None, flowers=None, seed=0, coll="SET"):
    """A rounded shrub. flowers="#hex" dots it with blossoms."""
    rnd = random.Random(seed)
    root = core.empty(name, (0, 0, 0), coll, 0.2)
    for i in range(4):
        r = size * rnd.uniform(0.38, 0.55)
        b = ball(f"{name}.{i}", r, (rnd.uniform(-0.35, 0.35) * size, rnd.uniform(-0.3, 0.3) * size, rnd.uniform(-0.1, 0.12) * size), surface, tint, squash=(1, 1, 0.85), subdiv=3, coll=coll)
        lump(b, 0.3 * r, 0.4, seed=1)
        b.parent = root
    if flowers:
        m = _mat(flowers)
        bm = bmesh.new()
        for i in range(int(14 * size) + 4):
            a, e = rnd.uniform(0, 6.28), rnd.uniform(0.25, 1.35)
            p = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * size * 0.62
            r = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.055)
            bmesh.ops.translate(bm, vec=p + Vector((0, 0, size * 0.2)), verts=r["verts"])
        f = _obj(f"{name}.flowers", bm, coll, m, smooth=True, uv=False)
        f.parent = root
    return _place(root, at)


def flowers(name="flowers", area=(-1, 1, -1, 1), count=18, colors=("#F6F1E4", "#F2C94C", "#D9534F"), height=0.32, seed=0, avoid=(), coll="SET"):
    """Small flowers on stems scattered in a rectangle (x0, x1, y0, y1): edges of paths, the foot of a wall."""
    rnd = random.Random(seed)
    stems = bmesh.new()
    heads = {c: bmesh.new() for c in colors}
    for _ in range(count):
        x, y = rnd.uniform(area[0], area[1]), rnd.uniform(area[2], area[3])
        if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid):
            continue
        h = height * rnd.uniform(0.6, 1.2)
        _cylv(stems, 0.008, 0.006, h, Matrix.Translation((x, y, 0)), 5, caps=False)
        c = rnd.choice(colors)
        r = bmesh.ops.create_icosphere(heads[c], subdivisions=1, radius=rnd.uniform(0.04, 0.065))
        bmesh.ops.scale(heads[c], vec=(1, 1, 0.55), verts=r["verts"])
        bmesh.ops.translate(heads[c], vec=(x, y, h), verts=r["verts"])
    root = _obj(f"{name}.stems", stems, coll, _mat("#4E7A36"), uv=False)
    for c, bm in heads.items():
        o = _obj(f"{name}.{c}", bm, coll, _mat(c), smooth=True, uv=False)
        o.parent = root
    return root


def grass_tufts(name="tufts", area=(-6, 6, -6, 6), count=220, height=0.22, tint="#5E8F3C", seed=0, avoid=(), inside=None, coll="SET"):
    """Blades of longer grass in clumps: break the flat lawn at wall feet, tree roots, pond edges. avoid=[(x, y, r)] keeps
    walking marks clear; inside=outline keeps tufts out of a polygon (the pond)."""
    rnd = random.Random(seed)
    bm = bmesh.new()
    placed = 0
    for _ in range(count * 3):
        if placed >= count:
            break
        x, y = rnd.uniform(area[0], area[1]), rnd.uniform(area[2], area[3])
        if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid):
            continue
        if inside and _in_poly((x, y), inside):
            continue
        placed += 1
        for _b in range(rnd.randint(4, 7)):
            a = rnd.uniform(0, 6.28)
            h = height * rnd.uniform(0.5, 1.3)
            lean = rnd.uniform(0.02, 0.1)
            w = rnd.uniform(0.012, 0.022)
            bx, by = x + rnd.uniform(-0.06, 0.06), y + rnd.uniform(-0.06, 0.06)
            c, s = math.cos(a), math.sin(a)
            v = [bm.verts.new((bx - s * w, by + c * w, 0)), bm.verts.new((bx + s * w, by - c * w, 0)), bm.verts.new((bx + c * lean, by + s * lean, h))]
            bm.faces.new(v)
    return _obj(name, bm, coll, _mat(tint), uv=False)


def _in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
            inside = not inside
    return inside


def ivy(name="ivy", at=(0, 0, 0), rot_z=0.0, width=2.5, height=3.0, density=140, tint="#3F7A35", seed=0, coll="SET"):
    """Ivy climbing a wall face (a vertical sheet of leaves hugging the wall, thicker at the bottom). The wall faces -Y at rot_z=0."""
    rnd = random.Random(seed)
    bm = bmesh.new()
    for _ in range(density):
        u = rnd.gauss(0, 0.33)
        v = abs(rnd.gauss(0, 0.42))
        if abs(u) > 1 or v > 1:
            continue
        x, z = u * width / 2 * (1 - 0.45 * v), v * height
        s = rnd.uniform(0.09, 0.17)
        a = rnd.uniform(0, 6.28)
        pts = [(0, 0.5), (0.35, 0.2), (0.5, -0.1), (0.2, -0.5), (0, -0.3), (-0.2, -0.5), (-0.5, -0.1), (-0.35, 0.2)]
        y = -rnd.uniform(0.02, 0.07)
        vs = [bm.verts.new((x + s * (px * math.cos(a) - pz * math.sin(a)), y, z + s * (px * math.sin(a) + pz * math.cos(a)))) for px, pz in pts]
        f = bm.faces.new(vs)
        if f.normal.y > 0:
            f.normal_flip()
    return _place(_obj(name, bm, coll, "leaves", tint, uv=False), at, rot_z)


def reeds(name="reeds", at=(0, 0, 0), count=14, height=1.1, spread=0.5, seed=0, coll="SET"):
    """Reeds and cattails at a water's edge."""
    rnd = random.Random(seed)
    bm, heads = bmesh.new(), bmesh.new()
    for i in range(count):
        x, y = rnd.gauss(0, spread), rnd.gauss(0, spread * 0.5)
        h = height * rnd.uniform(0.6, 1.15)
        tilt = Matrix.Rotation(rnd.uniform(-0.14, 0.14), 4, "X") @ Matrix.Rotation(rnd.uniform(-0.14, 0.14), 4, "Y")
        _cylv(bm, 0.012, 0.006, h, Matrix.Translation((x, y, -0.3)) @ tilt, 5, caps=False)
        if i % 3 == 0:
            _cylv(heads, 0.028, 0.028, 0.16, Matrix.Translation((x, y, -0.3)) @ tilt @ Matrix.Translation((0, 0, h - 0.2)), 8)
    o = _obj(name, bm, coll, _mat("#6F8F45"), uv=False)
    hd = _obj(f"{name}.heads", heads, coll, _mat("#5A3A22"), smooth=True, uv=False)
    hd.parent = o
    return _place(o, at)


def rock(name="rock", at=(0, 0, 0), size=0.6, surface="rock_face", tint=None, seed=0, coll="SET"):
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=size / 2)
    for v in bm.verts:
        v.co *= rnd.uniform(0.78, 1.15)
        v.co.z *= 0.62
    ob = _obj(name, bm, coll, surface, tint, smooth=False, bevel=0.0, uv=False)
    ob.rotation_euler.z = rnd.uniform(0, 6.28)
    return _place(ob, (at[0], at[1], (at[2] if len(at) > 2 else 0) + size * 0.14))


def scatter(maker, count, area=(-10, 10, -10, 10), seed=1, avoid=(), min_gap=0.0, **kw):
    """Place `count` things made by `maker(name=, at=, seed=, **kw)` at random spots in a rectangle, away from avoid=[(x, y, r)]."""
    rnd = random.Random(seed)
    made, pts, tries = [], [], 0
    while len(made) < count and tries < count * 40:
        tries += 1
        x, y = rnd.uniform(area[0], area[1]), rnd.uniform(area[2], area[3])
        if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid) or any(math.hypot(x - px, y - py) < min_gap for px, py in pts):
            continue
        pts.append((x, y))
        made.append(maker(name=f"{maker.__name__}{len(made)}_{seed}", at=(x, y, 0), seed=seed * 131 + len(made), **kw))
    return made


# ----------------------------------------------------------------------------- water
def pond(name="pond", at=(0, 0), size=(5.0, 7.0), depth=1.2, rim="fieldstone", water="pond_water", floor="pond_mud", wall="fieldstone",
         corner=1.4, sluice=None, sluice_width=1.0, channel=4.2, level=-0.12, lilies=6, seed=0, coll="SET"):
    """A stone-edged pond sunk into the ground, deep enough to hide what falls in.
    sluice: None, or the side with a wooden sluice gate and outflow channel: "north" (+Y, the far end from the camera),
    "south", "east", "west". Lifting the gate (P["gate"]) lets the water out through the channel beyond it.

    Returns a dict: holes (pass to ground(holes=P["holes"])), outline, water, floor, surface_z, floor_z, centre, size, and with a sluice:
    gate (the sliding board), gate_grab {"left", "right", "mid"} (points on the lifting bar for hands), gate_stand {"left",
    "right"} (where to stand on the stone cheeks), channel, and two actions:
      open_gate(t0, t1)   the board slides up by gate_lift metres (key a character's reach to gate_grab over the same times)
      drain(t0, t1)       the emptying: water bursts under the board and runs down the channel, the level falls to the mud,
                          lilies settle on the bottom."""
    rnd = random.Random(seed)
    cx, cy = at[0], at[1]
    w, l = size
    outline = rounded_rect(cx, cy, w, l, corner)
    root = core.empty(name, (0, 0, 0), coll, 0.3)
    side = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}.get(sluice) if sluice else None
    gate_pos = Vector((cx + (side[0] * w / 2 if side else 0), cy + (side[1] * l / 2 if side else 0), 0)) if side else None
    # basin walls + floor
    bm = bmesh.new()
    top = [bm.verts.new((x, y, 0.0)) for x, y in outline]
    bot = [bm.verts.new((cx + (x - cx) * 0.94, cy + (y - cy) * 0.94, -depth)) for x, y in outline]
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((top[j], top[i], bot[i], bot[j]))
    walls = _obj(f"{name}.walls", bm, coll, wall)
    walls.parent = root
    bm = bmesh.new()
    ring = [bm.verts.new((cx + (x - cx) * 0.94, cy + (y - cy) * 0.94, -depth)) for x, y in outline]
    c = bm.verts.new((cx, cy, -depth - 0.05))
    for i in range(n):
        bm.faces.new((ring[i], ring[(i + 1) % n], c))
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=2, use_grid_fill=True)
    for v in bm.verts:
        v.co.z += rnd.uniform(-0.04, 0.05)
    fl = _obj(f"{name}.floor", bm, coll, floor, smooth=True)
    fl.parent = root
    # water sheet
    bm = bmesh.new()
    vs = [bm.verts.new((x - cx, y - cy, 0.0)) for x, y in [(cx + (px - cx) * 0.995, cy + (py - cy) * 0.995) for px, py in outline]]
    f = bm.faces.new(vs)
    if f.normal.z < 0:
        f.normal_flip()
    wat = _obj(f"{name}.water", bm, coll, water, uv=False)
    wat.location = (cx, cy, level)
    wat.parent = root
    # rim stones: irregular blocks along the edge, skipping the sluice mouth
    bm = bmesh.new()
    per = [Vector((x, y, 0)) for x, y in outline]
    acc = 0.0
    i = 0
    seg_len = [(per[(k + 1) % n] - per[k]).length for k in range(n)]
    total = sum(seg_len)
    s = 0.0
    while s < total:
        ln = rnd.uniform(0.42, 0.74)
        mid = s + ln / 2
        t, k = mid, 0
        while t > seg_len[k]:
            t -= seg_len[k]
            k = (k + 1) % n
        a, b = per[k], per[(k + 1) % n]
        p = a.lerp(b, t / seg_len[k])
        d = (b - a).normalized()
        if not (gate_pos is not None and (p - gate_pos).length < sluice_width / 2 + 0.28):
            ang = math.atan2(d.y, d.x) + rnd.uniform(-0.06, 0.06)
            ww = rnd.uniform(0.46, 0.6)
            hh = rnd.uniform(0.2, 0.3)
            out = Vector((d.y, -d.x, 0))
            if (p - Vector((cx, cy, 0))).dot(out) < 0:
                out = -out
            _cube(bm, Vector((ln - 0.035, ww, hh)), Matrix.Translation(p + out * (ww / 2 - 0.12) + Vector((0, 0, hh / 2 - 0.05))) @ Matrix.Rotation(ang, 4, "Z"))
        s += ln
    rimo = _obj(f"{name}.rim", bm, coll, rim, bevel=0.035)
    rimo.parent = root
    pads = []
    for i in range(lilies):
        px, py = cx + rnd.uniform(-0.36, 0.36) * w, cy + rnd.uniform(-0.38, 0.38) * l
        pad = _lily(f"{name}.lily{i}", rnd.uniform(0.16, 0.26), flower=(i % 3 == 0), coll=coll)
        pad.location = (px, py, level + 0.012)
        pad.rotation_euler.z = rnd.uniform(0, 6.28)
        pad.parent = root
        pads.append(pad)
    out = {"root": root, "outline": outline, "holes": [outline], "water": wat, "floor": fl, "rim": rimo, "walls": walls, "lilies": pads, "surface_z": level,
           "floor_z": -depth, "centre": (cx, cy), "size": size, "gate": None}
    if side:
        out.update(_sluice(name, gate_pos, side, sluice_width, depth, level, coll, root, channel))
        ax, ay = side                                             # the channel needs its own cut in the ground beyond the gate
        hw = sluice_width / 2 + 0.16
        y0, y1 = 0.74, 0.74 + channel
        loc = [(-hw, y0), (hw, y0), (hw, y1), (-hw, y1)]
        out["holes"] = [outline, [(gate_pos.x + lx * ay + ly * ax, gate_pos.y - lx * ax + ly * ay) for lx, ly in loc]]

        def open_gate(t0: float, t1: float, amount: float | None = None):
            shot = core.current()
            g = out["gate"]
            g.keyframe_insert("location", index=2, frame=shot.f(t0))
            g.location.z += out["gate_lift"] if amount is None else amount
            g.keyframe_insert("location", index=2, frame=shot.f(t1))
            core.ease(g, "location", "BACK", 2)
            return t1

        out["open_gate"] = open_gate

        def drain(t0: float, t1: float, keep: float = 0.0):
            """Empty the pond between two times. keep: metres of water left over the mud (0 = dry)."""
            shot = core.current()
            f0, f1 = shot.f(t0), shot.f(t1)
            end_z = -depth + 0.02 + keep
            wat.keyframe_insert("location", index=2, frame=f0)
            wat.keyframe_insert("scale", frame=f0)
            wat.location.z = end_z
            wat.scale = (0.94, 0.94, 1.0)
            wat.keyframe_insert("location", index=2, frame=f1)
            wat.keyframe_insert("scale", frame=f1)
            core.ease(wat, "location", "SINE", 2)
            if keep <= 0:
                core.show(wat, (f1 + 1) / shot.fps, False)
            for pad in pads:
                pad.keyframe_insert("location", index=2, frame=f0)
                pad.location.z = -depth + 0.04
                pad.keyframe_insert("location", index=2, frame=f1)
            fm = out["foam"]
            core.show(fm, t0, True)
            for i in range(int((t1 - t0) * 8) + 1):
                fm.scale = (1.0, 1.0 + 0.25 * (i % 2), 1.0 + 0.3 * ((i + 1) % 2))
                fm.keyframe_insert("scale", frame=shot.f(t0 + i / 8))
            core.show(fm, t1 + 0.3, False)
            st = out["stream"]
            core.show(st, t0, True)
            st.scale = (1, 0.02, 1)
            st.keyframe_insert("scale", frame=f0)
            st.scale = (1, 1, 1)
            st.keyframe_insert("scale", frame=min(f1, f0 + int(0.5 * shot.fps)))
            st.keyframe_insert("scale", frame=max(f0 + 1, f1 - int(0.3 * shot.fps)))
            st.scale = (0.25, 1, 0.2)
            st.keyframe_insert("scale", frame=f1 + int(0.6 * shot.fps))
            return t1

        out["drain"] = drain
    return out


def _lily(name, r, flower=False, coll="SET"):
    bm = bmesh.new()
    seg = 14
    vs = [bm.verts.new((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), 0)) for i in range(1, seg)]
    vs.append(bm.verts.new((0, 0, 0)))
    bm.faces.new(vs)
    ob = _obj(name, bm, coll, _mat("#5E9A4A"), uv=False)
    if flower:
        fb = bmesh.new()
        for i in range(6):
            a = math.pi * i / 3
            v = [fb.verts.new((0, 0, 0.01)), fb.verts.new((0.07 * math.cos(a - 0.4), 0.07 * math.sin(a - 0.4), 0.04)),
                 fb.verts.new((0.11 * math.cos(a), 0.11 * math.sin(a), 0.07)), fb.verts.new((0.07 * math.cos(a + 0.4), 0.07 * math.sin(a + 0.4), 0.04))]
            fb.faces.new(v)
        fl = _obj(f"{name}.flower", fb, coll, _mat("#F7EFE6"), uv=False)
        fl.parent = ob
    return ob


def _sluice(name, pos, side, width, depth, level, coll, root, channel=4.2, lift=0.46):
    """A wooden gate board sliding between two low stone cheeks under a timber frame, with a lifting bar at chest height,
    and a stone channel beyond it for the water to leave by. The cheeks are flat-topped: stand a character on one to work the bar."""
    ang = math.atan2(side[1], side[0]) - math.pi / 2            # local +Y points out of the pond
    base = core.empty(f"{name}.sluice", pos, coll, 0.2)
    base.rotation_euler.z = ang
    base.parent = root
    gh = depth + 0.42                                            # the board reaches from the mud to above the water
    top = 0.30                                                   # cheek tops: a step up from the lawn
    cheeks = bmesh.new()
    for sx in (-1, 1):
        _cube(cheeks, Vector((0.9, 1.15, depth + top)), Matrix.Translation((sx * (width / 2 + 0.45), 0.12, (top - depth) / 2)))
    ck = _obj(f"{name}.sluice.cheeks", cheeks, coll, "fieldstone", bevel=0.03)
    ck.parent = base
    frame = bmesh.new()
    for sx in (-1, 1):
        _cube(frame, Vector((0.17, 0.17, 2.3)), Matrix.Translation((sx * (width / 2 + 0.8), 0.3, top + 1.15)))
    _cube(frame, Vector((width + 2.1, 0.2, 0.2)), Matrix.Translation((0, 0.3, top + 2.3 + 0.1)))
    fr = _obj(f"{name}.sluice.frame", frame, coll, "dark_timber", bevel=0.012)
    fr.parent = base
    gb = bmesh.new()
    _cube(gb, Vector((width - 0.04, 0.09, gh)), Matrix.Translation((0, 0, gh / 2)))
    gate = _obj(f"{name}.sluice.gate", gb, coll, "oak_planks", bevel=0.01)
    gate.parent = base
    gate.location = (0, 0.16, -depth)
    for k, z in enumerate((0.18, gh - 0.2)):
        b = box(f"{name}.sluice.band{k}", (width - 0.02, 0.12, 0.09), (0, 0, z), "iron_dark", bevel=0.006, coll=coll)
        b.parent = gate
    for k, sx in enumerate((-1, 1)):                                # two short rods up to one wide lifting bar
        rod = box(f"{name}.sluice.rod{k}", (0.05, 0.05, 0.68), (sx * width * 0.3, 0, gh), "iron_dark", bevel=0.006, coll=coll)
        rod.parent = gate
    bar = box(f"{name}.sluice.handle", (width + 0.8, 0.1, 0.1), (0, 0.0, gh + 0.63), "oak_planks", bevel=0.03, coll=coll)   # waist height from a cheek; chest height once lifted
    bar.parent = gate
    grabs = {}
    for nm, sx in (("left", -1), ("right", 1), ("mid", 0)):
        e = core.empty(f"{name}.sluice.grab.{nm}", (sx * (width / 2 + 0.3), -0.02, gh + 0.68), coll, 0.06)
        e.parent = gate
        grabs[nm] = e
    stands = {}
    for nm, sx in (("left", -1), ("right", 1)):
        e = core.empty(f"{name}.sluice.stand.{nm}", (sx * (width / 2 + 0.62), -0.2, top), coll, 0.06)       # an arm's length from the bar end
        e.parent = base
        stands[nm] = e
    # channel beyond the gate: stone-lined trough running away and slightly down
    ch = bmesh.new()
    cl = channel
    _cube(ch, Vector((width + 0.9, cl, 0.2)), Matrix.Translation((0, 0.75 + cl / 2, -depth * 0.55 - 0.1)) @ Matrix.Rotation(math.radians(-4), 4, "X"))
    for sx in (-1, 1):
        _cube(ch, Vector((0.3, cl, depth * 0.55 + 0.16)), Matrix.Translation((sx * (width / 2 + 0.3), 0.75 + cl / 2, -(depth * 0.55) / 2 + 0.0)))
    # the far end is closed by a stone head wall with a dark culvert mouth: the water has somewhere to go, and no
    # camera ever looks out under the lawn
    _cube(ch, Vector((width + 0.9, 0.35, depth * 0.55 + 0.36)), Matrix.Translation((0, 0.75 + cl + 0.1, -(depth * 0.55 + 0.36) / 2 + 0.08)))
    chan = _obj(f"{name}.sluice.channel", ch, coll, "fieldstone", bevel=0.03)
    chan.parent = base
    cv = bmesh.new()
    _cube(cv, Vector((width * 0.72, 0.06, depth * 0.36)), Matrix.Translation((0, 0.75 + cl - 0.1, -depth * 0.55 - 0.16 + depth * 0.18)))
    culvert = _obj(f"{name}.sluice.culvert", cv, coll, "#0B0A09", bevel=0)
    culvert.parent = base
    sb = bmesh.new()
    vs = [(-width / 2 + 0.03, 0.2, 0.0), (width / 2 - 0.03, 0.2, 0.0), (width / 2 - 0.03, cl + 0.7, -0.36), (-width / 2 + 0.03, cl + 0.7, -0.36)]
    f = sb.faces.new([sb.verts.new(v) for v in vs])
    if f.normal.z < 0:
        f.normal_flip()
    bmesh.ops.subdivide_edges(sb, edges=sb.edges[:], cuts=6, use_grid_fill=True)
    stream = _obj(f"{name}.sluice.stream", sb, coll, "clear_water", uv=False)
    stream.parent = base
    stream.location = (0, 0.0, -depth * 0.55 + 0.14)
    stream.hide_render = stream.hide_viewport = True
    # white water where it bursts under the board
    fb = bmesh.new()
    for i in range(7):
        r = bmesh.ops.create_icosphere(fb, subdivisions=2, radius=0.16 + 0.05 * (i % 3))
        bmesh.ops.translate(fb, vec=((i - 3) * width / 7.5, 0.42 + 0.12 * (i % 2), -depth * 0.55 + 0.2 + 0.05 * (i % 3)), verts=r["verts"])
    foam = _obj(f"{name}.sluice.foam", fb, coll, mat.emit("#EAF6F4", 1.0, "SK_foam"), smooth=True, uv=False)
    foam.parent = base
    foam.hide_render = foam.hide_viewport = True
    foam.visible_shadow = False
    return {"gate": gate, "gate_grab": grabs, "gate_stand": stands, "gate_height": gh, "gate_lift": lift, "sluice": base, "channel": chan, "stream": stream,
            "foam": foam, "gate_pos": tuple(pos)}


# ----------------------------------------------------------------------------- props
def barrel(name="barrel", at=(0, 0, 0), height=0.95, radius=0.34, seed=0, coll="SET"):
    bm = bmesh.new()
    seg, rings = 18, 6
    for j in range(rings + 1):
        z = height * j / rings
        r = radius * (0.82 + 0.18 * math.sin(math.pi * j / rings))
        for i in range(seg):
            bm.verts.new((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z))
    bm.verts.ensure_lookup_table()
    for j in range(rings):
        for i in range(seg):
            a, b = j * seg + i, j * seg + (i + 1) % seg
            bm.faces.new((bm.verts[a], bm.verts[b], bm.verts[b + seg], bm.verts[a + seg]))
    bm.faces.new([bm.verts[rings * seg + i] for i in range(seg)])
    bm.faces.new([bm.verts[i] for i in range(seg)][::-1])
    ob = _obj(name, bm, coll, "oak_planks", smooth=True, uv=False)
    for z in (0.14, 0.86):
        hp = cyl(f"{name}.hoop{z}", radius * (0.82 + 0.18 * math.sin(math.pi * z)) + 0.012, 0.05, (0, 0, height * z - 0.025), "iron_dark", seg=seg, coll=coll)
        hp.parent = ob
    ob.rotation_euler.z = seed * 1.3
    return _place(ob, at)


def crate(name="crate", at=(0, 0, 0), size=0.6, rot_z=0.0, seed=0, coll="SET"):
    bm = bmesh.new()
    _cube(bm, Vector((size, size, size)), Matrix.Translation((0, 0, size / 2)))
    ob = _obj(name, bm, coll, "oak_planks", bevel=0.012)
    for i, (dx, dy, sx, sy) in enumerate(((0, -1, 1, 0.06), (0, 1, 1, 0.06), (-1, 0, 0.06, 1), (1, 0, 0.06, 1))):
        for zz in (0.08, size - 0.08):
            b = box(f"{name}.b{i}{zz}", (size * sx + 0.02, size * sy + 0.02, 0.09), (dx * size / 2, dy * size / 2, zz - 0.045), "dark_timber", bevel=0.006, coll=coll)
            b.parent = ob
    return _place(ob, at, rot_z + seed * 17)


def bucket(name="bucket", at=(0, 0, 0), seed=0, coll="SET"):
    ob = cyl(name, 0.15, 0.28, (0, 0, 0), "oak_planks", top_radius=0.19, seg=14, coll=coll)
    hp = cyl(f"{name}.hoop", 0.18, 0.03, (0, 0, 0.2), "iron_dark", seg=14, coll=coll)
    hp.parent = ob
    return _place(ob, at)


def sack(name="sack", at=(0, 0, 0), seed=0, coll="SET"):
    ob = ball(name, 0.3, (0, 0, 0), "cloth", "#B49A6C", squash=(1, 0.8, 1.15), subdiv=2, coll=coll)
    lump(ob, 0.05, 0.3, seed=1)
    return _place(ob, (at[0], at[1], (at[2] if len(at) > 2 else 0) + 0.3))


def bench(name="bench", at=(0, 0, 0), rot_z=0.0, length=1.5, surface="oak_planks", coll="SET"):
    bm = bmesh.new()
    _cube(bm, Vector((length, 0.36, 0.07)), Matrix.Translation((0, 0, 0.45)))
    for sx in (-1, 1):
        _cube(bm, Vector((0.08, 0.32, 0.42)), Matrix.Translation((sx * (length / 2 - 0.16), 0, 0.21)))
    return _place(_obj(name, bm, coll, surface, bevel=0.012), at, rot_z)


def torch(name="torch", at=(0, 0, 2.0), rot_z=0.0, lit=True, power=60.0, coll="SET"):
    """A wall torch (iron bracket, wooden shaft, flame that is also a small warm light)."""
    root = core.empty(name, (0, 0, 0), coll, 0.1)
    sh = cyl(f"{name}.shaft", 0.03, 0.5, (0, -0.16, 0), "dark_timber", seg=8, coll=coll)
    sh.rotation_euler.x = math.radians(-18)
    sh.parent = root
    br = box(f"{name}.bracket", (0.05, 0.2, 0.05), (0, -0.1, 0.12), "iron_dark", bevel=0.004, coll=coll)
    br.parent = root
    if lit:
        fl = ball(f"{name}.flame", 0.09, (0, -0.31, 0.44), mat.emit("#FFB347", 9.0), squash=(0.8, 0.8, 1.6), subdiv=2, coll="FX")
        fl.parent = root
        ld = bpy.data.lights.new(f"{name}.light", "POINT")
        ld.energy = power
        ld.color = core.hex_rgba("#FFB067")[:3]
        ld.shadow_soft_size = 0.12
        lo = bpy.data.objects.new(f"{name}.light", ld)
        core.link(lo, "LIGHTS")
        lo.parent = root
        lo.location = (0, -0.4, 0.55)
    return _place(root, at, rot_z)


def ring(name="ring", at=(0, 0, 0), radius=0.07, coll="PROPS"):
    """A gold ring, drawn large enough to read on a phone (real rings are too small to see)."""
    bm = bmesh.new()
    r = bmesh.ops.create_cone(bm, cap_ends=False, segments=24, radius1=radius, radius2=radius, depth=radius * 0.5)
    ob = _obj(name, bm, coll, "gold", smooth=True, uv=False)
    s = ob.modifiers.new("thick", "SOLIDIFY")
    s.thickness = radius * 0.3
    s.offset = 0
    gem = ball(f"{name}.glint", radius * 0.2, (0, 0, 0), mat.emit("#FFF3C4", 3.0), subdiv=1, coll=coll)
    gem.parent = ob
    gem.location = (radius, 0, 0)
    ob.rotation_euler.x = math.radians(90)
    return _place(ob, at)


def pole_net(name="net", at=(0, 0, 0), pole=2.6, hoop=0.32, coll="PROPS"):
    """A long-handled landing net with a coarse mesh: the hoop is at local +X end. Returns the root (pivot at the grip)."""
    root = core.empty(name, (0, 0, 0), coll, 0.1)
    p = cyl(f"{name}.pole", 0.022, pole, (0, 0, 0), "dark_timber", seg=8, coll=coll)
    p.rotation_euler.y = math.radians(90)
    p.location = (-0.5, 0, 0)
    p.parent = root
    bm = bmesh.new()
    seg = 14
    cxn = pole - 0.5 + hoop
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        p0 = Vector((cxn + hoop * math.cos(a0), hoop * math.sin(a0), 0))
        p1 = Vector((cxn + hoop * math.cos(a1), hoop * math.sin(a1), 0))
        d = (p1 - p0)
        _cylv(bm, 0.014, 0.014, d.length, Matrix.Translation(p0) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4(), 6, caps=False)
    hp = _obj(f"{name}.hoop", bm, coll, "dark_timber", smooth=True, uv=False)
    hp.parent = root
    bm = bmesh.new()
    rings, depth, nseg = 3, hoop * 1.25, 8                  # a coarse mesh: holes about 0.2 m, plainly bigger than a ring
    for j in range(rings + 1):
        rr = hoop * math.cos(math.pi / 2 * j / rings * 0.9)
        zz = -depth * math.sin(math.pi / 2 * j / rings)
        for i in range(nseg):
            bm.verts.new((cxn + rr * math.cos(2 * math.pi * i / nseg), rr * math.sin(2 * math.pi * i / nseg), zz))
    bm.verts.ensure_lookup_table()
    for j in range(rings):
        for i in range(nseg):
            a, b = j * nseg + i, j * nseg + (i + 1) % nseg
            bm.faces.new((bm.verts[a], bm.verts[b], bm.verts[b + nseg], bm.verts[a + nseg]))    # the wireframe modifier turns these into cords
    me = bpy.data.meshes.new(f"{name}.mesh")
    bm.to_mesh(me)
    bm.free()
    net = bpy.data.objects.new(f"{name}.mesh", me)
    core.link(net, coll)
    w = net.modifiers.new("wire", "WIREFRAME")
    w.thickness = 0.02
    w.use_boundary = True
    w.use_replace = True
    me.materials.append(_mat("rope"))
    net.parent = root
    grip = core.empty(f"{name}.grip", (0, 0, 0), coll, 0.05)
    grip.parent = root
    hoop_c = core.empty(f"{name}.hoop_centre", (cxn, 0, -depth * 0.6), coll, 0.05)
    hoop_c.parent = root
    _place(root, at)
    root["hoop_x"] = cxn
    return {"root": root, "hoop": hoop_c, "mesh": net}


def halberd(name="halberd", at=(0, 0, 0), length=2.3, coll="PROPS"):
    """A guard's pole weapon, held upright. Pivot at the grip, about 1 m from the butt."""
    root = core.empty(name, (0, 0, 0), coll, 0.1)
    p = cyl(f"{name}.shaft", 0.022, length, (0, 0, -1.0), "dark_timber", seg=8, coll=coll)
    p.parent = root
    bm = bmesh.new()
    z0 = length - 1.0
    pts = [(0, 0), (0.035, 0.0), (0.035, 0.2), (0.0, 0.42), (-0.035, 0.2), (-0.035, 0.0)]
    blade = [(0.03, -0.02), (0.26, -0.12), (0.3, 0.1), (0.22, 0.24), (0.03, 0.16)]
    for shp in (pts, blade):
        f1 = [bm.verts.new((x, -0.008, z0 + z - 0.24)) for x, z in shp]
        f2 = [bm.verts.new((x, 0.008, z0 + z - 0.24)) for x, z in shp]
        bm.faces.new(f1)
        bm.faces.new(f2[::-1])
        for i in range(len(shp)):
            j = (i + 1) % len(shp)
            bm.faces.new((f1[i], f2[i], f2[j], f1[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    b = _obj(f"{name}.blade", bm, coll, "steel_bright", uv=False)
    b.parent = root
    return _place(root, at)
