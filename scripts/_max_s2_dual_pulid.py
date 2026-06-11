"""S2 spike (runbook Phase 4; spec §S2): dual-PuLID VRAM + composition.

Injects a SECOND ApplyPulidFlux (node 103, free in the static graph) against
the POST-PRUNE graph: 103 splices between 100 and 100's surviving consumer,
shares the loaders (99 pulid_flux / 101 eva_clip / 97 face_analysis), and
reads its face from a new LoadImage(95, also free). Both weights 0.85.

Go for Pass B (spec): no OOM at N=4+ AND both arc scores >0.70.
This script renders N_RUNS sequential candidates (sequential N does not move
peak VRAM — single-GPU pod, candidates reuse the allocation — so OOM-at-N=4
reduces to OOM-on-any-candidate with the dual stack resident) and polls
/system_stats for peak VRAM between submissions. Arc scoring of the two
faces happens locally afterwards (face_validator_gate), reported per face.

Run: PYTHONPATH=. .venv/bin/python scripts/_max_s2_dual_pulid.py
Requires: both face refs uploaded (Aria + the P1-2 fresh man from
scripts/_max_multichar_pass_a.py step 1).
"""
import copy
import time

import requests

import quality_max as q
from workflow_selector import get_max_quality_params

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
ARIA_REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
MAN_REF = "logs/p12_fresh_face_man.jpg"
PROMPT = ("a woman with short dark wavy hair on the left and a middle-aged "
          "man with a grey beard on the right, standing together in a sunlit "
          "meadow, medium two-shot, both faces clearly visible, "
          "photorealistic, cinematic")
N_RUNS = 4
SEEDS = [990011, 990022, 990033, 990044]
assert len(SEEDS) >= N_RUNS, "raise SEEDS alongside N_RUNS"


def _upload(path, name):
    with open(path, "rb") as f:
        return requests.post(
            f"{URL}/upload/image", files={"image": (name, f, "image/jpeg")},
            data={"overwrite": "true"}, timeout=40).json()["name"]


def _vram():
    s = requests.get(f"{URL}/system_stats", timeout=10).json()
    d = s["devices"][0]
    return (d["vram_total"] - d["vram_free"]) / 1024**3


def build_dual(available, aria_remote, man_remote):
    w = q._load_max_workflow()
    w.pop("_metadata", None)
    q._apply_model_precision(w, "fp16")
    params = get_max_quality_params("portrait")
    q._prune_unavailable(w, available, True, False)
    q._inject_identity(w, None, aria_remote, params, True)  # LoRA-less: isolate the PuLID axis
    q._inject_conditioning(w, PROMPT, None, None, params, True)
    q._inject_sampling(w, params)
    q._inject_latent_source(w, None, params)
    q._inject_post_passes(w, params, available)

    if "100" not in w:
        raise SystemExit("ApplyPulidFlux(100) was pruned — dual spike impossible on this pod")
    # find 100's surviving consumer(s) post-prune
    consumers = [(nid, key) for nid, node in w.items()
                 if isinstance(node, dict)
                 for key, val in node.get("inputs", {}).items()
                 if isinstance(val, list) and len(val) == 2 and str(val[0]) == "100"]
    print(f"post-prune consumers of 100: {consumers}")
    w["95"] = {"inputs": {"image": man_remote}, "class_type": "LoadImage"}
    inputs_103 = copy.deepcopy(w["100"]["inputs"])
    inputs_103["model"] = ["100", 0]
    inputs_103["image"] = ["95", 0]
    w["103"] = {"class_type": "ApplyPulidFlux", "inputs": inputs_103}
    for nid, key in consumers:
        w[nid]["inputs"][key] = ["103", 0]
    return w


def main():
    available = set(requests.get(f"{URL}/object_info", timeout=40).json().keys())
    aria_remote = _upload(ARIA_REF, "s2_aria.jpg")
    man_remote = _upload(MAN_REF, "s2_man.jpg")
    print(f"uploaded: {aria_remote}, {man_remote}")
    base = build_dual(available, aria_remote, man_remote)

    peak = 0.0
    saved = []
    for i, seed in enumerate(SEEDS[:N_RUNS]):
        wf = copy.deepcopy(base)
        wf["25"]["inputs"]["noise_seed"] = seed
        t = time.time()
        pid = requests.post(f"{URL}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
        print(f"[n{i+1}] queued {pid} seed={seed}", flush=True)
        done = False
        err_streak = 0
        for _ in range(90):
            time.sleep(10)
            try:
                peak = max(peak, _vram())
                h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
                err_streak = 0
            except Exception as e:  # noqa: BLE001
                err_streak += 1
                print(f"[n{i+1}] poll err {e}", flush=True)
                # sustained gateway failure = the 502 pattern: ComfyUI process
                # gone (OOM-killed) — exactly the failure this spike probes for.
                if err_streak >= 6:
                    print(f"S2 VERDICT: NO-GO (gateway down {err_streak}0s+ at "
                          f"n={i+1} — ComfyUI likely OOM-killed; peak observed "
                          f"{peak:.1f} GiB before loss)", flush=True)
                    return 1
                continue
            if pid not in h:
                continue
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                msgs = str(st.get("messages"))
                print(f"[n{i+1}] RUN ERROR (OOM?): {msgs[:800]}", flush=True)
                print(f"S2 VERDICT: NO-GO (error at n={i+1}; peak {peak:.1f} GiB)")
                return 1
            if st.get("completed") or st.get("status_str") == "success":
                outs = h[pid].get("outputs", {})
                node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
                imgs = (node or {}).get("images")
                if not imgs:
                    # operator Lane V IMPORTANT (01:27:54Z): a completed run
                    # with empty outputs must FAIL, not count as done — else
                    # the spike exits 0 with nothing to arc-score.
                    print(f"[n{i+1}] completed with NO images — failing", flush=True)
                    return 1
                if imgs:
                    img = imgs[-1]
                    # gateway resets large transfers transiently (bit the
                    # Pass-A driver live) — retry; render is already pod-side.
                    for attempt in range(3):
                        try:
                            dl = requests.get(f"{URL}/view", params={
                                "filename": img["filename"],
                                "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output")}, timeout=300)
                            dl.raise_for_status()  # a 502 RESPONSE is not success
                            break
                        except Exception as e:  # noqa: BLE001
                            print(f"[n{i+1}] download attempt {attempt+1} "
                                  f"failed: {e}", flush=True)
                            time.sleep(5)
                    else:
                        print(f"[n{i+1}] download failed 3x — render is on the "
                              f"pod ({img['filename']}); continuing the VRAM leg",
                              flush=True)
                        done = True
                        break
                    path = f"logs/s2_dual_n{i+1}.jpg"
                    with open(path, "wb") as f:
                        f.write(dl.content)
                    saved.append(path)
                    print(f"[n{i+1}] SAVED {path} ({(time.time()-t)/60:.1f} min, "
                          f"peak so far {peak:.1f} GiB)", flush=True)
                done = True
                break
        if not done:
            print(f"[n{i+1}] TIMEOUT")
            return 1
    print(f"S2 RENDER LEG COMPLETE: {len(saved)}/{N_RUNS} ok, peak VRAM {peak:.1f} GiB "
          f"(arc scoring of both faces = next step, local)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
