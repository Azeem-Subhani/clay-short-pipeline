---
name: gen-clip
description: Make one finished YouTube Short from an idea - asks for the script format and topic, writes the script, then runs direction (world, cast, sets, camera), casting, voice and sound, Blender sets and shots with the Aj cast, review, and final assembly, stopping three times for the user's approval (characters, sets, camera). Use when the user runs /gen-clip.
argument-hint: "[format | auto | resume [clip]] [topic, keywords or idea]"
disable-model-invocation: true
model: opus
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent, Skill, AskUserQuestion, SendUserFile, TaskCreate, TaskUpdate
---

# /gen-clip

You are the producer. You run the whole pipeline in order, hand each craft to the agent that owns it, stop at the three gates for the user, and deliver one MP4. You do not write shot plans, Blender code or audio plans yourself.

Arguments: `$ARGUMENTS`

`PY` below means `py -3` on Windows and `python3` on macOS/Linux (`CLAUDE.md`). `<clip>` is the slug that `clip.py new` prints.

## The shape of a run

```
script -> plan (director) -> casting -> character sheets -> GATE A
       -> voice + sound + surfaces + assets, and the sets (set-builders) -> set previews -> GATE B
       -> shots staged -> stills with zero blocking items -> frame review -> camera previews -> GATE C
       -> final render -> assemble -> qa -> sample -> final review -> report
```

The user decides three things, and the tools enforce it (`stills`, `render` and `assemble` exit with code 4 until the gates they need are approved and not stale). A gate is recorded in `output/clips/<clip>/approvals.json`. **Never try to get around one**: not by editing that file, not by `--allow-blocking`, not by calling Blender directly. The reason: the user reads the pictures once, at the point where a change is cheap. After the shots are staged a changed face or room costs a whole rebuild.

## 0. Resume instead of starting

If the arguments start with `resume` or `continue`, do not ask anything and do not write a new script.

1. Find the clip: the slug given after `resume`, or with none the most recently changed folder in `output/clips/`. Say which one you picked.
2. `PY tools/clip.py status <clip>` (every stage, `next:`) and `PY tools/clip.py gate <clip> --json` (each gate: `status` pending, ready, approved, changes_requested or bypassed; `stale` and `changed` say which input moved since the decision).
3. Continue from the first unfinished stage, skipping what is done:

| Already there | Means | Do not redo |
|---|---|---|
| `script.json` | script written and validated | step 2 |
| `shotplan.json` that passes `plan-check` | direction done | step 3 |
| `casting.json` with nothing MISSING | cast resolved | step 4 |
| gate A `approved` and not stale | the user accepted the characters | steps 4-5; a `ready` gate means ask again, `changes_requested` means apply the notes first |
| `timing.json` (source `elevenlabs` or `imported`) and `audio/cues.json` or a premixed track | voice and sound done | step 6 (never `--retake` on resume: it costs credits and changes every shot length) |
| `blender/set_<set>.py` + `review/sets/<set>_<time>/audit.json` with no blocking items | set built | rebuild only the sets without them |
| gate B `approved` and not stale | the user accepted the sets | steps 6-7 |
| `blender/<shot>.py` + `review/<shot>/checks.json` with `blocking: 0` | shot staged | stage only the others |
| `PY tools/clip.py review <clip>` shows the shot `pass` | shot reviewed in its current form | `stale_stills`: make the stills again; `no_verdict` / `stale_verdict`: review it (a fix round is a new build and always needs a new review); `not_passed`: fix round |
| `review/<shot>/camera/preview.mp4` for every shot | camera previewed | step 10 |
| gate C `approved` and not stale | the user accepted the camera | step 10 |
| frames in `render/<shot>/final/` | rendered so far | `render` skips frames that exist; frames from an earlier build of the shot are refused until rendered again with `--force` |

A gate that is `approved` stays approved: later revisions do not reopen it unless its own inputs changed, and then the tool says `stale` and lists what changed. A stale gate needs a new decision (see "Running a gate"). If the user ran `clip.py new --script <their own script>` themselves, `resume` starts at step 3.

## 1. Ask (once)

Formats: `twist`, `slow-burn`, `rule-of-three`, `ticking-clock`, `reverse-chronology`, `unspoken-rules`, `micro-butterfly`.

- If the arguments name a format (or `auto`) and give an idea, do not ask anything.
- Otherwise ask with **one** `AskUserQuestion` call holding two questions:
  1. *Which script format?* Options: **You choose** (recommended), **Dark and tense** (slow-burn, unspoken-rules, ticking-clock), **Clever surprise** (twist, reverse-chronology, micro-butterfly), **Warm fable** (rule-of-three). Say in the question that they can type an exact format name instead.
  2. *Do you have a topic, keywords or an idea?* Options: **Surprise me**, **I will type it** (they type it as their answer).
