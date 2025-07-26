#!/usr/bin/env python3
"""Generate release notes from GitHub releases in Jupyter organizations."""

import json
import re
import subprocess
import sys
import shutil
import yaml
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
BOT_USERNAMES = [
    "dependabot",
    "dependabot[bot]",
    "dependabot-preview[bot]",
    "changeset-bot",
    "changeset-bot[bot]",
    "github-actions[bot]",
    "github-actions",
    "renovate",
    "renovate[bot]",
    "greenkeeper[bot]",
    "greenkeeper",
    "snyk-bot",
    "snyk-bot[bot]",
    "mergify[bot]",
    "mergify",
    "bors",
    "bors[bot]",
    "homu",
    "homu[bot]",
    "jupyterlab-probot",
    "meeseeksmachine",
    "lumberbot-app",
]

CONTRIBUTOR_PATTERNS = [
    r"\*\*Contributors to this release\*\*.*$",
    r"Contributors to this release.*$",
    r"\*\*Contributors\*\*.*$",
    r"Contributors:.*$",
    r"New Contributors.*$",
    r"\*\*New Contributors\*\*.*$",
]

BOT_PATTERNS = [
    "bump ",
    "dependency update",
    "update dependencies",
    "automated dependency",
    "automated update",
    "chore:",
    "ci:",
    "build:",
    "maintenance:",
]


def format_date(date_str):
    """Convert ISO date to readable format."""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    day = date_obj.day
    suffix = (
        "th" if 4 <= day <= 20 or 24 <= day <= 30 else ["st", "nd", "rd"][day % 10 - 1]
    )
    return f"{date_obj.strftime('%B')} {day}{suffix}, {date_obj.year}"


