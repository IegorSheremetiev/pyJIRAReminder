# src/jira_reminder/ui.py
from __future__ import annotations

from datetime import datetime, date, timedelta

from PyQt6 import QtWidgets, QtGui, QtCore

from .metrics import (
    S,
    BLOCK_WIDTH_PX,
    BLOCK_HEIGHT_PX,
    CARD_HEIGHT_PX,
    GAP_PX,
    SHOW_MORE_H_PX,
    APP_NAME,
)
from .logging_setup import log


class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
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
        return self._doLayout(QtCore.QRect(0, 0, width, 0), testOnly=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._doLayout(rect, testOnly=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QtCore.QSize(0, 0)
        m = self.contentsMargins()
        for item in self._items:
            s = s.expandedTo(item.sizeHint())
        s += QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())
        return s

    def _doLayout(self, rect, testOnly):
        m = self.contentsMargins()
        effectiveRect = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effectiveRect.x()
        y = effectiveRect.y()
        lineHeight = 0

        for item in self._items:
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


class IssueCard(QtWidgets.QFrame):
    clicked = QtCore.pyqtSignal(str)  # url

    def __init__(self, issue: dict, url_builder, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 140))
        self.setGraphicsEffect(shadow)

        self.issue = issue
        self.url = url_builder(issue["key"])

        key_lbl = QtWidgets.QLabel(f"<b>{issue['key']}</b>")
        key_lbl.setTextFormat(QtCore.Qt.TextFormat.RichText)
        key_lbl.setToolTip(issue.get("summary") or "")

        summary = QtWidgets.QLabel(issue.get("summary") or "(no summary)")
        summary.setWordWrap(True)
        summary.setObjectName("Summary")
        summary.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        due = issue.get("duedate")
        due_lbl = QtWidgets.QLabel(self._due_text(due))
        due_state = self._due_state(due)
        due_lbl.setObjectName("DuePill")
        due_lbl.setProperty("state", due_state)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(key_lbl)
        top.addStretch(1)
        top.addWidget(due_lbl)

        itype = issue.get("issuetype") or "Issue"
        prio = (issue.get("priority") or "").strip() or "—"
        stat = (issue.get("status") or "").strip() or "—"

        badges = FlowLayout(hspacing=S(6), vspacing=S(6))

        def _badge(text, objname, **props):
            lbl = QtWidgets.QLabel(text)
            lbl.setObjectName(objname)
            lbl.setProperty("badge", True)
            for k, v in props.items():
                lbl.setProperty(k, v)
            return lbl

        badges.addWidget(_badge(itype, "TypeBadge"))
        badges.addWidget(_badge(f"Priority: {prio}", "PriorityBadge", level=prio))
        badges.addWidget(_badge(f"Status: {stat}", "StatusBadge", state=self._status_state(stat)))

        badges.addItem(
            QtWidgets.QSpacerItem(
                0,
                0,
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Minimum,
            )
        )

        btn_open = QtWidgets.QPushButton("Open")
        btn_open.clicked.connect(lambda: self.clicked.emit(self.url))
        actions = QtWidgets.QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(btn_open)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        lay.addLayout(top)
        lay.addWidget(summary)
        lay.addLayout(badges)
        lay.addLayout(actions)

        self.setProperty("state", due_state)

        sp = self.sizePolicy()
        sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Expanding)
        sp.setVerticalPolicy(QtWidgets.QSizePolicy.Policy.Fixed)
        self.setSizePolicy(sp)

        log.debug(f"The IssueCard for {issue['key']} is initialized")

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.url)
        super().mousePressEvent(e)

    def _due_text(self, iso: str | None) -> str:
        if not iso:
            return "No due"
        return f"Due {iso}"

    def _due_state(self, iso: str | None) -> str:
        if not iso:
            return "none"
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
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GAP_PX())
        lay.addWidget(self.label)
        lay.addWidget(self.scroll)
        lay.addWidget(self.show_more_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        self.setFixedWidth(BLOCK_WIDTH_PX())
        self.setFixedHeight(BLOCK_HEIGHT_PX())
        self.scroll.setMinimumHeight(CARD_HEIGHT_PX() * 2 + GAP_PX())
        self.scroll.setMaximumHeight(CARD_HEIGHT_PX() * 2 + GAP_PX())

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

        for it in issues[:2]:
            card = IssueCard(it, url_builder)
            card.setFixedHeight(CARD_HEIGHT_PX())
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
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.Tool)
        self.setModal(False)

        self.block = IssuesCardList("Today", self)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(GAP_PX(), GAP_PX(), GAP_PX(), GAP_PX())
        outer.setSpacing(0)
        outer.addWidget(self.block)

        self.block.openLink.connect(lambda url: __import__("webbrowser").open(url))

        self.block.set_issues(issues, more_url, url_builder)

        win_w = BLOCK_WIDTH_PX() + GAP_PX() * 2
        win_h = BLOCK_HEIGHT_PX() + GAP_PX() * 2
        self.setFixedSize(win_w, win_h)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app_icon: QtGui.QIcon, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon)
        self.resize(880, 600)

        self.setStyleSheet(
            """
            QFrame#Card { border: 1px solid #3a3f44; background: #1e1f24; border-radius: 12px; }
            QFrame#Card[state="overdue"]   { border-color: #ff6b6b; }
            QFrame#Card[state="today"]     { border-color: #ffd166; }
            QFrame#Card[state="tomorrow"]  { border-color: #06d6a0; }

            QLabel#Summary { color: palette(text); }

            QLabel[badge="true"] {
                padding: 2px 8px;
                border-radius: 10px;
                background: #2b3036;
                color: #c9d1d9;
            }

            QLabel#DuePill[state="overdue"]  { background: #3a0f0f; color: #ff9b9b; padding: 2px 8px; border-radius: 10px; }
            QLabel#DuePill[state="today"]    { background: #3a2e0f; color: #ffd166; padding: 2px 8px; border-radius: 10px; }
            QLabel#DuePill[state="tomorrow"] { background: #103528; color: #06d6a0; padding: 2px 8px; border-radius: 10px; }
            QLabel#DuePill[state="future"],
            QLabel#DuePill[state="none"]     { background: #2b3036; color: #9aa5b1; padding: 2px 8px; border-radius: 10px; }

            QLabel#PriorityBadge[level="Highest"] { background: #3a0f0f; color: #ff9b9b; }
            QLabel#PriorityBadge[level="High"]    { background: #3a220f; color: #ffb27a; }
            QLabel#PriorityBadge[level="Medium"]  { background: #243248; color: #8ab8ff; }
            QLabel#PriorityBadge[level="Low"]     { background: #123a22; color: #5ad1a0; }
            QLabel#PriorityBadge[level="Lowest"]  { background: #2b3036; color: #aab2bd; }

            QLabel#StatusBadge[state="done"]       { background: #103528; color: #06d6a0; }
            QLabel#StatusBadge[state="inprogress"] { background: #20324a; color: #8ab8ff; }
            QLabel#StatusBadge[state="todo"]       { background: #3a2e0f; color: #ffd166; }
            QLabel#StatusBadge[state="other"]      { background: #2b3036; color: #c9d1d9; }

            QPushButton { padding: 6px 12px; border-radius: 8px; }
            """
        )

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

        grid.setHorizontalSpacing(GAP_PX())
        grid.setVerticalSpacing(GAP_PX())
        grid.setContentsMargins(GAP_PX(), GAP_PX(), GAP_PX(), GAP_PX())

        grid.addWidget(self.overdue, 0, 0)
        grid.addWidget(self.today, 0, 1)
        grid.addWidget(self.tomorrow, 1, 0)

        grid.addItem(
            QtWidgets.QSpacerItem(
                BLOCK_WIDTH_PX(),
                BLOCK_HEIGHT_PX(),
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            ),
            1,
            1,
        )

        win_w = BLOCK_WIDTH_PX() * 2 + GAP_PX() * 3
        win_h = BLOCK_HEIGHT_PX() * 2 + GAP_PX() * 3
        self.setFixedSize(win_w, win_h)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        event.ignore()
        self.hide()


