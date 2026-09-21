import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wx
from accessible_mail.interactive_learning import InteractiveLearning


class CompletionNavigationTests(unittest.TestCase):
    def test_down_on_card_is_consumed_and_dismisses_it(self):
        card = object()
        obj = SimpleNamespace(step=0, completion_card=card, hide_completion=Mock())
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_DOWN, Skip=Mock())
        with patch("accessible_mail.interactive_learning.wx.Window.FindFocus", return_value=card):
            InteractiveLearning.on_key(obj, event)
        obj.hide_completion.assert_called_once()
        event.Skip.assert_not_called()

    def test_dismiss_focuses_explanation_not_picker(self):
        card = object()
        for focused in (card, object()):
            obj = SimpleNamespace(IsBeingDeleted=lambda: False, IsShown=lambda: True,
                                  completion_card=card, card_timer=Mock(), refresh=Mock(), explain=Mock())
            with patch("accessible_mail.interactive_learning.wx.Window.FindFocus", return_value=focused):
                InteractiveLearning.hide_completion(obj)
            obj.refresh.assert_called_once()
            self.assertEqual(obj.explain.called, focused is card)

    def test_space_dispatches_both_read_states(self):
        for read, expected in ((False, "read"), (True, "unread")):
            messages = SimpleNamespace(GetSelection=lambda: 0)
            obj = SimpleNamespace(completion_card=object(), messages=messages, step=5,
                                  practice_message={"read": read}, finish_context_action=Mock())
            event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_SPACE, Skip=Mock())
            with patch("accessible_mail.interactive_learning.wx.Window.FindFocus", return_value=messages):
                InteractiveLearning.on_key(obj, event)
            obj.finish_context_action.assert_called_once_with(expected, 5)
            event.Skip.assert_not_called()

    def test_record_defers_new_content_until_card_dismissal(self):
        obj = SimpleNamespace(step=0, task_states={}, refresh=Mock(), save_progress=Mock(), show_completion=Mock())
        InteractiveLearning.record(obj, "open_elements")
        self.assertEqual(obj.step, 1)
        self.assertTrue(obj._completion_pending)
        obj.refresh.assert_not_called()
        InteractiveLearning.record(obj, "elements")
        self.assertEqual(obj.step, 1)

    def test_close_finishes_pending_transition_and_clears_card(self):
        obj = SimpleNamespace(save_progress=lambda: True, _completion_pending=True,
                              refresh=Mock(), card_timer=Mock(), reply_text=Mock(),
                              completion_card=Mock(), Hide=Mock())
        InteractiveLearning.close(obj)
        obj.refresh.assert_called_once()
        obj.completion_card.SetLabel.assert_called_once_with("")
        obj.completion_card.SetName.assert_called_once_with("")
        obj.Hide.assert_called_once()
