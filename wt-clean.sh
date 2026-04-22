#!/usr/bin/env bash

set -euo pipefail

FORCE=false
AUTO_YES=false
DELETE_BRANCHES=false
DELETE_MERGED_ONLY=false

usage() {
    cat <<'EOF'
Usage:
  wt-clean.sh [--force] [--yes] [--delete-branches] [--delete-merged-only]

Options:
  --force               remove dirty worktrees too
  --yes                 do not ask for confirmation
  --delete-branches     also delete local branches of removed worktrees
  --delete-merged-only  in main repo, delete only branches already merged into current HEAD
                        if not set, branch deletion still uses safe `git branch -d`
                        and falls back to `-D` only when --force is set
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
current_branch="$(git branch --show-current || true)"

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
    echo
fi

if [[ "$DELETE_BRANCHES" == true ]]; then
    echo "Branch cleanup enabled."
    if [[ "$DELETE_MERGED_ONLY" == true ]]; then
        echo "Only branches already merged into current HEAD in main repo will be deleted."
    else
        echo "Branch deletion uses safe delete (-d); with --force it may fall back to -D."
    fi
    echo
fi

if [[ ${#to_remove_paths[@]} -eq 0 && "$DELETE_BRANCHES" != true ]]; then
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

if [[ "$DELETE_BRANCHES" == true && ${#removed_branches[@]} -gt 0 ]]; then
    echo
    echo "Deleting local branches in main repo..."
    (
        cd "$main_repo"

        mapfile -t merged_branches < <(git branch --merged | sed 's/^\*//' | xargs -n 1 echo | sed '/^$/d' || true)
        merged_set=" ${merged_branches[*]} "

        for br in "${removed_branches[@]}"; do
            if [[ "$br" == "main" || "$br" == "master" || "$br" == "$current_branch" ]]; then
                echo "Skipping protected/current branch: $br"
                continue
            fi

            if [[ "$DELETE_MERGED_ONLY" == true ]]; then
                if [[ "$merged_set" == *" $br "* ]]; then
                    git branch -d "$br"
                    echo "Deleted merged branch: $br"
                else
                    echo "Skipping unmerged branch: $br"
                fi
                continue
            fi

            if git branch -d "$br"; then
                echo "Deleted branch: $br"
            else
                if [[ "$FORCE" == true ]]; then
                    git branch -D "$br"
                    echo "Force deleted branch: $br"
                else
                    echo "Branch not deleted: $br (not fully merged; use --force or --delete-merged-only)"
                fi
            fi
        done
    )
fi

echo
echo "Done."
