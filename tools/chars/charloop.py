"""charloop.py - the design loop for ONE character: build it alone, pose it, put it next to its reference.

    py -3 work/tools/charloop.py <Name> [--ref <crop.png>] [--poses rest,wave,proud,sit] [--front-only] [--next-to Soldier]

Writes work/out/chars/<Name>/review.png:
    row 1  rest pose: front, three-quarter, side
    rows   one row per pose (front, 3q, side)
    last   the reference crop (if given or found in character_refs/crops_v4/<Name>.png) beside the front view
--front-only  renders just the front rest view (the quick mock before drawing the other two views)
--next-to     also renders <Name> beside an existing character at the same scale (height / proportion check)
Prints the build's errors, LIMB_NOSPLIT and POLY_ISSUES lines. Exit code 1 if the build failed.
Takes about 15 seconds. Several of these can run at once (each character has its own files).
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charpaths as P  # noqa: E402

W = P.TOOLS.parent
BL = P.BL
PACK = P.PACK
sys.path.insert(0, str(P.TOOLS))
import sheet  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--ref", default=None)
    ap.add_argument("--poses", default="rest,wave,proud,sit,carry")
    ap.add_argument("--front-only", action="store_true")
    ap.add_argument("--next-to", default=None)
    ap.add_argument("--px", type=int, default=480)
    a = ap.parse_args()
    n = a.name
    out = P.OUT / "chars" / n
    out.mkdir(parents=True, exist_ok=True)
    blend = P.CHARS / f"{n}.blend"
    plug = [f.name for f in sorted((PACK / "scripts" / "costumes_v4").glob("*.py")) if f'name="{n}"' in f.read_text(encoding="utf-8")]
    extra = ["--plugins", plug[0]] if plug and plug[0] not in ("modern_a.py", "modern_b.py", "fantasy_a.py", "fantasy_b.py") else []
    r = subprocess.run([BL, "-b", "--factory-startup", "--threads", "2", "--python", str(PACK / "scripts" / "build_character_library_v4.py"), "--",
                        "--names", n, "--out", str(blend), "--overwrite", *extra], capture_output=True, text=True, cwd=str(PACK / "scripts"))
    log = r.stdout + r.stderr
    (out / "build.log").write_text(log, encoding="utf-8")
    bad = [ln for ln in log.splitlines() if any(k in ln for k in ("Traceback", "Error", "LIMB_NOSPLIT", "POLY_ISSUES", "  File ", "REFUSING", "SystemExit"))
           and "POLY_ISSUES none" not in ln]
    for ln in bad[:30]:
        print("BUILD:", ln)
    if "SAVED" not in log:
        print(f"BUILD FAILED for {n}: see {out / 'build.log'}")
        return 1
    poses = ["rest"] if a.front_only else a.poses.split(",")
    views = "front" if a.front_only else "front,3q,side"
    zoom = "2.3"
    r = subprocess.run([BL, "-b", "--factory-startup", "--threads", "2", "--python", str(P.TOOLS / "bl" / "pose_sheet.py"), "--", "--pipeline", str(P.PIPELINE), "--char", n,
                        "--pack", str(blend), "--out", str(P.OUT / "chars" / "_frames"), "--px", str(a.px), "--zoom", zoom, "--faces", "right",
                        "--views", views, "--poses", ",".join(poses), "--samples", "12"], capture_output=True, text=True)
    if "POSE_SHEET_DONE" not in r.stdout:
        print("POSE RENDER FAILED:\n" + "\n".join((r.stdout + r.stderr).splitlines()[-25:]))
        return 1
    fr = P.OUT / "chars" / "_frames" / n
    files = [fr / f"{p}__{v}_right.png" for p in poses for v in views.split(",")]
    ref = Path(a.ref) if a.ref else PACK / "character_refs" / "crops_v4" / f"{n}.png"
    cols = len(views.split(","))
    sheet.make(files, out / "poses.png", cols=cols, scale=a.px, label=True)
    parts = [str(out / "poses.png")]
    if ref.exists():
        h = a.px
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ref), "-i", str(fr / "rest__front_right.png"), "-filter_complex",
                        f"[0:v]scale=-2:{h},pad=iw+8:ih:4:0:white[a];[1:v]scale=-2:{h}[b];[a][b]hstack=inputs=2", "-frames:v", "1",
                        str(out / "ref_vs_front.png")], check=True)
        parts.append(str(out / "ref_vs_front.png"))
    if a.next_to:
        nb = P.CHARS / f"{a.next_to}.blend"
        if nb.exists():
            subprocess.run([BL, "-b", "--factory-startup", "--python", str(P.TOOLS / "bl" / "pose_sheet.py"), "--", "--pipeline", str(P.PIPELINE), "--char", a.next_to, "--pack", str(nb),
                            "--out", str(P.OUT / "chars" / "_frames"), "--px", str(a.px), "--zoom", zoom, "--faces", "right", "--views", "front",
                            "--poses", "rest", "--samples", "12"], capture_output=True, text=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(P.OUT / "chars" / "_frames" / a.next_to / "rest__front_right.png"), "-i",
                            str(fr / "rest__front_right.png"), "-filter_complex", "hstack=inputs=2", "-frames:v", "1", str(out / "next_to.png")], check=True)
            parts.append(str(out / "next_to.png"))
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for p_ in parts:
        cmd += ["-i", p_]
    if len(parts) > 1:
        wmax = max(cols * (a.px + 4), 3 * a.px + 16)       # wide enough for the reference pair and the neighbour pair too
        flt = ";".join(f"[{i}:v]pad={wmax}:ih:0:0:white[p{i}]" for i in range(len(parts))) + ";" + "".join(f"[p{i}]" for i in range(len(parts))) + f"vstack=inputs={len(parts)}"
        cmd += ["-filter_complex", flt]
    cmd += ["-frames:v", "1", str(out / "review.png")]
    subprocess.run(cmd, check=True)
    print(f"OK {n}: {out / 'review.png'}" + (f"  ({len(bad)} build message(s) above)" if bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
