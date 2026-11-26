"""stagekit.arch - architecture: rooms with real openings, doors, windows, columns, stairs, and the outsides of places.

Everything is metric and real-sized (door 2.0-2.1 m, house ceiling 2.6-3 m, hall 6-10 m) and built from bevelled boxes and
prisms, with surfaces by name (stagekit.mat). The camera side of a set is -Y.

    R = arch.room((12, 20, 8), floor="flagstone", walls="castle_stone", ceiling="dark_timber", ceiling_kind="beams",
                  openings=[dict(wall="N", kind="door", type="double", w=3.0, h=4.2, arched=True, id="gate"),
                            dict(wall="E", kind="window", type="arched", w=1.2, h=3.2, sill=1.8, at=-4.0, id="win1")])
    arch.vista(R, "E", "hills")                       # what the windows of the east wall look out on
    lights.window_key(R.openings["win1"])             # a real window light, from outside, with shadows of the frame
    arch.cutaway(R, camera_object)                    # hide the walls (and ceiling) that stand between the camera and the room

Conventions
  * A wall is built in its own frame: local +X along the wall, +Z up, local Y = 0 on the INTERIOR face and +thickness on
    the exterior face. Wall N is at +Y (rot 0), S at -Y (rot 180), E at +X (rot -90), W at -X (rot 90).
  * `at` for an opening is the offset of its centre from the room centre along the wall, in world X (walls N, S) or Y (walls E, W).
  * Every part of a wall (its mesh, doors, windows, trim, vista) carries sk_room / sk_wall so `cutaway` can hide it.
  * Furniture and props live in furnish.py; Parts (below) is the shared builder both modules use.
"""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import core, mat
from .build import _mat
from .build import _cylv as _cylv_plain

WALLS = ("N", "S", "E", "W")
WALL_ROT = {"N": 0.0, "S": 180.0, "E": -90.0, "W": 90.0}
OUT = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}          # outward direction of each wall in world XY


# ----------------------------------------------------------------------------- the shared builder
_CUBE = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))      # faces of the 8 corners, outward


