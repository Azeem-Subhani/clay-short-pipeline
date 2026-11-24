"""A fortune-teller's card: a cream card with a dark border and a gold star, standing upright."""
import math

from stagekit import build

ASSET = dict(id="prop_fortune_card", name="Fortune-teller's card (star)", kind="prop", tags=["card", "tarot", "fortune", "star", "playing card", "omen"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.11 x 0.17 m (oversized so it reads on a phone), stands upright on z = 0, face toward -Y (the camera). "
                   "Hold it by the lower edge: hold(card, 'R', t, offset=(0, 0, -0.03)).")


def build_asset():
    parts = [
        build.box("card.border", (0.11, 0.006, 0.17), (0, 0, 0), "#6B4A33", bevel=0.003),
        build.box("card.face", (0.094, 0.004, 0.154), (0, -0.003, 0.008), "#F6EEDD", bevel=0.002),
        build.ball("card.star_core", 0.014, (0, -0.006, 0.071), "gold", squash=(1, 0.25, 1)),
    ]
    for k in range(4):       # eight rays: four thin bars crossing at the centre
        ray = build.box(f"card.ray{k}", (0.008, 0.003, 0.066 if k % 2 == 0 else 0.046), (0, 0, 0), "gold", bevel=0.002)
        ray.rotation_euler.y = math.radians(45 * k)
        h = 0.033 if k % 2 == 0 else 0.023
        ray.location = (h * math.sin(math.radians(45 * k)) * -1, -0.0065, 0.085 - h * math.cos(math.radians(45 * k)))
        parts.append(ray)
    return build.group("prop_fortune_card", parts)
