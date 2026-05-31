#!/bin/bash
# ---------------------------------------------------------------------------
# RunPod E2E Test Environment Setup
# ---------------------------------------------------------------------------
# This script configures a RunPod GPU pod for running the cinema pipeline
# end-to-end tests. Run it once after launching a new pod.
#
# Prerequisites:
#   - RunPod GPU pod (RTX 4090 / A100 recommended, minimum 24GB VRAM)
#   - Ubuntu 22.04+ base image with NVIDIA drivers (any recent RunPod/Novita
#     PyTorch image works; step 5 reinstalls a torch/torchvision/torchaudio stack
#     matched to the pod driver's max CUDA, detected via nvidia-smi)
#   - .env file with API keys (see .env.example)
#
# Usage:
#   bash scripts/setup_runpod.sh
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMFYUI_DIR="/workspace/ComfyUI"
COMFYUI_PORT=8188

echo "============================================"
echo " RunPod E2E Environment Setup"
echo "============================================"

# ------------------------------------------------------------------
# 1. System dependencies
# ------------------------------------------------------------------
echo ""
echo "[1/6] Installing system dependencies..."
apt-get update -qq && apt-get install -y -qq \
    ffmpeg \
    imagemagick \
    libgl1-mesa-glx \
    libglib2.0-0 \
    wget \
    git \
    unzip \
    jq \
    > /dev/null 2>&1
echo "  Done."

# ------------------------------------------------------------------
# 2. Install ComfyUI + required custom nodes
# ------------------------------------------------------------------
echo ""
echo "[2/6] Setting up ComfyUI..."

if [ ! -d "$COMFYUI_DIR" ]; then
    git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFYUI_DIR"
    pip install -r "$COMFYUI_DIR/requirements.txt" -q
else
    echo "  ComfyUI already installed at $COMFYUI_DIR"
fi

# Custom nodes — use tarball download (avoids git credential issues on pods)
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"
mkdir -p "$CUSTOM_NODES_DIR"

# Clean up any stale partial clones from previous failed attempts
rm -rf "$CUSTOM_NODES_DIR/comfyui-reactor-node" 2>/dev/null

declare -A CUSTOM_NODES=(
    ["ComfyUI-PuLID"]="https://github.com/cubiq/PuLID_ComfyUI/archive/refs/heads/main.tar.gz"
    ["ComfyUI_IPAdapter_plus"]="https://github.com/cubiq/ComfyUI_IPAdapter_plus/archive/refs/heads/main.tar.gz"
    ["ComfyUI_essentials"]="https://github.com/cubiq/ComfyUI_essentials/archive/refs/heads/main.tar.gz"
    ["ComfyUI-ReActor"]="https://github.com/Gourieff/ComfyUI-ReActor/archive/refs/heads/main.tar.gz"
)

for node_name in "${!CUSTOM_NODES[@]}"; do
    node_path="$CUSTOM_NODES_DIR/$node_name"
    if [ ! -d "$node_path" ]; then
        echo "  Installing $node_name..."
        mkdir -p "$node_path"
        if curl -sL "${CUSTOM_NODES[$node_name]}" | tar xz --strip-components=1 -C "$node_path"; then
            if [ -f "$node_path/requirements.txt" ]; then
                pip install -r "$node_path/requirements.txt" -q
            fi
        else
            echo "  ERROR: Failed to download $node_name"
            rm -rf "$node_path"
        fi
    else
        echo "  $node_name already installed."
    fi
done

# ComfyUI-PuLID-Flux (balazik) — provides ApplyPulidFlux / PulidFluxModelLoader /
# PulidFluxEvaClipLoader for the max-tier workflow (pulid_max.json). git clone to
# match the brief v2.0 §11.1 manual one-liner. Closes C-D4 / A10 step 2.
PULID_FLUX_DIR="$CUSTOM_NODES_DIR/ComfyUI-PuLID-Flux"
if [ ! -d "$PULID_FLUX_DIR" ]; then
    echo "  Installing ComfyUI-PuLID-Flux (balazik)..."
    if git clone --depth 1 https://github.com/balazik/ComfyUI-PuLID-Flux "$PULID_FLUX_DIR"; then
        if [ -f "$PULID_FLUX_DIR/requirements.txt" ]; then
            pip install -r "$PULID_FLUX_DIR/requirements.txt" -q || true
        fi
    else
        echo "  ERROR: failed to clone ComfyUI-PuLID-Flux; max-tier PuLID-FLUX unavailable."
        rm -rf "$PULID_FLUX_DIR"
    fi