def _cube(bm, size, matrix):
    """A box of `size` (corners built directly: about 8x quicker than bmesh.ops.create_cube + scale + transform)."""
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    vs = [bm.verts.new(matrix @ Vector((sx * hx, sy * hy, sz * hz))) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    for f in _CUBE:
        bm.faces.new([vs[i] for i in f])
    return vs


def _cylv(bm, r1, r2, h, matrix, seg=20, caps=True):
    """A cone or cylinder on the base point of `matrix`. An upright one is flagged for cylindrical UVs (mat.uv_box reads the
    face attributes sk_cyl, sk_cx, sk_cy), so stone courses and planks wrap round a column instead of banding."""
    vs = _cylv_plain(bm, r1, r2, h, matrix, seg, caps)
    z = matrix.to_3x3() @ Vector((0, 0, 1))
    if z.z > 0.999 and max(r1, r2) > 1e-4:
        lay = bm.faces.layers.int.get("sk_cyl") or bm.faces.layers.int.new("sk_cyl")
        lx = bm.faces.layers.float.get("sk_cx") or bm.faces.layers.float.new("sk_cx")
        ly = bm.faces.layers.float.get("sk_cy") or bm.faces.layers.float.new("sk_cy")
        c = matrix.translation
        seen = set()
        for v in vs:
            for f in v.link_faces:
                if f in seen:
                    continue
                seen.add(f)
                f.normal_update()
                if abs(f.normal.z) < 0.75 and len(f.verts) <= 4:
                    f[lay], f[lx], f[ly] = 1, c.x, c.y
    return vs


def _rot(r):
    return Matrix.Rotation(math.radians(r[2]), 4, "Z") @ Matrix.Rotation(math.radians(r[1]), 4, "Y") @ Matrix.Rotation(math.radians(r[0]), 4, "X")


def _finish(bm, sharp_deg: float = 38.0):
    """Smooth shading with hard edges where the surface turns sharply: round things look round, boxes stay crisp."""
    bm.normal_update()
    lim = math.radians(sharp_deg)
    for e in bm.edges:
        if len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < lim
    for f in bm.faces:
        f.smooth = True


def tag(ob, sk_type: str | None = None, kind: str = "prop", **props):
    """Mark an object for the set audit: sk_type is what it IS (counted as one prop type), kind is "shell" (walls, floor,
    ceiling, openings: not counted as props) or "prop"."""
    if sk_type:
        ob["sk_type"] = sk_type
    ob["sk_kind"] = kind
    for k, v in props.items():
        ob[f"sk_{k}"] = v
    return ob


class Parts:
    """Collects boxes, cylinders, lathed profiles, prisms and rods per material and builds them as a few merged meshes under one
    empty. The result's origin is the floor point at the centre of the BACK face of what was built (the front faces -Y), and its
    size is recorded in sk_size, so a piece placed `at` a wall stands against it. recentre=False keeps the authored coordinates."""

    def __init__(self, name: str, coll: str = "SET", sk_type: str | None = None, kind: str = "prop", era=None):
        self.name, self.coll, self.sk_type, self.kind, self.era = name, coll, sk_type, kind, era
        self.g: dict = {}
        self._lights: list = []
        self._tops: list = []
        self._anchors: dict = {}
        self.size = (0.0, 0.0, 0.0)

    # -- primitives
    def _bm(self, surface, tint, bevel):
        key = (getattr(surface, "name", surface), tint, bevel)
        if key not in self.g:
            self.g[key] = {"bm": bmesh.new(), "surface": surface, "tint": tint, "bevel": bevel}
        return self.g[key]["bm"]

    def box(self, size, at=(0, 0, 0), surface="oak_planks", tint=None, rot=(0, 0, 0), bevel: float = 0.008, mid: bool = False):
        """A box. `at` = centre in x, y and the BOTTOM in z (mid=True: the centre in z too). rot = (rx, ry, rz) degrees about the centre."""
        z = at[2] if mid else at[2] + size[2] / 2
        bevel = min(bevel, 0.4 * min(size))                    # a bevel wider than the board is thick folds the mesh over itself
        _cube(self._bm(surface, tint, bevel), Vector(size), Matrix.Translation((at[0], at[1], z)) @ _rot(rot))
        return self

    def cyl(self, r: float, h: float, at=(0, 0, 0), surface="oak_planks", tint=None, top: float | None = None, seg: int = 20, rot=(0, 0, 0),
            bevel: float = 0.0, caps: bool = True):
        """A cylinder or cone standing on `at` (rot turns it about that base point; rot=(0, 90, 0) lays it along +X)."""
        _cylv(self._bm(surface, tint, bevel), r, r if top is None else top, h, Matrix.Translation(at) @ _rot(rot), seg, caps)
        return self

    def ball(self, r: float, at=(0, 0, 0), surface="oak_planks", tint=None, squash=(1, 1, 1), sub: int = 2):
        bm = self._bm(surface, tint, 0.0)
        res = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
        bmesh.ops.scale(bm, vec=squash, verts=res["verts"])
        bmesh.ops.translate(bm, vec=at, verts=res["verts"])
        return self

    def lathe(self, profile, at=(0, 0, 0), surface="oak_planks", tint=None, seg: int = 24, bevel: float = 0.0):
        """A turned shape (vase, goblet, jug, lamp, column): profile = [(radius, height), ...] from the bottom up, spun round Z.
        A radius of 0 becomes a single point (no degenerate faces at the poles)."""
        bm = self._bm(surface, tint, bevel)
        rings = []
        for r, z in profile:
            if r < 1e-5:
                rings.append([bm.verts.new((at[0], at[1], at[2] + z))] * seg)
            else:
                rings.append([bm.verts.new((at[0] + r * math.cos(2 * math.pi * i / seg), at[1] + r * math.sin(2 * math.pi * i / seg), at[2] + z)) for i in range(seg)])
        for a, b in zip(rings, rings[1:]):
            for i in range(seg):
                j = (i + 1) % seg
                vs = []
                for v in (a[i], a[j], b[j], b[i]):
                    if v not in vs:
                        vs.append(v)
                if len(vs) >= 3:
                    bm.faces.new(vs)
        if profile[0][0] > 1e-4:
            bm.faces.new(rings[0][::-1])
        if profile[-1][0] > 1e-4:
            bm.faces.new(rings[-1])
        return self

    def prism(self, pts, z0: float, z1: float, surface="oak_planks", tint=None, bevel: float = 0.0):
        """A polygon outline (x, y) extruded from z0 to z1."""
        bm = self._bm(surface, tint, bevel)
        lo = [bm.verts.new((x, y, z0)) for x, y in pts]
        hi = [bm.verts.new((x, y, z1)) for x, y in pts]
        bm.faces.new(lo[::-1])
        bm.faces.new(hi)
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        return self

    def profile(self, pts, y0: float, y1: float, surface="oak_planks", tint=None, bevel: float = 0.0):
        """A polygon outline in the wall plane (x, z) extruded from y0 to y1 (door leaves, arched panels, gable ends)."""
        bm = self._bm(surface, tint, bevel)
        a = [bm.verts.new((x, y0, z)) for x, z in pts]
        b = [bm.verts.new((x, y1, z)) for x, z in pts]
        bm.faces.new(a)
        bm.faces.new(b[::-1])
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            bm.faces.new((a[i], b[i], b[j], a[j]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        return self

    def rod(self, p0, p1, r: float = 0.01, surface="iron_dark", tint=None, seg: int = 8):
        """A straight round bar between two points (rails, chains, candelabra arms, chair legs that splay)."""
        a, b = Vector(p0), Vector(p1)
        d = b - a
        if d.length < 1e-5:
            return self
        m = Matrix.Translation(a) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        _cylv(self._bm(surface, tint, 0.0), r, r, d.length, m, seg, True)
        return self

    def grid(self, w: float, h: float, at=(0, 0, 0), surface="cloth", tint=None, nx: int = 18, ny: int = 2, amp: float = 0.0, waves: float = 6.0,
             rot=(0, 0, 0), phase: float = 0.0, sag: float = 0.0):
        """A sheet hanging in the XZ plane (centre x, top z = at z + h), with sine folds `amp` deep: curtains, banners, tapestries."""
        bm = self._bm(surface, tint, 0.0)
        m = Matrix.Translation(at) @ _rot(rot)
        vs = []
        for j in range(ny + 1):
            row = []
            for i in range(nx + 1):
                u = i / nx
                x = (u - 0.5) * w
                z = h * (1 - j / ny)
                y = amp * math.sin(u * waves * math.pi * 2 + phase) * (0.35 + 0.65 * (j / max(1, ny))) - sag * math.sin(math.pi * u)
                row.append(bm.verts.new(m @ Vector((x, y, z - h))))
            vs.append(row)
        for j in range(ny):
            for i in range(nx):
                bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
        return self

    # -- lights, anchors, tops
    def glow(self, color="#FFC477", strength: float = 6.0):
        """A glowing surface. A saturated warm colour (flame, candle, lantern glass, lit window) is held to a peak of 1.1: pushed harder,
        the neutral tone map bleaches it to pink-white, so flames would lose their orange. White and pale light panels keep their strength."""
        c = core.hex_rgba(color)
        hi = max(c[:3])
        if hi > 0 and min(c[:3]) / hi < 0.5 and strength * hi > 1.1:
            strength = round(1.1 / hi, 2)
        return mat.emit(color, strength, f"SK_emit_{color}_{strength}")

    def light(self, name: str, at, color="#FFC477", power: float = 40.0, radius: float = 0.08, shadow: bool = True, kind: str = "POINT", aim=None, size=None):
        """A real light that belongs to this piece (a candle flame, a lamp): built with lights.practical when the piece is built."""
        self._lights.append(dict(name=name, at=tuple(at), color=color, power=power, radius=radius, shadow=shadow, kind=kind, aim=aim, size=size))
        return self

    def top(self, centre_xy, size_xy, z: float, label: str = "top"):
        """Declare a flat surface small props may stand on (a table top, a shelf): centre (x, y), size (w, d), height z."""
        self._tops.append([centre_xy[0], centre_xy[1], z, size_xy[0], size_xy[1], label])
        return self

    def anchor(self, name: str, at):
        self._anchors[name] = tuple(at)
        return self

    # -- build
    def build(self, at=(0, 0, 0), rot_z: float = 0.0, recentre: bool = True, parent=None):
        from . import lights
        lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
        for g in self.g.values():
            for v in g["bm"].verts:
                lo = Vector(map(min, lo, v.co))
                hi = Vector(map(max, hi, v.co))
        if lo.x > hi.x:
            lo = hi = Vector((0, 0, 0))
        shift = Vector((-(lo.x + hi.x) / 2, -hi.y, 0)) if recentre else Vector((0, 0, 0))
        root = core.empty(self.name, (0, 0, 0), self.coll, 0.1)
        for gi, g in enumerate(self.g.values()):
            bm = g["bm"]
            if shift.length:
                bmesh.ops.translate(bm, vec=shift, verts=bm.verts)
                lx, ly = bm.faces.layers.float.get("sk_cx"), bm.faces.layers.float.get("sk_cy")
                if lx is not None:
                    for f in bm.faces:
                        f[lx] += shift.x
                        f[ly] += shift.y
            _finish(bm)
            me = bpy.data.meshes.new(f"{self.name}.{gi}")
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(f"{self.name}.{gi}", me)
            core.link(ob, self.coll)
            m = _mat(g["surface"], g["tint"])
            if m:
                me.materials.append(m)
            if me.polygons and not me.uv_layers and not (hasattr(g["surface"], "node_tree") and g["surface"].name.startswith("SK_emit")):
                mat.uv_box(ob)
            if g["bevel"] > 0 and len(me.polygons) < 4000:
                b = ob.modifiers.new("bevel", "BEVEL")
                b.width = g["bevel"]
                b.segments = 2 if g["bevel"] >= 0.02 else 1
                b.limit_method = "ANGLE"
                b.harden_normals = True
            ob.parent = root
        for L in self._lights:
            lo_ = lights.practical(L["name"], Vector(L["at"]) + shift, L["color"], L["power"], L["radius"], L["kind"], None, L["size"], L["shadow"])
            lo_.parent = root
            lo_.location = Vector(L["at"]) + shift
            if L["aim"] is not None:
                lo_.rotation_euler = (Vector(L["aim"]) + shift - lo_.location).to_track_quat("-Z", "Y").to_euler()
        root["sk_size"] = [round(hi.x - lo.x, 4), round(hi.y - lo.y, 4), round(hi.z - min(lo.z, 0.0) if lo.z > -0.05 else hi.z - lo.z, 4)]
        root["sk_zlo"] = round(lo.z, 4)
        root["sk_tops"] = [dict(x=t[0] + shift.x, y=t[1] + shift.y, z=t[2], w=t[3], d=t[4], label=t[5]) for t in self._tops]
        root["sk_anchors"] = {k: [v[0] + shift.x, v[1] + shift.y, v[2]] for k, v in self._anchors.items()}
        root["sk_nlights"] = len(self._lights)
        tag(root, self.sk_type, self.kind)
        if self.era:
            root["sk_era"] = list(self.era)
        self.size = tuple(root["sk_size"])
        if parent is not None:
            root.parent = parent
        root.location = Vector(at)
        root.rotation_euler.z = math.radians(rot_z)
        return root


def put(ob, x: float, y: float, z: float = 0.0, rot_z: float | None = None):
    """Stand a built piece at x, y, z (z = height of its back-centre origin) and turn it about Z."""
    ob.location = (x, y, z)
    if rot_z is not None:
        ob.rotation_euler.z = math.radians(rot_z)
    return ob


# ----------------------------------------------------------------------------- 2D wall profiles
def _arc_pts(cx: float, zs: float, r: float, n: int = 12, rx: float | None = None):
    """Half-ellipse from the right spring point to the left, excluding both ends: (x, z) tuples."""
    rx = r if rx is None else rx
    return [(cx + rx * math.cos(math.pi * k / (n + 1)), zs + r * math.sin(math.pi * k / (n + 1))) for k in range(1, n + 1)]


def _opening_pts(u0: float, u1: float, z0: float, z1: float, arched: bool, n: int = 12):
    """Corner/arc points of an opening, counter-clockwise from the bottom-left."""
    if not arched:
        return [(u0, z0), (u1, z0), (u1, z1), (u0, z1)]
    r = (u1 - u0) / 2
    zs = z1 - r
    return [(u0, z0), (u1, z0), (u1, zs)] + _arc_pts((u0 + u1) / 2, zs, r, n) + [(u0, zs)]


def _wall_mesh(name, L, top, t, openings, surfaces, coll):
    """A wall slab along local X (centred), 0 <= y <= t, with real openings. Openings reaching the floor are notches in the
    bottom edge; others are holes. top: height, or a function of u for gable ends. surfaces = (inner, outer)."""
    topf = top if callable(top) else (lambda u, _h=top: _h)
    bm = bmesh.new()
    pts = [(-L / 2, 0.0)]
    notches = sorted([o for o in openings if o["z0"] <= 1e-6], key=lambda o: o["u0"])
    for o in notches:
        pts += [(o["u0"], 0.0)] + _arc_pts_up(o) + [(o["u1"], 0.0)]
    pts.append((L / 2, 0.0))
    n_top = 24 if callable(top) else 1
    for k in range(n_top + 1):
        u = L / 2 - L * k / n_top
        pts.append((u, topf(u)))
    ring = [bm.verts.new((u, 0.0, z)) for u, z in pts]
    edges = [bm.edges.new((ring[i], ring[(i + 1) % len(ring)])) for i in range(len(ring))]
    for o in openings:
        if o["z0"] <= 1e-6:
            continue
        hp = _opening_pts(o["u0"], o["u1"], o["z0"], o["z1"], o["arched"])
        hv = [bm.verts.new((u, 0.0, z)) for u, z in hp]
        edges += [bm.edges.new((hv[i], hv[(i + 1) % len(hv)])) for i in range(len(hv))]
    bmesh.ops.triangle_fill(bm, edges=edges, use_beauty=True)
    ext = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, vec=(0, t, 0), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    for f in bm.faces:
        f.material_index = 1 if f.normal.y > 0.5 else 0
    for f in bm.faces:
        f.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, coll)
    for s in surfaces:
        me.materials.append(_mat(s))
    mat.uv_box(ob)
    return ob


def _arc_pts_up(o):
    """Points of a notch (door) between its two floor corners, going up the left side, over the top, down the right."""
    if not o["arched"]:
        return [(o["u0"], o["z1"]), (o["u1"], o["z1"])]
    r = (o["u1"] - o["u0"]) / 2
    zs = o["z1"] - r
    cx = (o["u0"] + o["u1"]) / 2
    return [(o["u0"], zs)] + [(cx - r * math.cos(math.pi * k / 13), zs + r * math.sin(math.pi * k / 13)) for k in range(1, 13)] + [(o["u1"], zs)]


# ----------------------------------------------------------------------------- the room
class Room:
    """What room() returns: R.N R.S R.E R.W (wall meshes), R.floor, R.ceiling, R.anchors, R.openings, R.lo / R.hi (inner XY corners)."""

    def __init__(self, name):
        self.name = name
        self.anchors: dict = {}
        self.openings: dict = {}
        self.wallroot: dict = {}
        self.parts: list = []

    def __getitem__(self, k):
        return getattr(self, k)

    def inner(self, margin: float = 0.0):
        """(x0, y0, x1, y1) of the usable floor, inset by margin."""
        return (self.lo[0] + margin, self.lo[1] + margin, self.hi[0] - margin, self.hi[1] - margin)

    def wall_point(self, wall: str, along: float = 0.0, z: float = 0.0, inset: float = 0.0):
        """World point on the inner face of a wall (along = offset from the centre as for openings), pushed `inset` m into the room."""
        cx, cy = self.at
        x0, y0, x1, y1 = self.lo[0], self.lo[1], self.hi[0], self.hi[1]
        if wall == "N":
            return Vector((cx + along, y1 - inset, z))
        if wall == "S":
            return Vector((cx + along, y0 + inset, z))
        if wall == "E":
            return Vector((x1 - inset, cy + along, z))
        return Vector((x0 + inset, cy + along, z))

    def objects_of(self, wall: str | None = None):
        out = []
        for o in bpy.data.objects:
            if o.get("sk_room") == self.name and (wall is None or o.get("sk_wall") == wall):
                out.append(o)
        return out


def _tag_wall(ob, room, wall):
    ob["sk_room"], ob["sk_wall"] = room.name if hasattr(room, "name") else room, wall
    return ob


def tag_wall(ob, room, wall: str):
    """Declare that `ob` (wall dressing: a painting, a sconce) belongs to a wall, so cutaway hides it with the wall."""
    return _tag_wall(ob, room, wall)


def _u_of(wall: str, at: float) -> float:
    """World offset along a wall -> the wall's local X."""
    return {"N": at, "S": -at, "E": -at, "W": at}[wall]


def room(size=(6.0, 5.0, 2.8), at=(0.0, 0.0), floor="wood_floor", walls="plaster_warm", ceiling="plaster_clean", openings=(), trim: bool = True,
         name: str = "room", thick: float = 0.25, ceiling_kind: str = "flat", rise: float = 0.0, outside=None, floor_tint=None, wall_tint=None,
         skirting="dark_timber", cornice="plaster_clean", beams="dark_timber", beam_gap: float = 2.4, vault_axis: str = "Y", panel_wainscot=None, coll: str = "SET"):
    """Floor, four walls with real cut openings, a ceiling, skirting and cornice: one enclosed room whose inside spans
    size = (w, d, h) metres centred on `at`. Walls and ceiling are separately hideable (cutaway).
      walls     one surface name, or a dict {"N": ..., "S": ..., "E": ..., "W": ...}
      openings  [dict(wall="N", kind="door"|"window"|"gap", type=..., w=, h=, sill=, at=, arched=, id=, open=, vista...)]
      floor / ceiling  None leaves that part out (a glass room set into a bigger one shares its floor and ceiling)
      ceiling_kind  "flat" | "beams" (timber beams under a flat ceiling) | "vault" (barrel vault rising `rise` m, ridge along vault_axis)
      outside   surface of the outer wall faces (default: the same as inside)
    Returns a Room (see the class). R.openings[id] = {"centre", "normal", "w", "h", "root", "leaf"...} for lights.window_key."""
    w, d, h = size
    cx, cy = at
    R = Room(name)
    R.at, R.size, R.h, R.thick = (cx, cy), size, h, thick
    R.lo, R.hi = (cx - w / 2, cy - d / 2), (cx + w / 2, cy + d / 2)
    R.ceiling_kind, R.rise = ceiling_kind, rise
    ws = walls if isinstance(walls, dict) else {k: walls for k in WALLS}
    gable = set("NS" if vault_axis == "Y" else "EW") if ceiling_kind == "vault" and rise > 0 else set()
    R.top = h + rise if gable else h

    def arch_top(span):
        return lambda u, _s=span: h + rise * math.sqrt(max(0.0, 1 - (u / (_s / 2)) ** 2)) if abs(u) < _s / 2 else h

    # ---- floor
    R.floor = None
    if floor is not None:
        fl = Parts(f"{name}.floor", coll, kind="shell")
        fl.box((w + 2 * thick, d + 2 * thick, 0.3), (0, 0, -0.3), floor, floor_tint, bevel=0.0)
        R.floor = fl.build(at=(cx, cy, 0), recentre=False)
        R.floor["sk_surface"] = floor if isinstance(floor, str) else ""
    # ---- walls
    for W in WALLS:
        L = w + 2 * thick if W in "NS" else d
        span_inner = w if W in "NS" else d
        ops = []
        for spec in (o for o in openings if o["wall"] == W):
            ow, oh = float(spec.get("w", 1.0)), float(spec.get("h", 2.1))
            kind = spec.get("kind", "window")
            z0 = float(spec.get("sill", 0.0 if kind in ("door", "gap") else 0.9)) if kind == "window" else float(spec.get("sill", 0.0))
            u = _u_of(W, float(spec.get("at", 0.0)))
            ops.append(dict(spec=spec, u0=u - ow / 2, u1=u + ow / 2, z0=z0, z1=z0 + oh, arched=bool(spec.get("arched", spec.get("type") == "arched")), u=u))
        topf = arch_top(span_inner + (0 if W in "NS" else 0)) if W in gable else h
        wob = _wall_mesh(f"{name}.wall{W}", L, topf, thick, ops, (ws[W], outside or ws[W]), coll)
        wr = core.empty(f"{name}.wallroot{W}", (0, 0, 0), coll, 0.2)
        wob.parent = wr
        tag(wob, "wall", "shell")
        if W in "NS":
            wr.location = (cx, cy + (d / 2 if W == "N" else -d / 2), 0)
        else:
            wr.location = (cx + (w / 2 if W == "E" else -w / 2), cy, 0)
        wr.rotation_euler.z = math.radians(WALL_ROT[W])
        R.wallroot[W] = wr
        setattr(R, W, wob)
        _tag_wall(wr, R, W)
        _tag_wall(wob, R, W)
        # ---- the things that fill the openings (the wall root's world matrix is known here: no scene update per opening)
        Wm = Matrix.Translation(wr.location) @ Matrix.Rotation(math.radians(WALL_ROT[W]), 4, "Z")
        for o in ops:
            sp = dict(o["spec"])
            oid = sp.get("id") or f"{sp.get('kind', 'window')}_{W}{len(R.openings)}"
            kind = sp.get("kind", "window")
            ow, oh = o["u1"] - o["u0"], o["z1"] - o["z0"]
            if kind == "door":
                hd = door(sp.get("type", "panel"), ow, oh, open=sp.get("open", 0.0), frame=sp.get("frame", True), wall_t=thick, arched=o["arched"],
                          surface=sp.get("surface", "oak_planks"), surround=sp.get("surround"), hinge=sp.get("hinge", "left"), name=f"{name}.{oid}", coll=coll)
            elif kind == "window":
                hd = window(sp.get("type", "sash"), ow, oh, sill=o["z0"], glass=sp.get("glass", True), shutters=sp.get("shutters", False), wall_t=thick,
                            arched=o["arched"], sill_ledge=sp.get("sill_ledge", True), surround=sp.get("surround"), frame_surface=sp.get("frame_surface", "dark_timber"),
                            name=f"{name}.{oid}", coll=coll)
            else:
                hd = {"root": None}
            hd_root = hd.get("root")
            if hd_root is not None:
                hd_root.parent = wr
                hd_root.location = (o["u"], 0, o["z0"] if kind == "window" else 0.0)
                _tag_wall(hd_root, R, W)
            zc = o["z0"] + oh / 2
            centre = Wm @ Vector((o["u"], thick, zc))
            normal = Wm.to_3x3() @ Vector((0, -1, 0))
            hd.update(centre=centre, normal=normal.normalized(), w=ow, h=oh, wall=W, id=oid, kind=kind, z0=o["z0"])
            hd["inner_centre"] = Wm @ Vector((o["u"], 0.0, zc))
            R.openings[oid] = hd
        # ---- trim: skirting and cornice, broken at doorways
        if trim:
            tp = Parts(f"{name}.trim{W}", coll, kind="shell")
            cuts = sorted([(o["u0"], o["u1"]) for o in ops if o["z0"] <= 1e-6] + [])
            a = -span_inner / 2
            segs = []
            for c0, c1 in cuts:
                if c0 - 0.04 > a:
                    segs.append((a, c0 - 0.04))
                a = c1 + 0.04
            if a < span_inner / 2:
                segs.append((a, span_inner / 2))
            sk_h = 0.14 if h < 4 else 0.3
            for s0, s1 in segs:
                tp.box((s1 - s0, 0.025, sk_h), ((s0 + s1) / 2, -0.0125, 0.0), skirting, bevel=0.006)
                tp.box((s1 - s0, 0.012, 0.035), ((s0 + s1) / 2, -0.03, sk_h), skirting, bevel=0.004)
            if W not in gable:
                ch = 0.1 if h < 4 else 0.22
                tp.box((span_inner, ch, ch), (0, -ch / 2 + 0.002, h - ch), cornice, bevel=0.01)
            if panel_wainscot:
                for s0, s1 in segs:
                    tp.box((s1 - s0, 0.03, 0.95), ((s0 + s1) / 2, -0.015, sk_h), panel_wainscot, bevel=0.006)
                    tp.box((s1 - s0, 0.045, 0.05), ((s0 + s1) / 2, -0.0225, sk_h + 0.95), panel_wainscot, bevel=0.006)
            tr = tp.build(at=(0, 0, 0), recentre=False)
            tr.parent = wr
            _tag_wall(tr, R, W)
            R.parts.append(tr)
        # anchors
        R.anchors[f"wall_{W}"] = R.wall_point(W, 0.0, 0.0)
        R.anchors[f"wall_{W}_mid"] = R.wall_point(W, 0.0, h / 2)
    for k, (x, y) in {"NE": (R.hi[0], R.hi[1]), "NW": (R.lo[0], R.hi[1]), "SE": (R.hi[0], R.lo[1]), "SW": (R.lo[0], R.lo[1])}.items():
        R.anchors[f"corner_{k}"] = Vector((x, y, 0.0))
    R.anchors["centre"] = Vector((cx, cy, 0.0))
    for oid, hd in R.openings.items():
        R.anchors[f"open_{oid}"] = hd["centre"]
    # ---- ceiling
    R.ceiling = None
    if ceiling is not None:
        R.ceiling = _ceiling(R, ceiling, ceiling_kind, rise, vault_axis, thick, beams, beam_gap, cornice, coll)
        _tag_wall(R.ceiling, R, "C")
    return R


def _ceiling(R, surface, kind, rise, axis, thick, beams, beam_gap, cornice, coll):
    w, d, h = R.size
    cx, cy = R.at
    p = Parts(f"{R.name}.ceiling", coll, kind="shell")
    if kind == "vault" and rise > 0:
        span = w if axis == "Y" else d
        run = d if axis == "Y" else w
        n = 20
        pts = [(-span / 2 * math.cos(math.pi * k / n), h + rise * math.sin(math.pi * k / n)) for k in range(n + 1)]
        for (a0, a1) in zip(pts, pts[1:]):
            q = [(a0[0], a0[1]), (a1[0], a1[1]), (a1[0], a1[1] + 0.2), (a0[0], a0[1] + 0.2)]
            if axis == "Y":
                p.profile([(q[0][0], q[0][1]), (q[1][0], q[1][1]), (q[2][0], q[2][1]), (q[3][0], q[3][1])], -run / 2 - thick, run / 2 + thick, surface, bevel=0.0)
            else:
                p.profile([(q[0][0], q[0][1]), (q[1][0], q[1][1]), (q[2][0], q[2][1]), (q[3][0], q[3][1])], -run / 2 - thick, run / 2 + thick, surface, bevel=0.0)
        ob = p.build(at=(cx, cy, 0), rot_z=0 if axis == "Y" else 90, recentre=False)
        # ribs under the vault
        rp = Parts(f"{R.name}.ribs", coll, kind="shell")
        k = max(2, int(run / 3.2))
        for i in range(k + 1):
            y = -run / 2 + run * i / k
            prev = None
            for j in range(n + 1):
                x, z = pts[j][0] * 0.995, pts[j][1] - 0.04
                if prev:
                    rp.rod((prev[0], y, prev[1]), (x, y, z), 0.11, beams, seg=6)
                prev = (x, z)
        rib = rp.build(at=(cx, cy, 0), rot_z=0 if axis == "Y" else 90, recentre=False)
        rib.parent = ob
        _tag_wall(rib, R, "C")
        return ob
    p.box((w + 2 * thick, d + 2 * thick, 0.25), (0, 0, h), surface, bevel=0.0)
    if kind == "beams":
        along_y = w >= d * 0.0 and True
        n = max(2, int(w / beam_gap))
        for i in range(n):
            x = -w / 2 + w * (i + 0.5) / n
            p.box((0.22, d, 0.3), (x, 0, h - 0.3), beams, bevel=0.012)
        p.box((w, 0.26, 0.34), (0, -d / 2 + 0.13, h - 0.34), beams, bevel=0.012)
        p.box((w, 0.26, 0.34), (0, d / 2 - 0.13, h - 0.34), beams, bevel=0.012)
    return p.build(at=(cx, cy, 0), recentre=False)


def wall(a, b, h: float = 2.8, thickness: float = 0.2, openings=(), surface="plaster_clean", outside=None, name: str = "wall", coll: str = "SET"):
    """A free-standing wall from floor point a to floor point b (x, y) with real openings: a partition, a garden wall, a house side.
    The wall runs along its local X from a to b; the FACE ON THE RIGHT of the walking direction a -> b is the face doors and
    windows open toward (their 'interior', y = 0 in the wall frame); thickness grows to the left. openings are dicts like room()'s,
    but `at` is the offset of the opening's centre from the wall's middle along a -> b.
    Returns {"root", "mesh", "openings": {id: handle}} (handles as in room())."""
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    L = math.hypot(bx - ax, by - ay)
    rot = math.degrees(math.atan2(by - ay, bx - ax))
    ops = []
    for spec in openings:
        ow, oh = float(spec.get("w", 1.0)), float(spec.get("h", 2.1))
        kind = spec.get("kind", "window")
        z0 = float(spec.get("sill", 0.9 if kind == "window" else 0.0))
        u = float(spec.get("at", 0.0))
        ops.append(dict(spec=spec, u0=u - ow / 2, u1=u + ow / 2, z0=z0, z1=z0 + oh, arched=bool(spec.get("arched", spec.get("type") == "arched")), u=u))
    mesh = _wall_mesh(f"{name}.mesh", L, h, thickness, ops, (surface, outside or surface), coll)
    root = core.empty(name, (0, 0, 0), coll, 0.2)
    mesh.parent = root
    tag(mesh, "wall", "shell")
    root.location = ((ax + bx) / 2, (ay + by) / 2, 0.0)
    root.rotation_euler.z = math.radians(rot)
    handles = {}
    for o in ops:
        sp = o["spec"]
        kind = sp.get("kind", "window")
        oid = sp.get("id") or f"{kind}{len(handles)}"
        ow, oh = o["u1"] - o["u0"], o["z1"] - o["z0"]
        if kind == "door":
            hd = door(sp.get("type", "panel"), ow, oh, open=sp.get("open", 0.0), wall_t=thickness, arched=o["arched"], surface=sp.get("surface", "oak_planks"),
                      surround=sp.get("surround"), name=f"{name}.{oid}", coll=coll)
        elif kind == "window":
            hd = window(sp.get("type", "sash"), ow, oh, sill=o["z0"], wall_t=thickness, arched=o["arched"], shutters=sp.get("shutters", False), name=f"{name}.{oid}", coll=coll)
        else:
            hd = {"root": None}
        if hd.get("root") is not None:
            hd["root"].parent = root
            hd["root"].location = (o["u"], 0, o["z0"] if kind == "window" else 0.0)
        bpy.context.view_layer.update()
        hd.update(centre=root.matrix_world @ Vector((o["u"], thickness, o["z0"] + oh / 2)), normal=(root.matrix_world.to_3x3() @ Vector((0, -1, 0))).normalized(), w=ow, h=oh, id=oid, kind=kind)
        handles[oid] = hd
    return {"root": root, "mesh": mesh, "openings": handles}


# ----------------------------------------------------------------------------- doors
def door(kind: str = "panel", width: float = 1.0, height: float = 2.1, open: float = 0.0, frame: bool = True, wall_t: float = 0.25, arched: bool = False,
         surface: str = "oak_planks", surround=None, hinge: str = "left", name: str = "door", coll: str = "SET", handle: bool = True):
    """A door in a wall opening, in wall-local coordinates (centred on x=0, floor at z=0, interior face y=0, exterior y=wall_t).
    kind: plank (boards with iron bands) | panel (raised panels) | double | arched (arched head) | glass (office glass door).
    The leaf (or leaves) hang on hinges and swing INTO the room when `open` > 0 degrees: animate leaf.rotation_euler.z.
    Returns {"root", "leaf", "leaves", "frame"}."""
    root = core.empty(name, (0, 0, 0), coll, 0.2)
    kind = "arched" if arched and kind in ("panel", "plank") else kind
    sur = surround or ("castle_stone" if kind == "arched" or arched else "dark_timber")
    leaves = []
    n_leaf = 2 if kind == "double" else 1
    lw = width / n_leaf
    ty = wall_t * 0.5
    for li in range(n_leaf):
        side = ("left" if li == 0 else "right") if kind == "double" else hinge
        sgn = 1 if side == "left" else -1                       # leaf extends +x from a left hinge, -x from a right hinge
        hx = -width / 2 if side == "left" else width / 2
        p = Parts(f"{name}.leaf{li}", coll, kind="shell")
        thk = 0.06
        z_top = height
        sx0, sx1 = (0.0, lw - 0.012) if sgn > 0 else (-(lw - 0.012), 0.0)
        e = sgn * (lw - 0.012)
        if arched:
            # leaf-local x runs from the hinge (0) to the free edge (e); the head follows the opening's round arch
            r_ = width / 2
            zs_ = height - r_

            def ztop(lx, _hx=hx, _r=r_, _zs=zs_):
                gx = _hx + lx
                return _zs + math.sqrt(max(0.0, _r * _r - gx * gx)) - 0.01

            poly = [(0.0, 0.0), (e, 0.0)] + [(e * (1 - i / 16), ztop(e * (1 - i / 16))) for i in range(17)]
            p.profile(poly, -thk / 2, thk / 2, surface, bevel=0.004)
        else:
            p.box((lw - 0.012, thk, height - 0.01), (sgn * (lw - 0.012) / 2, 0, 0.005), surface, bevel=0.006)
        xc = sgn * (lw - 0.012) / 2
        if kind in ("plank", "arched", "double") or arched:
            nb = max(3, int(lw / 0.2))
            for i in range(1, nb):
                p.box((0.008, 0.012, height * 0.86), (sgn * (lw - 0.012) * i / nb, -thk / 2 - 0.002, 0.02), "dark_timber", bevel=0.0)
            for zb in (0.35, height * 0.62 if not arched else min(height * 0.62, height - width / 2 - 0.1)):
                p.box((lw * 0.94, 0.012, 0.1), (xc, -thk / 2 - 0.006, zb), "iron_dark", bevel=0.003)
        elif kind == "panel":
            pw = lw - 0.3
            for (zb, ph) in ((0.2, 0.75), (1.1, 0.8), (1.0 + 0.05, 0.0)):
                if ph > 0 and zb + ph < height - 0.1:
                    p.box((pw, 0.018, ph), (xc, -thk / 2 - 0.009, zb), surface, tint="#C9A67F", bevel=0.006)
                    p.box((pw, 0.018, ph), (xc, thk / 2 + 0.009, zb), surface, tint="#C9A67F", bevel=0.006)
        elif kind == "glass":
            p.g.clear()
            p.box((lw - 0.012, thk, 0.1), (xc, 0, 0.0), "brushed_metal", bevel=0.004)
            p.box((lw - 0.012, thk, 0.1), (xc, 0, height - 0.1), "brushed_metal", bevel=0.004)
            p.box((0.06, thk, height), (xc - sgn * (lw - 0.012) / 2 + sgn * 0.03, 0, 0), "brushed_metal", bevel=0.004)
            p.box((0.06, thk, height), (xc + sgn * (lw - 0.012) / 2 - sgn * 0.03, 0, 0), "brushed_metal", bevel=0.004)
            p.box((lw - 0.1, 0.012, height - 0.22), (xc, 0, 0.1), mat.surface("glass"), bevel=0.0)
            p.box((lw * 0.5, 0.02, 0.012), (xc, -0.03, 1.0), mat.solid("#F2F2F2", 0.5), bevel=0.0)       # frosted privacy strip
        if handle:
            hx_ = sgn * (lw - 0.1)
            hm = mat.surface("brushed_metal") if kind in ("glass", "panel") else mat.surface("iron_dark")
            if kind == "arched" or arched or kind in ("plank", "double"):
                p.box((0.05, 0.02, 0.05), (hx_, -thk / 2 - 0.02, height * 0.46), hm, bevel=0.004, mid=True)
            else:
                p.box((0.12, 0.05, 0.022), (hx_ - sgn * 0.05, -thk / 2 - 0.035, 1.0), hm, bevel=0.004, mid=True)
                p.box((0.04, 0.04, 0.04), (hx_ - sgn * 0.1, -thk / 2 - 0.015, 1.0), hm, bevel=0.003, mid=True)
        leaf = p.build(at=(hx, ty, 0.0), recentre=False)
        leaf.parent = root
        leaf.rotation_euler.z = math.radians(-open * sgn)
        leaves.append(leaf)
    fr = None
    if frame:
        fp = Parts(f"{name}.frame", coll, kind="shell")
        if kind == "arched" or arched:
            r = width / 2
            zs = height - r
            fp.box((0.22, wall_t + 0.04, zs), (-width / 2 - 0.11, wall_t / 2, 0), sur, bevel=0.02)
            fp.box((0.22, wall_t + 0.04, zs), (width / 2 + 0.11, wall_t / 2, 0), sur, bevel=0.02)
            nseg = 11
            for k in range(nseg):
                a = math.pi * (k + 0.5) / nseg
                c = (math.cos(a) * (r + 0.11), wall_t / 2, zs + math.sin(a) * (r + 0.11))
                fp.box((0.22, wall_t + 0.04, 2 * (r + 0.11) * math.tan(math.pi / (2 * nseg)) + 0.01), (c[0], c[1], c[2]), sur, rot=(0, -math.degrees(a), 0), bevel=0.015, mid=True)
        else:
            fp.box((0.1, wall_t + 0.08, height + 0.1), (-width / 2 - 0.05, wall_t / 2, 0), sur, bevel=0.012)
            fp.box((0.1, wall_t + 0.08, height + 0.1), (width / 2 + 0.05, wall_t / 2, 0), sur, bevel=0.012)
            fp.box((width + 0.2, wall_t + 0.08, 0.1), (0, wall_t / 2, height), sur, bevel=0.012)
        fp.box((width, wall_t, 0.03), (0, wall_t / 2, 0), sur, bevel=0.004)             # threshold
        fr = fp.build(at=(0, 0, 0), recentre=False)
        fr.parent = root
    tag(root, "door", "shell")
    return {"root": root, "leaf": leaves[0], "leaves": leaves, "frame": fr}


# ----------------------------------------------------------------------------- windows
def _clip_line(p0, p1, xmin, xmax, zmin, zmax):
    """Liang-Barsky: the part of the segment p0-p1 inside the rectangle, or None."""
    (x0, z0), (x1, z1) = p0, p1
    dx, dz = x1 - x0, z1 - z0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - xmin), (dx, xmax - x0), (-dz, z0 - zmin), (dz, zmax - z0)):
        if abs(pp) < 1e-9:
            if qq < 0:
                return None
            continue
        r = qq / pp
        if pp < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
    if t1 - t0 < 0.02:
        return None
    return (x0 + t0 * dx, z0 + t0 * dz), (x0 + t1 * dx, z0 + t1 * dz)


