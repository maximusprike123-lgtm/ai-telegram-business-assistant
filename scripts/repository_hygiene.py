"""Fail when tracked text contains local paths or non-English Cyrillic text."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("/" + "Users/", "/" + "home/", "C:" + "\\Users\\")


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.split(b"\0")
    failures: list[str] = []
    for raw_path in tracked:
        if not raw_path:
            continue
        relative = raw_path.decode()
        data = (ROOT / relative).read_bytes()
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        if any(marker in text for marker in FORBIDDEN):
            failures.append(f"{relative}: machine-specific absolute path")
        if any("\u0400" <= character <= "\u04ff" for character in text):
            failures.append(f"{relative}: Cyrillic text")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"repository hygiene passed ({len(tracked) - 1} tracked files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
