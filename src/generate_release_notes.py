#!/usr/bin/env python3
"""
Script to generate release notes from GitHub releases in Jupyter organizations.
"""

import json
import re
import subprocess
import sys
import shutil
import yaml
from datetime import datetime, timedelta
from pathlib import Path


def format_date(date_str):
    """Convert ISO date string to readable format like 'June 17th, 2025'"""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    # Get month name
    month = date_obj.strftime("%B")

    # Get day with ordinal suffix
    day = date_obj.day
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]

    # Get year
    year = date_obj.year

    return f"{month} {day}{suffix}, {year}"


def load_organizations(yaml_file):
    """Load organizations from YAML file"""
    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f)
    return data.get('organizations', [])


def get_org_name_from_url(url):
    """Extract organization name from GitHub URL"""
    return url.split('/')[-1]


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


def fetch_releases_from_last_six_months(org_url, repo_name):
    """Fetch releases from the last 6 months for a specific repository"""
    org_name = get_org_name_from_url(org_url)
    six_months_ago = datetime.now() - timedelta(days=180)
    
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org_name}/{repo_name}/releases", 
             "--paginate"],
            capture_output=True,
            text=True,
            check=True,
        )
        releases = json.loads(result.stdout)
        
        # Filter releases from the last 6 months
        recent_releases = []
        for release in releases:
            if release.get("published_at"):
                release_date = datetime.strptime(
                    release["published_at"][:10], "%Y-%m-%d"
                )
                if release_date >= six_months_ago:
                    release["repo_name"] = repo_name
                    recent_releases.append(release)
        
        return recent_releases
    except subprocess.CalledProcessError:
        print(f"No releases found for {org_name}/{repo_name}")
        return []
    except json.JSONDecodeError:
        print(f"Error parsing releases for {org_name}/{repo_name}")
        return []


def create_index_md(org_folder, org_name, releases):
    """Create index.md file for an organization"""
    index_file = org_folder / "index.md"
    
    with open(index_file, "w") as f:
        f.write("---\n")
        f.write(f"title: {org_name} Releases\n")
        f.write("date: 2024-01-01\n")
        f.write("author: The Jupyter Team\n")
        f.write("tags:\n")
        f.write("  - releases\n")
        f.write(f"  - {org_name.lower().replace(' ', '-')}\n")
        f.write("---\n\n")
        f.write(f"# {org_name} Releases\n\n")
        f.write(f"This page contains all releases from the {org_name} "
                f"organization in the last year.\n\n")
        
        folder_name = org_name.lower().replace(" ", "-").replace("&", "and")
        f.write(":::{blog-posts}\n")
        f.write(f":path: releases/{folder_name}/\n")
        f.write(":limit: 50\n")
        f.write(":::\n")


def main():
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
    temp_dir = Path("_build/release_notes")

    # Load organizations from YAML
    organizations = load_organizations(yaml_file)
    if not organizations:
        print("Error: No organizations found in YAML file")
        sys.exit(1)

    # Clean and ensure directories exist
    if releases_dir.exists():
        shutil.rmtree(releases_dir)
    releases_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing {len(organizations)} organizations...")

    all_releases = []

    # First pass: collect all releases from all organizations
    for org in organizations:
        org_name = org["name"]
        org_url = org["url"]
        
        print(f"\nProcessing {org_name}...")
        
        # Fetch repositories for this organization
        repos = fetch_repositories(org_url)
        if not repos:
            print(f"No repositories found for {org_name}")
            continue
        
        # Fetch releases from the last 6 months for each repository
        for repo in repos:
            repo_name = repo["name"]
            print(f"  Fetching releases from {repo_name}...")
            
            releases = fetch_releases_from_last_six_months(org_url, repo_name)
            for release in releases:
                release["org_name"] = org_name
            all_releases.extend(releases)
    
    # Sort all releases by publication date (oldest first)
    all_releases.sort(key=lambda x: x["published_at"])
    
    print(f"\nFound {len(all_releases)} total releases from the last 6 months")
    
    # Second pass: generate files in chronological order
    for release_counter, release in enumerate(all_releases, 1):
        title = release["name"] or release["tag_name"]
        repo_name = release["repo_name"]
        org_name = release["org_name"]

        # Add repository name to title if it's not already present
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
        title = f"{title} - {formatted_date}"
        body = release["body"] or ""

        # Wrap @mentions in backticks (only if preceded by space, (, comma, 
        # or [, and not already wrapped)
        body = re.sub(r"(?<=[\s(,\[])@(\w+)(?!`)", r"`@\1`", body)

        # Create filename
        safe_title = re.sub(r"[^a-zA-Z0-9-]", "-", title.lower())
        org_folder_name = org_name.lower().replace(" ", "-").replace("&", "and")
        filename = releases_dir / f"{release_counter:03d}-{org_folder_name}-{repo_name}-{safe_title}.md"

        # Write the markdown file
        with open(filename, "w") as f:
            f.write("---\n")
            f.write(f"title: {title}\n")
            f.write(f"date: {date}\n")
            f.write("author: The Jupyter Team\n")
            f.write("tags:\n")
            f.write("  - release\n")
            f.write(f"  - {org_name.lower().replace(' ', '-')}\n")
            f.write("---\n\n")
            f.write(
                f"{{button}}`Release Source <{release['html_url']}>`\n\n"
            )
            f.write(body)
            f.write("\n")

        print(f"Generated: {filename}")

    print("\nRelease posts generated successfully!")


if __name__ == "__main__":
    main()
