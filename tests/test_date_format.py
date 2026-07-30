from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from accessible_mail.date_format import (
    _text_separator,
    format_message_date,
    format_system_datetime,
)


class DateFormatTests(unittest.TestCase):
    @patch(
        "accessible_mail.date_format._windows_formatted_datetime",
        return_value="الخميس، 30 تموز, 2026، 04:05 م",
    )
    def test_system_format_is_used_without_app_language_mapping(
        self,
        system_format: Mock,
    ) -> None:
        value = datetime(2026, 7, 30, 16, 5)

        self.assertEqual(
            format_system_datetime(value),
            "الخميس، 30 تموز, 2026، 04:05 م",
        )
        system_format.assert_called_once_with(value)

    @patch(
        "accessible_mail.date_format.format_system_datetime",
        return_value="system date",
    )
    @patch("accessible_mail.date_format.datetime")
    def test_message_timestamp_is_converted_to_local_system_time(
        self,
        datetime_type: Mock,
        system_format: Mock,
    ) -> None:
        local_value = datetime(2026, 7, 30, 16, 5)
        datetime_type.fromtimestamp.return_value.astimezone.return_value = local_value

        self.assertEqual(format_message_date(1.0, "fallback"), "system date")
        datetime_type.fromtimestamp.assert_called_once_with(1.0)
        system_format.assert_called_once_with(local_value)

    def test_separator_follows_the_script_direction(self) -> None:
        self.assertEqual(_text_separator("تموز"), "، ")
        self.assertEqual(_text_separator("July"), ", ")


if __name__ == "__main__":
    unittest.main()
