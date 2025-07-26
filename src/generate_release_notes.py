#!/usr/bin/env python3
"""
Script to generate release notes from GitHub releases in Jupyter organizations.
"""

import json
import subprocess
import sys
import shutil
import yaml
import argparse
from datetime import datetime, timedelta
from pathlib import Path

today = datetime.now().strftime("%Y-%m-%d")


def format_date(date_str):
    """Convert ISO date string to readable format like 'June 17th, 2025'"""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    month = date_obj.strftime("%B")
    day = date_obj.day
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    year = date_obj.year
    return f"{month} {day}{suffix}, {year}"


def load_organizations(yaml_file):
    """Load organizations from YAML file"""
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)
    return data.get("organizations", [])


def get_org_name_from_url(url):
    """Extract organization name from GitHub URL"""
    return url.split("/")[-1]


def fetch_repositories(org_url):
    """Fetch all repositories for an organization"""
    org_name = get_org_name_from_url(org_url)
    print(f"Fetching all repositories from {org_name} organization...")

    try:
        result = subprocess.run(
            ["gh", "api", f"orgs/{org_name}/repos", "--paginate"],
            capture_output=True,
            text=True,
            check=True,
        )
        repos = json.loads(result.stdout)
        return repos
    except subprocess.CalledProcessError as e:
        print(f"Error fetching repositories for {org_name}: {e}")
        return []


def fetch_releases_from_last_n_months(org_url, repo_name, months=6):
    """Fetch releases from the last n months for a specific repository"""
    org_name = get_org_name_from_url(org_url)
    n_months_ago = datetime.now() - timedelta(days=months * 30)

    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org_name}/{repo_name}/releases", "--paginate"],
            capture_output=True,
            text=True,
            check=True,
        )
        releases = json.loads(result.stdout)

        # Filter releases from the last n months and exclude pre-releases
        recent_releases = []
        for release in releases:
            if release.get("published_at"):
                release_date = datetime.strptime(
                    release["published_at"][:10], "%Y-%m-%d"
                )
                # Skip if it's a pre-release (alpha, beta, etc.)
                if release.get("prerelease", False):
                    continue
                if release_date >= n_months_ago:
                    release["repo_name"] = repo_name
                    recent_releases.append(release)

        return recent_releases
    except subprocess.CalledProcessError:
        print(f"No releases found for {org_name}/{repo_name}")
        return []
    except json.JSONDecodeError:
        print(f"Error parsing releases for {org_name}/{repo_name}")
        return []


def clean_release_body(body):
    """Remove only the '**Full Changelog**' line from the release body."""
    lines = body.splitlines()
    cleaned_lines = [line for line in lines if "full changelog" not in line.lower()]
    return "\n".join(cleaned_lines).strip()


def convert_headers_to_bold(text):
    """Convert all markdown headers to bold text."""
    lines = text.splitlines()
    result = []
    for line in lines:
        if line.startswith("#"):
            # Count the number of # at the start
            header_level = len(line) - len(line.lstrip("#"))
            # Remove the # and strip whitespace
            content = line[header_level:].strip()
            # Convert to bold
            result.append(f"**{content}**")
        else:
            result.append(line)
    return "\n".join(result)


def convert_github_usernames_to_links(text):
    """Convert GitHub usernames (starting with @) to markdown links."""
    import re

    # Only convert @usernames that are not already in markdown links or backticks
    # Use negative lookbehind and lookahead to avoid double-processing
    pattern = r"(?<!\[)(?<!`)@([\w\-\[\]]+)(?!\])"
    replacement = r"[@\1](https://github.com/\1)"
    return re.sub(pattern, replacement, text)


