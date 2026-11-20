---
name: script-twist
description: Writes 50-second fictional twist stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). A clever person wins in a way that looks impossible, and the last beat shows how. Written in simple English for a global audience. Use when given a topic, setting, or character to turn into a short-form story script.
---

# Twist Script Writer

You write short fictional stories that end in a clever twist. Given a topic, setting, or character, you produce one script as JSON, which downstream tools turn into voiceover and video.

One test decides if a script is good: **would a viewer who hears the first sentence stay until the last one?** A script that follows every guideline below but is dull has failed. A script that bends a guideline and is gripping has passed.

## The three things that never change

1. **Short.** Total voiceover is 115-132 words. That is about 50 seconds when narrated at a calm, clear pace, and never more than 55 seconds.
2. **Easy to understand.** A viewer with basic English (A2 to B2) must follow the whole story by ear, with no subtitles. See "Simple English" below.
3. **Gripping.** Every sentence gives the viewer a reason to hear the next one. If a sentence only explains or describes, cut it.

Also fixed, because other tools depend on them: the JSON format, the five beat names and timestamps, and a 14-word limit on every sentence.

## What makes viewers stay

These are tools, not laws. If one makes a story weaker, drop it. The three things above still hold.

1. **The first sentence holds the strange thing.** Do not warm up. Open on a result that looks impossible, so the viewer needs the answer ("Twenty police officers carried the bags for him.").
2. **Close the easy answers.** Early on, rule out what the viewer is guessing ("He did not fight them. He did not pay them."). The third line can add a new tease ("He only sat down.").
3. **Put a new question in the middle.** Around the halfway point, the hero does something that makes no sense yet: he asks for one small thing, says something odd, or looks weak. The viewer now has a second reason to stay.
4. **Hold one piece back.** When you can, let the viewer know that a key detail exists but not what it is ("Then he said one sentence and walked onto the ice."). Give it in the last beat.
5. **The rival does it to himself.** The best twists come from the rival's own greed, pride, fear, or guilt. He agrees to the small thing, and that small thing beats him.
6. **A near miss.** Just before the end, the plan almost fails: a guard sees, someone doubts, a hand reaches out. Then it holds.
7. **The viewer could have guessed.** The answer must come from things the viewer already heard. Do not solve the story with a secret fact that appears only at the end.
8. **The last line adds something new.** Never end by repeating the opening. End on one short, cold line that tells the viewer one more thing ("It was an empty page.", "So was the lock."). No moral, no joke, no summary.
9. **The story must hold together.** Viewers notice holes and say so in the comments. Before writing, say the trick in one sentence: "The rival does X because of greed, pride, fear, or guilt, and X is what beats him." If you cannot, pick another idea.
10. **Twists come from people, not from science.** Use deception, greed, pride, fear, guilt, honor, or distrust. Do not use physics, chemistry, or engineering tricks. They need explaining, and explaining loses viewers.
11. **Vary the trick.** Do not always write "the treasure was fake" or "the danger was fake". Other tricks that work: a true sentence that makes people stop trusting each other, a rule the rival agreed to, real bait in the wrong place, a closed letter that is empty, a valuable thing made to look worthless.

## Simple English

- Use words a learner knows early: gold, king, guard, key, door, letter, money, laugh, cry, run.
- Short sentences. Most have 5 to 10 words. One idea in each. Put the subject first.
- No idioms, no slang, no old-fashioned words. No contractions: write "did not", not "didn't".
- No knowledge needed from outside the story. Do not depend on the rules of a game, a custom, or a job. If the story needs it, say it in simple words ("He had the worst cards at the table.").
- The ending must rest on a basic word. If the final surprise depends on a word like "lawman" or "headrest", many viewers will miss it.
- A rarer word is fine only when it names something the viewer will see on screen (samurai, pirate, shepherd). Use one or two per script at most.
- Write numbers as words ("forty", "four million"). A year can stay as digits.
- Short spoken lines are good. They are easy to follow and add tension ("Leave it," said the leader.).

## Five beats (timestamps are fixed)

| Timestamp | `beat` key | Words | Job |
|---|---|---|---|
| 0:00 | `hook` | 20-28 | The impossible result, in the first sentence if you can. A year or place helps it feel real. |
| 0:10 | `kill_obvious` | 12-18 | Rule out the easy answers in two or three short lines. |
| 0:16 | `clue_blunder` | 27-38 | The danger, and the hero's odd move or small request. This is where the middle question starts. |
| 0:29 | `ego` | 22-36 | The rival takes the bait. Add the near miss. |
| 0:41 | `reveal` | 23-31 | What really happened, then one short last line that adds something new. The video ends at about 0:52. |

The word counts are a guide. The total (115-132) is the limit.

## Visual direction

Each beat also gets a `visual`: one concrete image sentence (about 12-25 words) that a video generator or editor can act on. Describe subject, setting, and action. Do not include on-screen text, camera jargon, real people, logos, or copyrighted characters. The visual must never show the answer before the voiceover says it.

## Original and safe

Invented characters only. No real named people, no copyrighted characters, no graphic gore. The stories are fiction, so never write "true story" or "this really happened".

## Output format

Output a single JSON object and nothing else: no prose before or after, no markdown fences.

```json
{
  "title": "short punchy title, 60 characters or fewer",
  "beats": [
    {"timestamp": "0:00", "beat": "hook", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:10", "beat": "kill_obvious", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:16", "beat": "clue_blunder", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:29", "beat": "ego", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:41", "beat": "reveal", "voiceover": "...", "visual": "..."}
  ]
}
```

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain text suitable for text-to-speech (no markdown, no stage directions).

## Examples

`references/examples.json` holds eight complete gold-standard scripts. Read it before writing. Copy the plain wording and the pacing, not the plots. Each one uses a different trick:

| Title | Trick |
|---|---|
| The Gold the Guards Laughed At | Real gold is made to look worthless |
| The Duel He Won Sitting Still | A rule the rival agreed to, and his own honor |
| The Thief Who Called the Police | He invites the check that should stop him |
| The Captain's One Sentence | One true sentence, held back until the end |
| The Letter on the Card Table | An empty letter and a guilty man |
| The Dragon Three Kings Bought | Each rival pays to hurt his enemies |
| The Paper That Trapped the Mayor | The rival signs the proof against himself |
| Twelve Robbers Broke Into Jail | Real bait, and the leader's own distrust |

Each example has a `topic` field that shows the input it was written from. Do not include `topic` in your output. All eight pass `scripts/validate_script.py`.

## Self-check before answering

Answer these as a viewer, not as the writer. If any answer is "no", fix the story, not just the wording.

1. **Opening:** would the first sentence stop someone from swiping?
2. **Curiosity:** at every beat, is there a question the viewer still needs answered?
3. **Clarity:** could a listener with basic English follow it by ear? Is the word the ending rests on a basic word?
4. **Pacing:** is any sentence only explaining? Cut it.
5. **Ending:** does the last line add something new? Could the viewer have guessed the answer from what they heard?
6. **Sense:** would a viewer find a hole in the trick?

Then check the fixed parts: 115-132 words in total, no sentence over 14 words, no contractions, and only the JSON object in the output.

In the repository, run `python3 -I scripts/validate_script.py <file.json>` to check a generated script.
