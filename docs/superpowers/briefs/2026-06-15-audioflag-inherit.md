# R-BRIEF: audioflag-inherit - warn on audio-stream probe failure

PRIORITY: MAJOR        LANE: B (video/assembly/audio)
CROSS-CUTTING: no (touches cinema/shots/controller.py, not auto_approve.py, cinema/context.py, core.py, or web_server.py)

## The Defect

Inventory row: `audioflag-inherit | assembly | cinema/shots/controller.py:241 | MAJOR | swallowed _has_audio_stream failure drops variant audio flags silently -> scene-TTS overwrites real voice; no WARNING logged | xfail-pin tests/unit/test_lane_silent_gate_siblings_xfail.py | lane B | wave 2 | open`.

In `_inherit_audio_flags_from_base`, postprocess variants inherit `audio_embedded` / `dialogue_audio_in_clip` only after `_has_audio_stream(path)` proves the variant has an audio stream. If importing or calling `_has_audio_stream` raises, the helper returns silently. That preserves the existing conservative behavior (do not set flags when the probe failed), but hides a voice-loss path from operators: assembly may treat the variant as audio-less and substitute scene TTS over a clip that actually carried the real voice.

## Rule #12 - grep-the-writes

TARGET SYMBOL: `variant["metadata"]["audio_embedded"]` / `variant["metadata"]["dialogue_audio_in_clip"]`, plus the production caller that writes postprocess variants.

`$ rg -n "_inherit_audio_flags_from_base" cinema/shots/controller.py tests/unit/test_lane_silent_gate_siblings_xfail.py`

```
tests/unit/test_lane_silent_gate_siblings_xfail.py:17:  - cinema/shots/controller.py:241 `_inherit_audio_flags_from_base` (MAJOR, Pair-B/mine):
tests/unit/test_lane_silent_gate_siblings_xfail.py:43:    reason="controller.py:241 _inherit_audio_flags_from_base: when phase_c_ffmpeg."
tests/unit/test_lane_silent_gate_siblings_xfail.py:62:        controller._inherit_audio_flags_from_base(base_take, variant)
cinema/shots/controller.py:214:def _inherit_audio_flags_from_base(base_take: Optional[dict], variant: dict) -> None:
cinema/shots/controller.py:2510:            _inherit_audio_flags_from_base(base_take, variant)
```

`$ rg -n "metadata\\]\\[\\\"audio_embedded\\\"\\]|metadata\\]\\[\\\"dialogue_audio_in_clip\\\"\\]|setdefault\\(\\\"metadata\\\", \\{\\}\\)\\[\\\"dialogue_audio_in_clip\\\"\\]|get\\(\\\"audio_embedded\\\"\\)|get\\(\\\"dialogue_audio_in_clip\\\"\\)" cinema/shots/controller.py cinema_pipeline.py phase_c_ffmpeg.py`

```
cinema_pipeline.py:734:                if take_meta.get("audio_embedded") or take_meta.get("dialogue_audio_in_clip"):
cinema/shots/controller.py:245:    if base_meta.get("audio_embedded"):
cinema/shots/controller.py:247:    if base_meta.get("dialogue_audio_in_clip"):
cinema/shots/controller.py:1796:        if has_dialogue and not take["metadata"].get("audio_embedded"):
cinema/shots/controller.py:1894:        elif has_dialogue and take["metadata"].get("audio_embedded"):
cinema/shots/controller.py:2452:                        variant.setdefault("metadata", {})["dialogue_audio_in_clip"] = True
```

Runtime write confirmed: the postprocess path calls `_inherit_audio_flags_from_base(base_take, variant)` before appending `variant` to `postprocess_variants`; the helper writes the two metadata flags from `base_meta`. Assembly reads those same keys in `cinema_pipeline.py` when deciding whether standalone scene audio should be suppressed.

## Rule #13 - symmetric / sibling audit

SHARED FENCE/FLAG/STATE: audio-embedding metadata that controls assembly TTS suppression.

`$ rg -n "silent|WARNING|warn|DEGRADED|except Exception|_has_audio_stream" cinema/shots/controller.py tests/unit/test_lane_silent_gate_siblings_xfail.py`

Relevant audited sites:

```
cinema/shots/controller.py:238:        from phase_c_ffmpeg import _has_audio_stream
cinema/shots/controller.py:239:        if not _has_audio_stream(path):
cinema/shots/controller.py:241:    except Exception:
cinema/shots/controller.py:1737:                except Exception:
cinema/shots/controller.py:1738:                    logger.warning(
cinema/shots/controller.py:1870:                        logger.warning(
cinema/shots/controller.py:1878:                    logger.warning(
cinema/shots/controller.py:1885:            except Exception:
cinema/shots/controller.py:1889:                logger.warning(
cinema/shots/controller.py:2452:                        variant.setdefault("metadata", {})["dialogue_audio_in_clip"] = True
```

Sibling audit result:

- Native audio generation writes `audio_embedded` directly and logs `audio=embedded-native` on the embedded branch.
- Generation lipsync writes `dialogue_audio_in_clip` only after a result exists; missing result, missing inputs, and exception paths already log WARNING.
- Correction `lip_sync` writes `dialogue_audio_in_clip` directly because it generates new embedded dialogue rather than inheriting base flags.
- The inheritance helper is the remaining same-family silent exception site. Fold it by logging WARNING before the existing return; do not widen behavior to inherit flags on probe failure.

## Full-shape Pattern Reference

MIRROR: nearby best-effort exception logging in `cinema/shots/controller.py`, e.g. scene audio fallback and lipsync degradation paths, uses module logger at WARNING with `exc_info=True` plus relevant `extra` fields. No HTTP endpoint is involved; R-PID is N/A.

## The Fix

Small direct implementation:

- In `cinema/shots/controller.py`, replace the silent `_has_audio_stream` exception return with `logger.warning(...)` and then return.
- Keep `_has_audio_stream(path) == False` behavior unchanged: return without logging and without inheriting flags.
- Convert only `test_inherit_audio_flags_warns_when_has_audio_stream_raises` from strict xfail to live; keep the sibling pins/tests unchanged.

## Verification

Focused:

- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lane_silent_gate_siblings_xfail.py::test_inherit_audio_flags_warns_when_has_audio_stream_raises -q`
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lane_silent_gate_siblings_xfail.py -q`

Repo smoke:

- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`

Expected: focused pin flips live and passes; full pin file passes with existing live siblings; smoke exits OK with only known advisory warnings.
