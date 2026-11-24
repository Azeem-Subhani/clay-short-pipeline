---
name: stagekit
description: How to build a set and stage a shot in Blender for this pipeline - the stagekit Python toolkit (2D cast from the character pack with costumes, poses, hand contact and props; the 3D world kit with named surfaces; light rigs; camera views; effects), the file contract, and the stills/checks loop. Use when writing or fixing blender/set_*.py or blender/shNN.py, or building an asset.
---

# stagekit: sets and shots in Blender

A shot is a short Python file. `tools/clip.py` runs it headless in Blender 5.3 (EEVEE), renders two review stills per camera view, and measures framing, hidden faces, captions, grounding and exposure. You write the file, look at the stills, fix, repeat.

Read first: `examples/the-ring-in-the-pond/blender/` (one set, four shots, twenty views), `docs/poses.png` (every named pose in the three views) and `docs/ACTIONS.md` (every named action). The toolkit source is `tools/blender/stagekit/`; every function has a docstring.

## The contract

```
output/clips/<clip>/blender/set_<set_id>.py    def build_set(time="day_clear") -> dict    the place, its marks, its light for that time of day
output/clips/<clip>/blender/<shot_id>.py        def build_shot(shot)                       cast, action keyed to words, camera views
```

```python
"""sh04 - one line on what this shot is for."""
import set_pond_garden as sp
from stagekit import build, camera, cast, core, fx

def build_shot(shot):
    S = sp.build_set("morning")                         # same place, the light of this shot's `time`
    M, P = S["mark"], S["pond"]
    gardener = cast.from_plan("gardener", at=M["gardener"], face="right")     # costume comes from shotplan.json
    queen = cast.from_plan("queen", at=M["queen"], face="left")
    ring = build.ring("ring", at=M["ring_rest"])
    t_walk, t_lift, t_out = shot.t("She walked to the gate"), shot.t("lifted"), shot.t("The water ran out")   # seconds into the shot

    cam = camera.Camera()                               # views first: a figure's face / view heading is measured from where the camera stands
    cam.view("the_gardener", 0.0, on=[gardener], size="medium", side=12, why="eyes lead the idea")
    cam.push(0.0, t_walk, 0.07)
    cam.view("lifts_the_gate", t_walk, pos=(0.9, 1.5, 2.15), aim=(-0.85, 5.6, 0.95), lens=35, size="full", why="cause: hands on the bar, the board rising")
    cam.view("water_runs_out", t_out, pos=sp.WIDE[0], aim=sp.WIDE[1], lens=sp.WIDE[2], size="wide", why="effect, in the opening wide, so the change shows")

    gardener.eyes(1.0, 0.5, 0.75)                       # eyes lead: she looks at the gate before she moves
    stand = P["gate_stand"]["left"].matrix_world.translation
    arrive = gardener.walk(t_walk, to=(stand.x - 0.45, stand.y), speed=2.8)
    gardener.move(arrive, arrive + 0.22, tuple(stand), arc=0.16)             # a hop up onto the stone
    grab = P["gate_grab"]["left"]
    gardener.reach("R", grab, t_lift - 0.12)            # hands exactly on the bar ...
    up = P["open_gate"](t_lift, t_lift + 0.42)          # ... the board slides up ...
    gardener.reach("R", grab, up, blend=0.4)            # ... and the hands go with it
    gardener.lean(-9, up, 0.4)                          # weight: she leans back as it comes
    P["drain"](t_lift + 0.3, t_out + 0.85)              # effect: water out, level down
    queen.expr("surprised", t_out + 0.15)               # reactions a beat after the cause
    for a in (gardener, queen):
        a.idle()                                        # blinks and breath: nothing freezes
    shot.moment("gate_up", up + 0.2)                    # an extra review still at a moment that must read
```

Run and look:

