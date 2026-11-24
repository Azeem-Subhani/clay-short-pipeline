"""A wooden walking cane with a crook handle and a brass ferrule: an old person's stick, or a gentleman's cane."""
from stagekit import build

ASSET = dict(id="prop_walking_cane", name="Walking cane", kind="prop", tags=["cane", "walking stick", "old", "elderly", "gentleman", "stick"],
             era=["renaissance", "age_of_sail", "victorian", "modern", "fantasy"], source="built", license="project",
             notes="0.82 m tall, crook toward +X. Hold it by the crook: granny.hold(cane, 'R', t, offset=(0, 0, -0.80)); keep the tip on the ground while walking.")


def build_asset():
    parts = [build.cyl("cane.tip", 0.014, 0.04, (0, 0, 0), "gold", seg=10),
             build.cyl("cane.shaft", 0.013, 0.76, (0, 0, 0.04), "dark_timber", top_radius=0.015, seg=10),
             build.box("cane.top", (0.12, 0.03, 0.03), (0.045, 0, 0.79), "dark_timber", bevel=0.012),
             build.box("cane.hook", (0.03, 0.03, 0.07), (0.09, 0, 0.73), "dark_timber", bevel=0.012)]
    return build.group("prop_walking_cane", parts)
