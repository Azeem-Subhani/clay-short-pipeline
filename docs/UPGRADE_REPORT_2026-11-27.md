# Pipeline upgrade: completion report (27 November 2026)

Branch `pipeline-upgrade-v1`, 26 commits after the snapshot `fa409b1`, nothing pushed. The work was planned in the main session and built by sub-agents; every milestone was reviewed, tested and committed by the main session.

## Result in one paragraph

The pipeline now casts Mixamo-rigged characters from the new pack, builds complete audited sets, moves the camera through a real move library, stops at three recorded approval gates, and blocks on measured faults. One film was made end to end with the gates bypassed: `output/clips/two-seconds-at-the-office-door/final/two-seconds-at-the-office-door.mp4` (69.7 s, 1080x1920, 8 shots, 24 views, QA PASS with one length warning). An independent review graded the first cut **B, not A+**; the four faults it rated high were then fixed and the film re-rendered. The revised cut has not been independently re-graded.

## What was built

| Area | What exists now | Where |
|---|---|---|
| Characters | The Aj family behind the existing actor interface: hidden control rig on the Mixamo bones, faces from shape keys and the 2D mouth, finger hand shapes and a grip solver, 32 starter characters on all 8 bodies | `tools/blender/stagekit/{cast_aj,aj_rig,aj_face,aj_hands,aj_wardrobe}.py`, `tools/blender/ajkit/`, `config/cast.json` |
| Motion | 22 Mixamo clips registered and analysed; clip-backed walk, run, sneak, sit, kneel, lie, get up, fall, slip, jump, salute with feet locked; a missing clip stops the build with the exact download to ask for | `stagekit/aj_clips.py`, `config/mixamo_clips.json`, `tools/chars_aj/clips.py` |
| Casting | `clip.py casting` resolves each role to an existing character, an adapted one, or a MISSING requirement with the ask; character QA; Gate A sheets | `tools/casting.py`, `tools/chars_aj/{qa,gate_a_sheets}.py` |
| Wardrobe | Fitter with the pack's limits unchanged (a test compares them); 20 outfits and 7 add-ons, 111 accepted body fits; licences recorded per item; two independent review rounds with shot limits stored per fit | `tools/chars_aj/fit.py`, `library/wardrobe/` |
| Sets | Architecture, furniture (197 pieces) and dressing kits; a set audit; 18 worked sets including the office building in rain; set files can declare their own preview angles | `stagekit/{arch,furnish,dress,audit}.py`, `examples/sets/`, `tools/blender/set_preview.py` |
| Camera | Sampled-path move library (dolly, truck, pan, tilt, orbit, crane, follow, track_with, whip, through, rack focus and more), framing helpers, line of action, drift on holds, path checks, low-res motion previews; six shot-to-shot transitions in assembly | `stagekit/{camera,campath}.py`, `tools/blender/cam_preview.py`, `remotion/src/Transitions.tsx` |
| Gates | Gates A (characters), B (sets), C (camera) recorded in `approvals.json` with fingerprints; `stills`, `render`, `assemble` refuse to run without them; an unattended run records a bypass, never an approval | `tools/gates.py`, `clip.py gate` |
| Checks | Every check graded block or warn; `clip.py stills` exits 3 on blocking items; set audit and camera path merged into `checks.json`; motion strips for review; caption QA that ignores bright picture content | `stagekit/review.py`, `tools/blender/planlink.py`, `tools/qa.py` |
| Plan and instructions | Plan format 2 (structured sets, camera moves, transitions) with its validator; producer skill, agent prompts, style guide and character docs rewritten | `tools/plan_v2.py`, `.claude/`, `style/`, `docs/CHARACTERS_3D.md` |

Tests that pass: gates (25), plan schema (8), cast (20), fit limits (5), clips (4), caption QA (8), kit fixes (20, in Blender), plus set, camera and integration tests.

## The test film

Script "Two Seconds at the Office Door" (micro-butterfly example). Unattended: gates recorded as bypassed with your instruction as the reason. Real voice take, music and effects (about 2,700 ElevenLabs credits). Five sets, 21 cast including seven background extras.

**How it went.** No shot passed its first review, although every shot had zero blocking check items: the reviewer found the door-holding unreadable, the guard never turning the lock, the theft not shown, an empty "busy" office, and a security frame too small to read. One fix round per shot followed, then an independent final-film review (grade B), then a second fix round on five shots.