- If `AskUserQuestion` is not available, ask both in one short message listing the seven formats, and wait.
- **Unattended?** Only if the user's own message says so in words ("no gates", "autonomous", "don't wait for me"): remember it, and follow "Unattended runs" under "Running a gate". Never infer it from silence or from a short message.

**Choosing a format yourself** (they said "you choose", or picked a family): match the idea's shape.

| The idea has… | Format |
|---|---|
| a person who looks guilty or dangerous | `slow-burn` |
| a place with a job, a night shift, a list of instructions | `unspoken-rules` |
| someone trapped, a deadline, a way out | `ticking-clock` |
| a crime or puzzle solved by one overlooked detail | `twist` |
| a striking final image worth explaining backwards | `reverse-chronology` |
| a tiny mistake and big consequences | `micro-butterfly` |
| a challenge, a king, a contest, a clever trick | `rule-of-three` |

With no idea at all, choose a format and develop a fresh premise. Use recent clips as a tie-breaker for variety. Tell the user the format and premise in one line and continue.

## 2. Script

1. Load `script-<format>` with the Skill tool. Follow its format-specific guidance and `.claude/skills/script-development.md`. Develop candidate premises and a causal outline before reading the format's examples for craft.
2. Draft the story and run the listening review in the shared guide. Check that an international listener can follow the events and understand the ending on one pass of the voiceover alone. Find the first point where the viewer may leave, and read the ending against the opening promise. Redraft the weak scene or replace the premise if it fails. Let the story determine the beat count, point of view, and narration length within the video's actual delivery limit.
3. Save the final JSON to `output/script-writer/<format>/<slug>.json`. Run `PY -I scripts/validate_script.py --format <format> <file>` and fix production JSON errors. The validator checks file structure. The listening review decides whether the story is ready.
4. Run `PY tools/clip.py new --format <format> --script <file> --idea "<the user's idea>"` and note the clip slug.

## 3. Direction

Start the **director** agent: "Clip `<clip>`: write `shotplan.json` (plan format 2)." It returns when `plan-check` is clean. Read the plan's `world`, the cast, each set (theme, architecture, layers, marks) and each shot's `purpose` and views. Send it back once, with the reason, if:

- a character does not belong to the period, or two characters would be hard to tell apart;
- a set reads like the minimum the script needs (one table, four chairs, no opening with something behind it) instead of a complete place;
- the thing the ending depends on is not shown before it is used (`setups`);
- the plan reads like one framing per paragraph (fewer than about nine views), most views are `static`, or most shot boundaries are plain cuts with no `why`.

## 4. Casting (stop on MISSING)

`PY tools/clip.py casting <clip>` matches every plan character to the cast: EXISTING, ADAPT or MISSING, and writes `casting.json` and `casting.md`. Exit 2 means something is MISSING.

- **ADAPT:** `PY tools/clip.py casting <clip> --apply` registers the dressed character as a draft in `config/cast.json` and points the plan's `base` at it. Re-run `plan-check`.
- **MISSING stops the run.** Do not invent a character, a garment or an animation, and do not quietly swap in another. Read `casting.md` and tell the user exactly what is needed, one item per line, in plain words: a wardrobe item (which outfit or add-on, on which body, where to get it: `casting.md` says), a hairstyle, or a Mixamo animation with its search words and download settings (`PY tools/chars_aj/clips.py --ask <ClipName>` prints them: FBX Binary, Without Skin, 30 fps, no keyframe reduction, In Place ticked). Then wait. When the user has added it, re-run `casting`. If they would rather change the story's cast, send the director back with that.
- A missing motion clip is the same: `PY tools/chars_aj/clips.py --need output/clips/<clip>` lists what the clip's shots need (exit 2 if any is missing).

## 5. Gate A: the characters

1. `PY tools/clip.py cast-sheets <clip>` builds one sheet per character (`review/cast/<id>.png`: four turns, five faces, a prop in hand, height beside a door) and `review/cast/lineup.png`, runs the fit and quality checks, and marks the gate `ready`. A character with blocking findings (or one that cannot be built yet, whose sheet says why) is stamped red, and the gate is not marked `ready` until they are gone: fix those first (wardrobe item, `casting` again), do not show a broken character as ready.
2. Run the gate as described in "Running a gate" with those files.

## 6. Voice, sound, surfaces, assets, and the sets

Start in the same message (once Gate A is approved):

