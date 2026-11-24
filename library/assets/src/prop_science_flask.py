"""A conical lab flask with green liquid and a cork."""
import math

from stagekit import build, core

ASSET = dict(id="prop_science_flask", name="Lab flask with green liquid", kind="prop", tags=["flask", "science", "laboratory", "chemistry", "potion", "glass"],
             era=["victorian", "modern"], source="built", license="project",
             notes="0.24 m tall, stands on its base; hold it by the neck: scientist.hold(flask, 'R', t, offset=(0, 0, -0.17))")


def build_asset():
    P = "flask."
    liquid = build.cyl(P + "liquid", 0.092, 0.07, (0, 0, 0.0), "#6FBF73", top_radius=0.06, seg=20)
    body = build.cyl(P + "body", 0.09, 0.13, (0, 0, 0), "#DCEBEF", top_radius=0.028, seg=20)
    neck = build.cyl(P + "neck", 0.028, 0.08, (0, 0, 0.13), "#DCEBEF", seg=16)
    lip = build.cyl(P + "lip", 0.036, 0.014, (0, 0, 0.205), "#C5D9DE", seg=16)
    cork = build.cyl(P + "cork", 0.024, 0.03, (0, 0, 0.212), "#B98A55", top_radius=0.028, seg=12)
    return build.group("prop_science_flask", [body, liquid, neck, lip, cork])
