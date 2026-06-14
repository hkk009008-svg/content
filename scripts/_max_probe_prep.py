"""Prepare a max-tier workflow (LoRA-less + fp16 + fixed SUPIR/scheduler), upload a
real face ref so node 93 resolves, and write the /prompt payload."""
import json
import requests
import quality_max as q

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"

# upload the face ref to the pod's ComfyUI input dir
with open(REF, "rb") as f:
    up = requests.post(f"{URL}/upload/image",
                       files={"image": ("face_ref.jpg", f, "image/jpeg")},
                       data={"overwrite": "true"}, timeout=40)
face_remote = up.json().get("name")
print(f"uploaded face ref -> {face_remote}")

available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
print(f"pod available classes: {len(available)}")

w = q._load_max_workflow()
w.pop("_metadata", None)
q._apply_model_precision(w, "fp16")

has_face_ref, has_char_lora, has_init = True, True, False
params: dict = {}

q._prune_unavailable(w, available, has_face_ref, has_char_lora, has_init)
q._inject_identity(w, None, face_remote, params, has_face_ref)   # LoRA-less + real face anchor
q._inject_conditioning(w, "cinematic portrait of a woman, short dark wavy bob, soft window light, photorealistic, 85mm", None, None, params, has_face_ref)
q._inject_sampling(w, params)
q._inject_latent_source(w, None, params)
q._inject_post_passes(w, params, available)

with open("/tmp/max_probe_payload.json", "w") as f:
    json.dump({"prompt": w}, f)

print(f"prepared workflow: {len(w)} nodes")
print("node 17:", w.get("17", {}).get("class_type"), "| 901.sigmas:", w.get("901", {}).get("inputs", {}).get("sigmas"))
print("node 93 image:", w.get("93", {}).get("inputs", {}).get("image"))
print("SUPIR nodes:", [n for n in ("505","500","501","504","502","503") if n in w])
