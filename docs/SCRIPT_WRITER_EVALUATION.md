# Script writer evaluation

The user reported difficulty following the new drafts on the first pass. See the [first-listen revisions](#first-listen-revisions) for clearer versions of all three and the change made to the shared writer guide.

## Before-and-after controls

The comparison uses one new script per writer in each phase. Both phases give each writer the same idea, examples, and output request. The prompt changes under evaluation are the producer's script-stage instructions, the selected writer instructions, and any shared writing instructions they load.

| Writer | Idea supplied in both phases |
|---|---|
| `unspoken-rules` | A night shift at an otherwise empty laundromat. |
| `slow-burn` | At a crowded train station, a janitor takes a little girl's red suitcase and walks away. |
| `rule-of-three` | A village baker offers her shop to one of three apprentices. Set the challenge in and around the bakery. |

- Generate baselines while the production prompts and validator are at `266894b8861bedb82ff45565289175690e41b236`. Preserve the generated story files and their checksums before changing the production workflow.
- The saved comparison uses Codex in one conversation for both phases because the sandbox blocked the signed-in Claude Code service. The same assistant executed the writer instructions in both phases and saved its outputs verbatim. The comparison shares conversation history and uses an unblinded editorial review. It measures this set of scripts as a prompt comparison and cannot establish Claude Code performance. The CLI runner is available for a fresh-session replication with Claude Code and Opus.
- Save the first script that passes its phase's production validator. If parsing or validation fails, keep the rejected output and allow one retry with the reported errors. Apply this policy to both phases. Retain the writer's narration verbatim.
- Stop after script generation. Estimate narration duration as whitespace-separated voiceover words divided by 177 WPM, multiplied by 60. Exclude pauses, visual notes, and title text. Treat the duration as an estimate and the WPM as an assumption.

```powershell
python -I scripts/evaluate_script_writers.py before
python -I scripts/evaluate_script_writers.py after
```

For Claude Code replication, `before` loads the original production files from the recorded Git revision, and `after` uses the current working files. The runner passes the relevant prompt and fictional reference material to the service from an empty working directory with tools and project discovery disabled. It uses Opus, high effort, and a fresh request per attempt. Compare the resolved model IDs in the run records. The CLI exposes no sampling seed here. Each phase stores script JSON and run records under `output/script-writer-evaluation/<phase>/`. Saved samples use exclusive writes to preserve the originals. The saved Codex evaluation is under `output/script-writer-evaluation/codex/`.

## Editorial rubric

Score each dimension from 1 to 5. A 1 indicates a major weakness, 3 means it works with a clear weakness, and 5 means the draft earns its effect throughout the relevant beats. Cite a line, choice, or sequence for each judgment.

| Dimension | Evidence to look for |
|---|---|
| Hook | The first sentence gives a concrete, remarkable event or choice and a question the ending can answer. |
| Storytelling | Specific motives, decisions, and visible consequences make the sequence easy to follow. |
| Retention | Point to the likeliest place viewers leave and what changes in each beat to keep them listening. |
| Pacing and flow | The draft reads naturally aloud, gives important turns space, and cuts repeated or incidental information. |
| Suspense and engagement | A viewer has a reason to care and something plausible to anticipate or fear. Humor and anticipation count for lighter stories. |
| Ending and payoff | The last moment delivers on the opening promise and gives an earlier detail a meaningful second use. |
| Entertainment | Judge whether the entire short feels distinctive and worth listening to, including any weak middle or unearned ending. |

Scores are editorial judgments about the scripts. Viewer retention would require audience watch-time data. Three pairs can show how these writers performed under these conditions. Repeated samples across formats would be needed to estimate consistency.

## Baseline audit

All three baselines passed the original validator before the production files changed. Their SHA-256 hashes are recorded in the comparison's `baseline.sha256`.

- **Three Knocks at the Laundromat** opens on a suspicious coat pocket and has a memorable final image. The coat, the disconnected water line, and the wet floor give competing questions. The script spends 114 words on the job and rules before June appears. Her wet shoe makes the breach plausible, but the scene jumps straight from her crossword to the morning discovery. The final knock connects to the first rule without clearly establishing why the front door matters.
- **The Red Suitcase** starts in motion and sets up physical clues, including the janitor carrying the case flat and listening to it. The chase gets stuck when the janitor ignores the key the girl is already holding. After the kitten appears, an explanation of how the suitcase reached the belt interrupts the payoff. The three scratch marks are a stronger ending than the explanation preceding them.
- **One Cut for the Bakery** gives the audience an easy-to-grasp game and ends on a warm joke. The horseshoe is identified in the first sentence as the conspicuous way to cut a single loaf twice. Both first attempts lose for foreseeable reasons and neither helps the audience discover the solution. The performance hinges on how quickly the viewer notices the shape.

The original writers contain thoughtful format-specific advice, but they ask for a finished draft immediately and leave quality to a general self-check. The fixed beat order, repeated trigger words, point-of-view restrictions, and sentence limits are easier to satisfy than the harder creative tasks. Reading the examples first also makes their conventions the first ideas in play. The producer only has a concrete retry loop for schema failures. All three baseline scripts passed that loop with their story-level weaknesses intact.

## Comparison results

| Writer | Baseline words / seconds | Updated words / seconds | Overall editorial score |
|---|---:|---:|---:|
| Unspoken rules | 176 / 59.7 | 165 / 55.9 | 3 → 4 |
| Slow burn | 189 / 64.1 | 151 / 51.2 | 3 → 4 |
| Rule of three | 188 / 63.7 | 170 / 57.6 | 3 → 4 |

All estimates assume 177 WPM. The three updated scripts use four beats each. Two are shorter than the original 170-word minimum. The full JSON files include the visual direction. The narration reproduced here is complete.

### Unspoken rules

#### Before — Three Knocks at the Laundromat

> You get a hundred dollars to sit in an empty laundromat until dawn. The owner gives you three rules, then checks the pockets of a coat he's still wearing.
>
> Rule one: leave the front door locked after midnight. If somebody knocks twice, keep your hands where they are. The knocking stops after the third pair.
>
> Rule two: let washer seven finish its cycle, even if it sounds like somebody kicking the door. The machine doesn't have a water line. It still leaves puddles.
>
> Rule three: never match a sock from washer seven. It'll leave one on your chair, dry and just your size. If the other one's already on your foot, throw it out.
>
> Last winter, June came in with one shoe full of slush. The dry red sock was waiting on her chair. She pulled it on and went back to her crossword. At dawn, the owner found June's empty sneakers under her chair. Washer seven had finished its cycle. Behind the glass, a hand knocked twice. It was wearing both red socks like mittens.

The narration establishes three unusual signals before June enters. The rule she breaks gives her a practical reason to act, but her decision and the aftermath are separated by a jump to dawn. The coat check is vivid and unresolved. The final knock echoes the opening rules without making the outside door important to what happened. [Complete JSON](../output/script-writer-evaluation/codex/before/unspoken-rules.json)

#### After — The Rabbit in the Spin Cycle

> A washer in the empty laundromat pushed a stuffed rabbit out through its lid. Tess knew the crooked safety pin in its ear. She'd closed it herself before they buried her little sister.
>
> The owner had told her to stand on the yellow mat if the lid ever lifted. Tess stepped onto it. Let the washer take back whatever it sends up, he'd said. If it speaks, kill the lights.
>
> She reached for the switch. Then the rabbit said, in Abby's voice, "Tess, don't let go this time." The lid began to close. Tess had let go of that hand once. She put both hands around the rabbit and pulled.
>
> The rabbit slid free. Tess was looking up through the glass. Above her, the rabbit climbed down the side of the washer. It crossed to the yellow mat and climbed up the wall, one paw at a time. Abby's voice said, "Now the lights." Even the paw on the switch had Tess's little thumb scar.

The rabbit appears immediately and prompts a specific question. Tess recognizes an object she buried, then tries to obey until the voice uses her guilt against her. We hear her pull and experience the exchange from her side of the glass. The thumb scar gives the final image a second piece of evidence. The yellow mat still feels more like a staging instruction than a necessary rule, and the fast switch into the washer relies on clear staging. [Complete JSON](../output/script-writer-evaluation/codex/after/unspoken-rules.json)

| Criterion | Before | After | Editorial basis |
|---|---:|---:|---|
| Hook | 3 | 5 | The opening moves from a job offer to an impossible object Tess recognizes. |
| Storytelling | 2 | 4 | The pull leads directly to the switch in positions instead of a jump to discovery. |
| Retention | 2 | 4 | The rabbit and the voice give the viewer a changing question during the rules. |
| Pacing and flow | 3 | 4 | The draft reaches the breach sooner and spends more of the story on Tess. |
| Suspense and engagement | 3 | 5 | Tess has a personal reason to reach for the rabbit after hearing Abby. |
| Ending and payoff | 3 | 4 | The lights rule comes back, and the scar shows whose place the rabbit took. |
| Entertainment | 3 | 4 | The new setup and the final image are more distinctive, although one rule remains loose. |

### Slow burn

#### Before — The Red Suitcase

> The station janitor picked a little girl's red suitcase off the baggage belt and walked straight past her. She chased him, holding a key high above her head. He didn't slow down.
>
> A suitcase could roll right out the front doors without anyone looking twice. He carried this one instead. He held the red case flat against his chest and ducked behind the ticket booths.
>
> The girl reached the passage just as the janitor wedged three fingers through the gap beside the lock. She yelled something over the boarding announcement. A guard came running from the platform.
>
> He set the case on his folded coat and put his ear against the lid. Then he looked right at the girl. The guard grabbed his shoulder. He knocked the man's hand away.
>
> "The key," said the janitor. "I can't hear him scratching anymore." The girl shoved it into the lock. Out came a gray kitten, blinking in the station lights. The baggage clerk had put the case on the belt while she'd run to get her mother. The janitor sat back. Three tiny pink lines crossed the fingers he'd held inside.

The red case is taken in the first sentence. Carrying it level, putting an ear to it, and ending on the scratches give the reversal some fair evidence. The janitor doesn't take the key the girl is already holding, so the chase spends time delaying a simple action. An explanation about the baggage clerk comes between the kitten and the final image. [Complete JSON](../output/script-writer-evaluation/codex/before/slow-burn.json)

#### After — Who Is Alice?

> The janitor took a little girl's red suitcase. When a man shouted, "That's my daughter's," he walked faster.
>
> A thin yellow card was tied to the handle. The janitor folded it into his palm. He carried the case past the exit and kept it low enough for the girl to see. She followed. So did the man. "Alice, wait for Daddy."
>
> The janitor put the case down at the ticket desk and let the girl take it herself. The man squeezed past a line of passengers and put his hand on the handle. "Alice. Tell him who I am." The girl held the other end. She didn't look at him.
>
> "Okay," the girl said. She unzipped the case and pulled out a doll. It wore a yellow card just like the one on the handle. She set it on the counter so it faced him. "Alice," she said, "who's this man?"

The man sounds like a protective father while the janitor appears to steal the case. The yellow card, the man calling her Alice, and the case passing the exit can all be read two ways. The girl ends the ambiguity herself with the doll, without a paragraph of explanation. The title gives a spoiler-sensitive viewer an early lead, and the ending leaves the staff response outside the story. [Complete JSON](../output/script-writer-evaluation/codex/after/slow-burn.json)

| Criterion | Before | After | Editorial basis |
|---|---:|---:|---|
| Hook | 4 | 4 | Both open on the theft. The apparent father's reaction adds a second claim to judge. |
| Storytelling | 3 | 4 | The route past the exit and to the desk supports the reveal with action. |
| Retention | 3 | 4 | The girl's response becomes a live question as the man keeps asserting his claim. |
| Pacing and flow | 4 | 4 | The new draft cuts delay and explanation. Both read smoothly at the assumed cadence. |
| Suspense and engagement | 3 | 4 | The contest over the handle makes the stakes visible and gives the girl a choice. |
| Ending and payoff | 3 | 5 | The doll flips the meaning of the name and ends on the girl's line. |
| Entertainment | 3 | 4 | The reversal is easier to replay in the mind. A viewer who anticipates the doll loses some surprise. |

### Rule of three

#### Before — One Cut for the Bakery

> The village baker set three horseshoe loaves on her counter and put her shop key beside them. Cut a loaf into three equal pieces, she said, and the bakery was theirs.
>
> She put down a long bread knife. "One straight cut with this knife." The apprentices looked at each other. The baker pulled out her old brass scale to weigh the pieces.
>
> The first apprentice took a wild diagonal slash. With his free hand, he caught the falling tip like he'd planned it. The baker put the tip on one pan and waited for a third piece.
>
> The second started smiling halfway through his cut. On the way down, he turned the knife and made a corner. He got three pieces. The baker held up the crooked middle one next to the blade.
>
> The third apprentice put her loaf flat and turned the open end toward her. Then she set the knife across both arms of the horseshoe. One cut dropped two ends, leaving the curve whole. On the scale, each end balanced the curve. The baker slipped the key under one piece. "I suppose that's my share."

The baker's shop key makes the stakes clear and the challenge is easy to follow. Both failures are short, but the horseshoe shape names the solution early, and neither attempt makes the next one smarter. The weighing and the baker's joke give the original a clean finish. [Complete JSON](../output/script-writer-evaluation/codex/before/rule-of-three.json)

#### After — A Penny for the Smell

> On her last morning, the baker set out three hot loaves and took her own name off the shop door. "Back here at noon with this same loaf, whole, and a penny somebody paid you for it. Then the shop is yours."
>
> Ben sold his before he'd even crossed the square. "Can I buy it back at noon?" The customer bit the end off while he was still asking.
>
> Leo held his up at the soup cart. "A penny to smell it!" Six road workers stopped. They leaned right in, sniffed for free, then bought six bowls of soup. Leo hadn't made a penny. The soup seller was scraping his pot.
>
> Inez waited for the soup seller to put a full pot on. Then she set her loaf next to it. "Penny to keep this here till noon." He paid before she took her hands off it. When Inez came back for the loaf, he had people lining up. "Any chance," he said, "I could borrow the whole bakery tomorrow?"

The first try establishes the cost of surrendering the loaf. The second discovers a customer the apprentice overlooked. Inez uses that observation to earn her penny and keep her loaf. The middle now helps solve the puzzle. The original has the clearer verdict, though. The new script ends at the soup cart, so the viewer gets the business joke and infers that Inez wins the shop. [Complete JSON](../output/script-writer-evaluation/codex/after/rule-of-three.json)

| Criterion | Before | After | Editorial basis |
|---|---:|---:|---|
| Hook | 4 | 4 | Both give a concrete prize and a puzzle. The shop sign adds a specific visual. |
| Storytelling | 3 | 4 | The third try follows from what the second demonstrated. |
| Retention | 3 | 4 | Each failure changes the audience's available answers. |
| Pacing and flow | 4 | 4 | Both first attempts are economical. The new version carries the second try forward. |
| Suspense and engagement | 3 | 4 | The village square gives the second failure and the winning choice a social reaction. |
| Ending and payoff | 4 | 4 | The business joke pays off the soup cart. The baseline makes the handover more explicit. |
| Entertainment | 3 | 4 | The new middle earns its runtime and the economic trick belongs to this bakery. |

## Implementation and verification

- [Shared writing guide](../.claude/skills/script-development.md). The writer tries distinct premises, traces the visible cause and effect, drafts for speech, and identifies the likeliest point a viewer would leave. Weak setups go back to development before the JSON is saved.
- [Producer](../.claude/skills/gen-clip/SKILL.md) and [director](../.claude/agents/director.md). The normal entry point runs the editorial pass before creating a clip. The director reads the shared visual guidance. The producer uses the configured delivery limit of 70 seconds and allows a shorter story to finish early.
- [Twist](../.claude/skills/script-twist/SKILL.md), [slow-burn](../.claude/skills/script-slow-burn/SKILL.md), [rule-of-three](../.claude/skills/script-rule-of-three/SKILL.md), [ticking-clock](../.claude/skills/script-ticking-clock/SKILL.md), [reverse-chronology](../.claude/skills/script-reverse-chronology/SKILL.md), [unspoken-rules](../.claude/skills/script-unspoken-rules/SKILL.md), and [micro-butterfly](../.claude/skills/script-micro-butterfly/SKILL.md). All seven use the shared workflow and give specific tests for how their own kind of story can fail.
- [Validator](../scripts/validate_script.py). Validates JSON shape and timestamp order. Beat count, sentence length, point of view, required phrases, and creative metadata are flexible. All 26 reference scripts, all three existing saved scripts, and all six comparison scripts pass.
- [README](../README.md), [project instructions](../CLAUDE.md), and [comparison runner](../scripts/evaluate_script_writers.py). Document the normal writing workflow and how to repeat the comparison against the original revision.

The baseline hashes still match the saved files. All three updated scripts passed `clip.py new` and the offline `voice --estimate` stage with temporary shot plans. The timing check kept every narration word and stayed below the configured video limit. This checks the script handoff and timing compatibility. The four unbenchmarked writers were checked through their prompt wiring and existing references.

The updated drafts performed better overall in these three comparisons. The strongest gains were in the causal middle of the bakery story and the payoff of the station story. The laundromat draft still has a rule with weak story value. The bakery draft would benefit from showing the result of the contest, and the station title may give away more than the narration does. The small, unblinded Codex comparison cannot establish that Claude Code consistently writes better scripts. It also provides no audience watch-time data.

## First-listen revisions

The original review gave too much credit to endings that made sense on rereading. In the laundromat, the story skips the moment Tess is pulled into the washer. At the station, the viewer has to connect the doll, the name on the tag, and the man's claim in one beat. At the bakery, the audience has to infer who wins. Each of these is a fact the first-time listener needs to understand the ending.

- [The Rabbit in the Washing Machine](../output/script-writer-evaluation/codex/clarity-pass/unspoken-rules.json) states what happens when Tess picks up the rabbit and who walks out of the shop.
- [The Red Suitcase at the Station](../output/script-writer-evaluation/codex/clarity-pass/slow-burn.json) lets the girl say who Alice is, why that name is on the bag, and that she does not know the man.
- [A Coin for a Loaf of Bread](../output/script-writer-evaluation/codex/clarity-pass/rule-of-three.json) states the two parts of the challenge separately and shows the winner receiving the key.

These are follow-up revisions to the three stories. The original six benchmark files are preserved. The [shared guide](../.claude/skills/script-development.md) now requires a voiceover-only pass, with everyday wording and a clear cause and result at the decisive moment. Comprehension by an international audience still needs a listener test.