def window(kind: str = "sash", width: float = 1.2, height: float = 1.6, sill: float = 0.9, glass: bool = True, sill_ledge: bool = True,
           shutters: bool = False, wall_t: float = 0.25, arched: bool = False, surround=None, frame_surface: str = "dark_timber", name: str = "window", shutter_tint=None,
           coll: str = "SET"):
    """A window in a wall opening (wall-local: centred on x=0, its bottom at z=0 of the returned root, interior face y=0).
    kind: sash (grid of panes) | arched (round head, tracery bar) | lattice (leaded diamonds) | office (big pane, slim metal frame)
          | shop (plate glass with a stall board). shutters=True adds two leaves folded back flat against the interior wall.
    glass=True fits a clear pane (blended, casts no shadow so the key light comes through).
    Returns {"root", "glass", "frame"}."""
    root = core.empty(name, (0, 0, 0), coll, 0.2)
    arched = arched or kind == "arched"
    sur = surround or ("castle_stone" if arched or kind == "lattice" else "plaster_clean")
    if kind in ("office", "shop"):
        frame_surface = "brushed_metal"
    p = Parts(f"{name}.frame", coll, kind="shell")
    fw = 0.07 if kind not in ("office", "shop") else 0.045
    ym = wall_t * 0.5
    r = width / 2
    zs = height - r if arched else height
    # frame bars
    p.box((fw, 0.07, zs), (-width / 2 + fw / 2, ym, 0), frame_surface, bevel=0.006)
    p.box((fw, 0.07, zs), (width / 2 - fw / 2, ym, 0), frame_surface, bevel=0.006)
    p.box((width, 0.07, fw), (0, ym, 0), frame_surface, bevel=0.006)
    if arched:
        for k in range(12):
            a0, a1 = math.pi * k / 12, math.pi * (k + 1) / 12
            c0 = ((r - fw / 2) * math.cos(a0), zs + (r - fw / 2) * math.sin(a0))
            c1 = ((r - fw / 2) * math.cos(a1), zs + (r - fw / 2) * math.sin(a1))
            p.rod((c0[0], ym, c0[1]), (c1[0], ym, c1[1]), fw * 0.5, frame_surface, seg=6)
        p.box((width, 0.06, fw * 0.8), (0, ym, zs - fw * 0.4), frame_surface, bevel=0.004)
        p.box((fw * 0.7, 0.06, height - fw), (0, ym, fw * 0.5), frame_surface, bevel=0.004)
    else:
        p.box((width, 0.07, fw), (0, ym, height - fw), frame_surface, bevel=0.006)
    if kind == "sash":
        nx = max(2, int(width / 0.45))
        ny = max(2, int(height / 0.45))
        for i in range(1, nx):
            p.box((0.022, 0.05, height - 2 * fw), (-width / 2 + width * i / nx, ym, fw), frame_surface, bevel=0.003)
        for j in range(1, ny):
            p.box((width - 2 * fw, 0.05, 0.022), (0, ym, height * j / ny), frame_surface, bevel=0.003)
    elif kind == "lattice":
        lo_x, hi_x, lo_z, hi_z = -width / 2 + fw, width / 2 - fw, fw, zs - 0.0
        for i in range(-int(height / 0.2) - 2, int(width / 0.2) + 3):
            x0 = -width / 2 + i * 0.2
            for sgn_ in (1, -1):
                seg = _clip_line((x0, lo_z), (x0 + sgn_ * (hi_z - lo_z), hi_z), lo_x, hi_x, lo_z, hi_z)
                if seg:
                    (ax, az), (bx, bz) = seg
                    p.rod((ax, ym, az), (bx, ym, bz), 0.006, "iron_dark", seg=4)
    elif kind == "office":
        p.box((0.03, 0.05, height - 2 * fw), (width / 3 - width / 2 + width / 6, ym, fw), frame_surface, bevel=0.003) if width > 1.8 else None
        if width > 1.8:
            p.box((0.03, 0.05, height - 2 * fw), (width / 6, ym, fw), frame_surface, bevel=0.003)
    elif kind == "shop":
        p.box((width, 0.07, 0.35), (0, ym, 0), "dark_timber", bevel=0.01)
    if glass:
        gm = mat.surface("glass")
        if arched:
            pts = [(-width / 2 + fw, fw), (width / 2 - fw, fw), (width / 2 - fw, zs)] + _arc_pts(0, zs, r - fw, 10) + [(-width / 2 + fw, zs)]
            p.profile(pts, ym - 0.004, ym + 0.004, gm, bevel=0.0)
        else:
            p.box((width - 2 * fw, 0.008, height - 2 * fw), (0, ym, fw), gm, bevel=0.0)
    fr = p.build(at=(0, 0, 0), recentre=False)
    fr.parent = root
    gl = None
    # surround: reveal and sill ledge
    sp = Parts(f"{name}.surround", coll, kind="shell")
    if sill_ledge:
        sp.box((width + 0.2, wall_t + 0.1, 0.045), (0, wall_t / 2 - 0.02, -0.045), sur, bevel=0.01)
    if kind != "shop" and wall_t < 0.6:
        sp.box((0.09, 0.03, zs + 0.08), (-width / 2 - 0.045, -0.015, -0.02), sur, bevel=0.006)
        sp.box((0.09, 0.03, zs + 0.08), (width / 2 + 0.045, -0.015, -0.02), sur, bevel=0.006)
        if not arched:
            sp.box((width + 0.18, 0.03, 0.09), (0, -0.015, height - 0.02), sur, bevel=0.006)
    if arched and wall_t >= 0.5:
        nseg = 11
        for k in range(nseg):
            a = math.pi * (k + 0.5) / nseg
            c = ((r + 0.1) * math.cos(a), wall_t + 0.015, zs + (r + 0.1) * math.sin(a))
            sp.box((0.2, 0.05, 2 * (r + 0.1) * math.tan(math.pi / (2 * nseg)) + 0.01), c, sur, rot=(0, -math.degrees(a), 0), bevel=0.012, mid=True)
            c2 = ((r + 0.1) * math.cos(a), -0.015, zs + (r + 0.1) * math.sin(a))
            sp.box((0.2, 0.05, 2 * (r + 0.1) * math.tan(math.pi / (2 * nseg)) + 0.01), c2, sur, rot=(0, -math.degrees(a), 0), bevel=0.012, mid=True)
    sg = sp.build(at=(0, 0, 0), recentre=False)
    sg.parent = root
    if shutters:
        for sgn in (-1, 1):
            shp = Parts(f"{name}.shutter", coll, kind="shell")
            shp.box((width / 2 - 0.01, 0.035, zs), (sgn * (width / 4 + 0.0), 0, 0), "oak_planks", tint=shutter_tint or "#6B4A2E", bevel=0.005)
            for k in range(1, 4):
                shp.box((width / 2 - 0.03, 0.012, 0.035), (sgn * (width / 4), -0.02, zs * k / 4), "dark_timber", bevel=0.003)
            sh = shp.build(at=(sgn * (width / 2 + 0.04), -0.045, 0), recentre=False)       # folded back flat against the wall beside the window
            sh.parent = root
    tag(root, "window", "shell")
    return {"root": root, "frame": fr, "glass": gl, "surround": sg}


