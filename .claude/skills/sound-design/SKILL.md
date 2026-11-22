---
name: sound-design
description: Narration delivery, music and sound effects with the ElevenLabs API for a 50-second Short - how to direct the standardized Alex voice at 220-240 WPM with contextual emotion tags and punctuation, the audio plan format, cue timing on words, and the commands that generate and place everything. Use when writing audio/plan.json or running the voice and sound steps.
---

# Sound design

You direct a narrator, a composer and a foley artist through one file: `output/clips/<clip>/audio/plan.json`. Scripts turn it into audio and put every sound on the film's clock.

```
python tools/clip.py voice <clip>      # one narration take with timestamps -> audio/narration.wav + timing.json
python tools/clip.py sound <clip>      # music, ambience, effects -> audio/cues.json
        --mock      placeholder audio without the API (dry runs)      --retake   generate again (costs credits)
```

Worked example: `examples/sound/the-boy-in-the-basement.audio-plan.json`.

## The standard voice (every category)

Every video category uses the exact same voice profile (`config/voices.json`):

**Alex — Upbeat, Energetic and Clear**

- **Voice characteristics:** upbeat, energetic, clear, conversational, expressive, confident, engaging, natural, and fast-paced without becoming difficult to understand.
- **Never override to a different voice** unless explicitly asked. Category-specific storytelling and emotional turns vary through your delivery tags, not by switching narrators.
- Run `python tools/clip.py voices` once to resolve Alex on your ElevenLabs account.

## Speed & pacing target: 220–240 WPM

- **Target speed:** **220–240 words per minute (WPM)**, preferred average **~230 WPM**.
- **Model:** **Eleven v4 (`eleven_v4`)**, with `eleven_v3` and `eleven_multilingual_v2` as automatic fallbacks (`config/voices.json`).
- **How pacing works across models:**
  - **`eleven_v4` / `eleven_v3`** do not accept a numeric `speed` parameter. Brisk 220–240 WPM pacing comes from Alex's natural energetic cadence, tight conversational phrasing (170–198 words for ~50 s), minimal `[pause]` tags, and forward-driving delivery tags (`[energetic]`, `[upbeat]`, `[fast-paced]`, `[excited]`).
  - **`eleven_multilingual_v2` / `eleven_flash_v2_5`** (fallbacks) automatically strip `[...]` tags and apply `speed: 1.2` (ElevenLabs API maximum, configured in `config/voices.json`).
- Keep delivery energetic, engaging, and natural—avoid sluggish or drawn-out reads—while keeping names, numbers, and key story details crystal clear.

What controls delivery on v4 and v3:

| You want | How |
|---|---|
| Tone, emotion, energy | **Contextual audio tags** in square brackets right before the line or clause they shift (see the tag list below). |
| Brisk momentum | Open with `[energetic]` or `[upbeat]` (or `[serious]` on tense hooks), use `[fast-paced]` during action or escalation, and avoid stacking slow pauses. |
| Brief beat / pause | Punctuation (dashes `—`, ellipses `…`, full stops) or a rare `[pause]`. **SSML `<break>` tags do not work on v4/v3.** Exact silences between shots belong in `shotplan.json` as `hold_after_s`. |
| Emphasis | Punctuation (`!`, `?`) or occasional CAPITALS on one word (at most once or twice per script). |
| Expressive consistency | `stability: 0.45`, `similarity_boost: 0.75` (standard across all formats in `config/voices.json`). Lower stability lets Alex react vividly to emotion tags while staying clear. |

## Contextual emotion & delivery tags

Use tags contextually based on what is happening in the story. Shift tone where the story shifts—do not repeat the same emotion on every sentence, and do not clutter the script with tags on lines that already flow naturally.

Supported style directions:

- `[energetic]` — punchy hooks, high-energy openings, bold actions
- `[upbeat]` — bright momentum, setups, cheeky turns, fun narration
- `[amused]` — funny reactions, absurd details, watching someone fall for a trick
- `[confused]` — puzzled questions, character disbelief
- `[knowing]` — letting the viewer in on the secret or clever setup ("You see...")
- `[deadpan]` — dry comedy, flat punchlines, understated irony
- `[serious]` — real danger, sharp stakes, grounded warnings
- `[fast-paced]` — action chains, chases, rapid escalation
- `[dramatic]` — reveals, near-misses, sudden turns
- `[suspicious]` — catching a clue, calling out a bluff, creeping doubt
- `[excited]` — surprising twists, sudden breakthroughs, big payoffs
- `[amazed]` — jaw-dropping outcomes, unbelievable endings
- `[ironic]` — karmic twists, poetic justice, wry final lines
- `[dismissive]` — arrogant rivals brushing off warnings
- `[laughs]` — brief natural laugh inside comedic moments

How to vary delivery for storytelling:

- **Excitement** (`[energetic]`, `[excited]`, `[amazed]`) during hooks and surprising moments.
- **Suspense** (`[serious]`, `[suspicious]`, `[dramatic]`) during danger, clues, and reveals.
- **Humor** (`[amused]`, `[deadpan]`, `[dismissive]`, `[laughs]`) for funny characters and absurd beats.
- **Momentum** (`[fast-paced]`, `[upbeat]`) during action sequences and escalations.
- **Conspiratorial payoff** (`[knowing]`, `[ironic]`) when the audience is about to connect the dots.

