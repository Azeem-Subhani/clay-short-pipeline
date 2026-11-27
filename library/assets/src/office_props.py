"""File the NORTHLINE office hand props in library/assets (props/*.blend, index.json, previews/*.png).

    blender -b --factory-startup --python library/assets/src/office_props.py [-- id id ...]

Each prop is a furnish piece (tools/blender/stagekit/furnish.py) wrapped so its origin is the point it rests on (middle of its footprint, on
z = 0) and its front faces -Y, then saved with assets.save and indexed with a `grip` (and `grip_at` for a rod-like handle) that
aj_hands.prop_kind reads. Moving parts and screens keep their names: furnish.part(prop, "lid" / "flap" / "led") and furnish.screen(prop).
A shot gets one with:   prop = assets.use("prop_coffee_cup", at=(x, y, z))   and hands it to  actor.do("pick_up", prop, hit=shot.t("..."))
The pieces are also in the kit: furnish.make("coffee_cup", at=...), so a set can put them on a desk without touching the library.
Source: built here. Licence: own. Era: modern.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "tools" / "blender"))
sys.dont_write_bytecode = True

import bpy  # noqa: E402

import stagekit  # noqa: E402,F401
from stagekit import assets, build, camera, core, furnish, lights  # noqa: E402

PROPS = [
    # id, piece, options, name, tags, grip, notes
    ("prop_coffee_cup", "coffee_cup", {}, "Takeaway coffee cup with lid and sleeve", ["coffee", "cup", "drink", "takeaway", "paper cup"], "palm",
     "0.08 m wide, 0.125 m tall, standing on its base, origin under its middle: wrap the hand round the sleeve (hold(cup, 'R', t)). Lid with a sip hole, brown sleeve."),
    ("prop_cup_carrier", "cup_carrier", {}, "Cardboard two-cup carrier with two coffees", ["coffee", "cup", "carrier", "tray", "takeaway", "two cups"], "palm",
     "0.20 x 0.10 m tray, 0.135 m tall with both cups lidded; origin under its middle. Carry it flat on one palm, or one in each hand by taking the cups out with a second prop."),
    ("prop_cardboard_box_desk", "cardboard_box_desk", {}, "Cardboard box packed with desk things", ["box", "cardboard", "desk", "belongings", "fired", "moving", "plant", "mug"], "palm2",
     "0.40 x 0.30 x 0.26 m box with its flaps folded out and a plant, a mug, a framed photo, a folder and a notebook sticking out; hand slots in the short ends (+/-X). Origin under its middle. Carry it in both hands under the long sides: hold(box, 'LR', t)."),
    ("prop_laptop_open", "laptop_open", {}, "Open laptop with a screen slot", ["laptop", "computer", "open", "screen", "unlocked"], "palm",
     "0.32 x 0.22 m base, lid up 105 degrees, origin under the middle of the base. The lid is furnish.part(laptop, 'lid') (rotate about X; 0 degrees of opening = rotate X +90 to shut); the screen is furnish.screen(laptop): furnish.screen_set_image(laptop, path) or screen_set_image_builtin(laptop, 'desktop'|'slide'|'off'|'listing')."),
    ("prop_laptop_closed", "laptop_closed", {}, "Closed laptop", ["laptop", "computer", "closed", "silver"], "palm",
     "0.32 x 0.22 x 0.018 m silver slab, origin under the middle. Pick it up by the edges; slides into a bag."),
    ("prop_messenger_bag", "messenger_bag", {}, "Leather messenger bag with flap and strap", ["bag", "messenger", "leather", "satchel", "shoulder bag", "thief"], "power",
     "0.38 x 0.12 x 0.28 m body standing on its base, origin under its middle; the long strap arches 0.63 m above the floor: hold it by the strap (grip_at 0.9 = the top of the strap). The flap is furnish.part(bag, 'flap'), hinged along the top back edge: rotate X by -100 degrees to open it for a laptop to slide in (messenger_bag(open_flap=100) builds it open)."),
    ("prop_keycard_lanyard", "keycard_lanyard", {}, "Access card on a teal lanyard", ["keycard", "card", "badge", "lanyard", "access", "pass", "employee"], "pinch",
     "Card 0.086 x 0.054 m with a photo, a chip and a teal band, resting on its lower edge at z = 0; the cord rises from its clip to a loop 0.43 m up. Faces -Y. Pinch the card (or the cord) to tap it on a reader; hang it round the neck by moving it with the chest."),
    ("prop_smartphone", "smartphone", {}, "Smartphone with a screen slot", ["phone", "smartphone", "mobile", "screen"], "palm",
     "0.071 x 0.0085 x 0.147 m, standing on its lower edge, screen toward -Y, origin under the middle. The screen is furnish.screen(phone): furnish.screen_set_image(phone, path)."),
    ("prop_security_radio", "security_radio", {}, "Security guard's two-way radio", ["radio", "walkie talkie", "security", "guard", "two-way"], "palm",
     "0.056 x 0.034 x 0.115 m body with a 0.09 m antenna (0.205 m overall), standing on its base, origin under its middle. Status lamp: furnish.part(radio, 'led'), furnish.lamp_state(lamp, 'red'|'green', t)."),
    ("prop_file_stack", "file_stack", {}, "Stack of client files", ["files", "folders", "papers", "stack", "documents", "client"], "palm",
     "0.31 x 0.235 m stack of manila folders and papers, about 0.06 m high, a binder clip on one edge and a 'CLIENT FILES' label on the top folder; origin under its middle."),
]
GRIP_AT = {"prop_messenger_bag": 0.9}


def preview(path: Path, root):
    """The same neutral stage run_asset.py uses: a floor, soft daylight, a three-quarter view."""
    sx, sy, sz = assets.measure(root)
    lo, hi = core.world_bbox([o for o in [root, *root.children_recursive] if o.type == "MESH"])
    c = (lo + hi) / 2
    size = max(sx, sy, sz, 0.05)
    build.ground("preview_floor", size * 16, "#8E8A84", relief=0.0, coll="PREVIEW")
    lights.rig("day_soft", sun_from=35)
    cam = camera.Camera()
    d = size * 2.3 + 0.2
    cam.view("preview", 0.0, pos=(c.x - d * 0.55, c.y - d * 0.8, c.z + d * 0.42), aim=tuple(c), lens=60)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 640, 640
    sc.render.filepath = str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for aid, piece, opts, name, tags, grip, notes in PROPS:
        if argv and aid not in argv:
            continue
        stagekit.begin("asset_preview", 1.0, "preview")
        ob = furnish.make(piece, at=(0, 0, 0), **opts)
        w, d, h = furnish.footprint(ob)
        root = core.empty(aid, (0, 0, 0), "SET", 0.1)
        ob.parent = root
        ob.location = (0.0, d / 2, 0.0)                       # the footprint's middle over the origin
        bpy.context.view_layer.update()
        prev_rel = f"previews/{aid}.png"
        entry = assets.save(root, aid, name, "prop", tags, source="built", license="own", notes=notes, preview=prev_rel, era=("modern",))
        idx = assets._load()
        for a in idx["assets"]:
            if a["id"] == aid:
                a["grip"] = grip
                if aid in GRIP_AT:
                    a["grip_at"] = GRIP_AT[aid]
        assets._store(idx)
        preview(assets.LIB / prev_rel, root)
        print(f"[office_props] {aid}: {entry['size_m']} grip={grip} -> {assets.LIB / entry['file']}")


main()
