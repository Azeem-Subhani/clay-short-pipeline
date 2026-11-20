"""stagekit.build - clay materials and chunky, bevelled set pieces.

Everything is real-world scale in metres, Z up. `at=(x, y, z)` is where the piece RESTS (its bottom centre),
so `at=(1, 2, 0)` stands on the floor and nothing floats. Characters face -Y by default, so a camera on -Y
looking toward +Y sees their faces; build the back wall on +Y.

These builders are the third source of assets (after the project library and BlenderKit). They are meant to be
combined and extended: every function returns a normal Blender object you can move, parent, recolour or animate.
"""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import core

# ----------------------------------------------------------------------------- materials
_MATS: dict[tuple, bpy.types.Material] = {}


def clay(color="#B8A089", rough: float | None = None, bump: float | None = None, sss: float = 0.0, coat: float = 0.0,
         metallic: float = 0.0, name: str | None = None):
    """The one material language of the channel: matte clay with a faint hand-made surface.
    Shared per (colour, settings) so a recolour never leaks by accident: call again with a new colour instead."""
    cl, _, _ = core.pack_modules()
    c = core.STYLE["clay"]
    rough = c["roughness"] if rough is None else rough
    bump = c["bump"] if bump is None else bump
    k = (str(color), round(rough, 3), round(bump, 4), round(sss, 3), round(coat, 3), round(metallic, 3))
    if k in _MATS and _MATS[k].name in bpy.data.materials:
        return _MATS[k]
    hexcol = color if isinstance(color, str) else "#%02X%02X%02X" % tuple(int(max(0, min(1, v)) * 255) for v in color[:3])
    m = cl.new_clay_material(name or f"clay_{hexcol.lstrip('#')}_{len(_MATS)}", hexcol, rough=rough, bump=bump, sss=sss, coat=coat,
                             keep=True)
    if metallic:
        cl.principled(m).inputs["Metallic"].default_value = metallic
    _MATS[k] = m
    return m


def glow(color="#FFC477", strength: float = 6.0, name: str | None = None):
    """Emissive surface for things that ARE light in the story: a lit window, a bulb, a screen, a siren.
    It does not light the set by itself in EEVEE: pair it with lights.practical()."""
    m = bpy.data.materials.new(name or "glow")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = core.hex_rgba(color)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    m["glow_strength"] = strength
    return m


def glass(color="#BFD8E6", rough: float = 0.08, alpha: float = 0.25):
    """Simple see-through pane (dithered blend, EEVEE-friendly)."""
    m = bpy.data.materials.new("glass")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = core.hex_rgba(color)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Alpha"].default_value = alpha
    b.inputs["Coat Weight"].default_value = 0.4
    m.surface_render_method = "DITHERED"
    return m


def set_glow(ob_or_mat, strength: float, t: float | None = None):
    """Set (and key, if t is given) the emission strength of a glow material: a window going dark, a siren pulse."""
    mat = ob_or_mat if isinstance(ob_or_mat, bpy.types.Material) else ob_or_mat.active_material
    em = next(n for n in mat.node_tree.nodes if n.type == "EMISSION")
    em.inputs["Strength"].default_value = strength
    if t is not None:
        em.inputs["Strength"].keyframe_insert("default_value", frame=core.current().f(t))


# ----------------------------------------------------------------------------- mesh helpers
def _new(name: str, bm: bmesh.types.BMesh, coll: str = "SET"):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, coll)
    return ob


def finish(ob, color=None, bevel: float | None = None, smooth: bool = True, material=None, subdiv: int = 0):
    """Give a mesh the clay treatment: bevelled edges that catch a soft line of light, smooth shading, clay material."""
    c = core.STYLE["clay"]
    me = ob.data
    if material is None and color is not None:
        material = clay(color)
    if material is not None:
        me.materials.clear()
        me.materials.append(material)
    dims = _dims(me)
    if bevel is None:
        d = sorted(dims)
        ref = d[1] if d[1] > 1e-6 else max(d)
        bevel = max(c["bevel_min_m"], min(c["bevel_max_m"], ref * c["bevel_ratio"]))
    if bevel and bevel > 0 and max(dims) > 1e-6:
        b = ob.modifiers.new("Bevel", "BEVEL")
        b.width = min(bevel, 0.45 * min(d for d in dims if d > 1e-6))
        b.segments = 3
        b.limit_method = "ANGLE"
        b.angle_limit = math.radians(40)
        b.miter_outer = "MITER_ARC"
    if subdiv:
        s = ob.modifiers.new("Subdiv", "SUBSURF")
        s.levels = s.render_levels = subdiv
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
        wn = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
        wn.keep_sharp = False
    return ob


