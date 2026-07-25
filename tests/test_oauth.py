from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from accessible_mail.oauth import (
    google_provider_id,
    oauth_callback_error_message,
    oauth_error_requires_reauthentication,
    provider_id_from_name,
)


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

    def test_limited_edition_resolves_google_to_limited_provider(self) -> None:
        with patch.dict(os.environ, {"POWER_ACCESSIBLE_MAIL_LIMITED_GOOGLE": "1"}):
            self.assertEqual(provider_id_from_name("Google / Gmail"), "google_gmail_api")
            self.assertEqual(google_provider_id(), "google_gmail_api")

    def test_full_edition_resolves_google_to_full_provider(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("POWER_ACCESSIBLE_MAIL_LIMITED_GOOGLE", None)
            self.assertEqual(provider_id_from_name("Google / Gmail"), "google")
            self.assertEqual(google_provider_id(), "google")


if __name__ == "__main__":
    unittest.main()
