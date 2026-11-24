"""action_media.py - frames of one action test -> a frame strip PNG (every 2nd frame) and an MP4 at full speed.

    py -3 action_media.py <out dir> <Char> <action__view_face> [--step 2] [--cols 12] [--keep-frames]
    py -3 action_media.py <out dir> <Char> --all
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sheet  # noqa: E402


def one(out: Path, char: str, tag: str, step=2, cols=12, keep=False, scale=150, fps=24):
    fd = out / char / "frames" / tag
    frames = sorted(fd.glob("*.png"))
    if not frames:
        return False
    strip = out / char / f"{tag}.strip.png"
    sheet.make(frames[::step], strip, cols=cols, scale=scale, title=f"{char}  {tag}  ({len(frames[::step])} frames, every 2nd frame of the motion)")
    mp4 = out / char / f"{tag}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(fd / "%04d.png"), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(mp4)], check=True)
    if not keep:
        shutil.rmtree(fd, ignore_errors=True)
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("char")
    ap.add_argument("tag", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--cols", type=int, default=12)
    ap.add_argument("--keep-frames", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    tags = [d.name for d in sorted((out / a.char / "frames").iterdir())] if a.all else [a.tag]
    for t in tags:
        print("media", a.char, t, one(out, a.char, t, a.step, a.cols, a.keep_frames))
