"""office - the NORTHLINE open-plan floor ("Two Seconds at the Office Door": sh04 at noon, sh06 that night).

Adapted from examples/sets/set_office.py for this clip:

    marks first       the plan's nine marks: the aisle walk (aisle_start, aisle_mid, aisle_end), worker_a / worker_b, the victim's workstation
                      (victim_desk), and the front desk by the west door: front_desk (the visitor's side, on the aisle), front_desk_pass (where the
                      stranger passes and waves), front_desk_staff (behind the counter, on its south side, where the receptionist stands on the phone)
    then the place    arch.room 16 x 11 x 2.8 m: carpet, painted walls, tiled ceiling, four north windows (the city), three south windows (the street),
                      the open glass door in the west wall, which now looks down a lit corridor back toward the lifts (a real short corridor room,
                      lit by its own panels, with a LIFTS sign, a plant and notice boards); the glass meeting room in the north-east corner
    then the dressing dress.room(R, "office_open_plan"), the meeting room, the victim's workstation, and a hand-built front desk: a 2.2 m counter that
                      stands between front_desk_staff (south) and front_desk (north), its lit teal panel facing the aisle and the door
    then the light    office_day: the worked rig (window keys through the north windows under a grey sky, ceiling panels, a fill, a rim).
                      office_night - the SEARCHED state of sh06: the ceiling panels mostly off and the two left on cold; monitor glow on every
                      desk; three desk lamps; the north windows a cool city night; drawers pulled open on six drawers of five desks and a filing cabinet, papers on the
                      carpet round the victim's desk, the victim's chair shoved aside and NO laptop on the victim's desk (an empty space where it sat)

Camera side is -Y. WIDE is from the south-west corner, high, across the floor to the north-east (the plan's "nobody" / "tearing_apart" framing).
Returns the victim's desk, chair, the laptop (None at night), the front desk, the monitors and the desk lamps.
"""
import math
import random

import bpy
from mathutils import Vector

from stagekit import arch, core, dress, furnish, lights, mat

THEME = "office_open_plan"
SIZE = (16.0, 11.0, 2.8)
MEETING = (2.5, 0.5, 8.0, 5.5)             # x0, y0, x1, y1 of the glass meeting room (north-east corner)
MARK = {
    "worker_a": (-5.0, -2.55, 0.0),        # in the aisle behind the first row
    "worker_b": (-1.6, 0.25, 0.0),         # in the middle aisle
    "aisle_start": (-6.5, -2.2, 0.0),      # the west end of the aisle between the first and second rows
    "aisle_mid": (-1.9, -2.2, 0.0),        # in the aisle, in front of the victim's desk
    "aisle_end": (4.6, -2.2, 0.0),         # the east end of the aisle
    "victim_desk": (-2.9, -1.75, 0.0),     # the chair of the workstation with the unlocked laptop
    "front_desk": (-6.2, -3.3, 0.0),       # in front of the front desk counter (the aisle side)
    "front_desk_pass": (-5.2, -2.7, 0.0),  # where he passes the front desk on his way out (and waves)
    "front_desk_staff": (-6.1, -4.45, 0.0),  # behind the counter, south side: the receptionist on the phone
}
WIDE = ((-7.5, -5.2, 2.15), (2.2, 2.3, 0.15), 16.0)
LIGHT = {"office_day": {}, "office_night": dict(panels_on=((-4.0, -1.08), (-1.33, -3.83)))}   # night: the two ceiling panels left on (victim desk, aisle)
FRONT_DESK = dict(x=-6.1, y_front=-3.56, depth=0.5, length=2.2)    # the counter: front face (north) at y_front, staff side 0.5 m south


