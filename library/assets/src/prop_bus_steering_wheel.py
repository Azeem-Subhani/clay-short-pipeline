"""A big bus steering wheel: dark rim, three spokes, a hub with a red horn button."""
import math

from stagekit import build, core

ASSET = dict(id="prop_bus_steering_wheel", name="Bus steering wheel", kind="prop", tags=["steering wheel", "bus", "driver", "wheel", "vehicle"],
             era=["modern"], source="built", license="project",
             notes="0.46 m across, upright in the XZ plane facing -Y, resting on the rim; hold the rim: driver.hold(wheel, 'R', t, offset=(-0.2, 0, -0.23)); turn=True to steer")


def build_asset():
    P = "wheel."; R = 0.21; parts = []
    n = 20
    for i in range(n):
        a = math.tau * i / n
        parts.append(build.ball(P + f"rim{i}", 0.024, (R * math.cos(a), 0, 0.23 - 0.024 + R * math.sin(a)), "#2B2A2E", squash=(1.6, 1.0, 1.6), subdiv=1))
    for a in (90, 210, 330):
        for k in range(1, 6):
            r = R * k / 6
            parts.append(build.ball(P + f"spoke{a}_{k}", 0.02, (r * math.cos(math.radians(a)), 0, 0.23 - 0.02 + r * math.sin(math.radians(a))), "#3A393E",
                                    squash=(1.3, 0.8, 1.3), subdiv=1))
    hub = build.ball(P + "hub", 0.06, (0, 0, 0.17), "#2B2A2E", squash=(1, 0.5, 1))
    horn = build.ball(P + "horn", 0.032, (0, -0.022, 0.198), "#B8322E", squash=(1, 0.5, 1))
    return build.group("prop_bus_steering_wheel", parts + [hub, horn])
