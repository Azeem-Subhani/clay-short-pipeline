"""A single red rose on a green stem with two leaves, chunky enough to read at phone size."""
import math

from stagekit import build

ASSET = dict(id="prop_red_rose", name="Red rose", kind="prop", tags=['rose', 'flower', 'princess', 'gift', 'love'],
             era=['medieval', 'renaissance', 'age_of_sail', 'victorian', 'modern', 'fantasy'], source="built", license="project",
             notes="0.34 m tall, standing on the stem end; hold it 0.10 m up: princess.hold(rose, 'R', t, offset=(0, 0, -0.10))")


def build_asset():
    parts = [
        build.cyl("rose.stem", 0.009, 0.27, (0, 0, 0), "#4E7A3A", seg=8),
        build.ball("rose.leaf1", 0.035, (0.035, 0, 0.12), "#5E8F45", squash=(1.0, 0.25, 0.55)),
        build.ball("rose.leaf2", 0.035, (-0.035, 0, 0.17), "#5E8F45", squash=(1.0, 0.25, 0.55)),
        build.ball("rose.cup", 0.03, (0, 0, 0.245), "#4E7A3A", squash=(1, 1, 0.6)),
        build.ball("rose.bloom", 0.05, (0, 0, 0.255), "#B8302E", squash=(1, 1, 0.85)),
        build.ball("rose.heart", 0.03, (0, 0, 0.305), "#8E1F22", squash=(1, 1, 0.7)),
    ]
    return build.group("prop_red_rose", parts)