def _front_desk():
    """A short reception counter: polished stone body, pale top, a lit teal NORTHLINE panel on the aisle side (+Y), a monitor and a phone on the
    staff side (-Y). Built so front_desk (y -3.3) is in front of it and front_desk_staff (y -4.45) is behind it."""
    fd = FRONT_DESK
    L, Dp = fd["length"], fd["depth"]
    yc = fd["y_front"] - Dp / 2
    p = arch.Parts("front_desk", "SET", "reception_desk", kind="furniture")
    p.box((L, Dp, 1.02), (0.0, 0.0, 0.0), "stone_polished", bevel=0.01)
    p.box((L + 0.08, Dp + 0.12, 0.04), (0.0, 0.0, 1.02), mat.solid("#BDB8AE", 0.3), bevel=0.006)
    p.box((1.5, 0.02, 0.5), (-0.2, Dp / 2 + 0.01, 0.32), p.glow("#0E6B78", 1.1), bevel=0.0)
    p.box((L - 0.2, 0.02, 0.12), (0.0, Dp / 2 + 0.01, 0.04), "brushed_metal", bevel=0.003)
    p.box((L - 0.3, 0.24, 0.03), (0.0, -Dp / 2 - 0.12, 0.86), mat.solid("#B98B58", 0.45), bevel=0.004)      # a ledge on the staff side
    for sx in (-1, 1):
        p.box((0.04, 0.22, 0.86), (sx * (L / 2 - 0.25), -Dp / 2 - 0.12, 0.0), "brushed_metal", bevel=0.003)
    p.light("panel_glow", (-0.2, Dp / 2 + 0.25, 0.55), "#5FC6CF", 18.0, 0.2, False, "AREA", aim=(0, 3.0, -0.3), size=1.2)
    ob = p.build(at=(fd["x"], yc, 0.0), recentre=False)
    # the NORTHLINE lettering on the panel
    cu = bpy.data.curves.new("front_desk_sign", "FONT")
    cu.body = "NORTHLINE"
    cu.size = 0.12
    cu.align_x = "CENTER"
    cu.extrude = 0.003
    cu.materials.append(mat.emit("#F4FAFB", 2.0, "SK_emit_frontdesk_sign"))
    tx = bpy.data.objects.new("front_desk_sign", cu)
    core.link(tx, "SET")
    tx.parent = ob
    tx.location = (-0.2, Dp / 2 + 0.03, 0.52)
    tx.rotation_euler = (math.radians(90), 0, math.radians(180))
    tx["sk_kind"] = "detail"
    ob["sk_layer"] = "mid"
    top_z = 1.06
    mon = furnish.make("monitor_keyboard", at=(fd["x"] + 0.35, yc + 0.05, top_z), rot_z=0)
    ph = furnish.make("office_phone", at=(fd["x"] - 0.55, yc - 0.02, top_z), rot_z=10)
    pp = furnish.make("papers_stack", at=(fd["x"] - 0.05, yc - 0.06, top_z), rot_z=-4)
    for o in (mon, ph, pp):
        o["sk_on"] = ob.name
        o["sk_layer"] = "mid"
    return ob


