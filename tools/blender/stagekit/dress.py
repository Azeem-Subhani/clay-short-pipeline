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
            if len(v) > 2 and float(v[2]) > 1.0:                      # a mark in the air (a camera position) keeps no floor clear
                continue
            self.circles.append((float(v[0]), float(v[1]), keep_clear))
        self.rects: list = []                          # floor rectangles of placed pieces
        self.walls = {w: [] for w in "NSEW"}          # (a0, a1, z0, z1) along-wall occupancy
        self.tops_used: dict = {}                      # parent name -> list of (x, y, r) on its top
        self.made: list = []                           # every root created
        self.rejected = 0
        self.reject_log: list = []                       # (piece, why): what could not be placed, for the recipe author
        self.atmos: list = []
        self.floor_details = 0
        self.treepts: list = []                        # where trees stand (put() records them)
        self.zbase = 0.0                               # default standing height of floor(): a pavement or a step the recipe is working on
        self.zfn = None                                # ground height function when a recipe built terrain
        self.opts: dict = {}                           # options of the call (night=True, ...)
        self.night = False
        self.refs: dict = {}                           # things a recipe hands back to the set file: the doors, the seats, the screen...
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
    def floor(self, name, x, y, rot: float = 0.0, layer: str = "mid", z=None, margin: float = 0.08, marks: bool = True, flat: bool = False, check: bool = True, **kw):
        """Place a free-standing piece so that its footprint CENTRE is at (x, y). Returns it, or None if the spot is taken or out of bounds.
        check=False skips the overlap test (for pieces standing on a raised dais you have already cleared)."""
        fn = furnish.REGISTRY[name]["fn"] if name in furnish.REGISTRY else name
        z = self.zbase if z is None else z
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
    def top(self, parent, name, k: int = 0, layer=None, margin: float = 0.06, tries: int = 14, labels=None, avoid=(), **kw):
        """Stand a small piece on one of a parent's declared tops, away from what is already there. Returns it or None.
        labels: only tops with one of these labels (e.g. ("desk", "table")); avoid: never tops with one of these labels (e.g. ("seat",))."""
        tl = furnish.tops(parent)
        if labels is not None:
            tl = [t for t in tl if t[5] in labels]
        if avoid:
            tl = [t for t in tl if t[5] not in avoid]
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
            jitter = 0.0 if name in ("monitor_keyboard", "laptop", "office_phone", "tv", "till", "balance_scales", "desk_monitor", "laptop_open", "laptop_closed", "router", "power_strip", "water_jug_set") else math.radians(self.rnd.uniform(-25, 25))
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

    def shelves(self, items, n: int = 4, length=(0.8, 1.3), z=(1.35, 1.95), per_shelf: int = 4, walls="NSEW", layer: str = "background"):
        """Hang up to n plank shelves on the free wall stretches (not over doors or windows), then stand small things on each: every item is a
        separate object, which is what a lived-in small room is made of. items = names of small pieces."""
        done = 0
        order = [w_ for w_ in walls for _ in range(2)]
        self.rnd.shuffle(order)
        for W_ in order:
            if done >= n:
                break
            ln = self.rnd.uniform(*length)
            zz = self.rnd.uniform(*z)
            spots = self.free_wall_spots(W_, ln + 0.15, zz - 0.25, zz + 0.45, 0.3)
            if not spots:
                continue
            a = self.rnd.choice(spots)
            sh = self.hang("wall_shelf", W_, a, z=zz, layer=layer, length=ln)
            if sh is not None:
                done += 1
                for _ in range(self.n(per_shelf)):
                    self.top(sh, self.rnd.choice(items), k=0, layer=layer, tries=8)
        return done

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
        """Scattered small things lying on the ground, one merged mesh: straw, leaves, papers, petals, stones, grass tufts, puddles, mud,
        litter, flowers. Not on the marks; on terrain they follow the ground height."""
        region = region or (self.lo[0] + 0.3, self.lo[1] + 0.3, self.hi[0] - 0.3, self.hi[1] - 0.3)
        p = Parts(f"{name}_{kind}", "SET", "floor_detail", kind="prop")
        cm = {"straw": ["#A08848", "#8F7A3E", "#B09A58"], "leaves": ["#8A5A2A", "#B07A2E", "#6A7A2E"], "papers": ["#D8D2C0", "#CFC7B2"], "petals": ["#E8A0B8", "#F4E6EA"],
              "stones": ["#8A8680", "#9A948A", "#74706A", "#A39D90"], "grass": ["#5E8A3C", "#6E9A44", "#7A9A48", "#8AA050"], "puddles": ["#27323A"], "mud": ["#4A3826", "#3E2E20", "#54402C"],
              "litter": ["#F4F1E8", "#B3322C", "#2D6CB0", "#D8A93A", "#7A5A38"], "flowers": ["#E8A0B8", "#F2E27A", "#F6F1E4", "#B58BD6"]}[kind]
        mats = [mat.solid(c, 0.04 if kind == "puddles" else 0.9) for c in cm]
        gm_ = mat.solid("#4C7A3A", 0.9)
        placed = 0
        for _ in range(n * 4):
            if placed >= n:
                break
            x, y = self.rnd.uniform(region[0], region[2]), self.rnd.uniform(region[1], region[3])
            if any(math.hypot(x - mx, y - my) < r * 0.8 for mx, my, r in self.circles):
                continue
            if kind not in ("straw", "leaves", "papers", "petals") and any(rects_overlap((x, y, 0.4 if kind in ("puddles", "mud") else 0.25, 0.4 if kind in ("puddles", "mud") else 0.25, 0.0), r_, 0.05) for r_ in self.rects):
                continue                                          # nothing tall or wet lies under a piece: the audit would read it as the ground it stands on
            z0 = self.zat(x, y)
            m = self.rnd.choice(mats)
            a = self.rnd.uniform(0, 360)
            if kind == "straw":
                p.box((self.rnd.uniform(0.08, 0.18), 0.006, 0.005), (x, y, z0), m, rot=(0, 0, a), bevel=0.0)
            elif kind == "papers":
                p.box((0.21, 0.297, 0.002), (x, y, z0), m, rot=(0, 0, a), bevel=0.0)
            elif kind == "stones":
                s_ = self.rnd.uniform(0.05, 0.22)
                p.ball(s_, (x, y, z0 + s_ * 0.3), m, squash=(self.rnd.uniform(0.8, 1.3), 1, 0.6), sub=1)
            elif kind == "grass":
                for k in range(5):
                    b_ = math.radians(a + 72 * k)
                    h_ = self.rnd.uniform(0.14, 0.32)
                    p.cyl(0.022, h_, (x + math.cos(b_) * 0.02, y + math.sin(b_) * 0.02, z0), m, top=0.002, seg=3, rot=(self.rnd.uniform(8, 22) * math.cos(b_), self.rnd.uniform(8, 22) * math.sin(b_), 0))
            elif kind == "puddles":
                r_ = self.rnd.uniform(0.35, 1.1)
                p.ball(r_, (x, y, z0 + 0.003), m, squash=(1.0, self.rnd.uniform(0.5, 0.9), 0.006), sub=2)
            elif kind == "mud":
                r_ = self.rnd.uniform(0.4, 1.3)
                p.ball(r_, (x, y, z0 + 0.002), m, squash=(1.0, self.rnd.uniform(0.5, 0.9), 0.008), sub=2)
            elif kind == "litter":
                p.box((self.rnd.uniform(0.04, 0.12), self.rnd.uniform(0.04, 0.1), 0.01), (x, y, z0), m, rot=(0, 0, a), bevel=0.0)
            elif kind == "flowers":
                p.rod((x, y, z0), (x, y, z0 + 0.22), 0.004, gm_, seg=3)
                p.ball(0.03, (x, y, z0 + 0.23), m, sub=1)
            else:
                p.box((0.06, 0.04, 0.004), (x, y, z0), m, rot=(0, 0, a), bevel=0.0)
            placed += 1
        if not placed:
            return None
        ob = p.build(at=(0, 0, 0), recentre=False)
        ob["sk_layer"] = "mid"
        ob["sk_floor_detail"] = kind
        self.floor_details += 1
        self.made.append(ob)
        return ob

    # -- open places (exteriors)
    def zat(self, x: float, y: float) -> float:
        """Ground height at (x, y): 0 on a flat stage, the terrain height where a recipe built relief (see arch.terrain)."""
        return self.zfn(x, y) if self.zfn else 0.0

    def put(self, name, x, y, rot: float = 0.0, layer: str = "mid", z=None, reserve=None, avoid=None, foot=None, **kw):
        """Stand a piece with its footprint CENTRE at (x, y) with no stage-bounds test: for what lies beyond the walkable stage (houses, trees,
        far props) or sits on terrain (z defaults to the ground height there). Unless z is given (a wall piece at its mount height) the piece
        is dropped, and None returned, if its footprint would overlap one already placed. reserve=True marks it taken even if it is flat."""
        fn = furnish.REGISTRY[name]["fn"] if name in furnish.REGISTRY else name
        avoid = (z is None or z < 1.0) if avoid is None else avoid           # ground-level pieces keep clear of each other; wall pieces at their mount height do not
        on_terrain = z is None and self.zfn is not None
        z = self.zat(x, y) if z is None else z
        ob = fn(at=(0, 0, z), rot_z=rot, **kw)
        w, d, h = furnish.footprint(ob)
        r = math.radians(rot)
        ob.location = (x - math.sin(r) * d / 2, y + math.cos(r) * d / 2, z)
        rect = footprint_rect(ob)
        if on_terrain:                                    # on relief a piece needs level ground under its feet: sample the ground there, stand on the lowest, skip if it slopes
            fr = foot if foot is not None else min(1.5, min(w, d) / 2)
            zs = [self.zat(x + dx * fr, y + dy * fr) for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))]
            if max(zs) - min(zs) > (0.02 if foot is not None else 0.03):
                self.rejected += 1
                self.reject_log.append((name, f"slope ({x:.1f}, {y:.1f})"))
                self._drop(ob)
                return None
            ob.location.z = min(zs)
        if avoid and h > 0.04 and any(rects_overlap(rect, r_, 0.05) for r_ in self.rects):
            self.rejected += 1
            self.reject_log.append((name, f"put ({x:.1f}, {y:.1f})"))
            self._drop(ob)
            return None
        ob["sk_layer"] = layer
        self.made.append(ob)
        if name.startswith("tree"):
            self.treepts.append((x, y))
        if avoid and h > 0.04:
            self.rects.append(rect)
        return ob

    def reserve(self, x: float, y: float, hw: float, hd: float, rot: float = 0.0):
        """Mark a floor rectangle (centre, half sizes, turn in degrees) as taken."""
        self.rects.append((x, y, hw, hd, math.radians(rot)))

    def add(self, ob, layer: str = "background", rect=None):
        """Record something built elsewhere (an arch.* piece, a smoke column) in the inventory."""
        ob["sk_layer"] = layer
        self.made.append(ob)
        if rect is not None:
            self.rects.append(rect)
        return ob

    def house_row(self, a, b, face_rot: float, styles=("timber", "stone", "brick"), storeys=(1, 3), width=(5.0, 8.0), gap=(0.0, 0.6), skip=(), awning: bool = False,
                  layer: str = "background", signs: float = 0.35, smoke_p: float = 0.5, flowers: float = 0.5, tints=None, lit: float = 0.5, night: bool = False, depth: float = 6.0,
                  roofs=None, gaps_at=()):
        """A terrace of house fronts along the segment a -> b, every front turned to face_rot (0 faces -Y, 90 faces +X, 180 faces +Y,
        -90 faces -X). Heights, widths, styles, tints, shutters and flower boxes vary; lit windows, a door lantern, a hanging sign and a
        chimney with smoke come by chance. gaps_at: distances (m) from a where a street opens (no house covers it). Returns [(root, x, y, w)]."""
        rnd = self.rnd
        ax, ay = a
        L = math.hypot(b[0] - ax, b[1] - ay)
        ux, uy = (b[0] - ax) / L, (b[1] - ay) / L
        r = math.radians(face_rot)
        tints = tints or [None, "#E6D8C0", "#D8C0A8", "#C9D4C0", "#E8C9B0", "#BFC8D4"]
        out = []
        s = 0.0
        while s < L - 3.5:
            wd = rnd.uniform(*width)
            if s + wd > L:
                break
            mid = s + wd / 2
            if any(g0 - wd / 2 < mid < g1 + wd / 2 for g0, g1 in gaps_at):
                s += 1.0
                continue
            st = rnd.choice(list(styles))
            ns = rnd.randint(storeys[0], storeys[1]) if st != "modern" else rnd.randint(max(storeys[0], 2), storeys[1])
            x, y = ax + ux * mid, ay + uy * mid
            hf = arch.house_front(storeys=ns, style=st, width=wd, depth=depth, at=(x, y, self.zat(x, y)), rot_z=face_rot, awning=(rnd.choice(["#B3322C", "#2D6CB0", "#D8A93A", "#3F8F5A"]) if awning and rnd.random() < 0.6 else None),
                                  seed=rnd.randint(0, 999), door_type=rnd.choice(["panel", "plank"]), tint=rnd.choice(tints), lit=1.35 if night else lit, night=night,
                                  flowerbox=rnd.random() < flowers, shutter_tint=rnd.choice(["#6B4A2E", "#3F5F3A", "#2D4A6B", "#8A3A2A"]), roof_surface=(rnd.choice(roofs) if roofs else None))
            hf["sk_layer"] = layer
            self.made.append(hf)
            fx, fy = -math.sin(r), math.cos(r)               # house local +Y in the world: the way "back" runs
            self.rects.append((x + fx * depth / 2, y + fy * depth / 2, wd / 2, depth / 2 + 0.2, r))
            dxw, dyw = math.cos(r), math.sin(r)                # house local +X in the world
            # a lantern beside the door (the door stands at local x = 0.2 w) and, sometimes, a sign hung between the door and the next window
            lx = wd * 0.2 + 0.8
            if night or rnd.random() < 0.5:
                self.put("torch_wall", x + dxw * lx, y + dyw * lx, face_rot, layer, z=2.1, power=60.0 if night else 30.0)
            if rnd.random() < signs:
                sx_ = -wd * 0.2
                self.put(rnd.choice(["hanging_sign", "sign_board"]), x + dxw * sx_, y + dyw * sx_, face_rot, layer, z=2.5)
            if "sk_chimney" in hf.keys() and rnd.random() < smoke_p:
                cxl, cyl, czl = hf["sk_chimney"]
                cxw, cyw = x + dxw * cxl + fx * cyl, y + dyw * cxl + fy * cyl
                self.add(arch.smoke((cxw, cyw, czl + self.zat(x, y)), height=rnd.uniform(5.0, 8.0), puffs=11, width=0.35, drift=(rnd.uniform(0.8, 2.2), rnd.uniform(-0.6, 0.6)),
                                    color="#B9B6B0" if not night else "#4A4E5E", alpha=0.32 if not night else 0.28, seed=rnd.randint(0, 99)), "beyond")
            out.append((hf, x, y, wd))
            s += wd + rnd.uniform(*gap)
        return out

    def trees(self, n, region, kinds=("tree_round", "tree_pine", "tree_round"), layer: str = "background", avoid=(), size=(5.0, 8.5), autumn: bool = False, bushes: int = 0):
        """Trees and bushes scattered over a rectangle (x0, y0, x1, y1), away from the circles in avoid=[(x, y, r)] and from each other."""
        rnd = self.rnd
        pts = []
        for _ in range(n * 30):
            if len(pts) >= n:
                break
            x, y = rnd.uniform(region[0], region[2]), rnd.uniform(region[1], region[3])
            if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid) or any(math.hypot(x - px, y - py) < 4.5 for px, py in pts + self.treepts):
                continue
            pts.append((x, y))
            k = rnd.choice(kinds)
            h = rnd.uniform(*size)
            if k == "tree_pine":
                self.put(k, x, y, 0.0, layer, foot=0.4, height=h, radius=h * 0.22, seed=rnd.randint(0, 99))
            else:
                self.put(k, x, y, 0.0, layer, foot=0.4, height=h, crown=h * 0.4, seed=rnd.randint(0, 99), autumn=autumn)
        for _ in range(bushes * 20):
            if bushes <= 0:
                break
            x, y = rnd.uniform(region[0], region[2]), rnd.uniform(region[1], region[3])
            if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid):
                continue
            self.put("bush", x, y, 0.0, layer, size=rnd.uniform(0.7, 1.3), seed=rnd.randint(0, 99), flowers=rnd.random() < 0.3)
            bushes -= 1
        return pts

    def path(self, pts, width: float = 2.4, surface: str = "earth_path", z: float = -0.004, name: str = "path"):
        """A worn track along a polyline of (x, y) points: flat strips a hair above the ground. One merged mesh, not counted as a prop."""
        p = Parts(name, "SET", "ground_path", kind="shell")
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
            p.box((L + width * 0.4, width, 0.016), ((x0 + x1) / 2, (y0 + y1) / 2, z), surface, rot=(0, 0, ang), bevel=0.0)
        ob = p.build(at=(0, 0, 0), recentre=False)
        self.made.append(ob)
        return ob

    def fire_smoke(self, x, y, z=0.0, height: float = 6.0, drift=(1.5, 0.3), night: bool = False, seed: int = 0):
        """A smoke column rising from a fire at (x, y)."""
        return self.add(arch.smoke((x, y, z + 0.6), height=height, puffs=12, width=0.3, drift=drift, color="#8A8A8E" if not night else "#4A4A54", alpha=0.34, seed=seed or self.rnd.randint(0, 99),
                                   glow=0.35 if night else 0.0), "beyond")

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
                lights.dust(lo, hi, 130, size=0.009, strength=0.6, seed=self.seed + k)
                k += 1
            if k == 0 and self.h:
                lights.dust((self.lo[0] + 1, self.lo[1] + 1, 0.5), (self.hi[0] - 1, self.hi[1] - 1, self.h - 0.4), 160, size=0.009, strength=0.6, seed=self.seed)
                k = 1
        else:
            lights.dust((self.lo[0], self.lo[1], 0.5), (self.hi[0], self.hi[1], 6.0), 160, size=0.03, strength=0.6, seed=self.seed)
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
def room(room_, theme_name: str, marks=None, density: float = 1.0, seed: int = 0, keep_clear: float = 0.9, cam=None, reserve=(), autofill_: bool = True, night: bool = False, **opts) -> dict:
    """Dress an enclosed room (arch.room) with a theme. cam: where the wide shot stands (default: the -Y side).
    reserve: floor rectangles (x0, y0, x1, y1) the recipe must leave alone (a glass meeting room you built yourself)."""
    if theme_name not in THEMES or THEMES[theme_name]["kind"] != "room":
        raise KeyError(f"no room theme '{theme_name}'. Room themes: {', '.join(k for k, v in THEMES.items() if v['kind'] == 'room')}")
    D = Dresser(None, theme_name, marks, density, seed, keep_clear, cam, room_)
    D.night, D.opts = night, opts
    for (rx0, ry0, rx1, ry1) in reserve:
        D.rects.append(((rx0 + rx1) / 2, (ry0 + ry1) / 2, (rx1 - rx0) / 2, (ry1 - ry0) / 2, 0.0))
    THEMES[theme_name]["fn"](D)
    if autofill_:
        autofill(D, POOLS.get(theme_name, {}))
    D.dust()
    lights.limit_shadows()
    inv = D.inventory()
    room_.inventory = inv
    room_.refs = D.refs                                                   # what the recipe handed back (doors, seats, a screen...), by name
    return inv


