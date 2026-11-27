# Shorts pipeline (3D cast, 3D world)

A Claude Code project that turns a short script into a finished YouTube Short: a narrator over simple round 3D cartoon characters (the "Aj" cast: real figures on a Mixamo skeleton with drawn faces) staged in a complete 3D world, 1080×1920, about 60–65 seconds, with captions.

Run **`/gen-clip`** in Claude Code. It asks for a script format and an idea, writes the script, plans the world, cast, shots and camera views, casts the characters from the registry, records the voice, builds the sets and stages the characters in Blender, reviews the frames, renders, and assembles the final MP4 with music, sound effects and captions. It stops three times for your approval from pictures: **Gate A** characters and wardrobe, **Gate B** sets, **Gate C** camera (`python tools/clip.py gate <clip>` shows where they stand).

| Stage | Tool |
|---|---|
| Script | seven `script-*` skills |
| Characters | the Aj character pack (`packs/aj_rebuild_v1`, Blender 5.3): 8 bodies, a fit-checked wardrobe, Mixamo clips; see [`docs/CHARACTERS_3D.md`](docs/CHARACTERS_3D.md) |
| Sets, staging, light, render | Blender 5.3 + EEVEE, driven headless by `tools/blender/stagekit` |
| Surfaces | ambientCG scanned textures by name (free, CC0), with procedural stand-ins |
| Props and set pieces | the built-in kit → project library → BlenderKit (your Full plan) → built in Blender |
| Voice, music, sound effects | ElevenLabs API |
| Assembly, mix, captions | Remotion 4 + FFmpeg |

How the look and the rules were derived from the two reference Shorts: [`docs/REFERENCE_BREAKDOWN.md`](docs/REFERENCE_BREAKDOWN.md). What was wrong with the first version and why: [`docs/DIAGNOSIS.md`](docs/DIAGNOSIS.md). Where the project stands and what is unverified: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Setup

You need: **Claude Code**, **Blender 5.3**, **Python 3.10+**, **Node.js 20+**, **FFmpeg**, an **ElevenLabs API key**, and the **BlenderKit add-on** logged in inside Blender (only used when a story needs a prop the kit and library do not have).

1. **Unzip the project** anywhere, for example `D:\clay-shorts`.
2. **Put the character pack in place.** Copy **`Character_Rebuild_Video_Pipeline.zip`** to the project folder and run `python tools/chars_aj/install_pack.py` (it unpacks to `packs/aj_rebuild_v1/` and verifies every file; `--check` verifies only). The pack is never committed. The hair library and the 22 Mixamo clips are not in git either: see "Installing the pack on a new machine" in [`docs/CHARACTERS_3D.md`](docs/CHARACTERS_3D.md).
3. **Run setup** from the project folder (`python3` on macOS and Linux):

   ```
   python tools/clip.py setup
   ```

   It creates `.env` from `.env.example` and installs the Remotion packages. Its "character pack" line still looks for the old 2D zip and can be ignored: the Aj pack is checked by `install_pack.py --check` and `python tools/clip.py clips --check`.
4. **Add your keys to `.env`:**

   ```
   ELEVENLABS_API_KEY=sk_...
   BLENDER_BIN=C:\Program Files\Blender Foundation\Blender 5.3\blender.exe
   ```

   `BLENDER_BIN` is only needed if `blender` is not on your PATH and not in the default install folder.
5. **Download the surfaces** (once; about 150 MB for the whole catalog, or pass a clip name to fetch only what that clip uses):

   ```
   python tools/clip.py materials fetch
   ```

   Without this step everything still works, with plainer procedural stone, wood and grass.
