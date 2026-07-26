from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accessible_mail import config
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
    def test_legacy_full_google_account_requires_gmail_api_reauthentication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounts.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "email_address": "person@gmail.com",
                            "oauth_provider": "google",
                            "oauth_client_id": "obsolete-client",
                            "oauth_client_secret": "obsolete-secret",
                            "oauth_access_token": "obsolete-access",
                            "oauth_refresh_token": "obsolete-refresh",
                            "oauth_token_expiry": 9999999999,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch("accessible_mail.config.accounts_path", return_value=path):
                accounts = load_accounts()

        self.assertEqual(len(accounts), 1)
        account = accounts[0]
        self.assertEqual(account.oauth_provider, "google_gmail_api")
        self.assertEqual(account.oauth_client_id, "")
        self.assertEqual(account.oauth_client_secret, "")
        self.assertEqual(account.oauth_access_token, "")
        self.assertEqual(account.oauth_refresh_token, "")
        self.assertEqual(account.oauth_token_expiry, 0.0)

    def test_limited_profile_accounts_are_merged_into_unified_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            appdata = Path(directory)
            unified = appdata / "PowerAccessibleMail"
            legacy = appdata / "PowerAccessibleMailGmailApiLimited"
            unified.mkdir()
            legacy.mkdir()
            (unified / "accounts.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "manual",
                            "email_address": "manual@example.com",
                            "auth_method": "password",
                        },
                        {
                            "id": "old-google",
                            "email_address": "person@gmail.com",
                            "oauth_provider": "google",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (legacy / "accounts.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "gmail-api",
                            "email_address": "person@gmail.com",
                            "oauth_provider": "google_gmail_api",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"APPDATA": directory}, clear=False):
                config._MIGRATED_PROFILE_ROOTS.clear()
                migrated_path = config.data_dir()
                payload = json.loads(
                    (migrated_path / "accounts.json").read_text(encoding="utf-8")
                )
                backup_created = (
                    unified / "accounts.pre-unified-backup.json"
                ).exists()
                marker_created = (
                    unified / ".unified-profile-migration-v1"
                ).exists()

        self.assertEqual(len(payload), 2)
        providers = {
            item["email_address"]: item.get("oauth_provider", "")
            for item in payload
        }
        self.assertEqual(providers["person@gmail.com"], "google_gmail_api")
        self.assertTrue(backup_created)
        self.assertTrue(marker_created)

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
