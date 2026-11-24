"""A judge's gavel: turned dark-wood mallet with two brass bands."""
import math

from stagekit import build

ASSET = dict(id="prop_judge_gavel", name="Judge's gavel", kind="prop", tags=['gavel', 'judge', 'court', 'hammer', 'mallet', 'verdict'],
             era=['renaissance', 'age_of_sail', 'victorian', 'modern'], source="built", license="project",
             notes="0.30 m long, standing on the handle end, head across X; hold it 0.07 m up: judge.hold(gavel, 'R', t, offset=(0, 0, -0.07)); strike with turn=True")


def build_asset():
    head = build.cyl("gavel.head", 0.04, 0.14, (0, 0, 0), "dark_timber", seg=14)
    head.rotation_euler.y = math.radians(90)
    head.location = (-0.07, 0, 0.26)
    parts = [build.cyl("gavel.handle", 0.013, 0.25, (0, 0, 0), "dark_timber", seg=10),
             build.ball("gavel.knob", 0.018, (0, 0, 0), "dark_timber"), head]
    for sx in (-1, 1):
        b = build.cyl(f"gavel.band{sx}", 0.043, 0.018, (0, 0, 0), "gold", seg=14)
        b.rotation_euler.y = math.radians(90)
        b.location = (sx * 0.045 - 0.009, 0, 0.26)
        parts.append(b)
    return build.group("prop_judge_gavel", parts)
