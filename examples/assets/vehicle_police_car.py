"""Chunky clay police car. Front toward -Y. The light bar halves are <root>_bar_blue / _bar_red (glow materials):
use build.set_glow(...) to pulse them and lights.flash(...) at the bar for the light they throw."""
from stagekit import build

ASSET = dict(id="vehicle_police_car", name="Police car (clay, chunky)", kind="vehicle", tags=["police", "car", "vehicle", "siren", "patrol"],
             notes="4.2 x 1.8 x 1.55 m. Front toward -Y. Light bar at z 1.5. Headlights are glow panels: pair with a SPOT practical.")


def build_asset():
    white, dark, blue = "#E9E6DF", "#1B2233", "#27457F"
    parts = [
        build.box("body", (1.8, 4.2, 0.62), (0, 0, 0.3), white, bevel=0.12),
        build.box("stripe", (1.82, 2.0, 0.26), (0, 0.1, 0.5), blue, bevel=0.02),
        build.box("cabin", (1.56, 2.1, 0.58), (0, 0.25, 0.9), dark, bevel=0.16),
        build.box("roof", (1.5, 1.7, 0.08), (0, 0.3, 1.42), white, bevel=0.03),
        build.box("bar_base", (1.1, 0.26, 0.05), (0, 0.25, 1.5), "#2A2D33", bevel=0.01),
        build.box("bar_blue", (0.5, 0.22, 0.11), (-0.28, 0.25, 1.54), "#000", bevel=0.03, material=build.glow("#2B5BFF", 9.0, "bar_blue_glow")),
        build.box("bar_red", (0.5, 0.22, 0.11), (0.28, 0.25, 1.54), "#000", bevel=0.03, material=build.glow("#FF2B2B", 9.0, "bar_red_glow")),
        build.box("bumper_f", (1.84, 0.16, 0.2), (0, -2.08, 0.3), "#2A2D33", bevel=0.05),
        build.box("bumper_r", (1.84, 0.16, 0.2), (0, 2.08, 0.3), "#2A2D33", bevel=0.05),
    ]
    for sx in (-1, 1):
        parts.append(build.box(f"headlight{sx}", (0.34, 0.05, 0.16), (sx * 0.6, -2.11, 0.62), "#000", bevel=0.02, material=build.glow("#FFF3D6", 7.0, f"headlight_glow{sx}")))
        parts.append(build.box(f"taillight{sx}", (0.3, 0.05, 0.12), (sx * 0.62, 2.11, 0.66), "#000", bevel=0.02, material=build.glow("#FF2A1A", 2.5, f"tail_glow{sx}")))
        for sy in (-1.3, 1.35):
            w = build.cyl(f"wheel{sx}{sy}", 0.36, 0.26, (0, 0, 0), "#15161A", segments=28, bevel=0.05)
            w.rotation_euler.y = 1.5708
            w.location = (sx * 0.8 - 0.13, sy, 0.36)
            hub = build.cyl(f"hub{sx}{sy}", 0.17, 0.03, (0, 0, 0), "#B9BEC6", segments=20, bevel=0.01)
            hub.rotation_euler.y = 1.5708
            hub.location = (sx * 0.93 - (0.015 if sx > 0 else 0.015), sy, 0.36)
            parts += [w, hub]
    return build.group("vehicle_police_car", parts)
