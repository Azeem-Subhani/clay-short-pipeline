"""Set: a dark open field falling toward a road where two police cars wait. The runners come from +Y.
car_a faces the field with its headlights on: its light bar is the foreground of the wide frame, and its lights are
what finally shows us his face."""
from stagekit import assets, build, lights


def build_set():
    build.ground("field", 160, "#1F2B27", relief=1.6, seed=11, keep_flat_radius=22)
    build.backdrop("sky", "#24337A", "#0D1640", strength=0.75, radius=70, height=45, arc_deg=360)
    build.slab("road", (90, 6.5), (0, -9.5, 0.02), "#26282D", thickness=0.05)
    cars = [assets.use("vehicle_police_car", "car_a", at=(0.75, -7.4, 0.02), rot_z=180),
            assets.use("vehicle_police_car", "car_b", at=(-4.2, -8.6, 0.02), rot_z=205)]
    for i in range(7):
        build.box(f"post{i}", (0.12, 0.12, 1.1), (-13 + i * 4.4, -5.6, 0), "#4A443C", bevel=0.02)
    build.scatter(build.bush, 14, (-16, 16, -3, 24), seed=6, avoid=[(0.3, 5, 3.0), (0.3, -3, 3.0)], color="#1E322B", size=0.8)
    build.scatter(build.tree, 12, (-34, 34, 26, 44), seed=3, min_gap=4, kind="pine", height=9.0, color="#182B28", trunk_color="#2B211C")
    rig = lights.rig("night_moon", subject=(0.3, -3.0, 1.4), key_azimuth=150, key_elevation=40)
    return {"rig": rig, "cars": cars}
