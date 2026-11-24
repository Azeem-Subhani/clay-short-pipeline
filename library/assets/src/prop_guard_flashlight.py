"""A chunky black security flashlight with a wide head and a pale yellow lens."""
import math

from stagekit import build, core

ASSET = dict(id="prop_guard_flashlight", name="Security flashlight", kind="prop", tags=["flashlight", "torch", "guard", "security", "night", "light"],
             era=["modern"], source="built", license="project",
             notes="0.26 m long, standing on its tail cap with the lens up; hold the barrel: guard.hold(light, 'R', t, offset=(0, 0, -0.08)); aim with turn=True")


def build_asset():
    P = "flashlight."
    cap = build.cyl(P + "cap", 0.026, 0.02, (0, 0, 0), "#1F1E22", seg=14)
    barrel = build.cyl(P + "barrel", 0.022, 0.15, (0, 0, 0.02), "#2B2A2E", seg=14)
    switch = build.box(P + "switch", (0.014, 0.012, 0.03), (0, -0.022, 0.10), "#B8322E", bevel=0.004)
    neck = build.cyl(P + "neck", 0.022, 0.05, (0, 0, 0.17), "#2B2A2E", top_radius=0.045, seg=16)
    head = build.cyl(P + "head", 0.045, 0.035, (0, 0, 0.22), "#1F1E22", seg=16)
    lens = build.cyl(P + "lens", 0.038, 0.006, (0, 0, 0.255), "#FFE9A0", seg=16)
    return build.group("prop_guard_flashlight", [cap, barrel, switch, neck, head, lens])
