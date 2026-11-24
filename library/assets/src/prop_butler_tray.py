"""Butler's silver tray with a cloche: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_butler_tray.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_butler_tray", name="Butler's silver tray with a cloche", kind="prop", tags=['tray', 'salver', 'silver', 'serve', 'butler', 'waiter', 'cloche'],
             era=['victorian', 'modern'], source="built", license="project",
             notes="38 cm round silver tray with a domed cover, 16 cm tall; origin under its centre: carry it on a flat hand, hold(tray, 'R', t)")


def build_asset():
    parts = []
    parts.append(build.cyl("tray.plate", 0.19, 0.012, (0, 0, 0), "steel_bright", seg=32))
    parts.append(build.cyl("tray.rim", 0.19, 0.01, (0, 0, 0.01), "steel_bright", top_radius=0.2, seg=32))
    for i, (r0, r1, h, z) in enumerate(((0.13, 0.122, 0.05, 0.02), (0.122, 0.09, 0.04, 0.07), (0.09, 0.03, 0.025, 0.11))):      # the dome
        parts.append(build.cyl(f"tray.cloche{i}", r0, h, (0, 0, z), "steel_bright", top_radius=r1, seg=32))
    parts.append(build.ball("tray.knob", 0.018, (0, 0, 0.132), "gold"))
    return build.group("prop_butler_tray", parts)
