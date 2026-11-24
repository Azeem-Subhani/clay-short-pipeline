"""A folded letter with a red wax seal, drawn chunky so it reads in a hand."""
import math

from stagekit import build

ASSET = dict(id="prop_sealed_letter", name="Sealed letter", kind="prop", tags=['letter', 'envelope', 'seal', 'message', 'post', 'mail'],
             era=['medieval', 'renaissance', 'age_of_sail', 'victorian', 'fantasy'], source="built", license="project",
             notes="0.20 x 0.13 m, standing on its long edge, sealed face toward -Y; hold it 0.05 m up: messenger.hold(letter, 'R', t, offset=(0, 0, -0.05))")


def build_asset():
    flap = build.box("letter.flap", (0.19, 0.006, 0.06), (0, -0.008, 0.066), "#E2D3B2", bevel=0.002)
    parts = [
        build.box("letter.paper", (0.20, 0.014, 0.13), (0, 0, 0), "#F3EAD3", bevel=0.004),
        flap,
        build.ball("letter.seal", 0.02, (0, -0.02, 0.05), "#B8302E", squash=(1, 0.4, 1)),
    ]
    return build.group("prop_sealed_letter", parts)
