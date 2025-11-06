#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt

APP=jira_reminder.py
NAME=JiraReminder
VER="v$(python - <<'PY'
import re
print(re.search(r'__version__ = "(.+?)"', open("jira_reminder.py","r",encoding="utf-8").read()).group(1))
PY
)"

pyinstaller --noconfirm --onefile \
  --name "${NAME}-${VER}-linux-x86_64" \
  --add-data "app.png:." \
  "$APP"

echo "Done. BIN: dist/${NAME}-${VER}-linux-x86_64"
