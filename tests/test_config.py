from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accessible_mail import config
from accessible_mail import __version__
from accessible_mail.notification_preferences import (
    EVENT_CONTEXT_MENUS,
    EVENT_SEND,
    NOTIFICATION_LEVEL_SOME,
)


class OAuthClientConfigTests(unittest.TestCase):
    def test_invalid_message_read_mode_falls_back_to_manual(self) -> None:
        settings = config.normalize_settings(
            config.ProgramSettings(message_read_mode="invalid")
        )

        self.assertEqual(settings.message_read_mode, config.MESSAGE_READ_MANUAL)

    def test_notification_preferences_round_trip_in_settings(self) -> None:
        settings = config.ProgramSettings(
            spoken_notification_level=NOTIFICATION_LEVEL_SOME,
            spoken_notification_events=[EVENT_CONTEXT_MENUS, EVENT_SEND],
        )
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            with patch("accessible_mail.config.settings_path", return_value=settings_path):
                config.save_settings(settings)
                loaded = config.load_settings()

        self.assertEqual(loaded.spoken_notification_level, NOTIFICATION_LEVEL_SOME)
        self.assertEqual(
            loaded.spoken_notification_events,
            [EVENT_CONTEXT_MENUS, EVENT_SEND],
        )

    def test_launcher_probes_python_before_using_a_virtual_environment(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        batch_launcher = (project_root / "run.bat").read_text(encoding="utf-8")
        launcher = (
            project_root / "scripts" / "run_power_accessible_mail.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("run_power_accessible_mail.ps1", batch_launcher)
        self.assertIn('-c "import wx"', launcher)
        self.assertIn(".venv-codex", launcher)
        self.assertIn("Get-Command python", launcher)

    def test_install_uses_the_locked_release_dependencies(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        installer = (project_root / "install.bat").read_text(encoding="utf-8")
        self.assertIn("requirements-release.lock", installer)
        self.assertNotIn("-r requirements.txt", installer)

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
        version_quad = ", ".join((*__version__.split("."), "0"))

        self.assertEqual(config.APP_VERSION, __version__)
        self.assertIn(f'#define MyAppVersion "{__version__}"', installer)
        self.assertIn(f"VersionInfoVersion={__version__}.0", installer)
        self.assertIn(f"filevers=({version_quad})", version_info)
        self.assertIn(f"prodvers=({version_quad})", version_info)
        self.assertIn(f"StringStruct('FileVersion', '{__version__}.0')", version_info)
        self.assertIn(f"StringStruct('ProductVersion', '{__version__}')", version_info)
        self.assertIn(f'$Version = "{__version__}"', release_script)
        for release_text_name in (
            "installer_info_ar.txt",
            "installer_info_en.txt",
            "installer_info_fr.txt",
            "installer_readme_ar.txt",
            "installer_readme_en.txt",
            "installer_readme_fr.txt",
        ):
            release_text = (project_root / release_text_name).read_text(
                encoding="utf-8-sig"
            )
            self.assertIn(__version__, release_text)

    def test_installer_and_portable_package_include_french_resources(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        installer = (project_root / "installer_power_accessible_mail.iss").read_text(
            encoding="utf-8-sig"
        )
        release_script = (
            project_root / "build_release_power_accessible_mail.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('Name: "french"', installer)
        self.assertIn(r"compiler:Languages\French.isl", installer)
        self.assertIn('InfoBeforeFile: "installer_info_fr.txt"', installer)
        self.assertIn('DestName: "README_FR.txt"', installer)
        self.assertIn("Languages: french", installer)
        self.assertLess(installer.index('Name: "english"'), installer.index('Name: "arabic"'))
        self.assertIn("installer_readme_fr.txt", release_script)
        self.assertIn("PackageFrenchReadme", release_script)

    def test_application_build_bundles_all_program_guides(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        build_script = (project_root / "build_power_accessible_mail.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("$ProgramGuides", build_script)
        for guide_name in (
            "installer_readme_ar.txt",
            "installer_readme_en.txt",
            "installer_readme_fr.txt",
        ):
            self.assertIn(guide_name, build_script)

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

    def test_build_checks_pyinstaller_and_output_pe_architecture(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        app_build = (project_root / "build_power_accessible_mail.ps1").read_text(
            encoding="utf-8"
        )
        architecture_tests = (
            project_root / "test_all_architectures.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("bootloaderMachine", app_build)
        self.assertIn("appMachine", app_build)
        self.assertIn("bootloader_machine", architecture_tests)
        self.assertIn("0x8664", app_build)
        self.assertIn("0x014C", app_build)
        self.assertIn("pefile.PE(sys.argv[1]", app_build)
        self.assertIn("-c $appMachineScript $AppDistExe", app_build)

    def test_public_release_requires_authenticode_signing(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        release_build = (
            project_root / "build_release_power_accessible_mail.ps1"
        ).read_text(encoding="utf-8")
        readme = (project_root / "README.md").read_text(encoding="utf-8")

        self.assertIn("[switch]$AllowUnsigned", release_build)
        self.assertIn("Public releases must be Authenticode-signed", release_build)
        self.assertIn("tester-only GitHub pre-release", release_build)
        self.assertIn("Never publish an unsigned build as a stable release", release_build)
        self.assertIn('@(".exe", ".dll", ".pyd")', release_build)
        self.assertIn("PE signature verification failed", release_build)
        self.assertIn("Portable PE signature verification failed", release_build)
        self.assertIn("Push-Location $ProjectRoot", release_build)
        self.assertIn("[System.IO.Path]::IsPathRooted($PythonPath)", release_build)
        self.assertIn("Pre-release", readme)
        self.assertIn("PowerAccessibleMailSetup-1.3.1-win-x64-UNSIGNED.exe", readme)

    def test_release_pipeline_avoids_opaque_update_behavior(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        app_build = (project_root / "build_power_accessible_mail.ps1").read_text(
            encoding="utf-8"
        )
        release_build = (
            project_root / "build_release_power_accessible_mail.ps1"
        ).read_text(encoding="utf-8")
        installer = (
            project_root / "installer_power_accessible_mail.iss"
        ).read_text(encoding="utf-8")
        updater = (project_root / "accessible_mail" / "updater.py").read_text(
            encoding="utf-8"
        )
        defender_scan = (
            project_root / "scan_release_with_defender.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('"--noupx"', app_build)
        self.assertNotIn('"--onefile"', app_build)
        self.assertIn("Compression=zip", installer)
        self.assertIn("SolidCompression=no", installer)
        self.assertIn("AppSupportURL=", installer)
        self.assertIn("LOCALAPPDATA", updater)
        self.assertNotIn('"/SILENT"', updater)
        self.assertNotIn('"/SUPPRESSMSGBOXES"', updater)
        self.assertIn("[switch]$RunDefenderScan", release_build)
        self.assertIn("PeComponents = $peComponents", release_build)
        self.assertIn("-DisableRemediation", defender_scan)
        self.assertIn("f'Unexpected PE machine", release_build)
        self.assertNotIn('f"Unexpected PE machine', release_build)
        self.assertIn("function Get-CompatibleRelativePath", release_build)
        self.assertNotIn("[System.IO.Path]::GetRelativePath", release_build)


if __name__ == "__main__":
    unittest.main()