def _dims(me):
    if not me.vertices:
        return (0.0, 0.0, 0.0)
    xs, ys, zs = zip(*(v.co for v in me.vertices))
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def group(name: str, parts, at=(0, 0, 0), rot_z: float = 0.0, coll: str = "SET"):
    """Parent parts to one empty so a whole prop moves as one thing. Parts keep the positions they were built at
    (built around the origin), then the group is placed at `at` and turned by rot_z degrees."""
    root = core.empty(name, (0, 0, 0), coll=coll, size=0.2)
    for p in parts:
        if p is not None and p.parent is None:
            p.parent = root
    root.location = at
    root.rotation_euler.z = math.radians(rot_z)
    return root


# ----------------------------------------------------------------------------- primitives
def box(name: str, size=(1, 1, 1), at=(0, 0, 0), color="#B8A089", bevel: float | None = None, rot_z: float = 0.0,
        material=None, coll: str = "SET"):
    """Rounded box resting on `at`."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    sx, sy, sz = size
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, sz / 2), verts=bm.verts)
    ob = _new(name, bm, coll)
    ob.location = at
    ob.rotation_euler.z = math.radians(rot_z)
    return finish(ob, color, bevel, material=material)


def cyl(name: str, radius: float = 0.5, height: float = 1.0, at=(0, 0, 0), color="#B8A089", top_radius: float | None = None,
        segments: int = 40, bevel: float | None = None, material=None, coll: str = "SET"):
    """Cylinder or cone (top_radius) resting on `at`."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius,
                          radius2=radius if top_radius is None else max(top_radius, 1e-4), depth=height)
    bmesh.ops.translate(bm, vec=(0, 0, height / 2), verts=bm.verts)
    ob = _new(name, bm, coll)
    ob.location = at
    return finish(ob, color, bevel, material=material)


