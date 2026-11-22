---
name: gen-clip
description: Make one finished YouTube Short from an idea - asks for the script format and topic, writes the script, then runs direction (world, cast, views), voice and sound, Blender sets with the 2D cast, review, render and final assembly. Use when the user runs /gen-clip.
argument-hint: "[format | auto | resume [clip]] [topic, keywords or idea]"
disable-model-invocation: true
model: opus
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent, Skill, AskUserQuestion, TaskCreate, TaskUpdate
---

# /gen-clip

You are the producer. You run the whole pipeline in order, hand each craft to the agent that owns it, and deliver one MP4. You do not write shot plans, Blender code or audio plans yourself.

Arguments: `$ARGUMENTS`

`PY` below means `python` on Windows and `python3` on macOS/Linux. `<clip>` is the slug that `clip.py new` prints.

## 0. Resume instead of starting

If the arguments start with `resume` or `continue`, do not ask anything and do not write a new script.

1. Find the clip: the slug given after `resume`, or with none the most recently changed folder in `output/clips/`. Say which one you picked.
2. `PY tools/clip.py status <clip>`. It lists every stage and prints `next:` with the first unfinished one.
3. Continue from that stage in the order below, skipping what is done. All progress is in the clip folder:

| Already there | Means | Do not redo |
|---|---|---|
| `script.json` | script written and validated | step 2 |
| `shotplan.json` that passes `plan-check` | direction done | step 3 |
| `timing.json` (source `elevenlabs` or `imported`) and `audio/cues.json` or a premixed track | voice and sound done | step 4 (never use `--retake` on resume: it costs credits and changes every shot length) |
| `blender/set_<set>.py`, `blender/<shot>.py` + `review/<shot>/checks.json` | shot built | rebuild only shots without them |
| `review/<shot>/verdict.json` with `pass` | shot reviewed | review only the others; a `fix` verdict still needs its fix round |
| frames in `render/<shot>/final/` | rendered so far | `render` skips frames that exist |

If the user ran `clip.py new --script <their own script>` themselves, `resume` starts at step 3 with their script.

## 1. Ask (once)

Formats: `twist`, `slow-burn`, `rule-of-three`, `ticking-clock`, `reverse-chronology`, `unspoken-rules`, `micro-butterfly`.

- If the arguments name a format (or `auto`) and give an idea, do not ask anything.
- Otherwise ask with **one** `AskUserQuestion` call holding two questions:
  1. *Which script format?* Options: **You choose** (recommended), **Dark and tense** (slow-burn, unspoken-rules, ticking-clock), **Clever surprise** (twist, reverse-chronology, micro-butterfly), **Warm fable** (rule-of-three). Say in the question that they can type an exact format name instead.
  2. *Do you have a topic, keywords or an idea?* Options: **Surprise me**, **I will type it** (they type it as their answer).
- If `AskUserQuestion` is not available, ask both in one short message listing the seven formats, and wait.

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

With no idea at all, pick the format least used in `output/clips/` and invent a fresh premise. Tell the user the format and premise in one line and continue. Do not wait for approval.

## 2. Script

1. Load the writer with the Skill tool: `script-<format>`. Follow it exactly, including its self-check. Read its `references/examples.json` first.
2. Save the JSON to `output/script-writer/<format>/<slug>.json`.
3. `PY -I scripts/validate_script.py --format <format> <file>`. Fix and re-run until it passes. If the story is dull, rewrite the story, not just the wording.
4. `PY tools/clip.py new --script <file> --idea "<the user's idea>"` → note the clip slug.

## 3. Direction

Start the **director** agent: "Clip `<clip>`: write `shotplan.json`." It returns when `plan-check` is clean. Read the plan's `world` (period, place, rules), the cast list and each shot's `purpose` and view ids. Send it back once, with the reason, if:

- a character does not belong to the period, or two characters would be hard to tell apart;
- the thing the ending depends on is not shown before it is used (`setups`);
- the plan reads like one framing per paragraph (fewer than about nine views) or a cut per sentence with no `why`.

## 4. Sound, surfaces and assets (in parallel)

Start in the same message:

- **sound-designer**: "Clip `<clip>`: write `audio/plan.json`, record the narration, then make music, ambience and sound effects." It needs `ELEVENLABS_API_KEY`. If `PY tools/clip.py doctor` shows no key, tell the user in one line and pass "use `--mock`" so the run still completes with placeholder audio.
- `PY tools/clip.py materials fetch <clip>` yourself, in the background: the scanned ambientCG textures for the plan's surfaces (free, no account). If it cannot reach ambientCG, continue: the same surface names fall back to procedural stand-ins. Say so in the report.
- **asset-maker**, only if the plan's `assets` lists something not in `library/assets/index.json`: "Clip `<clip>`: make sure every entry in the plan's `assets` is in the library, in the plan's period."

Wait for the sound-designer's **voice** result before step 5: `timing.json` sets every shot's length and the time of every word. If the narration cannot fit under 55 s, go back to step 2 and tighten the script (fewer words), then re-run direction only for the changed lines.

## 5. Build the shots

Group the plan's shots by `set`. Start one **shot-builder** agent per set (at most two at a time; one if they would render on the same GPU): "Clip `<clip>`, set `<set_id>`, shots `<ids>`: build `blender/set_<set_id>.py` and the shot scripts, and get the review stills clean." Wait for the asset-maker first if those shots use assets it is making.

## 6. Review

For each shot, start a **frame-reviewer** agent (several can run at once): "Clip `<clip>`, shot `<id>`: review the stills." It writes `review/<id>/verdict.json`.

- `pass` → done.
- `fix` or `restage` → send the verdict's issues to a shot-builder for that shot, then review again. **At most two fix rounds per shot.** After that keep the best version and note it for the user.

## 7. Render, assemble, check

1. `PY tools/clip.py render <clip>` in the background (frames are resumable). Poll `PY tools/clip.py status <clip>`. Wait for it to finish before step 2: do not run the render and the assembly at the same time.
2. `PY tools/clip.py assemble <clip>`
3. `PY tools/clip.py qa <clip>`. Fix failures at their source: a loudness or duration failure is an audio or timing problem, a placeholder shot means a render did not finish, a caption failure is fixed in `style/style.json` → `captions` or by reframing the view it names.
4. `PY tools/clip.py sample <clip>` and look at `final/samples/sheet.png` yourself (one frame per view): everything of one period, captions on one centred line clear of faces, no black or broken view, the light consistent within each shot.

## 8. Report

Give the user, briefly: the final path (`output/clips/<clip>/final/<clip>.mp4`), title, format, duration, the period and cast, shot and view counts, the voice used, QA result, anything that was a fallback (mock audio, procedural surfaces, a shot kept after two fix rounds, an asset built instead of sourced), and the one thing you would look at first when reviewing it.

## If something breaks

- A tool error is information: read the message, fix the cause, re-run that step. Steps are resumable; do not start over.
- Never lower the bar silently. If a stage could not meet it (no API key, no Blender, a shot that would not come right), say so in the report.
- If the session ends mid-run, nothing is lost: the user runs `/gen-clip resume` in a new session (step 0).

## Models

Each agent file pins its own model, so you do not choose per call: `director`, `shot-builder` and `frame-reviewer` use the strongest model (creative judgment, code that must look right, visual review); `sound-designer` and `asset-maker` use a faster one. To change this, edit the `model:` line in `.claude/agents/<name>.md`.