def _corridor(night: bool):
    """The corridor outside the west door, running north toward the lifts: lit panels, a LIFTS sign and arrow at the far end, a plant, a notice
    board, an extinguisher. Its east wall has the doorway that lines up with the office's west door."""
    R2 = arch.room((2.6, 9.0, 2.7), at=(-9.55, -1.4), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile",
                   openings=[dict(wall="E", kind="gap", w=1.3, h=2.3, at=-0.5, id="to_office")],
                   name="corridor", thick=0.25, skirting="brushed_metal", cornice="plaster_clean", floor_tint="#9BA3AA")
    D2 = dress.Dresser(None, "office_private", {}, 0.5, 17, 0.3, None, R2)
    for yy in (-4.6, -1.9, 0.8, 2.8):
        D2.ceiling_piece("ceiling_light_panel", -9.55, yy, "beyond", size=(1.2, 0.6), power=35.0 if night else 45.0)
    D2.floor("potted_plant", -10.45, -3.2, 0, "beyond", margin=0.0, marks=False, height=1.4, seed=6)
    D2.hang("notice_board", "W", -1.0, z=1.3, layer="beyond", width=0.9, height=0.65, seed=8)
    D2.hang("poster", "W", 0.9, z=1.4, layer="beyond", color="#0E6B78", seed=5, width=0.6, height=0.85)
    D2.hang("fire_extinguisher", "W", -2.4, z=0.35, layer="beyond")
    D2.hang("exit_sign", "N", 0.0, z=2.35, layer="beyond")
    D2.hang("wall_clock", "W", 2.2, z=2.0, layer="beyond", radius=0.16)
    # the far end: the lift lobby sign
    cu = bpy.data.curves.new("lifts_sign", "FONT")
    cu.body = "LIFTS  >"
    cu.size = 0.2
    cu.align_x = "CENTER"
    cu.extrude = 0.004
    cu.materials.append(mat.solid("#20242A", 0.4))
    tx = bpy.data.objects.new("lifts_sign", cu)
    core.link(tx, "SET")
    tx.location = (-9.55, 3.08, 1.9)
    tx.rotation_euler = (math.radians(90), 0, 0)
    arch.tag(tx, "sign", kind="prop", size=[0.9, 0.01, 0.2])
    tx["sk_layer"] = "beyond"
    tx["sk_mount"] = 1
    arch.tag_wall(tx, R2.name, "N")
    lights.ambient_fill((-9.55, -1.4, 2.5), (2.2, 8.0), power=26 if not night else 18, color="#F4F6FF", name="FILL_corridor")
    return R2


def _open_drawer(desk, k: int, pull: float, rnd: random.Random):
    """Pull out drawer k (0 = bottom) of a desk_office pedestal by `pull` m: a tray with a front, sides, bottom and a few papers inside. It is parented
    to the desk (it is part of the desk, held by it), so the audit treats it as one piece."""
    length, depth = float(desk["sk_size"][0]), float(desk["sk_size"][1])
    face = desk.location.y - depth - 0.001                  # desks stand at rot_z 0: origin at the back centre, the drawer fronts face -Y
    px = desk.location.x - length / 2 + 0.3
    z = (0.1, 0.28, 0.46)[k]
    w, h = 0.36, 0.13
    p = arch.Parts(f"drawer_{desk.name}_{k}", "SET", None, kind="prop")
    grey = mat.solid("#D8DADC", 0.4)
    inner = mat.solid("#A9ADB1", 0.5)
    p.box((0.38, 0.015, 0.15), (px, face - pull - 0.0075, z), grey, bevel=0.003)                   # the drawer front, pulled out
    p.box((0.12, 0.02, 0.012), (px, face - pull - 0.025, z + 0.11), mat.solid("#4A4D52", 0.4, 0.9), bevel=0.002)
    p.box((w, pull, 0.01), (px, face - pull / 2, z + 0.005), inner, bevel=0.0)                    # bottom
    for sx in (-1, 1):
        p.box((0.01, pull, h - 0.01), (px + sx * (w / 2 - 0.005), face - pull / 2, z + 0.01), inner, bevel=0.0)
    for j in range(3):                                                                            # papers in it, rifled
        p.box((0.21, 0.27, 0.002), (px + rnd.uniform(-0.05, 0.05), face - pull / 2 + rnd.uniform(-0.03, 0.03), z + 0.012 + 0.003 * j),
              mat.solid(rnd.choice(["#ECE8DC", "#DCD6C6", "#F2EFE6"]), 0.9), rot=(0, 0, rnd.uniform(-25, 25)), bevel=0.0)
    ob = p.build(at=(0, 0, 0), recentre=False)
    ob.parent = desk                                        # world coordinates were authored: undo the desk's own transform (matrix_basis is
    ob.matrix_parent_inverse = desk.matrix_basis.inverted()  # current even before the depsgraph has evaluated the new desk)
    for k_ in [k for k in ob.keys() if k.startswith("sk_")]:
        del ob[k_]
    return ob