# ----------------------------------------------------------------------------- vistas: what the windows look out on
def _sky_mat(zenith="#6FA6E6", horizon="#CFE6F7", name="SK_vista_sky", clouds: float = 0.5, strength: float = 1.0):
    key = f"{name}_{zenith}_{horizon}_{clouds}_{strength}"
    m = bpy.data.materials.get(key)
    if m:
        return m
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    uv = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = core.hex_rgba(horizon)
    ramp.color_ramp.elements[1].color = core.hex_rgba(zenith)
    ramp.color_ramp.elements[1].position = 0.85
    nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    if clouds > 0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (0.045, 0.16, 0.05)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 3.0
        nz.inputs["Detail"].default_value = 5.0
        nt.links.new(mp.outputs[0], nz.inputs["Vector"])
        cr = nt.nodes.new("ShaderNodeValToRGB")
        cr.color_ramp.elements[0].position = 0.5 - 0.15 * clouds
        cr.color_ramp.elements[1].position = 0.72
        nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.inputs["B"].default_value = (1, 1, 1, 1)
        nt.links.new(col, mx.inputs["A"])
        nt.links.new(cr.outputs["Color"], mx.inputs["Factor"])
        col = mx.outputs["Result"]
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    nt.links.new(col, em.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def _lerp_hex(a, b, k):
    ha, hb = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(int(ha[i:i + 2], 16) * (1 - k) + int(hb[i:i + 2], 16) * k):02X}" for i in (0, 2, 4))


def vista(room_, wall: str, kind: str = "hills", distance: float = 16.0, seed: int = 1, strength: float = 1.0, night: bool | None = None, coll: str = "SET"):
    """What the windows and doors of one wall look out on: a lit-from-itself backdrop of real geometry placed outside the wall
    (it hides with the wall when the camera is outside). kind:
      sky | hills (ridges, a castle on the far one) | garden (lawn, hedge, trees) | street (terraced facades across the road)
      | rooftops (roofs below eye level) | city_day | night_city (lit windows).
    The backdrop is emissive, so it never changes the room's light, and it is wide enough to be seen through every opening of the wall."""
    rnd = random.Random(seed)
    W = wall
    wr = room_.wallroot[W]
    span = (room_.size[0] if W in "NS" else room_.size[1]) + 40
    t = room_.thick
    d0 = t + distance
    nightv = kind == "night_city" if night is None else night
    Z = 40.0
    gstr = strength * (0.2 if nightv and kind in ("garden", "hills", "sky") else 1.0)       # lawns and trees are dark at night; the sky keeps its own strength
    sky_top, sky_hor = ("#0A1230", "#2B3560") if nightv else ("#6FA6E6", "#D7EBF7")
    parts = []

    def card(w_, h_, y, z0, matl, name):
        p = Parts(f"{room_.name}.vista{W}.{name}", coll, kind="shell")
        bm = p._bm(matl, None, 0.0)
        vs = [bm.verts.new((-w_ / 2, y, z0)), bm.verts.new((w_ / 2, y, z0)), bm.verts.new((w_ / 2, y, z0 + h_)), bm.verts.new((-w_ / 2, y, z0 + h_))]
        f = bm.faces.new(vs)
        uvl = bm.loops.layers.uv.new("UVMap")
        for lp, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = (u, v)
        return p

    # sky wall far away
    sk = card(700.0, Z * 2.0, d0 + 70, -15, _sky_mat(sky_top, sky_hor, clouds=0.0 if nightv else 0.6, strength=strength), "sky")
    parts.append(sk)
    # ground plane: the earth the room stands on
    gp = Parts(f"{room_.name}.vista{W}.ground", coll, kind="shell")
    gcol = {"hills": "#6E9A52", "garden": "#5F9444", "street": "#4A4B50", "rooftops": "#7A6A5E", "city_day": "#6A6F76", "night_city": "#12141F", "sky": "#6E9A52"}[kind]
    gp.box((700.0, 140, 0.05), (0, t + 70, -0.12), mat.emit(_lerp_hex(gcol, sky_hor, 0.1 if not nightv else 0.0), 0.9 * gstr, f"SK_vg_{gcol}_{gstr}"), bevel=0.0) if kind != "rooftops" else None
    if kind != "rooftops":
        parts.append(gp)
    if kind == "hills":
        for li, (dist_, col, hmax, k) in enumerate(((distance + 12, "#6C9A55", 4.0, 0.25), (distance + 30, "#7BA574", 8.0, 0.45), (distance + 52, "#9DB9C4", 14.0, 0.7))):
            hp = Parts(f"{room_.name}.vista{W}.ridge{li}", coll, kind="shell")
            m_ = mat.emit(_lerp_hex(col, sky_hor, k * 0.55), 0.95 * gstr, f"SK_ridge{li}_{col}")
            n = 40
            ph = rnd.uniform(0, 6)
            top = [(-span * 1.2 + span * 2.4 * i / n, hmax * (0.55 + 0.45 * math.sin(i * 0.37 + ph) * math.cos(i * 0.11 + ph * 2)) + rnd.uniform(-0.3, 0.3)) for i in range(n + 1)]
            hp.profile([(-span * 1.2, -0.2)] + top + [(span * 1.2, -0.2)], dist_, dist_ + 1.5, m_, bevel=0.0)
            parts.append(hp)
        # a distant castle on the far ridge
        cp = Parts(f"{room_.name}.vista{W}.castle", coll, kind="shell")
        cm = mat.emit(_lerp_hex("#A8A6A0", sky_hor, 0.5), 0.95 * gstr, "SK_far_castle")
        bx = rnd.uniform(-6, 6)
        yy = distance + 30
        for (dx, wd, hh) in ((0, 7.0, 5.0), (-4.5, 2.2, 9.0), (4.6, 2.2, 8.0), (0.0, 2.6, 8.4)):
            cp.box((wd, 2.4, hh), (bx + dx, yy + 3.0, 5.5), cm, bevel=0.0)
        for dx in (-4.5, 4.6, 0.0):
            cp.box((2.6, 2.6, 1.2), (bx + dx, yy + 3.0, 5.5 + (9.0 if dx == -4.5 else 8.0 if dx == 4.6 else 8.4)), mat.emit("#B04A3A", 0.9 * gstr, "SK_far_roof"), bevel=0.0)
        parts.append(cp)
    elif kind == "garden":
        hp = Parts(f"{room_.name}.vista{W}.garden", coll, kind="shell")
        hp.box((span * 2, 1.2, 1.5), (0, t + 5.0, 0), mat.emit("#3E7A3A", 0.9 * gstr, "SK_hedge"), bevel=0.2)
        for i in range(9):
            x = -22 + i * 5.5 + rnd.uniform(-1.2, 1.2)
            y = t + rnd.uniform(9, 16)
            h_ = rnd.uniform(5.5, 8.5)
            hp.cyl(0.35, h_ * 0.55, (x, y, 0), mat.emit("#5B4630", 0.7 * gstr, "SK_trunk"), seg=8)
            for k, (dx, dy, dz, rr) in enumerate(((0, 0, 0.6, 2.6), (1.4, 0.4, 0.4, 1.9), (-1.4, -0.3, 0.45, 2.0))):
                hp.ball(rr, (x + dx, y + dy, h_ * 0.55 + dz), mat.emit(_lerp_hex("#4F8F45", "#2F6A35", rnd.random()), 0.9 * gstr, f"SK_tree{k}"), sub=2)
        for i in range(40):
            hp.ball(0.35, (rnd.uniform(-9, 9), t + rnd.uniform(2, 4.5), 0.2), mat.emit(rnd.choice(["#E8A0B8", "#F2E27A", "#F6F1E4", "#B58BD6"]), 1.0 * gstr, "SK_bloom"), sub=1)
        parts.append(hp)
        hl = Parts(f"{room_.name}.vista{W}.hills", coll, kind="shell")
        hl.profile([(-span, -0.2)] + [(-span + span * 2 * i / 30, 6 + 3 * math.sin(i * 0.5 + 1)) for i in range(31)] + [(span, -0.2)], distance + 40, distance + 41,
                   mat.emit(_lerp_hex("#8CB59A", sky_hor, 0.4), 0.95 * gstr, "SK_hill_far"), bevel=0.0)
        parts.append(hl)
    elif kind in ("street", "city_day", "night_city", "rooftops"):
        bp = Parts(f"{room_.name}.vista{W}.blocks", coll, kind="shell")
        wp = Parts(f"{room_.name}.vista{W}.panes", coll, kind="shell")
        lit = mat.emit("#FFD28A", 2.0 * gstr, "SK_pane_lit")
        lit2 = mat.emit("#CFE6FF", 1.5 * gstr, "SK_pane_lit2")
        dark = mat.emit("#2B3A52" if not nightv else "#10162A", 0.8 * gstr, "SK_pane_dark")
        x = -span
        rows = [(d0 + (4.0 if kind == "street" else 20), 1.0, 1.0)]
        if kind in ("city_day", "night_city"):
            rows = [(d0 + 18, 1.0, 1.0), (d0 + 40, 1.6, 0.8), (d0 + 66, 2.2, 0.7)]
        for ri, (yy, hs, ws) in enumerate(rows):
            x = -span * 0.9
            while x < span * 0.9:
                bw = rnd.uniform(5.5, 10.0) * ws if kind != "street" else rnd.uniform(5.0, 7.0)
                if kind == "street":
                    bh = rnd.uniform(9.0, 14.0)
                elif kind == "rooftops":
                    bh = rnd.uniform(-3.5, 1.0)
                else:
                    bh = rnd.uniform(10, 38) * hs
                base_col = rnd.choice(["#B9AA95", "#C9B8A0", "#A59A8E", "#B58E7A"]) if kind == "street" else rnd.choice(["#8E99A8", "#A5AFBA", "#7C8796", "#B7C0C9"]) if kind == "city_day" else rnd.choice(["#1B2136", "#222A42", "#161B2E"]) if nightv else rnd.choice(["#B07A5C", "#9B6A52", "#8C8680"])
                col = _lerp_hex(base_col, sky_hor, min(0.75, ri * 0.28 + (0.0 if kind == "street" else 0.12)))
                h_top = bh if kind != "rooftops" else bh + 3.5
                body_h = h_top + 6
                bp.box((bw - 0.2, 7.0, body_h), (x + bw / 2, yy + 3.5, -6.0), mat.emit(col, 0.95 * gstr, f"SK_blk_{col}"), bevel=0.0)
                if kind == "rooftops":
                    bp.box((bw - 0.4, 6.0, 1.6), (x + bw / 2, yy + 3.5, h_top), mat.emit("#8A4B36", 0.9 * gstr, "SK_roofbox"), bevel=0.0)
                    bp.box((0.5, 0.5, 2.4), (x + bw * 0.7, yy + 3.2, h_top + 1.6), mat.emit("#6D5A4C", 0.9 * gstr, "SK_chim"), bevel=0.0)
                else:
                    cols = max(2, int(bw / 1.7))
                    rows_n = max(1, int((h_top - 1.0) / 2.6))
                    for cj in range(cols):
                        for rj in range(rows_n):
                            if kind == "street" and rj == 0 and False:
                                continue
                            on = rnd.random() < (0.45 if nightv else 0.08)
                            m_ = lit if on and rnd.random() < 0.7 else (lit2 if on else dark)
                            px, pz = x + 0.6 + (bw - 1.2) * (cj + 0.5) / cols, 1.2 + rj * 2.6
                            wp.box((0.9, 0.04, 1.5), (px, yy - 0.01, pz), m_, bevel=0.0)
                x += bw
        parts += [bp, wp]
        if kind == "street":
            rp = Parts(f"{room_.name}.vista{W}.road", coll, kind="shell")
            rp.box((span * 2, 8.0, 0.06), (0, t + 6.0, -0.1), mat.emit("#55565C", 0.9 * gstr, "SK_road"), bevel=0.0)
            rp.box((span * 2, 0.35, 0.18), (0, t + 2.1, -0.05), mat.emit("#9A988F", 0.9 * gstr, "SK_kerb"), bevel=0.0)
            parts.append(rp)
    out = []
    for p in parts:
        ob = p.build(at=(0, 0, 0), recentre=False)
        ob.parent = wr
        ob.location = (0, 0, 0)
        for ch in ob.children:
            ch.visible_shadow = False
            ch.visible_glossy = False
        _tag_wall(ob, room_, "V")                 # a vista is for looking OUT of the room: cutaway hides it for cameras outside
        ob["sk_vista"] = kind
        ob["sk_vista_wall"] = W
        out.append(ob)
    room_.__dict__.setdefault("vistas", {})[W] = kind
    return out


# ----------------------------------------------------------------------------- the cutaway
def _hidden_state(room_, p: Vector, ceiling: bool | None = None, margin: float = 0.0):
    x0, y0, x1, y1 = room_.lo[0], room_.lo[1], room_.hi[0], room_.hi[1]
    hide = set()
    if p.y < y0 - margin:
        hide.add("S")
    if p.y > y1 + margin:
        hide.add("N")
    if p.x < x0 - margin:
        hide.add("W")
    if p.x > x1 + margin:
        hide.add("E")
    if (ceiling is None and p.z > room_.h - 0.02) or ceiling:
        hide.add("C")
    if p.z > room_.h + 0.5 or not (x0 - 0.2 <= p.x <= x1 + 0.2 and y0 - 0.2 <= p.y <= y1 + 0.2):
        hide.add("V")
    return hide


def _set_hidden(room_, hide: set, frame: int | None = None):
    for tagw in ("N", "S", "E", "W", "C", "V"):
        state = tagw in hide
        for o in room_.objects_of(tagw):
            for ob in [o, *o.children_recursive]:
                if frame is None:
                    ob.hide_render = ob.hide_viewport = state
                else:
                    ob.hide_render = ob.hide_viewport = state
                    core.key_frame(ob, "hide_render", frame, interp="CONSTANT")
                    core.key_frame(ob, "hide_viewport", frame, interp="CONSTANT")


def cutaway(room_, cam, at_frame=None, ceiling: bool | None = None, margin: float = 0.0):
    """Hide the walls (and the ceiling) that stand between a camera and the room, in the render and the viewport, so one
    enclosed room serves cameras on any side. cam: a camera object, a point, or a Vector. A wall is hidden when the camera is
    beyond its plane (outside the room on that side); the ceiling is hidden when the camera is above it (or ceiling=True); the
    vistas behind the windows are hidden whenever the camera is outside the room (they are only for looking out of it).
      at_frame=None      set the state now (static)
      at_frame=(f0, f1)  switch to this state at f0 and back to the room's default at f1 + 1 (CONSTANT keys), so each view of
                         a shot can have its own cutaway
      at_frame=f         from frame f on
    Wall dressing (objects tagged with arch.tag_wall) hides with its wall. Returns the set of hidden parts, e.g. {"S", "C"}."""
    p = core.point_of(cam)
    hide = _hidden_state(room_, p, ceiling, margin)
    if at_frame is None:
        _set_hidden(room_, hide)
        return hide
    f0, f1 = (at_frame, None) if isinstance(at_frame, int) else at_frame
    if f0 > 1:
        _set_hidden(room_, set(), f0 - 1)                    # before f0 the room is whole
    _set_hidden(room_, hide, f0)
    if f1 is not None:
        _set_hidden(room_, set(), f1 + 1)
    return hide


