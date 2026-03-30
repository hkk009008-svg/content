# Character Consistency & Identity System

## Philosophy: Real-Photo-First

Characters **require actual uploaded photographs** — NO synthetic character generation. This is a hard rule because:
- DeepFace validation needs real facial features to build reliable embeddings
- Synthetic faces introduce uncanny valley artifacts that compound in video
- Identity thresholds (0.70 production) are calibrated for real photo fidelity

---

## Multi-Angle Reference Generation

From `character_manager.py`:

**Input**: Single front-facing photo uploaded by user

**Process**: FLUX Kontext MAX Multi (via `fal-ai/flux-kontext/max/multi`) with AuraFace embeddings generates **5 additional angle variations**:
- Front (canonical — the upload itself)
- 45-degree left
- 45-degree right
- Profile left
- Profile right
- Back (optional)

**Prompt pattern** (verbatim from code):
> "PRESERVE IDENTITY. Generate the same person from [angle]. Maintain exact facial features, skin tone, hair style, clothing. Identity-preserving angle variation."

**Storage**: Reference images stored in `projects/<project_id>/characters/<character_id>/`

**Why multi-angle matters**: Kling's subject binding and Veo's reference images both perform significantly better with 2–3 angles. A single front-facing photo often produces identity drift during profile/3/4 view shots.

---

## Embedding System

### Architecture
- **Model**: GhostFaceNet (via DeepFace library)
- **Similarity**: Cosine distance mapped from [-1, 1] to [0, 1] via `(1 + cos_sim) / 2`
- **Caching**: Pre-computed embeddings stored as `.npy` files in character directory
- **Loading**: All character embeddings loaded into memory at pipeline start

### Pre-Computation Flow
```
Upload photo → DeepFace.represent(model="GhostFaceNet_w1d1")
  → embedding vector → save to characters/<id>/embedding.npy
  → load at pipeline start → available for all validation calls
```

### Similarity Scoring
```
similarity = (1 + cosine_similarity(ref_embedding, frame_embedding)) / 2
# Result: 0.0 = completely different, 1.0 = identical
# Production threshold: 0.70 (standard for portrait shots)
```

---

## Identity Validation

From `identity_validator.py`:

### Adaptive Frame Sampling
Number of frames sampled from video varies by shot type and video duration:

| Shot Type | Density Multiplier | Typical Frames (5s video) |
|-----------|--------------------|---------------------------|
| Portrait | 2.0x | 10 |
| Action | 1.5x | 7–8 |
| Medium | 1.0x (base) | 5 |
| Wide | 1.0x | 5 |
| Landscape | 0.0x (skip) | 0 |

### Per-Frame Diagnostics
Each sampled frame produces:
```
FrameSample:
  face_detected: bool
  face_confidence: float
  face_area_ratio: float      # face area / total frame area
  face_angle_estimate: str    # "frontal", "three_quarter", "profile"
  similarity: float           # 0.0–1.0 vs reference embedding
  matched: bool               # similarity >= threshold
  failure_reason: FailureReason | None
```

### Shot-Type-Aware Thresholds

From `identity_types.py` `SHOT_TYPE_THRESHOLDS`:

| Shot Type | Strict | Standard | Lenient |
|-----------|--------|----------|---------|
| portrait | 0.75 | 0.70 | 0.60 |
| medium | 0.70 | 0.65 | 0.55 |
| wide | 0.60 | 0.55 | 0.45 |
| action | 0.65 | 0.60 | 0.50 |
| landscape | — | — | — |

### Adaptive Degradation Across Retries

On retry attempts, thresholds degrade linearly:
```
attempt 0: standard threshold (e.g., 0.70 for portrait)
attempt 1: interpolate toward lenient (e.g., 0.65)
attempt 2: lenient threshold (e.g., 0.60)
```

This prevents infinite retry loops while keeping early attempts strict.

---

## Failure Reason Taxonomy

8 enum values from `identity_types.py:FailureReason`:

| Reason | Description | Remediation |
|--------|-------------|-------------|
| `NO_FACE_DETECTED` | No face found in frame | Check framing, increase subject size |
| `LOW_CONFIDENCE_DETECTION` | Face detected but low confidence | Improve lighting, reduce occlusion |
| `FACE_ANGLE_EXTREME` | Profile/back view, can't compare | Accept — PuLID boost won't help |
| `OCCLUSION` | Face partially hidden | Adjust composition, remove obstructions |
| `WRONG_PERSON` | Face matches a different character | Check subject binding references |
| `MULTIPLE_FACES_AMBIGUOUS` | Multiple faces, can't determine target | Specify primary character, crop |
| `SMALL_FACE_REGION` | Face too small in frame | Accept for wide shots — PuLID boost won't help |
| `POOR_LIGHTING` | Lighting prevents reliable comparison | Improve scene lighting constraints |

**Critical**: `FACE_ANGLE_EXTREME` and `SMALL_FACE_REGION` should NOT trigger PuLID weight increases — they are inherent to the shot type, not identity failures.

---

## Identity Anchors

From `character_manager.py:build_identity_anchor()`:

An **identity anchor** is an immutable string describing a character's physical appearance, injected verbatim into EVERY generation prompt.

### Structure
```
"[Character Name]: [exact physical description from character profile]"
```

### Rules
- NEVER modified or rephrased by GPT-4o or any LLM
- Injected as-is into positive prompt
- Prevents prompt-to-prompt description drift
- Includes: skin tone, hair style/color, eye color, distinguishing features
- Does NOT include: clothing (handled by wardrobe tracking)

### Why This Matters
Without anchors, GPT-4o's scene decomposition subtly rephrases character descriptions across shots ("brown hair" → "dark hair" → "auburn hair"), causing cumulative identity drift. The anchor prevents this by using the exact same string every time.

---

## Rolling Statistics for PuLID Feedback

From `identity_validator.py:get_rolling_stats()`:

```python
stats = get_rolling_stats(character_id, window=10)
# Returns:
#   mean_similarity: float     # average across last 10 validations
#   success_rate: float        # % of validations that passed
#   common_failure: FailureReason  # most frequent failure type
#   suggested_pulid_delta: float   # recommended weight adjustment
```

This feeds into `workflow_selector.py:get_adaptive_pulid_weight()`:
- `success_rate < 0.7` → delta = +0.10 (boost PuLID)
- `mean_similarity > 0.8` → delta = −0.05 (relax PuLID)
- `common_failure` is FACE_ANGLE_EXTREME or SMALL_FACE_REGION → delta = 0.0

---

## Voice Assignment

From `character_manager.py`:

**Pool**: 25 ElevenLabs voices (women, men, children, elderly, narrators)

**Voice model**: `eleven_v3`

**Default settings**: Stability 0.55, Similarity 0.85, Style 0.60

**Deduplication**: Within a project, no two characters share the same voice ID.

**Assignment**: Automatic based on character gender/age profile, with manual override support.
