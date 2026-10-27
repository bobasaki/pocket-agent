#!/usr/bin/env python3
"""PostToolUse hook: record that the test suite passed."""
import json
import os
import re
import shlex
import sys
from pathlib import Path

MARKER_NAME = ".claude/.validation_marker"


def runs_pytest(command):
    """True if some segment of the shell command actually invokes pytest.

    Accepts `pytest`, `uv run [opts] pytest`, `python -m pytest` and paths like
    `.venv/bin/pytest`; rejects mentions such as `grep pytest` or `echo pytest`.
    """
    for segment in re.split(r"&&|\|\||[;|&\n]", command):
        try:
            argv = shlex.split(segment)
        except ValueError:
            continue
        while argv and re.fullmatch(r"\w+=.*", argv[0]):   # FOO=bar pytest
            argv = argv[1:]
        if argv[:2] == ["uv", "run"]:
            argv = argv[2:]
            while argv and argv[0].startswith("-"):         # uv run --frozen pytest
                argv = argv[1:]
        if not argv:
            continue
        program = Path(argv[0]).name
        if program in ("pytest", "py.test"):
            return True
        if program.startswith("python") and argv[1:3] == ["-m", "pytest"]:
            return True
    return False


def pytest_passed(output):
    """True if pytest's final summary line reports passes and nothing broken.

    PostToolUse only fires when the Bash command exits 0, and its payload has no
    exit code, so a failure masked by `; echo` or `| tail` still arrives here.
    The summary line ("10 passed, 1 failed in 0.5s") is the only reliable signal.
    A run whose summary was cut off (`| head`) counts as not passed.
    """
    summaries = [
        line for line in output.splitlines()
        if re.search(r"\b\d+ (passed|failed|errors?|deselected)\b.* in [\d.]+s\b", line)
        or re.search(r"\bno tests ran\b", line)
    ]
    if not summaries:
        return False
    last = summaries[-1]
    return (
        re.search(r"\b\d+ passed\b", last) is not None
        and re.search(r"\b\d+ (failed|errors?)\b|interrupted", last) is None
    )


def main():
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
    response = data.get("tool_response") or {}
    output = f"{response.get('stdout', '')}\n{response.get('stderr', '')}"

    if runs_pytest(command) and pytest_passed(output):
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd", ".")
        marker = Path(project_dir) / MARKER_NAME
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

    sys.exit(0)


if __name__ == "__main__":
    main()
