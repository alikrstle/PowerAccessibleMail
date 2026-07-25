from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from accessible_mail import screen_reader


class ScreenReaderTests(unittest.TestCase):
    @patch("accessible_mail.screen_reader._load_controller")
    @patch(
        "accessible_mail.screen_reader._is_interactive_desktop",
        return_value=True,
    )
    def test_nvda_speech_is_cancelled_before_notification(
        self,
        _interactive_desktop: Mock,
        load_controller: Mock,
    ) -> None:
        controller = Mock()
        controller.nvdaController_testIfRunning.return_value = 0
        controller.nvdaController_cancelSpeech.return_value = 0
        controller.nvdaController_speakText.return_value = 0
        load_controller.return_value = controller

        spoken = screen_reader.interrupt_and_speak("Notification")

        self.assertTrue(spoken)
        self.assertEqual(
            controller.method_calls,
            [
                call.nvdaController_testIfRunning(),
                call.nvdaController_cancelSpeech(),
                call.nvdaController_speakText("Notification"),
            ],
        )

    @patch("accessible_mail.screen_reader._load_controller")
    @patch(
        "accessible_mail.screen_reader._is_interactive_desktop",
        return_value=False,
    )
    def test_secure_desktop_does_not_receive_nvda_speech(
        self,
        _interactive_desktop: Mock,
        load_controller: Mock,
    ) -> None:
        self.assertFalse(screen_reader.interrupt_and_speak("Private message"))
        load_controller.assert_not_called()

    def test_bundled_nvda_controllers_match_expected_release_files(self) -> None:
        vendor_path = Path(screen_reader.__file__).resolve().parent / "vendor" / "nvda"
        expected_hashes = {
            "x64": "2FE60CF00BE929AAE32E95C1E1507A20ADA4902C8FEC273B3CC2D3BF5472932A",
            "x86": "AB824A1126FEF9135F5E7FEDC4DDEB8EBCE73A5BFCB6086E1799971D92DCA8B4",
        }

        for architecture, expected_hash in expected_hashes.items():
            controller_path = vendor_path / architecture / "nvdaControllerClient.dll"
            digest = hashlib.sha256(controller_path.read_bytes()).hexdigest().upper()
            self.assertEqual(digest, expected_hash)
