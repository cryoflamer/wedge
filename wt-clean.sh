#!/usr/bin/env bash

set -euo pipefail

FORCE=false
AUTO_YES=false
DELETE_BRANCHES=false
DELETE_MERGED_ONLY=false
CLEAN_MERGED=false

usage() {
    cat <<'EOF'
Usage:
  wt-clean.sh [--force] [--yes] [--delete-branches] [--delete-merged-only] [--clean-merged]

Options:
  --force               remove dirty worktrees too
  --yes                 do not ask for confirmation
  --delete-branches     also delete local branches of removed worktrees
  --delete-merged-only  when deleting branches of removed worktrees, delete only those already merged
  --clean-merged        independently clean all local branches already merged into current HEAD
                        in the main repo (except protected/current branches)
EOF
}

for arg in "$@"; do
    case "$arg" in
        --force)
            FORCE=true
            ;;
        --yes)
            AUTO_YES=true
            ;;
        --delete-branches)
            DELETE_BRANCHES=true
            ;;
        --delete-merged-only)
            DELETE_BRANCHES=true
            DELETE_MERGED_ONLY=true
            ;;
        --clean-merged)
            CLEAN_MERGED=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo
            usage
            exit 1
            ;;
    esac
done

echo "== Git worktree cleanup =="

main_repo="$(git rev-parse --show-toplevel)"
current_branch="$(git -C "$main_repo" branch --show-current || true)"

echo "Main repo: $main_repo"
echo "Current branch in main repo: ${current_branch:-<detached>}"
echo

mapfile -t worktree_lines < <(git worktree list --porcelain)

to_remove_paths=()
to_remove_branches=()

current_path=""
current_branch_entry=""

flush_entry() {
    if [[ -n "${current_path:-}" && "$current_path" != "$main_repo" ]]; then
        to_remove_paths+=("$current_path")
        to_remove_branches+=("${current_branch_entry:-}")
    fi
}

for line in "${worktree_lines[@]}"; do
    if [[ "$line" == worktree\ * ]]; then
        flush_entry
        current_path="${line#worktree }"
        current_branch_entry=""
    elif [[ "$line" == branch\ refs/heads/* ]]; then
        current_branch_entry="${line#branch refs/heads/}"
    elif [[ -z "$line" ]]; then
        :
    fi
done
flush_entry

if [[ ${#to_remove_paths[@]} -eq 0 ]]; then
    echo "No extra worktrees found."
else
    echo "Worktrees to remove:"
    for i in "${!to_remove_paths[@]}"; do
        path="${to_remove_paths[$i]}"
        branch="${to_remove_branches[$i]}"
        if [[ -n "$branch" ]]; then
            echo "  $path    [branch: $branch]"
        else
            echo "  $path"
        fi
    done
fi

echo
if [[ "$DELETE_BRANCHES" == true ]]; then
    echo "Branch cleanup for removed worktrees enabled."
    if [[ "$DELETE_MERGED_ONLY" == true ]]; then
        echo "Only merged branches from removed worktrees will be deleted."
    else
        echo "Branch deletion uses safe delete (-d); with --force it may fall back to -D."
    fi
    echo
fi

if [[ "$CLEAN_MERGED" == true ]]; then
    echo "Global merged-branch cleanup enabled."
    echo "All local branches already merged into current HEAD may be deleted (except protected/current branches)."
    echo
fi

if [[ ${#to_remove_paths[@]} -eq 0 && "$DELETE_BRANCHES" != true && "$CLEAN_MERGED" != true ]]; then
    echo "Nothing to do."
    exit 0
fi

if [[ "$AUTO_YES" != true ]]; then
    read -r -p "Proceed with cleanup? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

removed_branches=()

for i in "${!to_remove_paths[@]}"; do
    wt="${to_remove_paths[$i]}"
    br="${to_remove_branches[$i]}"

    echo "Removing worktree: $wt"
    if [[ "$FORCE" == true ]]; then
        git worktree remove --force "$wt"
    else
        git worktree remove "$wt" || {
            echo "Failed to remove $wt (use --force if needed)"
            continue
        }
    fi

    if [[ "$DELETE_BRANCHES" == true && -n "$br" && "$br" != "main" && "$br" != "master" ]]; then
        removed_branches+=("$br")
    fi
done

echo
echo "Pruning..."
git worktree prune

delete_branch_safe() {
    local br="$1"
    if [[ "$br" == "main" || "$br" == "master" || "$br" == "$current_branch" ]]; then
        echo "Skipping protected/current branch: $br"
        return
    fi

    if git branch -d "$br"; then
        echo "Deleted branch: $br"
    else
        if [[ "$FORCE" == true ]]; then
            git branch -D "$br"
            echo "Force deleted branch: $br"
        else
            echo "Branch not deleted: $br (not fully merged; use --force if you really want to remove it)"
        fi
    fi
}

if [[ "$DELETE_BRANCHES" == true && ${#removed_branches[@]} -gt 0 ]]; then
    echo
    echo "Deleting local branches for removed worktrees in main repo..."
    (
        cd "$main_repo"

        mapfile -t merged_branches < <(git branch --merged | sed 's/^\*//' | xargs -n 1 echo | sed '/^$/d' || true)
        merged_set=" ${merged_branches[*]} "

        for br in "${removed_branches[@]}"; do
            if [[ "$DELETE_MERGED_ONLY" == true ]]; then
                if [[ "$merged_set" == *" $br "* ]]; then
                    delete_branch_safe "$br"
                else
                    echo "Skipping unmerged branch: $br"
                fi
            else
                delete_branch_safe "$br"
            fi
        done
    )
fi

if [[ "$CLEAN_MERGED" == true ]]; then
    echo
    echo "Cleaning all merged local branches in main repo..."
    (
        cd "$main_repo"
        while IFS= read -r br; do
            br="$(echo "$br" | sed 's/^\*//' | xargs)"
            if [[ -z "$br" ]]; then
                continue
            fi
            if [[ "$br" == "main" || "$br" == "master" || "$br" == "$current_branch" ]]; then
                echo "Skipping protected/current branch: $br"
                continue
            fi
            delete_branch_safe "$br"
        done < <(git branch --merged)
    )
fi

echo
echo "Done."
