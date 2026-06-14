# HANDOFF — Operator-1 (Pair-A), 2026-06-15 — Wave-2 OPEN, operator idle (no Pair-A diff to verify); pod re-oriented

**READ FIRST as operator-1.** Trust `git log -1`, not this prose. Load `seat-operator` + `four-seat-protocol` skills. Supersedes `docs/HANDOFF-operator-2026-06-15-pairA-wave1-MET-verified-idle-wave2-gated.md`.

## TL;DR
Resumed operator-1; **no production code this session.** Re-verified Wave-1 green, then the user pivoted me to the **pod-realism burn** — but mid-session a concurrent **coordinator Session-10** opened Wave-2, verified the 2 CRITICAL money rows, and **already ran the ADR-024 N=1 burn**. So the burn I was setting up was already done. Net operator-1 deliverables: (1) Rule-8 re-sync, (2) confirmed operator-1 has **no triggered verification work** (all Pair-A Wave-2 rows still `open`), (3) captured the pod access state for the *next* experiment.

## Campaign state (trust `git log -1` / the scripts)
- **HEAD `0d2e58f`** (coordinator S10 wrap), **1 ahead of origin `eabda0f`** (this handoff makes it 2). Push USER-GATED.
- **Wave-1 = GATE MET 8/8** (`scripts/wave_gate_check.py 1` → MET {verified:8}); **Wave-2 = OPEN, UNMET** (`wave_gate_check.py 2` → {open:26, verified:2}); **zero open CRITICAL campaign-wide.** ci_smoke OK. (Authoritative wrap: `docs/HANDOFF-coordinator-2026-06-15-s10-wave2-opened-2crit-verified-adr024-n1.md`.)
- Earlier this session I independently re-verified Wave-1 at the **then-HEAD `8b493b6`**: gate MET, suite **2487p/0f/31xfail**, production tree byte-identical to last-verified `8b13310` (6 unpushed commits were docs-only). HEAD has since advanced (S10's 2 money fixes `db25c39`/`24ef8a0` + opens) — coordinator re-confirmed MET at the new HEAD; a fresh `wave_gate_check 1` + smoke is the next-session entry check.

## OWED BY operator-1: nothing (no Pair-A diff awaits verification)
All 5 Pair-A Wave-2 rows are still `open`/unimplemented: `has-char-lora-hole` (MAJOR, ~24-site decouple, DESIGN) · `idgate-failopen` (MAJOR, **CROSS-LANE** phase_c_vision.py — Tier-A co-sign with Pair-B director owed before dispatch; possible CRITICAL gate-bypass) · `coherence-silent` (MEDIUM) · `identity-nan-arc-bypass` (MEDIUM) · `secondary-lora-hole` (MEDIUM, sibling of has-char-lora-hole). **Stay cold/uncontaminated on these until a director-1 brief + implementer commit lands** (impl≠verifier independence). Before authoring/verifying any Wave-2 test, read `docs/superpowers/specs/2026-06-15-wave2-stub-contract.md` (dual-mode stub + ≥1 gate-fail assertion per gate).

## NEXT operator-1 — HOLD until a trigger
- A **Pair-A Wave-2 diff lands** → cold-context Lane-V verify (Rule #9); on GO `git rm` any held lock in the SAME commit (§6b). Pair-A rows are non-cross-cutting (no lock) EXCEPT `idgate-failopen` is cross-lane (co-sign, no lock).
- NITS/FAIL bounce on a Pair-A diff (none pending).
- New agent types now exist for this: **`lane-v-verifier`** (independent post-commit verify) + **`money-gate-reviewer`** (added `2f2f46d`) — usable as the cold-context reviewer in Lane V.

## Pod / realism (the session's main detour — re-oriented)
- **One pod, not two.** `ssh -p 38597 root@35.164.116.189` **IS** the Novita pod `07ed667` (that IP:port is its SSH ingress; gateway = `.env COMFYUI_SERVER_URL`). It is **UP + burn-ready**: ComfyUI running (`:8188`→200 local), RTX 6000 Ada (~29 GB free), models `char_lora_man_v1.safetensors` + `pulid_flux_v0.9.1.safetensors` present, dir `/workspace/ComfyUI`.
- **ADR-024 dual-LoRA graft N=1 = DONE** (coordinator S10): **realism = WIN** (photoreal, over-cook fixed — the graft works), **dual-binding = FAIL** (both figures bind to the man; global man-LoRA + `TOKman` dominate the PuLID-only woman — the [[project_secondary_char_needs_lora]] problem). Artifacts `logs/passb_prod_n1_*` (gitignored). **Do NOT rerun `scripts/_prod_dual_lora_pulid.py`.**
- **Next experiment = Wave-3 Realism Route A** (`docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md`): spatial `attn_mask` confinement + drop the global LoRA/trigger. This is the work the pod is now for — a **Pair-A director/content** task, not operator-seat work.
- **Pod access (detail + password in local memory `pod-ssh-credential.md`):** use the stored **password + `scripts/_pod_ssh.exp`** driver. The managed pod's sshd **rejects manually-added pubkeys** at the offer stage despite a pristine `authorized_keys`/perms/policy (proven `ssh -vvv`) — don't burn time on `ssh-copy-id`/key-install (I lost ~30 min to it). Port 8188 isn't publicly exposed → reach via the gateway URL or a password tunnel `-L 8188:localhost:8188 -fN`.
- **Pod is BILLING** → **user decision surfaced: keep it for Wave-3 Route A, or stop it.**

## Sharp edges (this session)
- **Presence "all offline" at session-start was STALE** — peers (coordinator S10) came online mid-session; HEAD marched `8b493b6 → eabda0f → 0d2e58f` under me. **Git is the tiebreaker, never presence** — a fresh `git log -1` before wrapping caught that the ADR-024 burn I was setting up was already done. [[project_operator_is_parallel_claude]]
- **Phantom-index pollution persists** (peer Workflow skip-worktree): `git status`/`git diff HEAD` show a large staged blob + deletions of live test files — all phantom (coordinator S10 verified disk=YES head=YES; committed none). **Explicit-pathspec commits only.**
- **ComfyUI cache-hit false-fail** (S10): cached graph → `success` + EMPTY `/history` → false "no images" though the PNG was written; retrieve via `/view?filename=...` or fresh seed.
- **Don't reach for SSH pubkey on managed GPU pods** — the password + `_pod_ssh.exp` is the path (see [[pod-ssh-credential]]).

cursor: `2026-06-14T17:42:12Z` (consumed through director-1's realism-wrap broadcast; coordinator Wave-2-open + operator2 status in between); unread 0. NOTE: HEAD moved `0d2e58f`→`e92c7a1`+ during this wrap (3 peers live) — trust `git log -1`, this doc's SHA refs are point-in-time.
