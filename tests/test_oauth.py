from __future__ import annotations

import base64
import inspect
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import rsa

from accessible_mail.oauth import (
    OAUTH_PROVIDERS,
    OAuthError,
    _post_form,
    _callback_handler,
    _validate_id_token,
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
    @classmethod
    def setUpClass(cls) -> None:
        cls.public_key, cls.private_key = rsa.newkeys(2048)

    def signed_id_token(self, claims: dict[str, object]) -> tuple[str, dict[str, object]]:
        header = {"alg": "RS256", "kid": "test-key", "typ": "JWT"}

        def encoded(payload: dict[str, object]) -> str:
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

        signing_text = f"{encoded(header)}.{encoded(claims)}"
        signature = rsa.sign(signing_text.encode("ascii"), self.private_key, "SHA-256")
        token = (
            f"{signing_text}."
            f"{base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')}"
        )
        key = {
            "kid": "test-key",
            "kty": "RSA",
            "alg": "RS256",
            "n": base64.urlsafe_b64encode(
                self.public_key.n.to_bytes((self.public_key.n.bit_length() + 7) // 8, "big")
            ).decode("ascii").rstrip("="),
            "e": base64.urlsafe_b64encode(
                self.public_key.e.to_bytes((self.public_key.e.bit_length() + 7) // 8, "big")
            ).decode("ascii").rstrip("="),
        }
        return token, key

    @patch("accessible_mail.oauth._find_signing_key")
    def test_google_id_token_signature_audience_issuer_and_nonce_are_verified(
        self,
        find_key: Mock,
    ) -> None:
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "client-id",
            "sub": "google-user",
            "email": "user@example.com",
            "email_verified": True,
            "nonce": "expected-nonce",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token, key = self.signed_id_token(claims)
        find_key.return_value = key

        validated = _validate_id_token(
            "google_gmail_api",
            token,
            "client-id",
            "expected-nonce",
        )

        self.assertEqual(validated["sub"], "google-user")

    @patch("accessible_mail.oauth._find_signing_key")
    def test_id_token_with_wrong_nonce_is_rejected(self, find_key: Mock) -> None:
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "client-id",
            "sub": "google-user",
            "email": "user@example.com",
            "email_verified": True,
            "nonce": "wrong-nonce",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token, key = self.signed_id_token(claims)
        find_key.return_value = key

        with self.assertRaisesRegex(OAuthError, "إعادة التشغيل"):
            _validate_id_token(
                "google_gmail_api",
                token,
                "client-id",
                "expected-nonce",
            )

    @patch("accessible_mail.oauth._find_signing_key")
    def test_microsoft_id_token_issuer_is_bound_to_tenant(self, find_key: Mock) -> None:
        tenant_id = "9188040d-6c67-4c5b-b112-36a304b66dad"
        claims = {
            "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            "aud": "client-id",
            "sub": "microsoft-user",
            "preferred_username": "user@example.com",
            "nonce": "expected-nonce",
            "tid": tenant_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token, key = self.signed_id_token(claims)
        key["issuer"] = "https://login.microsoftonline.com/{tenantid}/v2.0"
        find_key.return_value = key

        validated = _validate_id_token(
            "microsoft",
            token,
            "client-id",
            "expected-nonce",
        )

        self.assertEqual(validated["tid"], tenant_id)

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

    def test_callback_page_does_not_claim_the_account_was_already_saved(self) -> None:
        source = inspect.getsource(_callback_handler)

        self.assertIn("تم استلام موافقة تسجيل الدخول", source)
        self.assertNotIn(
            "تم تسجيل الدخول. يمكنك العودة إلى برنامج البريد الإلكتروني.",
            source,
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
