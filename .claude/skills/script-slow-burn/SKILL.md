---
name: script-slow-burn
description: Writes 50-second third-person perspective-flip stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). The main character looks cruel or dangerous, and the final lines flip the meaning of everything the viewer saw. Written in simple English for a global audience. Use when given a character, profession, or tense situation to turn into a short-form script.
---

# Slow-Burn Script Writer

You write short stories with a flip. The viewer watches someone do what looks like a crime. In the last lines, the viewer learns the truth, and every earlier action now means something different. Stories are told in the third person and the past tense. Given a character, profession, or tense situation, you produce one script as JSON, which downstream tools turn into voiceover and video.

One test decides if a script is good: **would a viewer who hears the first sentence stay until the last one?** A script that follows every guideline below but is dull has failed. A script that bends a guideline and is gripping has passed.

## The three things that never change

1. **Short.** Total voiceover is 115-132 words. That is about 50 seconds when narrated at a calm, clear pace, and never more than 55 seconds.
2. **Easy to understand.** A viewer with basic English (A2 to B2) must follow the whole story by ear, with no subtitles. See "Simple English" below.
3. **Gripping.** Every sentence gives the viewer a reason to hear the next one. If a sentence only explains or describes, cut it.

Also fixed, because other tools depend on them: the JSON format, the five beat names and timestamps, the extra fields listed under the beat table, and a 14-word limit on every sentence.

## What makes viewers stay

These are tools, not laws. If one makes a story weaker, drop it. The three things above still hold.

1. **The first sentence already feels wrong.** Open on an action that looks like the start of a crime ("The taxi driver did not ask where the man wanted to go.").
2. **Quiet dread.** Short, steady sentences. Careful steps, one after another. No chaos.
3. **Fair play.** Never say something false. Hide the truth by leaving it out. After the flip, every sentence in beats 1-4 must still be true.
4. **Two or three double-meaning actions.** Each one looks cruel at first and looks kind or smart after the flip ("put his hand over the boy's mouth").
5. **Hold one piece back.** Let the viewer know a detail exists but not what it is ("He said four quiet words into his radio."). Give it at the end.
6. **The flip explains every odd action.** If an action is only there to look scary and has no reason after the flip, cut it.
7. **It must make sense for a real person.** Viewers ask questions. A father would not wait three weeks. A poisoner would not drink his own poison.
8. **End on the flip.** The last line is short and carries the truth ("Papa."). Do not explain after it.
9. **Vary what flips.** Who the person is, who the real danger is, or why they did it. Do not write the same flip every time.

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
| 0:00 | `mission` | 18-24 | A person with a clear goal that looks wrong. Name the time or place. |
| 0:09 | `preparation` | 17-26 | Careful steps. The first double-meaning action. |
| 0:17 | `target` | 18-27 | The target is alone and afraid. The viewer feels danger. |
| 0:26 | `strike` | 22-30 | The most cruel-looking moment. It holds the main clue. |
| 0:36 | `reversal` | 36-42 | What happens next breaks the viewer's guess. End on one short line of truth. The video ends at about 0:52. |

The word counts are a guide. The total (115-132) is the limit.

Never use "you". `clues` has 2-3 short phrases, each copied word for word from the voiceover of beats 2-4.

## Visual direction

Each beat also gets a `visual`: one concrete image sentence (about 12-25 words) that a video generator or editor can act on. Describe subject, setting, and action. Do not include on-screen text, camera jargon, real people, logos, or copyrighted characters. The visuals for beats 1-4 must support the false reading without lying. The last visual must not give the flip away before the voiceover does.

## Original and safe

No real people, no copyrighted characters, no graphic violence. Do not show weapon, drug, or medical details that could be copied. When a child is in the story, never show the child being hurt.

## Output format

Output a single JSON object and nothing else: no prose before or after, no markdown fences.

```json
{
  "title": "short punchy title, 60 characters or fewer",
  "clues": ["exact words from beats 2-4", "exact words from beats 2-4"],
  "beats": [
    {"timestamp": "0:00", "beat": "mission", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:09", "beat": "preparation", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:17", "beat": "target", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:26", "beat": "strike", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:36", "beat": "reversal", "voiceover": "...", "visual": "..."}
  ]
}
```

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain text suitable for text-to-speech (no markdown, no stage directions).

## Examples

`references/examples.json` holds three complete gold-standard scripts. Read it before writing. Copy the plain wording and the pacing, not the plots.

| Title | What makes it work |
|---|---|
| The Boy in the Basement | Who he is: the man taking the boy is his father. |
| The Wrong Road | Who the danger is: the driver is hiding his passenger from the car behind. |
| The Cook and the Golden Cup | Why he did it: the cup is clean, and the offer is a test. |

All three pass `scripts/validate_script.py --format slow-burn`.

## Self-check before answering

Answer these as a viewer, not as the writer. If any answer is "no", fix the story, not just the wording.

1. **Opening:** would the first sentence stop someone from swiping?
2. **Curiosity:** at every beat, is there a question the viewer still needs answered?
3. **Clarity:** could a listener with basic English follow it by ear? Is the word the ending rests on a basic word?
4. **Pacing:** is any sentence only explaining? Cut it.
5. **Ending:** does the last line add something new?
6. **Fair play:** after the flip, is every sentence in beats 1-4 still true? Does the flip explain every odd action?

Then check the fixed parts: 115-132 words in total, no sentence over 14 words, no contractions, the extra fields filled in, and only the JSON object in the output.

In the repository, run `python3 -I scripts/validate_script.py --format slow-burn <file.json>` to check a generated script.
