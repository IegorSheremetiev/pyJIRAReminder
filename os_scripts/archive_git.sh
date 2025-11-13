#!/usr/bin/env bash
set -euo pipefail

# archive_git.sh
# Create a zip archive of the current Git HEAD into an archives/ directory.
# Attempts to read version from .github/.release-please-manifest.json (key "."),
# otherwise falls back to a datestamp. Optionally appends a user-provided suffix.

name="pyJiraReminder"
suffix=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  -s, --suffix <text>   Extra suffix to append to archive name
  -h, --help            Show this help

Behavior:
  - Archive name format: ${name}_<version>[_<suffix>].zip
  - Version is read from .github/.release-please-manifest.json (key ".") if present,
    otherwise the current date/time in format ddMMyyyy_HHmm is used.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--suffix)
      suffix="${2-}"
      if [[ -z "$suffix" ]]; then
        echo "Error: --suffix requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is not installed or not in PATH" >&2
  exit 1
fi

# Prefer the repo root if inside a git repo, otherwise use current dir
repo_root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
archive_dir="$repo_root/archives"
manifest_path="$repo_root/.release-please-manifest.json"

mkdir -p "$archive_dir"

# Determine version
version=""
if [[ -f "$manifest_path" ]]; then
  if command -v jq >/dev/null 2>&1; then
    # Try to read the "." key, then fall back to the first value in the object
    version=$(jq -r '."."' "$manifest_path" 2>/dev/null || true)
    if [[ -z "$version" || "$version" == "null" ]]; then
      version=$(jq -r 'first(.[]?)' "$manifest_path" 2>/dev/null || true)
    fi
  fi
fi

if [[ -z "$version" || "$version" == "null" ]]; then
  version=$(date +%d%m%Y_%H%M)
fi

# Prompt for extra suffix if not provided
if [[ -z "$suffix" ]]; then
  read -r -p "Enter extra suffix for archive name (optional): " suffix || true
fi

archive_name="${name}_${version}"
if [[ -n "$suffix" ]]; then
  archive_name+="_${suffix}"
fi
archive_path="$archive_dir/${archive_name}.zip"

# Ensure we're archiving from the repo root and that HEAD exists
if ! git -C "$repo_root" rev-parse --quiet --verify HEAD >/dev/null 2>&1; then
  echo "Error: Not a Git repository with commits at: $repo_root" >&2
  exit 1
fi

(
  cd "$repo_root"
  git archive --format=zip --output="$archive_path" HEAD
)

echo "Archive created: $archive_path"

