from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from accessible_mail.content_security import (
    UnsafeImageError,
    detect_raster_image_type,
    scan_bytes_with_antimalware,
    validate_and_scan_image,
)
from accessible_mail.network_security import UnsafeRemoteUrl, validate_public_http_url


class NetworkSecurityTests(unittest.TestCase):
    @patch("accessible_mail.network_security.socket.getaddrinfo")
    def test_public_http_image_url_remains_supported(self, getaddrinfo: Mock) -> None:
        getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 80))]

        self.assertEqual(
            validate_public_http_url("http://images.example.com/logo.png"),
            "http://images.example.com/logo.png",
        )

    @patch("accessible_mail.network_security.socket.getaddrinfo")
    def test_private_and_loopback_image_hosts_are_blocked(self, getaddrinfo: Mock) -> None:
        getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.10", 80))]
        with self.assertRaisesRegex(UnsafeRemoteUrl, "محلية أو خاصة"):
            validate_public_http_url("http://images.example.com/logo.png")

        with self.assertRaisesRegex(UnsafeRemoteUrl, "محلي"):
            validate_public_http_url("http://127.0.0.1/logo.png")


class ContentSecurityTests(unittest.TestCase):
    def test_known_raster_signatures_are_detected(self) -> None:
        self.assertEqual(
            detect_raster_image_type(b"\x89PNG\r\n\x1a\nrest"),
            ("image/png", ".png"),
        )
        self.assertEqual(
            detect_raster_image_type(b"\xff\xd8\xffrest"),
            ("image/jpeg", ".jpg"),
        )

    def test_svg_and_executable_content_are_rejected(self) -> None:
        for content in (b"<svg><script>alert(1)</script></svg>", b"MZ executable"):
            with self.subTest(content=content[:3]):
                with self.assertRaises(UnsafeImageError):
                    detect_raster_image_type(content)

    @patch("accessible_mail.content_security.scan_bytes_with_antimalware")
    def test_declared_type_must_match_and_valid_image_is_scanned(self, scan: Mock) -> None:
        data = b"\x89PNG\r\n\x1a\nrest"
        self.assertEqual(
            validate_and_scan_image(data, "image/png"),
            ("image/png", ".png"),
        )
        scan.assert_called_once_with(data)

        with self.assertRaisesRegex(UnsafeImageError, "لا يطابق"):
            validate_and_scan_image(data, "image/jpeg")

    @patch("accessible_mail.content_security.os.name", "nt")
    @patch("accessible_mail.content_security._amsi_scan_buffer", return_value=32768)
    def test_antimalware_detection_rejects_image(
        self,
        _scan: Mock,
    ) -> None:
        with self.assertRaisesRegex(UnsafeImageError, "محتوى ضار"):
            scan_bytes_with_antimalware(b"data")


if __name__ == "__main__":
    unittest.main()
