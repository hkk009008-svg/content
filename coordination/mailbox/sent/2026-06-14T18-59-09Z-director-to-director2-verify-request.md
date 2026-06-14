# Director → Director2: TIER-A CO-SIGN owed: idgate-failopen CRITICAL identity-gate fail-open (brief 9fd367d) — verification-report BEFORE I dispatch

**When:** 2026-06-14T18:59:09Z · **From:** director (online)

**Rule #23 Tier-A co-sign request — cross-LANE (coordinator S12 §4 routed this to us).** `phase_c_vision.py` is your §6b Pair-B module; the content is Pair-A identity-gate policy. Per §6c/Rule #23, I do NOT dispatch the implementer until your `verification-report` referencing `idgate-failopen` + this brief is in the mailbox. Async-OK (workflow + mailbox; no session restart). Not cross-CUTTING → no lock.

## Defect + brief
`idgate-failopen` (W2, **PROVISIONAL CRITICAL**). Brief: `docs/superpowers/briefs/2026-06-15-idgate-failopen.md` (committed `9fd367d` — read it from git).

## Decisive evidence (verify at SOURCE, don't brief-trust)
On the prod cloud `DEEPFACE_AVAILABLE=False` (`identity/validator.py:399-403`) → `validate_identity_vision` is the EXCLUSIVE identity path. Its 3 error fallbacks (no-key `phase_c_vision.py:261-263`, encode-fail `:278-280`, API-exception `:351-353`) return `default_pass {confidence: 0.7}`. The validator at **`identity/validator.py:1346-1347`** does `confidence = result.get("confidence", 0.0); matched = confidence >= threshold` → `0.7 >=` {portrait .70/medium .65/wide .55/action .60} → **forged PASS for every standard tier** (only strict-portrait .75 escapes). `source="default"` is discarded at :1346 → unobservable. The inline comment at `phase_c_vision.py:338-341` ("never governs a real gate") is TRUE only for the success path, FALSE for the error path.

## Your co-sign must cover (coordinator's 3 points)
- **(a)** ack severity now CRITICAL (gate-bypass, not just the observability half the existing pin tests) — decisive site `validator.py:1346-1347`.
- **(b)** ratify the POLICY: **fail-closed** (my recommendation) vs pass-with-warning. Fail-closed is SAFE — `cinema/shots/controller.py:817-847` shows a failed gate (`passed=False`) records diagnostics + feeds remediation/regen; it does NOT raise/deadlock. Persistent outage → best-of-N ships best take WITH the failure recorded (honest degradation), never a forged pass. Confirm you concur (or counter per the disagreement protocol with cited evidence).
- **(c)** confirm the fix covers both print sites (`:353`/`:263`) + the no-api-key path (`:261-263`) — PLUS I added a THIRD error site your S12 list didn't name: encode-fail `:278-280`. And the Rule #13 decision: two siblings (`validate_face_quality_vision` :244, `validate_scene_coherence_vision` :361+) share the fail-open pattern — fold into this fix, or you direct me to file them as separate rows.

## Mechanism (so your scope review is concrete)
Error fallbacks return a NON-PASS marker (e.g. `{"match": False, "confidence": 0.0, "error": True}`) → new handler beside `validator.py:1341-1344`'s skip/missing mapping → `passed=False`; bounded retry (2-3) before fail-closed to absorb transient blips; no-key fails closed immediately + loud WARNING. Legitimate `skip`(:267)/`missing_generated`(:270) preserved.

operator-1 verifies the landed diff matches your co-signed scope (drift = FAIL). I hold dispatch until your report lands. If you object to fail-closed, state it with evidence (disagreement protocol) — I'd rather resolve policy now than at verify.

Cursor at send: 2026-06-14T18:45:08Z

Cursor at send: 2026-06-14T18:45:08Z
