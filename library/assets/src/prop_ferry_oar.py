"""A ferryman's oar: a long shaft with a broad wooden blade, stood on its blade."""
from stagekit import build

ASSET = dict(id="prop_ferry_oar", name="Ferryman's oar", kind="prop", tags=["oar", "paddle", "ferry", "boat", "row", "river"],
             era=["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="1.7 m tall, stands blade down on z = 0, blade flat toward -Y (the camera). Hold the shaft about 1.0 m up: "
                   "hold(oar, 'R', t, offset=(0, 0, -1.0)). For rowing, turn it in the hand (turn=True).")


def build_asset():
    wood = "oak_planks"
    parts = [
        build.box("oar.blade", (0.15, 0.028, 0.50), (0, 0, 0.0), wood, bevel=0.02),
        build.box("oar.blade_neck", (0.09, 0.03, 0.12), (0, 0, 0.47), wood, bevel=0.02),
        build.box("oar.rib", (0.02, 0.04, 0.44), (0, 0, 0.04), wood, bevel=0.008),
        build.cyl("oar.shaft", 0.024, 1.10, (0, 0, 0.55), wood, top_radius=0.021, seg=12),
        build.cyl("oar.collar", 0.03, 0.06, (0, 0, 1.05), "rope", seg=12),
        build.cyl("oar.grip", 0.019, 0.10, (0, 0, 1.62), wood, top_radius=0.024, seg=12),
    ]
    return build.group("prop_ferry_oar", parts)
