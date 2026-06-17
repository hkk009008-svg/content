# R-BRIEF: identity-arcface-embselect - deterministic reference-face selection

PRIORITY: MINOR        LANE: A (image/identity)
CROSS-CUTTING: no (does not touch auto_approve.py, cinema/context.py, core.py, or web_server.py)
LOCK: none required. CO-SIGN: not required.

## The Defect

`identity/validator.py` used `_get_embedding` for production reference embeddings
in both `validate_image` and `validate_video`. Before this fix, `_get_embedding`
selected `emb_list[0]`; DeepFace detection order is not a stable proxy for the
intended reference face. The binding instrument already used a largest-OK
selector, so multi-detection reference images could diverge between production
validation and binding measurements.

## Rule #12 - Grep The Writes

TARGET SYMBOL: production reference embedding write paths (`ref_emb`,
`ref_embeddings[cid]`, and the `_get_embedding` cache write).

```text
$ rg -n "_get_embedding\(|ref_embeddings\[cid\] = emb|ref_emb = self\._get_embedding|embedding_cache\[cache_key\] = emb" identity/validator.py
452:        ref_emb = self._get_embedding(reference_path, character_id)
811:            emb = self._get_embedding(ref_img, cid)
813:                ref_embeddings[cid] = emb
960:    def _get_embedding(self, image_path: str, cache_key: str = "") -> Optional[np.ndarray]:
976:                    self.embedding_cache[cache_key] = emb
989:                    self.embedding_cache[cache_key] = emb
```

Runtime write sites are in `validate_image` and `validate_video`; both route
through `_get_embedding`, and `_get_embedding` writes the selected embedding to
memory/disk cache when a cache key is supplied.

## Rule #13 - Symmetric / Sibling Audit

SHARED STATE: reference embedding selection from DeepFace `represent` output.

```text
$ rg -n "_ref_embedding_largest_ok|_largest_ok_embedding|_analyze_single_image|_analyze_frame|emb_list\[0\]" identity/validator.py tests/unit/test_discovery_identity_xfail.py
tests/unit/test_discovery_identity_xfail.py:178:# largest-OK selection rather than emb_list[0].
identity/validator.py:166:def _largest_ok_embedding(
identity/validator.py:317:def _ref_embedding_largest_ok(ref_path: str, ref_name: str = "ref") -> Optional[np.ndarray]:
identity/validator.py:390:        return np.array(emb_list[0]["embedding"])
identity/validator.py:457:        frame_sample = self._analyze_single_image(
identity/validator.py:673:                    ref_embs[char_id] = _ref_embedding_largest_ok(ref_path, char_id)
identity/validator.py:854:                per_char = self._analyze_frame(
identity/validator.py:985:                emb = _largest_ok_embedding(image_path, emb_list)
identity/validator.py:987:                    emb = np.array(emb_list[0]["embedding"])
identity/validator.py:1045:    def _analyze_frame(
identity/validator.py:1126:                        face_emb = np.array(emb_list[0]["embedding"])
identity/validator.py:1172:    def _analyze_single_image(
identity/validator.py:1183:                # Score the BEST-matching detected face, not emb_list[0]: on a
```

Audited siblings:

- `validate_image`: folded through `_get_embedding`.
- `validate_video`: folded through `_get_embedding`.
- `_ref_embedding_largest_ok`: existing binding-instrument sibling already uses
  largest OK selection; code comment updated so it no longer says production is
  divergent.
- `_analyze_single_image`: already scores best matching generated face, not
  first detection; no change needed.
- `_analyze_frame`: crop-level generated-face scoring still uses the crop's
  single embedding and then best similarity per detected face; not the reference
  selection defect.

## Full-Shape Pattern Reference

MIRROR: `_ref_embedding_largest_ok` in `identity/validator.py`.

Shape to mirror: load image dimensions, classify each DeepFace detection with
`_classify_face_detection`, choose the largest OK detection with deterministic
geometry tie-break, and preserve fallback to `emb_list[0]` when no OK face or
usable dimensions exist.

## The Fix

Add `_largest_ok_embedding(image_path, emb_list)` and route `_get_embedding`
through it before the existing first-detection fallback. This keeps scope to
`identity/validator.py` and the regression pin file, while making both
`validate_image` and `validate_video` inherit the corrected reference selector.

## Verification For Operator

RED observed before production change:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_get_embedding_uses_largest_ok_face_not_first_detection -q
FAILED tests/unit/test_discovery_identity_xfail.py::test_get_embedding_uses_largest_ok_face_not_first_detection
E AssertionError: _get_embedding must select the largest OK detection for reference images instead of trusting arbitrary DeepFace detection order
```

GREEN after fix:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_get_embedding_uses_largest_ok_face_not_first_detection -q
1 passed in 1.61s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py -q
4 passed in 1.68s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_identity_validator.py -q
76 passed in 1.91s
```

Operator should verify the focused selector plus the full validator file and
confirm the diff stays within the coordinator packet scope.