```
python tools/clip.py stills <clip> sh04                         # draft stills of every view -> review/sh04/sheet.png + checks.json
python tools/clip.py stills <clip> sh04 --views lifts_the_gate  # just one view while you work on it
python tools/clip.py stills <clip> sh04 --quality preview       # half size, for faces, hands and shadows
```

`sheet.png` shows the stills in time order, each stamped with shot, view, time and the words spoken; the yellow box is the Shorts safe area, the blue lines are the caption band. Read the `[check]` and `[note]` lines. A build error prints a traceback and `BUILD FAILED`.

## Space and time

- Metres, Z up. **The camera side is −Y.** +X is screen right, +Y is away from the camera. Keep every camera on the −Y side of the action and screen directions never flip.
- `at=(x, y)` or `(x, y, z)` is where a thing rests. `z=0` is the ground.
- Time is seconds from the start of the shot. `shot.t("phrase", edge="start"|"end", offset=0.0)` finds a spoken phrase; `shot.span("phrase")` gives (start, end). Key everything to words, never to guessed seconds.
- The cast is 3D (`docs/CHARACTERS_3D.md`): real figures the camera can go all the way round. `face="left"|"right"` and `view="front"|"3q"|"side"` turn the whole body, measured from where the camera stands at that moment and then held in the world; `a.heading((x, y), t)` faces a point whatever the camera. Thirteen special bodies (ghost, mermaid, dragon ...) are still flat and turn to the camera by themselves: keep the camera in front of those.

## cast: the 2D characters

`cast.from_plan("id", at=, face=, view=)` brings on the plan's character in its costume. `cast.actor("id", "Soldier", ..., costume={...})` makes one directly. `python tools/clip.py cast` lists the pack; `cast <Name>` lists a character's colours and parts.

