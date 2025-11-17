#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Version information for PFS QuickLook.

Version Detection Priority:
1. Git tags (primary source of truth)
2. APP_VERSION environment variable (fallback for non-Git environments)
3. "unknown" (last resort)

This approach ensures:
- Development: Automatic version from Git tags
- Production with Git: Uses Git tags
- Production without Git: Can specify version via APP_VERSION
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


def _run(cmd: list[str], cwd: Optional[Path] = None, timeout: float = 5.0) -> Optional[str]:
    """Run a command and return stdout, or None on any error.

    Parameters
    ----------
    cmd : list[str]
        Command and arguments to run
    cwd : Optional[Path]
        Working directory for command execution
    timeout : float
        Timeout in seconds (default: 5.0)

    Returns
    -------
    Optional[str]
        Command stdout stripped of whitespace, or None if command failed
    """
    try:
        out = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        ).stdout.strip()
        return out or None
    except Exception:
        return None


def _git_root(start: Path) -> Optional[Path]:
    """Find the root of the Git repository.

    Parameters
    ----------
    start : Path
        Starting directory for search

    Returns
    -------
    Optional[Path]
        Git repository root, or None if not in a Git repository
    """
    root = _run(["git", "rev-parse", "--show-toplevel"], cwd=start)
    return Path(root) if root else None


def _version_from_git(root: Path) -> Optional[str]:
    """Get version from Git tags.

    Parameters
    ----------
    root : Path
        Git repository root

    Returns
    -------
    Optional[str]
        Version string from Git, or None if no tags found

    Notes
    -----
    - On tagged commit: returns "v1.0.0"
    - After tagged commit: returns "v1.0.0-5-gabc123" (5 commits after v1.0.0)
    - No tags: returns "v0.0.0-gabc123" (commit hash only)
    - Dirty working tree: appends "-dirty"
    """
    # Check if we're exactly on a tag
    exact = _run(
        ["git", "describe", "--tags", "--exact-match", "--match", "v*"],
        cwd=root,
    )
    if exact:  # e.g., v1.2.3
        return exact

    # Not on a tag: get detailed description
    desc = _run(
        ["git", "describe", "--tags", "--match", "v*", "--always", "--dirty", "--long"],
        cwd=root,
    )
    if desc:  # e.g., v1.2.3-5-gabc123 or abc123 (no tags)
        return desc if desc.startswith("v") else f"v0.0.0-g{desc}"

    return None


def get_version() -> str:
    """Get application version string.

    Returns
    -------
    str
        Version string (e.g., "v1.0.0", "v1.0.0-5-gabc123", or "unknown")

    Notes
    -----
    Priority order:
    1. Git tags (if repository is available)
    2. APP_VERSION environment variable (fallback for non-Git environments)
    3. "unknown" (if all methods fail)
    """
    # Priority 1: Try Git first
    start = Path(__file__).resolve().parent
    root = _git_root(start)
    if root:
        ver = _version_from_git(root)
        if ver:
            return ver

    # Priority 2: Fall back to environment variable
    env = os.environ.get("APP_VERSION")
    if env:
        return env.strip()

    # Priority 3: Last resort
    return "unknown"


# Module-level constant for easy import
__version__ = get_version()


if __name__ == "__main__":
    # For testing: print version when run directly
    print(f"PFS QuickLook version: {__version__}")
