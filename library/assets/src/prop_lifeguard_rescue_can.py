"""A red lifeguard rescue can (torpedo buoy) with side handles and a coiled white rope."""
import math

from stagekit import build, core

ASSET = dict(id="prop_lifeguard_rescue_can", name="Lifeguard rescue can", kind="prop", tags=["rescue", "buoy", "lifeguard", "beach", "float", "can"],
             era=["modern"], source="built", license="project",
             notes="0.70 m long, lying along X on the ground; carry it by a side handle: lifeguard.hold(can, 'R', t, offset=(0, 0.13, -0.09))")


def build_asset():
    P = "rescuecan."
    body = build.ball(P + "body", 0.10, (0, 0, 0), "#D7392F", squash=(3.0, 1.25, 0.85), subdiv=3)
    parts = [body]
    for sy in (-1, 1):
        parts.append(build.box(P + f"handle{sy}", (0.34, 0.03, 0.035), (0, sy * 0.135, 0.07), "#B32B24", bevel=0.012))
        for sx in (-1, 1):
            parts.append(build.box(P + f"lug{sx}{sy}", (0.04, 0.05, 0.035), (sx * 0.16, sy * 0.115, 0.07), "#B32B24", bevel=0.01))
    parts.append(build.cyl(P + "ropecoil", 0.07, 0.03, (-0.40, 0, 0), "rope", seg=16))
    parts.append(build.cyl(P + "ropecoil2", 0.05, 0.025, (-0.40, 0, 0.03), "rope", seg=16))
    return build.group("prop_lifeguard_rescue_can", parts)