| Call | Does |
|---|---|
| `a.do("pick_up", ring, hit=shot.t("picked up"))` | **a named action**: a whole timed performance (anticipation, motion, settle). `t=` is its start, `hit=` lands its key moment on a word, `speed=` its tempo; it returns the end time. `python tools/clip.py actions` lists them. Use an action before posing by hand |
| `a.view("3q" \| "front" \| "side", t)` | which drawing shows. 3q is the default; front for hanging, falling, facing us; side for walking, pulling, reaching across. Held props move to the new drawing's hand by themselves |
| `a.face("left" \| "right", t)` | which way the figure looks and gestures on screen. The acting arm (R) is on that side in all three views |
| `a.place((x, y, z), t)` | stand somewhere (with `t`: pop there at that time, for a cut) |
| `a.expr("happy" \| "laugh" \| "grin" \| "excited" \| "surprised" \| "worried" \| "scared" \| "angry" \| "sad" \| "weeping" \| "crying" \| "sly" \| "sleepy" \| "wink" \| "neutral", t, amount=1.0)` | the whole face: eyes, lids, brows, mouth, tears. Change it 2–4 frames before the body |
| `a.eyes(dx, dz, t)` | where the eyes point: dx +1 toward the facing side, dz +1 up, −1 down. Eyes lead by 0.25 s |
| `a.speak("first words", "last words")` | mouth moves on the narrator's words: for lines in quotation marks |
| `a.pose("gasp", t, blend=0.25)` | a named pose (see `docs/poses.png`), the same idea in every view: rest, gasp, hands_up, cheer, point, point_up, offer, hips, proud, shrug, think, facepalm, hang, carry, reach_down, pull, lift, slump, laugh, wave, sit, kneel, hold_pole, cross_arms, cower, beg, pray, cover_mouth, shield_eyes, push, hug, crouch, salute, write, read, drink, phone, throw_back, throw_fwd, fists_up, sleep, hand_out, stop. `side="L"` swaps a one-armed pose. Your own: `{"R": (raise, bend, "fwd" \| "out"), "L": ("to", "chin"), "lean": d, "hands": ...}` |
| `a.arm("R", raise_deg, bend_deg, t, plane="fwd")` | one arm by hand: 0 hangs, 90 level, 180 up; bend folds the elbow. `plane="fwd"` moves it toward where the figure faces, `plane="out"` sideways away from the body, in every view |
| `a.aim("R", target, t)` · `a.wrist("R", deg, t)` | straighten an arm toward something (pointing, a torch, a sword) · turn the hand at the wrist (pouring, a key) |
| `a.lean(deg, t)` · `a.tilt_head(deg, t)` | bend at the hips (+ forward) · chin down (+) or head back (−) |
| `a.hand("R", "mitten" \| "open" \| "pinch" \| "point" \| "fist" \| "grip", t)` | hand shape (`grip` = closed round a held thing; `hold` sets it) |
| `a.reach("R", target, t)` | the palm goes exactly onto a point, object or anchor **as the camera sees it**. Call again after the target moves |
| `a.hold(prop, "R", t, offset=(x, y, z), turn=False)` · `a.release(prop, t)` | the prop sits in the palm, fingers drawn over it, and follows the hand (`turn=True`: it also turns with the hand; `grip=False`: it lies on an open hand) · it stays where the hand left it and the hand opens (returns that position; then `core.move` it) |
| `t1 = a.walk(t0, to=(x, y), speed=2.0, cycle="walk" \| "run" \| "sneak", arms=True)` | gait cycle with planted feet; returns the arrival time. Faces and picks the view from the direction. `arms=False` keeps the arms as posed (carrying, pointing) |
| `a.legs(raise, bend, t)` | fold the legs (sit 86, 84 · kneel 8, 98 · crouch 58, 104): the body sinks so feet or knees stay on the ground; a robe makes a lap |
| `a.move(t0, t1, to, arc=0.2)` · `a.hop(t)` | slide, jump or fall without walking (arc = height) |
| `a.rock(deg, t, pivot=height)` · `a.shake(t0, t1)` | tip the whole figure in the picture plane (pivot at the feet or at the hands) · laugh, shiver, strain |
| `a.squash(t, 0.12)` | squash on a landing or a jolt; negative = a stretch (a start, an inhale) |
| `a.blink(t)` · `a.idle()` | one blink · blinks and breath for the whole shot (call last, on everyone) |
| `a.recolor(key="#hex")` · `a.hide("Helmet*")` · `a.wear("apron", stains="#8A6B3F")` | costume by hand (normally it comes from the plan) |
| `a.head`, `a.chest`, `a.feet`, `a.top` | anchors for cameras and effects (`a.head.point()` is a world position) |
| `a.floating = True` | tell the grounding check this figure is meant to be off the ground (hanging, swimming) |

Three things to know about timing and hands:

- Every change holds the previous value until it starts, then eases over `blend` seconds ending at `t`. `blend=0.0` is a pop on one frame: use it on a cut.
- `reach` solves the arm for the camera that exists at time `t`. Add the camera views first (the runner prints a note if you did not).
- `walk`, `move` and `open_gate`-style helpers return the time they finish. Chain from that, not from a guess.

`cast.look(tint, lit, gain)` sets how the figures take the scene's light; `lights.rig` calls it for you.

Wardrobe (`stagekit/wardrobe.py`, listed with periods in `config/cast.json`): `straw_hat`, `beret`, `ruff`, `hood`, `kerchief`, `top_hat`, `crown`, `flat_cap`, `bonnet`, `tricorn`, `bowler`, `apron`, `sash`, `cloak`, `buttons`, `fur_trim`, `freckles`.

