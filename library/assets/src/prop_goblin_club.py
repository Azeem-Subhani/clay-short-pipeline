"""Goblin's club: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_goblin_club.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_goblin_club", name="Knobbly wooden club", kind="prop", tags=['club', 'cudgel', 'goblin', 'troll', 'weapon', 'wood'],
             era=['ancient', 'medieval', 'fantasy'], source="built", license="project",
             notes="44 cm tall, heavy end up, stands on z = 0; grip it 8 cm up: hold(club, 'R', t, offset=(0, 0, -0.08))")


def build_asset():
    parts = []
    parts.append(build.cyl("club.grip", 0.02, 0.16, (0, 0, -0.08), "dark_timber", top_radius=0.024, seg=10))
    parts.append(build.cyl("club.body", 0.024, 0.20, (0, 0, 0.08), "oak_planks", top_radius=0.05, seg=12))
    parts.append(build.ball("club.head", 0.055, (0, 0, 0.26), "oak_planks", squash=(1, 1, 0.9)))
    parts.append(build.cyl("club.band", 0.027, 0.02, (0, 0, 0.07), "iron_dark", seg=12))
    for i in range(4):
        a = math.tau * i / 4 + 0.4
        parts.append(build.ball(f"club.knob{i}", 0.014, (0.05 * math.cos(a), 0.05 * math.sin(a), 0.27 + 0.02 * (i % 2)), "iron_dark"))
    for ob in parts:      # stand it on z = 0 (the grip is 0.080 m up)
        ob.location.z += 0.080
    return build.group("prop_goblin_club", parts)
