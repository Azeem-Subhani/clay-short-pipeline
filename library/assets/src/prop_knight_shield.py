"""A knight's shield: blue field with a cream cross and a gold boss, steel rim, strap on the back."""
import math

from stagekit import build

ASSET = dict(id="prop_knight_shield", name="Knight's shield", kind="prop", tags=['shield', 'knight', 'armour', 'heraldry', 'guard'],
             era=['medieval', 'renaissance', 'fantasy'], source="built", license="project",
             notes="0.5 m wide, 0.62 m tall, standing on its rounded lower edge, face toward -Y; hold it by the back strap: knight.hold(shield, 'L', t, offset=(0, -0.05, -0.34))")


def build_asset():
    parts = [
        build.box("shield.rim", (0.48, 0.035, 0.62), (0, 0, 0.0), "steel_bright", bevel=0.11),
        build.box("shield.field", (0.42, 0.04, 0.56), (0, -0.006, 0.03), "#3F5584", bevel=0.09),
        build.box("shield.cross_v", (0.07, 0.02, 0.50), (0, -0.024, 0.06), "#F1E3C4", bevel=0.004),
        build.box("shield.cross_h", (0.36, 0.02, 0.07), (0, -0.024, 0.38), "#F1E3C4", bevel=0.004),
        build.ball("shield.boss", 0.045, (0, -0.07, 0.37), "gold", squash=(1, 0.6, 1)),
        build.box("shield.strap", (0.16, 0.02, 0.04), (0, 0.03, 0.32), "#5B3A22", bevel=0.004),
    ]
    return build.group("prop_knight_shield", parts)
