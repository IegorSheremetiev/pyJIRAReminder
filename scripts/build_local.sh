#!/usr/bin/env bash
set -euo pipefail

APP="JiraReminder"
SRC="pyJIRAReminder.py"

python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null
pip install pyinstaller >/dev/null

# get version from __version__
VER=$(grep -Po '__version__\s*=\s*["'\'']\K([^"'\'' ]+)(?=["'\''])' "$SRC" || echo "dev")

pyinstaller --onefile --name "$APP" --icon assets/app.ico --add-data "assets;assets" "$SRC"
if [[ -f "dist/$APP" ]]; then
  OUT="dist/${APP}-v${VER}-linux-x86_64"
  mv "dist/$APP" "$OUT"
  echo "Built $OUT"
else
  echo "Build failed: dist/$APP not found" >&2
  exit 1
fi
