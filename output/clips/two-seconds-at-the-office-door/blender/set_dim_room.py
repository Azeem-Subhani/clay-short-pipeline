"""dim_room - a dark private room across the city at night, where the stolen files are for sale ("Two Seconds at the Office Door": sh05).

Adapted from examples/sets/set_dim_room.py for this clip. A deliberately small INSERT set: the plan shows it only in tight views from a seated
eye height a metre in front of the desk, so the WIDE below is that insert framing (from just behind the chair), not a room-wide; it does not reach
the 60-object threshold of a whole room and is not padded to do so.

    marks first       the plan's four marks: the desk front, the chair turned to it, the window right of the desk, the door
    then the place    arch.room 4.2 x 3.4 x 2.6 m, dark carpet, plain walls, a window (night city, streetlight glow) and a closed door; dress.room
                      "dim_room"; then the desk is re-laid for the story: the stranger's brown leather messenger bag (prop_messenger_bag), flap open,
                      on the desk's LEFT FRONT corner nearest the camera; the stolen laptop open on the left of the desk showing a folder list headed
                      CLIENTS (200); the monitor centre-right showing the auction page (rows of client folders with price tags and BID buttons);
                      a shelf over the desk with box files and books in the glow, sticky notes on the monitor bezel, cables down the back of the desk
    then the light    no ceiling light: the screens (the monitor has a real glow light, the laptop gets a small one), router and power-strip lamps,
                      the violet LED strip, a faint orange streetlight shaft through the blinds, a weak cool fill so the dark stays deep blue

The two screen pictures are generated here (numpy, a 5x7 pixel font): screen_picture("clients") and screen_picture("auction", step) -
step 0..3 raises every price, so a shot can tick the prices up with furnish.screen_set_image-like swaps (see set_screen()).
Camera side is -Y. Times: "office_night".
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from stagekit import arch, core, dress, furnish, lights, mat

THEME = "dim_room"
SIZE = (4.2, 3.4, 2.6)
MARK = {
    "desk": (-0.55, 2.55, 0.0),            # the desk's front
    "chair": (-0.6, 1.85, 0.0),            # the chair, turned toward the desk
    "window": (1.4, 2.7, 0.0),             # in front of the window (north wall, right of the desk)
    "door": (-1.6, 0.45, 0.0),             # just inside the door (south wall)
}
# the worked file's wide (from just inside the door, at a seated person's eye height, looking at the screens): the six-angle sheet is built round
# it; the plan's insert framings (bag in the foreground, the two screens) are checked separately (INSERTS) - they are where the set is judged
WIDE = ((1.7, 0.3, 1.45), (-0.7, 2.9, 1.0), 15.0)
INSERTS = {"records": ((-0.95, 1.95, 1.2), (-0.8, 3.05, 0.9), 32.0), "auction": ((-0.25, 1.95, 1.2), (-0.1, 3.2, 1.05), 32.0)}
LIGHT = {"office_night": dict(street=6.0, fill=4.0)}

# ----------------------------------------------------------------------------- the screen pictures
_FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"], "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"], "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"], "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"], "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"], ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    "$": ["00100", "01111", "10100", "01110", "00101", "11110", "00100"], " ": ["00000"] * 7, ":": ["00000", "00100", "00000", "00000", "00000", "00100", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    ",": ["00000", "00000", "00000", "00000", "00110", "00100", "01000"], "#": ["01010", "11111", "01010", "01010", "11111", "01010", "00000"],
}


def _text(img, s, x, y, scale, col):
    """Draw s on img (rows top-down) at pixel x, y (top-left) with a 5x7 font scaled by `scale`."""
    for ch in s.upper():
        g = _FONT.get(ch, _FONT[" "])
        for r, row in enumerate(g):
            for c, b in enumerate(row):
                if b == "1":
                    img[y + r * scale:y + (r + 1) * scale, x + c * scale:x + (c + 1) * scale] = col
        x += 6 * scale
    return x


def _folder(img, x, y, w, h, col):
    img[y + h // 5:y + h, x:x + w] = col
    img[y:y + h // 5 + 1, x:x + w // 2] = col


def screen_picture(kind: str, step: int = 0):
    """'clients': the stolen laptop's folder list under CLIENTS (200). 'auction': the market page, client folders in rows with price tags that
    rise with `step`. Returns a packed bpy image (Non-Color, like the kit's built-in screen pictures)."""
    name = f"SK_screen_{kind}_{step}"
    have = bpy.data.images.get(name)
    if have is not None:
        return have
    W, H = 640, 400 if kind == "clients" else 360
    img = np.zeros((H, W, 3), np.float32)
    if kind == "clients":
        img[:] = (0.86, 0.88, 0.9)
        img[0:44] = (0.16, 0.2, 0.27)
        _text(img, "CLIENTS (200)", 18, 9, 4, (0.95, 0.96, 0.98))
        img[44:58] = (0.74, 0.77, 0.8)
        for i in range(9):
            y = 66 + i * 36
            if i % 2 == 0:
                img[y - 4:y + 32] = (0.93, 0.94, 0.95)
            _folder(img, 20, y + 3, 34, 24, (0.92, 0.7, 0.2))
            _text(img, f"CLIENT {i + 1:03d}", 70, y + 6, 3, (0.15, 0.17, 0.2))
            img[y + 10:y + 18, 330:330 + 60 + (i * 37) % 120] = (0.55, 0.58, 0.62)
            _text(img, f"{(i * 7) % 28 + 1:02d}", 560, y + 6, 3, (0.4, 0.43, 0.47))
        img[0:44, W - 120:W - 18] = (0.85, 0.22, 0.2)
        _text(img, "200", W - 105, 9, 4, (1, 1, 1))
    else:
        img[:] = (0.04, 0.05, 0.08)
        img[0:52] = (0.08, 0.1, 0.16)
        _text(img, "AUCTION", 18, 12, 4, (0.3, 0.9, 0.5))
        _text(img, "CLIENT FILES", 230, 18, 3, (0.6, 0.65, 0.75))
        img[8:44, W - 140:W - 18] = (0.75, 0.15, 0.15)
        _text(img, "LIVE", W - 125, 14, 4, (1, 1, 1))
        for r in range(3):
            for c in range(3):
                x0, y0 = 18 + c * 206, 66 + r * 98
                img[y0:y0 + 88, x0:x0 + 194] = (0.08, 0.11, 0.18)
                _folder(img, x0 + 10, y0 + 10, 44, 32, (0.92, 0.7, 0.2))
                _text(img, f"LOT {r * 3 + c + 1}", x0 + 64, y0 + 14, 3, (0.8, 0.84, 0.9))
                price = (300 + 150 * ((r * 3 + c) * 7 % 9) + 125 * step) * 10
                img[y0 + 52:y0 + 80, x0 + 10:x0 + 120] = (0.12, 0.42, 0.22) if (r + c + step) % 3 else (0.55, 0.15, 0.12)
                _text(img, f"${price:,}", x0 + 16, y0 + 58, 2, (1, 1, 1))
                img[y0 + 52:y0 + 80, x0 + 130:x0 + 184] = (0.22, 0.42, 0.85)
                _text(img, "BID", x0 + 139, y0 + 58, 2, (1, 1, 1))
    img = img[::-1]                                     # Blender's pixel rows run bottom-up
    rgba = np.ones((H, W, 4), np.float32)
    rgba[..., :3] = img
    im = bpy.data.images.new(name, W, H, alpha=False)
    im.colorspace_settings.name = "Non-Color"
    im.pixels.foreach_set(rgba.ravel())
    try:
        im.pack()
    except Exception:
        pass
    return im


def set_screen(piece, kind: str, step: int = 0):
    """Put one of this set's pictures on a piece's screen (the monitor or the laptop)."""
    s = furnish.screen(piece)
    s.data.materials[0].node_tree.nodes["image"].image = screen_picture(kind, step)
    return s


def _place(ob, x, y, z, rot=None):
    ob.location = (x, y, z)
    if rot is not None:
        ob.rotation_euler.z = math.radians(rot)


def build_set(time: str = "office_night"):
    ops = [dict(wall="N", kind="window", type="office", w=1.1, h=1.2, sill=1.1, at=1.4, id="window"),
           dict(wall="S", kind="door", type="panel", w=0.9, h=2.05, at=-1.6, id="door", open=0)]
    R = arch.room(SIZE, at=(0.0, 1.7), floor="carpet_grey", walls="plaster_clean", ceiling="ceiling_tile", openings=ops, name="dim_room", thick=0.2,
                  skirting="brushed_metal", cornice="plaster_clean", floor_tint="#7F8790", wall_tint="#8E8A86")
    arch.vista(R, "N", "night_city", distance=10, seed=12, night=True)
    lights.rig("office_night", look=False, rim=0.0, ambient=0.03)
    lights.window_key(R.openings["window"], color="#FF9A4A", power=LIGHT["office_night"]["street"], shaft=True, shaft_strength=0.03, pitch=12, shadow=False, name="KEY_street")
    inv = dress.room(R, "dim_room", marks=MARK, density=1.0, seed=5, keep_clear=0.3, night=True)
    refs = R.refs
    desk, monitor, laptop = refs.get("desk"), refs.get("monitor"), refs.get("laptop")
    chair = next((o for o in bpy.data.objects if o.get("sk_type") == "chair_office"), None)
    # ---- clear what the recipe left on the chair seat and the desk top that the story's layout needs
    drop = []
    for o in list(bpy.data.objects):
        if o.parent is not None or "sk_type" not in o.keys():
            continue
        on_chair = chair is not None and o.get("sk_on") == chair.name
        on_desk = desk is not None and o.get("sk_on") == desk.name and o.get("sk_type") in ("energy_can",)
        if on_chair or on_desk:
            drop.append(o)
    names = {c.name for o in drop for c in [o, *o.children_recursive]}
    for nm in names:
        ob = bpy.data.objects.get(nm)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)
    tz = 0.74
    # ---- the desk, laid out for the story (desk spans x -1.4..0.3, y 2.5..3.3)
    if monitor is not None:
        _place(monitor, -0.08, 3.27, tz, 0)
        set_screen(monitor, "auction", 0)
        for c in monitor.children_recursive:                 # the kit's monitor glow (55 W) bleaches the desk top in a close insert
            if c.type == "LIGHT":
                c.data.energy = min(c.data.energy, 30.0)
    if laptop is not None:
        _place(laptop, -0.74, 3.0, tz, 10)
        set_screen(laptop, "clients")
        lt = bpy.data.lights.new("GLOW_laptop", "AREA")
        lt.size, lt.size_y, lt.energy, lt.use_shadow = 0.3, 0.2, 2.5, False
        lt.color = core.hex_rgba("#C8D8F0")[:3]
        lo = bpy.data.objects.new("GLOW_laptop", lt)
        core.link(lo, "LIGHTS")
        lo.location = (-0.76, 2.82, 0.98)
        lo.rotation_euler = Vector((0.05, -1.0, -0.35)).to_track_quat("-Z", "Y").to_euler()
    bag = furnish.make("messenger_bag", at=(-1.17, 2.74, tz), rot_z=-14, open_flap=105)
    bag.name = "prop_messenger_bag"
    bag["sk_on"] = desk.name if desk is not None else ""
    bag["sk_layer"] = "foreground"
    can = furnish.make("energy_can", at=(0.22, 2.64, tz), color="#C8433A")
    can["sk_on"] = desk.name if desk is not None else ""
    pp = furnish.make("papers_stack", at=(-0.42, 2.62, tz), rot_z=-9)
    pp["sk_on"] = desk.name if desk is not None else ""
    for o in (can, pp):
        o["sk_layer"] = "mid"
    # sticky notes on the monitor bezel, in the glow
    if monitor is not None:
        sn = arch.Parts("sticky_notes", "SET", None, kind="prop")
        for k, (dx, dz, col) in enumerate(((-0.33, 0.47, "#F2E27A"), (-0.33, 0.39, "#F2A2C0"), (0.33, 0.44, "#9FE0A8"))):
            sn.box((0.06, 0.003, 0.06), (dx, -0.088, dz), mat.solid(col, 0.8), rot=(0, (k * 7) - 6, 0), bevel=0.0)
        so = sn.build(at=(0, 0, 0), recentre=False)
        for k_ in [k for k in so.keys() if k.startswith("sk_")]:
            del so[k_]
        so.parent = monitor
        so.matrix_parent_inverse.identity()
    # cables down the back of the desk from the monitor and the laptop to the floor and the power strip
    black = mat.solid("#101214", 0.5)
    runs = [("monitor_top", [(-0.08, 3.27, tz + 0.012), (-0.06, 3.33, tz + 0.012)]),
            ("monitor_drop", [(-0.05, 3.33, tz + 0.01), (-0.05, 3.32, 0.012)]),
            ("monitor_floor", [(-0.05, 3.32, 0.012), (0.6, 3.31, 0.012), (0.9, 2.6, 0.012)]),
            ("laptop_top", [(-0.62, 3.12, tz + 0.012), (-0.64, 3.33, tz + 0.012)]),
            ("laptop_drop", [(-0.66, 3.33, tz + 0.01), (-0.66, 3.32, 0.012)]),
            ("laptop_floor", [(-0.66, 3.32, 0.012), (-1.5, 3.31, 0.012), (-1.6, 2.7, 0.012)])]
    for nm, pts in runs:
        cb = arch.Parts(f"cable_{nm}", "SET", "cable", kind="prop")
        for a_, b_ in zip(pts, pts[1:]):
            cb.rod(a_, b_, 0.006, black, seg=4)
        cbo = cb.build(at=(0, 0, 0), recentre=False)
        cbo["sk_layer"] = "mid"
        if nm.endswith("_top") and desk is not None:
            cbo["sk_on"] = desk.name
        if nm.endswith("_drop"):
            cbo["sk_mount"] = 1                                # it hangs down the back of the desk from its plug
    # a shelf over the desk with box files and books catching the screen glow
    sh = furnish.make("wall_shelf", at=(-0.15, 3.4, 1.62), length=0.9, depth=0.22)
    arch.tag_wall(sh, R.name, "N")
    sh["sk_layer"] = "background"
    t0 = furnish.tops(sh)[0]
    for k, (nm, dx, kw) in enumerate((("book_stack", -0.3, {}), ("photo_frame", 0.0, {}), ("mugs", 0.3, {}))):
        o = furnish.make(nm, at=(t0[0].x + dx, t0[0].y + 0.06, t0[1]), rot_z=(k * 9) - 8, **kw)
        o["sk_on"] = sh.name
        o["sk_layer"] = "background"
    # ---- light: the screens and lamps are the room's only sources; a weak cool fill keeps the dark deep blue, not black
    for o in bpy.data.objects:
        if o.type == "LIGHT" and o.get("sk_role") == "fill":
            o.data.energy = LIGHT["office_night"]["fill"]
    # a faint warm spill from the street side picks the brown leather of the bag out of the dark
    bl = bpy.data.lights.new("SPILL_bag", "AREA")
    bl.size, bl.energy, bl.use_shadow = 0.6, 8.0, False
    bl.color = core.hex_rgba("#FFB27A")[:3]
    blo = bpy.data.objects.new("SPILL_bag", bl)
    core.link(blo, "LIGHTS")
    blo.location = (-1.6, 2.0, 1.5)
    blo.rotation_euler = (Vector((-1.17, 2.66, 0.85)) - Vector((-1.6, 2.0, 1.5))).to_track_quat("-Z", "Y").to_euler()
    lights.rim_light(MARK["chair"], from_deg=150, elevation=24, distance=2.2, power=25.0, color="#9FB4FF", name="RIM_chair")
    lights.limit_shadows(8)
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "refs": refs, "monitor": monitor, "laptop": laptop,
            "desk": desk, "bag": bag, "chair": chair, "set_screen": set_screen, "screen_picture": screen_picture}
