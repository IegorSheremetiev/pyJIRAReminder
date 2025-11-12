# src/jira_reminder/controller.py
from __future__ import annotations

from datetime import datetime, time as dtime

import requests, sys, os
from PyQt6 import QtWidgets, QtGui, QtCore

from .metrics import APP_NAME
from .logging_setup import log
from .paths import asset_path
from .jira_client import JiraClient
from .ui import MainWindow, TodayPopup


class JiraReminderController(QtCore.QObject):
    def __init__(self, app: QtWidgets.QApplication, cfg: dict):
        super().__init__()
        self.app = app
        self.icon = self._load_icon()

        self.window = MainWindow(self.icon)
        self.window.refresh_btn.clicked.connect(self.refresh_all)

        self.tray = QtWidgets.QSystemTrayIcon(self.icon)
        self.tray.setToolTip(APP_NAME)
        menu = QtWidgets.QMenu()
        act_open = menu.addAction("Open")
        act_open.triggered.connect(self.show_main)
        act_refresh = menu.addAction("Refresh")
        act_refresh.triggered.connect(self.refresh_all)
        menu.addSeparator()
        act_quit = menu.addAction("Quit")
        act_quit.triggered.connect(self.app.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        try:
            self._click_timer.setInterval(QtGui.QGuiApplication.styleHints().mouseDoubleClickInterval())
        except Exception:
            self._click_timer.setInterval(300)
        self._click_timer.timeout.connect(self.show_today_popup)

        self.cfg = cfg
        self.client = JiraClient(
            base_url=cfg["jira_base_url"],
            email=cfg["assignee_email"],
            api_token=cfg["api_token"],
            projects=cfg.get("project_keys", []),
            issue_types=cfg.get("issue_types", ["Sub-task - HW"]),
            start_date_field=cfg.get("start_date_field", "customfield_10015"),
            done_jql_override=cfg.get("done_jql"),
        )

        self.today_issues: list[dict] = []
        self._last_close_check: datetime | None = None

        self._setup_timers()
        self.refresh_all(initial=True)
        self.__undone_check_period = 30 * 60  # 30 minutes
        log.debug(f'The JireReminderController is initialized at {datetime.now().strftime("%d-%m-%Y %H:%M:%S")}')

    def _load_icon(self) -> QtGui.QIcon:
        if sys.platform.startswith("win"):
            candidates = ("app.ico", "jira_reminder_icon_256.png", "app.png", "icon.png")
        else:
            candidates = ("jira_reminder_icon_256.png", "app.png", "icon.png", "app.ico")

        for name in candidates:
            p = asset_path(name)
            if os.path.exists(p):
                ico = QtGui.QIcon(p)
                if not ico.isNull():
                    return ico

        pm = QtGui.QPixmap(64, 64)
        pm.fill(QtGui.QColor("white"))
        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtGui.QPen(QtGui.QColor("black"), 3))
        painter.drawEllipse(4, 4, 56, 56)
        painter.drawLine(32, 32, 32, 12)
        painter.drawLine(32, 32, 48, 32)
        painter.end()
        return QtGui.QIcon(pm)

    def _setup_timers(self):
        # Define a timer that ticks each minute
        self.tick = QtCore.QTimer(self)
        self.tick.setInterval(60_000)
        self.tick.timeout.connect(self._on_tick)
        self.tick.start()

        # Define a timer that ticks each 1 hour
        self.refresh_tick = QtCore.QTimer(self)
        self.refresh_tick.setInterval(1 * 60 * 60 * 1000)
        self.refresh_tick.timeout.connect(self.refresh_all)
        self.refresh_tick.start()

    def _on_tick_at(self, now: datetime):
        log.debug("Tick at %s", now.strftime("%H:%M:%S"))
        log.debug("Tick at %s", now.strftime("%H:%M:%S"))
        if now.hour == 10 and now.minute in (0, 1):
            log.debug("10:00 check triggered")
            self.check_today_and_notify()

        if dtime(16, 30) <= dtime(now.hour, now.minute) <= dtime(19, 0):
            seconds_passed = (int((now - self._last_close_check).total_seconds()) + 1) if self._last_close_check else float('inf')
            log.debug("Evening check time window: now %s, last check %s, seconds passed %s", now.strftime("%H:%M:%S"), 
                      self._last_close_check.strftime("%H:%M:%S") if self._last_close_check else "None", 
                      seconds_passed)
            
            if (self._last_close_check is None) or (seconds_passed >= self.__undone_check_period):
            seconds_passed = (int((now - self._last_close_check).total_seconds()) + 1) if self._last_close_check else float('inf')
            log.debug("Evening check time window: now %s, last check %s, seconds passed %s", now.strftime("%H:%M:%S"), 
                      self._last_close_check.strftime("%H:%M:%S") if self._last_close_check else "None", 
                      seconds_passed)
            
            if (self._last_close_check is None) or (seconds_passed >= self.__undone_check_period):
                self._last_close_check = now
                has = self._has_closed_today()
                log.debug("Evening check: has_closed_today=%s", has)
                if not has:
                    self.tray.showMessage(
                        APP_NAME,
                        "No tasks completed today. Choose at least one and get it to Done 💪",
                        QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                        10_000,
                    )

    def _on_tick(self):
        self._on_tick_at(datetime.now())

    def check_today_and_notify(self):
        try:
            jql_today = self.client.jql_for_day(self.cfg["assignee_email"], "today")
            self.today_issues = self.client.search(jql_today, max_results=10)
            if self.today_issues:
                items = "\n".join([f"{x['key']}: {x['summary']}" for x in self.today_issues[:5]])
                self.tray.showMessage(
                    APP_NAME,
                    f"Today's tasks:\n{items}",
                    QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                    12_000,
                )
        except Exception as e:
            log.exception("check_today_and_notify failed")
            self.tray.showMessage(
                APP_NAME,
                f"Update error: {e}",
                QtWidgets.QSystemTrayIcon.MessageIcon.Warning,
                8000,
            )

    def _has_closed_today(self) -> bool:
        try:
            jql = self.client.jql_closed_today(self.cfg["assignee_email"])
            log.debug("Checking closed today with JQL: %s", jql)
            log.debug("Checking closed today with JQL: %s", jql)
            issues = self.client.search(jql, max_results=1)
            return len(issues) > 0
        except Exception:
            log.exception("_has_closed_today failed")
            return False

    def refresh_all(self, initial: bool = False):
        try:
            assignee = self.cfg["assignee_email"]
            jql_over = self.client.jql_overdue(assignee)
            jql_today = self.client.jql_for_day(assignee, "today")
            jql_tom = self.client.jql_for_day(assignee, "tomorrow")

            over_issues = self.client.search(jql_over, max_results=50)
            self.today_issues = self.client.search(jql_today, max_results=50)
            tom_issues = self.client.search(jql_tom, max_results=50)

            self.window.overdue.set_issues(
                over_issues, self.client.make_issues_link(jql_over), self.client.make_issue_url
            )
            self.window.today.set_issues(
                self.today_issues, self.client.make_issues_link(jql_today), self.client.make_issue_url
            )
            self.window.tomorrow.set_issues(
                tom_issues, self.client.make_issues_link(jql_tom), self.client.make_issue_url
            )

            if not initial:
                self.tray.showMessage(
                    APP_NAME,
                    "Data updated",
                    QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
        except requests.HTTPError as e:
            log.exception("JIRA HTTP error during refresh")
            self.tray.showMessage(
                APP_NAME,
                f"JIRA HTTP error: {e}",
                QtWidgets.QSystemTrayIcon.MessageIcon.Critical,
                8000,
            )
        except Exception as e:
            log.exception("Unexpected error during refresh")
            self.tray.showMessage(
                APP_NAME,
                f"Error: {e}",
                QtWidgets.QSystemTrayIcon.MessageIcon.Critical,
                8000,
            )

    def show_main(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def show_today_popup(self):
        try:
            if not self.today_issues:
                jql_today = self.client.jql_for_day(self.cfg["assignee_email"], "today")
                self.today_issues = self.client.search(jql_today, max_results=50)
            else:
                jql_today = self.client.jql_for_day(self.cfg["assignee_email"], "today")

            more_url = self.client.make_issues_link(jql_today)
            dlg = TodayPopup(self.today_issues, more_url, self.client.make_issue_url, self.window)
            dlg.exec()
        except Exception as e:
            log.exception("show_today_popup failed")
            self.tray.showMessage(
                APP_NAME,
                f"Error: {e}",
                QtWidgets.QSystemTrayIcon.MessageIcon.Critical,
                8000,
            )

    def _tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            if self._click_timer.isActive():
                self._click_timer.stop()
            self._click_timer.start()
        elif reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            if self._click_timer.isActive():
                self._click_timer.stop()
            self.show_main()
