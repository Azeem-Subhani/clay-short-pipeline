---
name: stagekit
description: How to build a set and stage a shot in Blender for this pipeline - the stagekit Python toolkit (complete sets from arch, furnish and dress; the Aj 3D cast with named actions and Mixamo clips; light rigs; the camera move library with path checks), the file contract for set files and shot files, and the set preview / stills / camera preview loop with what every blocking check means. Use when writing or fixing blender/set_*.py or blender/shNN.py, or building an asset.
---

# stagekit: sets and shots in Blender

A set is a Python file that builds a complete place. A shot is a Python file that stages the cast in that place and moves the camera. `tools/clip.py` runs them headless in Blender 5.3 (EEVEE), audits the set, renders review stills, motion strips and a camera preview, and measures them; some findings **block** the next stage. You write the file, look at the pictures, fix, repeat. `PY` is `py -3` on Windows, `python3` elsewhere. The toolkit is `tools/blender/stagekit/`; every function has a docstring.

Copy from worked code, do not start from nothing:

- `examples/sets/set_throne_room.py` (hall, barrel vault, windows with real light, candlelit variant) and `set_office.py` (open plan, glass meeting room, city beyond). They are the set-file pattern. More worked sets may be added there: look in the folder.
- `tools/tests/camera/test_moves.py`: every camera move and framing helper in use, with a test set, a strip per move and a chained 12 s sequence. It is the camera cookbook.
- `docs/ACTIONS.md` (the named actions), `docs/CHARACTERS_3D.md` (3D figures, older but the API shape is the same).

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
LIGHT = {"interior_day": dict(sun_from=90, sun_elevation=32), "candlelit": dict()}    # every mood the plan's shots use for this set

