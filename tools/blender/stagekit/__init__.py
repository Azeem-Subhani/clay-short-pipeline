"""stagekit - the Blender toolkit of the clay Shorts pipeline (Blender 5.3, EEVEE).

A shot script is a short Python file with one function:

    from stagekit import build, cast, lights, camera, core, assets

    def build_shot(shot):
        ...set, cast, light rig, camera keys, action keyed in seconds...

`tools/clip.py stills|render` runs it inside Blender. See .claude/skills/stagekit/ for the cheat sheet and examples.
"""
from . import assets, build, camera, cast, core, lights, review  # noqa: F401
from .core import begin, current  # noqa: F401

__all__ = ["assets", "build", "camera", "cast", "core", "lights", "review", "begin", "current"]