else
    echo "  ComfyUI-PuLID-Flux already installed."
fi

# InsightFace runtime stack — REQUIRED for BOTH PuLID node packs to import at all.
# cubiq's ComfyUI-PuLID registers PulidInsightFaceLoader; balazik's ComfyUI-PuLID-Flux
# registers PulidFluxInsightFaceLoader + ApplyPulidFlux. Either pack's import fails
# without insightface/onnxruntime present, and ComfyUI then silently drops EVERY node
# in that pack — the exact C-B1/C-D4 cascade. Install explicitly rather than rely on
# each pack's -q requirements.txt (which can fail silently). onnxruntime-gpu suits the
# pod GPU; swap to onnxruntime if a CUDA mismatch surfaces. Closes the C-D4 root.
echo "  Installing InsightFace stack (insightface, onnxruntime-gpu, facexlib)..."
pip install -q insightface onnxruntime-gpu facexlib || \
    echo "  WARNING: InsightFace stack install failed — PulidInsightFaceLoader will NOT register. Resolve on-pod."

echo "  Done."

# ------------------------------------------------------------------
# 3. Download required models
# ------------------------------------------------------------------
echo ""
echo "[3/6] Downloading models (this may take a while)..."

MODELS_DIR="$COMFYUI_DIR/models"
mkdir -p "$MODELS_DIR"/{checkpoints,clip,vae,pulid,upscale_models,diffusion_models}

# FLUX1 dev FP8
if [ ! -f "$MODELS_DIR/checkpoints/FLUX1/flux1-dev-fp8.safetensors" ]; then
    mkdir -p "$MODELS_DIR/checkpoints/FLUX1"
    echo "  Downloading FLUX1 dev FP8..."
    wget -q --show-progress -O "$MODELS_DIR/checkpoints/FLUX1/flux1-dev-fp8.safetensors" \
        "https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-dev-fp8.safetensors"
fi

# Symlink FLUX UNet for UNETLoader (pulid.json + pulid_max.json reference it).
# ComfyUI's UNETLoader reads from models/diffusion_models/, distinct from
# CheckpointLoaderSimple which reads models/checkpoints/. Without this symlink,
# workflows reject with `unet_name: 'FLUX1/flux1-dev-fp8.safetensors' not in []`
# and the pipeline falls back to FAL FLUX-Pro WITHOUT PuLID identity anchoring.
# Closes C-B1 surfaced in Tier B Korean dialogue probe 2026-05-27 (a42a6af).
mkdir -p "$MODELS_DIR/diffusion_models/FLUX1"
if [ ! -e "$MODELS_DIR/diffusion_models/FLUX1/flux1-dev-fp8.safetensors" ]; then
    ln -sf "$MODELS_DIR/checkpoints/FLUX1/flux1-dev-fp8.safetensors" \
           "$MODELS_DIR/diffusion_models/FLUX1/flux1-dev-fp8.safetensors"
    echo "  Symlinked FLUX1/flux1-dev-fp8.safetensors into diffusion_models/ for UNETLoader."
fi

# CLIP models
if [ ! -f "$MODELS_DIR/clip/t5xxl_fp8_e4m3fn.safetensors" ]; then
    echo "  Downloading T5-XXL FP8..."
    wget -q --show-progress -O "$MODELS_DIR/clip/t5xxl_fp8_e4m3fn.safetensors" \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
fi

if [ ! -f "$MODELS_DIR/clip/clip_l.safetensors" ]; then
    echo "  Downloading CLIP-L..."
    wget -q --show-progress -O "$MODELS_DIR/clip/clip_l.safetensors" \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
fi

# VAE — the FLUX autoencoder. black-forest-labs/FLUX.1-{dev,schnell} are BOTH
# gated (HTTP 401 token-free), which hard-failed this wget under `set -e` and
# aborted the whole script before pulid/launch. ffxvs/vae-flux is a public
# mirror of the identical ae.safetensors (335304388 bytes).
if [ ! -f "$MODELS_DIR/vae/ae.safetensors" ]; then
    echo "  Downloading FLUX VAE..."
    wget -q --show-progress -O "$MODELS_DIR/vae/ae.safetensors" \
        "https://huggingface.co/ffxvs/vae-flux/resolve/main/ae.safetensors"
