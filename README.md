# Jira Reminder (PyQt6)

A lightweight system-tray app for Windows (primary) and Linux (secondary) that summarizes your JIRA tasks and nudges you to close at least one task per day.

- **Tray behavior:** single-click → compact “Today” popup; double-click → full dashboard.
- **Cards UI:** each block (“Overdue”, “Today”, “Tomorrow”) shows **exactly 2 issue cards** with a **Show more** link to JIRA.
- **Daily cadence:** 10:00 fetch of today’s tasks; between 16:30–19:00 ping every 30 minutes if nothing was closed today.
- **Secure config:** JIRA token and filters are encrypted locally with a **machine-tied key** (Scrypt + AES‑GCM).
- **Modern JIRA API:** uses `/rest/api/3/search/jql` (POST), with safe JQL like `startOfDay("1d")`.

---

## Table of contents
- [Features](#features)
- [Screenshots](#screenshots)
- [Install](#install)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [JQL logic](#jql-logic)
- [Tray controls & UI](#tray-controls--ui)
- [Logging & troubleshooting](#logging--troubleshooting)
- [Build (local)](#build-local)
- [Build (GitHub Actions)](#build-github-actions)
- [Security model](#security-model)
- [FAQ](#faq)
- [License](#license)

---

## Features

- **Three smart blocks**
  - **Overdue** — due date < today or start date < today.
  - **Today** — due/start is today.
  - **Tomorrow** — due/start is tomorrow.
- **Cards** show: Issue key, Summary, Due pill (overdue/today/tomorrow), badges (Type, Priority, Status).
- **Exactly 2 cards per block** + **Show more** opens the full JQL in JIRA.
- **System tray app**
  - **Single-click** → compact “Today” popup (same card block, fixed size, with **Show more**).
  - **Double-click** → full dashboard (three blocks).
  - Closing main window just hides it; **Quit** from tray menu exits the app.
- **JQL defaults compatible with JIRA Cloud** (`/rest/api/3/search/jql` + POST payload).
- **Encrypted configuration** bound to the machine and OS user.
- **UI scale** with `--ui-scale` (scales UI spacing and font size, preserves system font family).

> Primary OS: Windows. Secondary support: Linux.

---

## Screenshots

_(Add your screenshots here.)_

---

## Install

### Requirements
- Python 3.10+ (tested on Windows 11 and Ubuntu 22.04)
- JIRA Cloud account & API token
- Dependencies (see `requirements.txt`):
  - `PyQt6`
  - `requests`
  - `cryptography`
  - (build-only) `pyinstaller`

### Setup
```bash
# create venv (recommended)
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Quick start
```bash
# 1) Initialize encrypted config (stored under your home folder)
python jira_reminder.py --init

# 2) Run with logs and comfortable UI scale (keeps system font family)
python jira_reminder.py --logging --ui-scale 1.15
```

**Config & log location**
- Windows: `C:\Users\<YOU>\.jira_reminder\config.enc`, `jira_reminder.log`
- Linux: `~/.jira_reminder/config.enc`, `jira_reminder.log`

---

## Configuration

### What is stored (encrypted)
```json
{
  "jira_base_url": "https://yourcompany.atlassian.net",
  "assignee_email": "you@company.com",
  "api_token": "atlassian_api_token_here",
  "project_keys": ["ABC","XYZ"],
  "issue_types": ["Sub-task - HW"],               // default
  "start_date_field": "customfield_10015",        // default start date field
  "done_jql": null                                // optional override for “closed today”
}
```

- Run `--edit-config` to review/modify existing values (press Enter to keep a value):
```bash
python jira_reminder.py --edit-config
```

**Encryption storage path**: `~/.jira_reminder/config.enc` (Windows: in your user profile folder).

---

## JQL logic

A **base constraint** is applied to all queries:
- `project in (<config.project_keys>)` (if provided)
- `assignee = "<config.assignee_email>"`
- `issuetype in ("<config.issue_types>")` (if provided)
- `statusCategory != Done`

Then block-specific filters:

- **Overdue**
  ```jql
  (duedate < startOfDay() AND duedate is not EMPTY)
  OR
  (cf[10015] < startOfDay() AND cf[10015] is not EMPTY)
  ```
  > `cf[10015]` derives from `start_date_field = "customfield_10015"`

- **Today**
  ```jql
  duedate = startOfDay() OR cf[10015] = startOfDay()
  ```

- **Tomorrow**
  ```jql
  duedate = startOfDay("1d") OR cf[10015] = startOfDay("1d")
  ```
  > Using `"1d"` avoids the reserved `+` character parsing issue on newer APIs.

- **Closed today (default)**
  ```jql
  assignee = "<you>" AND project in (...) AND status CHANGED TO Done DURING (startOfDay(), now())
  ```
  You can override this with `done_jql` in the config.

**API endpoint**: `POST /rest/api/3/search/jql` with JSON body (`fields` is an array).

---

## Tray controls & UI

- **Single-click tray icon** → opens a small **Today** window:
  - same block size as dashboard blocks
  - exactly **2 cards**
  - **Show more** button
- **Double-click tray icon** → opens the **main dashboard**:
  - blocks: Overdue / Today / Tomorrow
  - each is a fixed-size **2-card** block with **Show more**
- **Close [X]**: hides the window; the app keeps running in tray.
- **Right-click tray** → **Quit** to exit.

**Daily schedule**
- At **10:00** (system time): fetch & notify Today’s tasks (single toast).
- Between **16:30–19:00**: every **30 minutes** notify if **no task** was moved to **Done** today.

**UI scaling**
- `--ui-scale X` (e.g., `1.25`) scales paddings and **font size** while keeping the system font family (e.g., Segoe UI on Windows).

---

## Logging & troubleshooting

Enable verbose logs:
```bash
python jira_reminder.py --logging
```
Logs are written to:
- Windows: `C:\Users\<YOU>\.jira_reminder\jira_reminder.log`
- Linux: `~/.jira_reminder/jira_reminder.log`

**Common pitfalls**
- **HTTP 410 Gone** on `/rest/api/3/search`: Atlassian removed legacy search; this app uses `/rest/api/3/search/jql`.
- **JQL “+ is reserved”**: we use `startOfDay("1d")` instead of `startOfDay(+1)`.
- **Single vs double click**: handled via a short timer; only one window opens per action.

---

## Build (local)

```bash
# ensure venv is active and deps installed
pip install -r requirements.txt
pip install pyinstaller

# Windows one-file build (GUI app)
pyinstaller ^
  --onefile ^
  --noconsole ^
  --name JiraReminder ^
  --icon app.ico ^
  jira_reminder.py

# Linux one-file build
pyinstaller   --onefile   --name JiraReminder   jira_reminder.py
```

Artifacts are under `dist/`.

---

## Build (GitHub Actions)

Build **only on tags** starting with `RC.` (release candidates). The workflow builds one-file binaries for Windows and Linux and attaches them to a Release.

`.github/workflows/release.yml`:
```yaml
name: release
on:
  push:
    tags:
      - 'RC.*'

permissions:
  contents: write

jobs:
  build:
    strategy:
      matrix:
        os: [windows-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Build (onefile)
        run: |
          pyinstaller --onefile --name JiraReminder jira_reminder.py

      - name: Archive
        uses: actions/upload-artifact@v4
        with:
          name: JiraReminder-${{ runner.os }}
          path: dist/**

  publish:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: JiraReminder-Windows
          path: win
      - uses: actions/download-artifact@v4
        with:
          name: JiraReminder-Linux
          path: linux

      - name: Create release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            win/**
            linux/**
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Security model

- **Storage**: `~/.jira_reminder/config.enc` with header + salt + nonce + ciphertext.
- **Key derivation**:
  - Identity string: `MachineID :: OS username :: platform fingerprint`
  - Scrypt parameters: `N=16384 (2^14), r=8, p=1`, output 32 bytes
- **Encryption**: AES-256-GCM (12-byte nonce, AEAD)
- **Implications**:
  - The config **cannot be decrypted** on another machine/user.
  - OS reinstall or major changes can invalidate the derived key → re-init config.
  - Logs never print the token; use `--logging` to debug requests/responses safely.

---

## FAQ

**How do I change the default start date field?**  
Edit with `--edit-config` and set `start_date_field` to your field id (e.g., `customfield_12345`). The app automatically converts it to `cf[12345]` in JQL.

**Can I limit to a different issue type set?**  
Yes. Edit `issue_types` in config. Default is `["Sub-task - HW"]`.

**Can I show more than 2 cards per block?**  
This UI is intentionally compact. Use **Show more** to open full results in JIRA.

**How do I auto-run on system startup?**  
Use OS tools (Windows Task Scheduler / Linux desktop autostart) pointing to the built binary.

---

## License
MIT (see `LICENSE`).

