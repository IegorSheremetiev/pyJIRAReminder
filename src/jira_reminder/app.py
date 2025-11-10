# src/jira_reminder/app.py
from __future__ import annotations

import sys
import argparse
import subprocess, os, shutil, ctypes

from PyQt6 import QtWidgets, QtCore

from .metrics import APP_NAME, __version__, set_ui_scale
from .paths import CONFIG_ENC_PATH, LOCK_PATH

from .logging_setup import setup_logging, log
from .security import load_config, init_config_interactive, edit_config_interactive
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

    # Quick helper: ensure a console is available when running CLI-only modes from a GUI/no-console build
    def open_console_or_terminal_for_args(cli_args: list[str]) -> bool:
        # Windows: allocate a console for interactive CLI work
        if sys.platform == "win32":
            try:
                if ctypes.windll.kernel32.AllocConsole() != 0:
                    # redirect stdio to the new console
                    sys.stdout = open("CONOUT$", "w", buffering=1)
                    sys.stderr = open("CONOUT$", "w", buffering=1)
                    sys.stdin = open("CONIN$", "r")
                return True
            except Exception:
                return False

        # Linux / other: attempt to spawn a terminal emulator that runs this executable with args
        exe = os.path.abspath(sys.argv[0])
        terminals = ["x-terminal-emulator", "gnome-terminal", "konsole", "xterm", "alacritty", "tilix", "mate-terminal", "lxterminal"]
        for term in terminals:
            term_path = shutil.which(term)
            if not term_path:
                continue
            try:
                if term in ("gnome-terminal", "mate-terminal", "tilix"):
                    subprocess.Popen([term_path, "--", exe] + cli_args)
                else:
                    subprocess.Popen([term_path, "-e", exe] + cli_args)
                return True
            except Exception:
                continue
        return False

    # If user requested console-only operations, make sure a console/terminal is available
    if args.init or args.edit_config:
        cli_args = []
        if args.init:
            cli_args.append("--init")
        if args.edit_config:
            cli_args.append("--edit-config")
        # if running headless (no tty) try to open console/terminal to run interactive code in-place
        if not sys.stdin or not sys.stdin.isatty():
            ok = open_console_or_terminal_for_args(cli_args)
            if not ok:
                print("No console available. Either run the program from a terminal or rebuild without --noconsole.")
                return 1

    set_ui_scale(args.ui_scale)

    if args.init:
        defaults = {"start_date_field": "customfield_10015", "issue_types": ["Sub-task - HW"], "done_jql": None}
        init_config_interactive(defaults)
        return 0

    if not CONFIG_ENC_PATH.exists():
        print("Encrypted config not found. Run: pyJIRAReminder.py --init")
        return 1

    try:
        cfg = load_config()
    except Exception as e:
        print(f"[ERROR] Cannot load encrypted config: {e}")
        return 1
    
    if args.edit_config:
        edit_config_interactive()
        return 0

    QtCore.QCoreApplication.setApplicationName(APP_NAME)
    app = QtWidgets.QApplication(sys.argv)
    lock = ensure_single_instance_or_exit()
    setup_logging(args.logging, args.new_log)
    log.debug("App start %s v%s", APP_NAME, __version__)
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
