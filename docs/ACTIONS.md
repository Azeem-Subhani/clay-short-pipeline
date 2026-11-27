# Actions: what the characters can do

Built from every `voiceover` and `visual` of the scripts in `script-examples/` (28 scripts: 26 in `gold-by-format/`, 2 in `produced-scripts/`; the brief said 56 gold scripts, the folder holds 26). 127 distinct on-screen actions were found; they are covered by 118 named actions in `stagekit.actions`.

## How to call an action

```python
t1 = actor.do("pick_up", ring, hit=shot.t("picked up"))     # the key moment (the grab) lands on the word
t1 = actor.do("wave", t=2.4)                                  # starts at 2.4 s; returns the time it ends
a.do("hand_over", key, to=b, hit=shot.t("gave"))             # two people
t1 = thief.do("sneak", t, to=(3, 1))                         # moving actions return the arrival time
a.do("laugh", t, until=shot.t("stopped"))                    # loops run until `until`
a.do("use_tool", broom, kind="sweep", t=t, speed=1.3)       # speed scales every beat of the action
```

Every action is a performance in three beats (anticipation, main motion, settle), keyed in seconds of the shot, built from view-aware poses, `reach`, `hold` and the gait cycles, so it plays in the front, three-quarter and side drawings and facing either way. `python tools/clip.py actions [word] -v` prints this catalogue; `config/actions.json` is its data. To add one: `ADDING_NEW_ACTIONS.md`.

## Test results

Each action was performed in a plain test scene (backdrop, ground, a prop / target / second character as needed), measured on **every frame** and rendered as a strip (every 2nd frame) and an MP4 (`proof/actions/<Character>/<action>__<view>_<facing>.strip.png` / `.mp4`). A combination passes only if on all frames: limb parts stay on their joints, a held prop stays in the palm, planted feet do not slide, a hand over the head is drawn in front of it, the acting hand is on the target's side, and a reaching palm arrives on the target at the key moment.

**9240 of 9240 action x character x view x facing combinations pass.** Columns below: the five standard body types (adult = AdultMan, child = Boy, baby = Baby, elderly = SeniorMan, robe = Queen), then the ten unusual bodies together. `pass n/n` counts view x facing combinations.

### Core actions on the whole cast

| Action | Characters tested | Combinations | Pass | Failing |
|---|---|---|---|---|
| `walk` | 105 | 330 | 330 | none |
| `point` | 105 | 330 | 330 | none |
| `pick_up` | 105 | 330 | 330 | none |
| `hold_up` | 105 | 330 | 330 | none |
| `hand_over` | 105 | 330 | 330 | none |
| `gasp` | 105 | 330 | 330 | none |
| `talk` | 105 | 330 | 330 | none |
| `sit_down` | 105 | 330 | 330 | none |

## Moving

| Action | What the body does | Needs | adult | child | baby | elderly | robe | unusual bodies | Instead, for unusual bodies |
|---|---|---|---|---|---|---|---|---|---|
| `climb` | climb up or down to a place (ladder, rope, wall): hands reach one after the other | to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: rises with the hands reaching in turn; mermaid: same |
| `crawl` | down on the belly and pull forward with the arms to a place | to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides flat along the ground; mermaid: drags herself by the arms: her natural move on land |
| `crouch` | squat low on the spot (hide, lurk, look at something on the ground) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: settles low, leaning; mermaid: settles low, leaning |
| `fall` | fall over: arms fly up, the figure tips and lands flat (to=(x, y, z) to fall down to a place) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `freeze` (loop) | stop dead mid-movement and hold perfectly still, wide-eyed | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `get_up` | get back on the feet after a fall or lying down | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `hang` (loop) | hang from the hands (a branch, a rope, a ledge) and swing a little | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: hangs and sways; nothing dangles; mermaid: tail hangs |
| `hide` | duck down behind cover, then peek over it | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: sinks low, then peeks; mermaid: sinks low, then peeks |
| `jump` | jump on the spot or to a place (to=): crouch, leave the ground, land with a squash | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: rises and drops (no knee bend); mermaid: a leap out of the water shape: rises and drops |
| `kneel` | drop to the knees | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: settles low with a lean; mermaid: settles low with a lean |
| `lean_on` | lean the weight forward onto something (a counter, a staff, a wall) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `lie_down` | lie flat on the back on the ground | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: tips flat; mermaid: lies on her side |
| `pace` (loop) | walk up and down in agitation (three legs) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides to and fro; mermaid: swims to and fro |
| `peek` | lean the head and shoulders out from behind something, look, pull back | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `recoil` | jerk back from something: hands up in front, body back, a half step away | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `ride` (loop) | seated holding reins or a wheel (horse, cart, car): hands forward, a steady bob | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: arms forward, body low; mermaid: sits side-on, arms forward |
| `roll` | roll along the ground to a place like a log | to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `run` | run to a place: long strides, body forward, elbows pumping | to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides fast; mermaid: swims fast |
| `sit_down` | sit: a small lean forward, then down onto a seat at knee height (mermaid: settles on her tail) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: the body settles a third of the hip height lower; mermaid: settles onto her tail |
| `sit_idle` (loop) | stay seated: small shifts of weight and a look around | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: stays settled low; mermaid: stays on her tail |
| `sleep` (loop) | asleep: eyes shut, slow deep breathing (lying if lie_down came first, else nodding off upright) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `slip` | a foot shoots out, arms windmill, down on the back | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: arms windmill, tips over backward; mermaid: same |
| `slip_banana` | step on a peel without looking: the foot shoots out, the peel flies off, the figure hangs level in the air and lands flat on its back | prop | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides over the peel, tumbles in the air, lands flat; mermaid: same |
| `sneak` | creep to a place: knees bent, careful high steps, hands held up (also tiptoe) | to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides slowly, leaning forward; mermaid: swims slowly |
| `stand_up` | rise from sitting, kneeling or crouching | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: rises back to float height; mermaid: rises off her tail |
| `step_forward` | one decisive step toward the facing side | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: a short glide; mermaid: a short glide |
| `stomp` | angry stomp on the spot: fists down, one foot slammed twice | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: fists down and two squashes, no foot; mermaid: same, no foot |
| `struggle` (loop) | stuck fast (mud, a trap, a grip): strain upward, twist, strain again | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `swim` (loop) | tread water or swim to a place (to=): body low, arms sweeping (mermaid: tail strokes) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | mermaid: her natural gait |
| `tiptoe` | tiptoe: the sneak cycle, upright and a little faster | to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides slowly; mermaid: swims slowly |
| `turn_around` | turn sharply to face the other way | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `wake_up` | wake with a start and sit / stand up | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `walk` | walk to a place on the walk cycle, feet planted (ghost: floats, mermaid: swims) | to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides with a slow bob (Ghost); mermaid: swims: glides low with a small bob |

