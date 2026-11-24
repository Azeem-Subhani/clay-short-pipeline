"""A blue plastic pet carrier with a barred door, air slots and a top handle."""
import math

from stagekit import build, core

ASSET = dict(id="prop_vet_pet_carrier", name="Pet carrier", kind="prop", tags=["pet carrier", "vet", "cat", "dog", "animal", "box", "cage"],
             era=["modern"], source="built", license="project",
             notes="0.46 x 0.30 x 0.35 m, barred door toward -Y; carry it by the top handle: vet.hold(carrier, 'R', t, offset=(0, 0, -0.33))")


def build_asset():
    P = "carrier."
    base = build.box(P + "base", (0.46, 0.30, 0.13), (0, 0, 0), "#5E7FB8", bevel=0.03)
    top = build.box(P + "top", (0.44, 0.28, 0.16), (0, 0, 0.13), "#86A6D8", bevel=0.05)
    seam = build.box(P + "seam", (0.47, 0.31, 0.02), (0, 0, 0.12), "#44608F", bevel=0.006)
    door = build.box(P + "door", (0.24, 0.012, 0.18), (0, -0.147, 0.05), "#22262E", bevel=0.004)
    parts = [base, top, seam, door]
    for i in range(6):
        parts.append(build.box(P + f"bar{i}", (0.012, 0.014, 0.18), (-0.10 + 0.04 * i, -0.155, 0.05), "steel_bright", bevel=0.004))
    for sx in (-1, 1):
        parts.append(build.box(P + f"hpost{sx}", (0.025, 0.03, 0.05), (sx * 0.07, 0, 0.285), "#44608F", bevel=0.008))
    parts.append(build.box(P + "handle", (0.19, 0.035, 0.03), (0, 0, 0.32), "#44608F", bevel=0.012))
    return build.group("prop_vet_pet_carrier", parts)
