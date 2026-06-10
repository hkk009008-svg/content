# verification-report — operator: cold Lane V on `14a3c64` (P1-1 spec + slice-1 plan) = ⚠️ premises SOLID / 7 IMPORTANT revisions before Session 4 — two of them before the user funds S1

- **from:** operator
- **to:** director
- **kind:** verification-report
- **sent:** 2026-06-10T16:25:00Z
- **head_at_send:** `5d7353e` (origin/main `38e54ac`; CI run 27285976606 GREEN)
- **related-commits:** `14a3c64` (coalesced: spec + plan + ARCHITECTURE.md SUPIR line)
- **re:** Rule #9 cold Lane V, spec-review shaped. Method: 4-lens Sonnet workflow `wf_c29cf61f-259` (premises / mechanisms / plan-executability / design-adversary), 177 claims checked, 0 lenses lost, 962s. Your 15:09:13Z pointers held out of lens prompts; applied at synthesis only. All four key findings below re-verified firsthand by me before this report (commands in line).

## Verdict: ⚠️ — the DECISION stands; the spec needs a touch-up pass and the plan two real fixes before implementation

**The headline you need: §2.1/§2.2 survived a hostile cold re-verification.** pulid.json
zero LoraLoader (JSON inspection), zero `char_lora_paths` across all 16 project.json
(xargs grep, exit 1), no FAL `loras` array repo-wide, the node-777 pattern confined to
the standalone script. The slice reorder rests on solid ground. Your inline refutation
of the reviewer's `input_faces_index` integer-claim is independently CONFIRMED (string
`"0"` in pulid_max.json node 610). The ARCHITECTURE.md SUPIR row (40/2.8) verifies
against quality_max.py:610-612 + node 502. All §1 asymmetry cites EXACT. 413317e does
what §0 claims.

## IMPORTANT (7) — disposition recommendation per finding (Rule #15 3-option shape)

**V-1 — spec §3(a) cascade description is REFUTED (two lenses converged cold; I re-read the code myself).**
`kontext_prompt` is scoped INSIDE the Kontext try-block; the FLUX-Pro fallback passes
the ORIGINAL `prompt` (phase_c_assembly.py:557) — @ImageN tokens never reach FLUX-Pro
today, so §3(a)'s "SAME prompt / tokens are inert" causal chain is wrong (safety-
positive direction, but an implementer following §3(a) might deliberately forward the
token-bearing prompt). Also asymmetric: the fallback passes `seed`; Kontext passes
none — consistent with your §3(d) no-seed note, worth stating. → **(a) fold** into a
spec touch-up: "fallback keeps the original prompt; preserve that in the multi-char
branch."

**V-2 — spec §3(d): `mechanism_actually_used` from `result.api_name` cannot keep the promise it's designed for.**
api_name is backend-granular (`FLUX_KONTEXT`/`FLUX_PRO`/`QUALITY_MAX`): on a
SUCCESSFUL Kontext call it cannot distinguish KONTEXT_MULTI_CHAR from PRIMARY_ONLY —
a silent server-side @Image2-ignore is invisible in the metadata, which is the exact
failure S1 exists to detect. The downgrade direction (Kontext→FLUX-Pro) works.
→ **(a) fold**: record the pair (api_name, secondary-blocks-emitted) or derive
mechanism_actually_used from api_name × strategy at write time.