## Hands and props

| Action | What the body does | Needs | adult | child | baby | elderly | robe | unusual bodies | Instead, for unusual bodies |
|---|---|---|---|---|---|---|---|---|---|
| `aim` | level a held thing at a target and keep it there (flashlight, pistol, sword, wand) | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `beckon` | palm up, curl the hand toward the body twice: come here | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `blow` | lean in and blow (out a candle, on hot soup, dust off a book) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `carry` | carry a thing level in front of the chest and keep it there: an Aj solves the carrying arm on every frame, so it stays upright through a run, a stop and a walk | prop | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `clap` | clap the hands together in front of the chest | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `drink` | lift a held cup to the mouth, tip it, lower it | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `drop` | the hand opens and the held thing falls to the ground | prop | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `dust_off` | brush the clothes down with both hands | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `eat` | bring a held bite to the mouth and chew | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `hands_up` | both empty hands thrown up (surrender, not mine) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `haul` | drag a heavy thing to a place: both hands on it, body thrown against the weight | prop, to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides backward with the load; mermaid: same |
| `hold_up` | raise the hand (and whatever it holds) high to show it | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `hold_up_finger` | one finger raised: "one rule", a warning, an idea | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `juggle` (loop) | keep two or three small things in the air: hands alternate low in front, eyes follow the top of the arc | props | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: no knee dip; the body bobs; mermaid: same |
| `hold_door` (loop) | grip a door's handle and keep the hand on it until= (target = furnish.anchor(doors, "handle_R_in"): side, reach and facing are checked, the hand follows the leaf while it swings, and stays until released) | target | not run: needs a fixture; see tools/tests/kitfix/test_anchors.py | - | - | - | - | - | same as everyone |
| `knock` | rap on a door with the knuckles three times | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `lift` | take a thing in both hands and lift it overhead (by= metres up: the hands stay on a thing that slides, like a gate) | prop | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `light` | strike a match / touch a flame to a thing held in the other hand or at a place | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `open_door` | hand on the handle and swing it (door= the leaf object, deg= how far): also close_door with a negative deg; with a furnish.anchor handle as target the palm lands on it, checked, and rides it while the leaf swings | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `phone` (loop) | hold a phone or a radio to the ear and talk (screen=True: hold it in front and look at it) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `pick_up` | look at a thing, bend to it, close the hand on it and bring it up (both=True: with two hands) | prop | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `point` | turn to a thing and point straight at it with one finger | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `pour` | tip a held jug, bottle or bucket so it pours (over to= if given) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `press` | jab a button, a switch or a bell with one finger (palm=True: slap it with the flat hand) | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `pull` | grab a thing with both hands and heave back (by=(dx, dy) also moves the thing) | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `push` | both hands on a thing and shove (by=(dx, dy) also moves the thing) | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `put_down` | set a held thing down on a place and take the hand away | prop, to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `read` (loop) | hold a paper or book up in both hands and read it, eyes moving along the lines | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `show` | hold a thing out in front for someone to see (chest height) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `slam` | bring the fist (or a held thing) down hard on a surface | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `stash` | tuck a held thing away into a pocket, a bag or under the coat (it disappears) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `take_out` | hand into a pocket or bag and out again holding a thing (prop appears in the hand) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `tap` | tap things one by one with a finger (counting): targets=[...] or the air in front | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `throw` | wind up and throw a held thing to a place (to=) or just ahead | prop | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `tie` (loop) | both hands busy together in front (tie a knot, fasten, button, unwrap) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `tip_hat` | touch the hat brim and dip the head | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `turn_key` | hand to a lock, a handle or a dial and twist the wrist (lock, unlock, turn a knob) | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `use_tool` (loop) | work a held tool in strokes: kind = dig | sweep | mop | hammer | saw | stir | cut | paint | scrub | chop | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `wave` | raise an open hand and wave it (greeting, goodbye, waving someone on) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `write` (loop) | bend over a page and write, the hand making small quick strokes | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |

