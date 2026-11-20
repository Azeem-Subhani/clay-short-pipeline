"""Child's school bag sitting on the floor, front (pocket) toward -Y."""
from stagekit import build

ASSET = dict(id="prop_school_bag", name="School bag", kind="prop", tags=["bag", "school", "backpack", "child"],
             notes="0.3 x 0.16 x 0.38 m. Soft rounded shapes; a quiet background clue for stories about a child.")


def build_asset():
    red, dark = "#B4463A", "#7E2F28"
    parts = [
        build.box("bag_body", (0.3, 0.16, 0.36), (0, 0, 0), red, bevel=0.06),
        build.box("bag_pocket", (0.22, 0.05, 0.17), (0, -0.095, 0.03), dark, bevel=0.03),
        build.box("bag_flap", (0.31, 0.17, 0.1), (0, -0.005, 0.28), dark, bevel=0.04),
        build.box("bag_handle", (0.1, 0.03, 0.03), (0, 0.02, 0.375), "#2A2D33", bevel=0.012),
    ]
    for sx in (-1, 1):
        parts.append(build.box(f"bag_strap{sx}", (0.04, 0.02, 0.3), (sx * 0.09, 0.085, 0.03), "#2A2D33", bevel=0.008))
    return build.group("prop_school_bag", parts)
