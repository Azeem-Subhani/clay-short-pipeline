"""Dragon's hoard: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_dragon_gold_pile.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_dragon_gold_pile", name="Small pile of gold with a gem and a goblet", kind="prop", tags=['gold', 'treasure', 'hoard', 'dragon', 'coins', 'loot'],
             era=['ancient', 'medieval', 'renaissance', 'age_of_sail', 'fantasy'], source="built", license="project",
             notes="48 cm across, 28 cm tall, sits on the ground; a set prop to guard or sit beside, not to hold")


def build_asset():
    parts = []
    parts.append(build.ball("hoard.mound", 0.24, (0, 0, 0), "gold", squash=(1, 1, 0.35)))
    top = lambda r: 0.080 + 0.084 * math.sqrt(max(0.0, 1 - (r / 0.24) ** 2))      # height of the mound surface at radius r
    for i in range(14):
        a = math.tau * i / 14
        r = 0.10 + 0.11 * ((i * 7) % 5) / 4
        coin = build.cyl(f"hoard.coin{i}", 0.028, 0.008, (r * math.cos(a), r * math.sin(a), top(r)), "gold", seg=12)
        coin.rotation_euler.x = math.radians(18 * ((i % 3) - 1))
        parts.append(coin)
    parts.append(build.ball("hoard.gem", 0.035, (0.07, -0.10, 0.14), "#C8302C", squash=(1, 1, 0.8), subdiv=1))
    parts.append(build.cyl("hoard.cup_foot", 0.03, 0.01, (-0.06, -0.02, 0.16), "gold", seg=12))
    parts.append(build.cyl("hoard.cup_stem", 0.008, 0.05, (-0.06, -0.02, 0.17), "gold", seg=8))
    parts.append(build.cyl("hoard.cup", 0.02, 0.055, (-0.06, -0.02, 0.22), "gold", top_radius=0.036, seg=14))
    return build.group("prop_dragon_gold_pile", parts)
