"""A stablehand's hay fork: a long wooden handle and three iron tines."""
from stagekit import build

ASSET = dict(id="prop_stable_pitchfork", name="Pitchfork (hay fork)", kind="prop", tags=["pitchfork", "hay fork", "fork", "stable", "farm", "tool"],
             era=["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="1.65 m tall, stands on its handle end on z = 0, tines up, fork spread along X. Hold it about 0.9 m up: "
                   "hold(fork, 'R', t, offset=(0, 0, -0.9)).")


def build_asset():
    parts = [
        build.cyl("fork.handle", 0.02, 1.30, (0, 0, 0), "oak_planks", top_radius=0.018, seg=12),
        build.cyl("fork.socket", 0.026, 0.12, (0, 0, 1.24), "iron_dark", top_radius=0.022, seg=12),
        build.box("fork.bar", (0.24, 0.028, 0.028), (0, 0, 1.35), "iron_dark", bevel=0.006),
    ]
    for i, x in enumerate((-0.105, 0.0, 0.105)):
        parts.append(build.cyl(f"fork.tine{i}", 0.012, 0.28, (x, 0, 1.37), "iron_dark", top_radius=0.004, seg=8))
    return build.group("prop_stable_pitchfork", parts)
