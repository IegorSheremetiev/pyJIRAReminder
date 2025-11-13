# src/jira_reminder/app.py
from __future__ import annotations

import sys
import subprocess, os, shutil

from PyQt6 import QtWidgets, QtCore

from .metrics import APP_NAME, __version__, set_ui_scale
from .paths import CONFIG_ENC_PATH, LOCK_PATH, CONFIG_PLAIN_PATH

from .logging_setup import setup_logging, log
from .security import load_config
from .ui import ConfigDialog
from .controller import JiraReminderController




def ensure_single_instance_or_exit(parent=None):
    lock = QtCore.QLockFile(LOCK_PATH)
    lock.setStaleLockTime(60 * 60 * 1000)  # 1 hour

    if lock.tryLock(0):
        return lock

    # try to clean stale lock once
    if lock.removeStaleLockFile() and lock.tryLock(100):
        return lock

    # Another instance is really running
    QtWidgets.QMessageBox.information(parent, APP_NAME, "Application is already running.")
    sys.exit(0)


def main(argv: list[str] | None = None) -> int:
    # Load plain settings (non-secure) if available to set UI scale and logging defaults
    import json
    ui_scale = 1.25
    plain_settings = {}
    try:
        if CONFIG_PLAIN_PATH.exists():
            plain_settings = json.loads(CONFIG_PLAIN_PATH.read_text(encoding="utf-8"))
            ui_scale = float(plain_settings.get("ui_scale", ui_scale))
    except Exception:
        plain_settings = {}

    set_ui_scale(ui_scale)

    # Ensure secure config exists: show config dialog if encrypted config missing
    QtCore.QCoreApplication.setApplicationName(APP_NAME)
    app = QtWidgets.QApplication(sys.argv)
    if not CONFIG_ENC_PATH.exists():
        dlg = ConfigDialog()
        dlg.exec()
        # after dialog, require encrypted config to exist; otherwise abort
        if not CONFIG_ENC_PATH.exists():
            QtWidgets.QMessageBox.critical(None, APP_NAME, "Encrypted config not found. Exiting.")
            return 1

    # load secure config (required for normal run)
    try:
        cfg = load_config()
    except Exception as e:
        QtWidgets.QMessageBox.critical(None, APP_NAME, f"Cannot load encrypted config: {e}")
        return 1

    lock = ensure_single_instance_or_exit()
    setup_logging(bool(plain_settings.get("logging", False)), bool(plain_settings.get("new_log", False)))
    log.debug("App start %s v%s", APP_NAME, __version__)
    log.debug("Single instance lock acquired: %s", lock.fileName())

    font = app.font()
    ps = font.pointSizeF()
    if ps <= 0:
        ps = 12.0
    from .metrics import UI_SCALE, set_base_font_size, BASE_FONT_SIZE  # читаємо актуальний масштаб
    # store unscaled base font size and apply scaling deterministically
    set_base_font_size(ps)
    font.setPointSizeF(max(7.5, BASE_FONT_SIZE * UI_SCALE))
    app.setFont(font)
    app.setQuitOnLastWindowClosed(False)
    log.debug("QApplication initialized with UI scale %.2fx", UI_SCALE)

    ctrl = JiraReminderController(app, cfg)
    return app.exec()
