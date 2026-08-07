---
name: windows-worker-ops
description: Use when starting, installing, unsticking, or diagnosing the Windows GPU worker from the Mac — worker start/status, SSH tunnel, Install-Worker/Install-Candidate runs, stranded locks, or when status shows a state that contradicts GPU telemetry. Machine-side operations only; installers run ON Windows and the Mac control surface is allowlisted to {status, start} — there is NO remote stop. For readiness states, graph contracts, or capability semantics prefer comfyui-mastery; for pipeline-level identity/video design prefer ai-video-gen.
---

# Windows worker operations

This skill is machine-side ops: which host runs what, and the traps that cost
real days on 2026-08-07. Background it does NOT duplicate — consult
`../comfyui-mastery/SKILL.md` (worker topology, readiness semantics) and
`../ai-video-gen/SKILL.md` (GPU topology). Never patch Windows-side files to
make a step pass, never retry a failed install or an unknown submission, and
never start GPU work without checking what already holds the card.

Do this first (EXECUTING HOST: Mac):

```bash
cd /Users/hyungkoookkim/Content && .venv/bin/python -c "
import json, web_gpu_worker_control as w
print(json.dumps(w._remote_control('status'), sort_keys=True))"
```

## Host matrix — which action runs where

| Action | Host | Mechanism |
| --- | --- | --- |
| `status`, `start` | Mac | forced-command SSH, allowlist is EXACTLY `{status, start}` |
| stop the worker | Windows, at the keyboard | no remote stop exists, by design — stop may kill a mid-training run |
| Install-Worker / Install-Candidate / Register-WorkerTask / Install-WorkerControl | Windows, elevated | PowerShell needing `py.exe` + `%PROGRAMDATA%`; no Mac-side trigger exists |
| code transfer to Windows | Windows pulls a SHA-pinned zip | repo is public; NEVER transfer by branch name |
| gateway API calls | Mac via tunnel `127.0.0.1:18189` | bearer token from the file named by `COMFYUI_API_KEY_FILE` in `.env` |
| training launch | Mac → gateway | the gateway is the ONLY training launcher |

Fixed paths: InstallRoot `D:\ContentLivePortraitWorker`, Flux2StateRoot
`D:\ContentFlux2Klein`, LoRA state `C:\ProgramData\Content\IdentityLab\flux2-lora`,
ComfyUI input/output `D:\ContentLivePortraitWorker\{input,output}` (OUTSIDE the
checkout — never guess `sources\ComfyUI\input`). Klein probe/benchmark need the
worker RUNNING (they talk to raw ComfyUI on `127.0.0.1:8188`) and an explicit
`-StateRoot` — its default is `%LOCALAPPDATA%`, the wrong disk.

## Trap 1 — the artifact that runs is not the artifact you fetched

The repo's `candidate.json` state is a CHECKED-IN DECLARATION, not live worker
state; only the gateway's `/api/capabilities/ready` is live truth. On
2026-08-07 the live klein manifest hash differed from the pinned one because
Windows ran a pre-cutover gateway — and later the freshly-registered task threw
on every remote call because Control-Worker.ps1 was installed from a commit
BEHIND its own fix, locking the Mac out (repair needed the keyboard). Before
diagnosing any worker behavior, hash the EXECUTING copy on Windows and compare
to the intended revision (global skill: `check-artifact-that-runs`).

## Trap 2 — status reports intent; the GPU reports reality

Utilization is the signal, not memory: 9,966 MiB at 0% for 35 minutes was a
deadlocked scorer; 5,837 MiB at 97–99% was healthy `low_vram` training that
never spun the fans (most weights live in system RAM and stream per step). A
cell can read `running` forever while nothing computes — corroborate any
surprising state with `gpu_used_mib` + `gpu_utilization_percent` from the
status payload, and with ComfyUI `/queue` via the gateway before calling
something stuck or healthy.

## Trap 3 — Windows-side runbook rules (each one cost a cycle)

- Batched deletions with `-ErrorAction Stop` abort on the FIRST failure and
  silently skip the rest, which then reads as success. Delete per-item, verify
  per-item.
- Never pipe an installer through `2>&1` filtering: under
  `$ErrorActionPreference='Stop'` PowerShell 5.1 wraps pip's routine stderr
  notice into a terminating error, kills `py.exe` mid-run, and strands
  `install.lock` (which then fails closed forever until removed by hand).
- An orphaned diagnostic process whose CWD sits inside `package\` blocks
  re-install with "being used by another process" — check holders BEFORE the
  delete, not after the error.
- `Export-ScheduledTask` XML OMITS default-valued elements; under
  `Set-StrictMode -Version Latest` reading them as properties throws exactly
  when the task is correct. Validate against the live CIM definition instead.
- `Stop-SshdCleanly` has a known unfixed race (no settle window after
  `Stop-Process`); a first-attempt failure there is expected — retry once,
  unmodified. Do not re-diagnose it.
- GPU telemetry reads "unavailable" for a few minutes after a display/driver
  change — re-measure before debugging.

## Trap 4 — network identity is part of the security boundary

The Windows firewall and `authorized_keys` pin the Mac's EXACT LAN IP. A DHCP
change (WiFi toggle, new adapter) fails everything closed BY DESIGN — restore
the pinned IP (or update the reservation) rather than "fixing" Windows. Keep
DHCP reservations for both machines; check them before multi-hour runs.

## Red flags (self-check)

- "The Mac can stop/fix the Windows side from here" — it cannot; say so.
- "Status says running, so it's working" — intent, not reality; check the GPU.
- "The install failed, I'll just retry" — the failure artifact (runner log,
  stranded lock) is the evidence; a retry destroys or masks it.
- "candidate.json says not_installed" — that is the declaration, not the live
  worker; ask the gateway.
- Quoting a digest from memory — recompute under `python -B`; a remembered
  digest was wrong seven times in one day.
