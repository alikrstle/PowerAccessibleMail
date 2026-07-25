from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ["POWER_ACCESSIBLE_MAIL_EDITION"] = "full"
os.environ["POWER_ACCESSIBLE_MAIL_APP_NAME"] = "PowerAccessibleMail"
os.environ["POWER_ACCESSIBLE_MAIL_APP_TITLE"] = "Power Accessible Mail"
if not getattr(sys, "frozen", False):
    os.environ["POWER_ACCESSIBLE_MAIL_OAUTH_CLIENTS_FILE"] = str(
        Path(__file__).resolve().parent / ". النسخة الكاملة" / "oauth_clients.json"
    )


def main() -> int:
    try:
        from accessible_mail.app import run
    except ModuleNotFoundError as exc:
        if exc.name == "wx":
            print(
                "wxPython is not installed. Install it with: "
                "python -m pip install -r requirements.txt"
            )
            return 1
        raise

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
