import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from accessible_mail.models import MessageSummary
from accessible_mail.search_filters import date_cutoff, matches_filters
from accessible_mail.mail_page import MailPage


class SearchFilterTests(unittest.TestCase):
    def test_hidden_search_label_is_cleared_in_shortcut_and_button_modes(self):
        for mode in ("shortcut", "button", "field"):
            with self.subTest(mode=mode):
                page = SimpleNamespace(search_button=Mock(), search_field=Mock(),
                                       search_field_label=Mock(), search_query="", Layout=Mock())
                MailPage.set_search_mode(page, mode)
                page.search_field_label.Show.assert_called_once_with(mode == "field")
                label = page.search_field_label.SetLabel.call_args.args[0]
                self.assertEqual(bool(label), mode == "field")

    def test_draft_changes_do_not_apply_search(self):
        page = SimpleNamespace(search_filters_panel=SimpleNamespace(IsShown=lambda: True),
                               search_query="previous", apply_filter=Mock())
        MailPage.on_search_text(page, None)
        self.assertEqual(page.search_query, "previous")
        page.apply_filter.assert_not_called()

    def test_search_button_commits_all_values_and_announces_results(self):
        timer = Mock()
        page = SimpleNamespace(
            _search_announcement_call=timer,
            search_field=SimpleNamespace(GetValue=lambda: "report"),
            sender_search_filter=SimpleNamespace(GetValue=lambda: " Ali "),
            date_search_filter=SimpleNamespace(GetSelection=lambda: 2),
            set_search_query=Mock(), announce_search_result_count=Mock(),
        )
        MailPage.on_apply_search(page, None)
        self.assertEqual(page._applied_sender_filter, "Ali")
        self.assertEqual(page._applied_date_filter, 2)
        page.set_search_query.assert_called_once_with("report")
        page.announce_search_result_count.assert_called_once()
        timer.Stop.assert_called_once()

    def test_calendar_months_and_leap_year(self):
        now = datetime(2024, 3, 31, tzinfo=timezone.utc)
        expected = [(2024, 3, 30), (2024, 3, 24), (2024, 2, 29),
                    (2023, 9, 30), (2023, 3, 31), (2022, 3, 31),
                    (2021, 3, 31), (2019, 3, 31)]
        self.assertIsNone(date_cutoff(0, now))
        for selection, parts in enumerate(expected, 1):
            self.assertEqual(date_cutoff(selection, now), datetime(*parts, tzinfo=timezone.utc).timestamp())

    def test_sender_and_date_are_combined(self):
        message = MessageSummary(uid="1", mailbox="INBOX", sender="Ali", sender_email="ali@example.com", received_at=100)
        self.assertTrue(matches_filters(message, "ALI example", 99, now=101))
        self.assertFalse(matches_filters(message, "someone", 99, now=101))
        self.assertFalse(matches_filters(message, "Ali", 101, now=102))
        self.assertTrue(matches_filters(message, "Ali", 100, now=101))
        self.assertFalse(matches_filters(message, "Ali", 99, now=99))
        self.assertTrue(matches_filters(message, "Ali", 101, older_than=True))

    def test_unknown_date_only_matches_unrestricted_date(self):
        message = MessageSummary(uid="1", mailbox="INBOX")
        self.assertTrue(matches_filters(message))
        self.assertFalse(matches_filters(message, cutoff=100))

    def test_escape_clears_inline_search_and_cancels_announcement(self):
        timer = Mock()
        page = SimpleNamespace(search_mode="field", search_query="hello", _search_announcement_call=timer,
                               set_search_query=Mock(), focus_message_list=Mock())
        self.assertTrue(MailPage.exit_search(page))
        page.set_search_query.assert_called_once_with("")
        timer.Stop.assert_called_once()
        page.focus_message_list.assert_called_once()

    def test_escape_closes_search_dialog(self):
        page = SimpleNamespace(close_search=Mock())
        self.assertTrue(MailPage.exit_search(page))
        page.close_search.assert_called_once()
