---
name: stagekit
description: How to build a set and stage a shot in Blender for this pipeline - the stagekit Python toolkit (complete sets from arch, furnish and dress; the Aj 3D cast with named actions and Mixamo clips; room light and the per-view key; the camera move library with path checks), the file contract for set files and shot files, and the set preview / stills / camera preview loop with what every blocking check means. Use when writing or fixing blender/set_*.py or blender/shNN.py, or building an asset.
---

# stagekit: sets and shots in Blender

A set is a Python file that builds a complete place. A shot is a Python file that stages the cast in that place and moves the camera. `tools/clip.py` runs them headless in Blender 5.3 (EEVEE), audits the set, renders review stills, motion strips and a camera preview, and measures them; some findings **block** the next stage. You write the file, look at the pictures, fix, repeat. `PY` is `py -3` on Windows, `python3` elsewhere. The toolkit is `tools/blender/stagekit/`; every function has a docstring.

Copy from worked code, do not start from nothing:

- `examples/sets/set_throne_room.py` (hall, barrel vault, windows with real light, candlelit variant) and `set_office.py` (open plan, glass meeting room, city beyond). They are the set-file pattern; `set_office_entrance.py`, `set_office_lobby.py`, `set_training_room.py`, `set_dim_room.py` are the office-building sets (rain, glass doors, gates, lifts, screens). More are in the folder.
- **`output/clips/two-seconds-at-the-office-door/`: the current worked film**, made with the Aj cast and this kit. `blender/set_lobby.py` is a set file (marks first, `build_set(time)` returning the pieces a shot animates), `blender/sh03.py` a shot that moves a door, a status lamp, speed-gate flaps and a prop through a hand, `sh05.py`/`sh06.py`/`sh08.py` screens a viewer must read, `sh02.py` a held door. Its `review/<shot>/verdict.json` files are what a reviewer found wrong the first time: read them before staging.
- `tools/tests/camera/test_moves.py`: every camera move and framing helper in use, with a test set, a strip per move and a chained 12 s sequence. It is the camera cookbook.
- `docs/ACTIONS.md` (the named actions), `docs/CHARACTERS_3D.md` (the Aj cast: acting, clips, grips, limits).

## The contract

```
output/clips/<clip>/blender/set_<set_id>.py    THEME, MARK, WIDE, LIGHT, build_set(time) -> dict
output/clips/<clip>/blender/<shot_id>.py       build_shot(shot)
```

