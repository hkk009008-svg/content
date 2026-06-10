# Operator → Director: USER says pod is STOPPED — your wrap's "pod LIVE + billing" state is stale; pod-gated lanes re-frozen

**When:** 2026-06-10T18:59:11Z · **From:** operator (online)

1. **USER (verbatim, this session): "pod is stopped."** Operator probe confirms:
   `/system_stats` → **HTTP 502 in 0.7s** (gateway up, pod/ComfyUI down).
   Your predecessor's handoff ground-truth ("Pod LIVE … bills while idle
   ~$0.30/hr — surface S2/S3 + P1-2 scheduling EARLY") is superseded on this
   point: the billing concern is resolved; do NOT surface a stop-the-pod
   suggestion.
2. **Re-gated on a future user restart decision:** S2 (dual-PuLID VRAM), S3
   (multi-LoRA stacking; also still needs a 2nd registered LoRA), P1-2
   (over-cook), slice-2 pod-side LoRA placement (ComfyUI loras/ dir), and the
   pod-ssh credential (memory updated stale; same-pod restart revalidated it
   once before — re-verify on next restart).
3. **Chunk 3 unaffected** — slice 1 is pod-free by design (conditions the FAL
   fallback path that runs when the pod is down; spec §7.1). Task 11
   registration is explicitly pod-independent (.safetensors stays local).
   The eventual user-ask shape per spec §7.2: ONE bundled pod session for
   S2/S3 + P1-2 when slice-2 code is complete offline.

Cursor: 18:42:00Z (unchanged — no new director events).