6. **Check the voices on your account:** `python tools/clip.py voices` (see [Voices](#voices); once).
7. **Check everything:** `python tools/clip.py doctor`

## Run it

Open the project folder in Claude Code and type:

```
/gen-clip
/gen-clip rule-of-three a king, a locked tower, and a baker
/gen-clip resume the-ring-in-the-pond
```

What happens, in order:

1. **Script.** The matching `script-*` skill develops and reviews the story with the [shared writing guide](.claude/skills/script-development.md). `scripts/validate_script.py` checks that the final JSON is usable by production.
2. **Direction and casting.** The `director` agent writes `shotplan.json`: the story's world and period, the cast with costumes, each set as a complete place and where people stand, the shots, and the camera views inside each shot with the narrator's words they start on. `plan-check` refuses characters, costume pieces and surfaces from the wrong period, and endings whose mechanism was never shown. `python tools/clip.py casting <clip>` then matches every role to the cast (EXISTING, ADAPT or MISSING; a MISSING stops the run with an exact ask), and you approve the character sheets (Gate A).
3. **Voice and sound.** The `sound-designer` agent records the narration (this sets every shot's length and every word's time), then makes music, ambience and effects. Surfaces are fetched in parallel. Sets are built and previewed for your approval (Gate B).
4. **Shots.** One `shot-builder` agent per set stages its shots: the cast on their marks, named actions and Mixamo clips, faces, hands and props keyed to the words, and the camera moves. It renders two review stills per view and motion strips and fixes what the measured checks (which block on a real fault) and the images show. You approve the camera from low-resolution previews (Gate C).
5. **Review.** A `frame-reviewer` agent judges each shot's stills against the plan: one world, purpose, performance, cause and effect, captions. At most two fix rounds per shot.
6. **Render, assemble, QA.** Blender renders the frames, Remotion adds the mix and the captions, FFmpeg normalises loudness, and `qa` measures the file, including where the captions sit and whether they are on time.

**Closing the session does not lose anything.** Every stage writes into `output/clips/<slug>/`. `/gen-clip resume` (or `resume <clip>`) runs `python tools/clip.py status <clip>`, finds the first unfinished stage and continues. The paid voice take is kept and frames that exist are not rendered again.

### Worked clips

`output/clips/two-seconds-at-the-office-door/` is the first film made with the Aj cast and the rebuilt kit (plan format 2, casting, five sets, eight shots): read its `shotplan.json`, `casting.md`, `blender/set_*.py` and `blender/sh0N.py` as the current example of how a film is written. `examples/the-ring-in-the-pond/` is an older clip made with the retired flat 2D cast: it shows the file layout, but its characters no longer exist and it cannot be rendered again. `examples/sets/` has worked sets.

### Expected outputs

```
output/script-writer/<format>/<slug>.json        the script
output/clips/<slug>/
  script.json  state.json  shotplan.json  timing.json
  audio/     plan.json  narration.wav  music.wav  sfx/*.wav  amb/*.wav  cues.json
  blender/   set_<id>.py  sh01.py …             the set and shot code (re-runnable)
  casting.json  casting.md  approvals.json     who plays whom; the three gates
  review/    cast/  sets/  sh01/sheet.png  checks.json  verdict.json  camera/
  render/    sh01/final/0001.png …
  final/     <slug>.mp4                         ← the Short: 1080×1920, 24 fps, H.264 + AAC 48 kHz, −14 LUFS
             <slug>.captions.json               every caption with its words and frames
             <slug>.qa.json                     measured facts and any warnings
library/                                         new surfaces and reusable assets, with source and licence
```

A complete worked clip: see "Worked clips" above.

### Doing steps by hand

```
python tools/clip.py cast --era medieval                    # who exists, and which outfits fit which body, for a period
python tools/clip.py stills <clip> sh03                     # rebuild one shot and look at review/sh03/sheet.png
python tools/clip.py stills <clip> sh03 --views through_the_net --quality preview
python tools/clip.py render <clip> --quality draft --step 3 # a fast animatic of the whole film ...
python tools/clip.py assemble <clip> --tag animatic         # ... with sound and captions, to judge timing and motion
python tools/clip.py voice <clip> --retake                  # a new narration take (costs credits; shot lengths change)
python tools/clip.py voice <clip> --from-media film.mp4     # reuse a recording instead: word times by offline speech recognition (once: voice <clip> --asr-setup)
python tools/clip.py render <clip> sh03 --force             # re-render one shot after a change
```

No API key yet? `voice --mock` and `sound --mock` produce placeholder audio with believable timing, so the whole pipeline can be tried offline.

## Captions

Captions are built from the same word times that drive the pictures (`tools/captions.py`): one to three words at a time, small words joined to the word they lead into, centred on the frame on one fixed line, never wrapped, shown 0.08 s ahead of the word. The numbers are in `style/style.json` → `captions`. `python tools/clip.py qa <clip>` reads the finished file back: it measures the caption block on real frames (centre, line, safe area) and compares caption times with the pauses in the narration; `--listen` also checks them against recognised speech (a free offline speech model, downloaded once with `python tools/clip.py voice <clip> --asr-setup`).

## Voices

All seven video categories are standardized on one voice profile in `config/voices.json`:

- **Voice profile:** **Alex — Upbeat, Energetic and Clear** (upbeat, energetic, clear, conversational, expressive, confident, engaging, natural, fast-paced without losing intelligibility).
- **Narration speed:** Alex's natural pace, about **177 words per minute (WPM)** (accepted range 165–190). Scripts of 170–198 words run about 58–68 seconds, 70 at most. The voice is never sped up.
- **Account setup:** `"Alex"` is an ElevenLabs Voice Library voice (`"search": "Alex - Upbeat, Energetic and Clear"`). Run `python tools/clip.py voices` once to resolve Alex's `voice_id` from *My Voices* into `config/voices.local.json` (or follow the printed `--add "Alex=<voice id>"` / `--pick "Alex=<voice id>"` command if Alex is not yet in *My Voices*).

The narration model is **Eleven v4** (`eleven_v4`), falling back to `eleven_v3`, then `eleven_multilingual_v2`. On v4/v3, delivery and brisk pacing are directed with contextual emotion and delivery tags (`[energetic]`, `[upbeat]`, `[amused]`, `[confused]`, `[knowing]`, `[deadpan]`, `[serious]`, `[fast-paced]`, `[dramatic]`, `[suspicious]`, `[excited]`, `[amazed]`, `[ironic]`, `[dismissive]`, `[laughs]`; see `.claude/skills/sound-design/SKILL.md`), with `stability: 0.45` and `similarity_boost: 0.75`. On v2 fallback models, tags are stripped automatically and `speed` stays at 1.0 so the pace matches. Sound effects use `eleven_text_to_sound_v3`, music `music_v2_5`.

To test a voice change on any clip, run `python tools/clip.py voice <clip> --retake`.

Music rights depend on your ElevenLabs plan (see the Music Commercial Rights table in the Eleven Music terms). For monetised uploads, check your plan, or set `"enabled": false` under `music` in a clip's `audio/plan.json` and add licensed music later.

## Changing the look

- **`style/STYLE_GUIDE.md`**: how stories are staged, shot, lit, acted and reviewed. Agents read it; edit it to change taste.
- **`style/style.json`**: numbers that scripts enforce: view counts and lengths, safe area, render quality, loudness, caption style.
- **`config/cast.json`**: the cast registry (bodies and the starter characters with their periods and limits); **`library/wardrobe/index.json`**: every outfit and add-on with its licence and fit per body; **`config/aj_face.json`**: expressions and mouth cells; **`config/mixamo_clips.json`**: the motion clips.
- **`library/materials/catalog.json`**: the named surfaces, their periods and the ambientCG scans behind them.
- **`tools/blender/stagekit/lights.py`**: the light moods (`MOODS`). Tune a mood once and every set that uses it follows.
- **`tools/blender/stagekit/actions.py`** and **`cast_aj.py`**: the named actions and poses of the Aj actor (`python tools/clip.py actions`; `docs/poses.png` shows the poses).
- **`.claude/agents/*.md`**: each agent's role and model (`model: opus | sonnet | haiku | fable | inherit`).

## Project map

```
.claude/skills/gen-clip/         the /gen-clip command (the producer)
.claude/skills/script-*/         the seven script writers and their reference examples
.claude/skills/script-development.md  shared story development, listening review, and JSON format
.claude/skills/shot-plan/        shot plan format: world, cast, sets, shots, views, setups
.claude/skills/cinematic-style/  the style guide as a decision card
.claude/skills/stagekit/         how to build a set and stage a shot in Blender (API cheat sheet)
.claude/skills/sound-design/     voice direction, music, effects (ElevenLabs)
.claude/skills/asset-library/    surfaces, kit, library, BlenderKit, build
.claude/skills/character-maker/  a person, garment or clip the cast lacks
.claude/agents/                  director, sound-designer, asset-maker, shot-builder, frame-reviewer
tools/clip.py                    every mechanical step
tools/plan.py, plan_v2.py        the shot-plan validator (period, cast, surfaces, sets, views, setups, narration)
tools/casting.py, cast_data.py   casting a plan against the cast registry and the wardrobe
tools/chars_aj/                  Aj characters: pack install, wardrobe fitting, clips registry, character QA and sheets
tools/gates.py                   the three approval gates
tools/captions.py                caption grouping and timing
tools/materials.py               ambientCG search and download
tools/blender/stagekit/          cast_aj and aj_* (the Aj actor), actions, arch, furnish, dress (sets), mat (surfaces), lights, camera and campath, fx, audit, review
tools/blender/run_shot.py        builds one shot in Blender: stills or frames
tools/audio/                     ElevenLabs client, narration + timing, music and effects, align.py (speech recognition for checks and imports)
tools/assemble.py, tools/qa.py   Remotion + FFmpeg assembly, delivery and caption checks
remotion/                        the assembly composition (shots, mix, captions, finish)
style/, config/                  style guide, style numbers, cast and wardrobe, voices
library/                         materials/catalog.json, assets/ (props and set pieces), wardrobe/ (outfits, fits, licences), characters/aj/ (bodies, hair, clips)
packs/                           where the Aj character pack goes (not shipped)
examples/                        worked sets, an older worked clip, an example asset script
docs/                            reference breakdown, diagnosis, handoff, pose sheet, earlier research
```

## Notes and limits

- **Blender version.** The Aj pack is built for Blender 5.3; so is this project. Render each Short on one machine: EEVEE can differ slightly between GPUs.
- **Windows.** EEVEE needs the GPU: render while logged in. Headless `blender -b` works for everything here.
- **Memory.** `render` restarts Blender every 120 frames (`--chunk`, or `RENDER_CHUNK` in `.env`). If Blender is stopped part-way (a crash, or the system ending it for using too much memory), `render` carries on by itself in smaller chunks and tells you the size that worked; nothing already rendered is redone. In the build sandbox (software rendering, 6 GB) memory grew with every frame that had characters in it, so chunks of 6 were needed there; a GPU machine may not show this at all. Do not run a render and `assemble` at the same time on a machine with little RAM.
- **What the characters can do.** Real 3D figures: any camera angle including from behind, 15 expressions and a drawn talking mouth, six hand shapes and grips that close on the prop, and Mixamo clips for walking, running, sneaking, sitting, kneeling, lying, getting up, falling and jumping. Limits (no seating blazers from behind, no hats, no self-contact guard, backward falls only) are in `docs/CHARACTERS_3D.md`; two characters gripping each other are still staged around.
- **Stills cannot show motion.** Reviewers judge frames. Watch a draft animatic for timing before a long final render.
- **BlenderKit.** Search and download run through the official add-on with your login. That path could not be exercised from the build sandbox. If it fails on your machine, click the asset in the add-on and use `python tools/clip.py assets bk-local <words>`; the agents fall back to building the asset.
- **Licences.** The character pack and BlenderKit assets are for use in your productions, not for redistribution. ambientCG textures are CC0. Remotion is free for individuals and teams of up to three people.
