"""Gamer's controller: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_game_controller.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_game_controller", name="Video game controller", kind="prop", tags=['controller', 'gamepad', 'gamer', 'video game', 'console'],
             era=['modern'], source="built", license="project",
             notes="15 cm wide, lying flat, grips toward -Y; hold(pad, 'R', t) or both hands at the grips")


def build_asset():
    parts = []
    parts.append(build.box("pad.body", (0.11, 0.055, 0.026), (0, 0, 0.0), "#2E2A32", bevel=0.01))
    for sx in (-1, 1):
        parts.append(build.ball(f"pad.grip{sx}", 0.03, (sx * 0.055, -0.022, 0.0), "#2E2A32", squash=(0.85, 1.45, 0.5)))
        parts.append(build.cyl(f"pad.stick{sx}", 0.009, 0.012, (sx * 0.022, -0.012, 0.026), "#55515C", seg=10))
    parts.append(build.box("pad.dpad_a", (0.024, 0.008, 0.004), (-0.04, 0.008, 0.026), "#E8E4D8", bevel=0.001))
    parts.append(build.box("pad.dpad_b", (0.008, 0.024, 0.004), (-0.04, 0.008, 0.026), "#E8E4D8", bevel=0.001))
    for i, c in enumerate(("#C8302C", "#F2C94C", "#4E6EA6", "#6FAE8E")):
        a = math.tau * i / 4
        parts.append(build.cyl(f"pad.btn{i}", 0.005, 0.005, (0.04 + 0.011 * math.cos(a), 0.008 + 0.011 * math.sin(a), 0.026), c, seg=8))
    return build.group("prop_game_controller", parts)
