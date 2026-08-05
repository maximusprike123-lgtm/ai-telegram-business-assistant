"""Run the representative release-candidate workflow matrix."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from time import monotonic

TESTS = (
    "tests/integration/test_seed.py",
    "tests/api/test_phase3_api.py",
    "tests/api/test_telegram_webhook.py",
    "tests/integration/test_phase5_booking.py",
    "tests/integration/test_phase6_qualification.py",
    "tests/unit/test_ai_runtime.py",
    "tests/integration/test_phase8_knowledge.py",
    "tests/integration/test_phase9_privacy.py",
    "tests/integration/test_phase10_background.py",
    "tests/unit/test_observability.py",
    "tests/integration/test_phase12_administration.py",
)


def main() -> int:
    if not os.environ.get("TEST_DATABASE_URL"):
        print(json.dumps({"status": "error", "reason": "TEST_DATABASE_URL is required"}))
        return 2
    started = monotonic()
    result = subprocess.run([sys.executable, "-m", "pytest", "--no-cov", "-q", *TESTS], check=False)
    print(
        json.dumps(
            {
                "status": "passed" if result.returncode == 0 else "failed",
                "duration_seconds": round(monotonic() - started, 3),
                "exit_code": result.returncode,
                "test_files": list(TESTS),
            },
            sort_keys=True,
        )
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
