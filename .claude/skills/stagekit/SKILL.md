---
name: stagekit
description: How to build a shot in Blender for this pipeline - the stagekit Python toolkit (sets, clay props, characters from the pack, light rigs, camera moves, focus), the shot-script contract, and the stills/checks loop. Use when writing or fixing blender/set_*.py or blender/shNN.py, or building an asset.
---

# stagekit: building shots in Blender

A shot is a short Python file. `tools/clip.py` runs it headless in Blender 5.3 (EEVEE), renders review stills, and measures framing, focus, occlusion and exposure. You write the file, look at the stills, fix, repeat.

Worked example to read first: `examples/the-boy-in-the-basement/blender/` (four sets, five shots). The toolkit source is `tools/blender/stagekit/` and every function has a docstring: read the source when you need a detail.

## The contract

```
output/clips/<clip>/blender/set_<set_id>.py    def build_set(**opts) -> dict of handles   (the place AND its one light rig)
output/clips/<clip>/blender/<shot_id>.py        def build_shot(shot)                       (cast, action, camera for one shot)
```

```python
"""sh03 - one line on what this shot is for."""
import set_basement
from stagekit import camera, cast, core, lights, build, assets

def build_shot(shot):
    S = set_basement.build_set()                        # same set + same light as every other shot in this place
    boy = cast.from_plan("boy")                         # the cast spec comes from shotplan.json
    boy.lie(at=(-0.35, -0.3), head_toward=-90, z=S["mattress_top"])
    man = cast.from_plan("man", at=(1.9, 1.2), facing=-60)

    t = shot.t("He crossed")                            # seconds into the shot when the narrator says it
    arrive = man.walk(t, to=(-0.75, 0.62), speed=0.55)  # returns the arrival time
    boy.brows("shocked", shot.t("mouth"))
    man.idle(); boy.idle()                              # breathing and blinks: nothing freezes

    cam = camera.Camera(lens=35, blur="medium")
    cam.at(0.0, pos=(-0.2, -3.3, 0.55), aim=(1.3, 2.25, 2.5))        # first key needs pos and aim
    cam.at(shot.t("a small boy"), pos=(-1.5, -2.35, 0.62), aim=boy.head, focus=boy.head)   # crane down to him
    cam.hold(shot.seconds)

    shot.moment("boy_alone", shot.t("a small boy") + 1.0)   # where to render a review still
```

Run and look:

```
python tools/clip.py stills <clip> sh03          # draft stills -> review/sh03/sheet.png + checks.json
python tools/clip.py stills <clip> sh03 --quality preview    # half-res, real blur and shadows, for a closer look
```

Read `review/<shot>/sheet.png` (stills left to right in time order, safe area in yellow) and the `[check]` lines. Fix what is wrong, run again. A build error prints a traceback and `BUILD FAILED`.

## Space and time

- Metres, Z up. **The camera side is −Y.** Characters face −Y at `facing=0`; `90` = screen-right (+X), `-90` = screen-left, `180` = away from camera. Build the back wall on +Y and leave −Y open.
- `at=(x, y, z)` is where a thing **rests** (bottom centre). `z=0` is the floor.
- Time is seconds from the start of the shot. `shot.seconds` is its length (from the voice take). `shot.t("phrase", edge="start"|"end", offset=0.0)` finds a spoken phrase. Start moves a little before the word they land on.
- Every keyed move eases in and out.

## shot

`shot.t(phrase)` · `shot.seconds` · `shot.f(t)` frame number · `shot.moment(name, t)` review still · `shot.subject(name, obj_or_anchor_or_point, moments=[…])` something the viewer must read (checked for framing, focus, occlusion, exposure; `moments` limits the check to the review moments where it matters; characters register their head automatically, remove with `shot.subjects.pop("man")` when a face is hidden on purpose) · `shot.plan` this shot's plan entry · `shot.notes.append("...")` a note for the reviewer.

## build: sets and clay props

Materials: `build.clay("#hex")` matte clay · `build.glow("#hex", strength)` for things that are light (pair with `lights.practical`) · `build.glass()` · `build.set_glow(obj, strength, t)` to key a glow.

Primitives (all bevelled, clay): `box(name, size, at, color)` · `cyl(name, radius, height, at, color, top_radius=)` · `ball(name, radius, at, color, squash=)` · `slab(name, (w, d), at, color)` (top surface at `at`) · `group(name, parts, at, rot_z)`.

Places: `room(name, width, depth, height, wall_color=, floor_color=, ceiling=, open_sides=("front",), openings={"back": [(cx, z0, w, h)]})` · `wall(...)` · `window(name, w, h, at, lit="#hex"|None)` · `door(name, at=, open_deg=)` (hinge empty is `group["pivot"]`) · `ground(name, size, color, relief=)` · `backdrop(name, horizon_color, top_color, strength)` self-lit sky · `house(name, at=, windows=, lit=)`.

Furniture and dressing: `table` · `chair` (seat 0.45) · `bed` (mattress top 0.5) · `shelf` (with books) · `crate` · `lamp(name, "table"|"floor"|"hanging"|"street", at=)` (returns `["bulb_point"]`) · `frame_picture` · `cup` · `rug` · `tree(kind="round"|"pine"|"bare")` · `bush` · `rock` · `fence` · `scatter(maker, count, area, avoid=[(x, y, r)])`.

