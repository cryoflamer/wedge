#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 [-d DIR] [-n] [-v] [-S] [-s] [-U] [-C] [-c MSG]
  -d DIR  directory to search for *.patch/*.diff (default: ./patches if exists, else .)
  -n      dry-run (print chosen patch and exit)
  -v      verbose (set -x)
  -S      skip auto-stash (do not pass -s to underlying scripts)
  -s      force auto-stash (tracked only) for underlying scripts
  -U      with -s, include untracked in stash
  -C      ask underlying scripts to auto-commit after apply
  -c MSG  commit message (requires -C)
EOF
}

search_dir=""
dry_run=0
verbose=0
pass_stash=1
force_stash=0
include_untracked=0
do_commit=0
commit_msg=""

while getopts "d:nvSsUCc:" opt; do
    case $opt in
        d) search_dir="$OPTARG" ;;
        n) dry_run=1 ;;
        v) verbose=1 ;;
        S) pass_stash=0 ;;
        s) force_stash=1 ;;
        U) include_untracked=1 ;;
        C) do_commit=1 ;;
        c) commit_msg="$OPTARG" ;;
        *) usage; exit 2 ;;
    esac
done
shift $((OPTIND-1))

[ $verbose -eq 0 ] || set -x

# Ensure we are inside a git repo and move to repo root
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Run inside a git repo"; exit 2; }
root="$(git rev-parse --show-toplevel)"
cd "$root"

# Choose directory to scan
if [ -z "${search_dir:-}" ]; then
    if [ -d "patches" ]; then
        search_dir="patches"
    else
        search_dir="."
    fi
fi

# Find newest patch/diff (GNU find)
latest="$(find "$search_dir" -type f \( -name '*.patch' -o -name '*.diff' \) -printf '%T@ %p\n' 2>/dev/null               | sort -nr | awk 'NR==1{ $1=""; sub(/^ /,""); print }')"

if [ -z "$latest" ]; then
    echo "No *.patch or *.diff files in '$search_dir'."
    exit 1
fi

echo "Latest patch: $latest"
# --- Preflight relocator: fix paths if files moved ---
relocator="tools/patch-relocator.py"
if [ -f "$relocator" ]; then
    if ! git apply --check "$latest" >/dev/null 2>&1; then
        echo "[preflight] git apply --check failed; trying relocator..." >&2
        relocated_path=$(python3 "$relocator" -y "$latest" 2> >(sed 's/^/[relocator] /' >&2) || true)
        if [ -n "${relocated_path:-}" ] && [ -f "$relocated_path" ] && [ "$relocated_path" != "$latest" ]; then
            echo "[preflight] using relocated patch: $relocated_path"
            latest="$relocated_path"
        fi
    fi
fi
# --- end preflight ---

[ $dry_run -eq 1 ] && exit 0

merge_script="tools/apply-patch-via-merge.sh"
force_script="tools/apply-patch.sh"

[ -f "$merge_script" ] || { echo "Missing $merge_script"; exit 2; }
[ -f "$force_script" ] || { echo "Missing $force_script"; exit 2; }

args=()
# Stash controls
if [ $pass_stash -eq 1 ] || [ $force_stash -eq 1 ]; then
    args+=(-s)
    [ $include_untracked -eq 1 ] && args+=(-U)
fi
# Commit controls
if [ $do_commit -eq 1 ]; then
    args+=(-C)
    [ -n "$commit_msg" ] && args+=(-c "$commit_msg")
fi

# Prefer merge strategy first
if bash "$merge_script" "${args[@]}" "$latest"; then
    echo "Applied via merge strategy."
    exit 0
else
    echo "Merge strategy failed; trying fallback force-apply..."
    if bash "$force_script" "${args[@]}" "$latest"; then
        echo "Applied via fallback."
        exit 0
    else
        echo "All strategies failed for: $latest"
        exit 1
    fi
fi
