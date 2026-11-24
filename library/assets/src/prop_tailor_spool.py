"""Spool of thread with a needle: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_tailor_spool.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_tailor_spool", name="Spool of thread with a needle", kind="prop", tags=['spool', 'thread', 'needle', 'sewing', 'tailor'],
             era=['medieval', 'renaissance', 'age_of_sail', 'victorian', 'fantasy', 'modern'], source="built", license="project",
             notes="chunky 9 cm tall wooden spool of red thread standing upright, a needle stuck in the top; origin at its base centre")


def build_asset():
    parts = []
    parts.append(build.cyl("spool.foot", 0.04, 0.012, (0, 0, 0), "oak_planks", seg=24))
    parts.append(build.cyl("spool.thread", 0.03, 0.062, (0, 0, 0.012), "#B8402E", seg=24))
    parts.append(build.cyl("spool.top", 0.04, 0.012, (0, 0, 0.074), "oak_planks", seg=24))
    needle = build.cyl("spool.needle", 0.0025, 0.07, (0.012, 0, 0.07), "steel_bright", seg=8)
    needle.rotation_euler.y = math.radians(28)
    parts.append(needle)
    return build.group("prop_tailor_spool", parts)
