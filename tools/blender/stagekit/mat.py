"""stagekit.mat - what the world is made of.

Sets ask for a surface by what it IS, not by a colour:

    wall.data.materials.append(mat.surface("castle_stone"))
    mat.surface("oak_planks", tint="#6B4A2E")

Each name is an entry in library/materials/catalog.json. If the ambientCG texture set for it has been downloaded
(`python tools/clip.py materials fetch`), the surface is that scanned PBR material (CC0). If not, the same name gives a
procedural stand-in with the same colour, scale and roughness, so a set always builds and a missing download never
changes the layout. Textures and procedurals both tile in metres on the UVs made by mat.uv_box / the build kit.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import bpy

from . import core

LIB = core.PROJECT / "library" / "materials"
_CAT = None
MAPS = {"Color": "Base Color", "Roughness": "Roughness", "Metalness": "Metallic", "NormalGL": "Normal", "AmbientOcclusion": "AO",
        "Displacement": "Height", "Opacity": "Alpha"}


def catalog() -> dict:
    global _CAT
    if _CAT is None:
        _CAT = json.loads((LIB / "catalog.json").read_text(encoding="utf-8"))["surfaces"]
    return _CAT


def downloaded(asset_id: str) -> dict | None:
    """Texture files of a downloaded ambientCG set: {"Color": path, "NormalGL": path, ...} or None."""
    d = LIB / "ambientcg" / asset_id
    if not d.is_dir():
        return None
    out = {}
    for p in sorted(d.iterdir()):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
            for key in MAPS:
                if p.stem.endswith("_" + key):
                    out[key] = p
    return out if "Color" in out else None


# ----------------------------------------------------------------------------- node helpers
def _new(name: str):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return m, nt, bsdf


def _coords(nt, tile_m: float, kind: str = "UV"):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    s = 1.0 / max(tile_m, 1e-4)
    mp.inputs["Scale"].default_value = (s, s, s)
    nt.links.new(tc.outputs[kind], mp.inputs["Vector"])
    return mp


def _ramp(nt, src, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    el = r.color_ramp.elements
    while len(el) < len(stops):
        el.new(0.5)
    for e, (pos, col) in zip(el, stops):
        e.position = pos
        e.color = core.hex_rgba(col) if isinstance(col, str) else (col, col, col, 1.0)
    nt.links.new(src, r.inputs["Fac"])
    return r


def _noise(nt, vec, scale, detail=4.0, rough=0.55, w=None):
    n = nt.nodes.new("ShaderNodeTexNoise")
    if w is not None:
        n.noise_dimensions = "4D"
        n.inputs["W"].default_value = w
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    nt.links.new(vec, n.inputs["Vector"])
    return n


def _bump(nt, bsdf, height, strength=0.4, distance=0.02):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(height, b.inputs["Height"])
    nt.links.new(b.outputs[0], bsdf.inputs["Normal"])
    return b


def _mix(nt, a, b, fac, blend="MIX"):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    for sock, val in ((m.inputs["Factor"], fac), (m.inputs["A"], a), (m.inputs["B"], b)):
        if hasattr(val, "is_linked"):
            nt.links.new(val, sock)
        elif isinstance(val, str):
            sock.default_value = core.hex_rgba(val)
        elif isinstance(val, (tuple, list)):
            sock.default_value = tuple(val)
        else:
            sock.default_value = val
    return m.outputs["Result"]


def _math(nt, op, a, b=None):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    for sock, val in ((m.inputs[0], a), (m.inputs[1], b)):
        if val is None:
            continue
        if hasattr(val, "is_linked"):
            nt.links.new(val, sock)
        else:
            sock.default_value = val
    return m.outputs[0]


def _shade(hexcol: str, k: float) -> str:
    h = hexcol.lstrip("#")
    return "#" + "".join(f"{max(0, min(255, int(int(h[i:i + 2], 16) * k))):02X}" for i in (0, 2, 4))


# ----------------------------------------------------------------------------- procedural stand-ins
def _p_blocks(name, color="#B9AD98", mortar="#6E675C", tile_m=1.0, block=(0.62, 0.30), rough=0.85, bump=0.5, vary=0.16, offset=0.5, moss=True, **_):
    """Coursed stone blocks or bricks with mortar lines, per-block colour drift and a pitted face."""
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0)
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = block[0]
    br.inputs["Row Height"].default_value = block[1]
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Mortar Smooth"].default_value = 0.3
    br.inputs["Bias"].default_value = 0.0
    br.offset = offset
    br.inputs["Color1"].default_value = core.hex_rgba(_shade(color, 1.0 + vary))
    br.inputs["Color2"].default_value = core.hex_rgba(_shade(color, 1.0 - vary))
    br.inputs["Mortar"].default_value = core.hex_rgba(mortar)
    nt.links.new(mp.outputs[0], br.inputs["Vector"])
    n1 = _noise(nt, mp.outputs[0], 1.1, 5, 0.62)
    n2 = _noise(nt, mp.outputs[0], 38.0, 3, 0.7)
    n3 = _noise(nt, mp.outputs[0], 0.35, 3, 0.5)
    stain = _ramp(nt, n1.outputs["Fac"], [(0.30, 0.66), (0.72, 1.10)])
    col = _mix(nt, br.outputs["Color"], stain.outputs["Color"], 1.0, "MULTIPLY")
    warm = _ramp(nt, n3.outputs["Fac"], [(0.35, "#E9DCC6"), (0.65, "#FFFFFF")])
    col = _mix(nt, col, warm.outputs["Color"], 1.0, "MULTIPLY")
    geo = nt.nodes.new("ShaderNodeNewGeometry")                        # damp and moss creep up from the ground
    sepz = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sepz.inputs[0])
    low = _ramp(nt, _math(nt, "ADD", sepz.outputs["Z"], _math(nt, "MULTIPLY", n1.outputs["Fac"], 1.6)), [(0.0, 1.0), (0.55, 0.0)])
    low.color_ramp.elements[0].position, low.color_ramp.elements[1].position = 0.55, 1.75
    if moss:
        col = _mix(nt, col, _mix(nt, col, "#5D6B45", 0.55), low.outputs["Color"])
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    h = _math(nt, "ADD", _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 1.0, br.outputs["Fac"]), 1.0), _math(nt, "MULTIPLY", n2.outputs["Fac"], 0.22))
    _bump(nt, bsdf, h, bump, 0.03)
    return m


def _p_cobble(name, color="#8E887C", gap="#4B463E", tile_m=1.0, stone=0.16, rough=0.8, bump=0.7, **_):
    """Rounded paving stones with dark gaps (Voronoi cells), slightly domed."""
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0)
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    vo.feature = "DISTANCE_TO_EDGE"
    vo.inputs["Scale"].default_value = 1.0 / stone
    nt.links.new(mp.outputs[0], vo.inputs["Vector"])
    vc = nt.nodes.new("ShaderNodeTexVoronoi")
    vc.inputs["Scale"].default_value = 1.0 / stone
    nt.links.new(mp.outputs[0], vc.inputs["Vector"])
    edge = _ramp(nt, vo.outputs["Distance"], [(0.02, 0.0), (0.11, 1.0)])
    tone = _ramp(nt, vc.outputs["Color"], [(0.0, _shade(color, 0.78)), (1.0, _shade(color, 1.2))])
    col = _mix(nt, gap, tone.outputs["Color"], edge.outputs["Color"])
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    dome = _ramp(nt, vo.outputs["Distance"], [(0.0, 0.0), (0.35, 1.0)])
    n = _noise(nt, mp.outputs[0], 60, 2)
    _bump(nt, bsdf, _math(nt, "ADD", dome.outputs["Color"], _math(nt, "MULTIPLY", n.outputs["Fac"], 0.1)), bump, 0.03)
    return m


def _p_ground(name, color="#5E8A3C", second=None, tile_m=1.0, patch=1.6, rough=0.95, bump=0.25, fine=55.0, **_):
    """Grass, earth, sand or mud: two tones in soft patches plus fine grain."""
    second = second or _shade(color, 0.72)
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0, "Object")
    big = _noise(nt, mp.outputs[0], 1.0 / patch, 4, 0.6)
    fine_n = _noise(nt, mp.outputs[0], fine, 3, 0.7)
    tone = _ramp(nt, big.outputs["Fac"], [(0.30, second), (0.52, color), (0.78, _mix_hex(color, "#D8C56A", 0.22))])
    g = _ramp(nt, fine_n.outputs["Fac"], [(0.3, 0.80), (0.75, 1.14)])
    mid = _noise(nt, mp.outputs[0], 6.0, 3, 0.6)
    g2 = _ramp(nt, mid.outputs["Fac"], [(0.35, 0.88), (0.7, 1.08)])
    nt.links.new(_mix(nt, _mix(nt, tone.outputs["Color"], g.outputs["Color"], 1.0, "MULTIPLY"), g2.outputs["Color"], 1.0, "MULTIPLY"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    _bump(nt, bsdf, fine_n.outputs["Fac"], bump, 0.02)
    return m


def _p_mud(name, color="#5A4630", tile_m=1.0, rough=0.35, **_):
    """Wet mud: dark, lumpy, with shiny puddled patches."""
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0, "Object")
    big = _noise(nt, mp.outputs[0], 1.4, 5, 0.65)
    fine_n = _noise(nt, mp.outputs[0], 14.0, 4, 0.6)
    tone = _ramp(nt, big.outputs["Fac"], [(0.3, _shade(color, 0.62)), (0.7, _shade(color, 1.18))])
    nt.links.new(tone.outputs["Color"], bsdf.inputs["Base Color"])
    wet = _ramp(nt, big.outputs["Fac"], [(0.38, 0.12), (0.62, 0.6)])
    nt.links.new(wet.outputs["Color"], bsdf.inputs["Roughness"])
    _bump(nt, bsdf, _math(nt, "ADD", big.outputs["Fac"], _math(nt, "MULTIPLY", fine_n.outputs["Fac"], 0.35)), 0.8, 0.06)
    return m


def _p_wood(name, color="#7A5634", tile_m=1.0, plank=0.16, rough=0.7, bump=0.35, along="Y", **_):
    """Planks with grain running along one axis and dark seams between boards."""
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0)
    if along == "X":
        mp.inputs["Rotation"].default_value = (0, 0, math.radians(90))
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(mp.outputs[0], sep.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(_math(nt, "MULTIPLY", sep.outputs["X"], 14.0), comb.inputs["X"])
    nt.links.new(_math(nt, "MULTIPLY", sep.outputs["Y"], 0.9), comb.inputs["Y"])
    grain = _noise(nt, comb.outputs[0], 3.0, 6, 0.62)
    board = _math(nt, "FLOOR", _math(nt, "DIVIDE", sep.outputs["X"], plank))
    wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "1D"
    nt.links.new(board, wn.inputs["W"])
    tone = _ramp(nt, grain.outputs["Fac"], [(0.28, _shade(color, 0.7)), (0.72, _shade(color, 1.16))])
    drift = _ramp(nt, wn.outputs["Value"], [(0.0, 0.82), (1.0, 1.1)])
    seam = _math(nt, "FRACT", _math(nt, "DIVIDE", sep.outputs["X"], plank))
    seam_m = _ramp(nt, seam, [(0.0, 0.25), (0.05, 1.0), (0.95, 1.0), (1.0, 0.25)])
    col = _mix(nt, _mix(nt, tone.outputs["Color"], drift.outputs["Color"], 1.0, "MULTIPLY"), seam_m.outputs["Color"], 1.0, "MULTIPLY")
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    _bump(nt, bsdf, _math(nt, "MULTIPLY", _math(nt, "ADD", grain.outputs["Fac"], seam_m.outputs["Color"]), 0.5), bump, 0.015)
    return m


def _p_bark(name, color="#5A4332", tile_m=1.0, **_):
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0, "Object")
    mp.inputs["Scale"].default_value = (9.0, 9.0, 1.6)
    n = _noise(nt, mp.outputs[0], 2.2, 6, 0.7)
    tone = _ramp(nt, n.outputs["Fac"], [(0.3, _shade(color, 0.6)), (0.7, _shade(color, 1.2))])
    nt.links.new(tone.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    _bump(nt, bsdf, n.outputs["Fac"], 0.9, 0.05)
    return m


def _p_leaves(name, color="#4F8A3A", tile_m=1.0, **_):
    """Foliage: mottled greens with a soft sheen, light passing through at the edges."""
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0, "Object")
    n = _noise(nt, mp.outputs[0], 5.5, 4, 0.7)
    n2 = _noise(nt, mp.outputs[0], 26.0, 2, 0.6)
    tone = _ramp(nt, n.outputs["Fac"], [(0.28, _shade(color, 0.62)), (0.55, color), (0.8, _shade(color, 1.28))])
    nt.links.new(tone.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.72
    try:
        bsdf.inputs["Subsurface Weight"].default_value = 0.12
        bsdf.inputs["Subsurface Radius"].default_value = (0.08, 0.14, 0.03)
    except KeyError:
        pass
    _bump(nt, bsdf, _math(nt, "ADD", n.outputs["Fac"], _math(nt, "MULTIPLY", n2.outputs["Fac"], 0.5)), 0.9, 0.08)
    return m


def _p_plain(name, color="#C9B8A0", tile_m=1.0, rough=0.8, metallic=0.0, bump=0.12, grain=30.0, sheen=0.0, **_):
    """Plaster, cloth, clay pot, painted wood, iron, gold: one colour with fine grain."""
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0, "Object")
    n = _noise(nt, mp.outputs[0], grain, 3, 0.6)
    n2 = _noise(nt, mp.outputs[0], 2.0, 3, 0.6)
    tone = _ramp(nt, n2.outputs["Fac"], [(0.3, _shade(color, 0.86)), (0.7, _shade(color, 1.08))])
    nt.links.new(tone.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if sheen:
        try:
            bsdf.inputs["Sheen Weight"].default_value = sheen
            bsdf.inputs["Sheen Roughness"].default_value = 0.4
        except KeyError:
            pass
    if bump:
        _bump(nt, bsdf, n.outputs["Fac"], bump, 0.01)
    return m


def _p_roof(name, color="#8A4B36", tile_m=1.0, **_):
    """Overlapping roof tiles or shingles in rows."""
    return _p_blocks(name, color, _shade(color, 0.45), tile_m, block=(0.28, 0.2), rough=0.75, bump=0.8, vary=0.22)


def _p_thatch(name, color="#B79A55", tile_m=1.0, **_):
    m = _p_wood(name, color, tile_m, plank=0.05, rough=0.95, bump=0.8)
    return m


def _p_water(name, color="#2F6B4F", deep="#12352B", tile_m=1.0, ripple=0.35, rough=0.06, speed=1.0, **_):
    """Still, deep water you cannot see into: dark body colour, bright sky reflection, slow moving ripples.
    The ripple pattern drifts over the shot (animated), so the surface is never frozen."""
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0, "Object")
    n = _noise(nt, mp.outputs[0], 2.4, 3, 0.5, w=0.0)
    n2 = _noise(nt, mp.outputs[0], 7.5, 2, 0.5, w=0.0)
    fres = nt.nodes.new("ShaderNodeLayerWeight")
    fres.inputs["Blend"].default_value = 0.35
    col = _mix(nt, deep, color, fres.outputs["Facing"])
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    try:
        bsdf.inputs["Specular IOR Level"].default_value = 0.9
        bsdf.inputs["Coat Weight"].default_value = 0.3
        bsdf.inputs["Coat Roughness"].default_value = 0.04
    except KeyError:
        pass
    h = _math(nt, "ADD", n.outputs["Fac"], _math(nt, "MULTIPLY", n2.outputs["Fac"], 0.45))
    _bump(nt, bsdf, h, ripple, 0.05)
    sc = bpy.context.scene
    for node, rate in ((n, 0.35), (n2, 0.9)):
        w = node.inputs["W"]
        w.default_value = 0.0
        w.keyframe_insert("default_value", frame=1)
        w.default_value = rate * speed * max(1, sc.frame_end) / sc.render.fps
        w.keyframe_insert("default_value", frame=max(2, sc.frame_end))
    for fc in core.fcurves(nt):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    m["sk_water"] = 1
    return m


def _p_checker(name, color="#E9E4D8", second="#2B2B2E", tile_m=1.0, size=0.5, rough=0.25, **_):
    """Chequered floor tiles: two tones in squares of `size` metres, glossy."""
    m, nt, bsdf = _new(name)
    mp = _coords(nt, 1.0)
    ck = nt.nodes.new("ShaderNodeTexChecker")
    ck.inputs["Scale"].default_value = 1.0 / (2 * size)
    ck.inputs["Color1"].default_value = core.hex_rgba(color)
    ck.inputs["Color2"].default_value = core.hex_rgba(second)
    nt.links.new(mp.outputs[0], ck.inputs["Vector"])
    n = _noise(nt, mp.outputs[0], 18.0, 3, 0.6)
    g = _ramp(nt, n.outputs["Fac"], [(0.3, 0.9), (0.7, 1.05)])
    nt.links.new(_mix(nt, ck.outputs["Color"], g.outputs["Color"], 1.0, "MULTIPLY"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    return m


def _p_glass(name, color="#CFE6F0", tile_m=1.0, alpha=0.16, rough=0.03, **_):
    """Window and display glass: nearly clear with a cool tint and a sharp sheen. Blended, so it costs nothing at draft quality."""
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = core.hex_rgba(color)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Alpha"].default_value = alpha
    try:
        bsdf.inputs["Specular IOR Level"].default_value = 1.0
    except KeyError:
        pass
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass
    try:
        m.use_backface_culling = False
    except AttributeError:
        pass
    return m


def solid(color="#C9B8A0", rough: float = 0.7, metallic: float = 0.0, name: str | None = None, sheen: float = 0.0):
    """A plain painted colour (plastic, enamel, paper, wax): cached, one material per look. Use mat.surface for real materials."""
    name = name or f"SK_solid_{color}_{rough}_{metallic}_{sheen}"
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = _p_plain(name, color=color, rough=rough, metallic=metallic, bump=0.0, sheen=sheen)
    m["sk_source"] = "procedural:solid"
    return m


def emit(color="#FFC477", strength: float = 5.0, name: str | None = None, **_):
    """Things that ARE light: flame, a lit window, a lantern glass, the sun disc."""
    name = name or f"SK_emit_{color}_{strength}"
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = core.hex_rgba(color)
    e.inputs["Strength"].default_value = strength
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


PROCEDURAL = {"blocks": _p_blocks, "cobble": _p_cobble, "ground": _p_ground, "mud": _p_mud, "wood": _p_wood, "bark": _p_bark,
              "leaves": _p_leaves, "plain": _p_plain, "roof": _p_roof, "thatch": _p_thatch, "water": _p_water, "glass": _p_glass, "checker": _p_checker}


# ----------------------------------------------------------------------------- scanned PBR sets (ambientCG)
def pbr(asset_id: str, tile_m: float = 1.0, tint: str | None = None, name: str | None = None, bump_scale: float = 1.0):
    """A material from a downloaded ambientCG texture set (library/materials/ambientcg/<id>/). Raises if it is not there."""
    files = downloaded(asset_id)
    if not files:
        raise FileNotFoundError(f"ambientCG set {asset_id} is not in library/materials/ambientcg/. Run: python tools/clip.py materials fetch {asset_id}")
    m, nt, bsdf = _new(name or f"ACG_{asset_id}")
    mp = _coords(nt, tile_m)

    def tex(key, colour=False):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(str(files[key]), check_existing=True)
        if not colour:
            n.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs[0], n.inputs["Vector"])
        return n

    col = tex("Color", True).outputs["Color"]
    if "AmbientOcclusion" in files:
        col = _mix(nt, col, tex("AmbientOcclusion").outputs["Color"], 0.6, "MULTIPLY")
    if tint:
        col = _mix(nt, col, tint, 1.0, "MULTIPLY")
    nt.links.new(col, bsdf.inputs["Base Color"])
    if "Roughness" in files:
        nt.links.new(tex("Roughness").outputs["Color"], bsdf.inputs["Roughness"])
    if "Metalness" in files:
        nt.links.new(tex("Metalness").outputs["Color"], bsdf.inputs["Metallic"])
    if "NormalGL" in files:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = bump_scale
        nt.links.new(tex("NormalGL").outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    if "Opacity" in files:
        nt.links.new(tex("Opacity").outputs["Color"], bsdf.inputs["Alpha"])
    m["sk_source"] = f"ambientCG:{asset_id}"
    return m


def surface(name: str, tint: str | None = None, tile_m: float | None = None, procedural: bool = False, **params):
    """The material for a named surface from the catalog: scanned if downloaded, else its procedural stand-in.
    tint multiplies the colour (a darker wall, a redder brick); extra params override the stand-in's defaults."""
    cat = catalog()
    if name not in cat:
        raise KeyError(f"no surface '{name}' in library/materials/catalog.json. It has: {', '.join(sorted(cat))}")
    e = cat[name]
    scan_tint = tint or e.get("tint")                      # a catalog entry may carry a tint for its scan (warm plaster = plaster, tinted)
    key = f"SURF_{name}" + (f"_{tint}" if tint else "") + (f"_{tile_m}" if tile_m else "") + ("".join(f"_{k}{v}" for k, v in sorted(params.items())))
    m = bpy.data.materials.get(key)
    if m:
        return m
    used = bpy.context.scene.get("surfaces_used")
    log = json.loads(used) if used else {}
    if not procedural:
        for aid in e.get("ambientcg", []):
            if downloaded(aid):
                m = pbr(aid, tile_m or e.get("tile_m", 1.0), scan_tint, key)
                log[name] = f"ambientCG:{aid}"
                break
    if m is None:
        p = dict(e["procedural"])
        kind = p.pop("kind")
        p.update(params)
        if tint:
            p["color"] = _tint_hex(p.get("color", "#888888"), tint)
        m = PROCEDURAL[kind](key, tile_m=tile_m or e.get("tile_m", 1.0), **p)
        m["sk_source"] = f"procedural:{kind}"
        log[name] = f"procedural stand-in ({kind})" + (f"; wants ambientCG {e['ambientcg'][0]}" if e.get("ambientcg") else "")
    m["sk_surface"] = name
    bpy.context.scene["surfaces_used"] = json.dumps(log)
    return m


def _mix_hex(a: str, b: str, k: float) -> str:
    ha, hb = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(int(ha[i:i + 2], 16) * (1 - k) + int(hb[i:i + 2], 16) * k):02X}" for i in (0, 2, 4))


def _tint_hex(a: str, b: str) -> str:
    ha, hb = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(int(ha[i:i + 2], 16) * int(hb[i:i + 2], 16) / 255):02X}" for i in (0, 2, 4))


# ----------------------------------------------------------------------------- UVs in metres
def uv_box(ob, scale: float = 1.0):
    """Box-project UVs in metres (object space x object scale), so every texture tiles at real size on any kit piece."""
    me = ob.data
    if not hasattr(me, "polygons"):
        return ob
    uv = me.uv_layers.active or me.uv_layers.new(name="UVMap")
    sx, sy, sz = (abs(v) * scale for v in ob.scale)
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if ax == 2:
                uv.data[li].uv = (co.x * sx, co.y * sy)
            elif ax == 1:
                uv.data[li].uv = (co.x * sx, co.z * sz)
            else:
                uv.data[li].uv = (co.y * sy, co.z * sz)
    return ob