fi

# PuLID
if [ ! -f "$MODELS_DIR/pulid/ip-adapter_pulid_sdxl_fp16.safetensors" ]; then
    echo "  Downloading PuLID IP-Adapter..."
    wget -q --show-progress -O "$MODELS_DIR/pulid/ip-adapter_pulid_sdxl_fp16.safetensors" \
        "https://huggingface.co/huchenlei/ipadapter_pulid/resolve/main/ip-adapter_pulid_sdxl_fp16.safetensors"
fi

# PuLID-Flux model (pulid_max.json references pulid_flux_v0.9.1.safetensors).
# Source: official PuLID author repo (guozinan/PuLID).
if [ ! -f "$MODELS_DIR/pulid/pulid_flux_v0.9.1.safetensors" ]; then
    echo "  Downloading PuLID-Flux v0.9.1..."
    wget -q --show-progress -O "$MODELS_DIR/pulid/pulid_flux_v0.9.1.safetensors" \
        "https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.1.safetensors" \
        || echo "  WARNING: PuLID-Flux model download failed — install into models/pulid/ manually."
fi

# antelopev2 InsightFace model (C-D4 / A10 step 3). PulidInsightFaceLoader loads
# it via insightface FaceAnalysis(name="antelopev2", root=models/insightface),
# which resolves to models/insightface/models/antelopev2/ — note the nested
# models/. The brief §11.1/A10 shorthand "models/insightface/antelopev2/" omits
# it; we populate the insightface-canonical path AND symlink the brief's path so
# the A10 probe `ls models/insightface/antelopev2/*.onnx` also resolves.
ANTELOPE_CANON="$MODELS_DIR/insightface/models/antelopev2"
ANTELOPE_PROBE="$MODELS_DIR/insightface/antelopev2"
if [ ! -f "$ANTELOPE_CANON/glintr100.onnx" ]; then
    echo "  Downloading antelopev2 InsightFace model..."
    mkdir -p "$ANTELOPE_CANON"
    rm -rf /tmp/antelope_dl && mkdir -p /tmp/antelope_dl
    if curl -sfL "https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip" \
            -o /tmp/antelope_dl/antelopev2.zip \
        && unzip -q -o /tmp/antelope_dl/antelopev2.zip -d /tmp/antelope_dl; then
        find /tmp/antelope_dl -name '*.onnx' -exec mv -t "$ANTELOPE_CANON/" {} + 2>/dev/null || true
    fi
    if [ ! -f "$ANTELOPE_CANON/glintr100.onnx" ]; then
        echo "  WARNING: antelopev2 auto-download failed or changed layout. MANUAL STEP —"
        echo "    place these 5 files into $ANTELOPE_CANON/ :"
        echo "    1k3d68.onnx 2d106det.onnx genderage.onnx glintr100.onnx scrfd_10g_bnkps.onnx"
        echo "    (verify the source on-pod where you have shell access — Q6.)"
    fi
fi
mkdir -p "$MODELS_DIR/insightface"
if [ ! -e "$ANTELOPE_PROBE" ]; then
    ln -sf "$ANTELOPE_CANON" "$ANTELOPE_PROBE"
fi

# Real-ESRGAN upscaler
if [ ! -f "$MODELS_DIR/upscale_models/RealESRGAN_x4plus.pth" ]; then
    echo "  Downloading Real-ESRGAN 4x..."
    wget -q --show-progress -O "$MODELS_DIR/upscale_models/RealESRGAN_x4plus.pth" \
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
fi

echo "  Done."

# ------------------------------------------------------------------
# 4. Load environment variables
# ------------------------------------------------------------------
echo ""
echo "[4/6] Loading environment variables..."

ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
    echo "  Loaded from $ENV_FILE"
else
    echo "  WARNING: No .env file found at $ENV_FILE"
    echo "  Copy .env.example and fill in your API keys:"
    echo "    cp $PROJECT_ROOT/.env.example $ENV_FILE"
fi

