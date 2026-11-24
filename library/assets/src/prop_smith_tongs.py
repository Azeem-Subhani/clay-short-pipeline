"""Blacksmith's tongs: two long iron arms crossing at a rivet, short flat jaws."""
import math

from stagekit import build

ASSET = dict(id="prop_smith_tongs", name="Blacksmith's tongs", kind="prop", tags=["tongs", "blacksmith", "forge", "tool", "iron"],
             era=["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.55 m long, standing on the handle ends, jaws on top. Hold it 0.15 m up: smith.hold(tongs, 'L', t, offset=(0, 0, -0.15)).")


def build_asset():
    parts = []
    for sx in (-1, 1):
        arm = build.box(f"tongs.arm{sx}", (0.018, 0.014, 0.42), (sx * 0.03, 0, 0), "iron_dark", bevel=0.004)
        arm.rotation_euler.y = math.radians(-8 * sx)
        jaw = build.box(f"tongs.jaw{sx}", (0.018, 0.02, 0.14), (-sx * 0.028, 0, 0.41), "iron_dark", bevel=0.004)
        jaw.rotation_euler.y = math.radians(9 * sx)
        parts += [arm, jaw]
    riv = build.cyl("tongs.rivet", 0.018, 0.03, (0, 0.015, 0.41), "steel_bright", seg=10)
    riv.rotation_euler.x = math.radians(90)
    parts.append(riv)
    return build.group("prop_smith_tongs", parts)
