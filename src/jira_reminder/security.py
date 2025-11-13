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


# Note: interactive CLI helpers (init/edit) were removed — configuration is now handled via GUI dialogs.
