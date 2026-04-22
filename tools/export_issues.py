#!/usr/bin/env python3
"""
Export GitHub issues to CSV for prompt-generation workflow.

Default behavior:
- export OPEN issues only

Supports:
- export all matching issues
- filter by issue number range
- filter by labels
- include closed/all states if requested

Output CSV columns:
- issue
- title
- body
- labels
- state
- url

Examples:
  python3 export_issues.py --repo cryoflamer/wedge
  python3 export_issues.py --repo cryoflamer/wedge --from 16 --to 25
  python3 export_issues.py --repo cryoflamer/wedge --labels ui,interaction
  python3 export_issues.py --repo cryoflamer/wedge --state all
  python3 export_issues.py --repo cryoflamer/wedge --labels ui --from 10 --to 30 --output issues.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print(">>", " ".join(cmd), file=sys.stderr)
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


def fetch_issues(repo: str, state: str, labels: list[str], limit: int) -> list[dict]:
    cmd = [
        "gh", "issue", "list",
        "--repo", repo,
        "--limit", str(limit),
        "--state", state,
        "--json", "number,title,body,state,url,labels",
    ]
    for label in labels:
        cmd += ["--label", label]

    result = run(cmd, capture_output=True)
    if result.returncode != 0:
        die(f"Failed to fetch issues from repo {repo}.\n{result.stderr}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        die(f"Failed to parse GitHub CLI JSON output: {exc}")

    return data


def normalize_state(state: str) -> str:
    state = state.strip().lower()
    if state not in {"open", "closed", "all"}:
        die("Invalid --state. Use: open, closed, or all")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Export GitHub issues to CSV")
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/repo format")
    parser.add_argument("--output", default="issues_export.csv", help="Output CSV path")
    parser.add_argument("--state", default="open", help="Issue state: open | closed | all (default: open)")
    parser.add_argument("--labels", help="Comma-separated labels to filter by")
    parser.add_argument("--from", dest="issue_from", type=int, help="Minimum issue number (inclusive)")
    parser.add_argument("--to", dest="issue_to", type=int, help="Maximum issue number (inclusive)")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum number of issues to fetch from GitHub (default: 1000)")
    parser.add_argument("--sort", choices=["asc", "desc"], default="asc", help="Sort by issue number (default: asc)")

    args = parser.parse_args()

    ensure_gh_available()
    ensure_gh_auth()

    state = normalize_state(args.state)
    labels = parse_csv_list(args.labels)

    if args.issue_from is not None and args.issue_to is not None and args.issue_from > args.issue_to:
        die("--from must be <= --to")

    issues = fetch_issues(args.repo, state, labels, args.limit)

    filtered: list[dict] = []
    for item in issues:
        number = int(item["number"])
        if args.issue_from is not None and number < args.issue_from:
            continue
        if args.issue_to is not None and number > args.issue_to:
            continue
        filtered.append(item)

    filtered.sort(key=lambda x: int(x["number"]), reverse=(args.sort == "desc"))

    output_path = Path(args.output)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["issue", "title", "body", "labels", "state", "url"],
        )
        writer.writeheader()

        for item in filtered:
            labels_joined = ",".join(label["name"] for label in item.get("labels", []))
            writer.writerow(
                {
                    "issue": item["number"],
                    "title": item["title"],
                    "body": item["body"],
                    "labels": labels_joined,
                    "state": item["state"],
                    "url": item["url"],
                }
            )

    print(f"Exported {len(filtered)} issue(s) to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
