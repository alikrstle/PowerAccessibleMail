from __future__ import annotations

import os
import sys
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROFILE_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["POWER_ACCESSIBLE_MAIL_LIMITED_GOOGLE"] = "1"
os.environ["POWER_ACCESSIBLE_MAIL_EDITION"] = "gmail_api_limited"
os.environ["POWER_ACCESSIBLE_MAIL_APP_NAME"] = "PowerAccessibleMailGmailApiLimited"
os.environ["POWER_ACCESSIBLE_MAIL_APP_TITLE"] = "Power Accessible Mail"
os.environ["POWER_ACCESSIBLE_MAIL_SETTINGS_APP_NAME"] = "PowerAccessibleMail"
os.environ["POWER_ACCESSIBLE_MAIL_OAUTH_CLIENTS_FILE"] = str(PROFILE_DIR / "oauth_clients.json")

from accessible_mail.app import run


if __name__ == "__main__":
    run()
