#!/usr/bin/env python3
"""Validate short-script JSON against each skill's hard rules.

Usage: python3 -I scripts/validate_script.py [--format twist|ticking-clock|slow-burn|rule-of-three|reverse-chronology|unspoken-rules|micro-butterfly] FILE.json [FILE2.json ...]
Each file holds one script object, or a list of them.
Without --format, the format comes from an output/script-writer/<category>/ folder in the
path, else defaults to "twist". Exit code 0 = all pass, 1 = any failure.
"""
import json
import re
import sys

MIN_WORDS, MAX_WORDS, MAX_SENTENCE = 115, 132, 14  # about 50 seconds narrated, 55 at most

FORMATS = {
    "twist": {
        "timestamps": ["0:00", "0:10", "0:16", "0:29", "0:41"],
        "beats": ["hook", "kill_obvious", "clue_blunder", "ego", "reveal"],
    },
    "ticking-clock": {
        "timestamps": ["0:00", "0:09", "0:16", "0:24", "0:33"],
        "beats": ["countdown", "kill_exit", "inventory", "failed_attempt", "escape"],
    },
    "slow-burn": {
        "timestamps": ["0:00", "0:09", "0:17", "0:26", "0:36"],
        "beats": ["mission", "preparation", "target", "strike", "reversal"],
    },
    "rule-of-three": {
        "timestamps": ["0:00", "0:09", "0:17", "0:26", "0:36"],
        "beats": ["challenge", "catch", "attempt_one", "attempt_two", "attempt_three"],
    },
    "reverse-chronology": {
        "timestamps": ["0:00", "0:11", "0:17", "0:26", "0:36"],
        "beats": ["freeze_frame", "rewind", "trigger", "improvise", "full_circle"],
    },
    "unspoken-rules": {
        "timestamps": ["0:00", "0:10", "0:18", "0:26", "0:34"],
        "beats": ["hook", "rule_one", "rule_two", "rule_three", "breach"],
    },
    "micro-butterfly": {
        "timestamps": ["0:00", "0:10", "0:20", "0:28", "0:38"],
        "beats": ["contrast", "mistake", "opportunist", "no_return", "collapse"],
    },
}

CONTRACTION = re.compile(r"\b\w+(n't|'re|'ll|'ve|'m|'d)\b", re.I)
YOU = re.compile(r"\byou(r|rs|rself)?\b", re.I)
CLOCK_WORD = re.compile(r"\b(seconds?|minutes?)\b", re.I)
TIME_WORD = re.compile(
    r"\b(then|later|soon|next|after|ago|earlier|before|minutes?|hours?|seconds?)\b", re.I
)


def sentences(text):
    # Split after . ! ? and also after a closing quote that follows one (e.g. coin." Anyone).
    return [s for s in re.split(r'(?<=[.!?]")\s+|(?<=[.!?])\s+', text.strip()) if s]


def check_ticking_clock(script, beats):
    """Extra rules for the ticking-clock format."""
    errs = []
    items = script.get("escape_items")
    if (
        not isinstance(items, list)
        or not 1 <= len(items) <= 2
        or not all(isinstance(i, str) and i.strip() for i in items)
    ):
        errs.append("escape_items must be a list of 1-2 non-empty strings")
        items = []
    inventory = beats[2].get("voiceover", "").lower()
    escape = beats[4].get("voiceover", "").lower()
    for item in items:
        w = item.strip().lower()
        if w not in inventory:
            errs.append(f"escape item {item!r} must appear in the inventory beat (0:20)")
        if w not in escape:
            errs.append(f"escape item {item!r} must be used in the escape beat (0:45)")
    for i, b in enumerate(beats):
        vo = b.get("voiceover", "")
        if not YOU.search(vo):
            errs.append(f"beat {i+1}: must speak to 'you' (second person)")
        if CONTRACTION.search(vo):
            errs.append(f"beat {i+1}: no contractions, write 'did not' not 'didn't'")
    for i in (0, 3):
        if not CLOCK_WORD.search(beats[i].get("voiceover", "")):
            errs.append(f"beat {i+1}: must state the time left (seconds or minutes)")
    return errs


def check_slow_burn(script, beats):
    """Extra rules for the slow-burn format (third person, double-meaning clues)."""
    errs = []
    clues = script.get("clues")
    if (
        not isinstance(clues, list)
        or not 2 <= len(clues) <= 3
        or not all(isinstance(c, str) and c.strip() for c in clues)
    ):
        errs.append("clues must be a list of 2-3 non-empty strings")
        clues = []
    middle = " ".join(b.get("voiceover", "") for b in beats[1:4]).lower()
    for clue in clues:
        if clue.strip().lower() not in middle:
            errs.append(f"clue {clue!r} must appear word for word in beats 2-4")
    for i, b in enumerate(beats):
        vo = b.get("voiceover", "")
        if YOU.search(vo):
            errs.append(f"beat {i+1}: third person only, do not use 'you'")
        if CONTRACTION.search(vo):
            errs.append(f"beat {i+1}: no contractions, write 'did not' not 'didn't'")
    return errs


