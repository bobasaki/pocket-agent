#!/usr/bin/env python3

import json
import subprocess
import sys

SECRET_FILES = {".env"}


def find_secrets(staged):
    return sorted(SECRET_FILES.intersection(staged))


def main():
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")

    if "git commit" not in command:
        sys.exit(0)

    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=data.get("cwd"),
        capture_output=True,
        text=True,
    )
    found = find_secrets(result.stdout.splitlines())

    if found:
        print(
            f"Blocked: {', '.join(found)} is staged and must never be committed. "
            f"Unstage it first: git restore --staged {' '.join(found)}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()