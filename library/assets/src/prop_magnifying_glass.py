"""A detective's magnifying glass: a brass ring with a pale lens on a turned dark handle."""
import math

from stagekit import build

ASSET = dict(id="prop_magnifying_glass", name="Magnifying glass", kind="prop", tags=["magnifying glass", "detective", "lens", "clue", "search"],
             era=["victorian", "modern"], source="built", license="project",
             notes="0.27 m long, standing on the handle end, lens facing -Y (the camera). Hold the handle: detective.hold(glass, 'R', t, offset=(0, 0, -0.05)).")


def build_asset():
    parts = [build.cyl("glass.handle", 0.016, 0.12, (0, 0, 0), "dark_timber", top_radius=0.012, seg=12),
             build.cyl("glass.ferrule", 0.015, 0.02, (0, 0, 0.115), "gold", seg=12)]
    ring = build.cyl("glass.ring", 0.075, 0.016, (0, 0.008, 0.195), "gold", seg=28)
    ring.rotation_euler.x = math.radians(90)
    lens = build.cyl("glass.lens", 0.063, 0.02, (0, 0.010, 0.195), "#CFE6EE", seg=28)
    lens.rotation_euler.x = math.radians(90)
    parts += [ring, lens]
    return build.group("prop_magnifying_glass", parts)