def check_rule_of_three(script, beats):
    """Extra rules for the rule-of-three format (exact rule wording, three attempts)."""
    errs = []
    rule = script.get("rule")
    if not isinstance(rule, str) or not rule.strip():
        errs.append("rule must be a non-empty string")
    else:
        opening = " ".join(b.get("voiceover", "") for b in beats[:2]).lower()
        if rule.strip().lower() not in opening:
            errs.append("rule must appear word for word in beats 1-2")
    if not isinstance(script.get("loophole"), str) or not script["loophole"].strip():
        errs.append("loophole must be a non-empty string")
    for i, word in ((2, "first"), (3, "second"), (4, "third")):
        if not re.search(rf"\b{word}\b", beats[i].get("voiceover", ""), re.I):
            errs.append(f"beat {i+1}: must say '{word}' so the pattern of three is clear")
    for i, b in enumerate(beats):
        if CONTRACTION.search(b.get("voiceover", "")):
            errs.append(f"beat {i+1}: no contractions, write 'did not' not 'didn't'")
    return errs


def check_reverse_chronology(script, beats):
    """Extra rules for the reverse-chronology format (freeze-frame opener, seamless loop)."""
    errs = []
    props = script.get("props")
    if (
        not isinstance(props, list)
        or not 1 <= len(props) <= 3
        or not all(isinstance(p, str) and p.strip() for p in props)
    ):
        errs.append("props must be a list of 1-3 non-empty strings")
        props = []
    for p in props:
        w = p.strip().lower()
        for i, label in ((0, "the freeze-frame (0:00)"), (3, "the improvise beat (0:33)"), (4, "the full-circle beat (0:48)")):
            if w not in beats[i].get("voiceover", "").lower():
                errs.append(f"prop {p!r} must appear in {label}")
    if not re.search(r"\b(ago|earlier|before)\b", beats[1].get("voiceover", ""), re.I):
        errs.append("beat 2: must jump back in time (use 'ago', 'earlier', or 'before')")
    for i in (2, 3):
        if not TIME_WORD.search(beats[i].get("voiceover", "")):
            errs.append(f"beat {i+1}: must carry a clear time marker (then, later, soon, minutes, seconds...)")
    for i, b in enumerate(beats):
        vo = b.get("voiceover", "")
        if not YOU.search(vo):
            errs.append(f"beat {i+1}: must speak to 'you' (second person)")
        if CONTRACTION.search(vo):
            errs.append(f"beat {i+1}: no contractions, write 'did not' not 'didn't'")
    return errs


MONSTER_WORDS = re.compile(
    r"\b(ghosts?|vampires?|aliens?|demons?|monsters?|zombies?|spirits?|witch(es)?|devils?)\b", re.I
)


def check_unspoken_rules(script, beats):
    """Extra rules for the unspoken-rules format (exactly three rules, unnamed threat)."""
    errs = []
    rules = script.get("rules")
    if not isinstance(rules, list) or len(rules) != 3 or not all(
        isinstance(r, str) and r.strip() for r in rules
    ):
        errs.append("rules must be a list of exactly 3 non-empty strings")
        rules = []
    labels = ["one", "two", "three"]
    for k, rule in enumerate(rules):
        vo = beats[k + 1].get("voiceover", "")
        if rule.strip().lower() not in vo.lower():
            errs.append(f"rule {labels[k]} text {rule!r} must appear word for word in beat {k+2}")
    for k, word in enumerate(labels):
        if not re.match(rf"\s*rule {word}\b", beats[k + 1].get("voiceover", ""), re.I):
            errs.append(f"beat {k+2}: voiceover must start with 'Rule {word}:'")
    if not re.search(r"\bthree rules\b", beats[0].get("voiceover", ""), re.I):
        errs.append("beat 1: must mention 'three rules'")
    if script.get("broken_rule") not in (1, 2, 3):
        errs.append("broken_rule must be 1, 2, or 3")
    if YOU.search(beats[4].get("voiceover", "")):
        errs.append("beat 5: tell the incident in third person, do not use 'you'")
    for i, b in enumerate(beats):
        vo = b.get("voiceover", "")
        if CONTRACTION.search(vo):
            errs.append(f"beat {i+1}: no contractions, write 'did not' not 'didn't'")
        if MONSTER_WORDS.search(vo):
            errs.append(f"beat {i+1}: never name the threat (ghost, vampire, alien, ...)")
    return errs


