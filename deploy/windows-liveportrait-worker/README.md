# Windows 11 LivePortrait worker

This profile installs a native, single-queue LivePortrait GPU worker on the
Windows 11 desktop. The Content application and authoritative project store
remain on the Mac, while bounded input working copies and generated output are
staged on Windows for execution. It does not install InsightFace, its pretrained models, or
`landmark_model.pth`. Face detection uses MediaPipe and landmark inference uses
CPU ONNX Runtime; LivePortrait inference itself uses the NVIDIA GPU.

The profile is deliberately fail-closed. Installation never starts or registers
the worker. A tracked one-frame API graph and deterministic source/expression
fixture pair are installed, but registration is refused until they pass
source/model/dependency/GPU checks, live `/object_info` input-schema validation,
and a real one-frame expression execution on the target GPU.

## Pinned contract

- Windows 11 AMD64, CPython 3.12.
- ComfyUI 0.30.0 at `b1693ecba9f5b65f8c80ab36b195ab963ec92413`.
- ComfyUI-LivePortraitKJ at `4d9dc6205b793ffd0fb319816136d9b8c0dbfdff`.
- VideoHelperSuite at `4ee72c065db22c9d96c2427954dc69e7b908444b`.
- PyTorch 2.11.0, torchvision 0.26.0 and torchaudio 2.11.0 CUDA 13.0
  CPython 3.12 Windows wheels, each bound to its official wheel SHA-256.
- NumPy 1.26.4, MediaPipe 0.10.14, CPU ONNX Runtime 1.19.2.
- A CPython 3.12 / Windows AMD64 resolved dependency lock; the three CUDA
  wheels additionally carry official SHA-256 fragments.
- The six exact artifacts in `models.json`, all from Hugging Face revision
  `59f30f36d7b791929c25437df7461d5b0e0010b1`.

The distributor does not declare model-file licensing in the pinned model
repository. LivePortrait and the Kijai integration have MIT provenance, but a
human must review the model terms before commercial use.

## Network boundary

Both processes bind to Windows loopback only:

- raw ComfyUI: `127.0.0.1:8188`
- bearer-authenticated gateway: `127.0.0.1:8189`

No Windows firewall rule opens 8188 or 8189. The registration script audits
enabled inbound rules that can actually apply to `sshd.exe`; packaged-app and
other-program rules are not mistaken for SSH authority. It accepts one existing
rule only when it is exactly TCP/22 from the Mac's concrete RFC1918 IPv4 address,
otherwise it refuses to mutate that rule. If no such rule exists it creates one
uniquely named package rule. A later failure removes only a package rule created
by that invocation. Registration also requires the Windows Defender Firewall
service and every effective profile to be enabled with default inbound blocking;
an allow rule is not treated as an enforced boundary otherwise. Do not configure
router port forwarding.

Reserve both LAN addresses in the router's DHCP configuration before
registering the Windows firewall rule or the Mac tunnel. The firewall and SSH
host-key contracts intentionally bind a concrete address; an unreviewed DHCP
change must fail closed instead of silently reaching another LAN host.

On the Mac, first connect once interactively and verify the Windows SSH host-key
fingerprint out of band so the concrete address is present in the user's
`known_hosts`. Then install the tracked per-user launchd supervisor (substitute
the account, address, and key path):

```bash
WINDOWS_PRIVATE_IPV4="<your-windows-rfc1918-ipv4>"
.venv/bin/python deploy/windows-liveportrait-worker/install_mac_tunnel.py \
  --windows-host "$WINDOWS_PRIVATE_IPV4" \
  --windows-user windows-user \
  --identity-file /absolute/path/to/a/mode-0600-private-key \
  --known-hosts /absolute/path/to/a/pinned/mode-0600-known_hosts
```

The installer refuses root, public or hostname-only destinations, unknown host
keys, permissive key files, password prompts, and a local port owned outside
the declared launchd service. It installs an atomic mode-0600 LaunchAgent with
`BatchMode`, `IdentitiesOnly`, `ExitOnForwardFailure`, strict host-key checking,
keepalives, loopback-only forwarding, restart throttling, and health verification.
If bootstrap or readiness fails, it removes the failed service and restores the
prior plist. Logs stay under `~/.local/state/content/liveportrait-tunnel/`.

Then configure the Mac application with:

```env
COMFYUI_SERVER_URL=http://127.0.0.1:18189
COMFYUI_API_KEY_FILE=/absolute/path/to/a/mode-0600-token-file
PERFORMANCE_COMFYUI_SERVER_URL=http://127.0.0.1:18189
PERFORMANCE_COMFYUI_API_KEY_FILE=/absolute/path/to/the-same-mode-0600-token-file
```

