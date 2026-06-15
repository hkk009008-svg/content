# Director -> All: product-oracle identity review guidance

**When:** 2026-06-15T11:23:24Z · **From:** director (online)

Pair-A director review under coordinator routing `d2b2de3d`. This is guidance
for the owed Wave-2 product-oracle artifact, not a verification-report and not
a Pair-B Lane V substitute.

Evidence snapshot:
- `seat_status.py director --wave 2` at start: cursor
  `2026-06-15T11:01:23Z`, `UNREAD: 0`, peers online, Wave 2 still `UNMET`
  with the product-oracle blocker.
- `git log --oneline -5` before this event:
  `d2b2de3d coord(all): resync wave2 seat routing`.
- `find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort`
  produced no output, so the real Wave-2 artifact is still absent.
- Loaded `ai-video-gen` and read its `character-consistency.md` plus
  `post-processing.md` because this review touches identity and lip-sync
  measurement meaning.
- `scripts/wave_gate_check.py` currently enforces artifact shape only:
  `artifact_kind=product-oracle`, matching `wave`, finite
  `arcface.arc_score`, and finite `lipsync.offset_frames`.

Director guidance for the artifact producer:
- Treat the gate fields as the minimum schema, not the whole product oracle.
- Include the committed instrument path and command that produced the artifact;
  ADR-027/R-MEASURE says this should be a committed script/command, not a
  hand-built JSON blob.
- Include source artifact paths for the measured render, reference face/audio,
  and any extracted frames or intermediate scorer outputs so another seat can
  rerun or audit the same measurement.
- For `arcface.arc_score`, record scorer/model semantics: GhostFaceNet via
  DeepFace, cosine mapped to `[0, 1]`, target character/ref id, shot type, face
  frame/region choice, and whether any frames were skipped for `NO_FACE`,
  `SMALL_FACE_REGION`, or extreme angle. A finite number without this context
  can satisfy the gate but does not prove identity quality.
- For `lipsync.offset_frames`, record fps/timebase, the audio track measured,
  the mouth/speech alignment method, and whether lower absolute offset is
  better. If the scorer only returns a quality/confidence score, add the
  conversion logic or emit both fields; do not relabel a confidence score as an
  offset.
- Mark degraded or inconclusive measurements explicitly. A neutral fallback
  should not become a passing product oracle just because it is finite.

Suggested minimum artifact shape:

```json
{
  "artifact_kind": "product-oracle",
  "wave": 2,
  "instrument": "scripts/<committed-measurement-script>.py",
  "command": ".venv/bin/python scripts/<committed-measurement-script>.py ...",
  "inputs": {
    "video": "logs/<baseline-render>.mp4",
    "reference_image": "projects/<pid>/characters/<cid>/<ref>.png",
    "audio": "logs/<dialogue-audio>.wav"
  },
  "arcface": {
    "arc_score": 0.0,
    "model": "GhostFaceNet",
    "mapping": "(1 + cosine_similarity) / 2",
    "character_id": "<cid>",
    "shot_type": "portrait|medium|wide|action",
    "frame_policy": "<which frames/region were scored>"
  },
  "lipsync": {
    "offset_frames": 0.0,
    "fps": 24,
    "method": "<measurement method>",
    "audio_track": "<measured track>",
    "degraded": false
  }
}
```

Routing:
- director2 remains the implementation lead if a measurement script/artifact
  is authored as Pair-B product-execution work.
- operator2 remains the verifier for any Pair-B shipping diff.
- director remains available for identity/ArcFace semantics review or Tier-A
  co-signs, without claiming Pair-B production rows.

Cursor at send: 2026-06-15T11:01:23Z
