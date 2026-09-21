import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from accessible_mail.gmail_api_service import GmailApiService
from accessible_mail.email_service import EmailService, MailError
from accessible_mail.main_frame import MainFrame
from accessible_mail.models import Account, MessageSummary


class ArchiveTests(unittest.TestCase):
    def test_gmail_archive_query_excludes_non_archived_folders(self):
        service = SimpleNamespace(_request_json=Mock(return_value={"messages": []}))
        GmailApiService._list_summary_page(service, Account(), "ARCHIVE", 50)
        query = parse_qs(urlsplit(service._request_json.call_args.args[2]).query)
        self.assertEqual(query["q"], ["-in:inbox -in:spam -in:trash -in:drafts"])
        self.assertNotIn("labelIds", query)

    def test_gmail_restore_only_adds_inbox_label(self):
        service = SimpleNamespace(_modify_message_labels=Mock(), cache=Mock())
        account = Account()
        message = MessageSummary("7", "ARCHIVE")
        GmailApiService.restore_archived_message(service, account, message)
        service._modify_message_labels.assert_called_once_with(account, "7", add=["INBOX"])
        service.cache.delete_message.assert_called_once_with(account, "ARCHIVE", "7")

    def test_imap_restore_requires_safe_move(self):
        conn = SimpleNamespace(capabilities=(b"IMAP4REV1",), uid=Mock())
        service = SimpleNamespace(_imap=lambda a: nullcontext(conn), cache=Mock())
        with self.assertRaises(MailError):
            EmailService.restore_archived_message(service, Account(), MessageSummary("1", "Archive"))
        conn.uid.assert_not_called()
        service.cache.delete_message.assert_not_called()

    def test_archive_load_result_cannot_cross_accounts(self):
        account = Account(id="first")
        page = SimpleNamespace(archive_messages=[], apply_filter=Mock(), selected_filter_key=lambda: "archive")
        pending = []
        frame = SimpleNamespace(selected_account=lambda: account, ensure_password=lambda a: True,
                                displayed_account_id="first", SetStatusText=Mock(),
                                run_worker=lambda text, work, done, failed: pending.append(done))
        MainFrame.load_archive_messages(frame, page)
        frame.displayed_account_id = "second"
        pending[0](("Archive", [MessageSummary("1", "Archive")]))
        self.assertEqual(page.archive_messages, [])
        self.assertFalse(page._archive_loading)
