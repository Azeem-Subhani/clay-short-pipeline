"""Florist's bouquet: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_florist_bouquet.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_florist_bouquet", name="Small flower bouquet in paper", kind="prop", tags=['bouquet', 'flowers', 'florist', 'gift', 'romance'],
             era=['renaissance', 'victorian', 'modern', 'fantasy'], source="built", license="project",
             notes="29 cm tall, flowers up, stands on z = 0; grip the tied stems 9 cm up: hold(bouquet, 'R', t, offset=(0, 0, -0.09))")


def build_asset():
    parts = []
    parts.append(build.cyl("bouquet.stems", 0.016, 0.12, (0, 0, -0.09), "#6F8A3E", seg=10))
    parts.append(build.cyl("bouquet.wrap", 0.022, 0.13, (0, 0, 0.0), "#F2E7CF", top_radius=0.075, seg=14))
    parts.append(build.cyl("bouquet.tie", 0.024, 0.014, (0, 0, 0.0), "#C8322C", seg=12))
    cols = ["#F6F1E4", "#E9826B", "#F2C94C", "#D98C8C", "#F6F1E4", "#E9826B"]
    for i, c in enumerate(cols):
        a = math.tau * i / len(cols)
        parts.append(build.ball(f"bouquet.flower{i}", 0.034, (0.045 * math.cos(a), 0.045 * math.sin(a), 0.115), c, squash=(1, 1, 0.7)))
    parts.append(build.ball("bouquet.flower_top", 0.038, (0, 0, 0.14), "#D9534F", squash=(1, 1, 0.75)))
    for i in range(3):
        a = math.tau * (i + 0.5) / 3
        parts.append(build.ball(f"bouquet.leaf{i}", 0.03, (0.07 * math.cos(a), 0.07 * math.sin(a), 0.10), "#5E8F3C", squash=(1, 1, 0.4)))
    for ob in parts:      # stand it on z = 0 (the grip is 0.090 m up)
        ob.location.z += 0.090
    return build.group("prop_florist_bouquet", parts)
