# Writing a Short people want to finish

Audience retention takes priority over creative conventions. The selected writer defines the experience the viewer came for. Its suggested order, point of view, number of beats, timing, wording, and length are tools for delivering that experience. Change them when it makes the story clearer, more compelling, or more surprising. Keep factual accuracy, platform safety, and the production JSON contract. Use original characters and plots for fiction. Check any material claims about real events or hazards.

## Develop the story

1. **Find the story inside the topic.** With a loose brief, try three materially different opening events and payoffs. Change what the character does, what they risk, or how the outcome happens. Three settings for the same twist are one idea. With a detailed brief, vary the hook and the route to the payoff without overriding the user's plot. Pick the idea that raises the sharpest question, gives the character a believable choice under pressure, and pays off something the viewer can see. Use reference scripts to study craft after finding your own premise. Replace a premise that mainly reuses an example's plot, signature props, or turn.
2. **Trace the parts that earn their place.** In a few private lines, write what happens, why it happens, and what changes for the viewer. Name the exact action and observable outcome at the biggest turn. Set up whatever the payoff depends on early enough to feel fair. If taking away a prop, rule, or attempt leaves the ending equally easy to reach and costs no tension, cut it or give it a job. Let viewers speculate about the truth while keeping the immediate action and stakes clear.
3. **Draft for an international audience.** Use everyday spoken English and keep one main action per sentence at fast or important moments. Call each person and key object by the same name. Repeat a name when a pronoun could mean two people. Use literal wording for rules, choices, and consequences so an idiom or a rare word can't hide the plot. Clearly announce any jump in time or place. Open on a concrete event and give listeners a reason to stay as the situation changes. Aim for roughly a minute at Alex's natural 177 WPM. Leave room for pauses and a final hold within `style/style.json`'s actual video limit.
4. **Check that the story works on one listen.** Read only the voiceover aloud once at the intended pace. For each turn, ask who acted, what they did, and what changed because of it. At the end, ask what happened and which detail lets the listener understand it. If an answer requires the title, visuals, metadata, a replay, or a guess about who a pronoun means, revise the voiceover. State the decisive action and its result in simple words. Keep the surprise or source of danger mysterious where it serves the story, while making events and consequences easy to follow.
5. **Review the story for attention and payoff.** Identify the first line where attention is likely to drop, what the viewer expects before the ending, and which early detail makes the ending work. Fix the scene or replace the premise if the hook is generic, the middle coasts, or the payoff is weak. End when the payoff is clear. Review format-specific failure modes in the selected writer before delivery.

## Production JSON

Return one object with `title` and a nonempty `beats` array in narration order. Each beat has an informative `beat` label, an approximate `timestamp` in `M:SS` starting at `0:00` and increasing, plain spoken `voiceover`, and a concrete `visual` for the decisive action, clue, or reaction. Start times are rough orientation. Voice alignment will set the real timings. Put neither headings nor delivery tags in the narration. Keep visuals legible and avoid spoiling a reveal ahead of the voice.

```json
{
  "title": "Story title",
  "beats": [
    {"timestamp": "0:00", "beat": "opening", "voiceover": "Spoken opening.", "visual": "Observable opening action."},
    {"timestamp": "0:08", "beat": "next_turn", "voiceover": "Continue the story.", "visual": "The next decisive action."}
  ]
}
```

The selected writer lists optional notes for direction. Include those that describe what the actual draft does. Save only the story JSON. Keep the candidates, causal outline, and review out of the narration and JSON. Run `python -I scripts/validate_script.py --format <format> <file.json>` when saving in the repo. Passing proves the file is usable by production. The listening review decides whether the script is ready to produce.
