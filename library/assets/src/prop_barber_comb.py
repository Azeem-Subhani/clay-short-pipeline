"""Barber's comb: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_barber_comb.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_barber_comb", name="Barber's comb", kind="prop", tags=['comb', 'barber', 'hair', 'grooming'],
             era=['victorian', 'modern'], source="built", license="project",
             notes="18 cm long comb lying flat along X, teeth toward -Y; origin at the middle of the spine: hold(comb, 'L', t)")


def build_asset():
    parts = []
    parts.append(build.box("comb.spine", (0.18, 0.014, 0.006), (0, 0.012, 0), "#2E2A2A", bevel=0.002))
    for i in range(18):
        parts.append(build.box(f"comb.tooth{i}", (0.005, 0.026, 0.005), (-0.085 + 0.01 * i, -0.007, 0), "#2E2A2A", bevel=0.001))
    return build.group("prop_barber_comb", parts)
