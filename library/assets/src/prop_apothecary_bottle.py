"""An apothecary's medicine bottle: amber glass, a paper label, a cork."""
from stagekit import build

ASSET = dict(id="prop_apothecary_bottle", name="Apothecary bottle with cork", kind="prop",
             tags=["bottle", "potion", "medicine", "apothecary", "tonic", "remedy", "flask"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.17 m tall, stands on z = 0. Drawn chunky so it reads on a phone. Hold it round the body: "
                   "hold(bottle, 'R', t, offset=(0, 0, -0.05)).")


def build_asset():
    amber = "#D98F3A"
    parts = [
        build.cyl("bottle.body", 0.042, 0.095, (0, 0, 0), amber, seg=20),
        build.cyl("bottle.shoulder", 0.042, 0.03, (0, 0, 0.095), amber, top_radius=0.018, seg=20),
        build.cyl("bottle.neck", 0.018, 0.025, (0, 0, 0.125), amber, seg=14),
        build.cyl("bottle.lip", 0.023, 0.008, (0, 0, 0.146), amber, seg=14),
        build.cyl("bottle.cork", 0.015, 0.022, (0, 0, 0.152), "#B98A5A", top_radius=0.017, seg=12),
        build.cyl("bottle.label", 0.0435, 0.045, (0, 0, 0.03), "#F3E7CF", seg=20),
        build.box("bottle.label_line", (0.04, 0.004, 0.006), (0, -0.0425, 0.05), "#7A5236", bevel=0.001),
    ]
    return build.group("prop_apothecary_bottle", parts)
