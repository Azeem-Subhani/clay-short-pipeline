"""A sailor's brass spyglass, drawn out in three tubes."""
from stagekit import build

ASSET = dict(id="prop_spyglass", name="Brass spyglass", kind="prop", tags=["spyglass", "telescope", "sailor", "ship", "lookout", "brass"],
             era=["age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.50 m long, standing on its eyepiece, big lens on top. Hold the thick tube: sailor.hold(spy, 'R', t, offset=(0, 0, -0.30)); rotate it 90 degrees about Y to look through it.")


def build_asset():
    parts = [build.cyl("spy.eye", 0.02, 0.02, (0, 0, 0), "iron_dark", seg=14),
             build.cyl("spy.t1", 0.018, 0.16, (0, 0, 0.02), "gold", seg=14),
             build.cyl("spy.t2", 0.025, 0.15, (0, 0, 0.17), "gold", seg=14),
             build.cyl("spy.t3", 0.033, 0.17, (0, 0, 0.31), "dark_timber", seg=14),
             build.cyl("spy.rim", 0.037, 0.025, (0, 0, 0.475), "gold", seg=14),
             build.cyl("spy.lens", 0.03, 0.004, (0, 0, 0.498), "#CFE6EE", seg=14)]
    for i, (z, r) in enumerate(((0.17, 0.028), (0.31, 0.036))):
        parts.append(build.cyl(f"spy.ring{i}", r, 0.012, (0, 0, z), "gold", seg=14))
    return build.group("prop_spyglass", parts)
