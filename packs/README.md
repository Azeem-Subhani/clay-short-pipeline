# packs/

Put the 2D character pack here. It is not part of this project's ZIP or git history (licensed for use, not redistribution).

```
packs/characters_beta_0_4.zip     <- copy your ZIP here, then run:  python tools/clip.py setup
packs/characters_beta_0_4/        <- setup extracts it here; this folder is what the pipeline reads
    characters_beta_0.4/character-library_v4.blend       the 105 characters (collections CH_<Name>)
    characters_beta_0.4/scripts/                         build, merge, verify, lineup, compare; costumes_v4/ = one file per batch
    characters_beta_0.4/character_refs/                  the style sheets and one crop per character
    characters_beta_0.4/registry/                        hand-written notes of the new characters (merged into config/cast.json)
```

The pipeline reads the `character-library*.blend` (it appends characters from it and never writes into it by hand).

- A pack kept somewhere else: set `CAST_PACK=<folder or .blend>` in `.env`.
- The default pack is **beta 0.4** (`PACK_DIR` in `tools/blender/stagekit/core.py`, `pack` in `config/cast.json`). Beta 0.3 still loads through `CAST_PACK`, but without the 0.4 fixes (rigid limbs, pose-following ink, grip, raised hands in front of the head) and without the run and sneak cycles.
- After a new pack release or a new character: `python tools/cast_registry.py merge <notes.json>`, then `python tools/clip.py cast --rescan` (parts, colours, height and headwear come from the pack; looks, eras, stand-ins, props are kept), then `python tools/cast_registry.py check`.
- A new character is built from its own costume file and merged in without rebuilding the others: the `character-maker` skill and `docs/CREATING_NEW_CHARACTERS.md`.
