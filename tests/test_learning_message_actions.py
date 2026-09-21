import unittest
from unittest.mock import Mock, patch
import wx

from accessible_mail.learning_message_actions import MessageActionsPractice, ENGLISH_TEXT


class MessageActionTests(unittest.TestCase):
    def fixture(self):
        obj = Mock(done=set(), visible_ids=[0, 1, 2], pending=False, current_id=1)
        obj.IsBeingDeleted.return_value = False
        obj.IsShownOnScreen.return_value = True
        obj.viewer.IsShown.return_value = True
        return obj

    def test_all_three_required_and_completion_only_once(self):
        obj = self.fixture()
        with patch("accessible_mail.learning_message_actions.wx.MessageBox", return_value=wx.YES):
            MessageActionsPractice.apply_action(obj, "delete", 0)
        self.assertEqual(obj.visible_ids, [1, 2])
        obj.completed.assert_not_called()
        obj.current_id = 1
        with patch("accessible_mail.learning_message_actions.wx.SingleChoiceDialog") as factory:
            factory.return_value.ShowModal.return_value = wx.ID_OK
            MessageActionsPractice.apply_action(obj, "translate", 1)
            factory.return_value.Destroy.assert_called_once()
        obj.viewer.ChangeValue.assert_called_with(ENGLISH_TEXT)
        obj.completed.assert_not_called()
        obj.current_id = 2
        with patch("accessible_mail.learning_message_actions.wx.TheClipboard") as clipboard, \
                patch("accessible_mail.learning_message_actions.wx.TextDataObject"):
            clipboard.Open.return_value = True
            clipboard.SetData.return_value = True
            MessageActionsPractice.apply_action(obj, "copy", 2)
            clipboard.Close.assert_called_once()
        self.assertEqual(obj.done, {"delete", "copy", "translate"})
        obj.completed.assert_called_once()
        MessageActionsPractice.apply_action(obj, "copy", 2)
        obj.completed.assert_called_once()

    def test_cancel_delete_keeps_message(self):
        obj = self.fixture()
        with patch("accessible_mail.learning_message_actions.wx.MessageBox", return_value=wx.NO):
            MessageActionsPractice.apply_action(obj, "delete", 0)
        self.assertEqual(obj.visible_ids, [0, 1, 2])
        self.assertEqual(obj.done, set())

    def test_cancel_translation_does_not_count(self):
        obj = self.fixture()
        with patch("accessible_mail.learning_message_actions.wx.SingleChoiceDialog") as factory:
            factory.return_value.ShowModal.return_value = wx.ID_CANCEL
            MessageActionsPractice.apply_action(obj, "translate", 1)
        obj.viewer.ChangeValue.assert_not_called()
        self.assertEqual(obj.done, set())

    def test_failed_copy_does_not_count(self):
        obj = self.fixture()
        obj.current_id = 2
        with patch("accessible_mail.learning_message_actions.wx.TheClipboard") as clipboard, \
                patch("accessible_mail.learning_message_actions.wx.MessageBox"):
            clipboard.Open.return_value = False
            MessageActionsPractice.apply_action(obj, "copy", 2)
            clipboard.Close.assert_not_called()
        self.assertEqual(obj.done, set())

    def test_wrong_message_and_stale_viewer_do_not_count(self):
        obj = self.fixture()
        with patch("accessible_mail.learning_message_actions.wx.MessageBox"):
            MessageActionsPractice.apply_action(obj, "delete", 2)
        MessageActionsPractice.apply_action(obj, "copy", 2)
        self.assertEqual(obj.done, set())
        obj.completed.assert_not_called()

    def test_escape_returns_to_list(self):
        obj = self.fixture()
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_ESCAPE
        with patch("accessible_mail.learning_message_actions.wx.Window.FindFocus", return_value=obj.viewer):
            MessageActionsPractice.on_key(obj, event)
        obj.viewer.Hide.assert_called_once()
        obj.messages.SetFocus.assert_called_once()
        event.Skip.assert_not_called()
