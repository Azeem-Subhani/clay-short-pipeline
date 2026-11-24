"""Innkeeper's ring of keys: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_innkeeper_keyring.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_innkeeper_keyring", name="Innkeeper's ring of keys", kind="prop", tags=["key", "keys", "keyring", "inn", "lock"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="a chunky iron ring 9 cm across with two brass keys hanging below it, 25 cm tall, flat in the X-Z plane, standing on z = 0; "
                   "hold it by the ring: hold(keys, 'R', t, offset=(0, 0, -0.21))")


def build_asset():
    parts = []
    for i in range(16):      # the ring
        a = 2 * math.pi * i / 16
        parts.append(build.ball(f"keys.ring{i}", 0.009, (0.045 * math.cos(a), 0, 0.2 + 0.045 * math.sin(a)), "iron_dark", subdiv=1))
    for k, dx in enumerate((-0.022, 0.024)):
        y = 0.012 * k
        bow = build.cyl(f"keys.bow{k}", 0.024, 0.01, (dx, y + 0.005, 0.135), "gold", seg=14)
        bow.rotation_euler.x = math.radians(90)
        shank = build.box(f"keys.shank{k}", (0.012, 0.01, 0.115), (dx, y, 0.0), "gold", bevel=0.002)
        bit = build.box(f"keys.bit{k}", (0.03, 0.01, 0.03), (dx + 0.018, y, 0.004), "gold", bevel=0.002)
        parts += [bow, shank, bit]
    return build.group("prop_innkeeper_keyring", parts)