def _open_cabinet_drawer(cab, k: int, pull: float):
    """Pull out drawer k of a filing cabinet (front faces the cabinet's local -Y), parented to the cabinet."""
    drawers = 3 if cab.get("sk_size", [0, 0, 1.34])[2] < 1.2 else 4
    H = 0.31 * drawers + 0.08
    hz = 0.06 + k * (H - 0.1) / drawers
    dh = (H - 0.1) / drawers - 0.02
    p = arch.Parts(f"drawer_{cab.name}_{k}", "SET", None, kind="prop")
    m = mat.solid("#A9B0B6", 0.4, 0.5)
    inner = mat.solid("#7E858C", 0.5, 0.3)
    # local frame of the cabinet: origin at the back-centre, front at y = -0.6
    fy = -0.6 - 0.006
    p.box((0.43, 0.015, dh), (0.0, fy - pull - 0.0075, hz), m, bevel=0.003)
    p.box((0.2, 0.025, 0.02), (0.0, fy - pull - 0.027, hz + dh * 0.7), mat.solid("#4A4D52", 0.4, 0.9), bevel=0.004)
    p.box((0.4, pull, 0.01), (0.0, fy - pull / 2, hz + 0.01), inner, bevel=0.0)
    for sx in (-1, 1):
        p.box((0.01, pull, dh - 0.05), (sx * 0.195, fy - pull / 2, hz + 0.02), inner, bevel=0.0)
    for j in range(5):                                                                            # hanging files
        p.box((0.36, 0.008, dh - 0.06), (0.0, fy - pull + 0.06 + j * (pull - 0.1) / 5, hz + 0.02), mat.solid(["#D9A21B", "#6E8FA8", "#C9B48A"][j % 3], 0.8), bevel=0.0)
    ob = p.build(at=(0, 0, 0), recentre=False)
    for k_ in [k for k in ob.keys() if k.startswith("sk_")]:
        del ob[k_]
    ob.parent = cab
    ob.matrix_parent_inverse.identity()
    ob.location = (0, 0, 0)
    return ob


def _papers_on_carpet(rnd: random.Random, region, n: int, avoid):
    """Loose sheets and a few folders on the carpet: one merged floor-detail mesh, kept off the marks."""
    p = arch.Parts("searched_papers", "SET", "floor_detail", kind="prop")
    mats = [mat.solid(c, 0.9) for c in ("#ECE8DC", "#DCD6C6", "#F2EFE6", "#E6E0CE")]
    fm = [mat.solid(c, 0.8) for c in ("#D9A21B", "#6E8FA8", "#C9B48A")]
    placed = 0
    for _ in range(n * 6):
        if placed >= n:
            break
        x, y = rnd.uniform(region[0], region[2]), rnd.uniform(region[1], region[3])
        if any(math.hypot(x - ax, y - ay) < r for ax, ay, r in avoid):
            continue
        folder = rnd.random() < 0.18
        p.box((0.24, 0.31, 0.004) if folder else (0.21, 0.297, 0.002), (x, y, 0.0005 * (placed % 4)), rnd.choice(fm if folder else mats),
              rot=(0, 0, rnd.uniform(0, 360)), bevel=0.0)
        placed += 1
    ob = p.build(at=(0, 0, 0), recentre=False)
    ob["sk_layer"] = "mid"
    return ob


