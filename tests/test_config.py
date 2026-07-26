from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accessible_mail import config
from accessible_mail import __version__


class OAuthClientConfigTests(unittest.TestCase):
    def test_release_version_is_consistent_across_build_inputs(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        installer = (project_root / "installer_power_accessible_mail.iss").read_text(
            encoding="utf-8-sig"
        )
        version_info = (project_root / "windows_version_info.txt").read_text(
            encoding="utf-8"
        )
        release_script = (
            project_root / "build_release_power_accessible_mail.ps1"
        ).read_text(encoding="utf-8")

        self.assertEqual(config.APP_VERSION, __version__)
        self.assertIn(f'#define MyAppVersion "{__version__}"', installer)
        self.assertIn(f"StringStruct('ProductVersion', '{__version__}')", version_info)
        self.assertIn(f'$Version = "{__version__}"', release_script)

    def test_limited_edition_can_share_only_full_edition_ui_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {
                    "APPDATA": temporary_directory,
                    "POWER_ACCESSIBLE_MAIL_SETTINGS_APP_NAME": "PowerAccessibleMail",
                },
                clear=True,
            ):
                path = config.settings_path()

        self.assertEqual(path.parent.name, "PowerAccessibleMail")
        self.assertEqual(path.name, "settings.json")

    def test_legacy_full_gmail_environment_is_ignored(self) -> None:
        env = {
            "ACCESSIBLE_MAIL_GOOGLE_CLIENT_ID": "full-client-id",
            "ACCESSIBLE_MAIL_GOOGLE_CLIENT_SECRET": "full-client-secret",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch.object(config, "oauth_clients_paths", return_value=[]):
                clients = config.load_oauth_clients()

        self.assertEqual(set(clients), {"google_gmail_api", "microsoft"})
        self.assertEqual(clients["google_gmail_api"]["client_id"], "")
        self.assertEqual(clients["google_gmail_api"]["client_secret"], "")

    def test_gmail_api_credentials_use_unified_env_names(self) -> None:
        env = {
            "ACCESSIBLE_MAIL_GOOGLE_CLIENT_ID": "full-client-id",
            "ACCESSIBLE_MAIL_GOOGLE_CLIENT_SECRET": "full-client-secret",
            "ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_ID": "limited-client-id",
            "ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_SECRET": "limited-client-secret",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch.object(config, "oauth_clients_paths", return_value=[]):
                clients = config.load_oauth_clients()

        self.assertNotIn("google", clients)
        self.assertEqual(clients["google_gmail_api"]["client_id"], "limited-client-id")
        self.assertEqual(clients["google_gmail_api"]["client_secret"], "limited-client-secret")

    def test_explicit_oauth_file_ignores_legacy_full_google_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            explicit_file = root / "limited.json"
            explicit_file.write_text(
                json.dumps(
                    {
                        "google_gmail_api": {
                            "client_id": "limited-file-id",
                            "client_secret": "limited-file-secret",
                        },
                        "google": {"client_id": "obsolete-full-id"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "oauth_clients.json").write_text(
                json.dumps({"google": {"client_id": "shared-id"}}),
                encoding="utf-8",
            )
            data_root = root / "data"
            data_root.mkdir()

            with patch.dict(
                os.environ,
                {"POWER_ACCESSIBLE_MAIL_OAUTH_CLIENTS_FILE": str(explicit_file)},
                clear=True,
            ):
                with patch.object(config, "app_dir", return_value=root):
                    with patch.object(config, "data_dir", return_value=data_root):
                        paths = config.oauth_clients_paths()
                        clients = config.load_oauth_clients()

        self.assertNotIn((root / "oauth_clients.json").resolve(), paths)
        self.assertNotIn("google", clients)
        self.assertEqual(clients["google_gmail_api"]["client_id"], "limited-file-id")

    def test_build_requires_both_unified_oauth_client_ids(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        app_build = (project_root / "build_power_accessible_mail.ps1").read_text(
            encoding="utf-8"
        )
        release_build = (
            project_root / "build_release_power_accessible_mail.ps1"
        ).read_text(encoding="utf-8")

        for source in (app_build, release_build):
            self.assertIn(
                "$bundledOAuthConfig.google_gmail_api.client_id",
                source,
            )
            self.assertIn("$bundledOAuthConfig.microsoft.client_id", source)
        self.assertIn("$oauthConfig.google_gmail_api.client_id", app_build)
        self.assertIn("$oauthConfig.microsoft.client_id", app_build)


if __name__ == "__main__":
    unittest.main()
