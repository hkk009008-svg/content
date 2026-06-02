"""Submit the validated max workflow, let it run, retrieve the output image."""
import json, time, sys, requests

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"
payload = json.load(open("/tmp/max_probe_payload.json"))

r = requests.post(f"{URL}/prompt", json=payload, timeout=30)
if r.status_code != 200:
    print("POST FAILED", r.status_code, r.text[:1500]); sys.exit(1)
pid = r.json()["prompt_id"]
print(f"queued prompt_id={pid}", flush=True)

out_images = None
for i in range(70):  # ~14 min max
    time.sleep(12)
    try:
        h = requests.get(f"{URL}/history/{pid}", timeout=25).json()
    except Exception as e:
        print(f"[{i*12+12}s] history poll err {e}", flush=True); continue
    if pid not in h:
        try:
            q = requests.get(f"{URL}/queue", timeout=10).json()
            print(f"[{i*12+12}s] running={len(q.get('queue_running',[]))} pending={len(q.get('queue_pending',[]))}", flush=True)
        except Exception:
            print(f"[{i*12+12}s] still working...", flush=True)
        continue
    entry = h[pid]
    status = entry.get("status", {})
    sstr = status.get("status_str"); done = status.get("completed")
    print(f"[{i*12+12}s] status={sstr} completed={done}", flush=True)
    if sstr == "error":
        msgs = status.get("messages", [])
        print("RUN ERROR:", json.dumps(msgs)[:2000]); sys.exit(2)
    if done or sstr == "success":
        outs = entry.get("outputs", {})
        # prefer SaveImage node 9; else any node with images
        node = outs.get("9") or next((o for o in outs.values() if "images" in o), None)
        out_images = (node or {}).get("images")
        break

if not out_images:
    print("NO OUTPUT (timed out or no images)"); sys.exit(3)

img = out_images[-1]
fn, sub, typ = img["filename"], img.get("subfolder", ""), img.get("type", "output")
print(f"output image: {fn} (subfolder={sub!r} type={typ})", flush=True)
dl = requests.get(f"{URL}/view", params={"filename": fn, "subfolder": sub, "type": typ}, timeout=120)
path = f"/tmp/max_out_{fn.replace('/', '_')}"
open(path, "wb").write(dl.content)
print(f"SAVED {path} ({len(dl.content)} bytes)")
