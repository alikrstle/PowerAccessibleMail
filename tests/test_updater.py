from __future__ import annotations

import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from accessible_mail.update_checker import UpdateCheckResult
from accessible_mail.updater import (
    UpdateDownloadCancelled,
    UpdateInstallError,
    can_install_update,
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
    def update_result(self, payload: bytes) -> UpdateCheckResult:
        return UpdateCheckResult(
            configured=True,
            available=True,
            current_version="1.2.10",
            latest_version="1.2.11",
            download_url=(
                "https://github.com/alikrstle/PowerAccessibleMail/releases/"
                "download/v1.2.11/"
                "PowerAccessibleMailSetup-1.2.11-win-x64-UNSIGNED.exe"
            ),
            sha256=hashlib.sha256(payload).hexdigest(),
            release_date="2026-08-01T10:00:00Z",
        )

    def test_direct_installer_requires_expected_product_name_and_https(self) -> None:
        valid = (
            "https://github.com/example/releases/download/v1/"
            "PowerAccessibleMailSetup-1.2.11-win-x86-UNSIGNED.exe"
        )

        self.assertEqual(
            installer_name_from_url(valid),
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

    @patch("accessible_mail.updater.urllib.request.urlopen")
    def test_download_verifies_sha256_and_reports_progress(self, urlopen) -> None:
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

    @patch("accessible_mail.updater.subprocess.Popen")
    def test_launcher_uses_internal_silent_update_mode(self, popen) -> None:
        with tempfile.TemporaryDirectory() as directory:
            installer = Path(directory) / "setup.exe"
            installer.write_bytes(b"MZinstaller")

            launch_update_installer(installer)

        arguments = popen.call_args.args[0]
        self.assertIn("/SILENT", arguments)
        self.assertIn("/UPDATEFROMAPP=1", arguments)
        self.assertNotIn("/RESTARTAPPLICATIONS", arguments)


if __name__ == "__main__":
    unittest.main()