Need something else? Combine primitives, or write plain `bpy`/`bmesh` and finish it with `build.finish(obj, color)` (bevel + smooth + clay). For anything reusable, make it a library asset instead (see the `asset-library` skill).

## cast: characters

`cast.from_plan("id", at=(x, y), facing=deg)` spawns the plan's character. `cast.cast(name, preset=… | base=…, …)` spawns one directly.

| Call | Does |
|---|---|
| `a.place(at, facing)` · `a.face(target_or_deg, t, duration)` | stand somewhere; turn the body |
| `a.walk(t0, to=(x, y), speed=1.0)` → arrival time | walk a straight line; `0.55` sneaks, `1.3` hurries. Chain: `t2 = a.walk(t1, to=B)` |
| `a.pose(name_or_spec, t, blend)` | `relaxed, hand_up_R/L, reach_R/L, point_R/L, arms_up, hands_to_face, carry, lean_forward, lean_back, bow_head, head_up, slump, crouch, sit` or a custom list like `[("upper_arm_fk.R", "X", -60)]` (X− raises a limb forward, X+ bends down/forward) |
| `a.sit(at, facing, seat_height)` · `a.lie(at, head_toward, z)` | already seated / lying when the shot starts |
| `a.look(target or (yaw, pitch), t, blend)` | head turn. Eyes lead: look 0.3 s before acting |
| `a.brows(preset, t)` | `neutral calm worried stern shocked arched cocky concerned proud`: the fastest readable emotion |
| `a.blink(t)` · `a.eyes_closed(True)` · `a.idle()` | `idle()` once per character per shot, after walks and poses |
| `a.hold(prop, "R", offset, rotation_deg)` | prop follows the hand |
| `a.carry(other)` | adult carries a child in both arms. Needs care: keep it wide or frame faces only |
| `a.head`, `a.chest`, `a.hand_R`, `a.hand_L`, `a.feet` | anchors that follow the animation: use as `aim=`, `focus=`, `look` targets; `.point()` gives the position now |

Adults are 1.76 m, the child 1.1 m. The characters have no mouth: emotion is brows, head and body.

## lights: one rig per set

`rig = lights.rig(mood, subject=(x, y, z), key_azimuth=, key_elevation=, distance=, strength=, fill=, rim=, ambient=)` builds key + fill + rim + world. Call it **once, inside `build_set`**.

Moods: `day_soft golden_hour overcast night_moon interior_warm interior_cold interior_night dread candle relief`. Azimuth is measured from the camera side: `-60` = key from screen-left front, `90` = from screen-right, `140` = from behind-right. Keep the key 35–80° off the camera axis. Indoors keep `distance` inside the room.

Add: `lights.practical(name, at, color, power, kind="POINT"|"AREA"|"SPOT", aim=, size=, rig_=rig)` · `lights.eye_light(cam.ob, actor.head)` · `lights.change(light, t0, t1, power=, color=)` · `lights.switch(light, t, on=False)` · `lights.flash(name, at, t0=, period=)` police lights · `lights.haze(0.01)`.

## camera: one per shot

```python
cam = camera.Camera(lens=40, blur="medium")       # blur: none | light | medium | strong | macro
cam.at(t, pos=, aim=, lens=, focus=, blur=)        # anything left out keeps its value: two keys = one move
cam.hold(t)                                        # stay as you are until t; the next key starts from here
cam.push(t0, t1, 0.10) / cam.pull(t0, t1, 0.15)    # dolly toward / away from the aim by a fraction of the distance
cam.rack(t, target, duration=0.7)                  # focus shift, finishing at t
cam.follow(actor.head, t0, t1, aim=True, focus=True, lag=0.25)   # keep a moving subject framed and sharp from a fixed camera
cam.track(actor.head, t0, t1)                      # travel with a moving subject
```

`aim`, `focus` and targets take a point, an object, or an anchor (`actor.head`).

## assets

`assets.find("lamp")` · `assets.use("prop_wire_cutters", at=, rot_z=, scale=)` → root object · see the `asset-library` skill for sourcing and saving.

## What the checks tell you

| Message | Usual fix |
|---|---|
| subject sits under the Shorts UI | move the camera or the aim so it is inside the yellow box |
| subject is hidden behind X | move X, the subject, or the camera |
| nothing registered is in focus | `cam.at(focus=…)`, `cam.rack`, or `cam.follow(..., focus=True)` |
| subject too dark to read | raise `rim=`/`fill=`, add a practical, or turn the subject to the key (ignore for a deliberate silhouette, and say so in `shot.notes`) |
| burnt white | halve that light's power or enlarge it |
| most of the frame is pure black / empty black top | sky backdrop, ceiling, taller walls, more ambient, or tilt down |

Checks do not judge composition, pose or mood. Look at the sheet: is the eye drawn to the right thing, do poses read, does anything float or intersect?

## Good habits

- Build the set and its light in `set_<id>.py`; shots only add cast, action and camera. That is what keeps light identical between shots.
- Key to words (`shot.t`), and mark a `shot.moment` at every beat the plan cares about, so the reviewer sees them.
- Change one thing per stills run when you are tuning; it takes under a minute at draft quality on a GPU.
- Do not change render settings, resolution or colour management in a shot. They are locked in `style/style.json`.
- At most three stills rounds per shot for look. If an action still reads badly, restage it (see the style guide) instead of polishing.
