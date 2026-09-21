import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wx

from accessible_mail.learning_exercises import EXERCISES, ITEMS, MAIL, filtered_items, search_mail, valid_draft, PracticeExercises
from accessible_mail.interactive_learning import LESSONS, advance_step


class ExtraLearningTests(unittest.TestCase):
    def test_command_list_only_opens_training_compose(self):
        from accessible_mail.command_labels import COMMAND_LABELS, COMPOSE_COMMAND_INDEX
        obj = SimpleNamespace(commands=Mock(), open_compose=Mock(), generation=7)
        with patch("accessible_mail.learning_exercises.wx.MessageBox"):
            for index in range(len(COMMAND_LABELS)):
                obj.commands.GetSelection.return_value = index
                PracticeExercises.on_commands(obj, None)
        obj.open_compose.assert_called_once_with(7)
        self.assertEqual(COMMAND_LABELS[COMPOSE_COMMAND_INDEX], "إنشاء بريد إلكتروني")

    def test_copy_before_compose_does_not_focus_hidden_address(self):
        obj = SimpleNamespace(compose_open=False, address=Mock(), copy_address_button=Mock())
        with patch("accessible_mail.learning_exercises.wx.TheClipboard") as clipboard, \
                patch("accessible_mail.learning_exercises.wx.TextDataObject") as data, \
                patch("accessible_mail.learning_exercises.wx.MessageBox"):
            clipboard.Open.return_value = True
            clipboard.SetData.return_value = True
            PracticeExercises.on_copy_address(obj, None)
            data.assert_called_once_with("learner@example.invalid")
            clipboard.Close.assert_called_once()
        obj.address.SetFocus.assert_not_called()
        obj.copy_address_button.SetFocus.assert_called_once()

    def test_compose_instructions_follow_commands_and_separate_address(self):
        instruction = next(item[1] for item in EXERCISES if item[2] == "compose_review")
        self.assertIn("تصفحها بالأسهم حتى إنشاء بريد إلكتروني", instruction)
        self.assertIn("\nlearner@example.invalid\n", instruction)

    def test_compose_cannot_complete_before_opening_from_commands(self):
        obj = SimpleNamespace(compose_open=False, finish=Mock())
        PracticeExercises.on_compose(obj, None)
        obj.finish.assert_not_called()

    def test_open_compose_reveals_fields_and_focuses_recipient(self):
        obj = Mock(generation=3, compose_controls=[Mock(), Mock()])
        obj.IsBeingDeleted.return_value = False
        obj.IsShownOnScreen.return_value = True
        PracticeExercises.open_compose(obj, 2)
        obj.address.SetFocus.assert_not_called()
        PracticeExercises.open_compose(obj, 3)
        obj.commands.Hide.assert_called_once()
        obj.address.SetFocus.assert_called_once()
        for control in obj.compose_controls:
            control.Show.assert_called_once()

    def test_seventeen_unique_exercises_registered(self):
        self.assertEqual(len(EXERCISES), 17)
        self.assertEqual(len(LESSONS), 25)
        self.assertEqual(len({lesson[2] for lesson in LESSONS}), 25)
        self.assertFalse({"compose_send", "compose_cancel", "delete_cancel", "delete_confirm"} & {lesson[2] for lesson in LESSONS})
        self.assertFalse({"filter_all", "search_empty"} & {lesson[2] for lesson in LESSONS})
        for _, _, action, _ in EXERCISES:
            step = next(i for i, lesson in enumerate(LESSONS) if lesson[2] == action)
            self.assertEqual(advance_step(step, action), step + 1)
            self.assertEqual(advance_step(step, "unrelated"), step)

    def test_filter_results_match_types(self):
        self.assertEqual(len(filtered_items("all")), 3)
        for kind, label in ITEMS:
            self.assertEqual(filtered_items(kind), [label])

    def test_search_result_and_reset(self):
        self.assertEqual(search_mail("اجتماع"), [MAIL[0]])
        self.assertEqual(search_mail("بركان"), [])
        self.assertEqual(search_mail(""), list(MAIL))

    def test_draft_rejects_missing_fields_and_real_address(self):
        self.assertTrue(valid_draft("learner@example.invalid", "subject", "body"))
        self.assertFalse(valid_draft("person@gmail.com", "subject", "body"))
        self.assertFalse(valid_draft("learner@example.invalid", " ", "body"))
        self.assertFalse(valid_draft("learner@example.invalid", "subject", ""))

    def test_search_success_requires_results_not_just_click(self):
        obj = SimpleNamespace(action="search_match", query=Mock(), results=Mock(), notice=Mock(), finish=Mock())
        obj.query.GetValue.return_value = ""
        PracticeExercises.on_search(obj, None)
        obj.finish.assert_not_called()
        obj.query.GetValue.return_value = "اجتماع"
        PracticeExercises.on_search(obj, None)
        obj.finish.assert_called_once()

    def test_delete_confirmation_controls_state_and_completion(self):
        for action in ("delete_confirm", "delete_cancel"):
            for answer in (wx.ID_OK, wx.ID_CANCEL):
                obj = SimpleNamespace(action=action, results=Mock(), notice=Mock(), finish=Mock())
                with patch("accessible_mail.learning_exercises.wx.MessageDialog") as factory:
                    factory.return_value.ShowModal.return_value = answer
                    PracticeExercises.on_delete(obj, None)
                    factory.return_value.Destroy.assert_called_once()
                self.assertEqual(obj.in_trash, answer == wx.ID_OK)
                self.assertEqual(obj.finish.called, (action == "delete_confirm") == (answer == wx.ID_OK))

    def test_duplicate_completion_is_not_queued(self):
        obj = SimpleNamespace(pending=False, action="filter_all", generation=2, deliver=Mock())
        with patch("accessible_mail.learning_exercises.wx.CallAfter") as after:
            PracticeExercises.finish(obj)
            PracticeExercises.finish(obj)
        after.assert_called_once_with(obj.deliver, "filter_all", 2)
