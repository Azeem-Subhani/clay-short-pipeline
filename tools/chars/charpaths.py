"""Where things are, for the character tools (charloop, actiontests, verifyall, mkqueue). Stdlib only.

The same tools run in two layouts:
  the pipeline      <project>/tools/chars/*.py     pack in packs/characters_beta_0_4/characters_beta_0.4 (or CAST_PACK in .env),
                                                   scratch output in <project>/output/_characters/
  the rework folder <work>/tools/*.py              pack in <work>/pack/characters_beta_0.4, pipeline in <work>/clay-short-pipeline,
                                                   scratch output in <work>/out/
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
if (HERE.parent / "clay-short-pipeline").exists():                  # the rework folder
    PIPELINE = HERE.parent / "clay-short-pipeline"
    PACK = HERE.parent / "pack" / "characters_beta_0.4"
    OUT = HERE.parent / "out"
else:                                                               # inside the pipeline: tools/chars/
    PIPELINE = HERE.parents[1]
    OUT = PIPELINE / "output" / "_characters"
    PACK = PIPELINE / "packs" / "characters_beta_0_4" / "characters_beta_0.4"
    env = PIPELINE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("CAST_PACK=") and line.split("=", 1)[1].strip():
                p = Path(line.split("=", 1)[1].strip())
                PACK = p.parent if p.suffix == ".blend" else p
TOOLS = HERE
SCRIPTS = PACK / "scripts"
LIB = PACK / "character-library_v4.blend"
CHARS = OUT / "v4" / "chars"                                        # one .blend per character
QUEUES = OUT / "q"
LIMITS = OUT / "limits.json"
BL = os.environ.get("BLENDER_BIN") or shutil.which("blender") or r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
ORIGINAL_COSTUME_FILES = ("modern_a.py", "modern_b.py", "fantasy_a.py", "fantasy_b.py")
