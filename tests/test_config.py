from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accessible_mail import config


class OAuthClientConfigTests(unittest.TestCase):
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

    def test_gmail_api_credentials_do_not_fall_back_to_full_gmail_env(self) -> None:
        env = {
            "ACCESSIBLE_MAIL_GOOGLE_CLIENT_ID": "full-client-id",
            "ACCESSIBLE_MAIL_GOOGLE_CLIENT_SECRET": "full-client-secret",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch.object(config, "oauth_clients_paths", return_value=[]):
                clients = config.load_oauth_clients()

        self.assertEqual(clients["google"]["client_id"], "full-client-id")
        self.assertEqual(clients["google"]["client_secret"], "full-client-secret")
        self.assertEqual(clients["google_gmail_api"]["client_id"], "")
        self.assertEqual(clients["google_gmail_api"]["client_secret"], "")

    def test_gmail_api_credentials_use_separate_env_names(self) -> None:
        env = {
            "ACCESSIBLE_MAIL_GOOGLE_CLIENT_ID": "full-client-id",
            "ACCESSIBLE_MAIL_GOOGLE_CLIENT_SECRET": "full-client-secret",
            "ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_ID": "limited-client-id",
            "ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_SECRET": "limited-client-secret",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch.object(config, "oauth_clients_paths", return_value=[]):
                clients = config.load_oauth_clients()

        self.assertEqual(clients["google"]["client_id"], "full-client-id")
        self.assertEqual(clients["google"]["client_secret"], "full-client-secret")
        self.assertEqual(clients["google_gmail_api"]["client_id"], "limited-client-id")
        self.assertEqual(clients["google_gmail_api"]["client_secret"], "limited-client-secret")

    def test_explicit_edition_file_excludes_shared_root_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            explicit_file = root / "limited.json"
            explicit_file.write_text(
                json.dumps(
                    {
                        "google_gmail_api": {
                            "client_id": "limited-file-id",
                            "client_secret": "limited-file-secret",
                        }
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
        self.assertEqual(clients["google"]["client_id"], "")
        self.assertEqual(clients["google_gmail_api"]["client_id"], "limited-file-id")


if __name__ == "__main__":
    unittest.main()
