"""Shell utility functions for wiki-agent."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def get_shell() -> str:
    """Get the default shell for the current platform."""
    if platform.system() == "Windows":
        return os.environ.get("COMSPEC", "cmd.exe")
    return os.environ.get("SHELL", "/bin/bash")


def run_command(cmd: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a shell command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"
