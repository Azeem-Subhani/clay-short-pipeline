"""stagekit.dress - dressing recipes: turn an empty room or open place into a believable, lived-in one.

    R = arch.room((12, 20, 8), ...)
    inv = dress.room(R, "throne_room", marks=MARK, density=1.0, seed=3, keep_clear=0.9)
    inv = dress.exterior(dict(lo=(-30, -6), hi=(30, 22)), "market_street", marks=MARK, seed=2)

A recipe fills FOUR depth layers, so a wide shot always has depth to read:
  foreground  occluders near the camera side: a column edge, a hanging banner, a table corner, a plant
  mid         furniture AROUND (never on) the acting marks: the working set
  background  wall dressing and furniture against the far and side walls
  beyond      what is seen through windows and doors: vistas (arch.vista), skylines, the layer behind the set
plus practical lights (real sources with a visible emissive part), small props placed on MEASURED table, shelf and counter tops,
wall dressing at sensible heights, floor detail (rugs, runners, scattered straw, leaves or paper), atmosphere (dust motes in the
window light, or haze) and readable details (signs, banners with a crest, notice papers, tapestries, a clock).

Rules every recipe keeps: deterministic for a seed; nothing overlaps (oriented-rectangle tests on the floor, interval tests on
walls and on table tops); nothing floats (floor pieces stand on z=0 or on a declared top; wall pieces hang on a wall face);
the acting marks stay clear (keep_clear metres round each), and so does the floor in front of every door.
A recipe returns an inventory: {"types": {name: count}, "objects": n, "layers": {...}, "practicals": n, "atmosphere": [...], "details": n}.
Themes and their eras: see THEMES (period tags agree with config/cast.json > eras).
"""
from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from . import arch, build, core, furnish, lights, mat
from .arch import Parts

THEMES: dict = {}

