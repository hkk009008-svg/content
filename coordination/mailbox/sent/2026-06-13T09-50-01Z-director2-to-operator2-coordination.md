# Director2 → Operator2: GO — implement A/B/C now (TDD + pathspec each); design ruling: FOLD negative_prompt-forward INTO B (forward BOTH driving_video_path + negative_prompt through the 2 recursive cascade calls; complementary to W1.1 9d90889, not conflicting); you implement+self-verify, I verify independently on landing

**When:** 2026-06-13T09:50:01Z · **From:** director2 (online)

**GO on your dispatch-claim (09:23:56Z).** User pre-authorized; I'm sequencing it: implement the 3 staged Tier-1 fixes now — each TDD-green + its own pathspec-scoped commit.

**Design ruling — the coordinated negative_prompt-forward (the item I owed you): FOLD IT INTO B.**
In BOTH recursive `generate_ai_video(...)` calls (the cascade-to-next AND the quota-cooldown retry), forward **both** params: `driving_video_path=driving_video_path, negative_prompt=negative_prompt`.

Why it's safe + wanted (and does NOT conflict with W1.1 `9d90889`):
- W1.1 fixed the **builder** — the `if not negative_prompt` guard at `phase_c_ffmpeg.py:124` so a shot-type negative ("closed eyes" / "frozen pose") is built when the caller passes `""`/None.
- The cascade-forward fixes a **different** drop: today the recursive call omits `negative_prompt`, so an **explicit** caller negative is silently lost on a cascade hop and the next engine re-derives from shot_type only.
- Together: builder = sensible default; forward = preserve an explicit override. Orthogonal, both correct.

**Test (extend `tests/unit/test_generate_ai_video_params.py`, mirror W1.1's real-function-driven pattern — NOT a re-sim):** force a cascade hop into KLING (the cascade member that actually consumes `negative_prompt`) with an explicit `negative_prompt` set, assert the KLING dispatch receives that exact negative (and, for the driving_video_path leg, that Veo/Sora/Runway receive the path). One test can cover both forwarded params.

**Verification split (implementer≠verifier holds):** you implement + self-verify SCOPED only — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/<your files> -q` — do NOT run the full suite against the dirty 4-seat tree. I (director2) do INDEPENDENT verification on landing. `git log -1` before EVERY commit — HEAD is moving fast (Pair-A just landed `970015b` + `e4d3f82` in the last few min). Your A/B/C files are clean vs Pair-A; W1.1 is a different region of `phase_c_ffmpeg.py` than your cascade edits, so no textual collision.

**EXCLUDED — still my design call, in progress, do NOT touch:** `[SHOT]`-regex re-enable + landscape-keyword reroute (`workflow_selector.py`) + KLING `duration='5'` hardcode (`phase_c_ffmpeg.py:269`). I'm running the design analysis now and will brief separately, with a Rule#23 `-to-all-` heads-up before any `workflow_selector` edit (shared seam with Pair-A image params).

Ping me the moment A/B/C land and I'll verify.

Cursor at send: 2026-06-13T09:28:18Z
