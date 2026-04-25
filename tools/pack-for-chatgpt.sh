#!/usr/bin/env bash
set -euo pipefail

# pack-for-chatgpt.sh
#
# Creates disposable git repositories for ChatGPT patch/review workflows.
#
# Modes:
#   full    <task-name> [--include-untracked]
#   slice   <task-name> <file-or-dir>...
#   changed <task-name>
#   history <task-name> [--depth N | --full-history]
#
# Examples:
#   ./pack-for-chatgpt.sh full overview
#   ./pack-for-chatgpt.sh slice fix-phase-ui src/wedge/ui.py etc/config.yaml
#   ./pack-for-chatgpt.sh slice docs-task docs/ src/wedge/
#   ./pack-for-chatgpt.sh changed review-local-edits
#   ./pack-for-chatgpt.sh history investigate-regression --depth 100
#   ./pack-for-chatgpt.sh history investigate-regression --full-history
#
# Output:
#   chatgpt-packs/chatgpt-pack-<mode>-<task>-<timestamp>.tar.gz
#
# Archive structure:
#   chatgpt-pack/
#     .git/
#     <project files...>
#     CHATGPT_PACK_USAGE.md
#     patch.base.sha256
#     patch.meta.json

usage() {
    cat <<'EOF'
Usage:
  pack-for-chatgpt.sh full    <task-name> [--include-untracked]
  pack-for-chatgpt.sh slice   <task-name> <file-or-dir>...
  pack-for-chatgpt.sh changed <task-name>
  pack-for-chatgpt.sh history <task-name> [--depth N | --full-history]

Modes:
  full
    Creates a fresh disposable git repo with all tracked files.
    With --include-untracked, also includes untracked non-ignored files.

  slice
    Creates a fresh disposable git repo with only selected files/directories.
    Paths are preserved relative to the project root.
    Directories are collected through git tracked/untracked-non-ignored files,
    not raw find, so caches/build outputs are not accidentally packed.

  changed
    Creates a fresh disposable git repo with changed tracked files plus
    untracked non-ignored files.

  history
    Creates a shallow clone with real git history and working tree diff.
    Use only when git log/blame/history is needed.
    Default depth: 50. Use --full-history to include all reachable history.

Environment:
  CHATGPT_PACK_OUT_DIR
    Output directory. Default: chatgpt-packs

Examples:
  ./pack-for-chatgpt.sh full overview
  ./pack-for-chatgpt.sh full overview --include-untracked
  ./pack-for-chatgpt.sh slice fix-ui src/app.py docs/SPEC.md
  ./pack-for-chatgpt.sh slice docs-review docs/
  ./pack-for-chatgpt.sh changed review-edits
  ./pack-for-chatgpt.sh history investigate --depth 50
EOF
}

die() {
    echo "error: $*" >&2
    exit 1
}

warn() {
    echo "warning: $*" >&2
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

json_escape() {
    python3 - "$1" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1], ensure_ascii=False))
PY
}

sanitize_task_name() {
    local raw="$1"
    local safe
    safe="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//')"
    [[ -n "$safe" ]] || safe="task"
    printf '%.80s' "$safe"
}

repo_root() {
    git rev-parse --show-toplevel 2>/dev/null || die "not inside a git repository"
}

is_safe_relative_path() {
    local p="$1"
    [[ -n "$p" ]] || return 1
    [[ "$p" != /* ]] || return 1
    [[ "$p" != "." ]] || return 1
    [[ "$p" != ".." ]] || return 1
    [[ "$p" != ../* ]] || return 1
    [[ "$p" != */../* ]] || return 1
    [[ "$p" != */.. ]] || return 1
    return 0
}

