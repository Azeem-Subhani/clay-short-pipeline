"""A town crier's handbell: a brass bell with a turned wooden handle and a clapper."""
from stagekit import build

ASSET = dict(id="prop_crier_bell", name="Town crier's handbell", kind="prop", tags=["bell", "handbell", "crier", "ring", "alarm", "school bell"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.30 m tall, stands mouth down on z = 0, handle up. Hold the handle: hold(bell, 'R', t, offset=(0, 0, -0.24)); "
                   "swing the hand to ring it. Child 'bell.clapper' can swing about Y.")


def build_asset():
    brass = "gold"
    parts = [
        build.cyl("bell.lip", 0.095, 0.02, (0, 0, 0), brass, top_radius=0.085, seg=24),
        build.cyl("bell.skirt", 0.085, 0.06, (0, 0, 0.02), brass, top_radius=0.06, seg=24),
        build.cyl("bell.body", 0.06, 0.07, (0, 0, 0.08), brass, top_radius=0.048, seg=24),
        build.cyl("bell.crown", 0.048, 0.025, (0, 0, 0.15), brass, top_radius=0.022, seg=24),
        build.cyl("bell.collar", 0.02, 0.02, (0, 0, 0.175), brass, seg=12),
        build.cyl("bell.handle", 0.017, 0.10, (0, 0, 0.19), "oak_planks", top_radius=0.02, seg=12),
        build.ball("bell.knob", 0.024, (0, 0, 0.28), "oak_planks"),
        build.ball("bell.clapper", 0.022, (0, 0, -0.012), "iron_dark"),
    ]
    return build.group("prop_crier_bell", parts)
