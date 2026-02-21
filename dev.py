"""
Dev task runner — replaces Makefile.

Usage:
    uv run python dev.py lint      # Check for lint errors
    uv run python dev.py fix       # Auto-fix lint errors
    uv run python dev.py format    # Format code
    uv run python dev.py test      # Run all tests
    uv run python dev.py check     # lint + format check + tests (full CI check)
"""
from __future__ import annotations

import subprocess
import sys


def run(cmd: str) -> int:
    """Run a shell command, stream output, return exit code."""
    print(f"\n$ {cmd}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode


def lint() -> int:
    return run("ruff check src/")


def fix() -> int:
    return run("ruff check src/ --fix")


def format_code() -> int:
    return run("ruff format src/")


def test() -> int:
    return run("pytest tests/ -x --tb=short -q")


def check() -> int:
    """Full CI check: lint + format check + tests."""
    codes = [
        run("ruff check src/"),
        run("ruff format src/ --check"),
        run("pytest tests/ -x --tb=short -q"),
    ]
    return max(codes)


COMMANDS = {
    "lint": lint,
    "fix": fix,
    "format": format_code,
    "test": test,
    "check": check,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Available commands: {', '.join(COMMANDS)}")
        sys.exit(1)

    exit_code = COMMANDS[sys.argv[1]]()
    sys.exit(exit_code)