def _night_lights(night_cfg):
    """Ceiling panels off except the two named (left on, cold and dimmer); monitor glow on every desk monitor."""
    on = night_cfg["panels_on"]
    dark = mat.solid("#5A5E66", 0.5, name="SK_panel_off")
    cold = mat.emit("#DCE6FF", 3.2, "SK_panel_cold")
    for ob in list(bpy.data.objects):
        if ob.get("sk_type") != "ceiling_light_panel" or ob.location.x < -8.0:          # the corridor's panels stay as they are
            continue
        keep = any(abs(ob.location.x - x) < 0.3 and abs(ob.location.y - y) < 0.3 for x, y in on)
        for c in [ob, *ob.children_recursive]:
            if c.type == "LIGHT":
                c.data.energy = c.data.energy * 0.7 if keep else 0.0
                c.data.color = core.hex_rgba("#DCE6FF")[:3]
            elif c.type == "MESH":
                for i, sl in enumerate(c.material_slots):
                    if sl.material is not None and sl.material.name.startswith("SK_emit_"):
                        c.material_slots[i].material = cold if keep else dark
    # the ceiling grid's own emissive panels (arch.room's "ceiling_panel" pieces) go dark too, except where a lit fitting stays on
    for ob in list(bpy.data.objects):
        if ob.get("sk_type") != "ceiling_panel":
            continue
        for c in [ob, *ob.children_recursive]:
            if c.type != "MESH":
                continue
            w = c.matrix_world.translation
            keep = any(abs(w.x - x) < 0.9 and abs(w.y - y) < 0.9 for x, y in on)
            for i, sl in enumerate(c.material_slots):
                if sl.material is not None and sl.material.name.startswith("SK_emit_"):
                    c.material_slots[i].material = cold if keep else dark
    glows = []
    for ob in list(bpy.data.objects):
        if ob.get("sk_type") == "monitor_keyboard":
            ld = bpy.data.lights.new(f"GLOW_{ob.name}", "AREA")
            ld.size, ld.size_y = 0.5, 0.3
            ld.shape = "RECTANGLE"
            ld.energy = 6.0
            ld.color = core.hex_rgba("#8FB6FF")[:3]
            ld.use_shadow = False
            lo = bpy.data.objects.new(f"GLOW_{ob.name}", ld)
            core.link(lo, "LIGHTS")
            fwd = ob.matrix_world.to_3x3() @ Vector((0, -1, 0))
            lo.location = ob.matrix_world.translation + Vector((0, 0, 0.3)) + fwd * 0.25
            lo.rotation_euler = (fwd + Vector((0, 0, -0.25))).to_track_quat("-Z", "Y").to_euler()
            glows.append(lo)
    return glows


