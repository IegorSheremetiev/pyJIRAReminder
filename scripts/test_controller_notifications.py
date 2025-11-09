# scripts/test_controller_notifications.py
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, date, time as dtime

from PyQt6 import QtWidgets

# Додаємо корінь проєкту в sys.path, щоб можна було імпортувати pyJIRAReminder
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyJIRAReminder as appmod  # головний модуль з JiraReminderController


APP_NAME = "Jira Reminder TEST"


class FakeTray:
    """
    Простий замінник QSystemTrayIcon для тестів.
    Лише збирає всі показані повідомлення.
    """
    def __init__(self):
        self.messages: list[tuple[str, str, object, int]] = []

    def showMessage(self, title, text, icon=None, msec=0):
        self.messages.append((title, text, icon, msec))


class FakeJiraClient:
    """
    Фейковий JiraClient з тим самим API, який очікує JiraReminderController.
    НІЯКИХ HTTP-запитів, тільки контрольовані відповіді.
    """
    def __init__(self, base_url, email, api_token, projects, issue_types, start_date_field, done_jql_override=None):
        self.base_url = base_url
        self.email = email
        self.api_token = api_token
        self.projects = projects
        self.issue_types = issue_types
        self.start_date_field = start_date_field
        self.done_jql_override = done_jql_override

        # Налаштовувані відповіді для тестів
        self.today_issues_to_return = []
        self.closed_today_issues_to_return = []

        # Лічильники викликів для перевірок
        self.jql_for_day_calls: list[tuple[str, str]] = []
        self.jql_closed_today_calls: list[str] = []
        self.jql_overdue_calls: list[str] = []
        self.search_calls: list[tuple[str, int]] = []
        self.make_issues_link_calls: list[str] = []
        self.make_issue_url_calls: list[str] = []

    # --- API, яке використовує контролер ---

    def jql_for_day(self, assignee_email: str, which: str) -> str:
        """
        Викликається для today/tomorrow (і, можливо, інших day-based JQL).
        """
        self.jql_for_day_calls.append((assignee_email, which))
        return f"JQL-{which}"

    def jql_closed_today(self, assignee_email: str) -> str:
        """
        Викликається у _has_closed_today().
        """
        self.jql_closed_today_calls.append(assignee_email)
        return "JQL-CLOSED-TODAY"

    def jql_overdue(self, assignee_email: str) -> str:
        """
        Викликається у refresh_all() для overdue задач.
        """
        self.jql_overdue_calls.append(assignee_email)
        return "JQL-OVERDUE"

    def search(self, jql: str, max_results: int = 50):
        """
        Емуляція пошуку. Ми реагуємо тільки на наші штучні JQL-рядки.
        Все інше повертає порожній список.
        """
        self.search_calls.append((jql, max_results))

        if jql.startswith("JQL-today"):
            return list(self.today_issues_to_return)

        if jql == "JQL-CLOSED-TODAY":
            return list(self.closed_today_issues_to_return)

        # OVERDUE, TOMORROW, etc. для наших тестів можна повертати пусто
        return []

    def make_issues_link(self, jql: str, wrap_login: bool = True, modern: bool = True) -> str:
        """
        Викликається для кнопок 'Show more' у вікні.
        Для тестів важливий лише факт виклику і те, що повертається валідний рядок.
        """
        self.make_issues_link_calls.append(jql)
        # достатньо стабльного, але умовного URL
        return f"{self.base_url}/jira/search?jql={jql}"

    def make_issue_url(self, key: str) -> str:
        """
        Викликається при побудові посилань на конкретні задачі.
        """
        self.make_issue_url_calls.append(key)
        return f"{self.base_url}/browse/{key}"

    # для зручності в тестах
    def reset_counters(self):
        self.jql_for_day_calls.clear()
        self.jql_closed_today_calls.clear()
        self.jql_overdue_calls.clear()
        self.search_calls.clear()
        self.make_issues_link_calls.clear()
        self.make_issue_url_calls.clear()



def create_controller_for_test():
    """
    Створює реальний JiraReminderController, але:
    - патчить JiraClient на FakeJiraClient;
    - зупиняє внутрішній tick-таймер;
    - підміняє tray на FakeTray.

    Повертає: (controller, fake_tray, fake_client).
    """
    # 1) Переконаємось, що є QApplication
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    # 2) Патчимо JiraClient у модулі на наш FakeJiraClient
    appmod.JiraClient = FakeJiraClient

    # 3) Мінімальна конфігурація (значення неважливі — нікуди не йдуть)
    cfg = {
        "jira_base_url": "https://example.atlassian.net",
        "assignee_email": "user@example.com",
        "api_token": "dummy-token",
        "project_keys": ["TEST"],
        "issue_types": ["Sub-task - HW"],
        "start_date_field": "customfield_10015",
        "done_jql": None,
    }

    ctrl = appmod.JiraReminderController(app, cfg)

    # 4) Зупиняємо внутрішній таймер, щоб він не бігав у тестах
    if hasattr(ctrl, "tick"):
        ctrl.tick.stop()

    # 5) Ховаємо реальний tray-ікон, щоб не миготіла іконка під час тестів
    real_tray = ctrl.tray
    try:
        real_tray.hide()
    except Exception:
        pass

    fake_tray = FakeTray()
    ctrl.tray = fake_tray

    # 6) Дістаємо фейкового клієнта
    fake_client = ctrl.client
    if not isinstance(fake_client, FakeJiraClient):
        raise RuntimeError("Expected FakeJiraClient, got something else")

    # Обнуляємо лічильники після initial refresh_all
    fake_client.reset_counters()
    fake_tray.messages.clear()
    ctrl._last_close_check = None

    return ctrl, fake_tray, fake_client


