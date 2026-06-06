# Part 4 — UI capability-surfacing (Capability dashboard) — design spec

*Date: 2026-06-04 · Status: DRAFT (brainstorm output, pre-plan) · Seat: operator ·
Relates to: `docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md` §"Part 4 — UI
dimension" (U1/U2/U8) and §"Part 5 — Phase D"; `docs/superpowers/specs/2026-06-01-comprehensive-capability-test-suite-design.md`
(S1–S14 quality bars). Supersedes nothing.*

## 1. Intent & grounding

The program turns a script into finished, photoreal cinematic video, and is meant to be **operated
to realize its full capability** (PROGRAM-MANUAL §5). Today the UI hides almost all of the
quality/health signal the pipeline already computes: `Telemetry.tsx` shows only live cost + an
identity histogram + failed-shot count. An operator cannot see, in the UI, whether a run actually
hit its quality bars, which engine truly produced each shot (silent fallbacks are invisible), or
whether a character's LoRA is degrading identity.

This increment surfaces that signal in a dedicated **Capability** dashboard, directly serving the
manual's success criteria: **S9** (quality made visible), **S8** (tier reality), **S3/S4**
(coherence/motion/lipsync quality), **S10** (degradation visible). It is the UI half of the
2026-06-02 audit's Phase D, scoped to its three highest-leverage items (U1 scorecard + U2 per-shot
scores + U8 provenance) because they reuse data the pipeline already produces or can persist cheaply.

## 2. Scope

**In scope (the "C" bundle chosen in brainstorm):**
- **U1 — Capability scorecard** (full): per-dimension measured-vs-bar, gate-audit rollup,
  per-character LoRA validation summary, tier realized, and component-wiring status.
- **U2 — Per-shot scores**: identity / coherence / motion-fidelity / lipsync per shot, vs bar.
- **U8 — Cascade provenance**: which engine actually won per shot, the fallback chain attempted,
  and a flag for silent fallbacks (max→production, Veo→silent-Kling).

**Out of scope (deferred to future increments, with rationale):**
- **U3 — audio loudness / format** (−14 LUFS, 1920×1080, h264+aac): needs a final-mp4 probe. **This
  is the designated prime follow-on** (user showed interest during brainstorm).
- **U5 — pod/infra health**, **U6 — budget caveats**, **U7 — headless-readiness**: each needs its
  own backend plumbing and is a separable increment.

These four are rendered as greyed "future" tiles on the scorecard so the gap is visible without
implying they're measured.

## 3. Decisions locked (brainstorm, 2026-06-04)

| Decision | Choice | Why |
|---|---|---|
| Scope | C — full scorecard + U2 + U8 | Highest-leverage, reuses existing data |
| Placement | **New 4th app mode `'capability'`** (a `CapabilityConsole` view) | Full C-scope is too much for the narrow console right-rail; a dashboard wants its own real estate |
| Architecture | **Hybrid** — Python scorecard endpoint + client renders per-shot tables from existing project JSON | Bar-evaluation/rollups belong server-side (single source of truth, matches the Python capability-test bars, pytest-testable); per-shot tables are simple pass-throughs |
| Refresh model | Load-on-open + manual refresh button (live SSE update = v2) | Keep v1 simple; review-oriented surface |

## 4. Data readiness — VERIFIED at HEAD (2026-06-04)

Field names and persistence verified by grep at HEAD `534abc9` (see Appendix A). **The implementer
MUST re-verify at their HEAD** — the survey that seeded this was wrong twice (corrected below);
treat every field as point-in-time (ADR-013, "survey-can-be-wrong").

| Datum | Where it lives today | Readiness |
|---|---|---|
| `identity_score` | `take["metadata"]["identity_score"]` (`cinema/shots/controller.py` ~661/1048) | ● ready |
| `motion_fidelity` | `take["metadata"]["motion_fidelity"]` (`controller.py:1055`) — **note: field is `motion_fidelity`**, ProgressEvent aliases it `motion_score` | ● ready |
| `lipsync_score` | `take["metadata"]["lipsync_score"]` (`controller.py:1466/1495/1503/1514`); `1.0` for native audio | ● ready |
| `coherence_score` | computed as `coh.overall_coherence_score` into transient `result["scores"]["coherence"]` (`controller.py:1867`) + live ProgressEvent only (`web_services.py:82`) — **NOT** in `take["metadata"]` | ◐ **small add**: persist to `take["metadata"]` mirroring motion_fidelity; verify the `result["scores"]` path reaches the take |
| video provenance | `take["cascade_metadata"]` top-level `{engine, score?, threshold?, fallback?, attempts?}` (`controller.py:1399`) | ● ready |
| lipsync provenance | `take["metadata"]["lipsync_cascade"]` (same shape) (`controller.py:1470`); postprocess `variant["cascade_metadata"]` (`1976`) | ● ready |
| gate audit | `shot.auto_approve_audit[]` `{gate, auto_approved, vetoes, rule_names, timestamp}` | ● ready (already aggregated in `PostRunSummary.tsx`) |
| LoRA verdict | `record_lora_verdict` (`prep/lora_training.py:270`) **already persists** `quality_score` + `best_strength` + `rejected` + `quality_warning`; `get_lora_status` surfaces them | ● ready (**survey was wrong** — score+strength ARE persisted) |
| LoRA strength sweep | the full per-strength scores array is **not** persisted | ○ optional add (defer; render score+strength+verdict from existing data) |
| tier | `global_settings.quality_tier` ∈ {production, max} | ● ready |
| component status | `docs/pipeline_status.toml` (live/wired/stubbed/parked/dead); CLI-only via `scripts/status.py` | ◐ small add: a read-only endpoint to serve it as JSON |

