"""Validate the patched pulid_max.json SUPIR subgraph against the live pod.

Submits to /prompt with a deferred client_id trick? No — we POST normally but
catch the validation error. To avoid actually RUNNING an 8-step max graph, we
isolate the SUPIR tail: feed node 610's input from a trivial EmptyImage-ish
source is hard, so instead we just submit the FULL workflow with placeholders
resolved enough to pass validation (validation only checks types + presence,
not file existence for most loaders). We then read node_errors.

Cheap: ComfyUI validates the whole graph BEFORE executing; a validation failure
returns immediately with node_errors and queues nothing (no GPU). If it PASSES
validation we immediately cancel so nothing heavy runs.
"""
import json, sys, os, urllib.request, urllib.error

SERVER = os.environ.get("COMFYUI_SERVER_URL", "").rstrip("/")
if not SERVER:
    # read from .env
    for line in open(".env"):
        if line.startswith("COMFYUI_SERVER_URL="):
            SERVER = line.split("=", 1)[1].strip().rstrip("/")
print("SERVER:", SERVER)

wf = json.load(open("pulid_max.json"))
del wf["_metadata"]

# Resolve placeholders to harmless real-ish values so validation can proceed.
# Validation checks COMBO membership + link types + required presence — file
# existence for image LoadImage is NOT checked at validate time.
def setp(nid, key, val):
    if nid in wf:
        wf[nid]["inputs"][key] = val

# fill text/image placeholders
for nid, node in wf.items():
    for k, v in list(node.get("inputs", {}).items()):
        if isinstance(v, str) and v.startswith("PLACEHOLDER"):
            if "prompt" in k or "caption" in k or k == "text":
                node["inputs"][k] = "a portrait of a woman"
            elif k == "image":
                node["inputs"][k] = "canonical.jpg"  # any name; not existence-checked
            elif "lora" in k:
                node["inputs"][k] = ""
            else:
                node["inputs"][k] = "x"

# LoraLoader 700 with empty lora_name fails COMBO (empty list). Bypass it like
# quality_max does when no LoRA: rewire its consumers off 700 and drop it.
if "700" in wf:
    # set strengths 0 won't help (still COMBO-empty). Drop + rewire model/clip.
    # 700.model<-112,0 ; 700.clip<-11,0  → consumers of [700,0]->[112,0], [700,1]->[11,0]
    for nid, node in wf.items():
        for k, v in node.get("inputs", {}).items():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) == "700":
                node["inputs"][k] = ["112", 0] if v[1] == 0 else ["11", 0]
    del wf["700"]

# Prune the CN+Redux branch (deferred — those nodes/models absent) the way
# quality_max would for a first shot (no init image).
for nid in ("400","401","402","403","404","410","411","412","420","421","422",
            "431","432","800","801","803","804","810","200","201","250"):
    wf.pop(nid, None)
# rewire BasicGuider.conditioning -> FluxGuidance(60); sampler latent -> EmptyLatent(102)
if "22" in wf: wf["22"]["inputs"]["conditioning"] = ["60", 0]
if "13" in wf: wf["13"]["inputs"]["latent_image"] = ["102", 0]
# FaceDetailer 600 positive/negative referenced 804 (pruned) -> use 60
if "600" in wf:
    wf["600"]["inputs"]["positive"] = ["60", 0]
    wf["600"]["inputs"]["negative"] = ["60", 0]

body = json.dumps({"prompt": wf}).encode()
req = urllib.request.Request(SERVER + "/prompt", data=body,
                             headers={"Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req, timeout=30)
    out = json.loads(r.read())
    pid = out.get("prompt_id")
    print("VALIDATION PASSED — prompt_id:", pid)
    # cancel immediately so nothing heavy runs
    try:
        c = urllib.request.Request(SERVER + "/interrupt", data=b"{}",
                                   headers={"Content-Type": "application/json"})
        urllib.request.urlopen(c, timeout=10)
        # also clear queue
        d = urllib.request.Request(SERVER + "/queue", data=json.dumps({"clear": True}).encode(),
                                   headers={"Content-Type": "application/json"})
        urllib.request.urlopen(d, timeout=10)
        print("interrupted + cleared queue")
    except Exception as e:
        print("cancel note:", e)
    sys.exit(0)
except urllib.error.HTTPError as e:
    err = e.read().decode()
    print("VALIDATION FAILED:")
    try:
        j = json.loads(err)
        ne = j.get("node_errors", {})
        for nid, info in ne.items():
            ct = info.get("class_type", "?")
            for er in info.get("errors", []):
                print(f"  [{nid} {ct}] {er.get('type')}: {er.get('details')}")
        if not ne:
            print(" ", j.get("error"))
    except Exception:
        print(err[:1500])
    sys.exit(1)
