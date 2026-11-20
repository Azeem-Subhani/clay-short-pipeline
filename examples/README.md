# Examples

## `the-boy-in-the-basement/`

One complete clip, made from the gold `slow-burn` script, to show what each stage produces and how the pieces fit. Agents read it before their first plan, audio plan or shot.

| File | Made by | Look at it for |
|---|---|---|
| `script.json` | `script-slow-burn` | the input |
| `shotplan.json` | the director's role | five long takes, each with a purpose; `why_cut` on every cut; moves and focus shifts tied to the narrator's words; a light story; fair hiding of the man's face |
| `audio/plan.json` | the sound designer's role | one voice direction per beat; effects anchored to words; a music prompt with a shape over time |
| `timing.json` | `clip.py voice --mock` | what the voice step hands to the builders (shot lengths, word times). This one comes from the offline mock narrator, not a real take |
| `blender/set_*.py` | the shot builder's role | one place + one light rig per file |
| `blender/sh01.py … sh05.py` | the shot builder's role | cast from the plan, action keyed with `shot.t("…")`, one camera with a few keys, `shot.moment` for review stills |
| `review/shNN/sheet.png`, `checks.json` | `clip.py stills` | what a builder and a reviewer look at |
| `the-boy-in-the-basement_animatic.mp4`, `animatic_samples.png` | `clip.py render --quality draft --step 12` + `assemble --tag animatic` + `sample` | the whole pipeline end to end at draft quality |
| `final_quality_frame_sh03.png` | `clip.py render … sh03 --quality final --frames 193-193` | what the locked render settings give at full quality: soft shadows, contact shadows, eye catchlight |

What the example is **not**: a finished Short. It was rendered in a sandbox with no GPU (quarter resolution, 8 samples, every 12th frame) and with mock audio (tone blips for the narrator, noise and a pad for sound and music). The sets are sparsely dressed, the carry in sh05 is rough, and the remaining `[check]` lines in `review/*/checks.json` are explained in each shot's notes. Use it to learn the structure; judge the look from your own first render.

To rebuild it on your machine:

```
python tools/clip.py new --script output/script-writer/slow-burn/the-boy-in-the-basement.json --force
# copy examples/the-boy-in-the-basement/{shotplan.json,audio/plan.json,blender/*.py} into output/clips/the-boy-in-the-basement/
python tools/clip.py voice the-boy-in-the-basement          # a real take with your key (or --mock)
python tools/clip.py sound the-boy-in-the-basement
python tools/clip.py stills the-boy-in-the-basement
python tools/clip.py render the-boy-in-the-basement
python tools/clip.py assemble the-boy-in-the-basement && python tools/clip.py qa the-boy-in-the-basement
```

Shot lengths follow your voice take, so the shots re-time themselves: actions are keyed to words.

## `assets/`

Four asset scripts (wire cutters, door key, police car, school bag) that built the starter library in `library/assets/`. Copy one as a starting point for a new built asset: `python tools/clip.py asset <script.py> --no-save` previews it.
