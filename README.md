# Clay Shorts pipeline

A Claude Code project that turns a short script into a finished, cinematic YouTube Short: narrated, clay-toy 3D, 1080×1920, about 50 seconds, about 4–5 shots.

Run **`/gen-clip`** in Claude Code. It asks for a script format and an idea, writes the script, plans the shots, records the voice, builds and lights the sets and characters in Blender, reviews the frames, renders, and assembles the final MP4 with music, sound effects and captions.

| Stage | Tool |
|---|---|
| Script | seven `script-*` skills (unchanged from `short-script-pipeline`) |
| Characters | your character pack `release_1` (Blender 5.3) |
| Sets, animation, light, render | Blender 5.3 + EEVEE, driven headless by `tools/blender/stagekit` |
| Assets | project library → BlenderKit → built in Blender |
| Voice, music, sound effects | ElevenLabs API |
| Assembly, mix, captions | Remotion 4 + FFmpeg |

## Setup

You need: **Claude Code**, **Blender 5.3**, **Python 3.10+**, **Node.js 20+**, **FFmpeg**, an **ElevenLabs API key**, and the **BlenderKit add-on** logged in inside Blender (for step 2 of asset sourcing).

1. **Unzip the project** anywhere, for example `D:\clay-shorts`.
2. **Put the character pack in place.** Copy the original **`release_1.zip`** to:

   ```
   <project>/packs/release_1.zip
   ```

   The pipeline reads the **extracted** pack at `<project>/packs/release_1/` (so that `packs/release_1/library/registry.json` and `packs/release_1/blender/py/character_factory.py` exist). The setup command below extracts the ZIP there for you. If you prefer, unzip it yourself into `packs/release_1/`; the ZIP is then not needed.
3. **Run setup** from the project folder:

   ```
   python tools/clip.py setup
   ```

   It extracts the pack, creates `.env` from `.env.example`, installs the Remotion packages, and prints what is missing. Use `python3` on macOS and Linux.
4. **Add your keys to `.env`:**

   ```
   ELEVENLABS_API_KEY=sk_...
   BLENDER_BIN=C:\Program Files\Blender Foundation\Blender 5.3\blender.exe
   ```

   `BLENDER_BIN` is only needed if `blender` is not on your PATH and not in the default install folder.
