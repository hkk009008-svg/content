#!/usr/bin/env python3
"""Tier C cheongsam reel — direct pipeline execution.

Operator-driven Tier C execution per director's T20:59:30Z decision event
scope-lock + operator's T21:08:00Z dispatch-claim. Bypasses web_server.py
HTTP/SSE wrapping (which is concurrency machinery only; no Tier-relevant
behavior) and invokes CinemaPipeline inline.

Scope (locked):
  Character    Single cheongsam Korean female + ref photo (gender=female)
  Reel         1 scene x 3 shots
  Language     Korean
  Performance  Enabled on shot index 1 (middle shot)
  Driving vid  ~/Downloads/3819343-hd_1920_1080_25fps.mp4
  Cost env     $5-10 estimated; $50 hard cap

Exercises VG-B1 + I-B1 + I-B2 + M-B1 + M-B2 + C-B1 + C-B2 + M-B3 closures
end-to-end on a 3-shot reel with PuLID-FLUX identity anchoring + cross-shot
continuity engine + Hedra C3 lipsync on the middle shot.
"""
import os
import sys
import json
import time
import traceback

# Make repo root importable when invoked as `python scripts/run_tier_c.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.project_manager import (
    create_project,
    load_project,
    mutate_project,
    make_scene,
)
from domain.character_manager import create_character_with_images
from domain.location_manager import create_location_with_images
from cinema_pipeline import CinemaPipeline


REF_PHOTO = "/Users/hyungkoookkim/Downloads/pexels-nektarios-moutakis-266968888-18898990.jpg"
DRIVING_VIDEO = "/Users/hyungkoookkim/Downloads/3819343-hd_1920_1080_25fps.mp4"


def main():
    assert os.path.exists(REF_PHOTO), f"REF_PHOTO missing: {REF_PHOTO}"
    assert os.path.exists(DRIVING_VIDEO), f"DRIVING_VIDEO missing: {DRIVING_VIDEO}"

    started_at = time.time()
    print("=" * 78)
    print("TIER C CHEONGSAM REEL — pipeline start")
    print(f"  started_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started_at))}")
    print("=" * 78)

    # ---------------------------------------------------------------- 1) Project
    project = create_project("Tier C cheongsam reel 2026-05-27")
    pid = project["id"]
    print(f"PROJECT_ID: {pid}")

    # ---------------------------------------------------------------- 2) Settings
    def _update_settings(p):
        p["global_settings"].update({
            "language": "Korean",
            "language_pref": "ko",
            "music_mood": "contemplative",
            "aspect_ratio": "16:9",
            "quality_tier": "production",
            "budget_limit_usd": 50.0,
            "screening_stage_enabled": True,
            "performance_driving_video_path": DRIVING_VIDEO,
            "performance_shot_index": 1,
        })
        # Avoid Tier B Run 1 freeze: cascade-fallback-veto on keyframe.
        aa = p["global_settings"].setdefault("auto_approve", {})
        aa["image_veto_on_fallback"] = False
        return p

    mutate_project(pid, _update_settings)
    print("SETTINGS: language=Korean, music_mood=contemplative, budget_limit_usd=50.0, "
          "screening_stage_enabled=True, perf_shot_index=1, image_veto_on_fallback=False")

    # ---------------------------------------------------------------- 3) Character
    project = load_project(pid)
    character = create_character_with_images(
        project,
        "정연",
        ("Late-20s Korean woman; dramatic studio portrait; black-and-red cheongsam with "
         "cherry blossoms; serious contemplative expression; red lipstick; soft camera-left "
         "rim light."),
        reference_image_paths=[REF_PHOTO],
        voice_id="",            # auto-assign via VG-B1 path (Korean + female -> 안나)
        ip_adapter_weight=0.85,
        gender="female",
    )
    cid = character["id"]
    print(f"CHARACTER_ID: {cid}")
    print(f"CHARACTER_VOICE: {character.get('voice_id', '<empty>')} "
          f"(VG-B1 expects 안나/uyVNoMrnUku1dZyVEXwD)")
    print(f"CHARACTER_GENDER: {character.get('gender', '<empty>')}")
    print(f"CHARACTER_REFS: {len(character.get('reference_images', []))}")
    print(f"CHARACTER_ANGLES: {len(character.get('multi_angle_refs', []))}")

    # ---------------------------------------------------------------- 4) Location
    project = load_project(pid)
    location = create_location_with_images(
        project,
        "스튜디오",
        ("Black-curtained dramatic studio; cherry blossom branches in foreground; soft "
         "camera-left rim light."),
        reference_image_paths=None,
        lighting="dramatic chiaroscuro spotlight",
        time_of_day="night",
        weather="indoor studio",
    )
    lid = location["id"]
    print(f"LOCATION_ID: {lid}")

    # ---------------------------------------------------------------- 5) Scene
    def _add_scene(p):
        scene = make_scene(
            title="회상",
            location_id=lid,
            characters_present=[cid],
            action=("Contemplative recollection sequence; three beats moving from intimate "
                    "close-up to medium framing; quiet emotional register; subject seated, "
                    "slow exhalations, eye movement carries the arc."),
            dialogue="",           # let P-DECOMPOSE + dialogue_writer auto-generate Korean
            mood="contemplative",
            camera_direction="cinematic close-up to medium",
            duration_seconds=15.0,
        )
        scene["num_shots"] = 3
        p["scenes"].append(scene)
        return p

    mutate_project(pid, _add_scene)
    print("SCENE: 1 scene, 3 shots planned (auto-decompose via P-DECOMPOSE)")

    # ---------------------------------------------------------------- 6) Pipeline
    print()
    print("=" * 78)
    print(f"PIPELINE start: project={pid}")
    print("=" * 78)
    print()

    try:
        pipe = CinemaPipeline(pid)
        result = pipe.generate(resume=False)
    except Exception:
        traceback.print_exc()
        result = None

    elapsed_sec = time.time() - started_at
    print()
    print("=" * 78)
    print(f"PIPELINE end: project={pid}")
    print(f"  result: {result!r}")
    print(f"  elapsed: {elapsed_sec/60:.1f} min")
    print(f"  ended_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print("=" * 78)

    # ---------------------------------------------------------------- 7) Snapshot
    project_final = load_project(pid) or {}
    cost_tracker = (project_final.get("global_settings") or {}).get("cost_tracker_snapshot")
    print(f"PROJECT_FINAL_STAGES: {[s.get('stage') for s in (project_final.get('stage_history') or [])]}")
    print(f"COST_TRACKER_SNAPSHOT: {cost_tracker}")

    return 0 if result else 2


if __name__ == "__main__":
    sys.exit(main())