def exterior(area, theme_name: str, marks=None, density: float = 1.0, seed: int = 0, keep_clear: float = 0.9, cam=None, autofill_: bool = True, night: bool = False, **opts) -> dict:
    """Dress an open place. area = dict(lo=(x0, y0), hi=(x1, y1)) in metres: the walkable stage; the recipe builds the street or ground
    it needs, the buildings and props around it, and the skyline beyond."""
    if theme_name not in THEMES or THEMES[theme_name]["kind"] != "exterior":
        raise KeyError(f"no exterior theme '{theme_name}'. Exterior themes: {', '.join(k for k, v in THEMES.items() if v['kind'] == 'exterior')}")
    D = Dresser(area, theme_name, marks, density, seed, keep_clear, cam, None)
    D.night, D.opts = night, opts
    THEMES[theme_name]["fn"](D)
    if autofill_:
        autofill(D, POOLS.get(theme_name, {}), floor=0.1)
    D.dust()
    lights.limit_shadows(0)
    inv = D.inventory()
    inv["refs"] = D.refs                                                  # what the recipe handed back (the doors, the canopy...), by name
    return inv


POOLS = {
    "throne_room": dict(top=["goblet", "tankard", "table_candle", "scroll", "book_stack", "papers_stack", "bottle", "crockery_set"], floor=["barrel", "sack", "crate", "chest", "stool"],
                        wall=["shield_wall", "banner", "tapestry"]),
    "great_hall": dict(top=["goblet", "tankard", "table_candle", "bread_basket", "bottle", "crockery_set", "jug"], floor=["barrel", "sack", "crate", "chest", "stool", "bench"], wall=["shield_wall", "banner", "painting_framed"]),
    "castle_kitchen": dict(shelf=["jug", "bottle", "basket", "mugs", "crockery_set", "bucket", "bread_basket"], top=["pots_and_pans", "bread_basket", "fruit_crate", "crockery_set", "market_goods", "mugs", "jug", "basket", "bottle", "cloth_bolts", "bucket", "scroll", "papers_stack"], floor=["barrel", "sack", "crate", "basket", "stool", "bucket"],
                           wall=["shelf_jars", "bottle_shelf", "wall_sconce"]),
    "tavern": dict(shelf=["tankard", "bottle", "jug", "mugs", "table_candle", "crockery_set"], top=["tankard", "bottle", "jug", "table_candle", "crockery_set", "bread_basket", "mugs", "scroll", "papers_stack"], floor=["barrel", "stool", "crate", "sack", "potted_plant", "bucket"], wall=["bottle_shelf", "painting_framed", "notice_board", "wall_sconce", "dartboard"]),
    "peasant_cottage": dict(shelf=["jug", "bottle", "basket", "mugs", "crockery_set", "bucket", "table_candle", "bread_basket"], top=["crockery_set", "jug", "basket", "bread_basket", "mugs", "table_candle", "bottle", "bucket"], floor=["sack", "basket", "crate", "stool", "broom", "bucket"], wall=["shelf_jars", "painting_framed", "wall_sconce"]),
    "office_open_plan": dict(top=["papers_stack", "mugs", "book_stack", "laptop", "office_phone", "vase_flowers"], floor=["potted_plant", "bin", "filing_cabinet"], wall=["poster", "painting_framed", "notice_board"]),
    "office_private": dict(shelf=["book_stack", "photo_frame", "globe", "vase_flowers", "mugs", "papers_stack", "desk_lamp"], top=["papers_stack", "mugs", "book_stack", "laptop", "vase_flowers", "office_phone", "desk_lamp", "globe", "photo_frame"], floor=["potted_plant", "bin", "filing_cabinet", "chair_dining"], wall=["painting_framed", "poster", "wall_clock", "notice_board"]),
    "home_living_room": dict(shelf=["book_stack", "photo_frame", "vase_flowers", "table_candle", "globe", "mugs", "basket"], top=["vase_flowers", "mugs", "book_stack", "papers_stack", "table_candle", "photo_frame", "globe"], floor=["potted_plant", "floor_lamp", "stool", "basket"], wall=["painting_framed", "poster", "wall_sconce", "wall_clock"]),
    "home_kitchen": dict(shelf=["mugs", "jug", "bottle", "crockery_set", "kettle", "bread_basket", "vase_flowers", "basket"], top=["mugs", "kettle", "bread_basket", "fruit_crate", "crockery_set", "pots_and_pans", "jug", "vase_flowers"], floor=["bin", "potted_plant", "stool", "basket"], wall=["shelf_jars", "painting_framed", "poster", "wall_clock"]),
    "shop_interior": dict(shelf=["jug", "bottle", "basket", "market_goods", "bread_basket", "cloth_bolts", "balance_scales", "book_stack"], top=["basket", "market_goods", "bread_basket", "jug", "scroll", "book_stack", "cloth_bolts", "fruit_crate", "bottle", "balance_scales"], floor=["barrel", "sack", "crate", "basket", "potted_plant", "bucket"],
                          wall=["bottle_shelf", "shelf_jars", "hanging_sign", "poster", "painting_framed"]),
    "market_street": dict(top=["jug", "basket", "bucket", "bottle", "bread_basket", "market_goods"], floor=["barrel", "crate", "sack", "hay_bale", "basket", "bucket"]),
    "village_square": dict(top=["jug", "basket", "bucket", "bottle", "bread_basket"], floor=["barrel", "crate", "sack", "hay_bale", "bench", "bucket"]),
    "army_camp": dict(top=["tankard", "jug", "bucket", "bread_basket", "arrow_bundle"], floor=["barrel", "crate", "sack", "hay_bale", "stakes", "shield_pile", "arrow_bundle", "bucket"]),
    "battlefield": dict(floor=["shield_pile", "arrow_bundle", "stakes", "crate", "barrel", "hay_bale"]),
    "city_street": dict(floor=["bin", "potted_plant", "bench", "hydrant"]),
}
WALL_DEFAULTS = {"bottle_shelf": dict(length=1.2, rows=2), "dartboard": dict(), "painting_framed": dict(width=0.8, height=0.6), "poster": dict(width=0.5, height=0.7), "shield_wall": dict(), "shelf_jars": dict(length=1.1), "wall_clock": dict(), "hanging_sign": dict(), "notice_board": dict(width=0.9, height=0.7),
                 "wall_sconce": dict(), "banner": dict(size=(0.8, 2.2)), "tapestry": dict(width=1.4, height=2.0)}


SEAT_LABELS = ("seat", "cushion")                                        # tops that are for sitting on: autofill never scatters on them
WORK_ONLY = ("laptop", "laptop_open", "laptop_closed")                  # small pieces that only belong where someone works...
WORK_TOPS = ("desk", "desk_full", "table", "counter", "worktop")        # ...on these tops


def autofill(D, pool: dict, tops: int = 7, walls: int = 3, floor: float = 0.34):
    """A last pass that lifts a recipe to the density of a lived-in place: small things on every declared top that still has room,
    pictures and shelves on the free stretches of each wall, and loose things about the floor in proportion to its area.
    Everything is still placed by the same rules (free spot, on a surface, clear of the marks)."""
    rnd = D.rnd
    area0 = (D.hi[0] - D.lo[0]) * (D.hi[1] - D.lo[1])
    if D.R is not None and pool.get("shelf") and area0 < 70:               # shelves first, while the walls still have room: every item on them is an object
        D.shelves(pool["shelf"], n=int(round(area0 / 4.5 * D.density)), per_shelf=5)
    if pool.get("top"):
        for ob in [o for o in D.made if o.get("sk_tops") and o.get("sk_type") not in ("desk_office", "monitor_keyboard")]:
            for _ in range(D.n(tops)):
                nm = rnd.choice(pool["top"])
                # nothing is left lying on a seat, and a laptop only goes on something you work at
                D.top(ob, nm, k=-1, tries=12, avoid=SEAT_LABELS, labels=WORK_TOPS if nm in WORK_ONLY else None)
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
        D.floor(nm, x, y, rnd.choice([0, 90, 180, 270]) + rnd.uniform(-10, 10), "foreground" if near else "mid", margin=0.12)


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


def _hang_from_beams(D, items, y_frac=(0.35, 0.62)):
    """Hang pieces (herbs, pot racks, game, lanterns) from the ceiling at spread-out spots clear of the marks: items = [(name, kwargs), ...]."""
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    k = 0
    for name, kw in items:
        tx = x0 + (x1 - x0) * (0.15 + 0.7 * ((k * 0.37) % 1.0))
        ty = y0 + (y1 - y0) * (y_frac[0] + (y_frac[1] - y_frac[0]) * ((k * 0.61) % 1.0))
        D.ceiling_piece(name, tx, ty, "mid", **kw)
        k += 1


@theme("castle_kitchen", ["medieval", "renaissance", "fantasy"])
def castle_kitchen(D):
    """A castle kitchen: a great hearth with a roasting spit and a cauldron, work tables heaped with food, shelves of bottles and jars, game and
    herbs and pots hanging from the beams, barrels and sacks, a pump by the yard door."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    fw = min(3.4, w * 0.4)
    fp = arch.fireplace(fw, 2.0, 1.0, at=(cx, y1, 0), rot_z=0, chimney_h=h, spit=True)
    arch.tag_wall(fp, R.name, "N")
    fp["sk_layer"] = "background"
    D.made.append(fp)
    D.walls["N"].append((-fw / 2 - 0.2, fw / 2 + 0.2, 0, h))
    D.rects.append((cx, y1 - 0.6, fw / 2 + 0.1, 0.6, 0.0))
    D.floor("cauldron", cx + fw / 2 + 1.7, y1 - 1.4, 0, "background", margin=0.0, marks=False)
    D.floor("woodpile", cx - fw / 2 - 1.1, y1 - 0.5, 0, "background", margin=0.05, length=1.3)
    D.floor("fireplace_set", cx - fw / 2 - 0.4, y1 - 1.0, 20, "background", margin=0.0, marks=False)
    D.floor("pots_and_pans", cx - 0.9, y1 - 1.7, 0, "background", margin=0.0, marks=False)
    D.hang("shelf_jars", "N", -fw / 2 - 2.7, z=1.9, layer="background", length=1.3, seed=1)
    D.hang("bottle_shelf", "N", fw / 2 + 2.7, z=1.7, layer="background", length=1.4, rows=2, seed=2)
    # the long walls: shelving, a sideboard, barrels; the west wall carries the pump and the yard door
    for W, sx in (("W", -1), ("E", 1)):
        for k, a in enumerate((-d * 0.3, d * 0.0, d * 0.3)):
            if W == "E" or k != 1:
                D.hang("bottle_shelf" if k % 2 == 0 else "shelf_jars", W, a, z=1.7 if k % 2 == 0 else 2.0, layer="background", **({"length": 1.4, "rows": 3, "seed": k + 4} if k % 2 == 0 else {"length": 1.3, "seed": k}))
        D.against("sideboard", W, -d * 0.18, "background", length=1.5)
    D.against_any("cabinet", "E", near=d * 0.18, layer="background")
    D.against_any("water_pump", "W", near=d * 0.12, layer="background")
    D.floor("bucket", x0 + 1.5, cy + d * 0.12 - 0.6, 0, "mid", margin=0.05, marks=False)
    for k in range(D.n(3)):
        D.floor("barrel", x1 - 0.7, y0 + 1.2 + 0.78 * k, 0, "background", margin=0.04)
    D.floor("keg", x1 - 1.3, y1 - 2.4, 0, "background", margin=0.05)
    # work tables
    t1 = D.floor("banquet_table", cx - 0.2, cy + 0.6, 0, "mid", length=min(3.2, w * 0.38), margin=0.5)
    if t1:
        D.clutter(t1, ["pots_and_pans", "bread_basket", "fruit_crate", "crockery_set", "market_goods", "mugs", "jug", "basket", "bottle", "scroll"], 9)
        for sx in (-1.0, 0.0, 1.0):
            D.floor("stool", cx - 0.2 + sx, cy + 1.45, 0, "mid", margin=0.0, marks=False)
    t2 = D.floor("trestle_table", cx + 0.4, y0 + 2.9, 0, "foreground", length=2.2, width=0.85, margin=0.4)
    if t2:
        D.clutter(t2, ["fruit_crate", "basket", "cloth_bolts", "bread_basket", "jug", "market_goods", "papers_stack", "scroll"], 8)
        D.floor("stool", cx + 0.1, y0 + 3.75, 0, "foreground", margin=0.0, marks=False)
    for k in range(D.n(5)):
        D.floor("barrel" if k % 2 else "sack", x0 + 0.7 + (k // 2) * 0.85, y0 + 1.0 + (k % 2) * 0.1, 0, "foreground", margin=0.05)
    for k in range(D.n(3)):
        D.floor("crate", x1 - 0.8 - k * 0.7, y0 + 1.0, 0, "foreground", size=0.55, margin=0.05)
    D.floor("basket", x1 - 1.0, y0 + 2.2, 0, "foreground")
    D.floor("potted_plant", x0 + 0.8, y0 + 2.2, 0, "foreground", height=0.9)
    D.floor("candelabra", x0 + 1.3, y1 - 1.4, 0, "background", margin=0.05, marks=False)
    D.floor("candelabra", x1 - 1.3, y1 - 1.2, 0, "background", margin=0.05, marks=False)
    D.floor("bench", x1 - 0.9, cy + 1.6, 90, "background", length=1.6, margin=0.05, marks=False)
    D.floor("hay_bale", x0 + 1.0, cy - 2.2, 0, "mid", margin=0.05)
    # overhead
    _hang_from_beams(D, [("pot_rack", dict(length=1.5)), ("pot_rack", dict(length=1.3)), ("herb_bundle", dict(seed=1)), ("herb_bundle", dict(seed=2, n=5)), ("hanging_game", dict(seed=1)),
                         ("hanging_game", dict(seed=2)), ("lantern", dict(hanging=True)), ("lantern", dict(hanging=True)), ("herb_bundle", dict(seed=5, n=5)),
                         ("herb_bundle", dict(seed=6)), ("pot_rack", dict(length=1.1)), ("hanging_game", dict(seed=7))])
    D.ceiling_piece("chandelier", cx, cy - 1.8, "mid", radius=0.6, drop=min(1.4, h * 0.3), candles=8)
    _sconces(D, "EW", z=2.4, step=3.4, margin=1.6)
    D.hang("notice_board", "E", d * 0.38, z=1.4, layer="background", width=0.8, height=0.6, seed=2)
    D.hang("hanging_sign", "S", -w * 0.08, z=2.5, layer="foreground")
    for sx in (-1, 1):                                              # the castle's colours either side of the chimney breast
        D.hang("banner", "N", sx * (fw / 2 + 0.75), z=h - 0.7, layer="background", size=(0.7, 2.0), emblem="lion", color=("#A3231F", "#2D4A6B")[sx > 0])
    D.hang("notice_board", "W", -d * 0.3, z=1.4, layer="background", width=0.8, height=0.6, seed=4)
    D.hang("shield_wall", "E", d * 0.05, z=2.6, layer="background", color="#2D4A6B")
    for oid, hd in R.openings.items():
        if hd["kind"] == "door":
            D.hang("torch_wall", hd["wall"], D._along(hd["wall"], hd["centre"]) + hd["w"] / 2 + 0.7, z=2.3)
    D.floor_detail("straw", D.n(80), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 2.0))
    D.floor_detail("papers", D.n(4), region=(x0 + 1, y0 + 1, x1 - 1, y1 - 2))


@theme("tavern", ["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"])
def tavern(D):
    """A tavern: a bar with shelves of bottles and kegs behind it, tables, stools and benches, a hearth, a gallery reached by stairs with a
    back door under it, beams with hanging lanterns, a dartboard, notices, barrels and straw."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    # ---- the bar along the north wall, the back-bar behind it
    bl = min(4.6, w * 0.45)
    bx = cx - w * 0.08
    bar = D.floor("bar_counter", bx, y1 - 1.75, 0, "background", length=bl, margin=0.0, marks=False)
    if bar:
        D.clutter(bar, ["tankard", "tankard", "tankard", "bottle", "jug", "table_candle", "bread_basket", "mugs", "bottle", "crockery_set", "scroll", "papers_stack"], 11)
        for sx in (-1.7, -0.6, 0.5, 1.6):
            D.floor("stool", bx + sx, y1 - 2.85, 0, "mid", margin=0.0, marks=False)
    for k, a in enumerate((-bl * 0.34, 0.0, bl * 0.34)):
        D.hang("bottle_shelf", "N", bx - cx + a, z=1.35 + 0.0, layer="background", length=1.4, rows=3, seed=k + 1)
    D.against_any("keg", "N", near=bx - cx - bl / 2 - 0.9, layer="background")
    D.against_any("barrel", "N", near=bx - cx + bl / 2 + 0.7, layer="background")
    D.against_any("barrel", "N", near=bx - cx + bl / 2 + 1.5, layer="background")
    D.hang("hanging_sign", "N", bx - cx + bl * 0.5 + 0.2, z=2.4, layer="background")
    D.hang("dartboard", "N", bx - cx - bl / 2 - 1.8, z=1.65, layer="background")
    D.hang("notice_board", "N", bx - cx - bl / 2 - 3.0, z=1.35, layer="background", width=0.8, height=0.65, seed=11)
    D.hang("banner", "N", bx - cx + bl / 2 + 1.9, z=h - 0.5, layer="background", size=(0.6, 1.5), emblem="tree")
    D.hang("painting_framed", "N", bx - cx + bl / 2 + 1.3, z=1.8, layer="background", width=0.7, height=0.55, seed=12)
    # ---- the hearth on the west wall with its chairs and wood
    fp = arch.fireplace(2.4, 1.5, 0.8, at=(x0, cy + 0.6, 0), rot_z=90, chimney_h=h)
    arch.tag_wall(fp, R.name, "W")
    fp["sk_layer"] = "background"
    D.made.append(fp)
    D.walls["W"].append((-0.8, 2.0, 0, h))
    D.rects.append((x0 + 0.5, cy + 0.6, 0.5, 1.3, 0.0))
    D.floor("chair_arm", x0 + 1.9, cy + 0.1, -70, "mid", margin=0.0, marks=False)
    D.floor("chair_arm", x0 + 1.9, cy + 1.4, -110, "mid", margin=0.0, marks=False)
    D.floor("fireplace_set", x0 + 1.2, cy - 0.9, 0, "background", margin=0.0, marks=False)
    D.floor("woodpile", x0 + 0.5, cy + 2.8, 90, "background", margin=0.05)
    D.floor("rug", x0 + 2.4, cy + 0.6, 90, "mid", flat=True, size=(1.8, 2.4), surface="carpet_red", inner="#6A2A22")
    # ---- the east wall: a gallery on posts, a stair up to it, the back door beneath
    gal_w = 2.2
    gz = 2.45
    sy = y0 + 0.9                                                # the stair starts here and climbs along the east wall
    gy0 = sy + 3.0
    gal_len = max(2.0, min(5.0, y1 - 0.4 - gy0))
    gy1 = gy0 + gal_len
    gal = arch.platform((gal_len, gal_w), 0.16, at=(x1 - gal_w, (gy0 + gy1) / 2, gz), rot_z=90, surface="oak_planks", name="gallery_floor")
    for ob in (gal,):
        ob["sk_mount"] = 1
        ob["sk_layer"] = "background"
        D.made.append(ob)
    for yy in (gy0 + 0.2, (gy0 + gy1) / 2, gy1 - 0.2):
        post = arch.column("square", gz, 0.1, at=(x1 - gal_w + 0.05, yy, 0), surface="dark_timber", capital=False, base=False, name="gallery_post")
        post["sk_layer"] = "background"
        D.made.append(post)
        D.rects.append((x1 - gal_w + 0.05, yy, 0.3, 0.3, 0.0))
    rail = arch.balcony_rail(gal_len, 1.0, at=(x1 - gal_w + 0.05, (gy0 + gy1) / 2, gz + 0.16), rot_z=90, name="gallery_rail")
    rail["sk_layer"] = "background"
    rail["sk_mount"] = 1
    D.made.append(rail)
    D.rects.append((x1 - gal_w / 2, (gy0 + gy1) / 2, gal_w / 2, gal_len / 2, 0.0))
    st = arch.stairs(3.0, gz + 0.16, 14, 1.0, at=(x1 - 0.6, sy, 0), rot_z=0.0, surface="oak_planks", rail="dark_timber", name="gallery_stairs")
    st["sk_layer"] = "background"
    D.made.append(st)
    D.rects.append((x1 - 0.6, sy + 1.5, 0.55, 1.5, 0.0))
    D.walls["E"].append((sy - cy - 0.2, gy1 - cy, 0, gz + 1.2))
    for yy in (gy0 + 0.9, gy1 - 0.9):
        D.floor("barrel", x1 - 0.7, yy, 0, "background", margin=0.04)
    D.floor("chest", x1 - 0.8, (gy0 + gy1) / 2, 90, "background", margin=0.05)
    # ---- tables, stools and benches in the room
    spots = [(-w * 0.17, -d * 0.2, 0), (w * 0.12, -d * 0.22, 90), (-w * 0.2, -d * 0.02, 90), (w * 0.17, -d * 0.02, 0), (w * 0.0, -d * 0.36, 90), (-w * 0.05, d * 0.13, 0)]
    for i, (dx, dy, rot) in enumerate(spots):
        t = D.floor("trestle_table", cx + dx, cy + dy, rot, "foreground" if dy < -d * 0.3 else "mid", length=1.7, width=0.8, margin=0.3)
        if t:
            for sx in (-0.55, 0.55):
                if rot == 0:
                    D.floor("stool", cx + dx + sx, cy + dy - 0.7, 0, "mid", margin=0.0, marks=False)
                    D.floor("stool", cx + dx + sx, cy + dy + 0.7, 0, "mid", margin=0.0, marks=False)
                else:
                    D.floor("stool", cx + dx - 0.7, cy + dy + sx, 0, "mid", margin=0.0, marks=False)
                    D.floor("stool", cx + dx + 0.7, cy + dy + sx, 0, "mid", margin=0.0, marks=False)
            D.clutter(t, ["tankard", "tankard", "table_candle", "crockery_set", "bottle", "bread_basket", "mugs", "scroll", "papers_stack"], 6)
    D.floor("bench", cx - w * 0.38, cy - d * 0.22, 90, "mid", length=2.0, margin=0.1, back=True, marks=False)
    # ---- walls, beams, lights
    D.hang("notice_board", "S", w * 0.25, z=1.3, layer="foreground", width=0.9, height=0.7, seed=3)
    D.hang("painting_framed", "S", -w * 0.2, z=1.6, layer="foreground", width=0.8, height=0.65, seed=4)
    D.hang("shield_wall", "W", -d * 0.3, z=2.1, layer="background", color="#2D4A6B")
    D.hang("tapestry", "E", -d * 0.34, z=1.1, layer="background", width=1.1, height=1.6, seed=6)
    _sconces(D, "S", z=2.3, step=3.0, margin=1.5, layer="foreground")
    _hang_from_beams(D, [("lantern", dict(hanging=True)), ("lantern", dict(hanging=True)), ("lantern", dict(hanging=True)), ("herb_bundle", dict(seed=3)), ("pot_rack", dict(length=1.2))], (0.25, 0.6))
    D.ceiling_piece("chandelier", cx + 1.0, cy - 0.6, "mid", radius=0.6, drop=min(1.2, h * 0.3), candles=8)
    D.floor("potted_plant", x1 - 0.7, y0 + 0.8, 0, "foreground", height=1.3)
    D.floor("crate", x0 + 0.8, y0 + 1.0, 0, "foreground", size=0.5)
    D.floor("barrel", x0 + 1.6, y0 + 0.8, 0, "foreground", margin=0.05)
    D.floor_detail("straw", D.n(70), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 2.2))
    D.floor_detail("papers", D.n(5), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5))


