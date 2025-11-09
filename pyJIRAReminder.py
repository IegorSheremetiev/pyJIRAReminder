#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

# Додаємо ./src у sys.path
if not getattr(sys, "frozen", False):
    ROOT = Path(__file__).resolve().parent
    SRC = ROOT / "src"
    if SRC.exists():
        sys.path.insert(0, str(SRC))

from jira_reminder.app import main  # noqa: E402
from jira_reminder import JiraReminderController, JiraClient, APP_NAME, __version__  # re-export для тестів / старого коду


if __name__ == "__main__":
    sys.exit(main())
