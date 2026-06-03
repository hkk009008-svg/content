# Director transplant handoff — 2026-06-04 (Part-3 no-op tickets cycle + prune merged to main)

**READ FIRST IF PICKING UP THE DIRECTOR SEAT.** Supersedes
`docs/HANDOFF-director-transplant-2026-06-03-prune-cycle.md`.

## §0 State at wrap (re-verified live, HEAD `57bef47`)

- **`main` == `origin/main` == `3fa46f4` — GREEN.** This session FF-merged the entire
  prune cycle (327 LOC dead-code removal `b4a03c8..8a5d425`) + **ADR-020** (`f499c81`) +
  arch-sync + 2 doc fixes + handoffs to trunk — the **#1 pickup** from the prior handoff,
  **DONE** (user-authorized). main moved `7e807d8` → `3fa46f4`. Full Part-3 program already
  on main.
- **`feat/max-tier-provisioning` == `origin/feat` == `57bef47`** — ahead of main by **4
  director ticket-closes + the operator's T1 spec** (6 commits). Pushed to origin (backup).
- **Suite: 1527 passed / 0 skipped / 0 failed** (re-run at wrap, tree code-clean; the 3
  former skips were T11's, now passing). **§15 ci_smoke OK.**
- **Operator is LIVE on T1** (user-directed parallel session), in spec phase.
- D-a INACTIVE (shared working tree, no per-seat `GIT_INDEX_FILE`). **`quality_max.py`
  contention with the operator's T1 is REAL** (see §2/§5).

## §1 This session's work (director seat)

**#1 PICKUP DONE — prune cycle merged to main.** Verified FF-clean (`main` was a direct
ancestor of `feat`), suite 1512/3/0 green at the merge commit, user-authorized push+merge.
`origin/main` 7e807d8 → 3fa46f4. (The "DECISIONS.md missing" scare during session-start was
a wrong-cwd artifact — the file is fine; ADR-020 intact.)

**4 no-op audit ticket closes** (from `docs/superpowers/2026-06-03-part3-noop-audit-tickets.md`):

| Ticket | SHA | What |
|---|---|---|
| **T8** | `547f7e7` | `config/prompts/pipeline_context.md` §2 was INVERTED (claimed native-lipsync / "overlay DISABLED"); reconciled to **overlay-default + native escape hatch**. Behavior-adjacent — 5 LLM consumers (phase_c_vision/style_director/chief_director/scene_decomposer/dialogue_writer). Verified vs `controller.py:128` `_dialogue_voice_mode="overlay"`. Operator acked + Lane-V-skipped (docs-substance). |
| **T11** | `1fcaaaa` | 3 `@unittest.skip` in `test_project_persistence.py` repaired + un-skipped. Root cause: tests patched root shims but `domain/` call-sites resolve from `domain.*` namespaces → re-pointed to `domain.project_manager.FileLock` / `domain.character_manager.add_character` / `domain.location_manager.add_location`. 9 pass / 0 skip; no assertions weakened. |
| **T7** | `4af8c05` | `CostTracker` now honors `EXPERIMENTS_DB_PATH` env (was a silent no-op — `settings` read it, nothing consumed it). Wire-via-env (precedence: explicit arg > env > legacy default), decoupled from `config.settings`. +3 tests. |
| **T5** | `57bef47` | Audio spend (dialogue TTS / BGM / foley) now **gated against the pipeline budget tracker** (was fresh untracked `CostTracker()`s; video already gated via `controller.py:707/1147/1161`). Threaded `self.cost_tracker` via optional `cost_tracker` param (backward-compatible default None). Cross-process `spent_usd` persistence DEFERRED (budget-semantics). +new test file. **Known nit (non-blocking):** type hints inconsistent (`Optional[object]` vs bare `Optional`) — runtime-fine, no mypy gate; cleanup welcome. |

All 4 pushed to `origin/feat`.

**Coordination — operator came online mid-session (user-directed):**
- Operator claimed **T1** (`validate_lora_quality`) via mailbox `2026-06-03T13-43-02Z`. User
  picked it for them. Their approved design (visibility): gate **+ auto-retrain**, LoRA
  **strength-sweep [0.45/0.55/0.7/1.0] + persist per-char strength** (closes the 1.0-over-bake
  gap; realism memory: 0.55 beats 1.0), new module **`prep/lora_quality.py`** (Approach B:
  `_generate_with_lora` + `validate_lora_quality` oracle + pure `_next_lora_action` +
  `train_character_lora_gated`), wire `char_lora_strength` beside `char_lora_path`. Spec
  committed `082edb5`. Offline session → design + boundary-tests only; live calibration is
  spend-gated Phase-B.
- I **corrected their "no contention" claim** (event `2026-06-03T13-56-21Z`, on disk): **T3 +
  T4 both edit `quality_max.py`**, which their T1 wiring (`:466`/`:649`/`:662`) also edits →
  shared-tree intermingling hazard. Proposed: **HOLD T3/T4 until T1's quality_max.py edits
  land.** Operator hadn't replied at wrap (heads-down on spec). My independent Lane V (Rule #9)
  applies to whatever T1 commits.

**T3 + T4 PRE-DESIGNED** (read-only, user-directed) — execution-ready plans below (§3).

## §2 OPEN items + ownership

