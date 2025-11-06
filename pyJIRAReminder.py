#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jira Reminder — PyQt6 tray app (updated)
- Дефолт:
  * start_date_field: customfield_10015
  * "Closed today": status CHANGED TO Done DURING (startOfDay(), now())
  * issue_types: ["Sub-task - HW"]
- --init  : створення шифрованого конфігу
- --edit-config : редагування існуючого конфігу (показує поточні значення, Enter = залишити)
- --logging : увімкнути DEBUG-лог у консоль (якщо термінал є) і у файл поряд з config.enc
"""

import sys, os, json, uuid, platform, getpass, pathlib, argparse, logging
from datetime import datetime, time as dtime
from urllib.parse import quote_plus

import requests
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PyQt6 import QtWidgets, QtGui, QtCore

APP_NAME = "Jira Reminder"
__version__ = "1.0.1-rc"

# -------------------------- Paths & logging --------------------------

def user_home() -> pathlib.Path:
    return pathlib.Path.home()

def app_dir() -> pathlib.Path:
    p = user_home() / ".jira_reminder"
    p.mkdir(parents=True, exist_ok=True)
    return p

CONFIG_ENC_PATH = app_dir() / "config.enc"
LOG_PATH = app_dir() / "jira_reminder.log"
MAGIC = b"JRM1"  # file header

log = logging.getLogger("jira_reminder")

def setup_logging(enabled: bool):
    if not enabled:
        return
    log.setLevel(logging.DEBUG)

    # Файловий лог
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    log.addHandler(fh)

    # Консольний лог (лише якщо це справжній термінал)
    try:
        if sys.stdout and sys.stdout.isatty():
            sh = logging.StreamHandler(sys.stdout)
            sh.setLevel(logging.DEBUG)
            sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            log.addHandler(sh)
    except Exception:
        pass

    # Менше шуму від HTTP-бібліотек
    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("requests").setLevel(logging.INFO)

# -------------------------- Security: encrypt config --------------------------

def _read_machine_id() -> str:
    mid = None
    try:
        if os.name == "nt":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            mid, _ = winreg.QueryValueEx(key, "MachineGuid")
    except Exception:
        pass
    if not mid and os.path.exists("/etc/machine-id"):
        try:
            with open("/etc/machine-id", "r", encoding="utf-8") as f:
                mid = f.read().strip()
        except Exception:
            pass
    if not mid:
        mid = str(uuid.getnode())
    return mid

def _derive_key_scrypt(salt: bytes) -> bytes:
    ident = f"{_read_machine_id()}::{getpass.getuser()}::{platform.platform()}".encode("utf-8")
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    return kdf.derive(ident)

def encrypt_config(obj: dict) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    salt = os.urandom(16)
    key = _derive_key_scrypt(salt)
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, raw, None)
    return MAGIC + salt + nonce + ct

def decrypt_config(blob: bytes) -> dict:
    if not blob.startswith(MAGIC):
        raise ValueError("Bad config file header.")
    salt = blob[4:20]
    nonce = blob[20:32]
    ct = blob[32:]
    key = _derive_key_scrypt(salt)
    aes = AESGCM(key)
    raw = aes.decrypt(nonce, ct, None)
    return json.loads(raw.decode("utf-8"))

def load_config() -> dict:
    data = CONFIG_ENC_PATH.read_bytes()
    obj = decrypt_config(data)
    # Інжектимо дефолти, якщо чогось бракує
    obj.setdefault("project_keys", [])
    obj.setdefault("issue_types", ["Sub-task - HW"])
    obj.setdefault("start_date_field", "customfield_10015")
    # done_jql може бути None — тоді за замовчуванням використовуємо "Done during today"
    obj.setdefault("done_jql", None)
    return obj

# -------------------------- JIRA Client --------------------------

class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str, projects: list[str], issue_types: list[str],
                 start_date_field: str | None = None, done_jql_override: str | None = None):
        self.base = base_url.rstrip("/")
        self.email = email
        self.token = api_token
        self.projects = projects or []
        self.issue_types = issue_types or ["Sub-task - HW"]
        self.start_date_field = start_date_field or "customfield_10015"
        self.done_override = (done_jql_override or "").strip()

        self.session = requests.Session()
        self.session.auth = (self.email, self.token)
        self.session.headers.update({"Accept": "application/json"})

    def _cf_key(self) -> str | None:
        if not self.start_date_field:
            return None
        s = self.start_date_field.strip()
        if s.startswith("cf[") and s.endswith("]"):
            return s
        if s.startswith("customfield_"):
            num = s.split("_", 1)[1]
            return f"cf[{num}]"
        return s

    def _base_constraints(self, assignee_email: str) -> str:
        proj = ", ".join(self.projects)
        issuet = ", ".join([f'"{t}"' for t in self.issue_types]) if self.issue_types else ""
        parts = [
            f'project in ({proj})' if self.projects else "",
            f'assignee = "{assignee_email}"',
            f'issuetype in ({issuet})' if issuet else "",
            'statusCategory != Done'
        ]
        return " AND ".join([p for p in parts if p])

    def jql_overdue(self, assignee_email: str) -> str:
        base = self._base_constraints(assignee_email)
        cf = self._cf_key()
        or_parts = ['(duedate < startOfDay() AND duedate is not EMPTY)']
        if cf:
            or_parts.append(f'({cf} < startOfDay() AND {cf} is not EMPTY)')
        return f'{base} AND ({" OR ".join(or_parts)}) ORDER BY duedate ASC, updated DESC'

    def jql_for_day(self, assignee_email: str, day: str) -> str:
        shift = 0 if day == "today" else 1
        base = self._base_constraints(assignee_email)
        cf = self._cf_key()
        target = "startOfDay()" if shift == 0 else "startOfDay('+1d')"
        or_parts = [f'(duedate = {target})']
        if cf:
            or_parts.append(f'({cf} = {target})')
        return f'{base} AND ({" OR ".join(or_parts)}) ORDER BY duedate ASC, updated DESC'

    def jql_closed_today(self, assignee_email: str) -> str:
        if self.done_override:
            return self.done_override
        # Дефолт: "Done сьогодні"
        proj = f' AND project in ({", ".join(self.projects)})' if self.projects else ""
        return f'assignee = "{assignee_email}"{proj} AND status CHANGED TO Done DURING (startOfDay(), now()) ORDER BY resolutiondate DESC'

    def search(self, jql: str, max_results: int = 50) -> list[dict]:
        url = f"{self.base}/rest/api/3/search/jql"
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "duedate", "issuetype", "assignee", "project"]
        }
        log.debug("POST %s", url); log.debug("JQL: %s", jql)
        try:
            r = self.session.post(url, json=payload, timeout=30)
            log.debug("HTTP %s %s", r.status_code, r.reason)
            r.raise_for_status()
            data = r.json()
        except requests.HTTPError as e:
            # Fallback: деякі інстанси тимчасово приймають лише GET-варіант нового API
            if getattr(e, "response", None) is not None and e.response.status_code in (404, 405):
                log.warning("POST /search/jql not accepted, trying GET fallback")
                r = self.session.get(
                    url,
                    params={
                        "jql": jql,
                        "maxResults": max_results,
                        "fields": "summary,duedate,issuetype,assignee,project"
                    },
                    timeout=30
                )
                log.debug("HTTP %s %s (GET fallback)", r.status_code, r.reason)
                r.raise_for_status()
                data = r.json()
            else:
                body = e.response.text if getattr(e, "response", None) is not None else str(e)
                log.error("JIRA HTTP error: %s\nResponse body:\n%s", e, body)
                raise
        issues = data.get("issues", [])
        parsed = []
        for it in issues:
            key = it["key"]
            f = it.get("fields", {})
            parsed.append({
                "key": key,
                "summary": f.get("summary", "(no summary)"),
                "duedate": f.get("duedate"),
                "issuetype": (f.get("issuetype") or {}).get("name"),
                "project": (f.get("project") or {}).get("key"),
            })
        # формуємо URL пізніше в UI, щоб не дублювати
        return parsed

    def make_issue_url(self, key: str) -> str:
        return f"{self.base}/browse/{key}"

    def make_issues_link(self, jql: str) -> str:
        return f"{self.base}/issues/?jql={quote_plus(jql)}"

# -------------------------- UI --------------------------

class IssuesList(QtWidgets.QWidget):
    openLink = QtCore.pyqtSignal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.label = QtWidgets.QLabel(f"<b>{title}</b>")
        self.list = QtWidgets.QListWidget()
        self.list.itemActivated.connect(self._activate)
        self.show_more_btn = QtWidgets.QPushButton("Show more")
        self.show_more_btn.setVisible(False)
        self.show_more_btn.clicked.connect(self._open_more)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.label)
        lay.addWidget(self.list)
        lay.addWidget(self.show_more_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        self._more_url = None

    def set_issues(self, issues: list[dict], more_url: str | None, url_builder):
        self.list.clear()
        self._more_url = more_url
        self.show_more_btn.setVisible(bool(more_url))
        for it in issues[:5]:
            due_txt = f" (due {it['duedate']})" if it.get("duedate") else ""
            txt = f"{it['key']}: {it['summary']}{due_txt}"
            item = QtWidgets.QListWidgetItem(txt)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, url_builder(it["key"]))
            self.list.addItem(item)

    def _activate(self, item: QtWidgets.QListWidgetItem):
        url = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if url:
            self.openLink.emit(url)

    def _open_more(self):
        if self._more_url:
            self.openLink.emit(self._more_url)

class TodayPopup(QtWidgets.QDialog):
    def __init__(self, issues: list[dict], url_builder, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Today's tasks")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.Tool)
        self.setModal(False)
        self.resize(520, 360)
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel("<b>Today's tasks</b>"))
        self.list = QtWidgets.QListWidget()
        v.addWidget(self.list)
        for it in issues[:10]:
            due_txt = f" (due {it['duedate']})" if it.get("duedate") else ""
            item = QtWidgets.QListWidgetItem(f"{it['key']}: {it['summary']}{due_txt}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, url_builder(it["key"]))
            self.list.addItem(item)
        self.list.itemActivated.connect(self._act)

    def _act(self, item):
        url = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if url:
            import webbrowser
            webbrowser.open(url)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app_icon: QtGui.QIcon, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon)
        self.resize(880, 600)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        grid = QtWidgets.QGridLayout(central)

        self.overdue = IssuesList("Overdue")
        self.today = IssuesList("Today")
        self.tomorrow = IssuesList("Tomorrow")

        for w in (self.overdue, self.today, self.tomorrow):
            w.openLink.connect(lambda url: __import__("webbrowser").open(url))

        grid.addWidget(self.overdue, 0, 0)
        grid.addWidget(self.today, 0, 1)
        grid.addWidget(self.tomorrow, 1, 0, 1, 2)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        grid.addWidget(self.refresh_btn, 2, 1, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        event.ignore()
        self.hide()

# -------------------------- Controller --------------------------

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
        # Візьмемо системний інтервал дабл-кліку, fallback 300 мс
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
            done_jql_override=cfg.get("done_jql")
        )

        self.today_issues = []
        self._last_close_check = None

        self._setup_timers()
        self.refresh_all(initial=True)

    def _load_icon(self) -> QtGui.QIcon:
        ico = None
        for name in ("app.ico", "app.png", "icon.png"):
            p = pathlib.Path(__file__).with_name(name)
            if p.exists():
                ico = QtGui.QIcon(str(p))
                break
        if not ico or ico.isNull():
            pm = QtGui.QPixmap(64, 64)
            pm.fill(QtGui.QColor("white"))
            painter = QtGui.QPainter(pm)
            painter.setPen(QtGui.QPen(QtGui.QColor("black"), 3))
            painter.drawEllipse(4, 4, 56, 56)
            painter.drawLine(32, 32, 32, 12)
            painter.drawLine(32, 32, 48, 32)
            painter.end()
            ico = QtGui.QIcon(pm)
        return ico

    def _setup_timers(self):
        self.tick = QtCore.QTimer(self)
        self.tick.setInterval(60_000)
        self.tick.timeout.connect(self._on_tick)
        self.tick.start()

    def _on_tick(self):
        now = datetime.now()
        if now.hour == 10 and now.minute in (0, 1):
            log.debug("10:00 check triggered")
            self.check_today_and_notify()
        if dtime(16, 30) <= dtime(now.hour, now.minute) <= dtime(19, 0):
            from datetime import timedelta
            if (self._last_close_check is None) or ((now - self._last_close_check).total_seconds() >= 30*60):
                self._last_close_check = now
                has = self._has_closed_today()
                log.debug("Evening check: has_closed_today=%s", has)
                if not has:
                    self.tray.showMessage(APP_NAME,
                                          "Жодної задачі не закрито сьогодні. Обери хоча б одну і доведи до Done 💪",
                                          QtWidgets.QSystemTrayIcon.MessageIcon.Information, 10_000)

    def check_today_and_notify(self):
        try:
            jql_today = self.client.jql_for_day(self.cfg["assignee_email"], "today")
            self.today_issues = self.client.search(jql_today, max_results=10)
            if self.today_issues:
                items = "\n".join([f"{x['key']}: {x['summary']}" for x in self.today_issues[:5]])
                self.tray.showMessage(APP_NAME, f"Сьогоднішні задачі:\n{items}",
                                      QtWidgets.QSystemTrayIcon.MessageIcon.Information, 12_000)
        except Exception as e:
            log.exception("check_today_and_notify failed")
            self.tray.showMessage(APP_NAME, f"Помилка оновлення: {e}",
                                  QtWidgets.QSystemTrayIcon.MessageIcon.Warning, 8000)

    def _has_closed_today(self) -> bool:
        try:
            jql = self.client.jql_closed_today(self.cfg["assignee_email"])
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

            self.window.overdue.set_issues(over_issues, self.client.make_issues_link(jql_over), self.client.make_issue_url)
            self.window.today.set_issues(self.today_issues, self.client.make_issues_link(jql_today), self.client.make_issue_url)
            self.window.tomorrow.set_issues(tom_issues, self.client.make_issues_link(jql_tom), self.client.make_issue_url)

            if not initial:
                self.tray.showMessage(APP_NAME, "Дані оновлено",
                                      QtWidgets.QSystemTrayIcon.MessageIcon.Information, 3000)
        except requests.HTTPError as e:
            log.exception("JIRA HTTP error during refresh")
            self.tray.showMessage(APP_NAME, f"JIRA HTTP помилка: {e}",
                                  QtWidgets.QSystemTrayIcon.MessageIcon.Critical, 8000)
        except Exception as e:
            log.exception("Unexpected error during refresh")
            self.tray.showMessage(APP_NAME, f"Помилка: {e}",
                                  QtWidgets.QSystemTrayIcon.MessageIcon.Critical, 8000)

    def show_main(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def show_today_popup(self):
        if not self.today_issues:
            try:
                jql_today = self.client.jql_for_day(self.cfg["assignee_email"], "today")
                self.today_issues = self.client.search(jql_today, max_results=10)
            except Exception:
                pass
        dlg = TodayPopup(self.today_issues, self.client.make_issue_url, self.window)
        dlg.exec()

    def _tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            # стартуємо таймер одинарного кліку; якщо прилетить DoubleClick — ми його скасуємо
            if self._click_timer.isActive():
                self._click_timer.stop()
            self._click_timer.start()
        elif reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            # подвійний клік — скасувати single-click і показати головне вікно
            if self._click_timer.isActive():
                self._click_timer.stop()
            self.show_main()

# -------------------------- CLI: init/edit config --------------------------

def _prompt_edit(label: str, current: str | None) -> str | None:
    show = current if (current not in (None, [], "")) else ""
    val = input(f"{label} [{show}]: ").strip()
    return current if val == "" else val

def init_config_interactive(defaults: dict):
    print("=== Jira Reminder config init ===")
    base = input("JIRA base URL (e.g. https://yourcompany.atlassian.net): ").strip()
    email = input("Assignee email: ").strip()
    token = input("JIRA API token: ").strip()
    projects = input("Project keys (comma-separated, e.g. ABC,XYZ): ").strip()
    issue_types = input('Issue types (comma-separated) [default: Sub-task - HW]: ').strip()
    start_field = input('Start date field [default: customfield_10015]: ').strip()
    done_override = input('Custom JQL for "closed today" [default: Done DURING today]: ').strip()

    cfg = {
        "jira_base_url": base,
        "assignee_email": email,
        "api_token": token,
        "project_keys": [x.strip() for x in projects.split(",") if x.strip()],
        "issue_types": [x.strip() for x in (issue_types or "Sub-task - HW").split(",") if x.strip()],
        "start_date_field": start_field or "customfield_10015",
        "done_jql": done_override or None
    }
    CONFIG_ENC_PATH.write_bytes(encrypt_config(cfg))
    print(f"OK: saved encrypted config at {CONFIG_ENC_PATH}")

def edit_config_interactive():
    if not CONFIG_ENC_PATH.exists():
        print("Config not found. Run --init first.")
        return
    cfg = load_config()
    print("=== Edit Jira Reminder config (Enter = keep current) ===")
    cfg["jira_base_url"]   = _prompt_edit("JIRA base URL", cfg.get("jira_base_url")) or cfg["jira_base_url"]
    cfg["assignee_email"]  = _prompt_edit("Assignee email", cfg.get("assignee_email")) or cfg["assignee_email"]
    cfg["api_token"]       = _prompt_edit("JIRA API token", cfg.get("api_token")) or cfg["api_token"]
    # lists:
    proj_raw = _prompt_edit("Project keys (comma-separated)", ", ".join(cfg.get("project_keys", []))) or ", ".join(cfg.get("project_keys", []))
    cfg["project_keys"] = [x.strip() for x in proj_raw.split(",") if x.strip()]
    issue_raw = _prompt_edit('Issue types (comma-separated)', ", ".join(cfg.get("issue_types", ["Sub-task - HW"]))) or ", ".join(cfg.get("issue_types", ["Sub-task - HW"]))
    cfg["issue_types"] = [x.strip() for x in issue_raw.split(",") if x.strip()]
    cfg["start_date_field"] = _prompt_edit("Start date field", cfg.get("start_date_field", "customfield_10015")) or cfg.get("start_date_field", "customfield_10015")
    cfg["done_jql"] = _prompt_edit('Custom "closed today" JQL (enter to keep default Done DURING today)', cfg.get("done_jql")) or cfg.get("done_jql")

    CONFIG_ENC_PATH.write_bytes(encrypt_config(cfg))
    print(f"Saved: {CONFIG_ENC_PATH}")

# -------------------------- main --------------------------

def main():
    parser = argparse.ArgumentParser(description="Jira Reminder Tray App")
    parser.add_argument("--init", action="store_true", help="Initialize encrypted config")
    parser.add_argument("--edit-config", action="store_true", help="Edit existing encrypted config")
    parser.add_argument("--logging", action="store_true", help="Enable DEBUG logging to console (if TTY) and to .log file")
    args = parser.parse_args()

    setup_logging(args.logging)
    log.debug("App start %s v%s", APP_NAME, __version__)

    if args.init:
        defaults = {"start_date_field": "customfield_10015", "issue_types": ["Sub-task - HW"], "done_jql": None}
        init_config_interactive(defaults)
        return
    if args.edit_config:
        edit_config_interactive()
        return

    if not CONFIG_ENC_PATH.exists():
        print("Encrypted config not found. Run: python jira_reminder.py --init")
        sys.exit(1)

    try:
        cfg = load_config()
    except Exception as e:
        print(f"[ERROR] Cannot load encrypted config: {e}")
        sys.exit(1)

    QtCore.QCoreApplication.setApplicationName(APP_NAME)
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) 
    ctrl = JiraReminderController(app, cfg)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
# EOF