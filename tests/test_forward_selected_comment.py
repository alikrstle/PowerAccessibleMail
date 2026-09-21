import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wx

from accessible_mail.dialogs import ComposeDialog
from accessible_mail.main_frame import MainFrame
from accessible_mail.models import MessageSummary


class SelectedForwardTests(unittest.TestCase):
    def test_only_context_message_is_passed_to_recipient_dialog(self):
        summary = MessageSummary(uid="selected", mailbox="INBOX", subject="Selected")
        page = Mock()
        page.selected_summary.return_value = summary
        account = object()
        frame = SimpleNamespace(selected_account=lambda: account, current_page=lambda: page,
                                prepare_forward_message=Mock(), received_messages_for_forwarding=Mock())
        with patch("accessible_mail.main_frame.load_address_book", return_value=[]), \
                patch("accessible_mail.main_frame.ForwardMessageDialog") as factory:
            factory.return_value.ShowModal.return_value = wx.ID_OK
            factory.return_value.recipient_email.return_value = "test@example.invalid"
            factory.return_value.selected_message.return_value = summary
            MainFrame.on_forward_message(frame)
            self.assertEqual(factory.call_args.args[2], [summary])
        frame.received_messages_for_forwarding.assert_not_called()
        frame.prepare_forward_message.assert_called_once_with(account, "test@example.invalid", summary)

    def test_comment_is_optional_and_not_duplicated(self):
        obj = SimpleNamespace(to_address=Mock(), subject=Mock(), body=Mock(), forward_comment=Mock(), attachment_paths=[])
        obj.body.GetValue.return_value = "Original content"
        obj.forward_comment.GetValue.return_value = "My comment"
        self.assertEqual(ComposeDialog.values(obj)[2], "My comment\n\nOriginal content")
        self.assertEqual(ComposeDialog.values(obj)[2], "My comment\n\nOriginal content")
        obj.forward_comment.GetValue.return_value = "  "
        self.assertEqual(ComposeDialog.values(obj)[2], "Original content")
        obj.forward_comment = None
        self.assertEqual(ComposeDialog.values(obj)[2], "Original content")

    def test_no_selection_does_not_offer_unrelated_messages(self):
        page = Mock()
        page.selected_summary.return_value = None
        frame = SimpleNamespace(selected_account=lambda: object(), current_page=lambda: page)
        with patch("accessible_mail.main_frame.wx.MessageBox"), \
                patch("accessible_mail.main_frame.ForwardMessageDialog") as factory:
            MainFrame.on_forward_message(frame)
        factory.assert_not_called()