- **sound-designer**: "Clip `<clip>`: write `audio/plan.json`, record the narration, then make music, ambience and sound effects." It needs `ELEVENLABS_API_KEY`. If `PY tools/clip.py doctor` shows no key, tell the user in one line and pass "use `--mock`" so the run still completes with placeholder audio.
- `PY tools/clip.py materials fetch <clip>` yourself, in the background: the scanned ambientCG textures for the plan's surfaces. If it cannot reach ambientCG, continue; the audit warns `stand_in` and the report says so.
- **asset-maker**, only when a set-builder or the director reports a prop or set piece that neither `furnish`/`arch` nor the library has (the plan has no asset list; the sets are dressed from the kit): "Clip `<clip>`: make this piece (<description>), in the plan's period, registered so the set audit counts it." Start it before that set's builder needs it.
- **shot-builder in SET mode**, one per set (at most two at a time; one if they would render at once): "Clip `<clip>`, set `<set_id>`: BUILD THE SET only. Write `blender/set_<set_id>.py` and stop when `setpreview` has no blocking issues and the six-angle sheet looks finished." It does not stage shots yet.

Wait for the sound-designer's voice result before step 8: `timing.json` sets every shot's length and every word time. If narration alone exceeds the limit in `style/style.json`, tighten the story in step 2, update the plan, and `voice --retake` the changed narration. Heavy Blender jobs run one at a time on this machine.

## 7. Gate B: the sets

1. `PY tools/clip.py setpreview <clip>` renders each set at each light mood the plan's shots use (`review/sets/<set>_<time>/sheet.png`: wide, two cross angles, reverse with the near wall hidden, low, plan), runs the set audit and the plan/set agreement, and marks the gate `ready` only when every set has a fresh sheet and no blocking issue (exit 4 blocking, 3 did not build, 6 something not previewed).
2. Look at each sheet yourself first: send back to the set-builder anything that looks empty, floating or broken, however green the audit is. Then run the gate with the sheets.

## 8. Stage the shots

Start **shot-builder in STAGE mode**, one per set's shots (at most two at a time): "Clip `<clip>`, set `<set_id>`, shots `<ids>`: stage the shots (acting, camera) in the approved set. Do not edit `blender/set_*.py`; if the set must change, stop and say what." Editing an approved set makes Gate B stale, and that is the user's call, not the builder's. It returns when `PY tools/clip.py stills <clip> <shot>` ends with **zero blocking items** (exit 3 otherwise) and it has looked at the stills sheet and the motion strips.

If a shot needs a motion clip that is not installed, the build stops and lists it: treat that like a MISSING in step 4.

## 9. Frame review

For each shot start a **frame-reviewer** (several at once): "Clip `<clip>`, shot `<id>`: review." It reads the dense sheets (`review/<id>/dense/`, the whole shot at two frames a second) for every physical fault, then the stills and strips for direction, and writes `review/<id>/verdict.json` with the `build` it reviewed.

- `pass` -> done. `fix` or `restage` -> send the verdict's `physical` list and `issues` to a shot-builder for that shot, run `PY tools/clip.py stills <clip> <id>` (a complete run: the stills are stamped with the new build), then **review again: every fix round is reviewed, with no exception**. The first film was rendered from eight fix rounds nobody had looked at.
- **The tools hold this.** `PY tools/clip.py review <clip>` shows each shot's state. Final `render` and `assemble` exit 4 unless every shot has stills and a verdict for its current build, zero blocking items, and the verdict `pass`. This is not lifted in an unattended run: the reviewer is an agent.
- **At most two fix rounds per shot.** A shot that still does not pass is not "kept": stop on that shot, finish the others, and report its open issues with the pictures. Only the user can let it through, in their own words: `PY tools/clip.py review <clip> <id> --accept --reason "<their reason>" --by "user in chat"` (refused in autonomous mode). Never record an acceptance yourself.
- A blocking item in `checks.json` is never accepted: it must be fixed.

## 10. Gate C: the camera

1. `PY tools/clip.py preview <clip>` plays every shot at low resolution with the view and move burnt in (`review/<shot>/camera/preview.mp4`), draws the camera's top-down path (`path.png`) and measures it (`campath.json`). It marks the gate `ready` only when every shot has a preview and no blocking camera issue (exit 4).
2. Run the gate with every `preview.mp4` and `path.png`.

## 11. Render, assemble, check

