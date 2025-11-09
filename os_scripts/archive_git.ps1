# archive_git.ps1

param (
    [string]$ExtraSuffix = ""
)

# Define variables
$name = "pyJiraReminder"
$repoRoot = Resolve-Path ".\"
$archiveDir = Join-Path $repoRoot "archives"
$manifestPath = Join-Path $repoRoot ".github\.release-please-manifest.json"
$VersionStorage = "."

# Ensure archive directory exists
if (-not (Test-Path $archiveDir)) {
    New-Item -ItemType Directory -Path $archiveDir | Out-Null
}

# Get version from manifest or use datestamp
$version = ""
if (Test-Path $manifestPath) {
    try {
        $manifest = Get-Content $manifestPath | ConvertFrom-Json
        if ($manifest.$VersionStorage) {
            $version = $manifest.$VersionStorage
        }
    } catch {
        $version = ""
    }
}
if (-not $version) {
    $version = Get-Date -Format "ddMMyyyy_HHmm"
}

# Prompt for extra suffix if not provided
if (-not $ExtraSuffix) {
    $ExtraSuffix = Read-Host "Enter extra suffix for archive name (optional)"
}

# Build archive name
$archiveName = "$name" + "_$version"
if ($ExtraSuffix) {
    $archiveName += "_$ExtraSuffix"
}
$archiveName += ".zip"
$archivePath = Join-Path $archiveDir $archiveName

# Run git archive
Push-Location $repoRoot
git archive --format=zip --output="$archivePath" HEAD
Pop-Location

Write-Host "Archive created: $archivePath"