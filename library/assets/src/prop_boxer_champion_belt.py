"""Boxer's championship belt: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_boxer_champion_belt.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_boxer_champion_belt", name="Championship belt with a gold plate", kind="prop", tags=['belt', 'boxing', 'champion', 'trophy', 'prize'],
             era=['modern'], source="built", license="project",
             notes="70 cm wide strap standing on its edge, plate toward -Y; hold it up with both hands at the plate or lay it over a shoulder")


def build_asset():
    parts = []
    parts.append(build.box("belt.strap", (0.70, 0.012, 0.11), (0, 0, 0.03), "#8E2B2B", bevel=0.005))
    parts.append(build.box("belt.plate", (0.16, 0.014, 0.17), (0, -0.008, 0.0), "gold", bevel=0.03))
    parts.append(build.ball("belt.gem", 0.024, (0, -0.03, 0.061), "#C8302C", squash=(1, 0.5, 1)))
    for sx in (-1, 1):
        parts.append(build.box(f"belt.side{sx}", (0.07, 0.008, 0.07), (sx * 0.16, -0.008, 0.05), "gold", bevel=0.006))
        parts.append(build.box(f"belt.tip{sx}", (0.02, 0.014, 0.09), (sx * 0.345, 0, 0.04), "#2B1B1B", bevel=0.003))
    return build.group("prop_boxer_champion_belt", parts)
