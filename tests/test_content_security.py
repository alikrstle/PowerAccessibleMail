from __future__ import annotations

import ssl
import unittest
import urllib.error
from unittest.mock import Mock, patch

from accessible_mail.content_security import (
    UnsafeImageError,
    detect_raster_image_type,
    scan_bytes_with_antimalware,
    validate_and_scan_image,
)
from accessible_mail.network_security import (
    TLS_CERTIFICATE_ERROR_MESSAGE,
    UnsafeRemoteUrl,
    certificate_verification_failed,
    friendly_https_error,
    trusted_https_context,
    validate_public_http_url,
)


class NetworkSecurityTests(unittest.TestCase):
    def tearDown(self) -> None:
        trusted_https_context.cache_clear()

    @patch("accessible_mail.network_security.truststore")
    def test_https_context_prefers_native_system_trust_store(
        self,
        native_truststore: Mock,
    ) -> None:
        context = native_truststore.SSLContext.return_value

        result = trusted_https_context()

        self.assertIs(result, context)
        native_truststore.SSLContext.assert_called_once()
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)

    @patch("accessible_mail.network_security.truststore", None)
    @patch("accessible_mail.network_security.sys.platform", "win32")
    @patch("accessible_mail.network_security.ssl.enum_certificates")
    @patch("accessible_mail.network_security.ssl.create_default_context")
    def test_https_context_loads_windows_root_certificates(
        self,
        create_default_context: Mock,
        enum_certificates: Mock,
    ) -> None:
        context = create_default_context.return_value
        enum_certificates.side_effect = [
            [(b"root-certificate", "x509_asn", True)],
            [],
        ]
        trusted_https_context.cache_clear()

        result = trusted_https_context()

        self.assertIs(result, context)
        self.assertEqual(enum_certificates.call_count, 2)
        context.load_verify_locations.assert_called_once_with(
            cadata=b"root-certificate"
        )

    def test_certificate_verification_error_is_detected_through_url_error(self) -> None:
        certificate_error = ssl.SSLCertVerificationError(
            1,
            "certificate verify failed: certificate has expired",
        )
        error = urllib.error.URLError(certificate_error)

        self.assertTrue(certificate_verification_failed(error))
        self.assertEqual(friendly_https_error(error), TLS_CERTIFICATE_ERROR_MESSAGE)

    def test_unrelated_network_error_is_not_mislabeled_as_certificate_failure(self) -> None:
        error = OSError("connection timed out")

        self.assertFalse(certificate_verification_failed(error))
        self.assertEqual(friendly_https_error(error), "")

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
