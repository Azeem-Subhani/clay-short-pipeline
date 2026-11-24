"""An expedition flag on a steel pole, held out stiff by a top rod as on the Moon (signature prop of the Astronaut).

    python tools/clip.py asset library/assets/src/prop_astronaut_flag.py --no-save     preview only
"""
import math

from stagekit import build

ASSET = dict(id="prop_astronaut_flag", name="Astronaut's expedition flag", kind="prop",
             tags=["flag", "flagpole", "astronaut", "moon", "expedition", "banner"], era=["modern"], source="built", license="project",
             notes="1.64 m steel pole standing on z = 0, stiff 0.55 x 0.34 m orange flag with a white band (no nation) toward +X; "
                   "hold it 0.9 m up: astronaut.hold(flag, 'R', t, offset=(0, 0, -0.9)); stand it on the ground to plant it")


def build_asset():
    parts = [build.cyl("flag.pole", 0.014, 1.60, (0, 0, 0), "steel_bright", seg=12),
             build.cyl("flag.foot", 0.022, 0.06, (0, 0, 0), "iron_dark", top_radius=0.016, seg=12),
             build.ball("flag.knob", 0.024, (0, 0, 1.59), "gold"),
             build.box("flag.cloth", (0.55, 0.012, 0.34), (0.29, 0, 1.22), "#D2693C", bevel=0.004),
             build.box("flag.band", (0.552, 0.016, 0.07), (0.29, 0, 1.355), "#F4EFE6", bevel=0.003)]
    rod = build.cyl("flag.rod", 0.008, 0.57, (0, 0, 0), "steel_bright", seg=8)
    rod.rotation_euler.y = math.radians(90)
    rod.location = (0, 0, 1.565)
    parts.append(rod)
    return build.group("prop_astronaut_flag", parts)
