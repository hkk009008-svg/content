# Cinema Production Tool — Comprehensive Product Unification Plan

**Goal:** Make the active cinema product truthful, current, efficient, and
ready for real use: paid actions fail closed, provider adapters follow current
official contracts, every exposed control has a real backend effect, runtime
state is project-scoped and backend-authoritative, persisted media survives a
repo move, and the four-page UI presents a polished operator product rather
than internal implementation archaeology.

**Execution model:** This is a multi-slice orchestration. Each production slice
lands as one focused commit, followed by an independent spec review and an
independent code-quality review of the actual `BASE..HEAD` diff. Implementers
run sequentially when their files or contracts overlap. Reviews and read-only
research may run in parallel. Ordinary Git and test commands use
`env -u GIT_INDEX_FILE`.

**Scope:** Exhaustively reconcile active production code, web UI, tests,
operator-facing prompts/config, current source-of-truth documentation, the
project skills whose routing guidance affects production, and dependency
contracts. Preserve append-only ADR history, protocol evidence, archived
handoffs, and historical lock snapshots unless an active product change
specifically requires a new explanatory entry. “Comprehensive” does not mean
rewriting historical evidence or abstracting every provider into one shape.
This plan and the coverage ledger at
`docs/AUDIT-product-unification-2026-07-30.md` make that scope measurable:
every discovered active surface must end with an owner, disposition, verifier,
and acceptance test or an explicit API-only/internal/no-change rationale.

## Verified baseline

Verified on `main` at `decf72ee` before creating
`codex/comprehensive-unification-20260730`:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q
3436 passed, 2 skipped, 10 subtests passed

$ npm --prefix web test -- --run && npm --prefix web run build
14 test files / 46 tests passed; production build succeeded

