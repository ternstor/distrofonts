"""Shared subprocess helpers and errors."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path


class FontError(Exception):
    """A package failed in a way the batch run can record and continue past."""


def run_command(command: list[str], cwd: Path, logger: logging.Logger) -> int:
    """Run a command in ``cwd`` and log stderr when it fails."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        logger.error(
            "Error running '%s' in '%s':\n%s",
            " ".join(command),
            cwd,
            completed.stderr,
        )
    return completed.returncode
