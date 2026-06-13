# Director-Seat Transplant Handoff — 2026-05-29 (cycle 17 POST-MID-5)

**Outgoing director-seat session:** cold-pickup at `1dc72d2` → ARCHITECTURE §9.7 stale-fix → `_build_transition_prompt` delete → d90036b close → **Lane V #25 M1 fix (brainstorm→spec→plan→TDD)** → DECISIONS template relocate → ARCHITECTURE M1-sync → handoff.
**Inheritor:** next director-seat.
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-29-cycle17-post-mid-4.md`.
**Companion (operator side):** `docs/HANDOFF-operator-transplant-2026-05-29-cycle17-postMID-4.md` (`95533a0`, reconciled `a031a47`). **Both seats are transplanting this cycle** — the next operator picks up Lane V #26 + the Novita bring-up.
**HEAD at handoff:** `a6cc18c` (origin sync on final push — carries the operator's `95533a0`/`a031a47` + my `a6cc18c`).
**Pytest:** `1229 passed / 3 skipped` in `tests/unit/` (verified at handoff via `.venv/bin/python -m pytest tests/unit/ -q`). **§15 smoke OK** (anchor + sha-ref + manifest gates clean).
**Pod:** RunPod DOWN (`/system_stats` → HTTP 404). **⚠️ Novita H100 bring-up IN-FLIGHT** — user mid-bootstrap; see operator handoff ⚠️B for the full runbook.

---

## TL;DR — five closes, one of them the M1 fix

1. **Lane V #25 M1 CLOSED** (`a2798ad`) — the mixed-audio-presence xfade bug. Full brainstorm→spec→plan→TDD per user direction. `xfade_concat` now pads silent legs with `anullsrc` + normalizes every leg → embedded audio preserved across the stitch instead of dropped. **Real-ffmpeg verified (no pod needed — it's CPU/ffmpeg).**
2. **`_build_transition_prompt` dead-code RESOLVED** (`7682c12`) — the long-open delete-vs-wire roadmap call: deleted (0 callers; superseded by the ffmpeg xfade route), user-approved. + −29 ARCHITECTURE re-anchor + 4 skill-doc de-references.
3. **d90036b orphaned-SHA finding CLOSED** (`435efd2`) — operator's SHA-ref checker (`af6d69f`) caught CLAUDE.md citing an orphaned v4-ship SHA 6×; fixed → `7da49ed` (Guard-1 re-verified).
4. **ARCHITECTURE stale-claims fixed** — §9.7 F1-conditional (`6911477`) at pickup; §9.7 M1-sync + §16 count 1223→1229 (`a6cc18c`) at handoff.
5. **DECISIONS ADR template relocated** (`1aff64e`) — operator doc-maint flag; the `ADR-NNN` template was stranded between ADR-015/016, moved to the true bottom (Guard-1: intentional template, not cruft).

---

## What's CLOSED + verified

| Item | Status | Refs |
|---|---|---|
| **Lane V #25 M1** (mixed-audio xfade) | ✅ fixed (anullsrc-pad); 16/16 xfade tests incl a **real-ffmpeg integration test** (mixed → output HAS audio @ ~5.5s; RED pre-fix); no `cinema_pipeline.py` change | `7d15180`+`a2798ad`; spec/plan `docs/superpowers/{specs,plans}/2026-05-29-xfade-mixed-audio-anullsrc*` |
| `_build_transition_prompt` dead-code | ✅ deleted, 0 callers, user-approved | `7682c12` |
| d90036b orphaned v4-ship SHA (6× CLAUDE.md) | ✅ → `7da49ed`; verifier `--sha-refs` clean | `435efd2` |
| ARCHITECTURE §9.7 (F1 + M1) + §16 count | ✅ synced (conditional acrossfade; M1 padded; 1229) | `6911477`, `a6cc18c` |
| DECISIONS stranded ADR template | ✅ relocated to bottom; ADRs contiguous 001-019 | `1aff64e` |
| Branch | ✅ suite 1229/3 green, smoke OK, 19 ADRs (ADR-019), Rules→#18 (v5.6) | — |

---

## 🟡 OPEN ITEMS (next director)

1. **⚠️ Novita GPU pod bring-up — IN-FLIGHT (biggest unblock).** User is replacing the down RunPod pod with a **Novita H100 SXM 80GB** + `setup_runpod.sh`. Operator can't SSH-drive it (no key in non-interactive shell); **user drives, operator/director guides**. Full runbook (instance ID, SSH, the `COMFYUI_SERVER_URL` wiring, the DOWN→UP check) is in the operator handoff §B. **Once UP, the entire GPU backlog unparks — including scene-transitions end-to-end validation (which now includes the M1 fix).**
2. **Lane V #26 on the M1 fix (`7d15180`+`a2798ad`)** — **director-invited, NOT mandatory** (I framed the Rule #9 cold second-opinion as optional in coord `T06:17:07Z`; operator reconciled to that in `a031a47`). My own verification was thorough (16/16 incl real-ffmpeg, full suite green), so it's a confidence-add, not a blocker. Next operator's call.
3. **Scene-transitions real-render validation — STILL pod-gated.** The M1 fix + the F1 fix are unit/integration-verified at the **ffmpeg layer** (local). The full **multi-scene render with transitions ON + mixed-audio scenes** end-to-end is unverified until a pod (Novita) is up. This is the one piece of M1/transitions that genuinely needs GPU-produced multi-scene inputs.
4. **Pod-INDEPENDENT backlog you can spec+build now** (the M1 playbook): **B2 (`evaluate_generation_quality` wire)** + **SD3_5 dispatcher**. Both are CPU/wiring or pattern-mirror work — spec-able + likely buildable without the pod, exactly like M1 was. (See the key insight below — don't lump these with the GPU backlog.)
5. **upscale dispatch (Topaz/SUPIR/CCSR)** — needs a **user design decision** before specing.
6. **GPU-gated backlog (unparks on Novita UP):** HiDream firing + Korean-dialogue re-probe + `storyboard_mode` + dialogue/storyboard/HiDream validation · research_location Part 2 · max-tier SUPIR/HiDream (**NOT** in `setup_runpod.sh` — separate provisioning per operator §B).
7. **Rule #18 doc-maintenance graduation tracking** — null-hypothesis HOLDS at N=2 (operator's first dispatch, `e726976`): ephemeral suffices, don't graduate (needs N≥3 + residual>ephemeral + prose-stays-true). **Buildout signal:** §16-test-count-vs-pytest + §17-orphan-caller-grep are the next automatable claim-types (the bridge-sunset thesis — keep shrinking hand-work).
8. **`~/Downloads/PROPOSAL-doc-maintenance-role-v1.md`** — stale provenance (carry-forward); user's to discard. Not in-repo.

---

## What the next director needs to know

1. **KEY INSIGHT — bucket the backlog; ffmpeg/CPU work is NOT pod-gated.** `ffmpeg 8.1` is local. The M1 fix was specced, built, AND verified (real-ffmpeg integration test) with the pod DOWN. So: **CPU/ffmpeg + wiring/dispatch-logic work = buildable now**; **only GPU image/video *generation* needs the pod.** Don't defer pod-independent work waiting on Novita.
2. **The M1 anullsrc-pad pattern** lives in `phase_c_ffmpeg.py::_build_xfade_filtergraph` (3-case: all-audio raw / none video-only / mixed → normalize+pad). Spec + plan in `docs/superpowers/` document the design + the de-risk (step-5 voice mux is decoupled from stitch audio — `cinema_pipeline.py:1362`).
3. **Both seats transplanted.** Next operator's priorities are Lane V #26 + Novita (their handoff). Expect concurrent commits when they pick up; this session had heavy healthy concurrency (operator shipped the SHA-ref checker + doc-maint N=2 while I did M1) — git serialized cleanly, disjoint files, explicit staging throughout.
4. **Doc-truth tooling grew this cycle:** `check_doc_claims.py` now covers line-anchors + manifest-symbols + **SHA-refs** (`af6d69f`); `scripts/ci_smoke.py` runs all three gates. Use `scripts/status.py` for the git/mailbox/ADR/anchor/pod dashboard.
5. **Pod pre-flight:** RunPod `curl -sI https://525nb9d5cc0p3y-8188.proxy.runpod.net/system_stats` (404 = down). For Novita, follow operator §B to get + wire the new endpoint. **Key rotation: user DECLINED — do NOT re-recommend.**
6. **Co-Authored-By trailer is version-agnostic** (harness injects 4.8).

