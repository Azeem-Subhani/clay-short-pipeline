"""verifyall.py - run the pack's verify script on characters, one per Blender process, in parallel.

    py -3 verifyall.py [--names A,B]        (default: every character the build knows)

Needs the per-character files (output of charloop.py or of `mkqueue.py build` + jobrun). Prints n/m and each failure.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charpaths as P  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--names", default=None)
a = ap.parse_args()
q = P.QUEUES / "verify.jsonl"
cmd = [sys.executable, str(P.TOOLS / "mkqueue.py"), "verify", str(q)] + (["--names", a.names] if a.names else [])
subprocess.run(cmd, check=True)
for f in (q.with_suffix(".state.json"),):
    if f.exists():
        f.unlink()                       # a verify is always a fresh run
rc = subprocess.run([sys.executable, str(P.TOOLS / "jobrun.py"), "run", str(q), "--limits", str(P.LIMITS)]).returncode
res = {}
for f in sorted((P.OUT / "verify").glob("*.json")):
    res.update(json.loads(f.read_text(encoding="utf-8")))
names = a.names.split(",") if a.names else list(res)
ok = [n for n in names if res.get(n, {}).get("pass")]
print(f"verify: {len(ok)}/{len(names)} pass")
for n in names:
    if n not in ok:
        print("  FAIL", n, "; ".join(res.get(n, {}).get("fails", ["did not run"])[:4]))
sys.exit(0 if len(ok) == len(names) else 1)
