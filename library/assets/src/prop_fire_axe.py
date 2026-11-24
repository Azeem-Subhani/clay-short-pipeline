"""A firefighter's axe: red-painted head with a steel edge and a pick, on a wooden handle. Grip point at the origin."""
from stagekit import build

ASSET = dict(id="prop_fire_axe", name="Firefighter's axe", kind="prop", tags=["axe", "fire", "firefighter", "tool", "rescue"],
             era=["modern"], source="built", license="project",
             notes="0.9 m long, standing on its handle end; hold it 0.35 m up: firefighter.hold(axe, 'R', t, offset=(0, 0, -0.35)); "
                   "the blade points +X")


def build_asset():
    parts = [
        build.cyl("axe.handle", 0.022, 0.86, (0, 0, 0), "oak_planks", seg=10),
        build.cyl("axe.grip", 0.026, 0.16, (0, 0, 0), "#B8463C", seg=10),
        build.box("axe.head", (0.11, 0.045, 0.11), (0.0, 0, 0.74), "#B8463C", bevel=0.01),
        build.box("axe.blade", (0.11, 0.03, 0.17), (0.10, 0, 0.71), "#B8463C", bevel=0.012),
        build.box("axe.edge", (0.035, 0.022, 0.19), (0.165, 0, 0.70), "steel_bright", bevel=0.008),
        build.box("axe.pick", (0.10, 0.03, 0.05), (-0.09, 0, 0.77), "steel_bright", bevel=0.012),
    ]
    return build.group("prop_fire_axe", parts)
