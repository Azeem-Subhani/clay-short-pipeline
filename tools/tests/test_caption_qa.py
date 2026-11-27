"""The caption measurement in tools/qa.py: correct captions pass over any picture, faulty ones fail.

    py -3 tools/tests/test_caption_qa.py          (plain Python plus FFmpeg; also collected by pytest)

Each case draws a 1080x1920 frame with FFmpeg (white bold text with a dark outline, like the Remotion captions, over a chosen
picture), encodes it as a short H.264 clip so compression blur is there too, and runs qa.check_caption_placement on it with
six captions. The picture cases that must pass: a dark picture, a white (frosted) band behind and beside the text, and a white
page behind the whole line. The faults that must fail: two lines, a caption shifted off centre, a caption pushed out of the
Shorts safe area. Needs a bold system font (Arial Bold on Windows, DejaVu Sans Bold on Linux).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.dont_write_bytecode = True

import qa  # noqa: E402
from common import STYLE, which_ffmpeg  # noqa: E402

W, H = 1080, 1920
FONT_PX = 84
CY = 0.705                                                         # the caption line (style.json captions.center_y_fraction)
STYLE_ROW = {"fontSizePx": FONT_PX, "centerXFraction": 0.5, "centerYFraction": CY}
LINE_Y = int(CY * H)
FONTS = ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]


def font() -> str:
    for f in FONTS:
        if Path(f).exists():
            return f.replace(":", "\\:")                            # FFmpeg filter syntax: a colon in the path is escaped
    raise SystemExit("no bold system font found for the caption test")


def make_clip(path: Path, text: str, picture: list[str], x_expr: str = "(w-text_w)/2", lines: int = 1) -> None:
    """A 2 s clip: grey-blue picture + `picture` drawbox filters + the caption text with a 7 px dark outline."""
    txt = path.with_suffix(".txt")
    txt.write_text(text.replace("|", "\n"), encoding="utf-8")
    y = f"{LINE_Y}-text_h/2"
    vf = ",".join(["format=rgb24"] + picture + [
        f"drawtext=fontfile='{font()}':textfile='{txt.name}':fontsize={FONT_PX}:fontcolor=white:borderw=7:bordercolor=0x111016:x={x_expr}:y={y}:line_spacing=6"])
    subprocess.run([which_ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x3a4a58:s={W}x{H}:r=24:d=2", "-vf", vf,
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(path.name)], cwd=path.parent, check=True)


def measure(path: Path):
    caps = [{"text": "x", "start": 0.2 + 0.25 * i, "end": 0.5 + 0.25 * i} for i in range(6)]
    facts, fails, warns = {}, [], []
    qa.check_caption_placement(path, caps, STYLE_ROW, facts, fails, warns)
    return facts, fails, warns


def band(x0: int, x1: int, y0: int, y1: int, color: str = "white") -> str:
    return f"drawbox=x={x0}:y={y0}:w={x1 - x0}:h={y1 - y0}:color={color}:t=fill"


def run_cases() -> list[tuple[str, bool, str]]:
    tmp = Path(tempfile.mkdtemp(prefix="capqa_"))
    results = []

    def case(name: str, expect_pass: bool, text: str, picture: list[str], **kw):
        p = tmp / f"{name}.mp4"
        make_clip(p, text, picture, **kw)
        facts, fails, warns = measure(p)
        # a clean pass has no failure and no warning about this caption line
        ok = (not fails and not warns) if expect_pass else bool(fails)
        results.append((name, ok, f"expected {'PASS' if expect_pass else 'FAIL'}; fails={fails} warns={warns} box={facts.get('caption_placement')}"))

    case("correct_over_dark", True, "at the front", [])
    case("correct_over_white_band_behind", True, "flashed", [band(0, W, LINE_Y - 150, LINE_Y + 150, "white")])          # frosted band right through the line
    case("correct_over_white_beside", True, "at the front", [band(700, W, LINE_Y - 300, LINE_Y + 300), band(0, 120, LINE_Y - 300, LINE_Y + 300)])
    case("correct_over_white_page", True, "at the front", [band(0, W, 0, H)])
    case("correct_over_white_above_and_below", True, "a top-performing", [band(0, W, LINE_Y - 400, LINE_Y - 70), band(0, W, LINE_Y + 70, LINE_Y + 400)])
    case("fault_two_lines", False, "the whole|office", [])
    case("fault_shifted_off_centre", False, "at the front", [], x_expr="(w-text_w)/2+160")
    case("fault_outside_safe_area", False, "a top-performing", [], x_expr="20")
    return results


def test_caption_measurement():
    bad = [(n, d) for n, ok, d in run_cases() if not ok]
    assert not bad, "\n".join(f"{n}: {d}" for n, d in bad)


if __name__ == "__main__":
    res = run_cases()
    for n, ok, d in res:
        print(("ok   " if ok else "FAIL ") + n + "  " + d)
    sys.exit(0 if all(ok for _n, ok, _d in res) else 1)