$ env -u GIT_INDEX_FILE .venv/bin/python -m pip check
No broken requirements found.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md
93 auto-fixable definition drifts and 2 manual drifts
```

The green baseline does not prove current provider contracts or semantic
documentation truth. The audit reproduced a Firecrawl signature failure,
confirmed a first-shot continuity strength despite an explicit anchor, and
found UI/backend state and paid-capability mismatches not covered by the
baseline suite.

## Product invariants

1. **Spend safety:** no UI or API path may start a paid operation that cannot
   produce and validate an artifact consumed by the production pipeline.
2. **Backend authority:** the server owns job state, allowed actions, engine
   availability, validation, and persisted revisions. The UI renders that
   truth and never treats a non-2xx response as success.
3. **Narrow canonical catalogs:** static engine/capability facts have one typed
   source. Provider payloads, errors, and modality-specific parameters remain
   provider-specific.
4. **Do not collapse independent truths:** model maturity, provider lifecycle
   (including deprecation/sunset), static product support, and current runtime
   availability are separate fields. Credentials, quota, pod state, or a
   temporary outage do not rewrite model lifecycle.
5. **Project isolation:** switching project IDs resets or hydrates every
   project-scoped page, focus, job, budget, event, failure, and media state.
6. **Portable persistence:** project-owned output is stored by project-relative
   path or stable media ID, never by a repo-location-dependent absolute path.
7. **Current official contracts:** active external adapters are checked against
   primary provider documentation and protected by offline request/response
   contract tests.
8. **Generated facts, authored rationale:** catalogs may generate or validate
   reference tables and config surfaces; architectural rationale and operating
   guidance stay human-readable and reviewed.
9. **No speculative refactor:** dead-code removal and hotspot decomposition
   require caller evidence, regression coverage, and preserved billing/cascade
   semantics.

## Current primary-source anchors

- Gemini Omni inline/URI video output and aspect contract:
  <https://ai.google.dev/gemini-api/docs/omni>
- LTX 2.3 supported models and image-to-video request:
  <https://docs.ltx.io/models> and
  <https://docs.ltx.io/api-documentation/api-reference/video-generation/image-to-video>
- Firecrawl Python scrape contract:
  <https://docs.firecrawl.dev/quickstarts/python>
- Runway current model and SDK mapping:
  <https://docs.dev.runwayml.com/guides/models/> and
  <https://docs.dev.runwayml.com/api-details/sdks/>
- OpenAI Sora lifecycle:
  <https://developers.openai.com/api/docs/models/sora-2> and
  <https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation>
- FAL Sora endpoint retirement:
  <https://fal.ai/models/fal-ai/sora-2/image-to-video/api>
- Google model deprecation schedule:
  <https://ai.google.dev/gemini-api/docs/deprecations>

Refresh these sources in the relevant implementation slice; this list is a
starting contract record, not a permanent substitute for live verification.

## Ordered implementation slices

### 0. Audit and orchestration record

- [x] Run the architecture smoke, backend suite, frontend suite/build, and
  dependency consistency checks.
- [x] Audit active provider adapters against primary documentation.
- [x] Trace UI controls through routes, write sites, runtime reads, and tests.
- [x] Inspect the built product in-browser at desktop and constrained viewport
  sizes.
- [x] Obtain an independent ChatGPT Pro architecture challenge.
- [x] Commit the active-surface audit/coverage ledger with reproducible
  discovery commands and slice ownership.
- [x] Commit this plan as the durable task board.

Acceptance: each later slice names the exact files it owns, its direct callers,
its offline acceptance tests, and the current official contract it implements.

### 1. Fail-close dormant character LoRA

Owned surface: `web_server.py`, a dependency-free LoRA deny policy,
`prep/lora_quality.py`, `prep/lora_training.py`, direct FAL/manual training and
registration scripts, protected project-setting writes, the character panel,
capability status/manifest, and their focused tests/docs.

- [x] Refuse training before importing or invoking the trainer; return a stable
  machine-readable unavailable error.
- [x] Apply the same non-overridable deny policy before raw trainer subprocess,
  direct FAL upload/subscription, manual reference generation, and registry
  scripts. No environment, request, project, pod, or CLI flag may bypass it.
- [x] Make the dormant LoRA registry fields read-only: unchanged legacy values
  may round-trip, but new/changed paths, strengths, or triggers fail atomically
  inside the latest project mutation.
- [x] Make skipped/unavailable validation non-accepting so an unvalidated LoRA
  cannot be activated or registered.
- [x] Remove the paid training affordance and all claims that the dormant
  producer is an engaged production capability.
- [x] Preserve ADR-065 and the dormant implementation for a separately
  authorized future reactivation; keep historical status readable.

Acceptance: endpoint, raw trainer, FAL scripts, and manual registry tests prove
no thread/subprocess/upload/subscription/mutation; the protected PUT test proves
changed registry values cannot land; policy test proves `best_score=None`
cannot accept; UI has no actionable training control; manifest classifies the
structurally disconnected capability as inactive rather than wired.

### 2. Establish the checked-at provider ledger and narrow typed truth boundary

Owned surface: engine catalog/compatibility exports, shot schema/HTTP
validation, workflow rankings/cascade validation, `/api/config`, UI engine
selectors, the provider decision ledger across every active modality, and
catalog coherence tests.

- [x] Record a checked-at decision for video, image, LLM, TTS, music, lip-sync,
  performance, foley, upscale/post, and research providers: official endpoint
  and model ID, maturity, lifecycle, I/O constraints, runtime prerequisites,
  routing role, and disposition. Provider-advertised cost/quality stays labeled
  as such; product quality/cost rankings require committed R-MEASURE artifacts.
- [x] Define modality, maturity, lifecycle, product support, selectability,
  dispatchability, spendability, provider, native-audio support, accepted
  parameter constraints, optional sunset date, and separately computed runtime
  availability.
- [ ] Keep the existing registry export as a read-only compatibility view while
  migrating consumers.
- [x] Limit selectable shot targets to `AUTO` or live, dispatchable video
  engines; reject planned, disabled, unknown, and non-video values at schema,
  HTTP, optimizer, and dispatcher boundaries. (Landed via `2b-A`; reviews
  owed — see ledger.)
- [x] Retire unsupported FAL Sora immediately. Keep native Sora as a visibly
  deprecated, date-gated fallback through 2026-09-24, then make it
  non-dispatchable automatically; do not present it as a preferred/default
  choice. Preserve cost/history data. (`SORA_2` catalogued
  `RETIRED`/`UNSUPPORTED`, all capability flags false; legacy dispatch arm
  in `phase_c_ffmpeg.py` is policy-unreachable, pruning deferred to Slice 15.)
- [ ] Make every UI picker use the same server-provided selectable view.

Acceptance: no orphan IDs across catalog, selector, rankings, cascade, pricing,
and dispatch; non-video/planned/retired targets fail before sleep/network/spend;
legacy entries remain inspectable but not selectable.

### 3. Repair Gemini Omni and portrait routing

Owned surface: `gemini_omni_native.py`, Gemini dispatch/aspect declarations,
focused tests, and the Google SDK constraint only if the repaired contract
requires it.

- [ ] Decode inline base64 data before binary publication.
- [ ] Poll URI results with the required `files/<id>` name and download the
  returned output URI.
- [ ] Treat failed and empty terminal results explicitly.
- [ ] Declare the documented 9:16 support in portrait routing.

Acceptance: offline fixtures cover inline, URI processing-to-active, URI
failed, empty output, atomic publication, and portrait dispatch.

### 4. Repair LTX 2.3 duration, audio, and error semantics

Owned surface: `ltx_native.py`, its dispatcher/config/setting contract, safe
download usage, and focused tests.

- [ ] Use the current API host and model the documented model/resolution/FPS
  duration matrix. The selected native `ltx-2-3-pro` profile deliberately
  restricts the product to its supported 6/8/10-second set, with 6 as default;
  do not misstate that as the limit of every LTX-2.3 Fast profile.
- [ ] Pass duration deliberately from dispatcher/config and reject invalid
  values before the network.
- [ ] Disable native audio when the product intends silent motion input.
- [ ] Classify provider-contract errors explicitly; allow the documented FAL
  fallback where safe without concealing a malformed local request.

Acceptance: native and FAL payload fixtures agree on duration; invalid 4
seconds makes no network call; native failure/cascade and billing provenance
are deterministic; guarded download is used.

### 5. Repair Firecrawl and Runway performance adapters

Owned surface: one shared Firecrawl adapter plus both research consumers;
Runway Act-One/Act-Two adapter, registry labels, and focused tests.

- [ ] Use Firecrawl `scrape(url, formats=[...])` and the current `Document`
  result shape; remove duplicated incompatible calls.
- [ ] Migrate Runway performance transfer to Act-Two, remove unsupported
  duration input, and make SDK/REST fallback behavior explicit.
- [ ] Rename Gen-4 Turbo and remove unsupported multi-reference claims.
- [ ] Update dependency constraints only with the adapter tests in the same
  slice; do not blanket-upgrade unrelated SDKs.

Acceptance: exact SDK-shaped calls, terminal polling, empty/error cases, and
fallback behavior pass without live provider spend.

### 6. Decide and migrate current cross-modality models

Owned surface: shared LLM adapters/model settings, Gemini image/text/vision,
TTS/music/foley/post-processing selections, registry truth, and offline
behavior/contract tests.

- [ ] Evaluate the exact configured GPT-4o aliases/snapshots against current
  OpenAI lifecycle guidance and a Responses-based GPT-5.6 candidate. Migrate
  through one adapter only when structured JSON, tools, vision, latency, cost,
  and product benefit are proven; do not call the GPT-4o alias deprecated
  merely because a particular dated snapshot is.
- [ ] Migrate Gemini 2.5 image/text/vision models before their published
  October 2026 shutdowns, with fixtures for media and structured-output
  behavior.
- [ ] Evaluate, rather than blindly adopt, currently offered upgrades such as
  Runway Gen-4.5/router, Cartesia Sonic 3.5, and newer Stable Audio variants.
  Record why the selected model is better for this product and what remains a
  provider claim versus locally measured evidence.
- [ ] Correct falsely surfaced OpenAI Audio, the unofficial SunoAPI.org proxy,
  the live Stable Audio fallback, undocumented Viggle, unverified Kling v1.6,
  and configured-but-unused Pexels status.

Acceptance: every modality ledger row has a current official contract or is
explicitly `unverified/disabled`; migrations preserve structured outputs and
media semantics offline; measured ranking claims cite committed instruments
and `logs/` artifacts.

### 7. Repair continuity and canonical identity authority

Owned surface: continuity engine/temporal policy, optimizer-to-shot merge, and
focused integration/mutation tests.

- [ ] Derive denoise from the actual explicit anchor/init-image condition, not
  disconnected mutable history.
- [ ] Ensure the user-approved canonical character identity wins over
  optimizer-invented face/hair/build text.
- [ ] Keep optimizer identity output advisory or object-specific.

Acceptance: first shot with an explicit anchor uses continuity strength; first
shot without one uses first-shot strength; deleting the anchor branch reddens
the test; optimizer output cannot override canonical identity.

### 8. Project-scoped UI state, basic action authority, and typed errors

Owned surface: project/page/pipeline client state, a minimal typed API client,
the backend pipeline-state response, its basic `allowed_actions`, start/cancel/
pause/resume mutations, and frontend tests.

- [ ] Reset or hydrate page, focus, stages, shots, failures, halt, generation,
  and event state atomically when PID changes.
- [ ] Hydrate existing pipeline/checkpoint state instead of painting a new idle
  run over backend truth.
- [ ] Derive `running` and the currently legal lifecycle actions under the
  backend pipeline lock, including the pending-start sentinel; transport
  connectivity is never treated as job truth.
- [ ] Centralize only HTTP decoding/error normalization; retain feature-specific
  API functions.
- [ ] Treat 409 and other non-2xx results as errors, keep editors open, and
  refresh authoritative state.

Acceptance: A-to-B project switch cannot leak A state; idle backend shows no
cancel/approve actions; mutations cannot report success on a non-2xx response.

### 9. Settings, language, and spend-control reconciliation

Owned surface: validated project setting updates, inspector controls/defaults,
language-default application, and focused backend/frontend contract tests.

- [ ] Replace overlapping stale whole-object writes with a small validated
  patch/revision contract or an explicit draft-and-save interaction.
- [ ] Reconcile runtime and display defaults for face swap, cascade retries,
  forced alignment, engine duration/audio, and other exposed flags.
- [ ] Wire only settings with real consumers; remove or label unconsumed
  controls instead of storing decorative values.
- [ ] Make language selection invoke the language-default contract and show the
  fields changed.

Acceptance: every visible setting has a validated write and production read;
out-of-order responses cannot clobber newer state; defaults are identical in
config, UI, and runtime.

### 10. Portable media persistence and explicit media states

Owned surface: media path publication/storage, `/file` resolution, migration
of old in-project absolute paths, media components, and tests.

- [ ] Persist project-relative paths or stable media IDs for new output.
- [ ] Resolve old absolute paths by safe project-owned suffix migration without
  weakening traversal/root guards.
- [ ] Return correct MIME/status metadata and render missing/migrated/loading
  states instead of broken blank media.

Acceptance: a project moved between repo roots still serves its owned media;
outside-root paths remain forbidden; previews explain missing media.

### 11. Broadcast-safe progress, replay, resume, and stage truth

Owned surface: pipeline state/checkpoint/resume APIs, event fan-out/replay,
stage reducer, advanced review/action transitions, and Run-page tests.

- [ ] Extend the basic lifecycle authority from Slice 8 to checkpoint,
  review-stage, and resume transitions without synthesizing facts absent from
  the server snapshot.
- [ ] Replace competing single-consumer SSE queues with per-subscriber
  broadcast semantics and monotonic replay/snapshot support.
- [ ] Map backend events into one documented stage vocabulary and support
  reconnect/resume.

Acceptance: two subscribers receive the same event; reconnect recovers state;
idle/running/paused/completed/failed actions are truthful; conflicts return 409
with refresh guidance.

### 12. Evidence-backed capability product

Owned surface: capability manifest/scorecard, credential/readiness surface, UI
copy/layout, and validation tests.

- [ ] Distinguish producer, consumer, evidence test, exposure, spend kind,
  static capability, and runtime availability.
- [ ] Remove raw internal hashes/IDs and retired implementation notes from the
  operator view while keeping them available in diagnostic artifacts.
- [ ] Correct identity labeling to the actual validator and show unavailable
  credentials/pod/provider status without exposing secrets.

Acceptance: no capability is advertised as engaged without a live consumer and
test; public UI contains human labels and next actions; internal evidence
remains inspectable through diagnostic output.

### 13. Final product polish, accessibility, and no-spend E2E

Owned surface: the four page layouts, shared states/feedback primitives, inert
controls, keyboard/focus semantics, responsive styling, and frontend tests.

- [ ] Remove or wire every visually interactive affordance.
- [ ] Add consistent loading, empty, error, offline, busy, and success feedback.
- [ ] Add dialog focus management, accessible labels/live regions, keyboard
  operation, and media/caption status.
- [ ] Tighten Setup density, Edit/Run media framing, Capability hierarchy, and
  constrained-width behavior using existing design tokens.
- [ ] Run a seeded no-spend journey against the real Flask server and built
  frontend. Reconcile every active operator API as surfaced, deliberately
  API-only, or internal in the coverage ledger.
- [ ] Retain named viewport/state screenshots at `1440x1000` and `1024x768`
  under `logs/ui/product-unification/<viewport>/` (loading, empty, idle,
  running, error, resumed). Record automated accessibility output at
  `logs/ui/product-unification/a11y.txt` and the seeded E2E command/output at
  `logs/ui/product-unification/e2e.txt`.

Acceptance: component tests, production build, keyboard checks, no console
errors, and browser walkthroughs of project selection, Setup, Edit, Run,
Capability, switching, error, and resume states; a documented screenshot
command and `npm --prefix web run test:a11y` reproduce the retained artifacts.

### 14. Unify prompts, config, dependencies, and current documentation

Owned surface: `README.md`, `ARCHITECTURE.md`, `OPERATIONS.md`,
`docs/PROGRAM-MANUAL.md`, `config/prompts/pipeline_context.md`,
`.env.example`, active status/config references, and affected project skills.

- [ ] Generate or validate factual engine/capability/environment tables from
  the canonical sources; keep prose rationale authored.
- [ ] Correct Google-first routing, native-audio, current UI pages, identity
  stack, retired PuLID/max/LoRA claims, environment precedence, and real
  operator routes.
- [ ] Fix Program Manual anchors only after semantic contradictions are
  resolved; do not run blind auto-fix over conflicting claims.
- [ ] Update the `ai-video-gen` guidance and any production prompt that names
  obsolete routing/model behavior.
- [ ] Pin or bound only the SDK versions proven by the adapter suites; retain
  historical lock files as labeled historical artifacts or create a new
  current lock rather than mutating history.

Acceptance: doc-claim checks pass; generated-surface `--check` passes; smoke,
full backend suite, frontend suite/build, and dependency checks are green.

### 15. Evidence-led pruning and hotspot decomposition

Owned surface is selected only after the preceding contracts are green.

- [ ] Remove confirmed dead functions/modules and migrate remaining shim
  imports before deletion.
- [ ] Extract provider attempts from large dispatch functions only where
  contract tests preserve success, retryability, billing, provenance, aspect,
  and cascade behavior.
- [ ] Establish a reproducible coverage artifact before adding any threshold.

Acceptance: grep/call-path evidence accompanies every deletion; mutation or
contract tests prove the extracted real call path; no refactor-only provider
behavior change slips into the diff.

## Per-slice dispatch record

Before a production implementer starts, the orchestrator appends or updates the
matching coverage-ledger row with:

| Required field | Meaning |
|---|---|
| `slice/task` | One independently shippable behavior, split again if shared-file or review scope is too broad |
| `BASE` | Fresh pre-task commit SHA |
| `owned files` | Exact production/test/doc pathspec; implementer does not own other worktree changes |
| `direct callers/writes` | Grep-backed real call sites and persistent write sites |
| `dependencies` | Earlier slice/contract that must already be green |
| `implementer` | Fresh bounded worker; main remains orchestration-only for production code |
| `spec review` | Independent reviewer and GO/NITS/FAIL over actual `BASE..HEAD` |
| `quality review` | Different independent reviewer and GO/NITS/FAIL after spec GO |
| `verification` | Exact offline commands plus mutation/contract probe where required |
| `disposition` | Landed, deferred with regression pin, API-only/internal by design, or removed |

Each task ends with one clean commit. A nit fix is a separate focused commit and
is re-reviewed over its own range. Main may author the plan/ledger and perform
integration verification, but does not implement the production slices.

### Live task ledger

| Slice/task | Base and owned scope | Call/write evidence and dependency | Implement/review evidence | Disposition |
|---|---|---|---|---|
| `0.1` deterministic product-surface inventory | `871c10f2`; `scripts/product_surface_inventory.py`, its unit test, generated JSON | Static Flask decorators plus `web/src` transports; no application imports | `ea59894c`, artifact refreshes `4dd28474`/`dd68ec56`; spec review `FAIL` gaps then addressed by `bee6f8cb`/`b16d8e1d`/`fb17322a`/`22dbbb5b`/`c459f89b`/`830704e1`/`67d09b6e`/`fa5dbbd3`/`aaab3658`/`7e2d6b6d`/`7b8b6786` (fail-closed inventory, TS-AST frontend transports, wrapper-chain resolution); retroactive re-review 2026-07-31 `wf_b11a3a2c`: lane-v **FAIL** + quality **FAIL** — 2 IMPORTANT latent under-count gaps (non-literal imported-wrapper drop at `.mjs:892`; `abstractSafeDefinition` bypass of the Tarjan gate at `.mjs:833`), both live-reproduced | Fix slice I1 dispatched |
| `1a` dormant LoRA containment | `a0485546`; policy, trainer/quality boundaries, direct scripts, endpoint/write guards, focused tests/ADR | Training endpoint, raw trainer/subprocess/FAL/register entrypoints, locked `global_settings` mutation | `411146aa`, fixes `2e24346f`/`871c10f2`; independent spec `GO`; Lane V quality `GO`; 91 focused tests plus sibling/full verification | Landed and closed |
| `1b` inactive/read-only LoRA product surface | `ea59894c`; character/identity/capability UI, scorecard/manifest/status, current docs/tests | Status GET only; scorecard projection; manifest renderer; zero remaining action/POST caller | `d686f2ca`, quality fix `7ac36338`; independent spec `GO`; Lane V quality `GO`; 60 frontend tests and production build | Landed and closed |
| `2a` additive typed provider truth | `4dd28474`; `domain/provider_catalog.py` and its unit test only | Exact 40 legacy keys plus dispatch-only `FAL_SVD`; no production consumer import | `cf25eee3`, fixes `6319106c`/`960c044b`/`1e386c70`; independent spec `GO`; Lane V quality `GO`; 60 focused tests plus coherence verification | Landed and closed; consumer work prepared |
| `2b-A` video authoring/ranking policy | base `14ddd8b4`; `domain/video_engine_policy.py`, `llm/prompt_optimizer.py`, `workflow_selector.py`, scene schema, target-write HTTP fences | `make_shot(target_api=...)`, optimizer suggestion writes, purpose rankings, workflow template consumers; typed catalog | `8fc46759` plus `174c056a`/`1eb6f9e8`/`f76a0a01`/`292173f9`/`de14ef19`/`d4a464a9`/`f414e8a2`/`fd6646d1`/`34531d31`/`1a8e0a91`; verified in-tree: `SORA_2` catalogued `RETIRED`/`UNSUPPORTED` all-flags-false, selectable-target policy enforced at schema/HTTP/optimizer/dispatch; retroactive reviews `wf_b11a3a2c`: lane-v **FAIL** (IMPORTANT: `_validate_raw_shot` omits `api_engines`/`aspect_ratio` so the LLM-authoring boundary cannot see project-disabled/aspect state — sibling `update_scene_shots` threads both), quality GO, money-gate GO | Fix slice R1 dispatched; `2c` NOT started |
| `5a` Firecrawl shared adapter | `firecrawl_adapter.py` (new), `web_research.py`, `research_engine.py`, `firecrawl>=3.0.2,<5` bound | Both research consumers migrated off `scrape_url(params=...)`; wheel-contract evidence in `c8327b34` body | `c8327b34` plus `8c8f8988`/`badc1217`/`37f65ec9`/`b631554f` (retry/URL bounds, public-target and private-host fences); retroactive reviews `wf_b11a3a2c`: lane-v **GO**, quality **NITS** (syntactic-only URL validation is a recorded deliberate trade; dual host-policy vs `performance/_net` noted) | Landed and closed |
| storyboard/motion spend truth (unplanned; invariant 1) | `cinema/phases/motion_render.py`, `cinema/storyboard.py`, `kling_native.py`, `phase_c_ffmpeg.py` and focused tests | Storyboard batch dispatch, segment timeline/stems, motion-output ownership | `0a035eef`/`86d0848c`/`628ae5f6`/`7790409e`/`956eb18a`/`fc9940cc`/`1d0f13a6`; retroactive reviews `wf_b11a3a2c`: lane-v **GO**, quality **NITS**, money-gate **FAIL** — CRITICAL billed-spend loss: `generate_storyboard` post-billing download failure collapses to `None`, caller records cost only on success, per-shot fallback double-spends (`kling_native.py:459`, sibling `phase_c_ffmpeg.py` legacy branch, swallowed cost-record in `motion_render.py`); the family's own test pins the bug | Fix slice M1 dispatched |
| project identity boundaries (unplanned; invariant 2) | `web_server.py`, `domain/project_manager.py`; ADR-070/071/072 | Public project/scene/shot mutation routes; stored-ID equality; typed optimizer-cache boundary | `a83ab8ec`/`93f5a296` (+ fences above); retroactive reviews `wf_b11a3a2c`: lane-v **GO**, quality **NITS** (redundant FileNotFoundError wrap) | Landed and closed |
| ADR-073 lock + optimizer-cache unification | completes the in-flight worktree draft left at `7b8b6786`; `domain/project_manager.py` sibling lock via stock `filelock>=3.24.3,<4`, `domain/optimizer_cache.py` extraction, stale-pin repairs, `scripts/clean_test_fixtures.py`, docs | Lock callers `_acquire_project_lock`/`_acquire_existing_project_lock`; cache consumers in `web_server.py` + both controller sites | Completed and reviewed in-session by the picking-up seat (Claude): vacuous Q3 lock pin repointed, sibling-geometry pin added, direct `optimizer_cache` unit tests added; focused files green (314), smoke OK, full matrix run at landing | Landed this session |

### Wave-R fix-slice ledger (2026-07-31)

| Slice | Commit | Reviews (wf_be55f23e) | State |
|---|---|---|---|
| M1 billed-spend truth (storyboard/motion) | `55c0797e` | money-gate **GO**; lane-v **FAIL** — guards correct at HEAD but unpinned for the real success shape (mutation probes: guard removal stays green across 250 tests) | Fixup `fixup:M1-pins` dispatched (test-only) |
| R1 authoring-boundary threading | `1b822551` | lane-v **FAIL** + quality **FAIL** — `test_competitive_decompose_scene_threads_aspect_state_from_global_settings` vacuous (monkeypatched predicate; green with threading removed) | Fixup `fixup:R1-test` dispatched (test-only) |
| I1 inventory fail-closed visibility | `342492d8` | lane-v **FAIL** + quality **FAIL** — zero-arg and callback-first-arg local-wrapper calls still vanish; commit's "all 25 non-network" claim false for ≥2 rows | Fixup `fixup:I1-failclosed` dispatched (production + tests) |
| M2 native billed-swallow siblings (SORA/VEO/LTX/OMNI) | — | defect verified thrice (M1 implementer Rule #13, money-gate NIT, lane-v corroboration + orchestrator source check) | Implementer dispatched (`wf_a64283dc`) |
| R2 optimizer coercion threading | — | defect verified thrice (2b-A quality MINOR, R1 implementer Rule #13, orchestrator source check of `prompt_optimizer.py:633`) | Implementer dispatched (`wf_a64283dc`) |

### Wave-1 round-2 landings (2026-07-31)

| Slice | Commit | State |
|---|---|---|
| fixup-S2C cascade-toggle CRITICAL | `a20c8b68` | landed; re-verify in flight (`wf_232e9282`) |
| fixup-tests (vacuous aspect pin, Omni on_billed asserts, enum comments) | `384d45f2` | landed; re-verify in flight |
| 4 LTX duration/audio/errors | `932135f8` (+ catalog hunks in `8b04bc6b`) | landed; money+lane-v in flight |
| 5b Act-Two migration + Gen-4 truth | `8b04bc6b` | landed; lane-v+quality in flight |
| artifact refresh | `ecd16698` | landed |

Matrix: backend 4345/0, web 74/74 + build + tsc, smoke OK, anchors clean.
**Queued follow-up fix slices:** (a) `domain/performance.py` preconditions
still assume Act-One audio-only capability — failed Mode-B synth now
hard-fails instead of degrading (S5B disclosure, needs severity judgment
from its review); (b) continuity temporal chaining (`record_generated`)
dead in production (S7 review finding — dedicated wiring slice).
Wave-1 slice roster (3/4/5b/2c/7) fully landed; Wave 2 opens next
(6b Gemini 2.5 migrations first — 2026-10 shutdown deadline).

### Wave-1 round-1 verdicts (wf_dec8ec5e, resumed post-limit)

I2 **GO** (NIT: Map/Set-typed imports over-included — disclosed trade). R3
**NITS** (one of four new tests vacuous via predicate mock-bleed; sibling spy
covers the plumbing — fixup dispatched). S3 money **NITS** + lane-v **NITS**
+ quality **FAIL** (IMPORTANT: ARCHITECTURE.md §9 still called GEMINI_OMNI
known-broken in 3 regions — fixed by orchestrator doc-sync in this commit;
MINORs: two terminal tests lack on_billed asserts, KLING_LIPSYPC_2 comment
says KNOWN_BROKEN vs actual NOT_IMPLEMENTED — fixup dispatched). S2C lane-v
**GO** + quality **FAIL** (CRITICAL: project-disabling a cascade toggle
permanently hides the row — `videoEngines()` filter keys on `selectable`;
fixup dispatched with the missing disabled-not-in-use test shape). S7
**NITS**x2 — recorded follow-ups: continuity chaining history
(`record_generated`) is DEAD in production (temporal chaining never wired —
candidate for a dedicated slice), and optimizer `image_prompt`/
`negative_constraints` still merge unconditionally (canonical-wins guards
identity_anchor only; widening is a product decision, not a defect).

### Wave-1 round-1 landings (2026-07-31)

| Slice | Commit | State |
|---|---|---|
| fixup-I2 member-access inventory | `9135587b` | landed; reviews in flight (`wf_dec8ec5e`) |
| R3 optimizer fallback filter | `4b5293d5` | landed; reviews in flight |
| 3 Gemini Omni repair + re-admission | `caad6bcf` | landed (incl. disclosed orchestrator integration: PORTRAIT set + 20 roster-pin reconciliations); money+lane-v+quality in flight |
| 2c pickers on server selectable view | `9d131e77` | landed (disclosed: SelectPill + App.tsx project_id fetch); reviews in flight |
| 7 continuity denoise + canonical identity | `4ce38c1a` | landed; reviews in flight |
| artifact refresh | `f20f40bc` | landed |

Matrix at landing: backend 4311/0, web 65/65 + build, smoke OK, anchors clean.
Remaining Wave 1: slice 4 (LTX) -> 5b (Runway Act-Two), sequential, dispatch
on review-clear (phase_c/adapter overlap with slice 3 now resolved).

### Wave-R round-2 verdicts (wf_54301ec0)

`49d1c36a` fixup-M1 lane-v **GO** (mutation re-probed). `45eed520` fixup-R1
lane-v **GO** (real-arithmetic data-narrowing verified). `10284394` M2
money-gate **GO** + lane-v **NITS** (MINOR: OMNI billed-then-aspect-rejected
pin — folded into slice 3's owned surface). `e838e18b` R2 lane-v **NITS**
(MINOR: `_fallback_optimize` shares the threading gap — slice R3 dispatched)
+ quality **GO**. `cd82f01c` fixup-I1 lane-v **NITS** + quality **FAIL**
(IMPORTANT: named-import object member-access calls — `import { api };
api.get(url)` — still vanish; contract-covered shape → fixup-I2 dispatched;
exotic residuals recorded as disclosed limitations: rebound namespace const,
barrel `export * as`, `.call/.apply`, rebound identifier).

Wave R closes on fixup-I2/R3 GO; Wave 1 (slices 3 + 2c + 7) dispatched in
parallel with them — file-disjoint.

### Resumption sequencing (recorded 2026-07-31, after the Codex pickup)

Standing rules for every wave below: fresh implementer per slice, one commit
per slice, independent spec + quality review recorded in this ledger **before
the next dependent slice dispatches** (the post-`14ddd8b4` review gap must not
recur); implementers sequential wherever owned files overlap; full offline
matrix (smoke, backend suite, web test/build, `pip check`) at each wave
boundary; R-MEASURE for any ranking/cost claim. All slices below are offline
(fixture-based) except 13d's real-local-server no-spend journey.

- **Wave R (in flight):** retroactive reviews of the five owed families
  (workflow `wf_b11a3a2c-ade`, 12 read-only reviewers). Triage gate: any
  CRITICAL/IMPORTANT finding becomes a focused fix slice — implemented,
  reviewed, and landed **before Wave 1 dispatches**.
- **Wave 1 — provider contracts + selectors:** sequential adapter chain
  3 (Gemini Omni) → 4 (LTX) → 5b (Runway Act-Two); parallel-eligible track
  (disjoint files): 2c (`/api/config` + UI selectors on the server-provided
  selectable view) and 7 (continuity/identity authority).
- **Wave 2 — model currency:** 6b first (Gemini 2.5 shutdowns 2026-10-02/16
  are a hard deadline), then 6a (OpenAI/Responses evaluation), 6c1 (Cartesia),
  6c2 (music/foley truth), 6c3 (OpenAI Audio/Viggle/Pexels status guards).
  Research fan-out may parallelize; production commits land one provider at a
  time.
- **Wave 3 — backend/UI state authority:** 8 (project-scoped state,
  `allowed_actions`, typed errors) — prerequisite for Waves 4–6.
- **Wave 4 — settings + media:** 9a (validated patch/revision write contract)
  → 9b/9c/9d (parallel-eligible, distinct consumer families) → 10 (portable
  media).
- **Wave 5 — events/resume:** 11a (broadcast fan-out/replay) → 11b (stage
  reducer/reconnect) → 11c (checkpoint/resume/review actions).
- **Wave 6 — capability + polish + evidence:** 12 → 13a → 13b/13c (parallel)
  → 13d (seeded no-spend E2E, `logs/ui/product-unification/` screenshots +
  a11y artifacts).
- **Wave 7 — documentation unification:** 14a → 14b → 14c (final drift gate).
- **Wave 8 — evidence-led pruning:** 15a–15g, each gated on the caller-evidence
  requirements already listed; only after the full contract matrix is green.

## Completion gate

The modernization is complete only when:

- no dormant, unsupported, past-sunset, or runtime-unavailable paid action is
  selectable or dispatchable; any pre-sunset deprecated fallback is clearly
  labeled and date-gated;
- every active provider adapter has a current primary-source contract test;
- every visible UI action/parameter maps to a validated backend operation and
  production consumer, or is removed/labeled read-only;
- project switching, restart, reconnect, resume, and repo relocation preserve
  truthful state and media;
- the four-page UI is visually inspected and keyboard/error paths are tested;
- the coverage ledger gives every discovered active provider, API route,
  networked UI control, setting, prompt, dependency surface, current document,
  and production skill an owner and final disposition;
- the seeded no-spend real-server journey, named screenshots, and automated
  accessibility checks are retained as reproducible evidence;
- source-of-truth docs, prompts, config, manifests, and skills agree with code;
- the full offline verification matrix is green; and
- each production commit has independent spec and code-quality review evidence.