| Item | Owner | Status |
|---|---|---|
| **T1** validate_lora_quality | **OPERATOR** (user-directed) | Spec phase (`082edb5`). Their lane. |
| **T3** hires_fix Pass-2 wiring | DIRECTOR | **HELD** for T1's quality_max.py edits. Plan §3.1. |
| **T4** halt_rule modes | DIRECTOR | **HELD** for T1. Recommend implement `conjunctive`; reject/defer `budget_only`. Plan §3.2. |
| **T6** auto-diagnose loop wiring | unassigned | Design-first; not started. Quality lever (PROGRAM-MANUAL §5). |
| **merge ticket commits → main** | DIRECTOR + user | **GATED** — do NOT merge feat→main mid-T1. After T1 + T3/T4 land + green, offer the same FF merge as the prune cycle. |

## §3 T3 + T4 execution-ready plans (pre-designed; line numbers are point-in-time, RE-VERIFY post-T1)

### §3.1 — T3: wire hires_fix Pass-2 (~7-10 LOC)
Nodes EXIST in `pulid_max.json`: `900 LatentUpscaleBy` (1.5×) → `901 SamplerCustomAdvanced`
(pass-2) → `902 VAEDecode`. Bug: node 901 reuses node **17**'s sigmas (the *pass-1*
`OptimalStepsScheduler`; inputs `model_type/steps/denoise`), so `hires_fix_denoise` (already
in all 5 MAX_QUALITY_TEMPLATES + schema; reaches `_inject_post_passes` at `quality_max.py:822`)
never reaches pass-2.
**Plan** — in `_inject_post_passes` (~`:597`, after the final_resolution block; mirror the
FaceDetailer/SUPIR `workflow[id]["inputs"][k]=params.get(...)` idiom):
```python
if params.get("hires_fix_enabled", True) and "901" in workflow:
    if "18" not in workflow:
        workflow["18"] = copy.deepcopy(workflow["17"])   # copy imported quality_max.py:34
    workflow["18"]["inputs"]["denoise"] = params.get("hires_fix_denoise", 0.40)
    workflow["18"]["inputs"]["steps"]   = params.get("hires_fix_steps", 18)
    workflow["901"]["inputs"]["sigmas"] = ["18", 0]
```
**IMPL-TIME VERIFY:** node 17's current denoise source (pass-1 param vs static), no node-18
collision, params present.
⭐ **CAPABILITY / REALISM INSIGHT:** pass-2 currently inherits the aggressive pass-1/baseline
denoise (≈full re-sample at 1.5×) instead of the intended `0.40` — **this plausibly feeds the
"max tier over-processes into painterly" symptom** (realism memory). Wiring 0.40 = gentle
refine → likely **more** photoreal. So T3 may be a max-tier realism win, not just plumbing →
do a visual A/B on the pod (spend-gated) when validating.

### §3.2 — T4: halt_rule modes (capability decision — CONFIRM WITH USER)
`should_halt` (`face_validator_gate.py:227-281`) is composite-only; has per-candidate
`arc_score`+`aesthetic_score`+`composite` in scope but **no** budget/cost. `halt_rule` is
written to params (`quality_max.py:705`) but **NEVER READ** (grep-confirmed).
**DIRECTOR RECOMMENDATION (capability-intent):** implement **`conjunctive`** = halt only when
`best.arc >= arc_threshold` AND `composite >= threshold` — an **identity-floor lever** (today a
high aesthetic masks weak identity: arc 0.87 + aesthetic 1.0 → composite 0.922 halts as
"good"; character consistency is the program's core). **Reject/defer `budget_only`** (needs
`CostTracker` threaded into `should_halt` = bigger arch; cost-control, not quality).
*(Subagent's conservative alt: reject ALL — simpler, but forecloses the conjunctive lever.)*
**Plan:** add `halt_rule` param + conjunctive branch to `should_halt` (`face_validator_gate.py`
— **NOT contended**, can prep anytime); thread `params["halt_rule"]` at caller
`quality_max.py:897` + narrow schema `:131` + reject `budget_only` at config-validate `:173`
(**CONTENDED — hold for T1**). Tests: conjunctive halt/no-halt + rejected-mode warning.

## §4 #1 PICKUP for next director (or this seat, post-T1)
1. **Watch `git log` for the operator's T1 `quality_max.py` edits.** The moment they land →
   rebase the §3 plans (line numbers shift) and implement **T3** (simpler) then **T4**.
2. **Confirm the T4 `conjunctive` decision with the user** before implementing (capability call).
3. **After T1 + T3/T4 land + suite green:** offer **merge-to-main** (user-gated) — same FF
   pattern used for the prune cycle this session. Do NOT merge mid-T1.
4. **T6** remains design-first (its own brainstorm→spec cycle).
5. Independent Lane V (Rule #9) on the operator's T1 impl commits when they land.

## §5 Protocol/coordination state
- **D-a INACTIVE** (shared working tree). **Coordinate `quality_max.py` edits with the
  operator** — concurrent edits intermingle on the one tree.
- Director cursor advanced to `2026-06-03T13:43:02Z` (all to-director events processed).
- Coordination event `2026-06-03T13-56-21Z-director-to-operator-coordination.md` is on disk
  (committed with this handoff).
- Task tracker (this session) held the T3/T4 plans (#5/#6) — but TaskCreate is session-scoped;
  **§3 above is the durable copy.**

*— director-seat, wrap 2026-06-04. 4 closes + prune-merge shipped; T3/T4 pre-designed + held
for T1; operator live on T1.*
