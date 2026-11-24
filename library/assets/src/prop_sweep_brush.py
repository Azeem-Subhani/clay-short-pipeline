"""A chimney sweep's flue brush: a round head of stiff black bristles on a rod."""
import math

from stagekit import build

ASSET = dict(id="prop_sweep_brush", name="Chimney sweep's brush", kind="prop", tags=["brush", "chimney", "sweep", "flue brush", "soot", "broom"],
             era=["renaissance", "age_of_sail", "victorian"], source="built", license="project",
             notes="1.1 m long, stands on its brush head on z = 0, rod up. Hold the rod about 0.75 m up, head down as on the sheet: "
                   "hold(brush, 'R', t, offset=(0, 0, -0.75)); turn=True to shoulder it head up.")


def build_asset():
    soot = "#2E2622"
    parts = [
        build.cyl("brush.rod", 0.016, 0.96, (0, 0, 0.14), "oak_planks", seg=10),
        build.cyl("brush.ferrule", 0.022, 0.07, (0, 0, 0.12), "iron_dark", seg=10),
        build.cyl("brush.core", 0.03, 0.14, (0, 0, 0.02), soot, seg=10),
        build.cyl("brush.disc", 0.135, 0.035, (0, 0, 0.07), soot, top_radius=0.12, seg=20),
    ]
    for k in range(12):          # bristle tufts round the head: a spiky silhouette
        a = math.tau * k / 12
        tuft = build.cyl(f"brush.tuft{k}", 0.02, 0.17, (0, 0, 0.0875), soot, top_radius=0.006, seg=6)
        tuft.rotation_euler = (0.0, math.radians(90), a)
        parts.append(tuft)
    return build.group("prop_sweep_brush", parts)
