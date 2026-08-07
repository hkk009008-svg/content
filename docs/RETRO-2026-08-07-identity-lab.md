# RETRO — 2026-08-07 Identity Lab campaign

Written the same day, from session artifacts and command output rather than
memory. Companion skills route each lesson (see the routing footer). The live
incident at the bottom was still open when this was written.

## The campaign in one paragraph

Goal: five-cell Identity Lab comparison (native FLUX.2 Klein at 1/2/4
references vs text-only control vs character LoRA) on the Windows RTX 5070 Ti
worker, driven from the Mac. The native half COMPLETED: 1 ref **0.791 pass**,
2 refs **0.766 pass**, 4 refs **0.499 FAIL** (GhostFaceNet, 0.70 gate) — more
references made identity monotonically WORSE. The LoRA half reached real
training for the first time (~7 minutes at 97–99% GPU, 5,837 MiB) and failed
post-training; diagnosis was in flight when this was written. Getting there
took ~16 defects across 8 pushes, with the LoRA `package_digest` moving seven
times in one day. Every defect was found by running or reading code on the
target machine. Zero were caught by the 5,535-test backend suite.

## Defect ledger (chronological)

1. **Register-WorkerTask.ps1 — serializer-omitted XML reads.** Read
   `RunLevel`/`Enabled`/`StartWhenAvailable`/`WakeToRun` from
   `Export-ScheduledTask` XML as bare properties under
   `Set-StrictMode -Version Latest`. Task Scheduler OMITS default-valued
   elements, so the assertion was unsatisfiable exactly when the task was
   correct. Fix: subtractive — the live CIM definition already enforced all
   four. Measured on the host: `<RunLevel>` present in 16/60 tasks, none of
   them LeastPrivilege.