Both role URLs point at the same loopback tunnel and both resolved credentials
must equal the random gateway token entered on Windows. `COMFYUI_API_KEY` and
`PERFORMANCE_COMFYUI_API_KEY` remain supported and outrank their `_FILE`
alternatives. The authenticated capability contract below keeps each role's
readiness independent while the secret remains outside the repository dotenv.

## Install without starting the GPU worker

Copy this directory to the Windows PC, open PowerShell as the intended worker
user, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
$InstallRoot = "D:\ContentLivePortraitWorker" # or Join-Path $env:LOCALAPPDATA "ContentLivePortraitWorker"
.\Install-Worker.ps1 -InstallRoot $InstallRoot
.\Set-WorkerSecret.ps1 -InstallRoot $InstallRoot
```

`InstallRoot` is one indivisible deployment identity. If you place the worker
somewhere other than the default `%LOCALAPPDATA%\ContentLivePortraitWorker`,
pass the same explicit `-InstallRoot` to **Install-Worker.ps1,
Set-WorkerSecret.ps1, Test-Worker.ps1, Register-WorkerTask.ps1,
Start-Worker.ps1, and Benchmark-Worker.ps1**. Mixing the default and a custom
root creates a second installation and is rejected operationally; quarantine
any partial wrong-root install before continuing.

The installer also copies the tracked graph and contract into `probes` and
decodes the hash-bound fixture payloads into `input`. It is idempotent for
verified source/model/probe files. It stops on a
dirty or unexpected untracked source file, origin mismatch, revision mismatch, corrupt existing model,
failed wheel hash, or dependency conflict. It does not replace corrupt files
automatically.

Runtime user state, Hugging Face/Torch caches, inputs, outputs, logs, and temp
files live outside the pinned repositories. The installer mirrors the tracked
worker package through a hash-verified staging directory, replaces the prior
package inventory atomically, and excludes or removes Python bytecode caches.
Bytecode writes are disabled for every worker Python process. The only permitted untracked entries in the ComfyUI repository
are the two separately pinned nested custom-node repositories; each nested
repository is then audited with all untracked files visible.

The token is entered as a `SecureString`, must contain at least 32 characters,
and is stored with current-user Windows DPAPI protection plus a current-user-only
ACL. It is never placed in a task argument or persistent environment variable.

## Working-copy retention

Tunnel authentication protects transport; it does not erase media or provide
at-rest encryption. The Mac project store is the source of record, but uploaded
production keyframes/driving clips and generated results can remain under the
Windows worker's `input`, `output`, and `temp` directories after a request.
Probe fixtures in `input` are intentional installed assets. Production media is
not currently subject to an automatic retention timer, so an operator must stop
the scheduled worker and perform a reviewed, project-aware cleanup before
repurposing the PC or account. Do not recursively wipe the installation root:
it also contains models, pinned sources, protected state, and probe assets.

The one-frame readiness probe and guarded benchmark are different: each assigns
a fresh UUID filename prefix and removes only regular files with that prefix
after validation, including VideoHelperSuite PNG sidecars. Cleanup resolves
every candidate beneath the worker output root and fails closed on links or
non-file entries; unrelated output is preserved.

## Tracked expression probe

`probes/one-frame-expression-api.json` is generated from the same
`performance.live_portrait_workflow` graph builder used by the Mac. It binds
`source-face.jpg` and `driving-expression.mp4`, caps video ingestion to one
frame, uses the CPU MediaPipe cropper, and saves output through node `19`.
`probes/probe.json` binds the exact workflow and decoded fixtures by SHA-256 and
byte count. Preflight also walks the dependency graph to prove that every node
reaches output 19, validates every input against the live `/object_info` schema,
and decodes the resulting MP4 with PyAV to prove it is a real one-frame media
container.

The two fixture payloads are deterministic crops of the tracked synthetic
performer test asset. `fixtures/provenance.json` preserves that source's path,
hash, crop, and output hashes. The neutral top-left portrait is the source; the
surprised bottom-right portrait is the one-frame expression driver.

If any tracked graph, fixture, model, source revision, package, node schema, GPU
allocation, or execution result differs, `state\ready.json` is absent,
registration fails, the gateway is not started, and `/health/ready` cannot
report ready.

## Validate and register

`Test-Worker.ps1` is the first command that intentionally initializes CUDA and
loads the models:

```powershell
$InstallRoot = "D:\ContentLivePortraitWorker" # or the default under $env:LOCALAPPDATA
& "$InstallRoot\package\Test-Worker.ps1" -InstallRoot $InstallRoot
```

After it passes, open an elevated PowerShell window under the same Windows user
and register the manual-only supervisor. Replace the Mac address if DHCP assigned
a different one:

```powershell
$InstallRoot = "D:\ContentLivePortraitWorker" # reuse the exact install identity
$Flux2StateRoot = Join-Path $env:LOCALAPPDATA "ContentFlux2Klein"
$MacPrivateIPv4 = "<your-mac-rfc1918-ipv4>"
& "$InstallRoot\package\Register-WorkerTask.ps1" `
  -InstallRoot $InstallRoot `
  -Flux2StateRoot $Flux2StateRoot `
  -MacIPAddress $MacPrivateIPv4
```

