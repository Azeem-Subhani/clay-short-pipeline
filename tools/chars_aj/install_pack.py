"""Install the Aj character pack from its ZIP into packs/aj_rebuild_v1/ and verify every file.

    python tools/chars_aj/install_pack.py [--zip Character_Rebuild_Video_Pipeline.zip] [--check] [--only 02_,09_]

The pack is never committed (packs/* is ignored). Files are verified against the pack's own MANIFEST.csv
(size and SHA-256); a file that is already there and matches is not written again. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ZIP = ROOT / "Character_Rebuild_Video_Pipeline.zip"
DEST = ROOT / "packs" / "aj_rebuild_v1"
PREFIX = "Character_Rebuild_Video_Pipeline/"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest().upper()


def manifest(z: zipfile.ZipFile) -> dict[str, tuple[int, str]]:
    raw = z.read(PREFIX + "MANIFEST.csv").decode("utf-8-sig", "replace")
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        out[row["zip_path"]] = (int(row["bytes"]), row["sha256"].upper())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--zip", default=str(DEFAULT_ZIP))
    ap.add_argument("--check", action="store_true", help="verify what is installed; write nothing")
    ap.add_argument("--only", default="", help="comma-separated folder prefixes to install (default: everything)")
    a = ap.parse_args()

    zpath = Path(a.zip)
    if not zpath.exists():
        print(f"pack ZIP not found: {zpath}", file=sys.stderr)
        return 2
    only = [p for p in a.only.split(",") if p]
    wrote = same = bad = unlisted = 0
    with zipfile.ZipFile(zpath) as z:
        man = manifest(z)
        for info in z.infolist():
            if info.is_dir() or not info.filename.startswith(PREFIX):
                continue
            rel = info.filename[len(PREFIX):]
            if only and not any(rel.startswith(p) for p in only):
                continue
            target = (DEST / rel).resolve()
            if DEST.resolve() not in target.parents:          # never write outside the pack folder
                print(f"skipped (path leaves the pack folder): {rel}", file=sys.stderr)
                bad += 1
                continue
            want = man.get(info.filename)
            if want is None:
                unlisted += 1
            if target.exists() and target.stat().st_size == info.file_size and (want is None or sha256(target) == want[1]):
                same += 1
                continue
            if a.check:
                print(f"missing or different: {rel}")
                bad += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, target.open("wb") as dst:
                for block in iter(lambda: src.read(1 << 20), b""):
                    dst.write(block)
            if want is not None and (target.stat().st_size != want[0] or sha256(target) != want[1]):
                print(f"CHECKSUM MISMATCH: {rel}", file=sys.stderr)
                bad += 1
                continue
            wrote += 1
    print(f"pack: {DEST}")
    print(f"written {wrote}, already there {same}, not in manifest {unlisted}, problems {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
