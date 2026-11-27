# The 3D cast (pointer)

This file used to describe a cast of 92 standard characters built from sheets (`config/cast3d.json`, `config/cast3d_custom.json`, `library/hair/`). That cast was removed on purpose.

The cast is now the **Aj family**: eight bodies on an unmodified Mixamo skeleton, a drawn mouth, real fingers, hair from the hair library, and outfits from a fit-checked wardrobe. 32 starter characters exist, all `modern`.

- How to use, act with, add to and trust the cast, and its known limits: [`docs/CHARACTERS_3D.md`](docs/CHARACTERS_3D.md)
- What each body may wear, where every piece came from, its licence, and the reviewers' verdicts: [`library/wardrobe/README.md`](library/wardrobe/README.md) and `library/wardrobe/reports/`
- The registry (bodies, characters, limits): [`config/cast.json`](config/cast.json); `py -3 tools/clip.py cast` lists it
- Adding a person, a garment or a Mixamo clip: `.claude/skills/character-maker/SKILL.md`
- Installing the character pack on a new machine: `py -3 tools/chars_aj/install_pack.py` (see "Installing the pack" in `docs/CHARACTERS_3D.md`)

`config/cast3d*.json` are empty now, and `tools/chars3d/` (the old sheet tools, apart from `action_test3d.py`, which `qa.py` still runs) is left over from that cast: do not add characters there. The Aj actor (`tools/blender/stagekit/cast_aj.py`) builds on `cast3d.Actor3D`, which is why the actor API did not change.
