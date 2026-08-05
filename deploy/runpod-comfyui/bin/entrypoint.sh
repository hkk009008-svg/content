#!/usr/bin/env bash
# Production entrypoint.  The development/E2E bootstrap remains separate at
# scripts/setup_runpod.sh and is never invoked from this image.

set -Eeuo pipefail
umask 027

readonly DEPLOY_ROOT="/opt/content/deployment"
readonly MODEL_ROOT="/workspace/models"
readonly WORKSPACE="/workspace"
readonly RUNTIME_DIR="/run/content"
readonly COMFYUI_TOKEN="${COMFYUI_API_KEY:-}"

if [[ "${COMFYUI_TOKEN,,}" == bearer\ * ]]; then
  echo "FATAL: COMFYUI_API_KEY must contain only the token, without the Bearer prefix." >&2
  exit 2
fi
if (( ${#COMFYUI_TOKEN} < 32 )); then
  echo "FATAL: COMFYUI_API_KEY must be supplied as a RunPod Secret and be at least 32 characters." >&2
  exit 2
fi

mkdir -p "$RUNTIME_DIR" "$MODEL_ROOT"

case "${RUNPOD_FETCH_MODELS:-1}" in
  1)
    /opt/content-venv/bin/python "$DEPLOY_ROOT/bin/model_artifacts.py" \
      --manifest "$DEPLOY_ROOT/models.json" \
      --model-root "$MODEL_ROOT" \
      --download
    ;;
  0)
    /opt/content-venv/bin/python "$DEPLOY_ROOT/bin/model_artifacts.py" \
      --manifest "$DEPLOY_ROOT/models.json" \
      --model-root "$MODEL_ROOT" \
      --check-only
    ;;
  *)
    echo "FATAL: RUNPOD_FETCH_MODELS must be 0 or 1." >&2
    exit 2
    ;;
esac

/opt/content-venv/bin/python "$DEPLOY_ROOT/bin/preflight.py" \
  --revisions "$DEPLOY_ROOT/revisions.json" \
  --models "$DEPLOY_ROOT/models.json" \
  --workflow /opt/content/pulid.json \
  --model-root "$MODEL_ROOT" \
  --workspace "$WORKSPACE" \
  --extra-model-paths "$RUNTIME_DIR/extra_model_paths.yaml"

exec /opt/content-venv/bin/supervisord -n -c "$DEPLOY_ROOT/supervisord.conf"
