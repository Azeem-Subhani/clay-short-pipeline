"""Electrician's screwdriver: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_electrician_screwdriver.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_electrician_screwdriver", name="Screwdriver with a yellow handle", kind="prop", tags=['screwdriver', 'tool', 'electrician', 'repair'],
             era=['modern'], source="built", license="project",
             notes="22 cm tall, blade up, stands on z = 0; grip the handle 5 cm up: hold(driver, 'R', t, offset=(0, 0, -0.05))")


def build_asset():
    parts = []
    parts.append(build.cyl("driver.handle", 0.017, 0.10, (0, 0, -0.05), "#F0C02E", top_radius=0.014, seg=14))
    parts.append(build.cyl("driver.collar", 0.012, 0.012, (0, 0, 0.05), "#2B2B30", seg=12))
    parts.append(build.cyl("driver.shaft", 0.005, 0.10, (0, 0, 0.06), "steel_bright", seg=10))
    parts.append(build.box("driver.tip", (0.012, 0.003, 0.012), (0, 0, 0.158), "steel_bright", bevel=0.0))
    for ob in parts:      # stand it on z = 0 (the grip is 0.050 m up)
        ob.location.z += 0.050
    return build.group("prop_electrician_screwdriver", parts)
