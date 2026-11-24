"""make_actions_md.py - write ACTIONS.md from: the actions found in the scripts (actions_extracted.json), the action
catalogue (config/actions.json) and the test verdicts (results.json of actiontests.py). Also fills 'covers', 'sources' and
'bodies' in config/actions.json so `clip.py actions -v` shows them.

    py -3 make_actions_md.py --results <results.json> [<results.json> ...] --out <ACTIONS.md>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charpaths as P  # noqa: E402

# script action (as extracted) -> (library action, how to call it when it is not just the name)
MAP = {
    "walk": ("walk", ""), "run": ("run", ""), "sneak": ("sneak", "tiptoe is `tiptoe`"), "step_forward": ("step_forward", ""), "pace": ("pace", ""),
    "stomp_storm": ("stomp", "then `walk` with `arms=False`"), "sit_down": ("sit_down", ""), "sit_idle": ("sit_idle", ""), "stand_up": ("stand_up", ""),
    "kneel": ("kneel", ""), "crouch": ("crouch", ""), "hide_behind_cover": ("hide", ""), "lie_down": ("lie_down", ""), "sleep": ("sleep", ""),
    "wake_up": ("wake_up", ""), "fall": ("fall", "`to=` for a fall down to a place"), "slip": ("slip", ""), "jump": ("jump", "`to=` for a leap"),
    "climb": ("climb", ""), "climb_through_window": ("climb", "`crouch`, then `climb(to=the sill)`, then `jump(to=inside)`"),
    "hang_from_rope": ("hang", ""), "swim_tread_water": ("swim", ""), "crawl_on_belly": ("crawl", ""), "roll_sideways": ("roll", ""),
    "struggle_stuck": ("struggle", ""), "lean": ("lean_on", ""), "ride_horse": ("ride", "seat the figure on the horse with `place`"),
    "drive_vehicle": ("ride", "`bob=False` for a car"), "enter_exit_vehicle": ("step_forward", "`step_forward` + `sit_down` / `stand_up`"),
    "turn_around": ("turn_around", ""), "stand_idle": (None, "`actor.idle()`: blinks and breath; no action needed"), "freeze": ("freeze", ""),
    "recoil": ("recoil", ""),
    "pick_up": ("pick_up", "`both=True` for a heavy thing"), "put_down": ("put_down", ""), "carry": ("carry", "then `walk(..., arms=False)`"),
    "haul_heavy": ("haul", ""), "throw": ("throw", ""), "drop": ("drop", ""), "hold_up_object": ("hold_up", "`show` for chest height toward someone"),
    "point": ("point", ""), "hold_up_finger": ("hold_up_finger", ""), "wave": ("wave", ""), "beckon": ("beckon", ""), "pull_object": ("pull", "`by=` moves the thing"),
    "lift": ("lift", "`by=` for a thing that slides up (a gate)"), "roll_up": ("tie", "`kneel`, then `tie(target=the roll)`"),
    "hold_door_open": ("open_door", "then hold: `lean_on(target=the door edge)`"), "open_door": ("open_door", ""), "close_door": ("open_door", "negative `deg`"),
    "lock_unlock": ("turn_key", "`prop=` the key"), "tap_keycard": ("press", "`palm=True`, card held"), "press_button": ("press", ""),
    "open_container": ("lift", "`lift(target=the lid, by=0.3)` or `tie` for a zip or latch"), "take_out": ("take_out", ""), "stash": ("stash", ""),
    "cut": ("use_tool", '`kind="cut"` (or `"saw"`)'), "stab_plant": ("slam", "with the thing held"), "slam_smash": ("slam", ""),
    "grip_bars": ("push", "`push(target=the bars)` without `by`; add `tremble` to rattle them"), "pour": ("pour", ""), "drink": ("drink", ""),
    "light_flame": ("light", ""), "blow_out": ("blow", ""), "write_sign": ("write", ""), "read": ("read", ""), "draw_paint": ("use_tool", '`kind="paint"`'),
    "mop": ("use_tool", '`kind="mop"` (or `"sweep"`)'), "tie_fasten": ("tie", ""), "use_phone": ("phone", "`screen=True`"), "radio_phone_call": ("phone", ""),
    "shine_flashlight": ("aim", "`prop=` the torch"), "aim_weapon": ("aim", "`prop=` the weapon"), "reach_for_weapon": ("take_out", '`spot="belt"`'),
    "hold_cards": ("read", ""), "slide_across_table": ("push", "one hand: `press(target=...)` then `core.move` the thing"), "count_tap": ("tap", "`targets=[...]`"),
    "shake_object": ("listen", "`hold` the thing, then `listen` and `shake`"), "hammer_nail": ("use_tool", '`kind="hammer"`'),
    "fish_with_net": ("use_tool", '`kind="sweep"`, net held with `turn=True`'), "tip_hat": ("tip_hat", ""), "dust_off": ("dust_off", ""), "hands_up": ("hands_up", ""),
    "gasp": ("gasp", ""), "laugh": ("laugh", ""), "smile_grin": ("smile", "`smug=True` for a smirk"), "cry": ("cry", ""), "sad_slump": ("sigh", ""), "shrug": ("shrug", ""),
    "think": ("think", ""), "nod": ("nod", ""), "shake_head": ("shake_head", ""), "cheer": ("cheer", ""), "jeer": ("jeer", ""), "panic": ("panic", ""), "cower": ("cower", ""),
    "tremble_shiver": ("tremble", ""), "angry": ("angry", ""), "suspicious_squint": ("suspicious", ""), "dread_sweat": ("dread", ""), "yawn": ("yawn", ""),
    "hold_back_sneeze": ("sneeze", ""), "whistle": ("whistle", ""), "sniff": ("sniff", ""), "listen": ("listen", ""), "look_around": ("look_around", ""), "watch": ("watch", ""),
    "peek": ("peek", ""), "inspect_closely": ("inspect", ""), "avoid_eye_contact": ("look_away", ""), "smug_pose": ("proud", ""),
    "hand_over": ("hand_over", ""), "receive": ("receive", ""), "push_person": ("push_person", ""), "grab_person": ("grab_person", ""),
    "carry_person": ("carry", "`carry(target=child.stage)`: the child's stage empty rides the hands. Not tested in isolation"),
    "cover_mouth": ("cover_mouth", "`target=` the other character"), "hug": ("hug", ""), "chase": ("chase", ""), "argue": ("argue", ""), "lock_eyes": ("watch", "both ways"),
    "pat_back": ("pat_back", ""), "slap_hand_away": ("slap_away", ""), "plead_beg": ("plead", "`knees=True`"),
    "talk": ("talk", ""), "shout": ("shout", ""), "whisper": ("whisper", ""),
}
# what unusual bodies do instead (keys: no_legs = Ghost and any legs=False body, mermaid, all others = same as everyone)
BODIES = {
    "walk": {"no_legs": "glides with a slow bob (Ghost)", "mermaid": "swims: glides low with a small bob"},
    "run": {"no_legs": "glides fast", "mermaid": "swims fast"}, "sneak": {"no_legs": "glides slowly, leaning forward", "mermaid": "swims slowly"},
    "tiptoe": {"no_legs": "glides slowly", "mermaid": "swims slowly"}, "step_forward": {"no_legs": "a short glide", "mermaid": "a short glide"},
    "pace": {"no_legs": "glides to and fro", "mermaid": "swims to and fro"}, "stomp": {"no_legs": "fists down and two squashes, no foot", "mermaid": "same, no foot"},
    "sit_down": {"no_legs": "the body settles a third of the hip height lower", "mermaid": "settles onto her tail"},
    "sit_idle": {"no_legs": "stays settled low", "mermaid": "stays on her tail"}, "stand_up": {"no_legs": "rises back to float height", "mermaid": "rises off her tail"},
    "kneel": {"no_legs": "settles low with a lean", "mermaid": "settles low with a lean"}, "crouch": {"no_legs": "settles low, leaning", "mermaid": "settles low, leaning"},
    "hide": {"no_legs": "sinks low, then peeks", "mermaid": "sinks low, then peeks"}, "jump": {"no_legs": "rises and drops (no knee bend)", "mermaid": "a leap out of the water shape: rises and drops"},
    "climb": {"no_legs": "rises with the hands reaching in turn", "mermaid": "same"}, "hang": {"no_legs": "hangs and sways; nothing dangles", "mermaid": "tail hangs"},
    "swim": {"mermaid": "her natural gait"}, "curtsy": {"no_legs": "a dip of the whole body", "mermaid": "a dip of the whole body"},
    "slip": {"no_legs": "arms windmill, tips over backward", "mermaid": "same"}, "slip_banana": {"no_legs": "glides over the peel, tumbles in the air, lands flat", "mermaid": "same"},
    "chase": {"no_legs": "glides after / away", "mermaid": "swims after / away"}, "haul": {"no_legs": "glides backward with the load", "mermaid": "same"},
    "hug": {"no_legs": "glides in", "mermaid": "glides in"}, "ride": {"no_legs": "arms forward, body low", "mermaid": "sits side-on, arms forward"},
    "plead": {"no_legs": "settles low instead of kneeling", "mermaid": "settles low"}, "juggle": {"no_legs": "no knee dip; the body bobs", "mermaid": "same"},
    "lie_down": {"no_legs": "tips flat", "mermaid": "lies on her side"}, "crawl": {"no_legs": "glides flat along the ground", "mermaid": "drags herself by the arms: her natural move on land"},
}
STANDARD = [("adult", ["AdultMan"]), ("child", ["Boy"]), ("baby", ["Baby"]), ("elderly", ["SeniorMan"]), ("robe", ["Queen"])]
UNUSUAL = ["Ghost", "Mermaid", "Dragon", "Fairy", "Robot", "Alien", "Werewolf", "Mummy", "Genie", "Goblin"]
GROUPS = [("moving", "Moving"), ("hands", "Hands and props"), ("reactions", "Reactions"), ("two_person", "Two people"), ("talking", "Talking")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--extracted", default=str(P.TOOLS.parent / "actions_extracted.json"))
    a = ap.parse_args()
    catp = P.PIPELINE / "config" / "actions.json"
    cat = json.loads(catp.read_text(encoding="utf-8"))
    ex = json.loads(Path(a.extracted).read_text(encoding="utf-8"))
    res = {}
    for r in a.results:
        res.update(json.loads(Path(r).read_text(encoding="utf-8")))
    by = {}
    for v in res.values():
        by.setdefault((v["action"], v["char"]), []).append(v)
    needs_of, covers = {}, {}
    for e in ex["actions"]:
        lib, how = MAP.get(e["name"], (None, "NOT MAPPED"))
        if lib:
            needs_of.setdefault(lib, []).append(e)
            covers.setdefault(lib, []).append(e["name"].replace("_", " "))
    for ac in cat["actions"]:                                   # write covers / sources / bodies back into the catalogue
        ac["covers"] = sorted(set(ac.get("covers", [])) | set(covers.get(ac["name"], [])) - {ac["name"].replace("_", " ")})
        srcs = []
        for e in needs_of.get(ac["name"], []):
            srcs += [f'{s["script"]} / {s["beat"]}' for s in e["sources"][:3]]
        ac["sources"] = sorted(set(ac.get("sources", [])) | set(srcs))[:10]
        ac["bodies"] = {**BODIES.get(ac["name"], {}), **ac.get("bodies", {})}
    catp.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    def status(action, chars):
        vs = [v for c in chars for v in by.get((action, c), [])]
        if not vs:
            return "not run"
        ok = sum(1 for v in vs if v["pass"])
        if ok == len(vs):
            return f"pass {ok}/{len(vs)}"
        why = next(v["fails"][0] for v in vs if not v["pass"])
        return f"**FAIL {len(vs) - ok}/{len(vs)}**: {why}"

    L = []
    W = L.append
    n_scripts = len(ex["scripts"])
    W("# Actions: what the characters can do\n")
    W(f"Built from every `voiceover` and `visual` of the scripts in `script-examples/` ({n_scripts} scripts: "
      f"{sum(1 for s_ in ex['scripts'] if 'produced' not in s_['file'])} in `gold-by-format/`, 2 in `produced-scripts/`; the brief said 56 gold scripts, "
      "the folder holds 26). "
      f"{len(ex['actions'])} distinct on-screen actions were found; they are covered by {len(cat['actions'])} named actions in `stagekit.actions`.\n")
    W("## How to call an action\n")
    W("```python\nt1 = actor.do(\"pick_up\", ring, hit=shot.t(\"picked up\"))     # the key moment (the grab) lands on the word\n"
      "t1 = actor.do(\"wave\", t=2.4)                                  # starts at 2.4 s; returns the time it ends\n"
      "a.do(\"hand_over\", key, to=b, hit=shot.t(\"gave\"))             # two people\n"
      "t1 = thief.do(\"sneak\", t, to=(3, 1))                         # moving actions return the arrival time\n"
      "a.do(\"laugh\", t, until=shot.t(\"stopped\"))                    # loops run until `until`\n"
      "a.do(\"use_tool\", broom, kind=\"sweep\", t=t, speed=1.3)       # speed scales every beat of the action\n```\n")
    W("Every action is a performance in three beats (anticipation, main motion, settle), keyed in seconds of the shot, built from view-aware poses, "
      "`reach`, `hold` and the gait cycles, so it plays in the front, three-quarter and side drawings and facing either way. "
      "`python tools/clip.py actions [word] -v` prints this catalogue; `config/actions.json` is its data. To add one: `ADDING_NEW_ACTIONS.md`.\n")
    W("## Test results\n")
    W("Each action was performed in a plain test scene (backdrop, ground, a prop / target / second character as needed), measured on **every frame** "
      "and rendered as a strip (every 2nd frame) and an MP4 (`proof/actions/<Character>/<action>__<view>_<facing>.strip.png` / `.mp4`). "
      "A combination passes only if on all frames: limb parts stay on their joints, a held prop stays in the palm, planted feet do not slide, "
      "a hand over the head is drawn in front of it, the acting hand is on the target's side, and a reaching palm arrives on the target at the key moment.\n")
    tot = len(res)
    okn = sum(1 for v in res.values() if v["pass"])
    W(f"**{okn} of {tot} action x character x view x facing combinations pass.** Columns below: the five standard body types "
      "(adult = AdultMan, child = Boy, baby = Baby, elderly = SeniorMan, robe = Queen), then the ten unusual bodies together. "
      "`pass n/n` counts view x facing combinations.\n")
    core = ["walk", "point", "pick_up", "hold_up", "hand_over", "gasp", "talk", "sit_down"]
    chars_all = sorted({v["char"] for v in res.values()})
    W("### Core actions on the whole cast\n")
    W("| Action | Characters tested | Combinations | Pass | Failing |")
    W("|---|---|---|---|---|")
    for c_ in core:
        vs = [v for v in res.values() if v["action"] == c_]
        bad = sorted({v["char"] for v in vs if not v["pass"]})
        W(f"| `{c_}` | {len({v['char'] for v in vs})} | {len(vs)} | {sum(1 for v in vs if v['pass'])} | {', '.join(bad) if bad else 'none'} |")
    W("")
    for gid, gname in GROUPS:
        W(f"## {gname}\n")
        W("| Action | What the body does | Needs | adult | child | baby | elderly | robe | unusual bodies | Instead, for unusual bodies |")
        W("|---|---|---|---|---|---|---|---|---|---|")
        for ac in sorted((x for x in cat["actions"] if x["group"] == gid), key=lambda x: x["name"]):
            cols = [status(ac["name"], chars) for _n, chars in STANDARD]
            un = status(ac["name"], UNUSUAL)
            sub = "; ".join(f"{k.replace('no_legs', 'no legs')}: {v}" for k, v in ac.get("bodies", {}).items()) or "same as everyone"
            needs = ", ".join(ac["needs"]) or "none"
            W(f"| `{ac['name']}`{' (loop)' if ac.get('loops') else ''} | {ac['summary']} | {needs} | " + " | ".join(cols) + f" | {un} | {sub} |")
        W("")
    W("## From the scripts to the actions\n")
    W("Every action found in the scripts, most frequent first, with the call that performs it.\n")
    W("| In the scripts | Beats | Example (script / beat) | Hands and props in the scripts | Performed with |")
    W("|---|---|---|---|---|")
    for e in sorted(ex["actions"], key=lambda x: -x["count"]):
        lib, how = MAP.get(e["name"], (None, "NOT MAPPED"))
        src = e["sources"][0]
        call = (f"`{lib}`" + (f": {how}" if how else "")) if lib else how
        W(f"| {e['name'].replace('_', ' ')} | {e['count']} | {src['script']} / {src['beat']}: \"{src['quote']}\" | {e['hands_props']} | {call} |")
    W("")
    extra = [x["name"] for x in cat["actions"] if x["name"] not in {m[0] for m in MAP.values()}]
    W("## Actions in the library that no gold script uses yet\n")
    W("Asked for in the brief or needed to make the others complete: " + ", ".join(f"`{n}`" for n in sorted(extra)) + ".\n")
    W("`juggle` and `slip_banana` were added by following `ADDING_NEW_ACTIONS.md` literally, to prove the procedure.\n")
    W("## Unusual bodies in one place\n")
    W("| Body | Characters | What changes |")
    W("|---|---|---|")
    W("| no legs | Ghost | every gait is a glide with a bob; sit / kneel / crouch settle the body about a third of the hip height lower; no foot or knee work; `legs()` only lowers the body |")
    W("| tail | Mermaid | every gait is a swim (a low glide); she sits on her tail (the body settles lower); `legs()` only lowers the body; her fin sways by itself |")
    W("| wings, tail | Dragon, Fairy | standard arms, legs and gaits; wings and tail are swung by `idle()` (`cl_wiggle`), so they keep moving through every action |")
    W("| antennae, loose ends | Alien, Robot, Mummy | standard body; the marked parts sway by themselves |")
    W("| claws, muzzle | Werewolf | standard body; claws ride the hands, so `fist` and `grip` shapes show them |")
    W("| child height | Goblin, Fairy | reach and pick-up lean and crouch more; everything else as a child |")
    W("| legs, as drawn | Genie | standard body (the sheet shows legs; a smoke tail was not built) |")
    W("")
    fails = sorted((v for v in res.values() if not v["pass"]), key=lambda v: (v["action"], v["char"], v["view"], v["face"]))
    W("## Everything that still fails\n")
    if not fails:
        W("Nothing: every tested combination passes.\n")
    else:
        W("| Action | Character | View / facing | Why |")
        W("|---|---|---|---|")
        for v in fails[:200]:
            W(f"| `{v['action']}` | {v['char']} | {v['view']} / {v['face']} | {'; '.join(v['fails'])} |")
        if len(fails) > 200:
            W(f"\n... and {len(fails) - 200} more in `proof/actions/results.json`.")
        W("")
    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print(f"ACTIONS.md: {len(cat['actions'])} actions, {okn}/{tot} combinations pass, {len(fails)} fail -> {a.out}")


if __name__ == "__main__":
    main()
