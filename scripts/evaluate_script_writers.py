"""Generate unedited before/after samples with the same Claude Code settings."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BASELINE_REVISION = "266894b8861bedb82ff45565289175690e41b236"
TOPICS = {
    "unspoken-rules": "A night shift at an otherwise empty laundromat.",
    "slow-burn": "At a crowded train station, a janitor takes a little girl's red suitcase and walks away.",
    "rule-of-three": "A village baker offers her shop to one of three apprentices. Set the challenge in and around the bakery.",
}
OPTIONS = [
    "-p", "--model", "opus", "--effort", "high", "--safe-mode", "--tools", "",
    "--strict-mcp-config", "--no-session-persistence", "--output-format", "json",
]


def digest(contents):
    return hashlib.sha256(contents).hexdigest()


def write_new(path, contents):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(contents)


def source(path, phase):
    if phase == "before":
        return subprocess.check_output(["git", "show", f"{BASELINE_REVISION}:{path}"], cwd=ROOT)
    return (ROOT / path).read_bytes()


def writer_prompt(fmt, topic, phase):
    skill = f".claude/skills/script-{fmt}"
    producer = source(".claude/skills/gen-clip/SKILL.md", phase).decode("utf-8").replace("\r\n", "\n")
    script_stage = producer.split("## 2. Script\n", 1)[1].split("\n## 3. Direction", 1)[0]
    writer = source(f"{skill}/SKILL.md", phase).decode("utf-8")
    sections = [f"Write one complete {fmt} script. Idea: {topic}", "## Producer's script stage", script_stage]
    if "script-development.md" in writer:
        guide = source(".claude/skills/script-development.md", phase).decode("utf-8")
        sections.extend(["## Shared script development", guide])
    sections.extend([
        "## Selected writer", writer,
        "## Writer's reference examples", source(f"{skill}/references/examples.json", phase).decode("utf-8"),
        "Perform the writing and review instructions here. The caller handles file operations and validation. "
        "Return only the complete script JSON object. Stop before direction, audio, or video production.",
    ])
    return "\n\n".join(sections)


def cli_result(claude, prompt):
    with tempfile.TemporaryDirectory(prefix="shorts-writer-eval-") as working_dir:
        result = subprocess.run(
            [claude, *OPTIONS], input=prompt, cwd=working_dir,
            capture_output=True, encoding="utf-8", timeout=240,
        )
    if not result.stdout.strip():
        raise RuntimeError(f"Claude Code exited with {result.returncode}: {result.stderr.strip()}")
    response = json.loads(result.stdout)
    if result.returncode or response.get("is_error"):
        raise RuntimeError(response.get("result") or response.get("subtype") or result.stderr.strip())
    return response


def generate(claude, phase, fmt, output, validator):
    story_path = output / f"{fmt}.json"
    if story_path.exists():
        raise FileExistsError(f"Sample already exists: {story_path}")
    topic = TOPICS[fmt]
    prompt = writer_prompt(fmt, topic, phase)
    for attempt in (1, 2):
        response = cli_result(claude, prompt)
        raw = response["result"].strip()
        fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.S | re.I)
        story_text = fence[1] if fence else raw
        try:
            if not isinstance(json.loads(story_text), dict):
                raise ValueError("Expected one JSON object")
        except ValueError as error:
            failure = str(error)
        else:
            candidate = output / f"{fmt}.candidate.json"
            write_new(candidate, story_text + "\n")
            validation = subprocess.run(
                [sys.executable, "-X", "utf8", "-I", str(validator), "--format", fmt, candidate.name],
                cwd=output, capture_output=True, text=True, encoding="utf-8",
            )
            if validation.returncode == 0:
                write_new(story_path, story_text + "\n")
                candidate.unlink()
                metadata = {
                    "phase": phase, "format": fmt, "topic": topic, "attempt": attempt,
                    "options": OPTIONS, "resolved_models": list(response.get("modelUsage", {})),
                    "prompt_sha256": digest(prompt.encode("utf-8")),
                    "story_sha256": digest(story_path.read_bytes()),
                    "validator_sha256": digest(validator.read_bytes()),
                    "validator_result": validation.stdout.strip().replace(candidate.name, story_path.name),
                }
                write_new(output / f"{fmt}.run.json", json.dumps(metadata, indent=2) + "\n")
                print(f"{phase} {fmt}: {metadata['validator_result']}", flush=True)
                return
            candidate.unlink()
            failure = validation.stdout.strip() or "The validator could not read the script structure."
        write_new(output / f"{fmt}.rejected-{attempt}.txt", raw + "\n\nValidation:\n" + failure + "\n")
        prompt += f"\n\n## Previous attempt\n{raw}\n\nCorrect these validation errors and return the script JSON.\n{failure}"
    raise RuntimeError(f"{phase} {fmt} failed validation twice. See the rejected attempts in {output}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"), help="original revision or current working files")
    parser.add_argument("formats", nargs="*", metavar="FORMAT")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "script-writer-evaluation")
    args = parser.parse_args()
    formats = args.formats or list(TOPICS)
    if unknown := set(formats) - TOPICS.keys():
        parser.error(f"Unknown evaluation format: {', '.join(sorted(unknown))}")
    claude = shutil.which("claude")
    if claude is None:
        parser.error("Claude Code CLI is not on PATH")
    output = (args.output / args.phase).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shorts-validator-") as working_dir:
        validator = Path(working_dir) / "validate_script.py"
        validator.write_bytes(source("scripts/validate_script.py", args.phase))
        for fmt in formats:
            generate(claude, args.phase, fmt, output, validator)


if __name__ == "__main__":
    main()
