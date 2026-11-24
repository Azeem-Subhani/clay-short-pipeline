"""Pewter tankard of ale: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_innkeeper_tankard.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_innkeeper_tankard", name="Pewter tankard of ale", kind="prop", tags=['tankard', 'mug', 'ale', 'beer', 'inn', 'tavern', 'drink'],
             era=['medieval', 'renaissance', 'age_of_sail', 'victorian', 'fantasy'], source="built", license="project",
             notes="15 cm tall tankard with foam, handle toward +X; origin at the base centre: hold(tankard, 'R', t)")


def build_asset():
    parts = []
    parts.append(build.cyl("tankard.body", 0.05, 0.14, (0, 0, 0), "steel_bright", top_radius=0.044, seg=24))
    parts.append(build.cyl("tankard.foot", 0.054, 0.014, (0, 0, 0), "iron_dark", seg=24))
    parts.append(build.cyl("tankard.rim", 0.047, 0.012, (0, 0, 0.132), "iron_dark", seg=24))
    parts.append(build.ball("tankard.foam", 0.043, (0, 0, 0.125), "#FBF4E2", squash=(1, 1, 0.5)))
    parts.append(build.box("tankard.handle", (0.014, 0.02, 0.085), (0.078, 0, 0.03), "steel_bright", bevel=0.004))
    for z in (0.03, 0.103):
        parts.append(build.box(f"tankard.arm{z}", (0.04, 0.02, 0.014), (0.06, 0, z), "steel_bright", bevel=0.004))
    return build.group("prop_innkeeper_tankard", parts)
