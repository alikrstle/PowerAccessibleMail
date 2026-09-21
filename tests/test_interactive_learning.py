import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail.interactive_learning import InteractiveLearning, LESSONS, IDEAS, advance_step, INTRODUCTION, task_description, completion_message
from accessible_mail.interactive_learning import MESSAGE_ACTIONS, PAIR_FIELDS, pair_completed, initial_message_state, apply_message_action


class LearningTests(unittest.TestCase):
    def test_previous_end_resumes_at_first_new_lesson(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "progress.json"
            states = {lesson[2]: "completed" for lesson in LESSONS[:16]}
            path.write_text(json.dumps({"version": 2, "current": "end", "states": states}), encoding="utf-8")
            obj = SimpleNamespace(progress_path=path, task_states={})
            self.assertEqual(InteractiveLearning.load_progress(obj), 16)
            self.assertEqual(obj.task_states, states)

    def test_old_combined_contact_progress_migrates_to_split_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "progress.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "current": "practice_attachments",
                        "states": {"practice_contacts": "completed"},
                    }
                ),
                encoding="utf-8",
            )
            obj = SimpleNamespace(progress_path=path, task_states={})
            step = InteractiveLearning.load_progress(obj)
            self.assertEqual(LESSONS[step][2], "practice_viewers")
            self.assertEqual(
                obj.task_states["practice_contacts_edit_use"], "completed"
            )

    def test_old_combined_compose_address_progress_migrates_to_split_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "progress.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "current": "practice_compose_address_book",
                        "states": {"practice_compose_address_book": "completed"},
                    }
                ),
                encoding="utf-8",
            )
            obj = SimpleNamespace(progress_path=path, task_states={})
            step = InteractiveLearning.load_progress(obj)
            self.assertEqual(LESSONS[step][2], "practice_compose_address_add")
            self.assertEqual(
                obj.task_states["practice_compose_address_add"], "completed"
            )
            self.assertEqual(
                obj.task_states["practice_compose_address_pick"], "completed"
            )

    def test_removed_tasks_resume_at_next_remaining_task(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "progress.json"
            obj = SimpleNamespace(progress_path=path, task_states={})
            for old, replacement in (("filter_all", "search_shortcut"), ("search_empty", "search_exit"),
                                     ("compose_send", "message_actions"), ("compose_cancel", "message_actions"),
                                     ("delete_cancel", "message_actions"), ("delete_confirm", "message_actions")):
                path.write_text(json.dumps({"version": 2, "current": old,
                    "states": {old: "completed", "read_pair": "completed"}}), encoding="utf-8")
                step = InteractiveLearning.load_progress(obj)
                self.assertEqual(LESSONS[step][2], replacement)
                self.assertEqual(obj.task_states, {"read_pair": "completed"})

    def test_organization_tasks_require_actual_state_change(self):
        for action, (field, expected) in MESSAGE_ACTIONS.items():
            state = initial_message_state(action)
            self.assertNotEqual(state[field], expected)
            self.assertTrue(apply_message_action(state, action))
            self.assertEqual(state[field], expected)
            self.assertFalse(apply_message_action(state, action))

    def test_pairs_require_both_messages_not_one(self):
        for action, field in PAIR_FIELDS.items():
            states = [initial_message_state(""), initial_message_state("")]
            states[1][field] = True
            self.assertFalse(pair_completed(states, action))
            states[0][field] = True
            self.assertFalse(pair_completed(states, action))
            states[1][field] = False
            self.assertTrue(pair_completed(states, action))

    def test_filter_cannot_complete_before_navigation(self):
        step = next(i for i, lesson in enumerate(LESSONS) if lesson[2] == "filter_types")
        obj = SimpleNamespace(step=step, filter_stage="list", task_states={},
                              refresh=Mock(), save_progress=Mock(), show_completion=Mock())
        InteractiveLearning.record(obj, "filter_types")
        self.assertEqual(obj.step, step)
        obj.filter_stage = "viewer"
        InteractiveLearning.record(obj, "filter_types")
        self.assertEqual(obj.step, step)
        obj.filter_stage = "elements"
        InteractiveLearning.record(obj, "filter_types")
        self.assertEqual(obj.step, step + 1)

    def test_old_pair_progress_is_merged_conservatively(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "progress.json"
            obj = SimpleNamespace(progress_path=path, task_states={})
            path.write_text(json.dumps({"version": 2, "current": "unstar", "states": {
                "star": "completed", "unstar": "completed", "read": "completed"}}), encoding="utf-8")
            step = InteractiveLearning.load_progress(obj)
            self.assertEqual(LESSONS[step][2], "star_pair")
            self.assertEqual(obj.task_states.get("star_pair"), "completed")
            self.assertNotIn("read_pair", obj.task_states)

    def test_message_actions_do_not_affect_other_properties(self):
        state = initial_message_state("archive")
        before = dict(state)
        self.assertTrue(apply_message_action(state, "archive"))
        self.assertTrue(state["archived"])
        for key in ("read", "starred", "pinned"):
            self.assertEqual(state[key], before[key])
        self.assertTrue(apply_message_action(state, "restore"))
        self.assertEqual(state, before)
        self.assertFalse(apply_message_action(state, "unknown"))

    def test_only_expected_action_advances(self):
        for index, lesson in enumerate(LESSONS):
            self.assertEqual(advance_step(index, lesson[2]), index + 1)
            self.assertEqual(advance_step(index, "unrelated"), index)

    def test_training_completion_only_after_last_lesson(self):
        for step in range(1, len(LESSONS)):
            self.assertNotIn("أكملت التدريب", completion_message(step))
        self.assertIn("أكملت التدريب", completion_message(len(LESSONS)))

    def test_empty_reply_does_not_complete_task(self):
        obj = SimpleNamespace(step=3, reply_text=Mock(), reply_to=Mock(), reply_subject=Mock(), record=Mock())
        obj.reply_text.GetValue.return_value = "  \n"
        with patch("accessible_mail.interactive_learning.wx.MessageBox"):
            InteractiveLearning.finish_reply_training(obj)
        obj.record.assert_not_called()
        obj.reply_text.SetFocus.assert_called_once()
        obj.reply_text.GetValue.return_value = "شكرا على الرسالة"
        InteractiveLearning.finish_reply_training(obj)
        obj.record.assert_called_once_with("reply_complete")

    def test_reply_action_outside_its_task_does_not_count(self):
        obj = SimpleNamespace(step=0, reply_text=Mock(), record=Mock())
        InteractiveLearning.finish_reply_training(obj)
        obj.record.assert_not_called()

    def test_progress_round_trip_and_invalid_data(self):
        with tempfile.TemporaryDirectory() as folder:
            obj = SimpleNamespace(progress_path=Path(folder) / "progress.json", step=2, status=Mock())
            self.assertEqual(InteractiveLearning.load_progress(obj), 0)
            self.assertTrue(InteractiveLearning.save_progress(obj))
            self.assertEqual(InteractiveLearning.load_progress(obj), 2)
            for value in ({"version": 1, "step": 999}, {"version": 1, "step": True}, [], None):
                obj.progress_path.write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual(InteractiveLearning.load_progress(obj), 0)

    def test_record_does_not_advance_on_wrong_action(self):
        obj = SimpleNamespace(step=0, refresh=Mock(), save_progress=Mock(), explain=Mock(), status=Mock(), show_completion=Mock())
        InteractiveLearning.record(obj, "return")
        self.assertEqual(obj.step, 0)
        obj.save_progress.assert_not_called()
        InteractiveLearning.record(obj, "open_elements")
        self.assertEqual(obj.step, 1)
        obj.save_progress.assert_called_once()
        obj.show_completion.assert_called_once()

    def test_intro_only_contains_safety_notice(self):
        self.assertIn("تدريب آمن:", INTRODUCTION)
        for step in range(len(LESSONS)):
            text = task_description(step)
            self.assertTrue(text.startswith("\nالمهمة"))
            self.assertNotIn("تدريب آمن:", text)
            self.assertIn(str(step + 1), text)
            self.assertLess(text.index("فكرة المهمة:"), text.index("المطلوب:"))

    def test_revised_task_two_six_and_eight_wording(self):
        self.assertIn("وبعد ذلك، قف على المرفق", LESSONS[1][1])
        self.assertIn("صندوق التصنيفات", LESSONS[5][1])
        self.assertNotIn("قسم", LESSONS[5][1])
        self.assertIn("تصنيف الرسائل المميزة بنجمة", IDEAS[5])
        self.assertIn("صندوق التصنيفات", LESSONS[7][1])
        self.assertNotIn("قسم", LESSONS[7][1])
        self.assertIn("عكس خاصية الحذف", IDEAS[7])

    def test_skip_does_not_go_past_end(self):
        obj = SimpleNamespace(step=len(LESSONS), refresh=Mock(), save_progress=Mock(), explain=Mock())
        InteractiveLearning.skip(obj)
        self.assertEqual(obj.step, len(LESSONS))

    def test_skip_is_not_completion_and_preserves_previous_success(self):
        obj = SimpleNamespace(step=0, task_states={}, refresh=Mock(), save_progress=Mock(), explain=Mock())
        InteractiveLearning.skip(obj)
        self.assertEqual(obj.task_states["open_elements"], "skipped")
        obj.step = 0
        obj.task_states["open_elements"] = "completed"
        InteractiveLearning.skip(obj)
        self.assertEqual(obj.task_states["open_elements"], "completed")

    def test_stable_task_ids_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            obj = SimpleNamespace(progress_path=Path(folder) / "progress.json", step=3,
                                  task_states={"open_elements": "completed", "return": "skipped"}, status=Mock())
            self.assertTrue(InteractiveLearning.save_progress(obj))
            loaded = SimpleNamespace(progress_path=obj.progress_path, task_states={})
            self.assertEqual(InteractiveLearning.load_progress(loaded), 3)
            self.assertEqual(loaded.task_states, obj.task_states)
            obj.progress_path.write_text(json.dumps({"version": 1, "step": 2}), encoding="utf-8")
            loaded.task_states = {}
            self.assertEqual(InteractiveLearning.load_progress(loaded), 2)
            self.assertEqual(loaded.task_states, {})

    def test_previous_does_not_change_task_states(self):
        obj = SimpleNamespace(step=2, go_to_task=Mock())
        InteractiveLearning.previous(obj)
        obj.go_to_task.assert_called_once_with(1)