2. **Control-Worker.ps1 — same class, in the forced SSH command.** Installed
   from a commit behind the fix; the first remote `status` after correct task
   registration threw and locked the Mac out (exit 70, "worker control failed
   closed"). Found by the new class guard's FIRST run, in a file nobody was
   editing. Repair required the keyboard.
3. **Stop-SshdCleanly race.** `Stop-Process` does not block; the assertion
   follows with no settle window; the script's own precondition guarantees a
   live per-connection sshd child to race against. UNFIXED by choice — retry
   unmodified works; an untested timing change did not belong in a recovery
   push.
4. **contract.py — json.loads before returncode.** A crashing probe prints
   nothing, so `json.loads("")` always raised first and the child's stderr was
   captured and discarded. Cost hours of misdirected CUDA diagnosis when the
   real cause was an unimportable dependency.
5. **torchcodec needs system FFmpeg DLLs pip cannot supply.** ai-toolkit never
   imports torchcodec (only stale comments name it; PyAV does the real work).
   Decision: REMOVE the pin rather than add an unhashed system dependency to a
   hash-pinned candidate. Net −19 lines (23 deleted, 4 binding updates).
6. **The write-once family blocks re-install.** `_copy_package` digest
   equality; `runtime-receipt.json` written `O_EXCL` and never deleted;
   `evidence/install.json` compared for exact equality while embedding
   volatile telemetry (`free_disk_bytes`, `free_vram_mib`,
   `gpu_utilization_percent`) — a byte-identical package could fail because
   the disk filled slightly. Re-install requires deleting all three.
7. **packages_sha256 asymmetry.** install.py enumerated distributions in a
   clean interpreter; the probe enumerated AFTER importing 47 modules —
   `import setuptools` appends its `_vendor` directory to `sys.path`, adding
   ten vendored distributions and shadowing platformdirs. Receipt and snapshot
   could never agree. Reproduced on macOS (151→163 distributions), proving the
   mechanism platform-independent. `importlib.metadata.distributions()` is NOT
   a pure function of the environment. Fix: enumerate BEFORE importing.
8. **Nine-variable env allowlist vs import-time home lookup.** The gateway's
   runner environment omits `USERPROFILE`/`HOME`; matplotlib calls
   `Path.home()` at import → `RuntimeError` surfaced as "CUDA runtime probe
   failed". Install had passed only because the elevated shell HAD a home.
   Fix: `MPLCONFIGDIR` (non-empty, absolute). Proven: 47/47 imports succeed
   with `Path.home()` still raising, so the scrub stays intact.
9. **refs/main newline.** install.py wrote `QWEN_REVISION + "\n"`;
   huggingface_hub reads the ref with no `.strip()` and joins
   `snapshots/<rev>\n/` — every offline lookup failed. contract.py `.strip()`ed
   before comparing, so verification was structurally blind to the byte the
   installer wrote. The FIRST fix was inert: it stopped writing the newline
   but only wrote when the file was absent — tolerate-not-repair, the same
   defect one layer up. Second fix: repair in place when bytes differ, refuse
   symlinks.
10. **.aitk_size.json.** ai-toolkit writes it unconditionally into the
    manifest-sealed input directory; the exact-set validator would fail a
    COMPLETED run at harvest and every retry at admission. Fix: tolerate
    exactly one named file.
11. **Cache directories.** `cache_latents_to_disk` + `cache_text_embeddings`
    (a train-level flag copied into every dataset by BaseSDTrainProcess)
    create `_latent_cache/` and `_t_e_cache/` inside the same sealed
    directory; name tolerance alone was insufficient because the entry loop
    requires `S_ISREG`. Our own config requested what our own validator
    forbade. Fix: `RUNTIME_INPUT_ARTIFACT_DIRS`, admitted only as real
    directories (symlinks rejected — a tolerated NAME must not admit arbitrary
    content). Filesystem control 7/7.
12. **Telemetry latch above the return-code check.** `telemetry_complete`
    latches False on ONE sampling hiccup (the sampler runs every 0.25 s for
    hours) and the branch sat ABOVE `return_code != 0`, so `return_code or 4`
    turned a CLEAN exit into `failed`, `adapter=None`, returning before
    harvest — discarding a fully trained adapter. Fix: moved below. The FIRST
    version of this fix had its own defect, caught by the adversarial
    verification pass over this document: the `training_passed` terminal
    hardcoded `telemetry_complete=True`, which was accidentally correct while
    the path was unreachable with incomplete telemetry — and became a lie the
    moment the fix made it reachable. The success terminal now records the
    MEASURED value, so `peak_vram_bytes` is honestly marked a lower bound
    whenever the flag is False. Guarded by an executable test
    (`test_run_toolkit_clean_exit_with_failed_telemetry_returns_measured_flag`),
    reversion-proven against the pre-fix shape.
13. **Poll loop caught ContractError only.** `TimeoutExpired` (nvidia-smi
    stalls under load) or `AttributeError` (stdout `None` under defect 14)
    escaped the loop AND the `with`, orphaning the live trainer holding VRAM.
    Fix: deliberately broad except (telemetry is observational) + `finally`
    kill/reap. Guarded by an executable test
    (`test_run_toolkit_reaps_child_when_loop_exits_abnormally`),
    reversion-proven: on the pre-fix shape the exception escapes and the
    child is orphaned.
14. **`-I` implies `-E` → child loses PYTHONUTF8.** The child writes the host
    ANSI code page (949 here) while the parent decodes UTF-8. On Windows
    stderr comes back `None` (reader-thread decode error swallowed); on macOS
    the `UnicodeDecodeError` ESCAPES `subprocess.run`. So `(stderr or "")` —
    inside the very fix for defect 4 — produced an EMPTY diagnostic, precisely
    on the non-ASCII DLL-load failure class it existed to expose. Fix:
    `encoding="utf-8", errors="replace"` on both calls; "DLL" survives legibly
    through replacement characters.
15. **TensorFlow/PyArrow Abseil collision (Mac).** Both vendor Abseil
    `lts_20250814`; pandas imports pyarrow long before deepface imports
    tensorflow; macOS binds first-loaded symbols process-wide → TF's
    `Notification::WaitForNotification` waited on libarrow's Abseil forever.
    Identity scoring hung at 0% CPU with no timeout; an experiment cell stayed
    "running" indefinitely. Diagnosed by `sample` on the stuck process, not by
    inference. Fix: `import tensorflow` FIRST in web_server.py — that import
    is load-bearing and commented as such.
16. **The web server was running yesterday's code.** Started the previous
    morning, it predated every Identity Lab route (404). Process edition of
    the master pattern below.

Own-goal appendix: the source-text assertion budget guard counted EVERY
`assert`, so it fired when two behavioural assertions were added to a file
holding ZERO source-text assertions. A control that penalises good tests to
keep a bad-test counter flat is the class it exists to catch. Ceilings
re-derived from the correct measurement (256/4/0), all sitting exactly at the
limit.

## Known-open at time of writing

1. LIVE: training ran ~7 min @97–99% then `runner_preflight_failed` — the
   gateway's catch-all for "train.py exited without parseable evidence"; does
   NOT mean preflight. Windows-side log diagnosis in flight.
2. Harvest-window crash leaves two safetensors where the resume probe requires
   exactly one → job permanently unretriable (high confidence).
3. `_final_adapter` hard-fails a successful run if `optimizer.pt` is missing
   (medium).
4. Retained `gpu-training.lock` no code path removes (medium).
5. Qwen cache pinned subset-only, not exact-set — an extra file in the
   snapshot dir silently changes the tokenizer build (medium; does not fire on
   the current filesystem).
6. NTFS junctions bypass `S_ISLNK` at seven contract.py sites (a junction is a
   reparse point, not a symlink) — a tolerated cache name could point outside
   the sealed tree. One-clause fix (`FILE_ATTRIBUTE_REPARSE_POINT`); deferred
   as defense-in-depth needing write access to an already-sealed dir.
7. Stop-SshdCleanly race (ledger #3).
8. The terminal-decision branch inside `train.run()` (ledger #12's elif
   ordering and success-terminal call site) has no executable coverage —
   reaching it requires the gateway's hash-bound activity lease, which tests
   cannot forge by design. The `_run_toolkit` guards cover the measured-flag
   propagation up to that boundary.

## Patterns

- **P1 — The artifact that runs is not the artifact you fetched.** Stale
  installed `package\` imported by the probe; Control-Worker installed from a
  pre-fix commit; the web server running yesterday's code; `state_root`
  package vs source tree. Hash the EXECUTING copy; compare process start time
  to deploy time. (→ global skill `check-artifact-that-runs`)
- **P2 — Write-once-then-compare breaks re-install** whenever the compared
  value mixes immutable identity with volatile readings. Separate them; only
  identity gets equality.
- **P3 — Normalization hides the difference the check exists to detect.**
  `.strip()` before compare made verification blind to the byte the installer
  wrote; tolerate-not-repair repeated it one layer up. If you normalize on
  read, you must repair on write.
- **P4 — Discarded stream at the throw site** (four instances, one inside its
  own fix). Check returncode before parsing stdout; decode explicitly with
  `errors="replace"`; carry a bounded stderr tail into every message.
- **P5 — Two halves of one system requesting opposite things.** Config asks
  for caches the validator seals out; installer writes what the verifier
  strips. Test the SEAM, not the halves.
- **P6 — Tests prove only what they execute, and a guard needs TWO controls.**
  5,535 green while all sixteen shipped; substring assertions over another
  language's text cannot fail when the logic is wrong. A **reversion** control
  (restore the defect, watch the guard fire) proves non-vacuity ONLY; an
  **evasion** control (guard intact, reach the bad outcome another way) proves
  sufficiency — reversion structurally cannot catch the evasion class. The
  class guard here was reversion-proven against pre-fix source (4/4 caught)
  and evasion was demonstrated by the NTFS-junction bypass of `S_ISLNK`.
- **P7 — Falsify-first with outcome contracts.** Define pass/fail meaning
  BEFORE the run. Four wrong hypotheses died cheaply (sm_120, `[N/A]` parse,
  /history proxy, GPU contention). A prediction stated in advance (the
  `dabf85d8…` receipt) is stronger confirmation than an absent error.
  (→ global skill `falsify-first-debugging`; prior art: Platt, *Strong
  Inference*, Science 1964 — prefer the experiment whose alternative outcomes
  each EXCLUDE a hypothesis.)
- **P8 — Validate the instrument on a known value first.** `package_digest`
  reproduced `06962ede…` on both source and installed copies before being
  trusted to judge `a653df7b…` — so a later mismatch indicts the tree, not the
  tool.
- **P9 — Vendored-dependency collisions corrupt process-global state.** Two
  libraries bundling the same C++ dep (Abseil) or vendor tree (setuptools)
  fight over symbols and `sys.path`. Import order becomes load-bearing;
  enumeration becomes impure.
- **P10 — Cross-machine transfer rules.** Pin full commit SHAs, never
  branches; download by SHA-zip; state SUPERSEDED items explicitly in every
  fresh-session brief; run digest gates under `python -B` (a `__pycache__`
  from a bare import fails the exact-set rglob — bit two agents in one day);
  delete per-item, never `-ErrorAction Stop` across a batch; no redirection
  around installers whose callers treat stderr as terminating (`2>&1` under
  `$ErrorActionPreference='Stop'` turned pip's routine notice into a
  mid-install kill and a stranded lock).
- **P11 — Utilization is the signal, not memory.** 9,966 MiB @ 0% = deadlock;
  5,837 MiB @ 99% = healthy training. With `low_vram` block-swapping, real
  training barely warms the fans — a quiet card is not an idle card, and a
  status field can report intent while the GPU reports reality.
- **P12 — Subtractive fixes close review; additive fixes reopen it.** Four of
  the session's fixes were pure deletions.

## What worked (keep doing)

- Pre-verification gates before spending cycles — caught three blockers before
  any execution, twice saving a full install round-trip.
- Outcome contracts agreed before each run.
- Adversarial refuters — three independent attempts to break the "refs/main
  fix is a no-op here" claim; all failed; the claim was then trusted and was
  right.
- Reduced-scope external replay (the import-loop replay recovered the full
  traceback WITHOUT touching the pinned digest).
- Cross-platform reproduction to prove mechanism (setuptools pollution on
  macOS; the decode failure's two distinct per-platform failure modes).
- Immutable evidence chains — probe evidence sha binds into the benchmark;
  status pointers carry the hash of what they point at.
- No-retry discipline; `submission_unknown` treated as neither pass nor fail,
  never resubmitted.
- Honest supersession — telling the fresh session what NOT to believe
  prevented at least one wasted cycle (the stale FFmpeg decision replay).

## Identity findings (product level)

- **Klein multi-reference AVERAGES.** The generated face widened monotonically
  as profile/¾ references were added; 1 frontal (0.791) beat 4 mixed angles
  (0.499) at 3.4× the latency. Independently corroborated by practitioner
  guidance ("2 images most reliable; 4+ unpredictable; influences roughly
  balanced"). Scope the claim to Klein at its 4-image ceiling.
- **Session confounds get baked in.** All four references came from one
  sitting; glasses appear in 100% of generations though never prompted. For
  re-shoots: vary sessions/lighting/clothing, keep references near-frontal —
  vary the confounds, not the yaw.
- **Caption strategy fixes confounds at zero pin cost** (research-sourced):
  the trigger absorbs what captions do NOT describe — caption
  glasses/wardrobe/background explicitly, never facial features. Candidate
  change for the next LoRA round: captions currently read "portrait photograph
  of hkkperson person, identity reference view N".
- **Checkpoint-selection tip** (research-sourced): 4 images × 500 steps = 125
  epochs; the best checkpoint is often pre-final. Checkpoints exist at
  100/200/300/400; evaluate more than the final adapter.
- **Config already matches best practice** on two research warnings, verified
  against candidate.json: optimizer is `adamw8bit` (adafactor reportedly
  collapses faces on Klein), and training uses the base checkpoint
  (`FLUX.2-klein-base-4B`) while inference uses the distilled fp8 — the
  recommended split.
- **Confound-swapped scoring** (research-sourced, cheap): add "no glasses" /
  "wearing a suit" prompts to the eval; the similarity drop quantifies how
  much of "identity" is actually glasses.
- **PuLID baseline for comparison:** FLUX.1-dev bare 0.6205 fail / +PuLID
  0.8779 pass. PuLID-FLUX.2 stays failed-closed by design: 18.2 GiB measured
  peak (does not fit 16 GB), adapter 4096-wide vs Klein's 3072, InsightFace
  models non-commercial.
- **Scoring instrument:** GhostFaceNet at 0.70 via `identity/validator.py` —
  the "ArcFace" name in older ADRs is a recorded misnomer. Scoring runs on the
  Mac; `web_server.py` must import tensorflow before anything imports pyarrow
  (ledger #15) — that import is load-bearing.

## Routing footer

| Lesson | Where it lives now |
|---|---|
| P1, P2, P8 + ledger 16 (stale-process instance) | `~/.claude/skills/check-artifact-that-runs` (global, portable) |
| P4, P7 + Platt | `~/.claude/skills/falsify-first-debugging` (global, portable) |
| Worker ops, P10, P11, ledger 1–3 | `.claude/skills/windows-worker-ops` |
| Digest/re-pin cycle, P8, P10 | `.claude/skills/digest-repin-cycle` |
| Handoff briefs, SUPERSEDED discipline | `.claude/skills/cross-machine-handoff` |
| Retro procedure itself, P6 two-control doctrine | `.claude/skills/post-incident-retrospective` |
| Ledger 10–11 (sealed-input tolerance) | executable test `test_runtime_artifacts_tolerated_and_symlink_cache_rejected` |
| Ledger 12 (telemetry latch + measured-flag evidence) | executable test `test_run_toolkit_clean_exit_with_failed_telemetry_returns_measured_flag` |
| Ledger 13 (supervision: broad except + finally reap) | executable test `test_run_toolkit_reaps_child_when_loop_exits_abnormally` |
| Campaign state + patterns | memory `content-identity-lab.md` (Pipeline-session memory dir) |
| Tenth vacuity class (own-goal appendix) | memory `doc-guard-tests-claim-more-than-they-enforce.md` (same dir) |
| Transfer manifest | `docs/HARNESS-TRANSFER-BUNDLE.md` |

All three executable tests live in `tests/unit/test_windows_flux2_lora.py` and
were reversion-proven against the reconstructed pre-fix shapes (each fails on
the pre-fix code for the stated reason). Ledger 12's decision branch inside
`train.run()` itself remains execution-untested — reaching it requires forging
the gateway's hash-bound activity lease; recorded as known-open #8 rather than
papered over.
