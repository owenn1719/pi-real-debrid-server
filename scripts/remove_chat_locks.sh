#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: remove_chat_locks.sh [--dry-run] [--safe]

Remove all Codex chat writer lock files, including locks still reported as held.
The internal .coordination.lock file is always preserved.

Options:
  --dry-run  Show what would be removed without removing it.
  --safe     Remove only stale locks and skip locks held by a process.

Environment:
  CODEX_HOME  Codex data directory (default: $HOME/.codex)
EOF
}

dry_run=false
safe_mode=false
while (( $# > 0 )); do
  case "$1" in
    --dry-run)
      dry_run=true
      shift
      ;;
    --safe)
      safe_mode=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$safe_mode" == true ]] && ! command -v flock >/dev/null 2>&1; then
  echo "Error: 'flock' is required to distinguish stale locks from active ones." >&2
  exit 1
fi

codex_home="${CODEX_HOME:-${HOME:?HOME is not set}/.codex}"
lock_dir="$codex_home/thread-writer-locks"

if [[ ! -d "$lock_dir" ]]; then
  echo "No Codex chat lock directory found at: $lock_dir"
  exit 0
fi

thread_id_pattern='^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$'

removed=0
active=0

while IFS= read -r -d '' lock_file; do
  lock_name="${lock_file##*/}"

  # Codex thread locks are UUID-named. This deliberately excludes internal
  # files such as .coordination.lock and unrelated files in the directory.
  thread_id="${lock_name%.lock}"
  if [[ ! "$thread_id" =~ $thread_id_pattern ]]; then
    continue
  fi

  if [[ "$safe_mode" != true ]]; then
    if [[ "$dry_run" == true ]]; then
      echo "Would remove lock: $lock_name"
    else
      rm -- "$lock_file"
      echo "Removed lock: $lock_name"
    fi
    removed=$((removed + 1))
    continue
  fi

  # Keep the advisory lock held through deletion so another cleanup process
  # cannot race this one. A lock held by Codex makes flock fail immediately.
  if (
    flock -n 9 || exit 1
    if [[ "$dry_run" == true ]]; then
      echo "Would remove stale lock: $lock_name"
    else
      rm -- "$lock_file"
      echo "Removed stale lock: $lock_name"
    fi
  ) 9<"$lock_file"; then
    removed=$((removed + 1))
  else
    echo "Skipped active lock: $lock_name"
    active=$((active + 1))
  fi
done < <(find "$lock_dir" -maxdepth 1 -type f -name '*.lock' -print0)

if [[ "$dry_run" == true ]]; then
  echo "Dry run complete: $removed removable lock(s), $active active lock(s) skipped."
else
  echo "Cleanup complete: removed $removed lock(s), skipped $active active lock(s)."
fi
