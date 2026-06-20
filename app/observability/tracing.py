"""Tracing utilities — git SHA lookup and other cross-cutting helpers."""

from __future__ import annotations

import subprocess

_git_sha: str | None = None


def get_git_sha() -> str:
    """Return the short git SHA of HEAD, cached after first call."""
    global _git_sha
    if _git_sha is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            _git_sha = result.stdout.strip() or "unknown"
        except Exception:
            _git_sha = "unknown"
    return _git_sha
