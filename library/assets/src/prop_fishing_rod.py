"""A simple fishing rod: a long tapering cane, a line from the tip and a red-and-white float."""
import math

from stagekit import build

ASSET = dict(id="prop_fishing_rod", name="Fishing rod with float", kind="prop", tags=['fishing', 'rod', 'fisherman', 'line', 'float', 'angler'],
             era=['ancient', 'medieval', 'renaissance', 'age_of_sail', 'victorian', 'modern', 'fantasy'], source="built", license="project",
             notes="1.9 m tall, standing on the butt, line hanging 0.7 m from the tip on +X; hold it 0.25 m up: fisherman.hold(rod, 'R', t, offset=(0, 0, -0.25)); child 'rod.float' can be animated")


def build_asset():
    link = build.cyl("rod.tip_link", 0.004, 0.035, (0, 0, 0), "#F3EFE6", seg=5)
    link.rotation_euler.y = math.radians(90)
    link.location = (0, 0, 1.885)
    parts = [
        build.cyl("rod.cane", 0.016, 1.9, (0, 0, 0), "#B88A4A", top_radius=0.006, seg=8),
        build.cyl("rod.grip", 0.021, 0.30, (0, 0, 0), "#5B3A22", seg=10),
        build.cyl("rod.line", 0.004, 0.70, (0.035, 0, 1.19), "#F3EFE6", seg=5),
        build.ball("rod.float", 0.03, (0.035, 0, 1.14), "#C8302C", squash=(1, 1, 1.3)),
        build.ball("rod.float_top", 0.02, (0.035, 0, 1.20), "#F6F1E4"),
        link,
    ]
    return build.group("prop_fishing_rod", parts)
