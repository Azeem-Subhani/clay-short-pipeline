"""ajkit.paths - where the Aj pack, its hair library and its Mixamo clips live in this project.

The pack scripts held absolute paths into the old working folder (character-rework-v2). Here they are relative to the
project root, which is SHORTS_PROJECT when it is set (the pipeline's tools set it) or three folders above this file.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT = Path(os.environ.get("SHORTS_PROJECT") or os.environ.get("CLAY_PROJECT") or Path(__file__).resolve().parents[2])
PACK = PROJECT / "packs" / "aj_rebuild_v1"                      # the Aj pack (gitignored; open its .blend files read-only)
BASES = PACK / "01_Base_Characters"                             # Aj_Base_Male.blend, Aj_Base_Female.blend
BODIES = PACK / "02_Age_Body_Variants"                          # Aj_<Sex>_<Age>.blend
DRESSED = PACK / "03_Dressed_Variants"                          # Aj_<Sex>_<Age>_dressed.blend
HAIR = PROJECT / "library" / "characters" / "aj" / "hair"       # the hybrid hair library (when it is installed)
CLIPS = PROJECT / "library" / "characters" / "aj" / "mixamo"    # Mixamo clips, FBX, no skin
MEASURED = PROJECT / "library" / "characters" / "aj" / "bodies"   # <Sex>_<Age>.json, written by tools/chars_aj/measure_bodies.py

# names the pack scripts used for the folders above
ROOT = str(PACK)
BASE_FILE = str(BASES / "Aj_Base_Male.blend")
FEMALE_FILE = str(BASES / "Aj_Base_Female.blend")
OUT_DIR = str(BODIES)
ANIM_DIR = str(CLIPS)
