"""A three-tined hay fork on an oak shaft (signature prop of the Farmer).

    python tools/clip.py asset library/assets/src/prop_pitchfork.py --no-save     preview only
"""
from stagekit import build

ASSET = dict(id="prop_pitchfork", name="Pitchfork", kind="prop", tags=["pitchfork", "hay fork", "fork", "farmer", "farm tool"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "modern", "fantasy"], source="built", license="project",
             notes="1.66 m tall, three iron tines up, shaft standing on z = 0; hold it 0.9 m up: "
                   "farmer.hold(fork, 'R', t, offset=(0, 0, -0.9)); turn=True to lower or swing it")


def build_asset():
    parts = [build.cyl("fork.shaft", 0.022, 1.30, (0, 0, 0), "oak_planks", seg=12),
             build.cyl("fork.socket", 0.03, 0.10, (0, 0, 1.26), "iron_dark", seg=12),
             build.box("fork.bar", (0.24, 0.03, 0.03), (0, 0, 1.34), "iron_dark", bevel=0.006)]
    for sx in (-1, 0, 1):
        parts.append(build.cyl(f"fork.tine{sx}", 0.013, 0.30, (sx * 0.105, 0, 1.36), "iron_dark", top_radius=0.004, seg=10))
    return build.group("prop_pitchfork", parts)