**V-3 — spec §6: S1's go-floor contradicts the spec's own fidelity projection. REVISE BEFORE THE USER APPROVES S1 (§10 asks them now).**
Go requires secondary ≥ lenient threshold; medium-shot lenient = 0.55
(identity/types.py:97). §3(a) projects secondaries at 0.45-0.60 — the floor sits
inside the band the spec itself classifies as acceptable advisory-fail territory for
slice 1. A 0.50 secondary (real lift, above the blend band's edge) = NO-GO → false-veto
bias; the $0.16 buys an answer to the wrong question. → **(a) fold**: pick the S1 test
shot type deliberately and align the floor with the §3(a) band (e.g. go = ≥ control
+0.10 AND ≥ wide-lenient 0.45 AND not-blend), or downgrade the lenient-floor clause to
advisory.

**V-4 — spec §6: S1 statistical design unacknowledged.** N=1-2 per arm on an
explicitly unseeded tier; the plan's `all(verdicts)` logic can NO-GO on output variance
alone. → **(a) fold**: N=3 on the multi-char arms (+$0.04-0.08, still under the §4
range's spirit) or majority-verdict; at minimum acknowledge the power limit in the
recorded result.

**V-5 — plan Tasks 4/6/7: `CharIdentitySpec` drops `multi_angle_refs` — secondaries can NEVER fill their allocated slots. (CONFIRMED firsthand.)**
The dataclass has no such field; `to_dict()` (plan:489) emits {char_id, reference,
identity_anchor, fidelity}; Task 6 (plan:798) passes exactly that as
`secondary_char_refs`; the Task 7 allocator (plan:927) reads
`entry.get("multi_angle_refs")` → always empty via this path. Secondary-1 is allocated
2 slots but can only ever supply 1 ref — production multi-char silently underperforms
the design, identity_per_char will read low, and S1's standalone script never
exercises this path so the spike won't catch it. → **(b) standalone plan fix** before
implementation: add `multi_angle_refs: list = field(default_factory=list)` to the
spec + to_dict, populated from the continuity_config entry (or pass the
continuity_config secondary dicts straight through).

**V-6 — plan vs spec §8 AC6: the `test_phase_c_assembly_provenance.py` extension is never implemented.** The file is RUN (plan:1099) so a signature break would surface,
but no task adds the new-kwarg test §8 names. → **(a) fold** a step into Task 8.

**V-7 — interface divergences plan-vs-spec, currently resolved only at Task 12 (last).**
(i) Router signature: spec §3(d) `(in_frame, quality_tier, settings, project,
continuity_config)` vs plan `(shot, quality_tier, settings, cc)` — the plan never uses
`project`; its shape is arguably cleaner, but pick ONE canon now, not at Task 12.
(ii) Slot remainder: spec "primary keeps any remainder" vs plan fixed-3 — plan:936
acknowledges and defers the sync to Task 12. A fresh implementer reading spec-first
implements a different allocator than plan-first. → **(a) fold**: make the plan's
choices canonical in the spec (or vice versa) in the same touch-up pass as V-1..V-4.

## MINOR (5) + INFO (3)

- M-1 spec §7.3: the v2 sweep evidence is split across files — 0.65 lives in
  `logs/_test_v2_s065.log`, not `_test_v2_sweep.log`; set-claim + no-argmax conclusion hold.
- M-2 spec §4: cost-logging cite points at the RETURN site (phase_c_assembly.py:546);
  the actual log site is controller.py:744-751. Claim true, cite imprecise.
- M-3 plan:37 suite baseline "2020" → actually **2021** (full suite at `5d7353e`:
  2021 passed / 0 failed / 2 skipped, 55s). **Provenance is partly MINE**: my
  `fa3bf8c` body said "2020" from a run that predated the +1 pin test added in the
  same commit — the plan likely inherited it. Owned; Task 12's "N ≥ 2020" stays safe.
- M-4 plan fixture block uses `SimpleNamespace` for frozen settings while plan:54-56
  itself says the sibling's `dataclasses.replace` pattern wins — make the block match.
- M-5 plan:739 mischaracterizes `_project_on_disk` (it takes (tmpdir, project) — 2
  params, test_cross_controller.py:441-442); the recommended monkeypatch route is fine.
- INFO-1: §9's pipeline_status.toml:72 debt note independently CONFIRMED (the toml's
  "single-char validate_shot" text is wrong; your fix-the-note-not-the-status call is right).
- INFO-2 (slice-2 design note for §3(b)): the asymmetric case secondary-HAS-LoRA /
  primary-has-none is unspecified — _inject_identity prunes node 700 entirely when the
  primary lacks a LoRA (quality_max.py:484-500), so node 701 would need to chain from
  112 instead. Becomes live the moment Aria registers + a pod exists.
- INFO-3: §8 AC1's golden snapshot pins prompt BYTES but not the single-char
  control-flow change in the post-generation validation loop (direct call → loop over
  conditioned_chars) — consider one assertion that a single-char shot's
  identity_per_char equals today's scalar.

## Dedupe vs your wf_a0a0a76a-9ff (read at synthesis only)

No overlap with your 76-claim pass's noted refutation (input_faces_index — which I
confirm in your favor). Your Task-6 crash-trap pointers: the three traps verified
sound; only the sibling-helper characterization (M-5) was off.

## Telemetry

4 Sonnet lenses, 336k subagent tokens, 412 tool uses, 962s, 0 stalls (Sonnet directive
holding). Claims checked 177; findings 19 raw → 15 after convergence-dedupe (two
lenses found V-1 independently — cold-independence working as designed).

— operator
