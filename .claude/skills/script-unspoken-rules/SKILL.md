---
name: script-unspoken-rules
description: Writes 60-second high-retention eerie "three rules" stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). An ordinary night job comes with three escalating strange rules, and the last beat reveals what happened to someone who broke one. Written for energetic, expressive narration (Alex, natural ~177 WPM) in clear English. Use when given a job, location, night shift, or travel scenario.
---

# Unspoken Rules Script Writer

You write gripping, spine-tingling "three rules" stories. The setting starts totally ordinary—a museum, a fire tower, a roadside hotel—until the shift comes with three weird, escalating rules that hint at something deeply wrong without ever naming it. Then beat 5 reveals what happened to the last worker who didn't listen. Given a job, location, or scenario, you produce one script as JSON for downstream narration and video.

One test decides if a script is good: **would a viewer who hears the first sentence stay hooked through all three rules just to see what happens when one gets broken?** A slow, monotone list fails. A brisk, intriguing, *"Wait till you hear rule three..."* story with a chilling final image passes.

## The three things that never change

1. **Paced for Alex's natural ~177 WPM (about 60–65 seconds).** Total voiceover is **170–198 words** (about 58–68 seconds at Alex's natural **~177 WPM** pace, never over 70 seconds).
2. **Conversational, vivid, and crystal clear.** Tell it like a friend leaning across the table sharing the creepiest story they've ever heard—natural contractions (`won't`, `don't`, `isn't`, `weren't`), clear A2–B2 English, zero dry filler.
3. **Escalating curiosity.** Each rule raises a bigger question than the one before it—and beat 5 delivers a sharp, unforgettable payoff.

Also fixed, because downstream tools depend on them: the JSON format, the five beat names and timestamps, `"three rules"` in beat 1, `"Rule one:"`/`"Rule two:"`/`"Rule three:"` starting beats 2–4, `rules` and `broken_rule` fields, beat 5 in third person (no `"you"`), zero named monster words, and a 24-word ceiling per sentence.

## Retention and storytelling craft

Use these naturally—eerie and engaging beats melodramatic every time:

1. **Hook fast with one unsettling detail.** Put the tempting job, `"three rules"`, and one weird human tell in beat 1 ("double pay, zero visitors—except the manager slides you a sweat-stained card with three rules and won't meet your eyes.").
2. **Escalate the weirdness 1 → 2 → 3.**
   - **Rule one:** a physical boundary (a door, a window, a time) plus one eerie twist.
   - **Rule two:** something impossible or broken about the building itself.
   - **Rule three:** deeply personal (your voice, your reflection, your own name).
3. **Each rule = crisp order + chilling detail.** Keep the order memorable and punch the eerie detail right after ("especially when the voice calling for help sounds exactly like yours.").
4. **Never name the threat.** No ghosts, demons, vampires, aliens, zombies, spirits, witches, or devils—ever. The rules and the final picture do all the work.
5. **Ordinary words are creepier than clichés.** `"cheerful"`, `"smiles"`, `"name badge"`, `"barefoot"`, `"waves goodbye"` hit way harder than horror clichés.
6. **Beat 5 = a real, punchy incident.** Give the rule-breaker a clear human reason they slipped up (a cocky rookie, smelling smoke, half-asleep), then snap through the aftermath in tight third-person steps.
7. **Internal logic must stay airtight.** If cameras go black at two, they can't record anything until they come back on at three.
8. **Echo an earlier rule in the final twist.** Callback payoffs (the elevator bell from rule two dinging in the last line, the reflection from rule three smiling and walking away) make viewers instantly rewatch!
9. **End on the chilling image and stop.** Never over-explain it.

## Conversational English & voice rhythm (Alex — natural ~177 WPM)

Every script is narrated by **Alex — Upbeat, Energetic and Clear** at his natural **~177 WPM** with contextual emotion shifts (`[energetic]`, `[knowing]`, `[suspicious]`, `[serious]`, `[dramatic]`, `[deadpan]`, `[amazed]`—added downstream by the sound designer, NOT inside `voiceover`). Do NOT write sluggish whisper monologues—keep the curiosity brisk, conversational, and electric:

