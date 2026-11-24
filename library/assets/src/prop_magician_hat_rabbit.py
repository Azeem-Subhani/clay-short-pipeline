"""A black top hat standing upside down on its crown with a white rabbit peeking out."""
import math

from stagekit import build, core

ASSET = dict(id="prop_magician_hat_rabbit", name="Top hat with a rabbit", kind="prop", tags=["top hat", "rabbit", "magic", "magician", "trick", "bunny"],
             era=["victorian", "modern", "fantasy"], source="built", license="project",
             notes="0.30 m across the brim, 0.45 m tall with the ears; hold it by the brim: magician.hold(hat, 'L', t, offset=(-0.14, 0, -0.2)). Child 'hatrabbit.rabbit' moves in Z (0 = peeking out, -0.25 = hidden in the hat)")


def build_asset():
    P = "hatrabbit."
    crown = build.cyl(P + "crown", 0.095, 0.20, (0, 0, 0), "#26222A", top_radius=0.105, seg=22)
    band = build.cyl(P + "band", 0.108, 0.04, (0, 0, 0.15), "#8E4E86", seg=22)
    brim = build.cyl(P + "brim", 0.15, 0.014, (0, 0, 0.20), "#26222A", seg=26)
    hole = build.cyl(P + "hole", 0.095, 0.004, (0, 0, 0.213), "#0E0C10", seg=22)
    rabbit = core.empty(P + "rabbit", (0, 0, 0), "SET", 0.05)
    kids = [build.ball(P + "rabbit.head", 0.065, (0, 0, 0.19), "#F6F1E8")]
    for sx in (-1, 1):
        ear = build.ball(P + f"rabbit.ear{sx}", 0.025, (sx * 0.03, 0.01, 0.29), "#F6F1E8", squash=(0.9, 0.5, 2.9))
        inner = build.ball(P + f"rabbit.earin{sx}", 0.013, (sx * 0.03, -0.006, 0.31), "#F2B8B4", squash=(0.8, 0.5, 2.8))
        eye = build.ball(P + f"rabbit.eye{sx}", 0.009, (sx * 0.026, -0.058, 0.262), "#1F1C22")
        kids += [ear, inner, eye]
    kids.append(build.ball(P + "rabbit.nose", 0.008, (0, -0.064, 0.24), "#E58E8A"))
    for k in kids:
        k.parent = rabbit
    return build.group("prop_magician_hat_rabbit", [crown, band, brim, hole, rabbit])
