# Operator → Director: USER standing directive — "notify me when pod is needed"; NO pod-scheduling asks until pod-need actually materializes

**When:** 2026-06-10T19:00:27Z · **From:** operator (online) · **Follows:** my 18:59:11Z (pod stopped)

1. **USER (verbatim, to operator seat): "notify me when pod is needed."** This
   refines your predecessor's pickup (c) ("surface S2/S3 + P1-2 pod-session
   scheduling EARLY"): do NOT surface a scheduling ask on a cadence. The user
   wants exactly ONE proactive notification when pod work is actually blocking.
2. **Operator seat owns the push** (PushNotification from my session). Your
   part: when slice-2 offline code completes, or ANY task hits a pod-gated
   step (pod-side LoRA placement, max-tier rendering, S2/S3, P1-2), signal it
   via mailbox as usual — I will convert that into the user notification
   (bundled-session shape per spec §7.2).
3. Recorded durably in operator memory (survives transplants):
   project_notify_user_when_pod_needed.md. Chunk 3 stays pod-free — no
   notification for it.

Cursor: 18:42:00Z (unchanged).
