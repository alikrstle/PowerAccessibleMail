from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail.address_book import (
    AddressEntry,
    add_address,
    load_address_book,
    normalize_email_address,
    save_address_book,
)
from accessible_mail.address_book_dialog import AddressBookDialog
from accessible_mail.notification_preferences import EVENT_ADDRESS_BOOK


class AddressBookStorageTests(unittest.TestCase):
    def test_email_addresses_are_validated_and_normalized(self) -> None:
        self.assertEqual(
            normalize_email_address("Person <person@example.com>"),
            "person@example.com",
        )
        self.assertEqual(normalize_email_address("person@example.com"), "person@example.com")
        self.assertEqual(normalize_email_address("not-an-email"), "")
        self.assertEqual(normalize_email_address("one@example.com, two@example.com"), "")

    def test_addresses_round_trip_with_pinned_entries_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "address_book.json"
            with patch("accessible_mail.address_book.address_book_path", return_value=path):
                save_address_book(
                    [
                        AddressEntry("z@example.com"),
                        AddressEntry("pinned@example.com", pinned=True),
                        AddressEntry("a@example.com"),
                    ]
                )
                restored = load_address_book()

        self.assertEqual(
            [(entry.email, entry.pinned) for entry in restored],
            [
                ("pinned@example.com", True),
                ("a@example.com", False),
                ("z@example.com", False),
            ],
        )

    def test_add_address_rejects_case_insensitive_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "address_book.json"
            with patch("accessible_mail.address_book.address_book_path", return_value=path):
                first = add_address("Person@Example.com")
                duplicate = add_address("person@example.com")
                invalid = add_address("invalid")

        self.assertEqual(first, (True, "Person@Example.com"))
        self.assertEqual(duplicate, (False, "duplicate"))
        self.assertEqual(invalid, (False, "invalid"))

    @patch("accessible_mail.address_book_dialog.save_address_book")
    def test_pin_command_toggles_between_pinned_and_unpinned(
        self,
        save: Mock,
    ) -> None:
        entry = AddressEntry("person@example.com")
        dialog = SimpleNamespace(
            entries=[entry],
            address_list=Mock(),
            selected_entry=lambda: entry,
            refresh_list=Mock(),
            announce_event=Mock(),
        )

        AddressBookDialog.on_pin(dialog)
        self.assertTrue(entry.pinned)
        self.assertIn("تم تثبيت", dialog.announce_event.call_args.args[0])

        AddressBookDialog.on_pin(dialog)
        self.assertFalse(entry.pinned)
        self.assertIn("تم إلغاء تثبيت", dialog.announce_event.call_args.args[0])
        self.assertEqual(save.call_count, 2)

    @patch("accessible_mail.address_book_dialog.announce_to_screen_reader")
    def test_address_events_are_passed_through_nvda_notification_path(
        self,
        announce: Mock,
    ) -> None:
        event_status = Mock()
        dialog = SimpleNamespace(event_status=event_status, Layout=Mock())

        AddressBookDialog.announce_event(dialog, "تم حذف عنوان البريد الإلكتروني.")

        event_status.SetLabel.assert_called_once()
        dialog.Layout.assert_called_once_with()
        announce.assert_called_once_with(
            event_status,
            "تم حذف عنوان البريد الإلكتروني.",
            EVENT_ADDRESS_BOOK,
        )

    @patch(
        "accessible_mail.address_book_dialog.wx.CallAfter",
        side_effect=lambda function, *args: function(*args),
    )
    @patch("accessible_mail.address_book_dialog.wx.MessageBox")
    def test_empty_conversation_result_keeps_focus_in_address_book(
        self,
        message_box: Mock,
        _call_after: Mock,
    ) -> None:
        entry = AddressEntry("person@example.com")
        address_list = Mock()
        dialog = SimpleNamespace(
            selected_entry=lambda: entry,
            message_matcher=lambda _email: [],
            address_list=address_list,
        )

        AddressBookDialog.on_view_messages(dialog)

        message_box.assert_called_once()
        self.assertIn("لا توجد محادثات مع هذا العنوان", message_box.call_args.args[0])
        self.assertIs(message_box.call_args.args[-1], dialog)
        address_list.SetFocus.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
