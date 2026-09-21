import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wx

from accessible_mail.interactive_learning import InteractiveLearning, LESSONS, IDEAS, task_description
from accessible_mail.learning_exercises import PracticeExercises


class RevisedTasksTests(unittest.TestCase):
    def test_forward_accepts_each_sample_recipient_only(self):
        from accessible_mail.learning_exercises import FORWARD_RECIPIENTS
        self.assertEqual(len(FORWARD_RECIPIENTS), 3)
        self.assertNotIn("omar@example.invalid", {email for email, _ in FORWARD_RECIPIENTS})
        for recipient in [email for email, _ in FORWARD_RECIPIENTS] + ["person@gmail.com"]:
            obj = Mock(generation=1, pending=False)
            obj.IsBeingDeleted.return_value = False
            obj.IsShownOnScreen.return_value = True
            with patch("accessible_mail.address_book_dialog.ForwardMessageDialog") as factory, \
                    patch("accessible_mail.dialogs.ComposeDialog") as preview, \
                    patch("accessible_mail.learning_exercises.wx.MessageBox"):
                factory.return_value.ShowModal.return_value = wx.ID_OK
                factory.return_value.recipient_email.return_value = recipient
                factory.return_value.selected_message.return_value = object()
                preview.return_value.ShowModal.return_value = wx.ID_OK
                preview.return_value.values.return_value = (recipient, "subject", "body", [])
                PracticeExercises.forward_training(obj, 1)
                entries = factory.call_args.args[1]
                self.assertEqual([entry.email for entry in entries], [email for email, _ in FORWARD_RECIPIENTS])
            self.assertEqual(obj.finish.called, recipient != "person@gmail.com")

    def test_attachment_save_completes_after_copy_without_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            obj = Mock(step=1, _completion_pending=False, element_actions={"copy"})
            obj.IsBeingDeleted.return_value = False
            obj.IsShown.return_value = True
            with patch("accessible_mail.interactive_learning.wx.FileDialog") as factory, \
                    patch("accessible_mail.interactive_learning.wx.MessageBox"):
                factory.return_value.ShowModal.return_value = wx.ID_OK
                factory.return_value.GetPath.return_value = str(Path(folder) / "training.txt")
                InteractiveLearning.apply_element_action(obj, 1, 1)
            obj.record.assert_called_once_with("return")
            obj.messages.SetFocus.assert_called_once()

    def test_copy_completes_when_attachment_already_saved(self):
        obj = Mock(step=1, _completion_pending=False, element_actions={"save"})
        obj.IsBeingDeleted.return_value = False
        obj.IsShown.return_value = True
        with patch("accessible_mail.interactive_learning.wx.TheClipboard") as clipboard, \
                patch("accessible_mail.interactive_learning.wx.TextDataObject"):
            clipboard.Open.return_value = True
            clipboard.SetData.return_value = True
            InteractiveLearning.apply_element_action(obj, 0, 1)
        obj.record.assert_called_once_with("return")

    def test_completion_clears_and_hides_old_task_hint(self):
        obj = Mock(step=1, task_states={}, card_timer=None)
        with patch("accessible_mail.interactive_learning.wx.CallLater"):
            InteractiveLearning.show_completion(obj)
        obj.status.SetLabel.assert_called_once_with("")
        obj.status.Hide.assert_called_once()

    def test_filter_task_requires_all_three_types(self):
        obj = SimpleNamespace(action="filter_types", kinds=("all", "links", "attachments", "images"),
                              filter=Mock(), results=Mock(), visited_filters=set(), finish=Mock(),
                              GetParent=lambda: SimpleNamespace(filter_stage="elements"))
        for index in (1, 2, 1):
            obj.filter.GetSelection.return_value = index
            PracticeExercises.on_filter(obj, None)
        obj.finish.assert_not_called()
        obj.filter.GetSelection.return_value = 3
        PracticeExercises.on_filter(obj, None)
        obj.finish.assert_called_once()

    def test_forward_requires_selection_and_final_confirmation(self):
        for selected, confirmed in ((wx.ID_CANCEL, wx.ID_OK), (wx.ID_OK, wx.ID_CANCEL), (wx.ID_OK, wx.ID_OK)):
            obj = Mock(generation=1, pending=False)
            obj.IsBeingDeleted.return_value = False
            obj.IsShownOnScreen.return_value = True
            with patch("accessible_mail.address_book_dialog.ForwardMessageDialog") as factory, \
                    patch("accessible_mail.dialogs.ComposeDialog") as preview:
                factory.return_value.ShowModal.return_value = selected
                factory.return_value.recipient_email.return_value = "learner@example.invalid"
                factory.return_value.selected_message.return_value = object()
                preview.return_value.ShowModal.return_value = confirmed
                preview.return_value.values.return_value = ("learner@example.invalid", "subject", "body", [])
                PracticeExercises.forward_training(obj, 1)
                factory.return_value.Destroy.assert_called_once()
            self.assertEqual(obj.finish.called, selected == confirmed == wx.ID_OK)

    def test_numbering_and_search_notes_at_end(self):
        self.assertEqual(LESSONS[8][2], "forward")
        self.assertEqual(LESSONS[9][2], "filter_types")
        for index in (10, 11, 12):
            instruction = LESSONS[index][1]
            self.assertIn("إعدادات البرنامج", instruction.split("\n\n")[-1])
        self.assertIn("للخروج من أوضاع البحث والنتائج", LESSONS[13][1])

    def test_picker_selection_does_not_focus_explanation(self):
        obj = SimpleNamespace(task_picker=Mock(), refresh=Mock(), save_progress=Mock(), explain=Mock())
        obj.task_picker.GetSelection.return_value = 5
        InteractiveLearning.choose_task(obj)
        self.assertEqual(obj.step, 5)
        obj.task_picker.SetFocus.assert_called_once()
        obj.explain.assert_not_called()

    def test_save_training_attachment_and_cancel(self):
        for answer in (wx.ID_OK, wx.ID_CANCEL):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "attachment.txt"
                obj = Mock(step=1, _completion_pending=False, element_actions=set())
                obj.IsBeingDeleted.return_value = False
                obj.IsShown.return_value = True
                with patch("accessible_mail.interactive_learning.wx.FileDialog") as factory, \
                        patch("accessible_mail.interactive_learning.wx.MessageBox"):
                    factory.return_value.ShowModal.return_value = answer
                    factory.return_value.GetPath.return_value = str(path)
                    InteractiveLearning.apply_element_action(obj, 1, 1)
                    factory.return_value.Destroy.assert_called_once()
                self.assertEqual(path.exists(), answer == wx.ID_OK)
                self.assertEqual("save" in obj.element_actions, answer == wx.ID_OK)
                self.assertFalse(obj._child_dialog_open)
                if path.exists():
                    self.assertIn("training attachment", path.read_text(encoding="utf-8"))

    def test_child_dialog_escape_is_not_handled_by_guide(self):
        obj = SimpleNamespace(_child_dialog_open=True)
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_ESCAPE
        with patch("accessible_mail.interactive_learning.wx.Window.FindFocus", return_value=None):
            InteractiveLearning.on_key(obj, event)
        event.Skip.assert_called_once()

    def test_reply_menu_focuses_recipient(self):
        obj = Mock(step=3, _completion_pending=False)
        obj.IsBeingDeleted.return_value = False
        obj.IsShown.return_value = True
        InteractiveLearning.finish_context_action(obj, "reply_open", 3)
        obj.reply_to.SetFocus.assert_called_once()
        obj.record.assert_not_called()

    def test_second_starred_message_initially_hidden_from_all_categories(self):
        obj = SimpleNamespace(practice_mailbox=Mock(), practice_messages=[
            {"starred": False, "archived": False, "read": False, "pinned": False},
            {"starred": True, "archived": False, "read": False, "pinned": False, "starred_only": True}],
            selected_practice_id=0, messages=Mock(), select_practice_message=Mock())
        obj.practice_mailbox.GetSelection.return_value = 0
        InteractiveLearning.update_practice_messages(obj)
        self.assertEqual(obj.visible_practice_ids, [0])
        obj.practice_mailbox.GetSelection.return_value = 2
        InteractiveLearning.update_practice_messages(obj)
        self.assertEqual(obj.visible_practice_ids, [1])
    def test_descriptions_and_ids(self):
        self.assertEqual(len(LESSONS), len(IDEAS))
        ids = {item[2] for item in LESSONS}
        self.assertTrue({"open_elements", "archive_roundtrip", "search_shortcut", "search_button", "search_field"} <= ids)
        self.assertFalse({"open", "elements", "archive", "restore", "filter_images", "search_match"} & ids)
        self.assertIn("إجراءات أكثر", task_description(len(LESSONS)))
        self.assertIn("بدء التدريب من جديد", task_description(len(LESSONS)))
        self.assertIn("النتائج تم فرزها مسبقاً", next(item[1] for item in LESSONS if item[2] == "search_exit"))

    def test_search_escape_only_completes_in_query(self):
        obj = SimpleNamespace(query=Mock(), results=Mock(), finish=Mock())
        with patch("accessible_mail.learning_exercises.wx.MessageBox") as message:
            PracticeExercises.handle_search_escape(obj, obj.results)
            message.assert_called_once()
        obj.finish.assert_not_called()
        PracticeExercises.handle_search_escape(obj, obj.query)
        obj.finish.assert_called_once()
        obj.query.ChangeValue.assert_called_once_with("")

    def test_search_shortcut_requires_reveal_before_completion(self):
        obj = SimpleNamespace(action="search_shortcut", search_revealed=False, query=Mock(), results=Mock(), notice=Mock(), finish=Mock())
        obj.query.GetValue.return_value = "اجتماع"
        PracticeExercises.on_search(obj, None)
        obj.finish.assert_not_called()
        obj.search_revealed = True
        PracticeExercises.on_search(obj, None)
        obj.finish.assert_called_once()

    def test_search_button_requires_requested_filters(self):
        obj = SimpleNamespace(action="search_button", search_revealed=True, query=Mock(), results=Mock(), notice=Mock(),
                              sender_filter=Mock(), date_filter=Mock(), finish=Mock())
        obj.query.GetValue.return_value = "اجتماع"
        obj.sender_filter.GetValue.return_value = ""
        obj.date_filter.GetSelection.return_value = 0
        PracticeExercises.on_search(obj, None)
        obj.finish.assert_not_called()
        obj.sender_filter.GetValue.return_value = "فريق"
        obj.date_filter.GetSelection.return_value = 2
        PracticeExercises.on_search(obj, None)
        obj.finish.assert_called_once()

    def test_quote_alone_is_not_a_reply(self):
        obj = SimpleNamespace(step=next(i for i, item in enumerate(LESSONS) if item[2] == "reply_complete"),
                              reply_quote="quoted original", reply_text=Mock(), record=Mock())
        obj.reply_text.GetValue.return_value = "quoted original"
        with patch("accessible_mail.interactive_learning.wx.MessageBox"):
            InteractiveLearning.finish_reply_training(obj)
        obj.record.assert_not_called()

    def test_starred_view_filters_and_completes_only_final_pair(self):
        obj = SimpleNamespace(practice_mailbox=Mock(), practice_messages=[
            {"starred": True, "archived": False, "read": False, "pinned": False},
            {"starred": False, "archived": False, "read": False, "pinned": False}],
            selected_practice_id=0, messages=Mock(), select_practice_message=Mock(), record=Mock(),
            step=next(i for i, item in enumerate(LESSONS) if item[2] == "star_pair"))
        obj.practice_mailbox.GetSelection.return_value = 2
        InteractiveLearning.update_practice_messages(obj, object())
        self.assertEqual(obj.visible_practice_ids, [0])
        self.assertTrue(obj.starred_view_visited)
        obj.record.assert_called_once_with("star_pair")

    def test_archive_roundtrip_requires_return_to_inbox(self):
        obj = SimpleNamespace(practice_mailbox=Mock(), practice_messages=[], messages=Mock(), record=Mock(),
                              archive_actions={"archive"}, step=next(i for i, item in enumerate(LESSONS) if item[2] == "archive_roundtrip"))
        obj.practice_mailbox.GetSelection.return_value = 0
        InteractiveLearning.update_practice_messages(obj, object())
        obj.record.assert_not_called()
        obj.archive_actions.add("restore")
        obj.practice_mailbox.GetSelection.return_value = 1
        InteractiveLearning.update_practice_messages(obj, object())
        obj.record.assert_not_called()
        obj.practice_mailbox.GetSelection.return_value = 0
        InteractiveLearning.update_practice_messages(obj, object())
        obj.record.assert_called_once_with("archive_roundtrip")