## Reactions

| Action | What the body does | Needs | adult | child | baby | elderly | robe | unusual bodies | Instead, for unusual bodies |
|---|---|---|---|---|---|---|---|---|---|
| `angry` | fury: face first, fists clenched at the sides, body forward | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `cheer` | jump with both arms thrown up | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `cower` (loop) | shrink down small behind raised arms, trembling | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `cry` (loop) | face in the hands, shoulders shaking | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `dread` | the smile goes, the body stiffens, a hand comes up to the collar | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `facepalm` | palm to the forehead, head down | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `gasp` | shock: the face first, a jolt up, both hands fly up beside the face | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `inspect` | lean right in to examine a thing closely | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `jeer` (loop) | shake a raised fist and shout (a crowd booing) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `laugh` (loop) | head back, one hand on the belly, shoulders shaking | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `listen` (loop) | stop, tilt the head, a hand cupped at the ear | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `look_around` | look one way, then the other, then back | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `look_away` | eyes and head turned away on purpose (avoiding someone's eye) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `nod` | nod the head twice | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `panic` (loop) | arms flailing overhead, looking one way then the other, shaking | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `proud` | chest out, chin up, fists on the hips | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `shake_head` | shake the head: no | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `shrug` | shoulders up, palms out, head to one side, and down again | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `sigh` | a breath in, then shoulders and head drop (also: sad slump) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `smile` | a smile or grin with a small lift of the head (smug=True: chin up, hands on hips) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `sneeze` | the head goes back, back... and snaps forward | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `sniff` | nose up, two short sniffs | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `suspicious` | arms crossed, a slight lean in, narrowed look | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `think` (loop) | hand to the chin, eyes up and away | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `tremble` (loop) | the whole body shakes (cold, fear, rage held in) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `watch` (loop) | turn to a thing and keep the eyes on it (also: lock eyes with a person) | target | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `whistle` (loop) | lips pursed, head bobbing to a tune | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `yawn` | a big yawn behind the hand, with a stretch | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |

## Two people

| Action | What the body does | Needs | adult | child | baby | elderly | robe | unusual bodies | Instead, for unusual bodies |
|---|---|---|---|---|---|---|---|---|---|
| `argue` (loop) | two characters go at each other: jabbing fingers and thrown-up hands by turns | other | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `bow` | bow from the waist, one hand on the chest, and straighten | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `chase` | one runs for it to a place and the other runs after, a stride behind | other, to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides after / away; mermaid: swims after / away |
| `cover_mouth` | clap a hand over the mouth: the character's own, or another's (other=) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `curtsy` | curtsy: skirt held out, knees dip, head bows | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: a dip of the whole body; mermaid: a dip of the whole body |
| `grab_person` | seize another character by the arm or collar and hold on | other | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `hand_over` | hold a thing out to another character, who takes it (a.do('hand_over', prop, to=b)) | prop, to | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `handshake` | two characters clasp right hands between them and shake | other | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `hug` | two characters close in and put their arms round each other | other | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: glides in; mermaid: glides in |
| `pat_back` | friendly slaps on another character's shoulder | other | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `plead` (loop) | hands clasped out in front, body bent toward the other (knees=True: on the knees) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | no legs: settles low instead of kneeling; mermaid: settles low |
| `push_person` | shove another character, who staggers back | other | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `receive` | hold out an open hand and close it on a thing that is given or lying there | prop | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `salute` | snap the flat hand to the brow, hold, drop it | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `slap_away` | knock another character's reaching hand aside | other | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `whisper` (loop) | lean in to another character with a hand beside the mouth and speak low (other=) | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |

## Talking

| Action | What the body does | Needs | adult | child | baby | elderly | robe | unusual bodies | Instead, for unusual bodies |
|---|---|---|---|---|---|---|---|---|---|
| `shout` (loop) | shout or call out: body forward, mouth wide, a hand cupped at the mouth or a fist up | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |
| `talk` (loop) | speak a line with lip sync and hand gestures: do("talk", first="Bring it back", last="is yours") or t0/t1 | none | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 6/6 | pass 30/30 | same as everyone |

## From the scripts to the actions

Every action found in the scripts, most frequent first, with the call that performs it.

| In the scripts | Beats | Example (script / beat) | Hands and props in the scripts | Performed with |
|---|---|---|---|---|
| smile grin | 24 | Twelve Robbers Broke Into Jail / 4:reveal: "grins outside the locked cell" | none | `smile`: `smug=True` for a smirk |
| talk | 23 | The Cook and the Golden Cup / 3:strike: ""A toast from the king's own cup!" he announced" | one free hand gestures; the other may hold a prop (goblet, clipboard, sack, bars) | `talk` |
| walk | 15 | The Cook and the Golden Cup / 2:target: "cook walks steadily toward him carrying the golden goblet" | free arms, or one hand holding a prop: goblet, flashlight, wooden box, staff | `walk` |
| laugh | 13 | The Crown on the Red Carpet / 2:attempt_one: "noblemen burst out laughing" | hands on belly or slapping table | `laugh` |
| shout | 13 | The Sand That Would Not Let Go / 1:kill_exit: "shouts across a wide empty gray beach" | hand cupped at mouth or fist raised; clipboard | `shout` |
| run | 11 | The Man in the Bee Suit / 3:improvise: "beekeeper sprints out of an open elevator" | free arms pumping, or clutching a prop: wooden box, coffees, cash bags | `run` |
| sit idle | 11 | The Duel He Won Sitting Still / 3:ego: "sits peacefully cross-legged in the dust" | hands on lap/table; cards, candle jar, plastic cup, knife | `sit_idle` |
| hold up object | 10 | The Ring in the Pond (produced) / 4:attempt_three: "holds up a gold ring in the middle of an empty" | R hand or both: keys, sack of gold, candle, dragon scale, parchment, brass key, ring, pan lid, phone, glove, bottle | `hold_up`: `show` for chest height toward someone |
| watch | 10 | The Boy in the Basement / 0:mission: "watches a lonely farmhouse from between dark trees" | none | `watch` |
| stand idle | 9 | The Duel He Won Sitting Still / 1:kill_obvious: "stands calmly with empty hands" | empty open hands at sides; or staff and sack, sword at waist | `actor.idle()`: blinks and breath; no action needed |
| freeze | 9 | The Statue That Was Breathing / 0:freeze_frame: "A motionless figure wrapped in a white sheet" | hand stopped mid-reach; sword raised; sheet wrapped around body | `freeze` |
| put down | 9 | The Cook and the Golden Cup / 3:strike: "the cook set the gleaming cup right under the brother's nose" | R hand or both: goblet, candle, envelope, gold chest, sack, pan lid, walking stick, glass jar | `put_down` |
| carry | 9 | The Man in the Bee Suit / 0:freeze_frame: "hugs a wooden hive box in a marble hotel lobby" | both arms or one hand: cardboard box, wooden hive box, coffees, goblet, sack over shoulder, staff, duffel bag, gold chests | `carry`: then `walk(..., arms=False)` |
| sneak | 8 | The Boy in the Basement / 3:strike: "He crossed the basement floor without a sound" | arms tucked or hands slightly raised for balance; sometimes a key or tool in hand | `sneak`: tiptoe is `tiptoe` |
| pick up | 8 | The Crown on the Red Carpet / 4:attempt_three: "She plucked it up and winked" | R hand (or both for heavy): crown, ring, gold bar, drop sheet, flashlight, pitcher, pan lid | `pick_up`: `both=True` for a heavy thing |
| lock unlock | 8 | The Boy in the Basement / 3:strike: "quietly turns a brass key in an upstairs bedroom door" | R hand; key (brass, iron, silver) | `turn_key`: `prop=` the key |
| gasp | 8 | The Ring in the Pond (produced) / 0:challenge: "A queen in a red dress gasps" | hands may fly to mouth/chest; or keep clutching a prop | `gasp` |
| climb | 6 | Three Rules Cut in the Desk / 4:breach: "scrambled down the ladder" | both hands on rungs/edge; rope ladder, ladder, ice edge | `climb` |
| lean | 6 | The Sand That Would Not Let Go / 3:failed_attempt: "leans heavily on a vertical walking stick" | hands on support: walking stick, counter, throne arms | `lean_on` |
| drive vehicle | 6 | The Wrong Road / 1:preparation: "the driver speaks quietly into a dashboard radio" | both hands on steering wheel or cart reins | `ride`: `bob=False` for a car |
| point | 6 | The Paper That Trapped the Mayor / 4:reveal: "points straight at the pale mayor beside the gallows" | R arm; sometimes holding parchment or clipboard in the other hand | `point` |
| panic | 6 | The Man in the Bee Suit / 4:full_circle: "grown men shriek like toddlers" | hands flailing or raised; grip seat | `panic` |
| tremble shiver | 6 | One Key in Each Hand / 2:inventory: "Shivering violently" | shaking hands; keys, paper, sword | `tremble` |
| grab person | 6 | The Wrong Road / 3:strike: "yanked the trembling passenger by the collar" | one or both hands on collar/shoulder/arms; handcuffs | `grab_person` |
| whisper | 6 | The Boy in the Basement / 4:reversal: "whispered, "Papa."" | one hand near mouth; radio handset | `whisper` |
| lie down | 5 | The Sand That Would Not Let Go / 4:escape: "lies flat back across the horizontal walking stick with arms spread" | arms at sides or spread wide; walking stick, knife | `lie_down` |
| fall | 5 | One Key in Each Hand / 0:countdown: "hiker plunges through cracked gray lake ice" | arms flailing | `fall`: `to=` for a fall down to a place |
| hang from rope | 5 | The Painter on the Rope / 0:freeze_frame: "dangles from a rope high on a glass skyscraper" | one or both hands on rope/branch; safety rope, tree branch, paint can | `hang` |
| wave | 5 | The Thief Who Called the Police / 2:clue_blunder: "waves a clipboard frantically to halt an armored truck" | R hand open; or clipboard in hand | `wave` |
| open door | 5 | The Paper That Trapped the Mayor / 3:ego: "swung the cell doors open" | one or both hands: cell doors, window, floor hatch | `open_door` |
| slide across table | 5 | The Letter on the Card Table / 3:ego: "The stranger slides the sealed envelope toward the mine boss" | R hand or one finger: rule card, sheet of rules, envelope, silver coins, deed | `push`: one hand: `press(target=...)` then `core.move` the thing |
| angry | 5 | The Gold the Guards Laughed At / 4:reveal: "furious guards stare down at a smashed clay pot" | clenched fists; sword, knife | `angry` |
| hand over | 5 | The Captain's One Sentence / 4:reveal: "holds out a heavy iron key to the smiling captain" | R hand: duffel bag, candle, goblet, iron key | `hand_over` |
| stand up | 4 | The Duel He Won Sitting Still / 4:reveal: "The old man grinned, stood up, and dusted off his robe" | hands push off knees/ground | `stand_up` |
| hide behind cover | 4 | The Paper That Trapped the Mayor / 3:ego: "watches silently from behind a stone pillar" | hands on cover edge | `hide` |
| sleep | 4 | The Candle That Lasted Longest / 4:attempt_three: "tucked the unlit candle under his pillow before going to sleep" | none; pillow, candle under pillow | `sleep` |
| jump | 4 | The Crown on the Red Carpet / 2:attempt_one: "leaped fifteen feet through the air" | arms swing; sometimes armored | `jump`: `to=` for a leap |
| struggle stuck | 4 | The Sand That Would Not Let Go / 1:kill_exit: "strains upward on one stuck leg" | arms straining; walking stick | `struggle` |
| turn around | 4 | The Man in the Bee Suit / 2:trigger: "spin sharply inside a hotel elevator to stare" | none | `turn_around` |
| drop | 4 | The Man in the Bee Suit / 4:full_circle: "two shrieking robbers drop their guns" | one or both hands: pistols, cash bags, ring, crown | `drop` |
| take out | 4 | The Dragon Three Kings Bought / 2:clue_blunder: "dragged out a jagged black dragon scale" | R hand: packages, dragon scale, cash bundles, phone, glove, keys | `take_out` |
| stash | 4 | Two Seconds at the Office Door / 2:opportunist: "slips an open laptop smoothly into a leather bag" | R hand: laptop, clay pot, map, candle | `stash` |
| cut | 4 | The Boy in the Basement / 1:preparation: "snips a thin black wire cleanly with metal wire cutters" | R hand tool, L hand steadies: wire cutters, knife, utility knife; wire, gold bar, rope | `use_tool`: `kind="cut"` (or `"saw"`) |
| slam smash | 4 | The Letter on the Card Table / 4:reveal: "He slammed his four kings face-down" | palms or R hand: playing cards, gold chest, ice edge | `slam` |
| pour | 4 | The Cook and the Golden Cup / 1:preparation: "the cook pours dark red wine carefully into an ornate golden goblet" | R hand or both: wine jug into goblet, gold sacks, paint can, water pitcher | `pour` |
| radio phone call | 4 | The Wrong Road / 1:preparation: "he lifted his handset, whispered four words into his radio" | R hand; radio handset, phone | `phone` |
| dread sweat | 4 | The Cook and the Golden Cup / 4:reversal: "his face went chalk-white" | hand hovering or tugging collar | `dread` |
| listen | 4 | The Ring in the Pond (produced) / 1:catch: "while three people listen" | hand may cup ear | `listen` |
| look around | 4 | The Pan on Fire / 1:kill_exit: "glancing between the blazing stove and a closed bedroom door" | none | `look_around` |
| peek | 4 | The Cook and the Golden Cup / 0:mission: "peers through a stone kitchen archway" | hand on corner edge | `peek` |
| smug pose | 4 | The Candle That Lasted Longest / 2:attempt_one: "A boastful young man" | hands on hips or holding prop high: candle, cards | `proud` |
| carry person | 4 | The Boy in the Basement / 3:strike: "lifts the wide-eyed boy with one hand over his mouth" | both arms (one hand may cover mouth); child | `carry`: `carry(target=child.stage)`: the child's stage empty rides the hands. Not tested in isolation |
| lock eyes | 4 | The Statue That Was Breathing / 2:trigger: "One spun around and locked eyes on you" | none | `watch`: both ways |
| step forward | 3 | The River and the Dry Feet / 1:catch: "Three confident men step forward on the rocky riverbank" | arms at sides or elbowing others | `step_forward` |
| climb through window | 3 | The Boy in the Basement (produced) / 2:target: "A dark shape climbs through a ground-floor window" | both hands on sill/frame | `climb`: `crouch`, then `climb(to=the sill)`, then `jump(to=inside)` |
| swim tread water | 3 | One Key in Each Hand / 1:kill_exit: "A lone head and shoulders bob inside a jagged hole" | arms on water/ice edge | `swim` |
| ride horse | 3 | The River and the Dry Feet / 3:attempt_two: "rides a massive horse into the river" | both hands on reins | `ride`: seat the figure on the horse with `place` |
| recoil | 3 | The Cook and the Golden Cup / 4:reversal: "The pale-faced brother recoils from the golden cup" | hands thrown up or yanked back | `recoil` |
| haul heavy | 3 | The Gold the Guards Laughed At / 0:hook: "hauls a heavy sack of gold out of a jungle temple" | both hands: sack of gold, cash bags | `haul` |
| pull object | 3 | The Wrong Road / 2:target: "tugs at the locked cab door handle" | one or both hands: car door handle, fishing net, keys as ice picks | `pull`: `by=` moves the thing |
| hold door open | 3 | Two Seconds at the Office Door / 1:mistake: "props a badge-locked glass office door open" | one arm extended on door; glass door, gate | `hold_door(target=furnish.anchor(doors, "handle_R_in"), until=...)` |
| press button | 3 | The Statue That Was Breathing / 4:full_circle: "slam the red alarm" | R hand/palm; alarm button, power-lock switch, burner dial | `press` |
| open container | 3 | The Man in the Bee Suit / 4:full_circle: "flip the brass latch, and tip the lid wide open" | both hands: hive box, duffel bag, wall safe | `lift`: `lift(target=the lid, by=0.3)` or `tie` for a zip or latch |
| light flame | 3 | The Candle That Lasted Longest / 2:attempt_one: "He struck his match immediately" | R hand match, L hand candle; match, candle, sheet of paper | `light` |
| read | 3 | The Paper That Trapped the Mayor / 4:reveal: "the king's inspector read every word" | one or both hands: parchment, note; finger tracing desk carving | `read` |
| draw paint | 3 | The Painter on the Rope / 4:full_circle: "smears a giant red arrow pointing upward across the glass" | R hand/palm: stick or chalk, paint-covered palm, paint brush; paint bucket | `use_tool`: `kind="paint"` |
| tie fasten | 3 | The Painter on the Rope / 1:rewind: "ties his safety rope on a sunny skyscraper roof" | both hands: safety rope, shoelace, seatbelt | `tie` |
| aim weapon | 3 | The Man in the Bee Suit / 0:freeze_frame: "two masked robbers point pistols at him" | R hand or both: pistol, rifle, sword | `aim`: `prop=` the weapon |
| think | 3 | The Candle That Lasted Longest / 4:attempt_three: "He looked at his candle, looked at his match" | hand to chin; candle, match | `think` |
| shake head | 3 | The Photo of the New Keys / 4:collapse: "shakes his head while the stunned nurse stands beside him" | none | `shake_head` |
| jeer | 3 | The Duel He Won Sitting Still / 3:ego: "three thousand voices roared, "Coward!"" | fists raised | `jeer` |
| suspicious squint | 3 | Twelve Robbers Broke Into Jail / 2:clue_blunder: "the suspicious gang leader squints closely at him" | arms may cross | `suspicious` |
| inspect closely | 3 | The Statue That Was Breathing / 4:full_circle: "A squinting burglar shines a flashlight inches from" | flashlight or phone in hand | `inspect` |
| push person | 3 | The Captain's One Sentence / 0:hook: "Angry sailors shove their captain down a rope ladder" | both hands on the other's back/shoulders | `push_person` |
| plead beg | 3 | The Paper That Trapped the Mayor / 2:clue_blunder: "pleading with the greedy mayor" | clasped hands or gripping bars; dragon scale | `plead`: `knees=True` |
| sit down | 2 | The Duel He Won Sitting Still / 3:ego: "the old man immediately sat down in the dirt" | hands may brace on knees/ground | `sit_down` |
| kneel | 2 | The Crown on the Red Carpet / 4:attempt_three: "kneels on the bare stone floor rolling up the red carpet" | both hands working a prop: carpet roll, dragon scale | `kneel` |
| crouch | 2 | The Stranger's Bag / 2:opportunist: "The guy crouched down like he was tying his boot" | hands near feet or on knees | `crouch` |
| slip | 2 | The River and the Dry Feet / 2:attempt_one: "soldier slips on a mossy river rock" | arms windmill | `slip` |
| roll sideways | 2 | One Key in Each Hand / 4:escape: "Roll sideways toward shore like a log" | arms tucked | `roll` |
| enter exit vehicle | 2 | The Wrong Road / 0:mission: "the businessman slid into the back seat" | hand on door | `step_forward`: `step_forward` + `sit_down` / `stand_up` |
| throw | 2 | The Crown on the Red Carpet / 0:challenge: "tossed his solid gold crown dead-center onto a red carpet" | R hand or both: crown, cash bags | `throw` |
| hold up finger | 2 | The Crown on the Red Carpet / 1:catch: "The king holds up one finger" | R hand | `hold_up_finger` |
| lift | 2 | The Ring in the Pond (produced) / 4:attempt_three: "She walked to the gate and lifted it" | both hands: wooden gate, gold crown | `lift`: `by=` for a thing that slides up (a gate) |
| close door | 2 | Twelve Robbers Broke Into Jail / 4:reveal: "swung the heavy iron door shut" | one or both hands: iron cell door, wooden window | `open_door`: negative `deg` |
| stab plant | 2 | One Key in Each Hand / 4:escape: "Two fists jab house keys into solid lake ice" | one or both fists: house keys, walking stick | `slam`: with the thing held |
| grip bars | 2 | The Paper That Trapped the Mayor / 2:clue_blunder: "The pirate captain grips the iron bars pleading" | both hands; iron bars | `push`: `push(target=the bars)` without `by`; add `tremble` to rattle them |
| write sign | 2 | The Paper That Trapped the Mayor / 3:ego: "he scribbled his bold signature" | R hand quill, L hand holds paper; quill, parchment pass | `write` |
| use phone | 2 | The Photo of the New Keys / 1:mistake: "snaps a clear phone photo" | R hand phone (L hand may hold keys up); phone | `phone`: `screen=True` |
| shine flashlight | 2 | The Statue That Was Breathing / 4:full_circle: "shines a flashlight inches from the dusty motionless face" | R hand; flashlight | `aim`: `prop=` the torch |
| reach for weapon | 2 | Twelve Robbers Broke Into Jail / 1:kill_obvious: "twelve rough outlaws reach for their holsters" | R hand; holster, jacket | `take_out`: `spot="belt"` |
| hands up | 2 | The Stranger's Bag / 3:no_return: "the engineer raises empty hands" | both hands empty | `hands_up` |
| sad slump | 2 | The Photo of the New Keys / 0:contrast: "A heartbroken young nurse" | hands limp on knees | `sigh` |
| shrug | 2 | The Candle That Lasted Longest / 4:attempt_three: "looked at his match, shrugged" | both hands; may hold candle/match | `shrug` |
| nod | 2 | The Stranger's Bag / 1:mistake: "the engineer nodded" | none | `nod` |
| cheer | 2 | The Duel He Won Sitting Still / 4:reveal: "as the crowd cheers" | both arms up | `cheer` |
| cower | 2 | The Boy in the Basement / 2:target: "a small boy sits huddled alone on a bare basement mattress" | arms around knees | `cower` |
| avoid eye contact | 2 | The Night Guard's Three Rules / 0:hook: "and won't meet your eyes" | none | `look_away` |
| receive | 2 | The Stranger's Bag / 1:mistake: "a polite traveler takes a black duffel bag from a hurried man" | R hand or both: duffel bag, key, candle | `receive` |
| cover mouth | 2 | The Boy in the Basement / 3:strike: "he clamped a hand over the boy's mouth" | R hand | `cover_mouth`: `target=` the other character |
| hug | 2 | The Boy in the Basement / 4:reversal: "The child buried his face in the man's coat" | both arms around the other | `hug` |
| argue | 2 | The Man in the Bee Suit / 2:trigger: "Two guys in dark ski masks were arguing over the vault code" | jabbing fingers, open palms | `argue` |
| pace | 1 | The Duel He Won Sitting Still / 4:reveal: "he paced and shouted while the whole stadium laughed" | sword in R hand | `pace` |
| stomp storm | 1 | The Duel He Won Sitting Still / 4:reveal: "red-faced samurai storms over the line in the dust" | clenched fists; sword | `stomp`: then `walk` with `arms=False` |
| wake up | 1 | Three Rules Cut in the Desk / 4:breach: "woke up at three in the morning smelling thick woodsmoke" | none | `wake_up` |
| crawl on belly | 1 | One Key in Each Hand / 4:escape: "slides out on their stomach" | both fists gripping house keys as ice picks | `crawl` |
| beckon | 1 | The Dragon Three Kings Bought / 0:hook: "a grinning king waves servants forward with chests of gold" | R hand | `beckon` |
| roll up | 1 | The Crown on the Red Carpet / 4:attempt_three: "rolling the carpet up like a giant sleeping bag" | both hands; red carpet | `tie`: `kneel`, then `tie(target=the roll)` |
| tap keycard | 1 | Two Seconds at the Office Door / 1:mistake: "Maya tapped her keycard" | R hand; keycard | `press`: `palm=True`, card held |
| drink | 1 | The Stranger's Bag / 4:collapse: "sipping soda at thirty thousand feet" | R hand; plastic cup | `drink` |
| blow out | 1 | The Candle That Lasted Longest / 1:catch: "Then he blew out the kitchen lamp" | none or one hand cupped; lamp | `blow` |
| mop | 1 | The Statue That Was Breathing / 1:rewind: "mops a gleaming museum gallery floor" | both hands; mop | `use_tool`: `kind="mop"` (or `"sweep"`) |
| hold cards | 1 | The Letter on the Card Table / 1:kill_obvious: "he fans four kings close to his chest" | both hands; playing cards | `read` |
| count tap | 1 | The Captain's One Sentence / 2:clue_blunder: "the captain calmly taps crates one by one" | R index finger/hand; wooden crates | `tap`: `targets=[...]` |
| shake object | 1 | The Gold the Guards Laughed At / 3:ego: "shakes the stolen clay pot beside his ear" | R hand; clay pot | `listen`: `hold` the thing, then `listen` and `shake` |
| hammer nail | 1 | The Paper That Trapped the Mayor / 4:reveal: "nailed the mayor's signed pass straight to the dock post" | R hand hammer, L hand holds paper; parchment pass, nail | `use_tool`: `kind="hammer"` |
| fish with net | 1 | The Ring in the Pond (produced) / 3:attempt_two: "He fished all day with a long net" | both hands; fishing net | `use_tool`: `kind="sweep"`, net held with `turn=True` |
| tip hat | 1 | Twelve Robbers Broke Into Jail / 4:reveal: "tipped his hat" | R hand; hat | `tip_hat` |
| dust off | 1 | The Duel He Won Sitting Still / 4:reveal: "dusted off his robe" | both hands; robe | `dust_off` |
| cry | 1 | The Paper That Trapped the Mayor / 2:clue_blunder: "sobbed to the mayor" | hands gripping bars or covering face | `cry` |
| yawn | 1 | The River and the Dry Feet / 4:attempt_three: "he yawned, stood up" | one hand to mouth | `yawn` |
| hold back sneeze | 1 | The Statue That Was Breathing / 4:full_circle: "you're fighting the sneeze of your life" | none (arms wrapped in sheet) | `sneeze` |
| whistle | 1 | The Painter on the Rope / 1:rewind: "whistling along to the radio" | hands busy with brush/rope | `whistle` |
| sniff | 1 | Three Rules Cut in the Desk / 4:breach: "smelling thick woodsmoke" | none | `sniff` |
| chase | 1 | The Man in the Bee Suit / 3:improvise: "two angry robbers chasing close behind" | pursuers may hold pistols | `chase` |
| pat back | 1 | The Cook and the Golden Cup / 2:target: "slapping the king's back" | R hand | `pat_back` |
| slap hand away | 1 | The Gold the Guards Laughed At / 3:ego: "slaps a rookie's hand away from a pile of yellow bars" | R hand; gold bars | `slap_away` |

## Actions in the library that no gold script uses yet

Asked for in the brief or needed to make the others complete: `bow`, `clap`, `curtsy`, `eat`, `facepalm`, `get_up`, `handshake`, `juggle`, `knock`, `salute`, `show`, `slip_banana`, `tiptoe`.

`juggle` and `slip_banana` were added by following `ADDING_NEW_ACTIONS.md` literally, to prove the procedure.

## Unusual bodies in one place

| Body | Characters | What changes |
|---|---|---|
| no legs | Ghost | every gait is a glide with a bob; sit / kneel / crouch settle the body about a third of the hip height lower; no foot or knee work; `legs()` only lowers the body |
| tail | Mermaid | every gait is a swim (a low glide); she sits on her tail (the body settles lower); `legs()` only lowers the body; her fin sways by itself |
| wings, tail | Dragon, Fairy | standard arms, legs and gaits; wings and tail are swung by `idle()` (`cl_wiggle`), so they keep moving through every action |
| antennae, loose ends | Alien, Robot, Mummy | standard body; the marked parts sway by themselves |
| claws, muzzle | Werewolf | standard body; claws ride the hands, so `fist` and `grip` shapes show them |
| child height | Goblin, Fairy | reach and pick-up lean and crouch more; everything else as a child |
| legs, as drawn | Genie | standard body (the sheet shows legs; a smoke tail was not built) |

## Everything that still fails

Nothing: every tested combination passes.
