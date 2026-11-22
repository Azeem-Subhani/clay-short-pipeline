"""stagekit.wardrobe - flat costume pieces that turn a pack character into the person the story needs.

The pack has 28 characters. A story needs a rich merchant, a gardener, a miller, a guard captain. Dress a pack character
whose face and build fit: change colours (actor.recolor), take parts off (actor.hide) and add pieces from here (actor.wear).
Every piece is drawn for all three views with the pack's own outline, so it turns and walks with the character.

    rich = cast.actor("rich_man", "AdultMan", costume={
        "recolor": {"tunic_tan": "#7A1F2B", "belt": "#2E1A12"},
        "hide": ["Tunic_Lace*"],
        "wear": [{"item": "beret", "color": "#7A1F2B", "feather": "#F3E7CF"}, {"item": "ruff"}, {"item": "buttons", "color": "#E9C04A"}]})

Head pieces are drawn in head units (1 = head radius, origin = head centre, +x = the side the 3q/side views face).
Torso pieces are drawn in torso units (u: -1..1 across the torso, v: 0 = hem .. 1 = shoulders).
Each item lists the periods it belongs to in config/cast.json; the plan check uses that.
"""
from __future__ import annotations

import math

from . import core

HEAD_C = 0.30
TORSO_C = 0.22
LAYER = dict(cape=0, hair_back=1, torso=9, det=10, det2=11, collar=12, collar_det=13, head=16.5, face=17.5, hair_front=20.5, hat=22,
             hat_det=23, hat_det2=24)