---

## Mailbox state at handoff

Director cursor: **`T04:47:48Z`** (consumed operator's doc-maint N=2 notice). Last director-sent: **`T06:17:07Z`** (M1-closure + N=2-ack + DECISIONS-disposition coordination). Operator consumed it (their `a031a47` reconcile advanced operator cursor → `T06:17:07Z`). **0 director-unread at handoff.**

---

## Sign-off

Cycle-17 POST-MID-5. Picked up at `1dc72d2`; shipped five closes — the headline being **Lane V #25 M1** (mixed-audio xfade, anullsrc-pad, full brainstorm→spec→plan→TDD, real-ffmpeg-verified with the pod down) — plus the `_build_transition_prompt` dead-code resolution, the d90036b orphaned-SHA fix (operator's SHA-ref-checker catch), ARCHITECTURE §9.7/§16 syncs, and the DECISIONS ADR-template relocate. Suite 1229/3 green, smoke OK, 19 ADRs, Rules→#18. **Open for next director:** track the Novita bring-up (biggest unblock; once UP → scene-transitions end-to-end + the GPU backlog), the optional Lane V #26, and the pod-independent B2/SD3_5 specs (ffmpeg/CPU work builds now — that's the session's transferable lesson). Both seats transplanted; coordinate with the next operator.

Signed,
Director-seat — 2026-05-29 (cycle 17 POST-MID-5).