should_exclude_path() {
    local p="$1"

    case "$p" in
        .git|.git/*) return 0 ;;

        chatgpt-packs|chatgpt-packs/*|*/chatgpt-packs|*/chatgpt-packs/*) return 0 ;;
        *.tar|*.tar.gz|*.tgz|*.zip|*.7z|*.rar) return 0 ;;

        .venv|.venv/*|venv|venv/*|env|env/*) return 0 ;;
        node_modules|node_modules/*|*/node_modules|*/node_modules/*) return 0 ;;
        __pycache__|*/__pycache__|*/__pycache__/*) return 0 ;;
        .mypy_cache|.mypy_cache/*|*/.mypy_cache|*/.mypy_cache/*) return 0 ;;
        .pytest_cache|.pytest_cache/*|*/.pytest_cache|*/.pytest_cache/*) return 0 ;;
        .ruff_cache|.ruff_cache/*|*/.ruff_cache|*/.ruff_cache/*) return 0 ;;
        .idea|.idea/*|*/.idea|*/.idea/*) return 0 ;;
        .vscode|.vscode/*|*/.vscode|*/.vscode/*) return 0 ;;
        build|build/*|*/build|*/build/*) return 0 ;;
        dist|dist/*|*/dist|*/dist/*) return 0 ;;
        target|target/*|*/target|*/target/*) return 0 ;;
        .DS_Store|*/.DS_Store) return 0 ;;

        .env|.env.*|*/.env|*/.env.*) return 0 ;;
        id_rsa|id_rsa.pub|id_ed25519|id_ed25519.pub) return 0 ;;
        */id_rsa|*/id_rsa.pub|*/id_ed25519|*/id_ed25519.pub) return 0 ;;
        *.pem|*.key|*.p12|*.pfx|*.crt|*.cer) return 0 ;;

        *.mp4|*.mov|*.avi|*.mkv|*.webm) return 0 ;;
        *.pt|*.pth|*.onnx|*.engine) return 0 ;;
    esac

    return 1
}

copy_file_preserve_path() {
    local root="$1"
    local dst="$2"
    local rel="$3"

    is_safe_relative_path "$rel" || die "unsafe path: $rel"
    [[ -f "$root/$rel" ]] || die "not a file: $rel"

    mkdir -p "$dst/$(dirname "$rel")"
    cp -p "$root/$rel" "$dst/$rel"
}

copy_paths_from_nul_stream() {
    local root="$1"
    local dst="$2"
    local count=0

    while IFS= read -r -d '' rel; do
        [[ -n "$rel" ]] || continue
        is_safe_relative_path "$rel" || die "unsafe path from git: $rel"
        if should_exclude_path "$rel"; then
            continue
        fi
        if [[ -f "$root/$rel" ]]; then
            copy_file_preserve_path "$root" "$dst" "$rel"
            count=$((count + 1))
        fi
    done

    printf '%s\n' "$count"
}

collect_tracked_files() {
    git ls-files -z
}

collect_untracked_files() {
    git ls-files --others --exclude-standard -z
}

collect_changed_files() {
    {
        git diff --name-only -z HEAD
        git diff --name-only -z --cached HEAD
        git ls-files --others --exclude-standard -z
    } | awk -v RS='\0' -v ORS='\0' 'NF && !seen[$0]++ { print }'
}

collect_git_known_files() {
    {
        git ls-files -z
        git ls-files --others --exclude-standard -z
    } | awk -v RS='\0' -v ORS='\0' 'NF && !seen[$0]++ { print }'
}

path_is_inside_slice() {
    local file="$1"
    local slice="$2"

    [[ "$file" == "$slice" ]] && return 0
    [[ "$file" == "$slice/"* ]] && return 0
    return 1
}

copy_slice_path() {
    local root="$1"
    local dst="$2"
    local rel="$3"
    local tmp_list="$4"
    local copied=0
    local file

    rel="${rel%/}"

    is_safe_relative_path "$rel" || die "unsafe slice path: $rel"
    [[ -e "$root/$rel" ]] || die "path does not exist: $rel"

    if [[ -f "$root/$rel" ]]; then
        if ! should_exclude_path "$rel"; then
            copy_file_preserve_path "$root" "$dst" "$rel"
            copied=$((copied + 1))
        fi
    elif [[ -d "$root/$rel" ]]; then
        while IFS= read -r -d '' file; do
            [[ -n "$file" ]] || continue
            if path_is_inside_slice "$file" "$rel" && ! should_exclude_path "$file"; then
                copy_file_preserve_path "$root" "$dst" "$file"
                copied=$((copied + 1))
            fi
        done < "$tmp_list"
    else
        die "unsupported path type: $rel"
    fi

    printf '%s\n' "$copied"
}

