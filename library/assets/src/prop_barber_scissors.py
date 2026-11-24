"""Barber's scissors: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_barber_scissors.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_barber_scissors", name="Barber's scissors", kind="prop", tags=['scissors', 'shears', 'barber', 'cut', 'hair'],
             era=['victorian', 'modern'], source="built", license="project",
             notes="17 cm long, slightly open, lying flat along +X; finger rings at the origin: hold(scissors, 'R', t)")


def build_asset():
    parts = []
    for sg in (-1, 1):
        blade = build.box(f"scissors.blade{sg}", (0.12, 0.014, 0.004), (0.09, 0, 0.004 + 0.002 * sg), "steel_bright", bevel=0.001)
        blade.rotation_euler.z = math.radians(7 * sg)
        parts.append(blade)
        parts.append(build.cyl(f"scissors.ring{sg}", 0.017, 0.006, (-0.012, -0.02 * sg, 0.002), "steel_bright", seg=18))
        parts.append(build.cyl(f"scissors.hole{sg}", 0.010, 0.007, (-0.012, -0.02 * sg, 0.002), "#2B2B30", seg=18))
        arm = build.box(f"scissors.arm{sg}", (0.04, 0.008, 0.004), (0.012, -0.01 * sg, 0.003), "steel_bright", bevel=0.001)
        arm.rotation_euler.z = math.radians(22 * sg)
        parts.append(arm)
    parts.append(build.cyl("scissors.pivot", 0.006, 0.012, (0.032, 0, 0), "iron_dark", seg=12))
    return build.group("prop_barber_scissors", parts)