Registration first builds and validates a fresh Task Scheduler 2.0 definition
with an explicitly empty trigger collection. If an older same-name task has an
automatic trigger, registration quarantines it in the disabled state before the
long GPU proof; a failed proof deliberately leaves that unsafe old task disabled.
It then reruns the full execution proof before changing the firewall or replacing
the task. If it reports a conflicting TCP/22 rule, inspect it with
`Get-NetFirewallRule` and make the intended administrative change yourself; the
script accepts an existing rule only when it is exactly TCP/22 from the declared
Mac IPv4 address, and it will not weaken or disable unrelated access policy. The
replacement uses `CREATE_OR_UPDATE | IGNORE_REGISTRATION_TRIGGERS`, and
registration accepts it only after the installed COM definition, ScheduledTasks
CIM object, and exported XML all prove zero triggers, zero restart-on-failure,
one exact action, the current-user SID, interactive-token least privilege,
`IgnoreNew`, and unlimited supervisor execution time. On a later failure the
prior task is restored disabled, never re-enabled automatically, and its recovery
XML is retained. Every execution must therefore be explicitly admitted through
the GPU-idle start control. The readiness sentinel is removed whenever either
child process exits.

## Restricted launch control for the Mac UI

The Setup UI can start the registered task, but it must not expose a general
administrator SSH session. Generate the dedicated key at the exact path the Mac
backend requires:

```bash
ssh-keygen -t ed25519 -N '' \
  -C content-worker-control \
  -f ~/.ssh/content_gpu_control_ed25519
chmod 600 ~/.ssh/content_gpu_control_ed25519
```

Keep the existing Mac tunnel connected. Copy this package's
`Control-Worker.ps1` and `Install-WorkerControl.ps1` to one temporary Windows
directory, then run the installer from a **local elevated PowerShell** so its
intentional sshd restart cannot terminate the installer itself:

```powershell
$MacPrivateIPv4 = "<your-mac-rfc1918-ipv4>"
& .\Install-WorkerControl.ps1 `
  -MacIPAddress $MacPrivateIPv4 `
  -TunnelPublicKey "ssh-ed25519 <existing-tunnel-public-key>" `
  -ControlPublicKey (Get-Content .\content_gpu_control_ed25519.pub -Raw) `
  -InstallRoot "D:\ContentLivePortraitWorker" `
  -Flux2StateRoot "D:\ContentFlux2Klein"
