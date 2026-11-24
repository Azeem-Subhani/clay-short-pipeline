"""A rolled parchment scroll tied with a red ribbon."""
import math

from stagekit import build

ASSET = dict(id="prop_scribe_scroll", name="Rolled parchment scroll", kind="prop", tags=["scroll", "parchment", "letter", "decree", "scribe", "paper"],
             era=["ancient", "medieval", "renaissance", "age_of_sail", "fantasy"], source="built", license="project",
             notes="0.34 m long, lies along X on z = 0; the origin is under its middle (the ribbon), where a hand holds it. "
                   "Turn it upright in the hand with rot or hold(..., turn=True).")


def build_asset():
    r = 0.032
    parts = []
    roll = build.cyl("scroll.roll", r, 0.30, (0, 0, 0), "#EFDDB5", seg=18)
    roll.rotation_euler.y = math.radians(90)
    roll.location = (-0.15, 0, r)
    parts.append(roll)
    for sx in (-1, 1):       # the darker spiral ends and a loose lip of paper
        end = build.cyl(f"scroll.end{sx}", r * 0.62, 0.02, (0, 0, 0), "#D9BF8E", seg=14)
        end.rotation_euler.y = math.radians(90)
        end.location = (sx * 0.16 - 0.01, 0, r)
        parts.append(end)
    parts.append(build.box("scroll.lip", (0.30, 0.03, 0.006), (0, -r * 0.8, r * 1.15), "#F6E8C6", bevel=0.002))
    band = build.cyl("scroll.ribbon", r * 1.08, 0.035, (0, 0, 0), "#A63A32", seg=18)
    band.rotation_euler.y = math.radians(90)
    band.location = (-0.0175, 0, r)
    parts.append(band)
    parts.append(build.ball("scroll.seal", 0.02, (0, -r * 1.0, r * 0.6), "#8C2B25", squash=(1, 0.5, 1)))
    return build.group("prop_scribe_scroll", parts)
