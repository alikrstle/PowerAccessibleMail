import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wx

from accessible_mail.learning_extended import ExtendedPractice, EXTENDED_LESSONS
from accessible_mail.interactive_learning import LESSONS
from accessible_mail.config import VIEWER_HTML, VIEWER_SIMPLE
from accessible_mail.models import MessageSummary
from accessible_mail.ui_constants import BULK_ACTION_MARK_READ


class ExtendedPracticeTests(unittest.TestCase):
    def test_nine_new_tasks_appended_without_renumbering_existing(self):
        self.assertEqual(len(EXTENDED_LESSONS), 9)
        self.assertEqual([lesson[2] for lesson in LESSONS[16:]], [lesson[2] for lesson in EXTENDED_LESSONS])
        self.assertEqual(LESSONS[8][2], "forward")
        self.assertEqual(LESSONS[18][2], "practice_contacts")
        self.assertEqual(LESSONS[19][2], "practice_contacts_edit_use")
        self.assertEqual(LESSONS[20][2], "practice_viewers")
        self.assertEqual(LESSONS[23][2], "practice_compose_address_add")
        self.assertEqual(LESSONS[24][2], "practice_compose_address_pick")
        self.assertIn("قائمة السياق على عنوان احمد", LESSONS[18][1])
        self.assertIn("قائمة السياق على عنوان أحمد المثبت", LESSONS[19][1])

    def test_sections_need_ahmad_and_all_sections_not_return_to_iris(self):
        obj = SimpleNamespace(done=set(), account=Mock(), section=Mock(), finish=Mock())
        obj.account.GetSelection.return_value = 1
        event = Mock()
        for index in range(4):
            obj.section.GetSelection.return_value = index
            ExtendedPractice.visit_section(obj, event)
        obj.finish.assert_not_called()
        obj.done.add(("account", 0))
        obj.account.GetSelection.return_value = 0
        for index in range(4):
            obj.section.GetSelection.return_value = index
            ExtendedPractice.visit_section(obj, event)
        obj.finish.assert_called_once()
        self.assertNotIn(("account", 1), obj.done)

    def test_switching_account_changes_visible_sample_sender(self):
        page = Mock()
        obj = SimpleNamespace(account=Mock(), section=Mock(), message_lists=[page], done=set())
        obj.section.GetSelection.return_value = 0
        event = Mock()
        event.GetEventObject.return_value = obj.account
        obj.account.GetSelection.return_value = 0
        ExtendedPractice.switch_section(obj, event)
        first = page.set_messages.call_args.args[0]
        obj.account.GetSelection.return_value = 1
        ExtendedPractice.switch_section(obj, event)
        second = page.set_messages.call_args.args[0]
        self.assertNotEqual(first[0].sender, second[0].sender)
        self.assertEqual(second[0].sender, "Iris")
        self.assertIsInstance(second[0], MessageSummary)
        self.assertEqual(obj.done, {("account", 0), ("account", 1)})

    def test_multiple_selection_requires_select_then_deselect(self):
        first = MessageSummary(uid="1", mailbox="training")
        second = MessageSummary(uid="2", mailbox="training")
        page = SimpleNamespace(
            multi_select_mode=True,
            selected_summaries=Mock(return_value=[first]),
            update_message_flags_bulk=Mock(),
        )
        obj = SimpleNamespace(done=set(), hint=Mock())
        ExtendedPractice.selection_changed(obj, page)
        ExtendedPractice.apply_training_bulk_action(
            obj, page, BULK_ACTION_MARK_READ, [first]
        )
        page.update_message_flags_bulk.assert_not_called()
        page.selected_summaries.return_value = [first, second]
        ExtendedPractice.selection_changed(obj, page)
        page.selected_summaries.return_value = [first]
        ExtendedPractice.selection_changed(obj, page)
        ExtendedPractice.apply_training_bulk_action(
            obj, page, BULK_ACTION_MARK_READ, [first]
        )
        self.assertIn("applied", obj.done)
        self.assertTrue(first.is_read)
        page.update_message_flags_bulk.assert_called_once_with([first])

    def test_escape_only_finishes_multi_after_action(self):
        for applied in (False, True):
            obj = SimpleNamespace(
                done={"applied"} if applied else set(), finish=Mock()
            )
            ExtendedPractice.selection_mode_exited(obj, Mock())
            self.assertEqual(obj.finish.called, applied)

    def test_contact_edit_task_cannot_use_address_before_editing(self):
        obj = SimpleNamespace(
            action="practice_contacts_edit_use",
            done={"added"},
            pinned=True,
            hint=Mock(),
        )
        ExtendedPractice.use_contact(obj)
        obj.hint.assert_called_once()

    def test_pin_toggles_only_training_contact(self):
        obj = SimpleNamespace(
            action="practice_contacts",
            pinned=False,
            contacts=Mock(),
            contact_name="أحمد",
            done={"added"},
            finish=Mock(),
        )
        ExtendedPractice.pin_contact(obj)
        self.assertTrue(obj.pinned)
        self.assertIn("ahmad@example.invalid", obj.contacts.SetString.call_args.args[1])
        obj.finish.assert_called_once()
        ExtendedPractice.pin_contact(obj)
        self.assertFalse(obj.pinned)

    def test_attachment_add_cancel_does_not_count(self):
        obj = SimpleNamespace(done=set(), attached=[], update_files=Mock())
        with patch("accessible_mail.learning_extended.wx.SingleChoiceDialog") as factory:
            factory.return_value.ShowModal.return_value = wx.ID_CANCEL
            ExtendedPractice.add_attachment(obj)
        self.assertEqual(obj.attached, [])
        self.assertEqual(obj.done, set())

    def test_attachment_review_requires_both_additions_and_correct_removal(self):
        obj = SimpleNamespace(done={0}, attached=[0], finish=Mock(), hint=Mock(), files=Mock(), update_files=Mock())
        ExtendedPractice.review_attachments(obj)
        obj.finish.assert_not_called()
        obj.done.add(1)
        obj.attached.append(1)
        obj.files.GetSelection.return_value = 1
        ExtendedPractice.remove_attachment(obj)
        self.assertEqual(obj.attached, [0])
        ExtendedPractice.review_attachments(obj)
        obj.finish.assert_called_once()

    def test_translation_requires_language_and_both_fields(self):
        obj = SimpleNamespace(subject=Mock(), body=Mock(), done=set(), language_added=False, hint=Mock(), finish=Mock())
        obj.subject.GetValue.return_value = "مرحبا"
        obj.body.GetValue.return_value = "شكرا"
        ExtendedPractice.translate_control(obj, obj.subject)
        obj.subject.ChangeValue.assert_not_called()
        obj.language_added = True
        ExtendedPractice.translate_control(obj, obj.subject)
        obj.subject.ChangeValue.assert_called_once_with("Hello")
        obj.finish.assert_not_called()
        ExtendedPractice.translate_control(obj, obj.body)
        obj.body.ChangeValue.assert_called_once_with("Thank you")
        obj.finish.assert_called_once()

    @patch(
        "accessible_mail.learning_extended.request_custom_address_name",
        return_value="سام",
    )
    def test_compose_address_book_saves_sam_as_third_entry(self, _request_name):
        obj = SimpleNamespace(
            action="practice_compose_address_add",
            sam_email="sam@example.invalid",
            compose_to=Mock(),
            compose_add_address=Mock(),
            compose_training_panel=Mock(),
            command_list=Mock(),
            done=set(),
            hint=Mock(),
            Layout=Mock(),
            finish=Mock(),
        )
        obj.compose_to.GetValue.return_value = "sam@example.invalid"
        ExtendedPractice.add_training_recipient(obj)
        self.assertEqual(
            [entry.name for entry in obj.training_entries],
            ["أحمد", "علي", "سام"],
        )
        self.assertEqual(obj.training_entries[2].email, "sam@example.invalid")
        self.assertIn("sam_saved", obj.done)
        obj.compose_training_panel.Hide.assert_called_once()
        obj.command_list.SetFocus.assert_called_once()
        obj.finish.assert_called_once()

    @patch("accessible_mail.learning_extended.AddressPickerDialog")
    def test_compose_address_book_selects_sam_into_recipient(self, picker_class):
        picker = picker_class.return_value
        picker.ShowModal.return_value = wx.ID_OK
        picker.selected_email.return_value = "sam@example.invalid"
        obj = SimpleNamespace(
            action="practice_compose_address_pick",
            sam_email="sam@example.invalid",
            training_entries=[
                SimpleNamespace(name="أحمد"),
                SimpleNamespace(name="علي"),
                SimpleNamespace(name="سام"),
            ],
            compose_to=Mock(),
            done=set(),
            hint=Mock(),
            finish=Mock(),
        )
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_DOWN, Skip=Mock())
        ExtendedPractice.on_compose_training_to_key(obj, event)
        obj.compose_to.SetValue.assert_called_once_with("sam@example.invalid")
        obj.compose_to.SetInsertionPointEnd.assert_called_once()
        obj.finish.assert_called_once()
        picker.Destroy.assert_called_once()

    def test_viewer_requires_simple_then_html_before_training_link(self):
        obj = SimpleNamespace(done=set(), finish=Mock())
        page = SimpleNamespace(viewer_mode=VIEWER_SIMPLE)
        ExtendedPractice.viewer_entered(obj, page, Mock())
        self.assertEqual(obj.done, set())
        obj.done.add("simple_configured")
        ExtendedPractice.viewer_entered(obj, page, Mock())
        self.assertIn("simple_opened", obj.done)
        self.assertNotIn("simple_read", obj.done)

        viewer = Mock()
        viewer.GetValue.return_value = "سطر أول\nسطر أخير"
        viewer.GetInsertionPoint.return_value = 4
        obj.viewer_page = SimpleNamespace(viewer_mode=VIEWER_SIMPLE, viewer=viewer)
        ExtendedPractice.update_simple_read_state(obj)
        self.assertNotIn("simple_read", obj.done)
        viewer.GetInsertionPoint.return_value = 8
        ExtendedPractice.update_simple_read_state(obj)
        self.assertIn("simple_read", obj.done)

        page.viewer_mode = VIEWER_HTML
        obj.done.add("html_configured")
        ExtendedPractice.viewer_entered(obj, page, Mock())
        self.assertIn("html_viewed", obj.done)
        ExtendedPractice.viewer_link_requested(
            obj, page, SimpleNamespace(url="https://unrelated.invalid/")
        )
        obj.finish.assert_not_called()
        ExtendedPractice.viewer_link_requested(
            obj, page, SimpleNamespace(url="https://example.invalid/training")
        )
        obj.finish.assert_called_once()

    def test_duplicate_finish_does_not_advance_twice(self):
        obj = SimpleNamespace(pending=False, completed=Mock())
        ExtendedPractice.finish(obj)
        ExtendedPractice.finish(obj)
        obj.completed.assert_called_once()
