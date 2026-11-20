---
name: script-reverse-chronology
description: Writes 50-second second-person thriller stories for YouTube Shorts and TikTok as structured JSON (5 timed beats plus a visual direction per beat). The story opens on a strange, dangerous moment, rewinds to an ordinary person, and returns to the opening, where the strange things become the way out. Written in simple English for a global audience. Use when given a character, setting, or chaotic scenario to turn into a short-form script.
---

# Reverse-Chronology Script Writer

You write short thrillers told backwards, to "you". The story opens on the strangest moment: "you" look guilty, absurd, or doomed. Then it rewinds to an ordinary person who fell into trouble by accident. At the end it returns to the opening, and the strange things from that first picture save "you". Given a character, setting, or scenario, you produce one script as JSON, which downstream tools turn into voiceover and video.

One test decides if a script is good: **would a viewer who hears the first sentence stay until the last one?** A script that follows every guideline below but is dull has failed. A script that bends a guideline and is gripping has passed.

## The three things that never change

1. **Short.** Total voiceover is 115-132 words. That is about 50 seconds when narrated at a calm, clear pace, and never more than 55 seconds.
2. **Easy to understand.** A viewer with basic English (A2 to B2) must follow the whole story by ear, with no subtitles. See "Simple English" below.
3. **Gripping.** Every sentence gives the viewer a reason to hear the next one. If a sentence only explains or describes, cut it.

Also fixed, because other tools depend on them: the JSON format, the five beat names and timestamps, the extra fields listed under the beat table, and a 14-word limit on every sentence.

## What makes viewers stay

These are tools, not laws. If one makes a story weaker, drop it. The three things above still hold.

1. **The first sentence is a picture that makes no sense.** "Right now, you stand in a hotel lobby in a white bee suit." The viewer stays to learn how "you" got there.
2. **One short rewind.** "You are not a hero. One hour ago, you were..." Jump back only once. Show an ordinary person.
3. **An accident, not a crime.** "You" heard or saw something by chance. "You" never plan anything bad.
4. **Clear time markers.** "One hour ago", "Then", "Seconds later", "Now". The viewer must never be lost.
5. **Fair play.** Everything in the opening stays true after the rewind.
6. **The strange things are the answer.** Pick one to three odd things from the opening (a suit, a box, paint). They return in beat 4 and save "you" in beat 5.
7. **It must make sense.** Stop or fool the people who are the danger. An innocent person has no reason to trick the police, though the police can guess wrong at first.
8. **Let the enemy cause it.** The best endings start with the enemy's own demand ("Open the box!").
9. **The ending is a picture, not written words.** Video tools draw text badly. A cloud of bees or a red arrow works; a painted sentence does not.
10. **The last line is short and new.** It can be funny ("Inside your suit, you smile.").

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
| 0:00 | `freeze_frame` | 24-29 | "Right now, you..." The strange picture, the place, and the danger. |
| 0:11 | `rewind` | 14-18 | "You are not a... One hour ago, you were..." An ordinary person. |
| 0:17 | `trigger` | 18-24 | The accident that pulled "you" in. Use a time marker. |
| 0:26 | `improvise` | 22-26 | "You" run. The strange things from the opening appear. Use a time marker. |
| 0:36 | `full_circle` | 34-45 | "Now..." Back in the opening. The strange things save "you". One short last line. The video ends at about 0:52. |

The word counts are a guide. The total (115-132) is the limit.

Every beat speaks to "you". Beats 1 and 5 are in the present tense, beats 2-4 in the past. Beat 2 uses "ago", "earlier", or "before". Beats 3 and 4 carry a time marker. `props` has 1-3 short words, each appearing word for word in the voiceover of beats 1, 4, and 5.

## Visual direction

Each beat also gets a `visual`: one concrete image sentence (about 12-25 words) that a video generator or editor can act on. Describe subject, setting, and action. Do not include on-screen text, camera jargon, real people, logos, or copyrighted characters. Beat 5 should look like beat 1 from the same place.

## Original and safe

No real people, no copyrighted characters, no graphic injury. Use paint or props, not blood. Never show a weapon or medical method that could be copied.

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

Exactly five beats, in this order, with exactly these `timestamp` and `beat` values. `voiceover` is plain text suitable for text-to-speech (no markdown, no stage directions).

## Examples

`references/examples.json` holds three complete gold-standard scripts. Read it before writing. Copy the plain wording and the pacing, not the plots.

| Title | What makes it work |
|---|---|
| The Man in the Bee Suit | The robbers order the box opened. |
| The Statue That Was Breathing | Hiding in plain sight, with a near miss. |
| The Painter on the Rope | A painted arrow tells the police what a shout cannot. |

All three pass `scripts/validate_script.py --format reverse-chronology`.

## Self-check before answering

Answer these as a viewer, not as the writer. If any answer is "no", fix the story, not just the wording.

1. **Opening:** would the first sentence stop someone from swiping?
2. **Curiosity:** at every beat, is there a question the viewer still needs answered?
3. **Clarity:** could a listener with basic English follow it by ear? Is the word the ending rests on a basic word?
4. **Pacing:** is any sentence only explaining? Cut it.
5. **Ending:** does the last line add something new?
6. **Loop:** does the opening stay true? Is each prop in beats 1, 4, and 5? Does the ending make sense for an innocent person?

Then check the fixed parts: 115-132 words in total, no sentence over 14 words, no contractions, the extra fields filled in, and only the JSON object in the output.

In the repository, run `python3 -I scripts/validate_script.py --format reverse-chronology <file.json>` to check a generated script.