**Net backend work is smaller than first sketched:** one real persistence add (coherence_score), one
tiny config endpoint (pipeline_status), and the aggregation endpoint. LoRA/gate/provenance/scores
are already-persisted.

## 5. Backend design (Python)

### 5.1 New endpoint — `GET /api/projects/<pid>/capability-scorecard`

Computes the scorecard server-side and returns one compact JSON. Route is `<pid>`-scoped explicitly
(per CLAUDE.md endpoint convention; inspect a sibling like `api_get_project` for route shape — do
**not** scan `list_projects()`). Response shape (illustrative — finalize in plan):

```json
{
  "project_id": "…", "tier": "max",
  "summary": {"shots_total": 18, "shots_clearing_all_bars": 14},
  "dimensions": [
    {"key": "identity",  "label": "Identity · ArcFace", "value": 0.71, "bar": 0.60, "pass": true,  "n_measured": 18},
    {"key": "coherence", "label": "Coherence",          "value": 0.64, "bar": 0.60, "pass": true,  "n_measured": 18},
    {"key": "motion",    "label": "Motion fidelity",    "value": 0.82, "bar": null, "pass": true,  "n_measured": 16},
    {"key": "lipsync",   "label": "Lipsync · SyncNet",  "value": 0.66, "bar": 0.65, "pass": true,  "n_measured": 5}
  ],
  "routing":   {"first_try": 16, "fallback": 2, "silent_fallback": 1},
  "gates":     {"plan": {"approved": 18, "vetoed": 0}, "image": {"approved": 15, "vetoed": 3, "top_vetoes": [["identity_floor", 3]]}, "motion": {…}, "final": {…}},
  "lora":      [{"char_id": "char_alex", "strength": 0.55, "score": 0.79, "verdict": "ok"}, {"char_id": "char_mia", "strength": 0.60, "score": 0.61, "verdict": "warning"}],
  "components": [{"id": "lora_validation", "status": "wired"}, {"id": "hires_fix", "status": "live"}, {"id": "multi_identity_validation", "status": "stubbed"}],
  "future_dimensions": ["audio_lufs", "format_codec", "pod_health", "budget"]
}
```

- **Bar definitions are the single source of truth here.** Reuse/extend the thresholds defined by the
  capability-test suite (`docs/.../2026-06-01-…`) and existing gate constants (e.g. coherence ≥ 0.6,
  lipsync ≥ 0.65, identity floor) rather than re-deriving. Where a dimension has no scalar bar
  (motion advisory), `bar: null` and `pass` reflects the gate's own logic.
- Reads: the project JSON (takes → metadata/cascade_metadata, `auto_approve_audit`),
  `get_lora_status` per character, `global_settings.quality_tier`, and `pipeline_status.toml`.
- Pure/aggregating; no mutation. Errors on unknown `<pid>` with the same shape as sibling endpoints.

### 5.2 Persistence add — coherence_score → `take["metadata"]`

Today coherence is computed (`controller.py:1867`) but only reaches a transient `result["scores"]`
+ the live SSE. Persist it onto `take["metadata"]["coherence_score"]` at the same point
motion_fidelity is written (`controller.py:1055`), so the scorecard/U2 table can read historical
projects. Implementer verifies the exact write-site + that `result["scores"]["coherence"]` is the
canonical value.

### 5.3 Component-status endpoint (small)

A read-only `GET /api/pipeline-status` (or fold into `/api/config`) returning the parsed
`pipeline_status.toml` rows `{id, status, note}`. Reuses `scripts/status.py`'s loader if one exists;
otherwise a thin toml read.

### 5.4 Optional (deferred) — persist LoRA strength sweep

`validate_lora_quality` produces a per-strength sweep; only best score+strength is persisted today.
Persisting the full sweep enables a sweep viz later. **Deferred** — not needed for v1 (verdict +
score + strength already render).

## 6. Frontend design (React 19 / Vite / Tailwind)

### 6.1 New view wiring
- Add `'capability'` to the mode union in `App.tsx` (currently `'setup' | 'pipeline' | 'console'`,
  state-driven, no router — verify the enum site at HEAD).
- New `web/src/components/console/CapabilityConsole.tsx` (sibling of `DirectorsConsole.tsx`),
  rendered when `mode === 'capability'`.
