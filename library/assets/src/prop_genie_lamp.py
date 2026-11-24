"""A genie's oil lamp: a low gold body on a foot, a long spout, a lid with a knob and a ring handle at the back."""
from stagekit import build

ASSET = dict(id="prop_genie_lamp", name="Genie's oil lamp", kind="prop", tags=["lamp", "genie", "magic", "oil lamp", "gold", "wish"],
             era=["ancient", "medieval", "fantasy"], source="built", license="project",
             notes="0.30 m long, 0.16 m tall, resting on its foot, spout toward +X; rub it with the free hand; "
                   "carry it with hold(lamp, 'R', t, offset=(0.11, 0, -0.08)) so the hand is on the handle")


def build_asset():
    parts = [
        build.cyl("lamp.foot", 0.05, 0.02, (0, 0, 0), "gold", top_radius=0.03, seg=20),
        build.ball("lamp.body", 0.085, (0, 0, 0.015), "gold", squash=(1.25, 0.9, 0.62)),
        build.cyl("lamp.lid", 0.04, 0.02, (0, 0, 0.115), "gold", top_radius=0.02, seg=20),
        build.ball("lamp.knob", 0.016, (0, 0, 0.132), "gold"),
        build.ball("lamp.tip", 0.02, (0.185, 0, 0.115), "gold"),
        build.ball("lamp.handle", 0.045, (-0.125, 0, 0.035), "gold", squash=(0.8, 0.28, 1.0)),
        build.ball("lamp.handle.hole", 0.026, (-0.128, 0, 0.054), "#3A2E2A", squash=(0.8, 0.5, 1.0)),
    ]
    spout = build.cyl("lamp.spout", 0.03, 0.14, (0, 0, 0), "gold", top_radius=0.014, seg=14)
    spout.rotation_euler.y = 1.05
    spout.location = (0.07, 0, 0.07)
    parts.append(spout)
    return build.group("prop_genie_lamp", parts)