**Hard rules for tagged narration:**

- **The words never change.** Tags and punctuation may change; the tools reject any narration whose words differ from the shot's `vo_text`.
- **Keep total runtime at or under 55 s** (target 46–53 s at 220–240 WPM). Do not add unnecessary `[pause]` or `[long pause]` tags that drag the WPM down.
- **After the take**, check what `voice` prints: total seconds (target 46–53, limit 55), WPM (target **220–240**, avg ~230), and each shot's length. If it runs slow or over 55 s, trim pauses/heavy tags or tighten the script before using `--retake`.

## Reference voice example

Study how this reference builds instant interest, moves briskly like a friend telling a great story, and shifts emotion naturally from beat to beat. Learn from its pacing and emotional variation—do not copy its plot or wording:

```text
[energetic] He loaded the shotgun with gold, and fired it into the walls of the mine!

[amused] His buddy just watches the gold vanish into the rock.

[confused] "So... we're shooting gold... into a gold mine?"

[knowing] You see, it's called salting. [upbeat] He's dug this mine for ten years and found nothing but rock.

And tomorrow, a rich guy is coming to buy it. So he spent his last hundred bucks on gold dust instead.

[amused] Next morning, the rich guy rolls up in a white suit and bangs his head on the first beam.

[serious] But he's brought an expert, and the expert isn't stupid.

[fast-paced] He smashes a chunk of wall, swirls it in a pan, and gold flakes spin to the bottom.

[dramatic] But under his magnifying glass, every flake is flat.

[suspicious] "Somebody shot this gold into the wall!"

[amused] But the rich guy just laughs. [laughs] [dismissive] "Why would anyone shoot gold into a wall? That's insane!"

[amused] And his buddy nods. [deadpan] "Completely insane."

[upbeat] So, the rich guy pays up. [excited] And while those two bolt with the money, he stays behind and pulls a stick of dynamite out of his suit.

[amused] He's never mined a day in his life, so he just lights it, tosses it down the tunnel like a firecracker, and runs!

[amazed] And when the dust clears, there's a vein of real gold as thick as your arm— [ironic] ten feet past where the last guy gave up.
```

## The plan

```json
{
  "voice": {"voice": "Alex", "stability": 0.45, "similarity_boost": 0.75, "seed": 4107},
  "narration": [
    {"shot": "sh01", "text": "[energetic] Twenty Chicago cops personally hauled four million dollars straight into a thief's getaway van— [amused] and then waved him goodbye!"}
  ],
  "music": {"prompt": "…", "gain_db": -19},
  "ambience": [{"id": "amb_street", "prompt": "… seamless loop", "shots": ["sh01", "sh02"], "seconds": 20, "gain_db": -25}],
  "sfx": [{"id": "cash_thud", "prompt": "…", "duration_s": 0.7, "at": {"word": "van", "shot": "sh01", "offset_s": 0.05}, "gain_db": -7}]
}
```

`narration` has one entry per shot, in order. Leave a shot out to send its `vo_text` untouched.

**Where a cue starts (`at`)**

- `{"word": "lights went out", "shot": "sh01", "edge": "end", "offset_s": -0.2}`: on a spoken word or phrase. `edge` is `start` (default) or `end`; `nth` picks a repeat. **Prefer this**: it stays right when the take changes.
- `{"shot": "sh05", "t": 0.1}`: seconds into a shot (`t` negative counts from its end).
- `{"time": 12.3}`: seconds on the film. Avoid.

Line effects up with what the builder animates: the plan's `staging` and `light_change` say which word an action lands on. Use the same word.

## Music

One instrumental bed for the whole film (`music_v2_5`), generated at the film's length.

- Describe genre, instruments, tempo, mood, and **the shape over time**: match the energetic pacing—e.g. light rhythmic pulse that drives forward, thins out for suspense or a reveal, and punches cleanly into the payoff.
- Say "instrumental, no vocals, no drums" (or "light percussion" when energy fits) so the voice stays crystal clear.
- The mix puts music about 19 dB under the voice and ducks it further while the narrator speaks. Raise `gain_db` only for a musical moment with no narration.
- Licence: generated music is tied to your ElevenLabs plan's terms. For monetised uploads check them, or set `"enabled": false` and add licensed music later.

## Ambience and effects

Sound effects use `eleven_text_to_sound_v3` (0.5–30 s; `loop` for beds).

- **Ambience**: one bed per place, "seamless loop" in the prompt, 15–25 s. Say what is *not* there ("no birds, no traffic") to keep it clean.
- **Effects**: 5–10 per film is plenty. One sound per clue or action the viewer must notice. Prompt = the sound, the distance, the room: "Single sharp metal wire cutter snip, close, dry." Give `duration_s` close to the real sound.
- Typical gains: hero effect −6 to −9 dB, incidental −12 to −16, ambience −22 to −26.
- **Leave space.** Do not put an effect under the stressed word of a sentence; put it just after (`offset_s` 0.05–0.15) or in the hold. Let the last punchline stay clean.

## Check before you return

- `python tools/clip.py voice` used **Alex**, printed a total at or under 55 s (target 46–53 s), hit **220–240 WPM** (~230 WPM avg), and reported no word-mismatch error.
- `python tools/clip.py sound` listed every cue with a start time that makes sense against the shot times.
- You listened with your eyes: no two effects on the same half second, nothing starting before its shot.
