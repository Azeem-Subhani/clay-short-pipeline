"""stagekit.furnish - furniture and props, built procedurally in metres with real surfaces.

    from stagekit import furnish
    t = furnish.banquet_table(at=(0, 2, 0), rot_z=90)             # every piece: (at, rot_z, name, coll, **options) -> one parent object
    furnish.make("goblet", at=(0, 2, 0.78))                       # or by name: furnish.REGISTRY lists every piece

Conventions shared by every piece
  * One parent empty; the meshes are children, merged per material. Origin on the FLOOR at the centre of the BACK face; the
    front faces -Y. Place a piece against a wall by putting `at` on the wall face. Wall hung things (picture, sconce, clock,
    banner) stand on z = 0 of their own geometry: pass their mount height as at.z (REGISTRY[name]["mount_z"] is the usual one).
  * Size in metres is in ob["sk_size"] = [width, depth, height]; ob["sk_type"] is the piece's name; ob["sk_tops"] lists the flat
    surfaces small props may stand on ({x, y, z, w, d, label}) in the piece's own frame: dress.py puts clutter there.
  * Pieces that are light sources (candle, sconce, chandelier, lamp, brazier, ceiling panel, fireplace...) have an emissive
    part AND a real light made with lights.practical, parented to the piece.
  * Surfaces by name from library/materials/catalog.json; tint="#hex" shifts the main one.
"""
from __future__ import annotations

import functools
import math
import random
import sys

import bpy
from mathutils import Vector

from . import arch, build, core, mat
from .arch import Parts, put, tag  # noqa: F401

REGISTRY: dict = {}
MED = ["ancient", "medieval", "renaissance", "fantasy"]
OLD = ["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy", "east_asia_feudal"]
ANY = ["any"]
MODERN = ["modern"]
HOME = ["victorian", "modern"]
LATER = ["renaissance", "age_of_sail", "victorian", "modern"]

W, DW, IRON, GOLD, STEEL, BM, CLOTH = "oak_planks", "dark_timber", "iron_dark", "gold", "steel_bright", "brushed_metal", "cloth"


def piece(type_: str, era=ANY, kind: str = "furniture", mount_z: float | None = None, detail: bool = False, source: bool = False, hang: bool = False, tags=()):
    """Register a builder. The decorated function receives (p: Parts, **options) and draws the piece in authored coordinates
    (centred on x, y; floor at z = 0; front toward -Y); the wrapper makes, recentres and places it."""
    def deco(fn):
        @functools.wraps(fn)
        def make_(at=(0, 0, 0), rot_z: float = 0.0, name: str | None = None, coll: str = "SET", **kw):
            p = Parts(name or type_, coll, type_, era=era)
            fn(p, **kw)
            ob = p.build(at=at, rot_z=rot_z)
            ob["sk_piece_kind"] = kind
            if detail:
                ob["sk_detail"] = 1
            if source:
                ob["sk_source"] = 1
            if mount_z is not None or hang:
                ob["sk_mount"] = 1                      # hangs on a wall or a ceiling: not tested for floating
            if hang:
                ob["sk_hang"] = 1
            return ob
        REGISTRY[type_] = dict(fn=make_, era=era, kind=kind, mount_z=mount_z, detail=detail, source=source, hang=hang, tags=list(tags))
        make_.type = type_
        return make_
    return deco