write_sha256_manifest() {
    local pack_dir="$1"

    (
        cd "$pack_dir"
        find . \
            -path './.git' -prune -o \
            -path './.git/*' -prune -o \
            -type f \
            ! -name 'patch.base.sha256' \
            ! -name 'patch.meta.json' \
            -print0 \
        | sort -z \
        | xargs -0 sha256sum
    ) > "$pack_dir/patch.base.sha256"
}

write_usage_file() {
    local pack_dir="$1"

    cat > "$pack_dir/CHATGPT_PACK_USAGE.md" <<'EOF'
# ChatGPT disposable repository pack

This archive contains a disposable git repository prepared for review or patch generation.

Expected assistant workflow:

1. Unpack the archive.
2. Enter `chatgpt-pack/`.
3. Confirm baseline state with `git status`.
4. Edit files as needed.
5. Produce patch with `git diff --binary`.
6. Verify patch against a clean copy with `git apply --check`.
7. Return the patch plus sidecar metadata/checksum files.

Notes:

- `patch.base.sha256` contains SHA256 checksums for files included in this pack.
- `patch.meta.json` describes pack mode, source branch/head, and included files.
- This repository is disposable. Do not treat its `.git` history as authoritative unless mode is `history`.
EOF
}

write_meta_json() {
    local pack_dir="$1"
    local mode="$2"
    local task_name="$3"
    local source_root="$4"
    local file_count="$5"
    local history_depth="${6:-}"

    local head_sha
    head_sha="$(git -C "$source_root" rev-parse HEAD 2>/dev/null || true)"

    local branch
    branch="$(git -C "$source_root" branch --show-current 2>/dev/null || true)"

    local timestamp
    timestamp="$(date -Iseconds)"

    local files_json
    files_json="$(
        cd "$pack_dir"
        find . \
            -path './.git' -prune -o \
            -path './.git/*' -prune -o \
            -type f \
            ! -name 'patch.base.sha256' \
            ! -name 'patch.meta.json' \
            -printf '%P\n' \
        | sort \
        | python3 -c 'import json,sys; print(json.dumps([line.rstrip("\n") for line in sys.stdin if line.strip()], ensure_ascii=False, indent=2))'
    )"

    cat > "$pack_dir/patch.meta.json" <<EOF
{
  "pack_format": "chatgpt-disposable-repo-v2",
  "mode": $(json_escape "$mode"),
  "task": $(json_escape "$task_name"),
  "created_at": $(json_escape "$timestamp"),
  "history_depth": $(if [[ -n "$history_depth" ]]; then json_escape "$history_depth"; else printf 'null'; fi),
  "source": {
    "root_basename": $(json_escape "$(basename "$source_root")"),
    "branch": $(json_escape "$branch"),
    "head": $(json_escape "$head_sha")
  },
  "file_count": $file_count,
  "files": $files_json
}
EOF
}

init_disposable_repo() {
    local pack_dir="$1"

    git -C "$pack_dir" init -q
    git -C "$pack_dir" config user.name "ChatGPT Pack Bot"
    git -C "$pack_dir" config user.email "chatgpt-pack@example.invalid"
    git -C "$pack_dir" add .
    git -C "$pack_dir" commit -q -m "base"
}

next_counter() {
    local out_dir="$1"
    local state_file="$out_dir/.chatgpt-pack-counter"
    local n=1

    mkdir -p "$out_dir"

    if [[ -f "$state_file" ]]; then
        n="$(cat "$state_file")"
        [[ "$n" =~ ^[0-9]+$ ]] || n=0
        n=$((n + 1))
    fi

    printf '%s\n' "$n" > "$state_file"
    printf '%03d' "$n"
}

