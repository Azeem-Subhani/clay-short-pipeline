# Why the test film had sixty physical faults, and what now stops them

27 November 2026. A study run by Claude with Gemini 4 Neon, at the owner's request, after Gemini's frame-by-frame audit of the first film made with the Aj cast (`docs/VIDEO_MISTAKES_AUDIT.md`: hands through doors, props not held, people walking through closed gates, rain under a canopy). The question was not "what is wrong with this film" but "why did the pipeline let it through, and what change stops the next one". Design discussion happened in one shared thread; each hypothesis was tested in its own experiment, scored against one list of faults.

Everything measured is in `output/experiments/` (not committed): `ground_truth.json` (the scored fault list), one folder per experiment with its script, raw results and `REPORT.md`.

## The scored list

Gemini turned its audit into `ground_truth.json`: 64 claims, each with shot, frame, class, severity and the earliest stage that should stop it. Checking each claim against the shot code, it **withdrew four of its own** (a door that was in fact open 82 degrees, a cup carrier cropped by the frame edge, the same box seen from another angle, a seat "swap" that was a 90 degree camera change). That leaves **60 confirmed faults**: 23 a geometry check should catch, 21 a kit action should prevent, 7 that belong to the character gate (glasses off faces, lanyards through collars), 4 for a cross-shot ledger, 5 that only eyes can judge.

Lesson kept from the four withdrawals: **geometry is the authority on where things are; eyes judge whether it reads.** A vision review must not block on a spatial claim that the scene data contradicts.

## What was wrong with the pipeline (five causes, in order of weight)

1. **The measured checks could not see any of it.** `review.checks_at` measured framing, exposure, feet on the floor and the camera. Nothing measured a hand on a prop, a body in a door, or a walk through a closed gate. Every shot of the film had zero blocking items (the one exception, a set-count block on sh05, was rendered anyway: `render` never looked at the count).
2. **No shot was ever reviewed in the form that was rendered.** All eight `verdict.json` files said `fix` or `restage` and were written between 09:25 and 09:56; all eight shot files were changed after that (10:06 to 14:10). The fix rounds went straight to the final render. Nothing in the tools required a passing verdict, and the producer's instructions said "at most two fix rounds, then keep the best version".
3. **The reviewer was told to stop at three problems.** Its instructions said "three real ones beat ten small ones", so camera and story notes used up the list and contact faults were dropped, although they were visible in the 270x480 stills it had (`review/sh02/0109_coffee_guy.a.png` shows the tray behind the shoulder and the strap in the air).
4. **Builders posed by typed numbers instead of asking the kit.** The eight shot files call a named action 10 times, raw `reach` 48 times, raw `arm` 26 times, and set `.parent` by hand 29 times. The bag was fixed to a chest bone at a typed offset; the door hold reached a typed point on the leaf's edge because doors, readers, gates and lifts expose no named grip points; the carrying arm was posed in torso angles under a run clip that pitches the spine 35 degrees.
5. **Some faults are upstream of the shot.** Glasses that sit off a face and a lanyard that cuts a collar are fit problems of the character (Gate A). Rain under the canopy was the weather effect: the set did list the canopy as sheltered, and the wind-slanted streaks still came in under its edge.

## Experiments