def make(type_: str, **kw):
    """Build a piece by its registered name."""
    if type_ not in REGISTRY:
        raise KeyError(f"no piece '{type_}'. Pieces: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[type_]["fn"](**kw)


def footprint(ob):
    """(width, depth, height) of a built piece in metres."""
    s = ob.get("sk_size", [0.5, 0.5, 0.5])
    return float(s[0]), float(s[1]), float(s[2])


def tops(ob):
    """World-space standing surfaces of a piece: [(centre Vector, z, w, d, rot_z_radians, label)]. Computed from the piece's own
    location and turn (pieces are placed at the top level), so it costs nothing."""
    out = []
    rz = ob.rotation_euler.z
    c, s = math.cos(rz), math.sin(rz)
    for t in ob.get("sk_tops", []):
        out.append((Vector((ob.location.x + c * t["x"] - s * t["y"], ob.location.y + s * t["x"] + c * t["y"], ob.location.z + t["z"])), ob.location.z + t["z"], t["w"], t["d"], rz, t["label"]))
    return out


# ----------------------------------------------------------------------------- small drawing helpers
def _flame(p: Parts, at, r: float = 0.02, h: float = 1.0, color="#FF8A1E", strength: float = 3.2):
    p.ball(r, at, p.glow(color, strength), squash=(1, 1, 2.3 * h), sub=1)


def _books(p: Parts, rnd, x0: float, x1: float, y: float, z: float, depth: float, hmax: float = 0.3, palette=None):
    """A row of books standing on a shelf between x0 and x1."""
    palette = palette or ["#7A2E2A", "#2D4A6B", "#3F5F3A", "#8A6A2E", "#5A3A5E", "#9A8F7A", "#3A3A44", "#A04A2A"]
    x = x0
    while x < x1 - 0.03:
        w_ = rnd.uniform(0.025, 0.055)
        h_ = rnd.uniform(0.62, 1.0) * hmax
        d_ = depth * rnd.uniform(0.7, 0.95)
        if x + w_ > x1:
            break
        lean = rnd.uniform(-3, 3) if rnd.random() < 0.08 else 0
        p.box((w_, d_, h_), (x + w_ / 2, y, z), mat.solid(rnd.choice(palette), 0.6), rot=(0, lean, 0), bevel=0.002)
        x += w_ + 0.003


def _text(root, body: str, at, size: float = 0.1, color="#1A1814", rot=(90, 0, 0), align: str = "CENTER", extrude: float = 0.002, emit: float = 0.0, bold: bool = False):
    """Real lettering: a text object parented to a piece, facing -Y by default (rot turns it). Readable detail."""
    cu = bpy.data.curves.new(f"txt_{body[:10]}", "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.extrude = extrude
    cu.space_line = 0.9
    ob = bpy.data.objects.new(f"txt_{body[:10]}", cu)
    core.link(ob, "SET")
    ob.parent = root
    ob.location = at
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    cu.materials.append(mat.emit(color, emit, f"SK_txt_e_{color}_{emit}") if emit else mat.solid(color, 0.6))
    ob.visible_shadow = False
    return ob


def _grow(root, ob):
    root["sk_text"] = int(root.get("sk_text", 0)) + 1
    return ob


# ============================================================================= SEATS AND TABLES
@piece("throne", MED, "furniture")
def throne(p, tint=None, cushion="#8E1B24", width: float = 1.1):
    """A royal throne on a two-step base: carved dark wood, gold trim, red velvet seat and back panel, a crown finial."""
    w, d = width, 0.85
    p.box((w + 0.5, d + 0.3, 0.12), (0, 0, 0), "castle_stone", tint="#8B8579", bevel=0.015)
    p.box((w + 0.25, d + 0.1, 0.12), (0, 0, 0.12), "castle_stone", tint="#9A948A", bevel=0.015)
    z0 = 0.24
    p.box((w, d, 0.3), (0, 0, z0), DW, bevel=0.02)
    p.box((w - 0.16, d - 0.14, 0.1), (0, -0.03, z0 + 0.3), mat.solid(cushion, 0.92, sheen=0.9), bevel=0.02)
    for sx in (-1, 1):
        p.box((0.12, d * 0.85, 0.34), (sx * (w / 2 - 0.06), -0.04, z0 + 0.3), DW, bevel=0.02)
        p.box((0.16, 0.22, 0.05), (sx * (w / 2 - 0.06), -d * 0.35, z0 + 0.64), GOLD, bevel=0.008)
    p.box((w, 0.14, 1.75), (0, d / 2 - 0.07, z0), DW, bevel=0.02)
    p.box((w - 0.3, 0.03, 1.3), (0, d / 2 - 0.15, z0 + 0.3), mat.solid(cushion, 0.92, sheen=0.9), bevel=0.01)
    p.box((w + 0.1, 0.18, 0.1), (0, d / 2 - 0.07, z0 + 1.75), DW, bevel=0.02)
    for sx in (-1, 1):
        p.box((0.14, 0.2, 2.0), (sx * (w / 2 + 0.0), d / 2 - 0.07, z0), DW, bevel=0.02)
        p.ball(0.07, (sx * w / 2, d / 2 - 0.07, z0 + 2.04), GOLD, sub=2)
    p.box((0.5, 0.14, 0.3), (0, d / 2 - 0.07, z0 + 1.85), GOLD, bevel=0.01)
    for k in (-1, 0, 1):
        p.box((0.1, 0.14, 0.2 if k else 0.3), (k * 0.17, d / 2 - 0.07, z0 + 2.05), GOLD, bevel=0.01)
    p.top((0, 0), (w, d), z0 + 0.4, "seat")


@piece("banquet_table", OLD, "furniture")
def banquet_table(p, length: float = 3.2, width: float = 1.0, tint=None, cloth: bool = False):
    """A long heavy hall table on two slab trestles joined by a stretcher."""
    h = 0.78
    p.box((length, width, 0.07), (0, 0, h - 0.07), W, tint or "#7A5A3A", bevel=0.012)
    for sx in (-1, 1):
        x = sx * (length / 2 - 0.4)
        p.box((0.1, width * 0.8, h - 0.07), (x, 0, 0), DW, bevel=0.012)
        p.box((0.1, width * 0.9, 0.08), (x, 0, 0), DW, bevel=0.01)
        p.box((0.08, width * 0.5, 0.06), (x, 0, h - 0.18), DW, bevel=0.008)
    p.box((length - 0.8, 0.08, 0.1), (0, 0, 0.25), DW, bevel=0.01)
    if cloth:
        p.box((length * 0.96, width * 0.5, 0.01), (0, 0, h), CLOTH, tint="#E8DDC3", bevel=0.002)
    p.top((0, 0), (length - 0.1, width - 0.1), h, "table")


@piece("trestle_table", OLD, "furniture")
def trestle_table(p, length: float = 1.8, width: float = 0.7, tint=None):
    h = 0.76
    p.box((length, width, 0.04), (0, 0, h - 0.04), W, tint or "#8A6A44", bevel=0.008)
    for sx in (-1, 1):
        x = sx * (length / 2 - 0.3)
        for sy in (-1, 1):
            p.rod((x - 0.12 * sx * 0, sy * width * 0.38, 0.02), (x, sy * 0.06, h - 0.04), 0.03, DW)
        p.box((0.05, width * 0.8, 0.05), (x, 0, h - 0.08), DW, bevel=0.005)
    p.box((length - 0.6, 0.05, 0.05), (0, 0, 0.3), DW, bevel=0.005)
    p.top((0, 0), (length - 0.1, width - 0.1), h, "table")


@piece("bench", OLD, "furniture")
def bench(p, length: float = 1.6, tint=None, back: bool = False):
    p.box((length, 0.34, 0.06), (0, 0, 0.42), W, tint, bevel=0.008)
    for sx in (-1, 1):
        p.box((0.07, 0.3, 0.42), (sx * (length / 2 - 0.15), 0, 0), W, tint, bevel=0.008)
    p.box((length - 0.4, 0.04, 0.08), (0, 0, 0.18), W, tint, bevel=0.004)
    if back:
        p.box((length, 0.05, 0.4), (0, 0.15, 0.48), W, tint, bevel=0.008)
    p.top((0, 0), (length - 0.05, 0.3), 0.48, "seat")


@piece("stool", ANY, "furniture")
def stool(p, tint=None, height: float = 0.46):
    p.cyl(0.19, 0.05, (0, 0, height - 0.05), W, tint, seg=18, bevel=0.006)
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.5
        p.rod((math.cos(a) * 0.17, math.sin(a) * 0.17, height - 0.05), (math.cos(a) * 0.24, math.sin(a) * 0.24, 0.0), 0.022, W, tint)
    p.top((0, 0), (0.3, 0.3), height, "seat")


@piece("chair_dining", ANY, "furniture")
def chair_dining(p, tint=None, seat_h: float = 0.46):
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((0.04, 0.04, seat_h), (sx * 0.19, sy * 0.19, 0), W, tint, bevel=0.004)
        p.box((0.04, 0.04, 0.5), (sx * 0.19, 0.19, seat_h), W, tint, bevel=0.004)
    p.box((0.44, 0.44, 0.04), (0, 0, seat_h - 0.04), W, tint, bevel=0.006)
    p.box((0.42, 0.03, 0.07), (0, 0.19, seat_h + 0.38), W, tint, bevel=0.004)
    for x in (-0.1, 0.0, 0.1):
        p.box((0.025, 0.02, 0.32), (x, 0.19, seat_h + 0.06), W, tint, bevel=0.003)
    p.top((0, 0), (0.4, 0.4), seat_h, "seat")


@piece("chair_arm", OLD, "furniture")
def chair_arm(p, tint=None, upholstery: str = "leather"):
    """An armchair: carved frame, padded seat and back."""
    p.box((0.62, 0.6, 0.08), (0, 0, 0.36), DW, bevel=0.01)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((0.06, 0.06, 0.36), (sx * 0.27, sy * 0.25, 0), DW, bevel=0.006)
        p.box((0.07, 0.56, 0.3), (sx * 0.3, 0, 0.44), DW, bevel=0.01)
        p.box((0.09, 0.4, 0.04), (sx * 0.3, -0.02, 0.74), DW, bevel=0.01)
    p.box((0.5, 0.52, 0.12), (0, -0.02, 0.44), upholstery, tint, bevel=0.03)
    p.box((0.58, 0.1, 0.62), (0, 0.27, 0.44), upholstery, tint, bevel=0.03)
    p.box((0.6, 0.1, 0.08), (0, 0.29, 1.06), DW, bevel=0.01)
    p.top((0, -0.02), (0.4, 0.4), 0.56, "seat")


@piece("chair_office", MODERN, "furniture")
def chair_office(p, color="#2B2F3A", seat_h: float = 0.48):
    """A swivel office chair: five-star base on castors, gas lift, padded seat and mesh-style back, arms."""
    pm = mat.solid("#202226", 0.5)
    cm = mat.solid(color, 0.85, sheen=0.3)
    for k in range(5):
        a = 2 * math.pi * k / 5
        p.rod((0, 0, 0.1), (math.cos(a) * 0.3, math.sin(a) * 0.3, 0.06), 0.022, pm)
        p.ball(0.03, (math.cos(a) * 0.3, math.sin(a) * 0.3, 0.03), pm, sub=1)
    p.cyl(0.03, seat_h - 0.1, (0, 0, 0.1), BM, seg=10)
    p.box((0.5, 0.48, 0.08), (0, 0, seat_h - 0.07), cm, bevel=0.025)
    p.box((0.46, 0.06, 0.52), (0, 0.22, seat_h + 0.02), cm, rot=(-6, 0, 0), bevel=0.025)
    p.box((0.05, 0.05, 0.16), (0, 0.18, seat_h - 0.05), pm, bevel=0.01)
    for sx in (-1, 1):
        p.box((0.04, 0.04, 0.2), (sx * 0.26, 0.04, seat_h), pm, bevel=0.005)
        p.box((0.05, 0.26, 0.03), (sx * 0.26, -0.04, seat_h + 0.2), pm, bevel=0.008)
    p.top((0, 0), (0.4, 0.4), seat_h, "seat")


@piece("sofa", HOME, "furniture")
def sofa(p, length: float = 2.0, color="#5E6B78", tint=None):
    """A three-seat sofa: frame, loose seat cushions, back cushions, arms, short feet."""
    d = 0.92
    cm = mat.solid(color, 0.92, sheen=0.4)
    dm = mat.solid("#3D3631", 0.6)
    p.box((length, d, 0.18), (0, 0, 0.1), cm, bevel=0.03)
    for sx in (-1, 1):
        p.box((0.22, d, 0.6), (sx * (length / 2 - 0.11), 0, 0.1), cm, bevel=0.05)
        p.box((0.06, 0.06, 0.1), (sx * (length / 2 - 0.15), -d / 2 + 0.1, 0), dm)
        p.box((0.06, 0.06, 0.1), (sx * (length / 2 - 0.15), d / 2 - 0.1, 0), dm)
    p.box((length - 0.44, 0.22, 0.52), (0, d / 2 - 0.11, 0.28), cm, bevel=0.05)
    n = 3 if length > 1.6 else 2
    cw = (length - 0.44) / n
    for i in range(n):
        x = -(length - 0.44) / 2 + cw * (i + 0.5)
        p.box((cw - 0.02, d - 0.3, 0.16), (x, -0.08, 0.28), cm, bevel=0.04)
        p.box((cw - 0.04, 0.16, 0.38), (x, d / 2 - 0.3, 0.44), cm, rot=(-12, 0, 0), bevel=0.05)
    p.top((0, 0), (length - 0.5, d - 0.3), 0.46, "seat")


# ============================================================================= DESKS, SHELVES, STORAGE
@piece("desk_writing", OLD, "furniture")
def desk_writing(p, tint=None):
    """A period writing desk: carved dark top with a leather inlay, a drawer row, turned legs."""
    L, D, h = 1.3, 0.68, 0.76
    p.box((L, D, 0.05), (0, 0, h - 0.05), DW, tint, bevel=0.01)
    p.box((L - 0.2, D - 0.18, 0.012), (0, 0, h), "leather", "#3A2A1C", bevel=0.002)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.cyl(0.035, h - 0.05, (sx * (L / 2 - 0.07), sy * (D / 2 - 0.07), 0), DW, tint, top=0.028, seg=10)
    p.box((L - 0.2, D - 0.1, 0.14), (0, 0.02, h - 0.2), DW, tint, bevel=0.008)
    for x in (-0.38, 0, 0.38):
        p.box((0.32, 0.02, 0.1), (x, -D / 2 + 0.06, h - 0.18), DW, "#6A4A30", bevel=0.004)
        p.ball(0.014, (x, -D / 2 + 0.045, h - 0.13), GOLD, sub=1)
    p.top((0, 0), (L - 0.2, D - 0.2), h + 0.012, "desk")


@piece("desk_office", MODERN, "furniture")
def desk_office(p, length: float = 1.6, depth: float = 0.78, tint=None, color="#C9B79A"):
    """A modern office desk: laminate top, metal legs, a fixed drawer pedestal, a modesty panel."""
    h = 0.74
    top = mat.solid(color, 0.5)
    mm = mat.solid("#4A4D52", 0.4, 0.9)
    p.box((length, depth, 0.035), (0, 0, h - 0.035), top, bevel=0.004)
    for sx in (-1, 1):
        p.box((0.045, depth - 0.1, h - 0.035), (sx * (length / 2 - 0.05) if sx > 0 else sx * (length / 2 - 0.05), 0, 0), mm, bevel=0.003)
    p.box((length - 0.2, 0.02, 0.4), (0, depth / 2 - 0.1, h - 0.45), mm, bevel=0.003)
    p.box((0.42, depth - 0.12, 0.6), (-length / 2 + 0.3, 0, 0.06), mat.solid("#B5B8BB", 0.45, 0.4), bevel=0.004)
    for z in (0.1, 0.28, 0.46):
        p.box((0.38, 0.015, 0.15), (-length / 2 + 0.3, -depth / 2 + 0.065, z), mat.solid("#D8DADC", 0.4), bevel=0.003)
        p.box((0.12, 0.02, 0.012), (-length / 2 + 0.3, -depth / 2 + 0.05, z + 0.11), mm, bevel=0.002)
    p.top((0.1, 0), (length - 0.9, depth - 0.1), h, "desk")
    p.top((0, 0.05), (length - 0.1, depth - 0.2), h, "desk_full")


@piece("meeting_table", MODERN, "furniture")
def meeting_table(p, length: float = 2.6, width: float = 1.1, color="#CDB89A"):
    """A meeting-room table: thick laminate top, two slab legs, a cable port."""
    h = 0.74
    top = mat.solid(color, 0.4)
    mm = mat.solid("#4A4D52", 0.4, 0.9)
    p.box((length, width, 0.04), (0, 0, h - 0.04), top, bevel=0.006)
    for sx in (-1, 1):
        p.box((0.06, width * 0.7, h - 0.04), (sx * (length / 2 - 0.35), 0, 0), mm, bevel=0.004)
        p.box((0.08, width * 0.85, 0.04), (sx * (length / 2 - 0.35), 0, 0), mm, bevel=0.004)
    p.box((0.12, 0.08, 0.006), (0, 0, h), mat.solid("#2B2D31", 0.4), bevel=0.0)
    p.top((0, 0), (length - 0.2, width - 0.2), h, "table")


@piece("bookcase", ANY, "furniture")
def bookcase(p, width: float = 1.0, height: float = 2.1, seed: int = 0, tint=None, doors: bool = False):
    """A tall bookcase with five shelves, rows of books and a few lying stacks."""
    rnd = random.Random(seed)
    D = 0.32
    p.box((width, 0.02, height), (0, D / 2 - 0.01, 0), W, tint or "#6A4B30", bevel=0.004)
    for sx in (-1, 1):
        p.box((0.03, D, height), (sx * (width / 2 - 0.015), 0, 0), W, tint or "#6A4B30", bevel=0.006)
    p.box((width + 0.06, D + 0.04, 0.04), (0, 0, height), W, tint or "#6A4B30", bevel=0.008)
    n = 5
    for i in range(n):
        z = 0.08 + (height - 0.16) * i / n
        p.box((width - 0.06, D - 0.02, 0.025), (0, -0.0, z), W, tint or "#6A4B30", bevel=0.003)
        gap = (height - 0.16) / n - 0.03
        x0 = -width / 2 + 0.04
        if rnd.random() < 0.8:
            _books(p, rnd, x0, x0 + (width - 0.08) * rnd.uniform(0.55, 1.0), 0.0, z + 0.0125, D - 0.06, min(gap - 0.03, 0.34))
        else:
            for k in range(3):
                p.box((0.28, 0.2, 0.04), (x0 + 0.18 + k * 0.1, 0.0, z + 0.0125 + k * 0.04), mat.solid(rnd.choice(["#7A2E2A", "#2D4A6B", "#8A6A2E"]), 0.6), rot=(0, 0, rnd.uniform(-8, 8)), bevel=0.002)
    p.top((0, 0), (width - 0.1, D - 0.06), height + 0.04, "top")


@piece("shelf_jars", ANY, "furniture", mount_z=1.45)
def shelf_jars(p, length: float = 1.2, seed: int = 0, tint=None):
    """A wall shelf on brackets with jars, boxes and a small sack: kitchens, apothecaries, shops."""
    rnd = random.Random(seed)
    p.box((length, 0.24, 0.03), (0, 0, 0.0), W, tint, bevel=0.005)
    for sx in (-1, 1):
        p.box((0.03, 0.2, 0.16), (sx * (length / 2 - 0.1), 0.02, -0.15), DW, bevel=0.004)
    x = -length / 2 + 0.1
    while x < length / 2 - 0.1:
        k = rnd.random()
        if k < 0.45:
            r = rnd.uniform(0.04, 0.06)
            h = rnd.uniform(0.12, 0.2)
            p.lathe([(0, 0.03), (r, 0.03), (r * 1.05, 0.03 + h * 0.5), (r * 0.9, 0.03 + h * 0.85), (r * 0.55, 0.03 + h), (r * 0.55, 0.03 + h + 0.025), (0, 0.03 + h + 0.025)], (x, 0, 0), mat.surface("terracotta", tint=None) if rnd.random() < 0.5 else mat.solid(rnd.choice(["#7FA37A", "#C9B27A", "#B5704E"]), 0.35), seg=14)
            x += r * 2 + 0.03
        elif k < 0.8:
            wd, hh = rnd.uniform(0.09, 0.16), rnd.uniform(0.08, 0.14)
            p.box((wd, 0.12, hh), (x + wd / 2, 0, 0.03), mat.solid(rnd.choice(["#8A6A44", "#C9B79A", "#6A4B30"]), 0.8), bevel=0.004)
            x += wd + 0.03
        else:
            p.ball(0.06, (x + 0.06, 0, 0.09), CLOTH, squash=(1, 0.9, 1.1), sub=1)
            x += 0.14
    p.top((0, 0), (length, 0.22), 0.03, "shelf")


@piece("cabinet", ANY, "furniture")
def cabinet(p, width: float = 1.0, height: float = 1.9, tint=None, doors: int = 2):
    """A tall cupboard with panelled doors and a cornice."""
    D = 0.5
    p.box((width, D, height), (0, 0, 0.1), W, tint or "#6D4C31", bevel=0.01)
    p.box((width + 0.08, D + 0.06, 0.08), (0, -0.02, height + 0.1), W, tint or "#6D4C31", bevel=0.01)
    p.box((width + 0.04, D + 0.02, 0.1), (0, 0, 0.0), DW, bevel=0.008)
    dw = (width - 0.1) / doors
    for i in range(doors):
        x = -width / 2 + 0.05 + dw * (i + 0.5)
        p.box((dw - 0.02, 0.025, height - 0.18), (x, -D / 2 - 0.01, 0.16), W, tint or "#7A5A3A", bevel=0.006)
        p.box((dw - 0.18, 0.015, height * 0.34), (x, -D / 2 - 0.03, 0.26), W, tint or "#8A6A48", bevel=0.004)
        p.box((dw - 0.18, 0.015, height * 0.34), (x, -D / 2 - 0.03, height * 0.5 + 0.1), W, tint or "#8A6A48", bevel=0.004)
        p.ball(0.018, (x + (dw / 2 - 0.06) * (1 if i % 2 == 0 else -1), -D / 2 - 0.045, height * 0.52), IRON, sub=1)
    p.top((0, 0), (width, D), height + 0.18, "top")


@piece("chest", OLD, "furniture")
def chest(p, width: float = 0.9, tint=None):
    """A banded travelling chest with a domed lid."""
    D, H = 0.5, 0.4
    p.box((width, D, H), (0, 0, 0.04), W, tint or "#6A4B30", bevel=0.01)
    for sx in (-1, 1):
        p.box((0.07, D + 0.02, H + 0.02), (sx * (width / 2 - 0.08), 0, 0.03), IRON, bevel=0.004)
    p.box((width + 0.02, D + 0.02, 0.1), (0, 0, H + 0.04), W, tint or "#6A4B30", bevel=0.02)
    p.box((width * 0.92, D * 0.86, 0.06), (0, 0, H + 0.14), W, tint or "#6A4B30", bevel=0.025)
    for sx in (-1, 1):
        p.box((0.06, D + 0.04, 0.16), (sx * (width / 2 - 0.08), 0, H + 0.04), IRON, bevel=0.004)
    p.box((0.08, 0.03, 0.1), (0, -D / 2 - 0.01, H - 0.03), GOLD, bevel=0.004)
    p.box((width, D, 0.04), (0, 0, 0.0), DW, bevel=0.006)
    p.top((0, 0), (width * 0.8, D * 0.6), H + 0.2, "lid")


@piece("bed", ANY, "furniture")
def bed(p, width: float = 1.4, length: float = 2.0, blanket="#3F5F8A", tint=None, posts: bool = True):
    """A bed with a headboard at +Y, mattress, blanket, two pillows and four posts."""
    wood = DW
    p.box((width + 0.1, length, 0.2), (0, 0, 0.15), wood, tint, bevel=0.01)
    p.box((width - 0.04, length - 0.08, 0.22), (0, -0.02, 0.35), mat.solid("#EDE6D6", 0.95, sheen=0.5), bevel=0.04)
    p.box((width, length * 0.6, 0.07), (0, -length * 0.16, 0.54), mat.surface("cloth", tint=blanket), bevel=0.03)
    p.box((width, 0.1, 0.075), (0, -length * 0.16 + length * 0.3, 0.54), mat.surface("cloth", tint="#E8DDC3"), bevel=0.03)
    for sx in (-1, 1):
        p.box((width * 0.4, 0.34, 0.12), (sx * width * 0.23, length / 2 - 0.3, 0.57), mat.solid("#F4F0E8", 0.95, sheen=0.6), bevel=0.05)
    p.box((width + 0.1, 0.08, 1.0), (0, length / 2, 0.0), wood, tint, bevel=0.015)
    p.box((width + 0.1, 0.06, 0.45), (0, -length / 2, 0.0), wood, tint, bevel=0.015)
    if posts:
        for sx in (-1, 1):
            p.box((0.07, 0.07, 1.2), (sx * (width / 2 + 0.05), length / 2, 0.0), wood, tint, bevel=0.01)
            p.ball(0.045, (sx * (width / 2 + 0.05), length / 2, 1.22), wood, sub=1)
    p.top((0, -length * 0.2), (width - 0.2, length * 0.5), 0.58, "bed")


@piece("wardrobe", OLD, "furniture")
def wardrobe(p, tint=None):
    D, Wd, H = 0.6, 1.2, 2.0
    p.box((Wd, D, H), (0, 0, 0.1), W, tint or "#5E4630", bevel=0.01)
    p.box((Wd + 0.1, D + 0.06, 0.09), (0, -0.02, H + 0.1), W, tint or "#5E4630", bevel=0.01)
    for sx in (-1, 1):
        p.box((Wd / 2 - 0.05, 0.025, H - 0.3), (sx * Wd / 4, -D / 2 - 0.01, 0.2), W, tint or "#74543A", bevel=0.006)
        p.box((Wd / 2 - 0.24, 0.015, H * 0.6), (sx * Wd / 4, -D / 2 - 0.03, 0.55), W, tint or "#85633F", bevel=0.004)
        p.ball(0.02, (sx * 0.08, -D / 2 - 0.045, 1.05), GOLD, sub=1)
    for sx in (-1, 1):
        p.box((0.08, 0.08, 0.1), (sx * (Wd / 2 - 0.05), -D / 2 + 0.05, 0.0), DW)
    p.top((0, 0), (Wd, D), H + 0.19, "top")


@piece("rug", ANY, "floor")
def rug(p, size=(2.4, 1.6), surface="carpet_red", border="#C9A44A", inner=None, tint=None):
    """A floor rug with a border band, an optional inner field in a second colour, and fringe."""
    w, d = size
    p.box((w, d, 0.008), (0, 0, 0), surface, tint, bevel=0.003)
    bm_ = mat.solid(border, 0.9, sheen=0.4)
    bw = 0.12
    for sy in (-1, 1):
        p.box((w - 0.1, bw * 0.5, 0.010), (0, sy * (d / 2 - bw), 0), bm_, bevel=0.002)
    for sx in (-1, 1):
        p.box((bw * 0.5, d - 0.1, 0.010), (sx * (w / 2 - bw), 0, 0), bm_, bevel=0.002)
    if inner:
        p.box((w - 4 * bw, d - 4 * bw, 0.011), (0, 0, 0), mat.solid(inner, 0.95, sheen=0.4), bevel=0.002)
    p.box((w * 0.3, d * 0.3, 0.012), (0, 0, 0), bm_, rot=(0, 0, 45), bevel=0.002)
    for sx in (-1, 1):
        for i in range(int(d / 0.07)):
            p.box((0.1, 0.012, 0.008), (sx * (w / 2 + 0.05), -d / 2 + 0.035 + i * 0.07, 0), CLOTH, "#E9DFC8", bevel=0.0)


# ============================================================================= WALL DECOR
@piece("tapestry", OLD, "wall", mount_z=0.6, detail=True)
def tapestry(p, width: float = 1.8, height: float = 2.6, base="#6F2A2F", seed: int = 0):
    """A woven wall hanging on a rod: a field with a gold border and a heraldic stag or tree woven in."""
    rnd = random.Random(seed)
    p.cyl(0.03, width + 0.3, (-(width + 0.3) / 2, -0.04, height), DW, seg=10, rot=(0, 90, 0))
    p.ball(0.05, (-(width + 0.3) / 2, -0.04, height), GOLD, sub=1)
    p.ball(0.05, ((width + 0.3) / 2, -0.04, height), GOLD, sub=1)
    p.grid(width, height - 0.05, (0, -0.045, 0.0), CLOTH, base, nx=14, ny=2, amp=0.008, waves=3, phase=rnd.uniform(0, 3))
    bm_ = mat.solid("#C9A44A", 0.85, sheen=0.4)
    bw = 0.09
    for z in (0.05, height - 0.14):
        p.box((width - 0.06, 0.012, bw), (0, -0.052, z), bm_, bevel=0.001)
    for sx in (-1, 1):
        p.box((bw, 0.012, height - 0.3), (sx * (width / 2 - bw), -0.052, 0.12), bm_, bevel=0.001)
    cm = mat.solid("#E9DFC8", 0.9)
    gm = mat.solid("#2F5A3A", 0.9)
    p.box((0.05, 0.012, height * 0.3), (0, -0.055, height * 0.2), mat.solid("#4A3322", 0.9), bevel=0.0)           # trunk
    for k, (dz, rr) in enumerate(((0.58, 0.46), (0.74, 0.36), (0.88, 0.26))):
        p.ball(rr * width * 0.32, (0, -0.056, height * dz * 0.9), gm, squash=(1, 0.04, 0.85), sub=1)
    for sx in (-1, 1):
        for z in (0.35, 0.6, 0.78):
            p.ball(0.04, (sx * width * 0.26, -0.056, height * z), cm, squash=(1, 0.1, 1), sub=1)
    p.box((0.5 * width, 0.012, 0.03), (0, -0.056, height * 0.12), cm, bevel=0.0)
    for i in range(int(width / 0.06)):
        p.box((0.014, 0.01, 0.09), (-width / 2 + 0.03 + i * 0.06, -0.046, -0.07), bm_, bevel=0.0)


def banner(at=(0, 0, 3.0), rot_z: float = 0.0, name: str = "banner", coll: str = "SET", size=(0.9, 2.2), color="#A3231F", trim="#EDC04A", emblem="lion", **_):
    """A hanging cloth banner with a swallow tail, gold border and a crest (lion, sun, tree, star): the shared kit's banner, tagged
    for the audit. Unlike other pieces its origin is the TOP centre of the banner, on the wall face (put at.z at the hanging height)."""
    b = build.banner(name, at=at, rot_z=rot_z, size=size, color=color, trim=trim, emblem=emblem, coll=coll)
    tag(b, "banner", "prop")
    b["sk_size"] = [size[0] + 0.3, 0.12, size[1]]
    b["sk_detail"] = 1
    b["sk_era"] = list(OLD)
    b["sk_piece_kind"] = "wall"
    b["sk_mount"] = 1
    return b


REGISTRY["banner"] = dict(fn=banner, era=OLD, kind="wall", mount_z=3.0, detail=True, source=False, hang=False, tags=[])
banner.type = "banner"


@piece("painting_framed", ANY, "wall", mount_z=1.3, detail=True)
def painting_framed(p, width: float = 0.9, height: float = 0.7, seed: int = 0, frame="#B8923A"):
    """A framed landscape painting: gilt frame, a mount and a canvas with sky, hills and a lit foreground."""
    rnd = random.Random(seed)
    fm = mat.solid(frame, 0.35, 0.8)
    fw = 0.07
    d = 0.045
    p.box((width, d, fw), (0, -d / 2, 0), fm, bevel=0.008)
    p.box((width, d, fw), (0, -d / 2, height - fw), fm, bevel=0.008)
    for sx in (-1, 1):
        p.box((fw, d, height - 2 * fw), (sx * (width / 2 - fw / 2), -d / 2, fw), fm, bevel=0.008)
    iw, ih = width - 2 * fw, height - 2 * fw
    sky = rnd.choice(["#8FB6D8", "#E5B887", "#9AA7C0"])
    p.box((iw, 0.01, ih), (0, -0.01, fw), mat.solid(sky, 0.7), bevel=0.0)
    for k, col in enumerate(("#6C8F5A", "#4E7048", "#3A5A3A")):
        xs = [(-iw / 2 + iw * i / 8, ih * (0.28 + 0.1 * k + 0.07 * math.sin(i * 1.3 + rnd.uniform(0, 3) + k))) for i in range(9)]
        pts = [(-iw / 2, 0)] + xs + [(iw / 2, 0)]
        p.profile([(x, fw + z) for x, z in pts], -0.016 - k * 0.002, -0.012 - k * 0.002, mat.solid(col, 0.8), bevel=0.0)
    p.ball(0.06 * width, (iw * rnd.uniform(-0.25, 0.25), -0.012, fw + ih * 0.72), mat.solid("#FFE9A8", 0.4), squash=(1, 0.1, 1), sub=1)


@piece("mirror", ANY, "wall", mount_z=1.1)
def mirror(p, width: float = 0.7, height: float = 1.0, frame="#7A5A30"):
    p.box((width, 0.05, height), (0, -0.025, 0), mat.solid(frame, 0.45, 0.4), bevel=0.012)
    p.box((width - 0.12, 0.01, height - 0.12), (0, -0.055, 0.06), mat.solid("#C9D4DA", 0.03, 1.0), bevel=0.0)
    p.cyl(0.05, 0.05, (0, -0.025, height), mat.solid(frame, 0.45, 0.4), seg=10, rot=(90, 0, 0))


@piece("curtain_pair", ANY, "wall", mount_z=0.0)
def curtain_pair(p, width: float = 1.6, height: float = 2.4, color="#7A1F2B", tint=None, rod_h: float | None = None):
    """Two gathered curtains with a rod, finials and tie-backs, hanging from z = height down to the floor."""
    rod_h = rod_h or height
    p.cyl(0.015, width + 0.3, (-(width + 0.3) / 2, -0.06, rod_h), mat.solid("#B8923A", 0.3, 0.9), seg=8, rot=(0, 90, 0))
    for sx in (-1, 1):
        p.ball(0.03, (sx * (width + 0.3) / 2, -0.06, rod_h), GOLD, sub=1)
        p.grid(width * 0.42, rod_h - 0.02, (sx * width * 0.3, -0.08, 0.0), mat.solid(tint or color, 0.92, sheen=0.9), None, nx=24, ny=2, amp=0.035, waves=5, phase=sx)
        p.box((0.06, 0.1, 0.04), (sx * width * 0.17, -0.1, rod_h * 0.45), mat.solid("#C9A44A", 0.5), bevel=0.005)


@piece("shield_wall", OLD, "wall", mount_z=1.9, detail=True)
def shield_wall(p, color="#A3231F", trim="#C9A44A", emblem: bool = True):
    """A heater shield hung on a wall: painted field, a metal rim and boss, a cross charge."""
    pts = [(-0.3, 0.4), (0.3, 0.4), (0.3, 0.1), (0.2, -0.1), (0.0, -0.3), (-0.2, -0.1), (-0.3, 0.1)]
    p.profile([(x, z) for x, z in pts], -0.03, 0.0, mat.solid(color, 0.55), bevel=0.01)
    p.box((0.62, 0.02, 0.025), (0, -0.04, 0.36), mat.solid("#8A8D91", 0.3, 0.9), bevel=0.0)
    p.ball(0.06, (0, -0.045, 0.14), mat.solid("#8A8D91", 0.3, 0.9), squash=(1, 0.5, 1), sub=1)
    if emblem:
        p.box((0.08, 0.01, 0.5), (0, -0.04, -0.05), mat.solid(trim, 0.4, 0.6), bevel=0.0)
        p.box((0.36, 0.01, 0.08), (0, -0.04, 0.15), mat.solid(trim, 0.4, 0.6), bevel=0.0)


@piece("wall_clock", MODERN, "wall", mount_z=2.3, detail=True)
def wall_clock(p, radius: float = 0.17, hour: float = 10.0, minute: float = 8.0):
    p.cyl(radius + 0.015, 0.04, (0, 0, 0), mat.solid("#2B2D31", 0.4), seg=32, rot=(90, 0, 0))
    p.cyl(radius, 0.01, (0, -0.043, 0), mat.solid("#F4F2EC", 0.5), seg=32, rot=(90, 0, 0))
    for k in range(12):
        a = math.radians(k * 30)
        p.box((0.012, 0.004, 0.03 if k % 3 == 0 else 0.016), (math.sin(a) * radius * 0.84, -0.05, math.cos(a) * radius * 0.84), mat.solid("#1C1C1E", 0.5), rot=(0, -k * 30, 0), mid=True, bevel=0.0)
    for ang, ln, wd in ((hour * 30 + minute * 0.5, 0.55, 0.012), (minute * 6, 0.8, 0.008)):
        a = math.radians(ang)
        p.box((wd, 0.004, radius * ln), (math.sin(a) * radius * ln / 2, -0.054, math.cos(a) * radius * ln / 2), mat.solid("#1C1C1E", 0.5), rot=(0, -ang, 0), mid=True, bevel=0.0)
    p.cyl(0.012, 0.01, (0, -0.056, 0), mat.solid("#B02A2A", 0.4), seg=10, rot=(90, 0, 0))


# ============================================================================= LIGHT SOURCES (emissive part + a real light)
def _candle(p: Parts, at, h: float = 0.12, r: float = 0.011, light: bool = False, power: float = 8.0, shadow: bool = False, name="candle"):
    p.cyl(r, h, at, mat.solid("#EFE6CF", 0.6), seg=8)
    _flame(p, (at[0], at[1], at[2] + h + 0.025), 0.011, 1.0)
    if light:
        p.light(name, (at[0], at[1], at[2] + h + 0.05), "#FFB86B", power, 0.03, shadow)


@piece("table_candle", OLD, "light", source=True)
def table_candle(p, height: float = 0.16, power: float = 10.0):
    """A candle in a brass holder: wax, a flame that glows, and a small warm light."""
    bm_ = mat.solid("#B8923A", 0.3, 0.9)
    p.lathe([(0, 0), (0.05, 0), (0.05, 0.012), (0.018, 0.03), (0.014, 0.08), (0.025, 0.1), (0.0, 0.1)], (0, 0, 0), bm_, seg=14)
    _candle(p, (0, 0, 0.1), height, 0.013, True, power, False, "table_candle")


@piece("candelabra", OLD, "light", source=True)
def candelabra(p, height: float = 1.4, arms: int = 5, power: float = 40.0):
    """A floor candle stand: iron base, a stem with a bulb, a crown of arms each carrying a candle; one real light at the crown."""
    ir = mat.surface(IRON)
    p.lathe([(0, 0), (0.18, 0), (0.18, 0.03), (0.06, 0.06), (0.025, 0.1), (0.025, height * 0.6), (0.05, height * 0.63), (0.025, height * 0.66), (0.02, height - 0.06), (0.0, height - 0.06)], (0, 0, 0), ir, seg=16)
    top = height - 0.06
    for k in range(arms):
        a = 2 * math.pi * k / arms
        r = 0.3 if k else 0.0
        if k == 0:
            _candle(p, (0, 0, top), 0.16, 0.014)
            continue
        ang = 2 * math.pi * (k - 1) / (arms - 1)
        x, y = math.cos(ang) * 0.24, math.sin(ang) * 0.24
        p.rod((0, 0, top - 0.02), (x * 0.9, y * 0.9, top + 0.1), 0.012, ir)
        p.cyl(0.03, 0.02, (x, y, top + 0.09), ir, seg=10)
        _candle(p, (x, y, top + 0.11), 0.14, 0.013)
    p.light("candelabra", (0, 0, top + 0.4), "#FFB86B", power, 0.1, False)


@piece("lantern", ANY, "light", source=True)
def lantern(p, power: float = 45.0, hanging: bool = False):
    """A lantern: iron cage, glowing glass, a candle, a ring on top (hanging=True adds a chain 0.6 m long)."""
    ir = mat.surface(IRON)
    gl = p.glow("#FFC477", 3.0)
    p.box((0.14, 0.14, 0.02), (0, 0, 0), ir, bevel=0.003)
    p.box((0.1, 0.1, 0.2), (0, 0, 0.02), gl, bevel=0.0)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((0.012, 0.012, 0.21), (sx * 0.06, sy * 0.06, 0.02), ir)
    p.cyl(0.09, 0.07, (0, 0, 0.23), ir, top=0.02, seg=4, rot=(0, 0, 45))
    p.cyl(0.004, 0.04, (0, 0, 0.3), ir, seg=6)
    p.ball(0.03, (0, 0, 0.34), ir, squash=(1, 0.2, 1), sub=1)
    if hanging:
        p.rod((0, 0, 0.34), (0, 0, 0.94), 0.005, ir, seg=4)
    p.light("lantern", (0, 0, 0.14), "#FFBE70", power, 0.06, False)


@piece("torch_wall", OLD, "light", mount_z=2.1, source=True)
def torch_wall(p, power: float = 40.0):
    """A wall torch in an iron sconce (the shared kit's torch, built here so it carries the audit tags and its light)."""
    ir = mat.surface(IRON)
    p.box((0.06, 0.04, 0.2), (0, -0.02, 0.0), ir, bevel=0.004)
    p.rod((0, -0.04, 0.12), (0, -0.2, 0.28), 0.02, ir, seg=6)
    p.cyl(0.05, 0.1, (0, -0.2, 0.2), ir, top=0.07, seg=10)
    p.rod((0, -0.2, 0.2), (0, -0.2, 0.62), 0.03, mat.surface(DW), seg=8)
    p.cyl(0.07, 0.1, (0, -0.2, 0.58), mat.solid("#3A2A1C", 0.9), top=0.05, seg=10)
    p.ball(0.08, (0, -0.2, 0.72), p.glow("#FF7A12", 3.2), squash=(0.85, 0.85, 1.8), sub=2)
    p.ball(0.05, (0.02, -0.2, 0.67), p.glow("#FFB04A", 3.8), squash=(0.85, 0.85, 1.4), sub=1)
    p.light("torch", (0, -0.22, 0.78), "#FFB067", power, 0.1, False)


@piece("wall_sconce", ANY, "light", mount_z=1.9, source=True)
def wall_sconce(p, power: float = 25.0, kind: str = "candle"):
    """A wall sconce: backplate, a curved arm, a cup and a candle (kind="candle") or an electric glow (kind="modern")."""
    if kind == "modern":
        pm = mat.solid("#2B2D31", 0.4, 0.8)
        p.box((0.14, 0.03, 0.24), (0, -0.015, 0), pm, bevel=0.005)
        p.box((0.1, 0.07, 0.18), (0, -0.065, 0.03), p.glow("#FFE6BD", 3.0), bevel=0.01)
        p.light("sconce", (0, -0.14, 0.12), "#FFE0B0", power * 1.5, 0.05, False)
        return
    ir = mat.solid("#B8923A", 0.3, 0.9)
    p.box((0.1, 0.02, 0.26), (0, -0.01, 0.0), ir, bevel=0.004)
    p.rod((0, -0.02, 0.1), (0, -0.16, 0.06), 0.012, ir, seg=6)
    p.rod((0, -0.16, 0.06), (0, -0.16, 0.12), 0.012, ir, seg=6)
    p.cyl(0.045, 0.02, (0, -0.16, 0.12), ir, top=0.03, seg=10)
    _candle(p, (0, -0.16, 0.14), 0.16, 0.014)
    p.light("sconce", (0, -0.18, 0.36), "#FFB86B", power, 0.06, False)


@piece("chandelier", OLD, "light", source=True, hang=True)
def chandelier(p, radius: float = 0.7, drop: float = 1.2, candles: int = 10, power: float = 150.0):
    """A hanging iron-wheel chandelier on a chain from the ceiling (the origin is the ceiling point; the wheel hangs `drop` below):
    a ring with candle cups all round, each with a candle and flame; one real light inside the ring."""
    ir = mat.surface(IRON)
    zr = -drop
    p.rod((0, 0, 0), (0, 0, zr + 0.2), 0.012, ir, seg=6)
    for k in range(6):
        a = 2 * math.pi * k / 6
        p.rod((math.cos(a) * radius, math.sin(a) * radius, zr), (0, 0, zr + 0.3), 0.01, ir, seg=6)
    n = 48
    for k in range(n):
        a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        p.rod((math.cos(a0) * radius, math.sin(a0) * radius, zr), (math.cos(a1) * radius, math.sin(a1) * radius, zr), 0.02, ir, seg=6)
    p.ball(0.07, (0, 0, zr + 0.3), ir, sub=1)
    p.ball(0.05, (0, 0, zr - 0.1), ir, sub=1)
    for k in range(candles):
        a = 2 * math.pi * k / candles
        x, y = math.cos(a) * radius, math.sin(a) * radius
        p.cyl(0.035, 0.03, (x, y, zr), ir, seg=8)
        _candle(p, (x, y, zr + 0.03), 0.17, 0.016)
    p.light("chandelier", (0, 0, zr + 0.35), "#FFB86B", power, 0.25, False)
    p.light("chandelier_low", (0, 0, zr - 0.2), "#FFC888", power * 0.35, 0.2, False)


@piece("brazier", OLD, "light", source=True)
def brazier(p, power: float = 110.0):
    """A tall iron brazier on three legs: a bowl of glowing coals and a rising flame, with a warm light."""
    ir = mat.surface(IRON)
    for k in range(3):
        a = 2 * math.pi * k / 3
        p.rod((math.cos(a) * 0.26, math.sin(a) * 0.26, 0.0), (math.cos(a) * 0.08, math.sin(a) * 0.08, 0.65), 0.025, ir, seg=6)
    p.lathe([(0, 0.62), (0.2, 0.62), (0.34, 0.8), (0.36, 0.86), (0.32, 0.86), (0.18, 0.72), (0, 0.7)], (0, 0, 0), ir, seg=18)
    p.ball(0.28, (0, 0, 0.82), p.glow("#FF5A1A", 4.0), squash=(1, 1, 0.3), sub=2)
    for dx, dy, s in ((0, 0, 1.0), (0.1, 0.05, 0.7), (-0.09, -0.05, 0.75), (0.02, -0.1, 0.55)):
        p.ball(0.12 * s, (dx, dy, 0.98 + 0.12 * s), p.glow("#FF7A12", 3.2), squash=(1, 1, 2.2), sub=2)
    p.ball(0.07, (0, 0, 1.12), p.glow("#FFB04A", 4.0), squash=(1, 1, 2.0), sub=1)
    p.light("brazier", (0, 0, 1.2), "#FF9A4A", power, 0.2, False)


@piece("campfire", ANY, "light", source=True)
def campfire(p, power: float = 200.0):
    """A ring of stones round crossed logs and flames."""
    for k in range(10):
        a = 2 * math.pi * k / 10
        p.ball(0.1, (math.cos(a) * 0.45, math.sin(a) * 0.45, 0.07), "fieldstone", squash=(1, 1, 0.7), sub=1)
    for k in range(5):
        a = 2 * math.pi * k / 5
        p.box((0.7, 0.1, 0.1), (0, 0, 0.1), "bark", rot=(0, 0, math.degrees(a)), bevel=0.01)
    for dx, dy, s in ((0, 0, 1.0), (0.1, 0.06, 0.7), (-0.1, -0.05, 0.8)):
        p.ball(0.14 * s, (dx, dy, 0.28 + 0.15 * s), p.glow("#FF7A12", 3.2), squash=(1, 1, 2.2), sub=2)
    p.ball(0.07, (0, 0, 0.5), p.glow("#FFB04A", 4.0), squash=(1, 1, 2.0), sub=1)
    p.light("campfire", (0, 0, 0.5), "#FF9A4A", power, 0.2, True)


@piece("fireplace_set", OLD, "small")
def fireplace_set(p, logs: bool = True):
    """Hearth tools: a stack of split logs, a poker and tongs on a stand, a bellows."""
    ir = mat.surface(IRON)
    if logs:
        for i in range(3):
            for j in range(3 - i):
                p.box((0.4, 0.13, 0.12), (j * 0.15 - (2 - i) * 0.075 + 0.075, 0.0, i * 0.12), "bark", rot=(0, 0, 0), bevel=0.02)
    p.lathe([(0, 0), (0.1, 0), (0.1, 0.02), (0.015, 0.04), (0.012, 0.6), (0, 0.6)], (0.5, 0.0, 0), ir, seg=10)
    p.rod((0.5, 0, 0.58), (0.58, 0.04, 0.12), 0.01, ir, seg=6)
    p.rod((0.5, 0, 0.58), (0.44, -0.04, 0.2), 0.01, ir, seg=6)
    p.box((0.32, 0.15, 0.06), (0.9, 0, 0.0), W, bevel=0.01, rot=(0, 0, 20))
    p.box((0.2, 0.1, 0.08), (0.9, 0.1, 0.06), mat.surface("leather"), bevel=0.02, rot=(0, 0, 20))


@piece("ceiling_light_panel", MODERN, "light", source=True, hang=True)
def ceiling_light_panel(p, size=(0.6, 0.6), power: float = 45.0, color="#F4F6FF"):
    """A flush panel light in a suspended ceiling (origin on the ceiling plane, facing down): an emissive panel in a thin frame,
    with a soft rectangular area light under it."""
    w, d = size
    p.box((w, d, 0.02), (0, 0, -0.03), mat.solid("#D8D9DB", 0.5), bevel=0.0)
    p.box((w - 0.05, d - 0.05, 0.01), (0, 0, -0.04), p.glow(color, 5.5), bevel=0.0)
    p.light("panel", (0, 0, -0.3), color, power, 0.3, False, "AREA", aim=(0, 0, -3), size=max(w, d))


@piece("desk_lamp", MODERN, "light", source=True)
def desk_lamp(p, power: float = 40.0):
    """An articulated desk lamp: weighted base, two arms, a hooded head with a glowing underside and a warm spot."""
    pm = mat.solid("#26282C", 0.4, 0.5)
    p.cyl(0.08, 0.02, (0, 0, 0), pm, seg=18)
    p.rod((0, 0, 0.02), (-0.08, 0, 0.3), 0.008, pm, seg=6)
    p.rod((-0.08, 0, 0.3), (0.12, 0, 0.42), 0.008, pm, seg=6)
    p.cyl(0.06, 0.09, (0.12, 0, 0.34), pm, top=0.02, seg=14, rot=(0, -50, 0))
    p.ball(0.02, (0.17, 0, 0.32), p.glow("#FFF1D6", 8.0), sub=1)
    p.light("desk_lamp", (0.18, 0, 0.3), "#FFE6C0", power, 0.03, False, "SPOT", aim=(0.4, 0, 0), size=100)


@piece("floor_lamp", HOME, "light", source=True)
def floor_lamp(p, power: float = 70.0, height: float = 1.6):
    """A standard lamp: round foot, slim pole, a fabric shade that glows warm, and a point light inside it."""
    pm = mat.solid("#2B2D31", 0.4, 0.6)
    p.cyl(0.14, 0.025, (0, 0, 0), pm, seg=20)
    p.cyl(0.015, height - 0.3, (0, 0, 0.02), pm, seg=8)
    p.lathe([(0.1, height - 0.32), (0.18, height - 0.05), (0.16, height - 0.05), (0.08, height - 0.32)], (0, 0, 0), p.glow("#FFDCA8", 2.2), seg=24)
    p.light("floor_lamp", (0, 0, height - 0.18), "#FFD8A0", power, 0.08, False)


# ============================================================================= FIRE-SIDE, KITCHEN AND TABLE SMALLS
@piece("barrel", OLD, "floor")
def barrel(p, height: float = 0.95, radius: float = 0.34, tint=None):
    """A stave barrel with iron hoops."""
    prof = [(0, 0), (radius * 0.82, 0), (radius * 0.9, height * 0.2), (radius, height * 0.5), (radius * 0.9, height * 0.8), (radius * 0.82, height), (0, height)]
    p.lathe(prof, (0, 0, 0), W, tint or "#6D4C31", seg=20)
    for z, rr in ((0.12, 0.86), (0.3, 0.95), (0.7, 0.95), (0.88, 0.86)):
        p.cyl(radius * rr + 0.012, 0.04, (0, 0, height * z - 0.02), IRON, seg=20)
    p.top((0, 0), (radius * 1.2, radius * 1.2), height, "lid")


@piece("crate", ANY, "floor")
def crate(p, size: float = 0.6, tint=None, slatted: bool = True):
    p.box((size, size, size), (0, 0, 0), W, tint, bevel=0.01)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((0.05, 0.05, size + 0.01), (sx * (size / 2 - 0.025), sy * (size / 2 - 0.025), 0), DW, bevel=0.004)
    p.box((size + 0.02, 0.04, 0.05), (0, 0, size * 0.5 - 0.025), DW, bevel=0.003) if slatted else None
    p.top((0, 0), (size * 0.9, size * 0.9), size, "lid")


@piece("sack", ANY, "floor")
def sack(p, tint="#B49A6C", size: float = 0.3):
    p.ball(size, (0, 0, size * 1.15), CLOTH, tint, squash=(1, 0.85, 1.15), sub=2)          # squashed round bag: its lowest point is z = 0
    p.ball(size * 0.35, (0, 0, size * 2.15), CLOTH, tint, squash=(1, 1, 0.5), sub=1)
    p.cyl(size * 0.18, 0.04, (0, 0, size * 1.95), "rope", seg=8)


@piece("basket", ANY, "small")
def basket(p, radius: float = 0.2, height: float = 0.22, handle: bool = True):
    """A wicker basket: a woven-banded round body and an arched handle."""
    wm = mat.solid("#B08A4E", 0.85)
    p.lathe([(0, 0), (radius * 0.8, 0), (radius * 0.95, height * 0.3), (radius, height), (radius * 0.94, height), (radius * 0.78, height * 0.1), (0, 0.02)], (0, 0, 0), wm, seg=18)
    for z in (0.3, 0.55, 0.8):
        p.cyl(radius * (0.82 + 0.18 * z) + 0.006, 0.012, (0, 0, height * z), mat.solid("#8A6A38", 0.9), seg=18)
    if handle:
        prev = None
        for k in range(10):
            a = math.pi * k / 9
            pt = (math.cos(a) * radius * 0.95, 0, height + math.sin(a) * radius * 1.0)
            if prev:
                p.rod(prev, pt, 0.011, wm, seg=5)
            prev = pt
    p.top((0, 0), (radius * 1.2, radius * 1.2), height * 0.5, "inside")


@piece("pots_and_pans", ANY, "small")
def pots_and_pans(p, tint=None):
    """A stockpot with a lid, a saucepan and a frying pan with a long handle."""
    sm = mat.solid("#9DA0A5", 0.3, 0.9)
    im = mat.surface(IRON)
    p.lathe([(0, 0), (0.15, 0), (0.16, 0.02), (0.16, 0.26), (0.165, 0.27), (0, 0.27)], (0, 0, 0), sm, seg=22)
    p.lathe([(0, 0.27), (0.17, 0.27), (0.16, 0.3), (0.05, 0.31), (0.03, 0.33), (0.0, 0.33)], (0, 0, 0), sm, seg=22)
    p.box((0.06, 0.03, 0.03), (-0.2, 0, 0.2), im, bevel=0.005)
    p.box((0.06, 0.03, 0.03), (0.2, 0, 0.2), im, bevel=0.005)
    p.lathe([(0, 0), (0.1, 0), (0.105, 0.11), (0.1, 0.11), (0, 0.01)], (0.42, -0.05, 0), sm, seg=18)
    p.box((0.2, 0.025, 0.02), (0.6, -0.05, 0.09), im, bevel=0.004)
    p.lathe([(0, 0), (0.13, 0), (0.15, 0.035), (0.0, 0.035)], (0.2, -0.38, 0), im, seg=22)
    p.box((0.22, 0.03, 0.02), (0.38, -0.38, 0.025), im, bevel=0.004)


@piece("crockery_set", ANY, "small")
def crockery_set(p, plates: int = 4, tint="#EDE8DC"):
    """A stack of plates, two bowls and a cup."""
    cm = mat.solid(tint, 0.25)
    for i in range(plates):
        p.lathe([(0, 0), (0.1, 0), (0.125, 0.015), (0.12, 0.018), (0.0, 0.008)], (0, 0, i * 0.014), cm, seg=22)
    for k, x in enumerate((0.3, 0.5)):
        p.lathe([(0, 0), (0.05, 0), (0.08, 0.05), (0.075, 0.052), (0.0, 0.006)], (x, 0.05 * (k - 0.5), 0), cm, seg=18)
    p.lathe([(0, 0), (0.035, 0), (0.04, 0.07), (0.035, 0.07), (0, 0.006)], (-0.28, 0, 0), mat.solid("#B5543A", 0.3), seg=14)


@piece("bottle", ANY, "small")
def bottle(p, color="#2F5A3A", height: float = 0.3):
    gm = mat.solid(color, 0.08)
    p.lathe([(0, 0), (0.05, 0), (0.052, height * 0.5), (0.04, height * 0.62), (0.017, height * 0.74), (0.017, height * 0.96), (0.02, height), (0.0, height)], (0, 0, 0), gm, seg=16)
    p.cyl(0.017, 0.025, (0, 0, height * 0.95), mat.solid("#C9A25A", 0.8), seg=10)


@piece("jug", ANY, "small")
def jug(p, tint=None, height: float = 0.26):
    cm = mat.surface("terracotta", tint=tint)
    p.lathe([(0, 0), (0.08, 0), (0.105, height * 0.4), (0.09, height * 0.72), (0.05, height * 0.86), (0.065, height), (0, height)], (0, 0, 0), cm, seg=18)
    prev = None
    for k in range(8):
        a = math.pi * 0.6 * k / 7 + 0.2
        pt = (0.1 + math.sin(a) * 0.06, 0, height * 0.7 - math.cos(a) * 0.2 * height + 0.0)
        pt = (0.06 + 0.07 * math.sin(a * 1.3), 0, height * 0.85 - 0.4 * height * (1 - math.cos(a)))
        if prev:
            p.rod(prev, pt, 0.014, cm, seg=5)
        prev = pt


@piece("goblet", OLD, "small")
def goblet(p, metal: bool = True):
    gm = mat.solid("#C9A44A", 0.25, 1.0) if metal else mat.solid("#C9C3B8", 0.05)
    p.lathe([(0, 0), (0.04, 0), (0.04, 0.012), (0.012, 0.03), (0.012, 0.075), (0.05, 0.095), (0.055, 0.14), (0.048, 0.14), (0.046, 0.1), (0, 0.092)], (0, 0, 0), gm, seg=18)


@piece("tankard", OLD, "small")
def tankard(p):
    wm = mat.surface(W)
    p.lathe([(0, 0), (0.05, 0), (0.055, 0.13), (0.052, 0.13), (0.047, 0.01), (0, 0.01)], (0, 0, 0), mat.solid("#8E8E92", 0.3, 0.9), seg=16)
    p.ball(0.045, (0, 0, 0.125), mat.solid("#F2E9C9", 0.9), squash=(1, 1, 0.3), sub=1)
    prev = None
    for k in range(7):
        a = math.pi * k / 6
        pt = (0.055 + math.sin(a) * 0.04, 0, 0.11 - 0.09 * (k / 6) * 0 - 0.0 - (0.06 * (1 - math.cos(a)) / 2) + 0.0)
        if prev:
            p.rod(prev, pt, 0.008, mat.solid("#8E8E92", 0.3, 0.9), seg=5)
        prev = pt


@piece("scroll", OLD, "small", detail=True)
def scroll(p, length: float = 0.3):
    cm = mat.solid("#E8D9B5", 0.9)
    p.cyl(0.02, length, (-length / 2, 0, 0.02), cm, seg=12, rot=(0, 90, 0))
    p.cyl(0.006, length + 0.04, (-length / 2 - 0.02, 0, 0.02), mat.solid("#5A3A22", 0.7), seg=6, rot=(0, 90, 0))
    p.box((0.16, 0.02, 0.002), (0.05, 0.0, 0.002), cm, bevel=0.0)


@piece("book_stack", ANY, "small")
def book_stack(p, count: int = 4, seed: int = 0):
    rnd = random.Random(seed)
    z = 0.0
    for i in range(count):
        h = rnd.uniform(0.025, 0.05)
        w_, d_ = rnd.uniform(0.16, 0.24), rnd.uniform(0.12, 0.17)
        p.box((w_, d_, h), (rnd.uniform(-0.01, 0.01), rnd.uniform(-0.01, 0.01), z), mat.solid(rnd.choice(["#7A2E2A", "#2D4A6B", "#3F5F3A", "#8A6A2E", "#5A3A5E"]), 0.55), rot=(0, 0, rnd.uniform(-12, 12)), bevel=0.003)
        z += h


@piece("papers_stack", ANY, "small", detail=True)
def papers_stack(p, count: int = 6, seed: int = 0):
    """Loose sheets in a slightly skewed pile."""
    rnd = random.Random(seed)
    for i in range(count):
        p.box((0.21, 0.297, 0.002), (rnd.uniform(-0.01, 0.01), rnd.uniform(-0.01, 0.01), i * 0.0022), mat.solid("#F4F1E8", 0.9), rot=(0, 0, rnd.uniform(-8, 8)), bevel=0.0)
    p.box((0.17, 0.003, 0.0015), (0, 0.04, count * 0.0022 + 0.001), mat.solid("#555555", 0.9), bevel=0.0)


@piece("potted_plant", ANY, "floor")
def potted_plant(p, height: float = 1.0, pot_r: float = 0.17, seed: int = 0, tint=None):
    """A leafy plant in a terracotta pot: a stem cluster of long leaves."""
    rnd = random.Random(seed)
    p.lathe([(0, 0), (pot_r * 0.7, 0), (pot_r, pot_r * 1.6), (pot_r * 1.05, pot_r * 1.7), (pot_r * 0.95, pot_r * 1.7), (0, pot_r * 1.55)], (0, 0, 0), "terracotta", tint, seg=18)
    p.cyl(pot_r * 0.95, 0.02, (0, 0, pot_r * 1.55), mat.solid("#3A2A1C", 1.0), seg=16)
    top = pot_r * 1.6
    for k in range(9):
        a = rnd.uniform(0, 6.28)
        lean = rnd.uniform(0.2, 0.7)
        L = (height - top) * rnd.uniform(0.6, 1.0)
        tip = (math.cos(a) * lean * L * 0.6, math.sin(a) * lean * L * 0.6, top + L * (1 - lean * 0.3))
        p.rod((0, 0, top), tip, 0.006, mat.solid("#4C7A3A", 0.6), seg=4)
        p.ball(0.07, tip, "leaves", None, squash=(1.0, 0.45, 1.8), sub=1)
        p.ball(0.06, ((tip[0] * 0.7), tip[1] * 0.7, top + (tip[2] - top) * 0.65), "leaves", None, squash=(0.8, 0.5, 1.5), sub=1)


@piece("vase_flowers", ANY, "small")
def vase_flowers(p, seed: int = 0, vase_color="#3F6C7A"):
    rnd = random.Random(seed)
    p.lathe([(0, 0), (0.06, 0), (0.09, 0.1), (0.05, 0.2), (0.04, 0.26), (0.055, 0.28), (0.045, 0.28), (0.0, 0.24)], (0, 0, 0), mat.solid(vase_color, 0.12), seg=18)
    for k in range(9):
        a = rnd.uniform(0, 6.28)
        r_ = rnd.uniform(0.03, 0.11)
        tip = (math.cos(a) * r_, math.sin(a) * r_, 0.28 + rnd.uniform(0.18, 0.34))
        p.rod((0, 0, 0.25), tip, 0.004, mat.solid("#4C7A3A", 0.6), seg=4)
        p.ball(0.03, tip, mat.solid(rnd.choice(["#E8A0B8", "#F2E27A", "#F6F1E4", "#C95A5A", "#B58BD6"]), 0.6), squash=(1, 1, 0.7), sub=1)


@piece("weapon_rack", OLD, "floor", detail=False)
def weapon_rack(p, length: float = 1.6, spears: int = 5, seed: int = 0):
    """A floor rack: an oak frame holding upright spears and a row of swords, a shield leaning at the side."""
    rnd = random.Random(seed)
    for sx in (-1, 1):
        p.box((0.08, 0.3, 0.06), (sx * (length / 2 - 0.1), 0, 0), DW, bevel=0.008)
        p.box((0.06, 0.06, 1.15), (sx * (length / 2 - 0.1), 0.1, 0.06), DW, bevel=0.008)
    p.box((length, 0.06, 0.08), (0, 0.1, 0.85), DW, bevel=0.008)
    p.box((length, 0.06, 0.08), (0, 0.1, 0.35), DW, bevel=0.008)
    p.box((length - 0.2, 0.22, 0.04), (0, 0.0, 0.1), DW, bevel=0.006)
    for i in range(spears):
        x = -length / 2 + 0.25 + (length - 0.5) * i / max(1, spears - 1)
        H = 2.1 + rnd.uniform(-0.1, 0.1)
        p.cyl(0.014, H, (x, 0.0, 0.1), mat.surface(DW), seg=6)
        p.cyl(0.02, 0.2, (x, 0.0, 0.1 + H), STEEL, top=0.0, seg=4)
    for i in range(3):
        x = -length / 2 + 0.4 + i * (length - 0.8) / 2
        p.box((0.045, 0.012, 0.7), (x, 0.14, 0.32), STEEL, rot=(0, rnd.uniform(-4, 4), 0), bevel=0.003)
        p.box((0.2, 0.02, 0.03), (x, 0.14, 0.99), mat.solid("#B8923A", 0.3, 0.9), bevel=0.004)


@piece("suit_of_armour", OLD, "floor")
def suit_of_armour(p, tint=None):
    """A suit of plate armour on a stand with a halberd: greaves, cuirass, pauldrons, helm with a plume."""
    sm = mat.surface(STEEL)
    p.box((0.5, 0.5, 0.06), (0, 0, 0), DW, bevel=0.01)
    for sx in (-1, 1):
        p.lathe([(0.04, 0.06), (0.075, 0.3), (0.06, 0.5), (0.07, 0.55), (0.0, 0.56)], (sx * 0.1, 0, 0), sm, seg=12)
        p.box((0.11, 0.2, 0.05), (sx * 0.1, -0.05, 0.06), sm, bevel=0.012)
    p.box((0.28, 0.16, 0.14), (0, 0, 0.56), sm, bevel=0.03)
    p.lathe([(0.16, 0.7), (0.2, 0.95), (0.19, 1.1), (0.22, 1.28), (0.0, 1.3)], (0, 0, 0), sm, seg=14)
    for sx in (-1, 1):
        p.ball(0.1, (sx * 0.27, 0, 1.22), sm, squash=(1, 1, 0.8), sub=1)
        p.rod((sx * 0.27, 0, 1.2), (sx * 0.31, -0.08, 0.84), 0.04, sm, seg=8)
    p.lathe([(0, 1.3), (0.1, 1.3), (0.115, 1.4), (0.1, 1.5), (0.04, 1.58), (0.0, 1.59)], (0, 0, 0), sm, seg=14)
    p.box((0.16, 0.02, 0.025), (0, -0.1, 1.44), mat.solid("#0C0C0E", 0.9), bevel=0.0)
    p.box((0.03, 0.18, 0.2), (0, 0.0, 1.55), mat.solid("#A3231F", 0.7), bevel=0.01)
    p.cyl(0.014, 2.0, (0.38, -0.12, 0.06), DW, seg=6)
    p.cyl(0.04, 0.3, (0.38, -0.12, 2.06), STEEL, top=0.0, seg=4)


@piece("tent", ANY, "floor")
def tent(p, width: float = 3.4, length: float = 4.0, height: float = 2.4, color="#D8CDB4", flap: bool = True):
    """A canvas ridge tent: two sloped canvas sides, an end wall with an open flap, a ridge pole and guy ropes."""
    cm = mat.solid(color, 0.95)
    ang = math.degrees(math.atan2(height, width / 2))
    sl = math.hypot(width / 2, height)
    bm = p._bm(cm, None, 0.0)
    h2 = width / 2
    V = lambda x, y, z: bm.verts.new((x, y, z))
    a, b, c, d = V(-h2, -length / 2, 0), V(h2, -length / 2, 0), V(0, -length / 2, height), V(0, length / 2, height)
    e, f_ = V(-h2, length / 2, 0), V(h2, length / 2, 0)
    bm.faces.new((a, c, d, e))
    bm.faces.new((b, f_, d, c))
    bm.faces.new((e, d, f_))
    if flap:
        bm.faces.new((a, b, c))
        p.box((0.5, 0.01, height * 0.7), (0, -length / 2 - 0.01, 0), mat.solid("#1C1612", 1.0), bevel=0.0)
    p.cyl(0.03, height + 0.4, (0, -length / 2, 0), DW, seg=8)
    p.cyl(0.03, height + 0.4, (0, length / 2, 0), DW, seg=8)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.rod((sx * h2 * 0.9, sy * length / 2 * 0.95, height * 0.5), (sx * (h2 + 0.8), sy * (length / 2 + 0.5), 0.0), 0.008, "rope", seg=4)
            p.cyl(0.015, 0.2, (sx * (h2 + 0.8), sy * (length / 2 + 0.5), 0.0), DW, seg=6)


@piece("hay_bale", ANY, "floor")
def hay_bale(p, tint=None):
    p.box((0.9, 0.45, 0.45), (0, 0, 0), "thatch", tint, bevel=0.03)
    for x in (-0.25, 0.25):
        p.box((0.025, 0.46, 0.46), (x, 0, 0), "rope", bevel=0.004)
    p.top((0, 0), (0.8, 0.4), 0.45, "bale")


def _wheel(p, x: float, y: float, z: float, r: float = 0.5, tint=None):
    """A spoked cart wheel standing in the XZ plane at (x, y, z): rim of 20 rods, 8 spokes, hub, iron tyre."""
    n = 20
    for k in range(n):
        a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        p.rod((x + math.cos(a0) * r, y, z + math.sin(a0) * r), (x + math.cos(a1) * r, y, z + math.sin(a1) * r), 0.03, DW, tint, seg=6)
    for k in range(8):
        a = math.pi * k / 4
        p.rod((x, y, z), (x + math.cos(a) * r, y, z + math.sin(a) * r), 0.014, DW, tint, seg=5)
    p.cyl(0.07, 0.1, (x, y - 0.05, z), IRON, seg=12, rot=(-90, 0, 0))


@piece("cart", OLD, "floor")
def cart(p, tint=None, goods: bool = True):
    """A two-wheeled hand cart with shafts, side boards and spoked wheels."""
    p.box((1.4, 0.9, 0.06), (0, 0, 0.55), W, tint, bevel=0.008)
    for sy in (-1, 1):
        p.box((1.4, 0.04, 0.35), (0, sy * 0.43, 0.6), W, tint, bevel=0.006)
    p.box((0.04, 0.9, 0.35), (0.68, 0, 0.6), W, tint, bevel=0.006)
    p.rod((-0.7, -0.3, 0.55), (-1.9, -0.3, 0.7), 0.03, DW, seg=8)
    p.rod((-0.7, 0.3, 0.55), (-1.9, 0.3, 0.7), 0.03, DW, seg=8)
    for sy in (-1, 1):
        _wheel(p, 0.0, sy * 0.52, 0.535, 0.5, tint)
    p.rod((0, -0.55, 0.535), (0, 0.55, 0.535), 0.03, IRON, seg=8)
    if goods:
        for i in range(4):
            p.ball(0.18, (-0.35 + i * 0.28, 0.0, 0.76), CLOTH, "#B49A6C", squash=(1, 0.8, 0.85), sub=1)
    p.top((0, 0), (1.2, 0.8), 0.61, "bed")


@piece("stakes", ANY, "floor")
def stakes(p, count: int = 8, seed: int = 0, height: float = 1.4):
    """A row of sharpened stakes leaning outward (a palisade or a field defence)."""
    rnd = random.Random(seed)
    for i in range(count):
        x = (i - (count - 1) / 2) * 0.22
        p.cyl(0.06, height * rnd.uniform(0.85, 1.1), (x, 0, 0.03), DW, top=0.01, seg=8, rot=(rnd.uniform(-14, -8), rnd.uniform(-3, 3), 0))


@piece("banner_pole", ANY, "floor", detail=True)
def banner_pole(p, height: float = 3.2, color="#A3231F", trim="#EDC04A"):
    """A standard on a pole with a pennant flying from a crossbar, set in a stone base."""
    p.cyl(0.25, 0.2, (0, 0, 0), "castle_stone", top=0.2, seg=10)
    p.cyl(0.035, height, (0, 0, 0.2), DW, seg=8)
    p.ball(0.06, (0, 0, height + 0.22), GOLD, sub=1)
    p.box((0.9, 0.03, 0.03), (0, 0, height - 0.15), DW, bevel=0.004)
    p.grid(0.8, 1.4, (0, -0.02, height - 1.55), CLOTH, color, nx=10, ny=3, amp=0.03, waves=2.5)
    p.box((0.8, 0.012, 0.06), (0, -0.04, height - 1.6), mat.solid(trim, 0.5), bevel=0.0)


@piece("arrow_bundle", ANY, "small")
def arrow_bundle(p, seed: int = 0):
    """Arrows standing in a quiver on the ground (or lying in a bundle)."""
    rnd = random.Random(seed)
    p.cyl(0.07, 0.5, (0, 0, 0.012), mat.surface("leather"), top=0.08, seg=10, rot=(0, 8, 0))
    for k in range(7):
        a = rnd.uniform(0, 6.28)
        p.cyl(0.006, 0.6, (math.cos(a) * 0.03, math.sin(a) * 0.03, 0.2), DW, seg=4, rot=(rnd.uniform(-6, 6), 8 + rnd.uniform(-3, 3), 0))
        p.ball(0.02, (math.cos(a) * 0.03 + 0.09, math.sin(a) * 0.03, 0.78), mat.solid("#EDE6D6", 0.8), squash=(1, 1, 1.5), sub=1)


@piece("shield_pile", OLD, "floor")
def shield_pile(p, seed: int = 0):
    """Round shields stacked and leaning against each other with a spear laid across."""
    rnd = random.Random(seed)
    for i, col in enumerate(("#A3231F", "#2D4A6B", "#C9A44A", "#3F5F3A")):
        p.cyl(0.36, 0.05, (rnd.uniform(-0.08, 0.08), rnd.uniform(-0.08, 0.08), i * 0.055), mat.solid(col, 0.55), top=0.34, seg=24, rot=(0, 0, 0))
        p.cyl(0.07, 0.05, (0, 0, i * 0.055 + 0.04), STEEL, seg=12)
    p.rod((-0.7, 0.05, 0.28), (0.8, -0.05, 0.3), 0.014, DW, seg=6)


@piece("fruit_crate", ANY, "small")
def fruit_crate(p, fruit="#C73A2D", seed: int = 0):
    """A slatted crate brimming with fruit (apples, oranges, pears: pass the colour)."""
    rnd = random.Random(seed)
    p.box((0.5, 0.35, 0.2), (0, 0, 0), W, bevel=0.006)
    for sx in (-1, 1):
        p.box((0.03, 0.37, 0.22), (sx * 0.24, 0, 0), DW, bevel=0.003)
    for i in range(14):
        x, y = rnd.uniform(-0.2, 0.2), rnd.uniform(-0.12, 0.12)
        p.ball(0.045, (x, y, 0.2 + rnd.uniform(0.0, 0.03)), mat.solid(fruit, 0.4), sub=1)
    p.top((0, 0), (0.4, 0.28), 0.26, "fruit")


@piece("bread_basket", ANY, "small")
def bread_basket(p, seed: int = 0):
    """Loaves and rolls piled on a board."""
    rnd = random.Random(seed)
    p.box((0.5, 0.3, 0.025), (0, 0, 0), W, bevel=0.004)
    bm_ = mat.solid("#B98349", 0.8)
    for i in range(3):
        p.ball(0.1, (-0.15 + i * 0.15, rnd.uniform(-0.04, 0.04), 0.07), bm_, squash=(1.8, 0.8, 0.75), sub=1)
    for i in range(3):
        p.ball(0.045, (-0.15 + i * 0.15, 0.1, 0.045), bm_, sub=1)


@piece("cloth_bolts", ANY, "small")
def cloth_bolts(p, seed: int = 0):
    """Rolls of dyed cloth stacked on a table (the draper's stall): three on the bottom, two above, one on top."""
    cols = ["#A3231F", "#2D4A6B", "#C9A44A", "#3F5F3A", "#7A3E7A", "#E8DDC3"]
    rows = ((0.07, (-0.14, 0.0, 0.14)), (0.2, (-0.07, 0.07)), (0.32, (0.0,)))
    k = 0
    for z, xs in rows:
        for x in xs:
            p.cyl(0.065, 0.45, (x, 0.225, z), mat.solid(cols[(k + seed) % 6], 0.9, sheen=0.4), seg=14, rot=(90, 0, 0))
            k += 1


# ============================================================================= SIGNS AND READABLE DETAIL
@piece("sign_board", ANY, "wall", mount_z=2.4, detail=True)
def sign_board(p, width: float = 1.0, height: float = 0.45, color="#3A2A1C", text_color="#E8D9B5", hanging: bool = True):
    """A hanging painted signboard on a bracket. Add the lettering with furnish.add_text(root, "THE ANCHOR")."""
    p.box((width, 0.05, height), (0, -0.12, 0.0), mat.solid(color, 0.7), bevel=0.012)
    p.box((width + 0.06, 0.03, 0.04), (0, -0.12, height), DW, bevel=0.005)
    p.box((0.05, 0.16, 0.05), (0, 0.0, height + 0.1), mat.surface(IRON), bevel=0.004)
    p.rod((0, -0.04, height + 0.12), (0.0, -0.12, height), 0.012, IRON, seg=5)
    p.anchor("face", (0, -0.147, height / 2))


def add_text(root, body: str, size: float = 0.12, color="#E8D9B5", at=None, emit: float = 0.0):
    """Letter a piece: real text on its front face. at defaults to the middle of the front, a hair proud of the surface."""
    w, d, h = footprint(root)
    face = root.get("sk_anchors", {}).get("face")
    at = at or ((face[0], face[1] - 0.004, face[2]) if face else (0.0, -d - 0.004, h * 0.5))
    t = _text(root, body, at, size, color, emit=emit)
    root["sk_detail"] = 1
    return t


@piece("notice_board", ANY, "wall", mount_z=1.2, detail=True)
def notice_board(p, width: float = 1.2, height: float = 0.9, seed: int = 0):
    """A cork board in a wooden frame covered in pinned papers, cards and a calendar."""
    rnd = random.Random(seed)
    p.box((width, 0.035, height), (0, -0.0175, 0), mat.solid("#7A5230", 0.6), bevel=0.008)
    p.box((width - 0.08, 0.01, height - 0.08), (0, -0.04, 0.04), mat.solid("#B8864B", 0.95), bevel=0.0)
    used = []
    for k in range(9):
        for _ in range(12):
            pw, ph = rnd.uniform(0.12, 0.22), rnd.uniform(0.14, 0.26)
            x, z = rnd.uniform(-width / 2 + 0.12 + pw / 2, width / 2 - 0.12 - pw / 2), rnd.uniform(0.1 + ph / 2, height - 0.1 - ph / 2)
            if all(abs(x - ux) > (pw + uw) / 2 + 0.01 or abs(z - uz) > (ph + uh) / 2 + 0.01 for ux, uz, uw, uh in used):
                used.append((x, z, pw, ph))
                col = rnd.choice(["#F4F1E8", "#F7E9A8", "#CFE3F0", "#F2C9C0", "#F4F1E8"])
                p.box((pw, 0.004, ph), (x, -0.047 - k * 0.0003, z - ph / 2), mat.solid(col, 0.9), rot=(0, rnd.uniform(-5, 5), 0), mid=True, bevel=0.0)
                for ln in range(int(ph / 0.035)):
                    p.box((pw * rnd.uniform(0.5, 0.85), 0.002, 0.006), (x, -0.0505, z + ph / 2 - 0.03 - ln * 0.035), mat.solid("#4A4A52", 0.9), bevel=0.0)
                p.ball(0.011, (x, -0.052, z + ph / 2 - 0.012), mat.solid(rnd.choice(["#C0392B", "#2980B9", "#27AE60"]), 0.4), sub=1)
                break


@piece("whiteboard", MODERN, "wall", mount_z=0.9, detail=True)
def whiteboard(p, width: float = 1.8, height: float = 1.1, seed: int = 0):
    """A whiteboard with an aluminium frame, a marker tray and a diagram: boxes, arrows and scribbled lines in marker colours."""
    rnd = random.Random(seed)
    p.box((width, 0.03, height), (0, -0.015, 0), mat.solid("#B5B8BB", 0.35, 0.9), bevel=0.006)
    p.box((width - 0.05, 0.01, height - 0.05), (0, -0.034, 0.025), mat.solid("#F6F7F8", 0.2), bevel=0.0)
    p.box((width * 0.6, 0.05, 0.03), (0, -0.045, 0.0), mat.solid("#B5B8BB", 0.35, 0.9), bevel=0.004)
    cols = ["#1E5FB4", "#B02A2A", "#1F8A4C", "#222222"]
    for k in range(3):
        x0 = -width * 0.38 + k * width * 0.28
        z0 = height * 0.55
        c = cols[k % 4]
        for (bx, bz, bw, bh) in ((0, 0, 0.3, 0.012), (0, 0.16, 0.3, 0.012)):
            p.box((bw, 0.004, bh), (x0 + bx, -0.04, z0 + bz), mat.solid(c, 0.4), bevel=0.0)
        for sx in (0, 0.3):
            p.box((0.012, 0.004, 0.17), (x0 - 0.15 + sx, -0.04, z0), mat.solid(c, 0.4), bevel=0.0)
        for ln in range(3):
            p.box((rnd.uniform(0.12, 0.22), 0.004, 0.008), (x0, -0.04, z0 + 0.04 + ln * 0.045), mat.solid("#222222", 0.4), bevel=0.0)
        if k < 2:
            p.box((0.14, 0.004, 0.01), (x0 + 0.26, -0.04, z0 + 0.08), mat.solid("#222222", 0.4), bevel=0.0)
            p.box((0.04, 0.004, 0.01), (x0 + 0.32, -0.04, z0 + 0.095), mat.solid("#222222", 0.4), rot=(0, 35, 0), mid=True, bevel=0.0)
    for k in range(7):
        p.box((rnd.uniform(0.2, 0.5), 0.004, 0.008), (-width * 0.2, -0.04, height * 0.28 - k * 0.03), mat.solid("#1E5FB4" if k % 3 else "#222222", 0.4), bevel=0.0)
    p.cyl(0.008, 0.1, (width * 0.15, -0.05, 0.02), mat.solid("#B02A2A", 0.4), seg=6, rot=(0, 90, 0))


@piece("poster", ANY, "wall", mount_z=1.4, detail=True)
def poster(p, width: float = 0.5, height: float = 0.7, color="#D95D39", seed: int = 0):
    rnd = random.Random(seed)
    p.box((width, 0.006, height), (0, -0.003, 0), mat.solid(color, 0.8), bevel=0.0)
    p.box((width * 0.8, 0.002, height * 0.35), (0, -0.007, height * 0.5), mat.solid("#F4F1E8", 0.8), bevel=0.0)
    p.box((width * 0.6, 0.002, 0.03), (0, -0.007, height * 0.3), mat.solid("#F4F1E8", 0.8), bevel=0.0)
    p.box((width * 0.4, 0.002, 0.02), (0, -0.007, height * 0.2), mat.solid("#F4F1E8", 0.8), bevel=0.0)


# ============================================================================= MODERN OFFICE AND HOME
@piece("monitor_keyboard", MODERN, "small")
def monitor_keyboard(p, screen: str = "#7FB2E5", power: float = 0.0, seed: int = 0, diag: float = 0.55):
    """A flat monitor on a stand with a keyboard and mouse. The screen glows (a lit desktop), without lighting the room."""
    pm = mat.solid("#1E2024", 0.4)
    p.box((0.2, 0.18, 0.012), (0, 0.12, 0.0), pm, bevel=0.003)
    p.box((0.04, 0.03, 0.14), (0, 0.15, 0.0), pm, bevel=0.003)
    p.box((diag, 0.025, diag * 0.58), (0, 0.15, 0.13), pm, bevel=0.006)
    p.box((diag - 0.03, 0.005, diag * 0.58 - 0.03), (0, 0.135, 0.145), p.glow(screen, 1.6), bevel=0.0)
    p.box((diag * 0.5, 0.004, 0.012), (-diag * 0.1, 0.132, 0.145 + diag * 0.58 - 0.07), mat.solid("#F4F4F4", 0.5), bevel=0.0)
    for k in range(4):
        p.box((diag * 0.3 + 0.03 * k, 0.004, 0.012), (-diag * 0.1, 0.132, 0.145 + diag * 0.58 * 0.5 - k * 0.04), mat.solid("#FFFFFF", 0.5), bevel=0.0)
    p.box((0.44, 0.15, 0.018), (0, -0.14, 0.0), mat.solid("#2B2E33", 0.5), bevel=0.004)
    p.box((0.40, 0.11, 0.004), (0, -0.14, 0.018), mat.solid("#3C4048", 0.6), bevel=0.0)
    p.box((0.06, 0.1, 0.03), (0.34, -0.1, 0.0), pm, bevel=0.012)


@piece("laptop", MODERN, "small")
def laptop(p, screen="#9CC4EE", open_deg: float = 105.0):
    pm = mat.solid("#B5B8BC", 0.35, 0.9)
    p.box((0.32, 0.22, 0.015), (0, 0, 0), pm, bevel=0.004)
    p.box((0.28, 0.08, 0.002), (0, -0.04, 0.015), mat.solid("#2B2E33", 0.6), bevel=0.0)
    a = math.radians(open_deg - 90)
    p.box((0.32, 0.01, 0.21), (0, 0.11 + 0.02, 0.1), pm, rot=(-14, 0, 0), mid=True, bevel=0.003)
    p.box((0.30, 0.004, 0.19), (0, 0.11 + 0.012, 0.1 - 0.003), p.glow(screen, 1.4), rot=(-14, 0, 0), mid=True, bevel=0.0)


@piece("office_phone", MODERN, "small")
def office_phone(p):
    pm = mat.solid("#26282C", 0.4)
    p.box((0.2, 0.22, 0.05), (0, 0, 0), pm, rot=(0, 0, 0), bevel=0.012)
    p.box((0.05, 0.2, 0.025), (-0.06, 0.0, 0.05), pm, bevel=0.01)
    p.box((0.2, 0.05, 0.03), (0, 0.0, 0.07), pm, bevel=0.012)
    p.box((0.08, 0.06, 0.004), (0.04, -0.08, 0.052), p.glow("#BFE6B0", 1.0), bevel=0.0)
    for r in range(3):
        for c in range(3):
            p.box((0.012, 0.012, 0.005), (0.0 + c * 0.02, -0.05 - r * 0.02 + 0.06, 0.052), mat.solid("#C9CBCE", 0.4), bevel=0.0)


@piece("filing_cabinet", MODERN, "furniture")
def filing_cabinet(p, drawers: int = 4, color="#8E959C"):
    """A steel filing cabinet: drawer fronts with handles and label holders."""
    D, H, Wd = 0.6, 0.35 * drawers / 1.0 * 0.9 + 0.12, 0.46
    H = 0.31 * drawers + 0.08
    bm_ = mat.solid(color, 0.45, 0.6)
    p.box((Wd, D, H), (0, 0, 0.02), bm_, bevel=0.006)
    for i in range(drawers):
        z = 0.06 + i * (H - 0.1) / drawers
        p.box((Wd - 0.03, 0.015, (H - 0.1) / drawers - 0.02), (0, -D / 2 - 0.005, z), mat.solid("#A9B0B6", 0.4, 0.5), bevel=0.003)
        p.box((0.2, 0.025, 0.02), (0, -D / 2 - 0.02, z + (H - 0.1) / drawers * 0.7), mat.solid("#4A4D52", 0.4, 0.9), bevel=0.004)
        p.box((0.1, 0.005, 0.04), (0, -D / 2 - 0.016, z + (H - 0.1) / drawers * 0.35), mat.solid("#F4F1E8", 0.8), bevel=0.0)
    p.top((0, 0), (Wd, D), H + 0.02, "top")


@piece("water_cooler", MODERN, "furniture")
def water_cooler(p):
    wm = mat.solid("#E4E7EA", 0.4)
    p.box((0.32, 0.35, 0.95), (0, 0, 0.0), wm, bevel=0.015)
    p.box((0.3, 0.02, 0.2), (0, -0.18, 0.62), mat.solid("#2B2E33", 0.4), bevel=0.004)
    p.box((0.03, 0.04, 0.03), (-0.06, -0.2, 0.7), mat.solid("#2D7DD2", 0.3), bevel=0.004)
    p.box((0.03, 0.04, 0.03), (0.06, -0.2, 0.7), mat.solid("#D0432F", 0.3), bevel=0.004)
    p.box((0.2, 0.12, 0.02), (0, -0.2, 0.58), mat.solid("#9EA3A8", 0.3, 0.8), bevel=0.003)
    p.lathe([(0.0, 0.95), (0.14, 0.95), (0.16, 1.1), (0.15, 1.3), (0.08, 1.4), (0.03, 1.42), (0.0, 1.42)], (0, 0, 0), mat.solid("#7BB6E8", 0.08), seg=20)


@piece("printer", MODERN, "furniture")
def printer(p):
    """A floor-standing office printer-copier with a lid, a control panel, an output tray and a paper stack."""
    pm = mat.solid("#D9DCDF", 0.45)
    dm = mat.solid("#34373C", 0.5)
    p.box((0.58, 0.5, 0.55), (0, 0, 0.45), pm, bevel=0.012)
    p.box((0.52, 0.46, 0.04), (0, 0, 1.0), pm, bevel=0.008)
    p.box((0.6, 0.52, 0.45), (0, 0, 0.0), dm, bevel=0.01)
    for z in (0.03, 0.18):
        p.box((0.52, 0.01, 0.12), (0, -0.26, z + 0.02), mat.solid("#454A50", 0.5), bevel=0.004)
    p.box((0.2, 0.08, 0.05), (0.12, -0.19, 0.96), dm, rot=(-24, 0, 0), bevel=0.004)
    p.box((0.12, 0.035, 0.03), (0.13, -0.21, 0.985), p.glow("#9CE0B0", 1.4), rot=(-24, 0, 0), bevel=0.0)
    p.box((0.4, 0.16, 0.012), (0, -0.33, 0.62), pm, bevel=0.003)
    for i in range(5):
        p.box((0.3, 0.2, 0.002), (0.0, -0.31, 0.634 + i * 0.002), mat.solid("#F4F1E8", 0.9), rot=(0, 0, 0), bevel=0.0)
    p.top((0, 0), (0.5, 0.45), 1.04, "top")


@piece("bin", MODERN, "floor")
def bin_(p, height: float = 0.38, color="#3A3E44"):
    p.lathe([(0, 0), (0.12, 0), (0.15, height), (0.145, height), (0.11, 0.015), (0, 0.015)], (0, 0, 0), mat.solid(color, 0.5), seg=20)
    p.cyl(0.152, 0.015, (0, 0, height - 0.01), mat.solid("#262A2E", 0.5), seg=20)
    p.box((0.1, 0.1, 0.02), (0.02, 0, height - 0.02), mat.solid("#F4F1E8", 0.9), rot=(0, 15, 30), mid=True, bevel=0.0)


waste_bin = bin_


@piece("coat_stand", MODERN, "floor")
def coat_stand(p, coats: int = 2, seed: int = 0):
    """A coat stand: weighted base, a pole with five hooks and a coat and scarf hung on it."""
    rnd = random.Random(seed)
    dm = mat.surface(DW)
    p.cyl(0.2, 0.025, (0, 0, 0), dm, seg=20)
    p.cyl(0.02, 1.75, (0, 0, 0.02), dm, seg=10)
    for k in range(5):
        a = 2 * math.pi * k / 5
        p.rod((0, 0, 1.68), (math.cos(a) * 0.14, math.sin(a) * 0.14, 1.78), 0.012, dm, seg=5)
        p.ball(0.02, (math.cos(a) * 0.14, math.sin(a) * 0.14, 1.79), dm, sub=1)
    for i in range(coats):
        col = rnd.choice(["#34425A", "#5A3A3A", "#3F4A3A", "#6A6560"])
        a = 2 * math.pi * i * 0.4 + 0.5
        p.ball(0.13, (math.cos(a) * 0.17, math.sin(a) * 0.17, 1.45), mat.solid(col, 0.95, sheen=0.4), squash=(0.7, 1.0, 2.3), sub=2)


@piece("tv", HOME, "furniture")
def tv(p, diag: float = 1.1, stand: bool = True):
    """A flat television on a low media unit, screen dark with a faint glow."""
    pm = mat.solid("#18191C", 0.35)
    if stand:
        p.box((1.5, 0.4, 0.45), (0, 0, 0.0), W, "#4A3A2C", bevel=0.01)
        p.box((1.46, 0.015, 0.2), (0, -0.2, 0.08), mat.solid("#2B2D31", 0.4), bevel=0.003)
    z0 = 0.45 if stand else 0.0
    p.box((0.3, 0.16, 0.02), (0, 0, z0), pm, bevel=0.004)
    p.box((diag, 0.04, diag * 0.58), (0, 0.0, z0 + 0.06), pm, bevel=0.008)
    p.box((diag - 0.03, 0.005, diag * 0.58 - 0.03), (0, -0.022, z0 + 0.075), p.glow("#4A6C96", 0.7), bevel=0.0)
    p.top((0, 0), (1.4, 0.35), 0.45, "unit")


@piece("coffee_table", HOME, "furniture")
def coffee_table(p, length: float = 1.0, depth: float = 0.55, tint=None):
    p.box((length, depth, 0.04), (0, 0, 0.38), W, tint or "#7A5A3A", bevel=0.008)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((0.04, 0.04, 0.38), (sx * (length / 2 - 0.06), sy * (depth / 2 - 0.06), 0), DW, bevel=0.004)
    p.box((length - 0.2, depth - 0.2, 0.025), (0, 0, 0.12), W, tint or "#7A5A3A", bevel=0.004)
    p.top((0, 0), (length - 0.1, depth - 0.1), 0.42, "top")


@piece("kitchen_counter", HOME, "furniture")
def kitchen_counter(p, length: float = 2.4, sink: bool = True, hob: bool = True, wall_units: bool = True, color="#E6E2D8", top="#4E4A46"):
    """A run of base units with a worktop, a stainless sink with a tap, a four-ring hob, plinth, handles, and wall cabinets."""
    D, H = 0.62, 0.9
    cm = mat.solid(color, 0.5)
    tm = mat.solid(top, 0.35)
    sm = mat.solid("#B9BDC2", 0.25, 1.0)
    p.box((length, D - 0.04, 0.1), (0, 0.02, 0.0), mat.solid("#2B2D31", 0.6), bevel=0.0)
    p.box((length, D, H - 0.14), (0, 0, 0.1), cm, bevel=0.006)
    p.box((length + 0.02, D + 0.03, 0.04), (0, -0.01, H - 0.04), tm, bevel=0.004)
    n = max(2, int(length / 0.6))
    for i in range(n):
        x = -length / 2 + length * (i + 0.5) / n
        p.box((length / n - 0.01, 0.015, H - 0.2), (x, -D / 2 - 0.005, 0.12), mat.solid("#F1EEE6", 0.45), bevel=0.004)
        p.box((0.1, 0.02, 0.014), (x, -D / 2 - 0.02, H - 0.2), mat.solid("#9EA3A8", 0.3, 0.9), bevel=0.003)
    tops_ = []
    if sink:
        x = -length / 2 + 0.55
        p.box((0.5, 0.4, 0.012), (x, 0, H), sm, bevel=0.0)
        p.rod((x, 0.2, H), (x, 0.2, H + 0.24), 0.014, sm, seg=8)
        p.rod((x, 0.2, H + 0.24), (x, 0.08, H + 0.24), 0.012, sm, seg=8)
    if hob:
        x = length / 2 - 0.45
        p.box((0.58, 0.5, 0.012), (x, 0, H), mat.solid("#18191C", 0.2), bevel=0.003)
        for dx in (-0.14, 0.14):
            for dy in (-0.1, 0.1):
                p.cyl(0.07, 0.006, (x + dx, dy, H + 0.012), mat.solid("#3A3D42", 0.4), seg=18)
        for k in range(4):
            p.cyl(0.012, 0.015, (x - 0.19 + k * 0.126, -0.28, H - 0.02), mat.solid("#9EA3A8", 0.3, 0.9), seg=8, rot=(90, 0, 0))
    if wall_units:
        for i in range(n):
            x = -length / 2 + length * (i + 0.5) / n
            p.box((length / n - 0.02, 0.32, 0.7), (x, D / 2 - 0.24, 1.45), cm, bevel=0.006)
            p.box((length / n - 0.04, 0.012, 0.66), (x, D / 2 - 0.24 - 0.17, 1.47), mat.solid("#F1EEE6", 0.45), bevel=0.003)
            p.box((0.012, 0.02, 0.12), (x + 0.1, D / 2 - 0.24 - 0.18, 1.55), mat.solid("#9EA3A8", 0.3, 0.9), bevel=0.002)
    p.top((0, 0), (length - 0.1, D - 0.1), H, "worktop")


@piece("fridge", MODERN, "furniture")
def fridge(p, height: float = 1.8, color="#DCDFE2"):
    fm = mat.solid(color, 0.35, 0.3)
    p.box((0.68, 0.68, height), (0, 0, 0.0), fm, bevel=0.015)
    p.box((0.66, 0.012, 0.012), (0, -0.345, height * 0.33), mat.solid("#2B2D31", 0.5), bevel=0.0)
    p.box((0.02, 0.04, 0.4), (0.26, -0.36, height * 0.5), mat.solid("#B9BDC2", 0.25, 1.0), bevel=0.004)
    p.box((0.02, 0.04, 0.22), (0.26, -0.36, height * 0.16), mat.solid("#B9BDC2", 0.25, 1.0), bevel=0.004)
    p.top((0, 0), (0.6, 0.6), height, "top")


@piece("microwave", MODERN, "small")
def microwave(p):
    p.box((0.46, 0.34, 0.27), (0, 0, 0), mat.solid("#B9BDC2", 0.3, 0.8), bevel=0.01)
    p.box((0.3, 0.01, 0.2), (-0.06, -0.172, 0.035), mat.solid("#14161A", 0.1), bevel=0.0)
    p.box((0.08, 0.01, 0.2), (0.17, -0.172, 0.035), mat.solid("#26282C", 0.4), bevel=0.0)
    p.box((0.05, 0.005, 0.03), (0.17, -0.178, 0.19), p.glow("#9CE0B0", 1.4), bevel=0.0)


@piece("kettle", MODERN, "small")
def kettle(p, color="#C9CDD1"):
    sm = mat.solid(color, 0.25, 1.0)
    p.lathe([(0, 0), (0.09, 0), (0.1, 0.05), (0.085, 0.2), (0.05, 0.23), (0.0, 0.235)], (0, 0, 0), sm, seg=20)
    p.rod((0.07, 0, 0.18), (0.16, 0, 0.12), 0.01, sm, seg=5)
    p.box((0.03, 0.07, 0.1), (-0.11, 0, 0.1), mat.solid("#26282C", 0.5), bevel=0.01)
    p.rod((-0.09, 0, 0.2), (-0.14, 0, 0.14), 0.008, sm, seg=5)
    p.cyl(0.095, 0.02, (0, 0, -0.0), mat.solid("#26282C", 0.5), seg=20)


@piece("mugs", ANY, "small")
def mugs(p, count: int = 3, seed: int = 0):
    rnd = random.Random(seed)
    for i in range(count):
        c = mat.solid(rnd.choice(["#E8E4DA", "#2D7DD2", "#D0432F", "#2F8F5A", "#E8B63A"]), 0.3)
        x, y = i * 0.12 + rnd.uniform(-0.01, 0.01), rnd.uniform(-0.03, 0.03)
        p.lathe([(0, 0), (0.04, 0), (0.042, 0.095), (0.037, 0.095), (0.035, 0.008), (0, 0.008)], (x, y, 0), c, seg=16)
        prev = None
        for k in range(6):
            a = math.pi * k / 5
            pt = (x + 0.042 + math.sin(a) * 0.03, y, 0.08 - 0.05 * (1 - math.cos(a)) / 2 * 1.2)
            if prev:
                p.rod(prev, pt, 0.006, c, seg=4)
            prev = pt


# ============================================================================= TAVERN, SHOP, STREET
@piece("bar_counter", OLD, "furniture")
def bar_counter(p, length: float = 3.2, tint=None):
    """A tavern bar: panelled front, a broad top, a brass foot rail and a back shelf ledge."""
    D, H = 0.7, 1.05
    p.box((length, D, H - 0.06), (0, 0, 0.0), W, tint or "#6D4C31", bevel=0.01)
    n = int(length / 0.5)
    for i in range(n):
        x = -length / 2 + length * (i + 0.5) / n
        p.box((length / n - 0.08, 0.02, H - 0.3), (x, -D / 2 - 0.005, 0.12), W, tint or "#80603E", bevel=0.005)
    p.box((length + 0.12, D + 0.16, 0.06), (0, -0.04, H - 0.06), DW, bevel=0.012)
    p.rod((-length / 2 + 0.1, -D / 2 - 0.1, 0.18), (length / 2 - 0.1, -D / 2 - 0.1, 0.18), 0.022, mat.solid("#B8923A", 0.3, 0.9), seg=8)
    p.top((0, -0.04), (length, D + 0.1), H, "bar")


@piece("hanging_sign", ANY, "wall", mount_z=2.6, detail=True)
def hanging_sign(p, color="#2D4A6B", symbol="#E8D9B5"):
    """A shop or inn sign on an iron bracket: a painted board with a pictogram (a mug and a loaf)."""
    ir = mat.surface(IRON)
    p.box((0.05, 0.9, 0.05), (0, -0.45, 0.4), ir, bevel=0.004)
    p.rod((0, -0.05, 0.1), (0, -0.55, 0.42), 0.015, ir, seg=5)
    for x in (-0.28, 0.28):
        p.rod((x, -0.8, 0.4), (x, -0.8, 0.28), 0.006, ir, seg=4)
    p.box((0.7, 0.05, 0.5), (0, -0.8, -0.1), mat.solid(color, 0.6), bevel=0.012)
    p.cyl(0.11, 0.015, (0, -0.84, 0.13), mat.solid(symbol, 0.5), seg=20, rot=(90, 0, 0))
    p.box((0.34, 0.012, 0.05), (0, -0.84, -0.18), mat.solid(symbol, 0.5), bevel=0.0)
    p.anchor("face", (0, -0.826, 0.15))


@piece("hydrant", MODERN, "floor")
def hydrant(p):
    rm = mat.solid("#B02A2A", 0.4)
    p.lathe([(0, 0), (0.1, 0), (0.1, 0.05), (0.07, 0.08), (0.07, 0.5), (0.09, 0.55), (0.06, 0.6), (0.0, 0.62)], (0, 0, 0), rm, seg=16)
    p.cyl(0.04, 0.2, (0, 0, 0.32), rm, seg=10, rot=(0, 90, 0))
    p.cyl(0.04, 0.2, (-0.2, 0, 0.32), rm, seg=10, rot=(0, 90, 0))


@piece("car", MODERN, "floor")
def car(p, color="#2D6CB0"):
    """A simple parked saloon car: body, cabin, glass, wheels, lights."""
    bm_ = mat.solid(color, 0.25, 0.5)
    gm = mat.solid("#1A2630", 0.05)
    L, Wd = 4.3, 1.8
    p.box((Wd, L, 0.55), (0, 0, 0.3), bm_, bevel=0.1)
    p.box((Wd - 0.1, L * 0.5, 0.5), (0, 0.15, 0.82), bm_, bevel=0.14)
    p.box((Wd - 0.04, L * 0.46, 0.4), (0, 0.15, 0.86), gm, bevel=0.06)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.cyl(0.33, 0.22, (sx * (Wd / 2 - 0.1) * 1.0, sy * L * 0.32, 0.33), mat.solid("#17181A", 0.8), seg=20, rot=(0, 90, 0)) if sx > 0 else p.cyl(0.33, 0.22, (sx * (Wd / 2 - 0.1) - 0.22, sy * L * 0.32, 0.33), mat.solid("#17181A", 0.8), seg=20, rot=(0, 90, 0))
            p.cyl(0.18, 0.225, (sx * (Wd / 2 - 0.1) - (0.22 if sx < 0 else 0), sy * L * 0.32, 0.33), mat.solid("#B9BDC2", 0.3, 0.9), seg=12, rot=(0, 90, 0))
    for sx in (-1, 1):
        p.box((0.3, 0.03, 0.1), (sx * 0.6, -L / 2, 0.55), p.glow("#FFF6DC", 3.0), bevel=0.01)
        p.box((0.3, 0.03, 0.1), (sx * 0.6, L / 2, 0.55), p.glow("#D82A2A", 2.0), bevel=0.01)


@piece("anvil", OLD, "floor")
def anvil(p):
    im = mat.surface(IRON)
    p.cyl(0.25, 0.5, (0, 0, 0), W, seg=12)
    p.box((0.55, 0.22, 0.12), (0, 0, 0.5), im, bevel=0.01)
    p.box((0.3, 0.2, 0.1), (0, 0, 0.62), im, bevel=0.01)
    p.cyl(0.04, 0.18, (0.35, 0, 0.56), im, top=0.0, seg=8, rot=(0, 90, 0))


@piece("spinning_wheel", OLD, "floor")
def spinning_wheel(p):
    dm = mat.surface(W)
    p.box((0.9, 0.2, 0.05), (0, 0, 0.35), dm, bevel=0.006)
    for sx in (-1, 1):
        p.rod((sx * 0.4, 0.0, 0.35), (sx * 0.5, 0.0, 0.0), 0.02, dm, seg=6)
    p.cyl(0.3, 0.025, (-0.18, 0.1, 0.35 + 0.3), dm, seg=24, rot=(90, 0, 0))
    for k in range(8):
        a = math.pi * k / 4
        p.rod((-0.18, 0.1, 0.65), (-0.18 + math.cos(a) * 0.29, 0.1, 0.65 + math.sin(a) * 0.29), 0.008, dm, seg=4)
    p.rod((0.2, 0.0, 0.4), (0.4, 0.0, 0.62), 0.015, dm, seg=6)


@piece("broom", ANY, "small")
def broom(p):
    p.cyl(0.012, 1.4, (0, 0, 0.0), mat.surface(DW), seg=6, rot=(8, 0, 0))
    p.cyl(0.07, 0.3, (0, 0.0, 0.0), "thatch", top=0.02, seg=10, rot=(8, 0, 0))


@piece("market_goods", ANY, "small")
def market_goods(p, seed: int = 0):
    """A tray of mixed market goods: pots, a cheese, cloth, and fruit."""
    rnd = random.Random(seed)
    p.box((0.7, 0.4, 0.02), (0, 0, 0), W, bevel=0.004)
    p.cyl(0.12, 0.09, (-0.2, 0, 0.02), mat.solid("#E8D9A8", 0.6), seg=18)
    p.lathe([(0, 0), (0.05, 0), (0.07, 0.07), (0.05, 0.12), (0.0, 0.12)], (0.05, 0.05, 0.02), "terracotta", seg=12)
    for k in range(6):
        p.ball(0.04, (0.25 + rnd.uniform(-0.05, 0.05), rnd.uniform(-0.1, 0.1), 0.06 + 0.0), mat.solid("#C73A2D", 0.4), sub=1)
    p.top((0, 0), (0.6, 0.3), 0.02, "tray")


# ----------------------------------------------------------------------------- wrappers around shared kit pieces
def torch(at=(0, 0, 2.1), rot_z: float = 0.0, name: str = "torch", coll: str = "SET", lit: bool = True, power: float = 55.0, **_):
    """The shared kit's wall torch, adopted as a piece (origin on the wall)."""
    return torch_wall(at=at, rot_z=rot_z, name=name, coll=coll, power=power)


def catalogue() -> list[dict]:
    """All pieces: [{"type", "era", "kind", "mount_z", "detail", "source"}] for dress.py and the audit."""
    return [dict(type=k, era=v["era"], kind=v["kind"], mount_z=v["mount_z"], detail=v["detail"], source=v["source"]) for k, v in sorted(REGISTRY.items())]


# ============================================================================= set kit v2: pieces the thin themes needed
def _bottle(p, x, y, z, h=0.28, r=0.04, color="#2F5A3A", label=True):
    """One bottle: a body, a shoulder, a neck and a cork, standing on (x, y, z)."""
    gm = mat.solid(color, 0.12)
    p.cyl(r, h * 0.62, (x, y, z), gm, top=r * 0.95, seg=8)
    p.cyl(r * 0.95, h * 0.14, (x, y, z + h * 0.62), gm, top=r * 0.34, seg=8)
    p.cyl(r * 0.34, h * 0.24, (x, y, z + h * 0.76), gm, seg=6)
    p.cyl(r * 0.3, 0.014, (x, y, z + h * 0.99), mat.solid("#B08A4E", 0.9), seg=6)
    if label:
        p.box((r * 1.4, 0.004, h * 0.24), (x, y - r - 0.002, z + h * 0.18), mat.solid("#EFE6CF", 0.9), bevel=0.0)


@piece("bottle_shelf", ANY, "wall", mount_z=1.35, detail=False)
def bottle_shelf(p, length: float = 1.5, rows: int = 3, seed: int = 0, mugs: bool = True):
    """A back-bar or pantry shelving: boards on brackets, every row lined with bottles, jugs and mugs."""
    rnd = random.Random(seed)
    cols = ["#2F5A3A", "#6A3B1E", "#3A5A7A", "#7A4A2A", "#4A6A3A", "#8A5A2A"]
    p.box((length, 0.02, rows * 0.36 + 0.04), (0, 0, -0.02), W, "#5A3E26", bevel=0.004)
    for r_ in range(rows + 1):
        z = r_ * 0.36
        p.box((length + 0.06, 0.2, 0.03), (0, -0.1, z), W, "#6D4C31", bevel=0.006)
    for sx in (-1, 1):
        p.box((0.04, 0.2, rows * 0.36 + 0.03), (sx * (length / 2 + 0.01), -0.1, 0.0), W, "#5A3E26", bevel=0.004)
    for r_ in range(rows):
        z = r_ * 0.36 + 0.03
        x = -length / 2 + 0.12
        while x < length / 2 - 0.1:
            k = rnd.random()
            if k < 0.62:
                _bottle(p, x, -0.1, z, rnd.uniform(0.24, 0.32), rnd.uniform(0.032, 0.045), rnd.choice(cols), label=rnd.random() < 0.6)
                x += 0.11
            elif k < 0.82 and mugs:
                p.cyl(0.045, 0.1, (x, -0.1, z), mat.solid("#B8B2A4", 0.5), seg=10)
                x += 0.12
            else:
                p.lathe([(0, 0), (0.06, 0), (0.09, 0.1), (0.05, 0.2), (0.035, 0.23), (0, 0.23)], (x, -0.1, z), mat.solid("#9A6A44", 0.7), seg=10)
                x += 0.2
    p.top((0, -0.1), (length, 0.18), 0.03, "shelf")


@piece("dartboard", ANY, "wall", mount_z=1.7, detail=True)
def dartboard(p, radius: float = 0.23):
    """A dartboard in a round timber frame, three darts in it."""
    p.cyl(radius + 0.04, 0.04, (0, 0, 0), W, "#4A3220", rot=(90, 0, 0), seg=24)
    cols = ("#1E1E1E", "#F2E8CF")
    for i in range(3):
        p.cyl(radius * (1 - i * 0.28), 0.012, (0, -0.042 - i * 0.003, 0), mat.solid(("#1E1E1E", "#B3322C", "#F2E8CF")[i], 0.7), rot=(90, 0, 0), seg=24)
    p.cyl(radius * 0.08, 0.004, (0, -0.058, 0), mat.solid("#2F7A3F", 0.6), rot=(90, 0, 0), seg=10)
    for dx, dz in ((0.05, 0.08), (-0.09, -0.03), (0.0, -0.1)):
        p.rod((dx, -0.05, dz), (dx * 1.1, -0.17, dz * 1.1 + 0.02), 0.004, STEEL, seg=4)
        p.box((0.03, 0.03, 0.002), (dx * 1.1, -0.18, dz * 1.1 + 0.02), mat.solid("#B3322C", 0.8), bevel=0.0)


@piece("herb_bundle", ANY, "light", hang=True)
def herb_bundle(p, n: int = 4, seed: int = 0):
    """Bunches of dried herbs and onions hung from a rail under the beams (hangs from z = 0)."""
    rnd = random.Random(seed)
    p.rod((-0.5, 0, 0), (0.5, 0, 0), 0.012, DW, seg=5)
    for i in range(n):
        x = -0.4 + 0.8 * i / max(1, n - 1)
        L = rnd.uniform(0.3, 0.5)
        p.rod((x, 0, 0), (x, 0, -0.1), 0.004, "rope", seg=4)
        if i % 2:
            for k in range(3):
                p.ball(0.045, (x + (k - 1) * 0.04, 0, -0.16 - k * 0.07), mat.solid("#C79A3E", 0.6), squash=(1, 1, 1.1), sub=1)
        else:
            p.cyl(0.06, L, (x, 0, -0.1 - L), mat.solid(rnd.choice(["#6E7A3E", "#8A7A3A", "#5E6A3A"]), 0.95), top=0.012, seg=6)


@piece("pot_rack", OLD, "light", hang=True)
def pot_rack(p, length: float = 1.4):
    """An iron rack hung from the ceiling, pots, pans and a ladle on hooks (hangs from z = 0)."""
    im = mat.surface(IRON)
    p.rod((-length / 2, 0, 0), (length / 2, 0, 0), 0.015, im, seg=6)
    for sx in (-1, 1):
        p.rod((sx * length * 0.45, 0, 0), (sx * length * 0.45, 0, 0.5), 0.006, im, seg=4)
    xs = [-length / 2 + 0.12 + k * (length - 0.24) / 5 for k in range(6)]
    for k, x in enumerate(xs):
        p.rod((x, 0, 0), (x, 0, -0.1), 0.004, im, seg=4)
        if k % 3 == 0:
            p.cyl(0.11, 0.13, (x, 0, -0.26), mat.solid("#B87A44", 0.35, 0.9), top=0.13, seg=14)
        elif k % 3 == 1:
            p.cyl(0.13, 0.03, (x, 0, -0.26), im, top=0.13, seg=14, rot=(90, 0, 0))
            p.rod((x, 0, -0.26), (x, 0, -0.5), 0.009, im, seg=5)
        else:
            p.ball(0.045, (x, 0, -0.2), im, sub=1)
            p.rod((x, 0, -0.2), (x, 0, -0.52), 0.007, im, seg=5)


@piece("hanging_game", OLD, "light", hang=True)
def hanging_game(p, seed: int = 0):
    """A hare, two pheasants and a string of onions hung from a hook bar in the larder (hangs from z = 0)."""
    p.rod((-0.45, 0, 0), (0.45, 0, 0), 0.012, DW, seg=5)
    p.rod((-0.3, 0, 0), (-0.3, 0, -0.25), 0.004, "rope", seg=4)
    p.ball(0.11, (-0.3, 0, -0.45), mat.solid("#8A6A48", 0.95), squash=(0.8, 0.8, 1.9), sub=2)
    p.ball(0.05, (-0.3, 0, -0.67), mat.solid("#7A5A3E", 0.95), squash=(0.8, 1, 1.3), sub=1)
    for x, col in ((0.0, "#7A4A2A"), (0.28, "#6A4426")):
        p.rod((x, 0, 0), (x, 0, -0.2), 0.004, "rope", seg=4)
        p.ball(0.09, (x, 0, -0.38), mat.solid(col, 0.95), squash=(0.85, 0.85, 1.7), sub=2)
        p.box((0.16, 0.02, 0.2), (x, 0, -0.78), mat.solid("#3F6A5A", 0.9), rot=(0, 0, 8), bevel=0.0)


@piece("cauldron", ANY, "light", source=True)
def cauldron(p, radius: float = 0.34):
    """A big iron cauldron on a tripod over a small fire: flames, a rolling surface and a warm light."""
    im = mat.surface(IRON)
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.3
        p.rod((math.cos(a) * 0.5, math.sin(a) * 0.5, 0), (math.cos(a) * 0.04, math.sin(a) * 0.04, 1.35), 0.025, DW, seg=6)
    p.ball(radius, (0, 0, 0.78), im, squash=(1, 1, 0.82), sub=2)
    p.cyl(radius * 0.92, 0.02, (0, 0, 0.9), mat.solid("#5C6A3A", 0.3), seg=18)
    p.cyl(radius * 1.02, 0.04, (0, 0, 0.9), im, seg=18)
    p.rod((0, 0, 1.35), (0, 0, 1.0), 0.008, im, seg=4)
    for k in range(5):
        a = 2 * math.pi * k / 5
        p.cyl(0.04, 0.5, (math.cos(a) * 0.26, math.sin(a) * 0.26, 0.04), DW, seg=6, rot=(90 if k % 2 else 0, 20 * k, 0))
    for dx, dy, s in ((0.1, 0.0, 1.0), (-0.1, 0.06, 0.8), (0.0, -0.1, 0.7)):
        p.ball(0.11 * s, (dx, dy, 0.2 + 0.1 * s), p.glow("#FF7A12", 3.2), squash=(1, 1, 2.0), sub=1)
    p.ball(0.06, (0.0, 0.0, 0.32), p.glow("#FFB04A", 3.8), squash=(1, 1, 1.8), sub=1)
    p.light("fire", (0, 0, 0.45), "#FFA24A", 70.0, 0.15, False)


@piece("spit_roast", OLD, "floor")
def spit_roast(p, length: float = 1.5):
    """A hearth spit: two iron forks, a turning bar with a crank and a roast on it, standing over the fire of the hearth it is put in."""
    im = mat.surface(IRON)
    for sx in (-1, 1):
        p.rod((sx * length / 2, 0, 0), (sx * length / 2, 0, 0.8), 0.02, im, seg=6)
        p.rod((sx * length / 2 - 0.05, 0, 0.8), (sx * length / 2 + 0.05, 0, 0.82), 0.015, im, seg=5)
    p.rod((-length / 2 - 0.2, 0, 0.82), (length / 2, 0, 0.82), 0.012, im, seg=6)
    p.rod((-length / 2 - 0.2, 0, 0.82), (-length / 2 - 0.2, -0.16, 0.7), 0.01, im, seg=5)
    p.ball(0.15, (0, 0, 0.82), mat.solid("#9A5A2E", 0.5), squash=(2.0, 0.9, 0.9), sub=2)
    p.ball(0.1, (0.28, 0, 0.82), mat.solid("#8A4A24", 0.5), squash=(1.5, 1, 1), sub=1)
    p.box((length * 0.7, 0.2, 0.02), (0, 0, 0.0), im, bevel=0.004)


@piece("water_pump", ANY, "floor")
def water_pump(p):
    """A village hand pump: a stone trough, an iron body with a long handle, a spout and a bucket under it."""
    im = mat.surface(IRON)
    p.box((0.9, 0.5, 0.35), (0, 0, 0), "fieldstone", bevel=0.02)
    p.box((0.74, 0.34, 0.02), (0, 0, 0.35), mat.solid("#1C3A48", 0.05), bevel=0.0)
    p.cyl(0.07, 1.1, (0, 0.08, 0.35), im, top=0.055, seg=10)
    p.cyl(0.095, 0.1, (0, 0.08, 1.4), im, seg=10)
    p.rod((0, 0.08, 1.3), (0.0, -0.45, 1.5), 0.016, im, seg=6)
    p.rod((0, 0.08, 1.1), (0.0, -0.22, 1.0), 0.02, im, seg=6)
    p.cyl(0.14, 0.13, (0, -0.28, 0.35), "oak_planks", top=0.17, seg=12)


@piece("bucket", ANY, "small")
def bucket(p, radius: float = 0.14, height: float = 0.26):
    """A stave bucket with two iron hoops and a rope handle."""
    p.cyl(radius * 0.85, height, (0, 0, 0), W, top=radius, seg=14, tint="#7A5A38")
    for z in (0.3, 0.75):
        p.cyl(radius * (0.86 + 0.15 * z) + 0.006, 0.014, (0, 0, height * z), IRON, seg=14)
    prev = None
    for k in range(9):
        a = math.pi * k / 8
        pt = (math.cos(a) * radius, 0, height + math.sin(a) * radius * 1.1)
        if prev:
            p.rod(prev, pt, 0.007, "rope", seg=4)
        prev = pt
    p.top((0, 0), (radius, radius), height * 0.7, "inside")


@piece("woodpile", ANY, "floor")
def woodpile(p, length: float = 1.3, layers: int = 4, seed: int = 0):
    """Split logs stacked between two posts, ends facing the room."""
    rnd = random.Random(seed)
    for sx in (-1, 1):
        p.box((0.07, 0.07, layers * 0.19 + 0.1), (sx * (length / 2 + 0.04), 0, 0), DW, bevel=0.006)
    for r_ in range(layers):
        n = int(length / 0.19) - (r_ % 2)
        for k in range(n):
            x = -length / 2 + 0.1 + k * 0.19 + (0.095 if r_ % 2 else 0)
            p.cyl(0.085 * rnd.uniform(0.85, 1.05), 0.5, (x, -0.25, 0.09 + r_ * 0.17), W, tint=rnd.choice(["#8A6A44", "#7A5A38", "#9A7A52"]), seg=7, rot=(-90, 0, 0))
    p.top((0, 0), (length, 0.45), layers * 0.17 + 0.18, "stack")


@piece("keg", OLD, "floor")
def keg(p, tint=None):
    """A small cask lying on a timber cradle with a brass tap in its end, a drip bucket."""
    p.box((0.7, 0.05, 0.22), (0, 0.22, 0), DW, bevel=0.006)
    p.box((0.7, 0.05, 0.22), (0, -0.22, 0), DW, bevel=0.006)
    p.lathe([(0, 0), (0.2, 0), (0.25, 0.11), (0.27, 0.25), (0.25, 0.39), (0.2, 0.5), (0, 0.5)], (0, 0, 0.0), W, tint or "#6D4C31", seg=18)
    p.cyl(0.015, 0.1, (0.0, 0.0, 0.0), IRON, seg=6, rot=(0, 0, 0))
    p.rod((0, -0.28, 0.3), (0, -0.4, 0.3), 0.012, mat.solid("#B8923A", 0.3, 0.9), seg=6)
    p.rod((0, -0.4, 0.3), (0, -0.4, 0.22), 0.012, mat.solid("#B8923A", 0.3, 0.9), seg=6)


@piece("cooker", HOME, "furniture")
def cooker(p, color="#E8E6E0"):
    """A freestanding range cooker: a four-ring hob, an oven door with a window and handle, control knobs on the front."""
    cm = mat.solid(color, 0.35, 0.1)
    p.box((0.6, 0.62, 0.88), (0, 0, 0.0), cm, bevel=0.01)
    p.box((0.58, 0.012, 0.42), (0, -0.315, 0.12), mat.solid("#2B2D31", 0.25), bevel=0.0)
    p.rod((-0.22, -0.35, 0.5), (0.22, -0.35, 0.5), 0.011, mat.solid("#B9BDC2", 0.25, 1.0), seg=6)
    p.box((0.6, 0.62, 0.02), (0, 0, 0.88), mat.solid("#18191C", 0.2), bevel=0.003)
    for dx in (-0.14, 0.14):
        for dy in (-0.14, 0.14):
            p.cyl(0.07, 0.006, (dx, dy, 0.9), mat.solid("#3A3D42", 0.4), seg=16)
    p.box((0.6, 0.06, 0.12), (0, 0.28, 0.9), cm, bevel=0.006)
    for k in range(4):
        p.cyl(0.018, 0.02, (-0.2 + k * 0.133, -0.3, 0.84), mat.solid("#9EA3A8", 0.3, 0.9), seg=8, rot=(90, 0, 0))
    p.top((0, 0), (0.56, 0.58), 0.9, "hob")


@piece("dining_table", HOME, "furniture")
def dining_table(p, length: float = 1.5, width: float = 0.85, tint="#8A6A44"):
    """A plain family table on four turned legs with a hard top."""
    p.box((length, width, 0.04), (0, 0, 0.72), W, tint, bevel=0.008)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((0.06, 0.06, 0.72), (sx * (length / 2 - 0.1), sy * (width / 2 - 0.1), 0), W, tint, bevel=0.006)
    p.box((length - 0.2, 0.04, 0.08), (0, 0, 0.62), W, tint, bevel=0.004)
    p.top((0, 0), (length - 0.1, width - 0.1), 0.76, "top")


@piece("side_table", HOME, "furniture")
def side_table(p, size: float = 0.5, tint="#6B4A30"):
    """A small square side table with a shelf below."""
    p.box((size, size, 0.035), (0, 0, 0.54), W, tint, bevel=0.006)
    p.box((size - 0.08, size - 0.08, 0.025), (0, 0, 0.14), W, tint, bevel=0.004)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((0.04, 0.04, 0.55), (sx * (size / 2 - 0.04), sy * (size / 2 - 0.04), 0), W, tint, bevel=0.004)
    p.top((0, 0), (size - 0.06, size - 0.06), 0.575, "top")


@piece("radiator", HOME, "wall", mount_z=0.15)
def radiator(p, length: float = 1.0):
    """A white panel radiator with fins, brackets and a valve."""
    wm = mat.solid("#F2F1EC", 0.4)
    n = int(length / 0.08)
    for i in range(n):
        p.box((0.05, 0.06, 0.55), (-length / 2 + 0.04 + i * 0.08, -0.04, 0.0), wm, bevel=0.012)
    p.box((length, 0.02, 0.04), (0, -0.01, 0.1), wm, bevel=0.003)
    p.cyl(0.02, 0.04, (length / 2 - 0.03, -0.04, -0.02), mat.solid("#B9BDC2", 0.3, 1.0), seg=8)


@piece("sideboard", ANY, "furniture")
def sideboard(p, length: float = 1.6, height: float = 0.8, tint="#6B4A30"):
    """A low cabinet with panelled doors and drawers, a top deep enough for lamps and frames."""
    D = 0.45
    p.box((length, D, height - 0.05), (0, 0, 0.06), W, tint, bevel=0.008)
    p.box((length + 0.04, D + 0.03, 0.04), (0, -0.01, height - 0.04), W, "#5A3E26", bevel=0.008)
    for sx in (-1, 1):
        p.box((0.05, 0.05, 0.07), (sx * (length / 2 - 0.06), 0, 0.0), DW, bevel=0.004)
    n = max(2, int(length / 0.5))
    for i in range(n):
        x = -length / 2 + length * (i + 0.5) / n
        p.box((length / n - 0.04, 0.015, height - 0.2), (x, -D / 2 - 0.005, 0.12), W, "#7A583A", bevel=0.004)
        p.cyl(0.015, 0.02, (x + 0.1 if i % 2 else x - 0.1, -D / 2 - 0.02, height * 0.5), mat.solid("#B8923A", 0.3, 0.9), seg=8, rot=(90, 0, 0))
    p.top((0, 0), (length - 0.08, D - 0.06), height, "top")


@piece("globe", LATER, "small", detail=False)
def globe(p, radius: float = 0.14):
    """A desk globe on a brass ring and a turned foot."""
    p.cyl(0.09, 0.02, (0, 0, 0), DW, seg=14)
    p.cyl(0.015, 0.14, (0, 0, 0.02), mat.solid("#B8923A", 0.3, 0.9), seg=6)
    p.ball(radius, (0, 0, 0.16 + radius), mat.solid("#2F6A8A", 0.4), sub=2)
    for k, (dx, dz, s) in enumerate(((0.05, 0.05, 0.06), (-0.07, -0.03, 0.05), (0.02, -0.09, 0.04))):
        p.ball(s, (dx, -radius * 0.82, 0.16 + radius + dz), mat.solid("#6E9A52", 0.6), squash=(1, 0.2, 1), sub=1)
    p.rod((-radius * 1.05, 0, 0.16), (radius * 1.05, 0, 0.16 + radius * 2), 0.006, mat.solid("#B8923A", 0.3, 0.9), seg=4)


@piece("photo_frame", ANY, "small", detail=True)
def photo_frame(p, w: float = 0.16, h: float = 0.2, seed: int = 0):
    """A framed photograph on a little stand."""
    rnd = random.Random(seed)
    p.box((w + 0.03, 0.015, h + 0.03), (0, 0, 0.0), mat.solid("#3A2A1C", 0.5), rot=(-10, 0, 0), bevel=0.003)
    p.box((w, 0.004, h), (0, -0.009, 0.015), mat.solid(rnd.choice(["#8FB0C9", "#C9A98F", "#9FBF9A", "#D8C27A"]), 0.5), rot=(-10, 0, 0), bevel=0.0)
    p.box((0.04, 0.03, 0.12), (0, 0.025, 0.0), mat.solid("#3A2A1C", 0.5), rot=(20, 0, 0), bevel=0.002)


@piece("till", LATER, "small")
def till(p, modern: bool = False):
    """A shop till: a brass cash register with keys and a drawer, or a modern card reader on a stand."""
    if modern:
        p.box((0.32, 0.25, 0.1), (0, 0, 0.0), mat.solid("#2B2D31", 0.4), bevel=0.01)
        p.box((0.2, 0.01, 0.11), (0, -0.12, 0.11), p.glow("#9CE0B0", 1.0), rot=(-20, 0, 0), bevel=0.0)
        return
    bm = mat.solid("#B8923A", 0.3, 0.9)
    p.box((0.4, 0.3, 0.16), (0, 0, 0.0), bm, bevel=0.01)
    p.box((0.4, 0.26, 0.2), (0, 0.02, 0.16), bm, rot=(-12, 0, 0), bevel=0.01)
    for r_ in range(3):
        for c in range(5):
            p.cyl(0.015, 0.012, (-0.13 + c * 0.065, -0.1 - r_ * 0.0, 0.18 + r_ * 0.05), mat.solid("#EFE6CF", 0.5), seg=8, rot=(-12, 0, 0))
    p.box((0.2, 0.05, 0.06), (0, 0.06, 0.36), mat.solid("#EFE6CF", 0.6), bevel=0.005)


@piece("balance_scales", OLD, "small", detail=True)
def balance_scales(p):
    """Merchant's balance scales: a post, a beam and two pans on chains, weights on one."""
    bm = mat.solid("#B8923A", 0.3, 0.9)
    p.cyl(0.06, 0.02, (0, 0, 0), bm, seg=12)
    p.cyl(0.012, 0.3, (0, 0, 0.02), bm, seg=6)
    p.rod((-0.2, 0, 0.32), (0.2, 0, 0.32), 0.008, bm, seg=5)
    for sx in (-1, 1):
        p.rod((sx * 0.2, 0, 0.32), (sx * 0.2, 0, 0.12), 0.003, bm, seg=3)
        p.cyl(0.07, 0.012, (sx * 0.2, 0, 0.1), bm, top=0.05, seg=12)
    for k in range(3):
        p.cyl(0.02, 0.02, (0.17 + k * 0.025, 0, 0.112), mat.solid("#4A4A4A", 0.5, 0.8), seg=8)


@piece("display_stand", ANY, "furniture")
def display_stand(p, width: float = 1.2, tiers: int = 3, seed: int = 0, kind: str = "goods"):
    """A stepped shop display: tiers of timber with bolts of cloth, loaves, boxes or fruit laid out on each."""
    rnd = random.Random(seed)
    for t in range(tiers):
        y = t * 0.28
        p.box((width, 0.5 - t * 0.12, 0.06), (0, y * 0.4, 0.3 + t * 0.3), W, "#7A583A", bevel=0.008)
        p.box((width - 0.08, 0.04, 0.3 + t * 0.3), (0, y * 0.4 + (0.25 - t * 0.06), 0.0), W, "#6D4C31", bevel=0.006)
    for t in range(tiers):
        yc = t * 0.28 * 0.4
        z = 0.36 + t * 0.3
        n = int(width / 0.2)
        for k in range(n):
            x = -width / 2 + 0.1 + k * (width - 0.2) / max(1, n - 1)
            c = rnd.choice(["#B3322C", "#2D6CB0", "#D8A93A", "#3F8F5A", "#E8DCC0", "#8A5A9A"])
            if kind == "goods":
                p.box((0.16, 0.2, 0.1 + 0.03 * rnd.random()), (x, yc, z), mat.solid(c, 0.8), bevel=0.01)
            else:
                p.ball(0.07, (x, yc, z + 0.06), mat.solid(c, 0.6), sub=1)
    p.top((0, 0), (width - 0.1, 0.3), 0.36 + (tiers - 1) * 0.3, "top")


@piece("grandfather_clock", HOME, "furniture", detail=True)
def grandfather_clock(p, height: float = 2.0, tint="#5A3E26"):
    """A tall case clock: plinth, long trunk with a glass door, a round dial with hands, a pendulum behind the glass."""
    p.box((0.46, 0.28, 0.25), (0, 0, 0.0), W, tint, bevel=0.01)
    p.box((0.36, 0.22, height - 0.7), (0, 0, 0.25), W, tint, bevel=0.01)
    p.box((0.22, 0.01, height - 1.1), (0, -0.115, 0.4), mat.solid("#2A2018", 0.2), bevel=0.0)
    p.rod((0, -0.1, 0.4 + height - 1.1), (0, -0.1, 0.55), 0.004, mat.solid("#B8923A", 0.3, 0.9), seg=4)
    p.cyl(0.05, 0.015, (0, -0.1, 0.55), mat.solid("#B8923A", 0.3, 0.9), seg=12, rot=(90, 0, 0))
    p.box((0.42, 0.26, 0.5), (0, 0, height - 0.45), W, tint, bevel=0.01)
    p.cyl(0.16, 0.012, (0, -0.131, height - 0.25), mat.solid("#EFE6CF", 0.6), seg=24, rot=(90, 0, 0))
    p.rod((0, -0.14, height - 0.25), (0.0, -0.14, height - 0.12), 0.006, mat.solid("#1E1E1E", 0.5), seg=4)
    p.rod((0, -0.14, height - 0.25), (0.08, -0.14, height - 0.28), 0.006, mat.solid("#1E1E1E", 0.5), seg=4)
    p.box((0.48, 0.3, 0.05), (0, 0, height - 0.05), W, tint, bevel=0.008)


# ----------------------------------------------------------------------------- outdoor pieces
@piece("tree_round", ANY, "floor")
def tree_round(p, height: float = 6.0, crown: float = 2.4, seed: int = 0, tint=None, autumn: bool = False):
    """A broadleaf tree: a tapering trunk with two limbs, and a crown of overlapping leaf masses."""
    rnd = random.Random(seed)
    th = height * 0.55
    p.cyl(0.26 * crown / 2.4 + 0.08, th, (0, 0, 0), "bark", top=0.1, seg=9)
    for sx in (-1, 1):
        p.rod((0, 0, th * 0.6), (sx * crown * 0.45, rnd.uniform(-0.4, 0.4), th * 0.92), 0.06, "bark", seg=5)
    cols = ["#6E8A3A", "#4F7A32", "#7A9A44"] if not autumn else ["#B8742A", "#9A5A22", "#C9942E"]
    for k in range(5):
        a = rnd.uniform(0, 6.28)
        r_ = crown * rnd.uniform(0.0, 0.45)
        rr = crown * rnd.uniform(0.62, 0.9)
        p.ball(rr, (math.cos(a) * r_, math.sin(a) * r_, th + crown * 0.3 + rnd.uniform(-0.2, 0.7) * crown * 0.5), "leaves", tint or rnd.choice(cols), squash=(1, 1, 0.82), sub=2)


@piece("tree_pine", ANY, "floor")
def tree_pine(p, height: float = 7.0, radius: float = 1.5, seed: int = 0):
    """A conifer: a straight trunk and five tiers of drooping needle-green cones."""
    rnd = random.Random(seed)
    p.cyl(0.18, height * 0.3, (0, 0, 0), "bark", top=0.12, seg=8)
    tiers = 5
    for t in range(tiers):
        z = height * (0.18 + 0.15 * t)
        r_ = radius * (1.0 - t / (tiers + 0.5))
        p.cyl(r_, height * 0.24, (0, 0, z), "leaves", tint=rnd.choice(["#2F5A32", "#3A6A38", "#2A4F30"]), top=0.04, seg=9)


@piece("bush", ANY, "floor")
def bush(p, size: float = 0.9, seed: int = 0, flowers: bool = False):
    """A shrub: three overlapping leaf masses, optionally with blossoms."""
    rnd = random.Random(seed)
    for k in range(3):
        rr = size * rnd.uniform(0.38, 0.55)
        p.ball(rr, (rnd.uniform(-0.3, 0.3) * size, rnd.uniform(-0.3, 0.3) * size, rr * 0.85), "leaves", rnd.choice(["#4F7A32", "#5E8A38", "#3F6A2E"]), squash=(1, 1, 0.85), sub=2)
    if flowers:
        for k in range(8):
            a = rnd.uniform(0, 6.28)
            p.ball(0.035, (math.cos(a) * size * 0.4, math.sin(a) * size * 0.4, size * rnd.uniform(0.35, 0.65)), mat.solid(rnd.choice(["#E8A0B8", "#F2E27A", "#F6F1E4"]), 0.6), sub=1)


@piece("hedge", ANY, "floor")
def hedge(p, length: float = 3.0, height: float = 1.1):
    """A clipped hedge: a leafy block with a rounded top."""
    p.box((length, 0.7, height * 0.82), (0, 0, 0), "leaves", "#4A7430", bevel=0.12)
    p.box((length - 0.1, 0.58, height * 0.2), (0, 0, height * 0.8), "leaves", "#5A8438", bevel=0.1)


@piece("signpost", ANY, "floor", detail=True)
def signpost(p, arms: int = 3, seed: int = 0):
    """A crossroads signpost: a post with pointed boards pointing different ways."""
    rnd = random.Random(seed)
    p.cyl(0.07, 2.5, (0, 0, 0), W, "#6A4A2E", seg=8)
    for k in range(arms):
        z = 1.5 + 0.28 * k
        a = rnd.uniform(-35, 35) + (180 if k % 2 else 0)
        p.box((0.9, 0.03, 0.2), (0, 0, z), W, "#C9AE7A", rot=(0, 0, a), bevel=0.004)
        p.box((0.5, 0.005, 0.03), (0, -0.02, z + 0.02), mat.solid("#2A2018", 0.9), rot=(0, 0, a), bevel=0.0)


@piece("washing_line", ANY, "floor", detail=True)
def washing_line(p, length: float = 4.0, seed: int = 0):
    """Two poles, a sagging rope and a row of washing: sheets, shirts and a pair of trousers."""
    rnd = random.Random(seed)
    for sx in (-1, 1):
        p.cyl(0.04, 2.2, (sx * length / 2, 0, 0), W, "#6A4A2E", seg=6)
    prev = None
    n = 14
    for k in range(n + 1):
        u = k / n
        pt = (-length / 2 + u * length, 0, 2.05 - 0.22 * math.sin(math.pi * u))
        if prev:
            p.rod(prev, pt, 0.004, "rope", seg=4)
        prev = pt
    x = -length / 2 + 0.4
    while x < length / 2 - 0.5:
        w_ = rnd.choice([0.5, 0.7, 0.9])
        h_ = rnd.choice([0.5, 0.8, 1.0])
        u = (x + length / 2) / length
        zt = 2.05 - 0.22 * math.sin(math.pi * u) - 0.02
        p.grid(w_, h_, (x + w_ / 2, 0, zt), CLOTH, rnd.choice(["#F1EADB", "#B3322C", "#3F6C9A", "#D8C27A", "#F4F4F4", "#7A9A6A"]), nx=6, ny=2, amp=0.02, waves=1.5)
        x += w_ + 0.25


@piece("hitching_rail", OLD, "floor")
def hitching_rail(p, length: float = 3.0):
    """A rail between posts for tying horses, a water trough and a heap of hay."""
    for sx in (-1, 1):
        p.cyl(0.07, 1.25, (sx * length / 2, 0, 0), W, "#6A4A2E", seg=8)
    p.cyl(0.05, length, (-length / 2, 0, 1.05), W, "#7A583A", seg=8, rot=(0, 90, 0))
    p.cyl(0.04, length, (-length / 2, 0, 0.7), W, "#7A583A", seg=8, rot=(0, 90, 0))
    p.box((1.3, 0.4, 0.4), (-length * 0.2, -0.55, 0), W, "#6D4C31", bevel=0.01)
    p.box((1.18, 0.28, 0.02), (-length * 0.2, -0.55, 0.38), mat.solid("#1C3A48", 0.05), bevel=0.0)
    p.ball(0.28, (length * 0.28, -0.55, 0.16), "thatch", None, squash=(1.5, 1, 0.6), sub=2)
    for k in range(2):
        p.rod((length * (0.1 + 0.2 * k) - 0.3, 0, 1.05), (length * (0.1 + 0.2 * k) - 0.3, -0.12, 0.75), 0.008, "rope", seg=4)


@piece("horse", OLD, "floor")
def horse(p, coat="#7A4A2A", mane="#2A1A12", seed: int = 0):
    """A stylised standing horse, simple rounded forms: barrel body, arched neck, wedge head, four legs, a tail and a blanket."""
    cm = mat.solid(coat, 0.75)
    mm = mat.solid(mane, 0.9)
    p.ball(0.36, (0, 0, 1.0), cm, squash=(2.0, 0.78, 0.8), sub=2)
    p.ball(0.3, (0.5, 0, 1.06), cm, squash=(1.0, 0.8, 0.95), sub=2)
    p.ball(0.28, (-0.5, 0, 1.02), cm, squash=(1.0, 0.82, 0.95), sub=2)
    p.rod((0.66, 0, 1.12), (0.98, 0, 1.55), 0.15, cm, seg=8)
    p.ball(0.2, (1.02, 0, 1.58), cm, squash=(1.0, 0.8, 0.95), sub=2)
    p.rod((1.04, 0, 1.54), (1.3, 0, 1.38), 0.085, cm, seg=8)
    p.ball(0.075, (1.31, 0, 1.36), mat.solid("#2A1A12", 0.8), sub=1)
    for sx in (-0.45, 0.5):
        for sy in (-0.14, 0.14):
            p.rod((sx, sy, 0.85), (sx + (0.04 if sx > 0 else -0.04), sy, 0.1), 0.065, cm, seg=7)
            p.cyl(0.07, 0.1, (sx + (0.04 if sx > 0 else -0.04), sy, 0.0), mat.solid("#1C1410", 0.5), top=0.06, seg=7)
    p.rod((0.8, 0, 1.64), (1.0, 0, 1.72), 0.03, mm, seg=5)
    p.rod((0.72, 0.02, 1.52), (0.96, 0.02, 1.7), 0.04, mm, seg=5)
    p.rod((-0.72, 0, 1.08), (-0.9, 0, 0.45), 0.06, mm, seg=6)
    p.box((0.6, 0.5, 0.05), (0.05, 0, 1.28), mat.solid("#A3231F", 0.9), bevel=0.01)
    for sy in (-0.07, 0.07):
        p.cyl(0.03, 0.12, (1.0, sy, 1.72), cm, top=0.01, seg=5)


@piece("torch_stand", ANY, "light", source=True)
def torch_stand(p, height: float = 2.0, power: float = 90.0):
    """A standing torch: a timber pole, an iron cup with oil-soaked rags burning, a warm light."""
    p.cyl(0.04, height, (0, 0, 0), W, "#4A3220", seg=7)
    p.cyl(0.12, 0.003 + 0.01, (0, 0, height - 0.06), mat.surface(IRON), seg=12)
    p.cyl(0.05, 0.16, (0, 0, height - 0.04), mat.surface(IRON), top=0.12, seg=10)
    p.ball(0.1, (0, 0, height + 0.18), p.glow("#FF7A12", 3.2), squash=(1, 1, 1.9), sub=2)
    p.ball(0.06, (0, 0, height + 0.12), p.glow("#FFB04A", 3.8), squash=(1, 1, 1.5), sub=1)
    p.light("torch", (0, 0, height + 0.2), "#FF9A4A", power, 0.12, False)


@piece("palisade", ANY, "floor")
def palisade(p, length: float = 6.0, height: float = 2.6, seed: int = 0, broken: bool = False, gate: bool = False):
    """A wall of sharpened logs lashed with two rails; broken=True leaves gaps and snapped stumps, gate=True a double gate in the middle."""
    rnd = random.Random(seed)
    n = int(length / 0.3)
    for k in range(n):
        x = -length / 2 + 0.15 + k * 0.3
        if gate and abs(x) < 1.0:
            continue
        hh = height * rnd.uniform(0.92, 1.08)
        if broken and rnd.random() < 0.18:
            continue
        if broken and rnd.random() < 0.2:
            hh *= rnd.uniform(0.3, 0.55)
            p.cyl(0.14, hh, (x, rnd.uniform(-0.03, 0.03), 0), W, "#6A4A2E", top=0.11, seg=7)
            continue
        lean = rnd.uniform(-4, 4) + (rnd.uniform(-14, -8) if broken and rnd.random() < 0.25 else 0)
        p.cyl(0.14, hh - 0.35, (x, rnd.uniform(-0.03, 0.03), 0.04), W, "#6A4A2E", top=0.13, seg=7, rot=(lean, 0, 0))
        p.cyl(0.13, 0.35, (x, rnd.uniform(-0.03, 0.03) + lean * 0.006, hh - 0.35), W, "#7A583A", top=0.01, seg=7, rot=(lean, 0, 0))
    for z in (0.5, height * 0.72):
        p.box((length, 0.1, 0.12), (0, -0.15, z), DW, bevel=0.01)
    if gate:
        for sx in (-1, 1):
            p.box((0.3, 0.3, height + 0.5), (sx * 1.15, 0, 0), DW, bevel=0.02)
        p.box((2.6, 0.3, 0.3), (0, 0, height + 0.3), DW, bevel=0.02)


@piece("watchtower", ANY, "floor")
def watchtower(p, height: float = 6.0, size: float = 2.2):
    """A timber watchtower: four braced legs, a ladder, a railed lookout platform and a pitched roof, a beacon bowl."""
    hs = size / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.cyl(0.11, height, (sx * hs, sy * hs, 0.015), DW, seg=7)
    for z in (1.2, 2.6, 4.0):
        for sx, sy, dx, dy in ((0, -1, 1, 0), (0, 1, 1, 0), (-1, 0, 0, 1), (1, 0, 0, 1)):
            p.box((size if dx else 0.07, size if dy else 0.07, 0.07), (sx * hs, sy * hs, z), DW, bevel=0.005)
    for sy in (-1, 1):
        p.rod((-hs, sy * hs, 1.2), (hs, sy * hs, 2.6), 0.04, DW, seg=5)
        p.rod((hs, sy * hs, 1.2), (-hs, sy * hs, 2.6), 0.04, DW, seg=5)
    p.box((size + 0.7, size + 0.7, 0.14), (0, 0, height - 0.1), W, "#7A583A", bevel=0.01)
    for sx, sy, w_, d_ in ((0, -1, size + 0.7, 0.06), (0, 1, size + 0.7, 0.06), (-1, 0, 0.06, size + 0.7), (1, 0, 0.06, size + 0.7)):
        p.box((w_, d_, 0.09), (sx * (hs + 0.32), sy * (hs + 0.32), height + 0.85), DW, bevel=0.004)
        p.box((w_, d_, 0.09), (sx * (hs + 0.32), sy * (hs + 0.32), height + 0.45), DW, bevel=0.004)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.cyl(0.04, 1.6, (sx * (hs + 0.3), sy * (hs + 0.3), height - 0.05), DW, seg=6)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.rod((sx * (hs + 0.3), sy * (hs + 0.3), height + 1.5), (0, 0, height + 2.3), 0.04, DW, seg=5)
    for sy in (-1, 1):
        p.box((size + 0.9, 1.6, 0.06), (0, sy * 0.7, height + 1.9), W, "#5A3E26", rot=(sy * -35, 0, 0), mid=True, bevel=0.01)
    for side in (-0.2, 0.2):
        p.rod((hs * 0.2 + side, -hs - 0.12, 0.0), (hs * 0.2 + side, -hs - 0.12, height - 0.1), 0.025, W, seg=5)
    for k in range(int(height / 0.4)):
        p.rod((hs * 0.2 - 0.2, -hs - 0.12, 0.3 + k * 0.4), (hs * 0.2 + 0.2, -hs - 0.12, 0.3 + k * 0.4), 0.015, W, seg=4)
    p.cyl(0.22, 0.18, (0, 0, height + 0.02), mat.surface(IRON), top=0.28, seg=10)
    p.ball(0.12, (0, 0, height + 0.3), p.glow("#FF7A12", 3.2), squash=(1, 1, 1.8), sub=1)
    p.light("beacon", (0, 0, height + 0.4), "#FF9A4A", 80.0, 0.15, False)


@piece("pavilion", ANY, "floor", detail=True)
def pavilion(p, width: float = 5.0, length: float = 6.5, height: float = 3.2, color="#A3231F"):
    """A commander's tent: tall walls, a hipped roof in a bold colour with a scalloped valance, a doorway, a gilt finial and two banners."""
    cm = mat.solid(color, 0.9)
    wm = mat.solid("#E8DCC0", 0.95)
    p.box((width, length, height * 0.62), (0, 0, 0), wm, bevel=0.02)
    for sy in (-1, 1):
        p.box((0.2, 0.2, height), (-width / 2, sy * (length / 2 - 0.1), 0), DW, bevel=0.01)
        p.box((0.2, 0.2, height), (width / 2, sy * (length / 2 - 0.1), 0), DW, bevel=0.01)
    hh = height * 0.62
    bm = p._bm(cm, None, 0.0)
    V = lambda x, y, z: bm.verts.new((x, y, z))
    a, b, c, d = V(-width / 2 - 0.2, -length / 2 - 0.2, hh), V(width / 2 + 0.2, -length / 2 - 0.2, hh), V(width / 2 + 0.2, length / 2 + 0.2, hh), V(-width / 2 - 0.2, length / 2 + 0.2, hh)
    apex = V(0, 0, hh + height * 0.55)
    for u, v in ((a, b), (b, c), (c, d), (d, a)):
        bm.faces.new((u, v, apex))
    for sy in (-1, 1):
        n = 9
        for k in range(n):
            p.box((width / n, 0.03, 0.22), (-width / 2 + width * (k + 0.5) / n, sy * (length / 2 + 0.2), hh - 0.18), mat.solid("#EDC04A" if k % 2 else color, 0.8), bevel=0.004)
    p.box((1.3, 0.02, hh * 0.85), (0, -length / 2 - 0.02, 0), mat.solid("#1C1612", 1.0), bevel=0.0)
    p.cyl(0.03, 0.6, (0, 0, hh + height * 0.55), DW, seg=6)
    p.ball(0.1, (0, 0, hh + height * 0.55 + 0.65), GOLD, sub=1)
    for sx in (-1, 1):
        p.cyl(0.035, 3.6, (sx * 1.4, -length / 2 - 0.9, 0), DW, seg=8)
        p.grid(0.7, 1.5, (sx * 1.4, -length / 2 - 0.92, 3.5), CLOTH, color if sx < 0 else "#2D4A6B", nx=8, ny=3, amp=0.03, waves=2.0)


@piece("siege_engine", OLD, "floor")
def siege_engine(p, damaged: bool = False):
    """A wheeled catapult: a heavy timber frame, a ratchet winch, a throwing arm with a sling cup, a stack of stones; damaged=True breaks the arm."""
    for sy in (-1, 1):
        p.box((2.6, 0.18, 0.2), (0, sy * 0.65, 0.35), DW, bevel=0.01)
    for x in (-1.0, 0.1, 1.1):
        p.box((0.2, 1.5, 0.18), (x, 0, 0.35), DW, bevel=0.01)
    for sy in (-1, 1):
        _wheel(p, -0.9, sy * 0.85, 0.54, 0.5)
        _wheel(p, 0.9, sy * 0.85, 0.54, 0.5)
        p.rod((-0.9, sy * 0.85, 0.5), (0.9, sy * 0.85, 0.5), 0.03, DW, seg=6)
    for sy in (-1, 1):
        p.box((0.2, 0.2, 1.4), (0.3, sy * 0.55, 0.45), DW, bevel=0.01)
        p.rod((0.3, sy * 0.55, 1.85), (-0.5, sy * 0.55, 1.1), 0.06, DW, seg=6)
    p.cyl(0.08, 1.3, (0.3, -0.65, 1.7), mat.surface(IRON), seg=8, rot=(-90, 0, 0))
    ang = 62 if not damaged else 30
    if damaged:
        p.rod((0.3, 0, 1.7), (-0.4, 0, 2.5), 0.07, DW, seg=7)
        p.rod((-0.4, 0, 2.5), (-0.55, 0.1, 2.35), 0.05, DW, seg=7)
    else:
        p.rod((0.3, 0, 1.7), (-1.9, 0, 2.7), 0.07, DW, seg=7)
        p.cyl(0.18, 0.12, (-1.95, 0, 2.62), mat.surface("leather"), top=0.12, seg=10)
    for k in range(5):
        p.ball(0.16, (1.55 + (k % 3) * 0.3, -0.9 + (k // 3) * 0.3, 0.16), mat.solid("#8A8680", 0.9), sub=1)
    p.rod((-0.1, 0.0, 1.45), (1.0, 0.0, 0.7), 0.012, "rope", seg=4)


@piece("wrecked_cart", OLD, "floor")
def wrecked_cart(p, seed: int = 0):
    """A cart on its side with a broken axle and one wheel off, spilled sacks beside it."""
    rnd = random.Random(seed)
    p.box((1.4, 0.06, 0.8), (0, 0.0, 0.0), W, bevel=0.008)
    for sx in (-1, 1):
        p.box((0.05, 0.7, 0.8), (sx * 0.68, -0.34, 0.0), W, bevel=0.006)
    p.box((1.4, 0.05, 0.4), (0, -0.7, 0.0), W, bevel=0.006, rot=(0, 0, 0))
    _wheel(p, 0.0, 0.05, 0.55, 0.5)
    p.rod((0, 0.0, 0.55), (0, -0.8, 0.3), 0.03, mat.surface(IRON), seg=6)
    p.cyl(0.5, 0.06, (1.2, -0.5, 0.0), W, seg=16, rot=(0, 0, 0))
    p.rod((-0.7, 0, 0.4), (-2.0, 0.4, 0.0), 0.03, DW, seg=6)
    for k in range(3):
        p.ball(0.2, (-0.5 + k * 0.5, -1.4 - 0.1 * k, 0.22), CLOTH, rnd.choice(["#B49A6C", "#A08A5C"]), squash=(1.2, 0.9, 0.8), sub=1)


@piece("spear_stuck", ANY, "small")
def spear_stuck(p, count: int = 3, seed: int = 0):
    """A few spears planted at angles in the ground, one with a torn pennant."""
    rnd = random.Random(seed)
    for k in range(count):
        a = rnd.uniform(-14, 14)
        b = rnd.uniform(-10, 10)
        x = (k - (count - 1) / 2) * 0.35
        p.cyl(0.018, 1.9, (x, rnd.uniform(-0.1, 0.1), 0), DW, seg=6, rot=(a, b, 0), top=0.016)
        p.cyl(0.03, 0.2, (x + math.sin(math.radians(b)) * 1.9, rnd.uniform(-0.1, 0.1) - math.sin(math.radians(a)) * 1.9, math.cos(math.radians(a)) * 1.88), STEEL, top=0.003, seg=5, rot=(a, b, 0))
    p.grid(0.3, 0.4, (0.0, 0.0, 1.55), CLOTH, "#A3231F", nx=5, ny=2, amp=0.03, waves=2.0)


@piece("shield_stuck", OLD, "floor")
def shield_stuck(p, color="#2D4A6B", seed: int = 0):
    """A round shield half in the ground, tilted, with a few arrows stuck in its face."""
    rnd = random.Random(seed)
    p.cyl(0.4, 0.05, (0, 0, 0.12), mat.solid(color, 0.55), seg=24, rot=(-62, 0, 0), top=0.38)
    p.cyl(0.07, 0.05, (0, -0.04, 0.34), STEEL, seg=12, rot=(-62, 0, 0))
    for k in range(3):
        x = rnd.uniform(-0.2, 0.2)
        z0 = 0.2 + rnd.random() * 0.2
        p.rod((x, -0.2, z0), (x + rnd.uniform(-0.1, 0.1), -0.55, z0 + 0.45), 0.007, DW, seg=4)


@piece("fallen_banner", ANY, "floor", detail=True)
def fallen_banner(p, color="#A3231F", length: float = 2.6):
    """A standard that has come down: a snapped pole on the ground and the torn cloth trailing from it."""
    p.cyl(0.035, length, (-length / 2, 0, 0.04), DW, seg=7, rot=(0, 90, 0))
    p.box((0.05, 0.05, 0.05), (length / 2, 0, 0.0), DW, bevel=0.0)
    p.grid(1.3, 0.8, (0.2, -0.2, 0.0), CLOTH, color, nx=14, ny=2, amp=0.0, waves=1.0, rot=(90, 0, 8))
    p.box((1.3, 0.8, 0.006), (0.2, -0.45, 0.01), mat.solid(color, 0.9), rot=(0, 0, 10), bevel=0.0)


@piece("haystack", ANY, "floor")
def haystack(p, radius: float = 1.1):
    """A rounded rick of hay with a pitchfork stuck in it."""
    p.ball(radius, (0, 0, radius * 0.7), "thatch", "#C9AE5E", squash=(1, 1, 0.85), sub=2)
    p.rod((radius * 0.5, -radius * 0.7, 0.2), (radius * 0.2, -radius * 0.9, 1.6), 0.015, DW, seg=5)


@piece("gravestone", ANY, "floor")
def gravestone(p, seed: int = 0):
    """A leaning headstone with a cross carved in it."""
    p.box((0.6, 0.12, 0.8), (0, 0, 0), "castle_stone", "#8A8A84", rot=(0, 0, 0), bevel=0.04)
    p.box((0.06, 0.02, 0.3), (0, -0.07, 0.35), mat.solid("#5A5A56", 0.9), bevel=0.0)
    p.box((0.2, 0.02, 0.06), (0, -0.07, 0.5), mat.solid("#5A5A56", 0.9), bevel=0.0)


@piece("traffic_light", MODERN, "floor")
def traffic_light(p, state: str = "red"):
    """A pole-mounted traffic light with three lenses, one lit."""
    im = mat.surface(IRON)
    p.cyl(0.07, 3.4, (0, 0, 0), im, seg=10)
    p.box((0.3, 0.26, 0.9), (0, -0.2, 2.6), mat.solid("#1E1F22", 0.5), bevel=0.02)
    for k, (c, s) in enumerate((("red", "#FF3A2A"), ("amber", "#FFB02A"), ("green", "#3AFF6A"))):
        p.ball(0.07, (0, -0.34, 2.9 - k * 0.27), p.glow(s, 2.5) if c == state else mat.solid("#3A3A3A", 0.3), squash=(1, 0.5, 1), sub=1)
    if state:
        p.light("signal", (0, -0.5, 2.6), {"red": "#FF3A2A", "amber": "#FFB02A", "green": "#3AFF6A"}[state], 25.0, 0.08, False)


@piece("street_sign", MODERN, "floor", detail=True)
def street_sign(p, kind: str = "bus"):
    """A roadside pole with a sign: a bus-stop disc, a parking square or a street-name plate."""
    p.cyl(0.04, 2.6, (0, 0, 0), mat.surface(IRON), seg=8)
    if kind == "bus":
        p.cyl(0.26, 0.02, (0, -0.04, 2.3), mat.solid("#2D6CB0", 0.4), seg=24, rot=(90, 0, 0))
        p.cyl(0.19, 0.02, (0, -0.06, 2.3), mat.solid("#F4F4F4", 0.4), seg=24, rot=(90, 0, 0))
    elif kind == "parking":
        p.box((0.45, 0.02, 0.6), (0, -0.04, 1.95), mat.solid("#2D6CB0", 0.4), bevel=0.005)
        p.box((0.28, 0.01, 0.34), (0, -0.056, 2.1), mat.solid("#F4F4F4", 0.4), bevel=0.0)
    else:
        p.box((0.8, 0.02, 0.2), (0, -0.04, 2.35), mat.solid("#1F5A3A", 0.4), bevel=0.004)
        p.box((0.7, 0.01, 0.04), (0, -0.056, 2.43), mat.solid("#F4F4F4", 0.4), bevel=0.0)


@piece("parking_meter", MODERN, "floor")
def parking_meter(p):
    """A pay-and-display meter on a post."""
    p.cyl(0.03, 1.1, (0, 0, 0), mat.surface(IRON), seg=8)
    p.box((0.2, 0.14, 0.34), (0, 0, 1.1), mat.solid("#3A4A5A", 0.4), bevel=0.02)
    p.box((0.13, 0.01, 0.09), (0, -0.075, 1.35), p.glow("#9CE0B0", 1.0), bevel=0.0)


@piece("post_box", ANY, "floor")
def post_box(p, color="#B3322C"):
    """A pillar post box: a red cylinder with a domed cap, a letter slot and a plaque."""
    p.cyl(0.24, 1.0, (0, 0, 0.05), mat.solid(color, 0.35), seg=18)
    p.ball(0.24, (0, 0, 1.05), mat.solid(color, 0.35), squash=(1, 1, 0.5), sub=2)
    p.box((0.22, 0.02, 0.04), (0, -0.245, 0.78), mat.solid("#1E1E1E", 0.5), bevel=0.0)
    p.cyl(0.25, 0.05, (0, 0, 0), mat.solid("#1E1E1E", 0.5), seg=18)


@piece("bus_stop", MODERN, "floor", detail=True)
def bus_stop(p, length: float = 3.0):
    """A glass-sided bus shelter with a roof, a bench, a timetable panel and an ad panel that glows."""
    im = mat.surface(BM)
    for sx in (-1, 1):
        p.box((0.06, 0.06, 2.6), (sx * length / 2, 0, 0), im, bevel=0.005)
        p.box((0.06, 0.06, 2.6), (sx * length / 2, 1.2, 0), im, bevel=0.005)
    p.box((length + 0.3, 1.5, 0.08), (0, 0.6, 2.6), im, bevel=0.01)
    p.box((length, 0.03, 1.7), (0, 1.2, 0.5), mat.surface("glass"), bevel=0.0)
    for sx in (-1, 1):
        p.box((0.03, 1.2, 1.7), (sx * length / 2, 0.6, 0.5), mat.surface("glass"), bevel=0.0)
    p.box((length * 0.7, 0.4, 0.05), (0, 0.9, 0.45), W, "#8A6A44", bevel=0.005)
    p.box((length * 0.7, 0.03, 0.4), (0, 1.1, 0.5), W, "#8A6A44", bevel=0.005)
    p.box((0.9, 0.08, 1.4), (length / 2 + 0.55, 0.4, 0.5), mat.solid("#1E1F22", 0.4), bevel=0.01)
    p.box((0.8, 0.01, 1.25), (length / 2 + 0.55, 0.35, 0.58), p.glow("#CFE6FF", 1.4), bevel=0.0)
    p.box((0.5, 0.012, 0.7), (-length / 2 + 0.2, 1.16, 1.0), mat.solid("#F4F4F4", 0.6), bevel=0.0)
    p.box((0.4, 0.014, 0.06), (-length / 2 + 0.2, 1.165, 1.55), mat.solid("#2D6CB0", 0.5), bevel=0.0)
    p.light("shelter", (0, 0.6, 2.5), "#EAF2FF", 30.0, 0.2, False)


@piece("fountain", ANY, "floor")
def fountain(p, radius: float = 1.4):
    """A stone fountain: a round basin of water, a tiered pedestal, and a spray that falls back as drops."""
    p.cyl(radius, 0.55, (0, 0, 0), "castle_stone", top=radius * 0.96, seg=28)
    p.cyl(radius - 0.14, 0.02, (0, 0, 0.5), mat.solid("#2F7A8A", 0.05), seg=28)
    p.cyl(0.32, 0.6, (0, 0, 0.5), "castle_stone", top=0.24, seg=14)
    p.cyl(0.7, 0.1, (0, 0, 1.0), "castle_stone", top=0.8, seg=20)
    p.cyl(0.74, 0.02, (0, 0, 1.1), mat.solid("#2F7A8A", 0.05), seg=20)
    p.cyl(0.14, 0.5, (0, 0, 1.1), "castle_stone", top=0.1, seg=10)
    p.ball(0.14, (0, 0, 1.68), "castle_stone", sub=1)
    for k in range(8):
        a = 2 * math.pi * k / 8
        p.rod((0, 0, 1.72), (math.cos(a) * 0.5, math.sin(a) * 0.5, 1.2), 0.012, mat.solid("#CFE8F2", 0.05), seg=4)
        p.rod((math.cos(a) * 0.5, math.sin(a) * 0.5, 1.2), (math.cos(a) * 0.62, math.sin(a) * 0.62, 1.12), 0.01, mat.solid("#CFE8F2", 0.05), seg=4)
    p.top((0, 0), (radius * 1.2, radius * 1.2), 0.62, "rim")


@piece("rubble", ANY, "floor")
def rubble(p, size: float = 1.0, seed: int = 0):
    """A heap of fallen stone blocks and broken beams."""
    rnd = random.Random(seed)
    for k in range(9):
        a = rnd.uniform(0, 6.28)
        r_ = rnd.uniform(0, size * 0.5)
        s = rnd.uniform(0.12, 0.3)
        p.box((s * 1.4, s, s * 0.8), (math.cos(a) * r_, math.sin(a) * r_, 0.04 if r_ > size * 0.3 else s * 0.5), "castle_stone", rot=(rnd.uniform(-12, 12), rnd.uniform(-12, 12), rnd.uniform(0, 180)), tint=rnd.choice(["#8A8680", "#9A948A", "#7A766E"]), bevel=0.02)
    p.rod((-size * 0.4, 0.1, 0.18), (size * 0.5, -0.1, 0.4), 0.04, DW, seg=5)


@piece("bunting", ANY, "floor", detail=True, hang=True)
def bunting(p, length: float = 8.0, sag: float = 0.5, seed: int = 0):
    """A string of small triangular flags hung in a swag between two points; origin at the left end, hangs from z = 0 (use hang=True mounting)."""
    rnd = random.Random(seed)
    cols = ["#B3322C", "#F2E27A", "#2D6CB0", "#F4F4F4", "#3F8F5A"]
    n = int(length / 0.45)
    prev = None
    for k in range(n + 1):
        u = k / n
        pt = (-length / 2 + u * length, 0, -sag * math.sin(math.pi * u))
        if prev:
            p.rod(prev, pt, 0.004, "rope", seg=3)
        if k < n:
            u2 = (k + 0.5) / n
            zc = -sag * math.sin(math.pi * u2)
            p.profile([(-length / 2 + u2 * length - 0.13, zc), (-length / 2 + u2 * length + 0.13, zc), (-length / 2 + u2 * length, zc - 0.3)], -0.004, 0.004, mat.solid(cols[k % len(cols)], 0.85), bevel=0.0)
        prev = pt


@piece("tree_dead", ANY, "floor")
def tree_dead(p, height: float = 5.0, seed: int = 0):
    """A blasted, bare tree: a split trunk and a few snapped limbs."""
    rnd = random.Random(seed)
    p.cyl(0.28, height * 0.7, (0, 0, 0.04), "bark", tint="#4A4038", top=0.12, seg=8, rot=(rnd.uniform(-4, 4), rnd.uniform(-4, 4), 0))
    for k in range(5):
        z = height * rnd.uniform(0.3, 0.68)
        a = rnd.uniform(0, 6.28)
        L = rnd.uniform(0.8, 1.8)
        p.rod((0, 0, z), (math.cos(a) * L, math.sin(a) * L, z + L * rnd.uniform(0.3, 0.9)), 0.07, "bark", seg=5)
    p.rod((0, 0, height * 0.7), (0.3, 0.1, height), 0.09, "bark", seg=5)


@piece("wall_shelf", ANY, "wall", mount_z=1.5)
def wall_shelf(p, length: float = 1.0, depth: float = 0.2, tint=None):
    """A single plank shelf on two brackets, its top declared so small things can be stood on it (dress.Dresser.shelves does that)."""
    p.box((length, depth, 0.035), (0, -depth / 2, 0.0), W, tint or "#7A583A", bevel=0.006)
    for sx in (-1, 1):
        p.box((0.03, depth * 0.85, 0.03), (sx * (length / 2 - 0.1), -depth * 0.45, -0.05), mat.surface(IRON), bevel=0.003)
        p.box((0.025, 0.02, 0.1), (sx * (length / 2 - 0.1), -0.01, -0.1), mat.surface(IRON), bevel=0.003)
    p.top((0, -depth / 2), (length - 0.04, depth - 0.02), 0.035, "shelf")
