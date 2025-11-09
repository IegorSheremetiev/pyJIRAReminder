# src/jira_reminder/metrics.py
from __future__ import annotations

APP_NAME = "Jira Reminder"
__version__ = "0.9.3"  # x-release-please-version

# --- UI scaling & metrics ---

UI_SCALE: float = 1.0  # буде оновлено в app.main() згідно з аргументом --ui-scale


def set_ui_scale(value: float) -> None:
    """
    Оновлює глобальний масштаб UI з обмеженнями [0.75; 2.5].
    """
    global UI_SCALE
    UI_SCALE = max(0.75, min(2.5, float(value)))


def S(px: float) -> int:
    """Scale helper."""
    return int(round(px * UI_SCALE))


BLOCK_WIDTH_PX  = lambda: S(450)   # 2x cards у ширину
CARD_HEIGHT_PX  = lambda: S(150)
GAP_PX          = lambda: S(12)
HEADER_H_PX     = lambda: S(24)
SHOW_MORE_H_PX  = lambda: S(28)
BLOCK_HEIGHT_PX = lambda: HEADER_H_PX() + GAP_PX() + (CARD_HEIGHT_PX()*2) + GAP_PX() + SHOW_MORE_H_PX()