@theme("peasant_cottage", ["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"])
def peasant_cottage(D):
    """A cottage: one warm room with a stone hearth and cauldron, a bed and a chest, a table with stools and a bench, a spinning wheel, herbs and
    game hung from the beams, shelves of jars, baskets, sacks and firewood, a rag rug."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    fw = min(2.0, w * 0.32)
    fp = arch.fireplace(fw, 1.2, 0.7, at=(cx, y1, 0), rot_z=0, chimney_h=h, surface="fieldstone")
    arch.tag_wall(fp, R.name, "N")
    fp["sk_layer"] = "background"
    D.made.append(fp)
    D.walls["N"].append((-fw / 2 - 0.15, fw / 2 + 0.15, 0, h))
    D.rects.append((cx, y1 - 0.45, fw / 2, 0.45, 0.0))
    D.floor("cauldron", cx - 0.1, y1 - 0.8, 0, "background", margin=0.0, marks=False, z=0.04)
    D.floor("fireplace_set", cx - fw / 2 - 0.35, y1 - 0.6, 15, "background", margin=0.0, marks=False)
    D.floor("woodpile", cx + fw / 2 + 0.9, y1 - 0.45, 0, "background", margin=0.05, length=1.2)
    D.floor("chair_arm", cx - fw / 2 - 1.0, y1 - 1.2, 30, "mid", margin=0.0, marks=False)
    D.against_any("bed", "W", near=d * 0.1, layer="background", width=1.1, length=1.9, blanket="#6A4A3A", posts=False)
    D.against_any("chest", "W", near=-d * 0.28, layer="background")
    D.against_any("cabinet", "E", near=d * 0.1, layer="background", width=0.9, height=1.7)
    D.against_any("sideboard", "E", near=-d * 0.25, layer="background", length=1.0)
    D.hang("shelf_jars", "E", -d * 0.05, z=1.7, layer="background", length=1.1, seed=2)
    D.hang("bottle_shelf", "W", -d * 0.12, z=1.6, layer="background", length=1.0, rows=2, seed=3)
    D.hang("hanging_sign", "S", -w * 0.25, z=2.1, layer="foreground")
    t = D.floor("trestle_table", cx + 0.2, cy - 0.3, 0, "mid", length=1.6, width=0.75, margin=0.45)
    if t:
        D.clutter(t, ["crockery_set", "bread_basket", "jug", "table_candle", "mugs", "basket", "scroll"], 6)
        D.floor("stool", cx - 0.1, cy - 1.0, 0, "mid", margin=0.0, marks=False)
        D.floor("stool", cx + 0.7, cy - 1.0, 0, "mid", margin=0.0, marks=False)
        D.floor("bench", cx + 0.2, cy + 0.45, 0, "mid", margin=0.0, length=1.5, marks=False)
    D.floor("spinning_wheel", x0 + 1.0, y1 - 1.5, 90, "mid")
    D.floor("broom", x1 - 0.5, y0 + 1.0, 0, "foreground", marks=False)
    D.floor("bucket", x1 - 0.9, y0 + 1.6, 0, "foreground", marks=False)
    for k in range(D.n(3)):
        D.floor("sack", x1 - 0.7, y1 - 0.8 - k * 0.7, 0, "background", margin=0.0)
    D.floor("basket", x0 + 0.8, y0 + 1.0, 0, "foreground")
    D.floor("crate", x0 + 0.8, y0 + 1.8, 0, "foreground", size=0.5)
    D.floor("barrel", x0 + 1.6, y0 + 0.8, 0, "foreground", margin=0.04)
    D.floor("rug", cx + 0.2, cy + 0.9, 0, "mid", flat=True, size=(2.0, 1.4), surface="carpet_red", inner="#6A4A3A", border="#B08A4E")
    D.hang("wall_sconce", "E", d * 0.35, z=1.8, layer="background")
    D.hang("wall_sconce", "W", -d * 0.38, z=1.8, layer="background")
    D.hang("painting_framed", "S", w * 0.1, z=1.5, layer="foreground", width=0.55, height=0.45)
    D.hang("notice_board", "E", d * 0.33, z=1.4, layer="background", width=0.6, height=0.5, seed=7)
    _hang_from_beams(D, [("herb_bundle", dict(seed=1)), ("herb_bundle", dict(seed=2, n=5)), ("hanging_game", dict(seed=3)), ("pot_rack", dict(length=1.0)), ("lantern", dict(hanging=True))], (0.3, 0.7))
    D.floor_detail("straw", D.n(90), region=(x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3))
    D.floor_detail("papers", D.n(3), region=(x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3))


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
    """A manager's office: an executive desk with a screen, lamp, globe and framed photographs, three bookcases, a credenza with a vase and trophies,
    a sofa corner with a coffee table, plants, a whiteboard, framed pictures and certificates, a rug, ceiling panels, floor and desk lamps."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    for i in range(2):
        D.ceiling_piece("ceiling_light_panel", cx - w * 0.2 + i * w * 0.4, cy + 0.4, "mid", size=(1.2, 0.6), power=45.0)
    D.floor("rug", cx, cy + 0.1, 0, "mid", flat=True, size=(min(3.6, w - 1.2), 2.6), surface="carpet_red", inner="#3A4A5A", border="#C9A44A")
    ds = D.floor("desk_office", cx, y1 - 2.3, 180, "background", length=2.1, depth=0.95, color="#6B4A30", margin=0.0)
    if ds:
        D.top(ds, "monitor_keyboard", k=1)
        for nm in ("papers_stack", "mugs", "office_phone", "desk_lamp", "book_stack", "globe", "photo_frame", "photo_frame"):
            D.top(ds, nm, k=1)
        D.floor("chair_arm", cx, y1 - 1.35, 0, "background", margin=0.0, marks=False)
    for sx in (-0.75, 0.75):
        D.floor("chair_dining", cx + sx, y1 - 3.45, 0, "mid", margin=0.0, marks=False)
    for k, a in enumerate((-w * 0.33, w * 0.0 - 1.3, w * 0.33)):
        D.against_any("bookcase", "N", near=a + (0.6 if k == 1 else 0.0), layer="background", width=1.2, seed=k + 1)
    D.hang("painting_framed", "N", 0.0, z=1.9, layer="background", width=1.4, height=0.9, seed=2)
    D.hang("painting_framed", "N", w * 0.2 + 0.4, z=1.7, layer="background", width=0.5, height=0.65, seed=8)
    D.hang("painting_framed", "N", -w * 0.2 - 0.4, z=1.7, layer="background", width=0.5, height=0.65, seed=9)
    sf = D.against_any("sofa", "W", near=-d * 0.12, layer="background", length=2.0)
    if sf:
        ct = D.floor("coffee_table", sf.location.x + 1.6, sf.location.y - 1.0, 90, "mid", margin=0.0)
        if ct:
            D.clutter(ct, ["mugs", "book_stack", "vase_flowers", "papers_stack"], 4)
        D.floor("chair_arm", sf.location.x + 1.6, sf.location.y - 2.4, 30, "mid", margin=0.0, upholstery="leather", marks=False)
    cr = D.against_any("sideboard", "E", near=d * 0.1, layer="background", length=1.6)
    if cr:
        D.clutter(cr, ["vase_flowers", "globe", "photo_frame", "book_stack", "mugs", "photo_frame"], 6)
    D.floor("floor_lamp", x0 + 0.7, y1 - 0.9, 0, "background")
    D.floor("floor_lamp", x1 - 0.6, y0 + 1.2, 0, "foreground", marks=False)
    for k, (px, py) in enumerate(((x1 - 0.8, y1 - 0.8), (x0 + 0.8, y0 + 0.8), (x0 + 0.7, y1 - 2.0), (x1 - 0.7, cy - 1.0))):
        D.floor("potted_plant", px, py, 0, "background" if py > cy else "foreground", height=1.1 + 0.4 * (k % 3), seed=k + 2)
    D.against_any("filing_cabinet", "E", near=d * 0.3, layer="background")
    D.against_any("water_cooler", "E", near=-d * 0.12, layer="background")
    D.hang("wall_clock", "E", d * 0.2, z=2.2, layer="background")
    D.hang("whiteboard", "W", d * 0.28, z=0.95, layer="background", width=1.6, height=1.0, seed=3)
    D.hang("poster", "S", w * 0.2, z=1.5, layer="foreground", color="#2D4A6B", seed=3)
    D.hang("notice_board", "S", -w * 0.2, z=1.3, layer="foreground", width=0.9, height=0.7, seed=4)
    D.hang("painting_framed", "W", -d * 0.35, z=1.7, layer="background", width=0.8, height=0.6, seed=5)
    D.against_any("coat_stand", "E", near=-d * 0.35, layer="background")
    D.against_any("bin", "E", near=-d * 0.2, layer="background")
    D.floor_detail("papers", D.n(3), region=(x0 + 1, y0 + 1, x1 - 1, y1 - 1))


