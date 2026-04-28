#!/usr/bin/env bash
set -e

echo "[venv-refresh] Using project: $(pwd)"

echo "[venv-refresh] Uninstalling old editable package..."
pip uninstall -y wedge-native-backend || true

echo "[venv-refresh] Installing current project (editable)..."
pip install -e .

echo "[venv-refresh] Verifying import path..."
python - <<'PY'
import app.models
print("[venv-refresh] app.models path:", app.models.__file__)
PY

echo "[venv-refresh] Done."