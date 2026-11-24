"""A stage wand: black stick with white tips."""
import math

from stagekit import build, core

ASSET = dict(id="prop_magician_wand", name="Magician wand", kind="prop", tags=["wand", "magic", "magician", "trick", "stage"],
             era=["victorian", "modern", "fantasy"], source="built", license="project",
             notes="0.36 m long, standing on one tip; hold it low: magician.hold(wand, 'R', t, offset=(0, 0, -0.08)); turn=True to flick it")


def build_asset():
    P = "magwand."
    tip0 = build.cyl(P + "tip0", 0.014, 0.05, (0, 0, 0), "#F6F1E4", seg=10)
    stick = build.cyl(P + "stick", 0.013, 0.26, (0, 0, 0.05), "#1F1C22", seg=10)
    tip1 = build.cyl(P + "tip1", 0.014, 0.05, (0, 0, 0.31), "#F6F1E4", seg=10)
    return build.group("prop_magician_wand", [tip0, stick, tip1])
