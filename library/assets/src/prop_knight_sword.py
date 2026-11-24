"""A knight's arming sword: broad steel blade, gold cross-guard and pommel, leather grip."""
import math

from stagekit import build

ASSET = dict(id="prop_knight_sword", name="Knight's sword", kind="prop", tags=['sword', 'blade', 'knight', 'prince', 'weapon', 'duel'],
             era=['medieval', 'renaissance', 'fantasy'], source="built", license="project",
             notes="0.93 m long, standing on the pommel, blade up; hold it 0.10 m up: knight.hold(sword, 'R', t, offset=(0, 0, -0.10)); the flat faces -Y")


def build_asset():
    tip = build.box("sword.tip", (0.05, 0.016, 0.05), (0, 0, 0), "steel_bright", bevel=0.005)
    tip.rotation_euler.y = math.radians(45)
    tip.location = (-0.018, 0, 0.84)
    parts = [
        build.ball("sword.pommel", 0.032, (0, 0, 0), "gold"),
        build.cyl("sword.grip", 0.02, 0.14, (0, 0, 0.05), "#5B3A22", seg=10),
        build.box("sword.guard", (0.24, 0.04, 0.035), (0, 0, 0.18), "gold", bevel=0.01),
        build.box("sword.blade", (0.07, 0.016, 0.65), (0, 0, 0.21), "steel_bright", bevel=0.005),
        build.box("sword.fuller", (0.014, 0.02, 0.50), (0, 0, 0.24), "#8E9296", bevel=0.002),
        tip,
    ]
    return build.group("prop_knight_sword", parts)