# architecture pieces that recipes place like furniture (footprint rules: origin on the floor at the back-centre)
for _n, _fn, _era, _src in (("market_stall", arch.market_stall, ["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], False),
                            ("well", arch.well, ["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], False),
                            ("lamp_post", arch.lamp_post, ["any"], True), ("low_wall", arch.low_wall, ["any"], False), ("fence", arch.fence, ["any"], False)):
    furnish.REGISTRY[_n] = dict(fn=_fn, era=_era, kind="floor", mount_z=None, detail=False, source=_src, hang=False, tags=["arch"])


def hall_bays(room_, centre_y: float = 0.0):
    """The y positions of the column rows of a hall (throne_room): windows go between them, at the midpoints.
    room_ is a built arch.Room, or just the (w, d, h) size when the windows are being planned before the room exists."""
    if hasattr(room_, "lo"):
        d = room_.hi[1] - room_.lo[1]
        y0 = room_.lo[1] + 3.2
    else:
        d = room_[1]
        y0 = centre_y - d / 2 + 3.2
    n = int((d - 8) / 3.6) + 1
    return [y0 + (d - 9.0) * i / max(1, n - 1) for i in range(max(2, n))]


def theme(name: str, era, kind: str = "room"):
    def deco(fn):
        THEMES[name] = dict(fn=fn, era=era, kind=kind)
        return fn
    return deco


# ----------------------------------------------------------------------------- geometry of placement
def _rect_corners(r):
    cx, cy, hw, hd, rot = r
    c, s = math.cos(rot), math.sin(rot)
    return [(cx + c * x - s * y, cy + s * x + c * y) for x, y in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]


def rects_overlap(a, b, margin: float = 0.0) -> bool:
    """Separating-axis test of two oriented rectangles (cx, cy, half_w, half_d, rot_radians), grown by margin."""
    a = (a[0], a[1], a[2] + margin, a[3] + margin, a[4])
    ca, cb = _rect_corners(a), _rect_corners(b)
    for rect in (a, b):
        c, s = math.cos(rect[4]), math.sin(rect[4])
        for ax in ((c, s), (-s, c)):
            pa = [p[0] * ax[0] + p[1] * ax[1] for p in ca]
            pb = [p[0] * ax[0] + p[1] * ax[1] for p in cb]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return False
    return True


def footprint_rect(ob, margin: float = 0.0):
    """The floor rectangle of a built piece: centre, half sizes, rotation (the origin is the back-centre of the piece)."""
    w, d, h = furnish.footprint(ob)
    rot = ob.rotation_euler.z
    ox, oy = ob.location.x, ob.location.y
    cx, cy = ox + math.sin(rot) * d / 2, oy - math.cos(rot) * d / 2
    return (cx, cy, w / 2 + margin, d / 2 + margin, rot)


class Dresser:
    """The state of one dressing job: what is placed where, what is free, and what was made."""

    def __init__(self, area, themename: str, marks=None, density: float = 1.0, seed: int = 0, keep_clear: float = 0.9, cam=None, room_=None):
        self.R = room_
        self.theme = themename
        self.rnd = random.Random(seed)
        self.seed = seed
        self.density = density
        self.cam = Vector(cam) if cam is not None else None
        if room_ is not None:
            self.lo, self.hi = (room_.lo[0] + 0.0, room_.lo[1] + 0.0), (room_.hi[0], room_.hi[1])
            self.h = room_.h
            self.at = room_.at
        else:
            self.lo, self.hi = tuple(area["lo"]), tuple(area["hi"])
            self.h = None
            self.at = ((self.lo[0] + self.hi[0]) / 2, (self.lo[1] + self.hi[1]) / 2)
        self.circles: list = []                        # (x, y, r): keep clear of acting marks and door fronts
        for k, v in (marks or {}).items():
            self.circles.append((float(v[0]), float(v[1]), keep_clear))
        self.rects: list = []                          # floor rectangles of placed pieces
        self.walls = {w: [] for w in "NSEW"}          # (a0, a1, z0, z1) along-wall occupancy
        self.tops_used: dict = {}                      # parent name -> list of (x, y, r) on its top
        self.made: list = []                           # every root created
        self.rejected = 0
        self.reject_log: list = []                       # (piece, why): what could not be placed, for the recipe author
        self.atmos: list = []
        self.floor_details = 0
        if room_ is not None:
            for oid, hd in room_.openings.items():
                W = hd["wall"]
                along = self._along(W, hd["centre"])
                self.walls[W].append((along - hd["w"] / 2 - 0.25, along + hd["w"] / 2 + 0.25, hd["z0"] - 0.15, hd["z0"] + hd["h"] + 0.2))
                if hd["kind"] == "door":
                    p = hd["inner_centre"] + hd["normal"] * 1.0
                    self.circles.append((p.x, p.y, 0.95))

    # -- helpers
    def n(self, base: float, lo: int = 0) -> int:
        """A count scaled by the density and never below lo."""
        return max(lo, int(round(base * self.density)))

    def _along(self, W, p):
        cx, cy = self.at
        return (p.x - cx) if W in "NS" else (p.y - cy)

    def wall_pos(self, W: str, along: float, inset: float = 0.0):
        x0, y0, x1, y1 = self.lo[0], self.lo[1], self.hi[0], self.hi[1]
        cx, cy = self.at
        return {"N": (cx + along, y1 - inset), "S": (cx + along, y0 + inset), "E": (x1 - inset, cy + along), "W": (x0 + inset, cy + along)}[W]

    def wall_len(self, W: str) -> float:
        return (self.hi[0] - self.lo[0]) if W in "NS" else (self.hi[1] - self.lo[1])

    def inside(self, rect, pad: float = 0.0) -> bool:
        return all(self.lo[0] + pad <= x <= self.hi[0] - pad and self.lo[1] + pad <= y <= self.hi[1] - pad for x, y in _rect_corners(rect))

    def clear_of_marks(self, rect, extra: float = 0.0) -> bool:
        cx, cy, hw, hd, rot = rect
        for mx, my, r in self.circles:
            # distance from the circle centre to the rectangle
            c, s = math.cos(-rot), math.sin(-rot)
            lx, ly = (mx - cx) * c - (my - cy) * s, (mx - cx) * s + (my - cy) * c
            dx, dy = max(abs(lx) - hw, 0.0), max(abs(ly) - hd, 0.0)
            if math.hypot(dx, dy) < r + extra:
                return False
        return True

    def free(self, rect, margin: float = 0.08, marks: bool = True) -> bool:
        if not self.inside(rect):
            return False
        if marks and not self.clear_of_marks(rect):
            return False
        return not any(rects_overlap(rect, r, margin) for r in self.rects)

    def _wall_free(self, W, a0, a1, z0, z1) -> bool:
        return not any(a0 < b1 and a1 > b0 and z0 < y1 and z1 > y0 for b0, b1, y0, y1 in self.walls[W])

    def _record(self, ob, layer: str, rect=None):
        ob["sk_layer"] = layer
        self.made.append(ob)
        if rect is not None and furnish.footprint(ob)[2] > 0.04:
            self.rects.append(rect)
        return ob

    # -- floor
    def floor(self, name, x, y, rot: float = 0.0, layer: str = "mid", z: float = 0.0, margin: float = 0.08, marks: bool = True, flat: bool = False, check: bool = True, **kw):
        """Place a free-standing piece so that its footprint CENTRE is at (x, y). Returns it, or None if the spot is taken or out of bounds.
        check=False skips the overlap test (for pieces standing on a raised dais you have already cleared)."""
        fn = furnish.REGISTRY[name]["fn"] if name in furnish.REGISTRY else name
        ob = fn(at=(0, 0, z), rot_z=rot, **kw)
        w, d, h = furnish.footprint(ob)
        r = math.radians(rot)
        ob.location = (x - math.sin(r) * d / 2, y + math.cos(r) * d / 2, z)
        rect = footprint_rect(ob)
        if not check:
            return self._record(ob, layer, None)
        if (not flat) and not self.free(rect, margin, marks):
            self.rejected += 1
            self.reject_log.append((name, f"floor ({x:.1f}, {y:.1f})"))
            self._drop(ob)
            return None
        if flat and not self.inside(rect):
            self.rejected += 1
            self._drop(ob)
            return None
        return self._record(ob, layer, None if flat else rect)

    def _drop(self, ob):
        for o in [*ob.children_recursive, ob]:
            if o.type == "LIGHT":
                bpy.data.objects.remove(o, do_unlink=True)
            else:
                bpy.data.objects.remove(o, do_unlink=True)

    def against(self, name, W: str, along: float, layer: str = "background", z: float = 0.0, gap: float = 0.02, margin: float = 0.06, **kw):
        """Stand a piece with its back on wall W at an offset along the wall (like opening `at`). It faces into the room."""
        fn = furnish.REGISTRY[name]["fn"] if name in furnish.REGISTRY else name
        rot = arch.WALL_ROT[W]
        ob = fn(at=(0, 0, z), rot_z=rot, **kw)
        w, d, h = furnish.footprint(ob)
        x, y = self.wall_pos(W, along, gap)
        ob.location = (x, y, z)
        a0, a1 = along - w / 2 - 0.02, along + w / 2 + 0.02
        rect = footprint_rect(ob)
        if not self._wall_free(W, a0, a1, z, z + h) or not self.free(rect, margin):
            self.rejected += 1
            self.reject_log.append((name, f"wall {W} {along:+.1f}"))
            self._drop(ob)
            return None
        self.walls[W].append((a0, a1, z, z + h))
        arch.tag_wall(ob, self.R.name, W) if self.R is not None else None
        return self._record(ob, layer, rect)

    def hang(self, name, W: str, along: float, z=None, layer: str = "background", **kw):
        """Hang a wall piece (painting, banner, tapestry, sconce, clock, shield, sign) on wall W at height z (default: the piece's usual)."""
        meta = furnish.REGISTRY[name]
        z = meta["mount_z"] if z is None else z
        z = 1.5 if z is None else z
        ob = meta["fn"](at=(0, 0, z), rot_z=arch.WALL_ROT[W], **kw)
        w, d, h = furnish.footprint(ob)
        zlo = z + float(ob.get("sk_zlo", 0.0)) if name != "banner" else z - h
        zhi = zlo + h
        a0, a1 = along - w / 2 - 0.05, along + w / 2 + 0.05
        if self.h is not None and zhi > self.h + 0.05:
            self.rejected += 1
            self._drop(ob)
            return None
        if not self._wall_free(W, a0, a1, zlo, zhi):
            self.rejected += 1
            self.reject_log.append((name, f"hang {W} {along:+.1f} z{z:.1f}"))
            self._drop(ob)
            return None
        x, y = self.wall_pos(W, along, 0.0)
        ob.location = (x, y, z)
        self.walls[W].append((a0, a1, zlo, zhi))
        arch.tag_wall(ob, self.R.name, W) if self.R is not None else None
        return self._record(ob, layer)

    def on_column(self, x: float, y: float, face: float, radius: float, z: float, name: str, layer: str = "mid", **kw):
        """Hang a wall piece (torch, sconce, shield) on the side of a column facing the nave: face = +1 faces +X, -1 faces -X."""
        rot = 90.0 if face > 0 else -90.0                       # the piece faces +X when turned +90 degrees
        ob = furnish.REGISTRY[name]["fn"](at=(x + face * radius, y, z), rot_z=rot, **kw)
        return self._record(ob, layer)

    def ground(self, surface: str = "cobblestone", z: float = -0.05, size: float = 400.0, tint=None):
        """A huge flat ground just under the street or plaza, so nothing past the edge of the built part looks out onto the void."""
        p = Parts("ground_apron", "SET", "ground", kind="shell")
        p.box((size, size, 0.2), (self.at[0], self.at[1], 0.0), surface, tint, bevel=0.0)
        ob = p.build(at=(0, 0, z - 0.2), recentre=False)
        self.made.append(ob)
        return ob

    def ceiling_piece(self, name, x, y, layer: str = "mid", **kw):
        """A piece hanging from the ceiling (chandelier, panel light): origin on the ceiling plane at (x, y)."""
        ob = furnish.REGISTRY[name]["fn"](at=(x, y, self.h), rot_z=0.0, **kw)
        arch.tag_wall(ob, self.R.name, "C")
        # the origin of these pieces is their centre, not their back: centre them
        w, d, h = furnish.footprint(ob)
        ob.location = (x, y + d / 2, self.h)
        return self._record(ob, layer)

    # -- surfaces
    def top(self, parent, name, k: int = 0, layer=None, margin: float = 0.06, tries: int = 14, **kw):
        """Stand a small piece on one of a parent's declared tops, away from what is already there. Returns it or None."""
        tl = furnish.tops(parent)
        if not tl:
            return None
        c0, zt, tw, td, rotz, label = tl[min(k, len(tl) - 1)] if k >= 0 else self.rnd.choice(tl)
        fn = furnish.REGISTRY[name]["fn"] if name in furnish.REGISTRY else name
        ob = fn(at=(0, 0, zt), rot_z=0.0, **kw)
        w, d, h = furnish.footprint(ob)
        used = self.tops_used.setdefault(parent.name + str(id(parent)), [])
        for _ in range(tries):
            lx = self.rnd.uniform(-tw / 2 + w / 2 + margin, tw / 2 - w / 2 - margin) if tw > w + 2 * margin else 0.0
            ly = self.rnd.uniform(-td / 2 + d / 2 + margin, td / 2 - d / 2 - margin) if td > d + 2 * margin else 0.0
            if tw < w - 0.05 or td < d - 0.05:
                break
            jitter = 0.0 if name in ("monitor_keyboard", "laptop", "office_phone") else math.radians(self.rnd.uniform(-25, 25))
            cand = (lx, ly, w / 2, d / 2, jitter)
            if any(rects_overlap(cand, u, 0.025) for u in used):
                continue
            if any(abs(px) > tw / 2 - 0.01 or abs(py) > td / 2 - 0.01 for px, py in _rect_corners(cand)):          # a turned piece must still sit inside the top
                continue
            used.append(cand)
            c, s = math.cos(rotz), math.sin(rotz)
            wx, wy = c0.x + c * lx - s * ly, c0.y + s * lx + c * ly
            rot = rotz + jitter
            ob.rotation_euler.z = rot
            ob.location = (wx - math.sin(rot) * d / 2, wy + math.cos(rot) * d / 2, zt)
            ob["sk_on"] = parent.name
            return self._record(ob, layer or parent.get("sk_layer", "mid"))
        self.rejected += 1
        self._drop(ob)
        return None

    def clutter(self, parent, names, n: int = 3, k: int = 0, **kw):
        """Scatter n small pieces (names: a list, picked at random) over a parent's top."""
        out = []
        for i in range(self.n(n)):
            nm = self.rnd.choice(names)
            o = self.top(parent, nm, k=k, **kw)
            if o:
                out.append(o)
        return out

    # -- repeated things
    def against_any(self, name, W: str, near=None, step: float = 0.45, layer: str = "background", **kw):
        """Stand a piece against wall W at the first free spot, scanning outward from `near` (an offset along the wall; default: a
        random start). Returns the piece or None if the wall has no room for it."""
        L = self.wall_len(W)
        start = self.rnd.uniform(-L / 2 + 1.0, L / 2 - 1.0) if near is None else near
        offs = sorted([a * step for a in range(int(-L / step / 2), int(L / step / 2) + 1)], key=lambda a: abs(a - start))
        for a in offs:
            n0, l0 = self.rejected, len(self.reject_log)
            o = self.against(name, W, a, layer=layer, **kw)
            self.rejected, self.reject_log = n0, self.reject_log[:l0]       # a scan is not a failure: only no spot at all is
            if o:
                return o
        self.rejected += 1
        self.reject_log.append((name, f"no free spot on wall {W}"))
        return None

    def run(self, name, W: str, start: float, stop: float, step: float, layer: str = "background", jitter: float = 0.0, **kw):
        """A piece placed along a wall every `step` metres between start and stop (offsets along the wall); skips taken spots."""
        out = []
        a = start
        while a <= stop + 1e-6:
            o = self.against(name, W, a + self.rnd.uniform(-jitter, jitter), layer=layer, **kw)
            if o:
                out.append(o)
            a += step
        return out

    def free_wall_spots(self, W: str, width: float, z0: float, z1: float, step: float = 0.5):
        """Offsets along wall W where a piece `width` wide fits between z0 and z1 (for hangings)."""
        L = self.wall_len(W)
        out = []
        a = -L / 2 + width / 2 + 0.3
        while a < L / 2 - width / 2 - 0.3:
            if self._wall_free(W, a - width / 2, a + width / 2, z0, z1):
                out.append(a)
            a += step
        return out

    def floor_detail(self, kind: str, n: int, region=None, name: str = "floor_detail"):
        """Scattered small things lying on the floor, one merged mesh: straw, leaves, papers, petals. Not on the marks."""
        region = region or (self.lo[0] + 0.3, self.lo[1] + 0.3, self.hi[0] - 0.3, self.hi[1] - 0.3)
        p = Parts(f"{name}_{kind}", "SET", "floor_detail", kind="prop")
        cm = {"straw": ["#C9AE5E", "#B8984A", "#D8C27A"], "leaves": ["#8A5A2A", "#B07A2E", "#6A7A2E"], "papers": ["#F4F1E8", "#EDE6D6"], "petals": ["#E8A0B8", "#F4E6EA"]}[kind]
        mats = [mat.solid(c, 0.9) for c in cm]
        placed = 0
        for _ in range(n * 4):
            if placed >= n:
                break
            x, y = self.rnd.uniform(region[0], region[2]), self.rnd.uniform(region[1], region[3])
            if any(math.hypot(x - mx, y - my) < r * 0.8 for mx, my, r in self.circles):
                continue
            m = self.rnd.choice(mats)
            a = self.rnd.uniform(0, 360)
            if kind == "straw":
                p.box((self.rnd.uniform(0.15, 0.3), 0.008, 0.006), (x, y, 0.0), m, rot=(0, 0, a), bevel=0.0)
            elif kind == "papers":
                p.box((0.21, 0.297, 0.002), (x, y, 0.0), m, rot=(0, 0, a), bevel=0.0)
            else:
                p.box((0.06, 0.04, 0.004), (x, y, 0.0), m, rot=(0, 0, a), bevel=0.0)
            placed += 1
        if not placed:
            return None
        ob = p.build(at=(0, 0, 0), recentre=False)
        ob["sk_layer"] = "mid"
        ob["sk_floor_detail"] = kind
        self.floor_details += 1
        self.made.append(ob)
        return ob

    # -- atmosphere
    def dust(self):
        """Dust motes in each window's light (rooms) or over the place (open sets)."""
        k = 0
        if self.R is not None:
            for oid, hd in self.R.openings.items():
                if hd["kind"] != "window":
                    continue
                c, nrm = hd["inner_centre"], hd["normal"]
                a, b = c + nrm * 0.3, c + nrm * 6.0 + Vector((0, 0, -2.5))
                lo = [min(a[i], b[i]) - (0.6 if i < 2 else 0.0) for i in range(3)]
                hi = [max(a[i], b[i]) + (0.6 if i < 2 else 0.0) for i in range(3)]
                lo[2], hi[2] = max(0.3, lo[2]), min(self.h - 0.3, hi[2] + 1.0)
                lights.dust(lo, hi, 110, size=0.009, strength=0.9, seed=self.seed + k)
                k += 1
            if k == 0 and self.h:
                lights.dust((self.lo[0] + 1, self.lo[1] + 1, 0.5), (self.hi[0] - 1, self.hi[1] - 1, self.h - 0.4), 200, size=0.009, strength=0.9, seed=self.seed)
                k = 1
        else:
            lights.dust((self.lo[0], self.lo[1], 0.5), (self.hi[0], self.hi[1], 6.0), 160, size=0.014, strength=0.7, seed=self.seed)
            k = 1
        if k:
            self.atmos.append("dust motes")

    # -- the inventory
    def inventory(self) -> dict:
        types: dict = {}
        layers = {"foreground": 0, "mid": 0, "background": 0, "beyond": 0}
        details = 0
        pr = 0
        for ob in self.made:
            t = ob.get("sk_type")
            if t:
                types[t] = types.get(t, 0) + 1
            layers[{"fg": "foreground", "foreground": "foreground", "mid": "mid", "background": "background", "bg": "background", "beyond": "beyond"}.get(ob.get("sk_layer", "mid"), "mid")] += 1
            if ob.get("sk_detail"):
                details += 1
            pr += int(ob.get("sk_nlights", 0))
        if self.R is not None:
            v = getattr(self.R, "vistas", {})
            layers["beyond"] += len(v)
        return {"theme": self.theme, "types": types, "objects": len(self.made), "layers": layers, "practicals": pr, "atmosphere": list(self.atmos),
                "details": details, "floor_detail": self.floor_details, "rejected": self.rejected,
                "rejected_names": [f"{n}@{w}" for n, w in self.reject_log[:80]]}


# ----------------------------------------------------------------------------- entry points
def room(room_, theme_name: str, marks=None, density: float = 1.0, seed: int = 0, keep_clear: float = 0.9, cam=None, reserve=(), autofill_: bool = True) -> dict:
    """Dress an enclosed room (arch.room) with a theme. cam: where the wide shot stands (default: the -Y side).
    reserve: floor rectangles (x0, y0, x1, y1) the recipe must leave alone (a glass meeting room you built yourself)."""
    if theme_name not in THEMES or THEMES[theme_name]["kind"] != "room":
        raise KeyError(f"no room theme '{theme_name}'. Room themes: {', '.join(k for k, v in THEMES.items() if v['kind'] == 'room')}")
    D = Dresser(None, theme_name, marks, density, seed, keep_clear, cam, room_)
    for (rx0, ry0, rx1, ry1) in reserve:
        D.rects.append(((rx0 + rx1) / 2, (ry0 + ry1) / 2, (rx1 - rx0) / 2, (ry1 - ry0) / 2, 0.0))
    THEMES[theme_name]["fn"](D)
    if autofill_:
        autofill(D, POOLS.get(theme_name, {}))
    D.dust()
    inv = D.inventory()
    room_.inventory = inv
    return inv


def exterior(area, theme_name: str, marks=None, density: float = 1.0, seed: int = 0, keep_clear: float = 0.9, cam=None, autofill_: bool = True) -> dict:
    """Dress an open place. area = dict(lo=(x0, y0), hi=(x1, y1)) in metres: the walkable stage; the recipe builds the street or ground
    it needs, the buildings and props around it, and the skyline beyond."""
    if theme_name not in THEMES or THEMES[theme_name]["kind"] != "exterior":
        raise KeyError(f"no exterior theme '{theme_name}'. Exterior themes: {', '.join(k for k, v in THEMES.items() if v['kind'] == 'exterior')}")
    D = Dresser(area, theme_name, marks, density, seed, keep_clear, cam, None)
    THEMES[theme_name]["fn"](D)
    if autofill_:
        autofill(D, POOLS.get(theme_name, {}), floor=0.1)
    D.dust()
    return D.inventory()


POOLS = {
    "throne_room": dict(top=["goblet", "tankard", "table_candle", "scroll", "book_stack", "papers_stack", "bottle", "crockery_set"], floor=["barrel", "sack", "crate", "chest", "stool"],
                        wall=["shield_wall", "banner", "tapestry"]),
    "great_hall": dict(top=["goblet", "tankard", "table_candle", "bread_basket", "bottle", "crockery_set", "jug"], floor=["barrel", "sack", "crate", "chest", "stool", "bench"], wall=["shield_wall", "banner", "painting_framed"]),
    "castle_kitchen": dict(top=["pots_and_pans", "bread_basket", "fruit_crate", "crockery_set", "market_goods", "mugs", "jug", "basket", "bottle", "cloth_bolts"], floor=["barrel", "sack", "crate", "basket", "stool"],
                           wall=["shelf_jars", "hanging_sign", "wall_sconce"]),
    "tavern": dict(top=["tankard", "bottle", "jug", "table_candle", "crockery_set", "bread_basket", "mugs"], floor=["barrel", "stool", "crate", "sack", "potted_plant"], wall=["shelf_jars", "painting_framed", "notice_board", "wall_sconce"]),
    "peasant_cottage": dict(top=["crockery_set", "jug", "basket", "bread_basket", "mugs", "table_candle", "bottle"], floor=["sack", "basket", "crate", "stool", "broom"], wall=["shelf_jars", "painting_framed", "wall_sconce"]),
    "office_open_plan": dict(top=["papers_stack", "mugs", "book_stack", "laptop", "office_phone", "vase_flowers"], floor=["potted_plant", "bin", "filing_cabinet"], wall=["poster", "painting_framed", "notice_board"]),
    "office_private": dict(top=["papers_stack", "mugs", "book_stack", "laptop", "vase_flowers", "office_phone", "desk_lamp"], floor=["potted_plant", "bin", "filing_cabinet", "chair_dining"], wall=["painting_framed", "poster", "wall_clock", "notice_board"]),
    "home_living_room": dict(top=["vase_flowers", "mugs", "book_stack", "papers_stack", "table_candle"], floor=["potted_plant", "floor_lamp", "stool", "basket"], wall=["painting_framed", "poster", "wall_sconce", "wall_clock"]),
    "home_kitchen": dict(top=["mugs", "kettle", "bread_basket", "fruit_crate", "crockery_set", "pots_and_pans", "jug", "vase_flowers"], floor=["bin", "potted_plant", "stool", "basket"], wall=["shelf_jars", "painting_framed", "poster", "wall_clock"]),
    "shop_interior": dict(top=["basket", "market_goods", "bread_basket", "jug", "scroll", "book_stack", "cloth_bolts", "fruit_crate", "bottle"], floor=["barrel", "sack", "crate", "basket", "potted_plant"],
                          wall=["shelf_jars", "hanging_sign", "poster", "painting_framed"]),
    "market_street": dict(floor=["barrel", "crate", "sack", "hay_bale", "basket", "potted_plant"]),
    "village_square": dict(floor=["barrel", "crate", "sack", "hay_bale", "bench", "potted_plant"]),
    "army_camp": dict(floor=["barrel", "crate", "sack", "hay_bale", "stakes", "shield_pile", "arrow_bundle"]),
    "battlefield": dict(floor=["shield_pile", "arrow_bundle", "stakes", "crate", "barrel", "hay_bale"]),
    "city_street": dict(floor=["bin", "potted_plant", "bench", "hydrant"]),
}
WALL_DEFAULTS = {"painting_framed": dict(width=0.8, height=0.6), "poster": dict(width=0.5, height=0.7), "shield_wall": dict(), "shelf_jars": dict(length=1.1), "wall_clock": dict(), "hanging_sign": dict(), "notice_board": dict(width=0.9, height=0.7),
                 "wall_sconce": dict(), "banner": dict(size=(0.8, 2.2)), "tapestry": dict(width=1.4, height=2.0)}


def autofill(D, pool: dict, tops: int = 5, walls: int = 3, floor: float = 0.28):
    """A last pass that lifts a recipe to the density of a lived-in place: small things on every declared top that still has room,
    pictures and shelves on the free stretches of each wall, and loose things about the floor in proportion to its area.
    Everything is still placed by the same rules (free spot, on a surface, clear of the marks)."""
    rnd = D.rnd
    if pool.get("top"):
        for ob in [o for o in D.made if o.get("sk_tops") and o.get("sk_type") not in ("desk_office", "monitor_keyboard")]:
            for _ in range(D.n(tops)):
                D.top(ob, rnd.choice(pool["top"]), k=-1, tries=6)
    if D.R is not None and pool.get("wall"):
        for W_ in "NSEW":
            for _ in range(D.n(walls)):
                nm = rnd.choice(pool["wall"])
                meta = furnish.REGISTRY[nm]
                z = meta["mount_z"] if meta["mount_z"] is not None else 1.5
                if nm == "banner" and D.h:
                    z = D.h - 0.9
                kw = dict(WALL_DEFAULTS.get(nm, {}))
                if nm in ("painting_framed", "poster", "tapestry", "notice_board", "shelf_jars"):
                    kw["seed"] = rnd.randint(0, 99)
                spots = D.free_wall_spots(W_, 1.0, z, z + 1.0, 0.4)
                if spots:
                    D.hang(nm, W_, rnd.choice(spots), z=z, layer="background", **kw)
    area = (D.hi[0] - D.lo[0]) * (D.hi[1] - D.lo[1])
    names = pool.get("floor", [])
    for _ in range(int(area * floor * D.density) if names else 0):
        nm = rnd.choice(names)
        x, y = rnd.uniform(D.lo[0] + 0.5, D.hi[0] - 0.5), rnd.uniform(D.lo[1] + 0.5, D.hi[1] - 0.5)
        near = y < D.lo[1] + 0.28 * (D.hi[1] - D.lo[1])
        D.floor(nm, x, y, rnd.choice([0, 90, 180, 270]) + rnd.uniform(-10, 10), "foreground" if near else "mid", margin=0.25)


# ============================================================================= shared compositions
def _desk_cluster(D, x, y, rot, chair_color="#2B2F3A", layer="mid", lamp=False):
    d = D.floor("desk_office", x, y, rot, layer, margin=0.04)
    if d is None:
        return None
    r = math.radians(rot)
    ay = (-math.sin(r), math.cos(r))
    D.floor("chair_office", x - ay[0] * 0.95, y - ay[1] * 0.95, rot + 180, layer, margin=0.0, color=chair_color)
    D.top(d, "monitor_keyboard", k=1, layer=layer)
    for nm, pr in (("papers_stack", 0.8), ("mugs", 0.75), ("office_phone", 0.7), ("laptop", 0.35), ("book_stack", 0.4)):
        if D.rnd.random() < pr:
            D.top(d, nm, k=1, layer=layer)
    if lamp:
        D.top(d, "desk_lamp", k=1, layer=layer)
    return d


def _sconces(D, walls, z=2.2, step=4.5, kind="candle", margin=2.0, layer="background"):
    out = []
    for W in walls:
        L = D.wall_len(W)
        a = -L / 2 + margin
        while a <= L / 2 - margin + 1e-6:
            o = D.hang("wall_sconce", W, a, z=z, layer=layer, kind=kind)
            if o:
                out.append(o)
            a += step
    return out


# ============================================================================= ROOM THEMES
@theme("throne_room", ["medieval", "renaissance", "fantasy"])
def throne_room(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    dw = min(6.0, w * 0.5)
    # ---- background: the dais and throne against the north wall, flanked by banners, braziers and candelabra
    dais = arch.dais((dw, 3.2), 0.45, at=(cx, y1, 0), surface="marble", steps=3)
    dais["sk_layer"] = "background"
    D.made.append(dais)
    D.rects.append((cx, y1 - 1.6, dw / 2, 1.6, 0.0))
    D.rects.append((cx, y1 - 3.2 - 0.4, dw / 2, 0.4, 0.0))
    D.walls["N"].append((-dw / 2, dw / 2, 0, 0.45))
    th = furnish.throne(at=(cx, y1 - 0.5, 0.45), rot_z=0)
    D._record(th, "background", None)
    D.walls["N"].append((-0.9, 0.9, 0.45, 3.2))
    for sx in (-1, 1):
        D.floor("brazier", cx + sx * 2.5, y1 - 1.5, 0, "background", z=0.45, check=False)
        D.floor("candelabra", cx + sx * 1.7, y1 - 2.4, 0, "background", z=0.45, check=False)
        D.hang("banner", "N", sx * 3.9, z=h - 1.3, layer="background", size=(1.1, 3.0), emblem="lion")
        D.against("chest", "N", sx * (dw / 2 + 1.3), "background")
        D.hang("shield_wall", "N", sx * (dw / 2 + 1.3), z=3.0, layer="background", color="#2D4A6B" if sx < 0 else "#A3231F")
    D.hang("tapestry", "N", 0.0, z=3.6, layer="background", width=2.0, height=min(3.0, h - 4.2), base="#5E2A2F")
    # ---- mid: the long red runner from the steps to the doors
    run_len = d - 5.2
    rn = arch.carpet_runner(run_len, 2.2, at=(cx, y1 - 4.1 - run_len / 2, 0))
    rn["sk_layer"] = "mid"
    D.made.append(rn)
    D.rects.append((cx, y1 - 4.1 - run_len / 2, 1.25, run_len / 2, 0.0))       # the runner is the walking lane: nothing stands on it
    # ---- two rows of fluted columns with pilasters on the walls between the windows
    ys = hall_bays(R)
    for i, yy in enumerate(ys):
        for sx in (-1, 1):
            xx = cx + sx * (w / 2 - 2.6)
            c = arch.column("fluted" if i % 2 == 0 else "round", h - 0.4, 0.38, at=(xx, yy, 0), surface="castle_stone", rot_z=0)
            c["sk_layer"] = "foreground" if yy < y0 + 4.5 else "mid"
            D.made.append(c)
            D.rects.append((xx, yy, 0.55, 0.55, 0.0))
            D.on_column(xx, yy, -sx, 0.5, 2.6, "torch_wall")
            D.on_column(xx, yy, -sx, 0.46, h - 1.7, "banner", layer="foreground" if yy < y0 + 4.5 else "mid", size=(0.55, 2.1), color=D.rnd.choice(["#A3231F", "#2D4A6B", "#3F5F3A"]), emblem=D.rnd.choice(["lion", "sun", "star", "tree"]))
            wl = "E" if sx > 0 else "W"
            al = yy - cy
            if D._wall_free(wl, al - 0.4, al + 0.4, 0, h):
                pl = arch.pilaster(h - 0.4, 0.55, at=(x1 if sx > 0 else x0, yy, 0), rot_z=arch.WALL_ROT[wl], surface="castle_stone", proud=0.2)
                arch.tag_wall(pl, R.name, wl)
                pl["sk_layer"] = "background"
                D.made.append(pl)
                D.walls[wl].append((al - 0.4, al + 0.4, 0, h))
    mids = [(a + b) / 2 for a, b in zip(ys, ys[1:])]
    # ---- chandeliers down the nave, between the column rows
    for yy in mids + [ys[0] - 1.8]:
        D.ceiling_piece("chandelier", cx, yy, "mid", radius=0.85, drop=min(2.0, h * 0.28), candles=12)
    # ---- background: along each side wall, bay by bay: a table with stools, a bench, and shields on the piers
    for wl, sx in (("W", -1), ("E", 1)):
        for k, ym in enumerate(mids):
            al = ym - cy
            if (k + (0 if wl == "W" else 1)) % 2 == 0:
                t = D.against("trestle_table", wl, al, "background", length=2.2, width=0.75)
                if t:
                    D.clutter(t, ["goblet", "table_candle", "scroll", "book_stack", "tankard", "bottle", "crockery_set"], 6)
                    xs_, ys_ = t.location.x + (-sx * 0.0), t.location.y
                    for off in (-0.55, 0.55):
                        px = x1 - 1.35 if sx > 0 else x0 + 1.35
                        D.floor("stool", px, ym + off, 0, "background", margin=0.0)
            else:
                b = D.against("bench", wl, al, "background", length=2.2, back=True)
            for a in D.free_wall_spots(wl, 0.6, 2.0, 3.2, 0.5)[:0]:
                pass
        for a in [s_ for s_ in D.free_wall_spots(wl, 0.7, 2.2, 3.0, 0.35)]:
            if abs(a) < d / 2 - 2.0 and D.rnd.random() < 0.55:
                D.hang("shield_wall", wl, a, z=2.2, layer="background", color=D.rnd.choice(["#A3231F", "#2D4A6B", "#C9A44A", "#3F5F3A"]))
        for a in D.free_wall_spots(wl, 0.5, 2.1, 2.7, 0.35):
            D.hang("wall_sconce", wl, a, z=2.1, layer="background")
            break
        for a in D.free_wall_spots(wl, 0.9, h - 3.6, h - 0.4, 0.7)[::2]:
            D.hang("banner", wl, a, z=h - 0.9, layer="background", size=(0.9, 2.6), color=D.rnd.choice(["#A3231F", "#2D4A6B"]), emblem=D.rnd.choice(["lion", "sun", "star"]))
    # ---- the south end: weapon racks and armour beside the doors, tapestries, torches either side of the gate
    D.against("weapon_rack", "S", -w / 2 + 2.3, "background", seed=D.seed)
    D.against("weapon_rack", "S", w / 2 - 2.3, "background", seed=D.seed + 1)
    for sx in (-1, 1):
        D.against("suit_of_armour", "S", sx * (w / 2 - 0.9), "background")
    for a in D.free_wall_spots("S", 1.6, 0.8, 3.8, 0.8)[:2]:
        D.hang("tapestry", "S", a, z=1.0, layer="background", width=1.6, height=2.6, seed=int(a * 10) % 9)
    for oid, hd in R.openings.items():
        if hd["kind"] == "door":
            W_ = hd["wall"]
            for s_ in (-1, 1):
                D.hang("torch_wall", W_, D._along(W_, hd["centre"]) + s_ * (hd["w"] / 2 + 0.7), z=2.4, layer="background")
    # ---- the near edge: occluders on the camera side
    for sx in (-1, 1):
        D.floor("brazier", cx + sx * (w / 2 - 1.1), y0 + 1.7, 0, "foreground", margin=0.0)
        D.floor("banner_pole", cx + sx * (w / 2 - 3.0), y0 + 2.4, 0, "foreground", height=3.6, margin=0.0)
    for sx in (-1, 1):                                    # long tables in the side aisles of the nave, close to the camera: occluders with plenty on them
        t = D.floor("banquet_table", cx + sx * 2.35, y0 + 5.1, 90, "foreground", margin=0.05, length=2.3, width=0.8)
        if t:
            D.clutter(t, ["goblet", "tankard", "table_candle", "scroll", "book_stack", "crockery_set", "bottle", "bread_basket", "papers_stack"], 9)
    # ---- the dais corners: great plants, vases; armour and a rack by the steps
    for sx in (-1, 1):
        D.floor("potted_plant", cx + sx * (dw / 2 - 0.6), y1 - 0.8, 0, "background", z=0.45, height=1.9, seed=sx + 3, check=False)
        D.floor("suit_of_armour", cx + sx * (dw / 2 + 0.7), y1 - 3.2, 0, "background", margin=0.0)
    # ---- mid: council tables flanking the dais, candelabra along the carpet, chests, sacks and barrels near the walls
    for sx in (-1, 1):
        t2 = D.floor("banquet_table", cx + sx * (w / 2 - 1.3), y1 - 4.3, 90, "mid", margin=0.1, length=2.4)
        if t2:
            D.clutter(t2, ["goblet", "tankard", "table_candle", "scroll", "book_stack", "papers_stack", "bottle"], 6)
        for yy_ in (y0 + 7.2, y0 + 9.6, cy + 1.0, y1 - 5.6):
            D.floor("candelabra", cx + sx * 1.75, yy_, 0, "mid", margin=0.0)
        D.floor("chair_arm", cx + sx * (w / 2 - 2.5), y1 - 4.3, -90 * sx, "mid", margin=0.0)
    for k in range(D.n(3)):
        D.floor("barrel", x0 + 0.7 + 0.8 * k, y0 + 0.9, 0, "foreground", margin=0.05)
    D.floor("sack", x1 - 0.8, y0 + 0.8, 0, "foreground")
    D.floor("sack", x1 - 1.5, y0 + 0.9, 0, "foreground")
    D.floor("chest", x0 + 0.9, y0 + 2.4, 90, "foreground", margin=0.05)
    D.floor_detail("straw", D.n(60), region=(x0 + 0.4, y0 + 0.4, x0 + 2.0, y1 - 4.5))
    D.floor_detail("straw", D.n(50), region=(x1 - 2.0, y0 + 0.4, x1 - 0.4, y1 - 4.5))
    D.floor_detail("papers", D.n(6), region=(x0 + 1.0, y1 - 8.0, x1 - 1.0, y1 - 4.6))


@theme("great_hall", ["medieval", "renaissance", "fantasy"])
def great_hall(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    # high table on a dais at the far end
    ds = arch.dais((min(w - 3, 7.0), 2.6), 0.4, at=(cx, y1, 0), surface="flagstone", steps=2)
    ds["sk_layer"] = "background"
    D.made.append(ds)
    D.rects.append((cx, y1 - 1.3, min(w - 3, 7.0) / 2, 1.3, 0.0))
    D.rects.append((cx, y1 - 3.0, min(w - 3, 7.0) / 2, 0.5, 0.0))
    ht = furnish.banquet_table(at=(cx, y1 - 1.5, 0.4), rot_z=0, length=min(w - 4, 5.0))
    D._record(ht, "background", None)
    D.clutter(ht, ["goblet", "table_candle", "crockery_set", "bread_basket", "bottle"], 7)
    for k, sx in enumerate((-1.6, 0, 1.6)):
        D.floor("chair_arm", cx + sx, y1 - 2.35, 0, "background", z=0.4, margin=0.0, marks=False)
    D.hang("banner", "N", -w * 0.3, z=h - 1.2, layer="background", size=(1.2, 3.0))
    D.hang("banner", "N", w * 0.3, z=h - 1.2, layer="background", size=(1.2, 3.0), emblem="sun")
    D.hang("tapestry", "N", 0.0, z=h * 0.42 if h > 5 else 1.2, layer="background", width=2.4, height=min(2.6, h * 0.45))
    # long tables with benches in the nave
    for i, xx in enumerate((cx - 2.2, cx + 2.2)):
        for j in range(max(1, int((d - 8) / 3.7))):
            t = D.floor("banquet_table", xx, y0 + 4.5 + j * 3.7, 90, "mid", margin=0.5, length=3.2)
            if t:
                for sx in (-1, 1):
                    D.floor("bench", xx + sx * 0.85, y0 + 4.5 + j * 3.7, 90, "mid", margin=0.0, length=2.8)
                D.clutter(t, ["goblet", "tankard", "crockery_set", "bread_basket", "table_candle"], 5)
    # fireplace on the east wall with its tools
    fp = arch.fireplace(2.6, 1.6, 0.8, at=(x1, cy - 2.0, 0), rot_z=-90, chimney_h=h)
    arch.tag_wall(fp, R.name, "E")
    fp["sk_layer"] = "background"
    D.made.append(fp)
    D.walls["E"].append((-4.0, 0.0, 0, h))
    D.rects.append((x1 - 0.5, cy - 2.0, 0.5, 1.5, 0.0))
    D.floor("fireplace_set", x1 - 1.5, cy - 0.6, 0, "background", margin=0.0, marks=False)
    D.floor("chair_arm", x1 - 2.3, cy - 2.0, 90, "mid", margin=0.0)
    D.hang("painting_framed", "E", 2.5, z=2.0, layer="background", width=1.1, height=0.9)
    # columns / pillars near the camera side, torches, banners
    for sx in (-1, 1):
        c = arch.column("round", h - 0.4, 0.35, at=(cx + sx * (w / 2 - 1.2), y0 + 2.2, 0))
        c["sk_layer"] = "foreground"
        D.made.append(c)
        D.rects.append((cx + sx * (w / 2 - 1.2), y0 + 2.2, 0.5, 0.5, 0.0))
    for a in D.free_wall_spots("W", 1.0, h - 3.2, h - 0.3, 0.8)[::2]:
        D.hang("banner", "W", a, z=h - 0.8, layer="background", size=(0.9, 2.4), emblem=D.rnd.choice(["lion", "sun", "star"]))
    _sconces(D, "W", z=2.5, step=3.5, margin=2.0)
    for oid, hd in R.openings.items():
        if hd["kind"] == "door":
            for s_ in (-1, 1):
                D.hang("torch_wall", hd["wall"], D._along(hd["wall"], hd["centre"]) + s_ * (hd["w"] / 2 + 0.7), z=2.4)
    for i in range(max(2, int(d / 6))):
        D.ceiling_piece("chandelier", cx, y0 + 4.0 + i * (d - 8) / max(1, int(d / 6) - 1 or 1), "mid", radius=0.8, drop=min(1.8, h * 0.25), candles=10)
    for k in range(D.n(3)):
        D.floor("barrel", x0 + 0.8 + k * 0.9, y0 + 0.9, 0, "foreground", margin=0.05)
    D.floor("sack", x0 + 0.8, y0 + 2.2, 0, "foreground")
    D.floor_detail("straw", D.n(80), region=(x0 + 0.4, y0 + 0.4, x1 - 0.4, y1 - 3.0))
    D.against("weapon_rack", "W", -d / 4, "background")
    D.against("chest", "W", d / 4, "background")


@theme("castle_kitchen", ["medieval", "renaissance", "fantasy"])
def castle_kitchen(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    fp = arch.fireplace(min(3.0, w * 0.5), 1.8, 0.9, at=(cx, y1, 0), rot_z=0, chimney_h=h)
    arch.tag_wall(fp, R.name, "N")
    fp["sk_layer"] = "background"
    D.made.append(fp)
    D.walls["N"].append((-min(3.0, w * 0.5) / 2 - 0.2, min(3.0, w * 0.5) / 2 + 0.2, 0, h))
    D.rects.append((cx, y1 - 0.5, 1.7, 0.5, 0.0))
    D.floor("pots_and_pans", cx, y1 - 1.3, 0, "background", margin=0.0, marks=False)
    D.floor("fireplace_set", cx + 2.0, y1 - 0.7, 0, "background", margin=0.0, marks=False)
    for k, W in enumerate(("W", "E")):
        for a in (-d * 0.25, d * 0.05, d * 0.3):
            D.hang("shelf_jars", W, a, z=1.6 + 0.4 * (k % 2), layer="background", length=1.3, seed=int(a * 7) % 17)
        D.against("cabinet", W, -d / 2 + 1.0, "background")
    for i in range(2):
        t = D.floor("trestle_table", cx - 1.6 + i * 3.2, cy + 0.4, 0, "mid", length=2.2, width=0.9, margin=0.4)
        if t:
            D.clutter(t, ["pots_and_pans", "bread_basket", "fruit_crate", "crockery_set", "market_goods", "mugs", "bottle", "basket"], 6)
    t = D.floor("banquet_table", cx, y0 + 3.0, 0, "foreground", length=2.6, margin=0.3)
    if t:
        D.clutter(t, ["fruit_crate", "basket", "cloth_bolts", "bread_basket", "jug"], 4)
        for sx in (-0.9, 0.9):
            D.floor("stool", cx + sx, y0 + 3.9, 0, "foreground", margin=0.0)
    for k in range(D.n(5)):
        D.floor("barrel" if k % 2 else "sack", x0 + 0.8 + (k // 2) * 0.9, y0 + 1.0 + (k % 2) * 0.1, 0, "foreground", margin=0.05)
    for k in range(D.n(3)):
        D.floor("crate", x1 - 0.8 - k * 0.7, y0 + 1.0, 0, "foreground", size=0.55, margin=0.05)
    D.floor("basket", x1 - 1.0, y0 + 2.2, 0, "foreground")
    _sconces(D, "EW", z=2.2, step=3.2, margin=1.5)
    D.hang("hanging_sign", "S", 0.0, z=2.2, layer="background")
    for oid, hd in R.openings.items():
        if hd["kind"] == "door":
            D.hang("torch_wall", hd["wall"], D._along(hd["wall"], hd["centre"]) + hd["w"] / 2 + 0.7, z=2.3)
    D.ceiling_piece("chandelier", cx, cy + 1.0, "mid", radius=0.55, drop=min(1.4, h * 0.3), candles=8)
    D.floor_detail("straw", D.n(70), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 2.0))


@theme("tavern", ["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"])
def tavern(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    bar = D.against("bar_counter", "N", -w * 0.1, "background", length=min(4.2, w * 0.5), gap=1.5)
    if bar:
        D.clutter(bar, ["tankard", "tankard", "bottle", "jug", "table_candle", "bread_basket"], 7)
        for sx in (-1.4, -0.4, 0.5, 1.4):
            D.floor("stool", bar.location.x + sx, bar.location.y - 1.0, 0, "mid", margin=0.0, marks=False)
    for k, a in enumerate((-w * 0.3, -w * 0.1, w * 0.1, w * 0.3)):
        D.hang("shelf_jars", "N", a, z=1.7 + 0.45 * (k % 2), layer="background", length=1.3, seed=k)
    D.against("barrel", "N", w * 0.38, "background")
    D.against("barrel", "N", w * 0.38 - 0.8, "background")
    D.hang("hanging_sign", "N", w * 0.3, z=2.4, layer="background")
    fp = arch.fireplace(2.2, 1.4, 0.7, at=(x0, cy + 1.5, 0), rot_z=90, chimney_h=h)
    arch.tag_wall(fp, R.name, "W")
    fp["sk_layer"] = "background"
    D.made.append(fp)
    D.walls["W"].append((0.2, 2.8, 0, h))
    D.rects.append((x0 + 0.4, cy + 1.5, 0.4, 1.1, 0.0))
    D.floor("chair_arm", x0 + 1.6, cy + 1.5, -90, "mid", margin=0.0)
    D.floor("fireplace_set", x0 + 1.2, cy + 0.3, 0, "background", margin=0.0, marks=False)
    for i, (x, y) in enumerate(((-2.6, -0.6), (2.4, -1.0), (-2.2, -3.4), (2.6, -3.6))):
        t = D.floor("trestle_table", cx + x, cy + y, 0 if i % 2 else 90, "mid", length=1.6, width=0.75, margin=0.5)
        if t:
            for sx, sy in ((0, 0.85), (0, -0.85)):
                D.floor("stool", t.location.x + sx, t.location.y + sy - 0.4, 0, "mid", margin=0.0)
            D.clutter(t, ["tankard", "tankard", "table_candle", "crockery_set", "bottle", "bread_basket"], 4)
    D.hang("notice_board", "E", -1.0, z=1.2, layer="background")
    D.hang("painting_framed", "E", 1.5, z=1.7, layer="background", width=0.8, height=0.65)
    D.hang("banner", "S", -w * 0.28, z=h - 0.5, layer="foreground", size=(0.6, 1.6), emblem="tree")
    _sconces(D, "S", z=2.3, step=3.0, margin=1.5, layer="foreground")
    D.ceiling_piece("chandelier", cx, cy - 0.5, "mid", radius=0.55, drop=min(1.1, h * 0.3), candles=8)
    D.floor("potted_plant", x1 - 0.7, y0 + 0.8, 0, "foreground", height=1.3)
    D.floor("crate", x1 - 0.8, y0 + 2.0, 0, "foreground", size=0.5)
    D.floor_detail("straw", D.n(60), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, cy - 1.0))
    D.floor_detail("papers", D.n(6), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5))


@theme("peasant_cottage", ["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"])
def peasant_cottage(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    fp = arch.fireplace(1.8, 1.2, 0.6, at=(cx, y1, 0), rot_z=0, chimney_h=h, surface="fieldstone")
    arch.tag_wall(fp, R.name, "N")
    fp["sk_layer"] = "background"
    D.made.append(fp)
    D.walls["N"].append((-1.1, 1.1, 0, h))
    D.rects.append((cx, y1 - 0.4, 1.0, 0.4, 0.0))
    D.floor("pots_and_pans", cx + 0.3, y1 - 1.1, 0, "background", margin=0.0, marks=False)
    D.floor("fireplace_set", cx - 1.9, y1 - 0.5, 0, "background", margin=0.0, marks=False)
    D.against("bed", "W", d * 0.12, "background", width=1.1, length=1.9, blanket="#6A4A3A", posts=False)
    D.against("chest", "W", -d * 0.25, "background")
    D.against("cabinet", "E", d * 0.12, "background", width=0.9, height=1.7)
    D.hang("shelf_jars", "E", -d * 0.2, z=1.5, layer="background", length=1.1, seed=2)
    D.hang("shelf_jars", "W", -d * 0.05, z=1.7, layer="background", length=0.9, seed=3)
    t = D.floor("trestle_table", cx + 0.4, cy - 0.2, 0, "mid", length=1.5, width=0.7, margin=0.45)
    if t:
        D.clutter(t, ["crockery_set", "bread_basket", "jug", "table_candle", "mugs", "basket"], 4)
        D.floor("stool", cx + 0.1, cy - 0.95, 0, "mid", margin=0.0)
        D.floor("stool", cx + 1.0, cy - 0.95, 0, "mid", margin=0.0)
        D.floor("bench", cx + 0.4, cy + 0.55, 0, "mid", margin=0.0, length=1.4)
    D.floor("spinning_wheel", x0 + 1.0, y1 - 1.6, 90, "mid")
    D.floor("broom", x1 - 0.5, y0 + 1.0, 0, "foreground", marks=False)
    for k in range(D.n(3)):
        D.floor("sack", x1 - 0.7, y1 - 0.8 - k * 0.7, 0, "background", margin=0.0)
    D.floor("basket", x0 + 0.8, y0 + 1.0, 0, "foreground")
    D.floor("crate", x0 + 0.8, y0 + 1.8, 0, "foreground", size=0.5)
    D.hang("wall_sconce", "E", 1.5, z=1.8, layer="background")
    D.hang("wall_sconce", "W", -1.6, z=1.8, layer="background")
    D.hang("painting_framed", "S", -1.0, z=1.5, layer="foreground", width=0.55, height=0.45)
    D.floor_detail("straw", D.n(90), region=(x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3))
    for k in range(3):
        D.ceiling_piece("lantern", cx - 1.0 + k * 1.0, cy + 1.5, "mid", hanging=True) if k == 1 else None


@theme("office_open_plan", ["modern"])
def office_open_plan(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    # ---- ceiling: a grid of tiles with light panels (eight with real lights, the rest glowing a little)
    nx, ny = max(2, int(w / 2.4)), max(2, int(d / 2.4))
    lit = 0
    for i in range(nx):
        for j in range(ny):
            x = x0 + w * (i + 0.5) / nx
            y = y0 + d * (j + 0.5) / ny
            if (i + j) % 2 == 0 and lit < 8:
                D.ceiling_piece("ceiling_light_panel", x, y, "mid", size=(1.2, 0.6), power=45.0)
                lit += 1
            else:
                p = Parts("ceiling_dark_panel", "SET", "ceiling_panel", kind="shell")
                p.box((1.2, 0.6, 0.02), (0, 0, -0.03), mat.solid("#D8D9DB", 0.5), bevel=0.0)
                p.box((1.15, 0.55, 0.01), (0, 0, -0.04), p.glow("#F1F3FF", 1.0), bevel=0.0)
                arch.tag_wall(p.build(at=(x, y, h), recentre=False), R.name, "C")
    # ---- the open-plan floor: rows of workstations facing the window wall (north), five desks to a row
    rows = [y0 + 1.9 + k * 2.8 for k in range(max(1, int((d - 1.0) / 2.8)))]
    for ri, yy in enumerate(rows):
        for ci in range(6):
            xx = x0 + 1.3 + ci * 1.9
            lay = "foreground" if ri == 0 else "mid"
            if D.rnd.random() < 0.06:
                continue
            _desk_cluster(D, xx, yy, 0, D.rnd.choice(["#2B2F3A", "#3A4A5A", "#4A3A3A", "#2F4A3A"]), lay, lamp=(ri + ci) % 3 == 0)
    # ---- storage and equipment: first free spot from the place it is wanted
    D.against_any("filing_cabinet", "W", near=d * 0.35, drawers=4)
    D.against_any("filing_cabinet", "W", near=d * 0.35 + 0.5, drawers=3)
    D.against_any("printer", "W", near=d * 0.15)
    D.against_any("water_cooler", "W", near=-d * 0.05)
    D.against_any("bookcase", "S", near=-w * 0.3, width=1.2, seed=3)
    D.against_any("coat_stand", "W", near=-d * 0.38)
    D.against_any("bin", "W", near=d * 0.05)
    D.against_any("bin", "N", near=-w * 0.4)
    D.against_any("bookcase", "S", near=w * 0.1, width=1.0, seed=5)
    for k, nr in enumerate((-5.6, -1.9, 1.9, 5.6)):                  # a plant under every north window
        D.floor("potted_plant", cx + nr, y1 - 0.65, 0, "background", height=1.0 + 0.3 * (k % 2), seed=k + 10, margin=0.0)
    D.against_any("filing_cabinet", "N", near=-w * 0.45, drawers=3)
    D.against_any("filing_cabinet", "N", near=w * 0.45, drawers=4)
    D.against_any("water_cooler", "N", near=0.0)
    for k, (wl, nr) in enumerate((("N", -w * 0.45), ("N", w * 0.45), ("S", w * 0.3), ("S", -w * 0.05))):
        D.floor("potted_plant", *({"N": (cx + nr, y1 - 0.7), "S": (cx + nr, y0 + 0.7)}[wl]), 0, "background" if wl == "N" else "foreground", height=1.2 + 0.25 * (k % 3), seed=k + 1)
    # ---- wall dressing at eye height: whiteboard, notice boards, posters, clock, a picture
    for W_, near, nm, kw in (("W", d * 0.0, "whiteboard", dict(width=2.0, height=1.1, seed=1)), ("W", d * 0.3, "notice_board", dict(width=1.3, height=0.9, seed=2)),
                             ("S", w * 0.2, "poster", dict(color="#2D7DD2", seed=1)), ("S", -w * 0.12, "poster", dict(color="#D95D39", seed=2)),
                             ("S", w * 0.4, "notice_board", dict(width=1.0, height=0.8, seed=6)), ("E", -d * 0.1, "painting_framed", dict(width=1.1, height=0.8, seed=4))):
        zz = furnish.REGISTRY[nm]["mount_z"]
        spots = D.free_wall_spots(W_, kw.get("width", 0.5) + 0.2, zz, zz + kw.get("height", 0.7), 0.3)
        if spots:
            D.hang(nm, W_, min(spots, key=lambda a: abs(a - near)), z=zz, layer="background", **kw)
    for W_ in ("N", "S", "E"):
        spots = D.free_wall_spots(W_, 0.5, h - 0.7, h - 0.2, 0.3)
        if spots:
            D.hang("wall_clock", W_, spots[len(spots) // 2], z=h - 0.55, layer="background", radius=0.2)
            break
    # ---- the kitchenette: counter run with sink and hob, fridge, kettle, mugs, microwave
    kc = D.against_any("kitchen_counter", "E", near=-d * 0.3, length=2.4, wall_units=True)
    if kc:
        D.clutter(kc, ["kettle", "mugs", "microwave", "mugs"], 4)
    D.against_any("fridge", "E", near=-d * 0.08)
    D.floor_detail("papers", D.n(5), region=(x0 + 1, y0 + 1, x1 - 1, y1 - 1))


@theme("office_private", ["modern"])
def office_private(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    for i in range(2):
        D.ceiling_piece("ceiling_light_panel", cx - w * 0.2 + i * w * 0.4, cy, "mid", size=(1.2, 0.6), power=45.0)
    ds = D.floor("desk_office", cx, y1 - 2.2, 180, "background", length=2.0, depth=0.9, color="#6B4A30", margin=0.0)
    if ds:
        D.top(ds, "monitor_keyboard", k=1)
        for nm in ("papers_stack", "mugs", "office_phone", "desk_lamp", "book_stack"):
            D.top(ds, nm, k=1)
        D.floor("chair_arm", cx, y1 - 1.3, 180 + 180, "background", margin=0.0, marks=False)
    for sx in (-0.7, 0.7):
        D.floor("chair_dining", cx + sx, y1 - 3.3, 0, "mid", margin=0.0)
    D.against("bookcase", "N", -w * 0.3, "background", width=1.2, seed=1)
    D.against("bookcase", "N", w * 0.3, "background", width=1.2, seed=2)
    D.hang("painting_framed", "N", 0.0, z=1.7, layer="background", width=1.4, height=0.9)
    sf = D.against("sofa", "W", -d * 0.1, "background", length=2.0)
    if sf:
        ct = D.floor("coffee_table", sf.location.x + 1.5, sf.location.y, 90, "mid", margin=0.0)
        if ct:
            D.clutter(ct, ["mugs", "book_stack", "vase_flowers"], 3)
    D.floor("floor_lamp", x0 + 0.7, y1 - 0.9, 0, "background")
    D.floor("potted_plant", x1 - 0.8, y1 - 0.8, 0, "background", height=1.7, seed=2)
    D.floor("potted_plant", x0 + 0.8, y0 + 0.8, 0, "foreground", height=1.4, seed=5)
    D.against("filing_cabinet", "E", d * 0.25, "background")
    D.hang("wall_clock", "E", -d * 0.2, z=2.1, layer="background")
    D.hang("poster", "S", w * 0.2, z=1.5, layer="foreground", color="#2D4A6B", seed=3)
    D.hang("notice_board", "W", d * 0.3, z=1.2, layer="background", width=0.9, height=0.7)
    D.against("coat_stand", "E", -d * 0.35, "background")
    D.against("bin", "E", -d * 0.1, "background")
    D.floor("rug", cx, cy + 0.3, 0, "mid", flat=True, size=(min(3.2, w - 1.0), 2.2), surface="carpet_red", inner="#5E1A20")


@theme("home_living_room", ["victorian", "modern"])
def home_living_room(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    D.floor("rug", cx, cy, 0, "mid", flat=True, size=(min(3.4, w - 1.2), min(2.6, d - 1.2)), surface="carpet_red", inner="#7A6A4E", border="#D9C9A0")
    tv = D.against("tv", "N", 0.0, "background")
    if tv:
        D.top(tv, "vase_flowers", k=0)
    sf = D.floor("sofa", cx, cy - 1.3, 180, "mid", length=2.2, color="#6B7D8A", margin=0.0)
    if sf is None:
        sf = D.against("sofa", "S", 0.0, "foreground", length=2.2)
    D.against("bookcase", "W", -d * 0.1, "background", width=1.2, seed=6)
    D.against("bookcase", "W", d * 0.2, "background", width=1.0, seed=7)
    ct = D.floor("coffee_table", cx, cy + 0.2, 0, "mid", margin=0.0)
    if ct:
        D.clutter(ct, ["mugs", "book_stack", "vase_flowers", "papers_stack"], 3)
    D.floor("chair_arm", cx + 1.9, cy + 0.4, 90, "mid", upholstery="leather")
    D.floor("floor_lamp", x1 - 0.7, y1 - 0.9, 0, "background")
    D.floor("potted_plant", x0 + 0.8, y1 - 0.8, 0, "background", height=1.5, seed=1)
    D.floor("potted_plant", x1 - 0.7, y0 + 1.0, 0, "foreground", height=1.2, seed=4)
    D.hang("painting_framed", "E", 0.0, z=1.5, layer="background", width=1.3, height=0.9, seed=2)
    D.hang("painting_framed", "E", d * 0.3, z=1.6, layer="background", width=0.6, height=0.8, seed=5)
    D.hang("wall_clock", "N", -w * 0.28, z=2.1, layer="background")
    D.hang("poster", "S", -w * 0.2, z=1.5, layer="foreground", color="#3F5F3A", seed=1)
    D.hang("wall_sconce", "N", w * 0.3, z=1.9, layer="background", kind="modern")
    D.ceiling_piece("ceiling_light_panel", cx, cy, "mid", size=(0.6, 0.6), power=35.0)
    D.against("cabinet", "E", -d * 0.3, "background", width=0.9, height=1.2)


@theme("home_kitchen", ["victorian", "modern"])
def home_kitchen(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    kc = D.against("kitchen_counter", "N", -w * 0.1, "background", length=min(2.8, w - 1.5))
    if kc:
        D.clutter(kc, ["kettle", "mugs", "pots_and_pans", "microwave", "bread_basket", "fruit_crate"], 5)
    D.against("fridge", "N", w * 0.38, "background")
    D.floor("potted_plant", x0 + 0.7, y1 - 0.8, 0, "background", height=1.2, seed=2)
    D.hang("shelf_jars", "W", 0.0, z=1.6, layer="background", length=1.1, seed=4)
    D.hang("wall_clock", "E", 0.0, z=2.0, layer="background")
    D.hang("poster", "E", d * 0.25, z=1.4, layer="background", color="#E8B63A", seed=3)
    D.hang("painting_framed", "W", d * 0.25, z=1.5, layer="background", width=0.7, height=0.5, seed=7)
    t = D.floor("coffee_table", cx, cy - 0.4, 0, "mid", margin=0.5)
    if t is None:
        t = D.floor("trestle_table", cx, cy - 0.4, 0, "mid", length=1.4, width=0.8, margin=0.5)
    if t:
        D.clutter(t, ["mugs", "bread_basket", "vase_flowers", "crockery_set", "fruit_crate"], 3)
        for sx in (-0.9, 0.9):
            D.floor("chair_dining", cx + sx, cy - 0.4, 90 if sx < 0 else -90, "mid", margin=0.0)
    D.floor("bin", x1 - 0.5, y1 - 1.2, 0, "background")
    D.ceiling_piece("ceiling_light_panel", cx, cy, "mid", size=(0.6, 0.6), power=35.0)
    D.floor("potted_plant", x1 - 0.7, y0 + 1.0, 0, "foreground", height=1.0, seed=5)
    D.floor_detail("papers", D.n(3), region=(x0 + 1, y0 + 1, x1 - 1, y1 - 1))


@theme("shop_interior", ["medieval", "renaissance", "age_of_sail", "victorian", "modern", "fantasy"])
def shop_interior(D):
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    ct = D.floor("bar_counter", cx, cy + 0.6, 0, "mid", length=min(3.0, w - 2.0), margin=0.6)
    if ct:
        D.clutter(ct, ["basket", "market_goods", "bread_basket", "jug", "scroll", "table_candle", "book_stack"], 6)
    for k, a in enumerate((-w * 0.32, -w * 0.1, w * 0.12, w * 0.34)):
        D.hang("shelf_jars", "N", a, z=1.5 + 0.5 * (k % 2), layer="background", length=1.3, seed=k + 1)
        D.hang("shelf_jars", "N", a, z=2.3 - 0.4 * (k % 2), layer="background", length=1.3, seed=k + 9)
    D.against("cabinet", "W", 0.0, "background")
    D.against("bookcase", "E", 0.0, "background", width=1.0, seed=8)
    for k in range(D.n(3)):
        D.floor("barrel", x0 + 0.8 + k * 0.9, y1 - 1.0, 0, "background", margin=0.04)
    for k in range(D.n(3)):
        D.floor("sack", x1 - 0.8 - k * 0.7, y1 - 0.8, 0, "background")
    t = D.floor("trestle_table", cx - w * 0.28, y0 + 2.6, 0, "foreground", length=1.4, margin=0.4)
    if t:
        D.clutter(t, ["cloth_bolts", "fruit_crate", "basket", "bread_basket"], 3)
    D.floor("crate", x1 - 0.8, y0 + 1.2, 0, "foreground", size=0.55)
    D.floor("potted_plant", x0 + 0.7, y0 + 0.8, 0, "foreground", height=1.2)
    D.hang("hanging_sign", "W", -d * 0.2, z=2.5, layer="background")
    D.hang("notice_board", "E", -d * 0.25, z=1.3, layer="background", width=0.9, height=0.7, seed=5)
    D.hang("wall_clock", "S", 0.0, z=2.3, layer="foreground")
    _sconces(D, "EW", z=2.1, step=3.0, margin=1.2)
    D.ceiling_piece("chandelier", cx, cy - 0.3, "mid", radius=0.5, drop=min(1.0, h * 0.28), candles=6)
    D.floor_detail("straw", D.n(40), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5))


# ============================================================================= EXTERIOR THEMES
def _row_of_houses(D, y, face_rot, x_from, x_to, styles, seed, awning=False, storeys=(2, 3)):
    x = x_from
    rnd = D.rnd
    out = []
    while x < x_to - 3:
        wd = rnd.uniform(5.5, 8.0)
        st = rnd.choice(styles)
        hs = house_args(st, rnd, storeys)
        hf = arch.house_front(storeys=hs["storeys"], style=st, width=wd, depth=6.0, at=(x + wd / 2, y, 0), rot_z=face_rot, awning=("#B3322C" if awning and rnd.random() < 0.5 else None), seed=rnd.randint(0, 99),
                              door_type=rnd.choice(["panel", "plank"]))
        hf["sk_layer"] = "background"
        D.made.append(hf)
        out.append(hf)
        x += wd + rnd.uniform(0.5, 0.8)
    return out


def house_args(style, rnd, storeys):
    return {"storeys": rnd.choice(list(range(storeys[0], storeys[1] + 1)))}


@theme("market_street", ["medieval", "renaissance", "age_of_sail", "victorian"], "exterior")
def market_street(D):
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    D.ground("earth_path")
    st = arch.street(x1 - x0 + 40, 7.0, 0.15, "cobblestone", at=(cx, cy, 0))
    st["sk_layer"] = "mid"
    D.made.append(st)
    D.floor_detail("straw", D.n(70), region=(x0, cy - 3.2, x1, cy + 3.2))
    # background: house fronts on both sides of the street; the near side's backs are not visible, so they face away from the camera
    _row_of_houses(D, cy + 5.6, 0.0, x0 - 20, x1 + 20, ["timber", "timber", "brick"], D.seed, awning=True)
    _row_of_houses(D, cy - 5.6, 180.0, x0 - 20, x1 + 20, ["timber", "stone"], D.seed + 1, awning=True)
    # mid and foreground: stalls on the pavement, with goods, barrels, crates, a cart
    for i, x in enumerate((cx - 7.0, cx - 2.5, cx + 3.0, cx + 8.0)):
        s = D.floor("market_stall", x, cy + 3.3, 0, "mid", canopy=D.rnd.choice(["#B3322C", "#2D6CB0", "#D8A93A", "#3F8F5A"]), margin=0.3)
        if s:
            D.clutter(s, ["fruit_crate", "basket", "cloth_bolts", "bread_basket", "market_goods", "jug"], 4)
    for x in (cx - 5.0, cx + 6.0):
        D.floor("barrel", x, cy - 3.0, 0, "foreground")
    for k in range(D.n(6)):
        D.floor("barrel" if k % 2 else "crate", D.rnd.uniform(x0, x1), cy - 3.2 + D.rnd.uniform(-0.2, 0.3), 0, "foreground", **({} if k % 2 else {"size": 0.55}))
    D.floor("cart", cx - 3.0, cy - 1.6, 12, "mid", margin=0.3)
    for k in range(D.n(5)):
        D.floor("sack", D.rnd.uniform(x0, x1), cy - 2.6 + D.rnd.uniform(-0.2, 0.4), 0, "mid")
    for x in (cx - 8.5, cx - 1.0, cx + 5.5):
        D.floor("lamp_post", x, cy + 3.6, 0, "mid", height=4.2, style="gas", margin=0.0)
    D.floor("potted_plant", cx + 2.0, cy - 2.8, 0, "foreground", height=1.1)
    sk = arch.skyline(120, 30, at=(cx, cy + 14, 0), kind="town", seed=D.seed)
    sk["sk_layer"] = "beyond"
    D.made.append(sk)


@theme("village_square", ["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], "exterior")
def village_square(D):
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    build.ground("ground", 400, "grass_lawn")
    pl = arch.plaza((x1 - x0, y1 - y0), at=(cx, cy, 0))
    pl["sk_layer"] = "mid"
    D.made.append(pl)
    D.floor("well", cx, cy + 1.0, 0, "mid", radius=0.8, height=0.9, margin=0.3)
    _row_of_houses(D, y1 + 1.0, 0.0, x0 - 4, x1 + 4, ["timber", "stone", "brick"], D.seed)
    for k in range(D.n(3)):
        D.floor("market_stall", x0 + 4.0 + k * 5.5, y1 - 4.0, 0, "mid", canopy=D.rnd.choice(["#B3322C", "#2D6CB0", "#D8A93A"]))
    for k in range(D.n(4)):
        D.floor("bench", D.rnd.uniform(x0 + 2, x1 - 2), D.rnd.uniform(y0 + 2, cy), D.rnd.choice([0, 90]), "foreground", length=1.6, margin=0.4)
    for x in (x0 + 2.0, x1 - 2.0):
        D.floor("lamp_post", x, y0 + 2.0, 0, "foreground", height=4.0, style="gas", margin=0.0)
    for k in range(D.n(4)):
        D.floor("barrel", D.rnd.uniform(x0, x1), D.rnd.uniform(y0, y1 - 6), 0, "mid")
    D.floor("cart", x1 - 4.0, cy + 1.0, 30, "mid", margin=0.3)
    D.floor("hay_bale", x0 + 3.0, cy + 1.5, 20, "mid")
    for k in range(D.n(3)):
        T = build.tree(f"vtree{k}", at=(x0 + 3.0 + k * (x1 - x0 - 6) / 2, y1 - 1.5), height=6.0 + k, crown=2.6, lean=0.3 * (k - 1), seed=k + D.seed)
        T["root"]["sk_layer"] = "background"
        T["root"]["sk_type"] = "tree"
        T["root"]["sk_kind"] = "prop"
        T["root"]["sk_size"] = [3.0, 3.0, 6.0]
        D.made.append(T["root"])
    tl = arch.treeline(120, 40, at=(cx, y1 + 14, 0), seed=D.seed)
    tl["sk_layer"] = "beyond"
    D.made.append(tl)
    sk = arch.skyline(120, 30, at=(cx, y1 + 22, 0), kind="town", seed=D.seed + 3)
    sk["sk_layer"] = "beyond"
    D.made.append(sk)


@theme("army_camp", ["ancient", "medieval", "renaissance", "age_of_sail", "fantasy"], "exterior")
def army_camp(D):
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    build.ground("ground", 400, "earth_path")
    for k in range(D.n(5)):
        D.floor("tent", x0 + 4 + k * (x1 - x0 - 8) / 4, y1 - 5.0 - (k % 2) * 3.0, 0, "background", color=D.rnd.choice(["#D8CDB4", "#C9B88A", "#B9C4B0"]), margin=0.3)
    for x, y in ((cx - 3.0, cy), (cx + 3.5, cy + 1.5)):
        D.floor("campfire", x, y, 0, "mid", margin=0.3)
        for a in (0, 120, 240):
            D.floor("hay_bale", x + 2.4 * math.cos(math.radians(a)), y + 2.4 * math.sin(math.radians(a)), a + 90, "mid", margin=0.2)
    for k in range(D.n(3)):
        D.floor("weapon_rack", x0 + 3 + k * 6.0, y1 - 11.0, 0, "background", length=1.8)
    for k in range(D.n(3)):
        D.floor("shield_pile", x1 - 3 - k * 2.5, y0 + 3.0, D.rnd.uniform(0, 90), "foreground")
    for k in range(D.n(3)):
        D.floor("banner_pole", x0 + 3 + k * (x1 - x0 - 6) / 2, cy + 3.0, 0, "mid", height=3.6, color=D.rnd.choice(["#A3231F", "#2D4A6B"]), margin=0.4)
    D.floor("cart", x0 + 5, y0 + 4.0, 20, "foreground", margin=0.3)
    for k in range(D.n(6)):
        D.floor(D.rnd.choice(["barrel", "crate", "sack", "hay_bale"]), D.rnd.uniform(x0, x1), D.rnd.uniform(y0 + 1, cy - 2), D.rnd.uniform(0, 90), "foreground", **{})
    D.floor("stakes", cx, y1 - 0.5, 0, "background", count=14, margin=0.1)
    D.floor("arrow_bundle", cx + 1.0, cy - 2.2, 0, "foreground")
    tl = arch.treeline(140, 38, at=(cx, y1 + 10, 0), seed=D.seed)
    tl["sk_layer"] = "beyond"
    D.made.append(tl)
    D.floor_detail("straw", D.n(90), region=(x0, y0, x1, y1))


@theme("battlefield", ["ancient", "medieval", "renaissance", "age_of_sail", "fantasy"], "exterior")
def battlefield(D):
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    build.ground("ground", 400, "forest_floor")
    for k in range(D.n(4)):
        D.floor("stakes", x0 + 4 + k * (x1 - x0 - 8) / 3, y1 - 7.0 + (k % 2) * 3, D.rnd.uniform(-15, 15), "mid", count=9, margin=0.2)
    for k in range(D.n(3)):
        D.floor("shield_pile", D.rnd.uniform(x0 + 2, x1 - 2), D.rnd.uniform(y0 + 1, y1 - 3), D.rnd.uniform(0, 180), "mid")
    for k in range(D.n(3)):
        D.floor("banner_pole", x0 + 4 + k * (x1 - x0 - 8) / 2, y1 - 4.0, D.rnd.uniform(-5, 5), "background", height=3.8, color=D.rnd.choice(["#A3231F", "#2D4A6B"]), margin=0.3)
    D.floor("cart", x1 - 5, cy, 160, "mid", goods=False, margin=0.3)
    for k in range(D.n(5)):
        D.floor("arrow_bundle", D.rnd.uniform(x0, x1), D.rnd.uniform(y0, y1), D.rnd.uniform(0, 180), "foreground")
    for k in range(D.n(8)):
        r = build.rock(f"rock{k}", at=(D.rnd.uniform(x0, x1), D.rnd.uniform(y0, y1 - 2)), size=D.rnd.uniform(0.4, 1.2), surface="rock_face", seed=k)
        r["sk_type"], r["sk_kind"], r["sk_layer"], r["sk_size"] = "rock", "prop", "mid" if k % 2 else "foreground", [0.8, 0.8, 0.4]
        D.made.append(r)
    D.floor("campfire", x0 + 4.0, y0 + 3.0, 0, "foreground")
    tl = arch.treeline(160, 45, at=(cx, y1 + 12, 0), seed=D.seed)
    tl["sk_layer"] = "beyond"
    D.made.append(tl)
    D.floor_detail("straw", D.n(70), region=(x0, y0, x1, y1))


@theme("city_street", ["modern"], "exterior")
def city_street(D):
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    D.ground("concrete")
    st = arch.street(x1 - x0 + 40, 8.0, 0.15, "asphalt", at=(cx, cy, 0), pavement="concrete", pavement_w=3.0)
    st["sk_layer"] = "mid"
    D.made.append(st)
    _row_of_houses(D, cy + 7.8, 0.0, x0 - 20, x1 + 20, ["modern", "brick", "modern"], D.seed, storeys=(3, 5))
    _row_of_houses(D, cy - 7.8, 180.0, x0 - 20, x1 + 20, ["brick", "modern"], D.seed + 1, storeys=(3, 5))
    for k, c in enumerate(("#2D6CB0", "#B02A2A", "#D8D9DB", "#2B2F3A")):
        D.floor("car", cx - 8 + k * 5.5, cy + 2.4, 0 if k % 2 else 180, "mid", color=c, margin=0.5)
    for x in (cx - 9, cx - 2, cx + 6):
        D.floor("lamp_post", x, cy + 4.6, 0, "mid", height=5.2, style="modern", margin=0.0)
    for k in range(D.n(4)):
        D.floor("bin", cx - 7 + k * 4.5, cy - 4.5, 0, "foreground")
    D.floor("hydrant", cx + 3, cy - 4.5, 0, "foreground")
    D.floor("bench", cx - 3, cy - 4.9, 0, "foreground", length=1.8)
    for k in range(D.n(3)):
        D.floor("potted_plant", cx - 6 + k * 6, cy - 5.0, 0, "foreground", height=1.6, seed=k)
    sk = arch.skyline(200, 40, at=(cx, cy + 26, 0), kind="city", seed=D.seed)
    sk["sk_layer"] = "beyond"
    D.made.append(sk)