@theme("home_living_room", ["victorian", "modern"])
def home_living_room(D):
    """A family living room: a sofa and two armchairs round a coffee table on a rug, television on a sideboard, bookcases, a case clock, side tables
    with lamps and photographs, plants, pictures, a radiator, ceiling light and sconces."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    D.floor("rug", cx, cy, 0, "mid", flat=True, size=(min(3.6, w - 1.2), min(2.8, d - 1.2)), surface="carpet_red", inner="#7A6A4E", border="#D9C9A0")
    sb = D.against_any("sideboard", "N", near=0.0, layer="background", length=1.8, height=0.55)
    if sb:
        t = D.top(sb, "tv", k=0, layer="background", diag=1.05, stand=False)
        D.clutter(sb, ["vase_flowers", "photo_frame", "book_stack", "photo_frame"], 4)
    sf = D.floor("sofa", cx, cy - 1.45, 180, "mid", length=2.2, color="#6B7D8A", margin=0.0, marks=False)
    if sf is None:
        D.against_any("sofa", "S", near=0.0, layer="foreground", length=2.2)
    D.floor("chair_arm", cx - 2.1, cy + 0.2, -90, "mid", upholstery="leather", margin=0.0, marks=False)
    D.floor("chair_arm", cx + 2.1, cy + 0.2, 90, "mid", margin=0.0, marks=False)
    ct = D.floor("coffee_table", cx, cy - 0.05, 0, "mid", margin=0.0)
    if ct:
        D.clutter(ct, ["mugs", "book_stack", "vase_flowers", "papers_stack", "table_candle"], 4)
    for sx in (-1, 1):
        st = D.floor("side_table", cx + sx * 2.0, cy - 1.6, 0, "mid", margin=0.0)
        if st:
            D.top(st, "desk_lamp" if sx < 0 else "photo_frame", k=0)
            D.top(st, "photo_frame", k=0)
    D.against_any("bookcase", "W", near=-d * 0.1, layer="background", width=1.2, seed=6)
    D.against_any("bookcase", "W", near=d * 0.2, layer="background", width=1.0, seed=7)
    D.against_any("grandfather_clock", "E", near=d * 0.3, layer="background")
    D.against_any("cabinet", "E", near=-d * 0.3, layer="background", width=0.9, height=1.2)
    D.floor("floor_lamp", x1 - 0.6, y1 - 0.8, 0, "background")
    D.floor("floor_lamp", x0 + 0.6, cy - 1.5, 0, "mid", marks=False)
    for k, (px, py, hh) in enumerate(((x0 + 0.8, y1 - 0.8, 1.5), (x1 - 0.7, y0 + 1.0, 1.2), (x1 - 0.7, cy + 1.0, 0.9))):
        D.floor("potted_plant", px, py, 0, "background" if py > cy else "foreground", height=hh, seed=k + 1)
    D.hang("painting_framed", "E", -d * 0.05, z=1.55, layer="background", width=1.3, height=0.9, seed=2)
    D.hang("painting_framed", "W", d * 0.4, z=1.6, layer="background", width=0.6, height=0.8, seed=5)
    D.hang("painting_framed", "N", w * 0.3, z=1.6, layer="background", width=0.7, height=0.9, seed=11)
    D.hang("painting_framed", "N", -w * 0.3, z=1.6, layer="background", width=0.9, height=0.6, seed=12)
    D.hang("wall_clock", "N", -w * 0.16, z=2.1, layer="background")
    D.hang("poster", "S", -w * 0.2, z=1.5, layer="foreground", color="#3F5F3A", seed=1)
    D.hang("wall_sconce", "N", w * 0.16, z=1.9, layer="background", kind="modern")
    D.hang("wall_sconce", "E", d * 0.1, z=1.9, layer="background", kind="modern")
    D.hang("radiator", "S", w * 0.3, z=0.15, layer="foreground", length=1.0)
    D.ceiling_piece("ceiling_light_panel", cx, cy, "mid", size=(0.6, 0.6), power=35.0)
    D.floor_detail("papers", D.n(2), region=(x0 + 1, y0 + 1, x1 - 1, y1 - 1))


@theme("home_kitchen", ["victorian", "modern"])
def home_kitchen(D):
    """A home kitchen: two runs of units with sink, hob and wall cabinets, a cooker, fridge, a family table with chairs and a laid breakfast,
    shelves of jars, a clock, a radiator, curtains, plants, a bin and three kinds of light."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    kc = D.against_any("kitchen_counter", "N", near=-w * 0.12, layer="background", length=min(2.6, w * 0.5), wall_units=False)
    if kc is None:
        kc = D.against_any("kitchen_counter", "N", near=-w * 0.12, layer="background", length=min(2.6, w * 0.5), wall_units=False, sink=False)
    if kc:
        D.clutter(kc, ["kettle", "mugs", "pots_and_pans", "microwave", "bread_basket", "fruit_crate", "mugs"], 6)
    D.against_any("fridge", "N", near=w * 0.34, layer="background")
    D.against_any("cooker", "N", near=w * 0.17, layer="background")
    kc2 = D.against_any("kitchen_counter", "E", near=-d * 0.1, layer="background", length=min(1.8, d * 0.4), sink=False, hob=False)
    if kc2:
        D.clutter(kc2, ["mugs", "kettle", "bread_basket", "jug"], 3)
    D.hang("shelf_jars", "W", -d * 0.15, z=1.6, layer="background", length=1.1, seed=4)
    D.hang("shelf_jars", "W", d * 0.15, z=1.9, layer="background", length=0.9, seed=5)
    D.hang("wall_clock", "E", d * 0.25, z=2.0, layer="background")
    D.hang("poster", "E", d * 0.05, z=1.4, layer="background", color="#E8B63A", seed=3)
    D.hang("painting_framed", "W", d * 0.35, z=1.5, layer="background", width=0.7, height=0.5, seed=7)
    D.hang("notice_board", "S", -w * 0.2, z=1.3, layer="foreground", width=0.6, height=0.5, seed=8)
    D.hang("radiator", "W", 0.0, z=0.15, layer="background")
    t = D.floor("dining_table", cx - 0.1, cy - 0.2, 0, "mid", length=1.5, width=0.85, margin=0.5)
    if t is None:
        t = D.floor("trestle_table", cx, cy - 0.2, 0, "mid", length=1.4, width=0.8, margin=0.5)
    if t:
        D.clutter(t, ["mugs", "bread_basket", "vase_flowers", "crockery_set", "fruit_crate", "jug"], 5)
        for sx in (-0.9, 0.9):
            D.floor("chair_dining", cx - 0.1 + sx, cy - 0.2, 90 if sx < 0 else -90, "mid", margin=0.0, marks=False)
        for sx in (-0.4, 0.4):
            D.floor("chair_dining", cx - 0.1 + sx, cy - 0.95, 0, "mid", margin=0.0, marks=False)
    D.floor("bin", x1 - 0.5, y1 - 1.4, 0, "background")
    D.floor("potted_plant", x0 + 0.6, y1 - 0.8, 0, "background", height=1.2, seed=2)
    D.floor("potted_plant", x1 - 0.7, y0 + 1.0, 0, "foreground", height=1.0, seed=5)
    D.floor("floor_lamp", x0 + 0.6, y0 + 1.0, 0, "foreground", marks=False)
    D.hang("wall_sconce", "W", d * 0.0 + 1.3, z=1.9, layer="background", kind="modern")
    for i in range(2):
        D.ceiling_piece("ceiling_light_panel", cx - 0.9 + i * 1.8, cy - 0.2, "mid", size=(0.6, 0.6), power=35.0)
    D.floor_detail("papers", D.n(3), region=(x0 + 1, y0 + 1, x1 - 1, y1 - 1))


