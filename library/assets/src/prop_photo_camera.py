"""A chunky photo camera: dark body with a grey top plate, a big lens with a glass front, a red shutter button and a flash."""
from stagekit import build

ASSET = dict(id="prop_photo_camera", name="Photo camera", kind="prop", tags=["camera", "photo", "photographer", "reporter", "tourist", "lens"],
             era=["modern"], source="built", license="project",
             notes="0.20 m wide, 0.14 m tall (drawn a little large so it reads on a phone), lens toward -Y, resting on its base; "
                   "photographer.hold(camera, 'R', t), raise both hands to the face to shoot")


def build_asset():
    body = "#2E2A2E"
    lens = build.cyl("cam.lens", 0.048, 0.07, (0, 0, 0), body, top_radius=0.044, seg=24)
    lens.rotation_euler.x = 1.5708
    lens.location = (0, -0.035, 0.062)
    glass = build.cyl("cam.glass", 0.034, 0.008, (0, 0, 0), "#7FB0D0", seg=24)
    glass.rotation_euler.x = 1.5708
    glass.location = (0, -0.104, 0.062)
    ring = build.cyl("cam.ring", 0.052, 0.014, (0, 0, 0), "steel_bright", seg=24)
    ring.rotation_euler.x = 1.5708
    ring.location = (0, -0.04, 0.062)
    parts = [
        build.box("cam.body", (0.20, 0.07, 0.115), (0, 0, 0), body, bevel=0.012),
        build.box("cam.top", (0.20, 0.07, 0.022), (0, 0, 0.115), "#B8BCC4", bevel=0.008),
        build.box("cam.prism", (0.07, 0.06, 0.03), (0, 0, 0.134), "#B8BCC4", bevel=0.008),
        build.cyl("cam.button", 0.013, 0.012, (0.07, 0, 0.137), "#C8302C", seg=12),
        build.box("cam.flash", (0.035, 0.008, 0.02), (-0.065, -0.036, 0.085), "#F6F1E4", bevel=0.003),
        lens, ring, glass,
    ]
    return build.group("prop_photo_camera", parts)