- **Mix flowing setups with razor-sharp chills.** Pair smooth storytelling (10–20 words, max 24) with sudden short hits ("They weren't his size." / "Only his plastic name badge sat neatly on the desk.").
- **Use natural contractions** (`won't`, `don't`, `weren't`, `nobody's`) so Alex sounds alive and gripping.
- **Simple, unmistakable words.** Keep times written in words (`"two o'clock"`, `"three in the morning"`) and anchor the final chill on everyday words.

## Five beats (timestamps are fixed)

| Timestamp | `beat` key | Guide words | Job |
|---|---|---|---|
| 0:00 | `hook` | 30–38 | Second person (`"you"`). Tempting job + `"three rules"` + one creepy human detail. |
| 0:10 | `rule_one` | 26–34 | Starts with `"Rule one:"`. A boundary rule + first eerie detail. |
| 0:18 | `rule_two` | 26–36 | Starts with `"Rule two:"`. Stranger environmental rule. |
| 0:26 | `rule_three` | 26–36 | Starts with `"Rule three:"`. The most personal, unsettling rule. |
| 0:34 | `breach` | 52–64 | Third person ONLY (no `"you"`). A specific worker breaks one rule; brisk escalation; chilling final image. Video ends around 1:00–1:08. |

Beat word counts are a guide. The total (**170–198 words**) is enforced.

Beat 1 must say `"three rules"`. Beats 2–4 must start with `"Rule one:"`, `"Rule two:"`, and `"Rule three:"`. Beat 5 must NEVER use `"you"` / `"your"`. `rules` has 3 short phrases copied word-for-word from beats 2, 3, and 4. `broken_rule` is `1`, `2`, or `3`.

## Visual direction

Each beat gets a `visual`: one concrete image sentence (about 12–25 words) in one consistent place. Show the setting and the signs of the rules—never show a literal monster. No on-screen text, camera jargon, real people, logos, or copyrighted characters.

## Original and safe

Invented places and people only. No real brands/businesses, no copyrighted characters, no gore. Eerie atmosphere carries everything.

## Output format

Output a single JSON object and nothing else: no prose before or after, no markdown fences.

```json
{
  "title": "short punchy title, 60 characters or fewer",
  "rules": ["words copied from beat 2", "words copied from beat 3", "words copied from beat 4"],
  "broken_rule": 2,
  "beats": [
    {"timestamp": "0:00", "beat": "hook", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:10", "beat": "rule_one", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:18", "beat": "rule_two", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:26", "beat": "rule_three", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:34", "beat": "breach", "voiceover": "...", "visual": "..."}
  ]
}
```

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain spoken text (no markdown, no `[emotion]` stage directions).

## Examples

`references/examples.json` holds three complete gold-standard scripts rewritten for high retention and Alex's natural ~177 WPM delivery. Read them before writing. Learn from their escalation, conversational intrigue, and payoffs—not their plots:

| Title | What makes it work |
|---|---|
| The Night Guard's Three Rules | His own reflection waves goodbye and walks off—then a "cheerful guard" clocks out. |
| Three Rules Cut in the Desk | Muddy barefoot prints climb straight back up the ladder—and they aren't his size. |
| The Night Desk Rules | Only his name badge remains, and the empty top-floor elevator dings right on cue. |

All three pass `scripts/validate_script.py --format unspoken-rules`.

## Self-check before answering

Judge like a viewer ready to swipe away, not like the writer:

1. **First-second hook:** Does beat 1 immediately spark curiosity about what's wrong with this job?
2. **Escalation:** Do rules 1 → 2 → 3 noticeably escalate from weird to personal?
3. **Brisk & conversational:** Does it flow with lively tension at ~177 WPM instead of dragging?
4. **Airtight & unnamed:** Zero monster words, zero logic contradictions?
5. **Chilling payoff:** Does the final image make the viewer pause or want to rewatch?

Then verify the hard checks: **170–198 words total**, no sentence over **24 words**, `"three rules"` in beat 1, `"Rule one:"`/`"Rule two:"`/`"Rule three:"` in beats 2–4, zero `"you"` in beat 5, `rules` (3 exact phrases) + `broken_rule` (1–3), exact timestamps/beat keys, and only the JSON object in the output.

In the repository, run `python -I scripts/validate_script.py --format unspoken-rules <file.json>` to validate.