def track_cutaway(room_, cam_ob, f0: int, f1: int, step: int = 1, ceiling: bool | None = None, margin: float = 0.0):
    """Follow an animated camera: evaluate it every `step` frames in f0..f1 and key the walls and ceiling whenever the hidden set changes."""
    last = None
    changes = []
    for f in range(f0, f1 + 1, step):
        sc = bpy.context.scene
        sc.frame_set(f)
        bpy.context.view_layer.update()
        hide = _hidden_state(room_, cam_ob.matrix_world.translation.copy(), ceiling, margin)
        if hide != last:
            changes.append((f, hide))
            last = hide
    for f, hide in changes:
        _set_hidden(room_, hide, f)
    bpy.context.scene.frame_set(f0)
    return changes


# ----------------------------------------------------------------------------- structure: columns, pilasters, arches, beams, stairs, platforms
def column(kind: str = "round", height: float = 4.0, radius: float = 0.3, at=(0, 0, 0), surface: str = "castle_stone", capital: bool = True, name: str = "column",
           coll: str = "SET", rot_z: float = 0.0, base: bool = True):
    """A free-standing column on a plinth: round | square | fluted (round with grooves). Origin at the foot centre."""
    p = Parts(name, coll, "column")
    r = radius
    if base:
        p.box((r * 2.5, r * 2.5, r * 0.5), (0, 0, 0), surface, bevel=0.02)
    z0 = r * 0.5 if base else 0.0
    sh = height - z0 - (r * 0.55 if capital else 0.0)
    if kind == "square":
        p.box((r * 1.7, r * 1.7, sh), (0, 0, z0), surface, bevel=0.02)
    else:
        seg = 24
        p.cyl(r * 0.92, sh, (0, 0, z0), surface, top=r * 0.82, seg=seg)
        if kind == "fluted":
            for i in range(14):
                a = 2 * math.pi * i / 14
                p.box((0.03, 0.025, sh * 0.9), (math.cos(a) * r * 0.9, math.sin(a) * r * 0.9, z0 + sh * 0.05), surface, rot=(0, 0, math.degrees(a)), tint="#9A9488", bevel=0.0)
    if capital:
        ct = height - r * 0.55
        p.box((r * 2.3, r * 2.3, r * 0.25), (0, 0, ct), surface, bevel=0.02)
        p.box((r * 2.6, r * 2.6, r * 0.3), (0, 0, ct + r * 0.25), surface, bevel=0.02)
    ob = p.build(at=at, rot_z=rot_z, recentre=False)
    return ob


def pilaster(height: float = 4.0, width: float = 0.5, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "castle_stone", proud: float = 0.16, name: str = "pilaster", coll: str = "SET"):
    """A flat column set into a wall: origin at its back (the wall face), the shaft projects `proud` m toward -Y."""
    p = Parts(name, coll, "pilaster")
    p.box((width * 1.3, proud + 0.04, 0.3), (0, -(proud + 0.04) / 2, 0), surface, bevel=0.015)
    p.box((width, proud, height - 0.65), (0, -proud / 2, 0.3), surface, bevel=0.012)
    p.box((width * 1.35, proud + 0.05, 0.2), (0, -(proud + 0.05) / 2, height - 0.35), surface, bevel=0.015)
    p.box((width * 1.5, proud + 0.08, 0.15), (0, -(proud + 0.08) / 2, height - 0.15), surface, bevel=0.015)
    return p.build(at=at, rot_z=rot_z, recentre=False)


def arch(width: float = 3.0, height: float = 4.0, depth: float = 0.5, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "castle_stone", thickness: float = 0.4,
         name: str = "arch", coll: str = "SET", pointed: bool = False):
    """A free-standing masonry arch: two piers and a ring of wedge blocks (a gateway, a screen between two parts of a hall)."""
    p = Parts(name, coll, "arch")
    r = width / 2
    zs = height - r - thickness
    p.box((thickness, depth, zs), (-r - thickness / 2, 0, 0), surface, bevel=0.02)
    p.box((thickness, depth, zs), (r + thickness / 2, 0, 0), surface, bevel=0.02)
    n = 13
    for k in range(n):
        a = math.pi * (k + 0.5) / n
        rr = r + thickness / 2
        p.box((thickness, depth, 2 * rr * math.tan(math.pi / (2 * n)) * 1.04), (rr * math.cos(a), 0, zs + rr * math.sin(a)), surface, rot=(0, -math.degrees(a), 0), bevel=0.02, mid=True)
    return p.build(at=at, rot_z=rot_z, recentre=False)


def beam(p0, p1, size=(0.25, 0.3), surface: str = "dark_timber", name: str = "beam", coll: str = "SET"):
    """A square timber between two points (roof beams, tie beams, a gallows arm)."""
    a, b = Vector(p0), Vector(p1)
    d = b - a
    p = Parts(name, coll, "beam")
    q = d.to_track_quat("Y", "Z").to_euler()
    p.box((size[0], d.length, size[1]), (0, 0, 0), surface, mid=True, bevel=0.012)
    ob = p.build(at=(a + b) / 2, recentre=False)
    ob.rotation_euler = q
    return ob


def ceiling_beams(room_, spacing: float = 2.2, size=(0.22, 0.3), axis: str = "X", surface: str = "dark_timber", coll: str = "SET"):
    """Timber beams under a ceiling across the room (axis "X": beams run along X, spaced along Y). Tagged with the ceiling."""
    w, d, h = room_.size
    p = Parts(f"{room_.name}.beams", coll, "ceiling_beams", kind="prop")
    n = max(2, int((d if axis == "X" else w) / spacing))
    for i in range(n):
        k = (i + 0.5) / n
        if axis == "X":
            p.box((w, size[0], size[1]), (0, -d / 2 + d * k, h - size[1]), surface, bevel=0.012)
        else:
            p.box((size[0], d, size[1]), (-w / 2 + w * k, 0, h - size[1]), surface, bevel=0.012)
    ob = p.build(at=(room_.at[0], room_.at[1], 0), recentre=False)
    _tag_wall(ob, room_, "C")
    return ob


def vault(room_, rise: float = 1.5, axis: str = "Y", surface: str = "castle_stone"):
    """Note: a vaulted ceiling is chosen when the room is made: arch.room(..., ceiling_kind="vault", rise=1.5). This returns the ceiling."""
    return room_.ceiling


def stairs(run: float = 3.0, rise: float = 1.2, steps: int = 7, width: float = 1.6, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "flagstone", rail=None,
           name: str = "stairs", coll: str = "SET"):
    """A straight stair rising along +Y from the origin (the foot) by `rise` m over `run` m. rail="oak_planks" adds a banister on both sides."""
    p = Parts(name, coll, "stairs")
    sr, sd = rise / steps, run / steps
    for i in range(steps):
        p.box((width, sd * (steps - i), sr), (0, sd * (steps - i) / 2 + 0.0, sr * i), surface, bevel=0.012)
    if rail:
        for sx in (-1, 1):
            xp = sx * (width / 2 - 0.05)
            p.rod((xp, 0.1, 0.9), (xp, run - 0.1, rise + 0.9), 0.03, rail, seg=8)
            for k in range(0, steps + 1, 2):
                y = max(0.1, min(run - 0.1, sd * k))
                z = 0.0 + sr * k
                p.rod((xp, y, z), (xp, y, 0.9 + (rise * (y - 0.1) / (run - 0.2))), 0.02, rail, seg=6)
    return p.build(at=at, rot_z=rot_z, recentre=False)


def dais(size=(4.0, 3.0), height: float = 0.45, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "marble", steps: int = 2, step_side: str = "front", name: str = "dais",
         coll: str = "SET", trim_surface=None):
    """A raised platform with steps down its front (-Y side at rot 0). The top is at `height`; origin at the back-centre on the floor."""
    p = Parts(name, coll, "dais")
    w, d = size
    p.box((w, d, height), (0, -d / 2, 0), surface, bevel=0.015)
    sd = 0.4
    for j in range(1, steps):                                   # each lower step is a longer, lower block under the one above
        p.box((w, j * sd, height - j * height / steps), (0, -d - j * sd / 2, 0), surface, bevel=0.012)
    p.top((0, -d / 2), (w - 0.1, d - 0.1), height, "dais")
    return p.build(at=at, rot_z=rot_z, recentre=False)


def platform(size=(3.0, 2.0), height: float = 0.3, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "oak_planks", name: str = "platform", coll: str = "SET"):
    """A plain raised stage or podium; its top is a declared standing surface."""
    p = Parts(name, coll, "platform")
    p.box((size[0], size[1], height), (0, -size[1] / 2, 0), surface, bevel=0.01)
    p.top((0, -size[1] / 2), size, height, "platform")
    return p.build(at=at, rot_z=rot_z, recentre=False)


def balcony_rail(length: float = 4.0, height: float = 1.0, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "dark_timber", baluster: str = "iron_dark", name: str = "rail", coll: str = "SET"):
    """A balustrade along local X: top rail, base rail and posts. Used for galleries, stairs landings and balconies."""
    p = Parts(name, coll, "balcony_rail")
    p.box((length, 0.08, 0.06), (0, 0, height - 0.06), surface, bevel=0.01)
    p.box((length, 0.06, 0.05), (0, 0, 0.0), surface, bevel=0.01)
    n = max(2, int(length / 0.14))
    for i in range(n + 1):
        x = -length / 2 + length * i / n
        p.cyl(0.012, height - 0.11, (x, 0, 0.05), baluster, seg=6)
    for sx in (-1, 1):
        p.box((0.08, 0.08, height), (sx * (length / 2 - 0.04), 0, 0), surface, bevel=0.01)
    return p.build(at=at, rot_z=rot_z, recentre=False)


def fireplace(width: float = 1.8, height: float = 1.3, depth: float = 0.5, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "castle_stone", lit: bool = True,
              chimney_h: float | None = None, name: str = "fireplace", coll: str = "SET", mantel_surface: str = "dark_timber", spit: bool = False):
    """A hearth against a wall (back at the origin, opening toward -Y): masonry jambs and lintel, a mantel shelf, a dark firebox, a
    chimney breast up to `chimney_h`, and with lit=True a flame that is also a flickering warm light."""
    p = Parts(name, coll, "fireplace")
    jam = 0.28
    p.box((jam, depth, height), (-width / 2 + jam / 2, -depth / 2, 0), surface, bevel=0.02)
    p.box((jam, depth, height), (width / 2 - jam / 2, -depth / 2, 0), surface, bevel=0.02)
    p.box((width, depth, 0.28), (0, -depth / 2, height), surface, bevel=0.02)
    p.box((width + 0.3, depth + 0.16, 0.08), (0, -(depth + 0.16) / 2 + 0.0, height + 0.28), mantel_surface, bevel=0.015)
    p.box((width - 2 * jam, depth - 0.02, 0.04), (0, -depth / 2 + 0.01, 0.0), "castle_stone", tint="#6A645C", bevel=0.005)
    p.box((width - 2 * jam, 0.05, height - 0.04), (0, -0.03, 0.04), mat.solid("#0C0A09", 1.0), bevel=0.0)
    p.box((width - 2 * jam - 0.04, 0.4, 0.04), (0, -depth * 0.5 + 0.05, 0.04), "iron_dark", bevel=0.0)
    if chimney_h:
        p.box((width * 0.78, depth * 0.62, chimney_h - height - 0.36), (0, -depth * 0.31, height + 0.36), surface, bevel=0.02)
    if lit:
        iw = width - 2 * jam
        p.box((iw - 0.06, 0.012, height * 0.62), (0, -0.046, 0.12), p.glow("#C2480F", 2.0), bevel=0.0)                   # firelight washing the sooty back wall
        p.box((iw - 0.14, depth * 0.55, 0.035), (0, -depth * 0.5, 0.045), p.glow("#FF4A10", 0.9), bevel=0.0)             # a bed of embers
        for dx, ang in ((-0.26, 10), (0.0, -6), (0.26, 14)):
            p.box((min(0.6, iw * 0.7), 0.09, 0.09), (dx * 0.3, -depth * 0.35 - dx * 0.2, 0.08), "bark", rot=(0, 0, ang), bevel=0.01)
        p.cyl(0.05, min(0.7, iw * 0.8), (0, -depth * 0.55, 0.16), "bark", seg=7, rot=(0, 90, 6))
        hs = height / 1.3
        for dx, dy, hh, r_ in ((0.0, 0.42, 0.34 * hs, 0.11), (-0.17, 0.36, 0.24 * hs, 0.085), (0.18, 0.36, 0.26 * hs, 0.09), (-0.05, 0.5, 0.16 * hs, 0.06), (0.09, 0.5, 0.2 * hs, 0.065)):
            p.ball(r_, (dx * iw / 0.7, -depth * dy, 0.12 + hh), p.glow("#FF6A10", 3.2), squash=(1.0, 0.9, 2.3), sub=2)
        for dx, dy, hh, r_ in ((0.0, 0.42, 0.22 * hs, 0.065), (0.15, 0.4, 0.16 * hs, 0.05), (-0.14, 0.4, 0.15 * hs, 0.05)):
            p.ball(r_, (dx * iw / 0.7, -depth * dy - 0.02, 0.12 + hh), p.glow("#FFC25A", 3.6), squash=(1.0, 0.9, 1.9), sub=1)
        p.light("fire", (0, -depth * 0.5, 0.45 * hs), "#FF9A4A", 260.0, 0.2, True)
        if spit:                                     # a roasting spit across the firebox over the flames: two forks, the bar, a roast, a crank outside
            sz = min(height * 0.6, 1.0)
            im = mat.surface("iron_dark")
            for sx in (-1, 1):
                p.rod((sx * (iw / 2 - 0.1), -depth * 0.5, 0.04), (sx * (iw / 2 - 0.1), -depth * 0.5, sz), 0.018, im, seg=6)
                p.box((0.06, 0.05, 0.03), (sx * (iw / 2 - 0.1), -depth * 0.5, sz), im, bevel=0.004)
            p.rod((-iw / 2 + 0.05, -depth * 0.5, sz + 0.02), (iw / 2 - 0.02, -depth * 0.5, sz + 0.02), 0.012, im, seg=6)
            p.ball(0.14, (0.05, -depth * 0.5, sz + 0.02), mat.solid("#9A5A2E", 0.5), squash=(min(2.2, iw * 0.7), 0.9, 0.9), sub=2)
            p.rod((iw / 2 - 0.02, -depth * 0.5, sz + 0.02), (iw / 2 + 0.12, -depth * 0.5 - 0.05, sz + 0.02), 0.012, im, seg=6)
            p.rod((iw / 2 + 0.12, -depth * 0.5 - 0.05, sz + 0.02), (iw / 2 + 0.12, -depth * 0.5 - 0.2, sz - 0.1), 0.01, im, seg=5)
    return p.build(at=at, rot_z=rot_z, recentre=False)


def alcove(width: float = 1.0, height: float = 1.6, depth: float = 0.35, sill: float = 0.9, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "castle_stone",
           name: str = "alcove", coll: str = "SET", arched: bool = True):
    """A niche frame applied to a wall face with a dark recess behind (statue niche, shelf recess, window blind). Origin at the wall face."""
    p = Parts(name, coll, "alcove")
    w = width
    p.box((0.12, 0.08, height), (-w / 2 - 0.06, -0.04, sill), surface, bevel=0.01)
    p.box((0.12, 0.08, height), (w / 2 + 0.06, -0.04, sill), surface, bevel=0.01)
    p.box((w + 0.24, 0.08, 0.12), (0, -0.04, sill + height), surface, bevel=0.01)
    p.box((w + 0.24, depth, 0.06), (0, -depth / 2, sill - 0.06), surface, bevel=0.01)
    p.box((w, 0.02, height), (0, -0.015, sill), mat.solid("#14110F", 1.0), bevel=0.0)
    return p.build(at=at, rot_z=rot_z, recentre=False)


# ----------------------------------------------------------------------------- floors: inlays, rugs, runners
def floor_inlay(size=(4.0, 4.0), at=(0, 0, 0), rot_z: float = 0.0, surface: str = "marble", border: str = "gold", border_w: float = 0.06, name: str = "inlay", coll: str = "SET",
                round_: bool = False, tint=None):
    """A flat panel of another material let into the floor (a marble medallion, a tiled hearth) with a thin border strip."""
    p = Parts(name, coll, "floor_inlay")
    if round_:
        p.cyl(size[0] / 2, 0.012, (0, 0, 0), border, seg=48)
        p.cyl(size[0] / 2 - border_w, 0.016, (0, 0, 0), surface, tint, seg=48)
    else:
        p.box((size[0], size[1], 0.012), (0, 0, 0), border, bevel=0.0)
        p.box((size[0] - 2 * border_w, size[1] - 2 * border_w, 0.016), (0, 0, 0), surface, tint, bevel=0.0)
    return p.build(at=at, rot_z=rot_z, recentre=False)