- A nav affordance to reach it (mirror the existing "Director's Console →" masthead button pattern
  in `EditorialShell.tsx`), plus a Back affordance.

### 6.2 Sections (top→bottom) and their data source
1. **Header band** — project, `tier` badge, `shots_clearing_all_bars / shots_total`. ← scorecard endpoint.
2. **Capability scorecard grid** — dimension tiles (value, bar, pass, mini-bar) + greyed `future_dimensions`. ← scorecard endpoint.
3. **Per-shot scores table (U2)** — row/shot: identity/coherence/motion/lipsync vs bar; row click → drill to takes. ← **project JSON** (`take.metadata`).
4. **Cascade provenance (U8)** — per shot: winning engine + attempts + silent-fallback flag. ← **project JSON** (`take.cascade_metadata`, `take.metadata.lipsync_cascade`). Reuse `TakeStrip`'s engine-chip + FALLBACK badge styling.
5. **Gate audit rollup (U1)** — plan/image/motion/final approved-vs-vetoed + top firing rules. ← scorecard endpoint; **extract/share** the aggregation already in `PostRunSummary.tsx` so the two don't diverge.
6. **LoRA + component status (U1)** — per-char strength/score/verdict; component live/wired/stubbed map. ← scorecard endpoint.

### 6.3 Styling
Match the console palette (`console-bg`/`console-ink`/`console-gold`/`console-accent`), `Eyebrow`
labels, Fraunces display + JetBrains Mono diagnostics, and the `ui/Button` variants. Reuse
`ui/ErrorState` + `ui/LoadingState`.

## 7. Data flow & states
- **Load:** on view open, fetch `/capability-scorecard` (headline) and `/api/projects/<pid>` (tables) in parallel.
- **Refresh:** a manual refresh button re-fetches. (Live SSE auto-update during an active run = v2.)
- **Empty:** project never run / no takes → a clear "no capability data yet — run the pipeline" empty state.
- **Missing values:** older projects predating coherence persistence → render `—` / "not measured" (drive off `n_measured`), never a fake 0.
- **Error:** endpoint failure → `ui/ErrorState` with retry; partial data (e.g., scorecard ok, project fetch fails) degrades gracefully per-section.

## 8. Testing strategy
- **pytest** for `/capability-scorecard`: bar evaluation per dimension, gate/routing/LoRA rollups,
  empty-project, missing-score fallback (no fake 0s), unknown-pid error shape, `<pid>`-scoping
  (no cross-project collision).
- **pytest** for the coherence-persistence write (a take ends up with `metadata.coherence_score`).
- **Frontend**: a render test of `CapabilityConsole` against a fixture scorecard + project (loading /
  empty / error / populated). Follow existing component-test conventions.
- §15 smoke + `check_doc_claims` stay green; if any doc anchor shifts, `--fix` in the same change.

## 9. Open questions for the plan
1. Exact bar constants per dimension — source each from a named existing constant (avoid magic numbers).
2. Does `result["scores"]["coherence"]` already reach the persisted take in any path? (decides whether 5.2 is a write-add or a plumbing-fix).
3. Nav placement for the new mode — masthead button vs. a tab in the existing nav.
4. Should the scorecard be per-project-latest or pinned to a specific run? (v1: latest persisted takes.)

## 10. Sequencing (for the plan)
Backend-first so the frontend renders real data: (1) coherence persistence + test → (2) scorecard
endpoint + tests → (3) component-status endpoint → (4) CapabilityConsole + mode wiring → (5) the six
sections → (6) empty/error states + render test. Each is independently reviewable.

---

## Appendix A — verification at write (ADR-013)

```
$ git rev-parse --short HEAD                                  → 534abc9
$ grep -n motion_fidelity cinema/shots/controller.py          → take["metadata"]["motion_fidelity"] = motion_score  (:1055)
$ grep -n lipsync_score   cinema/shots/controller.py          → take["metadata"]["lipsync_score"] = …               (:1466,1495,1503,1514)
$ grep -n coherence_score cinema/ web_services.py             → controller.py:1867 result["scores"]["coherence"]=…  ; web_services.py:82 event["coherence_score"]  (NOT take.metadata)
$ grep -n cascade_metadata cinema/shots/controller.py         → take["cascade_metadata"] (:1399); take["metadata"]["lipsync_cascade"] (:1470); variant["cascade_metadata"] (:1976)
$ sed -n /record_lora_verdict/ prep/lora_training.py          → persists quality_score, best_strength, rejected, quality_warning  (:270) — score+strength ALREADY persisted
```

Two survey corrections folded in: (a) coherence is in `result["scores"]`, not `take.metadata` (gap
real, but the value already exists pre-SSE); (b) LoRA score+strength ARE persisted via
`record_lora_verdict` — only the sweep array is not. Frontend app-shell refs (`App.tsx` mode enum,
`Telemetry`/`DirectorsConsole` mounts, `PostRunSummary` aggregation, `TakeStrip` chip) are from the
2026-06-04 read-only survey; verify at implementation.
