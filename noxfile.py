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
def releases(session):
    """Generate release notes with default settings (5 months, 2 repos)."""
    session.install("PyYAML>=6.0")

    # Build the command with default settings
    cmd = [
        sys.executable,
        "src/generate_release_notes.py",
        "--months",
        "5",
        "--n-repositories",
        "2",
    ]

    session.run(*cmd)

    session.log("Generated release notes with default settings (5 months, 2 repos)")