def rug_area(size=(3.0, 2.0), at=(0, 0, 0), rot_z: float = 0.0, surface: str = "carpet_red", border="#C9A44A", border_w: float = 0.18, fringe: bool = True, name: str = "rug", coll: str = "SET",
             tint=None, inner=None):
    """A rug lying on the floor: border band, inner field with a second tone, tassels. Counts as a rug in the audit."""
    p = Parts(name, coll, "rug")
    w, d = size
    p.box((w, d, 0.008), (0, 0, 0), surface, tint, bevel=0.003)
    if border:
        bm_ = mat.solid(border, 0.9, sheen=0.4) if isinstance(border, str) and border.startswith("#") else border
        p.box((w - 0.0, border_w * 0.5, 0.010), (0, d / 2 - border_w * 0.5 - 0.02, 0), bm_, bevel=0.002)
        p.box((w - 0.0, border_w * 0.5, 0.010), (0, -d / 2 + border_w * 0.5 + 0.02, 0), bm_, bevel=0.002)
        p.box((border_w * 0.5, d - border_w, 0.010), (w / 2 - border_w * 0.5 - 0.02, 0, 0), bm_, bevel=0.002)
        p.box((border_w * 0.5, d - border_w, 0.010), (-w / 2 + border_w * 0.5 + 0.02, 0, 0), bm_, bevel=0.002)
    if inner:
        p.box((w - 2 * border_w - 0.15, d - 2 * border_w - 0.15, 0.011), (0, 0, 0), mat.solid(inner, 0.95, sheen=0.4), bevel=0.002)
    if fringe:
        n = max(6, int(w / 0.07))
        for i in range(n):
            x = -w / 2 + w * (i + 0.5) / n
            p.box((0.012, 0.1, 0.008), (x, d / 2 + 0.05, 0), "cloth", tint="#E9DFC8", bevel=0.0)
            p.box((0.012, 0.1, 0.008), (x, -d / 2 - 0.05, 0), "cloth", tint="#E9DFC8", bevel=0.0)
    ob = p.build(at=at, rot_z=rot_z, recentre=False)
    return ob


def carpet_runner(length: float = 10.0, width: float = 1.4, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "carpet_red", border="#C9A44A", name: str = "runner", coll: str = "SET"):
    """A long carpet down the middle of a hall (along Y at rot 0): field, two gold border bands and fringed ends."""
    p = Parts(name, coll, "carpet_runner")
    p.box((width, length, 0.014), (0, 0, 0), surface, bevel=0.003)
    bm_ = mat.solid(border, 0.9, sheen=0.4)
    for sx in (-1, 1):
        p.box((0.07, length, 0.018), (sx * (width / 2 - 0.12), 0, 0), bm_, bevel=0.002)
        p.box((0.025, length, 0.018), (sx * (width / 2 - 0.22), 0, 0), bm_, bevel=0.002)
    for sy in (-1, 1):
        for i in range(int(width / 0.07)):
            p.box((0.012, 0.12, 0.008), (-width / 2 + 0.035 + i * 0.07, sy * (length / 2 + 0.06), 0), "cloth", tint="#E9DFC8", bevel=0.0)
    return p.build(at=at, rot_z=rot_z, recentre=False)


# ----------------------------------------------------------------------------- exteriors
def _backing(p: Parts, w: float, h: float, y: float, z: float, glow: str = "#E9B66B", s: float = 0.6):
    """A dim interior behind a window of a facade, so no window ever looks out onto the void."""
    p.box((w, 0.05, h), (0, y, z), mat.emit(glow, s, f"SK_back_{glow}_{s}"), bevel=0.0)


def house_front(storeys: int = 2, style: str = "timber", width: float = 7.0, depth: float = 6.0, at=(0, 0, 0), rot_z: float = 0.0, name: str = "house", coll: str = "SET",
                roof: str = "gable", chimney: bool = True, awning=None, door_type: str = "panel", storey_h: float = 2.9, seed: int = 0,
                tint=None, roof_surface=None, lit: float = 0.45, flowerbox: bool = False, shutter_tint=None, night: bool = False):
    """The outside of a house, facing -Y: ground-floor door and windows, upper windows, trim, a front-gable roof and a chimney.
    style: timber (plaster between dark beams, clay tiles) | brick | stone | modern (render and big glass, flat roof).
    awning: a colour hex adds a striped shop awning over the ground floor. Origin at the middle of the front wall's foot.
    tint / roof_surface vary the walls and the roof; lit is the glow strength of the rooms behind the windows (night: 1.2 and warm);
    flowerbox adds window boxes with blooms; shutter_tint colours the shutters. The chimney top is recorded in root["sk_chimney"] (for smoke).
    Openings are real holes; a dim lit card behind each one means no window looks out onto the void."""
    rnd = random.Random(seed)
    wall_surf = {"timber": "plaster_warm", "brick": "brick_red", "stone": "castle_stone", "modern": "painted_wall"}[style]
    roof_surf = roof_surface or {"timber": "roof_clay_tile", "brick": "roof_slate", "stone": "roof_slate", "modern": "concrete"}[style]
    H = storeys * storey_h
    t = 0.35
    root = core.empty(name, (0, 0, 0), coll, 0.3)
    ops = []
    ww = 1.1 if style != "modern" else 1.6
    nwin = max(1, int(width / 2.2))
    door_u = -width / 2 + width * 0.3
    ops.append(dict(u0=door_u - 0.55, u1=door_u + 0.55, z0=0.0, z1=2.1, arched=False, kind="door", u=door_u))
    for s_ in range(storeys):
        for i in range(nwin):
            u = -width / 2 + width * (i + 0.5) / nwin
            if s_ == 0 and abs(u - door_u) < 1.2:
                continue
            ops.append(dict(u0=u - ww / 2, u1=u + ww / 2, z0=s_ * storey_h + 0.95, z1=s_ * storey_h + 0.95 + (1.3 if style != "modern" else 1.5), arched=False, kind="window", u=u))
    wob = _wall_mesh(f"{name}.wall", width, H, t, ops, (wall_surf, wall_surf), coll)
    if tint:
        wm_ = mat.surface(wall_surf, tint=tint)
        wob.data.materials.clear()
        wob.data.materials.append(wm_)
    wob.rotation_euler.z = math.radians(180)       # the mesh's outer face (+Y) must face the street (-Y)
    wob.location = (0, t, 0)
    wob.parent = root
    tag(wob, "house_wall", "shell")
    body = Parts(f"{name}.body", coll, kind="shell")
    body.box((width, depth, H), (0, t + depth / 2, 0), wall_surf, tint, bevel=0.0)
    for o in ops:
        wd_, hd_ = o["u1"] - o["u0"], o["z1"] - o["z0"]
        body.box((wd_ + 0.1, 0.05, hd_ + 0.1), (-o["u"], t - 0.01, o["z0"] - 0.05), mat.emit("#D9A55E" if (rnd.random() < 0.65 or night) else "#7F93AA", lit, f"SK_house_in_{lit}_{int(night)}"), bevel=0.0)
    body.build(at=(0, 0, 0), recentre=False).parent = root
    tp = Parts(f"{name}.trim", coll, kind="shell")
    if style == "timber":
        for s_ in range(storeys + 1):
            tp.box((width + 0.1, 0.1, 0.18), (0, -0.04, s_ * storey_h - 0.09 if s_ else 0.0), "dark_timber", bevel=0.012)
        for x in (-width / 2, width / 2):
            tp.box((0.2, 0.12, H), (x, -0.05, 0), "dark_timber", bevel=0.012)
        for i in range(1, 4):
            for s_ in range(storeys):
                tp.box((0.12, 0.1, storey_h), (-width / 2 + width * i / 4, -0.04, s_ * storey_h), "dark_timber", bevel=0.01)
    elif style in ("brick", "stone"):
        for s_ in range(storeys + 1):
            tp.box((width + 0.1, 0.08, 0.08), (0, -0.03, s_ * storey_h), "castle_stone", bevel=0.01)
        for z in range(0, int(H / 0.9)):
            for x in (-width / 2, width / 2):
                tp.box((0.34, 0.06, 0.4), (x, -0.03, z * 0.9), "castle_stone", bevel=0.01)
    for o in ops:
        wd_ = o["u1"] - o["u0"]
        if o["kind"] == "window":
            tp.box((wd_ + 0.22, 0.12, 0.08), (-o["u"], -0.04, o["z0"] - 0.08), "castle_stone" if style != "modern" else "concrete", bevel=0.01)
    tp.build(at=(0, 0, 0), recentre=False).parent = root
    for o in ops:
        wd_, hd_ = o["u1"] - o["u0"], o["z1"] - o["z0"]
        if o["kind"] == "door":
            h_ = door(door_type, wd_, hd_, open=0.0, frame=True, wall_t=t, surface="oak_planks", surround="dark_timber" if style == "timber" else "castle_stone", name=f"{name}.door", coll=coll)
            h_["root"].location = (-o["u"], t, 0)
        else:
            h_ = window("sash" if style != "modern" else "office", wd_, hd_, sill=o["z0"], wall_t=t, name=f"{name}.win", coll=coll, sill_ledge=True,
                        frame_surface="dark_timber" if style != "modern" else "brushed_metal", shutters=(style == "timber" and rnd.random() < 0.5), shutter_tint=shutter_tint)
            h_["root"].location = (-o["u"], t, o["z0"])
        h_["root"].parent = root
        h_["root"].rotation_euler.z = math.radians(180)
    rp = Parts(f"{name}.roof", coll, kind="shell")
    if style == "modern" or roof == "flat":
        rp.box((width + 0.4, depth + 0.4, 0.3), (0, t + depth / 2, H), roof_surf, bevel=0.02)
        rp.box((width + 0.4, 0.15, 0.5), (0, -0.2, H + 0.3), roof_surf, bevel=0.02)
    else:
        rise = width * 0.42
        ov = 0.25
        ang = math.degrees(math.atan2(rise, width / 2))
        sl = math.hypot(width / 2, rise) + ov
        for sx in (-1, 1):
            rp.box((sl, depth + ov + 0.2, 0.14), (sx * (width / 4 + ov / 4), t + depth / 2 - 0.1, H + rise / 2 - 0.02), roof_surf, rot=(0, sx * ang, 0), mid=True, bevel=0.01)
        rp.profile([(-width / 2, H), (width / 2, H), (0, H + rise - 0.1)], 0.0, t, wall_surf, bevel=0.0)
        if chimney:
            rp.box((0.7, 0.7, 2.2), (width * 0.3, t + depth * 0.6, H - 0.4 + rise * 0.15), "brick_red", bevel=0.02)
            rp.box((0.82, 0.82, 0.12), (width * 0.3, t + depth * 0.6, H + 1.8 + rise * 0.15), "castle_stone", bevel=0.01)
            root["sk_chimney"] = [width * 0.3, t + depth * 0.6, H + 1.9 + rise * 0.15]
    rp.build(at=(0, 0, 0), recentre=False).parent = root
    if flowerbox and style != "modern":
        fb = Parts(f"{name}.flowers", coll, kind="shell")
        for o in ops:
            if o["kind"] == "window" and o["z0"] > 0.5 or (o["kind"] == "window" and rnd.random() < 0.5):
                wd_ = o["u1"] - o["u0"]
                fb.box((wd_ + 0.1, 0.22, 0.16), (-o["u"], -0.12, o["z0"] - 0.2), "oak_planks", "#6B4A2E", bevel=0.01)
                for k in range(5):
                    fb.ball(0.07, (-o["u"] - wd_ / 2 + 0.12 + k * (wd_ - 0.1) / 4, -0.12, o["z0"] - 0.02), mat.solid(rnd.choice(["#E8A0B8", "#F2E27A", "#C95A5A", "#F6F1E4"]), 0.6), sub=1)
                    fb.ball(0.08, (-o["u"] - wd_ / 2 + 0.12 + k * (wd_ - 0.1) / 4, -0.12, o["z0"] - 0.09), "leaves", None, squash=(1, 1, 0.7), sub=1)
        fb.build(at=(0, 0, 0), recentre=False).parent = root
    if awning:
        ap = Parts(f"{name}.awning", coll, kind="shell")
        n = 10
        aw = width * 0.6
        for i in range(n):
            col = awning if i % 2 == 0 else "#F4EFE6"
            ap.box((aw / n, 1.2, 0.03), (-aw / 2 + aw * (i + 0.5) / n - width * 0.2, -0.65, 2.45), mat.solid(col, 0.9), rot=(-14, 0, 0), mid=True, bevel=0.003)
        ap.box((aw, 0.04, 0.18), (-width * 0.2, -1.24, 2.3), mat.solid(awning, 0.9), bevel=0.003)
        ap.build(at=(0, 0, 0), recentre=False).parent = root
    root.location = at
    root.rotation_euler.z = math.radians(rot_z)
    tag(root, "house_front", "prop", style=style)
    return root


def street(length: float = 40.0, width: float = 7.0, kerb: float = 0.15, paving: str = "cobblestone", at=(0, 0, 0), rot_z: float = 0.0, pavement: str = "flagstone",
           pavement_w: float = 2.2, name: str = "street", coll: str = "SET"):
    """A street along local X: road surface, raised kerbs and pavements both sides. Centre at the origin, road top at z=0."""
    p = Parts(name, coll, "street", kind="shell")
    p.box((length, width, 0.4), (0, 0, -0.4), paving, bevel=0.0)
    for sy in (-1, 1):
        y = sy * (width / 2 + pavement_w / 2)
        p.box((length, pavement_w, kerb), (0, y, 0.0), pavement, bevel=0.01)
        p.box((length, 0.18, kerb + 0.02), (0, sy * (width / 2 + 0.09), 0.0), "castle_stone", bevel=0.01)
    return p.build(at=at, rot_z=rot_z, recentre=False)


def plaza(size=(18.0, 14.0), at=(0, 0, 0), surface: str = "cobblestone", inlay: str = "flagstone", name: str = "plaza", coll: str = "SET"):
    """A paved square with a flagged border and a central medallion."""
    p = Parts(name, coll, "plaza", kind="shell")
    w, d = size
    p.box((w, d, 0.4), (0, 0, -0.4), surface, bevel=0.0)
    p.box((w - 0.4, 0.5, 0.014), (0, d / 2 - 0.35, 0), inlay, bevel=0.0)
    p.box((w - 0.4, 0.5, 0.014), (0, -d / 2 + 0.35, 0), inlay, bevel=0.0)
    p.cyl(min(w, d) * 0.12, 0.016, (0, 0, 0), inlay, seg=40)
    return p.build(at=at, recentre=False)


def low_wall(length: float = 6.0, height: float = 0.9, thick: float = 0.4, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "fieldstone", cap: bool = True, name: str = "low_wall", coll: str = "SET"):
    p = Parts(name, coll, "low_wall")
    p.box((length, thick, height), (0, 0, 0), surface, bevel=0.02)
    if cap:
        p.box((length + 0.06, thick + 0.1, 0.07), (0, 0, height), "castle_stone", bevel=0.015)
    return p.build(at=at, rot_z=rot_z)


def fence(length: float = 6.0, height: float = 1.1, at=(0, 0, 0), rot_z: float = 0.0, surface: str = "oak_planks", style: str = "picket", name: str = "fence", coll: str = "SET"):
    """A timber fence: picket | rail. Posts every 1.5 m."""
    p = Parts(name, coll, "fence")
    n = max(1, int(length / 1.5))
    for i in range(n + 1):
        p.box((0.1, 0.1, height + 0.1), (-length / 2 + length * i / n, 0, 0), surface, bevel=0.01)
    if style == "picket":
        for i in range(int(length / 0.14)):
            x = -length / 2 + 0.07 + i * 0.14
            p.box((0.09, 0.025, height * 0.9), (x, 0.06, 0.0), surface, tint="#CDBFA8", bevel=0.004)
        for z in (0.2, height * 0.7):
            p.box((length, 0.04, 0.07), (0, 0.03, z), surface, bevel=0.004)
    else:
        for z in (0.35, 0.7, 1.0):
            p.box((length, 0.05, 0.08), (0, 0, z), surface, bevel=0.006)
    return p.build(at=at, rot_z=rot_z)


