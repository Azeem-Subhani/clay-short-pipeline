#!/usr/bin/env python3
"""Validate the production JSON shared by the seven short-script writers.

Usage: python -I scripts/validate_script.py [--format FORMAT] FILE.json [FILE2.json ...]
A file contains one script or a nonempty list of scripts. The CLI returns 1 if any fail.
Without --format, use the format in an output/script-writer/<format>/ path, else twist.
"""
import json
import re
import sys


FORMATS = (
    "twist", "ticking-clock", "slow-burn", "rule-of-three", "reverse-chronology",
    "unspoken-rules", "micro-butterfly",
)
TIME = re.compile(r"([0-9]+):([0-5][0-9])")


def nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def check(script):
    if not isinstance(script, dict):
        return ["script must be an object"]

    errors = []
    if not nonempty_text(script.get("title")):
        errors.append("title must be a nonempty string")
    beats = script.get("beats")
    if not isinstance(beats, list) or not beats:
        return errors + ["beats must be a nonempty list"]

    previous_time = -1
    for number, beat in enumerate(beats, start=1):
        if not isinstance(beat, dict):
            errors.append(f"beat {number} must be an object")
            continue
        for field in ("beat", "voiceover", "visual"):
            if not nonempty_text(beat.get(field)):
                errors.append(f"beat {number}: {field} must be a nonempty string")

        timestamp = beat.get("timestamp")
        match = TIME.fullmatch(timestamp) if isinstance(timestamp, str) else None
        if match is None:
            errors.append(f"beat {number}: timestamp must use M:SS")
            continue
        seconds = 60 * int(match[1]) + int(match[2])
        if number == 1 and timestamp != "0:00":
            errors.append("beat 1: timestamp must be 0:00")
        if seconds <= previous_time:
            errors.append(f"beat {number}: timestamp must increase")
        previous_time = seconds
    return errors


def format_from_path(path):
    parts = path.replace("\\", "/").split("/")
    for parent, child in zip(parts[:-2], parts[1:-1]):
        if parent == "script-writer" and child in FORMATS:
            return child
    return None


def main(argv):
    forced = None
    if argv and argv[0] == "--format":
        if len(argv) < 2 or argv[1] not in FORMATS:
            sys.exit(f"--format must be one of: {', '.join(FORMATS)}")
        forced, argv = argv[1], argv[2:]
    if not argv:
        sys.exit(__doc__)

    failed = False
    for path in argv:
        fmt = forced or format_from_path(path) or "twist"
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as error:
            print(f"FAIL {path} [{fmt}] :: {error}")
            failed = True
            continue
        scripts = data if isinstance(data, list) else [data]
        if not scripts:
            print(f"FAIL {path} [{fmt}] :: list must contain at least one script")
            failed = True
        for script in scripts:
            errors = check(script)
            name = script.get("title", "?") if isinstance(script, dict) else "?"
            if errors:
                print(f"FAIL {path} [{fmt}] :: {name}")
                for error in errors:
                    print("   -", error)
                failed = True
            else:
                words = sum(len(beat["voiceover"].split()) for beat in script["beats"])
                print(f"ok   {path} [{fmt}] :: {name} ({words} words)")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
