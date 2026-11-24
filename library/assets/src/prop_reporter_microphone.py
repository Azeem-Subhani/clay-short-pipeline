"""A reporter's hand microphone: dark grip, blue station cube, foam head (signature prop of the Reporter).

    python tools/clip.py asset library/assets/src/prop_reporter_microphone.py --no-save     preview only
"""
from stagekit import build

ASSET = dict(id="prop_reporter_microphone", name="Reporter's hand microphone", kind="prop",
             tags=["microphone", "mic", "reporter", "interview", "news", "singer"], era=["modern"], source="built", license="project",
             notes="0.27 m tall, standing on its base, foam head up; hold the grip: "
                   "reporter.hold(mic, 'R', t, offset=(0, 0, -0.07)); turn=True to point it at someone")


def build_asset():
    parts = [build.cyl("mic.grip", 0.016, 0.15, (0, 0, 0), "#2B2B30", top_radius=0.02, seg=14),
             build.cyl("mic.ring", 0.024, 0.012, (0, 0, 0), "steel_bright", seg=14),
             build.box("mic.cube", (0.062, 0.062, 0.05), (0, 0, 0.125), "#3E63A8", bevel=0.008),
             build.cyl("mic.collar", 0.026, 0.015, (0, 0, 0.172), "steel_bright", seg=14),
             build.ball("mic.head", 0.038, (0, 0, 0.18), "#3A3A40", squash=(1, 1, 1.1))]
    return build.group("prop_reporter_microphone", parts)
