from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accessible_mail.config import (
    LANGUAGE_ENGLISH,
    TRANSLATION_INLINE,
    ProgramSettings,
    load_accounts,
    load_settings,
    save_accounts,
    save_settings,
)
from accessible_mail.models import Account


class ConfigStorageTests(unittest.TestCase):
    def test_language_and_translation_mode_are_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = ProgramSettings(
                language=LANGUAGE_ENGLISH,
                translation_mode=TRANSLATION_INLINE,
            )

            with patch("accessible_mail.config.settings_path", return_value=path):
                save_settings(settings)
                loaded = load_settings()

        self.assertEqual(loaded.language, LANGUAGE_ENGLISH)
        self.assertEqual(loaded.translation_mode, TRANSLATION_INLINE)

    def test_oauth_tokens_are_protected_and_backup_recovers_corrupt_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounts.json"
            account = Account(
                id="account",
                email_address="user@example.com",
                oauth_access_token="access-token",
                oauth_refresh_token="refresh-token",
                save_oauth_tokens=True,
            )

            def protect(value: str) -> str:
                return "protected:" + value[::-1]

            def unprotect(value: str) -> str:
                return value.removeprefix("protected:")[::-1]

            with (
                patch("accessible_mail.config.accounts_path", return_value=path),
                patch("accessible_mail.config.protect_secret", side_effect=protect),
                patch("accessible_mail.config.unprotect_secret", side_effect=unprotect),
            ):
                save_accounts([account])
                payload = json.loads(path.read_text(encoding="utf-8"))

                self.assertEqual(payload[0]["oauth_access_token"], "")
                self.assertEqual(payload[0]["oauth_refresh_token"], "")
                self.assertNotIn("access-token", path.read_text(encoding="utf-8"))
                self.assertTrue(path.with_suffix(".json.bak").exists())

                path.write_text("not valid json", encoding="utf-8")
                loaded = load_accounts()

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].oauth_access_token, "access-token")
            self.assertEqual(loaded[0].oauth_refresh_token, "refresh-token")


if __name__ == "__main__":
    unittest.main()
