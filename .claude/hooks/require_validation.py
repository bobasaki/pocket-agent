#!/usr/bin/env python3
"""Stop hook: refuse to finish while source files are newer than the last passing test run.

Pairs with mark_validation.py, which touches the marker whenever pytest passes.
Blocks at most once per stop, so it is a reminder, not a gate: the agent can
always stop on its second attempt.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

MARKER_NAME = ".claude/.validation_marker"


def changed_python_files(project_dir):
    """Project-root .py files git reports as changed."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    paths = []
    for line in result.stdout.splitlines():
        path = line[3:]
        if " -> " in path:              # renamed: "old -> new"
            path = path.split(" -> ")[-1]
        path = path.strip('"')
        if path.endswith(".py") and "/" not in path:
            paths.append(path)
    return paths


def stale_files(project_dir, marker, paths):
    """Existing files modified after the marker. No marker means nothing was verified."""
    existing = [path for path in paths if (Path(project_dir) / path).exists()]
    if not marker.exists():
        return sorted(existing)
    marker_time = marker.stat().st_mtime
    return sorted(
        path for path in existing
        if (Path(project_dir) / path).stat().st_mtime > marker_time
    )


def main():
    data = json.load(sys.stdin)

    # Already blocked once this stop - let it finish rather than loop.
    if data.get("stop_hook_active"):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    changed = changed_python_files(project_dir)
    if not changed:
        sys.exit(0)

    stale = stale_files(project_dir, Path(project_dir) / MARKER_NAME, changed)
    if not stale:
        sys.exit(0)

    print(json.dumps({
        "decision": "block",
        "reason": (
            f"Changed since the tests last passed: {', '.join(stale)}. "
            "Run `uv run pytest` and get it green before finishing."
        ),
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
