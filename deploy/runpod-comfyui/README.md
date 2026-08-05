# Immutable RunPod ComfyUI image

This directory is the production deployment path for the repository's active
`pulid.json` image-fallback graph. It is separate from
`scripts/setup_runpod.sh`, which remains a mutable development/E2E bootstrap.

The image contract is intentionally narrow. It includes ComfyUI and the two
pinned PuLID node repositories needed by `pulid.json`. It does **not** claim to
provide LivePortrait or SadTalker; those paths need their own compatible,
model-manifested image before they can be advertised as production-capable.

## Security and immutability contract

- The PyTorch/CUDA base uses an image digest. PyTorch 2.6.0,
  torchvision 0.21.0, torchaudio 2.6.0 and CUDA 12.4 are checked at build and
  startup. There is no post-install torch mutation.
- ComfyUI and every custom node are checked out at the full SHAs in
  `revisions.json`. Startup rejects a different commit or tracked-file drift.
- Python packages are installed from `requirements.lock` with exact versions,
  hashes, `--no-deps`, and then `pip check`. The base image owns the omitted
  torch/CUDA packages.
- Large models stay on the `/workspace` network volume. `models.json` records
  each pinned source revision, license metadata, exact byte count, SHA-256 and
  destination. Downloads use an atomic temporary file and never overwrite a
  mismatched existing artifact. Missing metadata, missing models and checksum
  failures are fatal.
- Supervisor owns both processes. ComfyUI listens only on
  `127.0.0.1:8188`; the bearer-authenticated gateway listens on `:8189` and
  proxies both HTTP and `/ws`. The gateway refuses all ComfyUI traffic until
  source, dependency, storage, GPU, model, node-class, model-choice and
  zero-provider-cost execution-canary checks pass.
- Only `8189` is declared for exposure. Never publish raw port `8188`.

The FLUX and InsightFace artifacts include restrictive or distributor-undeclared
license notes in `models.json`. Deployment approval must include a human review
of those upstream terms; checksums prove bytes, not usage rights.

## Build and promote

Build from the repository root on an amd64 builder. Do not use or promote a
mutable tag as the RunPod template authority:

```bash
IMAGE=registry.example/content-comfyui
VERSION=<source-commit-or-release>

docker buildx build \
  --platform linux/amd64 \
  --file deploy/runpod-comfyui/Dockerfile \
  --tag "$IMAGE:$VERSION" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  .

docker buildx imagetools inspect "$IMAGE:$VERSION"
```

Record the resulting `sha256:...` manifest digest in the release evidence and
configure the RunPod template as `registry.example/content-comfyui@sha256:...`.
The Dockerfile-specific ignore file prevents the rest of the repository,
including `.env` and runtime projects, from entering the build context.

Regenerate the Python lock only as a reviewed dependency change:

```bash
./deploy/runpod-comfyui/lock_requirements.sh
env -u GIT_INDEX_FILE git diff --exit-code -- deploy/runpod-comfyui/requirements.lock
```

The second command is the CI freshness check after regeneration. Review the
resolved-version diff and rebuild/scan before promotion.

## RunPod template

Use an 80 GB or larger network volume mounted at `/workspace`. The image runs as
UID/GID `10001`; the mounted volume must be writable by that identity. Configure
the host for CUDA 12.4-compatible NVIDIA drivers.

Set these environment variables:

| Variable | Value |
|---|---|
| `COMFYUI_API_KEY` | A random token of at least 32 characters, injected from a RunPod Secret; token only, without the `Bearer` prefix |
| `RUNPOD_FETCH_MODELS` | `1` to fetch any absent verified artifact, or `0` to require a fully populated volume |

Create the secret in RunPod and map it in the template rather than placing it in
the image or template text, for example
`COMFYUI_API_KEY={{ RUNPOD_SECRET_comfyui_api_key }}`. RunPod documents the
secret-reference syntax in its [Secrets guide](https://docs.runpod.io/pods/templates/secrets).

Recommended networking is [RunPod global networking](https://docs.runpod.io/pods/networking):
do not expose any HTTP/TCP port, and configure the calling Content service with
`COMFYUI_SERVER_URL=http://<pod-id>.runpod.internal:8189` plus the same
`COMFYUI_API_KEY`. Authentication remains mandatory on the private network.

If a public endpoint is unavoidable, expose **only** `8189/http` and use
`https://<pod-id>-8189.proxy.runpod.net`. RunPod states that proxy ports are
public and applications must implement authentication; it also documents a
100-second proxy limit, so WebSocket reconnect/history fallback remains
important. See [Expose ports](https://docs.runpod.io/pods/configuration/expose-ports).

## Health and startup behavior

Health endpoints reveal no model or queue data and intentionally do not require
the bearer token:

```bash
curl --fail --silent --show-error http://127.0.0.1:8189/health/live
curl --fail --silent --show-error http://127.0.0.1:8189/health/ready
```

- `GET /health/live` returns HTTP 200 with `{"status":"live"}` when the
  gateway process is running.
- `GET /health/ready` returns HTTP 200 with `status=ready` only after the full
  startup contract and execution canary pass. It returns HTTP 503 with
  `status=not_ready` otherwise.

Use readiness, not liveness, for traffic admission. All other paths require
`Authorization: Bearer <COMFYUI_API_KEY>`. A missing node/model, failed `pip
check`, unavailable CUDA device or failed canary prevents readiness and causes
the supervised backend to exit; the container then exits for platform-level
restart rather than serving a degraded graph.

## SBOM and vulnerability gates

Run both an SBOM generator and an independent vulnerability scanner against the
**promoted digest**, not only the source tree:

```bash
IMAGE_REF=registry.example/content-comfyui@sha256:<digest>

syft "$IMAGE_REF" -o cyclonedx-json=content-comfyui.cdx.json
grype "$IMAGE_REF" --fail-on high
trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "$IMAGE_REF"
```

Store `content-comfyui.cdx.json`, scanner versions and scanner output with the
release evidence. A finding should be fixed or carried by an explicit,
time-bounded exception that records package, CVE, reachability, owner and expiry.
Do not silently filter fixed vulnerabilities.

CI should run the focused deployment tests and lock freshness check on every
change to `deploy/runpod-comfyui/**` or `pulid.json`; build the image on amd64;
produce the SBOM; and fail on unexcepted high/critical Grype or Trivy findings.
The image should be pushed and promoted by digest only from a protected release
job, never from an untrusted pull-request context.
