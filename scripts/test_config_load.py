# scripts/test_config_load.py
"""
Simple tests for config load/merge behavior.
These are lightweight, do not require a running GUI.
"""
import json
import tempfile
import pathlib

from jira_reminder import ui as ui_mod
from jira_reminder import security as sec_mod
from jira_reminder import paths as paths_mod


def test_load_combined_creates_merged_config():
    td = tempfile.TemporaryDirectory()
    tmp = pathlib.Path(td.name)

    # override paths to use temp dir
    paths_mod.CONFIG_PLAIN_PATH = tmp / "config.json"
    paths_mod.CONFIG_ENC_PATH = tmp / "config.enc"

    plain = {"logging": True, "ui_scale": 1.5}
    paths_mod.CONFIG_PLAIN_PATH.write_text(json.dumps(plain), encoding="utf-8")

    secure = {"jira_base_url": "https://example.atlassian.net", "assignee_email": "me@example.com"}
    paths_mod.CONFIG_ENC_PATH.write_bytes(sec_mod.encrypt_config(secure))

    combined = ui_mod.ConfigDialog.load_combined()
    assert combined.get("logging") is True
    assert combined.get("ui_scale") == 1.5
    assert combined.get("jira_base_url") == "https://example.atlassian.net"
    assert combined.get("assignee_email") == "me@example.com"


if __name__ == "__main__":
    test_load_combined_creates_merged_config()
    print("OK")
