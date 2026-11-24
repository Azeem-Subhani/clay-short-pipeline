"""fig3d - builds one 3D character from a sheet: a round body sized from its proportions, a drawn face that follows the
head, and clothes, hair and hats made from FLAT FRONT DRAWINGS that are wrapped onto the body, spun into hats or grown
into a hair cap. The same step serves the converted pack characters, the wardrobe and new characters.

    fig = fig3d.Fig(sheet, "queen")       # sheet: one entry of config/cast3d.json
    fig.J["head"], fig.ctrl, fig.parts     # joints (empties), the face / hand control, the built objects by part name

Space: metres, the figure stands at the origin facing -Y, +X is its left hand, Z up.
"""
from __future__ import annotations

import copy
import fnmatch
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

INK = 0.0075                 # ink line: thickness of the outline hull, metres
INK_ON = False               # the approved look has no outline; True draws the hull again
S_EYE = 1.22                 # eye size against the 2D design
SQUAT_MAX = 0.30             # how far the hips can sink while a gown's hem stays on the ground
EXPRS = ("happy", "worried", "angry", "sad", "surprised", "laugh", "grin", "sly")
VISEMES = ("A", "E", "I", "O", "U", "MBP")
HAND_SHAPES = ("mitten", "open", "pinch", "fist", "point", "grip")


# ------------------------------------------------------------------------------------------------ colour and materials
def lin(h, a=1.0):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(((v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c) + (a,)


def shade(h, k):
    h = h.lstrip("#")
    return "#" + "".join(f"{max(0, min(255, int(int(h[i:i + 2], 16) * k))):02X}" for i in (0, 2, 4))


def _lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.3 * r + 0.59 * g + 0.11 * b, max(r, g, b) - min(r, g, b)


def _new(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    return m, nt, nt.nodes["Principled BSDF"]


def _set(bsdf, **kw):
    for k, v in kw.items():
        key = k.replace("_", " ")
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = v


def seat_face(el, az, rp, anc, face, ear=None):
    """Generated beards and moustaches: fit a library piece to one character's face. el, az: numpy arrays, the points'
    elevation and turn from the front in degrees; rp: their distance from the head centre in head radii (1 = skin).
    anc: where the piece's own features are, measured when it was baked (degrees above the head centre): top / bottom of
    the moustache down the middle of the face, beard = upper edge of the beard under the mouth, side = how high it climbs
    in front of the ears. face: the sheet's face (nz nose, mz mouth). Returns the new (el, az, rp):
    the moustache is squeezed between the nose and the mouth (and thinned to match), the beard starts under the mouth,
    the sides stop below the hair line, and the beard gets flatter across the cheek and ends at the ear.
    ear: where the character's ear is, {"el", "az", "h_el", "h_az"} in degrees (centre, half height, half width, margin
    included). Given, a beard leaves the ear free the way a real beard line does: the sideburn passes in front of the
    ear, the jaw line under the lobe, and nothing is left behind or above it. The beard round that space is slid out of
    it (its edge then lies on a smooth curve and thins onto the skin) and the faces of the points that were deep inside
    it are dropped; the call then returns (el, az, rp, gone), gone = the points whose faces are to be dropped."""
    import numpy as np
    sm = lambda x: (lambda v: v * v * (3 - 2 * v))(np.clip(x, 0, 1))
    dg = lambda z: math.degrees(math.asin(max(-0.99, min(0.99, z))))
    T0, B0, C0, S0 = anc.get("top"), anc.get("bottom"), anc.get("beard"), anc.get("side")
    n1, u1, l1 = dg(face.get("nz", -0.15) - 0.045), dg(face.get("mz", -0.385) + 0.04), dg(face.get("mz", -0.385) - 0.12)
    u1 = min(u1, n1 - 6.0)                                    # a nose close to the mouth: the moustache covers the upper lip
    el0 = el
    WIDE, THICK = 36.0, 0.15                                  # a moustache: half width in degrees round the head, and how far it stands off the face (head radii)
    if T0 is not None:
        sv = min(1.0, (n1 - u1) / max(T0 - B0, 1.0))
        k = float(np.clip(math.sqrt(sv), 0.6, 1.0))           # width and thickness shrink less than the height
        fm = n1 + (el - T0) * sv
    if T0 is not None and C0 is None:                         # a moustache alone: one squeeze for the whole piece
        el, az, rp = fm, az * k, 1.0 + (rp - 1.0) * k
        aw = float(np.percentile(np.abs(az), 99.5))           # no wider than the face allows: the tips stay inside the cheeks
        if aw > WIDE:
            az, rp = az * (WIDE / aw), 1.0 + (rp - 1.0) * max(0.7, WIDE / aw)
        lo, lim = float(np.percentile(el, 0.5)), dg(face.get("mz", -0.385) - 0.17)
        if lo < lim:                                          # drooping ends stop beside the mouth, not at the chin
            el = np.where(el < u1, u1 + (el - u1) * (u1 - lim) / (u1 - lo), el)
        rp = 1.0 + THICK * np.tanh((rp - 1.0) / THICK)        # and it does not stand further off the face than this
    elif C0 is not None:
        w = sm((80.0 - np.abs(az)) / 50.0)                    # 1 on the front of the face, 0 at the ears
        fb = -90.0 + (el + 90.0) * (l1 + 90.0) / (C0 + 90.0)
        if T0 is None:
            front = np.where(el <= C0, fb, el + (l1 - C0))
        else:
            gap = l1 + (el - C0) / max(B0 - C0, 1.0) * (n1 + (B0 - T0) * sv - l1)
            front = np.where(el <= C0, fb, np.where(el >= B0, fm, gap))
            wz = w * sm((el - C0) / max(B0 - C0, 1.0))        # 1 on the moustache of a beard
            rp = 1.0 + (rp - 1.0) * (1.0 + (k - 1.0) * wz)
            rp = 1.0 + (rp - 1.0) * (1.0 - wz) + THICK * np.tanh((rp - 1.0) / THICK) * wz
        s1 = 6.0                                              # the sides end just under the ear, like the sculpted beards
        side = -90.0 + (el + 90.0) * (s1 + 90.0) / (S0 + 90.0) if (S0 is not None and S0 > s1) else el
        el = w * front + (1.0 - w) * side
    if C0 is not None:                                        # a beard gets flatter across the cheek and ends at the ear
        aa = np.abs(az)
        f = 1.0 - 0.65 * sm((aa - 55.0) / 45.0)              # flat sideburns; it stays on the skin, so its own edge is the edge
        rp = np.where(el0 > -60.0, 1.0 + (rp - 1.0) * f, rp)
    if ear is None:
        return el, az, rp
    gone = np.zeros(len(el), dtype=bool)
    if C0 is not None and S0 is not None:                     # a beard that reaches the sides: room for the ear
        e0, a0, he, ha = ear["el"], ear["az"], ear["h_el"], ear["h_az"]
        x = np.maximum(0.0, (a0 - np.abs(az)) / ha)           # how far in front of the ear centre, in ear half widths
        drop = 0.8 * np.maximum(0.0, np.abs(az) - a0)         # behind the ear the edge runs down toward the nape
        y = np.maximum(0.0, (e0 - drop - el) / he)            # how far below it, in ear half heights
        d = np.hypot(x, y)                                    # < 1: the ear's space (open above and behind the ear)
        DC, DO = 0.6, 2.0                                     # points nearer than DC go; DC .. DO is slid out to 1 .. DO
        L = DO - DC
        t = np.clip((d - DC) / L, 0.0, 1.0)
        h = 3 * t * t - 2 * t ** 3 + (L / (DO - 1.0)) * (t ** 3 - t * t)   # flat at the cut (a ragged cut lands on d = 1), smooth into DO
        d2 = np.where(d < DO, 1.0 + (DO - 1.0) * h, d)
        s = d2 / np.maximum(d, 1e-6)
        az = np.where(x > 0, np.sign(az) * (a0 - x * s * ha), az)
        el = np.where(y > 0, e0 - drop - y * s * he, el)
        rp = 1.0 + (rp - 1.0) * (0.06 + 0.94 * sm((d2 - 1.0) / 0.6))    # and thins onto the skin toward that edge
        gone = d < DC
    return el, az, rp, gone


def hair_look(m, R):
    """The approved look of generated hair, on top of the "hair" material: root-to-tip shading (the mesh's gen_grad),
    darker grooves, a soft shine and a little light through the lock tips."""
    nt = m.node_tree
    bs = nt.nodes["Principled BSDF"]

    def shade_by(fac, lo, hi):                                # base colour x (lo .. hi), driven by fac 0 .. 1
        src = bs.inputs["Base Color"].links[0].from_socket
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = lo, hi
        nt.links.new(fac, mr.inputs["Value"])
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type, mx.blend_type, mx.clamp_result = "RGBA", "MULTIPLY", False
        mx.inputs[0].default_value = 1.0
        nt.links.new(src, mx.inputs[6])
        nt.links.new(mr.outputs[0], mx.inputs[7])
        nt.links.new(mx.outputs[2], bs.inputs["Base Color"])

    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "gen_grad"
    shade_by(at.outputs["Fac"], 0.62, 1.25)
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = R * 0.16
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 1.6
    nt.links.new(ao.outputs["AO"], pw.inputs[0])
    shade_by(pw.outputs[0], 0.35, 1.0)
    _set(bs, Roughness=0.38, Sheen_Weight=0.25, Coat_Weight=0.30, Coat_Roughness=0.22, Subsurface_Weight=0.5, Subsurface_Scale=0.03)
    if "Subsurface Radius" in bs.inputs:
        bs.inputs["Subsurface Radius"].default_value = (1.0, 0.5, 0.25)
    return m


def _bump(nt, bsdf, height, strength, distance=0.004):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(height, b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])


def _mixc(nt, a, b, fac):
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    for sock, v in ((mx.inputs[6], a), (mx.inputs[7], b)):
        if isinstance(v, tuple):
            sock.default_value = v
        else:
            nt.links.new(v, sock)
    if isinstance(fac, float):
        mx.inputs[0].default_value = fac
    else:
        nt.links.new(fac, mx.inputs[0])
    return mx.outputs[2]


def _zgrad(nt, co, z0, z1):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(co, sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = z0
    mr.inputs["From Max"].default_value = z1
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    return mr.outputs["Result"]


def material(kind: str, color: str, name: str, height: float = 1.7):
    """One of the figure's surfaces. kind: cloth | skin | hair | fur | metal | leather | plain | gem | eye | glow."""
    m, nt, b = _new(name)
    co = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    c = lin(color)
    if kind == "cloth":
        g = _zgrad(nt, co, 0.05, height * 0.62)
        base = _mixc(nt, lin(shade(color, 0.72)), c, g)
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 9.0
        n.inputs["Detail"].default_value = 3.0
        nt.links.new(co, n.inputs["Vector"])
        sc = nt.nodes.new("ShaderNodeMath")
        sc.operation = "MULTIPLY"
        sc.inputs[1].default_value = 0.10
        nt.links.new(n.outputs["Fac"], sc.inputs[0])
        nt.links.new(_mixc(nt, base, lin(shade(color, 0.72)), sc.outputs[0]), b.inputs["Base Color"])
        w1, w2 = nt.nodes.new("ShaderNodeTexWave"), nt.nodes.new("ShaderNodeTexWave")
        w1.bands_direction, w2.bands_direction = "X", "Z"
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        for w, i in ((w1, 0), (w2, 1)):
            w.inputs["Scale"].default_value = 1300.0
            nt.links.new(co, w.inputs["Vector"])
            nt.links.new(w.outputs["Fac"], mul.inputs[i])
        _bump(nt, b, mul.outputs[0], 0.35, 0.0015)
        _set(b, Roughness=0.86, Sheen_Weight=1.0, Sheen_Roughness=0.35)
        if "Sheen Tint" in b.inputs:
            b.inputs["Sheen Tint"].default_value = c
    elif kind == "skin":
        g = _zgrad(nt, co, height * 0.55, height * 0.85)
        nt.links.new(_mixc(nt, lin(shade(color, 0.90)), c, g), b.inputs["Base Color"])
        _set(b, Roughness=0.55, Subsurface_Weight=0.25, Subsurface_Scale=0.02, Sheen_Weight=0.15)
        if "Subsurface Radius" in b.inputs:
            b.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.3)
    elif kind == "hair":
        g = _zgrad(nt, co, height * 0.60, height * 0.95)
        nt.links.new(_mixc(nt, lin(shade(color, 0.86)), c, g), b.inputs["Base Color"])
        _set(b, Roughness=0.48, Sheen_Weight=0.35, Coat_Weight=0.12, Subsurface_Weight=0.08)
    elif kind == "fur":
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 420.0
        n.inputs["Detail"].default_value = 6.0
        nt.links.new(co, n.inputs["Vector"])
        nt.links.new(_mixc(nt, lin(shade(color, 0.88)), c, n.outputs["Fac"]), b.inputs["Base Color"])
        _bump(nt, b, n.outputs["Fac"], 0.9, 0.004)
        _set(b, Roughness=0.95, Sheen_Weight=1.0, Sheen_Roughness=0.6)
    elif kind == "metal":
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 260.0
        nt.links.new(co, n.inputs["Vector"])
        _bump(nt, b, n.outputs["Fac"], 0.08, 0.001)
        _set(b, Base_Color=c, Roughness=0.22, Metallic=0.9, Coat_Weight=0.5, Emission_Color=c, Emission_Strength=0.2)
    elif kind == "leather":
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 180.0
        n.inputs["Detail"].default_value = 4.0
        nt.links.new(co, n.inputs["Vector"])
        _bump(nt, b, n.outputs["Fac"], 0.25, 0.002)
        _set(b, Base_Color=c, Roughness=0.42, Coat_Weight=0.25)
    elif kind == "gem":
        _set(b, Base_Color=c, Roughness=0.08, Coat_Weight=1.0, Emission_Color=c, Emission_Strength=0.25)
    elif kind == "eye":
        _set(b, Base_Color=c, Roughness=0.25)
    elif kind == "glow":
        _set(b, Base_Color=c, Roughness=0.3, Emission_Color=c, Emission_Strength=0.6)
    else:
        _set(b, Base_Color=c, Roughness=0.6)
    return m


def m_teeth(name, count=11.0):
    m, nt, b = _new(name)
    uv = nt.nodes.new("ShaderNodeTexCoord").outputs["UV"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv, sep.inputs[0])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = count
    nt.links.new(sep.outputs["X"], mul.inputs[0])
    fr = nt.nodes.new("ShaderNodeMath")
    fr.operation = "FRACT"
    nt.links.new(mul.outputs[0], fr.inputs[0])
    lt = nt.nodes.new("ShaderNodeMath")
    lt.operation = "LESS_THAN"
    lt.inputs[1].default_value = 0.085
    nt.links.new(fr.outputs[0], lt.inputs[0])
    nt.links.new(_mixc(nt, lin("#FFFBEF"), lin("#4A2A22"), lt.outputs[0]), b.inputs["Base Color"])
    _set(b, Roughness=0.18, Coat_Weight=0.6, Emission_Color=lin("#FFFBEF"), Emission_Strength=0.12)
    return m


def m_blush(name, color="#F08A7A"):
    m, nt, b = _new(name)
    uv = nt.nodes.new("ShaderNodeTexCoord").outputs["UV"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv, sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Max"].default_value = 0.5
    nt.links.new(sep.outputs["Y"], mr.inputs["Value"])
    nt.links.new(mr.outputs[0], b.inputs["Alpha"])
    _set(b, Base_Color=lin(color), Roughness=0.7)
    try:
        m.surface_render_method = "BLENDED"
    except Exception:
        m.blend_method = "BLEND"
    return m


def m_ink(name, color="#2B1B1B"):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = lin(color)
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    m.use_backface_culling = True
    if hasattr(m, "use_backface_culling_shadow"):
        m.use_backface_culling_shadow = True
    return m


def kind_of(part_name: str, color: str, skin: str) -> str:
    """Which surface a drawn part gets, from its name and colour."""
    n = part_name.lower()
    if color.upper() == skin.upper():
        return "skin"
    for words, k in ((("hair", "beard", "mustache", "moustache", "braid", "bun", "ponytail", "topknot", "curl", "lock", "fringe", "puff"), "hair"),
                     (("ermine", "fur", "fleece", "wool", "beanie", "puff", "pompom"), "fur"),
                     (("gem", "jewel", "pearl", "bead"), "gem"),
                     (("crown", "buckle", "button", "badge", "medal", "helmet", "armor", "armour", "breastplate", "pauldron", "fauld", "rivet", "stud",
                       "clasp", "chain", "ring", "brooch", "whistle", "zip", "blade", "tsuba", "wrench", "pin", "steth", "hardhat", "glasses", "earring",
                       "kusazuri", "pommel", "cross", "bell", "knob", "tool_h"), "metal"),
                     (("belt", "boot", "shoe", "strap", "bag", "glove", "sole", "sandal", "pouch", "holster", "saya", "pack"), "leather")):
        if any(w in n for w in words):
            return k
    return "cloth"


# ------------------------------------------------------------------------------------------------ flat-drawing maths
def _scan_x(pts, z):
    """x values where a closed outline crosses height z"""
    xs = []
    n = len(pts)
    for i in range(n):
        (x0, z0), (x1, z1) = pts[i], pts[(i + 1) % n]
        if (z0 <= z < z1) or (z1 <= z < z0):
            xs.append(x0 + (x1 - x0) * (z - z0) / (z1 - z0))
    return xs


def _scan_z(pts, x):
    zs = []
    n = len(pts)
    for i in range(n):
        (x0, z0), (x1, z1) = pts[i], pts[(i + 1) % n]
        if (x0 <= x < x1) or (x1 <= x < x0):
            zs.append(z0 + (z1 - z0) * (x - x0) / (x1 - x0))
    return zs


def bbox(pts):
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return min(xs), min(zs), max(xs), max(zs)


def _interp(profile, z):
    """radius of a (r, z) profile at height z (profile sorted by z, any direction); 0 outside"""
    pr = sorted(profile, key=lambda p: p[1])
    if z < pr[0][1] or z > pr[-1][1]:
        return 0.0
    for (r0, z0), (r1, z1) in zip(pr, pr[1:]):
        if z0 <= z <= z1:
            return r0 if z1 - z0 < 1e-9 else r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return pr[-1][0]


def _sphere(bm, c, r, scale=(1, 1, 1), seg=24, rings=14):
    mtx = Matrix.Translation(Vector(c)) @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r, matrix=mtx)


def _tube(bm, A, B, ra, rb, seg=20, caps=True):
    A, B = Vector(A), Vector(B)
    d = B - A
    if d.length < 1e-6:
        return
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=ra, radius2=rb, depth=d.length,
                          matrix=Matrix.Translation((A + B) / 2) @ rot)
    if caps:
        _sphere(bm, A, ra, seg=seg, rings=10)
        _sphere(bm, B, rb, seg=seg, rings=10)


def _lathe(bm, profile, seg=64, a0=0.0, a1=math.tau, sy=1.0, ripple=None, cap_bottom=False, cap_top=False, cx=0.0, cy=0.0):
    """spin (r, z) points round Z. Angles: 0 = +X, 90 = +Y (the back), 270 = -Y (the front)."""
    closed = abs((a1 - a0) - math.tau) < 1e-6
    n = seg if closed else seg + 1
    rows = []
    for k, (r, z) in enumerate(profile):
        kk = k / max(1, len(profile) - 1)
        row = []
        for i in range(n):
            th = a0 + (a1 - a0) * i / seg
            rr = max(1e-4, r) * (ripple(th, kk) if ripple else 1.0)
            row.append(bm.verts.new((cx + rr * math.cos(th), cy + rr * math.sin(th) * sy, z)))
        rows.append(row)
    for k in range(len(rows) - 1):
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            bm.faces.new((rows[k][i], rows[k][j], rows[k + 1][j], rows[k + 1][i]))
    if cap_bottom and closed:
        bm.faces.new(list(reversed(rows[-1])))
    if cap_top and closed:
        bm.faces.new(rows[0])
    return rows


def _flat_mesh(pts, step=0.016):
    """a flat outline (x, z) as a finely cut mesh in the XZ plane, ready to be bent onto a body"""
    bm = bmesh.new()
    clean = []
    for p in pts:
        if not clean or (abs(p[0] - clean[-1][0]) + abs(p[1] - clean[-1][1])) > 1e-5:
            clean.append((float(p[0]), float(p[1])))
    if len(clean) > 2 and abs(clean[0][0] - clean[-1][0]) + abs(clean[0][1] - clean[-1][1]) < 1e-5:
        clean.pop()
    if len(clean) < 3:
        return bm
    vs = [bm.verts.new((x, 0.0, z)) for x, z in clean]
    try:
        bm.faces.new(vs)
    except ValueError:
        return bm
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    x0, z0, x1, z1 = bbox(clean)
    for axis, lo, hi, no in ((0, x0, x1, (1, 0, 0)), (2, z0, z1, (0, 0, 1))):
        n = int((hi - lo) / step)
        for k in range(1, n + 1):
            co = [0.0, 0.0, 0.0]
            co[axis] = lo + (hi - lo) * k / (n + 1)
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co, plane_no=no, dist=1e-6)
    return bm


