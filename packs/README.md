# packs/

Put the character pack here. It is not part of this project's ZIP or git history.

```
packs/release_1.zip          <- copy the original ZIP here, then run:  python tools/clip.py setup
packs/release_1/             <- setup extracts it here; this folder is what the pipeline reads
    README.md  docs/  reference/  style/
    library/registry.json  library/chars/*.blend  library/accessories/*.blend  library/anims/*.fbx
    blender/py/character_factory.py  clay_look.py  mixamo_retarget.py
    blender/smoke_test.py
```

The pipeline never writes into the pack. To use a newer pack release, extract it to `packs/<name>/` and set `CLAY_PACK=<path>` in `.env`.
