# build_local.ps1 - Windows local onefile build
$ErrorActionPreference = 'Stop'

$APP  = 'JiraReminder'
$SRC  = 'pyJIRAReminder.py'
$METRICS = 'src/jira_reminder/metrics.py'
$ICON = 'assets\app.ico'

# Ensure deps
Write-Host "Upgrade pip... " -NoNewline
python -m pip install --upgrade pip | Out-Null
Write-Host "Done"
Write-Host "Install requirements.txt... " -NoNewline
pip install -r requirements.txt | Out-Null
Write-Host "Done"
Write-Host "Install requirements-dev.txt... " -NoNewline
pip install -r .\requirements-dev.txt | Out-Null
Write-Host "Done"

# Extract version from __version__ in pyJIRAReminder.py (if present)
Write-Host "Check the build version: " -NoNewline
$ver = ''
$match = Select-String -Path $METRICS -Pattern '__version__\s*=\s*["'']([^"'']+)["'']' -ErrorAction SilentlyContinue
if ($match) { $ver = $match.Matches[0].Groups[1].Value } else { $ver = 'dev' }
Write-Host "v.$ver"

# Build
Write-Host "Start pyinstaller execution..."
pyinstaller --onefile --noconsole --name $APP --paths src --icon $ICON --add-data "assets;assets" $SRC
Write-Host "pyinstaller execution: Done"

# Rename artifact
Write-Host "Rename artifacts..."
if (Test-Path "dist\$APP.exe") {
    $out = "dist\$APP-v$ver-windows-x86_64.exe"
    if (Test-Path $out) { Remove-Item $out -Force }
    $src     = Join-Path "dist" "$APP.exe"
    $newName = "$APP-v$ver-windows-x86_64.exe"
    Rename-Item -Path $src -NewName $newName -Force
    Write-Host "Built $out"
} else {
    Write-Error "Build failed: dist\$APP.exe not found"
}
