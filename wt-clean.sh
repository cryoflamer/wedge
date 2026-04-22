#!/usr/bin/env bash

set -euo pipefail

FORCE=false
AUTO_YES=false

# --- parse args ---
for arg in "$@"; do
    case "$arg" in
        --force)
            FORCE=true
            ;;
        --yes)
            AUTO_YES=true
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: wt-clean.sh [--force] [--yes]"
            exit 1
            ;;
    esac
done

echo "== Git worktree cleanup =="

main_repo="$(git rev-parse --show-toplevel)"

echo "Main repo: $main_repo"
echo ""

# collect worktrees
mapfile -t worktrees < <(git worktree list | awk '{print $1}')

# filter removable
to_remove=()
for wt in "${worktrees[@]}"; do
    if [[ "$wt" != "$main_repo" ]]; then
        to_remove+=("$wt")
    fi
done

if [[ ${#to_remove[@]} -eq 0 ]]; then
    echo "No extra worktrees found."
    exit 0
fi

echo "Worktrees to remove:"
for wt in "${to_remove[@]}"; do
    echo "  $wt"
done

echo ""

# confirm
if [[ "$AUTO_YES" != true ]]; then
    read -p "Proceed with removal? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# remove
for wt in "${to_remove[@]}"; do
    echo "Removing: $wt"
    if [[ "$FORCE" == true ]]; then
        git worktree remove --force "$wt"
    else
        git worktree remove "$wt" || {
            echo "Failed to remove $wt (use --force if needed)"
        }
    fi
done

echo ""
echo "Pruning..."
git worktree prune

echo "Done."