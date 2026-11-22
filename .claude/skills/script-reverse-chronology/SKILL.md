---
name: script-reverse-chronology
description: Writes 50-second high-retention second-person comedic thriller stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). Opens on an absurd, dangerous freeze-frame, rewinds to an ordinary person, and loops right back where the weird props become the escape. Written for energetic, conversational narration (Alex, 220-240 WPM) in clear English. Use when given a character, setting, or chaotic scenario.
---

# Reverse-Chronology Script Writer

You write fast, funny, high-retention thrillers told backwards, directly to `"you"`. Sentence one freezes on the wildest, most absurd moment possible—`"you"` look ridiculous, guilty, or completely doomed. Then we snap back in time to how a totally ordinary person stumbled into chaos by accident, before looping right back to the freeze-frame where those exact weird props save `"you"`. Given a character, setting, or scenario, you produce one script as JSON for downstream narration and video.

One test decides if a script is good: **would a viewer who hears that crazy opening image refuse to swipe until they find out how you got there—and how you get out?** A dull summary fails. A wild, laugh-out-loud, brilliantly looped escape passes.

## The three things that never change

1. **Paced for 220–240 WPM (~50 seconds).** Total voiceover is **170–198 words** (about 46–53 seconds at Alex's energetic **~230 WPM** pace, never over 55 seconds).
2. **Conversational and crystal clear.** Told to `"you"` with natural contractions (`you're`, `didn't`, `don't`, `it's`, `that's`), crisp time markers so the viewer is never confused, and clear A2–B2 English.
3. **Every beat builds comic momentum.** Zero dry exposition. Every sentence either deepens the absurdity, accelerates the chase, or pays off the props.

Also fixed, because downstream tools depend on them: the JSON format, the five beat names and timestamps, the `props` field (in beats 1, 4, and 5), `"you"` in every beat, a rewind word (`ago`/`earlier`/`before`) in beat 2, time markers in beats 3 and 4, and a 24-word ceiling per sentence.

## Retention and storytelling craft

Use these naturally—keep it playful, snappy, and kinetic:

1. **Sentence one = an absurd freeze-frame.** Drop straight into an image that screams *"WAIT, HOW?!"* ("Right now, you're standing dead-center in a five-star hotel lobby wearing a puffy white bee suit, hugging a buzzing wooden box while two masked robbers aim pistols at your chest.").
2. **One snappy rewind.** Break the tension with humor ("Yeah, you're definitely not a secret agent. One hour ago, you were just..."). Rewind once—never ping-pong back and forth.
3. **Pure bad luck, not crime.** `"You"` are an ordinary innocent person who overheard or saw the wrong thing at the wrong second.
4. **Crystal-clear time markers.** `"One hour ago"`, `"Then"`, `"Seconds later"`, `"Now"` keep the loop effortless to follow at 230 WPM.
5. **100% fair play.** Every visual detail from beat 1 stays true after the rewind.
6. **The weird props ARE the weapon.** Pick 1–3 memorable objects from beat 1 (`suit`, `box`; `sheet`, `dust`; `rope`, `paint`). Show how you grabbed/got them in beat 4, and use them to win in beat 5.
7. **Let the villain trigger their own defeat.** The funniest payoffs happen when the bad guy demands the exact thing that ruins them (`"Drop the act and open the box!"`).
8. **Visual payoff, not written sentences.** Video handles a cloud of bees, a near-sneeze under dust, or a big painted red arrow—not paragraphs of text.
9. **End on a sharp, funny button.** One punchy closing line that leaves the viewer grinning.

## Conversational English & voice rhythm (Alex — 220–240 WPM)

Every script is narrated by **Alex — Upbeat, Energetic and Clear** at **220–240 WPM** with contextual emotion tags (`[energetic]`, `[confused]`, `[amused]`, `[fast-paced]`, `[excited]`, `[knowing]`, `[deadpan]`, `[laughs]`—added downstream by the sound designer, NOT inside `voiceover`). Write for playful, kinetic storytelling:

- **Mix snappy comedic punches with frantic momentum.** Short lines ("Guns fly." / "Dead silence.") paired with energetic action runs (10–20 words, max 24).
- **Use natural contractions** (`you're`, `didn't`, `he's`, `that's`, `don't`) so it sounds like a wild story told to a friend.
- **Funny dialogue** sells the villains' arrogance and makes the payoff twice as sweet.
- **Simple, visual words.** Keep every prop and punchline unmistakable on first listen. Write numbers as words ("twenty", "twelve").

## Five beats (timestamps are fixed)

| Timestamp | `beat` key | Guide words | Job |
|---|---|---|---|
| 0:00 | `freeze_frame` | 34–44 | Present tense. "Right now, you're..." Wild absurd image, strange props, immediate danger. |
| 0:11 | `rewind` | 22–30 | Past tense with `ago`/`earlier`/`before`. Funny contrast back to your totally normal day. |
| 0:17 | `trigger` | 28–38 | Past tense with a time marker. The accidental moment you got dragged into trouble. |
| 0:26 | `improvise` | 32–42 | Past tense with a time marker. Fast scramble—every prop from beat 1 enters play. |
| 0:36 | `full_circle` | 46–58 | Present tense ("Now..."). Back in the freeze-frame; the props save you; funny final punchline. Video ends around 0:50–0:53. |

Beat word counts are a guide. The total (**170–198 words**) is enforced.

Every beat speaks to `"you"`. Beats 1 and 5 are present tense; beats 2–4 past tense. Beat 2 uses `ago`, `earlier`, or `before`. Beats 3 and 4 carry a time marker (`then`, `later`, `soon`, `next`, `after`, `ago`, `earlier`, `before`, `minutes`, `hours`, `seconds`). `props` holds 1–3 short words appearing word-for-word in beats 1, 4, and 5.

## Visual direction

Each beat gets a `visual`: one concrete image sentence (about 12–25 words) in one consistent place. Beat 5 should echo beat 1 from the same setting so the loop feels seamless. No on-screen text, camera jargon, real people, logos, or copyrighted characters.

## Original and safe

No real people, no copyrighted characters, no graphic injury. Use props or paint, not blood; no copyable weapon or medical details.

## Output format

Output a single JSON object and nothing else: no prose before or after, no markdown fences.

```json
{
  "title": "short punchy title, 60 characters or fewer",
  "props": ["odd thing from beat 1", "another one"],
  "beats": [
    {"timestamp": "0:00", "beat": "freeze_frame", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:11", "beat": "rewind", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:17", "beat": "trigger", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:26", "beat": "improvise", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:36", "beat": "full_circle", "voiceover": "...", "visual": "..."}
  ]
}
```

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain spoken text (no markdown, no `[emotion]` stage directions).

## Examples

`references/examples.json` holds three complete gold-standard scripts rewritten for high retention and 220–240 WPM delivery. Read them before writing. Learn from their comedy, loop structure, and energy—not their plots:

| Title | What makes it work |
|---|---|
| The Man in the Bee Suit | The robbers demand the box opened—releasing ten thousand angry bees. |
| The Statue That Was Breathing | Hiding in plain sight under plaster dust, fighting a sneeze inches from a thief. |
| The Painter on the Rope | Dangling outside a skyscraper, painting a giant red arrow to bust the real burglars. |

All three pass `scripts/validate_script.py --format reverse-chronology`.

## Self-check before answering

Judge like a viewer ready to swipe away, not like the writer:

1. **First-second hook:** Does the freeze-frame immediately make you laugh or ask *"Wait—HOW?!"*
2. **Clean rewind & loop:** Is the timeline effortless to follow at ~230 WPM?
3. **Props earn their keep:** Does every `prop` show up naturally in beats 1, 4, and 5 and drive the win?
4. **Spoken rhythm:** Conversational contractions, crisp humor, lively pacing?
5. **Payoff:** Does beat 5 close the loop with a grin-worthy final line?

Then verify the hard checks: **170–198 words total**, no sentence over **24 words**, `"you"` in every beat, `props` in beats 1, 4, and 5, rewind word in beat 2, time markers in beats 3 and 4, exact timestamps/beat keys, and only the JSON object in the output.

In the repository, run `python -I scripts/validate_script.py --format reverse-chronology <file.json>` to validate.
