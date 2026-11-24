"""A fat silver-blue fish, freshly caught: body, pale belly, tail, back fin and eyes."""
import math

from stagekit import build

ASSET = dict(id="prop_caught_fish", name="Caught fish", kind="prop", tags=['fish', 'catch', 'fisherman', 'food', 'market', 'sea'],
             era=['ancient', 'medieval', 'renaissance', 'age_of_sail', 'victorian', 'modern', 'fantasy'], source="built", license="project",
             notes="0.36 m long along X, lying on its belly on z = 0, head toward +X; hold it by the tail: fisherman.hold(fish, 'L', t, offset=(0.15, 0, -0.05))")


def build_asset():
    parts = [
        build.ball("fish.body", 0.07, (0, 0, 0), "#7F9BB0", squash=(2.0, 0.6, 1.0)),
        build.ball("fish.belly", 0.055, (0.01, 0, 0), "#DCE3E6", squash=(2.0, 0.72, 0.7)),
        build.box("fish.tail", (0.07, 0.016, 0.11), (-0.165, 0, 0.015), "#5E7A90", bevel=0.007),
        build.box("fish.fin", (0.08, 0.012, 0.05), (-0.01, 0, 0.105), "#5E7A90", bevel=0.005),
        build.ball("fish.eye_a", 0.012, (0.095, -0.034, 0.075), "#1F1A1C"),
        build.ball("fish.eye_b", 0.012, (0.095, 0.034, 0.075), "#1F1A1C"),
    ]
    return build.group("prop_caught_fish", parts)
