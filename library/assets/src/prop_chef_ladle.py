"""A steel soup ladle with a wooden grip (signature prop of the Chef).

    python tools/clip.py asset library/assets/src/prop_chef_ladle.py --no-save     preview only
"""
from stagekit import build

ASSET = dict(id="prop_chef_ladle", name="Chef's ladle", kind="prop", tags=["ladle", "spoon", "chef", "cook", "kitchen", "soup"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "modern", "fantasy"], source="built", license="project",
             notes="0.41 m tall, standing on its bowl, wooden grip at the top; hold the grip: "
                   "chef.hold(ladle, 'R', t, offset=(0, 0, -0.32)); turn=True to stir or taste")


def build_asset():
    bowl = build.cyl("ladle.bowl", 0.035, 0.05, (0.045, 0, 0), "steel_bright", top_radius=0.058, seg=18)
    inside = build.cyl("ladle.inside", 0.050, 0.004, (0.045, 0, 0.049), "#6E7378", seg=18)
    neck = build.box("ladle.neck", (0.06, 0.016, 0.012), (0.0, 0, 0.04), "steel_bright", bevel=0.004)
    stem = build.cyl("ladle.stem", 0.008, 0.22, (-0.025, 0, 0.04), "steel_bright", seg=10)
    grip = build.cyl("ladle.grip", 0.015, 0.14, (-0.025, 0, 0.25), "oak_planks", seg=12)
    cap = build.ball("ladle.cap", 0.017, (-0.025, 0, 0.38), "oak_planks")
    return build.group("prop_chef_ladle", [bowl, inside, neck, stem, grip, cap])
