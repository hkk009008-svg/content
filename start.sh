#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
export KMP_DUPLICATE_LIB_OK=TRUE
export PYTHONWARNINGS="ignore::FutureWarning,ignore::UserWarning"
python3 web_server.py