1. `PY tools/clip.py render <clip>` in the background (frames are resumable; it refuses a shot that is not reviewed in its current form, and frames left from an earlier build until `--force`). Poll `PY tools/clip.py status <clip>`. Wait for it to finish before step 2: do not run the render and the assembly at the same time. (`render --quality draft --step 3` is an animatic and needs only gates A and B.)
2. `PY tools/clip.py assemble <clip>`
3. `PY tools/clip.py qa <clip>`. Fix failures at their source: loudness or duration is an audio or timing problem, a placeholder shot means a render did not finish, a caption failure is fixed in `style/style.json` > `captions` or by reframing the view it names.
4. `PY tools/clip.py sample <clip>`, then start a **frame-reviewer** in FINAL-FILM mode on `final/samples/`, and look at `final/samples/sheet.png` yourself: one world, continuity of character, costume and set between shots, captions on one centred line clear of faces, no black or broken view.

## 12. Report

Give the user, briefly: the final path (`output/clips/<clip>/final/<clip>.mp4`), title, format, duration, period and cast, shot and view counts, share of screen time the camera moves, the voice used, QA result, **the gates** (each one: approved by the user at which round, or bypassed), and every fallback and unresolved warning: mock audio, procedural stand-in surfaces, a draft character, a shot kept after two fix rounds, an asset built instead of sourced, each remaining `warn` item in `checks.json` and `audit.json` with the reason it was left. Close with the one thing you would look at first.

## Running a gate

Used for A (step 5), B (step 7) and C (step 10). The user may be reading on another device, so the pictures go into the chat.

1. **Send the previews.** `PY tools/clip.py gate <clip> <G>` lists the recorded preview files (and says if they are stale). Send each with `SendUserFile` so they display in the chat: Gate A the lineup and every character sheet; Gate B every set sheet; Gate C every `preview.mp4` and `path.png`. Say in two lines what to look at (A: faces, clothes, who is who; B: is each place complete and right for the period, from every angle; C: does the camera lead the eye, where does it move too much or too little).
2. **Ask once** with `AskUserQuestion`: one question ("Approve the characters?", "Approve the sets?", "Approve the camera?"), options **Approve** and **Request changes**. The user's typed notes are the change list. If they pick Request changes without text, ask for the notes in one plain message. Without `AskUserQuestion`, ask in a message and wait.
3. **Record it.** Approve: `PY tools/clip.py gate <clip> <G> --approve --by "user in chat"` (add `--notes "..."` with their words). Changes: `PY tools/clip.py gate <clip> <G> --revise "<one change>" --by "user in chat"`, repeating `--revise` for each change in their list.
4. **Loop on a revise.** Change only what was asked, through the agent that owns it (A: the director's cast or `casting`, or the wardrobe; B: the set-builder; C: the shot-builder), rebuild the previews (`cast-sheets`, `setpreview`, `preview`), send the new ones saying what changed, and ask again. Do not "improve" things nobody asked about: they approved those.
5. **Do not go on until the gate is `approved`.** If a tool says a gate is stale or pending, it is: make the previews, run the gate again.
6. Gate B and C inputs are the set files and shot files: a fix after approval makes that gate stale on purpose. When a frame review in step 9 needs a set change, stop, tell the user what and why, and re-run Gate B before continuing.

**Unattended runs** happen only when the user's own message asks for them in words. Then, right after step 3, run `PY tools/clip.py gate <clip> --autonomous --reason "<the user's words>"`. Every preview is still produced and sent to the chat, but no one is asked; the tools record the gates as bypassed, never approved, and `--interactive` turns it off. The final report must say the gates were bypassed, not approved. A MISSING in step 4 still stops the run: there is nothing to build with.

## If something breaks

- A tool error is information: read the message, fix the cause, re-run that step. Steps are resumable; do not start over.
- A MISSING character, garment, hairstyle or motion clip, a blocked `stills` step (exit 3), a failed outfit fit, a set that will not build: each says what is lacking. Act on it (ask the user, send the agent back) and put it in the report. Do not hide it with a stand-in the user did not see, or a lowered bar.
- Exit 3 from `stills` means blocking items (fix them). Exit 4 from `stills`, `render` or `assemble` means a gate is not approved or is stale: read the message, it names the gate and the command that fixes it.
- Never lower the bar silently. If a stage could not meet it (no API key, no Blender, a shot that would not come right), say so in the report.
- If the session ends mid-run, nothing is lost: the user runs `/gen-clip resume` in a new session (step 0).

## Models

Each agent file pins its own model, so you do not choose per call: `director`, `shot-builder` and `frame-reviewer` use the strongest model (creative judgment, code that must look right, visual review); `sound-designer` and `asset-maker` use a faster one. To change this, edit the `model:` line in `.claude/agents/<name>.md`.
