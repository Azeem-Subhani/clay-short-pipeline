"""stagekit - the Blender toolkit of the Shorts pipeline (Blender 5.3, EEVEE): a 3D cast staged in a 3D world.

A shot script is a short Python file with one function:

    from stagekit import build, cast, lights, camera, core, fx, mat, assets

    def build_shot(shot):
        ...set, cast, action keyed to the narrator's words, camera views...

`tools/clip.py stills|render` runs it inside Blender. See .claude/skills/stagekit/ for the cheat sheet and
examples/the-ring-in-the-pond/ for a complete film.

The sets kit (arch, furnish, dress, audit), the camera path checks (campath) and the Aj character modules (cast_aj, aj_rig, aj_face,
aj_hands, aj_clips, aj_wardrobe) are imported when present. A missing or broken optional module does not stop `import stagekit`; its
error is kept in `stagekit.OPTIONAL_MISSING[name]` (and printed to stderr unless the module simply does not exist yet).
"""
import importlib
import sys

from . import assets, build, camera, cast, core, fx, lights, mat, review, viewlight, wardrobe  # noqa: F401
from .core import begin, current  # noqa: F401

OPTIONAL = ("arch", "furnish", "dress", "audit", "campath", "cast_aj", "aj_rig", "aj_face", "aj_hands", "aj_clips", "aj_wardrobe")
OPTIONAL_MISSING: dict = {}                      # name -> "ErrorType: message" for each optional module that did not import
for _name in OPTIONAL:
    try:
        globals()[_name] = importlib.import_module(f".{_name}", __name__)
    except Exception as _e:                      # not written yet, a dependency is missing, or another agent is part-way through editing it
        OPTIONAL_MISSING[_name] = f"{type(_e).__name__}: {_e}"
        if not isinstance(_e, ModuleNotFoundError):
            print(f"[stagekit] warning: optional module '{_name}' did not import ({OPTIONAL_MISSING[_name]})", file=sys.stderr)

__all__ = ["assets", "build", "camera", "cast", "core", "fx", "lights", "mat", "review", "viewlight", "wardrobe", "begin", "current",
           *[n for n in OPTIONAL if n in globals()]]
