$ErrorActionPreference = "Stop"
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt

# Іконка: поклади app.ico поруч з jira_reminder.py
$APP="pyJIRAReminder.py"
$NAME="JiraReminder"
$VER="v$((Select-String -Path $APP -Pattern '__version__ = \"(.+?)\"').Matches[0].Groups[1].Value)"

pyinstaller --noconfirm --onefile `
  --name "$NAME-$VER-windows-x86_64" `
  --icon app.ico `
  --add-data "jira_reminder_icon_256.png;." `
  $APP

Write-Host "Done. EXE: dist\$NAME-$VER-windows-x86_64.exe"
