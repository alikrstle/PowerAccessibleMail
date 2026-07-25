from __future__ import annotations

import runpy
import sys
from pathlib import Path


PROFILE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROFILE_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    runpy.run_path(str(PROJECT_ROOT / "main.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
