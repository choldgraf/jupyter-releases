"""Nox configuration for jupyter-releases."""

import nox
import sys
from pathlib import Path


@nox.session
def docs(session):
    """Start the documentation server with myst."""
    session.install("mystmd")

    # Change to docs directory and run myst start
    docs_dir = Path("docs")
    if not docs_dir.exists():
        session.error("docs directory not found")

    session.chdir("docs")
    session.run("myst", "start")


@nox.session
@nox.parametrize("months", [1, 3, 6, 12])
def update_releases(session, months):
    """Re-download release notes with specified number of months."""
    session.install("PyYAML>=6.0")

    # Build the command
    cmd = [sys.executable, "src/generate_release_notes.py", "--months", str(months)]

    session.run(*cmd)

    session.log(f"Updated release notes for the last {months} months")


@nox.session
@nox.parametrize("n_repos", [3, 5, 10])
def update_releases_limited(session, n_repos):
    """Re-download release notes with limited repositories per organization."""
    session.install("PyYAML>=6.0")

    # Build the command
    cmd = [
        sys.executable,
        "src/generate_release_notes.py",
        "--months",
        "6",
        "--n-repositories",
        str(n_repos),
    ]

    session.run(*cmd)

    session.log(f"Updated release notes with {n_repos} repositories per organization")
