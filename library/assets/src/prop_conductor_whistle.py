"""Train conductor's whistle: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_conductor_whistle.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_conductor_whistle", name="Conductor's brass whistle", kind="prop", tags=['whistle', 'conductor', 'train', 'referee', 'brass'],
             era=['victorian', 'modern'], source="built", license="project",
             notes="8 cm long, lying flat, mouthpiece toward +X; hold(whistle, 'R', t) and raise the hand to the mouth")


def build_asset():
    parts = []
    barrel = build.cyl("whistle.barrel", 0.016, 0.03, (0, 0, 0), "gold", seg=16)
    barrel.rotation_euler.x = math.radians(90)
    barrel.location = (-0.012, 0.015, 0.016)
    parts.append(barrel)
    parts.append(build.box("whistle.mouth", (0.05, 0.022, 0.014), (0.022, 0, 0.018), "gold", bevel=0.003))
    parts.append(build.box("whistle.slot", (0.012, 0.016, 0.003), (0.004, 0, 0.031), "#2B1B1B", bevel=0.0))
    parts.append(build.cyl("whistle.ring", 0.008, 0.004, (-0.034, 0, 0.012), "steel_bright", seg=12))
    return build.group("prop_conductor_whistle", parts)
