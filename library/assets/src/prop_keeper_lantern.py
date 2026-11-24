"""A storm lantern: iron base and cap, a glowing amber glass and a carrying handle on top."""
import math

from stagekit import build

ASSET = dict(id="prop_keeper_lantern", name="Storm lantern", kind="prop", tags=['lantern', 'lamp', 'light', 'lighthouse', 'night', 'keeper'],
             era=['medieval', 'renaissance', 'age_of_sail', 'victorian', 'fantasy'], source="built", license="project",
             notes="0.35 m tall with the handle, resting on z = 0; carry it by the handle: keeper.hold(lantern, 'R', t, offset=(0, 0, -0.33)); add a point light at (0, 0, 0.12) for a lit lantern")


def build_asset():
    parts = [
        build.cyl("lantern.base", 0.07, 0.04, (0, 0, 0), "iron_dark", seg=14),
        build.cyl("lantern.glass", 0.055, 0.15, (0, 0, 0.04), "#F2C65A", seg=14),
        build.cyl("lantern.cap", 0.07, 0.06, (0, 0, 0.19), "iron_dark", top_radius=0.02, seg=14),
        build.cyl("lantern.vent", 0.025, 0.03, (0, 0, 0.25), "iron_dark", seg=10),
        build.box("lantern.handle_top", (0.085, 0.014, 0.014), (0, 0, 0.335), "iron_dark", bevel=0.004),
    ]
    for sx in (-1, 1):
        parts.append(build.box(f"lantern.bar{sx}", (0.012, 0.012, 0.17), (sx * 0.06, 0, 0.03), "iron_dark", bevel=0.003))
        parts.append(build.box(f"lantern.handle{sx}", (0.012, 0.012, 0.08), (sx * 0.036, 0, 0.265), "iron_dark", bevel=0.003))
    return build.group("prop_keeper_lantern", parts)
