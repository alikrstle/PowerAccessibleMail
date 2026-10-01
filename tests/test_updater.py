from __future__ import annotations

import hashlib
import subprocess
import ssl
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from accessible_mail.update_checker import UpdateCheckResult, current_architecture
from accessible_mail.updater import (
    UpdateDownloadCancelled,
    UpdateInstallError,
    _system_powershell_path,
    authenticode_signature_status,
    can_install_update,
    default_update_root,
    download_update_installer,
    installer_name_from_url,
    launch_update_installer,
)


class DownloadResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self) -> DownloadResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return "https://release-assets.githubusercontent.com/download/setup.exe"

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.payload) - self.offset
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class InternalUpdaterTests(unittest.TestCase):
    @patch("accessible_mail.updater.ctypes.windll")
    @patch("accessible_mail.updater.Path.is_file", return_value=True)
    def test_signature_helper_uses_windows_system_directory(self, _is_file, windll) -> None:
        def system_directory(buffer, _length):
            buffer.value = r"C:\Windows\System32"
            return len(buffer.value)

        windll.kernel32.GetSystemDirectoryW.side_effect = system_directory
        with patch.dict("accessible_mail.updater.os.environ", {"PATH": r"C:\untrusted"}):
            self.assertEqual(
                _system_powershell_path(),
                Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"),
            )

    @patch("accessible_mail.updater._system_powershell_path", return_value=Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"))
    @patch("accessible_mail.updater.subprocess.run")
    def test_signature_path_is_data_not_powershell_code(self, run, powershell) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "Valid\n")
        target = Path(r"C:\synthetic folder\المثبت '$(); & name.exe")
        self.assertEqual(authenticode_signature_status(target), "Valid")
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[0], str(powershell.return_value))
        self.assertNotIn(str(target), arguments)
        self.assertNotIn(target.name, arguments[-1])
        self.assertEqual(run.call_args.kwargs["env"]["PAM_SIGNATURE_PATH"], str(target.resolve()))
        self.assertIn("-LiteralPath $env:PAM_SIGNATURE_PATH", arguments[-1])
        self.assertIn('Import-Module "$PSHOME\\Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1"', arguments[-1])
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    @patch("accessible_mail.updater._system_powershell_path", return_value=None)
    @patch("accessible_mail.updater.subprocess.run")
    def test_signature_check_never_falls_back_to_path(self, run, _powershell) -> None:
        self.assertEqual(authenticode_signature_status(Path("setup.exe")), "Unavailable")
        run.assert_not_called()

    @patch("accessible_mail.updater.ctypes.windll")
    def test_missing_system_directory_fails_closed(self, windll) -> None:
        for length in (0, 4096, 5000):
            with self.subTest(length=length):
                windll.kernel32.GetSystemDirectoryW.return_value = length
                self.assertIsNone(_system_powershell_path())

    def update_result(self, payload: bytes) -> UpdateCheckResult:
        architecture = current_architecture()
        return UpdateCheckResult(
            configured=True,
            available=True,
            current_version="1.2.10",
            latest_version="1.2.11",
            download_url=(
                "https://github.com/alikrstle/PowerAccessibleMail/releases/"
                "download/v1.2.11/"
                f"PowerAccessibleMailSetup-1.2.11-win-{architecture}.exe"
            ),
            sha256=hashlib.sha256(payload).hexdigest(),
            release_date="2026-08-01T10:00:00Z",
        )

    def test_direct_installer_requires_expected_product_name_and_https(self) -> None:
        valid = (
            "https://github.com/example/releases/download/v1/"
            "PowerAccessibleMailSetup-1.2.11-win-x86.exe"
        )

        self.assertEqual(
            installer_name_from_url(valid),
            "PowerAccessibleMailSetup-1.2.11-win-x86.exe",
        )
        self.assertEqual(
            installer_name_from_url(valid.replace(".exe", "-UNSIGNED.exe")),
            "PowerAccessibleMailSetup-1.2.11-win-x86-UNSIGNED.exe",
        )
        self.assertEqual(installer_name_from_url(valid.replace("https:", "http:")), "")
        self.assertEqual(
            installer_name_from_url("https://github.com/example/releases/tag/v1"),
            "",
        )

    def test_can_install_update_requires_sha256(self) -> None:
        result = self.update_result(b"MZinstaller")

        self.assertTrue(can_install_update(result))
        result.sha256 = ""
        self.assertFalse(can_install_update(result))

    def test_internal_update_requires_matching_version_and_architecture(self) -> None:
        result = self.update_result(b"MZinstaller")
        other_architecture = "x86" if current_architecture() == "x64" else "x64"

        result.download_url = result.download_url.replace(
            f"win-{current_architecture()}",
            f"win-{other_architecture}",
        )
        self.assertFalse(can_install_update(result))
        with self.assertRaisesRegex(UpdateInstallError, "معمارية"):
            download_update_installer(result)

        result = self.update_result(b"MZinstaller")
        result.latest_version = "../1.2.11"
        self.assertFalse(can_install_update(result))
        with self.assertRaisesRegex(UpdateInstallError, "رقم الإصدار"):
            download_update_installer(result)

        result = self.update_result(b"MZinstaller")
        result.latest_version = ".."
        result.download_url = result.download_url.replace("1.2.11", "..")
        self.assertFalse(can_install_update(result))
        with self.assertRaisesRegex(UpdateInstallError, "رقم الإصدار"):
            download_update_installer(result)

    @patch("accessible_mail.updater.urllib.request.urlopen")
    @patch("accessible_mail.updater.trusted_https_context")
    def test_download_verifies_sha256_and_reports_progress(
        self,
        https_context,
        urlopen,
    ) -> None:
        payload = b"MZ" + (b"installer-data" * 100)
        urlopen.return_value = DownloadResponse(payload)
        progress: list[tuple[int, int]] = []

        with tempfile.TemporaryDirectory() as directory:
            path = download_update_installer(
                self.update_result(payload),
                target_root=Path(directory),
                progress=lambda downloaded, total: progress.append(
                    (downloaded, total)
                ),
            )

            self.assertEqual(path.read_bytes(), payload)

        self.assertTrue(progress)
        self.assertEqual(progress[-1], (len(payload), len(payload)))
        self.assertIs(urlopen.call_args.kwargs["context"], https_context.return_value)

    @patch("accessible_mail.updater.urllib.request.urlopen")
    def test_download_rejects_wrong_sha256_and_removes_partial_file(
        self,
        urlopen,
    ) -> None:
        payload = b"MZwrong-installer"
        urlopen.return_value = DownloadResponse(payload)
        result = self.update_result(payload)
        result.sha256 = "0" * 64

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(UpdateInstallError):
                download_update_installer(result, target_root=root)
            self.assertEqual(list(root.iterdir()), [])

    @patch("accessible_mail.updater.urllib.request.urlopen")
    def test_certificate_failure_is_localized_and_removes_partial_file(
        self,
        urlopen,
    ) -> None:
        urlopen.side_effect = urllib.error.URLError(
            ssl.SSLCertVerificationError(
                1,
                "certificate verify failed: certificate has expired",
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                UpdateInstallError,
                "TLS-CERTIFICATE-VERIFY",
            ):
                download_update_installer(
                    self.update_result(b"MZinstaller"),
                    target_root=root,
                )
            self.assertEqual(list(root.iterdir()), [])

    @patch("accessible_mail.updater.urllib.request.urlopen")
    def test_download_can_be_cancelled(self, urlopen) -> None:
        payload = b"MZcancelled-installer"
        urlopen.return_value = DownloadResponse(payload)
        cancel_event = threading.Event()
        cancel_event.set()

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(UpdateDownloadCancelled):
                download_update_installer(
                    self.update_result(payload),
                    target_root=Path(directory),
                    cancel_event=cancel_event,
                )

    def test_default_update_root_uses_local_application_data(self) -> None:
        with patch.dict(
            "accessible_mail.updater.os.environ",
            {"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"},
            clear=True,
        ):
            root = default_update_root("1.2.14")

        self.assertEqual(
            root,
            Path(
                r"C:\Users\Tester\AppData\Local\SoljanAlSharq"
                r"\PowerAccessibleMail\Updates\1.2.14"
            ),
        )

    @patch("accessible_mail.updater.authenticode_signature_status", return_value="Valid")
    @patch("accessible_mail.updater.subprocess.Popen")
    def test_launcher_uses_visible_internal_update_mode(self, popen, _signature) -> None:
        with tempfile.TemporaryDirectory() as directory:
            installer = Path(directory) / "setup.exe"
            installer.write_bytes(b"MZinstaller")

            launch_update_installer(installer, "ar")

        arguments = popen.call_args.args[0]
        self.assertIn("/UPDATEFROMAPP=1", arguments)
        self.assertIn("/CLOSEAPPLICATIONS", arguments)
        self.assertNotIn("/VERYSILENT", arguments)
        self.assertIn("/LANG=arabic", arguments)
        self.assertNotIn("/SUPPRESSMSGBOXES", arguments)
        self.assertNotIn("/RESTARTAPPLICATIONS", arguments)

    @patch("accessible_mail.updater.authenticode_signature_status", return_value="Valid")
    @patch("accessible_mail.updater.subprocess.Popen")
    def test_launcher_passes_every_supported_installer_language(
        self, popen, _signature
    ) -> None:
        expected = {
            "en": "english",
            "ar": "arabic",
            "fr": "french",
            "es": "spanish",
            "tr": "turkish",
            "hi": "hindi",
            "zh-CN": "chinesesimplified",
            "ru": "russian",
            "ja": "japanese",
            "de": "german",
        }
        with tempfile.TemporaryDirectory() as directory:
            installer = Path(directory) / "setup.exe"
            installer.write_bytes(b"MZinstaller")
            for language, installer_language in expected.items():
                with self.subTest(language=language):
                    popen.reset_mock()
                    launch_update_installer(installer, language)
                    arguments = popen.call_args.args[0]
                    self.assertIn(f"/LANG={installer_language}", arguments)

    @patch("accessible_mail.updater.authenticode_signature_status", return_value="HashMismatch")
    @patch("accessible_mail.updater.subprocess.Popen")
    def test_launcher_rejects_untrusted_authenticode_signature(
        self, popen, _signature
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            installer = Path(directory) / "setup.exe"
            installer.write_bytes(b"MZinstaller")
            with self.assertRaisesRegex(UpdateInstallError, "Authenticode"):
                launch_update_installer(installer, "ar")
        popen.assert_not_called()

    @patch("accessible_mail.updater.authenticode_signature_status", return_value="NotSigned")
    @patch("accessible_mail.updater.subprocess.Popen")
    def test_launcher_allows_explicitly_named_unsigned_installer(
        self, popen, _signature
    ) -> None:
        architecture = current_architecture()
        with tempfile.TemporaryDirectory() as directory:
            installer = Path(directory) / (
                f"PowerAccessibleMailSetup-1.2.11-win-{architecture}-UNSIGNED.exe"
            )
            installer.write_bytes(b"MZinstaller")
            launch_update_installer(installer, "ar")
        popen.assert_called_once()

    @patch("accessible_mail.updater.authenticode_signature_status", return_value="NotSigned")
    @patch("accessible_mail.updater.subprocess.Popen")
    def test_launcher_rejects_unmarked_unsigned_installer(
        self, popen, _signature
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            installer = Path(directory) / "setup.exe"
            installer.write_bytes(b"MZinstaller")
            with self.assertRaisesRegex(UpdateInstallError, "Authenticode"):
                launch_update_installer(installer, "ar")
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
