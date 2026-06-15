# R-BRIEF: download-urllib-notimeout - bound Phase-C video downloads

PRIORITY: MAJOR        LANE: B (video/assembly/audio)
CROSS-CUTTING: no

## The Defect

`phase_c_ffmpeg.py` downloads generated video artifacts from seven provider
branches with `urllib.request.urlretrieve(url, output_mp4)`. Those calls have
no connect or read timeout, so a stalled CDN transfer can block the pipeline
thread indefinitely instead of failing into the cascade.

Inventory row:

```text
$ rg -n "download-urllib-notimeout" docs/REMEDIATION-INVENTORY.md
docs/REMEDIATION-INVENTORY.md:54:| download-urllib-notimeout | io | phase_c_ffmpeg.py:490 | MAJOR |  | 7 urlretrieve download sites have no timeout parameter; stalled CDN transfer blocks the pipeline thread indefinitely; except Exception never fires until OS TCP keepalive expires; all 7 video engine download paths affected | yes | tests/unit/test_discovery_io_xfail.py | B |  | 2 | open |  | discovery wf_13f9d2f6-f93 [idx 8]; no socket.setdefaulttimeout() in repo; sibling ltx_native.py uses explicit timeout= |
```

## Rule #12 - Grep The Writes

TARGET WRITE PATH: provider result URL -> `output_mp4`.

```text
$ rg -n "urllib\.request\.urlretrieve\(" phase_c_ffmpeg.py
phase_c_ffmpeg.py:490:                urllib.request.urlretrieve(video_url, output_mp4)
phase_c_ffmpeg.py:550:                    urllib.request.urlretrieve(video_url, output_mp4)
phase_c_ffmpeg.py:633:                    urllib.request.urlretrieve(video_url, output_mp4)
phase_c_ffmpeg.py:738:                        urllib.request.urlretrieve(video_url, output_mp4)
phase_c_ffmpeg.py:824:                    urllib.request.urlretrieve(video_url, output_mp4)
phase_c_ffmpeg.py:870:                urllib.request.urlretrieve(final_video_url, output_mp4)
phase_c_ffmpeg.py:957:                            urllib.request.urlretrieve(video_url, output_mp4)
```

Runtime write sites are confirmed in production code. The target is not a type
declaration; each listed branch writes the provider artifact directly to
`output_mp4`.

## Rule #13 - Sibling Audit

SHARED STATE: externally returned generated-video URL written to a local video
artifact.

Existing bounded-download sibling pattern:

```text
$ sed -n '35,78p' performance/_net.py
def safe_download(
    url: str,
    dest_path: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
    allow_http: bool = False,
) -> Optional[str]:
    """Stream a URL to dest_path with safety guards. Returns dest_path on success, None on failure.
...
        with requests.get(url, stream=True, timeout=(connect_timeout, read_timeout)) as r:
```

```text
$ nl -ba performance/act_one.py | sed -n '120,126p'
   120        out_url = (final.get("output") or [None])[0]
   121        if not out_url:
   122            print("   [ACT-ONE] SUCCEEDED but no output URL")
   123            return None
   124        if not safe_download(out_url, output_mp4):
   125            return None
   126        _cost_log("performance_capture", duration_s, shot_id, video_id, cost_tracker=cost_tracker)
```

```text
$ nl -ba lip_sync.py | sed -n '333,337p'
   333        out_url = result.get("video", {}).get("url")
   334        if out_url:
   335            if safe_download(out_url, output_path) is None:
   336                logger.warning("sync.so v3 download failed", extra={"engine": "syncSoV3"})
   337            elif _overlay_gate_or_stash("syncSoV3"):
```

Sibling disposition:

- Fold the seven `phase_c_ffmpeg.py` generated-video download branches into
  the `safe_download` pattern and return `try_next_api()` on download failure.
- Do not fold unrelated image/audio/script `urlretrieve` sites in this row.
  They are outside the inventory row and have different artifact semantics.
- `ltx_native.py` has both native `urlopen(..., timeout=...)` sites and FAL
  fallback `urlretrieve` sites. This brief records that sibling as deferred
  because the committed pin and row scope are `phase_c_ffmpeg.py`.

## Full-Shape Pattern Reference

MIRROR: `performance._net.safe_download(url, dest_path, ..., allow_http=False)`.

Full shape:

- Validates URL scheme and host.
- Streams with `requests.get(..., timeout=(connect_timeout, read_timeout))`.
- Caps response size.
- Returns `dest_path` on success and `None` on failure.
- External-provider callers use default HTTPS-only behavior; trusted internal
  ComfyUI pod callers pass `allow_http=True`.

In `generate_ai_video`, the matching return contract is cascade, not `None`, so
the local helper should call `safe_download(...)` and return `try_next_api()` if
the download fails.

## The Fix

Bounded direct implementation, no subagent implementer:

- Import `safe_download` in `phase_c_ffmpeg.py`.
- Add a small local `_download_video_or_cascade(video_url, engine)` helper
  inside `generate_ai_video`.
- Replace all seven `urllib.request.urlretrieve(..., output_mp4)` branches with
  the helper and preserve each branch's existing success path.
- Remove the now-unused branch-local `urllib.request` imports.
- Promote `tests/unit/test_discovery_io_xfail.py` from strict xfail to a live
  static regression that proves:
  - `phase_c_ffmpeg.py` has zero raw `urllib.request.urlretrieve` calls.
  - the helper calls `safe_download`.
  - the seven provider branches call the helper.
- Update `docs/REMEDIATION-INVENTORY.md` to identify the live selector and leave
  status `open` pending operator2 Lane V and coordinator reconciliation.

## Verification

Expected local verification:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_io_xfail.py -q
```

Expected wave-gate effect:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
```

Wave 2 should remain `UNMET`, but `tests/unit/test_discovery_io_xfail.py` should
no longer appear as a failing open row under `--runxfail`.