@theme("shop_interior", ["medieval", "renaissance", "age_of_sail", "victorian", "modern", "fantasy"])
def shop_interior(D):
    """A general store: a counter with scales and a till, shelving of bottles and jars behind it, display stands and tables heaped with goods,
    barrels, sacks and crates, herbs and pots hanging from the beams, signs, notices and lamps."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    w, d, h = x1 - x0, y1 - y0, D.h
    ct = D.floor("bar_counter", cx, cy + 0.9, 0, "mid", length=min(3.4, w - 2.0), margin=0.6)
    if ct:
        D.clutter(ct, ["balance_scales", "till", "basket", "market_goods", "bread_basket", "jug", "scroll", "book_stack"], 8)
    for k, a in enumerate((-w * 0.32, -w * 0.1, w * 0.12, w * 0.34)):
        D.hang("bottle_shelf" if k % 2 == 0 else "shelf_jars", "N", a, z=1.4 + 0.5 * (k % 2), layer="background", **({"length": 1.4, "rows": 3, "seed": k + 1} if k % 2 == 0 else {"length": 1.3, "seed": k + 9}))
    D.hang("shelf_jars", "N", -w * 0.1, z=2.35, layer="background", length=1.3, seed=21)
    D.hang("shelf_jars", "N", w * 0.34, z=2.35, layer="background", length=1.3, seed=22)
    D.against_any("cabinet", "W", near=0.0, layer="background")
    D.against_any("bookcase", "E", near=0.0, layer="background", width=1.0, seed=8)
    D.against_any("display_stand", "W", near=d * 0.28, layer="background", width=1.2, seed=2)
    D.against_any("display_stand", "E", near=d * 0.28, layer="background", width=1.2, seed=5, kind="fruit")
    for k in range(D.n(3)):
        D.floor("barrel", x0 + 0.8 + k * 0.9, y1 - 1.0, 0, "background", margin=0.04)
    for k in range(D.n(3)):
        D.floor("sack", x1 - 0.8 - k * 0.7, y1 - 0.8, 0, "background")
    t = D.floor("trestle_table", cx - w * 0.28, y0 + 2.6, 0, "foreground", length=1.4, margin=0.4)
    if t:
        D.clutter(t, ["cloth_bolts", "fruit_crate", "basket", "bread_basket", "market_goods"], 4)
    t2 = D.floor("trestle_table", cx + w * 0.28, y0 + 2.4, 0, "foreground", length=1.3, margin=0.4)
    if t2:
        D.clutter(t2, ["basket", "jug", "bottle", "book_stack", "scroll"], 4)
    D.floor("crate", x1 - 0.8, y0 + 1.2, 0, "foreground", size=0.55)
    D.floor("crate", x1 - 0.8, y0 + 0.5, 0, "foreground", size=0.45)
    D.floor("potted_plant", x0 + 0.7, y0 + 0.8, 0, "foreground", height=1.2)
    D.floor("woodpile", x0 + 1.9, y0 + 0.7, 0, "foreground", length=1.0, layers=3, margin=0.05)
    D.hang("hanging_sign", "W", -d * 0.2, z=2.5, layer="background")
    D.hang("notice_board", "E", -d * 0.25, z=1.3, layer="background", width=0.9, height=0.7, seed=5)
    D.hang("sign_board", "S", w * 0.2, z=2.2, layer="foreground")
    D.hang("wall_clock", "S", -w * 0.1, z=2.3, layer="foreground")
    _sconces(D, "EW", z=2.1, step=3.0, margin=1.2)
    _hang_from_beams(D, [("herb_bundle", dict(seed=1)), ("pot_rack", dict(length=1.2)), ("lantern", dict(hanging=True)), ("herb_bundle", dict(seed=4, n=5))], (0.3, 0.7))
    D.ceiling_piece("chandelier", cx, cy - 0.3, "mid", radius=0.5, drop=min(1.0, h * 0.28), candles=6)
    D.floor("rug", cx, cy - 0.9, 0, "mid", flat=True, size=(2.4, 1.2), surface="carpet_red", inner="#5A3E2A", border="#B08A4E")
    D.floor_detail("straw", D.n(40), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5))
    D.floor_detail("papers", D.n(3), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5))


# ============================================================================= EXTERIOR THEMES
SKY_DAY, SKY_NIGHT, SKY_DUSK = "#D7EBF7", "#2B3560", "#E8B890"


def _ring_beyond(D, cx, cy, distance=95.0, seed=1, castle_side=None, night=False, sky=None, colors=None, town_dist=None, heights=(10.0, 18.0, 30.0)):
    """The layer beyond an open place: ridges all round (so every direction shows hills, not a void), a far town on two sides."""
    sky = sky or (SKY_NIGHT if night else SKY_DAY)
    for k, rot in enumerate((0, 90, 180, 270)):
        h = arch.far_hills(360.0, distance, heights=heights, sky=sky, seed=seed + k, night=night, at=(cx, cy, 0), castle=(castle_side == rot), colors=colors or ("#6C9A55", "#7BA574", "#8FB0A8"))
        h.rotation_euler.z = math.radians(rot)
        D.made.append(h)
        h["sk_layer"] = "beyond"
    if town_dist:
        for k, rot in enumerate((0, 180)):
            t = arch.far_town(150.0, town_dist, at=(cx, cy, 0), seed=seed + 7 + k, sky=sky, night=night, church=(k == 0))
            t.rotation_euler.z = math.radians(rot)
            D.made.append(t)


@theme("village_square", ["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], "exterior")
def village_square(D):
    """A village green with a well-kept square: a fountain, stalls, a church, rings of houses on all four sides, trees, fences, a washing
    line, smoke from the chimneys, hills and a far town beyond. Looks right from the south (camera side), the middle and the north."""
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    W, Dp = x1 - x0, y1 - y0
    night = D.night
    D.ground("grass_lawn", z=-0.012, size=260)
    pl = arch.plaza((W - 6, Dp * 0.8), at=(cx, cy + 0.2, 0))
    D.add(pl, "mid")
    D.path([(cx - W * 0.1, y0 - 12), (cx - W * 0.1, y0 + 1.0)], 3.2)
    D.path([(x0 - 12, cy + 1.0), (x0 + 3, cy + 1.0)], 3.0)
    D.path([(x1 - 3, cy - 1.0), (x1 + 12, cy - 1.0)], 3.0)
    # ---- the centre: a fountain with a ring of benches
    D.put("fountain", cx + 0.5, cy + 1.2, 0, "mid", radius=1.4, reserve=True)
    for a in (35, 145, 215, 325):
        D.floor("bench", cx + 0.5 + 3.3 * math.cos(math.radians(a)), cy + 1.2 + 3.0 * math.sin(math.radians(a)), a + 90, "mid", length=1.6, margin=0.2, back=True)
    # ---- the north side: a church in a gap, houses either side, behind them the tall trees
    gx = cx - W * 0.12
    church = arch.church(7.0, 13.0, 17.0, at=(gx - 1.5, y1 + 2.2, 0), night=night)
    D.add(church, "background", (gx, y1 + 8.5, 5.0, 6.5, 0.0))
    D.house_row((x0 - 10, y1 + 1.4), (x1 + 10, y1 + 1.4), 0.0, gaps_at=[(gx - 4.5 - (x0 - 10), gx + 8.0 - (x0 - 10))], night=night, signs=0.45)
    for sx in (-1, 1):
        D.put("tree_round", gx + 1.5 + sx * 11.5, y1 + 4.5, 0, "background", height=7.5, crown=3.2, seed=4 + sx)
    # ---- west and east: houses facing the green, a lane between them
    D.house_row((x0 - 1.6, y0 + 1.0), (x0 - 1.6, y1 - 0.5), 90.0, night=night, storeys=(1, 2), gaps_at=[(cy + 1.0 - 1.5 - (y0 + 1.0), cy + 1.0 + 1.5 - (y0 + 1.0))], signs=0.3)
    D.house_row((x1 + 1.6, y0 + 1.0), (x1 + 1.6, y1 - 0.5), -90.0, night=night, storeys=(1, 3), gaps_at=[(cy - 1.0 - 1.5 - (y0 + 1.0), cy - 1.0 + 1.5 - (y0 + 1.0))], signs=0.3)
    # ---- the south side (behind the camera): a lower row with a wide gap for the road, so the reverse view is a place too
    D.house_row((x0 - 8, y0 - 3.5), (x1 + 8, y0 - 3.5), 180.0, night=night, storeys=(1, 2), gaps_at=[(W * 0.4 + 8 - 3.0, W * 0.4 + 8 + 3.0)], signs=0.3)
    # ---- the market: three stalls on the north side of the green with goods, two carts, barrels, crates, hay
    for k, col in enumerate(("#B3322C", "#2D6CB0", "#D8A93A")):
        s = D.floor("market_stall", cx + W * 0.12 + k * 3.7 - 2.0, y1 - 2.2, 0, "mid", canopy=col, margin=0.35)
        if s:
            D.clutter(s, ["fruit_crate", "basket", "cloth_bolts", "bread_basket", "market_goods", "jug"], 5)
    D.floor("cart", x1 - 4.2, cy - 2.2, 25, "mid", margin=0.3)
    D.floor("cart", x0 + 4.4, y1 - 4.4, -15, "mid", margin=0.3, goods=False)
    for k in range(3):
        D.floor("barrel", x1 - 2.3 + 0.8 * (k % 2), y1 - 3.2 - 0.8 * (k // 2) - 0.9 * k * 0, 0, "mid", margin=0.05)
    for k in range(D.n(4)):
        D.floor(D.rnd.choice(["crate", "sack", "hay_bale", "basket"]), D.rnd.uniform(x1 - 5.5, x1 - 1.2), D.rnd.uniform(y0 + 1.0, cy - 2.0), D.rnd.uniform(0, 90), "foreground", margin=0.15)
    D.floor("haystack", x0 + 2.3, y1 - 2.5, 0, "mid", radius=1.2, margin=0.2)
    D.floor("woodpile", x0 + 2.6, cy - 3.5, 90, "mid", margin=0.2)
    D.floor("water_pump", x0 + 3.0, y0 + 2.5, 20, "foreground", margin=0.2)
    D.floor("bucket", x0 + 3.9, y0 + 2.4, 0, "foreground", margin=0.05, marks=False)
    # ---- life on the edges: lamp posts, a signpost, a washing line, fences, notice board, flowers, trees and bushes
    for x, y in ((cx - W * 0.28, y0 + 2.0), (cx + W * 0.30, y0 + 2.0), (cx - W * 0.3, y1 - 2.2), (cx + W * 0.4, cy)):
        D.floor("lamp_post", x, y, 0, "mid", height=4.0, style="gas", margin=0.0, marks=False, power=700.0 if night else 120.0)
    D.floor("signpost", x1 - 1.4, y0 + 1.4, 20, "foreground", margin=0.0)
    for bx_ in (-6.5, 7.5):
        D.floor("banner_pole", cx + bx_, y0 + 4.5, 0, "mid", height=3.8, color="#A3231F" if bx_ < 0 else "#2D4A6B", margin=0.2)
    D.put("washing_line", x0 - 6.0, cy + 6.0, 90, "background", reserve=False, length=5.0, seed=D.seed)
    for sx, sy, rot in ((x0 + 1.0, y0 + 0.2, 0), (x0 + 6.2, y0 + 0.2, 0), (x1 - 7.0, y0 + 0.3, 0), (x1 - 1.8, y0 + 0.3, 0)):
        D.floor("fence", sx, sy, rot, "foreground", length=4.5, margin=0.0, marks=False)
    for k in range(2):
        D.put("tree_round", (x0 - 3.2) if k == 0 else (x1 + 3.2), y0 + 2.5 + 3 * k, 0, "mid", height=6.5, crown=3.0, seed=k + 20)
    D.trees(D.n(6), (x0 - 9, y0 - 12, x1 + 9, y0 - 7), layer="background", bushes=5)
    D.trees(D.n(8), (x0 - 22, y1 + 14, x1 + 22, y1 + 26), kinds=("tree_round", "tree_pine"), layer="beyond", size=(7.0, 12.0))
    D.floor_detail("grass", D.n(120), region=(x0 - 6, y0 - 8, x1 + 6, y1 + 1))
    D.floor_detail("flowers", D.n(36), region=(x0 - 1, y0 - 2, x1 + 1, y0 + 1))
    D.floor_detail("stones", D.n(50), region=(x0, y0, x1, y1))
    D.floor_detail("puddles", D.n(5), region=(cx - 7, cy - 4, cx + 7, cy + 4))
    D.floor_detail("straw", D.n(60), region=(x1 - 7, y0, x1 - 1, y1 - 1))
    D.floor_detail("leaves", D.n(60), region=(x0, y0, x1, y1))
    # ---- beyond: ridges all round, a far town to the north and south, mist low on the grass
    _ring_beyond(D, cx, cy, 95.0, D.seed, night=night, town_dist=75.0)
    D.add(arch.ground_haze((W + 30, Dp + 20), (cx, cy, 0), 1.4, "#E6EDF2" if not night else "#2A3350", 0.12 if not night else 0.10, D.seed), "beyond")


@theme("market_street", ["medieval", "renaissance", "age_of_sail", "victorian"], "exterior")
def market_street(D):
    """A market street: both sides lined with shops (awnings, hanging signs, bunting across), stalls and carts on the pavements,
    cobbles with puddles and straw, lamp posts, a church tower at one end and a gate at the other, smoke over the roofs."""
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    W = x1 - x0
    night = D.night
    D.ground("earth_path", z=-0.012, size=260)
    st = arch.street(W + 90, 7.0, 0.1, "cobblestone", at=(cx, cy, 0), pavement="flagstone", pavement_w=2.3)
    D.add(st, "mid")
    ns, ss = cy + 3.5 + 2.3 + 0.1, cy - 3.5 - 2.3 - 0.1
    D.house_row((x0 - 46, ns), (x1 + 46, ns), 0.0, styles=("timber", "timber", "stone", "brick"), storeys=(2, 3), awning=True, night=night, signs=0.6, width=(5.0, 7.5), gap=(0.0, 0.1), smoke_p=0.6)
    D.house_row((x0 - 46, ss), (x1 + 46, ss), 180.0, styles=("timber", "stone", "timber", "brick"), storeys=(2, 3), awning=True, night=night, signs=0.6, width=(5.0, 7.5), gap=(0.0, 0.1), smoke_p=0.6)
    # the ends of the street: a church tower beyond one, a town gate across the other
    D.add(arch.church(7.0, 13.0, 19.0, at=(x1 + 52, cy - 3.0, 0), rot_z=90.0, night=night), "beyond", (x1 + 58, cy, 7.0, 7.0, 0.0))
    gate = arch.house_front(storeys=3, style="stone", width=9.0, depth=3.0, at=(x0 - 48, cy, 0), rot_z=-90.0, seed=D.seed, night=night, roof_surface="roof_slate")
    D.add(gate, "beyond")
    # ---- bunting across the street between the first-floor windows, hanging signs on the shopfronts (house_row did the signs)
    for k, bx in enumerate((cx - 10, cx - 1, cx + 8, cx + 17)):
        D.put("bunting", bx, cy, 90.0, "foreground" if k == 0 else "mid", z=5.0, length=11.0, sag=0.6, seed=k)
    # ---- the market: stalls on the north pavement, goods in front of the shops on the south (the pavements stand 0.1 m above the cobbles)
    D.zbase = 0.1
    for k, col in enumerate(("#B3322C", "#2D6CB0", "#D8A93A", "#3F8F5A", "#B3322C")):
        s = D.floor("market_stall", cx - 12 + k * 5.7, cy + 4.65, 0, "mid", canopy=col, margin=0.3)
        if s:
            D.clutter(s, ["fruit_crate", "basket", "cloth_bolts", "bread_basket", "market_goods", "jug", "bottle"], 5)
    D.zbase = 0.0
    D.floor("cart", cx - 3.0, cy + 0.8, 8, "mid", margin=0.3)
    D.floor("cart", cx + 9.0, cy - 1.6, -10, "foreground", margin=0.3, goods=False)
    D.zbase = 0.1
    D.floor("hitching_rail", cx + 3.5, ss + 1.3, 0, "mid", length=3.0, margin=0.2)
    D.floor("horse", cx + 3.0, ss + 0.4, 0, "mid", margin=0.1)
    D.floor("well", cx - 7.5, ss + 1.8, 0, "mid", radius=0.8, height=0.9, margin=0.3)
    for k in range(D.n(7)):
        D.floor(D.rnd.choice(["barrel", "crate", "sack", "basket", "hay_bale"]), D.rnd.uniform(x0 + 1, x1 - 1), ss + 0.9 + D.rnd.uniform(-0.3, 0.4), D.rnd.choice([0, 90]), "foreground", margin=0.15)
    for k in range(D.n(5)):
        D.floor(D.rnd.choice(["barrel", "crate", "sack"]), D.rnd.uniform(x0 + 1, x1 - 1), ns - 0.9, 0, "mid", margin=0.1)
    for x in (cx - 9.2, cx - 3.3, cx + 2.4, cx + 8.1):
        D.floor("lamp_post", x, ns - 0.9, 0, "mid", height=4.2, style="gas", margin=0.0, marks=False, power=700.0 if night else 120.0)
    for x in (cx - 9, cx + 1, cx + 11):
        D.floor("lamp_post", x, ss + 0.9, 0, "foreground", height=4.2, style="gas", margin=0.0, marks=False, power=700.0 if night else 120.0)
    D.floor("signpost", cx + 14.5, ss + 0.5, 10, "foreground", margin=0.0)
    D.floor("potted_plant", cx - 14.0, ss + 0.6, 0, "foreground", height=1.1)
    D.floor("bench", cx + 6.8, ss + 0.7, 0, "foreground", length=1.6, margin=0.1, back=True)
    D.zbase = 0.0
    D.floor_detail("straw", D.n(90), region=(x0, cy - 3.3, x1, cy + 3.3))
    D.floor_detail("puddles", D.n(7), region=(x0, cy - 3.0, x1, cy + 3.0))
    D.floor_detail("litter", D.n(50), region=(x0, cy - 3.3, x1, cy + 3.3))
    D.floor_detail("leaves", D.n(40), region=(x0, cy - 3.3, x1, cy + 3.3))
    D.floor_detail("stones", D.n(40), region=(x0, cy - 3.3, x1, cy + 3.3))
    D.trees(D.n(6), (x0 - 20, cy + 16, x1 + 20, cy + 26), layer="beyond", size=(8.0, 13.0))
    D.trees(D.n(4), (x0 - 20, cy - 26, x1 + 20, cy - 16), layer="beyond", size=(8.0, 13.0))
    _ring_beyond(D, cx, cy, 120.0, D.seed + 3, night=night, town_dist=95.0)
    D.add(arch.ground_haze((W, 9), (cx, cy, 0), 1.2, "#E6EDF2" if not night else "#2A3350", 0.10, D.seed), "beyond")


@theme("city_street", ["modern"], "exterior")
def city_street(D):
    """A modern street: asphalt with markings and a zebra crossing, pavements, shopfronts with signs and awnings, parked cars, lamps,
    traffic lights, a bus stop, bins, trees in the pavement, a hydrant, steam from a manhole, towers closing both ends."""
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    W = x1 - x0
    night = D.night
    D.ground("concrete", z=-0.012, size=110)
    st = arch.street(W + 120, 8.0, 0.1, "asphalt", at=(cx, cy, 0), pavement="concrete", pavement_w=3.0)
    D.add(st, "mid")
    D.add(arch.road_markings(W + 120, 8.0, at=(cx, cy, 0), crossings=(cx + 3.5,)), "mid")
    ns, ss = cy + 4.0 + 3.0 + 0.1, cy - 4.0 - 3.0 - 0.1
    colors = ["#2B3B4E", "#B3322C", "#2D6CB0", "#D8A93A", "#3F8F5A"]
    D.house_row((x0 - 60, ns), (x1 + 60, ns), 0.0, styles=("modern", "brick", "modern", "brick"), storeys=(3, 6), width=(6.0, 10.0), gap=(0.0, 0.0), awning=True, night=night, signs=0.0, smoke_p=0.0, flowers=0.0,
                tints=[None, "#D8DADD", "#C8CED6", "#E6D8C6", "#B8C0C8"], lit=0.9, roofs=["concrete"], depth=8.0)
    D.house_row((x0 - 60, ss), (x1 + 60, ss), 180.0, styles=("brick", "modern", "modern", "brick"), storeys=(3, 6), width=(6.0, 10.0), gap=(0.0, 0.0), awning=True, night=night, signs=0.0, smoke_p=0.0, flowers=0.0,
                tints=[None, "#D8DADD", "#E6D8C6", "#B8C0C8"], lit=0.9, roofs=["concrete"], depth=8.0)
    # shop signs above the awnings (readable details), one every shopfront-ish
    rnd = D.rnd
    for k, x in enumerate(range(int(x0) - 6, int(x1) + 6, 7)):
        D.put("sign_board", x + 0.5, ns - 0.02, 0, "background", z=3.1, width=1.6, color=rnd.choice(["#1F3A5A", "#5A1F1F", "#1F5A3A", "#2B2B2E"]))
        D.put("sign_board", x + 3.0, ss + 0.02, 180, "background", z=3.1, width=1.6, color=rnd.choice(["#1F3A5A", "#5A1F1F", "#1F5A3A", "#2B2B2E"]))
    # ---- the road: parked cars along both kerbs (the pavements stand 0.1 m above the asphalt)
    for k, x in enumerate((cx - 12.0, cx - 7.0, cx - 1.8, cx + 9.0, cx + 14.0)):
        D.floor("car", x, cy + 2.6, 0, "mid", color=colors[k % len(colors)], margin=0.4)
    for k, x in enumerate((cx - 10.0, cx - 4.5, cx + 7.5, cx + 12.5)):
        D.floor("car", x, cy - 2.6, 180, "foreground", color=colors[(k + 2) % len(colors)], margin=0.4)
    # ---- street furniture, on the pavements
    D.zbase = 0.1
    for x in (cx - 11, cx - 1, cx + 10):
        D.floor("lamp_post", x, ns - 0.8, 0, "mid", height=5.4, style="modern", margin=0.0, marks=False, power=900.0 if night else 150.0)
    for x in (cx - 8, cx + 5):
        D.floor("lamp_post", x, ss + 0.8, 0, "foreground", height=5.4, style="modern", margin=0.0, marks=False, power=900.0 if night else 150.0)
    D.floor("traffic_light", cx + 1.2, ns - 0.7, 0, "mid", margin=0.0, marks=False, state="red")
    D.floor("traffic_light", cx + 6.0, ss + 0.7, 0, "foreground", margin=0.0, marks=False, state="green")
    D.floor("bus_stop", cx - 4.5, ns - 1.3, 0, "mid", length=3.0, margin=0.1, marks=False)
    D.floor("street_sign", cx + 12.2, ns - 0.8, 0, "mid", kind="bus", margin=0.0, marks=False)
    D.floor("street_sign", cx - 14.0, ss + 0.8, 0, "foreground", kind="parking", margin=0.0, marks=False)
    D.floor("hydrant", cx + 9.0, ss + 0.5, 0, "foreground", margin=0.0, marks=False)
    D.floor("parking_meter", cx - 13.0, ss + 0.9, 0, "foreground", margin=0.0, marks=False)
    D.floor("parking_meter", cx - 9.5, ss + 0.9, 0, "foreground", margin=0.0, marks=False)
    D.floor("post_box", cx + 12.8, ss + 0.8, 0, "foreground", margin=0.0, marks=False)
    for x in (cx - 11.0, cx - 2.0, cx + 7.5):
        D.floor("bin", x, ss + 0.6, 0, "foreground", margin=0.0, marks=False)
    for x in (cx - 8.0, cx + 2.0, cx + 11.0):
        D.floor("bin", x, ns - 0.6, 0, "mid", margin=0.0, marks=False)
    D.floor("bench", cx - 6.5, ss + 0.9, 0, "foreground", length=1.8, margin=0.0, marks=False, back=True)
    for k, x in enumerate((cx - 13.0, cx - 6.0, cx + 4.5, cx + 13.0)):
        D.put("tree_round", x, ns - 1.2, 0, "mid", z=0.1, height=4.6, crown=1.5, seed=k + 3)
    for k, x in enumerate((cx - 12.5, cx + 1.0, cx + 8.5)):
        D.put("tree_round", x, ss + 1.2, 0, "foreground", z=0.1, height=4.6, crown=1.5, seed=k + 11)
    for x in (cx - 3.0, cx + 6.2):
        D.floor("potted_plant", x, ns - 0.5, 0, "mid", height=1.2, margin=0.0, marks=False)
    for x in range(-12, 14, 5):                                          # parking meters along both kerbs, potted plants at the shop doors
        D.floor("parking_meter", cx + x + 0.6, ss + 0.9, 0, "foreground", margin=0.0, marks=False)
        D.floor("parking_meter", cx + x + 1.4, ns - 0.9, 0, "mid", margin=0.0, marks=False)
    for k, x in enumerate(range(-12, 14, 6)):
        D.floor("potted_plant", cx + x + 2.2, ns - 0.55, 0, "mid", height=1.0 + 0.2 * (k % 3), seed=k + 40, margin=0.0, marks=False)
        D.floor("potted_plant", cx + x + 3.2, ss + 0.55, 0, "foreground", height=1.0 + 0.2 * (k % 3), seed=k + 50, margin=0.0, marks=False)
    D.zbase = 0.0
    D.add(arch.smoke((cx - 6.0, cy - 0.5, 0.0), height=6.0, puffs=10, width=0.5, drift=(1.4, 0.5), color="#CFCFD4" if not night else "#8A8E9E", alpha=0.3), "mid")
    D.floor_detail("litter", D.n(80), region=(x0, cy - 7.0, x1, cy + 7.0))
    D.floor_detail("puddles", D.n(6), region=(x0, cy - 3.6, x1, cy + 3.6))
    D.floor_detail("leaves", D.n(30), region=(x0, cy - 7.0, x1, cy + 7.0))
    # ---- the street is closed at both ends by a tall block, so the far end of the view is a building and not a vanishing road
    D.add(arch.house_front(storeys=9, style="modern", width=24.0, depth=12.0, at=(x1 + 34, cy, 0), rot_z=-90.0, seed=D.seed + 40, night=night, lit=1.2 if night else 0.7, roof_surface="concrete"), "beyond")
    D.add(arch.house_front(storeys=8, style="brick", width=22.0, depth=12.0, at=(x0 - 34, cy, 0), rot_z=90.0, seed=D.seed + 41, night=night, lit=1.2 if night else 0.7, roof_surface="concrete"), "beyond")
    # ---- beyond: towers closing both ends of the street and over the rooftops
    for k, rot in enumerate((0, 90, 180, 270)):
        sk = arch.skyline(220.0, 45.0 if k % 2 == 0 else 70.0, at=(cx, cy, 0), kind="city", seed=D.seed + k, night=night, sky_card=False)
        sk.rotation_euler.z = math.radians(rot)
        D.add(sk, "beyond")
    D.add(arch.ground_haze((W + 40, 10), (cx, cy, 0), 2.2, "#D8DDE4" if not night else "#2A3350", 0.10, D.seed), "beyond")


@theme("army_camp", ["ancient", "medieval", "renaissance", "age_of_sail", "fantasy"], "exterior")
def army_camp(D):
    """An army camp at dusk: two columns of tents receding down a central lane lit by fires, a command pavilion at the far end under
    banners, a palisade and a watchtower, a horse line, weapon racks, carts and stores, smoke from other camps, ridges and forest beyond."""
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    night = D.night
    far = y1 + 14                                                          # the camp runs well beyond the stage: the lane recedes
    D.ground("earth_path", z=-0.05, size=200)
    ter, zf = arch.terrain((200.0, 150.0), at=(cx, cy + 25), flat=(x0 - 6, y0 - 8, x1 + 6, far + 8), relief=1.4, surface="earth_path", seed=D.seed, blend=10.0,
                           features=(("mound", cx - 40, y1 + 20, 9, 2.2), ("mound", cx + 46, y1 + 30, 12, 3.0)))
    D.add(ter, "mid")
    D.path([(cx, y0 - 10), (cx, far + 6)], 5.0, "earth_path")
    # ---- tents: two receding columns, each a little different; the near ones are on the stage, the far ones beyond it
    cols = ["#D8CDB4", "#C9B88A", "#B9C4B0", "#CBBFA6", "#C2B48E"]
    for r_ in range(5):
        y = y0 + 4.0 + r_ * 6.5
        for sx in (-1, 1):
            xx = cx + sx * (8.4 + 0.4 * (r_ % 2))
            rot = 90 * sx + D.rnd.uniform(-6, 6)
            t = D.put("tent", xx, y, rot, "mid" if r_ > 0 else "foreground", color=D.rnd.choice(cols), width=3.4, length=4.4, height=2.5, reserve=True) if y > y0 + 2.0 else None
            if t is not None and r_ % 2 == 0:
                D.put("barrel", xx - sx * 3.6, y - 1.4, 0, "mid")
            if t is not None:
                D.put("sack", xx - sx * 3.4, y + 0.6, 0, "mid")
    # ---- the lane: fires with log seats, a cauldron, torches, banners, weapon racks
    for k, (fx, fy) in enumerate(((cx - 2.0, y0 + 5.5), (cx + 2.4, y0 + 13.5), (cx - 1.5, y0 + 22.0))):
        D.put("campfire", fx, fy, 0, "mid", reserve=True)
        D.fire_smoke(fx, fy, 0, 7.0 + 2 * k, (2.0, 0.6), night=night, seed=k + 1)
        for a in (20, 140, 260):
            D.put("hay_bale" if k != 1 else "bench", fx + 2.2 * math.cos(math.radians(a)), fy + 2.2 * math.sin(math.radians(a)), a + 90, "mid", **({} if k != 1 else dict(length=1.4)))
    D.put("cauldron", cx + 3.6, y0 + 8.0, 0, "mid", reserve=True)
    D.fire_smoke(cx + 3.6, y0 + 8.0, 0.8, 4.0, (1.0, 0.2), night=night, seed=11)
    for k in range(5):
        for sx in (-1, 1):
            D.put("torch_stand", cx + sx * 3.2, y0 + 2.0 + k * 6.2, 0, "mid", height=2.1, power=110.0)
    for k in range(8):
        D.put("banner_pole", cx + (-1 if k % 2 else 1) * 4.6, y0 + 5.0 + k * 3.8, 0, "mid", height=4.0, color=("#A3231F", "#2D4A6B")[k % 2])
    for r_ in range(5):                                                       # every tent row has its own litter of kit: racks, stacks, seats, spears
        yy = y0 + 4.0 + r_ * 6.5
        for sx in (-1, 1):
            D.put("weapon_rack", cx + sx * 4.3, yy + 1.6, 90 * sx, "mid", length=1.6)
            D.put("crate", cx + sx * 4.6, yy - 1.4, 0, "mid", size=0.55)
            D.put("crate", cx + sx * 5.3, yy - 1.4, 25, "mid", size=0.5)
            D.put("barrel", cx + sx * 5.2, yy + 3.0, 0, "mid")
            D.put("stool", cx + sx * 4.3, yy + 3.2, 0, "mid")
            D.put("spear_stuck", cx + sx * 5.6, yy + 0.2, 0, "mid", seed=r_ * 3 + (sx > 0))
            D.put("shield_pile", cx + sx * 5.6, yy - 2.6, 40 * sx, "mid", seed=r_)
    D.floor("weapon_rack", cx - 9.8, y0 + 4.5, 90, "foreground", length=1.8, margin=0.1)
    D.floor("weapon_rack", cx + 9.9, y0 + 9.5, -90, "mid", length=1.8, margin=0.1)
    D.floor("shield_pile", cx - 8.8, y0 + 2.2, 20, "foreground", margin=0.1)
    D.floor("shield_pile", cx + 8.8, y0 + 3.0, 80, "foreground", margin=0.1)
    D.floor("spear_stuck", cx - 10.6, y0 + 7.5, 0, "mid", margin=0.1)
    D.floor("arrow_bundle", cx + 2.0, y0 + 3.2, 20, "foreground", margin=0.1)
    # ---- the horse line, carts and stores along the left, the watchtower and palisade at the back right
    D.floor("hitching_rail", x0 + 3.2, y0 + 11.0, 90, "mid", length=3.2, margin=0.2)
    D.floor("horse", x0 + 2.2, y0 + 10.0, 90, "mid", margin=0.1, coat="#7A4A2A")
    D.floor("horse", x0 + 2.2, y0 + 12.4, 90, "mid", margin=0.1, coat="#2F2A28")
    D.floor("cart", x0 + 3.5, y0 + 2.0, 60, "foreground", margin=0.2)
    D.floor("woodpile", x1 - 2.2, y0 + 3.0, 90, "foreground", margin=0.2)
    for k in range(D.n(6)):
        D.floor(D.rnd.choice(["crate", "barrel", "sack", "hay_bale"]), D.rnd.uniform(x1 - 6.5, x1 - 1.2), D.rnd.uniform(y0 + 4.5, y0 + 15), D.rnd.uniform(0, 90), "mid", margin=0.15)
    D.put("pavilion", cx, far + 2.0, 0, "background", width=5.5, length=7.0, height=3.4, color="#A3231F", reserve=True)
    D.put("palisade", cx - 15, far + 6, 0, "background", length=24.0, height=2.8, seed=3, gate=False)
    D.put("palisade", cx + 15, far + 6, 0, "background", length=24.0, height=2.8, seed=4)
    D.put("watchtower", cx + 21, far + 6, 0, "background", height=6.5)
    D.put("watchtower", cx - 21, far + 7, 0, "background", height=6.2)
    D.put("stakes", cx - 12, far - 1, 8, "background", count=14)
    D.put("stakes", cx + 12, far, -8, "background", count=14)
    # ---- ground life
    D.floor_detail("straw", D.n(120), region=(x0, y0, x1, far))
    D.floor_detail("mud", D.n(14), region=(x0, y0, x1, far))
    D.floor_detail("stones", D.n(60), region=(x0, y0, x1, far))
    D.floor_detail("puddles", D.n(6), region=(x0, y0, x1, far))
    D.floor_detail("grass", D.n(90), region=(x0 - 10, y0 - 6, x1 + 10, far + 6))
    D.trees(D.n(10), (x0 - 25, far + 16, x1 + 25, far + 34), kinds=("tree_pine", "tree_pine", "tree_round"), layer="beyond", size=(8.0, 14.0))
    D.trees(D.n(5), (x0 - 25, y0 - 14, x1 + 25, y0 - 8), layer="background", size=(6.0, 10.0), avoid=[(cx, y0 - 10, 8)])
    sky = SKY_DUSK if not night else SKY_NIGHT
    _ring_beyond(D, cx, cy + 10, 110.0, D.seed, night=night, sky=sky, colors=("#4A5A44", "#5A6A60", "#6E7A86"))
    for k, (sx, sy) in enumerate(((-45, far + 40), (38, far + 55), (65, far + 35))):
        D.fire_smoke(cx + sx, sy, 0, 28.0, (6.0, 1.0), night=night, seed=30 + k)
    D.add(arch.ground_haze((90, 70), (cx, cy + 14, 0), 1.8, "#C9B6A6" if not night else "#2A3350", 0.13, D.seed), "beyond")


@theme("battlefield", ["ancient", "medieval", "renaissance", "age_of_sail", "fantasy"], "exterior")
def battlefield(D):
    """The morning after a battle: churned ground with a trench, craters and ridges; a broken palisade, stakes, abandoned shields, spears and
    arrows, fallen and planted banners, a standing and a wrecked siege engine, a wrecked cart, dead trees, rubble, burning wreckage with smoke
    columns on the horizon, haze, two hosts in the distance and a castle on a far ridge under a heavy sky."""
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    cx, cy = D.at
    night = D.night
    D.ground("forest_floor", z=-0.06, size=200)
    feats = (("trench", cx - 40, y1 + 6, cx - 9, y1 + 3, 2.2, 1.0), ("trench", cx + 10, y1 + 3, cx + 45, y1 + 7, 2.2, 0.9), ("crater", cx - 24, y1 + 18, 4.0, 1.3), ("crater", cx + 26, y1 + 20, 5.0, 1.5),
             ("crater", cx + 8, y1 + 30, 4.0, 1.1), ("ridge", cx - 60, y1 + 38, cx + 60, y1 + 44, 6.0, 3.2), ("mound", cx - 30, y1 + 10, 6, 1.4), ("mound", cx + 34, y1 + 12, 7, 1.6),
             ("crater", x0 - 14, y0 + 6, 3.5, 0.9), ("crater", x1 + 15, y0 + 4, 4.0, 1.0), ("mound", x0 - 16, y1, 5, 1.2), ("mound", x1 + 18, y1 - 2, 6, 1.4))
    ter, zf = arch.terrain((220.0, 170.0), at=(cx, cy + 30), flat=(x0 - 3, y0 - 6, x1 + 3, y1 + 14), relief=1.8, features=feats, surface="forest_floor", tint="#8A7A66", seed=D.seed, blend=7.0, res=1.4)
    D.zfn = zf
    D.add(ter, "mid")
    D.path([(x0 - 20, cy + 3), (x0 + 3, cy + 1), (x1 + 4, cy + 3), (x1 + 22, cy + 6)], 3.2, "earth_path")
    # ---- the line that broke: a palisade with a gap, stakes, a trench behind
    D.put("palisade", cx - 14, y1 - 1.8, 4, "mid", length=11.0, height=2.6, seed=1, broken=True)
    D.put("palisade", cx + 12, y1 - 1.6, -3, "mid", length=13.0, height=2.6, seed=2, broken=True)
    D.put("stakes", cx - 2.5, y1 - 3.0, 6, "mid", count=10)
    D.put("stakes", cx + 3.0, y1 - 2.0, -10, "mid", count=8)
    D.floor("stakes", x0 + 2.5, cy - 1.0, 70, "mid", count=9, margin=0.1)
    D.floor("stakes", x1 - 2.0, cy + 1.5, 110, "mid", count=9, margin=0.1)
    # ---- what the armies left: shields, spears, arrows, banners, weapons
    for k in range(D.n(7)):
        D.floor("shield_stuck", D.rnd.uniform(x0 + 1, x1 - 1), D.rnd.uniform(y0 + 0.5, y1 - 2), D.rnd.uniform(0, 360), "mid" if k % 2 else "foreground", z=0.23, color=D.rnd.choice(["#A3231F", "#2D4A6B", "#3F5F3A", "#C9A44A"]), seed=k, margin=0.1)
    for k in range(D.n(3)):
        D.floor("shield_pile", D.rnd.uniform(x0 + 1, x1 - 1), D.rnd.uniform(y0 + 0.5, y1 - 2), D.rnd.uniform(0, 180), "mid", seed=k, margin=0.1)
    for k in range(D.n(4)):
        D.floor("spear_stuck", D.rnd.uniform(x0 + 1, x1 - 1), D.rnd.uniform(y0 + 1, y1 - 2), 0, "mid", seed=k, margin=0.15)
    for k in range(D.n(5)):
        D.floor("arrow_bundle", D.rnd.uniform(x0, x1), D.rnd.uniform(y0, y1 - 1), D.rnd.uniform(0, 180), "foreground", seed=k, margin=0.1)
    for k, col in enumerate(("#A3231F", "#2D4A6B", "#A3231F")):
        D.floor("fallen_banner", D.rnd.uniform(x0 + 2, x1 - 2), D.rnd.uniform(y0 + 1, y1 - 3), D.rnd.uniform(0, 360), "mid", color=col, margin=0.1)
    for k in range(3):
        D.floor("banner_pole", x0 + 3.0 + k * (x1 - x0 - 6) / 2, y1 - 3.6 - k % 2 * 2.0, D.rnd.uniform(-6, 6), "mid", height=4.0, color=("#A3231F", "#2D4A6B")[k % 2], margin=0.2)
    # ---- the second tier, beyond the stage on the level ground: the line that held, a siege tower's wreck, banners, a wrecked cart and fires
    D.put("palisade", cx - 10, y1 + 9.0, 2, "background", length=14.0, height=2.8, seed=5, broken=True)
    D.put("palisade", cx + 14, y1 + 10.0, -2, "background", length=12.0, height=2.8, seed=6, broken=True)
    D.put("siege_engine", cx - 22, y1 + 6.0, 20, "background", damaged=True)
    D.put("siege_engine", cx + 24, y1 + 7.5, 160, "background")
    for k, (px, py) in enumerate(((cx - 2, y1 + 8.0), (cx + 4, y1 + 11.0), (cx - 17, y1 + 12.0), (cx + 20, y1 + 12.5))):
        D.put("banner_pole", px, py, D.rnd.uniform(-8, 8), "background", height=4.2, color=("#A3231F", "#2D4A6B")[k % 2])
    for k in range(7):
        D.put("shield_stuck", D.rnd.uniform(x0, x1), y1 + D.rnd.uniform(3.5, 12.0), D.rnd.uniform(0, 360), "background", z=0.23, color=D.rnd.choice(["#A3231F", "#2D4A6B", "#3F5F3A"]), seed=k + 20)
    for k in range(4):
        D.put("rubble", D.rnd.uniform(x0, x1), y1 + D.rnd.uniform(4, 13), 0, "background", size=D.rnd.uniform(1.0, 1.6), seed=k + 9)
    for k, (tx, ty) in enumerate(((cx - 25, y1 + 12), (cx + 27, y1 + 13), (cx - 6, y1 + 13.5))):
        D.put("tree_dead", tx, ty, 0, "background", height=D.rnd.uniform(5.0, 7.5), seed=k + 30)
    D.put("wrecked_cart", cx + 8, y1 + 6.0, 200, "background", seed=7, z=-0.17)
    for k, (fx, fy) in enumerate(((cx - 14, y1 + 5.5), (cx + 16, y1 + 8.0))):
        D.put("campfire", fx, fy, 0, "background")
        D.fire_smoke(fx, fy, 0, 14.0, (4.0, 1.0), night=night, seed=60 + k)
    # ---- the engines and the wreckage
    D.floor("siege_engine", x1 - 4.5, y1 - 5.4, 160, "mid", margin=0.3)
    D.floor("siege_engine", x0 + 4.5, cy + 2.2, 25, "mid", damaged=True, margin=0.3)
    D.floor("wrecked_cart", cx + 6.0, y0 + 3.2, 20, "foreground", z=-0.17, seed=1, margin=0.3)
    D.put("wrecked_cart", cx - 18, y1 + 6, 80, "background", seed=3)
    for k in range(D.n(5)):
        D.floor("rubble", D.rnd.uniform(x0 + 1, x1 - 1), D.rnd.uniform(y0 + 1, y1 - 2), 0, "mid", size=D.rnd.uniform(0.9, 1.5), seed=k, margin=0.2)
    for k, (tx, ty) in enumerate(((x0 - 2.5, y0 + 3), (x1 + 4, cy), (cx - 9.0, y1 + 1.5), (cx + 17.0, y1 + 2.5), (x0 + 3.5, y1 + 8), (x1 - 3, y1 + 11))):
        D.put("tree_dead", tx, ty, 0, "mid" if ty < y1 else "background", height=D.rnd.uniform(4.0, 6.5), seed=k)
    for k, (fx, fy, hh) in enumerate(((x0 + 6.0, y0 + 2.4, 9.0), (x1 - 8.5, cy - 1.0, 12.0), (cx + 2.0, y1 + 4.5, 20.0))):
        D.put("campfire", fx, fy, 0, "mid")
        D.fire_smoke(fx, fy, 0, hh, (3.0 + k, 1.0), night=night, seed=k + 5)
    D.put("horse", x1 - 9.0, y0 + 4.0, 130, "mid", coat="#5A4A3A")
    D.put("horse", cx - 4.0, y1 + 2.0, 40, "background", coat="#2F2A28")
    # ---- the ground: churned mud, stones, puddles, broken ground, litter
    D.floor_detail("mud", D.n(22), region=(x0 - 6, y0 - 4, x1 + 6, y1 + 6))
    D.floor_detail("stones", D.n(90), region=(x0 - 6, y0 - 4, x1 + 6, y1 + 8))
    D.floor_detail("puddles", D.n(9), region=(x0, y0, x1, y1))
    D.floor_detail("grass", D.n(80), region=(x0 - 10, y0 - 4, x1 + 10, y1 + 8))
    D.floor_detail("litter", D.n(60), region=(x0, y0, x1, y1))
    D.floor_detail("straw", D.n(40), region=(x0, y0, x1, y1))
    # ---- beyond: hosts, a castle on the ridge, columns of smoke, haze, a drained sky
    sky = "#C2B8B0" if not night else "#242A44"
    _ring_beyond(D, cx, cy + 10, 120.0, D.seed, castle_side=0, night=night, sky=sky, colors=("#5A5A48", "#6A6A5C", "#8A8A88"))
    for k, (ax, ay, aw) in enumerate(((-70, y1 + 68, 70), (62, y1 + 64, 60))):
        D.add(arch.army(aw, ay - cy, rows=4, at=(cx + ax, cy, 0), seed=D.seed + k, color="#3A3A46", sky=sky, night=night), "beyond")
    for k, (sx, sy) in enumerate(((-60, y1 + 52), (-20, y1 + 78), (28, y1 + 66), (66, y1 + 56), (6, y1 + 95))):
        D.fire_smoke(cx + sx, sy, 0, 36.0, (8.0, 2.0), night=night, seed=40 + k)
    D.add(arch.ground_haze((120, 80), (cx, cy + 20, 0), 2.4, "#BDB6AE" if not night else "#262C48", 0.14, D.seed), "beyond")
    D.add(arch.ground_haze((100, 30), (cx, cy + 4, 0), 1.1, "#C9C2B8" if not night else "#2A3350", 0.10, D.seed + 1, 18), "mid")


# ============================================================================= OFFICE BUILDING: lobby, entrance, training room, dim room (set kit v3)
# One building, one layout. The lobby is 14 x 9 m, 4.6 m to the ceiling, its glass front on the south wall (y = 0, the street is -Y). Both the
# interior set (office_lobby) and the exterior set (office_entrance, which builds the same lobby behind the glass) use the same room and the same
# contents, so what the camera sees through the doors outside is what is inside.
LOBBY_SIZE, LOBBY_AT = (14.0, 9.0, 4.6), (0.0, 4.5)
FRONT_Y = -0.125                       # the glass plane: the middle of the south wall (inner face y = 0, outer face y = -0.25)


def office_lobby_room(name: str = "lobby", office: bool = True):
    """The lobby shell: stone floor, painted walls (a dark stone feature wall behind the lifts and the desk), plaster ceiling at 4.6 m, a 12.6 x 4.4 m
    gap in the south wall for the glass front, and (office=True) a 2.4 x 2.6 m opening in the west wall to the open-plan office."""
    ops = [dict(wall="S", kind="gap", w=12.6, h=4.4, at=0.0, id="front")]
    if office:
        ops.append(dict(wall="W", kind="gap", w=2.4, h=2.6, at=1.0, id="to_office"))
    return arch.room(LOBBY_SIZE, at=LOBBY_AT, floor="stone_polished", floor_tint="#B4B9BF", walls={"N": "stone_polished", "S": "painted_wall", "E": "painted_wall", "W": "painted_wall"},
                     ceiling="ceiling_smooth", openings=ops, name=name, thick=0.25, skirting="brushed_metal", cornice="plaster_clean", outside="cladding_panel")


def _hang_free(D, name, W: str, along: float, z: float, layer: str = "background", inset: float = 0.015, **kw):
    """Hang a wall piece in front of a window or opening (blinds, a curtain), where D.hang would refuse because the wall stretch is spoken for."""
    ob = furnish.REGISTRY[name]["fn"](at=(0, 0, z), rot_z=arch.WALL_ROT[W], **kw)
    x, y = D.wall_pos(W, along, inset)
    ob.location = (x, y, z)
    if D.R is not None:
        arch.tag_wall(ob, D.R.name, W)
    return D._record(ob, layer)


def _at_plane(fn, x: float, y_plane: float, z: float = 0.0, **kw):
    """Build a furnish piece and stand it so its glass plane (its anchor "plane") is at y = y_plane."""
    ob = fn(at=(x, 0.0, z), **kw)
    ob.location.y = y_plane - float(ob["sk_anchors"]["plane"][1])
    return ob


def _front(D, layer_glass="mid"):
    """The glass front and the entrance doors in the lobby's south wall, as pieces of that wall (cutaway hides them with it)."""
    gf = _at_plane(furnish.glass_front, 0.0, FRONT_Y, width=12.4, height=4.38, door_at=0.0)
    dr = _at_plane(furnish.glass_doors, 0.0, FRONT_Y, width=1.9, height=2.1)
    for ob in (gf, dr):
        if D.R is not None:
            arch.tag_wall(ob, D.R.name, "S")
        D.add(ob, layer_glass)
    D.refs.update(front=gf, doors=dr)
    return gf, dr


