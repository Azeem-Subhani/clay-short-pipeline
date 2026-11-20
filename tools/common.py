"""Shared helpers for the pipeline tools: paths, config, .env, word handling, subprocess wrappers.
Standard library only."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = json.loads((ROOT / "style" / "style.json").read_text(encoding="utf-8"))
FPS = STYLE["video"]["fps"]
FORMATS = ("twist", "ticking-clock", "slow-burn", "rule-of-three", "reverse-chronology", "unspoken-rules", "micro-butterfly")


def load_env():
    """Read KEY=value lines from .env into the environment (existing variables win)."""
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def clip_dir(arg: str) -> Path:
    """Accept a slug or a path."""
    p = Path(arg)
    if not p.exists():
        p = ROOT / "output" / "clips" / arg
    if not p.is_dir():
        raise SystemExit(f"clip folder not found: {arg} (looked in output/clips/)")
    return p.resolve()


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:48].strip("-") or "clip"


# ----------------------------------------------------------------------------- words
TAG = re.compile(r"\[[^\[\]]*\]")
BREAK = re.compile(r"<break[^>]*>", re.I)


def strip_tags(text: str) -> str:
    """Remove ElevenLabs audio tags and SSML breaks: what is left is what the narrator SAYS."""
    return re.sub(r"\s+", " ", BREAK.sub(" ", TAG.sub(" ", text))).strip()


def norm_word(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower().replace("\u2019", "'")).strip("'")


def words_of(text: str) -> list[str]:
    """Spoken words, normalised for comparison (case, punctuation and curly quotes do not matter)."""
    return [norm_word(w) for w in display_words(text)]


def display_words(text: str) -> list[str]:
    """Words as they should appear in captions (punctuation kept)."""
    return [w for w in strip_tags(text).split(" ") if norm_word(w)]


def script_voiceover(script: dict) -> str:
    return " ".join(b["voiceover"].strip() for b in script["beats"])


# ----------------------------------------------------------------------------- external programs
def which_ffmpeg() -> str:
    exe = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg not found: install it or set FFMPEG_BIN in .env")
    return exe


def which_ffprobe() -> str:
    exe = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
    if not exe:
        raise SystemExit("ffprobe not found: it ships with ffmpeg")
    return exe


def blender_cmd() -> list[str]:
    """How to run a Python script inside Blender on this machine.
    BLENDER_BIN (.env) > blender on PATH > usual install folders > the `bpy` Python module (pip install bpy)."""
    exe = os.environ.get("BLENDER_BIN") or shutil.which("blender")
    if not exe:
        cands = []
        if sys.platform == "win32":
            for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", "")):
                if base:
                    cands += sorted(Path(base).glob("Blender Foundation/Blender */blender.exe"), reverse=True)
        elif sys.platform == "darwin":
            cands += [Path("/Applications/Blender.app/Contents/MacOS/Blender")]
        else:
            cands += sorted(Path("/opt").glob("blender*/blender"), reverse=True) + sorted(Path.home().glob("blender*/blender"), reverse=True)
        exe = next((str(c) for c in cands if Path(c).exists()), None)
    if exe:
        return [exe, "-b", "--factory-startup", "--python-exit-code", "3", "--python"]
    try:
        import importlib.util
        if importlib.util.find_spec("bpy"):
            return [sys.executable]
    except Exception:
        pass
    raise SystemExit("Blender not found: set BLENDER_BIN in .env to blender(.exe) 5.3, or `pip install bpy==5.3.0`")


def run(cmd, check=True, capture=False, cwd=None, env=None, quiet=False):
    if not quiet:
        print("$", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, text=True, capture_output=capture)
    if check and r.returncode != 0:
        if capture:
            sys.stderr.write((r.stdout or "")[-3000:] + (r.stderr or "")[-3000:])
        raise SystemExit(f"command failed ({r.returncode}): {cmd[0]}")
    return r


def ffprobe_json(path) -> dict:
    r = run([which_ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture=True, quiet=True)
    return json.loads(r.stdout)


def audio_seconds(path) -> float:
    return float(ffprobe_json(path)["format"]["duration"])


def db(gain_db: float) -> float:
    return 10 ** (gain_db / 20.0)
