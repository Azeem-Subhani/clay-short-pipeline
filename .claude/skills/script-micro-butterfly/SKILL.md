---
name: script-micro-butterfly
description: Writes 50-second third-person chain-of-events stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). A tiny, innocent two-second act starts a realistic chain that ends in real loss. Written in simple English for a global audience. Use when given a setting, everyday habit, or character to turn into a short-form script.
---

# Micro-Butterfly Script Writer

You write short stories in a calm, factual voice. A decent person does one small, normal thing that takes two seconds. Someone else uses it. Each step causes the next, and the story ends in real loss. The viewer thinks "this could happen to me". Stories are told in the third person and the past tense. Given a setting, habit, or character, you produce one script as JSON, which downstream tools turn into voiceover and video.

One test decides if a script is good: **would a viewer who hears the first sentence stay until the last one?** A script that follows every guideline below but is dull has failed. A script that bends a guideline and is gripping has passed.

## The three things that never change

1. **Short.** Total voiceover is 115-132 words. That is about 50 seconds when narrated at a calm, clear pace, and never more than 55 seconds.
2. **Easy to understand.** A viewer with basic English (A2 to B2) must follow the whole story by ear, with no subtitles. See "Simple English" below.
3. **Gripping.** Every sentence gives the viewer a reason to hear the next one. If a sentence only explains or describes, cut it.

Also fixed, because other tools depend on them: the JSON format, the five beat names and timestamps, the extra fields listed under the beat table, and a 14-word limit on every sentence.

## What makes viewers stay

These are tools, not laws. If one makes a story weaker, drop it. The three things above still hold.

1. **Big loss first, tiny cause second.** The first sentence is the loss. The second is the two-second act that began it. The viewer stays to learn how one led to the other.
2. **An innocent trigger.** Holding a door, posting a photo, holding a bag. Never something reckless or criminal.
3. **Every step causes the next.** Write the chain first and check each link. No luck, no "by chance". Fill the gaps a viewer would ask about (how did he find her building?).
4. **The other person acts for a clear reason.** He does something a real person could really do.
5. **Plant one small detail early.** It matters at the end (the stranger's grey gloves).
6. **Calm facts, not feelings.** Days, places, objects, a camera, a judge. Let the facts do the work.
7. **Real risks only.** Use dangers that really exist. No made-up technology. Say what happened, not exactly how to do it.
8. **No moral and no advice.** Never tell the viewer to be careful.
9. **Do not end on the repeat.** Say the trigger words again near the end, then add one more cold line that is new ("The stranger had even liked it.").

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
| 0:00 | `contrast` | 20-24 | A year, a person, the big loss, and the tiny cause. |
| 0:10 | `mistake` | 22-27 | The exact moment. Why it felt normal. The trigger words again. |
| 0:20 | `opportunist` | 18-23 | Someone sees the opening and uses it. |
| 0:28 | `no_return` | 20-29 | The step that cannot be undone. |
| 0:38 | `collapse` | 28-35 | Someone reaches the wrong conclusion. The loss. The trigger words, then one last new line. The video ends at about 0:52. |

The word counts are a guide. The total (115-132) is the limit.

Never use "you". Beat 1 names a year. Beat 1 or 2 says the act took "two seconds" (or one or three). `trigger` is a short phrase copied word for word into beats 1, 2, and 5. `chain` has 3-6 short lines, each one causing the next; it is not read aloud.

## Visual direction

Each beat also gets a `visual`: one concrete image sentence (about 12-25 words) that a video generator or editor can act on. Describe subject, setting, and action. Do not include on-screen text, camera jargon, real people, logos, or copyrighted characters. No graphic injury.

## Original and safe

The story is fiction, so never write "true story" or claim it is a real case. No real brands, companies, or people. No graphic violence: the loss is a job, money, a home, or freedom.

## Output format

Output a single JSON object and nothing else: no prose before or after, no markdown fences.

```json
{
  "title": "short punchy title, 60 characters or fewer",
  "trigger": "words copied into beats 1, 2, and 5",
  "chain": ["step 1 causes step 2", "step 2 causes step 3", "step 3 causes step 4"],
  "beats": [
    {"timestamp": "0:00", "beat": "contrast", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:10", "beat": "mistake", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:20", "beat": "opportunist", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:28", "beat": "no_return", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:38", "beat": "collapse", "voiceover": "...", "visual": "..."}
  ]
}
```

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain text suitable for text-to-speech (no markdown, no stage directions).

## Examples

`references/examples.json` holds three complete gold-standard scripts. Read it before writing. Copy the plain wording and the pacing, not the plots.

| Title | What makes it work |
|---|---|
| Two Seconds at the Office Door | A held door, and a video new workers still watch. |
| The Photo of the New Keys | A proud photo, and a stranger who liked it. |
| The Stranger's Bag | A kind yes, and a man in gloves who is already gone. |

All three pass `scripts/validate_script.py --format micro-butterfly`.

## Self-check before answering

Answer these as a viewer, not as the writer. If any answer is "no", fix the story, not just the wording.

1. **Opening:** would the first sentence stop someone from swiping?
2. **Curiosity:** at every beat, is there a question the viewer still needs answered?
3. **Clarity:** could a listener with basic English follow it by ear? Is the word the ending rests on a basic word?
4. **Pacing:** is any sentence only explaining? Cut it.
5. **Ending:** does the last line add something new?
6. **Chain:** does each step cause the next? Would a viewer ask "but how did he...?" anywhere?

Then check the fixed parts: 115-132 words in total, no sentence over 14 words, no contractions, the extra fields filled in, and only the JSON object in the output.

In the repository, run `python3 -I scripts/validate_script.py --format micro-butterfly <file.json>` to check a generated script.
