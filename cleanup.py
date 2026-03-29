"""
Cinema Production Tool — Cleanup Manager
Automatically removes temporary files that are no longer needed after generation.

File lifecycle:
  DURING generation: temp/ accumulates images, videos, audio, normalized clips
  AFTER export: only final_cinema.mp4 + canonical refs matter
  CLEANUP: removes everything in temp/ that isn't needed for re-generation

Retention policy (configurable):
  - ALWAYS KEEP: canonical.jpg, multi-angle refs, embedding.npy, project.json
  - ALWAYS KEEP: final_cinema.mp4 (the export)
  - ALWAYS KEEP: bgm audio (reusable across re-generations)
  - DELETE: normalized clips (*_norm.mp4) — intermediate FFmpeg output
  - DELETE: interpolated clips (interp_*.mp4) — can be re-generated
  - DELETE: stitched.mp4 — intermediate assembly output
  - DELETE: face swap outputs (swapped_*.mp4)
  - DELETE: frame chain files (lastframe_*, chain_*, transition_*)
  - CONFIGURABLE: generated images (img_*.jpg) — delete or keep for reference
  - CONFIGURABLE: generated videos (vid_*.mp4) — delete or keep for reference
  - CONFIGURABLE: foley audio (foley_*.mp3) — delete or keep
  - CONFIGURABLE: dialogue audio (audio_*.mp3) — delete or keep
"""

import os
import glob
import shutil
from typing import Dict, List, Optional

from project_manager import get_project_dir


# File categories and their default retention
CLEANUP_RULES = {
    # Always delete (intermediate pipeline artifacts)
    "normalized_clips": {"pattern": "*_norm.mp4", "action": "delete", "description": "Normalized intermediate clips"},
    "interpolated": {"pattern": "interp_*.mp4", "action": "delete", "description": "Frame-interpolated clips"},
    "stitched": {"pattern": "stitched.mp4", "action": "delete", "description": "Stitched intermediate video"},
    "face_swaps": {"pattern": "swapped_*.mp4", "action": "delete", "description": "Face-swap outputs"},
    "chain_frames": {"pattern": "lastframe_*.*", "action": "delete", "description": "Frame-chain extraction files"},
    "chain_last": {"pattern": "chain_last_*.*", "action": "delete", "description": "Chain last-frame files"},
    "transitions": {"pattern": "transition_*.mp4", "action": "delete", "description": "Transition clips"},
    "storyboard": {"pattern": "storyboard_*.mp4", "action": "delete", "description": "Storyboard intermediate video"},
    "upscaled": {"pattern": "upscale_*.mp4", "action": "delete", "description": "Upscaled intermediate clips"},
    "temp_dialogue": {"pattern": "temp_dialogue_line_*.mp3", "action": "delete", "description": "Individual dialogue line audio"},

    # Configurable (keep by default for debugging, delete in aggressive mode)
    "generated_images": {"pattern": "img_*.jpg", "action": "keep", "description": "Generated keyframe images"},
    "generated_videos": {"pattern": "vid_*.mp4", "action": "keep", "description": "Generated video clips"},
    "foley_audio": {"pattern": "foley_*.mp3", "action": "keep", "description": "Foley sound effects"},
    "scene_audio": {"pattern": "audio_*.mp3", "action": "keep", "description": "Scene dialogue audio"},
    "bgm_audio": {"pattern": "bgm_*.mp3", "action": "keep", "description": "Background music"},
}


def cleanup_project(
    project_id: str,
    aggressive: bool = False,
    dry_run: bool = False,
) -> Dict:
    """
    Clean up temporary files from a project's temp directory.

    Args:
        project_id: The project to clean
        aggressive: If True, also delete generated images/videos/audio (keeps only export)
        dry_run: If True, report what would be deleted without actually deleting

    Returns:
        Dict with cleanup stats: files_deleted, bytes_freed, details
    """
    project_dir = get_project_dir(project_id)
    temp_dir = os.path.join(project_dir, "temp")

    if not os.path.exists(temp_dir):
        return {"files_deleted": 0, "bytes_freed": 0, "details": []}

    files_deleted = 0
    bytes_freed = 0
    details = []

    for category, rule in CLEANUP_RULES.items():
        should_delete = rule["action"] == "delete" or aggressive

        if not should_delete:
            continue

        pattern = os.path.join(temp_dir, rule["pattern"])
        matches = glob.glob(pattern)

        for file_path in matches:
            if os.path.isfile(file_path):
                size = os.path.getsize(file_path)
                if dry_run:
                    details.append(f"[DRY RUN] Would delete: {os.path.basename(file_path)} ({size // 1024}KB)")
                else:
                    os.remove(file_path)
                    details.append(f"Deleted: {os.path.basename(file_path)} ({size // 1024}KB)")
                files_deleted += 1
                bytes_freed += size

    # Summary
    mb_freed = bytes_freed / (1024 * 1024)
    mode = "AGGRESSIVE" if aggressive else "STANDARD"
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"   [CLEANUP] {prefix}{mode}: {files_deleted} files, {mb_freed:.1f} MB freed for project {project_id}")

    return {
        "files_deleted": files_deleted,
        "bytes_freed": bytes_freed,
        "mb_freed": round(mb_freed, 1),
        "details": details,
        "mode": mode,
    }


def cleanup_all_projects(aggressive: bool = False, dry_run: bool = False) -> Dict:
    """Clean up all projects."""
    from project_manager import list_projects

    total_files = 0
    total_bytes = 0
    project_results = []

    for p in list_projects():
        result = cleanup_project(p["id"], aggressive=aggressive, dry_run=dry_run)
        total_files += result["files_deleted"]
        total_bytes += result["bytes_freed"]
        if result["files_deleted"] > 0:
            project_results.append({"project": p["name"], **result})

    return {
        "total_files": total_files,
        "total_mb_freed": round(total_bytes / (1024 * 1024), 1),
        "projects": project_results,
    }


def get_project_disk_usage(project_id: str) -> Dict:
    """Get disk usage breakdown for a project."""
    project_dir = get_project_dir(project_id)
    usage = {"temp": 0, "characters": 0, "locations": 0, "exports": 0, "total": 0}

    for subdir in ["temp", "characters", "locations", "exports"]:
        path = os.path.join(project_dir, subdir)
        if os.path.exists(path):
            for root, _, files in os.walk(path):
                for f in files:
                    usage[subdir] += os.path.getsize(os.path.join(root, f))

    usage["total"] = sum(usage.values())

    # Convert to MB
    return {k: round(v / (1024 * 1024), 1) for k, v in usage.items()}