# ===== Тест-кейси =====

def test_morning_popup_when_tasks_exist():
    print("=== test_morning_popup_when_tasks_exist ===")
    ctrl, tray, client = create_controller_for_test()
    today = date(2025, 11, 9)

    # Налаштовуємо: є задачі на сьогодні
    client.today_issues_to_return = [
        {"key": "ABC-1", "summary": "First task"},
        {"key": "ABC-2", "summary": "Second task"},
        {"key": "ABC-3", "summary": "Third task"},
    ]

    # 09:59 – не повинно нічого статися
    ctrl._on_tick_at(datetime.combine(today, dtime(9, 59)))
    assert client.jql_for_day_calls == [], "До 10:00 не повинно бути jql_for_day"
    assert tray.messages == [], "До 10:00 не повинно бути сповіщень"

    # 10:00 – очікуємо 1 JQL + 1 popup
    ctrl._on_tick_at(datetime.combine(today, dtime(10, 0)))
    assert len(client.jql_for_day_calls) == 1, "О 10:00 має бути один виклик jql_for_day('today')"
    assert len(tray.messages) == 1, "О 10:00 має бути одне сповіщення"
    assert "Today's tasks" in tray.messages[0][1]

    # 10:05 – не потрапляє у (0,1) → нічого нового
    ctrl._on_tick_at(datetime.combine(today, dtime(10, 5)))
    assert len(client.jql_for_day_calls) == 1, "Після 10:01 не має бути додаткових jql_for_day"
    assert len(tray.messages) == 1, "І нових сповіщень теж"


def test_morning_no_tasks_no_popup():
    print("=== test_morning_no_tasks_no_popup ===")
    ctrl, tray, client = create_controller_for_test()
    today = date(2025, 11, 9)

    # Нема задач
    client.today_issues_to_return = []

    ctrl._on_tick_at(datetime.combine(today, dtime(10, 0)))
    assert len(client.jql_for_day_calls) == 1, "О 10:00 JQL все одно викликається"
    assert len(tray.messages) == 0, "Але без задач сповіщення не показується"


def test_evening_interval_and_stop_when_closed():
    print("=== test_evening_interval_and_stop_when_closed ===")
    ctrl, tray, client = create_controller_for_test()
    today = date(2025, 11, 9)

    # Спочатку нічого не закрито
    client.closed_today_issues_to_return = []

    # 16:29 – поза вікном
    ctrl._on_tick_at(datetime.combine(today, dtime(16, 29)))
    assert len(client.jql_closed_today_calls) == 0, "До 16:30 не викликаємо jql_closed_today"
    assert len(tray.messages) == 0

    # 16:30 – перша перевірка
    ctrl._on_tick_at(datetime.combine(today, dtime(16, 30)))
    assert len(client.jql_closed_today_calls) == 1, "О 16:30 має бути виклик jql_closed_today"
    assert len(tray.messages) == 1, "Має бути перше сповіщення"

    # 16:40 – ще немає 30 хв, не повинно бути нового виклику
    ctrl._on_tick_at(datetime.combine(today, dtime(16, 40)))
    assert len(client.jql_closed_today_calls) == 1, "До +30 хв не повторюємо перевірку"
    assert len(tray.messages) == 1

    # 17:01 – минуло >30 хв, ще нічого не закрито → ще одне сповіщення
    ctrl._on_tick_at(datetime.combine(today, dtime(17, 1)))
    assert len(client.jql_closed_today_calls) == 2, "Після +30 хв має бути друга перевірка"
    assert len(tray.messages) == 2, "І друге сповіщення"

    # Тепер уявімо, що задачу закрили
    client.closed_today_issues_to_return = [{"key": "ABC-99"}]

    # 17:40 – перевірка є, але popup вже НЕ має бути
    ctrl._on_tick_at(datetime.combine(today, dtime(17, 40)))
    assert len(client.jql_closed_today_calls) == 3, "Має бути третя перевірка"
    assert len(tray.messages) == 2, "Але кількість сповіщень не збільшується після закриття задачі"


def run_all():
    test_morning_popup_when_tasks_exist()
    test_morning_no_tasks_no_popup()
    test_evening_interval_and_stop_when_closed()
    print("\033[1m\033[42m\033[30m ALL CONTROLLER NOTIFICATION TESTS PASSED \033[0m")


if __name__ == "__main__":
    run_all()
