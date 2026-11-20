# Clay Shorts pipeline

Turns an idea into a finished, cinematic YouTube Short: script → shot plan → voice → sets, characters and camera in Blender → sound → assembled video. Run it with **`/gen-clip`**.

Every Short: 1080×1920, 24 fps, about 50 seconds (55 at most), simple English (A2–B2), a narrator over a clay-toy 3D world, **about 4–5 shots**. Story quality and viewer retention come first. The look must be polished: consistent light, soft fill, grounded shadows, controlled blur.

## How the work is split

| Stage | Who | Reads | Writes |
|---|---|---|---|
| Script | main session with a `script-*` skill | idea, format | `output/script-writer/<format>/<slug>.json` |
| Shot plan | `director` agent | script | `shotplan.json` |
| Voice, music, SFX | `sound-designer` agent + `tools/audio` | plan | `audio/plan.json`, `timing.json`, `audio/cues.json` |
| Missing assets | `asset-maker` agent | plan `assets` | `library/assets/**` |
| Sets, cast, light, camera | `shot-builder` agent (one per set) | plan, timing | `blender/set_<id>.py`, `blender/<shot>.py`, review stills |
| Review | `frame-reviewer` agent | stills, plan | `review/<shot>/verdict.json` |
| Render, assemble, QA | `tools/clip.py` (scripts, no agent) | everything | `render/`, `final/<slug>.mp4` |

One clip lives in `output/clips/<slug>/`. Agents hand work to each other through those files only.

## Commands

Use `python` on Windows and `python3` on macOS/Linux. All tools are standard library only.

```
python tools/clip.py doctor                 # what is installed and reachable
python tools/clip.py new --script <file>    # create the clip folder from a validated script
python tools/clip.py plan-check <clip>      # shot plan vs script and style numbers
python tools/clip.py voice <clip>           # narration take -> timing.json   (--mock without an API key)
python tools/clip.py sound <clip>           # music, ambience, SFX            (--mock without an API key)
python tools/clip.py stills <clip> [shot]   # build shot(s) in Blender, render review stills + measured checks
python tools/clip.py render <clip> [shot]   # final frames, resumable         (--quality draft --step 4 = animatic)
python tools/clip.py assemble <clip>        # Remotion + FFmpeg -> final MP4
python tools/clip.py qa <clip>              # measure the final file
python tools/clip.py sample <clip>          # frames from the final file for a last look
python tools/clip.py status <clip>          # which stages are done
python tools/clip.py assets find <words>    # search the asset library      (asset <script.py> builds and files one)
python tools/clip.py voices                 # check the voice shortlist on the ElevenLabs account
python -I scripts/validate_script.py --format <format> <script.json>
```

## Rules that hold everywhere

- **The voice take is the clock.** Shot lengths come from `timing.json`. In shot code, key actions to words with `shot.t("phrase")`, never to guessed seconds.
- **Style numbers live in `style/style.json`; reasons live in `style/STYLE_GUIDE.md`.** Render settings are locked there. Never change them per shot.
- **One light rig per set and time of day**, built in `blender/set_<id>.py` and reused by every shot in that set.
- **Assets: library first, then BlenderKit, then build.** Everything used is filed in `library/assets` with its source and licence.
- **Characters come from the pack** in `packs/release_1/` through `stagekit.cast`. Do not edit files inside the pack.
- **A skill or schema and its validator must agree.** If you change `tools/plan.py`, change the `shot-plan` skill in the same edit. Same for `scripts/validate_script.py` and the `script-*` skills.
- **Keep approved audio.** A voice take or sound is only generated again with `--retake`; every call costs credits and sounds different.
- **Generated media stays in `output/`** and is not committed. Script JSON and plans are.
- **One heavy job at a time on a small machine.** Blender renders and the Remotion assembly both want several GB of memory; do not run them together.
- Scripts measure what can be measured. Agents and the human judge purpose, mood and quality from images.

## Script formats

Seven writers live in `.claude/skills/script-*`. Each has fixed beats, timestamps and extra fields; see its `SKILL.md`. All use 115–132 words, sentences of 14 words or fewer, no contractions.

| Format | Shape | Voice (first choice) |
|---|---|---|
| `twist` | A puzzle with a psychological reveal | George |
| `slow-burn` | Someone looks dangerous; the last line flips it | George |
| `rule-of-three` | A challenge, two failures, a clever third try | George or Brian |
| `ticking-clock` | A countdown and a real, safe escape | Brian or Matilda |
| `reverse-chronology` | Starts at the end, rewinds to the cause | Archer |
| `unspoken-rules` | Three rules, one broken; the threat is never named | Lily or Christopher |
| `micro-butterfly` | One tiny mistake grows into a collapse | David Castlemore |

Voices and fallbacks are in `config/voices.json`.

## Layout

```
.claude/skills/      gen-clip (the command), script-* (7 writers), shot-plan, cinematic-style, stagekit, sound-design, asset-library
.claude/agents/      director, sound-designer, asset-maker, shot-builder, frame-reviewer
style/               STYLE_GUIDE.md (how we shoot), style.json (numbers scripts enforce)
config/voices.json   voice shortlist per format, models
tools/               clip.py (entry point), plan.py, assemble.py, qa.py, audio/, blender/stagekit/
remotion/            final assembly project (captions, mix)
packs/release_1/     the character pack (not in git; see README)
library/assets/      reusable asset library (index.json + .blend files)
examples/            a complete worked clip to learn from
output/              scripts and clips
```