# Set ComfyUI URL to local instance
export COMFYUI_SERVER_URL="http://127.0.0.1:${COMFYUI_PORT}"
echo "  COMFYUI_SERVER_URL=$COMFYUI_SERVER_URL"

echo "  Done."

# ------------------------------------------------------------------
# 5. Install Python test dependencies
# ------------------------------------------------------------------
echo ""
echo "[5/6] Installing Python dependencies..."

pip install -q \
    pytest \
    numpy \
    Pillow \
    requests \
    python-dotenv \
    openai \
    moviepy==1.0.3 \
    whisper

# blinker is often pre-installed via distutils on RunPod base images, which
# blocks pip from upgrading deps that require a newer blinker. --ignore-installed
# clears the conflict (cycle-15 manual hardening step 4; A10).
pip install -q --ignore-installed blinker || true

# Install project-specific deps if requirements.txt exists
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    pip install -q -r "$PROJECT_ROOT/requirements.txt"
fi

# Pin a MATCHED torch stack as the FINAL word on these versions. ComfyUI hard-imports
# torchaudio at startup (comfy/sd.py -> ldm/lightricks audio_vae), and torchaudio lags
# torch, so an unpinned torch resolved above (by ComfyUI's or the project's
# requirements) can leave torch+torchaudio ABI-mismatched ->
# "undefined symbol ..._ZNK5torch8autograd4Node4nameEv" and ComfyUI fails to start.
# So install torch/torchvision/torchaudio together as ONE matched set per channel,
# overriding whatever the requirements above resolved (the ABI lesson from 3fe8299).
#
# WHICH set depends on the HOST DRIVER's max CUDA: a cuXYZ wheel only uses the GPU if
# the driver supports CUDA >= X.Y. cu130 wheels need a CUDA-13.0 driver; common
# Novita/RunPod hosts cap at CUDA 12.4 (e.g. driver 550.x on an RTX 6000 Ada), where
# cu130 silently can't see the GPU. So read the driver's max CUDA from nvidia-smi's
# "CUDA Version: X.Y" header and pick the matched channel + version set.
DRIVER_CUDA=""
if command -v nvidia-smi >/dev/null 2>&1; then
    DRIVER_CUDA="$(nvidia-smi 2>/dev/null \
        | sed -n 's/.*CUDA Version: \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' \
        | head -n1 || true)"
fi

