"""A blacksmith's forging hammer: a short oak handle and a heavy square iron head."""
from stagekit import build

ASSET = dict(id="prop_smith_hammer", name="Blacksmith's hammer", kind="prop", tags=["hammer", "blacksmith", "forge", "tool", "iron"],
             era=["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.41 m long, standing on its handle end, head on top. Hold it low on the handle: smith.hold(hammer, 'R', t, offset=(0, 0, -0.10)); turn=True to swing it.")


def build_asset():
    parts = [build.cyl("hammer.handle", 0.02, 0.36, (0, 0, 0), "oak_planks", top_radius=0.017, seg=12),
             build.cyl("hammer.butt", 0.024, 0.03, (0, 0, 0), "oak_planks", seg=12),
             build.box("hammer.head", (0.17, 0.075, 0.075), (0, 0, 0.33), "iron_dark", bevel=0.01),
             build.box("hammer.face", (0.02, 0.085, 0.085), (0.085, 0, 0.325), "steel_bright", bevel=0.006)]
    return build.group("prop_smith_hammer", parts)
