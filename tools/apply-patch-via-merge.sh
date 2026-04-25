#!/usr/bin/env bash
# Stage only tracked changes + new files from the patch (avoid unrelated untracked).
stage_only_from_patch() {
  local patch_file="$1"
  git restore --staged :/ 2>/dev/null || true
  git add -u :/ 2>/dev/null || true
  if [ -n "$patch_file" ] && [ -f "$patch_file" ]; then
    git apply --numstat "$patch_file" | awk '{print $3}' | sed 's/^"//;s/"$//' | xargs -r git add -- 2>/dev/null || true
  fi
}
set -euo pipefail

usage() {
  cat <<EOF
Usage: $0 [-n MAX_COMMITS] [-r REV_RANGE] [-s] [-U] [-C] [-c MSG] <patch>
  -n   скільки предків HEAD переглядати (за замовчуванням 200)
  -r   явний rev-list діапазон (напр. 'origin/main..HEAD' або '--all')
  -s   auto-stash локальні зміни (лише відстежувані)
  -U   з -s: включити не відстежувані файли у стеш
  -C   авто-коміт після застосування/мерджу (за замовчуванням — ні)
  -c   повідомлення коміту (потребує -C)
Алгоритм: знайти перший коміт, де патч лягає чисто → зробити коміт у тимчасовій worktree-гілці → змерджити в поточну гілку (без автокоміту).
EOF
}

max_commits=200
rev_range=""
do_stash=0
include_untracked=0
do_commit=0
commit_msg=""

while getopts "n:r:sUCc:" opt; do
  case $opt in
    n) max_commits="$OPTARG" ;;
    r) rev_range="$OPTARG" ;;
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

git rev-parse --is-inside-work-tree >/dev/null || { echo "Run inside a git repo"; exit 2; }
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
# --- Preflight relocator: try to fix paths when --check fails ---
relocator="tools/patch-relocator.py"
if [ -f "$relocator" ] && ! git apply --check "$PATCH" >/dev/null 2>&1; then
  echo "[preflight] git apply --check failed; trying relocator..." >&2
  relocated_path=$(python3 "$relocator" -y "$PATCH" 2> >(sed 's/^/[relocator] /' >&2) || true)
  if [ -n "${relocated_path:-}" ] && [ -f "$relocated_path" ] && [ "$relocated_path" != "$PATCH" ]; then
    echo "[preflight] using relocated patch: $relocated_path"
    PATCH="$relocated_path"
  fi
fi
# --- end preflight ---

cur_branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$cur_branch" != "HEAD" ] || { echo "You are in detached HEAD. Checkout a branch first."; exit 2; }

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

# 0) Try direct apply on HEAD (no auto-commit unless -C)
if git apply --check "$PATCH" >/dev/null 2>&1; then
  git apply --index "$PATCH"
  if [ $do_commit -eq 1 ]; then
    stage_only_from_patch "$PATCH"
    [ -z "$commit_msg" ] && commit_msg="Apply $(basename "$PATCH")"
    git commit -m "$commit_msg"
    echo "Applied directly on $cur_branch with commit."
  else
    echo "Applied directly on $cur_branch (no commit)."
  fi
  [ $stashed -eq 1 ] && echo "Застешено попередні зміни: 'git stash pop' після завершення."
  exit 0
fi

if git apply --3way --check "$PATCH" >/dev/null 2>&1; then
  git apply --3way --index "$PATCH" || true
  if [ $do_commit -eq 1 ]; then
    stage_only_from_patch "$PATCH"
    [ -z "$commit_msg" ] && commit_msg="Apply (3-way) $(basename "$PATCH")"
    git commit -m "$commit_msg" || true
    echo "Застосовано з 3-way на $cur_branch з комітом (якщо не було конфліктів)."
  else
    echo "Застосовано з 3-way на $cur_branch (no commit). Якщо є конфлікти — розвʼяжи і коміть вручну."
  fi
  [ $stashed -eq 1 ] && echo "Застешено попередні зміни: 'git stash pop' після завершення."
  exit 0
fi

# 1) Build candidate list
if [ -z "$rev_range" ]; then
  if git rev-parse --verify origin/main >/dev/null 2>&1; then
    base="$(git merge-base HEAD origin/main)"
    candidates=$(git rev-list --max-count="$max_commits" --reverse "$base^..HEAD")
  else
    candidates=$(git rev-list --max-count="$max_commits" --reverse HEAD)
  fi
else
  candidates=$(git rev-list --reverse $rev_range)
fi

# 2) Try worktree approach
found=""
tmpdir="$(mktemp -d)"
ts="$(date +%Y%m%d-%H%M%S)"
tmp_branch="applypatch/$ts"

for c in $candidates; do
  git worktree add --quiet -b "$tmp_branch" "$tmpdir" "$c" || { rm -rf "$tmpdir"; tmpdir="$(mktemp -d)"; git worktree add --quiet -b "$tmp_branch" "$tmpdir" "$c"; }
  (
    set -e
    cd "$tmpdir"
    if git apply --check "$PATCH" >/dev/null 2>&1; then
      git apply --index "$PATCH"
      git commit -m "Apply $(basename "$PATCH") on $(git rev-parse --short "$c")"
      found="$(git rev-parse HEAD)"
      echo "$found" > .commit_applied
    fi
  ) || true
  if [ -f "$tmpdir/.commit_applied" ]; then
    break
  else
    git worktree remove --force "$tmpdir"
    git branch -D "$tmp_branch" >/dev/null 2>&1 || true
    tmpdir="$(mktemp -d)"
  fi
endfor=0
done

if [ -z "${found:-}" ]; then
  rm -rf "$tmpdir"
  echo "Не знайшов предка, де патч накладається чисто в межах заданого діапазону."
  [ $stashed -eq 1 ] && git stash pop >/dev/null || true
  exit 1
fi

echo "Патч застосовано на коміті $(git rev-parse --short "$c"); створено гілку $tmp_branch з комітом $found."
echo "Мержимо $tmp_branch у $cur_branch (без автокоміту)..."
git merge --no-ff --no-commit "$tmp_branch" || true

conflicts=$(git diff --name-only --diff-filter=U | wc -l | tr -d ' ')
if [ "$conflicts" != "0" ]; then
  echo "Є конфлікти ($conflicts файлів). Розвʼяжи, зроби 'git add' і 'git commit'."
else
  if [ $do_commit -eq 1 ]; then
    [ -z "$commit_msg" ] && commit_msg="Merge patch $(basename "$PATCH") from $tmp_branch"
    git commit -m "$commit_msg"
    echo "Мердж завершено комітом."
  else
    echo "Конфліктів немає. Зроби 'git commit' для завершення мерджа (або переглянь зміни перед комітом)."
  fi
fi

git worktree remove --force "$tmpdir"

[ $stashed -eq 1 ] && echo "Нагадування: у тебе є stash. 'git stash pop' після завершення."
exit 0
