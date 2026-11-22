"""stagekit - the Blender toolkit of the Shorts pipeline (Blender 5.3, EEVEE): a flat 2D cast staged in a 3D world.

A shot script is a short Python file with one function:

    from stagekit import build, cast, lights, camera, core, fx, mat, assets

    def build_shot(shot):
        ...set, cast, action keyed to the narrator's words, camera views...

`tools/clip.py stills|render` runs it inside Blender. See .claude/skills/stagekit/ for the cheat sheet and
examples/the-ring-in-the-pond/ for a complete film.
"""
from . import assets, build, camera, cast, core, fx, lights, mat, review, wardrobe  # noqa: F401
from .core import begin, current  # noqa: F401

__all__ = ["assets", "build", "camera", "cast", "core", "fx", "lights", "mat", "review", "wardrobe", "begin", "current"]