**Actions** (`stagekit/actions.py`, catalogue in `config/actions.json`, results per body type in `docs/ACTIONS.md`). Moving: walk, run, sneak, tiptoe, step_forward, pace, stomp, sit_down, sit_idle, stand_up, kneel, crouch, hide, peek, lie_down, sleep, wake_up, fall, get_up, slip, jump, climb, hang, swim, crawl, roll, struggle, lean_on, turn_around, freeze, recoil, ride. Hands: pick_up, put_down, carry, haul, throw, drop, hold_up, show, point, hold_up_finger, wave, beckon, push, pull, lift, open_door, turn_key, press, tap, knock, take_out, stash, use_tool (dig, sweep, mop, hammer, saw, stir, cut, paint, scrub, chop), pour, drink, eat, read, write, tie, light, blow, phone, aim, hands_up, tip_hat, dust_off, clap, slam, juggle. Reactions: gasp, laugh, smile, cry, sigh, shrug, think, nod, shake_head, cheer, jeer, panic, cower, tremble, angry, suspicious, dread, yawn, sneeze, whistle, sniff, listen, look_around, watch, inspect, look_away, facepalm, proud. Two people: hand_over, receive, handshake, hug, whisper, argue, chase, bow, curtsy, salute, plead, push_person, grab_person, pat_back, cover_mouth, slap_away. Talking: talk, shout. A character whose body cannot do something (a ghost has no legs) does the substitute listed in `config/cast.json > body` and `ACTIONS.md`. An action a script needs that is not here: `docs/ADDING_NEW_ACTIONS.md`. A character the pack lacks: the `character-maker` skill. To add a piece, copy a short one (`sash`, `kerchief`), draw it in head or torso units, and list it in `config/cast.json`.

## build: the world kit

Surfaces are names from `library/materials/catalog.json` (`python tools/clip.py materials`): `castle_stone`, `fieldstone`, `brick_red`, `rock_face`, `cobblestone`, `flagstone`, `grass_lawn`, `forest_floor`, `earth_path`, `sand`, `pond_mud`, `oak_planks`, `dark_timber`, `bark`, `leaves`, `plaster_white`, `plaster_ochre`, `roof_clay_tile`, `roof_slate`, `thatch`, `iron_dark`, `steel_bright`, `gold`, `cloth`, `terracotta`, `rope`, `pond_water`, `clear_water`. `mat.surface(name, tint="#hex")` returns the material; kit pieces take `surface=`/`tint=`. A `"#hex"` string gives a plain colour.

- **Ground:** `ground(name, size, surface, holes=[outline…], relief=, flat_radius=)` · `patch(name, outline, surface)` for a terrace, path or bed · `rect(cx, cy, w, l)` and `rounded_rect(...)` make outlines.
- **Stone:** `stone_wall(name, length, height, at=, rot_z=, crenels=True, gap=(centre, width, height))` · `tower(name, radius, height, at=, roof=None|"roof_slate")` · `arch_door(name, at=, open_deg=)` → `{"root", "leaf"}` · `steps(...)` · `banner(name, at=, color=, emblem="lion"|"sun"|"tree"|"star")`.
- **Plants:** `tree(name, at=, height, crown, lean, branch=(dx, dy, z, length))` → `{"branch", "branch_grip", "branch_tip", …}` (the branch is its own object: it can sag and break) · `bush(..., flowers="#hex")` · `flowers(name, area, count, colors)` · `grass_tufts(name, area, count, inside=outline, avoid=[(x, y, r)])` · `ivy(name, at=, width, height)` · `reeds(...)` · `rock(...)`.
- **Water:** `pond(name, at=, size=(w, l), depth, sluice="north"|…)` → `holes` (give to `ground`), `water`, `floor`, `surface_z`, `floor_z`, and with a sluice `gate`, `gate_grab{left,right,mid}`, `gate_stand{left,right}`, `channel`, `open_gate(t0, t1)`, `drain(t0, t1)`.
- **Props:** `barrel`, `crate`, `bucket`, `sack`, `bench`, `torch(lit=True)`, `ring`, `pole_net` → `{"root", "hoop"}`, `halberd`.
- **Basics:** `box`, `cyl`, `ball`, `group(name, parts, at, rot_z)`, `lump(obj, strength)` to break a too-perfect shape, `scatter(maker, count, area, avoid=)`.
- Need something else? Write plain `bpy`/`bmesh`, give it `mat.surface(...)` and `mat.uv_box(obj)`. Anything reusable belongs in the asset library (see the `asset-library` skill).

