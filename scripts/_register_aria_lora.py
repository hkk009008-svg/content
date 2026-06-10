"""Register the fal-trained Aria LoRA onto project cfd3f0967eb3 (P1-1 spec §7.3).

No machine-validated strength exists (the v2 sweep covered only {0.55, 0.65, 0.70};
no argmax persisted) — strength 0.55 is supplied manually per the 2026-06-02
finding. Trigger 'TOKwoman' is supplied manually (FAL-trained LoRAs have no
dataset_manifest.json; the value is hardcoded in scripts/_fal_lora_train.py:28).
The .safetensors stays local; pod-side placement into ComfyUI's loras/ dir is a
slice-2 pod-session step. Idempotent; prints before/after.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.project_manager import mutate_project, load_project

PROJECT_ID = "cfd3f0967eb3"
CHAR_ID = "char_b9c8bcfe9af0"
LORA_PATH = os.path.abspath("logs/char_lora_fal_v2.safetensors")
STRENGTH = 0.55
TRIGGER = "TOKwoman"


def main() -> int:
    assert os.path.exists(LORA_PATH), f"missing artifact: {LORA_PATH}"
    project = load_project(PROJECT_ID)
    chars = [c.get("id") for c in project.get("characters", [])]
    assert CHAR_ID in chars, f"{CHAR_ID} not in project characters: {chars}"

    def _mutate(p):
        gs = p.setdefault("global_settings", {})
        before = {k: gs.get(k) for k in
                  ("char_lora_paths", "char_lora_strengths", "char_lora_triggers")}
        gs.setdefault("char_lora_paths", {})[CHAR_ID] = LORA_PATH
        gs.setdefault("char_lora_strengths", {})[CHAR_ID] = STRENGTH
        gs.setdefault("char_lora_triggers", {})[CHAR_ID] = TRIGGER
        print("before:", json.dumps(before, indent=1))
        return p

    mutate_project(PROJECT_ID, _mutate)
    after = load_project(PROJECT_ID).get("global_settings", {})
    print("after:", json.dumps({k: after.get(k) for k in
          ("char_lora_paths", "char_lora_strengths", "char_lora_triggers")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
