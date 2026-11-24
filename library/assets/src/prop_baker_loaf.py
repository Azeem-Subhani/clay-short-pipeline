"""Crusty bread loaf: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_baker_loaf.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_baker_loaf", name="Crusty bread loaf", kind="prop", tags=['bread', 'loaf', 'baker', 'food', 'bakery'],
             era=['ancient', 'medieval', 'renaissance', 'age_of_sail', 'victorian', 'fantasy', 'modern'], source="built", license="project",
             notes="30 cm oval loaf with three slashes, lying along X; origin at its base centre: carry it with both hands or hold(loaf, 'L', t)")


def build_asset():
    parts = []
    parts.append(build.ball("loaf.body", 0.10, (0, 0, 0), "#C98A45", squash=(1.5, 0.95, 0.72)))
    for i, x in enumerate((-0.07, 0.0, 0.07)):
        cut = build.box(f"loaf.slash{i}", (0.016, 0.11, 0.012), (x, 0, 0.136 - 0.012 * abs(i - 1)), "#EAC98E", bevel=0.004)
        cut.rotation_euler.z = math.radians(28)
        parts.append(cut)
    return build.group("prop_baker_loaf", parts)