make_archive_name() {
    local out_dir="$1"
    local mode="$2"
    local task="$3"

    local timestamp
    timestamp="$(date +%Y%m%d-%H%M)"

    local base="$out_dir/chatgpt-pack-${mode}-${task}-${timestamp}"
    local candidate="${base}.tar.gz"

    if [[ ! -e "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return
    fi

    local i=1
    while true; do
        candidate="${base} (${i}).tar.gz"
        if [[ ! -e "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return
        fi
        i=$((i + 1))
    done
}

create_clean_pack_dir() {
    local tmp_parent="$1"
    local pack_dir="$tmp_parent/chatgpt-pack"
    mkdir -p "$pack_dir"
    printf '%s\n' "$pack_dir"
}

archive_pack_dir() {
    local pack_dir="$1"
    local archive="$2"

    local parent
    parent="$(dirname "$pack_dir")"

    tar -C "$parent" -czf "$archive" "$(basename "$pack_dir")"
    printf '%s\n' "$archive"
}

ensure_clean_or_warn() {
    local root="$1"

    if ! git -C "$root" diff --quiet || ! git -C "$root" diff --cached --quiet; then
        warn "repository has uncommitted tracked changes; packed files reflect working tree state"
    fi
}

print_result() {
    local archive="$1"
    local mode="$2"

    echo
    echo "Created:"
    echo "  $archive"
    echo
    echo "Archive root:"
    echo "  chatgpt-pack/"
    echo
    if [[ "$mode" == "history" ]]; then
        echo "History mode warning:"
        echo "  This archive may contain private git history. Share it only intentionally."
        echo
    fi
    echo "Check:"
    echo "  tar tzf \"$archive\" | head"
}

pack_full() {
    local root="$1"
    local task="$2"
    local include_untracked="$3"
    local tmp_parent="$4"
    local out_dir="$5"

    local pack_dir
    pack_dir="$(create_clean_pack_dir "$tmp_parent")"

    local count=0
    local c

    c="$(collect_tracked_files | copy_paths_from_nul_stream "$root" "$pack_dir")"
    count=$((count + c))

    if [[ "$include_untracked" == "1" ]]; then
        c="$(collect_untracked_files | copy_paths_from_nul_stream "$root" "$pack_dir")"
        count=$((count + c))
    fi

    [[ "$count" -gt 0 ]] || die "no files copied"

    write_usage_file "$pack_dir"
    write_sha256_manifest "$pack_dir"
    write_meta_json "$pack_dir" "full" "$task" "$root" "$count"
    init_disposable_repo "$pack_dir"

    local archive
    archive="$(make_archive_name "$out_dir" "full" "$task" "$pack_dir")"
    archive_pack_dir "$pack_dir" "$archive"
    print_result "$archive" "full"
}

pack_slice() {
    local root="$1"
    local task="$2"
    local tmp_parent="$3"
    local out_dir="$4"
    shift 4

    [[ "$#" -gt 0 ]] || die "slice mode requires at least one path"

    local pack_dir
    pack_dir="$(create_clean_pack_dir "$tmp_parent")"

    local tmp_list="$tmp_parent/git-known-files.nul"
    collect_git_known_files > "$tmp_list"

    local count=0
    local c
    local p

    for p in "$@"; do
        c="$(copy_slice_path "$root" "$pack_dir" "$p" "$tmp_list")"
        count=$((count + c))
    done

    [[ "$count" -gt 0 ]] || die "no files copied"

    write_usage_file "$pack_dir"
    write_sha256_manifest "$pack_dir"
    write_meta_json "$pack_dir" "slice" "$task" "$root" "$count"
    init_disposable_repo "$pack_dir"

    local archive
    archive="$(make_archive_name "$out_dir" "slice" "$task" "$pack_dir")"
    archive_pack_dir "$pack_dir" "$archive"
    print_result "$archive" "slice"
}

pack_changed() {
    local root="$1"
    local task="$2"
    local tmp_parent="$3"
    local out_dir="$4"

    local pack_dir
    pack_dir="$(create_clean_pack_dir "$tmp_parent")"

    local count
    count="$(collect_changed_files | copy_paths_from_nul_stream "$root" "$pack_dir")"

    [[ "$count" -gt 0 ]] || die "no changed or untracked files to pack"

    write_usage_file "$pack_dir"
    write_sha256_manifest "$pack_dir"
    write_meta_json "$pack_dir" "changed" "$task" "$root" "$count"
    init_disposable_repo "$pack_dir"

    local archive
    archive="$(make_archive_name "$out_dir" "changed" "$task" "$pack_dir")"
    archive_pack_dir "$pack_dir" "$archive"
    print_result "$archive" "changed"
}

pack_history() {
    local root="$1"
    local task="$2"
    local depth="$3"
    local tmp_parent="$4"
    local out_dir="$5"

    warn "history mode can include private commit messages, deleted code, old secrets, branches reachable from HEAD, and authorship data"
    warn "use full/slice/changed for normal patch work"

    local pack_dir="$tmp_parent/chatgpt-pack"

    if [[ "$depth" == "0" ]]; then
        git clone -q "file://$root" "$pack_dir"
    else
        git clone -q --depth "$depth" "file://$root" "$pack_dir"
    fi

    (
        cd "$root"
        git diff --binary HEAD > "$tmp_parent/working-tree.patch"
    )

    if [[ -s "$tmp_parent/working-tree.patch" ]]; then
        if ! git -C "$pack_dir" apply --index "$tmp_parent/working-tree.patch"; then
            warn "could not apply working tree diff to history pack"
            warn "packing committed history only"
        fi
    fi

    write_usage_file "$pack_dir"
    write_sha256_manifest "$pack_dir"
    write_meta_json "$pack_dir" "history" "$task" "$root" "$(git -C "$pack_dir" ls-files | wc -l | tr -d ' ')" "$depth"

    git -C "$pack_dir" add CHATGPT_PACK_USAGE.md patch.base.sha256 patch.meta.json
    git -C "$pack_dir" commit -q -m "Add ChatGPT pack metadata" || true

    local archive
    archive="$(make_archive_name "$out_dir" "history" "$task" "$pack_dir")"
    archive_pack_dir "$pack_dir" "$archive"
    print_result "$archive" "history"
}

main() {
    need_cmd git
    need_cmd tar
    need_cmd sha256sum
    need_cmd python3
    need_cmd find
    need_cmd awk
    need_cmd sed
    need_cmd date

    [[ "$#" -ge 1 ]] || { usage; exit 1; }

    local mode="$1"
    shift

    case "$mode" in
        -h|--help|help)
            usage
            exit 0
            ;;
    esac

    local root
    root="$(repo_root)"
    cd "$root"

    local task_raw="${1:-}"
    [[ -n "$task_raw" ]] || { usage; die "missing task name"; }
    shift

    local task
    task="$(sanitize_task_name "$task_raw")"

    local tmp_parent
    tmp_parent="$(mktemp -d)"
    trap 'rm -rf "$tmp_parent"' EXIT

    local out_dir="${CHATGPT_PACK_OUT_DIR:-$root/chatgpt-packs}"
    mkdir -p "$out_dir"

    ensure_clean_or_warn "$root"

    case "$mode" in
        full)
            local include_untracked="0"
            while [[ "$#" -gt 0 ]]; do
                case "$1" in
                    --include-untracked) include_untracked="1" ;;
                    *) die "unknown full option: $1" ;;
                esac
                shift
            done
            pack_full "$root" "$task" "$include_untracked" "$tmp_parent" "$out_dir"
            ;;
        slice)
            pack_slice "$root" "$task" "$tmp_parent" "$out_dir" "$@"
            ;;
        changed)
            [[ "$#" -eq 0 ]] || die "changed mode does not accept paths/options"
            pack_changed "$root" "$task" "$tmp_parent" "$out_dir"
            ;;
        history)
            local depth="50"
            while [[ "$#" -gt 0 ]]; do
                case "$1" in
                    --depth)
                        shift
                        [[ "${1:-}" =~ ^[0-9]+$ ]] || die "--depth requires a number; use 0 for full history"
                        depth="$1"
                        ;;
                    --full-history)
                        depth="0"
                        ;;
                    *)
                        die "unknown history option: $1"
                        ;;
                esac
                shift
            done
            pack_history "$root" "$task" "$depth" "$tmp_parent" "$out_dir"
            ;;
        *)
            usage
            die "unknown mode: $mode"
            ;;
    esac
}

main "$@"