def build_set(time: str = "office_day"):
    night = time == "office_night"
    rnd = random.Random(23)
    ops = []
    for x in (-5.6, -1.9, 1.9, 5.6):
        ops.append(dict(wall="N", kind="window", type="office", w=3.0, h=1.6, sill=0.9, at=x, id=f"win_N{x:+.0f}"))
    for x in (-5.0, 0.0, 5.0):
        ops.append(dict(wall="S", kind="window", type="shop", w=3.2, h=1.7, sill=0.8, at=x, id=f"win_S{x:+.0f}"))
    ops.append(dict(wall="W", kind="door", type="glass", w=1.1, h=2.2, at=-1.9, id="entrance", open=35))
    R = arch.room(SIZE, at=(0, 0), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile", openings=ops, name="office", thick=0.25,
                  skirting="brushed_metal", cornice="plaster_clean")
    arch.vista(R, "N", "night_city" if night else "city_day", distance=18, seed=4, night=night)
    arch.vista(R, "S", "street", distance=10, seed=6, night=night)
    _corridor(night)                                                       # the west door looks down a lit corridor toward the lifts
    # the glass meeting room
    x0, y0, x1, y1 = MEETING
    arch.glass_partition(x1 - x0 - 0.08, 2.7, at=((x0 + x1) / 2 + 0.04, y0, 0), rot_z=0, door=(-1.4, 1.0), opaque_band=0.5, name="meet_front", open_deg=45)
    arch.glass_partition(y1 - y0, 2.7, at=(x0, (y0 + y1) / 2, 0), rot_z=-90, opaque_band=0.5, name="meet_side")
    # ---- light
    mood = "office_night" if night else "office_day"
    lights.rig(mood, look=False, rim=0.0, ambient=0.05 if night else 0.15)
    for oid, hd in R.openings.items():
        if hd["kind"] != "window":
            continue
        if hd["wall"] == "N":
            lights.window_key(hd, color="#8FA4E8" if night else "#E4EDFA", power=140 if night else 380, shaft=not night, shaft_strength=0.04, pitch=18, name=f"KEY_{oid}")
        else:
            lights.window_key(hd, color="#9FB0D8" if night else "#F4EFE6", power=60 if night else 200, shaft=False, pitch=12, shadow=False, name=f"KEY_{oid}")
    lights.ambient_fill((0, 0, 2.5), (14, 9), power=42 if night else 15, color="#C8D6FF" if night else "#EAF0FF")
    lights.rim_light(MARK["worker_b"], from_deg=170, distance=4.0, power=260 if not night else 200, color="#CFE0FF")
    lights.rim_light(MARK["aisle_mid"], from_deg=200, elevation=30, distance=4.0, power=150 if not night else 170, color="#CFE0FF", name="RIM_aisle")
    # ---- the dressing; the recipe leaves alone the meeting room, the victim's workstation and the front desk corner (built by hand below)
    inv = dress.room(R, "office_open_plan", marks=MARK, density=1.0, seed=7, keep_clear=0.5,
                     reserve=[(x0 - 0.15, y0 - 0.15, x1, y1), (-3.9, -2.3, -1.9, -0.25), (-7.9, -5.3, -4.3, -3.0)])
    mt = furnish.meeting_table(at=(5.3, 3.55, 0.0), rot_z=0)
    mt["sk_layer"] = "mid"
    for k, sx in enumerate((-0.8, 0.0, 0.8)):
        for side in (-1, 1):
            c = furnish.chair_office(at=(5.3 + sx, 3.0 + side * 1.27, 0.0), rot_z=0 if side > 0 else 180, color="#3A4A5A")
            c["sk_layer"] = "mid"
    tl = furnish.tops(mt)[0]
    for k, nm in enumerate(("laptop", "papers_stack", "mugs", "book_stack", "office_phone", "laptop")):
        o = furnish.make(nm, at=(tl[0].x - 1.0 + 0.4 * k, tl[0].y + (0.28 if k % 2 else -0.28), tl[1]), rot_z=0 if k % 2 else 180)
        o["sk_on"] = mt.name
        o["sk_layer"] = "mid"
    wb = furnish.whiteboard(at=(x1, 3.0, 0.9), rot_z=-90, width=2.4, height=1.15, seed=5)
    arch.tag_wall(wb, R.name, "E")
    wb["sk_layer"] = "background"
    pl = furnish.potted_plant(at=(7.3, 4.8, 0.0), height=1.6, seed=9)
    pl["sk_layer"] = "background"
    tv = furnish.tv(at=(5.3, 5.45, 0.0), rot_z=0, diag=1.3, stand=True)
    tv["sk_layer"] = "background"
    for i in range(2):
        pn = furnish.ceiling_light_panel(at=(4.2 + i * 2.4, 3.6, 2.8), size=(1.2, 0.6), power=45.0)
        arch.tag_wall(pn, R.name, "C")
    # ---- the victim's workstation: desk, chair, monitor, mug, papers and (by day) the OPEN, UNLOCKED laptop
    dk = furnish.desk_office(at=(-2.9, -0.41, 0.0), rot_z=0, length=1.6, depth=0.78)
    dk["sk_layer"] = "mid"
    ch = furnish.chair_office(at=(-2.9, -2.04, 0.0), rot_z=188, color="#3A4A5A")
    ch["sk_layer"] = "mid"
    tl = furnish.tops(dk)[1]
    mon = furnish.make("monitor_keyboard", at=(tl[0].x + 0.35, tl[0].y + 0.1, tl[1]), rot_z=0)
    mug = furnish.make("mugs", at=(tl[0].x + 0.72, tl[0].y + 0.05, tl[1]), rot_z=20)
    papers = furnish.make("papers_stack", at=(tl[0].x - 0.05, tl[0].y + 0.32, tl[1]), rot_z=-6)
    laptop = None
    if not night:
        laptop = furnish.laptop_open(at=(tl[0].x - 0.42, tl[0].y + 0.2, tl[1]), rot_z=-12, image="desktop")
    else:
        # where the laptop sat: a bare patch of desk with its charger cable lying loose
        cb = arch.Parts("charger_cable", "SET", "cable", kind="prop")
        pts = [(tl[0].x - 0.62, tl[0].y + 0.32), (tl[0].x - 0.5, tl[0].y + 0.15), (tl[0].x - 0.36, tl[0].y + 0.08), (tl[0].x - 0.3, tl[0].y - 0.05)]
        for a, b in zip(pts, pts[1:]):
            cb.rod((a[0], a[1], tl[1] + 0.005), (b[0], b[1], tl[1] + 0.005), 0.004, mat.solid("#16181B", 0.5), seg=4)
        cb.box((0.06, 0.03, 0.02), (pts[-1][0], pts[-1][1], tl[1]), mat.solid("#22252A", 0.5), bevel=0.003)
        cbo = cb.build(at=(0, 0, 0), recentre=False)
        cbo["sk_on"] = dk.name
        cbo["sk_layer"] = "mid"
    for o in (mon, laptop, mug, papers):
        if o is not None:
            o["sk_on"] = dk.name
            o["sk_layer"] = "mid"
    # ---- the front desk by the west door
    fd = _front_desk()
    lamps = []
    if night:
        # ---- the searched state: drawers out, papers on the carpet, the victim's chair shoved back, three desk lamps left on
        ch.location = (-2.35, -2.1, 0.0)
        ch.rotation_euler.z = math.radians(150)
        def desk_at(x, y):
            return next((o for o in bpy.data.objects if o.get("sk_type") == "desk_office" and abs(o.location.x - x) < 0.2 and abs(o.location.y - y) < 0.2), None)
        _open_drawer(dk, 2, 0.30, rnd)
        _open_drawer(dk, 1, 0.24, rnd)
        for (x, y), k, pull in (((-1.0, -3.21), 2, 0.28), ((0.9, -3.21), 1, 0.3), ((-4.8, -0.41), 2, 0.26), ((-1.0, -0.41), 0, 0.3),
                                ((2.8, -3.21), 1, 0.25)):
            d = desk_at(x, y)
            if d is not None:
                _open_drawer(d, k, pull, rnd)
        for ob in list(bpy.data.objects):
            if ob.get("sk_type") == "filing_cabinet" and ob.location.x < -7.0 and ob.location.y < 4.5:
                _open_cabinet_drawer(ob, 2, 0.4)
                _open_cabinet_drawer(ob, 0, 0.32)
        avoid = [(m[0], m[1], 0.42) for m in MARK.values()] + [(-2.35, -2.1, 0.45)]
        _papers_on_carpet(rnd, (-4.6, -3.0, -0.6, -1.3), 26, avoid)
        _papers_on_carpet(random.Random(5), (-1.6, -4.1, 3.5, -3.2), 9, avoid)
        for x, y in ((-4.8, -0.41), (0.9, -3.21), (-1.0, 2.39)):
            d = desk_at(x, y)
            if d is None:
                continue
            t0 = furnish.tops(d)[1]
            lp = furnish.make("desk_lamp", at=(t0[0].x + 0.62, t0[0].y + 0.18, t0[1]), rot_z=200, power=22.0)
            lp["sk_on"] = d.name
            lp["sk_layer"] = "mid"
            lamps.append(lp)
        _night_lights(LIGHT["office_night"])
        lights.dust((-7.5, -5.0, 0.3), (7.5, 5.0, 2.6), count=220, color="#C8D4FF", strength=0.5)
    lights.limit_shadows(10)
    monitors = [o for o in bpy.data.objects if o.get("sk_type") == "monitor_keyboard"]
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "victim_desk": dk, "victim_chair": ch, "laptop": laptop,
            "front_desk": fd, "monitors": monitors, "desk_lamps": lamps, "victim_monitor": mon}
