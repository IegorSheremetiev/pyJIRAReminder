# src/jira_reminder/security.py
from __future__ import annotations

import os
import json
import uuid
import platform
import getpass

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .paths import CONFIG_ENC_PATH, MAGIC
from .logging_setup import log


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
    log.debug(f"Load Config PATH: {CONFIG_ENC_PATH}")
    obj = decrypt_config(data)
    # Inject defaults if anything is missing
    obj.setdefault("project_keys", [])
    obj.setdefault("issue_types", ["Sub-task - HW"])
    obj.setdefault("start_date_field", "customfield_10015")
    obj.setdefault("done_jql", None)
    return obj


# ---- interactive init / edit ----

def _prompt_edit(label: str, current: str | None) -> str | None:
    show = current if (current not in (None, [], "")) else ""
    val = input(f"{label} [{show}]: ").strip()
    return current if val == "" else val


def init_config_interactive(defaults: dict) -> None:
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
        "done_jql": done_override or None,
    }
    CONFIG_ENC_PATH.write_bytes(encrypt_config(cfg))
    print(f"OK: saved encrypted config at {CONFIG_ENC_PATH}")


def edit_config_interactive() -> None:
    from .paths import CONFIG_ENC_PATH  # локальний імпорт, щоб уникнути циклу у дуже ранніх стадіях

    if not CONFIG_ENC_PATH.exists():
        print("Config not found. Run --init first.")
        return
    cfg = load_config()
    print("=== Edit Jira Reminder config (Enter = keep current) ===")
    cfg["jira_base_url"]   = _prompt_edit("JIRA base URL", cfg.get("jira_base_url")) or cfg["jira_base_url"]
    cfg["assignee_email"]  = _prompt_edit("Assignee email", cfg.get("assignee_email")) or cfg["assignee_email"]
    cfg["api_token"]       = _prompt_edit("JIRA API token", cfg.get("api_token")) or cfg["api_token"]

    proj_raw = _prompt_edit("Project keys (comma-separated)", ", ".join(cfg.get("project_keys", []))) or ", ".join(cfg.get("project_keys", []))
    cfg["project_keys"] = [x.strip() for x in proj_raw.split(",") if x.strip()]

    issue_raw = _prompt_edit('Issue types (comma-separated)', ", ".join(cfg.get("issue_types", ["Sub-task - HW"]))) or ", ".join(cfg.get("issue_types", ["Sub-task - HW"]))
    cfg["issue_types"] = [x.strip() for x in issue_raw.split(",") if x.strip()]

    cfg["start_date_field"] = _prompt_edit("Start date field", cfg.get("start_date_field", "customfield_10015")) or cfg.get("start_date_field", "customfield_10015")
    cfg["done_jql"] = _prompt_edit('Custom "closed today" JQL (enter to keep default Done DURING today)', cfg.get("done_jql")) or cfg.get("done_jql")

    CONFIG_ENC_PATH.write_bytes(encrypt_config(cfg))
    print(f"Saved: {CONFIG_ENC_PATH}")