def gh_api(endpoint):
    """Run GitHub CLI API command and return JSON result."""
    try:
        result = subprocess.run(
            ["gh", "api", endpoint, "--paginate"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def fetch_releases(org_name, repo_name, months):
    """Fetch recent releases for a repository."""
    n_months_ago = datetime.now() - timedelta(days=months * 30)
    releases = gh_api(f"repos/{org_name}/{repo_name}/releases")

    recent_releases = []
    for release in releases:
        if not release.get("prerelease", False) and release.get("published_at"):
            release_date = datetime.strptime(release["published_at"][:10], "%Y-%m-%d")
            if release_date >= n_months_ago:
                release["repo_name"] = repo_name
                recent_releases.append(release)

    return recent_releases


def clean_text(text):
    """Clean and format release text."""
    if not text:
        return ""

    # Remove unwanted patterns
    for pattern in CONTRIBUTOR_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    # Filter out bot-related lines
    lines = []
    for line in text.splitlines():
        line_lower = line.lower()

        # Skip separator lines and changelog links
        if (
            line.strip() == "---"
            or line.strip() == "****"
            or "full changelog" in line_lower
        ):
            continue

        # Skip contributor-related lines
        if any(
            phrase in line_lower
            for phrase in [
                "made their first contribution",
                "contributors page",
                "graphs/contributors",
            ]
        ):
            continue

        # Skip lines that are primarily about bot activity (not just mentions)
        if any(pattern in line_lower for pattern in BOT_PATTERNS):
            continue

        # Skip PRs authored by bots (bot is the primary author)
        # Look for patterns like "by @botname" or "botname in" at the beginning of the line
        if any(
            line_lower.startswith(f"by @{bot}")
            or line_lower.startswith(f"{bot} in")
            or line_lower.startswith(f"by {bot}")
            or f" by [`@{bot}`]" in line_lower
            for bot in BOT_USERNAMES
        ):
            continue

        # Convert headers to bold
        if line.startswith("#"):
            content = line.lstrip("#").strip()
            line = f"**{content}**"

        # Convert usernames to links with backticks
        line = re.sub(
            r"(?<!\[)(?<!`)@([\w\-\[\]]+)(?!\])",
            r"[`@\1`](https://github.com/\1)",
            line,
        )

        lines.append(line)

    text = "\n".join(lines).strip()
    return remove_empty_sections(text)


def remove_empty_sections(text):
    """Remove empty sections (headers with no content)."""
    lines = text.splitlines()
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # If this is a bold header (starts with ** and ends with **)
        if line.strip().startswith("**") and line.strip().endswith("**"):
            # Look ahead to see if the next non-empty line is another header
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1

            # If we found another header or reached the end, skip this empty section
            if j >= len(lines) or (
                lines[j].strip().startswith("**") and lines[j].strip().endswith("**")
            ):
                i = j
                continue

        result.append(line)
        i += 1

    return "\n".join(result)


def write_release_file(org_name, org_url, releases, months, file_path):
    """Write release notes to markdown file."""
    with open(file_path, "w") as f:
        # YAML header
        f.write("---\n")
        f.write(f"title: {org_name}\n")
        f.write(f'date: "{datetime.now().strftime("%Y-%m-%d")}"\n')
        f.write(f"author: {org_name}\n")
        f.write("tags:\n  - release\n")
        f.write(f"  - {org_name.lower().replace(' ', '-')}\n")
        f.write("---\n\n")

        # Organization link
        f.write(f"Releases for the [{org_name}]({org_url}) organization.\n\n")

        if not releases:
            f.write(f"No releases found in the last {months} months.\n")
            return

        # Write each release
        for release in releases:
            title = release["name"] or release["tag_name"]
            repo_name = release["repo_name"]

            # Add repo name to title if not already present
            if repo_name.lower().replace("-", "").replace("_", "").replace(
                " ", ""
            ) not in title.lower().replace("-", "").replace("_", "").replace(" ", ""):
                title = f"{repo_name} {title}"

            formatted_date = format_date(release["published_at"][:10])
            body = clean_text(release["body"])

            f.write(f"# {title} - {formatted_date}\n\n")
            f.write(f"[View on GitHub]({release['html_url']})\n\n")
            if body:
                f.write(body + "\n\n")
            f.write("---\n\n")


def main():
    parser = argparse.ArgumentParser(
        description="Generate release notes from GitHub releases"
    )
    parser.add_argument(
        "--months", "-m", type=int, default=12, help="Months to look back (default: 12)"
    )
    parser.add_argument(
        "--n-repositories", "-n", type=int, help="Limit repositories per org"
    )
    args = parser.parse_args()

    # Check GitHub CLI
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: GitHub CLI (gh) not found. Install from: https://cli.github.com/")
        sys.exit(1)

    # Load organizations
    try:
        with open("src/jupyter_orgs.yml", "r") as f:
            organizations = yaml.safe_load(f).get("organizations", [])
    except FileNotFoundError:
        print("Error: src/jupyter_orgs.yml not found")
        sys.exit(1)

    if not organizations:
        print("Error: No organizations found")
        sys.exit(1)

    # Setup output directory
    releases_dir = Path("docs/releases")
    if releases_dir.exists():
        shutil.rmtree(releases_dir)
    releases_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing {len(organizations)} organizations...")

    # Process each organization
    for org in organizations:
        org_name = org["name"]
        org_url = org["url"]
        org_short = org_url.split("/")[-1]

        print(f"\nProcessing {org_name}...")

        # Fetch repositories
        repos = gh_api(f"orgs/{org_short}/repos")
        if not repos:
            print(f"No repositories found for {org_name}")
            continue

        if args.n_repositories:
            repos = repos[: args.n_repositories]

        # Fetch releases
        all_releases = []
        for repo in repos:
            repo_name = repo["name"]
            print(f"  Fetching releases from {repo_name}...")
            releases = fetch_releases(org_short, repo_name, args.months)
            all_releases.extend(releases)

        # Sort by date (newest first)
        all_releases.sort(key=lambda x: x["published_at"], reverse=True)

        print(
            f"  Found {len(all_releases)} releases from the last {args.months} months"
        )

        # Write file
        filename = org_name.lower().replace(" ", "-").replace("&", "and") + ".md"
        file_path = releases_dir / filename
        write_release_file(org_name, org_url, all_releases, args.months, file_path)

    print("\nRelease posts generated successfully!")


if __name__ == "__main__":
    main()
