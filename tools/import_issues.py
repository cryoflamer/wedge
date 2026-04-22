#!/usr/bin/env python3
"""
Import GitHub issues from CSV using gh CLI.

Features:
- creates issues from CSV columns: title, body
- supports global labels via --labels
- supports per-row labels via CSV column "labels"
- creates missing labels automatically
- supports milestone and assignee
- has dry-run mode

CSV columns:
- title   (required)
- body    (required)
- labels  (optional, comma-separated)
- assignees (optional, comma-separated)
- milestone (optional)
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


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
        # tolerate race / already exists
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


def create_issue(
        repo: str,
        title: str,
        body: str,
        labels: list[str],
        assignees: list[str],
        milestone: str | None,
        dry_run: bool,
) -> None:
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
        return

    result = run(cmd, capture_output=True)
    if result.returncode != 0:
        die(f"Failed to create issue '{title}'.\n{result.stderr}")
    print(result.stdout.strip())


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
        "--dry-run",
        action="store_true",
        help="Print actions without creating labels/issues",
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
            labels = uniq_keep_order([*global_labels, *row_labels])

            row_assignees = parse_csv_list(row.get("assignees"))
            assignees = row_assignees if row_assignees else default_assignees

            milestone = (row.get("milestone") or "").strip() or default_milestone

            ensure_labels_exist(args.repo, labels, existing_labels, args.dry_run)

            print(f"\nCreating issue from row {idx}: {title}")
            create_issue(
                repo=args.repo,
                title=title,
                body=body,
                labels=labels,
                assignees=assignees,
                milestone=milestone,
                dry_run=args.dry_run,
            )

        print(f"\nDone. Processed {row_count} row(s).")


if __name__ == "__main__":
    main()
