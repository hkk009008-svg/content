# ADR index (generated)

One row per `## ADR` heading in [DECISIONS.md](../DECISIONS.md), which is
immutable and stays the source of truth — read the full entry there.
Regenerate with `env -u GIT_INDEX_FILE .venv/bin/python scripts/gen_doc_index.py`.

| ADR | Title |
|---|---|
| ADR-001 | Single web entry point; CLI deleted |
| ADR-002 | Predicate-poll gate model (not event-driven) |
| ADR-003 | `PipelineContext` implements dict API |
| ADR-004 | IdentityValidator as process singleton via 4-way alias |
| ADR-005 | LLM ensemble: parallel quorum + judge (not fallback) |
| ADR-006 | ComfyUI workflow JSONs at repo root |
| ADR-007 | Pedalboard as a hard dependency |
| ADR-008 | `ARCHITECTURE.md` as single source of truth |
| ADR-009 | PERFORMANCE_REVIEW gate symmetric with other 3 gates |
| ADR-010 | N=8 best-of parallelism behind a project setting |
| ADR-011 | `threshold=0.0` in identity reads was a silent ML signal bug |
| ADR-012 | Document structure: README → ARCHITECTURE → OPERATIONS → DECISIONS |
| ADR-013 | Verification discipline for factual claims |
| ADR-014 | Motion-gate auto-approve as opt-in env flag (CINEMA_AUTO_APPROVE_MOTION) |
| ADR-015 | Cycle-16 close: brief v2.0, insight-achievement reframe, Rule #16 |
| ADR-016 | GitNexus mandate was a phantom rule; removed in favor of grep/Read |
| ADR-017 | Storyboard B-integrate: batched Kling generation behind a default-off flag |
| ADR-018 | Dynamic Workflows adopted for read-analysis lanes; implementation stays subagent-driven |
| ADR-019 | Doc-maintenance run as a verifier-scoped dispatch pattern; persistence earned; scope bounded to the Guard-1 line |
| ADR-020 | Prune 5 confirmed-dead modules/symbols (327 LOC); keep dormant quality levers + preserved primitives |
| ADR-021 | Aspect backstop `_accept_or_reject` fails OPEN on probe failure |
| ADR-022 | Wire `would_exceed` as the pre-spend motion budget gate (not delete) |
| ADR-023 | Per-shot-class halt_rule defaults in MAX_QUALITY_TEMPLATES |
| ADR-024 | Production-tier identity GRAFT for realism + binding (reject tier-unification and post-pass toggling) |
| ADR-025 | Production PuLID SDXL→FLUX correctness fix (shipping default; Task-4 pod-validated) |
| ADR-026 | A non-finite budget cap fails SAFE (blocks spend), it is not "unlimited" |
| ADR-027 | Wave verification must EXECUTE the oracle, not READ the attestation (closing the gate-circularity) |
| ADR-028 | Ceremony is forbidden from the verification core, and a detector enforces it |
| ADR-029 | Identity vision fallback fails closed when the oracle cannot run |
| ADR-030 | Cross-provider seat topology Slice 1: signed-JSON event store, single-writer, gate-recomputed merge to a TEST ref |
| ADR-031 | Cross-provider seat topology Slice 2: `refs/threeway/events` one-commit-per-event bus, dual-mode CAS append, verifying idempotency, validated per-seat cursors |
| ADR-032 | The verification dispatch is a self-executing, fail-aware, machine-consumable contract |
| ADR-033 | Reviewer-result consumer + R6 built; ADR-032's deferred follow-up discharged |
| ADR-034 | Cross-provider seat topology Slice 2.5: legacy `coordination/` mailbox migrated onto `refs/threeway/events` as carrier events, in-memory shadow, single authority-flip cutover; coordinator + coordinator2 become receiving seats |
| ADR-035 | Cross-provider seat topology Slice 3: tiered co-sign `co_sign_satisfied` enforces T2/T3, with all identity grounded on overseer-signed assignment facts + the key-bound seat token, never the unsigned `signer` string |
| ADR-036 | Revocation authority: an `attestation_revoked` takes effect only from the `overseer` or the target's own signer seat (closes the Slice-3 forged-revoke promotion/DoS) |
| ADR-037 | Event ids are globally unique: the gate rejects duplicate ids and the store refuses a colliding-id append |
| ADR-038 | Round-5 hardening: reserved merge-id integrity + `brief_superseded` authority (Rule #13 siblings) |
| ADR-039 | Availability hardening: authority-aware reducer, self-consistent candidate resolution, and a TOTAL run_gate (closes the insider availability/DoS class) |
| ADR-040 | Complete `run_gate` totality: verify-phase drop-not-raise + pre-CAS exception guard (ADR-039 follow-up) |
| ADR-041 | Make `run_gate` step 1 TOTAL: a `well_formed(ev)` envelope guard + reducer fold/skip guards (ADR-040 follow-up, completes the availability class) |
| ADR-042 | Close `threeway-candidate-id-pair-binding-dos`: structural pair-namespaced candidate ids (ADR-039 Residual (i)) |
| ADR-043 | Close the two scope-(b) T3 deferrals: re_verify freshness challenge + per-approver key-bound human_approval |
| ADR-044 | Cutover-substrate hardening: non-atomic `_teardown` (half-flip + masked cause) + refstore dedup dropping a distinct-target revoke/supersede |
| ADR-045 | Complete cutover-sequence teardown coverage: guard the pre-cursor-try validation (Rule-13 sibling of ADR-044) |
| ADR-046 | Make `RefEventStore._iter_local` TOTAL against a malformed stored blob (Rule-13 sibling of ADR-041; closes a deserialization-time total-bus DoS) |
| ADR-047 | Atomic cursor-backfill manifest write + diagnosable corrupt-manifest handling (closes a cutover resume/rollback wedge) |
| ADR-048 | Pin the merge-tree algorithm config for host-independent determinism (close merge-tree non-determinism) |
| ADR-049 | Cutover force-rerun cursor over-advance: source the seq-map from the archived manifest + reject non-ISO cursors |
| ADR-050 | Unify the cutover total-order derivation to one shared carrier-event classifier (close total-order congruence) |
| ADR-051 | Canonicalize cutover seat-cursor keys against the roster + loud-fail a missing seat (close the seen/-filename seat-key family) |
| ADR-052 | Correct the threeway activation tooling: real envelope/gate/cutover API + a --yes-gated cutover CLI + truthful status |
| ADR-053 | Wire inert threeway CI signing to the real integration SHA and authoritative bus ref |
| ADR-054 | Canonicalize the divergence checker's seated-set against the roster (close the seen/-filename seat-key family; Rule-13 sibling of ADR-051) |
| ADR-055 | Make the threeway activation scripts self-bootstrap sys.path (close the bare-`python scripts/X.py` ModuleNotFoundError; follow-up to ADR-052/053) |
| ADR-056 | Minimal operable mechanical-seat runtime (threeway scope-b, sub-project 1) |
| ADR-057 | `overseer-plan` auto-decompose layer (threeway scope-b automation track, T0/T1) |
| ADR-058 | `overseer-plan` T3 extension (all tiers; emit approver_roster + re_verify_challenge) |
| ADR-059 | `candidate_aborted` read-time abort authority (close the forge / cross-pair abort DoS) |
| ADR-060 | wire the rework circuit-breaker on authority-aware aborts (C1 Part 2) |
| ADR-061 | Retire `bootstrap_emit.py` shim; `seat_emit` + `consume_bus` are the live seat↔bus path (threeway scope-b, sub-project 2) |
| ADR-062 | De-degrade legacy unread surfaces to the live ref-bus; `consume-events` refuses scalar cursors (Slice-2.5 follow-up) |
| ADR-063 | De-degrade the two adjacent unread surfaces ADR-062 left out (seat_status dashboard; STATE.md hook) |
| ADR-064 | Threeway T2/T3 emitter completion and protected-main boundary |
| ADR-065 | Retire the max image-gen tier; production is the only tier (LoRA training kept dormant) |
| ADR-066 | Hard-contain dormant per-character LoRA until the full consumer contract exists |
| ADR-067 | Storyboard segments are bounded, frame-validated owned artifacts |
| ADR-068 | Persisted video targets are authorized at the terminal write boundary |
| ADR-069 | Canonicalize storyboard stems and prove containment before side effects |
| ADR-070 | Bound project identifiers and keep project-aware discovery read-only |
| ADR-071 | Public shot replacement admits only typed production fields |
| ADR-072 | Bind public updates to one existing project and typed cache shape |
| ADR-073 | Delegate lock hardening to upstream filelock; sibling lock path; shared optimizer-cache module |
| ADR-074 | Final assembly honors the color-grade setting; the mood fallback reads the real settings key |
| ADR-075 | opencv-python is capped below 5.x because the whole face stack needs the Haar API |
| ADR-076 | The unit suite supplies placeholder credentials instead of skipping without them |
| ADR-077 | Skill-twin body-parity gate in ci_smoke (.agents ↔ .claude) |
| ADR-078 | AdaFace embedding adapter behind the EMBED_MODEL chokepoint (P5 item 1) |
| ADR-079 | Dual-channel (stderr + warnings.warn) for all load-bearing production warnings |
| ADR-080 | The per-engine settings schema declares only what the program reads |
| ADR-081 | Delete `cinema/pipeline.py`; supersedes the 2026-06-03 KEEP |
| ADR-082 | Uncontain Viggle at ProductSupport.LIMITED, not SUPPORTED |
| ADR-083 | Delete the dormant LTX transition helpers (plan slice 15b) |
| ADR-084 | Durable production control plane with explicit paid-media boundaries |
| ADR-085 | Bind the LivePortrait canary to the local Windows worker and fence PuLID prompt IDs |
| ADR-086 | Retire SadTalker Mode-B and require explicit driving performances |
| ADR-087 | Make the app shortcut self-healing and Windows GPU launch explicit |
| ADR-088 | Cinemaker launch brings the Windows worker up alongside the UI |
| ADR-089 | One reference per character is the measured FLUX.2 default |
| ADR-090 | The published LoRA adapter is expected inside the ComfyUI checkout |
| ADR-091 | ADR-089's default is right where it was measured, and only there |
| ADR-092 | The identity scorer inverts rank on off-angle views; those findings are void |
| ADR-093 | A product fills only the reference slots no face was using |
| ADR-094 | Location plates reach a generator; the continuity anchor still does not |
| ADR-095 | The Reference Sheet shows provenance and delivery, never a score |
| ADR-096 | A character who depicts nobody can now be created, and costs more |
| ADR-097 | The previous shot now travels with the next one, at the cost of one face slot |
| ADR-098 | The approved keyframe was discarded by fal VEO; motion prompts stop asserting a face |
| ADR-099 | fal VEO accepts three reference images, not four; the old slice was unreachable |
| ADR-100 | Kontext accepts four images, not six; adding references broke identity |
