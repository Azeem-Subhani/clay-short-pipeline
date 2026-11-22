# Examples

## `the-ring-in-the-pond/`

One complete clip in the new look (flat 2D cast, real 3D world), made from the `rule-of-three` script *The Ring in the Pond*. Agents read it before their first plan, set or shot. It is a copy of `output/clips/the-ring-in-the-pond/`, so the live clip can keep changing while the example stays put.

| File | Made by | Look at it for |
|---|---|---|
| `script.json` | `script-rule-of-three` | the input |
| `shotplan.json` | the director's role | the world (medieval castle garden) and its rules; four pack characters cast and dressed for the period, one colour each; one set with its marks; four shots, one per time of day; twenty views, each starting on the narrator's words with a reason; three setups, including the gate that the ending needs |
| `blender/set_pond_garden.py` | the shot builder's role | marks first (`MARK`), one wide framing shared by every shot (`WIDE`), one light per time of day (`LIGHT`), the pond and gate built so the mechanism can be seen, dressing only at edges and background |
| `blender/sh01.py … sh04.py` | the shot builder's role | cast from the plan; action keyed with `shot.t("…")`; eyes, then face, then body; hands put on things with `reach` and `hold`; views as cuts, travels and pushes; effects on contacts |
| `review/shNN/sheet.png`, `checks.json` | `clip.py stills` | what a builder and a reviewer look at: two stills per view, stamped with the words, safe area and caption band drawn on |
| `timing.json` | `clip.py voice --from-media` | the clock: shot lengths and word times (here taken from an existing recording) |
| `captions.json` | `clip.py assemble` | every caption with its words, frames and scale |
| `animatic.mp4`, `animatic_views.jpg` | `render --quality draft --step 4` + `assemble --tag animatic` + `sample` | the whole pipeline end to end at draft quality |
| `preview_*.png` | `clip.py render … --quality preview --frames N-N` | a few views at half size, closer to what your GPU will give |
| `final_quality_sh04_never_said.jpg` | `clip.py render … sh04 --quality final --frames 300-300` | one frame at the locked delivery settings (with procedural surfaces) |

What the example is **not**: a finished Short. It was rendered in a sandbox with no GPU (quarter resolution, a few samples, every fourth frame, so it plays at 6 pictures a second) and with procedural stand-ins for the scanned surfaces, because ambientCG could not be reached from there. Use it to learn the structure and the staging; judge the final look from your own render.

To render it on your machine, see "Regenerating *The Ring in the Pond*" in the main `README.md`.

## `assets/`

`set_stone_well.py`: a built asset in the new look (real surfaces by name, a period tag, moving parts as children). Copy it as a starting point: `python tools/clip.py asset examples/assets/set_stone_well.py --no-save` previews it.

## `sound/`

`the-boy-in-the-basement.audio-plan.json`: an audio plan (`audio/plan.json`) from the first version of the pipeline, kept as the worked example for the sound designer: one voice direction per beat, effects anchored to words, a music prompt with a shape over time. Sound did not change in the rebuild.