def add_backticks_to_usernames_in_links(text):
    """Add single backticks around usernames in markdown links that don't have them."""
    import re

    # Find markdown links that contain usernames and don't already have backticks
    # Pattern: [@username](https://github.com/username) where username is not already in backticks
    pattern = r"(\[)@([\w\-\[\]]+)(\]\(https://github.com/\2\))(?!`)"
    replacement = r"\1`@\2`\3"
    return re.sub(pattern, replacement, text)


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Generate release notes from GitHub releases"
    )
    parser.add_argument(
        "--months",
        "-m",
        type=int,
        default=6,
        help="Number of months to look back for releases (default: 6)",
    )
    parser.add_argument(
        "--n-repositories",
        "-n",
        type=int,
        default=None,
        help="Limit number of repositories per organization (default: all)",
    )
    args = parser.parse_args()

    # Check if gh command exists
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: GitHub CLI (gh) is not installed or not available in PATH")
        print("Please install it from: https://cli.github.com/")
        sys.exit(1)

    # Configuration
    yaml_file = Path("src/jupyter_orgs.yml")
    releases_dir = Path("docs/releases")

    # Load organizations from YAML
    organizations = load_organizations(yaml_file)
    if not organizations:
        print("Error: No organizations found in YAML file")
        sys.exit(1)

    # Clean and ensure directories exist
    if releases_dir.exists():
        shutil.rmtree(releases_dir)
    releases_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing {len(organizations)} organizations...")

    # Process each organization separately
    for org in organizations:
        org_name = org["name"]
        org_url = org["url"]

        print(f"\nProcessing {org_name}...")

        # Create organization file name
        org_file_name = org_name.lower().replace(" ", "-").replace("&", "and") + ".md"
        org_file_path = releases_dir / org_file_name

        # Fetch repositories for this organization
        repos = fetch_repositories(org_url)
        if not repos:
            print(f"No repositories found for {org_name}")
            continue

        # Limit number of repositories if --n-repositories is set
        if args.n_repositories:
            repos = repos[: args.n_repositories]

        org_releases = []
        # Fetch releases from the last n months for each repository
        for repo in repos:
            repo_name = repo["name"]
            print(f"  Fetching releases from {repo_name}...")
            releases = fetch_releases_from_last_n_months(
                org_url, repo_name, args.months
            )
            for release in releases:
                release["repo_name"] = repo_name
                org_releases.append(release)
        # Sort releases by publication date (newest first)
        org_releases.sort(key=lambda x: x["published_at"], reverse=True)

        print(
            f"  Found {len(org_releases)} releases from the last {args.months} months"
        )

        # Write a single Markdown file for the organization
        with open(org_file_path, "w") as f:
            f.write("---\n")
            f.write(f"title: {org_name}\n")
            f.write(f'date: "{today}"\n')
            f.write(f"author: {org_name}\n")
            f.write("tags:\n")
            f.write("  - release\n")
            f.write(f"  - {org_name.lower().replace(' ', '-')}\n")
            f.write("---\n\n")
            f.write(f"# {org_name}\n\n")
            f.write(f"Releases for the [{org_name}]({org_url}) organization.\n\n")
            if not org_releases:
                f.write(f"No releases found in the last {args.months} months.\n")
            for release in org_releases:
                title = release["name"] or release["tag_name"]
                repo_name = release["repo_name"]
                normalized_repo = (
                    repo_name.lower().replace("-", "").replace("_", "").replace(" ", "")
                )
                normalized_title = (
                    title.lower().replace("-", "").replace("_", "").replace(" ", "")
                )
                if normalized_repo not in normalized_title:
                    title = f"{repo_name} {title}"
                date = release["published_at"][:10]
                formatted_date = format_date(date)
                body = release["body"] or ""
                body = clean_release_body(body)
                body = convert_github_usernames_to_links(body)
                body = convert_headers_to_bold(body)
                body = add_backticks_to_usernames_in_links(body)
                # Section for each release (top-level header)
                f.write(f"# {title} - {formatted_date}\n\n")
                f.write(f"[View on GitHub]({release['html_url']})\n\n")
                if body:
                    f.write(body + "\n\n")
                f.write("---\n\n")

    print("\nRelease posts generated successfully!")


if __name__ == "__main__":
    main()