# Encode "X.Y" as X*100+Y for an integer compare that stays safe under `set -u`
# (10# forces base-10 so a value like "12.08" isn't read as octal).
if [[ "$DRIVER_CUDA" =~ ^[0-9]+\.[0-9]+$ ]]; then
    CUDA_NUM=$((10#${DRIVER_CUDA%%.*} * 100 + 10#${DRIVER_CUDA#*.}))
else
    CUDA_NUM=0
fi

if [ "$CUDA_NUM" -ge 1300 ]; then
    TORCH_PKGS="torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0"  # verified H100 sm_90
    TORCH_CHANNEL="cu130"
elif [ "$CUDA_NUM" -ge 1204 ]; then
    TORCH_PKGS="torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0"    # verified RTX 6000 Ada
    TORCH_CHANNEL="cu124"
elif [ "$CUDA_NUM" -ge 1108 ]; then
    TORCH_PKGS="torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1"
    TORCH_CHANNEL="cu118"
else
    # nvidia-smi absent/unparseable, or a driver older than CUDA 11.8. Default to
    # cu124 (broadest modern-pod fit; the set verified on RTX 6000 Ada / H100). If
    # ComfyUI then fails with a torch/CUDA error, override the pin manually -- see
    # OPERATIONS.md §5.
    echo "  WARN: no CUDA >= 11.8 driver detected (nvidia-smi reported '${DRIVER_CUDA:-none}')."
    echo "        Defaulting to cu124; override the pin manually if ComfyUI hits a CUDA error."
    TORCH_PKGS="torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0"
    TORCH_CHANNEL="cu124"
fi

echo "  Driver max CUDA: ${DRIVER_CUDA:-unknown} -> installing matched torch stack (${TORCH_CHANNEL})."
# shellcheck disable=SC2086  # word-split $TORCH_PKGS into separate pip args (intended)
pip install -q $TORCH_PKGS \
    --index-url "https://download.pytorch.org/whl/${TORCH_CHANNEL}"

echo "  Done."

# ------------------------------------------------------------------
# 6. Start ComfyUI in background
# ------------------------------------------------------------------
echo ""
echo "[6/6] Starting ComfyUI server..."

COMFYUI_LOG="/workspace/comfyui.log"

# If ComfyUI is already running, RESTART it — a live instance loaded its node set
# at its own start, BEFORE this run's custom-node installs, so it will not serve the
# newly-installed PuLID nodes and the /object_info probe below would false-negative
# (Lane V #14 F2). On a fresh/restarted pod nothing is running and this is a no-op.
if curl -s "http://127.0.0.1:${COMFYUI_PORT}/system_stats" > /dev/null 2>&1; then
    echo "  ComfyUI already running — restarting to load newly-installed nodes..."
    pkill -f "main.py.*--port ${COMFYUI_PORT}" 2>/dev/null || true
    for i in $(seq 1 15); do
        curl -s "http://127.0.0.1:${COMFYUI_PORT}/system_stats" > /dev/null 2>&1 || break
        sleep 2
    done
fi

cd "$COMFYUI_DIR"
nohup python main.py --listen 0.0.0.0 --port "$COMFYUI_PORT" \
    > "$COMFYUI_LOG" 2>&1 &
COMFYUI_PID=$!
echo "  ComfyUI starting (PID: $COMFYUI_PID), log: $COMFYUI_LOG"

# Wait for ComfyUI to be ready (up to 120s)
echo "  Waiting for ComfyUI to initialize..."
for i in $(seq 1 60); do
    if curl -s "http://127.0.0.1:${COMFYUI_PORT}/system_stats" > /dev/null 2>&1; then
        echo "  ComfyUI ready after ${i}x2 seconds."
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "  ERROR: ComfyUI failed to start. Check $COMFYUI_LOG"
        exit 1
    fi
    sleep 2
done
cd "$PROJECT_ROOT"

# ------------------------------------------------------------------
# 6b. Verify PuLID node availability (closes the C-D4 silent-missing-node class)
# ------------------------------------------------------------------
# A silently-missing custom node was the root of both C-B1 and C-D4: a workflow
# referenced a class_type ComfyUI never registered, and nothing caught it until
# generation. Probe /object_info now, while it's cheap to act on. Mirrors brief
# v2.0 §3 A9.5.
echo ""
echo "[verify] Checking PuLID node availability via /object_info..."
PULID_NODES_OK=1
for node in PulidInsightFaceLoader ApplyPulidFlux; do
    if curl -s "http://127.0.0.1:${COMFYUI_PORT}/object_info/${node}" | grep -q "\"${node}\""; then
        echo "  OK: ${node} registered."
    else
        echo "  MISSING: ${node} not registered — PuLID identity path will fall back (C-D4)."
        PULID_NODES_OK=0
    fi
done
if [ "$PULID_NODES_OK" -eq 0 ]; then
    echo "  -> Inspect $COMFYUI_LOG for custom-node import errors (usually a missing"
    echo "     insightface/onnxruntime dep or absent antelopev2 model)."
fi

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo "============================================"
echo " Setup Complete"
echo "============================================"
echo ""
echo " ComfyUI:  http://127.0.0.1:${COMFYUI_PORT}"
echo " Project:  $PROJECT_ROOT"
echo ""
echo " Run e2e tests:"
echo "   cd $PROJECT_ROOT"
echo "   COMFYUI_SERVER_URL=http://127.0.0.1:${COMFYUI_PORT} \\"
echo "     python -m pytest tests/test_e2e_quality_benchmark.py -v -m e2e"
echo ""
echo " Required API keys (set in .env or export):"
echo "   KLING_ACCESS_KEY    - Kling video generation"
echo "   FAL_KEY             - FAL.ai FLUX fallback"
echo "   LTX_API_KEY         - LTX video generation"
echo "   OPENAI_API_KEY      - Sora video generation (optional)"
echo "   GOOGLE_API_KEY      - Veo video generation (optional)"
echo "   RUNWAYML_API_SECRET - Runway Gen4 (optional)"
echo ""
echo " Minimum: ComfyUI + at least one of KLING_ACCESS_KEY, FAL_KEY, or LTX_API_KEY"
echo ""