class SecureConfigDialog(QtWidgets.QDialog):
    """Dialog to edit the encrypted (secure) configuration portion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Secure configuration")

        from .paths import CONFIG_ENC_PATH
        from .security import decrypt_config

        self.base_url = QtWidgets.QLineEdit()
        self.email = QtWidgets.QLineEdit()
        self.api_token = QtWidgets.QLineEdit()
        self.api_token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.projects = QtWidgets.QLineEdit()
        self.issue_types = QtWidgets.QLineEdit()
        self.start_date_field = QtWidgets.QLineEdit()
        self.done_jql = QtWidgets.QLineEdit()

        form = QtWidgets.QFormLayout()
        form.addRow("JIRA base URL:", self.base_url)
        form.addRow("Assignee email:", self.email)
        form.addRow("JIRA API token:", self.api_token)
        form.addRow("Project keys (comma-separated):", self.projects)
        form.addRow("Issue types (comma-separated):", self.issue_types)
        form.addRow("Start date field:", self.start_date_field)
        form.addRow("Custom 'closed today' JQL:", self.done_jql)

        btn_ok = QtWidgets.QPushButton("Save")
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)

        outer = QtWidgets.QVBoxLayout(self)
        outer.addLayout(form)
        outer.addLayout(btns)

        # try to pre-load if encrypted config exists
        try:
            if CONFIG_ENC_PATH.exists():
                data = CONFIG_ENC_PATH.read_bytes()
                cfg = decrypt_config(data)
                self.base_url.setText(cfg.get("jira_base_url", ""))
                self.email.setText(cfg.get("assignee_email", ""))
                # don't pre-fill api_token for security, leave empty
                self.projects.setText(", ".join(cfg.get("project_keys", [])))
                self.issue_types.setText(", ".join(cfg.get("issue_types", [])))
                self.start_date_field.setText(cfg.get("start_date_field", "customfield_10015"))
                self.done_jql.setText(cfg.get("done_jql") or "")
        except Exception:
            # ignore decryption errors here
            pass

    def get_values(self) -> dict:
        return {
            "jira_base_url": self.base_url.text().strip(),
            "assignee_email": self.email.text().strip(),
            "api_token": self.api_token.text().strip() or None,
            "project_keys": [x.strip() for x in self.projects.text().split(",") if x.strip()],
            "issue_types": [x.strip() for x in self.issue_types.text().split(",") if x.strip()],
            "start_date_field": self.start_date_field.text().strip() or "customfield_10015",
            "done_jql": self.done_jql.text().strip() or None,
        }


class ConfigDialog(QtWidgets.QDialog):
    """Main configuration dialog. Non-secure settings live in a plain JSON file; secure settings are optional and edited via SecureConfigDialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jira Reminder — Configuration")

        import json
        from .paths import CONFIG_PLAIN_PATH

        self.chk_logging = QtWidgets.QCheckBox("Enable DEBUG logging")
        self.chk_new_log = QtWidgets.QCheckBox("Create new log file on start")
        self.spin_ui = QtWidgets.QDoubleSpinBox()
        self.spin_ui.setRange(0.5, 3.0)
        self.spin_ui.setSingleStep(0.05)
        self.spin_ui.setValue(1.25)

        btn_edit_secure = QtWidgets.QPushButton("Edit secure settings...")
        btn_edit_secure.clicked.connect(self._open_secure)

        btn_save = QtWidgets.QPushButton("Save")
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self.reject)

        form = QtWidgets.QFormLayout()
        form.addRow(self.chk_logging)
        form.addRow(self.chk_new_log)
        form.addRow("UI scale:", self.spin_ui)
        form.addRow(btn_edit_secure)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)

        outer = QtWidgets.QVBoxLayout(self)
        outer.addLayout(form)
        outer.addLayout(btns)

        # load plain config if present
        try:
            if CONFIG_PLAIN_PATH.exists():
                data = json.loads(CONFIG_PLAIN_PATH.read_text(encoding="utf-8"))
                self.chk_logging.setChecked(bool(data.get("logging", False)))
                self.chk_new_log.setChecked(bool(data.get("new_log", False)))
                self.spin_ui.setValue(float(data.get("ui_scale", 1.25)))
        except Exception:
            pass

    def _open_secure(self):
        dlg = SecureConfigDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            vals = dlg.get_values()
            # write encrypted config
            from .security import encrypt_config
            from .paths import CONFIG_ENC_PATH
            try:
                CONFIG_ENC_PATH.write_bytes(encrypt_config(vals))
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save secure config: {e}")

    def _on_save(self):
        import json
        from .paths import CONFIG_PLAIN_PATH

        plain = {
            "logging": bool(self.chk_logging.isChecked()),
            "new_log": bool(self.chk_new_log.isChecked()),
            "ui_scale": float(self.spin_ui.value()),
        }
        try:
            CONFIG_PLAIN_PATH.write_text(json.dumps(plain, ensure_ascii=False, indent=2), encoding="utf-8")
            # apply UI scale immediately
            try:
                # update global UI scale
                from .metrics import set_ui_scale, UI_SCALE, BLOCK_WIDTH_PX, BLOCK_HEIGHT_PX, GAP_PX, CARD_HEIGHT_PX
                set_ui_scale(plain["ui_scale"])
                app = QtWidgets.QApplication.instance()
                if app:
                    # update application font
                    font = app.font()
                    ps = font.pointSizeF()
                    if ps <= 0:
                        ps = 12.0
                    font.setPointSizeF(max(7.5, ps * UI_SCALE))
                    app.setFont(font)

                    # Full immediate re-layout: iterate all widgets and update sizes/polish
                    try:
                        for w in app.allWidgets():
                            try:
                                w.setFont(font)
                            except Exception:
                                pass

                            # Adjust known components that use fixed sizes based on metrics
                            try:
                                # MainWindow: recompute fixed size
                                if isinstance(w, MainWindow):
                                    win_w = BLOCK_WIDTH_PX() * 2 + GAP_PX() * 3
                                    win_h = BLOCK_HEIGHT_PX() * 2 + GAP_PX() * 3
                                    w.setFixedSize(win_w, win_h)
                            except Exception:
                                pass

                            try:
                                # IssuesCardList uses fixed width/height
                                if isinstance(w, IssuesCardList):
                                    w.setFixedWidth(BLOCK_WIDTH_PX())
                                    w.setFixedHeight(BLOCK_HEIGHT_PX())
                                    # update scroll limits
                                    w.scroll.setMinimumHeight(CARD_HEIGHT_PX() * 2 + GAP_PX())
                                    w.scroll.setMaximumHeight(CARD_HEIGHT_PX() * 2 + GAP_PX())
                            except Exception:
                                pass

                            try:
                                # IssueCard: adjust fixed height
                                if isinstance(w, IssueCard):
                                    w.setFixedHeight(CARD_HEIGHT_PX())
                            except Exception:
                                pass

                            # trigger style polish and geometry updates
                            try:
                                w.style().unpolish(w)
                                w.style().polish(w)
                                w.updateGeometry()
                                w.update()
                            except Exception:
                                pass
                    except Exception:
                        # be resilient: don't fail saving on re-layout errors
                        pass
            except Exception:
                # don't block saving on UI-scale application errors
                pass

            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save config: {e}")

    @staticmethod
    def load_combined() -> dict:
        """Return combined configuration dict by reading encrypted config (if present) and overlaying plain settings."""
        import json
        from .paths import CONFIG_PLAIN_PATH, CONFIG_ENC_PATH
        from .security import decrypt_config

        plain = {}
        try:
            if CONFIG_PLAIN_PATH.exists():
                plain = json.loads(CONFIG_PLAIN_PATH.read_text(encoding="utf-8"))
        except Exception:
            plain = {}

        secure = {}
        try:
            if CONFIG_ENC_PATH.exists():
                secure = decrypt_config(CONFIG_ENC_PATH.read_bytes())
        except Exception:
            secure = {}

        # combine: secure keys take precedence for JIRA-related fields
        res = {**plain, **secure}
        return res
