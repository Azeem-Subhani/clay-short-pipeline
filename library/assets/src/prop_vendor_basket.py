"""A street vendor's wicker basket with a hoop handle, a cloth and a heap of apples and a loaf."""
from stagekit import build

ASSET = dict(id="prop_vendor_basket", name="Vendor's basket of wares", kind="prop", tags=["basket", "vendor", "market", "apples", "bread", "wicker"],
             era=["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.44 m across, 0.40 m to the top of the handle. Carry it by the hoop: vendor.hold(basket, 'L', t, offset=(0, 0, -0.38)), or set it on a stall.")


def build_asset():
    parts = [build.cyl("basket.body", 0.15, 0.17, (0, 0, 0), "rope", top_radius=0.21, seg=20),
             build.cyl("basket.rim", 0.22, 0.025, (0, 0, 0.165), "oak_planks", seg=20),
             build.cyl("basket.cloth", 0.20, 0.02, (0, 0, 0.175), "cloth", seg=20)]
    for i, (x, y, c) in enumerate(((-0.09, -0.04, "#B5452E"), (0.0, 0.07, "#C8553A"), (0.09, -0.05, "#B5452E"), (-0.02, -0.09, "#9BAA4E"))):
        parts.append(build.ball(f"basket.apple{i}", 0.045, (x, y, 0.185), c))
    parts.append(build.ball("basket.loaf", 0.07, (0.06, 0.06, 0.185), "#C99A5B", squash=(1.5, 0.8, 0.7)))
    # hoop handle
    for sx in (-1, 1):
        parts.append(build.box(f"basket.h{sx}", (0.02, 0.03, 0.22), (sx * 0.20, 0, 0.17), "oak_planks", bevel=0.005))
    parts.append(build.box("basket.htop", (0.42, 0.03, 0.02), (0, 0, 0.38), "oak_planks", bevel=0.005))
    return build.group("prop_vendor_basket", parts)