```

The `.pub` file in that example is a transferred copy of
`~/.ssh/content_gpu_control_ed25519.pub`; the private key never leaves the Mac.
The installer preserves unrelated authorized keys, removes any prior entries
using the two reserved Content markers, and installs the new keys idempotently.
It installs the forced command under `%ProgramData%\ContentWorkerControl`,
rejects reparse points, applies and verifies an exact SYSTEM/Administrators
owner and DACL, stages the critical files beside their destinations, and rolls
back an atomic replacement if validation or restart fails. Narrowing the
`%ProgramData%\ssh`, config, key-file, and control-path ACLs is intentional
one-way hardening: a later validation failure does not restore broader local
write or delete authority. If rollback itself is incomplete, every remaining
recovery file is preserved and named in the error instead of being deleted.

The same protected directory contains an exact launch contract: task name and
root path, absolute executable, arguments, working directory, current-user SID,
least-privilege scheduling settings, and the installed `Start-Worker.ps1`
SHA-256. Every remote `status` and `start` revalidates that contract against the
live COM definition and its XML, then invokes the already-verified COM task
object. A same-name task, changed action, changed supervisor byte, automatic
trigger, retry policy, or broader principal therefore fails closed instead of
being launched by the restricted Mac key.

The installer also places a source-address-bound `Match User` block before the
Windows sshd configuration. It validates the effective policy with `sshd -T`:
TCP forwarding is local-direction only, its sole destination is
`127.0.0.1:8189`, stream-local forwarding is disabled, and remote forwarding is
therefore unavailable. This boundary applies to every SSH key for the same
Windows user arriving from the declared Mac address. The tunnel key is then
forced to a no-op session command. The control key has forwarding, PTY, agent,
X11, and user-rc access disabled and can request only exact `status` or `start`
actions. `start` is fixed to `Content LivePortrait Worker`, refuses a busy GPU,
and never accepts a host, task, path, or command from the browser.

Installation terminates all existing sshd sessions and restarts the service so
an older authenticated session cannot retain broader key options. The Windows
installer proves the static service, ACL, key-file, and effective sshd contracts,
but deliberately does not mistake a TCP socket for authenticated SSH. Before
accepting the deployment, invoke `status` from the Mac with the dedicated control
private key, start the fixed task through the application control route, and
verify the authenticated `127.0.0.1:18189` role-readiness response. Those external
checks prove both new key authentication and the reconnected local tunnel.

There is intentionally no remote Stop control. Stopping a task after ComfyUI
accepted a prompt can turn paid/GPU work into an ambiguous `UNKNOWN` outcome.
A future Stop action needs admission drain, queue-idle proof, and explicit
recovery semantics first.

After its startup execution proof, the persistent worker asks ComfyUI to unload
models and release cached memory. This keeps idle VRAM low while other desktop
work is active; the first real job reloads the models and remains queue-serialized.

This pinned Windows profile starts ComfyUI with `--disable-dynamic-vram`. The
default comfy-aimdo hook produced a native access violation while the pinned
LivePortrait node moved its model to the RTX 5070 Ti, even though an immediately
preceding one-frame proof had passed. Disabling the hook retains ComfyUI's
estimate-based loader and leaves async offload available. The schema-3 benchmark
and its clean-restart execution proof must be rerun after this compatibility
change; their package binding includes the exact worker supervisor hash. The
profile also gives ComfyUI an explicit SQLite URL under the runtime-owned `user`
directory so startup does not fall back to an unwritable source-tree database.

## Readiness schema

`/health/live` proves only that the gateway process is listening. A successful
`/health/ready` response is structurally and cryptographically role-bound:

```json
{
  "status": "ready",
  "role": "performance-liveportrait",
  "startup_ready": true,
  "execution_proven": true,
  "checked_at_unix": 0,
  "workflow_sha256": "<64 lowercase hex>",
  "model_manifest_sha256": "<64 lowercase hex>",
  "revisions_manifest_sha256": "<64 lowercase hex>",
  "contract_digest": "<64 lowercase hex>",
  "execution_canary_state": "passed"
}
```

The contract digest is SHA-256 over canonical compact JSON containing exactly
`model_manifest_sha256`, `revisions_manifest_sha256`, `role`, and
`workflow_sha256`, with keys sorted. The gateway independently hashes its active
files and rejects a stale or altered sentinel. A 503 response uses
`status=not_ready`, the fixed role, and both readiness booleans set to false.
Only non-secret role/status/hashes are returned.

`/health/live` and `/health/ready` remain backward-compatible and intentionally
public for process orchestration. They are not authority to share this endpoint
with the image role. The bearer-protected `GET /api/capabilities/ready` route is
the only shared-worker admission record. When the FLUX.2 state root is absent
or the candidate has not been installed, it returns:

```json
{
  "schema_version": 1,
  "status": "partial",
  "capabilities": {
    "performance-liveportrait": {
      "role": "performance-liveportrait",
      "status": "ready",
      "startup_ready": true,
      "execution_proven": true,
      "execution_canary_state": "passed",
      "workflow_sha256": "<64 lowercase hex>",
      "model_manifest_sha256": "<64 lowercase hex>",
      "revisions_manifest_sha256": "<64 lowercase hex>",
      "contract_digest": "<64 lowercase hex>"
    },
    "image-flux2-klein": {
      "capability": "image-flux2-klein",
      "state": "not_installed",
      "startup_ready": false,
      "execution_proven": false,
      "benchmark_state": "not_run",
      "blocker_code": "candidate_artifacts_not_installed",
      "artifacts_installed": false,
      "runtime_contract_sha256": "",
      "license_review_state": "official_sources_selected_derivation_pending",
      "execution_canary_state": "not_run",
      "execution_canary_sha256": "",
      "benchmark_sha256": "",
      "candidate_manifest_sha256": "<exact reviewed hash>",
      "workflow_sha256": "<exact reviewed hash>",
      "model_manifest_sha256": "<exact reviewed hash>",
      "revisions_manifest_sha256": "<exact reviewed hash>",
      "contract_digest": "<exact reviewed hash>"
    }
  }
}
```

The image record is deliberately not an installation or readiness claim. This
package does not install the FLUX.2 model artifacts, and changing the state
cannot promote it: Ready requires the exact candidate hashes, successful fixed
execution proof, approved license evidence, and a passed benchmark. The Mac
accepts one endpoint identity for both configured
roles only when both roles use the same bearer credential and this authenticated
record validates exactly. The public `/health/ready` endpoint remains bound to
the LivePortrait role; shared admission uses the authenticated capability route.

## Cross-capability queue boundary

This deployment has one ComfyUI process and therefore one serialized execution
queue. Both the FLUX.2 caller in `phase_c_assembly.py` and the LivePortrait
caller in `performance/live_portrait.py` bind each accepted prompt ID to the
durable project attempt ledger through completion and download. Uploaded-input
retention still requires the reviewed operator cleanup described above.
Ambiguous submissions remain recoverable and never trigger an automatic
replacement job. Full-project admission is independently serialized by the
durable pipeline queue; increasing its configured concurrency does not bypass
the worker's one-queue execution boundary.

The profile is one worker and one ComfyUI queue. The accepted schema-3
2026-08-06 run
completed one warm-up plus ten sequential 8-second/200-frame jobs, decoded every
output, and passed clean-restart recovery. It measured 33.6689 seconds mean and
33.8001 seconds inclusive p95 latency, with 3,978 MiB peak VRAM and
6,301,261,824 bytes peak worker RSS. The worker-RSS sampler was bound to the
exact ComfyUI descendant of the supervisor and recorded a nonzero
2,412,048,384-byte baseline. Its 1,221 samples had a 0.359-second maximum
observed interval. Those measurements establish the supported
single-job envelope; they do not authorize parallel GPU jobs on the 16 GB card.
The raw evidence uses schema version 3 and its normalized summary uses schema
version 2. Both bind the benchmark launcher, launch supervisor, preflight
instrument, benchmark/normalizer programs, manifests, lock, probe contract, and
workflow by SHA-256.

Run that guarded benchmark only while the GPU is reserved for this worker:

```powershell
$InstallRoot = "D:\ContentLivePortraitWorker" # reuse the exact install identity
& "$InstallRoot\package\Benchmark-Worker.ps1" -InstallRoot $InstallRoot
```

It binds `Benchmark-Worker.ps1`, `Start-Worker.ps1`, `preflight.py`, the
benchmark and normalizer programs, manifests, lock, probe contract, and workflow
by SHA-256. It starts ComfyUI with `--cache-none`, then runs one unmeasured warm-up followed
by ten sequential 200-frame jobs at 25 fps (the 8-second production cap) so the warm-up cannot substitute
cached nodes for measured inference. It decodes every MP4, samples VRAM and
worker/system RAM with actual sample offsets and observed intervals, records inclusive
p50/p95 latency, cleans generated media, and then performs a fresh supervisor
restart plus one-frame execution proof. Its durable result is
`state\benchmark.json`; the same command validates and writes the deterministic
`state\benchmark.normalized.json`. Concurrency remains fixed at one regardless
of the measured headroom.

The tracked `.raw.json` is a canonical UTF-8 serialization of the transported
worker JSON. It preserves the measured JSON values but does not claim that the
Windows BOM/CRLF transport encoding was retained. Its exact committed bytes are
bound by `raw_evidence_sha256` in the normalized summary. Reproduce and verify
the tracked release evidence with the committed normalizer:

```bash
.venv/bin/python deploy/windows-liveportrait-worker/normalize_benchmark.py \
  --raw logs/worker-benchmarks/windows-liveportrait/rtx-5070-ti-2026-08-06-v3.raw.json \
  --output logs/worker-benchmarks/windows-liveportrait/rtx-5070-ti-2026-08-06-v3.summary.json
.venv/bin/python deploy/windows-liveportrait-worker/normalize_benchmark.py \
  --raw logs/worker-benchmarks/windows-liveportrait/rtx-5070-ti-2026-08-06-v3.raw.json \
  --output logs/worker-benchmarks/windows-liveportrait/rtx-5070-ti-2026-08-06-v3.summary.json \
  --check
```

The `2026-08-06-v3` pair is the accepted production-envelope record. Superseded
test and pre-schema-3 records were removed during the fresh-start cleanup so
they cannot be mistaken for current release evidence.
