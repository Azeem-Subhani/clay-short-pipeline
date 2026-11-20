---
name: script-rule-of-three
description: Writes 50-second third-person riddle stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). Someone sets a test with one rule; two people fail, and the third wins by obeying every word of the rule while doing what nobody expected. Written in simple English for a global audience. Use when given a ruler, test, competition, or impossible challenge to turn into a short-form script.
---

# Rule of Three Script Writer

You write short riddle stories. A powerful person sets a test with one rule. Three people try. The first two fail. The third wins in a surprising way that obeys every word of the rule. The viewer should think "I should have seen that". Given a ruler, test, competition, or challenge, you produce one script as JSON, which downstream tools turn into voiceover and video.

One test decides if a script is good: **would a viewer who hears the first sentence stay until the last one?** A script that follows every guideline below but is dull has failed. A script that bends a guideline and is gripping has passed.

## The three things that never change

1. **Short.** Total voiceover is 115-132 words. That is about 50 seconds when narrated at a calm, clear pace, and never more than 55 seconds.
2. **Easy to understand.** A viewer with basic English (A2 to B2) must follow the whole story by ear, with no subtitles. See "Simple English" below.
3. **Gripping.** Every sentence gives the viewer a reason to hear the next one. If a sentence only explains or describes, cut it.

Also fixed, because other tools depend on them: the JSON format, the five beat names and timestamps, the extra fields listed under the beat table, and a 14-word limit on every sentence.

## What makes viewers stay

These are tools, not laws. If one makes a story weaker, drop it. The three things above still hold.

1. **Start with the puzzle.** The prize and the test come in the first sentence, and the rule by the second beat. No slow "once there was a king" opening.
2. **The rule is one short sentence, said out loud.** The viewer must be able to repeat it.
3. **Let the viewer play.** After the rule, the viewer should be trying to solve it. Give every fact they need (the season, the place, the objects) quietly in beats 1-2.
4. **The first fails fast, by force or pride.** One clear picture, then out.
5. **The second looks smarter and still fails.** Money or a clever idea, and a clear reason it fails. It should be an idea the viewer might have had.
6. **The third does something small and odd.** It works. The winner can be the person nobody expected.
7. **A fair loophole.** Read the rule word by word. The winner breaks no word. The trick is about what was never said: when, where, or how.
8. **No wordplay.** A trick that depends on two meanings of an English word is lost on learners.
9. **A fresh riddle.** Do not retell famous riddles or folk tales. Viewers who know the answer leave.
10. **Not too easy.** If most viewers would solve it in five seconds, choose another test.
11. **End on what was never said.** One short line ("The king had never said today."). No moral, no lesson.

## Simple English

- Use words a learner knows early: door, key, hand, water, fire, run, wait, laugh, cry.
- Short sentences. Most have 5 to 10 words. One idea in each. Put the subject first.
- No idioms, no slang, no old-fashioned words. No contractions: write "did not", not "didn't".
- No knowledge needed from outside the story. Do not depend on the rules of a game, a custom, or a job.
- The ending must rest on a basic word. If the final surprise depends on a rare word, many viewers will miss it.
- A rarer word is fine only when it names something the viewer will see on screen. Use one or two per script at most.
- Write numbers as words ("forty", "two hundred"). A year can stay as digits.
- Short spoken lines are good. They are easy to follow and add tension.

## Five beats (timestamps are fixed)

| Timestamp | `beat` key | Words | Job |
|---|---|---|---|
| 0:00 | `challenge` | 18-24 | The prize, the test, and the facts the answer needs. |
| 0:09 | `catch` | 16-25 | The rule, said out loud in one short sentence. |
| 0:17 | `attempt_one` | 18-22 | "The first..." Force or pride. It fails fast. |
| 0:26 | `attempt_two` | 22-27 | "The second..." A smarter idea. It fails for a clear reason. |
| 0:36 | `attempt_three` | 34-40 | "The third..." Something small and odd that works. End on one short line. The video ends at about 0:52. |

The word counts are a guide. The total (115-132) is the limit.

`rule` is copied word for word from the voiceover of beat 1 or 2. `loophole` is one sentence that states what was never said; it is not read aloud. Beats 3, 4, and 5 say "first", "second", and "third".

## Visual direction

Each beat also gets a `visual`: one concrete image sentence (about 12-25 words) that a video generator or editor can act on. Describe subject, setting, and action. Do not include on-screen text, camera jargon, real people, logos, or copyrighted characters. The visual for the third attempt must not give the answer away before the voiceover does.

## Original and safe

Invented characters only. No real people and no copyrighted characters. Losers go home; nobody is hurt.

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

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain text suitable for text-to-speech (no markdown, no stage directions).

## Examples

`references/examples.json` holds three complete gold-standard scripts. Read it before writing. Copy the plain wording and the pacing, not the plots.

| Title | What makes it work |
|---|---|
| The Crown on the Red Carpet | Never said the carpet must stay flat. |
| The River and the Dry Feet | Never said the river must be crossed today. |
| The Candle That Lasted Longest | Never said the candle must be lit. |

All three pass `scripts/validate_script.py --format rule-of-three`.

## Self-check before answering

Answer these as a viewer, not as the writer. If any answer is "no", fix the story, not just the wording.

1. **Opening:** would the first sentence stop someone from swiping?
2. **Curiosity:** at every beat, is there a question the viewer still needs answered?
3. **Clarity:** could a listener with basic English follow it by ear? Is the word the ending rests on a basic word?
4. **Pacing:** is any sentence only explaining? Cut it.
5. **Ending:** does the last line add something new?
6. **Fair:** read the rule word by word. Does the winner break none of it? Did the viewer get every fact needed?

Then check the fixed parts: 115-132 words in total, no sentence over 14 words, no contractions, the extra fields filled in, and only the JSON object in the output.

In the repository, run `python3 -I scripts/validate_script.py --format rule-of-three <file.json>` to check a generated script.