def ball(name: str, radius: float = 0.5, at=(0, 0, 0), color="#B8A089", squash=(1, 1, 1), material=None, coll: str = "SET"):
    """Sphere (or squashed blob) resting on `at`."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=24, radius=radius)
    bmesh.ops.scale(bm, vec=squash, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, radius * squash[2]), verts=bm.verts)
    ob = _new(name, bm, coll)
    ob.location = at
    return finish(ob, color, bevel=0, material=material)


def slab(name: str, size=(4, 4), at=(0, 0, 0), color="#6F6A64", thickness: float = 0.1, material=None, coll: str = "SET"):
    """Floor, rug, path or tabletop: a thin rounded box whose TOP surface is at `at` z."""
    ob = box(name, (size[0], size[1], thickness), (at[0], at[1], at[2] - thickness), color, bevel=min(0.02, thickness * 0.3),
             material=material, coll=coll)
    return ob


def ground(name: str = "ground", size: float = 60.0, color="#4E5B45", relief: float = 0.0, seed: int = 1, keep_flat_radius: float = 4.0,
           at=(0, 0, 0), coll: str = "SET"):
    """Large outdoor ground. relief > 0 adds soft hills away from the acting area (flat within keep_flat_radius)."""
    bm = bmesh.new()
    n = 48 if relief else 2
    bmesh.ops.create_grid(bm, x_segments=n, y_segments=n, size=size / 2)
    if relief:
        rnd = random.Random(seed)
        ph = [(rnd.uniform(0.05, 0.22), rnd.uniform(0.05, 0.22), rnd.uniform(0, 6.28), rnd.uniform(0.4, 1.0)) for _ in range(5)]
        for v in bm.verts:
            d = math.hypot(v.co.x, v.co.y)
            w = max(0.0, min(1.0, (d - keep_flat_radius) / (keep_flat_radius * 2.0)))
            h = sum(a * math.sin(fx * v.co.x + p) * math.cos(fy * v.co.y + p * 0.7) for fx, fy, p, a in ph)
            v.co.z = relief * w * w * (h * 0.5 + 0.3 * (d / (size / 2)) ** 2 * 3)
    ob = _new(name, bm, coll)
    ob.location = at
    return finish(ob, color, bevel=0)


def backdrop(name: str = "backdrop", color="#1B2240", top_color: str | None = None, strength: float = 1.0, radius: float = 40.0,
             height: float = 30.0, arc_deg: float = 220.0, center=(0, 0, 0), facing_deg: float = 0.0, coll: str = "SET"):
    """Curved sky wall behind the set (centred on +Y by default) so the horizon is never an empty black void.
    It glows by itself (it is sky, not a lit object): `color` at the horizon fading to `top_color` overhead.
    Night: "#1A2658" -> "#070B1E", strength 0.5-0.8.  Day: "#BFD9F2" -> "#6FA3E0", strength 1.0.  Dusk: "#F0A070" -> "#2A3A78"."""
    bm = bmesh.new()
    seg = 48
    a0 = math.radians(90 - arc_deg / 2 + facing_deg)
    ring0, ring1 = [], []
    for i in range(seg + 1):
        a = a0 + math.radians(arc_deg) * i / seg
        ring0.append(bm.verts.new((radius * math.cos(a), radius * math.sin(a), -2.0)))
        ring1.append(bm.verts.new((radius * math.cos(a), radius * math.sin(a), height)))
    for i in range(seg):
        bm.faces.new((ring0[i + 1], ring0[i], ring1[i], ring1[i + 1]))
    ob = _new(name, bm, coll)
    ob.location = center
    m = bpy.data.materials.new(f"{name}_sky")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mp = nt.nodes.new("ShaderNodeMapRange")
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mp.inputs["From Min"].default_value = 0.0
    mp.inputs["From Max"].default_value = height * 0.6
    mix.inputs["A"].default_value = core.hex_rgba(color)
    mix.inputs["B"].default_value = core.hex_rgba(top_color or _shade(color, 0.35))
    em.inputs["Strength"].default_value = strength
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mp.inputs["Value"])
    nt.links.new(mp.outputs["Result"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    ob.data.materials.append(m)
    ob.visible_shadow = False
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


# ----------------------------------------------------------------------------- architecture
def wall(name: str, length: float = 4.0, height: float = 2.7, at=(0, 0, 0), rot_z: float = 0.0, color="#C9B8A0", thickness: float = 0.16,
         openings=(), coll: str = "SET"):
    """A wall with real thickness, centred on `at`, running along local X.
    openings: [(centre_x, bottom_z, width, height), ...] cut for doors and windows (x measured from the wall centre)."""
    ob = box(name, (length, thickness, height), at, color, bevel=0.012, rot_z=rot_z, coll=coll)
    for i, (cx, z0, w, h) in enumerate(openings):
        cutter = box(f"{name}_cut{i}", (w, thickness * 4, h), (0, 0, 0), color, bevel=0, coll="HELPERS")
        cutter.parent = ob
        cutter.location = (cx, 0, z0)
        cutter.display_type = "WIRE"
        cutter.hide_render = True
        cutter.hide_viewport = True
        b = ob.modifiers.new(f"cut{i}", "BOOLEAN")
        b.operation = "DIFFERENCE"
        b.object = cutter
        b.solver = "EXACT"
        ob.modifiers.move(len(ob.modifiers) - 1, 0)      # cut before the bevel so the opening gets soft edges too
    return ob


def room(name: str = "room", width: float = 4.5, depth: float = 4.0, height: float = 2.7, at=(0, 0, 0), wall_color="#C9B8A0",
         floor_color="#7A5C45", ceiling: bool = False, open_sides=("front",), openings: dict | None = None, baseboard: bool = True,
         coll: str = "SET"):
    """Three-wall room set, open toward the camera (-Y) by default. Centre of the floor is `at`.
    openings: {"back": [(cx, z0, w, h)], "left": [...], "right": [...]} for doors/windows.
    Returns the group; walls are children named <name>_back/_left/_right/_front, floor <name>_floor."""
    openings = openings or {}
    parts = [slab(f"{name}_floor", (width + 0.4, depth + 0.4), (0, 0, 0), floor_color, coll=coll)]
    t = 0.16
    spec = {
        "back": ((0, depth / 2 + t / 2, 0), 0.0, width + 2 * t),
        "front": ((0, -depth / 2 - t / 2, 0), 0.0, width + 2 * t),
        "left": ((-width / 2 - t / 2, 0, 0), 90.0, depth),
        "right": ((width / 2 + t / 2, 0, 0), 90.0, depth),
    }
    for side, (pos, rz, ln) in spec.items():
        if side in open_sides:
            continue
        w = wall(f"{name}_{side}", ln, height, pos, rz, wall_color, t, openings.get(side, ()), coll=coll)
        parts.append(w)
        if baseboard:
            bb = box(f"{name}_{side}_base", (ln, t + 0.03, 0.1), pos, _shade(wall_color, 0.72), bevel=0.01, rot_z=rz, coll=coll)
            for i, (cx, z0, ow, oh) in enumerate(openings.get(side, ())):
                if z0 < 0.1:
                    bb.hide_render = bb.hide_viewport = True   # a door interrupts the baseboard: keep it simple, drop it
            parts.append(bb)
    if ceiling:
        parts.append(slab(f"{name}_ceiling", (width + 0.4, depth + 0.4), (0, 0, height + 0.1), _shade(wall_color, 1.08), coll=coll))
    return group(name, parts, at, coll=coll)


def window(name: str = "window", width: float = 0.9, height: float = 1.1, at=(0, 0, 1.0), rot_z: float = 0.0, frame_color="#E8E1D5",
           lit=None, lit_strength: float = 5.0, depth: float = 0.2, coll: str = "SET"):
    """Window frame with a cross bar. `lit` = a colour makes the pane glow (a lit room seen from outside, or daylight
    seen from inside); None = dark glass. The pane is <name>_pane: use build.set_glow(pane, 0, t) to switch it off."""
    f = 0.07
    parts = [
        box(f"{name}_l", (f, depth, height), (-width / 2 + f / 2, 0, 0), frame_color, coll=coll),
        box(f"{name}_r", (f, depth, height), (width / 2 - f / 2, 0, 0), frame_color, coll=coll),
        box(f"{name}_t", (width, depth, f), (0, 0, height - f), frame_color, coll=coll),
        box(f"{name}_b", (width + 0.1, depth + 0.08, f), (0, 0, 0), frame_color, coll=coll),
        box(f"{name}_mv", (f * 0.6, depth * 0.6, height), (0, 0, 0), frame_color, coll=coll),
        box(f"{name}_mh", (width, depth * 0.6, f * 0.6), (0, 0, height / 2), frame_color, coll=coll),
    ]
    pane = box(f"{name}_pane", (width - f, 0.02, height - f), (0, 0, f / 2), "#000000", bevel=0,
               material=glow(lit, lit_strength, f"{name}_glow") if lit else glass(), coll=coll)
    parts.append(pane)
    g = group(name, parts, at, rot_z, coll)
    g["pane"] = pane.name
    return g


def door(name: str = "door", width: float = 0.9, height: float = 2.05, at=(0, 0, 0), rot_z: float = 0.0, color="#6B4A33",
         frame_color="#E8E1D5", open_deg: float = 0.0, coll: str = "SET"):
    """Door in a frame. The leaf <name>_leaf hinges on its left edge: core.move(leaf_pivot, t0, t1, rotation_deg=(0,0,-80))
    swings it open. Returns the group; group['pivot'] is the name of the hinge empty."""
    f = 0.08
    parts = [
        box(f"{name}_fl", (f, 0.2, height + f), (-width / 2 - f / 2, 0, 0), frame_color, coll=coll),
        box(f"{name}_fr", (f, 0.2, height + f), (width / 2 + f / 2, 0, 0), frame_color, coll=coll),
        box(f"{name}_ft", (width + 2 * f, 0.2, f), (0, 0, height), frame_color, coll=coll),
    ]
    pivot = core.empty(f"{name}_pivot", (-width / 2, 0, 0), coll=coll)
    leaf = box(f"{name}_leaf", (width - 0.01, 0.05, height - 0.01), (width / 2, 0, 0.005), color, coll=coll)
    leaf.parent = pivot
    knob = ball(f"{name}_knob", 0.035, (width * 0.86, -0.05, 0.98), "#C9A24B", coll=coll)
    knob.parent = pivot
    pivot.rotation_euler.z = math.radians(-open_deg)
    parts.append(pivot)
    g = group(name, parts, at, rot_z, coll)
    g["pivot"] = pivot.name
    return g


# ----------------------------------------------------------------------------- furniture and props
def table(name: str = "table", size=(1.2, 0.7), height: float = 0.74, at=(0, 0, 0), rot_z: float = 0.0, color="#8A6748", coll: str = "SET"):
    w, d = size
    leg = 0.06
    parts = [box(f"{name}_top", (w, d, 0.05), (0, 0, height - 0.05), color, coll=coll)]
    for i, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        parts.append(box(f"{name}_leg{i}", (leg, leg, height - 0.05), (sx * (w / 2 - 0.08), sy * (d / 2 - 0.08), 0), _shade(color, 0.9), coll=coll))
    return group(name, parts, at, rot_z, coll)


def chair(name: str = "chair", at=(0, 0, 0), rot_z: float = 0.0, color="#7B5A40", seat_height: float = 0.45, coll: str = "SET"):
    """Chair facing -Y (rot_z=180 faces +Y). Seat top at seat_height."""
    s = 0.42
    parts = [box(f"{name}_seat", (s, s, 0.05), (0, 0, seat_height - 0.05), color, coll=coll),
             box(f"{name}_back", (s, 0.05, 0.45), (0, s / 2 - 0.025, seat_height), color, coll=coll)]
    for i, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        parts.append(box(f"{name}_leg{i}", (0.045, 0.045, seat_height - 0.05), (sx * (s / 2 - 0.04), sy * (s / 2 - 0.04), 0), _shade(color, 0.9), coll=coll))
    return group(name, parts, at, rot_z, coll)


def bed(name: str = "bed", size=(0.95, 1.95), at=(0, 0, 0), rot_z: float = 0.0, frame_color="#6B4A33", sheet_color="#D9D2C4",
        blanket_color="#5C7A99", coll: str = "SET"):
    """Single bed, head toward +Y. Mattress top is at z = 0.5: a lying character goes at z 0.5."""
    w, l = size
    parts = [
        box(f"{name}_frame", (w + 0.08, l + 0.08, 0.28), (0, 0, 0), frame_color, coll=coll),
        box(f"{name}_head", (w + 0.08, 0.07, 0.9), (0, l / 2 + 0.03, 0), frame_color, coll=coll),
        box(f"{name}_mattress", (w, l, 0.2), (0, 0, 0.28), sheet_color, bevel=0.05, coll=coll),
        box(f"{name}_pillow", (w * 0.7, 0.38, 0.11), (0, l / 2 - 0.3, 0.48), "#F1ECE2", bevel=0.05, coll=coll),
        box(f"{name}_blanket", (w + 0.05, l * 0.6, 0.06), (0, -l * 0.18, 0.47), blanket_color, bevel=0.03, coll=coll),
    ]
    return group(name, parts, at, rot_z, coll)


def shelf(name: str = "shelf", width: float = 0.9, height: float = 1.8, depth: float = 0.3, at=(0, 0, 0), rot_z: float = 0.0,
          color="#7B5A40", levels: int = 4, fill: bool = True, seed: int = 3, coll: str = "SET"):
    """Bookshelf with a few chunky books and boxes on it (lived-in dressing for a background)."""
    rnd = random.Random(seed)
    t = 0.04
    parts = [box(f"{name}_l", (t, depth, height), (-width / 2 + t / 2, 0, 0), color, coll=coll),
             box(f"{name}_r", (t, depth, height), (width / 2 - t / 2, 0, 0), color, coll=coll),
             box(f"{name}_bk", (width, 0.02, height), (0, depth / 2 - 0.01, 0), _shade(color, 0.8), coll=coll)]
    palette = ["#A6513B", "#3F5F7A", "#C9A24B", "#5E7355", "#D9D2C4", "#6E4A6B"]
    for i in range(levels + 1):
        z = i * (height - t) / levels
        parts.append(box(f"{name}_s{i}", (width, depth, t), (0, 0, z), color, coll=coll))
        if fill and i < levels:
            x = -width / 2 + t + 0.04
            while x < width / 2 - t - 0.12:
                bw = rnd.uniform(0.035, 0.07)
                bh = rnd.uniform(0.18, min(0.3, (height - t) / levels - 0.08))
                if rnd.random() < 0.8:
                    parts.append(box(f"{name}_b{i}_{int(x * 1000)}", (bw, depth * 0.7, bh), (x + bw / 2, -0.02, z + t), rnd.choice(palette), bevel=0.006, coll=coll))
                x += bw + rnd.uniform(0.004, 0.05)
    return group(name, parts, at, rot_z, coll)


def crate(name: str = "crate", size: float = 0.5, at=(0, 0, 0), rot_z: float = 0.0, color="#9A7448", coll: str = "SET"):
    s = size
    parts = [box(f"{name}_body", (s, s, s), (0, 0, 0), color, coll=coll)]
    for i, y in enumerate((-s / 2 - 0.006, s / 2 + 0.006)):
        parts.append(box(f"{name}_p{i}a", (s * 1.02, 0.02, s * 0.14), (0, y, s * 0.08), _shade(color, 0.82), coll=coll))
        parts.append(box(f"{name}_p{i}b", (s * 1.02, 0.02, s * 0.14), (0, y, s * 0.78), _shade(color, 0.82), coll=coll))
    return group(name, parts, at, rot_z, coll)


def lamp(name: str = "lamp", kind: str = "table", at=(0, 0, 0), color="#FFC477", shade_color="#E9D9B8", strength: float = 8.0,
         height: float | None = None, coll: str = "SET"):
    """A lamp prop whose shade glows. kind: table (0.45 m) | floor (1.5 m) | hanging (bulb hangs DOWN from `at`, a ceiling point)
    | street (3.2 m post). Returns the group; group['bulb_point'] is where lights.practical() should sit."""
    parts = []
    if kind == "hanging":
        drop = height or 0.8
        parts.append(cyl(f"{name}_cord", 0.008, drop, (0, 0, -drop), "#1E1E22", segments=8, bevel=0, coll=coll))
        parts.append(cyl(f"{name}_shade", 0.2, 0.14, (0, 0, -drop - 0.1), shade_color, top_radius=0.05, coll=coll))
        parts.append(ball(f"{name}_bulb", 0.05, (0, 0, -drop - 0.17), "#000", material=glow(color, strength, f"{name}_glow"), coll=coll))
        bp = (0, 0, -drop - 0.2)
    elif kind == "street":
        h = height or 3.2
        parts.append(cyl(f"{name}_post", 0.05, h, (0, 0, 0), "#2A2D33", top_radius=0.035, segments=16, coll=coll))
        parts.append(box(f"{name}_arm", (0.5, 0.05, 0.05), (0.22, 0, h - 0.05), "#2A2D33", coll=coll))
        parts.append(box(f"{name}_head", (0.26, 0.16, 0.07), (0.42, 0, h - 0.12), "#2A2D33", coll=coll))
        parts.append(box(f"{name}_bulb", (0.2, 0.11, 0.02), (0.42, 0, h - 0.14), "#000", bevel=0, material=glow(color, strength, f"{name}_glow"), coll=coll))
        bp = (0.42, 0, h - 0.25)
    else:
        h = height or (1.5 if kind == "floor" else 0.45)
        parts.append(cyl(f"{name}_foot", 0.11 if kind == "floor" else 0.07, 0.03, (0, 0, 0), "#2A2D33", coll=coll))
        parts.append(cyl(f"{name}_stem", 0.012, h - 0.2, (0, 0, 0.03), "#2A2D33", segments=10, bevel=0, coll=coll))
        sr = 0.17 if kind == "floor" else 0.13
        sh = cyl(f"{name}_shade", sr, 0.2, (0, 0, h - 0.2), "#000", top_radius=sr * 0.7, material=glow(shade_color, strength * 0.35, f"{name}_glow"), coll=coll)
        parts.append(sh)
        bp = (0, 0, h - 0.12)
    g = group(name, parts, at, coll=coll)
    g["bulb_point"] = tuple(Vector(at) + Vector(bp))
    g["glow"] = f"{name}_glow"
    return g


def frame_picture(name: str = "picture", size=(0.5, 0.4), at=(0, 0, 1.5), rot_z: float = 0.0, frame_color="#3A2A1E", art_color="#7FA6A0", coll: str = "SET"):
    """Framed picture to break up a bare wall. `at` is the bottom centre; it hangs flat against a wall running along X."""
    w, h = size
    parts = [box(f"{name}_frame", (w, 0.035, h), (0, 0, 0), frame_color, coll=coll),
             box(f"{name}_art", (w - 0.08, 0.02, h - 0.08), (0, -0.012, 0.04), art_color, bevel=0, coll=coll)]
    return group(name, parts, at, rot_z, coll)


def cup(name: str = "cup", at=(0, 0, 0), color="#D9D2C4", coll: str = "SET"):
    body = cyl(name, 0.04, 0.09, at, color, top_radius=0.045, segments=24, coll=coll)
    return body


def rug(name: str = "rug", size=(1.6, 1.1), at=(0, 0, 0), color="#8C4A3C", rot_z: float = 0.0, coll: str = "SET"):
    ob = slab(name, size, (at[0], at[1], at[2] + 0.015), color, thickness=0.015, coll=coll)
    ob.rotation_euler.z = math.radians(rot_z)
    return ob


# ----------------------------------------------------------------------------- exterior
def tree(name: str = "tree", kind: str = "round", height: float = 4.0, at=(0, 0, 0), color="#3E6B45", trunk_color="#5A4030", seed: int = 0,
         coll: str = "SET"):
    """Chunky clay tree. kind: round (blobby crown) | pine (stacked cones) | bare (trunk and a few limbs, for winter/night dread)."""
    rnd = random.Random(seed)
    th = height * (0.45 if kind == "round" else 0.3 if kind == "pine" else 0.85)
    tr = height * 0.045
    parts = [cyl(f"{name}_trunk", tr, th, (0, 0, 0), trunk_color, top_radius=tr * 0.6, segments=12, coll=coll)]
    if kind == "round":
        r = height * 0.26
        parts.append(ball(f"{name}_c0", r, (0, 0, th - r * 0.5), color, squash=(1, 1, 0.9), coll=coll))
        for i in range(4):
            a = rnd.uniform(0, 6.28)
            rr = r * rnd.uniform(0.5, 0.75)
            parts.append(ball(f"{name}_c{i + 1}", rr, (math.cos(a) * r * 0.65, math.sin(a) * r * 0.65, th - r * 0.4 + rnd.uniform(0, r * 0.9)), _shade(color, rnd.uniform(0.88, 1.1)), coll=coll))
    elif kind == "pine":
        n = 4
        for i in range(n):
            k = 1 - i / (n + 0.6)
            parts.append(cyl(f"{name}_c{i}", height * 0.24 * k, height * 0.3, (0, 0, th + i * height * 0.17), _shade(color, 0.9 + 0.06 * i), top_radius=0.02, segments=20, bevel=0.03, coll=coll))
    else:
        for i in range(5):
            a = rnd.uniform(0, 6.28)
            ln = height * rnd.uniform(0.2, 0.35)
            limb = cyl(f"{name}_l{i}", tr * 0.35, ln, (0, 0, 0), trunk_color, top_radius=tr * 0.12, segments=8, bevel=0, coll=coll)
            limb.location = (0, 0, th * rnd.uniform(0.55, 0.95))
            limb.rotation_euler = (math.radians(rnd.uniform(35, 65)), 0, a)
            parts.append(limb)
    return group(name, parts, at, rot_z=rnd.uniform(0, 360), coll=coll)


def bush(name: str = "bush", size: float = 0.8, at=(0, 0, 0), color="#44704A", seed: int = 0, coll: str = "SET"):
    rnd = random.Random(seed)
    parts = [ball(f"{name}_0", size * 0.5, (0, 0, -size * 0.12), color, squash=(1, 1, 0.8), coll=coll)]
    for i in range(3):
        a = rnd.uniform(0, 6.28)
        parts.append(ball(f"{name}_{i + 1}", size * rnd.uniform(0.28, 0.4), (math.cos(a) * size * 0.4, math.sin(a) * size * 0.4, -size * 0.1), _shade(color, rnd.uniform(0.88, 1.12)), coll=coll))
    return group(name, parts, at, coll=coll)


def rock(name: str = "rock", size: float = 0.6, at=(0, 0, 0), color="#77736C", seed: int = 0, coll: str = "SET"):
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=size * 0.5)
    for v in bm.verts:
        v.co *= rnd.uniform(0.78, 1.15)
        v.co.z *= 0.7
    bmesh.ops.translate(bm, vec=(0, 0, size * 0.25), verts=bm.verts)
    ob = _new(name, bm, coll)
    ob.location = at
    ob.rotation_euler.z = rnd.uniform(0, 6.28)
    return finish(ob, color, bevel=0, subdiv=2)


def fence(name: str = "fence", length: float = 4.0, height: float = 1.0, at=(0, 0, 0), rot_z: float = 0.0, color="#B9A88F", spacing: float = 0.28,
          coll: str = "SET"):
    """Picket fence running along local X, centred on `at`."""
    parts = []
    n = max(2, int(length / spacing))
    for i in range(n + 1):
        x = -length / 2 + i * length / n
        parts.append(box(f"{name}_p{i}", (0.09, 0.03, height), (x, 0, 0), color, coll=coll))
    for j, z in enumerate((height * 0.25, height * 0.7)):
        parts.append(box(f"{name}_r{j}", (length, 0.03, 0.07), (0, 0.03, z), _shade(color, 0.92), coll=coll))
    return group(name, parts, at, rot_z, coll)


def house(name: str = "house", width: float = 6.0, depth: float = 5.0, height: float = 3.0, at=(0, 0, 0), rot_z: float = 0.0,
          wall_color="#C7B49A", roof_color="#6B3F36", windows: int = 2, lit=("#FFC477",), lit_strength: float = 5.0, door_color="#5A3B2A",
          coll: str = "SET"):
    """Simple house seen from outside, front toward -Y. `lit`: colours for the front windows, cycled; None entries are dark.
    Window panes are <name>_win<i>_pane (use build.set_glow to switch a window off)."""
    parts = [box(f"{name}_body", (width, depth, height), (0, 0, 0), wall_color, bevel=0.03, coll=coll)]
    # pitched roof: a prism
    bm = bmesh.new()
    ov = 0.35
    w2, d2, rh = width / 2 + ov, depth / 2 + ov, height * 0.55
    vs = [bm.verts.new(p) for p in ((-w2, -d2, 0), (w2, -d2, 0), (w2, d2, 0), (-w2, d2, 0), (-w2, 0, rh), (w2, 0, rh))]
    for f in ((0, 1, 5, 4), (2, 3, 4, 5), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)):
        bm.faces.new([vs[i] for i in f])
    roof = _new(f"{name}_roof", bm, coll)
    roof.location = (0, 0, height)
    finish(roof, roof_color, bevel=0.04)
    parts.append(roof)
    parts.append(box(f"{name}_chimney", (0.5, 0.5, height * 0.5), (width * 0.28, depth * 0.15, height + rh * 0.3), _shade(wall_color, 0.8), coll=coll))
    parts.append(door(f"{name}_door", at=(0, -depth / 2 - 0.02, 0), color=door_color, coll=coll))
    parts.append(box(f"{name}_step", (1.3, 0.5, 0.14), (0, -depth / 2 - 0.3, 0), _shade(wall_color, 0.7), coll=coll))
    lit = list(lit or [None])
    for i in range(windows):
        side = -1 if i % 2 == 0 else 1
        col = (i // 2) + 1
        x = side * (width / 2) * (col / (windows // 2 + 1.0)) * 0.95
        if abs(x) < 0.9:
            x = side * 1.5
        c = lit[i % len(lit)]
        parts.append(window(f"{name}_win{i}", at=(x, -depth / 2 - 0.02, 1.0), lit=c, lit_strength=lit_strength, coll=coll))
    return group(name, parts, at, rot_z, coll)


def scatter(maker, count: int, area=(-10, 10, -10, 10), seed: int = 1, avoid=(), min_gap: float = 0.0, **kw):
    """Scatter `maker(name=..., at=..., seed=...)` (tree, bush, rock) over area=(x0, x1, y0, y1), never inside
    avoid=[(x, y, radius), ...] (the acting area, the camera path). Varies seed per item. Returns the list."""
    rnd = random.Random(seed)
    out, pts = [], []
    tries = 0
    base = kw.pop("name", maker.__name__)
    while len(out) < count and tries < count * 40:
        tries += 1
        x, y = rnd.uniform(area[0], area[1]), rnd.uniform(area[2], area[3])
        if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid):
            continue
        if min_gap and any(math.hypot(x - px, y - py) < min_gap for px, py in pts):
            continue
        pts.append((x, y))
        out.append(maker(name=f"{base}_{len(out):02d}", at=(x, y, kw.get("z", 0.0)), seed=rnd.randint(0, 9999), **{k: v for k, v in kw.items() if k != "z"}))
    return out


def _shade(hexcol: str, k: float) -> str:
    """Lighter (k > 1) or darker (k < 1) version of a hex colour."""
    h = hexcol.lstrip("#")
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(int(h[i:i + 2], 16) * k))) for i in (0, 2, 4))
