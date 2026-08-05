#!/usr/bin/env bash
set -Eeuo pipefail

readonly DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

uv pip compile "$DEPLOY_DIR/requirements.in" \
  --custom-compile-command './deploy/runpod-comfyui/lock_requirements.sh' \
  --python-version 3.11 \
  --python-platform x86_64-unknown-linux-gnu \
  --generate-hashes \
  --no-emit-package torch \
  --no-emit-package torchvision \
  --no-emit-package torchaudio \
  --no-emit-package nvidia-cublas-cu12 \
  --no-emit-package nvidia-cuda-cupti-cu12 \
  --no-emit-package nvidia-cuda-nvrtc-cu12 \
  --no-emit-package nvidia-cuda-runtime-cu12 \
  --no-emit-package nvidia-cudnn-cu12 \
  --no-emit-package nvidia-cufft-cu12 \
  --no-emit-package nvidia-curand-cu12 \
  --no-emit-package nvidia-cusolver-cu12 \
  --no-emit-package nvidia-cusparse-cu12 \
  --no-emit-package nvidia-cusparselt-cu12 \
  --no-emit-package nvidia-nccl-cu12 \
  --no-emit-package nvidia-nvjitlink-cu12 \
  --no-emit-package nvidia-nvtx-cu12 \
  --no-emit-package triton \
  --output-file "$DEPLOY_DIR/requirements.lock"
