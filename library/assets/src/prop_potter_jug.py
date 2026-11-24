"""Potter's clay jug: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_potter_jug.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_potter_jug", name="Potter's clay jug", kind="prop", tags=['jug', 'pot', 'clay', 'pottery', 'pitcher', 'vase'],
             era=['ancient', 'medieval', 'renaissance', 'age_of_sail', 'victorian', 'fantasy'], source="built", license="project",
             notes="24 cm tall terracotta jug with one handle toward +X; origin at the base centre: hold(jug, 'L', t) or carry it with both hands")


def build_asset():
    parts = []
    parts.append(build.cyl("jug.foot", 0.05, 0.02, (0, 0, 0), "terracotta", seg=24))
    parts.append(build.ball("jug.belly", 0.085, (0, 0, 0.01), "terracotta", squash=(1, 1, 0.95)))
    parts.append(build.cyl("jug.neck", 0.045, 0.07, (0, 0, 0.15), "terracotta", top_radius=0.04, seg=24))
    parts.append(build.cyl("jug.lip", 0.05, 0.016, (0, 0, 0.215), "terracotta", top_radius=0.054, seg=24))
    parts.append(build.cyl("jug.mouth", 0.04, 0.004, (0, 0, 0.229), "#3A2016", seg=24))
    parts.append(build.box("jug.handle", (0.016, 0.026, 0.09), (0.105, 0, 0.1), "terracotta", bevel=0.005))
    for z in (0.1, 0.176):
        parts.append(build.box(f"jug.arm{z}", (0.06, 0.026, 0.016), (0.075, 0, z), "terracotta", bevel=0.005))
    return build.group("prop_potter_jug", parts)
