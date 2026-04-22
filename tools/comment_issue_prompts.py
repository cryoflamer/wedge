#!/usr/bin/env python3
"""
Add agent prompt comments to existing GitHub issues from CSV using gh CLI.

CSV columns:
- issue          (required) issue number
- agent_prompt   (required unless agent_comment is provided)
- agent_comment  (optional alias for agent_prompt)
- codex_mode     (optional: fast | normal | thinking)
- labels         (optional, comma-separated labels to add)
- assignees      (optional, comma-separated assignees to add)

Features:
- adds a comment with agent prompt to existing issues
- can add Codex mode labels automatically from codex_mode
- can add arbitrary labels from CSV
- creates missing labels automatically
- backward-friendly minimal CSV supported
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


CODEX_MODE_TO_LABEL = {
    "fast": "codex:fast",
    "normal": "codex:normal",
    "thinking": "codex:thinking",
}


def run(cmd: list[str], capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print(">>", " ".join(cmd))
    return subprocess.run(
        cmd,
        text=True,
        capture_output=capture_output,
        check=False,
    )


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def ensure_gh_available() -> None:
    try:
        result = subprocess.run(
            ["gh", "--version"],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        die("gh CLI not found. Install GitHub CLI first.")
    if result.returncode != 0:
        die("gh CLI is installed but not working correctly.")


def ensure_gh_auth() -> None:
    result = subprocess.run(
        ["gh", "auth", "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        die("gh is not authenticated. Run: gh auth login")


def parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def uniq_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def normalize_codex_mode(value: str | None) -> str | None:
    if not value:
        return None
    mode = value.strip().lower()
    return mode if mode in CODEX_MODE_TO_LABEL else None


def get_existing_labels(repo: str) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    page = 1

    while True:
        cmd = [
            "gh", "api",
            f"repos/{repo}/labels",
            "--method", "GET",
            "-f", "per_page=100",
            "-f", f"page={page}",
        ]
        result = run(cmd, capture_output=True)
        if result.returncode != 0:
            die(f"Failed to fetch labels for repo {repo}.\n{result.stderr}")

        data = json.loads(result.stdout)
        if not data:
            break

        for item in data:
            labels[item["name"]] = item

        if len(data) < 100:
            break
        page += 1

    return labels


def create_label(repo: str, name: str, color: str = "d4c5f9", description: str = "") -> None:
    cmd = [
        "gh", "label", "create", name,
        "--repo", repo,
        "--color", color,
    ]
    if description:
        cmd += ["--description", description]

    result = run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").lower()
        stdout = (result.stdout or "").lower()
        if "already exists" in stderr or "already exists" in stdout:
            return
        die(f"Failed to create label '{name}'.\n{result.stderr}")


def ensure_labels_exist(repo: str, labels: Iterable[str], existing_labels: dict[str, dict], dry_run: bool) -> None:
    for label in labels:
        if label in existing_labels:
            continue
        if dry_run:
            print(f"[DRY RUN] would create missing label: {label}")
        else:
            print(f"Creating missing label: {label}")
            create_label(repo, label)
            existing_labels[label] = {"name": label}


def issue_exists(repo: str, issue_number: int) -> bool:
    cmd = [
        "gh", "issue", "view", str(issue_number),
        "--repo", repo,
        "--json", "number",
    ]
    result = run(cmd, capture_output=True)
    return result.returncode == 0


def add_labels_to_issue(repo: str, issue_number: int, labels: list[str], dry_run: bool) -> None:
    if not labels:
        return
    cmd = [
        "gh", "issue", "edit", str(issue_number),
        "--repo", repo,
    ]
    for label in labels:
        cmd += ["--add-label", label]
    if dry_run:
        print("[DRY RUN]", " ".join(cmd))
        return
    result = run(cmd, capture_output=True)
    if result.returncode != 0:
        die(f"Failed to add labels to issue #{issue_number}.\n{result.stderr}")


def add_assignees_to_issue(repo: str, issue_number: int, assignees: list[str], dry_run: bool) -> None:
    if not assignees:
        return
    cmd = [
        "gh", "issue", "edit", str(issue_number),
        "--repo", repo,
    ]
    for assignee in assignees:
        cmd += ["--add-assignee", assignee]
    if dry_run:
        print("[DRY RUN]", " ".join(cmd))
        return
    result = run(cmd, capture_output=True)
    if result.returncode != 0:
        die(f"Failed to add assignees to issue #{issue_number}.\n{result.stderr}")


def add_issue_comment(repo: str, issue_number: int, comment_body: str, dry_run: bool) -> None:
    cmd = [
        "gh", "issue", "comment", str(issue_number),
        "--repo", repo,
        "--body", comment_body,
    ]
    if dry_run:
        print("[DRY RUN]", " ".join(cmd))
        return
    result = run(cmd, capture_output=True)
    if result.returncode != 0:
        die(f"Failed to add comment to issue #{issue_number}.\n{result.stderr}")
    output = result.stdout.strip()
    if output:
        print(output)


def build_agent_comment(agent_prompt: str, codex_mode: str | None) -> str:
    parts: list[str] = []
    if codex_mode:
        parts.append(f"Recommended mode: {codex_mode}")
        parts.append("")
    parts.append("Agent prompt:")
    parts.append("")
    parts.append(agent_prompt.strip())
    return "\n".join(parts).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Add agent prompt comments to existing GitHub issues from CSV")
    parser.add_argument("csv", help="Path to CSV file")
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/repo format")
    parser.add_argument(
        "--labels",
        help="Global comma-separated labels applied to all referenced issues",
    )
    parser.add_argument(
        "--default-codex-mode",
        help="Default codex mode for rows that do not specify codex_mode (fast|normal|thinking)",
    )
    parser.add_argument(
        "--no-codex-mode-labels",
        action="store_true",
        help="Do not add codex:* labels automatically from codex_mode",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without creating comments/labels",
    )

    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        die(f"CSV file not found: {csv_path}")

    ensure_gh_available()
    ensure_gh_auth()

    global_labels = parse_csv_list(args.labels)
    default_codex_mode = normalize_codex_mode(args.default_codex_mode)

    if args.default_codex_mode and not default_codex_mode:
        die("Invalid --default-codex-mode. Use: fast, normal, or thinking")

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            die("CSV has no header row.")

        required = {"issue"}
        missing = required - set(reader.fieldnames)
        if missing:
            die(f"CSV missing required columns: {', '.join(sorted(missing))}")

        existing_labels = get_existing_labels(args.repo)

        row_count = 0
        for idx, row in enumerate(reader, start=2):
            row_count += 1

            issue_raw = (row.get("issue") or "").strip()
            if not issue_raw:
                print(f"Skipping row {idx}: empty issue number")
                continue
            try:
                issue_number = int(issue_raw)
            except ValueError:
                die(f"Invalid issue number in row {idx}: {issue_raw}")

            agent_prompt = (row.get("agent_prompt") or row.get("agent_comment") or "").strip()
            if not agent_prompt:
                print(f"Skipping row {idx}: empty agent prompt")
                continue

            codex_mode = normalize_codex_mode(row.get("codex_mode")) or default_codex_mode
            row_labels = parse_csv_list(row.get("labels"))
            labels = [*global_labels, *row_labels]
            if codex_mode and not args.no_codex_mode_labels:
                labels.append(CODEX_MODE_TO_LABEL[codex_mode])
            labels = uniq_keep_order(labels)

            assignees = parse_csv_list(row.get("assignees"))

            if not args.dry_run and not issue_exists(args.repo, issue_number):
                die(f"Issue #{issue_number} does not exist in repo {args.repo}")

            ensure_labels_exist(args.repo, labels, existing_labels, args.dry_run)

            print(f"\nUpdating issue #{issue_number} from row {idx}")
            add_labels_to_issue(args.repo, issue_number, labels, args.dry_run)
            add_assignees_to_issue(args.repo, issue_number, assignees, args.dry_run)

            comment_body = build_agent_comment(agent_prompt, codex_mode)
            if args.dry_run:
                print(f"[DRY RUN] would add comment to issue #{issue_number}:")
                print(comment_body)
            else:
                add_issue_comment(args.repo, issue_number, comment_body, args.dry_run)

        print(f"\nDone. Processed {row_count} row(s).")


if __name__ == "__main__":
    main()
