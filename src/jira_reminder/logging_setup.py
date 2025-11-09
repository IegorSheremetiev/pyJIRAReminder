# src/jira_reminder/logging_setup.py
from __future__ import annotations

import sys
import logging

from .paths import LOG_PATH

log = logging.getLogger("jira_reminder")


def setup_logging(enabled: bool, new_log: bool) -> None:
    if not enabled:
        return

    log.setLevel(logging.DEBUG)

    # File log
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8", mode="w" if new_log else "a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    log.addHandler(fh)

    # Console log (якщо реальний TTY)
    try:
        if sys.stdout and sys.stdout.isatty():
            sh = logging.StreamHandler(sys.stdout)
            sh.setLevel(logging.DEBUG)
            sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            log.addHandler(sh)
    except Exception:
        pass

    # Менше шуму від HTTP
    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("requests").setLevel(logging.INFO)
