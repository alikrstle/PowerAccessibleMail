from __future__ import annotations

import unittest
from unittest.mock import Mock
from types import SimpleNamespace

import wx

from accessible_mail.custom_categories import CustomCategory, decode_imap_mailbox, encode_imap_mailbox
from accessible_mail.custom_category_dialog import CategoryRulesDialog, CustomCategoryDialog
from accessible_mail.email_service import EmailService, MailError, MailboxInfo
from accessible_mail.gmail_api_service import GmailApiService
from accessible_mail.main_frame import MainFrame
from accessible_mail.mail_page import MailPage
from accessible_mail.models import Account, MessageSummary


class CustomCategoryTests(unittest.TestCase):
    def test_rule_picker_enter_or_click_accepts_single_rule(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        dialog = CategoryRulesDialog(parent, (("recent_read", "Recently read"), ("attachments", "Attachments")))
        try:
            dialog._accept_current_rule = Mock()
            event = Mock()
            event.GetKeyCode.return_value = wx.WXK_RETURN
            event.HasModifiers.return_value = False
            dialog.on_rule_key(event)
            self.assertEqual(dialog.selected_rules(), ("recent_read",))
            dialog._accept_current_rule.assert_called_once_with()
            dialog.rule_list.SetSelection(1)
            self.assertEqual(dialog.selected_rules(), ("attachments",))
            click = Mock()
            click.GetPosition.return_value = wx.Point(5, 5)
            dialog.rule_list.HitTest = Mock(return_value=0)
            with unittest.mock.patch("accessible_mail.custom_category_dialog.wx.CallAfter") as call_after:
                dialog.on_rule_click(click)
            self.assertEqual(dialog.selected_rules(), ("recent_read",))
            call_after.assert_called_once_with(dialog._accept_current_rule)
            event.Skip.assert_not_called()
        finally:
            dialog.Destroy()

    def test_custom_category_is_a_conjunction_of_message_properties(self) -> None:
        matching = MessageSummary(uid="1", mailbox="INBOX", sender_email="staff@company.org", has_attachments=True)
        not_matching = MessageSummary(uid="2", mailbox="INBOX", sender_email="person@gmail.com", has_attachments=True)
        rules = ("organization", "attachments")
        self.assertTrue(MailPage.matches_custom_category(matching, rules))
        self.assertFalse(MailPage.matches_custom_category(not_matching, rules))

    def test_new_custom_category_filters(self) -> None:
        message = MessageSummary(
            uid="1", mailbox="INBOX", sender_email="news@company.org",
            recipient_emails=["reader@example.com"], subject="خصم جديد", is_read=True,
        )
        context = dict(recent_read_keys=frozenset({("INBOX", "1")}), sender_frequency={"news@company.org": 5})
        self.assertTrue(MailPage.matches_custom_category(message, ("recent_read", "promotional", "frequent_sender", "no_attachments"), **context))
        self.assertTrue(MailPage.matches_custom_category(message, ("specific_email",), email_addresses=("reader@example.com",)))
        self.assertFalse(MailPage.matches_custom_category(message, ("attachments",), **context))
        self.assertFalse(MailPage.matches_custom_category(message, ("specific_email",), email_addresses=("other@example.com",)))

    def test_ctrl_arrows_jump_between_first_section_and_first_local_category(self) -> None:
        choice = Mock()
        page = SimpleNamespace(filter_choice=choice, base_filter_count=6, on_filter=Mock())
        notice = Mock()
        frame = SimpleNamespace(_visible_category_ids=["local-1"], current_page=lambda: page,
                                show_notification=notice)
        event = Mock()
        event.ControlDown.return_value = True
        event.AltDown.return_value = False
        event.ShiftDown.return_value = False
        event.GetKeyCode.return_value = wx.WXK_DOWN
        MainFrame.on_category_notebook_key(frame, event)
        choice.SetSelection.assert_called_with(6)
        notice.assert_called_with("تم الانتقال إلى التصنيفات المخصصة.")

        event.GetKeyCode.return_value = wx.WXK_UP
        MainFrame.on_category_notebook_key(frame, event)
        choice.SetSelection.assert_called_with(0)
        notice.assert_called_with("تم الانتقال إلى تصنيفات البرنامج.")

    def test_category_dialog_exposes_create_and_management_controls(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        dialog = CustomCategoryDialog(parent, Account(id="a"), Mock(), Mock())
        try:
            self.assertTrue(dialog.create_button.IsEnabled())
            self.assertFalse(dialog.rename_button.IsEnabled())
            self.assertFalse(dialog.delete_button.IsEnabled())
        finally:
            dialog._closed = True
            dialog.Destroy()

    def test_category_refresh_adds_local_category_to_mail_sections(self) -> None:
        account = Account(id="account-a")
        store = Mock()
        store.list_categories.return_value = [CustomCategory("local-1", "العمل")]
        pages = {
            key: SimpleNamespace(
                filter_choices=["كل الرسائل", "المميزة بنجمة"], filter_choice=Mock(),
                selected_filter_key=lambda: "all",
            )
            for key in ("inbox", "spam", "sent", "all", "folders", "section:local-2")
        }
        frame = SimpleNamespace(
            selected_account=lambda: account,
            _visible_category_ids=[],
            folder_store=lambda: store,
            pages=pages,
            load_selected_custom_category=Mock(),
            refresh_section_folder_choices=Mock(),
        )
        MainFrame.refresh_custom_categories(frame)
        store.list_categories.assert_called_once_with("account-a")
        self.assertEqual(frame._visible_category_ids, ["local-1"])
        for page in pages.values():
            self.assertEqual(page.local_category_ids, ["local-1"])
            self.assertEqual(page.base_filter_count, 2)
            self.assertEqual(page.filter_choice.Set.call_args.args[0][-1], "العمل")
        frame.load_selected_custom_category.assert_called_once()

    def test_imap_modified_utf7_round_trip(self) -> None:
        for name in ("رسائل العمل", "A & B", "日本語", "English"):
            with self.subTest(name=name):
                self.assertEqual(decode_imap_mailbox(encode_imap_mailbox(name)), name)
        self.assertEqual(encode_imap_mailbox("A & B"), "A &- B")

    def test_gmail_lists_only_user_labels_and_preserves_ids(self) -> None:
        service = GmailApiService(cache=Mock())
        service._request_json = Mock(return_value={"labels": [
            {"id": "INBOX", "name": "Inbox", "type": "system"},
            {"id": "Label_42", "name": "رسائل العمل", "type": "user"},
        ]})
        account = Account(id="a")
        categories = service.list_custom_categories(account)
        self.assertEqual([(item.id, item.name) for item in categories], [("Label_42", "رسائل العمل")])
        self.assertEqual(service.mailbox_to_label(categories[0].id), "Label_42")
        service.rename_custom_category(account, "Label_42", "العمل")
        self.assertEqual(service._request_json.call_args.args[1], "PATCH")
        with self.assertRaises(MailError):
            service.delete_custom_category(account, "INBOX")

    def test_gmail_create_and_delete(self) -> None:
        service = GmailApiService(cache=Mock())
        service._request_json = Mock(side_effect=[
            {"id": "Label_42"},
            {"labels": [{"id": "Label_42", "name": "العمل", "type": "user"}]},
            {},
        ])
        account = Account(id="a")
        created = service.create_custom_category(account, " العمل ")
        self.assertEqual((created.id, created.name), ("Label_42", "العمل"))
        self.assertEqual(service._request_json.call_args_list[0].args[3]["name"], "العمل")
        service.delete_custom_category(account, created.id)
        self.assertEqual(service._request_json.call_args.args[1], "DELETE")

    def test_imap_list_filters_system_and_create_quotes_arabic(self) -> None:
        service = EmailService(cache=Mock())
        conn = Mock()
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        conn.create.return_value = ("OK", [b"done"])
        service._imap = Mock(return_value=conn)
        service.list_mailboxes = Mock(return_value=[
            MailboxInfo("INBOX", ("\\Inbox",)),
            MailboxInfo("[Gmail]/All Mail", ("\\All",)),
            MailboxInfo(encode_imap_mailbox("العمل"), ("\\HasNoChildren",)),
        ])
        account = Account(id="a")
        self.assertEqual([item.name for item in service.list_custom_categories(account)], ["العمل"])
        created = service.create_custom_category(account, "العمل")
        self.assertEqual(created.name, "العمل")
        conn.create.assert_called_with('"' + encode_imap_mailbox("العمل") + '"')

    def test_imap_delete_refuses_nonempty_category(self) -> None:
        service = EmailService(cache=Mock())
        account = Account(id="a")
        service.list_custom_categories = Mock(return_value=[
            type("Category", (), {"id": "Work"})(),
        ])
        conn = Mock()
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        service._imap = Mock(return_value=conn)
        service._select = Mock(return_value=2)
        with self.assertRaises(MailError):
            service.delete_custom_category(account, "Work")
        conn.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
