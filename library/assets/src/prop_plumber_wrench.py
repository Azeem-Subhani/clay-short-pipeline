"""Plumber's wrench: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_plumber_wrench.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_plumber_wrench", name="Open-ended steel wrench", kind="prop", tags=['wrench', 'spanner', 'tool', 'plumber', 'mechanic'],
             era=['victorian', 'modern'], source="built", license="project",
             notes="31 cm tall, jaw up, stands on z = 0; grip the handle 10 cm up: hold(wrench, 'R', t, offset=(0, 0, -0.10))")


def build_asset():
    parts = []
    parts.append(build.box("wrench.handle", (0.028, 0.012, 0.22), (0, 0, -0.08), "steel_bright", bevel=0.004))
    parts.append(build.box("wrench.end", (0.04, 0.013, 0.03), (0, 0, -0.095), "steel_bright", bevel=0.006))
    parts.append(build.box("wrench.head", (0.07, 0.014, 0.035), (0, 0, 0.135), "steel_bright", bevel=0.005))
    for sx in (-1, 1):
        parts.append(build.box(f"wrench.jaw{sx}", (0.022, 0.014, 0.05), (sx * 0.024, 0, 0.165), "steel_bright", bevel=0.005))
    for ob in parts:      # stand it on z = 0 (the grip is 0.095 m up)
        ob.location.z += 0.095
    return build.group("prop_plumber_wrench", parts)
