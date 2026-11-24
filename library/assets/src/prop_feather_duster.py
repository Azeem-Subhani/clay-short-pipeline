"""A feather duster: turned wooden handle with a full plume of soft brown feathers."""
import math

from stagekit import build

ASSET = dict(id="prop_feather_duster", name="Feather duster", kind="prop", tags=['duster', 'feather', 'housemaid', 'cleaning', 'maid', 'dust'],
             era=['victorian', 'modern'], source="built", license="project",
             notes="0.48 m tall, standing on the handle end, plume up; hold it 0.08 m up: maid.hold(duster, 'R', t, offset=(0, 0, -0.08)); dust with turn=True")


def build_asset():
    parts = [
        build.ball("duster.knob", 0.017, (0, 0, 0), "dark_timber"),
        build.cyl("duster.handle", 0.012, 0.26, (0, 0, 0.01), "dark_timber", seg=10),
        build.cyl("duster.collar", 0.022, 0.03, (0, 0, 0.24), "gold", seg=12),
        build.ball("duster.plume", 0.085, (0, 0, 0.26), "#B58A5A", squash=(0.85, 0.85, 1.25)),
    ]
    for i in range(6):
        a = math.tau * i / 6
        parts.append(build.ball(f"duster.tuft{i}", 0.04, (0.055 * math.cos(a), 0.055 * math.sin(a), 0.33), "#8E6238", squash=(0.8, 0.8, 1.4)))
    return build.group("prop_feather_duster", parts)