**First cut, measured against the reference bar** (independent review, `final/review.json`):

| Measure | References | First cut |
|---|---|---|
| Framings per minute | 22-33 | 20.7 |
| Camera moving | 60-80% of the time | about 82% |
| View changes that are camera events | more than half | about 17% |

Scores out of 10: story clarity 7, captions and in-world text 7, characters 6, sets 6, camera 6, transitions and continuity 6, lighting 6, technical 6, acting and motion 5.

**Better than the references:** enclosed places with readable in-world text, hero props shown large, a security frame planted and paid off twice, the noon office wide returning at night, light that follows story time.
**Not better:** rhythm (it feels cut together), acting (figures pose or react against the line), frame area lost to ceilings and counters, costume finish.

**Fixed after that review** (seen on the revised sample sheet; not independently re-graded): the office floor is full of people with heads down and the receptionist bowed over her phone; the investigator pulls the drawer and the guard holds the laptop; the zoomed security image shows Maya's hand on the door handle with the stranger's coffees clear of it; the dim room is dark; the lobby fly-through is no longer overexposed; the ending has no ceiling band and nobody looks into the lens.

## Remaining faults and gaps

**In the film**
- Rhythm and transitions were not addressed: still about 21 framings a minute and few camera-event joins.
- The receptionist's small greeting does not read; from the high camera the laptop's drop into the bag is less clear than in close-up.
- Costume finish: hollow sleeve cuffs, a lumpy cardigan, glasses floating off one face, shirt speckle under pipeline light, blazers that puff at the back.
- Sets: tower windows are flat peach panels, the company name does not read at night, no dusk sky is ever seen, the training room is plain.
- The film's office set creates every night monitor glow at one point (a bug in the clip's `set_office.py`); the door opens outward in sh01 and inward in sh02 and sh03.
- The two security images were staged for the still and show a slightly different moment from the shot.
- Length is 69.7 s against a 58-68 s target; the take was kept rather than re-recorded.

**In the pipeline**
- Wardrobe: no fit is unreservedly film-ready; royal and period outfits are rejected or not built (the throne-room story could not be the test); pirate, merchant, monk, plate armour and the one-piece dress are missing; the two BlenderKit villager fits were not attempted.
- Hands and contact: two-handed carrying and the card grip fall back to a plain hand shape; there is no self-contact guard (the pack's checker could not be vendored unchanged); `ride` fails its action test.
- Motion: fall and slip still scrape 3-7 cm; there is no jog clip; no lie-down clip exists on Mixamo under that name, so lying down is Getting Up played backward.
- Rendering: neither `clip.py render` nor `assemble` verifies frame files. Two jobs writing one clip produced 43 corrupt frames that only surfaced as a crash inside assembly; a lock per clip and a frame check are needed.
- Sets: the dim-room insert cannot meet the 60-object audit threshold; the private office, living room and home kitchen sit at 49-51; the tavern has one intersection; the battlefield passes the numbers but is not art-directed.
- Never run: `/gen-clip` itself with gates on (the test was orchestrated by hand through the same commands); `clip.py setup`.
- Old code left dormant: `tools/chars3d/`, `tools/chars/`, the flat-cast paths.

## Things only you can settle

- **Hair licence.** The 32 hair and beard models are Tripo3D output; the generator's plan terms are unconfirmed and every character carries a note.
- **Mixamo.** Uploading Aj replaced the stock character that was active in your Mixamo account.
- **Clip choices.** Laying (on back, idle) and Stumble Backwards stand in for "lying down" and "slipping"; Jump has no in-place option.
- **Gate changes made during the run.** Seven extras were added to the plan and shot-level set dressing was moved after the sets were previewed; in a normal run both would reopen a gate.

## How to look at it

- Film: `output/clips/two-seconds-at-the-office-door/final/` (full file, 720p copy, `samples/sheet.png`, `review.json`).
- Cast: `py -3 tools/clip.py cast`, sheets in `library/characters/aj/previews/`.
- Wardrobe coverage and reviews: `library/wardrobe/README.md`, `library/wardrobe/reports/REVIEW_2026-11-27.md`.
- Sets: `output/set_previews/<set>/sheet.png`.
- Health: `py -3 tools/clip.py doctor`.
