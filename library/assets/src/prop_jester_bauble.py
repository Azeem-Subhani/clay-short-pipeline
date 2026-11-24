"""A jester's bauble (marotte): a short stick topped with a little two-horned fool's head and bells."""
import math

from stagekit import build

ASSET = dict(id="prop_jester_bauble", name="Jester's bauble", kind="prop", tags=['bauble', 'marotte', 'jester', 'fool', 'bells', 'stick'],
             era=['medieval', 'renaissance', 'fantasy'], source="built", license="project",
             notes="0.38 m tall, standing on the stick end; hold it 0.08 m up: jester.hold(bauble, 'R', t, offset=(0, 0, -0.08)); shake it with turn=True")


def build_asset():
    parts = [
        build.ball("bauble.knob", 0.016, (0, 0, 0), "gold"),
        build.cyl("bauble.stick", 0.012, 0.28, (0, 0, 0.01), "#6E4526", seg=10),
        build.cyl("bauble.ruff", 0.05, 0.02, (0, 0, 0.265), "#D9A93F", top_radius=0.03, seg=12),
        build.ball("bauble.head", 0.05, (0, 0, 0.275), "#F8D7B2"),
        build.ball("bauble.cap_l", 0.04, (-0.04, 0, 0.33), "#8E3A40", squash=(1.3, 0.9, 0.8)),
        build.ball("bauble.cap_r", 0.04, (0.04, 0, 0.33), "#D9A93F", squash=(1.3, 0.9, 0.8)),
        build.ball("bauble.bell_l", 0.016, (-0.10, 0, 0.34), "gold"),
        build.ball("bauble.bell_r", 0.016, (0.10, 0, 0.34), "gold"),
    ]
    return build.group("prop_jester_bauble", parts)
