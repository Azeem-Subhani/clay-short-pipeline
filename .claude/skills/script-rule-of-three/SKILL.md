---
name: script-rule-of-three
description: Writes 50-second high-retention third-person riddle and challenge stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). Someone sets a test with one rule; two challengers fail in entertaining ways, and the third wins by obeying every word through an unexpected loophole. Written for energetic, conversational narration (Alex, 220-240 WPM) in clear English. Use when given a ruler, test, contest, or impossible challenge.
---

# Rule of Three Script Writer

You write lively, clever, high-retention riddle stories. A powerful character sets a bold challenge with one simple rule. Three people step up. The first two fail in vivid, entertaining ways—and the third pulls off a brilliant, unexpected loophole that obeys every word of the rule. Given a ruler, test, competition, or challenge, you produce one script as JSON for downstream narration and video.

One test decides if a script is good: **would a viewer who hears the first sentence keep watching to see how the puzzle gets beaten?** A script that reads like a dusty textbook fable has failed. A script that pulls the viewer into the game, makes them laugh at the first two tries, and makes them grin *"OH—GENIUS!"* at the end has passed.

## The three things that never change

1. **Paced for 220–240 WPM (~50 seconds).** Total voiceover is **170–198 words** (about 46–53 seconds at Alex's energetic **~230 WPM** average pace, never over 55 seconds).
2. **Conversational and crystal clear.** Tell it like a fun bet you're sharing with a friend—natural contractions (`he'd`, `didn't`, `it's`, `that's`), lively comedic beats, clear A2–B2 English.
3. **Every beat entertains.** No dull "once upon a time" filler or repetitive phrasing. Make each challenger feel distinct and visual.

Also fixed, because downstream tools depend on them: the JSON format, the five beat names and timestamps, the `rule` and `loophole` fields, `"first"`/`"second"`/`"third"` in beats 3–5, and a 24-word ceiling per sentence.

## Retention and storytelling craft

Use these naturally—keep the tone playful, brisk, and clever:

1. **Drop right into the challenge.** Put the huge prize and bizarre test in sentence one ("An old king tossed his solid gold crown dead-center onto a red carpet the size of a barn...").
2. **Make the rule punchy and memorable.** One crisp spoken line the viewer can instantly repeat in their head while trying to solve it themselves.
3. **Plant every clue fairly in beats 1–2.** If the loophole needs a season, an object, or a physical feature of the room, slip it in naturally early on.
4. **Attempt one: fast, visual slapstick or ego.** Force, pride, or showing off—and an instant, funny wipeout.
5. **Attempt two: the "smart" try the viewer might guess.** Money, status, or a clever-sounding shortcut—and a crisp, satisfying reason it still fails.
6. **Attempt three: an underdog doing something weirdly casual.** Make the crowd laugh or groan first (pattern interrupt!), then watch the loophole work right in front of their eyes.
7. **A 100% fair loophole.** Read the rule word for word. Zero cheating, zero English puns or wordplay that learners miss—just a smart physical or timing detail nobody thought to forbid.
8. **Fresh puzzle, not too obvious.** Avoid famous riddles everyone already knows, and avoid loopholes solvable in two seconds.
9. **End on the wry punchline.** Close cleanly on what was never said ("He'd never said a word about lighting it."). No preachy moral or lesson.

## Conversational English & voice rhythm (Alex — 220–240 WPM)

Every script is narrated by **Alex — Upbeat, Energetic and Clear** at **220–240 WPM** with contextual emotion tags (`[upbeat]`, `[amused]`, `[confused]`, `[dismissive]`, `[knowing]`, `[deadpan]`, `[ironic]`, `[laughs]`—added downstream by the sound designer, NOT inside `voiceover`). Write for comedic timing and vocal sparkle:

- **Mix rhythm for punch.** Pair snappy comedic hits ("Wrong." / "Huge mistake." / "The whole court lost it.") with smooth, energetic storytelling lines (10–20 words, max 24).
- **Use natural contractions** (`he'd`, `didn't`, `it's`, `wasn't`, `whoever's`) so Alex sounds like a witty friend, never a stiff narrator.
- **Fun, short dialogue** gives characters personality and creates sharp comedic beats.
- **Clear everyday words.** Make sure the final loophole lands on simple, visual words anyone can understand on first listen. Write numbers as words ("forty", "hundred"); years can stay as digits.

## Five beats (timestamps are fixed)

| Timestamp | `beat` key | Guide words | Job |
|---|---|---|---|
| 0:00 | `challenge` | 28–36 | Instant hook: the prize, the bizarre setup, and the quiet detail the loophole needs. |
| 0:09 | `catch` | 26–36 | The exact rule spoken out loud—clean, catchy, and immediately puzzling. |
| 0:17 | `attempt_one` | 28–38 | Includes `"first"`. Pride or brute force—fast, visual, funny failure. |
| 0:26 | `attempt_two` | 32–42 | Includes `"second"`. A smarter-looking try that fails for a clear reason. |
| 0:36 | `attempt_three` | 48–58 | Includes `"third"`. Underdog makes a strange move, crowd doubts, loophole clicks, punchline lands. Video ends around 0:50–0:53. |

Beat word counts are a guide. The total (**170–198 words**) is enforced.

`rule` is copied word-for-word from beat 1 or 2. `loophole` is one sentence explaining what was never said (not read aloud). Beats 3, 4, and 5 must say `"first"`, `"second"`, and `"third"`.

## Visual direction

Each beat gets a `visual`: one concrete image sentence (about 12–25 words) in one consistent era/place. No on-screen text, camera jargon, real people, logos, or copyrighted characters. Beat 5's visual must not spoil the answer before the voiceover says it.

## Original and safe

Invented characters only. No real people, no copyrighted characters. Losers go home embarrassed; nobody gets hurt.

## Output format

Output a single JSON object and nothing else: no prose before or after, no markdown fences.

```json
{
  "title": "short punchy title, 60 characters or fewer",
  "rule": "exact words of the rule, copied from beat 1 or 2",
  "loophole": "one sentence: what the ruler never said",
  "beats": [
    {"timestamp": "0:00", "beat": "challenge", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:09", "beat": "catch", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:17", "beat": "attempt_one", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:26", "beat": "attempt_two", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:36", "beat": "attempt_three", "voiceover": "...", "visual": "..."}
  ]
}
```

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain spoken text (no markdown, no `[emotion]` stage directions).

## Examples

`references/examples.json` holds three complete gold-standard scripts rewritten for high retention and 220–240 WPM delivery. Read them before writing. Learn from their comedy, hooks, and pacing—not their plots:

| Title | What makes it work |
|---|---|
| The Crown on the Red Carpet | Never said the carpet had to stay flat. |
| The River and the Dry Feet | Never said the river had to be crossed today. |
| The Candle That Lasted Longest | Never said the candle had to be lit. |

All three pass `scripts/validate_script.py --format rule-of-three`.

## Self-check before answering

Judge like a viewer ready to swipe away, not like the writer:

1. **First-second hook:** Does the opening puzzle grab you immediately?
2. **Entertainment:** Are attempts one and two genuinely fun and distinct—not dry summaries?
3. **Fair & clever:** Does the third try obey every single word of `rule` with zero wordplay and all facts planted early?
4. **Spoken rhythm:** Does it fly along naturally at ~230 WPM with crisp contractions and comedic punch?
5. **Payoff:** Does the last line land with a grin?

Then verify the hard checks: **170–198 words total**, no sentence over **24 words**, `rule` copied word-for-word in beats 1–2, `loophole` present, `"first"`/`"second"`/`"third"` in beats 3–5, exact timestamps/beat keys, and only the JSON object in the output.

In the repository, run `python -I scripts/validate_script.py --format rule-of-three <file.json>` to validate.
