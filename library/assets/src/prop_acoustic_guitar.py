"""An acoustic guitar standing on its body: honey-coloured body with a dark sound hole and bridge, brown neck, head with pegs."""
from stagekit import build

ASSET = dict(id="prop_acoustic_guitar", name="Acoustic guitar", kind="prop", tags=["guitar", "music", "musician", "instrument", "song"],
             era=["renaissance", "age_of_sail", "victorian", "modern"], source="built", license="project",
             notes="1.0 m tall, standing on the body, the front faces -Y; hold it by the neck 0.65 m up: "
                   "musician.hold(guitar, 'L', t, offset=(0, 0, -0.65)); lay it across the body to play")


def build_asset():
    wood, dark = "#D9A55A", "#5B3A22"
    parts = [
        build.ball("gtr.lower", 0.19, (0, 0, 0.0), wood, squash=(1.0, 0.24, 1.0)),
        build.ball("gtr.upper", 0.145, (0, 0, 0.23), wood, squash=(1.0, 0.30, 1.0)),
        build.cyl("gtr.hole", 0.05, 0.012, (0, -0.036, 0.30), "#2B1B1B", seg=20),
        build.box("gtr.bridge", (0.13, 0.02, 0.025), (0, -0.045, 0.12), dark, bevel=0.004),
        build.box("gtr.neck", (0.05, 0.028, 0.44), (0, -0.022, 0.46), dark, bevel=0.006),
        build.box("gtr.head", (0.075, 0.026, 0.13), (0, -0.022, 0.88), dark, bevel=0.01),
        build.box("gtr.strings", (0.022, 0.004, 0.76), (0, -0.05, 0.13), "#EDE6D2", bevel=0.0),
    ]
    parts[2].rotation_euler.x = 1.5708
    for i in range(3):
        for sx in (-1, 1):
            parts.append(build.ball(f"gtr.peg{i}{sx}", 0.014, (sx * 0.05, -0.022, 0.895 + i * 0.035), "steel_bright"))
    return build.group("prop_acoustic_guitar", parts)
