"""Client-side timeout bounds for `fal_client.subscribe` calls.

fal_client 1.0.0 waits INDEFINITELY when `client_timeout` is not set, so a
single hung FAL job stalls the entire pipeline run. On expiry the SDK
cancels the remote request and raises `FalClientTimeoutError` (an
`Exception` subclass) — every production call site sits inside a
provider-cascade / fallback except-handler that routes around the failure,
so a timeout degrades to "this provider failed, try the next" instead of
an indefinite hang.

One source of truth: `tests/unit/test_fal_subscribe_timeouts.py` rejects
inline `client_timeout` literals at call sites and fails any new
`fal_client.subscribe` that doesn't pass a bound from here.
"""

# Per-shot generation-class jobs: video gen (Sora-2 / Veo 3.1 / Kling v3 /
# fast-svd / LTX), per-shot overlay lip-sync (sync-lipsync / MuseTalk /
# LatentSync), RIFE interpolation, SeedVR video upscale, Pixverse face swap,
# Stable Audio music. These all process short per-shot clips (4-10s) or
# seconds-fast audio. Observed Kling i2v slow tail is 178-195s
# (kling_native's poll bound is 300s for the same reason) and Seedance's own
# status-poll loop bounds at 600s; 600 clears slow tails plus FAL queue wait
# while still bounding a genuinely stuck job.
FAL_TIMEOUT_VIDEO_S = 600

# Talking-head GENERATION engines (Kling lipsync audio-to-video, Omnihuman
# 1.5, Creatify Aurora, Hedra Character-3): runtime scales with AUDIO length,
# and lip_sync_mode="generation" feeds scene-level audio. Measured ~40x
# realtime locally (logs/_lipsync_gen_test.log: 3.84s audio -> 156s wall,
# 720p, turbo off), so a contract-legal 60s job extrapolates well past 600s
# — and client_timeout CANCELS the in-flight job on expiry, which would
# silently downgrade Omnihuman -> Aurora 720p on the capability-maximized
# path (review wf_e0d1765b, adversarially confirmed). 1800 covers 60s audio
# at the measured rate plus queue wait.
FAL_TIMEOUT_TALKING_HEAD_S = 1800

# FLUX image fallbacks (kontext-multi / v1.1-ultra / schnell): seconds-fast
# inference; 180 absorbs queue wait.
FAL_TIMEOUT_IMAGE_S = 180