5. **Check the voices on your account:**

   ```
   python tools/clip.py voices
   ```

   See [Voices](#voices). Do this once; it writes `config/voices.local.json`.
6. **Check everything:**

   ```
   python tools/clip.py doctor          # add --pack to also run the pack's own 42-check smoke test (a few minutes)
   ```

BlenderKit: install the add-on in Blender 5.3 from blenderkit.com, enable it, and log in once from its panel. The pipeline then searches and downloads through the add-on as you (`python tools/clip.py bk-search "wooden chair"`).

## Run it

Open the project folder in Claude Code and type:

```
/gen-clip
```

It asks two things: the script format (or "you choose"), and whether you have a topic, keywords or an idea. You can also pass them directly:

```
/gen-clip slow-burn a lighthouse keeper who never lets anyone climb the stairs
/gen-clip auto keywords: night bus, last passenger, umbrella
```

What happens, in order:

1. **Script.** The matching `script-*` skill writes the story; `scripts/validate_script.py` checks it.
2. **Direction.** The `director` agent writes `shotplan.json`: 4–5 shots, each with a purpose, staging, camera, focus and light, and a reason for every cut and move.
3. **Voice and sound.** The `sound-designer` agent directs and records the narration (this sets every shot's length), then makes music, ambience and effects. In parallel the `asset-maker` agent fills any gaps in the asset library.
4. **Shots.** One `shot-builder` agent per set dresses the set, lights it, places and animates the characters, and sets camera and focus to the words. It renders review stills and fixes what the measured checks and the images show.
5. **Review.** A `frame-reviewer` agent judges each shot's stills against the plan. At most two fix rounds per shot.
6. **Render, assemble, QA.** Blender renders the frames, Remotion assembles picture, mix and captions, FFmpeg normalises loudness, and a QA script measures the result.

Rendering is the long part. As an estimate (not measured on your machine): about 1,300 frames at 1–2 seconds each on an RTX 5060, so 20–45 minutes, plus a few minutes of agent work per shot. The run is resumable: `python tools/clip.py status <clip>` shows where it stopped, and rendered frames are never rendered twice.

### Expected outputs

```
output/script-writer/<format>/<slug>.json        the script
output/clips/<slug>/
  script.json  state.json  shotplan.json  timing.json
  audio/     plan.json  narration.wav  music.wav  sfx/*.wav  amb/*.wav  cues.json
  blender/   set_<id>.py  sh01.py …             the shot code (re-runnable)
  review/    sh01/sheet.png  checks.json  verdict.json
  render/    sh01/final/0001.png …
  final/     <slug>.mp4                         ← the Short: 1080×1920, 24 fps, H.264 + AAC 48 kHz, −14 LUFS
             <slug>.qa.json                     measured facts and any warnings
library/assets/                                  new reusable assets, indexed with source and licence
```

A complete worked clip is in `examples/the-boy-in-the-basement/` (script, plan, audio plan, set and shot code, review stills, and a draft animatic).

### Doing steps by hand

Every stage is a command, so you can re-run one thing:

```
python tools/clip.py stills <clip> sh03                 # rebuild one shot and look at it
python tools/clip.py render <clip> --quality draft --step 4     # a fast animatic of the whole film
python tools/clip.py assemble <clip> --tag animatic --safe-area
python tools/clip.py voice <clip> --retake              # a new narration take (costs credits; shot lengths change)
python tools/clip.py render <clip> sh03 --force         # re-render one shot after a change
```

No API key yet? `voice --mock` and `sound --mock` produce placeholder audio with believable timing, so the whole pipeline can be tried offline.

## Voices

The shortlist per format is in `config/voices.json`. `python tools/clip.py voices` checks each voice on your account, resolves library voices by name, and prints the voice every format will use today.

| Format | Order tried |
|---|---|
| `unspoken-rules` | Lily → Christopher → Callum |
| `slow-burn` | George → David Castlemore |
| `twist` | George → Archer |
| `rule-of-three` | George → Brian → Lily |
| `micro-butterfly` | David Castlemore → Matilda |
| `ticking-clock` | Brian → Matilda → David Castlemore |
| `reverse-chronology` | Archer → Matilda → Callum |

What was verified on 21 November 2026, from the ElevenLabs documentation (the API itself could not be reached from the build sandbox):

- **George, Brian, Lily, Callum and Matilda are ElevenLabs *Default* voices, and ElevenLabs retires all Default voices on 31 December 2026.** They are only available to accounts created before March 2026. ElevenLabs names a replacement for each: George → *Eldrin – Crisp British Baritone*, Brian → *Sawyer – Midnight Storyteller*, Lily → *Florence – Atmospheric Storyteller*, Callum → *Callum – Husky Trickster*, Matilda → *Maisie – Friendly Casual Neighbor*. The config holds both ids, and after the retirement date the pipeline switches to the replacement by itself. The replacements are not exact matches: listen to them before January and reorder the shortlist if you prefer another voice.
- **David Castlemore, Archer and "Christopher – Smooth, Deep and Engaging" are Voice Library voices.** They exist, but a library voice must be in *My Voices* before the API can use it, and its id has to be read from your account. `clip.py voices` finds them by name. "Archer" matches several library voices; pick yours with `--pick "Archer=<voice id>"`. To add a library voice from the command line: `--add "David Castlemore=<voice id>"`.

To swap a voice, edit the `voices` list of the format in `config/voices.json` (first usable wins), or add a new entry under `"voices"` with its `voice_id`. To hear a change, run `python tools/clip.py voice <clip> --retake --voice "<name>"` on any clip.

The narration model is **Eleven v4** (`eleven_v4`), falling back to `eleven_v3`, then `eleven_multilingual_v2`. Delivery is directed with audio tags in the text (see `.claude/skills/sound-design/SKILL.md`). Sound effects use `eleven_text_to_sound_v3`, music `music_v2_5`.

Music rights depend on your ElevenLabs plan (see the Music Commercial Rights table in the Eleven Music terms). For monetised uploads, check your plan, or set `"enabled": false` under `music` in a clip's `audio/plan.json` and add licensed music later.

## Changing the look

- **`style/STYLE_GUIDE.md`**: how shots are planned, lit, staged and reviewed. Agents read it; edit it to change taste.
- **`style/style.json`**: numbers that scripts enforce: shot count, safe area, render quality, exposure limits, loudness, caption style, vignette and grain.
- **`tools/blender/stagekit/lights.py`**: the light moods (`MOODS`). Tune a mood once and every set that uses it follows.
- **`.claude/agents/*.md`**: each agent's role and model (`model: opus | sonnet | haiku | fable | inherit`).

## Project map

```
.claude/skills/gen-clip/         the /gen-clip command (the producer)
.claude/skills/script-*/         the seven script writers and their gold examples
.claude/skills/shot-plan/        shot plan format and rules
.claude/skills/cinematic-style/  the style guide as a decision card
.claude/skills/stagekit/         how to build a shot in Blender (API cheat sheet)
.claude/skills/sound-design/     voice direction, music, effects (ElevenLabs)
.claude/skills/asset-library/    library → BlenderKit → build
.claude/agents/                  director, sound-designer, asset-maker, shot-builder, frame-reviewer
tools/clip.py                    every mechanical step
tools/blender/stagekit/          sets, clay props, characters, light rigs, camera, review checks
tools/blender/run_shot.py        builds one shot in Blender: stills or frames
tools/audio/                     ElevenLabs client, narration + timing, music and effects
tools/assemble.py, tools/qa.py   Remotion + FFmpeg assembly, delivery checks
remotion/                        the assembly composition (shots, mix, captions, finish)
style/, config/                  style guide, style numbers, voices
library/assets/                  reusable assets (four starter assets included)
examples/                        the worked clip and example asset scripts
docs/RESEARCH.md                 what was researched, what was decided and why, what was verified
```

## Notes and limits

- **Blender version.** The character pack is built for Blender 5.3; so is this project. Render each Short on one machine: EEVEE can differ slightly between GPUs.
- **Windows.** EEVEE needs the GPU: render while logged in. Headless `blender -b` works for everything here.
- **Memory.** `render` restarts Blender every 120 frames (`--chunk`) so long takes cannot run out of memory, and a crash costs one chunk. Do not run a render and `assemble` at the same time on a machine with little RAM.
- **BlenderKit.** Search and download run through the official add-on's own functions with your login. That path was written from the add-on's source and could not be exercised from the build sandbox. If it fails on your machine, click the asset in the add-on and use `python tools/clip.py assets bk-local <words>`; the agents fall back to building the asset.
- **Stills cannot show motion.** The reviewer judges frames. Watch a draft animatic for timing and flicker before a long final render if a shot depends on movement.
- **Character limits.** No mouth animation; two characters touching, finger acting and climbing are staged around (see the style guide). `carry` works for an adult carrying a child at mid distance.
- **Licences.** The character pack and BlenderKit assets are for use in your productions, not for redistribution. Remotion is free for individuals and teams of up to three people.
