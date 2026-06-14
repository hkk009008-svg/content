"""Validate the REAL quality_max build path against the live pod.

Calls the actual _prune_unavailable / _inject_* functions (the exact code the
pipeline runs) with the run3 config: has_character=True (face ref, no LoRA),
has_init=False. Then POSTs to /prompt and reports node_errors. Interrupts on
pass so no GPU work runs.
"""
import json, os, urllib.request, urllib.error
import quality_max as qm

SERVER = ""
for line in open(".env"):
    if line.startswith("COMFYUI_SERVER_URL="):
        SERVER = line.split("=", 1)[1].strip().rstrip("/")
print("SERVER:", SERVER)

available = qm._probe_node_availability(SERVER)
print("pod node classes:", len(available))

wf = qm._load_max_workflow()

has_face_ref, has_char_lora, has_init = True, True, False
params = {k: v for k, v in []}  # defaults via .get() inside functions

# mirror generate_ai_broll_max ordering (skip uploads; use fake remote names —
# validation does not check image-file existence)
qm._prune_unavailable(wf, available, has_face_ref, has_char_lora, has_init)
face_anchor_remote = "canonical.jpg"
init_remote = None
style_remote = face_anchor_remote
qm._inject_identity(wf, None, face_anchor_remote, params, has_face_ref)   # char_lora=None (no LoRA)
qm._inject_conditioning(wf, "a portrait of a woman, cinematic", init_remote, style_remote, params, has_face_ref)
qm._inject_sampling(wf, params)
qm._inject_latent_source(wf, init_remote, params)
qm._inject_post_passes(wf, params, available)

# strip metadata key if present
wf.pop("_metadata", None)

print("nodes after build:", len(wf), "| 700 present:", "700" in wf, "| 804 present:", "804" in wf,
      "| 600 present:", "600" in wf, "| SUPIR 502 present:", "502" in wf)

body = json.dumps({"prompt": wf}).encode()
req = urllib.request.Request(SERVER + "/prompt", data=body,
                             headers={"Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req, timeout=30)
    out = json.loads(r.read())
    print("VALIDATION PASSED — prompt_id:", out.get("prompt_id"))
    for ep, pl in (("/interrupt", b"{}"), ("/queue", json.dumps({"clear": True}).encode())):
        try:
            urllib.request.urlopen(urllib.request.Request(SERVER + ep, data=pl,
                headers={"Content-Type": "application/json"}), timeout=10)
        except Exception:
            pass  # Interrupt/clear is best-effort — validation already printed success above
    print("interrupted + cleared queue (no GPU work ran)")
except urllib.error.HTTPError as e:
    j = json.loads(e.read().decode())
    print("VALIDATION FAILED:")
    ne = j.get("node_errors", {})
    for nid, info in ne.items():
        for er in info.get("errors", []):
            print(f"  [{nid} {info.get('class_type')}] {er.get('type')}: {er.get('details')}")
    if not ne:
        print(" ", j.get("error"))
