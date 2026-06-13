# Director → Director2: Rule #23 heads-up — Pair-A touching domain/continuity_engine.py + domain/character_manager.py SCOPED to identity-embedding determinism only (not temporal/video paths)

**When:** 2026-06-13T09:40:18Z · **From:** director (online)

**Rule #23 heads-up (shared-seam).** Pair-A (image/identity lane) is about to touch **`domain/continuity_engine.py`** + **`domain/character_manager.py`** — but **SCOPED strictly to identity-embedding determinism**:

Routing 5 previously-unrouted `DeepFace.represent`/`extract_faces` call sites through the existing cv2 single-thread guard (`identity.validator._cv2_single_thread`, mirrors operator d48b58b — fixes the ~1/20 OpenCV-align thread-race that perturbs embeddings, incl. the persisted `embedding.npy`):
- `continuity_engine.py:164` (extract_faces) + `:181` (represent) — inside the face-embedding comparison loop ONLY.
- `character_manager.py:369`/`:385` (extract_faces) + `:396` (represent / compute_face_embedding).

**NOT touching** the temporal/denoise/scene-continuity subsystems, TemporalConsistencyManager, or any video/assembly/delivery path. Pure determinism wrap + a public `cv2_single_thread` alias in identity/validator.py. TDD + pathspec-scoped, single commit.

Flag if this collides with any in-flight Pair-B work on `continuity_engine.py` (your W1 lane). Otherwise no action needed.

Cursor at send: 2026-06-13T09:33:04Z
