#!/bin/bash
# ---------------------------------------------------------------------------
# RunPod E2E Test Environment Setup
# ---------------------------------------------------------------------------
# This script configures a RunPod GPU pod for running the cinema pipeline
# end-to-end tests. Run it once after launching a new pod.
#
# Prerequisites:
#   - RunPod GPU pod (RTX 4090 / A100 recommended, minimum 24GB VRAM)
#   - Ubuntu 22.04+ base image (e.g., runpod/pytorch:2.1.0-py3.10-cuda11.8.0)
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
    ["ComfyUI-PuLID"]="https://github.com/cubiq/ComfyUI_PuLID/archive/refs/heads/main.tar.gz"
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

echo "  Done."

# ------------------------------------------------------------------
# 3. Download required models
# ------------------------------------------------------------------
echo ""
echo "[3/6] Downloading models (this may take a while)..."

MODELS_DIR="$COMFYUI_DIR/models"
mkdir -p "$MODELS_DIR"/{checkpoints,clip,vae,pulid,upscale_models}

# FLUX1 dev FP8
if [ ! -f "$MODELS_DIR/checkpoints/FLUX1/flux1-dev-fp8.safetensors" ]; then
    mkdir -p "$MODELS_DIR/checkpoints/FLUX1"
    echo "  Downloading FLUX1 dev FP8..."
    wget -q --show-progress -O "$MODELS_DIR/checkpoints/FLUX1/flux1-dev-fp8.safetensors" \
        "https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-dev-fp8.safetensors"
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

# VAE
if [ ! -f "$MODELS_DIR/vae/ae.safetensors" ]; then
    echo "  Downloading FLUX VAE..."
    wget -q --show-progress -O "$MODELS_DIR/vae/ae.safetensors" \
        "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors"
fi

# PuLID
if [ ! -f "$MODELS_DIR/pulid/ip-adapter_pulid_sdxl_fp16.safetensors" ]; then
    echo "  Downloading PuLID IP-Adapter..."
    wget -q --show-progress -O "$MODELS_DIR/pulid/ip-adapter_pulid_sdxl_fp16.safetensors" \
        "https://huggingface.co/huchenlei/ipadapter_pulid/resolve/main/ip-adapter_pulid_sdxl_fp16.safetensors"
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
    whisper \
    torch \
    torchvision

# Install project-specific deps if requirements.txt exists
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    pip install -q -r "$PROJECT_ROOT/requirements.txt"
fi

echo "  Done."

# ------------------------------------------------------------------
# 6. Start ComfyUI in background
# ------------------------------------------------------------------
echo ""
echo "[6/6] Starting ComfyUI server..."

COMFYUI_LOG="/workspace/comfyui.log"

if curl -s "http://127.0.0.1:${COMFYUI_PORT}/system_stats" > /dev/null 2>&1; then
    echo "  ComfyUI already running on port $COMFYUI_PORT"
else
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
