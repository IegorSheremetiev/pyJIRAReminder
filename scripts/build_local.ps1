# build_local.ps1 - Windows local onefile build
$ErrorActionPreference = 'Stop'

$APP  = 'JiraReminder'
$SRC  = 'pyJIRAReminder.py'
$ICON = 'assets\app.ico'

# Ensure deps
python -m pip install --upgrade pip | Out-Null
pip install -r requirements.txt | Out-Null
pip install pyinstaller | Out-Null

# Extract version from __version__ in pyJIRAReminder.py (if present)
$ver = ''
$match = Select-String -Path $SRC -Pattern '__version__\s*=\s*["'']([^"'']+)["'']' -ErrorAction SilentlyContinue
if ($match) { $ver = $match.Matches[0].Groups[1].Value } else { $ver = 'dev' }

# Build
pyinstaller --onefile --noconsole --name $APP --icon $ICON --add-data "assets;assets" $SRC

# Rename artifact
if (Test-Path "dist\$APP.exe") {
    $out = "dist\$APP-v$ver-windows-x86_64.exe"
    if (Test-Path $out) { Remove-Item $out -Force }
    Rename-Item "dist\$APP.exe" $out
    Write-Host "Built $out"
} else {
    Write-Error "Build failed: dist\$APP.exe not found"
}
