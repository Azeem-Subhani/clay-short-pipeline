"""Archaeologist's trowel: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_archaeologist_trowel.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_archaeologist_trowel", name="Archaeologist's trowel", kind="prop", tags=['trowel', 'dig', 'archaeology', 'tool', 'excavation'],
             era=['victorian', 'modern'], source="built", license="project",
             notes="28 cm long, lying flat along +X, wooden handle at the origin: hold(trowel, 'R', t)")


def build_asset():
    parts = []
    parts.append(build.box("trowel.handle", (0.11, 0.032, 0.032), (0, 0, 0), "oak_planks"))
    parts.append(build.box("trowel.ferrule", (0.02, 0.036, 0.036), (0.06, 0, -0.002), "steel_bright"))
    parts.append(build.box("trowel.neck", (0.05, 0.014, 0.014), (0.09, 0, 0.002), "iron_dark"))
    for i in range(5):      # the blade: a pointed leaf made of narrowing slabs
        parts.append(build.box(f"trowel.blade{i}", (0.03, 0.075 - 0.014 * i, 0.006), (0.125 + 0.027 * i, 0, 0), "steel_bright", bevel=0.002))
    return build.group("prop_archaeologist_trowel", parts)
