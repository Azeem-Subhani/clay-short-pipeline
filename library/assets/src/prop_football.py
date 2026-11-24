"""A football (soccer ball): white ball with black patches spread evenly over it. Rests on the ground, origin under it."""
import math

from stagekit import build

ASSET = dict(id="prop_football", name="Football (soccer ball)", kind="prop", tags=["football", "soccer", "ball", "sport", "game", "kick"],
             era=["modern"], source="built", license="project",
             notes="0.22 m across, resting on z = 0; kick it, carry it under an arm (hold with offset=(0, 0, -0.11)) or put a foot on it")


def build_asset():
    r = 0.11
    parts = [build.ball("ball.skin", r, (0, 0, 0), "#F6F4EE", subdiv=3)]
    g = (1 + math.sqrt(5)) / 2
    dirs = [(0, s1, s2 * g) for s1 in (-1, 1) for s2 in (-1, 1)] + [(s1, s2 * g, 0) for s1 in (-1, 1) for s2 in (-1, 1)] + \
           [(s2 * g, 0, s1) for s1 in (-1, 1) for s2 in (-1, 1)]
    for i, (x, y, z) in enumerate(dirs):          # 12 patches at the corners of an icosahedron
        n = math.sqrt(x * x + y * y + z * z)
        k = (r - 0.022) / n
        parts.append(build.ball(f"ball.patch{i}", 0.034, (x * k, y * k, r + z * k - 0.034), "#262022", subdiv=2))
    return build.group("prop_football", parts)
