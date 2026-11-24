"""Tile PNG/JPG frames into one labelled contact sheet with FFmpeg (stdlib only).

    py -3 work/tools/sheet.py --out sheet.png --cols 6 [--scale 240] [--label] [--title "text"] a.png b.png ...
    py -3 work/tools/sheet.py --out sheet.png --cols 6 --glob "dir/*.png"

--label stamps each cell with its file stem. Cells keep the order given (globs are sorted).
"""
import argparse
import glob
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FONT = "C\\:/Windows/Fonts/arialbd.ttf"


def esc(s: str) -> str:
    return s.replace("\\", "/").replace(":", "\\:").replace("'", "").replace(",", "\\,").replace("%", "\\%")


def make(files, out, cols=6, scale=240, label=False, title=None, labels=None, pad=2, bg="white"):
    files = [str(f) for f in files]
    if not files:
        raise SystemExit("sheet: no input files")
    ff = shutil.which("ffmpeg") or "ffmpeg"
    tmp = Path(tempfile.mkdtemp(prefix="sheet_"))
    try:
        lst = tmp / "in.txt"
        # the concat demuxer needs same-size frames: normalise each cell first (one ffmpeg per cell is slow, so use
        # a filter graph in batches of rows instead)
        rows = [files[i:i + cols] for i in range(0, len(files), cols)]
        row_imgs = []
        for ri, row in enumerate(rows):
            cmd = [ff, "-v", "error", "-y"]
            for f in row:
                cmd += ["-i", f]
            parts = []
            for ci, f in enumerate(row):
                txt = (labels[ri * cols + ci] if labels else Path(f).stem) if (label or labels) else None
                flt = f"[{ci}:v]scale={scale}:-2,pad=iw+{pad * 2}:ih+{pad * 2}:{pad}:{pad}:{bg}"
                if txt:
                    fs = max(9, scale // 20)
                    flt += (f",drawtext=fontfile='{FONT}':text='{esc(txt)}':x=4:y=4:fontsize={fs}:fontcolor=black:"
                            f"box=1:boxcolor=white@0.75:boxborderw=2")
                parts.append(flt + f"[c{ci}]")
            n = len(row)
            if n > 1:
                parts.append("".join(f"[c{i}]" for i in range(n)) + f"hstack=inputs={n}[o]")
            else:
                parts.append("[c0]copy[o]")
            rp = tmp / f"row{ri:04d}.png"
            cmd += ["-filter_complex", ";".join(parts), "-map", "[o]", "-frames:v", "1", str(rp)]
            subprocess.run(cmd, check=True)
            row_imgs.append(rp)
        # pad short last row, then vstack
        cmd = [ff, "-v", "error", "-y"]
        for rp in row_imgs:
            cmd += ["-i", str(rp)]
        n = len(row_imgs)
        w = cols * (scale + pad * 2)
        parts = [f"[{i}:v]pad={w}:ih:0:0:{bg}[r{i}]" for i in range(n)]
        if n > 1:
            parts.append("".join(f"[r{i}]" for i in range(n)) + f"vstack=inputs={n}[s]")
        else:
            parts.append("[r0]copy[s]")
        if title:
            parts.append(f"[s]pad=iw:ih+34:0:34:{bg},drawtext=fontfile='{FONT}':text='{esc(title)}':x=8:y=7:fontsize=20:fontcolor=black[o]")
        else:
            parts.append("[s]copy[o]")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        cmd += ["-filter_complex", ";".join(parts), "-map", "[o]", "-frames:v", "1", str(out)]
        subprocess.run(cmd, check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--scale", type=int, default=240)
    ap.add_argument("--label", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--glob", default=None)
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    fs = list(a.files) + (sorted(glob.glob(a.glob)) if a.glob else [])
    make(fs, a.out, a.cols, a.scale, a.label, a.title)
    print("sheet", a.out, len(fs))
