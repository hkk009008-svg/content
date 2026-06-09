#!/usr/bin/env python3
"""30-sec narrative talking-head — generation-mode lip-sync (single clip, no Veo 8s stitch).

Project cfd3f0967eb3 / Aria, reusing the existing approved keyframe. Sets the dialogue
line + the dialogue purpose (cache shortcut, verified safe: generate_motion_take reads
ONLY optimizer_cache.spec.purpose for has_dialogue, controller.py:1272-1276; target_api
is pinned KLING_NATIVE so suggested_video_api is irrelevant). dialogue_voice_mode=overlay
(audio NOT embedded -> the mandatory F1b lip-sync runs) + lip_sync_mode=generation (one
<=60s Omnihuman/Hedra clip from char image+TTS audio). Then generate_motion_take does
video + ElevenLabs TTS + generation lip-sync in one call.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.project_manager import mutate_project
from cinema.core import build_pipeline_core
from cinema_pipeline import CinemaPipeline

PID = "cfd3f0967eb3"
SCENE = "scene_77582037b605"
SHOT = "shot_scene_77582037b605_0"
NARRATIVE = (
    "They told me this city forgets everyone eventually. Maybe that's true. But standing "
    "here, watching the lights come on one by one, I've started to think forgetting is just "
    "another word for starting over. I came here with nothing — a name, and a promise I made "
    "to myself. Tonight, for the first time, I believe I'm going to keep both."
)


def _setup(proj):
    touched = False
    for sc in proj.get("scenes", []):
        if sc.get("id") != SCENE:
            continue
        sc["dialogue"] = NARRATIVE
        for sh in sc.get("shots", []):
            if sh.get("id") == SHOT:
                sh["dialogue"] = NARRATIVE
                sh["optimizer_cache"] = {"spec": {"purpose": "talking_head_full"}}
                touched = True
    gs = proj.setdefault("global_settings", {})
    gs["dialogue_voice_mode"] = "overlay"   # our ElevenLabs TTS, NOT engine-embedded -> F1b runs
    gs["lip_sync_mode"] = "generation"      # single <=60s clip (Omnihuman/Hedra), no Veo 8s stitch
    return touched


def main():
    print(f"[setup] dialogue ({len(NARRATIVE.split())} words) + talking_head_full purpose + "
          f"overlay/generation modes ...", flush=True)
    ok = mutate_project(PID, _setup)
    print(f"[setup] shot patched = {ok}", flush=True)

    print("[build] build_pipeline_core ...", flush=True)
    p = CinemaPipeline(PID, core=build_pipeline_core(PID))

    print("[gen] generate_motion_take (video + TTS + generation lip-sync) ...", flush=True)
    t = time.time()
    try:
        res = p.generate_motion_take(SCENE, SHOT)
    except Exception as e:  # noqa: BLE001
        print(f"[gen] EXCEPTION after {(time.time()-t)/60:.1f} min: {e}", flush=True)
        traceback.print_exc()
        return 1
    print(f"[gen] DONE in {(time.time()-t)/60:.1f} min", flush=True)
    print(f"[gen] result type={type(res).__name__} value={res!r}"[:800], flush=True)

    # Locate the produced video + lipsync score from the refreshed project.
    import json
    proj = json.load(open(f"domain/projects/{PID}/project.json"))
    for sc in proj.get("scenes", []):
        if sc.get("id") != SCENE:
            continue
        for sh in sc.get("shots", []):
            if sh.get("id") != SHOT:
                continue
            mt = sh.get("motion_takes", [])
            print(f"[result] motion_takes={len(mt)}; approved={sh.get('approved_motion_take_id')}", flush=True)
            for tk in mt[-3:]:
                print(f"  take {tk.get('id')}: video={tk.get('video_path') or tk.get('path')} "
                      f"lipsync_score={tk.get('lipsync_score')} dur={tk.get('duration')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
