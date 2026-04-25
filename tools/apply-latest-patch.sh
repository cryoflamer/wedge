#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF_USAGE
Usage: $0 [-d DIR] [-p PATCH] [-n] [-v] [-S] [-s] [-U] [-C] [-c MSG] [--strict]
  -d DIR    directory to search for *.patch/*.diff (default: ./patches if exists, else .)
  -p PATCH  apply an explicit patch instead of selecting the latest one
  -n        dry-run (print chosen patch and exit)
  -v        verbose (set -x)
  -S        skip auto-stash
  -s        force auto-stash (tracked only)
  -U        with -s/default stash, include untracked in stash
  -C        auto-commit after a clean apply/merge when possible
  -c MSG    commit message (requires -C)
  --strict  only allow clean git apply; do not try 3-way/merge fallbacks

Default strategy:
  1. select latest patch or use -p
  2. try clean git apply --check + git apply --index
  3. if clean apply fails, try git apply --3way and leave conflicts for manual resolve
  4. if 3-way cannot start, try applying on a recent ancestor in a temporary worktree
     and merge that patch commit into the current branch, again leaving conflicts if needed
EOF_USAGE
}

log() {
    echo "[apply-latest] $*"
}

err() {
    echo "error: $*" >&2
}

abs_path() {
    local p="$1"
    if command -v realpath >/dev/null 2>&1; then
        realpath "$p"
    else
        python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$p"
    fi
}

stage_only_from_patch() {
    local patch_file="$1"

    git restore --staged :/ 2>/dev/null || true
    git add -u :/ 2>/dev/null || true

    if [[ -n "$patch_file" && -f "$patch_file" ]]; then
        git apply --numstat "$patch_file" 2>/dev/null \
            | awk '{print $3}' \
            | sed 's/^"//;s/"$//' \
            | xargs -r git add -- 2>/dev/null || true
    fi
}

has_conflicts() {
    [[ -n "$(git diff --name-only --diff-filter=U)" ]]
}

print_conflicts() {
    log "conflicts detected; resolve them manually, then run:"
    echo "  git status"
    echo "  git add <resolved-files>"
    echo "  git commit"
    echo
    log "conflicted files:"
    git diff --name-only --diff-filter=U | sed 's/^/  /'
}

maybe_commit() {
    local patch_file="$1"
    local default_msg="$2"

    if [[ $do_commit -eq 0 ]]; then
        return 0
    fi

    stage_only_from_patch "$patch_file"
    if [[ -z "$commit_msg" ]]; then
        commit_msg="$default_msg"
    fi
    git commit -m "$commit_msg"
}

stash_if_needed() {
    stashed=0

    if [[ $do_stash -eq 1 && -n "$(git status --porcelain)" ]]; then
        if [[ $include_untracked -eq 1 ]]; then
            git stash push -u -m "auto-stash before applying $(basename "$PATCH")" >/dev/null
        else
            git stash push -m "auto-stash before applying $(basename "$PATCH")" >/dev/null
        fi
        stashed=1
        log "local changes were stashed"
    fi
}

remind_stash() {
    if [[ ${stashed:-0} -eq 1 ]]; then
        log "previous changes are stashed; run 'git stash pop' when ready"
    fi
}

try_relocator() {
    local patch_file="$1"
    local relocator="tools/patch-relocator.py"

    if [[ -f "$relocator" ]] && ! git apply --check "$patch_file" >/dev/null 2>&1; then
        log "git apply --check failed; trying patch relocator"
        local relocated_path
        relocated_path=$(python3 "$relocator" -y "$patch_file" 2> >(sed 's/^/[relocator] /' >&2) || true)
        if [[ -n "${relocated_path:-}" && -f "$relocated_path" && "$relocated_path" != "$patch_file" ]]; then
            log "using relocated patch: $relocated_path"
            printf '%s\n' "$relocated_path"
            return 0
        fi
    fi

    printf '%s\n' "$patch_file"
}

select_latest_patch() {
    local dir="$1"

    find "$dir" -type f \( -name '*.patch' -o -name '*.diff' \) -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | awk 'NR==1{ $1=""; sub(/^ /,""); print }'
}

try_clean_apply() {
    local patch_file="$1"

    if git apply --check "$patch_file" >/dev/null 2>&1; then
        git apply --index "$patch_file"
        maybe_commit "$patch_file" "Apply $(basename "$patch_file")"
        log "patch applied cleanly"
        remind_stash
        exit 0
    fi
}

try_three_way_apply() {
    local patch_file="$1"

    log "clean apply failed; trying git apply --3way"

    if git apply --3way "$patch_file"; then
        if has_conflicts; then
            print_conflicts
        else
            maybe_commit "$patch_file" "Apply (3-way) $(basename "$patch_file")"
            log "patch applied with 3-way fallback"
        fi
        remind_stash
        exit 0
    fi

    if has_conflicts; then
        print_conflicts
        remind_stash
        exit 0
    fi
}

candidate_commits() {
    if [[ -n "$rev_range" ]]; then
        git rev-list --reverse $rev_range
        return
    fi

    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        local base
        base="$(git merge-base HEAD origin/main)"
        git rev-list --max-count="$max_commits" --reverse "$base^..HEAD" 2>/dev/null \
            || git rev-list --max-count="$max_commits" --reverse HEAD
    else
        git rev-list --max-count="$max_commits" --reverse HEAD
    fi
}

try_ancestor_merge() {
    local patch_file="$1"
    local patch_abs
    patch_abs="$(abs_path "$patch_file")"

    log "3-way apply could not start; trying ancestor/worktree merge fallback"

    local cur_branch
    cur_branch="$(git rev-parse --abbrev-ref HEAD)"
    if [[ "$cur_branch" == "HEAD" ]]; then
        err "detached HEAD; ancestor merge fallback requires a branch"
        return 1
    fi

    local tmpdir tmp_branch ts found applied_commit applied_base
    tmpdir="$(mktemp -d)"
    ts="$(date +%Y%m%d-%H%M%S)"
    tmp_branch="applypatch/$ts"
    found=""
    applied_commit=""
    applied_base=""

    while IFS= read -r commit; do
        [[ -n "$commit" ]] || continue

        rm -rf "$tmpdir"
        tmpdir="$(mktemp -d)"
        git worktree add --quiet -b "$tmp_branch" "$tmpdir" "$commit" || {
            git branch -D "$tmp_branch" >/dev/null 2>&1 || true
            git worktree add --quiet -b "$tmp_branch" "$tmpdir" "$commit" || continue
        }

        if (
            cd "$tmpdir"
            git apply --check "$patch_abs" >/dev/null 2>&1
        ); then
            (
                cd "$tmpdir"
                git apply --index "$patch_abs"
                git commit -q -m "Apply $(basename "$patch_abs") on $(git rev-parse --short HEAD)"
                git rev-parse HEAD > .commit_applied
            )
            applied_commit="$(cat "$tmpdir/.commit_applied")"
            applied_base="$commit"
            found="1"
            break
        fi

        git worktree remove --force "$tmpdir" >/dev/null 2>&1 || true
        git branch -D "$tmp_branch" >/dev/null 2>&1 || true
    done < <(candidate_commits)

    if [[ -z "$found" ]]; then
        rm -rf "$tmpdir"
        err "no ancestor found where the patch applies cleanly"
        return 1
    fi

    log "patch applied on ancestor $(git rev-parse --short "$applied_base"); merging temporary branch $tmp_branch"
    git merge --no-ff --no-commit "$tmp_branch" || true

    if has_conflicts; then
        print_conflicts
    else
        if [[ $do_commit -eq 1 ]]; then
            if [[ -z "$commit_msg" ]]; then
                commit_msg="Merge patch $(basename "$patch_file")"
            fi
            git commit -m "$commit_msg"
            log "ancestor merge fallback completed with commit"
        else
            log "ancestor merge fallback completed without conflicts"
            log "review changes and run git commit when ready"
        fi
    fi

    git worktree remove --force "$tmpdir" >/dev/null 2>&1 || true
    remind_stash
    exit 0
}

search_dir=""
patch_arg=""
dry_run=0
verbose=0
do_stash=1
include_untracked=0
do_commit=0
commit_msg=""
strict=0
max_commits=200
rev_range=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d)
            shift
            [[ $# -gt 0 ]] || { usage; exit 2; }
            search_dir="$1"
            ;;
        -p)
            shift
            [[ $# -gt 0 ]] || { usage; exit 2; }
            patch_arg="$1"
            ;;
        -n)
            dry_run=1
            ;;
        -v)
            verbose=1
            ;;
        -S)
            do_stash=0
            ;;
        -s)
            do_stash=1
            ;;
        -U)
            include_untracked=1
            ;;
        -C)
            do_commit=1
            ;;
        -c)
            shift
            [[ $# -gt 0 ]] || { usage; exit 2; }
            commit_msg="$1"
            ;;
        --strict)
            strict=1
            ;;
        --max-commits)
            shift
            [[ "${1:-}" =~ ^[0-9]+$ ]] || { err "--max-commits requires a number"; exit 2; }
            max_commits="$1"
            ;;
        --rev-range)
            shift
            [[ $# -gt 0 ]] || { usage; exit 2; }
            rev_range="$1"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 2
            ;;
    esac
    shift
done

[[ $verbose -eq 0 ]] || set -x

if [[ $do_commit -eq 0 && -n "$commit_msg" ]]; then
    err "-c requires -C"
    exit 2
fi

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { err "run inside a git repo"; exit 2; }
root="$(git rev-parse --show-toplevel)"
cd "$root"

if [[ -n "$patch_arg" ]]; then
    PATCH="$patch_arg"
else
    if [[ -z "$search_dir" ]]; then
        if [[ -d patches ]]; then
            search_dir="patches"
        else
            search_dir="."
        fi
    fi
    PATCH="$(select_latest_patch "$search_dir")"
fi

if [[ -z "${PATCH:-}" ]]; then
    err "no *.patch or *.diff files found"
    exit 1
fi

[[ -f "$PATCH" ]] || { err "no such patch: $PATCH"; exit 2; }
PATCH="$(try_relocator "$PATCH")"

log "selected patch: $PATCH"

if [[ $dry_run -eq 1 ]]; then
    exit 0
fi

stash_if_needed
try_clean_apply "$PATCH"

if [[ $strict -eq 1 ]]; then
    err "strict mode: clean apply failed"
    exit 1
fi

try_three_way_apply "$PATCH"
try_ancestor_merge "$PATCH"

err "all apply strategies failed for: $PATCH"
exit 1