def _eye_material(fig, sfx, cx, cz, SE, iris_hex):
    """White, iris, pupil and two catch-lights, drawn by position inside the eye opening. The values to animate are the
    Value nodes named sc (iris size), lx / lz (where the eye looks, metres) and g (catch-light size)."""
    R, hz = fig.R, fig.hz
    m = bpy.data.materials.new(f"{fig.name}.eye.{sfx}")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nt.nodes.new("ShaderNodeTexCoord").outputs["Object"], sep.inputs[0])

    def val(name, v):
        n = nt.nodes.new("ShaderNodeValue")
        n.name = n.label = name
        n.outputs[0].default_value = v
        return n.outputs[0]

    def mth(op, a_, b_=None):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = op
        for i, x in enumerate((a_, b_)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = float(x)
            else:
                nt.links.new(x, n.inputs[i])
        return n.outputs[0]

    sc, lx, lz, g = val("sc", 1.0), val("lx", 0.0), val("lz", 0.0), val("g", 1.0)
    a0, b0 = 0.076 * SE * R, 0.110 * SE * R
    X0, Z0 = cx * R, hz + (cz - 0.014 * SE) * R
    dx = mth("DIVIDE", mth("SUBTRACT", mth("SUBTRACT", sep.outputs["X"], X0), lx), mth("MULTIPLY", sc, a0))
    dz = mth("DIVIDE", mth("SUBTRACT", mth("SUBTRACT", sep.outputs["Z"], Z0), lz), mth("MULTIPLY", sc, b0))
    dist = lambda ox, oz: mth("SQRT", mth("ADD", mth("POWER", mth("SUBTRACT", dx, ox), 2.0), mth("POWER", mth("SUBTRACT", dz, oz), 2.0)))
    d = dist(0.0, 0.0)
    in_iris, in_pupil = mth("LESS_THAN", d, 1.0), mth("LESS_THAN", d, 0.55)
    glint = mth("MAXIMUM", mth("LESS_THAN", dist(-0.36, 0.36), mth("MULTIPLY", g, 0.34)), mth("LESS_THAN", dist(0.38, -0.50), mth("MULTIPLY", g, 0.15)))
    col = _mixc(nt, lin("#FBF8F2"), _mixc(nt, lin(iris_hex), lin(shade(iris_hex, 0.52)), mth("MINIMUM", mth("POWER", d, 2.0), 1.0)), in_iris)
    col = _mixc(nt, col, lin("#140D0C"), in_pupil)
    col = _mixc(nt, col, (1.0, 1.0, 1.0, 1.0), glint)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.3
    nt.links.new(col, bsdf.inputs["Emission Color"])
    nt.links.new(mth("ADD", mth("MULTIPLY", glint, 1.2), 0.10), bsdf.inputs["Emission Strength"])
    return m


# ------------------------------------------------------------------------------------------------ the figure
HAT_WORDS = ("hat", "cap", "helmet", "hood", "bonnet", "beanie", "toque", "headwrap", "headband", "scarf", "kerchief", "beret", "turban", "tricorn")
STUD_WORDS = ("button", "gem", "medal", "badge", "brooch", "buckle", "pearl", "rivet", "stud", "clasp", "pendant", "knot", "pin", "jewel", "bead",
              "whistle", "pull", "mid")
FRONT_WORDS = ("apron", "bib", "pocket", "tie", "front", "placket", "jabot", "cravat", "lapel", "collar", "neck", "shirt_v", "v", "bow", "tag", "zip",
               "lanyard", "steth", "closure", "opening", "lace", "flap", "panel", "yoke", "split", "slit", "seam", "pleat", "fold", "stripe")
HAIR_BLOB = ("bun", "ponytail", "topknot", "puff", "braid", "pigtail")


class Fig:
    """One built character: joints, body, face control, and every clothing / hair / hat part by name."""

    def __init__(self, sheet: dict, name: str, coll=None):
        self.name = name
        self.sheet = sheet
        self.b = copy.deepcopy(sheet["body"])
        if not sheet.get("slim"):                            # the house proportions: sturdier arms, hands and feet, a fuller skirt
            fb = self.b
            for k_ in ("r_sh", "r_el", "r_wr"):
                fb[k_] = fb[k_] * 1.30
            fb["hand_r"] = fb["hand_r"] * 1.18
            fb["foot"] = dict(fb["foot"], w=fb["foot"]["w"] * 1.25, len=fb["foot"]["len"] * 1.2)
            if fb.get("robe"):
                wz = fb.get("waist_z", fb["hip_z"])
                zmin = min(q_[1] for q_ in fb["torso"])
                fb["torso"] = [[w_ * (1.0 + 0.30 * max(0.0, (wz - z_) / max(1e-6, wz - zmin))) * (1.08 if z_ > wz else 1.0), z_] for w_, z_ in fb["torso"]]
            else:
                fb["torso"] = [[w_ * 1.06, z_] for w_, z_ in fb["torso"]]
        asset = src_b = None
        self.own_head, self._head_bvh = False, None
        hat = next((q for q in sheet.get("attach", []) or [] if q.get("fit") == "hat"), None)
        self._hat_seat = float(hat.get("seat", 0.60)) if hat else None      # a worn hat: how high on the head its edge sits (head radii)
        if sheet.get("body_model"):                          # a sculpted body from library/bodies brings its own proportions
            from . import body3d
            asset = body3d.load(sheet["body_model"])
            self.own_head = bool(sheet.get("own_head")) and bool(asset["meta"].get("head")) and asset.get("below") is not None
            src_b = body3d.fit_sheet(self.b, asset, self.own_head)
            if self.own_head:                                # the sculpt keeps its head: the face and hair are set on that surface
                self._head_bvh = body3d.head_surface(asset, self.b["R"])
            dz = self.b["head_z"] - src_b["head_z"]          # what is drawn on the head moves with the head
            self.sheet = sheet = dict(sheet, parts=[dict(q, pts=[[x, z + dz] for x, z in q["pts"]]) if (q.get("on") == "head" and q.get("pts")) else q
                                                     for q in sheet.get("parts", [])])
        self.col = dict(sheet.get("colors", {}))
        self.keys = dict(sheet.get("keys", {}))
        self.skin = self.col.get("skin", "#F8D7B2")
        self.coll = coll or bpy.data.collections.new(name)
        if coll is None:
            bpy.context.scene.collection.children.link(self.coll)
        self.parts, self.J, self.W, self.mats, self.face_obs, self.eye = {}, {}, {}, {}, [], {}
        self.ink = m_ink(f"{name}.ink", sheet.get("ink", "#2B1B1B"))
        self.head_env = []                                   # hat profiles: flat drawings on the head sit on top of these
        b = self.b
        self.R, self.hz = b["R"], b["head_z"]
        self.robe = bool(b.get("robe"))
        self.waist = b.get("waist_z", b["hip_z"]) if self.robe else b["hip_z"]
        self._beard = any("beard" in str(q.get("name", "")).lower() for q in sheet.get("parts", []))
        self.body = None
        skinned = sheet.get("body_build") == "skinned" or asset is not None     # one skinned surface from the neck down, clothes made from it (stagekit.body3d)
        if skinned and asset is None:                        # a ball-joint shoulder sits on the side of the trunk, not inside it
            self.b["sh_x"] = max(self.b["sh_x"], 0.98 * self.torso_r(self.b["sh_z"]))
        self._joints()
        self._ctrl()
        if skinned:
            from . import body3d
            self._body(head_only=True)
            self.body = body3d.SculptBody(self, asset, src_b) if asset is not None else body3d.Body(self)
        else:
            self._body()
        self._face()
        self._pieces(sheet.get("parts", []))
        self._trim()
        if self.body:
            self.body.dress()
            if (sheet.get("cloth") or {}).get("skin"):       # a skin from the store: the nose and ears wear it too
                sm = self.body._material("skin", self.skin.upper())
                for nm in ("Nose", "Ear.L", "Ear.R"):
                    for ob in self.parts.get(nm, []):
                        co = [c_ for v_ in ob.data.vertices for c_ in v_.co]
                        ob.data.attributes.new("c3_rest", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", co)
                        ob.data.materials[0] = sm
            for spec in sheet.get("attach", []) or []:
                self.attach(spec)
        else:
            self._hands()
            if self.robe:
                self._skirt_keys()

    # ------------------------------------------------------------------ joints
    def _joints(self):
        b = self.b
        L1, L2 = b["arm1"], b["arm2"]
        js = [("root", None, (0, 0, 0)), ("hips", "root", (0, 0, b["hip_z"])), ("torso", "hips", (0, 0, self.waist)),
              ("head", "torso", (0, 0, b["neck_z"] + 0.02)), ("skirt", "hips", (0, 0, self.waist)), ("cape", "torso", (0, 0.05, b["neck_z"] - 0.04))]
        for sfx, s in (("L", 1.0), ("R", -1.0)):
            js += [(f"sh.{sfx}", "torso", (s * b["sh_x"], 0, b["sh_z"])), (f"el.{sfx}", f"sh.{sfx}", (s * b["sh_x"], 0, b["sh_z"] - L1)),
                   (f"wr.{sfx}", f"el.{sfx}", (s * b["sh_x"], 0, b["sh_z"] - L1 - L2)),
                   (f"hip.{sfx}", "hips", (s * b["hip_x"], 0, b["leg_z"])), (f"kn.{sfx}", f"hip.{sfx}", (s * b["hip_x"], 0, b["knee_z"])),
                   (f"an.{sfx}", f"kn.{sfx}", (s * b["hip_x"], 0, b["ankle_z"]))]
        for jn, par, w in js:
            e = bpy.data.objects.new(f"{self.name}.j.{jn}", None)
            e.empty_display_size = 0.03
            self.coll.objects.link(e)
            self.W[jn] = Vector(w)
            self.J[jn] = e
            if par:
                e.parent = self.J[par]
                e.location = Vector(w) - self.W[par]
            e.rotation_mode = "QUATERNION" if jn.startswith(("sh.", "el.")) else "XYZ"

    def _ctrl(self):
        c = bpy.data.objects.new(f"{self.name}.ctrl", None)
        self.coll.objects.link(c)
        c.parent = self.J["root"]
        for e in EXPRS:
            c[e] = 0.0
        for v in VISEMES:
            c[f"viseme_{v}"] = 0.0
        for k in ("blink", "look_x", "look_z"):
            c[k] = 0.0
        for s in "LR":
            for h in HAND_SHAPES[1:]:
                c[f"hand_{s}_{h}"] = 0.0
        self.ctrl = c

    # ------------------------------------------------------------------ plumbing
    def mat(self, kind, color, key=None):
        k = (kind, color.upper())
        if k not in self.mats:
            self.mats[k] = material(kind, color, f"{self.name}.{kind}.{color.lstrip('#')}", self.b.get("height", 1.6))
        return self.mats[k]

    def finish(self, name, bm, parent, kind="cloth", color="#888888", key=None, ink=True, smooth=True, shell=0.0, shadow=True, mat=None):
        me = bpy.data.meshes.new(f"{self.name}_{name}")
        bm.normal_update()
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = smooth
        ob = bpy.data.objects.new(f"{self.name}.{name}", me)
        self.coll.objects.link(ob)
        me.materials.append(mat or self.mat(kind, color))
        if shell:
            sd = ob.modifiers.new("shell", "SOLIDIFY")
            sd.thickness = shell
            sd.offset = 0.0
        if ink and INK_ON:
            me.materials.append(self.ink)
            hd = ob.modifiers.new("ink", "SOLIDIFY")
            hd.thickness = ink if isinstance(ink, float) else INK
            hd.offset = 1.0
            hd.use_flip_normals = True
            hd.use_rim = False
            hd.material_offset = 1
        if not shadow:
            ob.visible_shadow = False
        ob.parent = self.J[parent]
        ob.location = -self.W[parent]
        ob["c3_part"] = name
        ob["c3_kind"] = kind
        ob["c3_color"] = color
        ob["c3_key"] = key or ""
        self.parts.setdefault(name, []).append(ob)
        if self.robe and parent in ("skirt", "cape"):
            self._squat_key(ob, parent)
        return ob

    def _squat_key(self, ob, parent):
        top = self.waist if parent == "skirt" else self.b["neck_z"]
        hem = self.b.get("hem_z", 0.1)
        spread = 0.30 if parent == "skirt" else 0.42
        ob.shape_key_add(name="Basis")
        kb = ob.shape_key_add(name="squat")
        kb.value = 0.0
        for vi, v in enumerate(ob.data.vertices):
            k = max(0.0, min(1.0, (top - v.co.z) / max(1e-6, top - hem)))
            g = 1.0 + spread * math.sin(math.pi * min(1.0, k * 0.9)) * 0.9 + spread * 0.5 * k
            kb.data[vi].co = (v.co.x * g, v.co.y * g, v.co.z + SQUAT_MAX * k)

    # ------------------------------------------------------------------ the forms flat drawings are bent onto
    def torso_r(self, z):
        return _interp(self.b["torso"], z)

    def torso_sy(self, z):
        return 0.86 if (self.robe and z < self.waist) else 0.76

    def head_r(self, z):
        dz = (z - self.hz) / self.R
        r = self.R * math.sqrt(max(0.0, 1.0 - dz * dz))
        for prof in self.head_env:
            r = max(r, _interp(prof, z))
        return r

    def wrap(self, bm, on, lift, back=False):
        """bend a flat mesh (XZ plane, model space) onto the torso or the head"""
        for v in bm.verts:
            x, z = v.co.x, v.co.z
            if on == "head":
                r, sy = self.head_r(z) + lift, 1.0
                lim = 0.90 * r
                if abs(x) <= lim:
                    y = math.sqrt(max(0.0, r * r - x * x))
                else:                                        # past the edge of the head: carry on round it
                    ph = min(math.radians(150), math.asin(0.90) + (abs(x) - lim) / max(r, 1e-6))
                    x, y = math.copysign(r * math.sin(ph), x), r * math.cos(ph)
            else:
                r, sy = self.torso_r(z) + lift, self.torso_sy(z)
                ph = max(-math.radians(165), min(math.radians(165), x / max(r, 1e-6) * 1.08))
                x, y = r * math.sin(ph), sy * r * math.cos(ph)
            v.co.x = x
            v.co.y = y if back else -y

    # ------------------------------------------------------------------ body
    def _body(self, head_only=False):
        b, col, K = self.b, self.col, self.keys
        R, hz = self.R, self.hz
        prof = sorted(b["torso"], key=lambda p: -p[1])
        if head_only:
            pass
        elif self.robe:
            up = [p for p in prof if p[1] >= self.waist - 0.02]
            lo = [p for p in prof if p[1] <= self.waist + 0.02]
            bm = bmesh.new()
            _lathe(bm, [(0.05, b["neck_z"] + 0.045)] + up, seg=56, sy=0.76, cap_top=True, cap_bottom=True)
            self.finish("Torso", bm, "torso", "cloth", col["torso"], K.get("torso"))
            bm = bmesh.new()
            hem = lo[-1]
            _lathe(bm, lo + [(hem[0] * 0.95, hem[1] - 0.012)], seg=96, sy=0.86, cap_top=True, cap_bottom=True,
                   ripple=lambda th, k: 1.0 + 0.04 * (k ** 1.5) * math.cos(14 * th))
            self.finish("Skirt", bm, "skirt", "cloth", col["torso"], K.get("torso"))
            b["hem_z"] = hem[1]
        else:
            bm = bmesh.new()
            _lathe(bm, [(0.05, b["neck_z"] + 0.045)] + prof + [(prof[-1][0] * 0.82, prof[-1][1] - 0.02)], seg=56, sy=0.76, cap_top=True, cap_bottom=True)
            self.finish("Torso", bm, "torso", "cloth", col["torso"], K.get("torso"))
        if not head_only:
            bm = bmesh.new()
            _tube(bm, (0, 0, b["neck_z"] - 0.04), (0, 0, hz - R * 0.8), 0.05, 0.05, caps=False)
            self.finish("Neck", bm, "torso", "skin", self.skin, "skin", ink=False)
        nz_ = self.sheet.get("face", {}).get("nz", -0.15)
        if self.own_head:
            nose = self._on_head(0.0, nz_, -0.045 * R)
        else:
            bm = bmesh.new()
            _sphere(bm, (0, 0, hz), R, seg=64, rings=32)
            self.finish("Head", bm, "head", "skin", self.skin, "skin")
            nose = Vector((0, -R * 0.955, hz + nz_ * R))
        bm = bmesh.new()
        _sphere(bm, nose, 0.082 * R, scale=(0.95, 0.72, 0.72), seg=16, rings=10)
        self.finish("Nose", bm, "head", "skin", self.skin, "skin", ink=0.004)
        if b.get("ears") and not self.own_head:
            for sfx, s in (("L", 1.0), ("R", -1.0)):
                bm = bmesh.new()
                _sphere(bm, (s * R * 0.99, 0.01, hz - 0.06 * R), 0.16 * R, scale=(0.45, 0.8, 1.0), seg=16, rings=10)
                self.finish(f"Ear.{sfx}", bm, "head", "skin", self.skin, "skin", ink=0.004)
        if head_only:
            return
        # arms
        for sfx in ("L", "R"):
            sh, el, wr = self.W[f"sh.{sfx}"], self.W[f"el.{sfx}"], self.W[f"wr.{sfx}"]
            for nm, A, B, ra, rb, c, key, par in ((f"Arm.{sfx}", sh, el, b["r_sh"], b["r_el"], col["sleeve_u"], K.get("sleeve_u"), f"sh.{sfx}"),
                                                  (f"Arm_Lower.{sfx}", el, wr, b["r_el"], b["r_wr"], col["sleeve_l"], K.get("sleeve_l"), f"el.{sfx}")):
                bm = bmesh.new()
                _tube(bm, A, B, ra, rb)
                self.finish(nm, bm, par, kind_of("sleeve", c, self.skin), c, key)
        # legs and feet
        ft = b["foot"]
        for sfx in ("L", "R"):
            hp, kn, an = self.W[f"hip.{sfx}"], self.W[f"kn.{sfx}"], self.W[f"an.{sfx}"]
            for nm, A, B, ra, rb, c, key, par in ((f"Leg.{sfx}", hp, kn, b["r_hip"], b["r_kn"], col["leg_u"], K.get("leg_u"), f"hip.{sfx}"),
                                                  (f"Leg_Lower.{sfx}", kn, an, b["r_kn"], b["r_an"], col["leg_l"], K.get("leg_l"), f"kn.{sfx}")):
                bm = bmesh.new()
                _tube(bm, A, B, ra, rb)
                self.finish(nm, bm, par, kind_of("trouser", c, self.skin), c, key, ink=0.005)
            if col.get("shoe"):
                bm = bmesh.new()
                fl, fw = ft.get("len", 0.10), ft.get("w", 0.05)
                _sphere(bm, an + Vector((0, -fl * 0.40, -an.z + fw * 0.86)), fw * 1.08, scale=(1.0, fl / fw * 1.0, 0.80), seg=20, rings=12)
                self.finish(f"Foot.{sfx}", bm, f"an.{sfx}", "leather", col["shoe"], K.get("shoe"))
                if ft.get("top", 0.0) > an.z + 0.05:           # a boot: the shaft rides the shin
                    bm = bmesh.new()
                    _tube(bm, Vector((an.x, 0, 0.045)), Vector((an.x, 0, ft["top"])), b["r_an"] + 0.012, b["r_kn"] + 0.010, caps=False)
                    self.finish(f"Boot.{sfx}", bm, f"kn.{sfx}", "leather", col["shoe"], K.get("shoe"), ink=0.005)

    def _hands(self):
        b, col, K = self.b, self.col, self.keys
        hr = b["hand_r"]
        c = col.get("hand", self.skin)
        kind = "skin" if c.upper() == self.skin.upper() else "leather"
        for sfx in ("L", "R"):
            wr = self.W[f"wr.{sfx}"]
            hc = wr + Vector((0, 0, -hr * 0.95))
            bm = bmesh.new()
            _sphere(bm, hc, hr, scale=(0.82, 1.0, 1.10), seg=24, rings=14)
            _sphere(bm, hc + Vector((0, -hr * 0.80, hr * 0.25)), hr * 0.42, scale=(1, 1.2, 1.3), seg=14, rings=8)
            palm = self.finish(f"Hand.{sfx}", bm, f"wr.{sfx}", kind, c, K.get("hand", "skin"))
            # fingers: four short ones that fan out of the mitten (open), one that points
            bm = bmesh.new()
            for i in range(4):
                a = math.radians(-27 + 18 * i)
                tip = hc + Vector((0, math.sin(a) * hr * 1.05, -math.cos(a) * hr * 1.75))
                _tube(bm, hc + Vector((0, math.sin(a) * hr * 0.5, -hr * 0.6)), tip, hr * 0.26, hr * 0.22, seg=10)
            fo = self.finish(f"Fingers.{sfx}", bm, f"wr.{sfx}", kind, c, K.get("hand", "skin"), ink=0.004)
            bm = bmesh.new()
            _tube(bm, hc + Vector((0, -hr * 0.3, -hr * 0.6)), hc + Vector((0, -hr * 0.35, -hr * 2.1)), hr * 0.27, hr * 0.22, seg=10)
            po = self.finish(f"Pointer.{sfx}", bm, f"wr.{sfx}", kind, c, K.get("hand", "skin"), ink=0.004)
            for ob, expr, vs in ((fo, "max(0.001, o + 0.5 * p)", {"o": f"hand_{sfx}_open", "p": f"hand_{sfx}_pinch"}),
                                 (po, "max(0.001, p)", {"p": f"hand_{sfx}_point"})):
                piv = hc + Vector((0, 0, -hr * 0.4))
                for v in ob.data.vertices:                    # scale about the knuckles, not the wrist
                    v.co -= piv
                ob.location = Vector(ob.location) + piv
                for i in range(3):
                    self._drive(ob, "scale", expr, vs, index=i)
            self._drive(palm, "scale", "1.0 - 0.07 * f - 0.05 * g", {"f": f"hand_{sfx}_fist", "g": f"hand_{sfx}_grip"}, index=1)

    def _drive(self, ob, path, expr, vs, index=-1):
        fc = ob.driver_add(path, index) if index >= 0 else ob.driver_add(path)
        d = fc.driver
        d.type = "SCRIPTED"
        for vn, prop in vs.items():
            v = d.variables.new()
            v.name = vn
            v.type = "SINGLE_PROP"
            v.targets[0].id_type = "OBJECT"
            v.targets[0].id = self.ctrl
            v.targets[0].data_path = f'["{prop}"]'
        d.expression = expr

    # ------------------------------------------------------------------ face
    def _on_head(self, x, z, lift):
        if self._head_bvh is not None:                       # the sculpt's own head: the same place seen from the front, on its real surface
            hit, nrm, _i, _d = self._head_bvh.ray_cast(Vector((x * self.R, -5.0, self.hz + z * self.R)), Vector((0, 1, 0)))
            if hit is not None:
                return hit + (nrm if nrm.y < 0 else -nrm) * lift
        d = max(0.0, 1.0 - x * x - z * z)
        v = Vector((x, -math.sqrt(d), z))
        if v.length < 1e-6:
            v = Vector((0, -1, 0))
        v.normalize()
        return Vector((0, 0, self.hz)) + v * (self.R + lift)

    def _band(self, name, mat, shapes, lift, nu=28, nv=6, radial=False):
        keys = list(shapes)

        def pts(s):
            cx, hw, upper, lower = s
            out = []
            for j in range(nv + 1):
                v = j / nv
                for i in range(nu + 1):
                    u = -1.0 + 2.0 * i / nu
                    lo, up = lower(u), upper(u)
                    out.append(self._on_head(cx + hw * u, lo + (up - lo) * v, lift))
            return out

        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new("uv")
        vs = [bm.verts.new(p) for p in pts(shapes[keys[0]])]
        for j in range(nv):
            for i in range(nu):
                a = j * (nu + 1) + i
                f = bm.faces.new((vs[a], vs[a + 1], vs[a + nu + 2], vs[a + nu + 1]))
                for lp, (ii, jj) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                    if radial:
                        lp[uvl].uv = (0.5, max(0.0, 1.0 - math.hypot(-1.0 + 2.0 * ii / nu, -1.0 + 2.0 * jj / nv)))
                    else:
                        lp[uvl].uv = (ii / nu, jj / nv)
        ob = self.finish(name, bm, "head", "plain", "#000000", ink=False, shadow=False, mat=mat)
        ob.shape_key_add(name="Basis")
        for k in keys[1:]:
            kb = ob.shape_key_add(name=k)
            kb.value = 0.0
            for i, p in enumerate(pts(shapes[k])):
                kb.data[i].co = p
        self.face_obs.append(ob)
        return ob

    def _key_driver(self, ob, key, expr, vs):
        fc = ob.data.shape_keys.key_blocks[key].driver_add("value")
        d = fc.driver
        d.type = "SCRIPTED"
        for vn, prop in vs.items():
            v = d.variables.new()
            v.name = vn
            v.type = "SINGLE_PROP"
            v.targets[0].id_type = "OBJECT"
            v.targets[0].id = self.ctrl
            v.targets[0].data_path = f'["{prop}"]'
        d.expression = expr

    def _face(self):
        f = dict(ex=0.32, ez=0.03, es=1.0, bx=0.33, bz=0.30, mz=-0.385, mw=1.0, eye="#1F1414", brow="#5E3518", lips="#6E2420", blush=True)
        f.update(self.sheet.get("face", {}))
        circ = lambda u: math.sqrt(max(0.0, 1.0 - u * u))
        es = f["es"]
        LOOK = {"look_xp": (0.045, 0.0), "look_xn": (-0.045, 0.0), "look_zp": (0.0, 0.04), "look_zn": (0.0, -0.045)}
        EV = {"h": "happy", "w": "worried", "a": "angry", "s": "sad", "u": "surprised", "l": "laugh", "g": "grin", "y": "sly", "b": "blink",
              "lx": "look_x", "lz": "look_z"}

        def with_look(shapes, k=1.0):
            cx, hw, up, lo = shapes["rest"]
            for nm, (dx, dz) in LOOK.items():
                shapes[nm] = (cx + dx * k, hw, (lambda u, up=up, dz=dz: up(u) + dz * k), (lambda u, lo=lo, dz=dz: lo(u) + dz * k))
            return shapes

        def look_drivers(ob):
            self._key_driver(ob, "look_xp", "max(0.0, lx)", {"lx": "look_x"})
            self._key_driver(ob, "look_xn", "max(0.0, -lx)", {"lx": "look_x"})
            self._key_driver(ob, "look_zp", "max(0.0, lz)", {"lz": "look_z"})
            self._key_driver(ob, "look_zn", "max(0.0, -lz)", {"lz": "look_z"})

        for side, sfx in ((1, "L"), (-1, "R")):
            cx, cz = side * f["ex"], f["ez"]
            s_ = side
            U0, L0 = (lambda u: 0.150 * circ(u)), (lambda u: -0.150 * circ(u))
            OPEN = {   # the eye opening: half width, upper edge, lower edge (head units from the eye's centre)
                "rest": (0.105, U0, L0),
                "wide": (0.118, lambda u: 0.172 * circ(u), lambda u: -0.172 * circ(u)),
                "happy": (0.105, U0, lambda u: max(L0(u), -0.085 + 0.035 * circ(u))),
                "angry": (0.105, lambda u, s_=s_: min(U0(u), 0.060 + 0.085 * s_ * u), lambda u: max(L0(u), -0.105 + 0.02 * circ(u))),
                "sad": (0.105, lambda u, s_=s_: min(U0(u), 0.060 - 0.085 * s_ * u), L0),
                "half": (0.105, lambda u: min(U0(u), 0.045 + 0.01 * circ(u)), L0),
                "sly": (0.105, lambda u: min(U0(u), 0.050 + 0.01 * circ(u)), lambda u: max(L0(u), -0.080 + 0.030 * circ(u))),
                "closed": (0.100, lambda u: -0.050 * circ(u) + 0.0006, lambda u: -0.050 * circ(u) - 0.0006),
                "joy": (0.100, lambda u: -0.035 + 0.085 * circ(u) + 0.0006, lambda u: -0.035 + 0.085 * circ(u) - 0.0006),
            }
            SE = S_EYE * es

            def shape(hw, up, lo, cx=cx, cz=cz, SE=SE):
                return (cx, hw * SE, (lambda u: cz + SE * up(u)), (lambda u: cz + SE * min(lo(u), up(u))))

            self.eye[f"eye.{sfx}"] = self._band(f"Eye.{sfx}", _eye_material(self, sfx, cx, cz, SE, f.get("iris", "#8A5A30")),
                                                {k: shape(*v) for k, v in OPEN.items()}, 0.0032, nu=40, nv=22)
            lsh = {}
            for k, (hw, up, _lo) in OPEN.items():
                tk = 0.019 if k in ("closed", "joy") else 0.011
                th = lambda u, tk=tk: tk * circ(u) ** 0.5 + 0.002
                lsh[k] = shape(hw * 1.03, (lambda u, up=up, th=th: up(u) + th(u) * 0.6), (lambda u, up=up, th=th: up(u) - th(u) * 0.4))
            self.eye[f"lash.{sfx}"] = self._band(f"Lash.{sfx}", self.mat("plain", f.get("lash", "#4A2E20")), lsh, 0.0044, nu=40, nv=3)
            zc = cz - 0.30
            self.eye[f"tear.{sfx}"] = self._band(f"Tear.{sfx}", self.mat("glow", "#A9DCFF"), {
                "off": (cx + side * 0.03, 0.0006, lambda u, zc=zc: zc + 0.0006, lambda u, zc=zc: zc - 0.0006),
                "drop": (cx + side * 0.03, 0.036, lambda u, zc=zc: zc + 0.048 * circ(u) + 0.058 * (1 - abs(u)) ** 2, lambda u, zc=zc: zc - 0.048 * circ(u)),
                "stream": (cx + side * 0.04, 0.032, lambda u, cz=cz: cz - 0.15 + 0.02 * (1 - abs(u)), lambda u, cz=cz: cz - 0.58 - 0.04 * circ(u))},
                0.0052, nu=10, nv=8)
            bx, bz = side * f["bx"], f["bz"] + 0.055            # brows clear of the bigger eyes

            def brow(z, arch, tilt, th=0.036, hw=0.125, bx=bx, side=side):
                mid = lambda u: z + arch * (1 - u * u) + tilt * (side * u)
                return (bx, hw, lambda u: mid(u) + th * 0.5 * circ(u) ** 0.6, lambda u: mid(u) - th * 0.5 * circ(u) ** 0.6)

            br = self._band(f"Brow.{sfx}", self.mat("plain", f["brow"]),
                            with_look({"rest": brow(bz, 0.035, -0.01), "up": brow(bz + 0.10, 0.06, -0.02), "frown": brow(bz - 0.03, 0.01, 0.075),
                                       "sad_brow": brow(bz + 0.03, 0.03, -0.085), "villain": brow(bz + 0.07, 0.075, 0.085, 0.042, 0.14)}, 0.4), 0.0030, nu=20, nv=4)
            self._key_driver(br, "up", "min(1.0, u + 0.35 * h + 0.6 * l)", {"u": "surprised", "h": "happy", "l": "laugh"})
            self._key_driver(br, "frown", "min(1.0, a)", {"a": "angry"})
            self._key_driver(br, "sad_brow", "min(1.0, s + 0.8 * w)", {"s": "sad", "w": "worried"})
            self._key_driver(br, "villain", "min(1.0, g + y)", {"g": "grin", "y": "sly"})
            look_drivers(br)
            if f.get("blush"):
                ck = self._band(f"Cheek.{sfx}", m_blush(f"{self.name}.blush.{sfx}", f.get("blush_color", "#F08A7A")),
                                {"rest": (side * 0.56, 0.17, lambda u: -0.24 + 0.14 * circ(u), lambda u: -0.24 - 0.14 * circ(u)),
                                 "lifted": (side * 0.58, 0.18, lambda u: -0.16 + 0.14 * circ(u), lambda u: -0.16 - 0.14 * circ(u))}, 0.0012, nu=16, nv=16, radial=True)
                self._key_driver(ck, "lifted", "min(1.0, l + g + 0.6 * h)", {"l": "laugh", "g": "grin", "h": "happy"})
        # mouth: half width, centre z offset, corner lift, opening above / below, upper / lower teeth share
        mz, mw = f["mz"], f["mw"]
        M = {"rest": (0.215, 0.0, 0.085, 0.011, 0.011, 0.0, 0.0),
             "m_happy": (0.270, -0.005, 0.125, 0.012, 0.070, 0.62, 0.0), "m_worried": (0.150, -0.02, -0.035, 0.014, 0.030, 0.0, 0.0),
             "m_angry": (0.200, -0.02, -0.095, 0.030, 0.050, 0.485, 0.485), "m_sad": (0.190, -0.03, -0.110, 0.011, 0.011, 0.0, 0.0),
             "m_surprised": (0.105, -0.035, 0.0, 0.110, 0.125, 0.0, 0.0), "m_laugh": (0.300, 0.02, 0.150, 0.020, 0.255, 0.26, 0.0),
             "m_grin": (0.470, -0.015, 0.300, 0.045, 0.130, 0.485, 0.485), "m_sly": (0.300, 0.0, 0.170, 0.011, 0.011, 0.0, 0.0),
             "v_A": (0.165, -0.02, 0.030, 0.045, 0.150, 0.26, 0.0), "v_E": (0.230, 0.0, 0.050, 0.022, 0.060, 0.55, 0.0),
             "v_I": (0.250, 0.0, 0.085, 0.016, 0.040, 0.70, 0.0), "v_O": (0.100, -0.03, 0.0, 0.085, 0.095, 0.0, 0.0),
             "v_U": (0.070, -0.02, 0.0, 0.050, 0.055, 0.0, 0.0), "v_MBP": (0.170, 0.0, 0.030, 0.008, 0.008, 0.0, 0.0)}

        def curves(p, grow=0.0):
            w, dz, lift, up, dn, _fu, _fl = p
            w *= mw
            line = lambda u: mz + dz + lift * u * u
            shp = lambda u: circ(u) ** 0.75
            return (w + grow * 1.2, (lambda u: line(u) + (up + grow) * shp(u) + grow * 0.35), (lambda u: line(u) - (dn + grow) * shp(u) - grow * 0.35))

        def mshapes(kind):
            out = {}
            for k, p in M.items():
                w, upper, lower = curves(p, 0.020 if kind == "lips" else 0.0)
                fu, fl = p[5], p[6]
                if kind in ("lips", "cavity"):
                    out[k] = (0.0, w, upper, lower)
                elif kind == "teeth_up":
                    out[k] = (0.0, w * 0.985, upper, (lambda u, upper=upper, lower=lower, fu=fu: upper(u) - (upper(u) - lower(u)) * fu))
                elif kind == "teeth_dn":
                    out[k] = (0.0, w * 0.985, (lambda u, upper=upper, lower=lower, fl=fl: lower(u) + (upper(u) - lower(u)) * fl), lower)
                else:
                    show = 1.0 if (p[4] > 0.1 and fl == 0.0) else 0.0
                    out[k] = (0.0, w * 0.55, (lambda u, lower=lower, p=p, show=show: lower(u * 0.55) + show * p[4] * 0.62 * circ(u) + 0.002),
                              (lambda u, lower=lower: lower(u * 0.55) + 0.002))
            return out

        vis = "(1.0 - min(1.0, va + ve + vi + vo + vu + vm))"
        vvars = {"va": "viseme_A", "ve": "viseme_E", "vi": "viseme_I", "vo": "viseme_O", "vu": "viseme_U", "vm": "viseme_MBP"}
        ml = 0.0
        for nm, mat, lift, nu, nv in (("Lips", self.mat("plain", f["lips"]), 0.0020, 44, 8), ("Mouth", self.mat("plain", "#3A0E12"), 0.0032, 44, 8),
                                      ("Tongue", self.mat("plain", "#D9605F"), 0.0040, 20, 6), ("Teeth_Up", m_teeth(f"{self.name}.teeth_u"), 0.0048, 44, 4),
                                      ("Teeth_Dn", m_teeth(f"{self.name}.teeth_d"), 0.0048, 44, 4)):
            kind = {"Lips": "lips", "Mouth": "cavity", "Tongue": "tongue", "Teeth_Up": "teeth_up", "Teeth_Dn": "teeth_dn"}[nm]
            ob = self._band(nm, mat, mshapes(kind), lift + ml, nu=nu, nv=nv)
            for e in EXPRS:
                self._key_driver(ob, f"m_{e}", f"e * {vis}", dict(vvars, e=e))
            for v in VISEMES:
                self._key_driver(ob, f"v_{v}", "min(1.0, v)", {"v": f"viseme_{v}"})

    def _trim(self):
        """Costume trim asked for in the sheet: "trim": {"hem": "#FFC83A", "cuffs": "#FFC83A", "front": "#F6E7C2"}.
        hem: two bands round the hem of a gown; cuffs: a band at the end of each sleeve; front: a pale panel down the bodice."""
        t = self.sheet.get("trim") or {}
        b = self.b
        if t.get("hem") and self.robe:
            hem, w = b.get("hem_z", 0.13), 0.6
            for nm, z0, z1 in (("Hem_Trim", hem + 0.012, hem + 0.062), ("Hem_Trim2", hem + 0.085, hem + 0.098)):
                self._p_band(dict(name=nm, on="torso", pts=[(-w, z0), (w, z0), (w, z1), (-w, z1)], color=t["hem"], layer=11, mat="metal"))
        if t.get("front"):
            nz = b["neck_z"]
            self._p_decal(dict(name="Front_Panel", on="torso", color=t["front"], layer=10, mat="cloth",
                               pts=[(-0.050, nz - 0.055), (0.050, nz - 0.055), (0.014, self.waist), (-0.014, self.waist)]))
        if t.get("cuffs"):
            for sfx in "LR":
                if self.body:
                    self.body.paint(dict(name=f"Cuff_Trim.{sfx}", on=f"arm_lower.{sfx}", color=t["cuffs"], mat="metal", layer=16,
                                         s=(b["arm1"] + b["arm2"] - 0.052, b["arm1"] + b["arm2"] - 0.004)), "limb")
                    continue
                wr, r = self.W[f"wr.{sfx}"], b["r_wr"]
                bm = bmesh.new()
                _lathe(bm, [(r + 0.004, wr.z + 0.052), (r + 0.007, wr.z + 0.045), (r + 0.007, wr.z + 0.008), (r + 0.004, wr.z + 0.001)], seg=24, cx=wr.x, cy=wr.y)
                self.finish(f"Cuff_Trim.{sfx}", bm, f"el.{sfx}", "metal", t["cuffs"])

    def _skirt_keys(self):
        """A gown is cloth: the front of the skirt is pushed out by whichever thigh comes forward and the back by the one that
        trails (so a leg never breaks through), and it has a ripple round the hem and a flare for the gait to play."""
        hem = self.b.get("hem_z", 0.13)
        for obs in list(self.parts.values()):
            for ob in obs:
                if ob.type != "MESH" or ob.parent is not self.J["skirt"]:
                    continue
                if ob.data.shape_keys is None:
                    ob.shape_key_add(name="Basis")
                base = [v.co.copy() for v in ob.data.vertices]
                kf = lambda c: max(0.0, min(1.0, (self.waist - c.z) / max(1e-6, self.waist - hem)))
                for name in ("waveA", "waveB", "flare"):
                    kb = ob.shape_key_add(name=name)
                    kb.value = 0.0
                    for i, c in enumerate(base):
                        k = kf(c)
                        r = math.hypot(c.x, c.y) or 1e-6
                        th = math.atan2(c.y, c.x)
                        if name == "flare":
                            d, dz = 0.055 * k ** 1.5, 0.022 * k ** 2
                        else:
                            d, dz = 0.034 * k ** 1.6 * (math.sin(5 * th) if name == "waveA" else math.cos(5 * th)), 0.0
                        kb.data[i].co = (c.x + c.x / r * d, c.y + c.y / r * d, c.z + dz)
                for sfx, sd in (("L", 1.0), ("R", -1.0)):
                    for tag, fwd, D in (("F", -1.0, 0.36), ("B", 1.0, 0.20)):
                        kb = ob.shape_key_add(name=f"leg{tag}.{sfx}")
                        kb.value = 0.0
                        centre = math.atan2(fwd, sd * 0.42)
                        for i, c in enumerate(base):
                            th = math.atan2(c.y, c.x)
                            da = math.atan2(math.sin(th - centre), math.cos(th - centre))
                            wgt = math.exp(-(da / math.radians(48)) ** 2) * (kf(c) ** 1.15)
                            kb.data[i].co = (c.x + sd * 0.04 * wgt, c.y + fwd * D * wgt, c.z + 0.05 * wgt * (1.0 if tag == "F" else 0.4))
                        fc = kb.driver_add("value")
                        d = fc.driver
                        d.type = "SCRIPTED"
                        var = d.variables.new()
                        var.name = "r"
                        var.type = "TRANSFORMS"
                        var.targets[0].id = self.J[f"hip.{sfx}"]
                        var.targets[0].transform_type = "ROT_X"
                        var.targets[0].transform_space = "LOCAL_SPACE"
                        d.expression = "max(0.0, min(1.25, -r / 0.85))" if tag == "F" else "max(0.0, min(1.25, r / 0.85))"

    # ------------------------------------------------------------------ pieces: flat drawings become 3D
    def classify(self, p) -> str:
        if p.get("as"):
            return p["as"]
        if p.get("span") and p["on"].split(".")[0] in ("arm_upper", "arm_lower", "leg_upper", "leg_lower"):
            return "limb"                                    # a stretch of a limb given as a share of its length: no drawing needed
        if p.get("wire") or len(p.get("pts", [])) < 3:
            return "skip"
        n = p["name"].lower()
        on = p["on"].split(".")[0]
        x0, z0, x1, z1 = bbox(p["pts"])
        w, h, cx = x1 - x0, z1 - z0, (x0 + x1) / 2
        R = self.R
        if on == "head":
            if any(k in n for k in HAIR_BLOB) or "earring" in n:
                return "blob"
            if n.startswith("hair") or any(k in n for k in ("fringe", "curl", "lock")):
                return "skip" if any(k in n for k in ("line", "part", "strand", "edge")) else "hair"
            if "beard" in n or "mustache" in n or "moustache" in n or "goatee" in n or "sideburn" in n:
                return "beard"
            if "glasses" in n:
                return "glasses"
            if n.startswith("crown") or n.startswith("w_crown"):
                return "crown" if n.split(".")[0] in ("crown", "w_crown") else "skip"
            if n.startswith("ear"):
                return "skip"
            if p.get("layer", 0) >= 21.4 or any(k in n for k in HAT_WORDS):
                if abs(cx) < 0.04 and w > 0.9 * R:
                    return "peak" if any(k in n for k in ("peak", "visor")) else "lathe"
                return "decal"
            return "decal"
        if on == "torso":
            if p.get("layer", 9) < 8.5:
                return "cape" if any(k in n for k in ("cape", "cloak", "mantle", "coat", "tails", "shawl")) else "back"
            zm = (z0 + z1) / 2
            full = w >= 1.72 * max(self.torso_r(zm), self.torso_r(z0 + 0.25 * h), self.torso_r(z1 - 0.25 * h), 0.02)
            if full:
                if h < 0.12 and not any(k in n for k in ("apron", "bib")):
                    return "band"
                return "decal" if any(k in n.split("_") or k == n for k in ("apron", "bib")) or "apron" in n else "panel"
            if max(w, h) < 0.085 and any(k in n for k in STUD_WORDS):
                return "stud"
            return "decal"
        if on in ("arm_upper", "arm_lower", "leg_upper", "leg_lower"):
            return "limb"
        return "skip"

    def _units(self, p):
        """a part may be drawn in "head" units (x, z from the head centre, in head radii) or "torso" units (u -1..1 across
        the body, v 0 at the hip .. 1 at the shoulders) instead of metres"""
        u = p.get("units")
        if u == "head":
            return dict(p, pts=[(x * self.R, self.hz + z * self.R) for x, z in p["pts"]], units=None)
        if u == "torso":
            b = self.b
            z0 = b["hip_z"] if self.robe else min(q[1] for q in b["torso"])
            z1 = b["neck_z"]
            hw = max((q[0] for q in b["torso"] if q[1] >= z0), default=0.15)
            return dict(p, pts=[(x * hw, z0 + (z1 - z0) * v) for x, v in p["pts"]], units=None, fitted=True)
        return p

    def _pieces(self, parts):
        hair, glasses, beard = [], [], []
        todo = []
        for p in parts:
            p = self._units(p)
            k = self.classify(p)
            if k == "blob" and (self.sheet.get("hair") or {}).get("model") and any(w in p["name"].lower() for w in HAIR_BLOB):
                continue                                     # generated hair replaces the drawn buns, braids and tails
            p = dict(p, kind_=k)
            if k == "hair":
                hair.append(p)
            elif k == "glasses":
                glasses.append(p)
            elif k == "beard":
                beard.append(p)
            elif k != "skip":
                todo.append(p)
        self._has_hat = any(q["kind_"] in ("lathe", "crown") for q in todo)
        if hair or self.sheet.get("hair"):
            self._hair(hair)
        if beard or self.sheet.get("beard"):
            self._beard_from(beard)
        order = {"lathe": 0, "peak": 1, "crown": 1}
        for p in sorted(todo, key=lambda q: (order.get(q["kind_"], 5), q.get("layer", 0))):
            try:
                getattr(self, "_p_" + p["kind_"])(p)
            except Exception as ex:                          # one odd drawing must not stop the character
                print(f"[fig3d] {self.name}: part {p['name']} ({p['kind_']}) skipped: {ex}")
        if glasses:
            self._glasses(glasses)

    def _pk(self, p):
        c = p.get("color", "#888888")
        return p.get("mat") or kind_of(p["name"], c, self.skin), c, p.get("key")

    def _lift(self, p, base=9.0):
        return 0.0025 + 0.0016 * max(0.0, p.get("layer", base) - base)

    def _p_decal(self, p, back=False):
        on = p["on"].split(".")[0]
        if self.body and on != "head":
            return self.body.paint(p, "back" if back else "decal")
        kind, c, key = self._pk(p)
        head = on == "head"
        hairy = kind == "hair"
        lift = (0.010 if hairy else 0.0035 + 0.0012 * max(0.0, p.get("layer", 17.5) - 17.5)) if head else self._lift(p)
        bm = _flat_mesh(p["pts"], 0.012 if head else 0.018)
        if not bm.faces:
            bm.free()
            return
        self.wrap(bm, "head" if head else "torso", lift, back=back)
        par = "head" if head else ("skirt" if (self.robe and bbox(p["pts"])[3] < self.waist + 0.02) else "torso")
        bx0, bz0, bx1, bz1 = bbox(p["pts"])
        mark = head and not hairy and max(bx1 - bx0, bz1 - bz0) < 0.45 * self.R and p.get("layer", 17.5) < 21.4
        self.finish(p["name"], bm, par, kind, c, key, ink=False if mark else 0.004, shell=p.get("thick", 0.012 if hairy else (0.0012 if mark else 0.005)),
                    shadow=not mark)

    def _p_back(self, p):
        self._p_decal(p, back=True)

    def _p_vneck(self, p):
        """an open neck on a skinned body: {"as": "vneck", "vneck": [how low, half width at the top]} (torso units)"""
        if self.body:
            return self.body.paint(p, "vneck")

    def _p_band(self, p):
        if self.body:
            return self.body.paint(p, "band")
        kind, c, key = self._pk(p)
        x0, z0, x1, z1 = bbox(p["pts"])
        if p.get("z"):
            z0, z1 = p["z"]
        lift = self._lift(p) + 0.003
        n = max(2, int((z1 - z0) / 0.02) + 1)
        prof = [(self.torso_r(z1 + (z0 - z1) * i / n) + lift, z1 + (z0 - z1) * i / n) for i in range(n + 1)]
        bm = bmesh.new()
        _lathe(bm, prof, seg=56, sy=self.torso_sy((z0 + z1) / 2))
        par = "skirt" if (self.robe and z1 < self.waist + 0.02) else "torso"
        self.finish(p["name"], bm, par, kind, c, key, ink=0.004, shell=0.006)

    def _p_panel(self, p):
        """a garment drawn across the whole front (a vest, a coat, overalls): its front as drawn, and its back closed"""
        if self.body:
            return self.body.paint(p, "panel")
        self._p_decal(p)
        kind, c, key = self._pk(p)
        x0, z0, x1, z1 = bbox(p["pts"])
        lift = self._lift(p)
        n = max(2, int((z1 - z0) / 0.03) + 1)
        prof = [(self.torso_r(z1 + (z0 - z1) * i / n) + lift, z1 + (z0 - z1) * i / n) for i in range(n + 1)]
        bm = bmesh.new()
        _lathe(bm, prof, seg=28, a0=0.0, a1=math.pi, sy=self.torso_sy((z0 + z1) / 2))
        par = "skirt" if (self.robe and z1 < self.waist + 0.02) else "torso"
        self.finish(p["name"] + "_Back", bm, par, kind, c, key, ink=0.004, shell=0.005)

    def _p_stud(self, p):
        if self.body and p["on"].split(".")[0] != "head":
            return self.body.paint(p, "stud")
        kind, c, key = self._pk(p)
        x0, z0, x1, z1 = bbox(p["pts"])
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        head = p["on"].split(".")[0] == "head"
        r = (self.head_r(cz) if head else self.torso_r(cz)) + self._lift(p)
        sy = 1.0 if head else self.torso_sy(cz)
        y = -sy * math.sqrt(max(0.0, r * r - cx * cx))
        rr = max(0.008, min(x1 - x0, z1 - z0) / 2)
        bm = bmesh.new()
        _sphere(bm, (cx, y, cz), rr, scale=(max(1.0, (x1 - x0) / 2 / rr), 0.55, max(1.0, (z1 - z0) / 2 / rr)), seg=16, rings=10)
        par = "head" if head else ("skirt" if (self.robe and z1 < self.waist + 0.02) else "torso")
        self.finish(p["name"], bm, par, kind, c, key, ink=0.0035)

    def _p_lathe(self, p, arc=None, grow=1.0):
        kind, c, key = self._pk(p)
        x0, z0, x1, z1 = bbox(p["pts"])
        cx = 0.0
        n = max(6, int((z1 - z0) / 0.012))
        prof = []
        for i in range(n + 1):
            z = z1 - (z1 - z0) * i / n
            z = min(z1 - 1e-4, max(z0 + 1e-4, z))
            xs = _scan_x(p["pts"], z)
            r = max((abs(x - cx) for x in xs), default=0.0) * grow
            prof.append((max(r, 0.004), z))
        if arc:
            bm = bmesh.new()
            _lathe(bm, prof, seg=28, a0=math.radians(arc[0]), a1=math.radians(arc[1]))
            self.finish(p["name"], bm, "head", kind, c, key, ink=0.005, shell=0.010)
            return
        f = self.sheet.get("face", {})
        z_eye = self.hz + f.get("ez", 0.03) * self.R
        z_cut = self.hz + (f.get("bz", 0.30) + 0.14) * self.R
        over_face = z0 < z_eye and _interp(prof, z_eye) > 0.6 * self.R and p.get("face_window", True)
        if over_face and z1 > z_cut + 0.01:
            up = [q for q in prof if q[1] >= z_cut] + [(_interp(prof, z_cut), z_cut)]
            lo = [(_interp(prof, z_cut), z_cut)] + [q for q in prof if q[1] < z_cut]
            bm = bmesh.new()
            _lathe(bm, up, seg=48, cap_top=True)
            self.finish(p["name"], bm, "head", kind, c, key, ink=0.006, shell=0.008)
            bm = bmesh.new()
            _lathe(bm, lo, seg=40, a0=math.radians(-24), a1=math.radians(204))
            self.finish(p["name"] + "_Sides", bm, "head", kind, c, key, ink=0.006, shell=0.008)
        elif over_face:
            bm = bmesh.new()
            _lathe(bm, prof, seg=40, a0=math.radians(-24), a1=math.radians(204))
            self.finish(p["name"], bm, "head", kind, c, key, ink=0.006, shell=0.008)
        else:
            bm = bmesh.new()
            _lathe(bm, prof, seg=48, cap_top=True, cap_bottom=True)
            self.finish(p["name"], bm, "head", kind, c, key, ink=0.006)
        self.head_env.append(prof)

    def _p_peak(self, p):
        self._p_lathe(p, arc=(205, 335), grow=1.42)

    def _p_blob(self, p):
        kind, c, key = self._pk(p)
        x0, z0, x1, z1 = bbox(p["pts"])
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        rx, rz = max(0.012, (x1 - x0) / 2), max(0.012, (z1 - z0) / 2)
        ry = min(rx, rz) * 0.92
        R, hz = self.R, self.hz
        n = p["name"].lower()
        if "earring" in n:
            y = -0.07
        elif abs(cx) > 0.72 * R:
            y = 0.03
        elif cz > hz + 0.7 * R:
            y = 0.0
        elif cz < hz - 0.7 * R:
            y = 0.02 if abs(cx) > 0.3 * R else R * 0.55     # a braid over the shoulder / a ponytail down the back
        else:
            y = R * 0.92
            cx *= 0.4
        bm = bmesh.new()
        _sphere(bm, (cx, y, cz), 1.0, scale=(rx, ry, rz), seg=22, rings=12)
        if kind == "hair" and min(rx, rz) > 0.05:
            c0 = Vector((cx, y, cz))
            for v in bm.verts:
                d = v.co - c0
                v.co = c0 + d * (1.0 + 0.06 * math.cos(6 * math.atan2(d.z, d.y)))
        par = "head" if p["on"].startswith("head") else "torso"
        self.finish(p["name"], bm, par, kind, c, key, ink=0.005)

    def _p_limb(self, p):
        """a drawing on an arm or a leg: a ring round the limb where it was drawn (cuffs, hems, stripes, socks)"""
        if self.body:
            return self.body.paint(p, "limb")
        kind, c, key = self._pk(p)
        bone, sfx = p["on"].split(".")
        jn = {"arm_upper": "sh", "arm_lower": "el", "leg_upper": "hip", "leg_lower": "kn"}[bone] + "." + sfx
        nxt = {"sh": "el", "el": "wr", "hip": "kn", "kn": "an"}[jn.split(".")[0]] + "." + sfx
        b = self.b
        ra, rb = {"sh": (b["r_sh"], b["r_el"]), "el": (b["r_el"], b["r_wr"]), "hip": (b["r_hip"], b["r_kn"]), "kn": (b["r_kn"], b["r_an"])}[jn.split(".")[0]]
        a2, b2 = p.get("bone2d") or (None, None)
        if not a2:
            return
        A, B = Vector(a2), Vector(b2)
        ax = (B - A)
        L2d = ax.length
        ax.normalize()
        ds = [(Vector(q) - A).dot(ax) for q in p["pts"]]
        d0, d1 = max(-0.01, min(ds)), min(L2d + 0.02, max(ds))
        if d1 - d0 < 0.004:
            return
        L3 = (self.W[nxt] - self.W[jn]).length
        k = L3 / max(L2d, 1e-6)
        top = self.W[jn]
        lift = 0.004 + 0.001 * max(0.0, p.get("layer", 15) - 14.6)
        prof = []
        n = max(1, int((d1 - d0) * k / 0.02))
        for i in range(n + 1):
            d = (d0 + (d1 - d0) * i / n) * k
            t = max(0.0, min(1.0, d / L3))
            prof.append((ra + (rb - ra) * t + lift, top.z - d))
        bm = bmesh.new()
        _lathe(bm, prof, seg=20, cx=top.x, cy=top.y)
        self.finish(p["name"], bm, jn, kind, c, key, ink=0.004, shell=0.005)

    def _p_cape(self, p):
        kind, c, key = self._pk(p)
        x0, z0, x1, z1 = bbox(p["pts"])
        b = self.b
        top = min(z1, b["neck_z"] - 0.005)
        z0 = max(z0, 0.09)                                    # a cape or cloak stops above the ground
        hw_hem = min(max(abs(x0), abs(x1)), 0.50)
        nz, sx = b["neck_z"], b["sh_x"]
        zs = max(z0 + 0.2, nz - 0.26)
        prof = [(sx * 0.57, nz + 0.01), (sx, nz - 0.035), (sx + 0.055, nz - 0.10), (min(hw_hem, sx + 0.10), zs),
                (min(hw_hem, sx + 0.10) + (hw_hem - min(hw_hem, sx + 0.10)) * 0.55, (zs + z0) / 2), (hw_hem, z0)]
        half0, half1 = math.radians(46), math.radians(96)     # narrow at the shoulders: the arms hang clear in front of it
        lining = p.get("lining")
        for nm, off, kd, cc in ((p["name"], 0.0, kind, c), (p["name"] + "_Lining", -0.010, "fur" if lining else kind, lining or shade(c, 0.8))):
            bm = bmesh.new()
            seg = 64
            rows = []
            for k_, (r, z) in enumerate(prof):
                kk = k_ / (len(prof) - 1)
                half = half0 + (half1 - half0) * kk
                row = []
                for i in range(seg + 1):
                    th = math.pi / 2 - half + 2 * half * i / seg
                    rr = (r + off) * (1.0 + 0.05 * (kk ** 1.3) * math.cos(9 * (th - math.pi / 2)))
                    row.append(bm.verts.new((rr * math.cos(th), 0.065 + rr * math.sin(th) * 0.90, z)))
                rows.append(row)
            for k_ in range(len(rows) - 1):
                for i in range(seg):
                    bm.faces.new((rows[k_][i], rows[k_][i + 1], rows[k_ + 1][i + 1], rows[k_ + 1][i]))
            self.finish(nm, bm, "cape", kd, cc, key, ink=(off == 0.0), shell=0.010 if off == 0.0 else 0.0)

    def _p_crown(self, p):
        kind, c, key = self._pk(p)
        x0, z0, x1, z1 = bbox(p["pts"])
        R, hz = self.R, self.hz
        r0 = min((x1 - x0) / 2 * 0.86, R * 0.62)
        zb = hz + math.sqrt(max(0.0, (R * 1.055) ** 2 - r0 * r0)) - 0.012
        if getattr(self, "_hair_top", None):                 # generated hair: the crown rests on the hair, biting in a little
            zb = max(zb, self._hair_top(r0) - 0.03 * R)
        hgt = max(0.10, (z1 - z0))
        band, h = hgt * 0.30, hgt * 0.70
        pts_n = int(p.get("points", 5))
        n = 120
        bm = bmesh.new()
        lo, mid, hi = [], [], []
        for i in range(n):
            th = math.tau * i / n
            tri = abs(((i * pts_n / n) % 1.0) * 2 - 1)
            zz = zb + band + h * (1 - tri) ** 1.15
            flare = 1.0 + 0.16 * (zz - zb) / (band + h)
            lo.append(bm.verts.new((r0 * math.cos(th), r0 * math.sin(th), zb)))
            mid.append(bm.verts.new((r0 * 1.03 * math.cos(th), r0 * 1.03 * math.sin(th), zb + band * 0.6)))
            hi.append(bm.verts.new((r0 * flare * math.cos(th), r0 * flare * math.sin(th), zz)))
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], mid[j], mid[i]))
            bm.faces.new((mid[i], mid[j], hi[j], hi[i]))
        self.finish(p["name"], bm, "head", "metal", c, key, shell=0.012, smooth=False)
        bb, bg = bmesh.new(), bmesh.new()
        for k_ in range(pts_n):
            th = math.tau * (k_ + 0.5) / pts_n
            _sphere(bb, (r0 * 1.16 * math.cos(th), r0 * 1.16 * math.sin(th), zb + band + h + 0.012), 0.017, seg=14, rings=8)
            th2 = math.tau * k_ / pts_n
            _sphere(bg, (r0 * 1.05 * math.cos(th2), r0 * 1.05 * math.sin(th2), zb + band * 0.55), 0.015, scale=(1, 1, 1.35), seg=14, rings=8)
        self.finish(p["name"] + "_Ball", bb, "head", "metal", c, key, ink=0.005)
        self.finish(p["name"] + "_Gem", bg, "head", "gem", p.get("gem", "#C8302C"), None, ink=0.004)
        self.head_env.append([(r0 * 1.05, zb), (r0 * 1.2, zb + band + h)])

    def _p_collar_fur(self, p):
        kind, c, key = self._pk(p)
        x0, z0, x1, z1 = bbox(p["pts"])
        cz = (z0 + z1) / 2 + 0.01
        a_x = max(0.11, (x1 - x0) / 2 * 0.60)        # close to the neck: a raised arm passes outside it
        a_y, rm = a_x * 0.80, max(0.035, (z1 - z0) * 0.32)
        bm = bmesh.new()
        seg, ring = 56, 12
        vs = []
        for i in range(seg):
            th = math.tau * i / seg
            drop = 0.035 * max(0.0, -math.sin(th))
            row = []
            for j in range(ring):
                ph = math.tau * j / ring
                rr = 1.0 + (rm / a_x) * math.cos(ph)
                row.append(bm.verts.new((a_x * rr * math.cos(th), a_y * rr * math.sin(th), cz - drop + rm * 0.85 * math.sin(ph))))
            vs.append(row)
        for i in range(seg):
            for j in range(ring):
                bm.faces.new((vs[i][j], vs[(i + 1) % seg][j], vs[(i + 1) % seg][(j + 1) % ring], vs[i][(j + 1) % ring]))
        self.finish(p["name"], bm, "torso", "fur", c, key)
        if p.get("spots", True):
            bm = bmesh.new()
            for i in range(12):
                th = math.tau * (i + 0.5) / 12
                drop = 0.035 * max(0.0, -math.sin(th))
                for ph in ((0.35, 0.9) if i % 2 else (0.75,)):
                    rr = 1.0 + (rm / a_x) * math.cos(ph) * 1.04
                    _sphere(bm, (a_x * rr * math.cos(th), a_y * rr * math.sin(th), cz - drop + rm * 0.9 * math.sin(ph)), 0.011, scale=(1, 1, 1.8), seg=10, rings=6)
            self.finish(p["name"] + "_Spots", bm, "torso", "plain", "#2B1B1B", None, ink=False)

    def _glasses(self, ps):
        c = ps[0].get("color", "#3A2A20")
        f = dict(ex=0.32, ez=0.03)
        f.update(self.sheet.get("face", {}))
        rims = [p for p in ps if "rim" in p["name"].lower()]
        rr = 0.21 * self.R
        if rims:
            x0, z0, x1, z1 = bbox(rims[0]["pts"])
            rr = max(0.03, min(x1 - x0, z1 - z0) / 2)
        bm = bmesh.new()
        cs = []
        for s in (1, -1):
            cpt = self._on_head(s * f["ex"], f["ez"], 0.022)
            cs.append(cpt)
            nrm = (cpt - Vector((0, 0, self.hz))).normalized()
            rot = Vector((0, 0, 1)).rotation_difference(nrm).to_matrix().to_4x4()
            bmesh.ops.create_cone(bm, cap_ends=False, segments=28, radius1=rr, radius2=rr, depth=0.008, matrix=Matrix.Translation(cpt) @ rot)
            _tube(bm, cpt + Vector((s * rr, 0, 0)), Vector((s * self.R * 1.0, 0.0, cpt.z)), 0.005, 0.005, seg=8, caps=False)
        _tube(bm, cs[0] + Vector((-rr, 0, 0)), cs[1] + Vector((rr, 0, 0)), 0.005, 0.005, seg=8, caps=False)
        self.finish("Glasses", bm, "head", "metal", c, ps[0].get("key"), ink=0.004, shell=0.006)

    HAIR_STYLES = {   # named starting points for a sheet's "hair": {"style": ...}; any key can be given on top
        "short": dict(fringe=0.55, side=0.25, back=-0.40, vol=1.10, locks=18),
        "side_part": dict(part=-0.5, fringe=None, side=0.20, back=-0.40, vol=1.11, locks=18),
        "curtains": dict(part=0.0, fringe=None, side=-0.55, back=-0.60, vol=1.13, locks=20),
        "bob": dict(part=-0.35, fringe=None, side=-0.80, back=-0.85, vol=1.15, locks=20),
        "fringe_bob": dict(fringe=0.42, side=-0.85, back=-0.90, vol=1.15, locks=22),
        "long": dict(part=0.0, fringe=None, side=-1.30, back=-1.60, vol=1.16, locks=22),
        "long_fringe": dict(fringe=0.42, side=-1.30, back=-1.60, vol=1.16, locks=22),
        "swept_back": dict(fringe=None, part=0.0, side=0.30, back=-0.45, vol=1.10, locks=16, sweep=1.0),
        "ring": dict(crown=False, side=-0.35, back=-0.40, vol=1.08, locks=16),
        "back_only": dict(front=False, side=-0.50, back=-0.60, vol=1.10, locks=18),
    }

    def _hair_measure(self, ps):
        """read a 2D hair design (its flat outlines) into the numbers of a sculpted style"""
        R, hz = self.R, self.hz
        f = self.sheet.get("face", {})
        brow = f.get("bz", 0.30) + 0.145
        fronts = [[(x / R, (z - hz) / R) for x, z in q["pts"]] for q in ps if q.get("layer", 20.5) >= 16.4]
        backs = [[(x / R, (z - hz) / R) for x, z in q["pts"]] for q in ps if q.get("layer", 20.5) < 16.4]
        allp = [q for pl in fronts + backs for q in pl]
        if not allp:
            return dict(self.HAIR_STYLES["short"])

        def col(polys, x):
            zs = []
            for pl in polys:
                zs += _scan_z(pl, x)
            return (min(zs), max(zs)) if len(zs) >= 2 else None

        c0 = col(fronts, 0.0) or col(fronts, 0.06) or col(fronts, -0.06)
        cb = col(backs, 0.0)
        crown = bool((c0 and c0[1] >= 0.80) or (cb and cb[1] >= 0.85))
        front = bool(c0 and c0[1] >= 0.80)
        st = dict(crown=crown, front=front)
        xs = [k / 10.0 for k in range(-6, 7)]
        lows = [(x, col(fronts, x)) for x in xs]
        lows = [(x, c[0]) for x, c in lows if c and c[1] >= 0.6]
        if front and lows:
            mid = min((abs(x), z) for x, z in lows)[1]
            hi_x, hi_z = max(lows, key=lambda q: q[1])
            if mid >= 0.60 or hi_z - min(z for _x, z in lows if abs(_x) <= 0.35) > 0.22:
                st["fringe"] = None                                 # the forehead shows: a parting or swept hair
                st["part"] = max(-0.8, min(0.8, hi_x / 0.55)) if abs(hi_x) >= 0.15 else 0.0
            else:
                st["fringe"] = max(brow, min(0.62, mid))
        sides = [c for c in (col(fronts + backs, sx_) for sx_ in (-0.93, 0.93, -0.84, 0.84)) if c]
        side = min((c[0] for c in sides), default=0.25)
        low = min(q[1] for q in allp)
        st["side"] = max(-2.3, min(0.40, side))
        st["back"] = max(-2.5, min(-0.38, st["side"] - 0.05, low if low < -0.9 else 0.0))
        if not crown:
            st["ring_top"] = max(0.15, min(0.62, max((c[1] for c in sides), default=0.45)))
        st["vol"] = max(1.09, min(1.22, max(abs(q[0]) for q in allp)))
        st["locks"] = 22 if st["side"] < -0.6 else 18
        return st

    def _hair_model(self, spec):
        """Generated hair from library/hair/<model>.npz (made with bake_hair.py from an image-to-3D model): a sheet's
        "hair": {"model": "female_layered_locks", "color": "#7E4526", "scale": 1.0}. The asset is stored for a head of
        radius 1 with its fringe already above the brow line; here it is sized to the head and given the hair look."""
        import numpy as np
        from . import core
        f = core.PROJECT / "library" / "hair" / f"{spec['model']}.npz"
        if not f.exists():
            raise FileNotFoundError(f"{self.name}: hair model '{spec['model']}' is not in library/hair")
        d = np.load(str(f))
        R, hz = self.R, self.hz
        V = d["v"].astype(float) * (R * float(spec.get("scale", 1.0)))
        rp = np.maximum(np.linalg.norm(V, axis=1), 1e-9)
        U = V / rp[:, None]
        rho = np.full(len(V), R)
        if self._head_bvh is not None:                       # the sculpt's own head is not a ball: the hair keeps its height above the
            c0 = Vector((0, 0, hz))                          # real surface, so it neither floats nor sinks in
            # the surface is measured on a grid of directions and read off for every point of the hair
            NE, NA = 61, 120
            els, azs = np.linspace(-math.pi / 2, math.pi / 2, NE), np.linspace(-math.pi, math.pi, NA + 1)
            G = np.full((NE, NA + 1), R)
            for i_, el in enumerate(els):
                for j_, az in enumerate(azs):
                    u_ = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
                    hit, _n, _i, dist = self._head_bvh.ray_cast(c0, u_)
                    if hit is not None and dist < 1.35 * R:
                        G[i_, j_] = dist
            el_v, az_v = np.arcsin(np.clip(U[:, 2], -1, 1)), np.arctan2(U[:, 0], -U[:, 1])
            fi, fj = (el_v + math.pi / 2) / math.pi * (NE - 1), (az_v + math.pi) / math.tau * NA
            i0, j0 = np.clip(fi.astype(int), 0, NE - 2), np.clip(fj.astype(int), 0, NA - 1)
            ti, tj = fi - i0, fj - j0
            rho = (G[i0, j0] * (1 - ti) * (1 - tj) + G[i0 + 1, j0] * ti * (1 - tj) + G[i0, j0 + 1] * (1 - ti) * tj + G[i0 + 1, j0 + 1] * ti * tj)
            fade = np.clip((np.degrees(el_v) + 60.0) / 30.0, 0.0, 1.0)      # below the head there is only the neck: the ball's size there
            rho = R + (rho - R) * fade
        thick = rp - R                                       # how far the hair stands off the head
        if self._hat_seat is not None:                       # under a worn hat the hair lies flat, so the hat can come down onto the head
            zrel = U[:, 2] * (rho + thick) / R
            t_ = np.clip((zrel - (self._hat_seat - 0.16)) / 0.16, 0.0, 1.0)
            t_ = t_ * t_ * (3 - 2 * t_)
            thick = thick * (1 - t_) + np.minimum(thick, 0.045 * R) * t_
        V = U * (rho + thick)[:, None]
        V[:, 2] += hz
        me = bpy.data.meshes.new("gen_hair")
        me.from_pydata(V.tolist(), [], d["f"].tolist())
        me.attributes.new("gen_grad", "FLOAT", "POINT").data.foreach_set("value", d["g"].astype("float32"))
        bm = bmesh.new()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        ob = self.finish("Hair", bm, "head", "hair", spec.get("color") or "#6B4428", ink=False)
        ob.data.materials[0] = hair_look(ob.data.materials[0].copy(), R)
        self.hide("Ear.*")                                    # this hair covers the sides of the head

        def top(r0, V=V):                                     # how high the hair stands under a ring of radius r0 (for a crown)
            hr = np.hypot(V[:, 0], V[:, 1])
            ring = (hr > 0.7 * r0) & (hr < 1.1 * r0) & (V[:, 2] > hz)
            if ring.sum() < 50:
                return -1e9
            bi = ((np.arctan2(V[ring, 1], V[ring, 0]) + math.pi) / math.tau * 24).astype(int) % 24
            tops = np.full(24, -1e9)
            np.maximum.at(tops, bi, V[ring, 2])
            return float(np.percentile(tops[tops > -1e8], 60))
        self._hair_top = top

    def _hair(self, ps):
        """Sculpted hair: one thick cap carved into locks with rounded tips. Its shape comes from the sheet's "hair" entry
        ({"style": "bob", ...}) or, without one, is read from the character's flat hair drawings."""
        R, hz = self.R, self.hz
        spec = dict(self.sheet.get("hair") or {})
        if spec.get("model"):
            return self._hair_model(spec)
        st = self._hair_measure(ps) if ps else {}
        if spec.get("style"):
            st = dict(self.HAIR_STYLES[spec["style"]])
        st.update({k: v for k, v in spec.items() if k not in ("style", "color")})
        if not st:
            return
        big = max(ps, key=lambda q: (bbox(q["pts"])[2] - bbox(q["pts"])[0]) * (bbox(q["pts"])[3] - bbox(q["pts"])[1])) if ps else {}
        color, key = spec.get("color") or big.get("color", "#6B4428"), big.get("key")
        f = self.sheet.get("face", {})
        brow = f.get("bz", 0.30) + 0.145
        part, fringe = st.get("part", 0.0), st.get("fringe", 0.5)
        side, back = st.get("side", 0.25), st.get("back", -0.4)
        crown, front = st.get("crown", True), st.get("front", True)
        vol, locks, sweep = st.get("vol", 1.12), int(st.get("locks", 20)), st.get("sweep", 0.0)
        if getattr(self, "_has_hat", False):                 # under a hat the hair lies close and the hat covers the top
            vol = min(vol, 1.07)
        if fringe is not None:
            fringe = max(fringe, brow)
        smooth = lambda x: (lambda v: v * v * (3 - 2 * v))(max(0.0, min(1.0, x)))
        nphi, ns = 220, 26
        p0 = math.radians(part * 55)
        bm = bmesh.new()
        rows = []
        for i in range(nphi):
            phi = -math.pi + math.tau * i / nphi
            rel = math.atan2(math.sin(phi - p0), math.cos(phi - p0))
            a_ = abs(phi)
            tip = 0.5 + 0.5 * math.cos(locks * rel)
            z_hi = 1.0
            if a_ <= math.radians(78):
                if not front or not crown:
                    if a_ < math.radians(58):
                        rows.append(None)                    # no hair over the face here (a bald crown, or hair only behind)
                        continue
                    z_lo = side
                    z_hi = st.get("ring_top", 0.45) if not crown else 1.0
                elif fringe is None:
                    top = 0.72 if side < 0.1 else 0.62
                    z_lo = top + (side - top) * smooth(abs(rel) / math.radians(74)) ** (1.25 - 0.5 * sweep)
                    z_lo = max(z_lo, brow if a_ < math.radians(40) else -9.0)
                else:
                    z_lo = fringe + (side - fringe) * smooth((a_ - math.radians(46)) / math.radians(32))
            else:
                z_lo = side + (back - side) * smooth((a_ - math.radians(78)) / math.radians(50))
                if not crown:
                    z_hi = st.get("ring_top", 0.45)
            z_lo -= 0.055 * tip * (0.5 if z_hi < 1.0 else 1.0)
            row = []
            for j in range(ns + 1):
                sj = j / ns
                z = z_hi + (z_lo - z_hi) * sj
                flow = 0.5 + 0.5 * math.cos(locks * (rel + 0.10 * sj * math.copysign(1.0, rel)))
                bulge = 1.0 + 0.045 * (flow ** 0.7) * smooth(sj * 2.2) + 0.05 * smooth(sj) * (1 - smooth((sj - 0.8) / 0.2))
                if z >= -0.82:
                    rh = math.sqrt(max(0.0, 1.0 - max(-1.0, min(1.0, z)) ** 2))
                else:
                    rh = 0.57 + 0.06 * (-0.82 - z)
                if z < 0.0 and z_lo < -0.95:                 # long hair falls straight from the widest point of the head
                    rh = max(rh, 0.93 - 0.05 * min(1.0, -z))
                rr = rh * vol * bulge
                zz = z * (1.0 + (vol - 1.0) * 0.5 if z > 0 else 1.0)
                row.append(bm.verts.new((math.sin(phi) * rr * R, -math.cos(phi) * rr * R, hz + zz * R)))
            rows.append(row)
        for i in range(nphi):
            r0, r1 = rows[i], rows[(i + 1) % nphi]
            if r0 is None or r1 is None:
                continue
            for j in range(ns):
                try:
                    bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))
                except ValueError:
                    pass
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        self.finish("Hair", bm, "head", "hair", color, key, ink=0.0065, shell=0.030 * R / 0.27)
        self.head_env.append([(vol * R * 0.2, hz + (1.0 + (vol - 1.0) * 0.5) * R), (vol * R * 1.03, hz), (vol * R * 0.62, hz - 0.8 * R)])

    BEARD_STYLES = {  # named starting points for a sheet's "beard": {"style": ...}
        "stubble": dict(full=True, length=0.04, thick=0.35, moustache=False),
        "short": dict(full=True, length=0.16, thick=0.8, moustache=True),
        "full": dict(full=True, length=0.40, thick=1.0, moustache=True),
        "long": dict(full=True, length=0.75, thick=1.1, moustache=True),
        "goatee": dict(full=False, length=0.30, thick=0.9, moustache=True),
        "moustache": dict(none=True, moustache=True),
    }

    def _beard_model(self, spec, color):
        """Generated beard or moustache from library/hair/<model>.npz (made with bake_hair.py): a sheet's
        "beard": {"model": "facial_beard_short", "color": "#4A3122"}; model may be a list (a beard and a moustache).
        The piece is stored for a head of radius 1 with the heights of its own features; here it is fitted to this
        character's nose and mouth (seat_face), sized to the head and given the hair look. It replaces the drawn beard and
        moustache. "drop" (head radii, 0) moves the mouth line it aims at; "scale" (1.0) sizes it."""
        import json
        import numpy as np
        from . import core
        lib = core.PROJECT / "library" / "hair"
        meta = json.loads((lib / "index.json").read_text(encoding="utf-8")).get("facial", {})
        R, hz = self.R, self.hz
        models = spec["model"] if isinstance(spec["model"], (list, tuple)) else [spec["model"]]
        # the ear's space, from this character's own ear (built in _body; still there when a library hairstyle hides it,
        # and such hair leaves the opening for it), else from the size and place _body gives ears
        eo = (self.parts.get("Ear.L") or [None])[0]
        if eo is not None:
            P = np.array([v.co[:] for v in eo.data.vertices]) - np.array([0.0, 0.0, hz])
            lo, hi = P.min(axis=0), P.max(axis=0)
            c, hy, hzz = (lo + hi) / 2, (hi[1] - lo[1]) / 2, (hi[2] - lo[2]) / 2
        else:
            c, hy, hzz = np.array([0.99 * R, 0.01, -0.06 * R]), 0.128 * R, 0.16 * R
        rc = float(np.linalg.norm(c))
        EAR_GAP = 4.0                                         # clear skin round the ear, degrees
        ear = dict(el=math.degrees(math.asin(c[2] / rc)), az=math.degrees(math.atan2(abs(c[0]), -c[1])),
                   h_el=math.degrees(math.asin(min(0.9, hzz / rc))) + EAR_GAP, h_az=math.degrees(math.atan2(hy, rc)) + EAR_GAP)
        for i, name in enumerate(models):
            if name not in meta or not (lib / f"{name}.npz").exists():
                raise FileNotFoundError(f"{self.name}: beard model '{name}' is not in library/hair")
            d = np.load(str(lib / f"{name}.npz"))
            V = d["v"].astype(float)
            r = np.maximum(np.linalg.norm(V, axis=1), 1e-9)
            el = np.degrees(np.arcsin(np.clip(V[:, 2] / r, -1, 1)))
            az = np.degrees(np.arctan2(V[:, 0], -V[:, 1]))
            face = dict(self.sheet.get("face", {}))
            face["mz"] = float(face.get("mz", -0.385)) + float(spec.get("drop", 0.0))
            keep = ~(np.abs(az) > 112.0)[d["f"]].all(axis=1)          # nothing of a beard behind the ears
            el, az, rp, gone = seat_face(el, az, r, meta[name]["seat"], face, ear=ear)
            keep &= ~gone[d["f"]].any(axis=1)                         # nothing in the ear's space
            el, azr = np.radians(el), np.radians(az)
            rr = rp * R * float(spec.get("scale", 1.0))
            V = np.stack([np.sin(azr) * np.cos(el) * rr, -np.cos(azr) * np.cos(el) * rr, np.sin(el) * rr + hz], axis=1)
            me = bpy.data.meshes.new("gen_beard")
            me.from_pydata(V.tolist(), [], d["f"][keep].tolist())
            me.attributes.new("gen_grad", "FLOAT", "POINT").data.foreach_set("value", d["g"].astype("float32"))
            bm = bmesh.new()
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
            ob = self.finish("Beard" if i == 0 else f"Beard_{i}", bm, "head", "hair", color, ink=False)
            ob.data.materials[0] = hair_look(ob.data.materials[0].copy(), R)

    def _beard_from(self, ps):
        """Sculpted beard and moustache: real volume under the face, the mouth left free. From the sheet's "beard" entry
        ({"style": "full", ...}) or read from the character's flat beard / moustache drawings."""
        R, hz = self.R, self.hz
        spec = dict(self.sheet.get("beard") or {})
        if spec.get("model"):
            return self._beard_model(spec, spec.get("color") or (ps or [{}])[0].get("color", "#6B4428"))
        st = {}
        beards = [q for q in ps if "must" not in q["name"].lower()]
        mous = [q for q in ps if "must" in q["name"].lower()]
        f = dict(mz=-0.385)
        f.update(self.sheet.get("face", {}))
        if beards:
            pts = [((x) / R, (z - hz) / R) for q in beards for x, z in q["pts"]]
            zmin, zmax, wmax = min(q[1] for q in pts), max(q[1] for q in pts), max(abs(q[0]) for q in pts)
            st = dict(full=wmax >= 0.72, length=max(0.06, min(1.0, -0.97 - zmin)), thick=1.0, moustache=bool(mous) or zmax > f["mz"] + 0.12)
        elif mous:
            st = dict(none=True, moustache=True)
        if spec.get("style"):
            st = dict(self.BEARD_STYLES[spec["style"]])
        st.update({k: v for k, v in spec.items() if k not in ("style", "color")})
        if not st:
            return
        src = (beards or mous or [{}])[0]
        color, key = spec.get("color") or src.get("color", "#6B4428"), src.get("key")
        mz = f["mz"]
        smooth = lambda x: (lambda v: v * v * (3 - 2 * v))(max(0.0, min(1.0, x)))
        if not st.get("none"):
            length, thick = st.get("length", 0.3), st.get("thick", 1.0)
            span = math.radians(104 if st.get("full", True) else 58)
            nphi, nt = 120, 16
            bm = bmesh.new()
            rows = []
            for i in range(nphi + 1):
                phi = -span + 2 * span * i / nphi
                k = abs(phi) / span
                top0 = mz - 0.13
                z_up = top0 + (0.10 - top0) * smooth(k) ** 1.6 if st.get("full", True) else top0 - 0.02 * k
                z_dn = (-1.0 - length * math.cos(phi * 0.5) ** 2.2) + (0.02 + 1.0 + length) * smooth((k - 0.55) / 0.45) * 0.86
                if not st.get("full", True):
                    z_dn = -1.0 - length * (1 - k * k)
                    z_up = min(z_up, z_dn + 0.9)
                lobe = 0.5 + 0.5 * math.cos(9 * phi)
                row = []
                for jx in range(nt + 1):
                    t = jx / nt
                    z = z_up + (z_dn - z_up) * t
                    th = ((0.05 + 0.20 * (1 - k) ** 0.8) * math.sin(math.pi * min(1.0, t * 1.15)) ** 0.7 + 0.03 * lobe * math.sin(math.pi * t)) * thick
                    zc = max(-0.93, min(1.0, z))
                    rh = math.sqrt(max(0.0, 1.0 - zc * zc))
                    if z < -0.93:
                        rh = rh * max(0.0, 1.0 - (-0.93 - z) / (length + 0.12)) ** 0.6
                    rr = rh + th
                    row.append(bm.verts.new((math.sin(phi) * rr * R, -math.cos(phi) * rr * R, hz + z * R)))
                rows.append(row)
            for i in range(nphi):
                for jx in range(nt):
                    bm.faces.new((rows[i][jx], rows[i + 1][jx], rows[i + 1][jx + 1], rows[i][jx + 1]))
            self.finish("Beard", bm, "head", "hair", color, key, ink=0.0065, shell=0.022)
        if st.get("moustache"):
            wide = 1.0
            if mous:
                x0, _z0, x1, _z1 = bbox(mous[0]["pts"])
                wide = max(0.8, min(1.7, (x1 - x0) / (0.62 * R)))
                color = spec.get("color") or mous[0].get("color", color)
            bm = bmesh.new()
            for sd in (1, -1):
                for dx, dz, rx, rz in ((0.10, 0.0, 0.115, 0.062), (0.215, -0.022, 0.085, 0.050)) + (((0.31, 0.01, 0.07, 0.045),) if wide > 1.25 else ()):
                    c = self._on_head(sd * dx * wide, mz + 0.105 + dz, 0.020)
                    _sphere(bm, c, 1.0, scale=(rx * R * wide ** 0.5, 0.055 * R, rz * R), seg=18, rings=10)
            self.finish("Mustache", bm, "head", "hair", color, (mous[0].get("key") if mous else key), ink=0.005)

    def attach(self, spec):
        """A ready-made model from the asset store worn on the figure: {"name": "Hat", "file": "bk:<asset id>", "on": "head",
        "fit": "hat" | "necklace", "scale": 1.0, "lift": 0.0, "back": 0.0, "tilt": 0.0}. A hat is sized to the head and set on
        top of it. A necklace is sized to the neck, hung from the back of it, and kept on top of the body's surface, so it
        lies on the chest and follows it."""
        from . import body3d
        path = body3d.library_file(spec["file"][3:])
        with bpy.data.libraries.load(str(path)) as (src, dst):
            dst.objects = list(src.objects)
        obs = [o for o in dst.objects if o is not None]
        for o in obs:
            self.coll.objects.link(o)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new(f"{self.name}_{spec['name']}")     # everything the asset shows, as one plain mesh
        bm = bmesh.new()
        for inst in dg.object_instances:
            o = inst.object
            if o.type != "MESH" or (inst.parent.original if inst.is_instance else o.original) not in obs:
                continue
            tmp = bpy.data.meshes.new_from_object(o)
            tmp.transform(inst.matrix_world)
            base = len(me.materials)
            for mt in tmp.materials:
                me.materials.append(mt)
            n0 = len(bm.faces)
            bm.from_mesh(tmp)
            bm.faces.ensure_lookup_table()
            for f_ in bm.faces[n0:]:
                f_.material_index += base
            bpy.data.meshes.remove(tmp)
        bm.to_mesh(me)
        bm.free()
        for o in obs:
            bpy.data.objects.remove(o)
        import numpy as np
        V = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", V)
        V = V.reshape(-1, 3)
        lo, hi = V.min(axis=0), V.max(axis=0)
        b, R = self.b, self.R
        on = spec.get("on", "head")
        if spec.get("fit") == "necklace" and self.body and self.body.ob:
            return self._necklace(me, V, spec)
        if spec.get("fit") == "necklace":
            rn = (self.body.neck_r / 1.30) if (self.body and hasattr(self.body, "neck_r")) else 0.05
            k = (2 * rn * 2.1) / max(1e-6, hi[0] - lo[0]) * float(spec.get("scale", 1.0))
            c = np.array([(lo[0] + hi[0]) / 2, hi[1], hi[2]])        # the top of the loop, at the back
            to = np.array([0.0, rn * 0.95 + float(spec.get("back", 0.0)), b["neck_z"] + 0.035 + float(spec.get("lift", 0.0))])
            on = "torso"
        else:
            # a hat goes on by its crown: the crown is made as wide as the head (with the hair lying flat under it) is at the
            # height where the hat's edge sits, and the hat is set down to that height
            seat = self._hat_seat if self._hat_seat is not None else 0.60
            cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
            top = V[:, 2] > lo[2] + 0.62 * (hi[2] - lo[2])
            r_crown = float(np.percentile(np.hypot(V[top, 0] - cx, V[top, 1] - cy), 85)) * 0.92 if top.sum() > 20 else (hi[0] - lo[0]) * 0.3
            r_head = math.sqrt(max(0.05, 1.0 - seat * seat)) * R + 0.05 * R
            k = r_head / max(1e-6, r_crown) * float(spec.get("scale", 1.0))
            c = np.array([cx, cy, lo[2]])                    # the middle of its lower edge
            to = np.array([0.0, float(spec.get("back", 0.0)), self.hz + seat * R - 0.02 * R + float(spec.get("lift", 0.0))])
        V = (V - c) * k
        if spec.get("tilt"):
            a_ = math.radians(float(spec["tilt"]))
            y_, z_ = V[:, 1].copy(), V[:, 2].copy()
            V[:, 1], V[:, 2] = y_ * math.cos(a_) - z_ * math.sin(a_), y_ * math.sin(a_) + z_ * math.cos(a_)
        V += to
        me.vertices.foreach_set("co", V.ravel())
        me.update()
        ob = bpy.data.objects.new(f"{self.name}.{spec['name']}", me)
        self.coll.objects.link(ob)
        ob.parent = self.J[on]
        ob.location = -self.W[on]
        ob["c3_part"], ob["c3_kind"], ob["c3_color"], ob["c3_key"] = spec["name"], "plain", "", ""
        if spec.get("fit") == "necklace" and self.body and self.body.ob:
            sw = ob.modifiers.new("lie_on_body", "SHRINKWRAP")
            sw.target, sw.wrap_method, sw.wrap_mode, sw.offset = self.body.ob, "NEAREST_SURFACEPOINT", "OUTSIDE", 0.006
        self.parts.setdefault(spec["name"], []).append(ob)
        return ob

    def _necklace(self, me, V, spec):
        """A chain worn the way a person wears one: it is laid along a line on the body itself, round the base of the neck
        at the back, over the shoulders and down to a low point on the chest, and the pendant hangs from that point.
        The asset's chain is a loop of links: every link keeps its shape and size relative to the others, and is moved from
        its place on the asset's loop to the same place along the body's line. "drop": how low the chain reaches (torso
        units, 1 = the neck); "lift": how far it stands off the skin."""
        import numpy as np
        from mathutils.bvhtree import BVHTree
        b = self.b
        # pieces of the asset: many small links, the pendant, and sometimes a thin guide wire that runs the whole loop
        nV = len(V)
        E = np.empty(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", E)
        E = E.reshape(-1, 2)
        lab = np.arange(nV)
        while True:
            new = lab.copy()
            np.minimum.at(new, E[:, 0], lab[E[:, 1]])
            np.minimum.at(new, E[:, 1], lab[E[:, 0]])
            new = new[new]
            if np.array_equal(new, lab):
                break
            lab = new
        c = V.mean(axis=0)
        w_, e_ = np.linalg.eigh(np.cov((V - c).T))
        n0, e1, e2 = e_[:, 0], e_[:, 2], e_[:, 1]               # the loop's plane: its normal, and two directions in it
        phi = np.arctan2((V - c) @ e2, (V - c) @ e1)
        ids, inv, cnt = np.unique(lab, return_inverse=True, return_counts=True)
        span = np.zeros(len(ids))
        for i_ in range(len(ids)):
            ph = np.sort(phi[inv == i_])
            gaps = np.diff(np.concatenate([ph, ph[:1] + math.tau]))
            span[i_] = math.tau - gaps.max()                 # how much of the loop one piece covers
        med = float(np.median(cnt))
        wire = (span > math.radians(120))[inv]               # a guide wire: left out
        size = np.array([np.ptp(V[inv == i_], axis=0).max() for i_ in range(len(ids))])
        big = (size > 2.2 * np.median(size)) & (span <= math.radians(120))
        if big.any():                                        # the pendant is the biggest of these and what hangs right by it; a stray
            cents = np.array([V[inv == i_].mean(axis=0) for i_ in range(len(ids))])      # strand elsewhere is left out
            main = int(np.argmax(np.where(big, cnt, 0)))
            near = np.linalg.norm(cents - cents[main], axis=1) < 1.5 * size[main]
            wire = wire | (big & ~near)[inv]
            big = big & near
        pend = big[inv]
        link = ~wire & ~pend
        # the asset's own loop: how far out and how far off its plane the links lie, by angle round it
        NB = 180
        bi_ = ((phi + math.pi) / math.tau * NB).astype(int) % NB
        rad, off = np.hypot((V - c) @ e1, (V - c) @ e2), (V - c) @ n0
        rc, oc = np.zeros(NB), np.zeros(NB)
        for k_ in range(NB):
            m_ = link & (bi_ == k_)
            rc[k_], oc[k_] = (np.median(rad[m_]), np.median(off[m_])) if m_.any() else (np.nan, np.nan)
        for arr in (rc, oc):
            bad = np.isnan(arr)
            arr[bad] = np.interp(np.nonzero(bad)[0], np.nonzero(~bad)[0], arr[~bad], period=NB)
        cen = lambda a_: c + np.outer(np.interp(a_, np.linspace(-math.pi, math.pi, NB, endpoint=False) + math.pi / NB, rc, period=math.tau), [1, 1, 1]) * (
            np.outer(np.cos(a_), e1) + np.outer(np.sin(a_), e2)) + np.outer(np.interp(a_, np.linspace(-math.pi, math.pi, NB, endpoint=False) + math.pi / NB, oc, period=math.tau), n0)
        aa = np.linspace(-math.pi, math.pi, 721)
        L0 = float(np.linalg.norm(np.diff(cen(aa), axis=0), axis=1).sum())
        phi0 = float(np.arctan2(np.sin(phi[pend]).mean(), np.cos(phi[pend]).mean())) if pend.any() else float(aa[int(np.argmin(cen(aa)[:, 2]))])
        # the line on the body
        bo = self.body.ob.data
        P = np.empty(len(bo.vertices) * 3)
        bo.vertices.foreach_get("co", P)
        tree = BVHTree.FromPolygons([Vector(q_) for q_ in P.reshape(-1, 3)], [tuple(pl.vertices) for pl in bo.polygons])
        z0t = b["hip_z"] if self.robe else min(q_[1] for q_ in b["torso"])
        zf = z0t + (b["neck_z"] - z0t) * float(spec.get("drop", 0.72))
        zb = b["neck_z"] + 0.012
        M = 240
        th = np.linspace(-math.pi, math.pi, M, endpoint=False)             # 0 = the front
        zz = zb + (zf - zb) * ((1 + np.cos(th)) / 2) ** 1.6
        rr = np.zeros(M)
        for i_ in range(M):
            hit, _n, _i, dist = tree.ray_cast(Vector((0, 0, zz[i_])), Vector((math.sin(th[i_]), -math.cos(th[i_]), 0)))
            rr[i_] = dist if hit is not None else (rr[i_ - 1] if i_ else 0.07)
        ker = np.ones(9) / 9.0                                # a chain is taut: it bridges from the neck to the shoulder, it does not step
        rr = np.maximum(rr, np.convolve(np.concatenate([rr[-4:], rr, rr[:4]]), ker, mode="valid"))
        rr += 0.005 + float(spec.get("lift", 0.0))
        C = np.stack([rr * np.sin(th), -rr * np.cos(th), zz], axis=1)
        Lc = float(np.linalg.norm(np.diff(np.concatenate([C, C[:1]]), axis=0), axis=1).sum())
        k = Lc / L0 * float(spec.get("scale", 1.0))          # links keep their proportions: the whole chain is this much bigger
        def at(t_, A):                                       # read a value of the body's line at angle t_ (smoothly, round and round)
            f_ = (t_ + math.pi) / math.tau * M
            i0 = np.floor(f_).astype(int) % M
            u_ = (f_ - np.floor(f_))[:, None] if A.ndim > 1 else (f_ - np.floor(f_))
            return A[i0] * (1 - u_) + A[(i0 + 1) % M] * u_
        T = np.roll(C, -1, axis=0) - np.roll(C, 1, axis=0)
        T /= np.linalg.norm(T, axis=1, keepdims=True)
        N = np.stack([np.sin(th), -np.cos(th), np.zeros(M)], axis=1)
        N = N - T * (N * T).sum(axis=1, keepdims=True)
        N /= np.linalg.norm(N, axis=1, keepdims=True)
        Bn = np.cross(T, N)
        out = V.copy()
        tl = np.arctan2(np.sin(phi - phi0), np.cos(phi - phi0))             # place along the loop, 0 at the pendant
        a_l = phi[link]
        dr = rad[link] - np.interp(a_l, np.linspace(-math.pi, math.pi, NB, endpoint=False) + math.pi / NB, rc, period=math.tau)
        dn = off[link] - np.interp(a_l, np.linspace(-math.pi, math.pi, NB, endpoint=False) + math.pi / NB, oc, period=math.tau)
        sgn = 1.0 if (cen(np.array([phi0 + 0.3]))[0] - c) @ np.array([1.0, 0, 0]) > 0 else -1.0     # which way round the asset's loop runs
        tt = tl[link] * sgn
        out[link] = at(tt, C) + k * (dr[:, None] * at(tt, N) + dn[:, None] * at(tt, Bn) * sgn)
        if pend.any():                                       # the pendant hangs from the lowest point, as it was modelled, just clear of the chest
            pv = V[pend]
            anchor = pv[int(np.argmin(np.linalg.norm(pv - cen(np.array([phi0]))[0], axis=1)))]
            q_ = C[int(np.argmin(np.abs(th)))] + (pv - anchor) * k
            for _ in range(40):
                cm = Vector(q_.mean(axis=0))
                hit, _n, _i, dist = tree.ray_cast(cm + Vector((0, -2.0, 0)), Vector((0, 1, 0)))
                if hit is None or hit.y - 0.004 >= q_[:, 1].max():
                    break
                q_[:, 1] -= 0.002
            out[pend] = q_
        keep = ~wire
        if wire.any():                                       # drop the guide wire's faces
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.verts.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.verts[i_] for i_ in np.nonzero(wire)[0]], context="VERTS")
            bm.to_mesh(me)
            bm.free()
        me.vertices.foreach_set("co", out[keep].ravel())
        me.update()
        ob = bpy.data.objects.new(f"{self.name}.{spec['name']}", me)
        self.coll.objects.link(ob)
        ob.parent = self.J["torso"]
        ob.location = -self.W["torso"]
        ob["c3_part"], ob["c3_kind"], ob["c3_color"], ob["c3_key"] = spec["name"], "plain", "", ""
        self.parts.setdefault(spec["name"], []).append(ob)
        print(f"[fig3d] {self.name}: necklace {spec['name']}: {int(link.sum())} link points, pendant {int(pend.sum())}, wire {int(wire.sum())}, size x{k:.2f}")
        return ob

    # ------------------------------------------------------------------ costume changes
    def recolor(self, **colors):
        """recolor(tunic_tan="#7A1F2B"): every part painted with that colour name takes the new colour"""
        for key, hexc in colors.items():
            for obs in self.parts.values():
                for ob in obs:
                    if ob.get("c3_key") == key:
                        ob.data.materials[0] = self.mat(ob["c3_kind"], hexc)
                        ob["c3_color"] = hexc
        if self.body:
            self.body.recolor(colors)
        return self

    def hide(self, *patterns):
        n = 0
        for name, obs in self.parts.items():
            if any(fnmatch.fnmatchcase(name, p) for p in patterns):
                for ob in obs:
                    ob.hide_render = ob.hide_viewport = True
                    n += 1
        if self.body:
            n += self.body.hide(patterns)
        return n

    def add_flat(self, name, on, pts, color, layer=10.0, **opts):
        """Add ONE flat front drawing (x, z in metres, model space) and let the figure make it 3D: on = "head" | "torso" |
        "arm_upper.L" ... ; opts may force how with as_="decal" | "band" | "panel" | "lathe" | "peak" | "blob" | "cape" | "stud" | "crown"."""
        p = dict(name=name, on=on, pts=[(float(x), float(z)) for x, z in pts], color=color, layer=layer)
        if "as_" in opts:
            p["as"] = opts.pop("as_")
        p.update(opts)
        p = self._units(p)
        k = self.classify(p)
        p["kind_"] = k
        if k == "hair":
            self._hair([p])
        elif k == "beard":
            self._beard_from([p])
        elif k != "skip":
            getattr(self, "_p_" + k)(p)
            if self.body and self.body.ready and p["on"].split(".")[0] != "head":
                self.body.dress()
                return self.parts.get("Body", [])
        return self.parts.get(name, [])
