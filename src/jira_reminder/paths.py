# src/jira_reminder/paths.py
from __future__ import annotations

import os
import sys
import pathlib

MAGIC = b"JRM1"  # file header


def _base_path() -> str:
    """
    Base dir for assets.

    - In PyInstaller onefile: sys._MEIPASS (inside the bundled dir where `assets/` lives).
    - In dev mode: walk upwards from this file until we find a directory containing `assets/`.
    """
    # PyInstaller case
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass

    # Dev mode: search upwards
    here = pathlib.Path(__file__).resolve()

    # check this dir and all parents
    for cand in [here.parent, *here.parents]:
        assets_dir = cand / "assets"
        if assets_dir.is_dir():
            return str(cand)

    # Fallback: directory of this file
    return str(here.parent)


def asset_path(name: str) -> str:
    return str(pathlib.Path(_base_path()) / "assets" / name)


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
LOCK_PATH = str(app_dir() / "app.lock")
