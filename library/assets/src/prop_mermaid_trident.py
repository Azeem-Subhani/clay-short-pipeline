"""A sea trident: a pale driftwood shaft with a chunky gold three-pronged head."""
import math

from stagekit import build, core

ASSET = dict(id="prop_mermaid_trident", name="Mermaid trident", kind="prop", tags=["trident", "mermaid", "sea", "spear", "fork", "neptune"],
             era=["ancient", "fantasy"], source="built", license="project",
             notes="1.5 m tall, standing on the shaft end; hold it 0.8 m up: mermaid.hold(trident, 'R', t, offset=(0, 0, -0.8))")


def build_asset():
    P = "trident."
    shaft = build.cyl(P + "shaft", 0.018, 1.12, (0, 0, 0), "#C9A27A", seg=10)
    collar = build.cyl(P + "collar", 0.03, 0.06, (0, 0, 1.09), "gold", seg=12)
    bar = build.box(P + "bar", (0.30, 0.04, 0.045), (0, 0, 1.14), "gold", bevel=0.012)
    parts = [shaft, collar, bar]
    for sx, h in ((-1, 0.24), (0, 0.32), (1, 0.24)):
        parts.append(build.box(P + f"prong{sx}", (0.04, 0.035, h), (sx * 0.13, 0, 1.16), "gold", bevel=0.01))
        parts.append(build.cyl(P + f"tip{sx}", 0.034, 0.07, (sx * 0.13, 0, 1.16 + h - 0.01), "gold", top_radius=0.004, seg=8))
    return build.group("prop_mermaid_trident", parts)
