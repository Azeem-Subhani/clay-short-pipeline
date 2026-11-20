"""Small wire cutters, hero prop (held at the frame edge in a close-up). Jaws point toward +X; grips toward -X."""
import math

from stagekit import build

ASSET = dict(id="prop_wire_cutters", name="Wire cutters", kind="prop", tags=["tool", "cutters", "pliers", "wire", "metal"],
             notes="0.18 m long, lies flat. Jaws at +X. Hold it by the grips; rotate the group, the jaws are fixed slightly open.")


def build_asset():
    steel = build.clay("#8D9299", rough=0.35, metallic=0.85, bump=0.004)
    grip = "#B5362E"
    parts = []
    for sgn in (1, -1):
        jaw = build.box(f"jaw{sgn}", (0.06, 0.012, 0.012), (0.03, sgn * 0.006, 0.004), material=steel, bevel=0.003)
        jaw.rotation_euler.z = math.radians(sgn * 7)
        arm = build.box(f"arm{sgn}", (0.11, 0.014, 0.014), (-0.055, sgn * 0.016, 0.003), grip, bevel=0.005)
        arm.rotation_euler.z = math.radians(-sgn * 9)
        parts += [jaw, arm]
    parts.append(build.cyl("pivot", 0.011, 0.02, (0, 0, 0), material=steel, segments=16, bevel=0.002))
    return build.group("prop_wire_cutters", parts)
