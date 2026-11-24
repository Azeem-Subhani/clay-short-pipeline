"""A leather school satchel with a flap, two buckled straps and a top handle (signature prop of the Schoolgirl).

    python tools/clip.py asset library/assets/src/prop_school_satchel.py --no-save     preview only
"""
from stagekit import build

ASSET = dict(id="prop_school_satchel", name="School satchel", kind="prop", tags=["satchel", "school bag", "bag", "schoolgirl", "pupil"],
             era=["victorian", "modern"], source="built", license="project",
             notes="0.34 m wide, 0.31 m tall with the handle, standing on z = 0; hold it by the handle: "
                   "girl.hold(bag, 'R', t, offset=(0, 0, -0.30))")


def build_asset():
    parts = [build.box("satchel.body", (0.34, 0.11, 0.24), (0, 0, 0), "#8A4B2E", bevel=0.02),
             build.box("satchel.flap", (0.35, 0.02, 0.15), (0, -0.062, 0.10), "#74391F", bevel=0.01),
             build.box("satchel.pocket", (0.20, 0.015, 0.07), (0, -0.06, 0.015), "#74391F", bevel=0.008)]
    for sx in (-1, 1):
        parts.append(build.box(f"satchel.strap{sx}", (0.035, 0.012, 0.13), (sx * 0.095, -0.075, 0.07), "#5A2C18", bevel=0.004))
        parts.append(build.box(f"satchel.buckle{sx}", (0.045, 0.014, 0.03), (sx * 0.095, -0.08, 0.075), "gold", bevel=0.004))
        parts.append(build.box(f"satchel.handle{sx}", (0.02, 0.02, 0.055), (sx * 0.06, 0, 0.24), "#5A2C18", bevel=0.004))
    parts.append(build.box("satchel.handle", (0.15, 0.025, 0.022), (0, 0, 0.29), "#5A2C18", bevel=0.008))
    return build.group("prop_school_satchel", parts)