YEAR = re.compile(r"\b(19|20)\d{2}\b")
FEW_SECONDS = re.compile(r"\b(one|two|three) seconds?\b", re.I)
MORAL = re.compile(
    r"\b(be careful|next time|remember to|beware|the lesson|you should|never forget)\b", re.I
)


def check_micro_butterfly(script, beats):
    """Extra rules for the micro-butterfly format (tiny trigger, airtight chain, no moral)."""
    errs = []
    trigger = script.get("trigger")
    if not isinstance(trigger, str) or not trigger.strip():
        errs.append("trigger must be a non-empty string")
    else:
        t = trigger.strip().lower()
        for i, label in ((0, "beat 1"), (1, "beat 2"), (4, "beat 5")):
            if t not in beats[i].get("voiceover", "").lower():
                errs.append(f"trigger {trigger!r} must appear word for word in {label}")
    chain = script.get("chain")
    if (
        not isinstance(chain, list)
        or not 3 <= len(chain) <= 6
        or not all(isinstance(c, str) and c.strip() for c in chain)
    ):
        errs.append("chain must be a list of 3-6 non-empty strings (each step causes the next)")
    if not YEAR.search(beats[0].get("voiceover", "")):
        errs.append("beat 1: must name a year (documentary tone)")
    early = beats[0].get("voiceover", "") + " " + beats[1].get("voiceover", "")
    if not FEW_SECONDS.search(early):
        errs.append("beats 1-2: must say the mistake took 'two seconds' (or one/three)")
    for i, b in enumerate(beats):
        vo = b.get("voiceover", "")
        if YOU.search(vo):
            errs.append(f"beat {i+1}: third person only, do not use 'you'")
        if CONTRACTION.search(vo):
            errs.append(f"beat {i+1}: no contractions, write 'did not' not 'didn't'")
        if MORAL.search(vo):
            errs.append(f"beat {i+1}: no moral or advice, end on the consequence")
    return errs


def check(script, fmt="twist"):
    spec = FORMATS[fmt]
    errs = []
    beats = script.get("beats")
    if not isinstance(script.get("title"), str) or not script["title"].strip():
        errs.append("missing title")
    if not isinstance(beats, list) or len(beats) != 5:
        return errs + ["beats must be a list of exactly 5"]
    total = 0
    for i, b in enumerate(beats):
        if b.get("timestamp") != spec["timestamps"][i]:
            errs.append(f"beat {i+1}: timestamp must be {spec['timestamps'][i]}")
        if b.get("beat") != spec["beats"][i]:
            errs.append(f"beat {i+1}: beat must be '{spec['beats'][i]}'")
        vo, vis = b.get("voiceover", ""), b.get("visual", "")
        if not vo.strip():
            errs.append(f"beat {i+1}: empty voiceover")
        if not vis.strip():
            errs.append(f"beat {i+1}: empty visual")
        total += len(vo.split())
        for s in sentences(vo):
            n = len(s.split())
            if n > MAX_SENTENCE:
                errs.append(f"beat {i+1}: {n}-word sentence: {s!r}")
    if not MIN_WORDS <= total <= MAX_WORDS:
        errs.append(f"total voiceover words {total}, need {MIN_WORDS}-{MAX_WORDS}")
    if fmt == "ticking-clock":
        errs += check_ticking_clock(script, beats)
    elif fmt == "slow-burn":
        errs += check_slow_burn(script, beats)
    elif fmt == "rule-of-three":
        errs += check_rule_of_three(script, beats)
    elif fmt == "reverse-chronology":
        errs += check_reverse_chronology(script, beats)
    elif fmt == "unspoken-rules":
        errs += check_unspoken_rules(script, beats)
    elif fmt == "micro-butterfly":
        errs += check_micro_butterfly(script, beats)
    script["_words"] = total
    return errs


def format_from_path(path):
    """Return the format named by an output/script-writer/<category>/ folder, else None."""
    parts = path.replace("\\", "/").split("/")
    for i, part in enumerate(parts[:-2]):
        if part == "script-writer" and parts[i + 1] in FORMATS:
            return parts[i + 1]
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
    for p in argv:
        fmt = forced or format_from_path(p) or "twist"
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for s in data if isinstance(data, list) else [data]:
            errs = check(s, fmt)
            name = s.get("title", "?")
            if errs:
                failed = True
                print(f"FAIL {p} :: {name}")
                for e in errs:
                    print("   -", e)
            else:
                print(f"ok   {p} :: {name} ({s['_words']} words)")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
