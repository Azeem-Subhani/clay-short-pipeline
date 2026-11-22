# packs/

Put the 2D character pack here. It is not part of this project's ZIP or git history.

```
packs/characters_beta_0_3.zip     <- copy your ZIP here, then run:  python tools/clip.py setup
packs/characters_beta_0_3/        <- setup extracts it here; this folder is what the pipeline reads
    characters_beta_0.3/character-library_v3d.blend      the 28 characters (collections CH_<Name>)
    characters_beta_0.3/textures/ ...                    whatever else the pack ships
```

The pipeline only reads the `character-library*.blend` (it appends characters from it and never writes into it).

- A pack kept somewhere else: set `CAST_PACK=<folder or .blend>` in `.env`.
- A newer pack version: extract it next to the old one and point `CAST_PACK` at it, then run `python tools/clip.py cast --rescan`. That lists every character with its parts and colours and tells you which names are new, so you can add them (with their periods) to `config/cast.json`.
