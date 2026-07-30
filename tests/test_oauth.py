from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail.oauth import (
    OAUTH_PROVIDERS,
    OAuthError,
    _post_form,
    available_provider_ids,
    google_provider_id,
    oauth_callback_error_message,
    oauth_error_requires_reauthentication,
    provider_id_from_name,
    run_browser_oauth_flow,
)


class OAuthResponse:
    def __init__(self, final_url: str, payload: bytes) -> None:
        self.final_url = final_url
        self.payload = payload

    def __enter__(self) -> "OAuthResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.final_url

    def read(self, size: int) -> bytes:
        return self.payload[:size]


class OAuthErrorTests(unittest.TestCase):
    def test_invalid_grant_requires_reauthentication(self) -> None:
        self.assertTrue(oauth_error_requires_reauthentication("invalid_grant", ""))

    def test_expired_or_revoked_token_requires_reauthentication(self) -> None:
        self.assertTrue(
            oauth_error_requires_reauthentication(
                "",
                "Token has been expired or revoked.",
            )
        )

    def test_invalid_scope_is_not_treated_as_expired_token(self) -> None:
        self.assertFalse(oauth_error_requires_reauthentication("invalid_scope", "invalid_scope"))

    def test_blocked_test_user_gets_actionable_message(self) -> None:
        message = oauth_callback_error_message(
            "access_denied",
            "Access blocked: This app has not completed the Google verification process.",
        )

        self.assertIn("قائمة المختبرين", message)
        self.assertIn("الحساب المختار", message)

    def test_user_canceling_consent_is_not_reported_as_configuration_failure(self) -> None:
        message = oauth_callback_error_message("access_denied", "The user denied the request")

        self.assertEqual(
            message,
            "ألغيت الموافقة على وصول Power Accessible Mail إلى الحساب.",
        )

    def test_unknown_callback_error_keeps_provider_description(self) -> None:
        self.assertEqual(
            oauth_callback_error_message("server_error", "Temporary failure"),
            "Temporary failure",
        )

    def test_unified_product_uses_gmail_api_and_microsoft(self) -> None:
        self.assertEqual(
            available_provider_ids(),
            ["google_gmail_api", "microsoft"],
        )
        self.assertEqual(provider_id_from_name("Google / Gmail"), "google_gmail_api")
        self.assertEqual(google_provider_id(), "google_gmail_api")
        self.assertNotIn("google", OAUTH_PROVIDERS)

    @patch("accessible_mail.oauth.threading.Thread")
    @patch("accessible_mail.oauth.webbrowser.open", return_value=False)
    @patch("accessible_mail.oauth._make_callback_server")
    def test_browser_launch_failure_stops_local_callback_server(
        self,
        make_server: Mock,
        _open_browser: Mock,
        _thread: Mock,
    ) -> None:
        server = SimpleNamespace(
            server_port=8765,
            server_close=Mock(),
            oauth_event=threading.Event(),
        )
        make_server.return_value = server

        with self.assertRaisesRegex(OAuthError, "فتح المتصفح"):
            run_browser_oauth_flow("microsoft", "client-id")

        server.server_close.assert_called_once_with()

    @patch("accessible_mail.oauth.threading.Thread")
    @patch("accessible_mail.oauth.webbrowser.open", return_value=True)
    @patch("accessible_mail.oauth._make_callback_server")
    def test_browser_login_can_be_cancelled_without_waiting_for_timeout(
        self,
        make_server: Mock,
        _open_browser: Mock,
        _thread: Mock,
    ) -> None:
        server = SimpleNamespace(
            server_port=8765,
            server_close=Mock(),
            oauth_event=threading.Event(),
        )
        make_server.return_value = server
        cancel_event = threading.Event()
        cancel_event.set()

        with self.assertRaisesRegex(OAuthError, "إلغاء"):
            run_browser_oauth_flow(
                "microsoft",
                "client-id",
                cancel_event=cancel_event,
            )

        server.server_close.assert_called_once_with()

    @patch("accessible_mail.oauth.urllib.request.urlopen")
    def test_oauth_rejects_insecure_redirect(self, urlopen: Mock) -> None:
        urlopen.return_value = OAuthResponse(
            "http://login.example.com/token",
            b"{}",
        )

        with self.assertRaisesRegex(OAuthError, "غير آمن"):
            _post_form("https://login.example.com/token", {"code": "value"})

    @patch("accessible_mail.oauth.urllib.request.urlopen")
    def test_oauth_response_size_is_bounded(self, urlopen: Mock) -> None:
        urlopen.return_value = OAuthResponse(
            "https://login.example.com/token",
            b"x" * (1024 * 1024 + 1),
        )

        with self.assertRaisesRegex(OAuthError, "الحجم"):
            _post_form("https://login.example.com/token", {"code": "value"})


if __name__ == "__main__":
    unittest.main()