In a set file: build the story objects first, write the `MARK` table, then dress edges and background with `avoid=` around the marks.

## lights

`lights.rig(mood, sun_from=40, sun_elevation=None, rim=0.0, clouds=None)`: sky, sun, ambient and the cast's look for one time of day. Moods: `day_clear`, `day_soft`, `morning`, `golden_hour`, `sunset`, `dusk`, `night_moon`, `storm`, `interior_day`, `interior_warm`, `cave`. `sun_from` is degrees around the stage from the camera side: 30–60 either way gives flat figures a shadow beside them.

`lights.practical(name, at, color, power)` a visible source · `lights.flicker(light)` · `lights.change(light, t0, t1, power=, color=)` · `lights.haze(density)` (costly).

## camera: views

```python
cam = camera.Camera()
cam.view(id, t, on=[things], size="medium", side=0, high=6, fill=None, place=0.40, shift=0.0, lens=None, travel=0.0, why="")
cam.view(id, t, pos=(x, y, z), aim=(x, y, z) or anchor, lens=35, size="wide")     # by hand
```

- `on` may hold actors, anchors (`a.head`), objects, or points. `size`: insert, close, medium, full, wide. `side`: degrees round to screen right (+) or left (−). `high`: degrees looking down (negative looks up). `fill`: fraction of the frame height the subject takes. `place`: where its centre sits from the top (0.40 keeps faces above the captions). `shift`: slide the subject sideways.
- A view is a **cut** unless `travel=` seconds is given (0.3 a whip; 0.6 a move that shows geography).
- `cam.push(t0, t1, 0.06)` lean in during a held view · `cam.move(t0, t1, on=… | pos=…, aim=…)` travel to a new framing inside the view · `cam.follow(obj, t0, t1)` go with a moving thing · `cam.hold(t)` · `cam.shake(t, 0.06)` on an impact.
- Use the plan's view ids. The runner notes any that are missing or extra.

## fx

`fx.ripple(point, t)` · `fx.splash(point, t, size=)` · `fx.sparkle(obj, t, count=)` · `fx.puff(point, t)` · `fx.drips(anchor, t0, t1)` · `fx.lines(point, t, direction)`. Points on water use the pond's `surface_z`.

## core

`core.move(obj, t0, t1, location=, rotation_deg=, scale=)` eased · `core.key(obj, path, t, value)` · `core.key_frame(obj, path, frame, value, interp="CONSTANT")` for a pop · `core.ease(obj, path, "BACK")` · `core.show(obj, t, visible)` · `core.at_frame(f)` evaluate the scene (use before reading a moving object's position).

## shot

`shot.t(phrase)` · `shot.span(phrase)` · `shot.seconds` · `shot.f(t)` · `shot.moment(name, t)` an extra review still · `shot.subject(name, obj_or_anchor, moments=[view ids])` something the viewer must read (actors register their heads; limit a subject to the views where it matters) · `shot.world`, `shot.plan` · `shot.notes.append("...")` a note for the reviewer.

## What the checks say

- *hidden behind X*: a face or subject is behind set geometry from this camera. Move the mark or the camera `side`.
- *the caption line covers N% of the face*: raise the subject (`place=0.36`) or go wider.
- *sits under the Shorts UI*: outside the yellow box.
- *the face is only N% of the frame height*: too small to read; go closer or mark the view `wide` if the place is the subject.
- *floats / is sunk*: feet are not on what is under them. Use the mark's z, or `a.floating = True` / `a.move(arc=)` when it is meant.
- *the camera looks down N degrees with characters in frame*: a flat (2D pack) figure thins out past about 30°; a 3D figure does not.
- *this view lasts Ns*: too short to read, or long with nothing listed inside it.
- `WORLD:` a library asset tagged for another period. `PLAN:` a view id missing from or added to the plan.

A check you leave standing needs a reason in your return note.
