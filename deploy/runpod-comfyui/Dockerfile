# syntax=docker/dockerfile:1.7
# The tag is informational; the digest is the immutable authority.
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime@sha256:77f17f843507062875ce8be2a6f76aa6aa3df7f9ef1e31d9d7432f4b0f563dee

LABEL org.opencontainers.image.title="Content ComfyUI RunPod" \
      org.opencontainers.image.base.name="pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime" \
      org.opencontainers.image.base.digest="sha256:77f17f843507062875ce8be2a6f76aa6aa3df7f9ef1e31d9d7432f4b0f563dee"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    CONTENT_MODEL_ROOT=/workspace/models \
    HF_HOME=/workspace/models/.huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    COMFYUI_SERVER_URL=http://127.0.0.1:8188

# The final image digest is the deployable artifact.  These OS packages are
# captured by that digest; rebuilds must be rescanned before promotion.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        git \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version' \
    && python -m venv --system-site-packages /opt/content-venv

COPY deploy/runpod-comfyui/requirements.lock /opt/content/deployment/requirements.lock
RUN /opt/content-venv/bin/python -m pip install \
        --no-deps --require-hashes \
        -r /opt/content/deployment/requirements.lock \
    && /opt/content-venv/bin/python -m pip check \
    && /opt/content-venv/bin/python -c \
        'import torch, torchvision, torchaudio; assert torch.__version__.split("+")[0] == "2.6.0"; assert torchvision.__version__.split("+")[0] == "0.21.0"; assert torchaudio.__version__.split("+")[0] == "2.6.0"; assert str(torch.version.cuda).startswith("12.4")'

RUN set -Eeuo pipefail; \
    fetch_exact() { \
      local repository="$1" destination="$2" revision="$3"; \
      env -u GIT_INDEX_FILE git init "$destination"; \
      env -u GIT_INDEX_FILE git -C "$destination" remote add origin "$repository"; \
      env -u GIT_INDEX_FILE git -C "$destination" fetch --depth 1 origin "$revision"; \
      env -u GIT_INDEX_FILE git -C "$destination" checkout --detach FETCH_HEAD; \
      test "$(env -u GIT_INDEX_FILE git -C "$destination" rev-parse HEAD)" = "$revision"; \
    }; \
    fetch_exact \
      https://github.com/comfyanonymous/ComfyUI.git \
      /opt/comfyui \
      ba1d0efc9f7b9be64725e46093714401f265b1bb; \
    fetch_exact \
      https://github.com/cubiq/PuLID_ComfyUI.git \
      /opt/comfyui/custom_nodes/ComfyUI-PuLID \
      93e0c4c226b87b23c0009d671978bad0e77289ff; \
    fetch_exact \
      https://github.com/balazik/ComfyUI-PuLID-Flux.git \
      /opt/comfyui/custom_nodes/ComfyUI-PuLID-Flux \
      a80912fc3435c358607bf4b43a58dbcbebdb09ff

COPY deploy/runpod-comfyui/ /opt/content/deployment/
COPY pulid.json /opt/content/pulid.json

# Custom PuLID nodes derive their private model roots from ComfyUI's primary
# models directory.  These immutable links keep large, verified models on the
# RunPod network volume while core loaders use extra_model_paths.yaml.
RUN ln -s /workspace/models/insightface /opt/comfyui/models/insightface \
    && ln -s /workspace/models/pulid /opt/comfyui/models/pulid \
    && /opt/content-venv/bin/python /opt/content/deployment/bin/model_artifacts.py \
         --manifest /opt/content/deployment/models.json --validate-only \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin content \
    && mkdir -p /workspace/comfyui/{input,output,temp,user,logs} /workspace/models /run/content \
    && chown -R content:content /workspace /run/content \
    && chown -R root:root /opt/comfyui /opt/content /opt/content-venv \
    && chmod -R a-w /opt/comfyui /opt/content /opt/content-venv \
    && chmod a+x /opt/content/deployment/bin/*.py /opt/content/deployment/bin/*.sh

USER 10001:10001
WORKDIR /opt/content/deployment

# Only the authenticated gateway is public.  Raw ComfyUI stays on loopback:8188.
EXPOSE 8189

HEALTHCHECK --interval=30s --timeout=8s --start-period=10m --retries=3 \
  CMD ["/opt/content-venv/bin/python", "/opt/content/deployment/bin/probe.py", "--url", "http://127.0.0.1:8189", "--mode", "readiness"]

ENTRYPOINT ["/opt/content/deployment/bin/entrypoint.sh"]
