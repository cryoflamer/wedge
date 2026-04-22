#!/usr/bin/env python3
"""
Import GitHub issues from CSV using gh CLI.

Backward compatible with old CSV format.

Supported CSV columns:
- title            (required)
- body             (required)
- labels           (optional, comma-separated)
- assignees        (optional, comma-separated)
- milestone        (optional)
- codex_mode       (optional: fast | normal | thinking)
- agent_prompt     (optional: comment body to add after issue creation)
- agent_comment    (optional alias for agent_prompt)

Features:
- creates issues from CSV
- supports global labels via --labels
- supports per-row labels via CSV column "labels"
- creates missing labels automatically
- supports milestone and assignees
- supports dry-run mode
- can add Codex mode labels automatically from codex_mode
- can add an initial issue comment with agent prompt
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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


def normalize_codex_mode(value: str | None) -> str | None:
    if not value:
        return None
    mode = value.strip().lower()
    return mode if mode in CODEX_MODE_TO_LABEL else None


def extract_issue_number(issue_url: str) -> int | None:
    match = re.search(r'/issues/(\d+)$', issue_url.strip())
    if not match:
        return None
    return int(match.group(1))


def create_issue(
        repo: str,
        title: str,
        body: str,
        labels: list[str],
        assignees: list[str],
        milestone: str | None,
        dry_run: bool,
) -> str | None:
    cmd = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
    ]

    for label in labels:
        cmd += ["--label", label]

    for assignee in assignees:
        cmd += ["--assignee", assignee]

    if milestone:
        cmd += ["--milestone", milestone]

    if dry_run:
        print("[DRY RUN]", " ".join(cmd))
        return None

    result = run(cmd, capture_output=True)
    if result.returncode != 0:
        die(f"Failed to create issue '{title}'.\n{result.stderr}")

    issue_ref = result.stdout.strip()
    print(issue_ref)
    return issue_ref


def add_issue_comment(
        repo: str,
        issue_number: int,
        comment_body: str,
        dry_run: bool,
) -> None:
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
    parser = argparse.ArgumentParser(description="Import GitHub issues from CSV using gh CLI")
    parser.add_argument("csv", help="Path to CSV file")
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/repo format")
    parser.add_argument(
        "--labels",
        help="Global comma-separated labels applied to all issues, e.g. ui,refactor",
    )
    parser.add_argument(
        "--default-milestone",
        help="Default milestone for rows that do not specify their own milestone",
    )
    parser.add_argument(
        "--default-assignees",
        help="Default comma-separated assignees for rows that do not specify assignees",
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
        help="Print actions without creating labels/issues/comments",
    )

    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        die(f"CSV file not found: {csv_path}")

    ensure_gh_available()
    ensure_gh_auth()

    global_labels = parse_csv_list(args.labels)
    default_assignees = parse_csv_list(args.default_assignees)
    default_milestone = args.default_milestone
    default_codex_mode = normalize_codex_mode(args.default_codex_mode)

    if args.default_codex_mode and not default_codex_mode:
        die("Invalid --default-codex-mode. Use: fast, normal, or thinking")

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            die("CSV has no header row.")

        required = {"title", "body"}
        missing = required - set(reader.fieldnames)
        if missing:
            die(f"CSV missing required columns: {', '.join(sorted(missing))}")

        existing_labels = get_existing_labels(args.repo)

        row_count = 0
        for idx, row in enumerate(reader, start=2):
            row_count += 1
            title = (row.get("title") or "").strip()
            body = (row.get("body") or "").strip()

            if not title:
                print(f"Skipping row {idx}: empty title")
                continue

            row_labels = parse_csv_list(row.get("labels"))
            codex_mode = normalize_codex_mode(row.get("codex_mode")) or default_codex_mode

            labels = [*global_labels, *row_labels]
            if codex_mode and not args.no_codex_mode_labels:
                labels.append(CODEX_MODE_TO_LABEL[codex_mode])
            labels = uniq_keep_order(labels)

            row_assignees = parse_csv_list(row.get("assignees"))
            assignees = row_assignees if row_assignees else default_assignees

            milestone = (row.get("milestone") or "").strip() or default_milestone
            agent_prompt = (row.get("agent_prompt") or row.get("agent_comment") or "").strip()

            ensure_labels_exist(args.repo, labels, existing_labels, args.dry_run)

            print(f"\nCreating issue from row {idx}: {title}")
            issue_ref = create_issue(
                repo=args.repo,
                title=title,
                body=body,
                labels=labels,
                assignees=assignees,
                milestone=milestone,
                dry_run=args.dry_run,
            )

            if agent_prompt:
                comment_body = build_agent_comment(agent_prompt, codex_mode)
                if args.dry_run:
                    print(f"[DRY RUN] would add comment to created issue for row {idx}:")
                    print(comment_body)
                else:
                    if not issue_ref:
                        die(f"Could not determine issue reference for '{title}'")
                    issue_number = extract_issue_number(issue_ref)
                    if issue_number is None:
                        die(f"Could not parse issue number from: {issue_ref}")
                    print(f"Adding agent comment to issue #{issue_number}")
                    add_issue_comment(
                        repo=args.repo,
                        issue_number=issue_number,
                        comment_body=comment_body,
                        dry_run=args.dry_run,
                    )

        print(f"\nDone. Processed {row_count} row(s).")


if __name__ == "__main__":
    main()
