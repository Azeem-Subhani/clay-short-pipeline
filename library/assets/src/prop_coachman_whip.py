"""Coachman's whip: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_coachman_whip.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_coachman_whip", name="Coachman's whip", kind="prop", tags=['whip', 'coach', 'carriage', 'driver', 'horse'],
             era=['age_of_sail', 'victorian'], source="built", license="project",
             notes="1.5 m tall stiff whip standing upright with a drooping lash; hold it 0.12 m up: hold(whip, 'R', t, offset=(0, 0, -0.12))")


def build_asset():
    parts = []
    parts.append(build.cyl("whip.grip", 0.016, 0.24, (0, 0, 0), "#3E2616", seg=10))
    parts.append(build.cyl("whip.cap", 0.02, 0.02, (0, 0, 0), "gold", seg=10))
    parts.append(build.cyl("whip.stock", 0.011, 1.0, (0, 0, 0.24), "dark_timber", top_radius=0.006, seg=8))
    x, z = 0.0, 1.24
    for i in range(7):      # the lash bends over and hangs
        ang = 25 + 24 * i
        seg = build.cyl(f"whip.lash{i}", 0.006, 0.085, (x, 0, z), "rope", seg=6)
        seg.rotation_euler.y = math.radians(ang)
        parts.append(seg)
        x += 0.08 * math.sin(math.radians(ang))
        z += 0.08 * math.cos(math.radians(ang))
    return build.group("prop_coachman_whip", parts)
