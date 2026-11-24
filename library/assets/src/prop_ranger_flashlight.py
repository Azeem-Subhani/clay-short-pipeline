"""Park ranger's flashlight: signature prop of the roles sheet 12 (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_ranger_flashlight.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_ranger_flashlight", name="Hand flashlight", kind="prop", tags=['flashlight', 'torch', 'ranger', 'night', 'search'],
             era=['modern'], source="built", license="project",
             notes="20 cm tall, lens up, stands on z = 0; grip the body 7 cm up: hold(light, 'R', t, offset=(0, 0, -0.065)); add a spot light in the shot for the beam")


def build_asset():
    parts = []
    parts.append(build.cyl("light.body", 0.019, 0.13, (0, 0, -0.065), "#3A4030", seg=14))
    parts.append(build.cyl("light.head", 0.02, 0.055, (0, 0, 0.065), "#3A4030", top_radius=0.034, seg=16))
    parts.append(build.cyl("light.rim", 0.035, 0.012, (0, 0, 0.12), "steel_bright", seg=16))
    parts.append(build.cyl("light.lens", 0.03, 0.004, (0, 0, 0.131), "#FFF3C4", seg=16))
    parts.append(build.box("light.switch", (0.012, 0.008, 0.022), (0, -0.021, 0.0), "#C8302C", bevel=0.002))
    for ob in parts:      # stand it on z = 0 (the grip is 0.065 m up)
        ob.location.z += 0.065
    return build.group("prop_ranger_flashlight", parts)
