"""A cobbler's work piece: one brown leather ankle boot with a dark sole, a heel and laces."""
from stagekit import build

ASSET = dict(id="prop_cobbler_boot", name="Leather boot (cobbler's work piece)", kind="prop", tags=["boot", "shoe", "cobbler", "leather", "footwear"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.27 m long, 0.24 m tall, stands on z = 0, toe toward +X. Drawn a little large so it reads in the hand. "
                   "Hold it under the sole: hold(boot, 'R', t, offset=(0, 0, 0.02)).")


def build_asset():
    leather, sole = "#7A5236", "#3E2C24"
    parts = [
        build.box("boot.sole", (0.27, 0.10, 0.022), (0.035, 0, 0), sole, bevel=0.008),
        build.box("boot.heel", (0.085, 0.095, 0.03), (-0.055, 0, -0.0), sole, bevel=0.006),
        build.ball("boot.toe", 0.055, (0.11, 0, 0.018), leather, squash=(1.15, 0.85, 0.78)),
        build.box("boot.vamp", (0.15, 0.092, 0.075), (0.02, 0, 0.02), leather, bevel=0.025),
        build.cyl("boot.shaft", 0.052, 0.17, (-0.05, 0, 0.05), leather, top_radius=0.056, seg=16),
        build.cyl("boot.cuff", 0.06, 0.03, (-0.05, 0, 0.205), "#8E6344", seg=16),
        build.cyl("boot.inside", 0.047, 0.006, (-0.05, 0, 0.232), "#2E211B", seg=16),
    ]
    for k in range(3):       # laces across the front of the shaft
        parts.append(build.box(f"boot.lace{k}", (0.012, 0.06, 0.012), (0.004, 0, 0.10 + 0.035 * k), "#E8D9B8", bevel=0.003))
    return build.group("prop_cobbler_boot", parts)
