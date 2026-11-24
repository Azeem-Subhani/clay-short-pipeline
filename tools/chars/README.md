# tools/chars: making and testing characters

Not part of making a clip. These tools build and test the 2D cast itself, in plain test scenes.

| Tool | Does |
|---|---|
| `charloop.py <Name>` | build ONE character from its costume file, pose it, put it beside its reference: the design loop of `docs/CREATING_NEW_CHARACTERS.md` |
| `verifyall.py [--names]` | the pack's verify script, one character per Blender process, in parallel |
| `actiontests.py --names A,B --set core` | perform actions on characters in a test scene, measure every frame, render strips and MP4s (`docs/ADDING_NEW_ACTIONS.md`) |
| `matrix.py` | the whole action test matrix as one resumable queue |
| `make_actions_md.py` | write `docs/ACTIONS.md` from the catalogue and the test verdicts |
| `mkqueue.py build|verify|poses <queue>` | write job queues |
| `jobrun.py run <queue> --limits <limits.json>` | run a queue in parallel, sized to free RAM, VRAM and CPU; resumable; `measure` records a job's peaks |
| `mkproof.py <queue>` | queue the proof renders: ink test, pose sheets, transitions, compare-to-reference, wardrobe |
| `sheet.py`, `action_media.py` | contact sheets and MP4s with FFmpeg |
| `retest.py <out> Char:action:view:face ...` | re-measure a few combinations without pictures and print the worst frames of one check (`--show foot_slide`) |
| `bl/*.py` | the Blender-side scripts the tools above run; `bl/dump_cycle.py` prints a gait cycle's leg curves, `bl/drv_check.py` lists drivers that fell back to Python |

Scratch output goes to `output/_characters/` (not committed). The pack is found through `CAST_PACK` in `.env` or `packs/characters_beta_0_4/`.
Worker counts come from a limits file (`jobrun.py measure <kind> --limits <file> -- <command>` records a job's peak RAM and VRAM; `max_workers` caps a kind). On the 6-core machine this was built on, 3 render workers beside 3 measure workers fill the CPU; the small test renders are CPU-bound, not GPU-bound.
