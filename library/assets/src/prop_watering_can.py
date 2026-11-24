"""A gardener's tin watering can with a spout, a rose and a carrying handle."""
import math

from stagekit import build

ASSET = dict(id="prop_watering_can", name="Tin watering can", kind="prop", tags=["watering can", "garden", "gardener", "water", "tin"],
             era=["victorian", "modern", "fantasy"], source="built", license="project",
             notes="0.36 m tall, spout toward +X. Carry it by the top handle: gardener.hold(can, 'R', t, offset=(0, 0, -0.36)); tilt it about Y to pour.")


def build_asset():
    parts = [build.cyl("can.body", 0.11, 0.24, (0, 0, 0), "steel_bright", top_radius=0.095, seg=20),
             build.cyl("can.rim", 0.10, 0.02, (0, 0, 0.24), "iron_dark", seg=20)]
    spout = build.cyl("can.spout", 0.028, 0.30, (0.08, 0, 0.06), "steel_bright", top_radius=0.018, seg=12)
    spout.rotation_euler.y = math.radians(55)
    rose = build.cyl("can.rose", 0.02, 0.04, (0.325, 0, 0.232), "iron_dark", top_radius=0.05, seg=14)
    rose.rotation_euler.y = math.radians(55)
    parts += [spout, rose]
    # carrying handle over the top, and a grip at the back
    for sx in (-1, 1):
        parts.append(build.box(f"can.h{sx}", (0.02, 0.03, 0.12), (sx * 0.07, 0, 0.24), "iron_dark", bevel=0.004))
    parts.append(build.box("can.htop", (0.16, 0.03, 0.02), (0, 0, 0.35), "iron_dark", bevel=0.004))
    parts.append(build.box("can.back", (0.02, 0.03, 0.16), (-0.15, 0, 0.05), "iron_dark", bevel=0.004))
    for i, z in enumerate((0.05, 0.19)):
        parts.append(build.box(f"can.back{i}", (0.05, 0.03, 0.02), (-0.125, 0, z), "iron_dark", bevel=0.004))
    return build.group("prop_watering_can", parts)
