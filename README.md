# Shorts pipeline (2D cast, 3D world)

A Claude Code project that turns a short script into a finished YouTube Short: a narrator over flat 2D cartoon characters staged in a real 3D world, 1080×1920, about 60–65 seconds, with captions.

Run **`/gen-clip`** in Claude Code. It asks for a script format and an idea, writes the script, plans the world, cast, shots and camera views, records the voice, builds the set and stages the characters in Blender, reviews the frames, renders, and assembles the final MP4 with music, sound effects and captions.

| Stage | Tool |
|---|---|
| Script | seven `script-*` skills |
| Characters | your 2D character pack `characters_beta_0_4` (Blender 5.3) |
| Sets, staging, light, render | Blender 5.3 + EEVEE, driven headless by `tools/blender/stagekit` |
| Surfaces | ambientCG scanned textures by name (free, CC0), with procedural stand-ins |
| Props and set pieces | the built-in kit → project library → BlenderKit (your Full plan) → built in Blender |
| Voice, music, sound effects | ElevenLabs API |
| Assembly, mix, captions | Remotion 4 + FFmpeg |

How the look and the rules were derived from the two reference Shorts: [`docs/REFERENCE_BREAKDOWN.md`](docs/REFERENCE_BREAKDOWN.md). What was wrong with the first version and why: [`docs/DIAGNOSIS.md`](docs/DIAGNOSIS.md). Where the project stands and what is unverified: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Setup

You need: **Claude Code**, **Blender 5.3**, **Python 3.10+**, **Node.js 20+**, **FFmpeg**, an **ElevenLabs API key**, and the **BlenderKit add-on** logged in inside Blender (only used when a story needs a prop the kit and library do not have).

1. **Unzip the project** anywhere, for example `D:\clay-shorts`.
2. **Put the character pack in place.** Copy **`characters_beta_0_4.zip`** to:

   ```
   <project>/packs/characters_beta_0_4.zip
   ```

   Setup extracts it to `packs/characters_beta_0_4/` (the pipeline needs the `character-library_*.blend` inside). If you keep the pack somewhere else, set `CAST_PACK=<folder or .blend>` in `.env` instead. The pack is never committed and never included when the project is zipped.
3. **Run setup** from the project folder (`python3` on macOS and Linux):

   ```
   python tools/clip.py setup
   ```

   It extracts the pack, creates `.env` from `.env.example`, installs the Remotion packages, and prints what is missing.
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

1. **Script.** The matching `script-*` skill writes the story; `scripts/validate_script.py` checks it.
2. **Direction.** The `director` agent writes `shotplan.json`: the story's world and period, the cast from the pack with costumes, the set and where people stand, the shots, and the camera views inside each shot with the narrator's words they start on. `plan-check` refuses characters, costume pieces and surfaces from the wrong period, and endings whose mechanism was never shown.
3. **Voice and sound.** The `sound-designer` agent records the narration (this sets every shot's length and every word's time), then makes music, ambience and effects. Surfaces are fetched in parallel.
4. **Shots.** One `shot-builder` agent per set builds the place around the action, puts the cast on their marks, animates poses, faces, hands and props to the words, and adds the camera views. It renders two review stills per view and fixes what the measured checks and the images show.
5. **Review.** A `frame-reviewer` agent judges each shot's stills against the plan: one world, purpose, performance, cause and effect, captions. At most two fix rounds per shot.
6. **Render, assemble, QA.** Blender renders the frames, Remotion adds the mix and the captions, FFmpeg normalises loudness, and `qa` measures the file, including where the captions sit and whether they are on time.

**Closing the session does not lose anything.** Every stage writes into `output/clips/<slug>/`. `/gen-clip resume` (or `resume <clip>`) runs `python tools/clip.py status <clip>`, finds the first unfinished stage and continues. The paid voice take is kept and frames that exist are not rendered again.

### Regenerating *The Ring in the Pond*

The clip folder `output/clips/the-ring-in-the-pond/` ships with its script, shot plan, set and shot code, the soundtrack of your earlier render (voice, music and effects as one track) and the word times read from it. After the setup above (pack in `packs/`, `python tools/clip.py setup`):

```
python tools/clip.py materials fetch the-ring-in-the-pond     # scanned stone, wood, grass, water (once; skip it and you get procedural stand-ins)
python tools/clip.py render the-ring-in-the-pond              # all four shots at final quality; resumable, run it again if it stops
python tools/clip.py assemble the-ring-in-the-pond            # -> output/clips/the-ring-in-the-pond/final/the-ring-in-the-pond.mp4
python tools/clip.py qa the-ring-in-the-pond
python tools/clip.py sample the-ring-in-the-pond              # one frame per view -> final/samples/sheet.png
```

Want a fast look first? `python tools/clip.py render the-ring-in-the-pond --quality draft --step 3` then `assemble the-ring-in-the-pond --tag animatic` gives a small, rough version of the whole film in a few minutes on a GPU.

To change something, edit `blender/set_pond_garden.py` or `blender/shNN.py`, look at it with `python tools/clip.py stills the-ring-in-the-pond shNN`, then `render the-ring-in-the-pond shNN --force` and `assemble` again. To have the agents rebuild the visuals from the plan themselves, delete `blender/` and `review/` in the clip folder and run `/gen-clip resume the-ring-in-the-pond`.

