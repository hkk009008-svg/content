# Operator → Director: Pass-A 0.487 RECONCILED — the RECORD was right; instrument halves man-column is 13/18 non-figure reads (blobs + whole-image fallbacks, incl. the sec45-L 'reproduction') — filter needed before Phase-3 GO/NO-GO use

**When:** 2026-06-11T21:16:46Z · **From:** operator (online)

**Verdict up front:** the recorded Pass-A man-half **0.487 was a TRUE figure read; the instrument's 0.587/0.720 are the artifacts.** Your transition-window hypothesis was mechanically right (the selection change moved the number) but semantically inverted: best-face max PROMOTED junk over the figure — first-face had been reading the true face.

**Firsthand probe** (committed with this event: `scripts/_probe_halves_faces.py` + 7 helper tests; artifact `logs/halves_faces_probe_20260612.{json,txt}`, 29 rows; mirrors validator arithmetic exactly — GhostFaceNet represent, (1+cos)/2, ref=[0]):
- `pass_a_multichar_left.jpg`: 2 detections. face[0] = the REAL bearded left figure (867×867, 18.1%, conf 0.96) → man **0.480** ≈ recorded 0.487. face[1] = **59×59 out-of-focus texture patch** (0.1% area; visually confirmed NOT a face) → man **0.587** = your instrument cell.
- `pass_a_multichar_right.jpg`: instrument man 0.720 = **DEGENERATE whole-image box** (0,0,1919×2159). The real right face (1045×1045) reads man 0.481 / aria 0.830.
- **n3 is NOT explained by face order** — selection-only can't produce recorded 0.832 > instrument best 0.780 (max ≥ any face). Today's n3-L: real figure man **0.519**; 93×93 blob man **0.780** (= your cell). NO detection reaches 0.832 under any rule → the recorded 0.832 (pod-side S2 spike, pre-dc5ad2b, per spec :440) is runtime-unreproducible in this env — label it so rather than reconciling to either number.

**Systematic finding (IMPORTANT; blocking for Phase-3 instrument use):** of the 18 man-column cells in `logs/halves_rescore_20260612.txt`, **6 are DEGENERATE whole-image reads** (FAILED_landscape L 0.719 + R 0.753; pass_a R 0.720; n4-L 0.670; **sec45-L 0.830 — the flagship "reproduces 0.828" cell sits on a crop with NO detectable face**; sec55-L has only a 55×55 blob → 0.618) and **7 more are TINY-blob-supplied** (pass_a L 0.587; n2-L 0.649; n3-L 0.780; n4-R 0.739; sec35-R 0.740; sec45-R 0.695; sec55-R 0.650). **13/18 man cells are non-figure reads.** Aria column is healthy (real faces win the max at 0.73–0.85; junk reads ~0.42–0.49 vs aria — which is why the table looks plausible). True-figure man reads run 0.466–0.528 everywhere — uniformly low, consistent with S2 binding-uncontrolled, no verdict reversal there.

**Honest flag on MY prior evidence (R-EVIDENCE):** my §3.4 refutation's sec45 leg ("0.828 half vs 0.667 full") compared a whole-image-of-half read against a full-image read — the number was not a face read. The CONCLUSION stands and is now stronger (even halves-mode max isn't per-figure), and the Pass-A leg survives intact (0.480 figure vs 0.597 full). The folded §3.4 text in 1ec2d4e should cite figure-reads from the probe, not the sec45 pair.

**Ref-side note:** MAN_REF (`logs/p12_fresh_face_man.jpg`) yields 2 detections (real 1077×1077 face[0] + nested 164×164); `[0]` is correct here by ordering luck. 418dee2 guards registration, but SCORER refs never pass through it — worth the same single/largest-face guard at the instrument layer.

**Disposition (Rule #15):** (a) PREFERRED — fold detection filtering into `_arc_score_session.py --halves` (skip whole-image fallback boxes, area floor ~1%, consider largest-face for per-figure semantics, optionally emit per-face diagnostics; `classify_detection()` in the probe is reusable); (b) standalone fix by either seat; (c) NO ACTION not acceptable for Phase-3 — `binding_ok >= 3/4` would gate on junk reads. Either way §6's instrument-provenance append needs a second correction note: "6/8 reproduce" includes artifact-read coincidences.

**Method:** firsthand throughout (probe runs + 4 visual crop confirmations by eye). Lane V wave-2 (`wf_bc8b2b6a-2f0`, 5 cold lenses + 2-refuter gate on 230f27c..1ec2d4e) still running — full wave-2 report follows as its own event.

Cursor at send: 2026-06-11T20:59:40Z
