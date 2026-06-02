"""Inspect the pod's installed SUPIR node signatures vs local pulid_max.json wiring."""
import json
import requests

URL = "https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai"

SUPIR_CLASSES = [
    "SUPIR_model_loader_v2", "SUPIR_first_stage", "SUPIR_encode",
    "SUPIR_sample", "SUPIR_decode", "SUPIR_conditioner",
]

print("=" * 70)
print("POD SUPIR NODE SIGNATURES")
print("=" * 70)
for cls in SUPIR_CLASSES:
    r = requests.get(f"{URL}/object_info/{cls}", timeout=15)
    if r.status_code != 200:
        print(f"\n[{cls}] NOT PRESENT (HTTP {r.status_code})")
        continue
    info = r.json().get(cls, {})
    inp = info.get("input", {})
    req = inp.get("required", {})
    opt = inp.get("optional", {})
    print(f"\n[{cls}]")
    print("  required inputs:")
    for name, spec in req.items():
        t = spec[0] if isinstance(spec, list) and spec else spec
        print(f"    {name}: {t if not isinstance(t, list) else 'COMBO'}")
    if opt:
        print("  optional inputs:")
        for name, spec in opt.items():
            t = spec[0] if isinstance(spec, list) and spec else spec
            print(f"    {name}: {t if not isinstance(t, list) else 'COMBO'}")
    print(f"  outputs: {list(zip(info.get('output_name', []), info.get('output', [])))}")

print()
print("=" * 70)
print("LOCAL pulid_max.json SUPIR-RELATED NODES")
print("=" * 70)
w = json.load(open("pulid_max.json"))
for nid, node in w.items():
    if isinstance(node, dict) and "SUPIR" in str(node.get("class_type", "")):
        print(f"\nnode {nid} = {node['class_type']}")
        print("  inputs:", json.dumps(node.get("inputs", {}), indent=1))
# Also show what feeds into / out of the SUPIR chain (node 950 = final upscale/save feed?)
print("\n--- consumers of SUPIR nodes (who reads 500/501/502/503) ---")
for nid, node in w.items():
    if not isinstance(node, dict):
        continue
    for k, v in node.get("inputs", {}).items():
        if isinstance(v, list) and len(v) == 2 and str(v[0]) in ("500", "501", "502", "503"):
            print(f"  {nid}({node.get('class_type')}).{k} <- {v}")