def _lobby_contents(D, wet: bool = False, night: bool = False, office: bool = True):
    """Everything in the lobby: reception, speed gates, lifts, seating, plants, signs, security cameras, vending, bins, umbrellas, a wet-floor sign and
    a mat at the door, ceiling lights, the glass front with its doors, and (office=True) the open-plan office seen through the west opening."""
    R = D.R
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    h = D.h
    _front(D)
    # ---- ceiling: a grid of light panels, real lights, and a deeper cove along the glass
    for xx in (-4.6, 0.0, 4.6):
        for yy in (1.6, 4.5, 7.4):
            D.ceiling_piece("ceiling_light_panel", xx, yy, "mid", size=(1.6, 0.8), power=70.0)
    # ---- ceiling fittings: downlights along the glass and round the desk, linear vents, smoke detectors
    for xx in (-5.4, -3.6, -1.8, 1.8, 3.6, 5.4):
        D.ceiling_piece("downlight", xx, 0.75, "foreground", power=22.0)
    for xx in (2.0, 3.4, 4.8, 6.2):
        D.ceiling_piece("downlight", xx, 2.4, "mid", power=22.0)
    for xx, yy in ((-2.3, 3.0), (2.3, 6.0), (-5.6, 5.5)):
        D.ceiling_piece("ceiling_vent", xx, yy, "mid", length=1.4)
    for xx, yy in ((-3.0, 4.6), (3.2, 4.6), (0.0, 8.4)):
        D.ceiling_piece("smoke_detector", xx, yy, "mid")
    for xx in (-4.2, -1.4, 1.4, 4.2):
        D.ceiling_piece("downlight", xx, 5.0, "mid", power=22.0)
        D.ceiling_piece("downlight", xx, 5.9, "background", power=22.0)
    for xx in (-5.2, -2.6, 0.0, 2.6, 5.2):
        D.ceiling_piece("downlight", xx, 6.9, "background", power=22.0)
        D.ceiling_piece("downlight", xx, 3.2, "mid", power=22.0)
        D.ceiling_piece("downlight", xx, 8.3, "background", power=22.0)
    # ---- the door: mat, wet-floor sign, umbrellas
    D.floor("floor_mat", 0.0, 1.25, 0, "foreground", flat=True, margin=0.0, marks=False, wet=wet)
    D.floor("wet_floor_sign", 2.35, 1.0, 12, "foreground", margin=0.0, marks=False)
    D.floor("umbrella_stand", -2.35, 0.65, 0, "foreground", margin=0.0, marks=False)
    # ---- reception on the east side, facing the door
    desk = D.floor("reception_desk", 4.2, 4.1, 0, "mid", margin=0.0, marks=False, length=3.4, wing=1.7)
    D.refs["reception"] = desk
    if desk:
        for nm in ("mugs", "papers_stack", "office_phone"):
            D.top(desk, nm, k=0)
        ax, ay, _az = desk["sk_anchors"]["receptionist"]
        D.floor("chair_office", desk.location.x + ax, desk.location.y + ay, 180 + 15, "mid", margin=0.0, marks=False, color="#26303C")
    # ---- speed gates between the door and the lifts
    D.refs["gate"] = D.floor("badge_gate", 0.0, 3.9, 0, "mid", margin=0.0, marks=False, lanes=3)
    # ---- queue posts with belts in front of the desk, a sanitiser station by the gates
    for k, (sx, sy, bx, by) in enumerate(((2.6, 1.9, 1.5, 0.0), (4.1, 1.9, 1.5, 0.0), (5.6, 1.9, 0.0, 0.0))):
        D.floor("stanchion", sx, sy, 0, "mid", margin=0.0, marks=False, belt_to=((bx, by) if bx else None))
    D.floor("sanitiser_stand", 1.9, 3.15, 0, "mid", margin=0.0, marks=False)
    # ---- lifts on the north wall
    D.refs["lifts"] = D.against("lift_doors", "N", -3.2, "background", gap=0.0, margin=0.0, count=2, floor="G")
    # ---- seating group in the south-west corner
    sofa = D.floor("sofa", -4.3, 1.45, 180, "foreground", margin=0.0, marks=False, length=2.2, color="#5E7A84")
    ct = D.floor("coffee_table", -4.3, 2.75, 0, "mid", margin=0.0, marks=False, length=1.1, depth=0.6)
    if ct:
        D.top(ct, "magazines", k=0)
        D.top(ct, "mugs", k=0)
    D.floor("lounge_chair", -6.0, 2.75, -90, "mid", margin=0.0, marks=False, color="#0E6B78")
    D.floor("lounge_chair", -2.6, 2.75, 90, "mid", margin=0.0, marks=False, color="#C98A2E")
    arch_rug = arch.rug_area(size=(3.6, 2.8), at=(-4.3, 2.2, 0.0), surface="carpet_grey", border="#0E6B78", border_w=0.14, fringe=False, name="lobby_rug", tint="#8FA2AB")
    D.add(arch_rug, "mid")
    # ---- plants
    for k, (px, py, hh) in enumerate(((-6.55, 0.55, 1.9), (6.4, 0.55, 1.7), (6.4, 6.9, 1.6), (0.7, 8.35, 1.8), (-6.55, 8.2, 1.7), (-6.5, 3.9, 1.5), (-6.5, 6.8, 1.4), (6.45, 8.3, 1.6))):
        D.floor("potted_plant", px, py, 0, "background" if py > 5 else "foreground", height=hh, pot_r=0.26, seed=k + 3, margin=0.0, marks=False)
    # ---- east wall: vending, recycling, extinguisher, screen, notice board, clock
    D.against("vending_machine", "E", -2.9, "mid", margin=0.0, seed=2)
    D.against("recycling_bins", "E", -1.45, "mid", margin=0.0)
    D.hang("fire_extinguisher", "E", -0.2, z=0.35, layer="background")
    D.hang("wall_screen", "E", 1.8, z=1.55, layer="background", width=1.5, image="slide", look="clean", stamp=False)
    D.hang("notice_board", "E", 3.4, z=1.45, layer="background", width=1.0, height=0.75, seed=4)
    # ---- north wall: the logo behind reception, a clock between it and the lifts
    D.hang("wall_logo", "N", 3.7, z=1.9, layer="background", width=3.2)
    D.hang("wall_clock", "N", 0.45, z=3.1, layer="background", radius=0.26)
    # ---- west wall: exit sign over the opening, coat hooks, a poster
    D.hang("exit_sign", "W", 1.0, z=2.86, layer="background")
    D.hang("poster", "W", -1.2, z=1.5, layer="background", color="#0E6B78", seed=3, width=0.7, height=1.0)
    D.hang("painting_framed", "W", -3.0, z=1.7, layer="background", width=1.2, height=0.8, seed=5)
    D.hang("painting_framed", "N", 6.3, z=1.7, layer="background", width=0.7, height=1.0, seed=6)
    D.hang("painting_framed", "E", 4.3, z=1.9, layer="background", width=0.9, height=0.65, seed=7)
    D.hang("coat_hooks", "W", 2.9, z=1.55, layer="background", hooks=4)
    D.hang("painting_framed", "W", -2.0, z=1.7, layer="background", width=0.6, height=0.8, seed=8)
    D.hang("painting_framed", "W", -4.2, z=1.7, layer="background", width=0.6, height=0.8, seed=9)
    D.hang("wall_screen", "W", -0.6, z=1.4, layer="background", width=1.1, image="slide", look="clean", stamp=False)
    D.hang("poster", "N", 0.4, z=1.2, layer="background", color="#E0A82E", seed=2, width=0.5, height=0.7)
    D.hang("wall_shelf", "W", -3.9, z=1.1, layer="background", length=1.1)
    D.floor("floor_lamp", -6.45, 3.65, 0, "mid", margin=0.0, marks=False, height=1.55)
    D.floor("side_table", -6.4, 1.55, 0, "foreground", margin=0.0, marks=False, size=0.5)
    D.floor("bin", -0.6, 8.55, 0, "background", margin=0.0, marks=False)
    # ---- security cameras: the dome high in the north-east corner looks across the gates at the door (the lift core fills the north-west corner:
    # a camera there looks into its doors), a bullet over the vending machine
    cam = D.hang("security_camera", "N", 6.35, z=3.65, layer="background", kind="dome")
    D.hang("security_camera", "E", -2.9, z=3.2, layer="background", kind="bullet", state="red")
    D.refs["camera"] = cam
    # ---- the street door's frame of reference: wet footprints near the door in rain
    if wet:
        D.floor_detail("puddles", 5, region=(-1.6, 0.35, 1.6, 2.2), name="wet_floor")
    # ---- the open-plan office beyond the west opening
    if office:
        _office_beyond(D, night)