A set file (the plan's set entry says what goes in; `PY tools/clip.py setpreview` checks the agreement):

```python
THEME = "throne_room"                 # = the plan's sets[].theme (the build-time agreement compares them)
SIZE = (12.0, 20.0, 8.0)
MARK = {"throne": (0.0, 8.7, 0.45), "petitioner": (0.0, 1.0, 0.0)}    # EVERY mark the plan names; x, y, z
WIDE = ((0.6, -9.35, 1.9), (-0.3, 6.0, 2.9), 17.0)                    # (camera pos, aim, lens): the one wide every shot of this set uses; the audit judges the set from it
PREVIEWS = {"from_gate": ((6.2, 0.7, 1.9), (-2.2, 6.4, 1.25), 17.0)}  # optional: the other angles this film really uses, (pos, aim, lens)
LIGHT = {"interior_day": dict(sun_from=90, sun_elevation=32), "candlelit": dict()}    # every mood the plan's shots use for this set

def build_set(time="interior_day"):
    R = arch.room(SIZE, floor="flagstone", walls="castle_stone", ceiling="plaster_warm", openings=[...], ceiling_kind="vault", rise=2.2)
    arch.vista(R, "E", "hills")                                       # what each opening looks out on
    lights.interior(time, room=R)                                     # the room's light only: world, cool window light, sources (see "lights")
    inv = dress.room(R, "throne_room", marks=MARK, density=1.0, seed=3, keep_clear=0.9)
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
```

A shot file:

```python
"""sh04 - one line on what this shot is for."""
import set_throne_room as sp
from stagekit import arch, camera, cast, core, furnish

def build_shot(shot):
    S = sp.build_set("candlelit")                       # same place, the light of this shot's `time`
    M, R = S["mark"], S["room"]
    queen = cast.from_plan("queen", at=M["throne"], face="left")        # outfit, hair, palette come from shotplan.json
    petitioner = cast.from_plan("petitioner", at=M["petitioner"], face="right")
    goblet = furnish.make("goblet", at=(0.3, 0.9, 0.0))
    t_kneel, t_cup = shot.t("knelt"), shot.t("the goblet")

    cam = camera.Camera()                               # before anything that measures from the camera (reach, face)
    cam.line(queen, petitioner)                         # the line of action: helpers keep to one side of it
    cam.view("queen_judges", 0.0, framing=cam.ots(petitioner, queen), why="her face, from his shoulder")
    cam.dolly(0.0, t_kneel, 0.10, ease="ease_out")      # the move the plan names, timed to words
    cam.view("goblet", t_cup, framing=cam.insert(goblet), why="the goblet, big")
    cam.orbit(t_cup, t_cup + 2.8, goblet, deg=28)
    petitioner.do("kneel", hit=t_kneel)
    queen.expr("surprised", t_cup + 0.15)              # reactions a beat after the cause
    for a in (queen, petitioner):
        a.idle()
    arch.track_cutaway(R, cam.ob, 1, shot.frames)       # hide the wall that stands between the camera and the room, per frame
```

## Loops and commands

```
PY tools/clip.py setpreview <clip> [set_id]     # SET: audit + six-angle sheet per light mood -> review/sets/<set>_<time>/{sheet.png, audit.json}
PY tools/clip.py stills <clip> [shot] [--views a,b] [--quality preview]    # SHOT: stills, dense sheets, motion strips, look stills (complete run), checks incl. the physical sweep; exit 3 while blocking, 4 if a gate is not approved
PY tools/clip.py review <clip> [shot]           # where each shot stands with its review: only a complete stills run (no --views) stamps the shot's build, and a verdict counts for that build only
PY tools/clip.py preview <clip> [shot]          # CAMERA: low-res motion film + top-down path diagram + path measurements -> review/<shot>/camera/
```

- **Set loop:** build, `setpreview`, open `sheet.png` (wide, cross_a, cross_b, reverse with the near wall hidden, low, plan; a 1.75 m capsule stands on each mark for scale), fix, repeat until the audit has no blocking item and the place looks finished from every angle. A set file may declare `PREVIEWS = {"name": (pos, aim, lens)}`, the angles its film really uses (the planned views, a CCTV point of view, the reverse of a door); they are rendered and audited with the six derived views and tiled into the sheet (a name equal to a derived view replaces it; `PREVIEWS_ONLY = True` keeps only yours and the plan; `--views` can name any). Declare the angles the shots use: a set that is complete from the six standard angles can still be bare behind the door a shot flies through (`tools/blender/set_preview.py`).
- **Shot loop:** stage, `stills`, open **the dense sheets** `review/<shot>/dense/dense_NN.png` (the whole shot at two frames a second, six clean frames a sheet at 540x960, stamped with view, frame and time: read every frame for contact, clipping, facing, doors and floating things), `review/<shot>/sheet.png` (two stills per view stamped with view, time and words; yellow = safe area, blue lines = caption band) **and the strips** `review/<shot>/motion/*.png` (frames across every move), read `checks.json`. A build error prints a traceback and `BUILD FAILED`.
- Gates: `stills` needs A (characters) and B (sets) approved; the final `render` and `assemble` also need C (camera). Edit set files after Gate B and the gate goes stale; that is the user's decision, not a builder's.
- A standalone script can be tried without a clip: `blender -b --factory-startup --python tools/blender/set_preview.py -- --set <set_file> --time <mood> --out <dir>` (set), `... tools/blender/cam_preview.py -- --script <shot file> --seconds 8 --out <dir>` (camera), `... tools/tests/camera/test_moves.py -- --only dolly,orbit` (moves).

## Space and time

- Metres, Z up. **Camera side of a set is -Y** (`N` is the far wall, `S` the camera side, in `arch.room`). +X is screen right when the camera looks along +Y. Marks are `(x, y, z)`; `z` is the floor or the top of what they stand on.
- Time is seconds from the start of the shot. `shot.t("phrase", edge="start"|"end", offset=0.0)` finds a spoken phrase; `shot.span("phrase")` gives (start, end). Key everything to words, never to guessed seconds: the take can change; the words do not.
- **The line of action.** Draw a line between the two parties of a scene and keep the camera on one side (`cam.line(a, b)`; the framing helpers and the path check hold to it). Crossing it swaps who is left and right and loses the viewer, so it is a decision you show (`cross_line=True`), not an accident. The camera may go all the way round a single figure or an object: the line is for scenes between two.

## cast: the Aj characters

`cast.from_plan("id", at=(x, y[, z]), face="left"|"right")` brings on the plan's character, dressed from the registry (`config/cast.json`, wardrobe in `library/wardrobe/`; `PY tools/clip.py cast` lists who exists and what each body may wear; `library/wardrobe/README.md` has the licence and fit rules). It is a real 3D figure on a Mixamo skeleton with a drawn mouth: any angle is fine, including back views and walking away. `cast.actor("id", "<Name>", ...)` makes one directly. `face=` turns the whole body toward screen left or right as seen from where the camera stands at that moment and holds it in the world; `a.heading((x, y), t)` faces a point whatever the camera does.

| Call | Does |
|---|---|
| `a.do("pick_up", ring, hit=shot.t("picked up"))` | **a named action**: a whole timed performance (anticipation, motion, settle). `t=` is its start, `hit=` lands its key moment on a word, `speed=` its tempo; returns the end time. `PY tools/clip.py actions [word] -v` lists them. Use an action before posing by hand |
| `t1 = a.walk(t0, to=(x, y), speed=None, cycle="walk"\|"run"\|"sneak", arms=True)` | the Mixamo walk, run or sneak cycle: turns to the goal, feet planted, eases in and out, returns the arrival time. Chain from it |
| `a.play_clip("Stand_To_Sit", t0)` | one of the registered Mixamo clips (`config/mixamo_clips.json`: walk, run, sneak, sit, kneel, lie, get up, fall, stumble, jump, idles, greetings, salute); returns its end time; `groups=` limits which joints it owns, `loop=True, until=t` repeats. A clip that is not installed raises `MissingClip` with the download request: report it, do not substitute |
| `a.expr("happy"\|"laugh"\|"grin"\|"excited"\|"surprised"\|"worried"\|"scared"\|"angry"\|"sad"\|"weeping"\|"sly"\|"sleepy"\|"wink"\|"neutral", t, amount=1.0)` | the face. Change it 2-4 frames before the body |
| `a.eyes(dx, dz, t)` | where the eyes point: dx +1 toward the facing side, dz +1 up. Eyes lead by 0.25 s |
| `a.speak("first words", "last words")` | mouth on the narrator's words, for lines in quotation marks |
| `a.pose("gasp", t, blend=0.25)` | a named pose: rest, gasp, hands_up, cheer, point, offer, hips, proud, shrug, think, facepalm, carry, reach_down, pull, lift, slump, wave, sit, kneel, cross_arms, cower, beg, pray, push, hug, crouch, salute, write, read, drink, phone... (`docs/poses.png`) |
| `a.reach("R", target, t)` | the palm goes exactly onto a point, object or anchor. Call again after the target moves |
| `a.hold(prop, "R", t, offset=(x, y, z))` / `a.release(prop, t)` | the prop goes with the hand; the grip solver closes the fingers on a handle or small thin thing, otherwise it rests in the palm; release leaves it where the hand was |
| `a.hold(bag, "L", t, hang=True)` | a thing carried by a handle on top (a bag, a bucket, a lantern): the handle in the fist, the thing hanging straight down from it whatever the wrist does, turning only with the way the actor faces. `offset=(left, forward, up)` in metres moves it clear of the leg |
| `a.carry(prop, "R", t0)` (or `a.do("carry", prop)`) | a tray, a box, a cup carrier held level in front of the body from `t0` (to `t1`, default the end of the shot) through a run, a stop and a walk: the arm is solved on every frame in the world, over whatever the clip does to the spine. Use it instead of `hold` + `arm` whenever the actor moves with the thing; do not pose that arm yourself. `height`, `forward`, `side_offset` in metres from the chest |
| `a.interact(furnish.anchor(piece, "name"), hit=shot.t("word"), kind="press")` | **acting on a fixture**: the palm lands on a named grip point of a set piece, from the side it can be reached from, the wrist along the surface, the elbow clear of the fixture, and the hand follows the point when its leaf swings (`hold_until=` keeps it there). The build stops with a plain error when the actor is on the wrong side, out of reach, or cannot get an arm to it: walk to `anchor.stand()` first (where a person stands to reach it) or pass `auto_move=True`. `furnish.anchors_of(piece)` lists the names: glass doors `handle_L_out`, `handle_L_in`, `handle_R_out`, `handle_R_in`; card reader post and wall badge reader `tap`; badge gate `reader_0`...; lift doors `call_0`... `do("press" / "tap" / "open_door" / "hold_door", anchor, hit=...)` go the same way when the target is an anchor. Never type a point on a door or a reader yourself |
| `a.hand("R", "mitten"\|"open"\|"pinch"\|"fist"\|"point"\|"grip", t)` | hand shape |
| `a.lean(deg, t)`, `a.tilt_head(deg, t)`, `a.head_turn(amount, t)`, `a.arm(...)`, `a.aim(...)`, `a.wrist(...)`, `a.legs(...)` | the body by hand, for what no action covers |
| `a.move(t0, t1, to, arc=0.2)`, `a.squash(t, 0.12)` | slide, jump or fall without a clip; squash on a landing |
| `a.blink(t)`, `a.idle()` | one blink; the idle clip with blinks and breath for the whole shot (call last, on everyone) |
| `a.recolor(...)`, `a.hide(...)`, `a.wear("apron")` | the plan's `costume` is applied for you; by hand only for a one-off. Hiding an outfit piece is refused unless another worn piece covers it |
| `a.head`, `a.chest`, `a.feet`, `a.top` | anchors for cameras and effects (`a.head.point()` is a world position) |
| `a.floating = True` | tell the grounding check this figure is meant to be off the ground |

**On an Aj, mind these** (`docs/CHARACTERS_3D.md` has the reasons):

- **Read the character's `avoid` limits** before framing (`PY tools/clip.py cast <Name>`, or `casting.md`): "do not seat seen from behind", "keep the collar out of tight close-ups", "left wrist only". Staging against a limit is a fault the reviewer will send back, and `plan-check` warns when a seating action hits a seating limit.
- **Clip-backed actions start before their `hit=`.** `sit_down`, `kneel`, `lie_down`, `get_up`, `fall`, `slip`, `jump`, `salute` and every walk play a Mixamo clip whose key moment (the seat, the floor, the hand at the brow) is measured; `hit=` puts that moment on the word, so the legs of that figure are busy for the clip's lead before it. Leave the time free, do not rush it with `speed=`, and chain from the returned end time. A clip file that is not installed stops the build (exit 5) with the exact download request; report it, do not substitute.
- **Hands and props.** `a.hold(prop, "R", t)` grips by the prop's `grip` field (`power` rod or handle with `grip_at`, `pinch` small thin thing, `palm` carried on the palm, `palm2` wide thing taken in both hands, `none`) and falls back to the plain `grip` hand shape with a shot note when the solver would push the hand into the prop. A prop far from the hand is put into the palm at the hold (`offset=` moves it); `hold(grip=False)` lets a bag hang from its strap. **Keep a held prop in the hand through the whole move**: never release it or let it float between two poses to save work. `release` leaves it where the hand was.
- **`read` and `shout` leave a busy arm alone** (a hand holding a prop stays where it is). `a.do("press", target, hit=, palm=True)` slaps a flat hand on a button or reader.
- **People need a reason to be there.** A "busy" place (an open-plan floor, a lobby, a training room) is filled with people at their desks, in the queue, on the phone; an empty busy place reads as a set. Extras are cast like anyone (`extra_1`..), and `a.idle()` on each.

Timing rules: every change holds the previous value until it starts, then eases over `blend` seconds ending at `t`; `blend=0.0` is a pop on one frame. `reach` solves for the pose at time `t`. `walk`, `move`, `play_clip` return the time they finish.

Actions (catalogue in `config/actions.json`): moving (walk, run, sneak, sit_down, stand_up, kneel, lie_down, sleep, get_up, fall, slip, jump, turn_around, freeze, recoil...), hands (pick_up, put_down, carry, haul, throw, drop, hold_up, show, point, wave, push, pull, lift, open_door, knock, pour, drink, eat, read, write, phone, use_tool...), reactions (gasp, laugh, cry, shrug, think, nod, shake_head, cheer, panic, cower, listen, look_around...), two people (hand_over, receive, handshake, hug, whisper, argue, bow, salute, plead...), talking (talk, shout). Those that move the whole body use the Mixamo clips on an Aj figure. A missing action is added with `docs/ADDING_NEW_ACTIONS.md`; a missing character, outfit or clip comes through `PY tools/clip.py casting <clip>`.

## The set kit

**Surfaces** are names from `library/materials/catalog.json` (`PY tools/clip.py materials`). `mat.surface(name, tint="#hex")`; kit pieces take `surface=` / `tint=`.

- **Architecture (`arch`)**: `room(size, floor, walls, ceiling, openings=[...], ceiling_kind="flat"|"beams"|"vault")` makes floor, four walls with **real cut openings** (door, window, gap; each with `type`, `w`, `h`, `sill`, `at`, `arched`, `id`), ceiling, skirting and cornice; walls and ceiling can be hidden per view. `vista(room, wall, kind)` puts what an opening looks out on (hills, garden, street, town...): an opening with nothing behind it is blocked as a void. Then `column`, `pilaster`, `arch`, `beam`, `ceiling_beams`, `vault`, `stairs`, `dais`, `platform`, `balcony_rail`, `fireplace`, `alcove`, `floor_inlay`, `rug_area`, `carpet_runner`, `glass_partition`; outsides: `house_front`, `street`, `plaza`, `low_wall`, `fence`, `market_stall`, `well`, `lamp_post`, `skyline`, `treeline`, `far_hills`, `far_town`, `army`, `church`, `terrain`, `road_markings`; atmosphere: `smoke`, `ground_haze`. `cutaway(room, cam_or_point, at_frame=(f0, f1))` hides the walls and ceiling between a camera and the room; `track_cutaway(room, cam.ob, f0, f1)` follows a moving camera.
- **Furniture and props (`furnish`)**: about 140 registered pieces, every one in metres, grounded, tagged with its periods, with a real light where it is a lamp. `furnish.make("goblet", at=(x, y, z), rot_z=)`; `furnish.REGISTRY` lists them; `furnish.catalogue()` prints them. Origin on the floor at the centre of the back face, front toward -Y; wall pieces take their mount height as `at.z`.
- **Dressing (`dress`)**: `dress.room(R, "<theme>", marks=MARK, density=, seed=, keep_clear=)` and `dress.exterior(area, "<theme>", ...)` fill the four depth layers with props that never overlap, never float, and keep the marks and doors clear, plus practicals, floor detail, atmosphere and readable details. Themes: throne_room, great_hall, castle_kitchen, tavern, peasant_cottage, office_open_plan, office_private, home_living_room, home_kitchen, shop_interior (rooms); market_street, village_square, army_camp, battlefield, city_street, office_entrance (exteriors); office_lobby is also a room theme. It returns an inventory (`types`, `objects`, `layers`, `practicals`, `atmosphere`, `details`). `dress.THEMES` holds each theme's periods; a theme must belong to the plan's era.
- **Office-building pieces** (modern; `furnish` unless noted): `glass_front` (a curtain-wall front with a door gap), `glass_doors` (two leaves with closer and pull handles), `card_reader_post`, `badge_reader`, `badge_gate` (speed gates, lanes with flaps and lamps), `lift_doors`, `reception_desk`, `company_totem`, `wall_logo`, `security_camera` (dome), `wall_screen` (a screen with an image slot), `laptop`, `monitor_keyboard`, `entrance_canopy`; `arch.office_front(...)` a tower face for the street beyond (glass, panel or brick, some panes lit); `dress.office_lobby_room` and the themes `office_lobby` and `office_entrance`. Library hand props with grips: `prop_laptop_open/closed`, `prop_cup_carrier`, `prop_coffee_cup`, `prop_messenger_bag`, `prop_keycard_lanyard`, `prop_file_stack`, `prop_cardboard_box_desk`, `prop_smartphone`, `prop_security_radio` (`asset-library` skill). Worked sets are listed above.
- **Parts that move or light up.** A compound piece has named moving children. `furnish.part(piece, "leaf_R")` returns one (origin at its hinge or slide start), `furnish.parts_of(piece)` lists them. Animate with `core.move(part, t0, t1, rotation_deg=... / location=...)` or the helpers: `furnish.swing_door(doors, t0, t1, left=, right=)` (degrees, + into the room), `furnish.open_lift(lift, index, t0, t1)`, `furnish.lamp_state(furnish.part(reader, "lamp"), "green"|"red"|"amber"|"white"|"off", t=)` (a cut on the word; glow, colour and its small light change together). A set returns the pieces its shots animate in the dict `build_set` gives back (`doors`, `gate`, `lifts`...), and a shot finds the rest with `part`. **Screens:** `furnish.screen_set_image(tv, "<abs path>.png")` shows a picture (a frame from the film's own footage works; 16:9 on a wall screen), `furnish.screen_look(tv, "footage"|"clean", gain=)` the security-camera look or the plain picture, `furnish.screen_set_image_builtin(tv, "footage"|"slide"|"desktop"|"off")` a placeholder. `a.hand(...)` and `a.do("press", ...)` reach a reader or button: key the lamp to the touch.
- **Older outdoor kit (`build`)**: `ground`, `patch`, `stone_wall`, `tower`, `steps`, `banner`, `tree`, `bush`, `flowers`, `grass_tufts`, `ivy`, `reeds`, `rock`, `pond` (with a sluice gate that drains), `barrel`, `crate`, `bucket`, `sack`, `bench`, `torch`, `ring`, `halberd`, `box`, `cyl`, `ball`, `group`, `scatter`. Use `arch.terrain` and the themes for new work.
- Everything reusable that you make is registered with `arch.tag(root, "<type>", kind="prop", size=[w, d, h])` so the audit counts it (`asset-library` skill). Anything not in the kit: plain `bpy`/`bmesh` with `mat.surface(...)`.

**The set standard** (read from `style/style.json` > `sets` by `audit`; the wide must clear every minimum): at least 14 distinct prop types and 60 objects visible in the wide; four depth layers populated (foreground occluder, midground action, background, beyond: sky, vista, a room through a door); at least 3 visible practical lights indoors; at least one atmosphere element; at least 3 readable in-world details; nothing floating or sunk more than 2 cm; no pieces through each other or through walls; no mesh without a material; no ray from any camera that hits nothing; every door and window with something behind it. Enclosed places survive a reverse angle: real walls, floor and ceiling, with the wall nearest the camera hidden per view.

## lights

The room owns its fixtures, the view owns its key. Why: the first film's sets were lit before any camera or person existed and every shot then rescaled that light by hand and added a blue spot beside the lens, so faces were flat and nothing cast a shadow (`docs/LOOK_AUDIT_PHASE1.md`). The approved look (`style/look/`) is warm key and warm fixtures against cool window light and fill, shadows on, whites kept white by the view's white balance; every number is in `style/style.json` > `look`.

**A set lights the place, in two or three lines** (the worked set is `output/experiments/look_phase4/lights/set_training_room_new.py`):

```python
R = arch.room(SIZE, at=(0.0, 3.75), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile", openings=ops, name="training")
lights.interior(time, room=R)                     # low world, weak cool window light (shadows on) through every window, sources declared; no white balance and no character key
lights.window_sun(R, "E", elevation=34.0, yaw=-20.0, power=1.0)    # optional: sun patches on the floor
inv = dress.room(R, "training_room", marks=MARK, density=1.0, seed=3, keep_clear=0.3)   # fixtures at their warm defaults, sources declared, shadows fitted to the pool
```

- `lights.interior(mood, room=R)` for an enclosed place (a set with no window, candlelit or office night, leaves `room` out and is lit by its practicals); `lights.rig(mood, ...)` for an exterior. `lights.window_key(opening, mode="sky")` is the weak cool window light that `interior` places; the default `mode="key"` is the old 900 W key and is not for new sets.
- Fixtures: `lights.practical(name, at, ...)`, `furnish.make` pieces that carry a light, `dress.room`'s panels and downlights. `lights.practicals(scale=, kelvin=, emission=, match=)` and `lights.fixture(piece, ...)` change a fixture's light and its glowing surface together, so a lamp never has a bright shade and no light, or the reverse; scale is relative to the built power and does not compound. `lights.declare_sources()` declares the strong practicals and screens as sources (`dress.room` calls it; call it again after placing lamps by hand); `viewlight.source(kind, at, toward=, kelvin=, name=)` declares one by hand, kind `window`, `practical`, `screen` or `sky`.
- `lights.limit_shadows()` fits the casting lights into the shadow pool (2048, 1024 or 512 MB at final, preview, draft); `dress.room` already runs it. If a `shadow_pool_full` block remains, a hand-added light is the cause.
- Moods are `lights.MOODS`; `lights.mood_look(mood)` returns its colour identity (white balance, key, fill and fixture temperatures, window light, world). The white balance belongs with the warm key, so the per-view step sets it (the mood's, from `mood_look`) and a set never does: over a room still lit the old cool way a white balance only turns the picture blue (`lights.rig(..., white_balance=True)` exists for a caller that keys its characters the new way by hand). The mood decides it, and and each hour has its own face level and contrast: a day interior is bright and shaped, rain is soft and cool, night is a pool of light on the people in a dark room. `lights.current_mood()` says which one the scene was built in.
- Also: `lights.flicker`, `lights.change(light, t0, t1, power=)`, `lights.dust(lo, hi)`, `lights.haze(density)` (costly), `lights.light_shaft(...)`. `lights.rim_light` and `lights.ambient_fill` still run but are not for characters any more: the per-view step replaces them. Make every story light (a phone, a screen, a lamp someone holds) with `lights.practical(name, at, color=lights.SCREEN_K, power=W)`, never plain bpy: any other light the per-view step does not know switches it off and blocks the shot (`light_step_skipped`, which names the light).
- Never in a set: a character key, fill or rim, `shadow=False` on a window, a hand-multiplied `energy`, glow lights at hundreds of watts, a saturated blue fill.

**The per-view step lights the people** (`stagekit/viewlight.py`). `run_shot` calls `viewlight.shape(shot, cam, hero=, edge=, key_side=, scale=)` after `build_shot` returns, once per unbroken run of views (a view entered by a cut starts a run). For each run it places, named `VL_<view>_<role>`, and held for the run's frames: one key, warm, 45-60 degrees off the lens on the side of the nearest declared source that has a clear line to the hero, ray-cast for clearance, power by distance, casting shadows (a real sun stays the key); a weak cool side fill; a low warm front fill; an edge light on someone who would melt into the wall behind them (`edge`, or automatically when eligible); a restrained bounce from a visible screen. The report (`shot.viewlight`, hero, source, key angle and power, `compromises`) goes to `checks.json`. The step sets the view's white balance (`core.set_white_balance`), so a set never does.

The options are dicts keyed by the view that opens the run, or one value for all: `hero` (a cast id or a subject name; otherwise the first declared head in frame), `edge` (id or list), `key_side` (`"left"` or `"right"` from the camera), `scale` (multiplies the level the view ends at, after metering; a face the step could not measure is reported as `light_estimated` or `light_unmetered` in `checks.json`, and a view whose subject is a lit screen or lamp gets only a low shaping key and a cool intended lean). The plan's `hero` and `separate` reach them with one line at the end of `build_shot`:

```python
    ...                                                        # cast, camera, actions
    shot.viewlight = planlink.viewlight_options(getattr(shot, "plan", None))      # {"hero": {view: id}, "edge": {view: [ids]}}; run_shot then calls the step with it
    # only if a look still is wrong, and say why in the report:
    # shot.viewlight = {**planlink.viewlight_options(shot.plan), "key_side": {"ring_slips": "left"}, "scale": {"ring_slips": 0.8}}
```

`shot.viewlight = False` switches the step off (a shot that lights itself entirely; the checks still measure it).

**The look stills and look checks.** A complete `stills` run (no `--views`) also renders one final-quality still per view at its key moment, `review/<shot>/look/<view>.png` and `look/sheet.png` (draft stills have no ray tracing and 6 samples and do not show light; `SHORTS_NO_LOOK=1` skips them), and measures each (`checks.json` > `look`, items with `source: look`; limits in `style.json` > `look.checks`). Read the sheet at full size beside `style/look/office_training_room_faces.jpg`.

| Code | Level | Means | Fix |
|---|---|---|---|
| `face_flat` | warn; blocks when the face is also washed | the hero's shadow cheek is nearly as bright as the lit one: no shape | move the key off the lens (`key_side`), a lower `scale`, check a light beside the camera that is not `VL_*` |
| `face_washed`, `face_dark`, `face_dim` | warn | the hero's face is pale and bright, lost in darkness, or another face is under 60% of the hero's | `scale` on that view; `hero` the right person; `edge` or a nearer source for the dim one |
| `colour_lean` | warn; blocks past a margin | the frame leans warm or blue-cyan beyond the hour's intended lean (`review.intended_lean(mood)`) | a light with a wrong colour (a saturated fill, a fixture kelvin), or a white balance set by hand |
| `lifted_blacks` | warn; blocks above 100 of 255 in the darkest tenth | flat, no shadow: the picture is washed | remove flat fill, lower the world, shadows on |
| `crushed_blacks`, `no_highlights`, `blown_highlights` | warn | shadows without colour, nothing catching light, burnt highlights | low fill or a higher world; a brighter practical; a lower `scale` |
| `shadow_pool_full` | block | too many casting lights for the shadow pool | remove the hand-added lights; `lights.limit_shadows()` |
| `setting_not_applied` | warn | a render setting could not be applied in this Blender (listed in the text) | report it, never hide it |

What the checks cannot see is face shape (a pose-independent measure barely separates the film's light from the approved one, 0.81 against 0.78), so a green look list is not a good look: the reviewer judges faces by eye. `PY tools/clip.py qa <clip> --look` prints the shot-against-shot table (hero face, colour lean, tonal range).

Gate A character sheets and Gate B set previews carry a stand-in key (`viewlight.stand_in(camera, aim, mood=None, level=1.0)`: the same key and fills for a person standing at `aim`, with the mood's white balance), so the owner judges characters and sets at the film's exposure rather than in a room without a key.

## camera

```python
cam = camera.Camera()
cam.view(id, t, on=[things], size="medium", side=0, high=6, fill=None, place=0.40, shift=0.0, lens=None, travel=0.0, why="")
cam.view(id, t, pos=(x, y, z), aim=(x, y, z) or anchor, lens=35, size="wide")       # by hand
cam.view(id, t, framing=cam.ots(a, b))                                                # or with a framing helper
```

A view is a **cut** unless `travel=` seconds is given. `size`: insert, close, medium, full, wide (fraction of the frame height the subject fills). `side`: degrees round to screen right (+) or left (-). `high`: degrees looking down (negative looks up). `place`: where the subject's centre sits from the top (0.40 keeps faces above the captions). A view held longer than 1.2 s with no move of its own gets a slow drift (`still=True` or `drift=False` turns it off: only with a reason).

**Framing helpers** (return a framing; they keep to `cam.line(a, b)`): `ots(over, on)` over the shoulder, `two_shot(a, b)`, `reverse(of_view)` the opposite coverage, `low_hero(on)` a low wide-angle look up at a hero, `top_down(things)` a map, `establish(where)` a high wide of a place, `insert(on)` an object or a hand, `profile(on)` a side view.

**Moves** (times in seconds; all return the camera; chain with `blend=0.3` so there is no velocity jump; eases: `linear`, `ease_in`, `ease_out`, `ease_in_out` (default), `settle`, `whip`):

| Move | Use it to | Typical |
|---|---|---|
| `dolly(t0, t1, amount)` / `push` | lean toward a realisation or a hero prop (a negative amount pulls out) | slow 1.5-3 s, +5-40% subject size, `ease_out`; fast 0.5-1.5 s, x1.35-1.7 |
| `truck(t0, t1, right=, up=)` | travel beside the action; reveal behind a foreground occluder | 1.5-3 s, a third to a half of the frame width |
| `pan(t0, t1, deg)`, `tilt(t0, t1, deg)` | turn to follow the eye; tilt up a tall thing, down to a hand | 20-40 degrees over 1.5-2.5 s |
| `orbit(t0, t1, around, deg, rise=, to_distance=)` | show an object or a person from a new side without a cut | about 3 s, 25-30 degrees |
| `crane(t0, t1, rise=, back=, tilt_to=)` | go from a person to the geography, or back down into a scene | 2.5-3 s, 35-75 degrees of pitch |
| `follow(target, t0, t1)`, `track_with(target, t0, t1, side=, distance=)` | go with a falling, thrown or walking thing | 2-3 s |
| `whip(t, to, dur=0.35, vid=)` | carry the eye from one subject to the next inside a place; or the plan's `transition_in` | 0.3-0.5 s |
| `through(t0, t1, opening, to, vid=)` | fly through a doorway, window or screen into the next view | about 0.5-2 s |
| `rack_focus(t0, t1, to, fstop=)` | move the sharp plane from one face or object to another, over a slow push | 0.6-1.2 s |
| `reveal(t0, t1, from_behind, to)` | start behind an occluder and come out onto the subject | 1.5-2.5 s |
| `dolly_zoom(...)`, `handheld(t0, t1, amount)`, `shake(t, amount)` | unease or shock; a nervous held look; an impact | rare; short |
| `move(t0, t1, on=... or pos=, aim=)`, `hold(t)` | travel to a new framing inside the view; freeze here | |

Every move needs a story reason; a move that goes nowhere is cut. The camera should be moving 60-80% of screen time. Transitions between shots are camera events more often than plain cuts: the plan's `transition_in` (`whip`, `dissolve`, `dip`, `flash`, `wipe`, `match`) is read by the assembly (`tools/assemble.py`), so compose the first and last frames of a shot for it.

## fx, core, shot

**Rain** (thin slanted streaks that loop in the shader, so it reads as rain, not snow: faint with distance, gone within 2.5 m of the lens): `fx.rain(area, intensity=1.0, wind=(0.12, 0.0), ground=, near=(x, y, r), exclude=[(x0, y0, x1, y1, z_roof)])` pouring rain over a ground rectangle (`intensity=2` a downpour; `exclude` the canopies and shelters it must not fall under; `near` the camera hint), `fx.rain_splashes(area, count=, ground=)` crowns on the pavement, `fx.window_rain(glass_piece_or_opening, density=)` beads and runs on the inside of glass (it leaves the door gap dry), `fx.drips_edge(p0, p1, n=, fall=)` drops off a canopy or gutter edge. Use them in the `rain_day` set, once, in the set file. `lights.window_key` for the grey light through the glass.
`fx.ripple(point, t)` · `fx.splash(point, t, size=)` · `fx.sparkle(obj, t, count=)` · `fx.puff(point, t)` · `fx.drips(anchor, t0, t1)` · `fx.lines(point, t, direction)`.
`core.move(obj, t0, t1, location=, rotation_deg=, scale=)` eased · `core.key(obj, path, t, value)` · `core.show(obj, t, visible)` · `core.at_frame(f)` evaluate the scene before reading a moving object's position.
`shot.t(phrase)` · `shot.span(phrase)` · `shot.seconds` · `shot.frames` · `shot.f(t)` · `shot.moment(name, t)` an extra review still · `shot.subject(name, obj_or_anchor, moments=[view ids])` something the viewer must read · `shot.world`, `shot.plan` · `shot.notes.append("...")` a note for the reviewer.

## Lessons from the first test film

The first film made with the Aj cast and this kit (`output/clips/two-seconds-at-the-office-door/`) was reviewed shot by shot (`review/<shot>/verdict.json`). The faults it found, as rules:

- **Show the key action large and unobstructed.** The plan's trigger (a hand on a door handle, a lock turned, a laptop going into a bag) must be readable with the sound off: the hand and the object big in the upper middle, the leaf swung so its glass face and handle catch the light, nothing standing between the lens and the hand (a reader post, a mullion, a rain-beaded pane). If the action cannot be made to read, cut an insert of it.
- **A planted beat must actually happen.** If the plan says "he turns the lock", the hand reaches the handle on the word. A rack focus from a face to a hand that does nothing is a rack to an idle body. Never rest a rack focus on someone doing nothing.
- **A screen's important content is big enough to read on a phone.** A security picture shown as the whole wide frame leaves the two people a few pixels; make the screen show the crop that matters (a zoom picture made for it, with the same overlay so it is recognised), and let the screen fill most of the frame width at the end of the push. A screen is the brightest thing in a dim room: raise its `gain`.
- **Keep a held prop in the hand through the whole move.** A laptop that leaves the hand and hangs in the air, or slides behind the bag so the bag's mouth is never seen, reads as a mistake.
- **Fill a "busy" place with people.** "Nobody glanced up" over an empty floor shows nothing: put a floor of heads-down people in frame, large enough to count.
- **The face the viewer needs must be in the frame.** Put the other person's shoulder and the box corner in the foreground of an over-the-shoulder so it reads as her looking; keep faces above the caption band (a chin on the captions is a fix); do not crop the top of the head on a close.
- **Continuity is read from the files, not remembered.** A match cut across shots reads the previous shot's end position, door angle and prop from its file (`sh03.py` reads `HOLD_SPOT`, `LEAF_WIDE`, `IN_END` from `sh02.py`), so a change in one shot cannot silently break the next.
- **Keep the same look for a character and a prop in every shot**: skin tone under different lights (the per-view key does this; never relight by hand), the bag's colour and open flap, the beard or goatee. The reviewer will compare shots.
- **Moves that go nowhere are cut**: a tilt that crash-zooms through a blank wall, an orbit of 8 degrees a second that reads as a still, a truck that spends its middle on a plain wall (put an occluder in the gap, or drop the cut and let the push flow into the truck).
- **Rain**: seen from inside a lobby it must read as streaks and beads, not snow; the card of rain on the glass is cut away over an open door leaf; the `rain_day` mood is soft and cool outside with warm lamps inside.

## What the checks say

`checks.json` has `items`, each `{level: "block"|"warn", code, source: still|view|world|campath|set|physical, view, frame, text}`, plus `blocking`, `warnings`, `campath` (each move with peak speeds; `static_share`), `motion` (the strips), `dense` (the two-a-second sheets), `physical` (the sweep's summary; every finding with its frame range and measured value is in `physical.json`), `set_audit` (`inventory`) and, after a complete run, `build` (the form of the shot these stills show: `tools/reviewgate.py`). `stills` exits 3 while `blocking` is above 0, and the camera preview and Gate C stay shut with a blocking camera item.

**Blocking, and the fix:**

| Code | Fix |
|---|---|
| `no_camera`, `no_views` | create `camera.Camera()` and at least one `cam.view` |
| `subject_hidden`, `nothing_in_frame`, `subject_out_of_frame` | change `side` or the framing, hide the near wall, keep the subject in frame through the move |
| `actor_floating`, `actor_sunk` | stand them on what is under them, or `a.move(..., arc=)` / `a.floating = True` when meant |
| `camera_inside_geometry`, `camera_under_floor`, `camera_too_close`, `camera_through_geometry` | the camera path touches something: shorten the move, move its start, cutaway, or go `through` an opening |
| `speed_over_limit`, `accel_over_limit`, `ang_speed_over_limit`, `ang_accel_over_limit` (blocks at twice the limit), `jerk_spike` | lengthen the move, `ease="settle"`, `blend=0.3`; a whip is exempt |
| `static_share` (above 70% still) | add pushes, drift or tracks to held views |
| `blown_out`, `mostly_black`, `brightness` | a light or the sky is too strong or too weak: steer the per-view step (`scale`), not the set |
| `colour_lean`, `lifted_blacks`, `face_flat` (`source: look`, block only past the wider limit), `shadow_pool_full` | see the table under "lights" |
| `interpenetration` | a body, arm or prop is inside something solid by the depth given: move the mark, redirect the reach, take the hand to the handle on its own side, carry the prop clear of the body |
| `through_closed_leaf` | someone crosses a door leaf or gate flap that is not open at that frame (`walk` sweeps the body along its path against every leaf, flap and lift door, and the sweep measures it again on every frame): open it before the walk reaches it (`furnish.swing_door`, `core.move` on the part) |
| `grip_open`, `grip_impaled` | a held prop has no finger on it, or cuts through the hand: `a.hold` again at the prop's grip point after the hand is posed; check the asset's `grip` kind |
| `loose_attachment`, `attachment_in_body` | a prop fixed to a body by hand (`prop.parent = ...`) that no hand or shoulder carries, or that cuts into the body: use `a.hold` or `a.carry`, never a typed offset from a bone. A bag is held by its handle with `a.hold(bag, side, t, hang=True)`; the kit has no shoulder strap (three attempts failed their measurements), so a bag on the body is a request to the producer |
| `carry_tilt`, `carry_behind`, `carry_flung` | a carried thing tips past the limit, trails behind the chest or swings out during a walk or run: a torso-angle arm pose cannot hold it under a clip that pitches the spine: use `a.carry(prop, side, t0)` |
| `not_facing_target`, `reach_miss` | an action lands away from its target or the actor is turned from it: stand and turn the actor at the thing first, and give the action the real object, or for a fixture its anchor (`a.interact(furnish.anchor(piece, name), hit=...)`) |
| `floating_prop` | a prop rests on nothing and nobody holds it |
| `rain_under_cover` | weather under a roof: call `fx.rain` after the cover is built (it measures it), or list the place in `exclude` |
| `set_*` (the audit: `few_prop_types`, `few_objects`, `layers_missing`, `few_practicals`, `no_atmosphere`, `few_details`, `floating`, `sunk`, `intersect`, `through_wall`, `no_material`, `void`, `opening_void`, `flipped_normals`, `zero_area`; the agreement: `set_mark_missing`, `set_no_mark`, `set_theme_mismatch`, `set_time_missing`, `set_file_missing`, `set_not_in_plan`, `set_file_broken`) | the set file or the plan: see the shot-builder agent |

The physical findings (`source: physical`, `stagekit/physical.py`, thresholds in `style/style.json` > `physical`) are measured over the whole shot: every sixth frame, every frame an action lands on, and every frame for doors and gates. They know what was asked because the kit writes it down as the shot is built (`stagekit/record.py`: `shot.holds`, `shot.interactions`), which is why a targeted action can be checked and a typed arm angle cannot. On screen they block; the same fault off screen is a warning.

**Warnings** to fix or explain: `prop_backwards`, `reach_short`, `arm_through_obstacle`, `untargeted_action` (a wave, point, press or tap with no target cannot be checked: give it one), `face_under_captions` (raise the subject, `place=0.36`), `face_too_small`, `outside_safe_area`, `steep_angle` (over 60 degrees with characters), `view_too_short` / `view_too_long`, `line_crossed`, `whip_duration`, `camera_close`, `stand_in`, `world` (`WORLD:` an asset tagged for another period), `PLAN:` (a view id missing from or added to the plan). A warning you leave standing needs a reason in your return note.

The physical checks catch most collisions and misses, not all (in the study that set them up, about three quarters): a clean report is not a clean shot, and the dense sheets are read every time. What the numbers cannot say, you judge from the pictures and the strips: is the place complete and art-directed, is every prop grounded, does the costume fit, does each move reveal something and hold the subject where the eye should be.
