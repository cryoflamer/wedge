#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Usage: $0 [-b] [-s] [-U] [-C] [-c MSG] <patch-file>
  -b   create a temporary branch: patch/<name>-<timestamp>
  -s   stash local changes (tracked only)
  -U   with -s, include untracked files in stash
  -C   auto-commit after apply (default: no commit)
  -c   commit message (requires -C); if omitted, a default is used
EOF
}

branch=0
do_stash=0
include_untracked=0
do_commit=0
commit_msg=""

while getopts "bsU C c:" opt; do
  case $opt in
    b) branch=1 ;;
    s) do_stash=1 ;;
    U) include_untracked=1 ;;
    C) do_commit=1 ;;
    c) commit_msg="$OPTARG" ;;
    *) usage; exit 2 ;;
  esac
done
shift $((OPTIND-1))

[ $# -eq 1 ] || { usage; exit 2; }
PATCH="$1"
[ -f "$PATCH" ] || { echo "No such patch: $PATCH"; exit 2; }

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Run inside a git repo"; exit 2; }
root="$(git rev-parse --show-toplevel)"
cd "$root"

# Optional stash
stashed=0
if [ $do_stash -eq 1 ] && [ -n "$(git status --porcelain)" ]; then
  if [ $include_untracked -eq 1 ]; then
    git stash push -u -m "auto-stash before applying $(basename "$PATCH")" >/dev/null
  else
    git stash push -m "auto-stash before applying $(basename "$PATCH")" >/dev/null
  fi
  stashed=1
fi

if [ $branch -eq 1 ]; then
  name="$(basename "$PATCH")"
  ts="$(date +%Y%m%d-%H%M%S)"
  new_branch="patch/$(echo "$name" | tr -cs 'A-Za-z0-9._-' '-')-$ts"
  git checkout -b "$new_branch"
fi

try() { echo "+ $*"; "$@"; }
# Stage only tracked changes + new files from the patch (avoid unrelated untracked).
stage_only_from_patch() {
  local patch_file="$1"
  git restore --staged :/ 2>/dev/null || true
  git add -u :/ 2>/dev/null || true
  if [ -n "$patch_file" ] && [ -f "$patch_file" ]; then
    git apply --numstat "$patch_file" | awk '{print $3}' | sed 's/^"//;s/"$//' | xargs -r git add -- 2>/dev/null || true
  fi
}


ok=0

# Only use 'git am' for email patches if we are allowed to commit
if [ $do_commit -eq 1 ] && grep -qE '^From [0-9a-f]{40} ' "$PATCH"; then
  if try git am -3 "$PATCH"; then
    ok=1
  else
    echo "git am failed, falling back to git apply."
    git am --abort || true
  fi
fi

# 1) Fast path
if [ $ok -eq 0 ] && git apply --check "$PATCH"; then
  try git apply --index "$PATCH" && ok=1
fi

# 2) 3-way merge
if [ $ok -eq 0 ]; then
  if try git apply --3way --index -v "$PATCH"; then
    ok=1
  fi
fi

# 3) Apply with rejects
if [ $ok -eq 0 ]; then
  if try git apply --reject -v "$PATCH"; then
    ok=1
    echo "Some hunks were rejected. See *.rej files."
  fi
fi

# 4) GNU patch fallback with guessed -p
if [ $ok -eq 0 ]; then
  for p in 0 1 2 3; do
    if patch --dry-run -p"$p" < "$PATCH" >/dev/null 2>&1; then
      if try patch -p"$p" < "$PATCH"; then
        stage_only_from_patch "$PATCH"
        ok=1
        break
      fi
    fi
  done
fi

if [ $ok -eq 1 ]; then
  # Commit if requested
  if [ $do_commit -eq 1 ]; then
    # Ensure staged
    stage_only_from_patch "$PATCH"
    if [ -z "$commit_msg" ]; then
      commit_msg="Apply $(basename "$PATCH")"
    fi
    git commit -m "$commit_msg"
  fi
  echo "Patch applied. Review with 'git status'."
  if [ $do_stash -eq 1 ] && [ $stashed -eq 1 ]; then
    echo "Note: previous changes are stashed. Run 'git stash pop' when ready."
  fi
  exit 0
else
  echo "Failed to apply patch by all strategies."
  if [ $do_stash -eq 1 ] && [ $stashed -eq 1 ]; then
    git stash pop >/dev/null || true
  fi
  exit 1
fi
