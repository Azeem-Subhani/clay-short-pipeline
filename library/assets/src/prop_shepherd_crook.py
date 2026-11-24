"""A shepherd's crook: a tall wooden staff with a round hook at the top."""
import math

from stagekit import build

ASSET = dict(id="prop_shepherd_crook", name="Shepherd's crook", kind="prop", tags=["crook", "staff", "shepherd", "stick", "walking stick"],
             era=["ancient", "medieval", "renaissance", "fantasy"], source="built", license="project",
             notes="1.65 m tall, stands on z = 0, hook opens toward +X. Hold it about 1.0 m up: "
                   "shepherd.hold(crook, 'R', t, offset=(0, 0, -1.0)).")


def build_asset():
    parts = [build.cyl("crook.shaft", 0.022, 1.42, (0, 0, 0), "oak_planks", top_radius=0.019, seg=12),
             build.cyl("crook.foot", 0.025, 0.05, (0, 0, 0), "iron_dark", seg=12)]
    # the hook: short straight pieces round a circle of radius 0.10 centred beside the shaft top
    r, cx, cz, n = 0.10, 0.10, 1.42, 9
    pts = [(cx - r * math.cos(math.radians(a)), cz + r * math.sin(math.radians(a))) for a in [225 * k / n for k in range(n + 1)]]
    for k in range(n):
        (x0, z0), (x1, z1) = pts[k], pts[k + 1]
        seg = build.cyl(f"crook.hook{k}", 0.019, math.hypot(x1 - x0, z1 - z0) + 0.008, (x0, 0, z0), "oak_planks", top_radius=0.018, seg=10)
        seg.rotation_euler.y = math.atan2(x1 - x0, z1 - z0)
        parts.append(seg)
    parts.append(build.ball("crook.tip", 0.024, (pts[-1][0], 0, pts[-1][1] - 0.024), "oak_planks"))
    return build.group("prop_shepherd_crook", parts)