| | Hypothesis | Result |
|---|---|---|
| A | Collision geometry (interpenetration depth, passage through closed leaves, rain under cover), run on a sweep of frames, catches most collision faults with few false alarms | **Holds.** 10 of 13 audit items in sh01-sh04; the three "misses" have no 3D overlap in the scene (the audit misread perspective), so 10 of 10 real collisions. False alarms 0, 0, 0, 3 per shot; the three share one cause with a known fix. About 28 s per shot on top of the build |
| B | Interaction geometry (grip, hand-fixed attachments, carry, facing and reach), with the intent of each action known, catches most interaction faults | **Holds, narrowly.** 14 of 20 audit items (70%), 0 to 2 false alarms per shot, 2 to 22 s per shot. It also found four real faults the audit had missed (typists 27 to 156 cm from their keyboards). Four of its six misses are actions that never declared a target |
| C | A reviewer reading the whole shot at two frames a second from the low-resolution preview catches what the stills-based review missed | **Half.** Blind, from 270x480 frames only: Sonnet found 31 of 60 (52%), 21 of the 29 severe ones (72%), precision 0.72, in under two minutes; Opus 25 of 60, precision 0.74; GPT-6.2 Sol 29 of 60 (20 of the 29 severe), precision 0.71. The three together reach 40 of 60. All three missed the same things: small contact clipping (9) and wardrobe faults (5), the classes geometry and Gate A own. The two Claude reviewers repeated one or two claims the scene data disproves |
| D | A carry solved in world space on every frame, over the animated spine, keeps a carried tray level and in front; a shoulder bag worn through one kit call removes the floating strap and the clipping | **Carry holds; bag half.** Tray 28 cm in front of the chest and within 18 cm to the side on every frame through run, stop and walk (it had swung 58 cm out), no blocking flag, 2 to 4 s per shot. Bag body 0 mm into the hip at rest and strap within 2.7 cm of the body, but a strap rebuilt on every frame snaps to an inner clothing layer on about 5 of 96 frames (44 to 102 mm) and costs 43 s per shot. The strap has to be fitted once and skinned to the skeleton (experiment H) |
| E | Named anchors that ride on the moving part and carry an approach direction, an `interact` that checks side, distance and heading before it animates, an arm solve that comes at the anchor along its normal and picks an elbow that clears the fixture, and a passage check in `walk`, make the fixture faults impossible to stage | **Holds on every mark.** Palm 1.0 to 1.9 cm from the door handle, card reader, gate reader and lift button at the hit frame (was 9 to 78 cm), wrist on the correct side on every frame (was behind the stile on 12 of 13), zero arm penetration, facing error 0, passage flags 8 to 0, reach misses 11 to 0; wrong side, out of reach and a walk through a closed leaf each stop the build. Verifying the anchors against the real meshes found two bugs the film had hit (handle points 1.2 cm inside the handle; a reader post offset the shot code forgot) and a fixture flaw (the gate's reader pad sat 18 cm behind its own flap). About 13 s per shot |
| G | Measured checks on the assembled character (face, outfit and add-ons together), in the rest pose and a few test poses, stop the seven character-fit faults at Gate A | **Only in part: 5 of 7, and most of it is too noisy.** The glasses check is clean: 26 and 34 mm of air between bridge and nose on the two audited characters, four flags across the 32 starter characters (the two audited, two more that also float), no false alarm. Cause: the glasses template sets the bridge on the lens plane and nothing seats it on the nose; bending the bridge in memory brings the gap under 2 mm. The add-on-against-garment check caught two of three lanyard cases (the lanyard is fitted to one shirt and worn over any). The hair, stretch and spike checks are not usable: stretch flags all 32 characters and a dozen flags were false alarms. Kept: glasses as a blocking QA item, add-on in garment as a warning |
| K | A mostly automatic ledger (each shot's start and end state exported after the build, compared across the cuts the plan calls continuous, set invariants enforced everywhere, and every picture of the film shown inside the film made from its source shot's own scene) catches the continuity faults | **Holds for 3 of 4, and corrects the fourth.** The door's swing sign (+82 degrees in sh01, -89 in sh02 and sh03) breaks a set invariant; both security pictures are rejected as not made from the shot they show (the "zoom" helper had moved the stranger 1.0 m), and pictures rendered from sh03's own camera are accepted. The bag "left on the desk" is not true in the scene: it jumps to his shoulder one frame later with no pick-up shown, which the ledger reports as a missing pick-up. One false alarm over the film (a badge inside a carried box). 34 added plan lines, about 1 s per shot. Not yet in the pipeline: it changes the plan format, so it is a piece of work of its own |
| M | A reviewer sees more from the finished film at twice the resolution with the captions (one pass over all 70 seconds, 540x960, two frames a second) than from the per-shot preview sheets | **Depends on the reviewer.** GPT-6.2 Sol rose from 29 to 37 of 60 (62%; 23 of 29 severe; precision 0.77) and found eight real faults nobody had listed; its gain is mostly wardrobe (2 to 5 of 7). Claude Sonnet fell from 31 to 24: one pass over the whole film gave 34 findings where its shot-by-shot pass gave 50. Neither found the continuity faults or the picture-against-words ones (a clock showing 21:14 under "before dinner"). Resolution helps; so does reading one shot at a time; neither replaces the ledger |
| H | A strap fitted once in the rest pose around the dressed body and skinned to the skeleton, with the bag body kept outside the hip, gives a worn bag with no penetration on any frame, cheaply | **Does not hold.** The bag body clears hips, thighs and arms on all 435 frames for the blazer character, and the arm no longer passes through it (266 frames before), at about 1 s per shot. But the skinned strap cuts into the blazer by up to 16 mm on 263 of 305 frames and stands 5 to 10 cm off the body, and the same call on a T-shirt character gives hip and thigh spikes on 9 frames. With D that is two failed straps: a shoulder bag needs a strap made and fitted as a wardrobe add-on per body and outfit, like any garment |
| N | Third try at the strap, Gemini's design: keep H's rest fit, then shrinkwrap the torso part of the strap onto a hull of the outermost garment, and push the bag body off the posed body by closest point. A falsification test on sh02 only, two characters | **Killed on the first run.** Worse than H: up to 24 mm into the blazer (262 of 305 frames), 30 mm off the torso where the strap fades toward the bag, and the bag body back in hip and thigh on 98 frames; in the stills the strap pinches into the lower lapel and turns sharply toward the bag. Three designs have now failed on the same thing. Conclusion: no shoulder strap. A bag is carried in the hand; a bag on the body should be a rigid backpack mounted on the upper spine, which has not been built |

Taken together: geometry catches collisions and misses that eyes miss at low resolution; eyes catch what has no geometry (a wave at nobody, a bag left behind, a strap standing like a plank); neither alone is enough, and both are cheap next to a render.

## The film, measured again

Every shot of the test film was put through `clip.py stills` again with the new checks, unchanged otherwise. Before: zero physical findings, one unrelated block. After:

| Shot | Blocking physical items | Warnings | Sweep |
|---|---|---|---|
| sh01 | 8 | 3 | 27 s |
| sh02 | 5 | 9 | 36 s |
| sh03 | 4 | 4 | 10 s |
| sh04 | 17 | 7 | 30 s |
| sh05 | 0 | 0 | 0 s |
| sh06 | 8 | 3 | 9 s |
| sh07 | 2 | 0 | 17 s |
| sh08 | 1 | 7 | 13 s |

45 blocking items: 16 reach misses, 11 interpenetrations, 5 actions facing away from their target, 3 props through a hand, 3 attachments inside a body, 2 loose attachments, 2 carried things flung out, 2 walks through a closed leaf, 1 floating prop. `clip.py review` shows all eight shots blocked, and their final frames as rendered from an earlier form. Scored against the confirmed list for sh02 to sh04 with a generous match (frame range within one second, actor or object), 34 of 35 faults are covered by an item.

## Two shots restaged with the new kit

A copy of the clip (`output/experiments/final_check/clip/`; the film's own shot files were not changed) had sh02 and sh03 restaged with the new calls only: `st.carry(carrier, "R", t0)` for the coffees, `interact` on `handle_R_in`, the reader post's `tap`, the gate's `reader_2` and the lift's `call_0`, and the gate flaps opened before the walk. Through `clip.py stills`:

| Shot | Blocking physical items before | After | What is left |
|---|---|---|---|
| sh02 | 5 (bag in body twice, bag loose, tray flung 58 cm, Maya 6.6 cm inside the door leaf) | 3 | the bag, three times: there is no shoulder bag yet |
| sh03 | 4 (bag twice, Maya 7.3 cm inside the leaf, card tap 73 cm from its target) plus two walks through closed gate flaps | 2 | the bag, and the tray 14.2 mm into his fingers against a 14 mm limit |

Every fault that has a kit answer is gone from the measurements. Two things followed that are the builder's to solve, and the existing framing checks reported both: with her hand now on the lobby-side handle, the street camera no longer sees it (`subject_hidden`), and standing where an arm can reach the gate reader puts Maya at the edge of one view (`nothing_in_frame`). A correct action can cost a framing; that is a fix round, not a fault in the kit.

## What was built

**The review rule** (`tools/reviewgate.py`, 15 tests). A shot has a *build*: a hash of its script, the clip modules it leans on (sh03 reads sh02's marks), its set file, the clip assets it names, its length and word times, and its slice of the plan. A complete `stills` run stamps the build into `checks.json`; the reviewer copies it into its verdict. Final `render` and `assemble` exit 4 unless every shot has stills and a verdict for its current build, no blocking item, and the verdict `pass`. Frames rendered from an earlier build are refused. Autonomous mode does not lift any of this. `clip.py review <clip>` shows where each shot stands; `--accept --reason` records the owner letting a shot through, and is refused in an unattended run. Gemini reviewed the first version and found eight holes (the worst: old final frames were reused after a fix); all eight are closed.

**The physical checks** (`tools/blender/stagekit/physical.py`, thresholds in `style/style.json` > `physical`). Both experiments' checkers, merged, run on every `stills` over the whole shot: every sixth frame, every frame an action lands on, and every frame for passage. On screen a fault blocks; off screen it warns. Codes: `interpenetration`, `through_closed_leaf`, `rain_under_cover`, `grip_open`, `grip_impaled`, `prop_backwards`, `loose_attachment`, `attachment_in_body`, `carry_tilt`, `carry_behind`, `carry_flung`, `not_facing_target`, `reach_miss`, `reach_short`, `arm_through_obstacle`, `floating_prop`, `untargeted_action`.

**Intent, written down** (`stagekit/record.py`). Every hold (kept after its release), every reach and aim, and every targeted action with the frame it lands on is recorded on the shot as it is built, so a check compares the result with what was asked instead of guessing.

**Dense review sheets** (`review/<shot>/dense/`). `stills` renders the whole shot at two frames a second onto clean sheets of six at 540x960. The size comes from experiment M.

**The reviewer's two passes** (`.claude/agents/frame-reviewer.md`). First a physical pass over every dense frame that lists every fault and is never cut short; then the direction questions, which keep their limit. Any physical fault a phone viewer would notice means the verdict is not `pass`. Fix rounds are reviewed.

**The level carry** (`actor.carry(prop, side, t0)`, `stagekit/aj_carry.py`; the `carry` action uses it). The carrying arm is solved in the world on every frame after the locomotion clips are baked, so a tray stays level and 28 cm in front of the chest through a run. One line replaces three typed pose lines; 1.5 s per shot.

**Grip points on fixtures and a checked way to use them** (`furnish.anchor(piece, name)`, `actor.interact(anchor, hit=...)`, `stagekit/anchors.py`). Doors, the card reader post, the wall badge reader, the badge gate and the lift doors carry named anchors, verified against their own meshes, that ride on the moving part. `interact` refuses a wrong side or an out-of-reach anchor, comes at the anchor along its normal, and picks an elbow that clears the fixture. `walk` sweeps the body along its path against every leaf, flap and lift door and writes down any it meets closed; the sweep turns that into a blocking item. The badge gate's reader pad was moved in front of its flaps, where an arm can reach it.

**Fit checks on the assembled character** (`tools/chars_aj/qa.py` `_check_assembled_fit`). Glasses more than 6 mm off the nose block (`glasses_float`); an add-on inside the garment under it warns (`addon_in_garment`). Four starter characters now show a blocking item the next time their QA is run.

**Two faults found on the way.** `idle()` seeded its sway and blinks with Python's `hash()` of the character's name, which changes every time Blender starts: the review stills, the render and each 120-frame chunk of one render all moved differently. The seed is now fixed per name (`core.stable_seed`). And the new sweep read hand vertices from the stored mesh while measuring the masked one a dressed body evaluates to; it now reads both from the evaluated mesh.

**Rain that measures its own shelter** (`fx.rain(cover="auto")`). Each streak is tested against what is built, along the wind and straight up, so nothing is drawn under a canopy, a ceiling or a tree, with no rectangle to type.

**Instructions** for the builder and the producer (`.claude/agents/shot-builder.md`, `.claude/skills/gen-clip/SKILL.md`, the stagekit skill): act through named actions with their target, never fix a prop to a body by hand, open a door before walking through it, read the dense sheets, and what each new check code means.

## The review question: measured checks, a reviewer on dense frames, or an outside video pass

The owner asked for this to be tested and left for their decision. What was measured, all against the same 60 faults:

| Reviewer | What it saw | Found | Severe (of 29) | Precision |
|---|---|---|---|---|
| Geometry (`stagekit.physical`) | the built scenes of sh02 to sh04 | 34 of the 35 faults in those shots, by a generous match | | false alarms 0 to 3 per shot in the experiments |
| Gemini 4 Neon | the finished film, 720x1280, every half second and closer | all 60 (it wrote the list) plus 4 claims it later withdrew | 29 | 0.94 |
| GPT-6.2 Sol | the finished film, 540x960, two frames a second, captions | 37 | 23 | 0.77 |
| Claude Sonnet | per-shot preview sheets, 270x480, two frames a second | 31 | 21 | 0.72 |
| GPT-6.2 Sol | the same preview sheets | 29 | 20 | 0.71 |
| Claude Opus | the same preview sheets | 25 | 15 | 0.74 |
| Claude Sonnet | the finished film, 540x960, one pass | 24 | 14 | 0.71 |

What the numbers say:

- No reviewer at preview size finds much more than half. Three of them together find two thirds. What all of them miss is small contact clipping and wardrobe faults, which geometry and the character QA now measure.
- Size matters: the same model went from 48% to 62% at twice the size. The dense sheets are therefore rendered at 540x960.
- Attention matters as much: one pass over a whole film gave fewer findings than a pass per shot. The frame-reviewer keeps working per shot, with its physical list uncapped.
- No reviewer found the continuity faults or the picture-against-words ones. Those need the ledger and a reader who has the script.
- The best single reviewer was the full-resolution video pass, and it also made four spatial claims the scene data disproves.

Where the two of us ended, after experiment M changed Gemini's first position (a required whole-film pass on the animatic):

- **Required, per shot, before the final render:** the frame-reviewer reads one shot at a time on the 540x960 dense sheets, with that shot's narration in the stamps, and lists every physical fault. This is in place, and the build hash makes every fix round come back to it.
- **Vision may block** on acting, framing, picture against words, and visual glitches nothing measures. **It may not block** on a claim about where things are (contact, passage, a door's angle) that the sweep or the ledger contradicts: that becomes a warning and a closer look.
- **A whole-film pass is advice, never a gate:** one strip of cut frames with the whole narration, for story and pacing.
- Still to add: full-size crops of close-up, insert and in-film screen frames for the reviewer (a clock reading 21:14 is not legible at 540x960), and the last and first frames of the neighbouring shots at each cut.

Whether an outside model (the measured best single reviewer was the full-resolution video pass) reads the finished film as a last look is the owner's decision; nothing in the pipeline depends on it.

## What still has no owner

- **The continuity ledger** (experiment K) is designed and measured, not built: it changes the plan format (`continuity_in`, set invariants, `carry_in` / `carry_out`, `derived_media`), the plan validator and the shot-plan skill together.
- **A bag on the body.** The shot checks block a bag fixed to a body by hand, and three strap designs failed (D, H, N), so today a bag can only be held by its handle. The remaining option is a rigid backpack mounted on the upper spine.
- **Wardrobe fixes behind the new QA items.** Four starter characters wear glasses that float 26 to 37 mm off the nose; the fix is a nose-contact curve in the glasses template, refitted and reviewed through the wardrobe. Lanyards and ties are fitted to one shirt and worn over any garment; they need a fit per underlayer. Neither may be done by loosening a limit.
- **Actions the kit lacks.** Sitting at a desk or a tablet chair with hands on the surface, two-handed carrying of a box, putting a thing into a bag (the bag asset has no cavity), taking a thing from a drawer. Until they exist the checks will block these moments and the builder has to pose them by hand under the checks.
- **Props against props, and balance.** A phone standing on its edge, a mug half off a book, a bag flap through a monitor: the sweep measures actors and what they hold, not dressing against dressing.
- **Picture against words.** A wave at the wrong person, a clock that contradicts the narrator: only a reviewer with the script and the whole film sees these.
- **Structured `avoid` limits.** The registry's limits per fit are prose; a shot can still frame straight into one (the cardigan collar from behind in sh07). Experiment G prototyped tags and a shot-side check for that one case.
- **The test film itself.** Its eight shots are now blocked by 45 items. Restaging them with the new actions is a fix round through the normal builder and reviewer loop.

Gemini's ranking of these by faults prevented per day of work: prop-against-prop and balance checks first (about half a day, four faults), then the glasses and lanyard refits, then `sit at a surface` and a two-handed carry, then the ledger, then `avoid` tags, and restaging the test film last, once the kit it needs is whole.
