"""A small leather coin purse, drawn shut with a cord, two gold coins peeping out of the neck."""
from stagekit import build

ASSET = dict(id="prop_coin_purse", name="Leather coin purse", kind="prop", tags=["purse", "coins", "money", "pickpocket", "pouch", "gold"],
             era=["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.13 m tall. Hold it by the neck: thief.hold(purse, 'R', t, offset=(0, 0, -0.10)); or hang it on a belt.")


def build_asset():
    parts = [build.ball("purse.bag", 0.06, (0, 0, 0), "#7A4E30", squash=(1.0, 0.8, 0.85)),
             build.cyl("purse.neck", 0.022, 0.03, (0, 0, 0.09), "#7A4E30", top_radius=0.038, seg=12),
             build.cyl("purse.cord", 0.027, 0.012, (0, 0, 0.088), "rope", seg=12)]
    for i, x in enumerate((-0.012, 0.014)):
        c = build.cyl(f"purse.coin{i}", 0.02, 0.006, (x, 0, 0.115 + 0.006 * i), "gold", seg=14)
        c.rotation_euler.y = 0.5 * (1 if i else -1)
        parts.append(c)
    return build.group("prop_coin_purse", parts)