def market_stall(width: float = 2.6, depth: float = 1.6, height: float = 2.4, canopy: str = "#B3322C", at=(0, 0, 0), rot_z: float = 0.0, name: str = "market_stall", coll: str = "SET"):
    """A trestle counter under a striped cloth canopy on four posts. Faces -Y; the goods go on its top (declared with top())."""
    p = Parts(name, coll, "market_stall")
    for sx in (-1, 1):
        for sy in (0, 1):
            p.box((0.08, 0.08, height), (sx * (width / 2 - 0.05), -sy * (depth - 0.1), 0), "dark_timber", bevel=0.01)
    p.box((width, depth * 0.6, 0.08), (0, -depth * 0.3 - 0.05, 0.84), "oak_planks", bevel=0.01)
    p.box((width - 0.1, depth * 0.6, 0.78), (0, -depth * 0.3 - 0.05, 0.0), "oak_planks", tint="#8A6A44", bevel=0.01)
    n = 8
    for i in range(n):
        col = canopy if i % 2 == 0 else "#F1EADB"
        p.box((width / n, depth + 0.5, 0.025), (-width / 2 + width * (i + 0.5) / n, -depth / 2 + 0.05, height + 0.0 - 0.08), mat.solid(col, 0.9), rot=(10, 0, 0), mid=True, bevel=0.003)
        p.box((width / n, 0.03, 0.18), (-width / 2 + width * (i + 0.5) / n, -depth - 0.17, height - 0.28), mat.solid(col, 0.9), bevel=0.003)
    p.top((0, -depth * 0.3 - 0.05), (width - 0.2, depth * 0.5), 0.92, "counter")
    return p.build(at=at, rot_z=rot_z)


def well(radius: float = 0.8, height: float = 0.9, at=(0, 0, 0), name: str = "well", coll: str = "SET", roof: bool = True, surface: str = "fieldstone", rot_z: float = 0.0):
    """A round stone well with a timber frame, a crank and a bucket on a rope."""
    p = Parts(name, coll, "well")
    p.cyl(radius, height, (0, 0, 0), surface, top=radius * 0.96, seg=24)
    p.cyl(radius * 0.74, 0.02, (0, 0, height), mat.solid("#0F1A22", 0.05), seg=24)
    p.cyl(radius + 0.06, 0.08, (0, 0, height), "castle_stone", seg=24)
    if roof:
        for sx in (-1, 1):
            p.box((0.12, 0.12, 2.0), (sx * (radius + 0.05), 0, height), "dark_timber", bevel=0.01)
        p.box((radius * 2 + 0.4, 0.14, 0.14), (0, 0, height + 1.95), "dark_timber", bevel=0.01)
        p.cyl(0.07, radius * 2 + 0.3, (-radius - 0.15, 0, height + 1.3), "oak_planks", rot=(0, 90, 0), seg=10)
        for sy in (-1, 1):
            p.box((radius * 2 + 0.5, 0.75, 0.05), (0, sy * 0.3, height + 2.2), "roof_clay_tile", rot=(sy * 28, 0, 0), mid=True, bevel=0.01)
        p.rod((0, 0, height + 1.3), (0, 0, height + 0.4), 0.01, "rope", seg=4)
        p.cyl(0.14, 0.2, (0, 0, height + 0.2), "oak_planks", top=0.17, seg=12)
    return p.build(at=at, rot_z=rot_z)


def lamp_post(height: float = 4.2, style: str = "gas", at=(0, 0, 0), lit: bool = True, name: str = "lamp_post", coll: str = "SET", power: float = 700.0, color="#FFC980", rot_z: float = 0.0):
    """A street lamp: gas (iron post, glass lantern, warm light) or modern (curved arm, white-warm LED head)."""
    p = Parts(name, coll, "lamp_post")
    p.cyl(0.16, 0.4, (0, 0, 0), "iron_dark", top=0.1, seg=12)
    p.cyl(0.05, height - 0.4, (0, 0, 0.4), "iron_dark", seg=10)
    if style == "gas":
        p.cyl(0.13, 0.12, (0, 0, height - 0.5), "iron_dark", top=0.1, seg=4)
        gl = p.glow(color, 5.0) if lit else mat.surface("glass")
        p.cyl(0.14, 0.4, (0, 0, height - 0.4), gl, top=0.2, seg=4)
        p.cyl(0.26, 0.12, (0, 0, height - 0.0), "iron_dark", top=0.02, seg=4)
        if lit:
            p.light("lamp", (0, 0, height - 0.2), color, power, 0.15, True)
    else:
        p.rod((0, 0, height - 0.2), (0.0, -0.5, height + 0.1), 0.04, "iron_dark")
        p.box((0.55, 0.22, 0.07), (0, -0.7, height), "iron_dark", bevel=0.01)
        if lit:
            p.box((0.5, 0.18, 0.02), (0, -0.7, height - 0.03), p.glow("#FFF1D6", 8.0), bevel=0.0)
            p.light("lamp", (0, -0.7, height - 0.2), "#FFF1D6", power, 0.2, True, "SPOT", aim=(0, -0.7, 0), size=110)
    return p.build(at=at, rot_z=rot_z)


def skyline(width: float = 80.0, distance: float = 40.0, at=(0, 0, 0), kind: str = "town", seed: int = 1, name: str = "skyline", coll: str = "SET", strength: float = 1.0, night: bool = False,
            sky_card: bool = True):
    """The layer beyond an outdoor set: a row of far buildings (town: pitched roofs, spires; city: towers) along local X, facing -Y, with
    a sky card behind. Emissive so it never changes the set's light. Place its `at` behind the action (+Y)."""
    rnd = random.Random(seed)
    sky_top, sky_hor = ("#0A1230", "#2B3560") if night else ("#6FA6E6", "#D7EBF7")
    p = Parts(f"{name}.sky", coll, "skyline", kind="shell")
    matl = _sky_mat(sky_top, sky_hor, clouds=0.0 if night else 0.6, strength=strength)
    bm = p._bm(matl, None, 0.0)
    w2 = width * 1.6
    vs = [bm.verts.new((-w2 / 2, distance + 60, -2)), bm.verts.new((w2 / 2, distance + 60, -2)), bm.verts.new((w2 / 2, distance + 60, 90)), bm.verts.new((-w2 / 2, distance + 60, 90))]
    f = bm.faces.new(vs)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u, v)
    sk = p.build(at=at, recentre=False) if sky_card else core.empty(f"{name}.sky", at, coll, 0.3)
    b = Parts(f"{name}.blocks", coll, "skyline", kind="shell")
    x = -width / 2
    while x < width / 2:
        bw = rnd.uniform(4, 9)
        bh = rnd.uniform(5, 10) if kind == "town" else rnd.uniform(14, 48)
        col = _lerp_hex(rnd.choice(["#B9AA95", "#B58E7A", "#A59A8E"]) if kind == "town" else rnd.choice(["#8E99A8", "#A5AFBA", "#7C8796"]), sky_hor, 0.5)
        if night:
            col = rnd.choice(["#1B2136", "#222A42"])
        b.box((bw - 0.3, 6, bh), (x + bw / 2, distance, -0.5), mat.emit(col, 0.95 * strength, f"SK_sl_{col}"), bevel=0.0)
        if kind == "town":
            b.box((bw - 0.6, 5, 2.4), (x + bw / 2, distance, bh - 0.5), mat.emit("#9B5A44", 0.9 * strength, "SK_sl_roof"), bevel=0.0)
            if rnd.random() < 0.18:
                b.box((1.5, 1.5, 9), (x + bw / 2, distance, bh), mat.emit("#A59A8E", 0.9 * strength, "SK_sl_spire"), bevel=0.0)
                b.box((0.2, 0.2, 3), (x + bw / 2, distance, bh + 9), mat.emit("#8A4B36", 0.9 * strength, "SK_sl_spire2"), bevel=0.0)
        x += bw
    bl = b.build(at=at, recentre=False)
    bl.parent = sk
    bl.location = (0, 0, 0)
    for o in (sk, bl, *bl.children, *sk.children):
        if hasattr(o, "visible_shadow"):
            o.visible_shadow = False
    return sk


def treeline(width: float = 60.0, distance: float = 30.0, at=(0, 0, 0), seed: int = 1, name: str = "treeline", coll: str = "SET", strength: float = 1.0, colors=("#3F7A3A", "#4E8B44", "#2F6A35")):
    """A far row of round-crowned trees (emissive, so it never changes the set's light), for the edge of a field or a park."""
    rnd = random.Random(seed)
    p = Parts(name, coll, "treeline", kind="shell")
    x = -width / 2
    while x < width / 2:
        h_ = rnd.uniform(5, 9)
        p.cyl(0.3, h_ * 0.5, (x, distance + rnd.uniform(-2, 2), 0), mat.emit("#4A3A2A", 0.7 * strength, "SK_tl_trunk"), seg=7)
        for dx, dz, rr in ((0, 0.6, 2.4), (1.3, 0.3, 1.7), (-1.3, 0.3, 1.8)):
            p.ball(rr, (x + dx, distance + rnd.uniform(-2, 2), h_ * 0.5 + dz), mat.emit(rnd.choice(colors), 0.9 * strength, "SK_tl_leaf"), sub=2)
        x += rnd.uniform(3.2, 5.2)
    ob = p.build(at=at, recentre=False)
    for ch in ob.children:
        ch.visible_shadow = False
    return ob


def glass_partition(length: float = 4.0, height: float = 2.6, at=(0, 0, 0), rot_z: float = 0.0, door=None, pane: float = 1.1, frame: str = "brushed_metal", opaque_band: float = 0.0,
                    name: str = "glass_partition", coll: str = "SET", open_deg: float = 0.0):
    """A glass office wall along local X (front faces -Y): floor and head rails, mullions every `pane` m, glass between, and
    (door=(offset, width)) a glass door with its frame. opaque_band adds a frosted band at 0.9-1.5 m. Returns {"root", "door"}."""
    p = Parts(name, coll, "glass_partition")
    gm = mat.surface("glass")
    fm = mat.surface(frame)
    p.box((length, 0.07, 0.06), (0, 0, 0.0), fm, bevel=0.004)
    p.box((length, 0.07, 0.06), (0, 0, height - 0.06), fm, bevel=0.004)
    n = max(1, int(round(length / pane)))
    xs = [-length / 2 + length * i / n for i in range(n + 1)]
    gap = None
    if door:
        gap = (door[0] - door[1] / 2, door[0] + door[1] / 2)
        xs = sorted(set([x for x in xs if x <= gap[0] - 0.15 or x >= gap[1] + 0.15] + [gap[0], gap[1]]))
    for x in xs:
        p.box((0.05, 0.07, height), (x, 0, 0.0), fm, bevel=0.004)
    for a, b in zip(xs, xs[1:]):
        if gap and a >= gap[0] - 1e-6 and b <= gap[1] + 1e-6:
            continue
        p.box((b - a - 0.05, 0.012, height - 0.12), ((a + b) / 2, 0, 0.06), gm, bevel=0.0)
        if opaque_band:
            p.box((b - a - 0.05, 0.016, opaque_band), ((a + b) / 2, 0, 0.9), mat.solid("#E8EBEE", 0.6), bevel=0.0)
    if gap:
        p.box((door[1], 0.07, 0.06), (door[0], 0, 2.05), fm, bevel=0.004)
        p.box((door[1], 0.012, height - 2.1 - 0.06), (door[0], 0, 2.11), gm, bevel=0.0)
    ob = p.build(at=at, rot_z=rot_z, recentre=False)
    dr = None
    if door:
        dr = door_("glass", door[1], 2.05, open=open_deg, frame=True, wall_t=0.07, surround=frame, name=f"{name}.door", coll=coll)
        dr["root"].parent = ob
        dr["root"].location = (door[0], -0.0, 0.0)
        dr["root"].rotation_euler.z = 0.0
    return {"root": ob, "door": dr}


door_ = door


# ============================================================================= depth for open places (set kit v2)
def _quad_uv(bm, uvl, c, ax, ay):
    """A quad centred on c spanned by the half-vectors ax and ay, with 0..1 UVs (for the soft blob materials)."""
    vs = [bm.verts.new(c + ax * sx + ay * sy) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    f = bm.faces.new(vs)
    for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv
    return f


def smoke(at=(0, 0, 0), height: float = 7.0, puffs: int = 12, width: float = 0.6, drift=(1.2, 0.0), color="#8F9096", alpha: float = 0.30, seed: int = 1,
          glow: float = 0.0, name: str = "smoke", coll: str = "FX"):
    """A column of smoke or steam: soft puffs that widen and thin out as they rise and lean along `drift` (metres of sideways travel at the
    top). Each puff is three crossed quads, so it reads from every side. glow lights the puffs from inside (a fire, a forge).
    Counts as the set's atmosphere."""
    rnd = random.Random(seed)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for i in range(puffs):
        u = (i + rnd.uniform(-0.2, 0.2)) / max(1, puffs - 1)
        u = min(1.0, max(0.0, u))
        c = Vector((at[0] + drift[0] * u * u + rnd.uniform(-0.15, 0.15) * (1 + u), at[1] + drift[1] * u * u + rnd.uniform(-0.15, 0.15) * (1 + u), at[2] + height * u))
        s = width * (0.9 + 2.6 * u) * rnd.uniform(0.85, 1.2)
        a = rnd.uniform(0, 3.14)
        ax = Vector((math.cos(a), math.sin(a), 0)) * s
        ay = Vector((0, 0, 1)) * s
        _quad_uv(bm, uvl, c, ax, ay)
        _quad_uv(bm, uvl, c, Vector((-math.sin(a), math.cos(a), 0)) * s, ay)
        _quad_uv(bm, uvl, c, ax, Vector((-math.sin(a), math.cos(a), 0)) * s)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, coll)
    me.materials.append(mat.soft(color, alpha, 2.0, glow=glow))
    ob.visible_shadow = False
    ob["sk_role"] = "atmosphere"
    ob["sk_atmo"] = "smoke"
    return ob


def ground_haze(size=(80.0, 40.0), at=(0, 0, 0.0), height: float = 1.6, color="#C9D2DC", alpha: float = 0.16, seed: int = 1, count: int = 26, name: str = "ground_haze", coll: str = "FX"):
    """Low banks of mist or battlefield haze lying on the ground: broad soft upright cards scattered over a rectangle, thinner at the edges."""
    rnd = random.Random(seed)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for i in range(count):
        c = Vector((at[0] + rnd.uniform(-size[0] / 2, size[0] / 2), at[1] + rnd.uniform(-size[1] / 2, size[1] / 2), at[2] + height * rnd.uniform(0.3, 0.6)))
        s = rnd.uniform(4.0, 9.0)
        a = rnd.uniform(0, 3.14)
        _quad_uv(bm, uvl, c, Vector((math.cos(a), math.sin(a), 0)) * s, Vector((0, 0, 1)) * height * rnd.uniform(0.7, 1.2))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    core.link(ob, coll)
    me.materials.append(mat.soft(color, alpha, 1.4))
    ob.visible_shadow = False
    ob["sk_role"] = "atmosphere"
    ob["sk_atmo"] = "haze"
    return ob


def far_hills(width: float = 360.0, distance: float = 110.0, heights=(10.0, 18.0, 30.0), sky="#D7EBF7", colors=("#6C9A55", "#7BA574", "#8FB0A8"), seed: int = 1, night: bool = False,
              at=(0, 0, 0), name: str = "far_hills", coll: str = "SET", strength: float = 1.0, castle: bool = False, ridge_gap: float = 28.0):
    """Layered ridges behind an open set, each lighter and bluer than the one in front (aerial perspective), with an optional far castle
    on the last one. Emissive cut-outs: they never change the set's light. Place `at` at the middle of the far edge of the set."""
    rnd = random.Random(seed)
    root = Parts(name, coll, "far_hills", kind="prop")
    n = 46
    span = width
    for li, (hmax, col) in enumerate(zip(heights, colors)):
        k = (li + 1) / (len(heights) + 0.6)
        base = _lerp_hex(col, sky, 0.18 + 0.6 * k) if not night else _lerp_hex(col, "#0E1830", 0.7 - 0.12 * li)
        ph = rnd.uniform(0, 6)
        top = [(-span / 2 + span * i / n, hmax * (0.5 + 0.5 * math.sin(i * (0.33 + 0.07 * li) + ph) * math.cos(i * 0.11 + ph * 2) + 0.25 * math.sin(i * 0.9 + li)) + rnd.uniform(-0.4, 0.4)) for i in range(n + 1)]
        top = [(x, max(1.5, z)) for x, z in top]
        root.profile([(-span / 2, -1.0)] + top + [(span / 2, -1.0)], distance + li * ridge_gap, distance + li * ridge_gap + 1.2, mat.emit(base, 0.92 * strength, f"SK_hill_{base}"), bevel=0.0)
    if castle:
        yy = distance + (len(heights) - 1) * ridge_gap + 2
        bx = rnd.uniform(-30, 30)
        cm = mat.emit(_lerp_hex("#9A98A0", sky, 0.5) if not night else "#1A2038", 0.92 * strength, "SK_far_keep")
        rm = mat.emit(_lerp_hex("#7A4A44", sky, 0.4) if not night else "#161C30", 0.9 * strength, "SK_far_keep_roof")
        for dx, wd, hh in ((0, 14.0, 12.0), (-9.0, 4.0, 20.0), (9.0, 4.0, 18.0), (0.0, 5.0, 22.0), (-15.0, 3.4, 14.0), (15.0, 3.4, 13.0)):
            root.box((wd, 4.0, hh), (bx + dx, yy, 8.0), cm, bevel=0.0)
        for dx, hh, z in ((-9.0, 20.0, 8.0), (9.0, 18.0, 8.0), (0.0, 22.0, 8.0)):
            root.cyl(3.4, 6.0, (bx + dx, yy, z + hh), rm, top=0.2, seg=8)
    ob = root.build(at=at, recentre=False)
    ob["sk_layer"] = "beyond"
    for ch in ob.children:
        ch.visible_shadow = False
        ch.visible_glossy = False
    return ob


