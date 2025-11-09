# src/jira_reminder/app.py
from __future__ import annotations

import sys
import argparse

from PyQt6 import QtWidgets, QtCore

from .metrics import APP_NAME, __version__, set_ui_scale
from .paths import CONFIG_ENC_PATH, LOCK_PATH
from .logging_setup import setup_logging, log
from .security import load_config, init_config_interactive, edit_config_interactive
from .controller import JiraReminderController


def ensure_single_instance_or_exit(parent=None):
    from PyQt6 import QtCore, QtWidgets

    lock = QtCore.QLockFile(LOCK_PATH)
    lock.setStaleLockTime(60 * 60 * 1000)

    if lock.tryLock(0):
        return lock

    if lock.removeStaleLockFile() and lock.tryLock(100):
        return lock

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    QtWidgets.QMessageBox.information(parent, "Jira Reminder", "Application is already running.")
    sys.exit(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jira Reminder Tray App")
    parser.add_argument("--init", action="store_true", help="Initialize encrypted config")
    parser.add_argument("--edit-config", action="store_true", help="Edit existing encrypted config")
    parser.add_argument("--logging", action="store_true", help="Enable DEBUG logging to console (if TTY) and to .log file")
    parser.add_argument("--new-log", action="store_true", help="Create new log file instead of appending")
    parser.add_argument(
        "--ui-scale",
        dest="ui_scale",
        type=float,
        default=1.25,
        metavar="X",
        help="UI scale factor (e.g. 1.25 for 125%%)",
    )

    args = parser.parse_args(argv)

    setup_logging(args.logging, args.new_log)
    log.debug("App start %s v%s", APP_NAME, __version__)

    set_ui_scale(args.ui_scale)

    if args.init:
        defaults = {"start_date_field": "customfield_10015", "issue_types": ["Sub-task - HW"], "done_jql": None}
        init_config_interactive(defaults)
        return 0

    if args.edit_config:
        edit_config_interactive()
        return 0

    if not CONFIG_ENC_PATH.exists():
        print("Encrypted config not found. Run: pyJIRAReminder.py --init")
        return 1

    try:
        cfg = load_config()
    except Exception as e:
        print(f"[ERROR] Cannot load encrypted config: {e}")
        return 1

    QtCore.QCoreApplication.setApplicationName(APP_NAME)
    app = QtWidgets.QApplication(sys.argv)
    lock = ensure_single_instance_or_exit()
    log.debug("Single instance lock acquired: %s", lock.fileName())

    font = app.font()
    ps = font.pointSizeF()
    if ps <= 0:
        ps = 12.0
    from .metrics import UI_SCALE  # читаємо актуальний масштаб
    font.setPointSizeF(max(7.5, ps * UI_SCALE))
    app.setFont(font)
    app.setQuitOnLastWindowClosed(False)
    log.debug("QApplication initialized with UI scale %.2fx", UI_SCALE)

    ctrl = JiraReminderController(app, cfg)
    return app.exec()
