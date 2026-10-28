#!/usr/bin/env bash
# Native Linux build; Python dependencies belong to the caller's virtual environment.
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"
"${PYTHON_BIN:-python}" scripts/build.py
