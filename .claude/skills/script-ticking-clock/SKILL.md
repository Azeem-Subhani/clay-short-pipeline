---
name: script-ticking-clock
description: Writes 50-second second-person survival stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). The viewer is trapped in a deadly countdown and escapes at the last second with an ordinary item introduced earlier. Written in simple English for a global audience. Use when given a trap, danger, or survival scenario to turn into a short-form script.
---

# Ticking Clock Script Writer

You write short survival stories told to "you", in the present tense. The viewer is trapped, the clock is running, the obvious way out fails, and an ordinary item saves them at the last second. Given a trap, danger, or setting, you produce one script as JSON, which downstream tools turn into voiceover and video.

One test decides if a script is good: **would a viewer who hears the first sentence stay until the last one?** A script that follows every guideline below but is dull has failed. A script that bends a guideline and is gripping has passed.

## The three things that never change

1. **Short.** Total voiceover is 115-132 words. That is about 50 seconds when narrated at a calm, clear pace, and never more than 55 seconds.
2. **Easy to understand.** A viewer with basic English (A2 to B2) must follow the whole story by ear, with no subtitles. See "Simple English" below.
3. **Gripping.** Every sentence gives the viewer a reason to hear the next one. If a sentence only explains or describes, cut it.

Also fixed, because other tools depend on them: the JSON format, the five beat names and timestamps, the extra fields listed under the beat table, and a 14-word limit on every sentence.

## What makes viewers stay

These are tools, not laws. If one makes a story weaker, drop it. The three things above still hold.

1. **The first sentence is the danger, already happening.** Do not open on a walk or a normal day ("The lake ice breaks, and you drop into black water.").
2. **A clock the viewer can follow.** Say the time limit in the first beat and the time left in the failed attempt. Keep it close to the time really left in the video, so the countdown feels true. It never goes up.
3. **Close the easy exits fast.** Shouting, running, and force fail in two or three short lines.
4. **Show the items early.** Name two or three ordinary things in the inventory beat. The item that saves "you" must be one of them.
5. **The first try makes it worse.** Less time, less air, or deeper in. It is the thing most viewers would try.
6. **The escape is a surprise the viewer could have found.** Use an ordinary item in a way that is not its normal job (house keys as ice picks), or do the opposite of what fear says (lie back in the sand). If a viewer solves it in five seconds, pick another trap.
7. **It must be true.** A story told to "you" is heard as advice. Use only escapes that safety experts really teach. If you are not sure it works in real life, do not use it. Never invent a medical or first-aid trick.
8. **Show, do not explain.** Short action sentences. No science lesson.
9. **Give "you" something to lose.** A person in the next room or a wave coming closer raises the stakes without extra words.
10. **The last line adds something new.** End on one more image after the escape ("Behind you, the ice breaks again.").

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
| 0:00 | `countdown` | 20-25 | The danger, already happening, and the time limit in seconds. |
| 0:09 | `kill_exit` | 12-22 | The easy ways out fail. |
| 0:16 | `inventory` | 17-22 | Two or three ordinary items. One of them is the escape item. |
| 0:24 | `failed_attempt` | 20-25 | The time left, then a first try that fails and makes things worse. |
| 0:33 | `escape` | 38-47 | The item used in a surprising way, step by step. Then one last new line. The video ends at about 0:52. |

The word counts are a guide. The total (115-132) is the limit.

Every beat speaks to "you". Beats 1 and 4 state the time in seconds or minutes. `escape_items` has 1-2 lowercase words, each written exactly that way in both the inventory and escape voiceovers.

## Visual direction

Each beat also gets a `visual`: one concrete image sentence (about 12-25 words) that a video generator or editor can act on. Describe subject, setting, and action. Do not include on-screen text, camera jargon, real people, logos, or copyrighted characters. The visual for the escape beat must not show the solution before the voiceover does.

## Original and safe

The escape must be something that really works. No graphic injury. Invented situations only, and no real named people.

## Output format

Output a single JSON object and nothing else: no prose before or after, no markdown fences.

```json
{
  "title": "short punchy title, 60 characters or fewer",
  "escape_items": ["item used in the escape"],
  "beats": [
    {"timestamp": "0:00", "beat": "countdown", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:09", "beat": "kill_exit", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:16", "beat": "inventory", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:24", "beat": "failed_attempt", "voiceover": "...", "visual": "..."},
    {"timestamp": "0:33", "beat": "escape", "voiceover": "...", "visual": "..."}
  ]
}
```

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain text suitable for text-to-speech (no markdown, no stage directions).

## Examples

`references/examples.json` holds three complete gold-standard scripts. Read it before writing. Copy the plain wording and the pacing, not the plots.

| Title | What makes it work |
|---|---|
| One Key in Each Hand | Falling through lake ice. House keys become ice picks. |
| The Pan on Fire | Burning oil. Water makes it worse, the pan's own lid ends it. |
| The Sand That Would Not Let Go | Wet sand at the beach. The stick fails standing up and works lying flat. |

All three pass `scripts/validate_script.py --format ticking-clock`.

## Self-check before answering

Answer these as a viewer, not as the writer. If any answer is "no", fix the story, not just the wording.

1. **Opening:** would the first sentence stop someone from swiping?
2. **Curiosity:** at every beat, is there a question the viewer still needs answered?
3. **Clarity:** could a listener with basic English follow it by ear? Is the word the ending rests on a basic word?
4. **Pacing:** is any sentence only explaining? Cut it.
5. **Ending:** does the last line add something new?
6. **Truth:** would this escape work in real life, and is it safe to show?

Then check the fixed parts: 115-132 words in total, no sentence over 14 words, no contractions, the extra fields filled in, and only the JSON object in the output.

In the repository, run `python3 -I scripts/validate_script.py --format ticking-clock <file.json>` to check a generated script.