# ----------------------------------------------------------------------------- 2D shape helpers
def ellipse(cx, cz, rx, rz, n=36, rot=0.0, a0=0.0, a1=360.0):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    for i in range(n if abs(a1 - a0) >= 360 else n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        x, z = rx * math.cos(a), rz * math.sin(a)
        out.append((cx + x * c - z * s, cz + x * s + z * c))
    return out


def chaikin(pts, it=2, closed=True):
    for _ in range(it):
        out = []
        n = len(pts)
        for i in range(n if closed else n - 1):
            a, b = pts[i], pts[(i + 1) % n]
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        if not closed:
            out = [pts[0]] + out + [pts[-1]]
        pts = out
    return pts


def scallop(cx, cz, rx, rz, bumps=9, amp=0.12, n=8):
    out = []
    for b in range(bumps):
        for i in range(n):
            a = 2 * math.pi * (b + i / n) / bumps
            k = 1.0 + amp * abs(math.sin(math.pi * i / n))
            out.append((cx + rx * k * math.cos(a), cz + rz * k * math.sin(a)))
    return out


def _g3q(x):
    return x + HEAD_C * (1 - x * x) if abs(x) <= 1 else x


def _map_head(pts, view, rigid=True):
    if view == "Front":
        return list(pts)
    cx = sum(p[0] for p in pts) / len(pts)
    if view == "ThreeQuarter":
        if rigid:
            nx = _g3q(max(-1.0, min(1.0, cx)))
            return [(nx + (x - cx), z) for x, z in pts]
        return [(_g3q(x), z) for x, z in pts]
    if rigid:
        return [(cx * 0.9 - 0.02 + (x - cx) * 0.82, z) for x, z in pts]
    return [(x * 0.9 - 0.02, z) for x, z in pts]


def head_part(actor, name, pts, color, layer="hat", rigid=True, bone="head", outline=True, wire=False):
    """One head-unit shape, drawn in all three views."""
    obs = []
    for view in actor.rigs:
        cx, cz, r = actor.head_box(view)
        mapped = _map_head(pts, view, rigid)
        obs.append(actor.add_part(name, view, [(cx + x * r, cz + z * r) for x, z in mapped], color, bone,
                                  LAYER[layer] if isinstance(layer, str) else layer, outline, wire))
    return obs


def torso_part(actor, name, pts, color, layer="det", outline=True, wire=False, bone="torso"):
    """One torso-unit shape (u across, v up), drawn in all three views."""
    obs = []
    for view in actor.rigs:
        cx, z0, z1, hw = actor.torso_box(view)
        out = []
        for u, v in pts:
            if view == "Front":
                x = cx + hw * u
            elif view == "ThreeQuarter":
                x = cx + hw * (u + TORSO_C * (1 - u * u) if abs(u) <= 1 else u)
            else:
                x = cx + hw * (0.45 + 0.55 * u)
            out.append((x, z0 + (z1 - z0) * v))
        obs.append(actor.add_part(name, view, out, color, bone, LAYER[layer] if isinstance(layer, str) else layer, outline, wire))
    return obs


def _shade(hexcol: str, k: float) -> str:
    h = hexcol.lstrip("#")
    return "#" + "".join(f"{max(0, min(255, int(int(h[i:i + 2], 16) * k))):02X}" for i in (0, 2, 4))


# ----------------------------------------------------------------------------- the pieces
def straw_hat(actor, color="#E3C169", band="#3F7A4A", brim=1.72, **_):
    """A wide straw sun hat: field and garden work, any pre-industrial countryside."""
    head_part(actor, "W_Hat_Crown", chaikin([(-0.86, 0.66), (-0.80, 1.08), (-0.5, 1.33), (0.0, 1.40), (0.5, 1.33), (0.80, 1.08), (0.86, 0.66)], 2), color, "hat")
    head_part(actor, "W_Hat_Band", [(-0.86, 0.70), (-0.84, 0.90), (0.84, 0.90), (0.86, 0.70)], band, "hat_det")
    head_part(actor, "W_Hat_Brim", ellipse(0.0, 0.68, brim, 0.24, 44), color, "hat_det2")
    for i, x in enumerate((-1.1, -0.45, 0.3, 0.95)):
        head_part(actor, f"W_Hat_Weave{i}", [(x, 0.60), (x + 0.16, 0.76)], _shade(color, 0.72), 24.5, wire=True)


def beret(actor, color="#7A1F2B", feather="#F3E7CF", band=None, **_):
    """A soft cap worn to one side, with a plume: merchants, courtiers, artists (late medieval to renaissance)."""
    band = band or _shade(color, 0.72)
    head_part(actor, "W_Beret", chaikin([(-1.05, 0.72), (-1.22, 0.98), (-0.85, 1.30), (-0.1, 1.42), (0.7, 1.34), (1.12, 1.05), (1.02, 0.72), (0.0, 0.62)], 3), color, "hat")
    head_part(actor, "W_Beret_Band", chaikin([(-1.0, 0.60), (-1.02, 0.76), (0.0, 0.70), (1.0, 0.76), (1.0, 0.60), (0.0, 0.52)], 2), band, "hat_det")
    if feather:
        head_part(actor, "W_Feather", chaikin([(-0.62, 0.92), (-1.02, 1.30), (-1.20, 1.78), (-0.92, 2.02), (-0.50, 1.82), (-0.34, 1.36), (-0.40, 0.98)], 3), feather, "hat_det2")
        head_part(actor, "W_Feather_Spine", [(-0.52, 0.98), (-0.74, 1.40), (-0.92, 1.88)], _shade(feather, 0.7), 24.5, wire=True)


def ruff(actor, color="#F7F1E3", **_):
    """A pleated white collar: wealth and rank (renaissance), also a jester or a storybook noble."""
    head_part(actor, "W_Ruff", scallop(0.0, -1.03, 0.98, 0.25, 11, 0.16), color, "collar_det", bone="torso")


def hood(actor, color="#5B4632", **_):
    """A cloth hood with a short shoulder cape: peasants, monks, travellers, thieves."""
    head_part(actor, "W_Hood_Back", chaikin([(-1.16, -0.72), (-1.26, 0.2), (-0.98, 0.98), (-0.2, 1.36), (0.6, 1.24), (1.14, 0.7), (1.22, -0.1), (1.12, -0.74)], 3), color, 15.5)
    head_part(actor, "W_Hood_Cowl", chaikin([(-1.22, -0.70), (-1.42, -1.22), (0.0, -1.44), (1.42, -1.22), (1.22, -0.70), (0.0, -1.02)], 3), color, "collar", bone="torso")
    head_part(actor, "W_Hood_Peak", chaikin([(-1.0, 0.52), (-0.72, 1.02), (0.0, 1.22), (0.72, 1.02), (1.0, 0.52), (0.55, 0.80), (0.0, 0.88), (-0.55, 0.80)], 2), color, "hat")


def kerchief(actor, color="#C9463A", **_):
    """A headscarf tied under the hair line: farm women, cooks, washerwomen, market sellers."""
    head_part(actor, "W_Kerchief", chaikin([(-1.04, 0.30), (-1.0, 0.82), (-0.55, 1.14), (0.0, 1.22), (0.55, 1.14), (1.0, 0.82), (1.04, 0.30), (0.5, 0.62), (0.0, 0.70), (-0.5, 0.62)], 2), color, "hat")
    head_part(actor, "W_Kerchief_Knot", chaikin([(-1.0, 0.25), (-1.3, 0.05), (-1.34, -0.25), (-1.05, -0.05)], 2), color, 15.8)


def top_hat(actor, color="#2A2630", band="#7A1F2B", **_):
    """A tall hat: gentlemen, bankers, undertakers (1800s to early 1900s)."""
    head_part(actor, "W_TopHat", chaikin([(-0.74, 0.74), (-0.78, 1.95), (0.78, 1.95), (0.74, 0.74)], 1), color, "hat")
    head_part(actor, "W_TopHat_Band", [(-0.75, 0.80), (-0.76, 1.02), (0.76, 1.02), (0.75, 0.80)], band, "hat_det")
    head_part(actor, "W_TopHat_Brim", ellipse(0.0, 0.74, 1.22, 0.13, 36), color, "hat_det2")


def crown(actor, color="#F2C94C", gem="#C8302C", **_):
    """A simple crown for a prince, princess or pretender (kings and queens of the pack already wear theirs)."""
    pts = [(-0.66, 0.84), (-0.74, 1.42), (-0.40, 1.12), (-0.20, 1.52), (0.0, 1.14), (0.20, 1.52), (0.40, 1.12), (0.74, 1.42), (0.66, 0.84)]
    head_part(actor, "W_Crown", pts, color, "hat")
    head_part(actor, "W_Crown_Gem", ellipse(0.0, 0.98, 0.09, 0.11, 14), gem, "hat_det")


def apron(actor, color="#EFE3C8", stains=None, bib=True, **_):
    """A work apron over the clothes: gardeners, cooks, smiths, millers, innkeepers. stains: a colour for earth or flour marks."""
    top = 0.80 if bib else 0.36
    pts = [(-0.52, top), (-0.60, 0.36), (-0.74, -0.34), (0.74, -0.34), (0.60, 0.36), (0.52, top)] if bib else [(-0.74, top), (-0.78, -0.34), (0.78, -0.34), (0.74, top)]
    torso_part(actor, "W_Apron", chaikin(pts, 1), color, "det")
    torso_part(actor, "W_Apron_Tie", [(-0.76, 0.34), (-0.76, 0.42), (0.76, 0.42), (0.76, 0.34)], _shade(color, 0.8), "det2")
    if bib:
        for s in (-1, 1):
            torso_part(actor, f"W_Apron_Strap{'L' if s > 0 else 'R'}", [(s * 0.50, 0.80), (s * 0.40, 0.80), (s * 0.34, 1.0), (s * 0.46, 1.0)], _shade(color, 0.8), "det2")
    if stains:
        for i, (u, v, r) in enumerate(((-0.3, 0.02, 0.13), (0.28, 0.18, 0.10), (0.1, -0.16, 0.12), (-0.42, 0.26, 0.07))):
            torso_part(actor, f"W_Apron_Stain{i}", chaikin(ellipse(u, v, r * 1.3, r * 0.42, 9, rot=20 * i), 1), stains, "det2", outline=False)


def sash(actor, color="#C8302C", **_):
    """A band across the chest: officials, heralds, mayors, a prize winner."""
    torso_part(actor, "W_Sash", [(-0.92, 0.92), (-0.62, 1.0), (0.96, 0.22), (0.88, 0.02)], color, "det")


def cloak(actor, color="#3E4A66", **_):
    """A long cloak behind the body, shoulders to shins: travellers, guards on watch, nobles outdoors, villains."""
    torso_part(actor, "W_Cloak", chaikin([(-1.0, 1.0), (-1.75, -0.78), (0.0, -0.9), (1.75, -0.78), (1.0, 1.0)], 2), color, "cape")
    head_part(actor, "W_Cloak_Clasp", ellipse(0.0, -1.12, 0.11, 0.11, 14), "#E9C04A", "collar_det", bone="torso")


def buttons(actor, color="#E9C04A", count=3, **_):
    """A row of round buttons down the chest (a dressier coat)."""
    for i in range(count):
        v = 0.82 - i * 0.2
        torso_part(actor, f"W_Button{i}", ellipse(0.0, v, 0.085, 0.036, 14), color, "det2")


def fur_trim(actor, color="#F3EAD6", **_):
    """A fur band along the hem and neck: winter clothes, wealth."""
    torso_part(actor, "W_FurHem", chaikin([(-1.02, 0.0), (-1.06, 0.14), (1.06, 0.14), (1.02, 0.0)], 1), color, "det")
    head_part(actor, "W_FurCollar", scallop(0.0, -1.05, 0.9, 0.2, 7, 0.14), color, "collar", bone="torso")


def freckles(actor, color="#D4553B", **_):
    """Freckles across the cheeks: youth, outdoor work."""
    for i, (x, z) in enumerate(((-0.52, -0.16), (-0.40, -0.24), (-0.60, -0.28), (0.52, -0.16), (0.40, -0.24), (0.60, -0.28))):
        head_part(actor, f"W_Freckle{i}", ellipse(x, z, 0.035, 0.035, 8), color, 17.8, rigid=False, outline=False)


ITEMS = {f.__name__: f for f in (straw_hat, beret, ruff, hood, kerchief, top_hat, crown, apron, sash, cloak, buttons, fur_trim, freckles)}


def wear(actor, item: str, **opts):
    if item not in ITEMS:
        raise KeyError(f"wardrobe has no '{item}'. It has: {', '.join(sorted(ITEMS))}. Add a piece in stagekit/wardrobe.py "
                       "(copy a short one such as sash or kerchief) and list it in config/cast.json.")
    ITEMS[item](actor, **opts)
    return actor