def army(width: float = 90.0, distance: float = 70.0, rows: int = 5, at=(0, 0, 0), seed: int = 1, color="#3A4258", sky="#C9D6E6", banners=("#A3231F", "#2D4A6B"),
         density: float = 1.2, name: str = "army", coll: str = "SET", strength: float = 1.0, night: bool = False, gaps: float = 0.12):
    """A host in the distance: ranks of cheap soldier silhouettes (a tapering body, a head, a spear, some with shields) in blocks with
    gaps, a few standards over them. Each rank is lighter and bluer than the one in front. Low-poly figures: a few thousand triangles
    for hundreds of soldiers."""
    rnd = random.Random(seed)
    p = Parts(name, coll, "army", kind="prop")
    banner_m = [mat.emit(_lerp_hex(c, sky, 0.35), 0.9 * strength, f"SK_army_banner_{c}") for c in banners]
    for r_ in range(rows):
        y = distance + r_ * 3.4
        col = _lerp_hex(color, sky, 0.12 + 0.1 * r_) if not night else _lerp_hex(color, "#10162A", 0.2 * r_)
        bm_ = mat.emit(col, 0.9 * strength, f"SK_army_{col}")
        hm_ = mat.emit(_lerp_hex(col, "#D8B89A", 0.25), 0.9 * strength, f"SK_army_h_{col}")
        x = -width / 2 + rnd.uniform(0, 3)
        step = 1.35 / density
        while x < width / 2:
            if rnd.random() < gaps:
                x += rnd.uniform(4, 9)
                continue
            for k in range(int(rnd.uniform(5, 14))):
                if x > width / 2:
                    break
                xx, yy = x + rnd.uniform(-0.15, 0.15), y + rnd.uniform(-0.5, 0.5)
                p.cyl(0.3, 1.25, (xx, yy, 0.0), bm_, top=0.2, seg=5)
                p.ball(0.15, (xx, yy, 1.45), hm_, sub=1)
                if rnd.random() < 0.75:
                    p.rod((xx + 0.25, yy, 0.5), (xx + 0.28 + rnd.uniform(-0.1, 0.1), yy, 2.8), 0.025, bm_, seg=3)
                if rnd.random() < 0.3:
                    p.cyl(0.32, 0.06, (xx - 0.3, yy - 0.05, 0.6), bm_, seg=8, rot=(90, 0, 0))
                x += step
            x += rnd.uniform(0.5, 2.0)
        if r_ in (0, 1):
            for k in range(int(width / 26)):
                bx = -width / 2 + (k + rnd.uniform(0.2, 0.8)) * 26
                p.rod((bx, y, 1.0), (bx, y, 5.6), 0.05, bm_, seg=4)
                p.box((1.2, 0.04, 0.9), (bx + 0.65, y, 4.7), banner_m[(k + r_) % len(banner_m)], bevel=0.0)
    ob = p.build(at=at, recentre=False)
    ob["sk_layer"] = "beyond"
    for ch in ob.children:
        ch.visible_shadow = False
        ch.visible_glossy = False
    return ob


def far_town(width: float = 120.0, distance: float = 70.0, at=(0, 0, 0), seed: int = 1, sky="#D7EBF7", night: bool = False, strength: float = 1.0, name: str = "far_town", coll: str = "SET", church: bool = True):
    """Roofs and a church spire seen across fields: two ranks of low pitched-roof silhouettes with a few lit windows at night."""
    rnd = random.Random(seed)
    p = Parts(name, coll, "far_town", kind="prop")
    for r_ in range(2):
        y = distance + r_ * 9
        x = -width / 2
        while x < width / 2:
            bw = rnd.uniform(5, 10)
            bh = rnd.uniform(4.5, 8.5)
            wall = rnd.choice(["#B9AA95", "#B58E7A", "#A59A8E", "#C9B8A0"])
            wc = _lerp_hex(wall, sky, 0.35 + 0.15 * r_) if not night else rnd.choice(["#1B2136", "#222A42"])
            rc = _lerp_hex(rnd.choice(["#9B5A44", "#6A5A54", "#8A4B36"]), sky, 0.35 + 0.15 * r_) if not night else "#151B30"
            p.box((bw - 0.4, 6.0, bh), (x + bw / 2, y, -0.5), mat.emit(wc, 0.92 * strength, f"SK_ft_{wc}"), bevel=0.0)
            p.profile([(x + 0.1, bh - 0.5), (x + bw - 0.1, bh - 0.5), (x + bw / 2, bh + bw * 0.28)], y - 3.0, y + 3.0, mat.emit(rc, 0.9 * strength, f"SK_ft_r_{rc}"), bevel=0.0)
            if night and rnd.random() < 0.6:
                p.box((0.7, 0.05, 0.9), (x + bw / 2, y - 3.02, 2.2), mat.emit("#FFC477", 1.1, "SK_ft_win"), bevel=0.0)
            x += bw + rnd.uniform(0.3, 1.5)
    if church:
        cx = rnd.uniform(-width * 0.2, width * 0.2)
        y = distance + 3
        cc = mat.emit(_lerp_hex("#C9C2B2", sky, 0.4) if not night else "#1B2136", 0.92 * strength, "SK_ft_church")
        p.box((6.0, 7.0, 22.0), (cx, y, -0.5), cc, bevel=0.0)
        p.cyl(4.6, 14.0, (cx, y, 21.5), mat.emit(_lerp_hex("#5A5A62", sky, 0.4) if not night else "#10162A", 0.9 * strength, "SK_ft_spire"), top=0.1, seg=4, rot=(0, 0, 45))
    ob = p.build(at=at, recentre=False)
    ob["sk_layer"] = "beyond"
    for ch in ob.children:
        ch.visible_shadow = False
    return ob


def church(width: float = 7.0, length: float = 13.0, tower_h: float = 17.0, at=(0, 0, 0), rot_z: float = 0.0, name: str = "church", coll: str = "SET", night: bool = False):
    """A village church seen from outside: a stone nave with a slate roof and buttresses, arched windows (lit at night), a square tower with a
    clock face, louvred belfry openings, a pyramid spire and a weathercock. The tower stands at the +X end of the front (facing -Y)."""
    p = Parts(name, coll, "church")
    ws, rs = "castle_stone", "roof_slate"
    p.box((width, length, 6.2), (0, length / 2, 0), ws, tint="#CFC8B8", bevel=0.03)
    rise = width * 0.45
    ang = math.degrees(math.atan2(rise, width / 2))
    sl = math.hypot(width / 2, rise) + 0.3
    for sx in (-1, 1):
        p.box((sl, length + 0.6, 0.16), (sx * (width / 4 + 0.1), length / 2, 6.2 + rise / 2 - 0.02), rs, rot=(0, sx * ang, 0), mid=True, bevel=0.01)
    p.profile([(-width / 2, 6.2), (width / 2, 6.2), (0, 6.2 + rise - 0.1)], -0.01, 0.01, ws, tint="#CFC8B8", bevel=0.0)
    gl = mat.emit("#FFC477", 1.1, "SK_church_win") if night else mat.surface("glass")
    for k in range(3):
        y = 2.5 + k * 3.6
        for sx in (-1, 1):
            p.box((0.5, 0.2, 2.6), (sx * (width / 2 + 0.01), y, 1.9), gl, bevel=0.0)
            p.box((0.14, 0.6, 3.4), (sx * (width / 2 + 0.12), y + 1.8, 0), ws, bevel=0.02)
    tw = 3.4
    tx = width / 2 + tw / 2 - 0.4
    p.box((tw, tw, tower_h), (tx, tw / 2, 0), ws, tint="#C4BCAA", bevel=0.03)
    for z in (6.0, 11.0):
        p.box((tw + 0.2, tw + 0.2, 0.2), (tx, tw / 2, z), ws, bevel=0.02)
    p.box((1.0, 0.2, 2.2), (tx, -0.02, 1.0), gl if night else mat.solid("#2A1E14", 0.8), bevel=0.01)
    p.box((1.4, 0.12, 2.4), (tx, -0.04, 0.0), ws, tint="#A8A090", bevel=0.02)
    p.cyl(0.5, 0.1, (tx, -0.08, tower_h - 4.4), mat.solid("#EFE6CF", 0.5), seg=20, rot=(90, 0, 0))
    p.rod((tx, -0.14, tower_h - 3.9), (tx, -0.14, tower_h - 3.5), 0.02, mat.solid("#1E1E1E", 0.5), seg=4)
    for sx, sy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        p.box((0.8 if sy else 0.15, 0.15 if sy else 0.8, 1.8), (tx + sx * (tw / 2 + 0.01), tw / 2 + sy * (tw / 2 + 0.01), tower_h - 3.0), mat.solid("#1C1612", 0.9), bevel=0.0)
    p.box((tw + 0.3, tw + 0.3, 0.3), (tx, tw / 2, tower_h), ws, bevel=0.02)
    bm = p._bm(mat.surface(rs), None, 0.0)
    h = 6.5
    V = lambda x, y, z: bm.verts.new((x, y, z))
    a, b, c, d = V(tx - tw / 2 - 0.1, -0.1, tower_h + 0.3), V(tx + tw / 2 + 0.1, -0.1, tower_h + 0.3), V(tx + tw / 2 + 0.1, tw + 0.1, tower_h + 0.3), V(tx - tw / 2 - 0.1, tw + 0.1, tower_h + 0.3)
    e = V(tx, tw / 2, tower_h + 0.3 + h)
    for u, v in ((a, b), (b, c), (c, d), (d, a)):
        bm.faces.new((u, v, e))
    p.rod((tx, tw / 2, tower_h + h), (tx, tw / 2, tower_h + h + 1.6), 0.03, mat.solid("#B8923A", 0.3, 0.9), seg=4)
    p.ball(0.12, (tx, tw / 2, tower_h + h + 1.7), mat.solid("#B8923A", 0.3, 0.9), sub=1)
    ob = p.build(at=at, rot_z=rot_z, recentre=False)
    ob["sk_detail"] = 1
    return ob


def terrain(size=(120.0, 90.0), at=(0, 0, 0), flat=(-20.0, -12.0, 20.0, 14.0), relief: float = 1.6, features=(), surface: str = "forest_floor", tint=None, seed: int = 1,
            res: float = 1.5, blend: float = 7.0, name: str = "terrain", coll: str = "SET"):
    """Open ground with relief: noise hills and ridges that rise from a dead-level stage `flat` (x0, y0, x1, y1) over `blend` metres, and the
    outer 10 m of the sheet fade back to zero so it meets the ground apron without a seam. features add shapes to the height field:
    ("mound", cx, cy, radius, height), ("trench", x0, y0, x1, y1, half_width, depth), ("crater", cx, cy, radius, depth), ("ridge", x0, y0, x1, y1, half_width, height).
    Returns (object, height_function(x, y)); a prop placed with z = height_function(x, y) stands on it."""
    from mathutils import noise
    rnd = random.Random(seed)
    off = Vector((rnd.uniform(0, 100), rnd.uniform(0, 100), 0))
    w, d = size
    ox_, oy_ = at[0], at[1]
    at = (at[0], at[1], at[2] if len(at) > 2 else 0.0)
    nx, ny = int(w / res) + 1, int(d / res) + 1
    fx0, fy0, fx1, fy1 = flat
    sm = lambda t: t * t * (3 - 2 * t)

    def hf(x, y):                                  # x, y in WORLD metres (flat and features are given in world metres)
        dx = max(fx0 - x, 0.0, x - fx1)
        dy = max(fy0 - y, 0.0, y - fy1)
        k = sm(min(1.0, math.hypot(dx, dy) / blend))
        n = noise.fractal(Vector((x * 0.045, y * 0.045, 0)) + off, 0.5, 2.0, 4) * 0.5 + 0.5
        z = (n - 0.35) * relief * 2.0 * k
        for f in features:
            if f[0] == "mound":
                r2 = ((x - f[1]) ** 2 + (y - f[2]) ** 2) / (f[3] ** 2)
                z += f[4] * math.exp(-r2 * 2.2)
            elif f[0] == "crater":
                r = math.hypot(x - f[1], y - f[2]) / f[3]
                z += -f[4] * math.exp(-(r * 1.4) ** 2) + f[4] * 0.45 * math.exp(-((r - 1.05) * 3.0) ** 2)
            elif f[0] in ("trench", "ridge"):
                ax, ay, bx, by = f[1], f[2], f[3], f[4]
                abx, aby = bx - ax, by - ay
                t = max(0.0, min(1.0, ((x - ax) * abx + (y - ay) * aby) / (abx * abx + aby * aby)))
                dd = math.hypot(x - (ax + abx * t), y - (ay + aby * t)) / f[5]
                z += (-f[6] if f[0] == "trench" else f[6]) * math.exp(-dd * dd * 1.6) * (0.75 + 0.25 * math.sin(t * 9 + dd))
        lx_, ly_ = x - ox_, y - oy_
        ex = min(lx_ + w / 2, w / 2 - lx_, ly_ + d / 2, d / 2 - ly_)
        z *= sm(max(0.0, min(1.0, ex / 10.0)))
        return z

    bm = bmesh.new()
    vs = []
    for j in range(ny):
        row = []
        for i in range(nx):
            x, y = -w / 2 + w * i / (nx - 1), -d / 2 + d * j / (ny - 1)
            row.append(bm.verts.new((x, y, hf(x + ox_, y + oy_))))
        vs.append(row)
    for j in range(ny - 1):
        for i in range(nx - 1):
            bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
    bm.normal_update()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for pl in me.polygons:
        pl.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    core.link(ob, coll)
    m = _mat(surface, tint)
    if m:
        me.materials.append(m)
    mat.uv_box(ob)
    ob.location = at
    tag(ob, "terrain", "shell")

    def ground_z(x, y):
        """The height of the built mesh at world (x, y) (a ray down onto it: the same surface a prop stands on, not the smooth function behind it)."""
        hit, loc, _n, _i = ob.ray_cast(Vector((x - at[0], y - at[1], 60.0)), Vector((0, 0, -1)))
        return (loc.z + at[2]) if hit else hf(x, y) + at[2]
    return ob, ground_z


def road_markings(length: float = 60.0, width: float = 8.0, at=(0, 0, 0), rot_z: float = 0.0, crossings=(), name: str = "road_markings", coll: str = "SET", edge: bool = True):
    """Paint on a street along local X (centre at the origin, road top at z=0): a dashed centre line, edge lines and zebra crossings at the
    given x positions. Thin boxes a hair above the asphalt."""
    p = Parts(name, coll, "road_markings", kind="shell")
    wm = mat.solid("#EDEDE6", 0.8)
    n = int(length / 4.0)
    for i in range(n):
        x = -length / 2 + 2.0 + i * 4.0
        if any(abs(x - cx) < 4.5 for cx in crossings):
            continue
        p.box((2.0, 0.14, 0.004), (x, 0, 0.004), wm, bevel=0.0)
    if edge:
        for sy in (-1, 1):
            p.box((length, 0.1, 0.004), (0, sy * (width / 2 - 0.3), 0.004), wm, bevel=0.0)
    for cx in crossings:
        for k in range(int(width / 0.7)):
            p.box((3.0, 0.4, 0.005), (cx, -width / 2 + 0.5 + k * 0.7, 0.004), wm, bevel=0.0)
    return p.build(at=at, rot_z=rot_z, recentre=False)
