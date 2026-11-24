"""Field binoculars: two dark barrels with brown rims, a bridge and a focus knob (signature prop of the Explorer).

    python tools/clip.py asset library/assets/src/prop_explorer_binoculars.py --no-save     preview only
"""
import math

from stagekit import build

ASSET = dict(id="prop_explorer_binoculars", name="Explorer's binoculars", kind="prop",
             tags=["binoculars", "field glasses", "explorer", "scout", "lookout", "safari"], era=["victorian", "modern"], source="built",
             license="project",
             notes="0.15 m wide, 0.15 m long, lying on z = 0, big lenses toward -Y, eyepieces toward +Y; "
                   "explorer.hold(binos, 'R', t) and raise the hand to the eyes")


def build_asset():
    parts = []
    for sx in (-1, 1):
        for nm, r, r2, y0, ln, surf in (("barrel", 0.034, 0.028, -0.07, 0.09, "#2E2C2A"), ("rim", 0.037, 0.037, -0.075, 0.018, "#4A3A2A"),
                                        ("eye", 0.02, 0.022, 0.02, 0.05, "#2E2C2A"), ("lens", 0.029, 0.029, -0.078, 0.004, "#9CC3D6")):
            c = build.cyl(f"binos.{nm}{sx}", r, ln, (0, 0, 0), surf, top_radius=r2, seg=16)
            c.rotation_euler.x = math.radians(-90)
            c.location = (sx * 0.04, y0, 0.037)
            parts.append(c)
    parts.append(build.box("binos.bridge", (0.07, 0.05, 0.022), (0, -0.045, 0.036), "#4A3A2A", bevel=0.006))
    knob = build.cyl("binos.knob", 0.012, 0.03, (0, 0, 0), "steel_bright", seg=12)
    knob.rotation_euler.x = math.radians(-90)
    knob.location = (0, 0.005, 0.05)
    parts.append(knob)
    return build.group("prop_explorer_binoculars", parts)
