from __future__ import annotations

import unittest

from accessible_mail.windows_integration import (
    CAPABILITIES_PATH,
    DEFAULT_APPS_SETTINGS_URI,
    MAILTO_PROG_ID,
    REGISTERED_APPLICATION_NAME,
    default_mail_registry_entries,
)


class WindowsIntegrationTests(unittest.TestCase):
    def test_default_apps_uri_uses_the_registered_display_name(self) -> None:
        self.assertEqual(
            DEFAULT_APPS_SETTINGS_URI,
            "ms-settings:defaultapps?registeredAppUser=Power%20Accessible%20Mail",
        )

    def test_registry_registration_uses_one_consistent_application_name(self) -> None:
        entries = default_mail_registry_entries('"app.exe" "%1"', "app.exe,0")
        self.assertTrue(entries)
        values = {
            (path, value_name): value
            for path, value_name, value, _value_type in entries
        }

        self.assertEqual(
            values[(CAPABILITIES_PATH, "ApplicationName")],
            REGISTERED_APPLICATION_NAME,
        )
        self.assertEqual(values[(CAPABILITIES_PATH, "Hidden")], 0)
        self.assertEqual(
            values[(r"Software\RegisteredApplications", REGISTERED_APPLICATION_NAME)],
            CAPABILITIES_PATH,
        )
        self.assertEqual(
            values[(CAPABILITIES_PATH + r"\UrlAssociations", "mailto")],
            MAILTO_PROG_ID,
        )
        self.assertIn(
            (r"Software\Classes\mailto\OpenWithProgids", MAILTO_PROG_ID),
            values,
        )
        self.assertIn("%1", values[(rf"Software\Classes\{MAILTO_PROG_ID}\shell\open\command", "")])
        self.assertEqual(
            values[(rf"Software\Classes\{MAILTO_PROG_ID}\Application", "ApplicationName")],
            REGISTERED_APPLICATION_NAME,
        )
        self.assertEqual(
            values[(rf"Software\Classes\{MAILTO_PROG_ID}", "FriendlyTypeName")],
            "Power Accessible Mail email link",
        )


if __name__ == "__main__":
    unittest.main()