def _office_beyond(D, night: bool):
    """A short stretch of open-plan office behind the west opening, lit, so a camera looking through the opening sees desks and people's places."""
    cy = 4.5
    R2 = arch.room((9.5, 7.0, 2.8), at=(-12.25, cy), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile",
                   openings=[dict(wall="E", kind="gap", w=2.4, h=2.6, at=1.0, id="to_lobby")], name="office_beyond", thick=0.25, skirting="brushed_metal", cornice="plaster_clean")
    D2 = Dresser(None, "office_open_plan", {}, 0.8, D.seed + 5, 0.4, None, R2)
    THEMES["office_open_plan"]["fn"](D2)
    D.made.extend(D2.made)
    D.refs["office"] = R2
    lights.ambient_fill((-12.25, cy, 2.6), (8, 6), power=28 if not night else 14, color="#EAF0FF")


@theme("office_lobby", ["modern"])
def office_lobby(D):
    """The lobby of a glass office building (see the section comment): needs office_lobby_room()'s room. opts: wet=True (rain on the floor near the door),
    night=True, office=False (no open-plan office behind the west opening), outside=True (default: the forecourt, kerb, road and street furniture
    seen through the glass, with the doors' card reader)."""
    wet, night = bool(D.opts.get("wet", False)), bool(D.night)
    D.refs = {}
    _lobby_contents(D, wet, night, D.opts.get("office", True))
    if D.opts.get("outside", True):
        _street(D, wet, night, outside_only=True)
        _entrance_outside(D, wet, night)
        _city(D, night)
    lights.ambient_fill((0, 4.5, 4.2), (12, 8), power=(30 if night else 55), color="#FFEFD8")


# ----------------------------------------------------------------------------- the street outside the front doors
def _street(D, wet: bool, night: bool, outside_only: bool = False):
    """The pavement (top at z = 0), a kerb, a two-way road with a parking lane each side (top at z = -0.14), the far pavement, road markings and a
    zebra crossing, and the paved apron under everything. Pavement and road are wet in rain (darker, glossy)."""
    x0, x1 = -34.0, 34.0
    cx, W_ = (x0 + x1) / 2, x1 - x0
    pav = "paving_wet" if wet else "paving"
    road = "asphalt_wet" if wet else "asphalt"
    D.ground("concrete", z=-0.16, size=160)
    p = Parts("pavement", "SET", "pavement", kind="shell")
    p.box((W_, 5.25, 0.3), (cx, -0.25 - 2.625, -0.3), pav, bevel=0.0)
    p.box((W_, 3.6, 0.3), (cx, -14.4 - 1.8, -0.3), pav, bevel=0.0)
    D.add(p.build(at=(0, 0, 0), recentre=False), "mid")
    kb = Parts("kerb", "SET", "kerb", kind="shell")
    kb.box((W_, 0.2, 0.16), (cx, -5.6, -0.16), "concrete", bevel=0.012)
    kb.box((W_, 0.2, 0.16), (cx, -14.4, -0.16), "concrete", bevel=0.012)
    D.add(kb.build(at=(0, 0, 0), recentre=False), "mid")
    rd = Parts("road", "SET", "road", kind="shell")
    rd.box((W_, 8.6, 0.4), (cx, -10.0, -0.54), road, bevel=0.0)
    D.add(rd.build(at=(0, 0, 0), recentre=False), "mid")
    D.add(arch.road_markings(W_, 8.6, at=(cx, -10.0, -0.14), crossings=(-12.0,), edge=True), "mid")
    if wet:
        D.floor_detail("puddles", 7, region=(-9.0, -5.0, 9.0, -0.8), name="pavement_puddles")
    D.floor_detail("leaves", D.n(26), region=(-12.0, -5.2, 12.0, -0.6))
    D.floor_detail("litter", D.n(14), region=(-12.0, -5.2, 12.0, -0.6))


def _entrance_outside(D, wet: bool, night: bool):
    """What stands at the doors on the pavement: the canopy with its drips, the card reader post, planters, a bench, bollards, the totem sign, the
    outside mat, a bike rack with two bikes, lamps, a bus stop, a tree, litter bins, parked cars along the kerb and across the road."""
    colors = ["#2B3B4E", "#B3322C", "#2D6CB0", "#D8A93A", "#5B6770", "#3F8F5A"]
    D.zbase = 0.0
    # the canopy: bolted to the glass front, 3.3 m up, 7 m wide, 2.6 m deep
    cp = furnish.entrance_canopy(at=(0.0, -0.27, 3.3), width=7.0, depth=2.6, spots=4)
    D.add(cp, "mid")
    D.refs["canopy"] = cp
    # the card reader post beside the doors, and the mat outside
    rp = D.put("card_reader_post", 1.55, -0.95, 0, "mid", state="red", avoid=False)
    D.refs["reader"] = rp
    D.put("floor_mat", 0.0, -1.0, 0, "mid", wet=wet, size=(2.2, 1.2), avoid=False)
    for sx in (-1, 1):
        D.put("planter_box", sx * 4.4, -1.1, 0, "mid", length=2.0, width=0.75, seed=3 + sx, shrubs=5, avoid=False)
    D.put("bench_modern", -4.6, -3.9, 0, "foreground", length=1.8, avoid=False)
    D.put("bench_modern", 6.5, -3.9, 0, "foreground", length=1.8, avoid=False)
    for k, x in enumerate((-7.5, -5.0, -2.5, 0.0, 2.5, 5.0, 7.5)):
        D.put("bollard", x, -5.0, 0, "foreground", avoid=False)
    D.put("company_totem", -6.4, -1.6, 0, "mid", height=2.4, avoid=False)
    D.put("bike_rack", 9.2, -1.4, 0, "mid", hoops=4, avoid=False)
    for k, x in enumerate((8.4, 10.0)):
        D.put("bicycle", x, -2.0, 0, "mid", color=["#C8433A", "#2E6FA3"][k], avoid=False)
    # lamps (the arm reaches over the road), a bus stop, a street sign, a tree, a hydrant, bins
    for x in (-10.5, 4.0, 12.5):
        D.put("lamp_post", x, -5.0, 0, "mid", height=5.6, style="modern", power=(900.0 if night else 200.0), avoid=False)
    for x in (-8.0, 7.0):
        D.put("lamp_post", x, -15.0, 180, "background", height=5.6, style="modern", power=(900.0 if night else 200.0), avoid=False)
    D.put("bus_stop", -12.5, -3.6, 0, "mid", length=3.0, avoid=False)
    D.put("street_sign", -15.4, -4.9, 0, "mid", kind="bus", avoid=False)
    D.put("traffic_light", 10.5, -5.0, 0, "mid", state="red", avoid=False)
    D.put("tree_round", -7.6, -4.4, 0, "mid", z=0.0, height=5.2, crown=1.7, seed=7, avoid=False)
    D.put("tree_round", 11.2, -4.4, 0, "mid", z=0.0, height=5.0, crown=1.6, seed=9, avoid=False)
    for x in (-8.8, 7.6, 12.0):
        D.put("bin", x, -4.3, 0, "foreground", avoid=False)
    D.put("hydrant", 6.1, -5.0, 0, "foreground", avoid=False)
    D.put("post_box", -9.9, -4.4, 0, "mid", avoid=False)
    # cars: parked on the near lane (clear of the entrance) and the far lane, one in the traffic
    for k, x in enumerate((-16.0, -9.5, 9.5, 16.0)):
        D.put("car", x, -6.85, 90, "mid", z=-0.14, color=colors[k % len(colors)], avoid=False)
    for k, x in enumerate((-12.0, -5.0, 3.5, 12.0)):
        D.put("car", x, -13.2, -90, "background", z=-0.14, color=colors[(k + 3) % len(colors)], avoid=False)
    D.put("car", 5.5, -9.8, 90, "mid", z=-0.14, color="#F2C200", avoid=False)


