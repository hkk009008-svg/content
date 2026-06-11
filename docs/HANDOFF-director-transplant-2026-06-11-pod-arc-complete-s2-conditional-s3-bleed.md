# Director transplant handoff — 2026-06-11 (midday): POD ARC COMPLETE — Pass-A GREEN (fix confirmed live), S2 VRAM-GO/identity-CONDITIONAL, S3 BLEED at all strengths, 2nd LoRA trained+placed, FAL price verified, pod RELEASED

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-10-slice2-complete-pod-bundle-executing.md`
(its ⭐#1 fully discharged: pod stop/keep surfaced AND the user authorized the
full bundle instead; Pass-A diagnosed + FIXED + re-run GREEN; S2 spike run;
arc scores exist; spec §6 records landed; the (e) user asks — S3 funding and
FAL price — BOTH discharged this session).

## Ground truth (verified at wrap, 2026-06-11T~03:45Z)

- **Suite: 2151/0 — operator full recount at `3a589da`** (includes my
  dc5ad2b + 3a589da); commits since are docs/coord-only (verified via
  `git log 3a589da..HEAD --stat` — only .md files). Smoke OK + doc gate
  "no drift" re-run at wrap.
- **Mailbox: cursor 03:24:38Z, 0 unread** (operator wrap event consumed;
  fold rides this handoff's commit). Operator WRAPPED `da9edf8` + amendment
  `501f8a6` (folded my pod-arc closure). **Their next session leads with
  Lane V on `dc5ad2b`** (best-face scoring feeds every arc number in the
  S2/S3 verdicts; suite-green ≠ reviewed), then `3a589da` + `d870f9e` +
  the pod-arc batch per my 03:37:10Z enumeration.
- **POD: user told STOPPABLE (~02:30Z) and answered "stop it" guidance
  (~03:40Z "do you need pod running?" → NO).** Do NOT assume stopped:
  probe the gateway at session start; **if it answers 200, surface the
  billing immediately** (P2-2 guardrails still NOT_DONE — now
  thrice-relevant). Stopped-not-terminated keeps everything: credential,
  ComfyUI, BOTH character LoRAs in `loras/` (`char_lora_fal_v2` Aria +
  `char_lora_man_v1` TOKman). Terminated = credential + placements gone
  (memory `pod-ssh-credential` updated).
- **Push: local ~25 ahead of origin `107b347` (last CI-green run
  27312370385) — USER-gated as always.** Surface a push opportunity when
  the user is engaged.
- Pod-work authorization was verbatim this session ("do it all that
  requires pod") — it does NOT carry to the next session (seat- AND
  session-scoped; classifier precedent).

## What landed this session (director seat, chronological)

1. **Pass-A root cause + fix `945d022`** (TDD 6 RED→GREEN): the driver's
   partial `shot_hint` replaced the inferred fallback (`shot_hint or {…}`)
   → `characters_in_frame` lost → LANDSCAPE class → identity stack zeroed +
   arc gate off + untuned landscape sampling arm. `_resolve_shot_info` now
   MERGES (explicit keys win; LoRA/secondary payloads infer presence). The
   false "bypasses re-classification" docstring fixed. Operator verified
   the fix HOLDS (114-claim Lane V, convergence #3).
2. **Pass-A re-run through the REAL dispatch: GREEN** — `medium` class,
   gates live, 8 candidates, best arc 0.819, `QUALITY_MAX`. Failed artifact
   preserved (`logs/pass_a_multichar_FAILED_landscape_20260610.jpg`).
3. **S2 dual-PuLID spike (4/4): VRAM GO** (peak 41.8 GiB = +0.4 over the
   41.4 baseline) **/ identity CONDITIONAL-GO** — both ≥0.70 in 2/4 seeds
   (best 0.832/0.773) BUT identity↔figure binding UNCONTROLLED (man's
   geometry on the beardless figure, beard on the aria-geometry figure).
   Metric calibrated: cross-identity floor 0.447, self 1.000.
4. **S3 stacking sweep (3/3): BLEED at all strengths {0.35,0.45,0.55}** —
   all arms render two Aria-homogenized women (wardrobe bleed, beard-token
   neck artifact); **visual verdict overrides embeddings** (sec45 L:man
   0.828 would have false-GO'd). Finding: pure-LoRA secondary under a
   PuLID-anchored primary cannot hold distinct visual identity.
5. **2nd character LoRA trained + placed** (`char_lora_man_v1`, TOKman,
   2500 steps, ~$5.40 user-funded-authorized; production-recipe Kontext
   angle set `logs/man_lora_refs/`; operator validated the artifact —
   684 BF16 tensors). Re-run guard + client_timeout added `3a589da`.
6. **FAL price VERIFIED $0.08/output-image** (kontext/max/multi model
   page; no per-input-ref surcharge listed) — cost_tracker + spec rows
   `78c1053`, direct price pin `3a589da`. 3-session user-ask DISCHARGED.
7. **`dc5ad2b` validator fix (TDD):** `validate_image` scored only the
   FIRST detected face — multi-char frames false-negatived. Best-face now.
   **UNREVIEWED — operator's next Lane V leads with it.**
8. **ADR-023 + halt_rule per-shot-class defaults `ec21c0a`** (operator
   latent-gap disposition): portrait/medium → conjunctive (their 0.83 arc
   thresholds were DEAD under the composite_only fallback), action/wide/
   landscape → composite_only. First template characterization tests.
9. **P1-2(b) probed:** ai-toolkit INSTALLED + import-verified pod-side;
   disk (14 GiB free) is the binding constraint; FAL path stays practical.
10. **Records `d870f9e`:** spec §6 "Pod-session results record
    (2026-06-11)" (full numbers/verdicts/caveats) + runbook COMPLETE
    header + Exit record.
11. Coordination: 5 events sent, all operator findings disposed both
    directions (`6d1eefa` done-guard/raise_for_status/seeds/image_api;
    runbook header; spec:267; F1 train guard) · anchor shifts hand-fixed
    (quality_max +33, workflow_selector +5, cost_tracker +3 — every
    target verified against live defs) · hole-2 overclaim OWNED (their
    diagnosis: atomic-fix tree = the gate never saw the broken state).

## ⭐ #1 PICKUP (in order)

a. **Probe the pod gateway** (read-only `curl …/system_stats`). 200 →
   surface billing to the user FIRST (they were told stoppable; if still
   up it's burning). 502/timeout → stopped, proceed offline.
b. **Surface the next-arc decision to the user** (don't silently pick):
   **(i) Pass-B direction work** — the S2/S3 verdicts REDIRECT Pass B:
   spec the attn-mask dual-PuLID approach (`ApplyPulidAdvanced.attn_mask`,
   the documented escape hatch), per-face multi-char validation (§3(d);
   dc5ad2b was step 1), per-face best-of-N selection, and the
   swap-targeting investigation (`input_faces_index="1"` vs composition —
   why the accepted Pass-A artifact's swap underdelivered at 0.487);
   **(ii) strategic-review P2 arc** (P2-1 + P2-5 + NF-7) — the named next
   CODE arc, carried two sessions. Recommendation: (ii) unless the user
   prioritizes multi-char — Pass B needs a fresh spike spec either way,
   and (i)'s spec work can ride along without pod time.
c. **Fold operator Lane V findings as they land** (their queue: dc5ad2b →
   3a589da → d870f9e → pod-arc batch). dc5ad2b is the load-bearing one.
d. **Surface the push opportunity** (~25 ahead of CI-green origin).

## Director backlog (carried + new)

P2-2 pod idle guardrails (THRICE-relevant now) · per-face multi-char
validation §3(d) (dc5ad2b = step 1) · swap-targeting investigation ·
aesthetics_predictor install decision (hermeticity-safe path — channel is
neutral-0.5 locally, Pass-A selected on arc alone) · spec §9 debts ·
budget-coverage map / ADR-022 exemptions · LLMEnsemble hermeticity ·
`check_pause()` wiring · QUALITY_MAX_MULTI cost entry ships with Pass B ·
19-param `generate_ai_broll_max` signature (MaxTierRequest candidate) ·
PM:1773 dotted-token slash-row · verifier assignment-binding class
(operator-queued; ALL-CAPS-constant anchors are bounds-only today).

## Operational notes (this session, on top of predecessors')

- **Visual verdicts override embedding metrics** for cross-identity claims
  — S3 sec45 read 0.828 numerically and rendered the WRONG GENDER.
  Calibrate the cross-identity floor (here 0.447) before trusting any
  cross-score; the metric reads geometry, not surface markers.
- **To claim "the gate misses X", break X first** (hole-2 lesson, owned):
  my doc+code fixes landed atomically, so the checker never saw the broken
  state — zero flags ≠ no coverage. The operator reproduced 21-24 flags
  against the actually-broken tree.
- **Never run a VRAM-measured spike concurrently with other renders** —
  ComfyUI queues globally; an interleaved job contaminates the peak.
- **USER STANDING DIRECTIVE (new, in memory): show EVERY generated
  artifact** — open each batch in Preview as it lands (intermediates
  included), not just final deliverables.
- Training scripts are NOT idempotent (FAL fee) — existing-output guards
  mandatory (operator F1, fixed `3a589da`).
- Pod-work authorization is session-scoped; re-obtain verbatim each
  session. SSH+scp worked via `scripts/_pod_ssh.exp` + inline expect-scp.
- Sonnet directive holding: ~4 subagents (2 adversarial reviewers, both
  verdict-accurate), zero stalls.

*Last verified: 2026-06-11T~03:45Z — smoke OK + doc gate no-drift at wrap;
suite 2151/0 = operator recount at 3a589da with verified docs-only delta
since; cursor 03:24:38Z, 0 unread; pod last probed 200 ~02:30Z, user told
stoppable twice since.*
