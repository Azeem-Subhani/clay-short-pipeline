"""Carpenter's wooden mallet: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_carpenter_mallet.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_carpenter_mallet", name="Carpenter's wooden mallet", kind="prop", tags=['mallet', 'hammer', 'carpenter', 'wood', 'tool'],
             era=['medieval', 'renaissance', 'age_of_sail', 'victorian', 'fantasy', 'modern'], source="built", license="project",
             notes="32 cm tall, head up; the origin is the grip 6 cm above the handle end: hold(mallet, 'R', t)")


def build_asset():
    parts = []
    parts.append(build.cyl("mallet.handle", 0.016, 0.26, (0, 0, -0.06), "oak_planks", seg=12))
    parts.append(build.box("mallet.head", (0.15, 0.075, 0.085), (0, 0, 0.18), "dark_timber", bevel=0.008))
    for sx in (-1, 1):
        parts.append(build.box(f"mallet.face{sx}", (0.008, 0.07, 0.08), (sx * 0.077, 0, 0.1825), "oak_planks", bevel=0.003))
    return build.group("prop_carpenter_mallet", parts)