**About the sound.** The rebuild had no access to your ElevenLabs files, so the clip uses the finished soundtrack of your earlier MP4 as one track; nothing is re-mixed. If you want the original separate stems back (cleaner, and effects can be re-timed to the new action), copy the `audio/` folder from the first version's clip folder into this one, delete this clip's `timing.json`, and ask Claude Code: *"sound-designer: clip the-ring-in-the-pond has a new four-shot plan. Update the shot anchors in audio/plan.json to it, keep every generated file (no --retake), then run voice and sound."* The voice step keeps your take and only re-times it. This path was not tested in the rebuild.

### Expected outputs

```
output/script-writer/<format>/<slug>.json        the script
output/clips/<slug>/
  script.json  state.json  shotplan.json  timing.json
  audio/     plan.json  narration.wav  music.wav  sfx/*.wav  amb/*.wav  cues.json
  blender/   set_<id>.py  sh01.py …             the set and shot code (re-runnable)
  review/    sh01/sheet.png  checks.json  verdict.json
  render/    sh01/final/0001.png …
  final/     <slug>.mp4                         ← the Short: 1080×1920, 24 fps, H.264 + AAC 48 kHz, −14 LUFS
             <slug>.captions.json               every caption with its words and frames
             <slug>.qa.json                     measured facts and any warnings
library/                                         new surfaces and reusable assets, with source and licence
```

A complete worked clip is in `examples/the-ring-in-the-pond/`.

### Doing steps by hand

```
python tools/clip.py cast --era medieval                    # who in the pack fits a period
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
- **`config/cast.json`**: every pack character with its periods, colours and parts; the wardrobe; costume recipes that move a character into another period.
- **`library/materials/catalog.json`**: the named surfaces, their periods and the ambientCG scans behind them.
- **`tools/blender/stagekit/lights.py`**: the light moods (`MOODS`). Tune a mood once and every set that uses it follows.
- **`tools/blender/stagekit/cast.py`** (`POSES`) and **`wardrobe.py`**: named poses and costume pieces. `docs/poses.png` shows the poses.
- **`.claude/agents/*.md`**: each agent's role and model (`model: opus | sonnet | haiku | fable | inherit`).

## Project map

```
.claude/skills/gen-clip/         the /gen-clip command (the producer)
.claude/skills/script-*/         the seven script writers and their gold examples
.claude/skills/shot-plan/        shot plan format: world, cast, sets, shots, views, setups
.claude/skills/cinematic-style/  the style guide as a decision card
.claude/skills/stagekit/         how to build a set and stage a shot in Blender (API cheat sheet)
.claude/skills/sound-design/     voice direction, music, effects (ElevenLabs)
.claude/skills/asset-library/    surfaces, kit, library, BlenderKit, build
.claude/agents/                  director, sound-designer, asset-maker, shot-builder, frame-reviewer
tools/clip.py                    every mechanical step
tools/plan.py                    the shot-plan validator (period, cast, surfaces, views, setups, narration)
tools/captions.py                caption grouping and timing
tools/materials.py               ambientCG search and download
tools/blender/stagekit/          cast (2D actors), wardrobe, build (world kit), mat (surfaces), lights, camera (views), fx, review
tools/blender/run_shot.py        builds one shot in Blender: stills or frames
tools/audio/                     ElevenLabs client, narration + timing, music and effects, align.py (speech recognition for checks and imports)
tools/assemble.py, tools/qa.py   Remotion + FFmpeg assembly, delivery and caption checks
remotion/                        the assembly composition (shots, mix, captions, finish)
style/, config/                  style guide, style numbers, cast and wardrobe, voices
library/                         materials/catalog.json, assets/ (reusable props and set pieces)
packs/                           where the character pack goes (not shipped)
examples/                        the worked clip and an example asset script
docs/                            reference breakdown, diagnosis, handoff, pose sheet, earlier research
```

## Notes and limits

- **Blender version.** The character pack is built for Blender 5.3; so is this project. Render each Short on one machine: EEVEE can differ slightly between GPUs.
- **Windows.** EEVEE needs the GPU: render while logged in. Headless `blender -b` works for everything here.
- **Memory.** `render` restarts Blender every 120 frames (`--chunk`, or `RENDER_CHUNK` in `.env`). If Blender is stopped part-way (a crash, or the system ending it for using too much memory), `render` carries on by itself in smaller chunks and tells you the size that worked; nothing already rendered is redone. In the build sandbox (software rendering, 6 GB) memory grew with every frame that had characters in it, so chunks of 6 were needed there; a GPU machine may not show this at all. Do not run a render and `assemble` at the same time on a machine with little RAM.
- **What the characters can do.** Three drawings (front, three-quarter, side), five expressions, a talking mouth, three hand shapes, a walk, and limbs that turn in the picture plane. No back views; climbing, getting up and down, and two characters gripping each other are staged around (start, cut, result).
- **Stills cannot show motion.** Reviewers judge frames. Watch a draft animatic for timing before a long final render.
- **BlenderKit.** Search and download run through the official add-on with your login. That path could not be exercised from the build sandbox. If it fails on your machine, click the asset in the add-on and use `python tools/clip.py assets bk-local <words>`; the agents fall back to building the asset.
- **Licences.** The character pack and BlenderKit assets are for use in your productions, not for redistribution. ambientCG textures are CC0. Remotion is free for individuals and teams of up to three people.
