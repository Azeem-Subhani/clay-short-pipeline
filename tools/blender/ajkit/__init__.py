"""ajkit - the Aj pack's own Blender modules, vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts.

    grips     fingers that close on the real surface of a held object (power, pen, pinch)
    joints    plain-language joint angles, the hanging-arm maths (_arm_matrix), arm IK
    variants  the eight bodies: specs, measure(), load_clip() / retarget() for Mixamo clips
    faces     the eight face presets (shape keys on the head)
    paths     where the pack, the hair library and the clips are in this project

Each module says at its top what was changed against the pack copy: only object names turned into arguments and
absolute paths moved to paths.py. The pipeline's actors use them through stagekit.cast_aj / aj_rig / aj_hands.
"""