def build_set(time="interior_day"):
    R = arch.room(SIZE, floor="flagstone", walls="castle_stone", ceiling="plaster_warm", openings=[...], ceiling_kind="vault", rise=2.2)
    arch.vista(R, "E", "hills")                                       # what each opening looks out on
    lights.rig("interior_day", look=False, ...); lights.window_key(R.openings["win_E0"]); lights.rim_light(MARK["petitioner"])
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
PY tools/clip.py stills <clip> [shot] [--views a,b] [--quality preview]    # SHOT: stills, motion strips, checks; exit 3 while blocking, 4 if a gate is not approved
PY tools/clip.py preview <clip> [shot]          # CAMERA: low-res motion film + top-down path diagram + path measurements -> review/<shot>/camera/
```

- **Set loop:** build, `setpreview`, open `sheet.png` (wide, cross_a, cross_b, reverse with the near wall hidden, low, plan; a 1.75 m capsule stands on each mark for scale), fix, repeat until the audit has no blocking item and the place looks finished from every angle.
- **Shot loop:** stage, `stills`, open `review/<shot>/sheet.png` (two stills per view stamped with view, time and words; yellow = safe area, blue lines = caption band) **and the strips** `review/<shot>/motion/*.png` (frames across every move), read `checks.json`. A build error prints a traceback and `BUILD FAILED`.
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
| `a.hand("R", "mitten"\|"open"\|"pinch"\|"fist"\|"point"\|"grip", t)` | hand shape |
| `a.lean(deg, t)`, `a.tilt_head(deg, t)`, `a.head_turn(amount, t)`, `a.arm(...)`, `a.aim(...)`, `a.wrist(...)`, `a.legs(...)` | the body by hand, for what no action covers |
| `a.move(t0, t1, to, arc=0.2)`, `a.squash(t, 0.12)` | slide, jump or fall without a clip; squash on a landing |
| `a.blink(t)`, `a.idle()` | one blink; the idle clip with blinks and breath for the whole shot (call last, on everyone) |
| `a.recolor(...)`, `a.hide(...)`, `a.wear("apron")` | the plan's `costume` is applied for you; by hand only for a one-off. Hiding an outfit piece is refused unless another worn piece covers it |
| `a.head`, `a.chest`, `a.feet`, `a.top` | anchors for cameras and effects (`a.head.point()` is a world position) |
| `a.floating = True` | tell the grounding check this figure is meant to be off the ground |

Timing rules: every change holds the previous value until it starts, then eases over `blend` seconds ending at `t`; `blend=0.0` is a pop on one frame. `reach` solves for the pose at time `t`. `walk`, `move`, `play_clip` return the time they finish.

Actions (catalogue in `config/actions.json`): moving (walk, run, sneak, sit_down, stand_up, kneel, lie_down, sleep, get_up, fall, slip, jump, turn_around, freeze, recoil...), hands (pick_up, put_down, carry, haul, throw, drop, hold_up, show, point, wave, push, pull, lift, open_door, knock, pour, drink, eat, read, write, phone, use_tool...), reactions (gasp, laugh, cry, shrug, think, nod, shake_head, cheer, panic, cower, listen, look_around...), two people (hand_over, receive, handshake, hug, whisper, argue, bow, salute, plead...), talking (talk, shout). Those that move the whole body use the Mixamo clips on an Aj figure. A missing action is added with `docs/ADDING_NEW_ACTIONS.md`; a missing character, outfit or clip comes through `PY tools/clip.py casting <clip>`.

## The set kit

**Surfaces** are names from `library/materials/catalog.json` (`PY tools/clip.py materials`). `mat.surface(name, tint="#hex")`; kit pieces take `surface=` / `tint=`.

- **Architecture (`arch`)**: `room(size, floor, walls, ceiling, openings=[...], ceiling_kind="flat"|"beams"|"vault")` makes floor, four walls with **real cut openings** (door, window, gap; each with `type`, `w`, `h`, `sill`, `at`, `arched`, `id`), ceiling, skirting and cornice; walls and ceiling can be hidden per view. `vista(room, wall, kind)` puts what an opening looks out on (hills, garden, street, town...): an opening with nothing behind it is blocked as a void. Then `column`, `pilaster`, `arch`, `beam`, `ceiling_beams`, `vault`, `stairs`, `dais`, `platform`, `balcony_rail`, `fireplace`, `alcove`, `floor_inlay`, `rug_area`, `carpet_runner`, `glass_partition`; outsides: `house_front`, `street`, `plaza`, `low_wall`, `fence`, `market_stall`, `well`, `lamp_post`, `skyline`, `treeline`, `far_hills`, `far_town`, `army`, `church`, `terrain`, `road_markings`; atmosphere: `smoke`, `ground_haze`. `cutaway(room, cam_or_point, at_frame=(f0, f1))` hides the walls and ceiling between a camera and the room; `track_cutaway(room, cam.ob, f0, f1)` follows a moving camera.
- **Furniture and props (`furnish`)**: about 140 registered pieces, every one in metres, grounded, tagged with its periods, with a real light where it is a lamp. `furnish.make("goblet", at=(x, y, z), rot_z=)`; `furnish.REGISTRY` lists them; `furnish.catalogue()` prints them. Origin on the floor at the centre of the back face, front toward -Y; wall pieces take their mount height as `at.z`.
- **Dressing (`dress`)**: `dress.room(R, "<theme>", marks=MARK, density=, seed=, keep_clear=)` and `dress.exterior(area, "<theme>", ...)` fill the four depth layers with props that never overlap, never float, and keep the marks and doors clear, plus practicals, floor detail, atmosphere and readable details. Themes: throne_room, great_hall, castle_kitchen, tavern, peasant_cottage, office_open_plan, office_private, home_living_room, home_kitchen, shop_interior (rooms); market_street, village_square, army_camp, battlefield, city_street (exteriors). It returns an inventory (`types`, `objects`, `layers`, `practicals`, `atmosphere`, `details`). `dress.THEMES` holds each theme's periods; a theme must belong to the plan's era.
- **Older outdoor kit (`build`)**: `ground`, `patch`, `stone_wall`, `tower`, `steps`, `banner`, `tree`, `bush`, `flowers`, `grass_tufts`, `ivy`, `reeds`, `rock`, `pond` (with a sluice gate that drains), `barrel`, `crate`, `bucket`, `sack`, `bench`, `torch`, `ring`, `halberd`, `box`, `cyl`, `ball`, `group`, `scatter`. Use `arch.terrain` and the themes for new work.
- Everything reusable that you make is registered with `arch.tag(root, "<type>", kind="prop", size=[w, d, h])` so the audit counts it (`asset-library` skill). Anything not in the kit: plain `bpy`/`bmesh` with `mat.surface(...)`.

**The set standard** (read from `style/style.json` > `sets` by `audit`; the wide must clear every minimum): at least 14 distinct prop types and 60 objects visible in the wide; four depth layers populated (foreground occluder, midground action, background, beyond: sky, vista, a room through a door); at least 3 visible practical lights indoors; at least one atmosphere element; at least 3 readable in-world details; nothing floating or sunk more than 2 cm; no pieces through each other or through walls; no mesh without a material; no ray from any camera that hits nothing; every door and window with something behind it. Enclosed places survive a reverse angle: real walls, floor and ceiling, with the wall nearest the camera hidden per view.

## lights

One light rig per set and time of day, built in `build_set(time)`:

- `lights.rig(mood, sun_from=40, sun_elevation=None, strength=1.0, ambient=None, rim=None, clouds=None, look=True)`: sky, sun, ambient and how the cast takes the light. Moods (`lights.MOODS`): `day_clear`, `day_soft`, `morning`, `golden_hour`, `sunset`, `dusk`, `night_moon`, `storm`, `interior_day`, `interior_warm`, `candlelit`, `office_day`, `office_night`, `cave`. `sun_from` is degrees around the stage from the camera side.
- `lights.window_key(opening, color, power, shaft=True)` a real soft light from outside a window or door with shadows of the frame; `lights.window_sun(room, wall, elevation, yaw, power)` sun patches on the floor; `lights.interior(mood, key_from=, fill=...)` the whole interior rig in one call.
- `lights.practical(name, at, color, power)` a visible source; `lights.flicker`, `lights.change(light, t0, t1, power=)`; `lights.rim_light(target, ...)` a shadowless back light for the characters; `lights.ambient_fill(at, size, power, color)` bounce that lifts shadow into deep colour; `lights.dust(lo, hi)`, `lights.haze(density)` (costly), `lights.light_shaft(...)`; `lights.limit_shadows()` if the shadow pool overflows.
- A motivated key (you can point to its source), a rim or value step that separates the figures from the background, practicals you can see, and one atmosphere element. Darkness is deep colour, never black.

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

`fx.ripple(point, t)` · `fx.splash(point, t, size=)` · `fx.sparkle(obj, t, count=)` · `fx.puff(point, t)` · `fx.drips(anchor, t0, t1)` · `fx.lines(point, t, direction)`.
`core.move(obj, t0, t1, location=, rotation_deg=, scale=)` eased · `core.key(obj, path, t, value)` · `core.show(obj, t, visible)` · `core.at_frame(f)` evaluate the scene before reading a moving object's position.
`shot.t(phrase)` · `shot.span(phrase)` · `shot.seconds` · `shot.frames` · `shot.f(t)` · `shot.moment(name, t)` an extra review still · `shot.subject(name, obj_or_anchor, moments=[view ids])` something the viewer must read · `shot.world`, `shot.plan` · `shot.notes.append("...")` a note for the reviewer.

## What the checks say

`checks.json` has `items`, each `{level: "block"|"warn", code, source: still|view|world|campath|set, view, frame, text}`, plus `blocking`, `warnings`, `campath` (each move with peak speeds; `static_share`), `motion` (the strips) and `set_audit` (`inventory`). `stills` exits 3 while `blocking` is above 0, and the camera preview and Gate C stay shut with a blocking camera item.

**Blocking, and the fix:**

| Code | Fix |
|---|---|
| `no_camera`, `no_views` | create `camera.Camera()` and at least one `cam.view` |
| `subject_hidden`, `nothing_in_frame`, `subject_out_of_frame` | change `side` or the framing, hide the near wall, keep the subject in frame through the move |
| `actor_floating`, `actor_sunk` | stand them on what is under them, or `a.move(..., arc=)` / `a.floating = True` when meant |
| `camera_inside_geometry`, `camera_under_floor`, `camera_too_close`, `camera_through_geometry` | the camera path touches something: shorten the move, move its start, cutaway, or go `through` an opening |
| `speed_over_limit`, `accel_over_limit`, `ang_speed_over_limit`, `ang_accel_over_limit` (blocks at twice the limit), `jerk_spike` | lengthen the move, `ease="settle"`, `blend=0.3`; a whip is exempt |
| `static_share` (above 70% still) | add pushes, drift or tracks to held views |
| `blown_out`, `mostly_black`, `brightness` | a light or the sky is too strong or too weak |
| `set_*` (the audit: `few_prop_types`, `few_objects`, `layers_missing`, `few_practicals`, `no_atmosphere`, `few_details`, `floating`, `sunk`, `intersect`, `through_wall`, `no_material`, `void`, `opening_void`, `flipped_normals`, `zero_area`; the agreement: `set_mark_missing`, `set_no_mark`, `set_theme_mismatch`, `set_time_missing`, `set_file_missing`, `set_not_in_plan`, `set_file_broken`) | the set file or the plan: see the shot-builder agent |

**Warnings** to fix or explain: `face_under_captions` (raise the subject, `place=0.36`), `face_too_small`, `outside_safe_area`, `steep_angle` (over 60 degrees with characters), `view_too_short` / `view_too_long`, `line_crossed`, `whip_duration`, `camera_close`, `stand_in`, `world` (`WORLD:` an asset tagged for another period), `PLAN:` (a view id missing from or added to the plan). A warning you leave standing needs a reason in your return note.

What the numbers cannot say, you judge from the pictures and the strips: is the place complete and art-directed, is every prop grounded, does the costume fit, does each move reveal something and hold the subject where the eye should be.
