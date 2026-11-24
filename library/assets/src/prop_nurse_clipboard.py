"""A clipboard with a patient chart: brown board, steel clip, a white sheet with a few lines. Grip point at the origin."""
from stagekit import build

ASSET = dict(id="prop_nurse_clipboard", name="Clipboard with a chart", kind="prop", tags=["clipboard", "chart", "nurse", "doctor", "notes", "paper"],
             era=["modern"], source="built", license="project",
             notes="0.24 x 0.33 m, standing on its lower edge, the sheet faces -Y; hold it at the lower edge: nurse.hold(board, 'L', t)")


def build_asset():
    parts = [
        build.box("clip.board", (0.24, 0.012, 0.33), (0, 0, 0), "oak_planks", bevel=0.006),
        build.box("clip.sheet", (0.21, 0.004, 0.28), (0, -0.008, 0.015), "#F6F1E4", bevel=0.0),
        build.box("clip.clip", (0.10, 0.02, 0.035), (0, -0.008, 0.292), "steel_bright", bevel=0.006),
    ]
    for i, w in enumerate((0.16, 0.16, 0.12, 0.16, 0.09)):
        parts.append(build.box(f"clip.line{i}", (w, 0.002, 0.012), (-(0.16 - w) / 2, -0.011, 0.235 - i * 0.042), "#6F7C8C", bevel=0.0))
    return build.group("prop_nurse_clipboard", parts)
