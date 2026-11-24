"""A toy-like ray gun: rounded silver body, green rings round the barrel, a glowing-green tip ball, a dark grip at the origin."""
from stagekit import build

ASSET = dict(id="prop_alien_ray_gun", name="Alien ray gun", kind="prop", tags=["ray gun", "blaster", "alien", "space", "weapon", "sci-fi"],
             era=["modern", "fantasy"], source="built", license="project",
             notes="0.30 m long, barrel toward +X, standing on its grip; alien.hold(gun, 'R', t); point the arm to aim")


def build_asset():
    parts = [
        build.box("ray.grip", (0.04, 0.035, 0.12), (0, 0, 0), "#3E3A3A", bevel=0.01),
        build.ball("ray.body", 0.06, (0.03, 0, 0.10), "steel_bright", squash=(1.5, 0.8, 0.85)),
        build.ball("ray.fin", 0.03, (-0.05, 0, 0.17), "#C8302C", squash=(1.4, 0.4, 1.0)),
    ]
    barrel = build.cyl("ray.barrel", 0.022, 0.15, (0, 0, 0), "steel_bright", seg=16)
    barrel.rotation_euler.y = 1.5708
    barrel.location = (0.09, 0, 0.151)
    parts.append(barrel)
    for i, (x, rad) in enumerate(((0.13, 0.040), (0.165, 0.034), (0.20, 0.028))):
        ring = build.cyl(f"ray.ring{i}", rad, 0.012, (0, 0, 0), "#7BC96F", seg=20)
        ring.rotation_euler.y = 1.5708
        ring.location = (x, 0, 0.151)
        parts.append(ring)
    parts.append(build.ball("ray.tip", 0.024, (0.25, 0, 0.127), "#B6F29A"))
    return build.group("prop_alien_ray_gun", parts)
