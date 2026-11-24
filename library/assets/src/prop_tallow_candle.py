"""A thick tallow candle with a wick and a small flame (no holder: the candlemaker carries it in the hand)."""
from stagekit import build

ASSET = dict(id="prop_tallow_candle", name="Tallow candle, lit", kind="prop", tags=["candle", "light", "flame", "candlemaker", "wax", "tallow"],
             era=["ancient", "medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.24 m tall with the flame, stands on z = 0. Children a shot can animate or hide: 'candle.flame' "
                   "(scale it to flicker, hide it for an unlit candle). Hold it low: hold(candle, 'R', t, offset=(0, 0, -0.06)).")


def build_asset():
    wax = "#F3E7CF"
    parts = [
        build.cyl("candle.body", 0.028, 0.17, (0, 0, 0), wax, top_radius=0.026, seg=16),
        build.cyl("candle.rim", 0.029, 0.012, (0, 0, 0.165), "#FAF2DE", top_radius=0.024, seg=16),
        build.ball("candle.drip", 0.012, (0.024, -0.012, 0.11), wax, squash=(0.8, 0.8, 2.2)),
        build.cyl("candle.wick", 0.004, 0.022, (0, 0, 0.175), "#3A2E28", seg=6),
        build.ball("candle.flame", 0.016, (0, 0, 0.192), "#F6B63C", squash=(0.9, 0.9, 1.7)),
        build.ball("candle.flame_core", 0.008, (0, 0, 0.196), "#FFF1B8", squash=(0.9, 1.3, 1.6)),
    ]
    return build.group("prop_tallow_candle", parts)