def _city(D, night: bool):
    """The city round the entrance: house fronts left and right on the building line, a row across the road, two glass-and-panel blocks behind it,
    tall blocks closing both ends of the street, the skyline and a ground haze."""
    cx, cy = D.at
    # neighbours: house fronts left and right on the building line, a row across the road, a tall glass block behind it
    tints = [None, "#D8DADD", "#C8CED6", "#E6D8C6", "#B8C0C8"]
    for (a, b) in (((-62.0, -0.25), (-7.6, -0.25)), ((7.6, -0.25), (62.0, -0.25))):
        D.house_row(a, b, 0.0, styles=("modern", "brick", "modern"), storeys=(4, 8), width=(6.0, 9.0), gap=(0.0, 0.0), awning=True, night=night, signs=0.0, smoke_p=0.0,
                    flowers=0.0, tints=tints, lit=0.5 if not night else 0.9, roofs=["concrete"], depth=10.0)
    D.house_row((-62.0, -18.4), (62.0, -18.4), 180.0, styles=("brick", "modern", "modern", "brick"), storeys=(4, 7), width=(6.0, 10.0), gap=(0.0, 0.0), awning=True, night=night,
                signs=0.0, smoke_p=0.0, flowers=0.0, tints=tints, lit=0.5 if not night else 0.9, roofs=["concrete"], depth=10.0)
    D.add(arch.office_front(width=26.0, storeys=15, storey_h=3.6, style="glass", base=0.0, depth=16.0, at=(-6.0, -33.0, 0.0), rot_z=180.0, seed=D.seed + 8, lit=0.3 if not night else 0.7, night=night), "beyond")
    D.add(arch.office_front(width=18.0, storeys=11, storey_h=3.5, style="panel", base=0.0, depth=14.0, at=(24.0, -34.0, 0.0), rot_z=180.0, seed=D.seed + 9, lit=0.3 if not night else 0.7, night=night), "beyond")
    # the street is closed at both ends by a tall block, and the towers stand beyond
    D.add(arch.house_front(storeys=9, style="modern", width=24.0, depth=12.0, at=(52.0, -9.0, 0), rot_z=-90.0, seed=D.seed + 40, night=night, lit=1.2 if night else 0.7, roof_surface="concrete"), "beyond")
    D.add(arch.house_front(storeys=8, style="brick", width=22.0, depth=12.0, at=(-52.0, -9.0, 0), rot_z=90.0, seed=D.seed + 41, night=night, lit=1.2 if night else 0.7, roof_surface="concrete"), "beyond")
    for k, rot in enumerate((0, 90, 180, 270)):
        sk = arch.skyline(240.0, 70.0 if k % 2 == 0 else 95.0, at=(cx, cy - 6.0, 0), kind="city", seed=D.seed + k, night=night, sky_card=False)
        sk.rotation_euler.z = math.radians(rot)
        D.add(sk, "beyond")
    D.add(arch.ground_haze((70.0, 10), (0.0, -9.0, 0), 2.4, "#D8DDE4" if not night else "#2A3350", 0.10, D.seed), "beyond")


@theme("office_entrance", ["modern"], "exterior")
def office_entrance(D):
    """The front of a sleek glass office building on a city street, rain or shine: a glazed lobby (the same lobby as the office_lobby theme, lit, with
    the reception desk, speed gates and lifts seen through the glass) behind double glass doors under a canopy, the card reader post, the NORTHLINE
    sign on the facade and on a totem, storeys of curtain wall rising out of frame, a pavement with kerb, bollards, planters, benches, a bike rack, lamps
    and a bus stop, a road with parked cars, neighbouring fronts to the left and right, a row of buildings and a glass tower across the street, and a
    skyline beyond. opts: wet=True (rain-soaked pavement and road), night=True."""
    night, wet = bool(D.night), bool(D.opts.get("wet", False))
    cx, cy = D.at
    D.refs = {}
    _street(D, wet, night)
    R = office_lobby_room(name="lobby", office=False)
    D2 = Dresser(None, "office_lobby", {}, 1.0, D.seed + 2, 0.5, None, R)
    D2.refs = D.refs
    D2.night, D2.opts = night, dict(D.opts)
    _lobby_contents(D2, wet, night, office=False)
    lights.ambient_fill((0, 4.5, 4.2), (12, 8), power=(30 if night else 55), color="#FFEFD8")
    D.made.extend(D2.made)
    # the lobby's side walls and back face the street only at an angle: nothing is needed there. Above the lobby the glass tower of offices:
    up = arch.office_front(width=14.5, storeys=9, storey_h=3.6, style="glass", base=4.6, depth=13.0, at=(0.0, -0.25, 0.0), seed=D.seed + 1, lit=0.32 if not night else 0.75, night=night)
    D.add(up, "background")
    D.add(furnish.wall_logo(at=(-0.4, -0.42, 4.8), width=3.0, glow=1.4 if night else 0.0), "mid")
    _entrance_outside(D, wet, night)
    _city(D, night)


# ============================================================================= THE TRAINING ROOM
@theme("training_room", ["modern"])
def training_room(D):
    """A bright corporate training room, 9 x 7.5 m: twelve seats with tablet arms in three rows facing the screen on the north wall, a lectern and
    flipchart, a whiteboard and notice board, windows with blinds and a city vista on the east wall, a ceiling projector, light panels, a side table with
    water and cups, plants, a clock and a glass door. opts: night=True."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    h = D.h
    D.refs = {}
    for xx in (-2.2, 2.2):
        for yy in (1.6, 3.8, 6.0):
            D.ceiling_piece("ceiling_light_panel", xx, yy, "mid", size=(1.2, 0.6), power=60.0)
    # the screen and what hangs round it
    D.refs["screen"] = D.hang("wall_screen", "N", 0.0, z=1.2, layer="background", width=2.9, image="footage", look="footage", stamp=True, label="LOBBY CAM 2    MON 08:47:12")
    D.hang("whiteboard", "N", -3.15, z=1.0, layer="background", width=1.2, height=1.0, seed=4)
    D.hang("notice_board", "N", 3.3, z=1.3, layer="background", width=0.9, height=0.8, seed=5)
    D.hang("wall_clock", "N", 3.3, z=2.55, layer="background", radius=0.22)
    # projector: over the middle of the room, aiming at the screen
    pj = furnish.ceiling_projector(at=(0.0, 3.4, h), rot_z=180.0, drop=0.45)
    arch.tag_wall(pj, R.name, "C")
    D.add(pj, "mid")
    D.refs["projector"] = pj
    # twelve seats, sitters facing +Y
    seats = []
    cols = ["#2F6FA3", "#2F6FA3", "#2F6FA3", "#2F6FA3"]
    for r, yy in enumerate((1.9, 3.15, 4.4)):
        for c_, xx in enumerate((-1.95, -0.65, 0.65, 1.95)):
            s = D.floor("training_seat", xx, yy, 180, "foreground" if r == 0 else "mid", margin=0.0, marks=False, color=("#2F6FA3" if (r + c_) % 3 else "#0E6B78"), arm="right")
            seats.append(s)
            if s is not None:
                D.top(s, D.rnd.choice(["laptop_closed", "coffee_cup", "papers_stack", "book_stack"]), k=0)
    D.refs["seats"] = seats
    D.refs["lectern"] = D.floor("lectern", -2.6, 6.5, 0, "background", margin=0.0, marks=False)
    D.refs["flipchart"] = D.floor("flipchart", 3.1, 6.4, -12, "background", margin=0.0, marks=False)
    st = D.floor("side_table", 3.8, 5.2, 0, "background", margin=0.0, marks=False, size=0.6)
    if st:
        D.top(st, "water_jug_set", k=0)
    for k, (px, py, hh) in enumerate(((-4.0, 6.7, 1.7), (4.0, 0.7, 1.5), (-4.0, 0.7, 1.3))):
        D.floor("potted_plant", px, py, 0, "background" if py > 3 else "foreground", height=hh, seed=k + 5, margin=0.0, marks=False)
    D.floor("bin", 4.1, 4.3, 0, "mid", margin=0.0, marks=False)
    D.floor("coat_stand", -4.1, 1.8, 0, "mid", margin=0.0, marks=False, coats=2)
    D.hang("poster", "W", 1.9, z=1.5, layer="background", color="#0E6B78", seed=8, width=0.7, height=1.0)
    D.hang("poster", "W", 0.5, z=1.5, layer="background", color="#D95D39", seed=9, width=0.7, height=1.0)
    D.hang("fire_extinguisher", "W", -1.6, z=0.35, layer="background")
    D.hang("exit_sign", "S", -3.2 + 0.0, z=2.5, layer="foreground")
    D.hang("security_camera", "S", 3.6, z=2.5, layer="foreground", kind="dome", state="green")
    # blinds in the east windows (three), lowered by different amounts
    for k, along in enumerate((-2.4, 0.0, 2.4)):
        _hang_free(D, "window_blinds", "E", along, 2.55, "background", width=2.1, height=1.6, drop=(0.5, 0.35, 0.6)[k], tilt=(30, 22, 36)[k])
    for k, along in enumerate((-2.4, 0.0, 2.4)):                              # radiators under the windows
        D.hang("radiator", "E", along, z=0.2, layer="background", length=1.4)
    D.against_any("water_cooler", "W", near=1.5, layer="background")
    D.against_any("filing_cabinet", "W", near=-0.6, layer="background", drawers=3)
    D.against_any("bookcase", "W", near=-2.6, layer="background", width=1.0, seed=2)
    D.hang("painting_framed", "S", 1.2, z=1.8, layer="foreground", width=1.0, height=0.7, seed=3)
    D.hang("coat_hooks", "S", 2.9, z=1.55, layer="foreground", hooks=4)
    D.hang("poster", "W", -2.0, z=1.5, layer="background", color="#2D7DD2", seed=4, width=0.6, height=0.85)
    for xx, yy in ((-3.0, 2.8), (3.0, 2.8)):
        D.ceiling_piece("ceiling_vent", xx, yy, "mid", length=1.3)
    for xx, yy in ((-1.4, 5.2), (1.4, 5.2), (0.0, 1.0)):
        D.ceiling_piece("smoke_detector", xx, yy, "mid")
    for xx in (-3.3, -1.1, 1.1, 3.3):
        D.ceiling_piece("downlight", xx, 6.9, "background", power=16.0)
        D.ceiling_piece("downlight", xx, 3.0, "mid", power=16.0)
    D.hang("wall_clock", "S", -1.2, z=2.45, layer="foreground", radius=0.2)
    D.hang("painting_framed", "W", 2.6, z=1.7, layer="background", width=0.9, height=0.7, seed=6)
    _training_corridor(D)
    D.floor_detail("papers", D.n(4), region=(x0 + 1, y0 + 1, x1 - 1, y1 - 1))


def _training_corridor(D):
    """The corridor outside the training room's glass door: a short lit passage with a plant and a fire-door sign, so the door never opens on a void."""
    R2 = arch.room((3.4, 3.2, 2.8), at=(-3.4, -1.85), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile",
                   openings=[dict(wall="N", kind="gap", w=1.1, h=2.25, at=0.0, id="to_training"),
                             dict(wall="W", kind="window", type="office", w=1.6, h=1.3, sill=1.0, at=0.0, id="corridor_win")],
                   name="corridor", thick=0.25, skirting="brushed_metal", cornice="plaster_clean")
    arch.vista(R2, "W", "city_day", distance=14, seed=9)
    D2 = Dresser(None, "office_private", {}, 0.5, D.seed + 3, 0.3, None, R2)
    D2.ceiling_piece("ceiling_light_panel", -3.4, -1.6, "mid", size=(1.2, 0.6), power=45.0)
    D2.floor("potted_plant", -4.9 + 0.55, -2.7, 0, "mid", margin=0.0, marks=False, height=1.5, seed=4)
    D2.hang("exit_sign", "S", 0.0, z=2.3, layer="mid")
    D2.hang("fire_extinguisher", "E", 0.4, z=0.35, layer="mid")
    D2.hang("notice_board", "E", -0.8, z=1.3, layer="mid", width=0.8, height=0.6, seed=2)
    D.made.extend(D2.made)
    lights.ambient_fill((-3.4, -1.85, 2.5), (3.0, 2.8), power=18, color="#F4F6FF")


# ============================================================================= THE DIM ROOM (a night insert: one lit screen in a dark room)
@theme("dim_room", ["modern"])
def dim_room(D):
    """A small dark room at night, 4.2 x 3.4 m: a desk against the north wall with a market page glowing on the monitor and an open laptop, a chair
    turned toward it, shelves and bookcases with boxes and books, cables across the floor, a router and a power strip with their lights, mugs, cans,
    headphones and a pizza box, a switched-off lamp, posters, a window with a streetlight outside. The only real light is the screens and the little lamps."""
    R = D.R
    cx, cy = D.at
    x0, y0, x1, y1 = D.lo[0], D.lo[1], D.hi[0], D.hi[1]
    D.refs = {}
    ds = D.floor("desk_office", cx - 0.55, y1 - 0.5, 0, "mid", margin=0.0, marks=False, length=1.7, depth=0.8, color="#7A6A58")
    D.refs["desk"] = ds
    if ds:
        D.refs["monitor"] = D.top(ds, "desk_monitor", k=1, width=0.62, image="listing", glow=55.0)
        D.refs["laptop"] = D.top(ds, "laptop_open", k=1, image="listing")
        for nm, kw in (("mugs", {}), ("mugs", {}), ("energy_can", {}), ("energy_can", dict(color="#C8433A")), ("headphones", {}), ("papers_stack", {}),
                       ("desk_lamp", dict(on=False)), ("book_stack", {}), ("office_phone", {}), ("energy_can", dict(color="#3A6FD8")), ("photo_frame", {})):
            D.top(ds, nm, k=1, **kw)
    D.floor("chair_office", cx - 0.6, y1 - 1.55, 192, "mid", margin=0.0, marks=False, color="#2A2F38")
    cab = D.floor("filing_cabinet", x0 + 0.33, y1 - 1.5, 90, "background", margin=0.0, marks=False, drawers=3)
    if cab:
        D.top(cab, "router", k=0)
        D.top(cab, "power_strip", k=0)
        D.top(cab, "energy_can", k=0)
    D.hang("poster", "N", -1.05, z=1.55, layer="background", color="#3A2F5A", seed=11, width=0.45, height=0.65)
    D.hang("poster", "N", -1.9, z=1.4, layer="background", color="#5A2F2F", seed=12, width=0.4, height=0.6)
    D.hang("notice_board", "E", 0.6, z=1.2, layer="background", width=0.8, height=0.6, seed=14)
    D.hang("whiteboard", "W", -0.7, z=1.0, layer="background", width=0.9, height=0.7, seed=21)
    for W_, nr, sd in (("W", -1.0, 2), ("E", -0.8, 3)):
        bc = D.against_any("bookcase", W_, near=nr, layer="background", width=0.9, height=1.9, seed=sd)
        if bc:
            for nm in ("storage_box", "potted_plant", "papers_stack"):
                D.top(bc, nm, k=0, **({"height": 0.5} if nm == "potted_plant" else {}))
    D.shelves(["book_stack", "mugs", "papers_stack", "bottle", "photo_frame", "energy_can", "globe"], n=5, per_shelf=5, walls="EW")
    _hang_free(D, "window_blinds", "N", 1.4, 2.3, "background", width=1.15, height=1.2, drop=0.5, tilt=40, inset=0.04)
    D.hang("coat_hooks", "E", 1.0, z=1.55, layer="background", hooks=3)
    D.hang("wall_clock", "E", 0.0 - 1.2, z=2.15, layer="background", radius=0.14)
    D.floor("bin", x1 - 0.5, y1 - 1.3, 0, "mid", margin=0.0, marks=False)
    D.floor("potted_plant", x0 + 0.45, y0 + 0.75, 0, "foreground", margin=0.0, marks=False, height=1.05, seed=3)
    for k, (bx, by, rz) in enumerate(((-0.8, 0.85, 8), (-0.7, 0.85, -12), (0.75, 0.95, 20))):
        D.floor("storage_box", bx, by, rz, "foreground", margin=0.0, marks=False, seed=k + 1)
    D.floor("pizza_box", 0.25, 1.05, 25, "foreground", margin=0.0, marks=False)
    D.floor("energy_can", -1.2, 1.2, 0, "foreground", margin=0.0, marks=False, color="#C8433A")
    D.floor("storage_box", x0 + 0.4, y1 - 1.0, 0, "mid", margin=0.0, marks=False, seed=7)
    cb = Parts("cables", "SET", "cables", kind="prop")
    black = mat.solid("#101214", 0.5)
    pts = [(cx + 0.3, y1 - 0.7), (cx + 0.2, y1 - 1.1), (cx + 0.55, y1 - 1.5), (cx + 1.2, y1 - 1.45), (x1 - 0.35, y1 - 1.2)]
    for a, b in zip(pts, pts[1:]):
        cb.rod((a[0], a[1], 0.012), (b[0], b[1], 0.012), 0.008, black, seg=4)
    for a, b in (((cx - 0.9, y1 - 0.6), (cx - 1.3, y1 - 1.3)), ((cx - 1.3, y1 - 1.3), (cx - 1.9, y1 - 1.2))):
        cb.rod((a[0], a[1], 0.012), (b[0], b[1], 0.012), 0.008, mat.solid("#C8C4B8", 0.5), seg=4)
    D.add(cb.build(at=(0, 0, 0), recentre=False), "mid")
    D.floor_detail("papers", D.n(6), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 1.2))
    D.floor_detail("litter", D.n(10), region=(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 1.2))
    p = Parts("led_strip", "SET", "led_strip", kind="prop")
    p.box((1.2, 0.012, 0.012), (0, 0, 0), p.glow("#7B5CFF", 3.0), bevel=0.0)
    p.light("led", (0, -0.1, -0.05), "#7B5CFF", 18.0, 0.05, False, "AREA", aim=(0, -1.0, -0.6), size=1.0)
    ls = p.build(at=(x1 - 0.12, cy - 0.2, 1.7), rot_z=90.0, recentre=False)
    ls["sk_mount"] = 1
    D.add(ls, "background")
    lights.ambient_fill((cx, cy, 2.4), (3.8, 3.0), power=3.0 if D.night else 9.0, color="#9FB4FF")


POOLS["office_lobby"] = dict(top=["magazines", "mugs", "papers_stack"], wall=["poster", "notice_board"])
POOLS["office_entrance"] = dict()
POOLS["training_room"] = dict(top=["papers_stack", "mugs", "book_stack"], floor=["potted_plant", "bin"], wall=["poster"])
POOLS["dim_room"] = dict(top=["mugs", "papers_stack"], floor=["bin"], wall=["poster"])
