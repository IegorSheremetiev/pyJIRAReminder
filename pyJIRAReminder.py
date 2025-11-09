#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jira Reminder — PyQt6 tray app (updated)
- Defaults:
  * start_date_field: customfield_10015
  * "Closed today": status CHANGED TO Done DURING (startOfDay(), now())
  * issue_types: ["Sub-task - HW"]
- --init  : create encrypted config
- --edit-config : edit existing config (shows current values, Enter = keep current)
- --logging : enable DEBUG logging to console (if terminal exists) and to file next to config.enc
"""

from tkinter import font
import sys, os, json, uuid, platform, getpass, pathlib, argparse, logging
from datetime import datetime, time as dtime
from urllib.parse import quote_plus

import requests
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PyQt6 import QtWidgets, QtGui, QtCore

# -------------------------- App constants & metrics --------------------------
APP_NAME = "Jira Reminder"
__version__ = "0.7.1"  # x-release-please-version

# --- UI scaling & metrics ---
UI_SCALE = 1
def S(px: float) -> int: return int(round(px * UI_SCALE))

BLOCK_WIDTH_PX  = lambda: S(450)   # was 350
CARD_HEIGHT_PX  = lambda: S(150)   # slightly more space for summary
GAP_PX          = lambda: S(12)
HEADER_H_PX     = lambda: S(24)
SHOW_MORE_H_PX  = lambda: S(28)
BLOCK_HEIGHT_PX = lambda: HEADER_H_PX() + GAP_PX() + (CARD_HEIGHT_PX()*2) + GAP_PX() + SHOW_MORE_H_PX()

# -------------------------- Paths & logging --------------------------
def _base_path():
    return getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))

def asset_path(name: str) -> str:
    return os.path.join(_base_path(), "assets", name)

def user_home() -> pathlib.Path:
    return pathlib.Path.home()

def app_dir() -> pathlib.Path:
    p = user_home() / ".jira_reminder"
    p.mkdir(parents=True, exist_ok=True)
    return p

CONFIG_ENC_PATH = app_dir() / "config.enc"
LOG_PATH = app_dir() / "jira_reminder.log"
MAGIC = b"JRM1"  # file header
LOCK_PATH = str(app_dir() / "app.lock")

def ensure_single_instance_or_exit(parent=None):
    lock = QtCore.QLockFile(LOCK_PATH)
    # Prevent old lock from persisting forever after crash (1 hour is safe)
    lock.setStaleLockTime(60 * 60 * 1000)  # 1h

    if lock.tryLock(0):
        return lock  # keep lock reference until program end
    else:
        # If lock is stale - try to remove and acquire
        if lock.removeStaleLockFile() and lock.tryLock(100):
            return lock
        # Second instance - show toast and exit
        if parent is None:
            app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        else:
            app = QtWidgets.QApplication.instance()
        QtWidgets.QMessageBox.information(parent, "Jira Reminder",
            "Application is already running.")
        sys.exit(0)

log = logging.getLogger("jira_reminder")

def setup_logging(enabled: bool, new_log: bool):
    if not enabled:
        return
    log.setLevel(logging.DEBUG)

    # File log
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8", mode="w" if new_log else "a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    log.addHandler(fh)

    # Console log (only if it's a real terminal)
    try:
        if sys.stdout and sys.stdout.isatty():
            sh = logging.StreamHandler(sys.stdout)
            sh.setLevel(logging.DEBUG)
            sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            log.addHandler(sh)
    except Exception:
        pass

    # Less noise from HTTP libraries
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
    # log the path to the encrypted file
    log.debug(f"Load Config PATH: {CONFIG_ENC_PATH}")
    obj = decrypt_config(data)
    # Inject defaults if anything is missing
    obj.setdefault("project_keys", [])
    obj.setdefault("issue_types", ["Sub-task - HW"])
    obj.setdefault("start_date_field", "customfield_10015")
    # done_jql can be None - then we use default "Done during today"
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
        log.debug(f"The JiraClient is intialized for user {self.email}")

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
        # Default: "Done today"
        proj = f' AND project in ({", ".join(self.projects)})' if self.projects else ""
        return f'assignee = "{assignee_email}"{proj} AND status CHANGED TO Done DURING (startOfDay(), now()) ORDER BY resolutiondate DESC'

    def search(self, jql: str, max_results: int = 50) -> list[dict]:
        url = f"{self.base}/rest/api/3/search/jql"
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "duedate", "issuetype", "assignee", "project", "priority", "status"]
        }
        log.debug("POST %s", url); log.debug("JQL: %s", jql)
        try:
            r = self.session.post(url, json=payload, timeout=30)
            log.debug("HTTP %s %s", r.status_code, r.reason)
            r.raise_for_status()
            data = r.json()
        except requests.HTTPError as e:
            # Fallback: some instances temporarily only accept GET variant of new API
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
                "priority": (f.get("priority") or {}).get("name"),
                "status": (f.get("status") or {}).get("name"),
            })
        # form URL later in UI to avoid duplication
        return parsed

    def make_issue_url(self, key: str) -> str:
        return f"{self.base}/browse/{key}"

    def make_issues_link(self, jql: str) -> str:
        return f"{self.base}/issues/?jql={quote_plus(jql)}"

# -------------------------- UI --------------------------
class IssueCard(QtWidgets.QFrame):
    clicked = QtCore.pyqtSignal(str)  # url

    def __init__(self, issue: dict, url_builder, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)

        # Soft shadow
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 140))
        self.setGraphicsEffect(shadow)

        self.issue = issue
        self.url = url_builder(issue["key"])

        # --- Top row: KEY + due pill
        key_lbl = QtWidgets.QLabel(f"<b>{issue['key']}</b>")
        key_lbl.setTextFormat(QtCore.Qt.TextFormat.RichText)
        key_lbl.setToolTip(issue.get("summary") or "")

        summary = QtWidgets.QLabel(issue.get("summary") or "(no summary)")
        summary.setWordWrap(True)
        summary.setObjectName("Summary")
        summary.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                              QtWidgets.QSizePolicy.Policy.Preferred)

        due = issue.get("duedate")
        due_lbl = QtWidgets.QLabel(self._due_text(due))
        due_state = self._due_state(due)
        due_lbl.setObjectName("DuePill")
        due_lbl.setProperty("state", due_state)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(key_lbl)
        top.addStretch(1)
        top.addWidget(due_lbl)

        # --- Badges: issuetype, project, priority, status
        itype = issue.get("issuetype") or "Issue"
        prio  = (issue.get("priority") or "").strip() or "—"
        stat  = (issue.get("status") or "").strip() or "—"

        badges = FlowLayout(hspacing=S(6), vspacing=S(6))

        def _badge(text, objname, **props):
            lbl = QtWidgets.QLabel(text)
            lbl.setObjectName(objname)
            lbl.setProperty("badge", True)
            for k, v in props.items():
                lbl.setProperty(k, v)
            return lbl
        # for text, objname in ((itype, "TypeBadge"), (proj, "ProjBadge")):
        #     b = QtWidgets.QLabel(text); b.setObjectName(objname); b.setProperty("badge", True)
        #     badges.addWidget(b)

        # prio_badge = QtWidgets.QLabel(f"Priority: {prio}")
        # prio_badge.setObjectName("PriorityBadge")
        # prio_badge.setProperty("badge", True)
        # prio_badge.setProperty("level", prio)
        # badges.addWidget(prio_badge)

        # status_badge = QtWidgets.QLabel(f"Status: {stat}")
        # status_badge.setObjectName("StatusBadge")
        # status_badge.setProperty("badge", True)
        # status_badge.setProperty("state", self._status_state(stat))
        # badges.addWidget(status_badge)

        

        # badges.addWidget(_badge(itype, "TypeBadge"))
        
        # prio_badge = _badge(f"Priority: {prio}", "PriorityBadge", "level", prio)
        # badges.addWidget(prio_badge)

        # status_badge = _badge(f"Status: {stat}", "StatusBadge", "state", self._status_state(stat))
        # badges.addWidget(status_badge)

        badges.addWidget(_badge(itype, "TypeBadge"))
        badges.addWidget(_badge(f"Priority: {prio}", "PriorityBadge", level=prio))
        badges.addWidget(_badge(f"Status: {stat}", "StatusBadge", state=self._status_state(stat)))


        badges.addItem(QtWidgets.QSpacerItem(
            0, 0,
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum
        ))

        # --- Actions
        btn_open = QtWidgets.QPushButton("Open")
        btn_open.clicked.connect(lambda: self.clicked.emit(self.url))
        actions = QtWidgets.QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(btn_open)

        # --- Compose
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        lay.addLayout(top)
        lay.addWidget(summary)
        lay.addLayout(badges)
        lay.addLayout(actions)

        # state hint for CSS border color
        self.setProperty("state", due_state)

        # ensure card grows to width, fixed height is set by parent list
        sp = self.sizePolicy()
        sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Expanding)
        sp.setVerticalPolicy(QtWidgets.QSizePolicy.Policy.Fixed)
        self.setSizePolicy(sp)
        # (height is set by IssuesCardList via setFixedHeight(CARD_HEIGHT_PX()))
        log.debug(f"The IssueCard for {issue['key']} is initialized")


    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.url)
        super().mousePressEvent(e)

    # -------- helpers
    def _due_text(self, iso: str | None) -> str:
        if not iso:
            return "No due"
        return f"Due {iso}"

    def _due_state(self, iso: str | None) -> str:
        if not iso:
            return "none"
        from datetime import datetime, date, timedelta
        try:
            d = datetime.fromisoformat(iso).date()
        except Exception:
            return "none"
        today = date.today()
        if d < today:
            return "overdue"
        if d == today:
            return "today"
        if d == today + timedelta(days=1):
            return "tomorrow"
        return "future"

    def _status_state(self, name: str) -> str:
        n = (name or "").strip().lower()
        if n in {"done", "resolved", "closed", "accepted"}:
            return "done"
        if n in {"in progress", "implementing", "in review"}:
            return "inprogress"
        if n in {"to do", "todo", "backlog", "open"}:
            return "todo"
        return "other"

class IssuesCardList(QtWidgets.QWidget):
    openLink = QtCore.pyqtSignal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.label = QtWidgets.QLabel(f"<b>{title}</b>")

        self.container = QtWidgets.QWidget()
        self.vbox = QtWidgets.QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(GAP_PX())

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.container)

        self.show_more_btn = QtWidgets.QPushButton("Show more")
        self.show_more_btn.setFixedHeight(SHOW_MORE_H_PX())
        self.show_more_btn.setVisible(False)
        self.show_more_btn.clicked.connect(self._open_more)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.setSpacing(GAP_PX())
        lay.addWidget(self.label)
        lay.addWidget(self.scroll)
        lay.addWidget(self.show_more_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        # <<< HERE: fixed sizes for block and visible window for 2 cards >>>
        self.setFixedWidth(BLOCK_WIDTH_PX())
        self.setFixedHeight(BLOCK_HEIGHT_PX())
        self.scroll.setMinimumHeight(CARD_HEIGHT_PX()*2 + GAP_PX())
        self.scroll.setMaximumHeight(CARD_HEIGHT_PX()*2 + GAP_PX())

        self._more_url = None
        self._url_builder = None
        log.debug(f"The IssueCardList for {title} is initialized")

    def _clear_cards(self):
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    def set_issues(self, issues: list[dict], more_url: str | None, url_builder):
        self._clear_cards()
        self._more_url = more_url
        self._url_builder = url_builder
        self.show_more_btn.setVisible(bool(more_url))

        # exactly 2 cards
        for it in issues[:2]:
            card = IssueCard(it, url_builder)
            card.setFixedHeight(CARD_HEIGHT_PX())   # <<< HERE: fixed card height >>>
            card.clicked.connect(self.openLink.emit)
            self.vbox.addWidget(card)

        self.vbox.addStretch(1)

    def _open_more(self):
        if self._more_url:
            self.openLink.emit(self._more_url)

class TodayPopup(QtWidgets.QDialog):
    def __init__(self, issues: list[dict], more_url: str, url_builder, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Today's tasks")
        # small tool window without resize
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.Tool)
        self.setModal(False)

        # Content: same block as in main window
        self.block = IssuesCardList("Today", self)
        # fixed block size is already set inside IssuesCardList,
        # add thin padding around window edges
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(GAP_PX(), GAP_PX(), GAP_PX(), GAP_PX())
        outer.setSpacing(0)
        outer.addWidget(self.block)

        # click on card/Show more → open browser
        self.block.openLink.connect(lambda url: __import__("webbrowser").open(url))

        # fill with two cards + "Show more"
        self.block.set_issues(issues, more_url, url_builder)

        # make window fixed size (like larger blocks)
        win_w = BLOCK_WIDTH_PX() + GAP_PX()*2
        win_h = BLOCK_HEIGHT_PX() + GAP_PX()*2
        self.setFixedSize(win_w, win_h)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app_icon: QtGui.QIcon, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon)
        self.resize(880, 600)

        self.setStyleSheet("""
            QFrame#Card { border: 1px solid #3a3f44; background: #1e1f24; border-radius: 12px; }
            QFrame#Card[state="overdue"]   { border-color: #ff6b6b; }
            QFrame#Card[state="today"]     { border-color: #ffd166; }
            QFrame#Card[state="tomorrow"]  { border-color: #06d6a0; }

            QLabel#Summary { color: palette(text); }

            /* Badges */
            QLabel[badge="true"] {
                padding: 2px 8px;
                border-radius: 10px;
                background: #2b3036;
                color: #c9d1d9;
            }

            /* Due pill */
            QLabel#DuePill[state="overdue"]  { background: #3a0f0f; color: #ff9b9b; padding: 2px 8px; border-radius: 10px; }
            QLabel#DuePill[state="today"]    { background: #3a2e0f; color: #ffd166; padding: 2px 8px; border-radius: 10px; }
            QLabel#DuePill[state="tomorrow"] { background: #103528; color: #06d6a0; padding: 2px 8px; border-radius: 10px; }
            QLabel#DuePill[state="future"],
            QLabel#DuePill[state="none"]     { background: #2b3036; color: #9aa5b1; padding: 2px 8px; border-radius: 10px; }

            /* Priority variants (dynamic level property) */
            QLabel#PriorityBadge[level="Highest"] { background: #3a0f0f; color: #ff9b9b; }
            QLabel#PriorityBadge[level="High"]    { background: #3a220f; color: #ffb27a; }
            QLabel#PriorityBadge[level="Medium"]  { background: #243248; color: #8ab8ff; }
            QLabel#PriorityBadge[level="Low"]     { background: #123a22; color: #5ad1a0; }
            QLabel#PriorityBadge[level="Lowest"]  { background: #2b3036; color: #aab2bd; }

            /* Status variants */
            QLabel#StatusBadge[state="done"]       { background: #103528; color: #06d6a0; }
            QLabel#StatusBadge[state="inprogress"] { background: #20324a; color: #8ab8ff; }
            QLabel#StatusBadge[state="todo"]       { background: #3a2e0f; color: #ffd166; }
            QLabel#StatusBadge[state="other"]      { background: #2b3036; color: #c9d1d9; }

            /* Buttons */
            QPushButton { padding: 6px 12px; border-radius: 8px; }
            """)


        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        grid = QtWidgets.QGridLayout(central)

        self.overdue = IssuesCardList("Overdue")
        self.today = IssuesCardList("Today")
        self.tomorrow = IssuesCardList("Tomorrow")


        for w in (self.overdue, self.today, self.tomorrow):
            w.openLink.connect(lambda url: __import__("webbrowser").open(url))

        grid.addWidget(self.overdue, 0, 0)
        grid.addWidget(self.today, 0, 1)
        grid.addWidget(self.tomorrow, 1, 0, 1, 2)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        grid.addWidget(self.refresh_btn, 2, 1, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        # layout paddings
        grid.setHorizontalSpacing(GAP_PX())
        grid.setVerticalSpacing(GAP_PX())
        grid.setContentsMargins(GAP_PX(), GAP_PX(), GAP_PX(), GAP_PX())

        # Place blocks in a 2x2 grid; Tomorrow sits bottom-left (no spanning)
        grid.addWidget(self.overdue, 0, 0)
        grid.addWidget(self.today,   0, 1)
        grid.addWidget(self.tomorrow,1, 0)

        # spacer to balance bottom-right cell
        grid.addItem(QtWidgets.QSpacerItem(BLOCK_WIDTH_PX(), BLOCK_HEIGHT_PX(),
                                        QtWidgets.QSizePolicy.Policy.Fixed,
                                        QtWidgets.QSizePolicy.Policy.Fixed), 1, 1)

        # Fixed window size from metrics
        win_w = BLOCK_WIDTH_PX()*2 + GAP_PX()*3      # 2 blocks + internal gaps + margins
        win_h = BLOCK_HEIGHT_PX()*2 + GAP_PX()*3     # 2 rows + internal gaps + margins
        self.setFixedSize(win_w, win_h)


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
        # Get system double-click interval, fallback to 300ms
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
        log.debug("The JireReminderController is initialized")

    def _load_icon(self) -> QtGui.QIcon:
        """
        Searches for icon in assets/ for dev and PyInstaller onefile.
        On Windows - priority for .ico, on Linux - .png. Has safe fallback icon.
        """
        # Priority order depending on platform
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

        # Fallback: draw a simple icon
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
                                          "No tasks completed today. Choose at least one and get it to Done 💪",
                                          QtWidgets.QSystemTrayIcon.MessageIcon.Information, 10_000)

    def check_today_and_notify(self):
        try:
            jql_today = self.client.jql_for_day(self.cfg["assignee_email"], "today")
            self.today_issues = self.client.search(jql_today, max_results=10)
            if self.today_issues:
                items = "\n".join([f"{x['key']}: {x['summary']}" for x in self.today_issues[:5]])
                self.tray.showMessage(APP_NAME, f"Today's tasks:\n{items}",
                                      QtWidgets.QSystemTrayIcon.MessageIcon.Information, 12_000)
        except Exception as e:
            log.exception("check_today_and_notify failed")
            self.tray.showMessage(APP_NAME, f"Update error: {e}",
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
                self.tray.showMessage(APP_NAME, "Data updated",
                                      QtWidgets.QSystemTrayIcon.MessageIcon.Information, 3000)
        except requests.HTTPError as e:
            log.exception("JIRA HTTP error during refresh")
            self.tray.showMessage(APP_NAME, f"JIRA HTTP error: {e}",
                                  QtWidgets.QSystemTrayIcon.MessageIcon.Critical, 8000)
        except Exception as e:
            log.exception("Unexpected error during refresh")
            self.tray.showMessage(APP_NAME, f"Error: {e}",
                                  QtWidgets.QSystemTrayIcon.MessageIcon.Critical, 8000)

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
            self.tray.showMessage(APP_NAME, f"Error: {e}",
                                QtWidgets.QSystemTrayIcon.MessageIcon.Critical, 8000)


    def _tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            # start single click timer; if DoubleClick arrives - we'll cancel it
            if self._click_timer.isActive():
                self._click_timer.stop()
            self._click_timer.start()
        elif reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            # double click - cancel single-click and show main window
            if self._click_timer.isActive():
                self._click_timer.stop()
            self.show_main()

class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self._hspace = hspacing
        self._vspace = vspacing

    def addItem(self, item): self._items.append(item)
    def count(self): return len(self._items)
    def itemAt(self, i): return self._items[i] if 0 <= i < len(self._items) else None
    def takeAt(self, i): return self._items.pop(i) if 0 <= i < len(self._items) else None
    def expandingDirections(self): return QtCore.Qt.Orientation(0)
    def hasHeightForWidth(self): return True

    def heightForWidth(self, width):
        return self._doLayout(QtCore.QRect(0,0,width,0), testOnly=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._doLayout(rect, testOnly=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QtCore.QSize(0, 0)
        m = self.contentsMargins()
        for i in range(self.count()):
            item = self._items[i]
            s = s.expandedTo(item.sizeHint())
        s += QtCore.QSize(m.left()+m.right(), m.top()+m.bottom())
        return s

    def _doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        m = self.contentsMargins()
        effectiveRect = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effectiveRect.x()
        y = effectiveRect.y()
        lineHeight = 0

        for item in self._items:
            wid = item.widget()
            spaceX = self._hspace
            spaceY = self._vspace
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > effectiveRect.right() and lineHeight > 0:
                x = effectiveRect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0
            if not testOnly:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y() + m.bottom()


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
    parser.add_argument("--new-log", action="store_true", help="Create new log file instead of appending")
    parser.add_argument("--ui-scale", dest="ui_scale", type=float, default=1.25, metavar="X", help="UI scale factor (e.g. 1.25 for 125%%)")

    args = parser.parse_args()

    setup_logging(args.logging, args.new_log)
    log.debug("App start %s v%s", APP_NAME, __version__)

    # after setup_logging(args.logging):
    global UI_SCALE
    UI_SCALE = max(0.75, min(2.5, args.ui_scale))  # clamp between 0.75x..2.5x

    # apply to default font so text scales too
    # font = QtGui.QFont()
    # font.setPointSizeF(max(8.0, font.pointSizeF() * UI_SCALE))
    
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
    lock = ensure_single_instance_or_exit()
    log.debug("Single instance lock acquired: %s", lock.fileName())
    font = app.font()                      # current system font family
    ps = font.pointSizeF()
    if ps <= 0:                            # if in pixels/undefined - use base 12pt
        ps = 12.0
    font.setPointSizeF(max(7.5, ps * UI_SCALE))
    app.setFont(font)
    app.setQuitOnLastWindowClosed(False) 
    log.debug("QApplication initialized with UI scale %.2fx", UI_SCALE)
    ctrl = JiraReminderController(app, cfg)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
# EOF