"""An old iron hand lantern with a glowing pale-green pane, a peaked cap and a ring handle."""
import math

from stagekit import build, core

ASSET = dict(id="prop_ghost_lantern", name="Ghost lantern", kind="prop", tags=["lantern", "ghost", "light", "haunted", "night", "lamp"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.35 m tall, stands on its base; carry it by the ring: ghost.hold(lantern, 'R', t, offset=(0, 0, -0.32)); add a small light in the shot for the glow")


def build_asset():
    P = "ghostlantern."
    base = build.cyl(P + "base", 0.075, 0.03, (0, 0, 0), "iron_dark", seg=8)
    glow = build.cyl(P + "glow", 0.055, 0.16, (0, 0, 0.03), "#CFF5C8", seg=8)
    parts = [base, glow]
    for i in range(4):
        a = math.tau * i / 4 + math.pi / 4
        parts.append(build.box(P + f"post{i}", (0.016, 0.016, 0.16), (0.058 * math.cos(a), 0.058 * math.sin(a), 0.03), "iron_dark", bevel=0.003))
    parts.append(build.cyl(P + "rim", 0.075, 0.02, (0, 0, 0.19), "iron_dark", seg=8))
    parts.append(build.cyl(P + "cap", 0.07, 0.07, (0, 0, 0.21), "iron_dark", top_radius=0.015, seg=8))
    parts.append(build.ball(P + "ring", 0.032, (0, 0, 0.275), "iron_dark", squash=(1, 0.35, 1)))
    parts.append(build.ball(P + "ringhole", 0.018, (0, 0, 0.289), "#CFF5C8", squash=(1, 0.75, 1)))
    return build.group("prop_ghost_lantern", parts)
