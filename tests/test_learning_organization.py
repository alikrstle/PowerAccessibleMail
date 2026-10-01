from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import wx

from accessible_mail.interactive_learning import LESSONS
from accessible_mail.learning_organization import (
    ORGANIZATION_LESSONS, OrganizationPractice,
)
from accessible_mail.i18n import ENGLISH_TRANSLATIONS
from accessible_mail.ui_constants import (
    BULK_ACTION_MARK_READ, BULK_ACTION_PIN, BULK_ACTION_STAR,
)


class OrganizationPracticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = wx.App.Get() or wx.App(False)
        self.frame = wx.Frame(None)
        self.frame.CreateStatusBar()
        self.addCleanup(self.frame.Destroy)

    def practice(self, action: str) -> tuple[OrganizationPractice, Mock]:
        completed = Mock()
        panel = OrganizationPractice(self.frame, action, completed)
        self.addCleanup(panel.Destroy)
        return panel, completed

    def test_six_tasks_follow_existing_twenty_five(self) -> None:
        self.assertEqual(len(ORGANIZATION_LESSONS), 6)
        self.assertEqual(len(LESSONS), 31)
        self.assertEqual(
            [lesson[2] for lesson in LESSONS[25:]],
            [lesson[2] for lesson in ORGANIZATION_LESSONS],
        )
        for title, instruction, _action, idea in ORGANIZATION_LESSONS:
            self.assertIn(title, ENGLISH_TRANSLATIONS)
            self.assertIn(instruction, ENGLISH_TRANSLATIONS)
            self.assertIn(idea, ENGLISH_TRANSLATIONS)

    def test_every_training_panel_builds_without_real_account(self) -> None:
        for _title, _instruction, action, _idea in ORGANIZATION_LESSONS:
            with self.subTest(action=action):
                panel, _completed = self.practice(action)
                self.assertEqual(panel.action, action)
                self.assertFalse(panel.pending)

    def test_bulk_submenus_only_change_two_selected_messages(self) -> None:
        panel, completed = self.practice("organize_bulk_submenus")
        page = panel.page
        page.enter_multi_selection_mode()
        first_two = panel.messages[:2]
        for action in (BULK_ACTION_MARK_READ, BULK_ACTION_STAR, BULK_ACTION_PIN):
            panel.on_bulk_submenus(page, action, first_two)
        self.assertTrue(all(message.is_read and message.is_starred and message.is_pinned for message in first_two))
        self.assertFalse(panel.messages[2].is_read)
        self.assertFalse(panel.messages[2].is_starred)
        self.assertFalse(panel.messages[2].is_pinned)
        completed.assert_called_once()

    def test_folder_delete_keeps_messages(self) -> None:
        panel, completed = self.practice("organize_folder_management")
        panel.done.update({"rename", "pin", "star", "archive", "restore"})
        with patch("accessible_mail.learning_organization.wx.MessageBox", return_value=wx.YES):
            panel.manage_folder("delete")
        self.assertIsNone(panel.folder)
        self.assertEqual({message.uid for message in panel.page.messages}, {"1", "2", "3"})
        completed.assert_called_once()

    def test_archived_folder_moves_to_archive_filter(self) -> None:
        panel, _completed = self.practice("organize_folder_management")
        panel.manage_folder("archive")
        self.assertEqual(panel.page.folder_rows, [])
        panel.page.filter_choice.SetSelection(5)
        panel.page.apply_filter()
        self.assertEqual(len(panel.page.visible_messages), 1)
        self.assertEqual(panel.page.visible_messages[0].folder_id, "training-folder")
        panel.manage_folder("restore")
        panel.page.filter_choice.SetSelection(0)
        panel.page.apply_filter()
        self.assertEqual(len(panel.page.folder_rows), 1)

    def test_merged_folder_lesson_adds_outside_message_and_removes_it(self) -> None:
        panel, completed = self.practice("organize_folder_create")
        with patch.object(panel, "ask_name", return_value="مشروعي"):
            panel.on_folder_create_bulk(panel.page, "create_folder", panel.messages[:2])
        self.assertEqual(panel.folder_items, {"1", "2"})
        self.assertEqual(len(panel.page.messages), 1)
        self.assertFalse(hasattr(panel, "section_choice"))
        dialog = Mock()
        dialog.ShowModal.return_value = wx.ID_OK
        dialog.GetSelection.return_value = 0
        with patch("accessible_mail.learning_organization.choose_message_destination", return_value="folder"), patch(
            "accessible_mail.learning_organization.wx.SingleChoiceDialog", return_value=dialog
        ):
            panel.on_folder_create_bulk(panel.page, "add_to_folder", [panel.messages[2]])
        self.assertEqual(panel.page.messages, [])
        panel.open_folder("training-folder")
        self.assertEqual({message.uid for message in panel.page.messages}, {"1", "2", "3"})
        completed.assert_not_called()
        panel.on_folder_create_bulk(panel.page, "remove_from_folder", [panel.messages[2]])
        panel.leave_folder()
        self.assertEqual([message.uid for message in panel.page.messages], ["3"])
        completed.assert_called_once()

    def test_folder_membership_roundtrip_does_not_delete_message(self) -> None:
        panel, completed = self.practice("organize_folder_membership")
        dialog = Mock()
        dialog.ShowModal.return_value = wx.ID_OK
        dialog.GetSelection.return_value = 0
        with patch("accessible_mail.learning_organization.choose_message_destination", return_value="folder"), patch("accessible_mail.learning_organization.wx.SingleChoiceDialog", return_value=dialog):
            panel.on_folder_membership_action(panel.page, "add_to_folder", [panel.messages[1]])
        self.assertEqual(panel.folder_items, {"1", "2"})
        panel.open_folder("training-folder")
        panel.on_folder_membership_action(panel.page, "remove_from_folder", [panel.messages[1]])
        panel.leave_folder()
        self.assertEqual(panel.folder_items, {"1"})
        self.assertIn(panel.messages[1], panel.page.messages)
        completed.assert_called_once()

    def test_conversation_folder_selection_and_opening(self) -> None:
        panel, completed = self.practice("organize_conversation_folder")
        panel.start_conversation_selection()
        self.assertTrue(panel.contact_checks.IsShown())
        panel.contact_checks.CheckItem(0, True)
        panel.contact_checks.CheckItem(1, True)
        with patch.object(panel, "ask_name", return_value="الأصدقاء"):
            panel.create_conversation_folder()
        self.assertFalse(panel.contact_checks.IsShown())
        self.assertIn("الأصدقاء", panel.contact_list.GetString(0))
        self.assertEqual(panel.contact_list.GetCount(), 2)
        panel.contact_list.SetSelection(0)
        panel.activate_contact()
        self.assertEqual(panel.contact_list.GetCount(), 2)
        self.assertIn("created", panel.done)
        self.assertIn("opened", panel.done)
        completed.assert_not_called()
        back = Mock()
        back.GetKeyCode.return_value = wx.WXK_BACK
        panel.on_contact_key(back)
        completed.assert_called_once()

    def test_category_filter_does_not_move_messages(self) -> None:
        panel, completed = self.practice("organize_category")
        with patch.object(panel, "choose_category_rule", return_value="attachments"), patch.object(panel, "ask_name", return_value="الفواتير") as naming:
            panel.create_category()
        naming.assert_called_once()
        completed.assert_not_called()
        self.assertEqual(panel.categories.GetSelection(), 0)
        panel.categories.SetSelection(1)
        panel.render_category_messages()
        self.assertEqual(panel.category_messages.GetCount(), 1)
        self.assertEqual(len(panel.messages), 3)
        completed.assert_called_once()

    def test_escape_leaves_folder_before_outer_guide_closes(self) -> None:
        panel, completed = self.practice("organize_folder_create")
        panel.make_folder("تدريب", {"1", "2"})
        panel.open_folder("training-folder")
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_ESCAPE
        event.AltDown.return_value = event.ControlDown.return_value = event.ShiftDown.return_value = False
        with patch("accessible_mail.accessibility.announce_to_screen_reader"):
            self.assertTrue(panel.handle_navigation(event, panel.page.list))
        self.assertFalse(panel.in_folder)
        self.assertIn("مرة ثانية", panel.navigation_notice.GetLabel())
        self.assertFalse(panel.handle_navigation(event, panel.page.list))
        completed.assert_not_called()

    def test_section_tabs_and_return_command(self) -> None:
        panel, completed = self.practice("organize_section")
        self.assertIsInstance(panel.sections, wx.Notebook)
        self.assertEqual(panel.sections.GetPageCount(), 4)
        with patch.object(panel, "ask_name", return_value="مشروعي"):
            panel.create_section()
        self.assertEqual(panel.sections.GetPageCount(), 5)
        dialog = Mock()
        dialog.ShowModal.return_value = wx.ID_OK
        dialog.GetSelection.return_value = 1
        with patch("accessible_mail.learning_organization.choose_message_destination", return_value="section"), patch("accessible_mail.learning_organization.wx.SingleChoiceDialog", return_value=dialog):
            panel.move_training_section_message()
        self.assertEqual([m.uid for m in panel.section_pages[0].messages], ["2", "3"])
        panel.sections.SetSelection(4)
        panel.render_section_messages()
        self.assertEqual([m.uid for m in panel.section_pages[4].messages], ["1"])
        with patch.object(panel, "popup") as menu:
            panel.section_messages.Select(0)
            panel.section_message_menu()
        self.assertEqual(menu.call_args.args[1][0][0], "إعادة إلى الأقسام الأصلية")
        panel.return_section_message()
        self.assertEqual(len(panel.section_pages[0].messages), 3)
        completed.assert_called_once()

    def test_realistic_message_content(self) -> None:
        panel, _ = self.practice("organize_bulk_submenus")
        self.assertEqual([m.subject for m in panel.messages], ["رسالة العمل", "القسط الشهري للثلاجة", "رحلة إلى حديقة الحيوانات"])
        with patch.object(panel.page, "show_content") as show:
            panel.show_training_message(panel.page, panel.messages[1])
        self.assertIn("للثلاجة", show.call_args.args[0].text)

    def test_destination_prompt_uses_two_buttons_not_choice_list(self) -> None:
        from accessible_mail.message_destination_dialog import choose_message_destination
        seen = []

        def show(dialog):
            seen.extend(child.GetLabel() for child in dialog.GetChildren() if isinstance(child, wx.Button))
            self.assertFalse(any(isinstance(child, (wx.Choice, wx.ListBox)) for child in dialog.GetChildren()))
            return 2

        with patch.object(wx.Dialog, "ShowModal", show):
            self.assertEqual(choose_message_destination(self.frame), "section")
        self.assertEqual(seen, ["إلى مجلد", "إلى قسم"])

    def test_item_filter_stays_hidden_after_folder_selection(self) -> None:
        panel, _ = self.practice("organize_folder_create")
        page = panel.page
        page.begin_folder_creation()
        self.assertFalse(page.viewer.IsShown())
        self.assertTrue(page.create_folder_button.IsShown())
        page.exit_multi_selection_mode()
        self.assertFalse(page.link_panel.IsShown())
        self.assertFalse(page.item_filter_choice.IsShownOnScreen())
        self.assertTrue(page.filter_choice.IsShown())

    def test_contact_selection_space_and_tab(self) -> None:
        panel, _ = self.practice("organize_conversation_folder")
        panel.start_conversation_selection()
        self.assertIsInstance(panel.contact_checks, wx.ListCtrl)
        event = Mock()
        event.ControlDown.return_value = event.ShiftDown.return_value = False
        event.GetKeyCode.return_value = wx.WXK_SPACE
        panel.on_contact_selection_key(event)
        self.assertTrue(panel.contact_checks.IsItemChecked(0))
        panel.on_contact_selection_key(event)
        self.assertFalse(panel.contact_checks.IsItemChecked(0))
        event.GetKeyCode.return_value = wx.WXK_TAB
        with patch.object(panel.confirm_conversation, "SetFocus") as focus:
            panel.on_contact_selection_key(event)
        focus.assert_called_once()

    def test_section_arrow_navigation(self) -> None:
        panel, _ = self.practice("organize_section")
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_RIGHT
        with patch("accessible_mail.learning_organization.wx.Window.FindFocus", return_value=panel.sections):
            panel.on_section_key(event)
            self.assertEqual(panel.sections.GetSelection(), 1)
            event.GetKeyCode.return_value = wx.WXK_LEFT
            panel.on_section_key(event)
            self.assertEqual(panel.sections.GetSelection(), 0)

    def test_section_tabs_do_not_steal_message_context_key(self) -> None:
        panel, _ = self.practice("organize_section")
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_MENU
        with patch("accessible_mail.learning_organization.wx.Window.FindFocus", return_value=panel.section_messages), patch.object(panel, "section_menu") as menu:
            panel.on_section_key(event)
        event.Skip.assert_called_once()
        menu.assert_not_called()

    def test_section_tab_visits_tabs_before_page_and_shift_tab_returns(self) -> None:
        panel, _ = self.practice("organize_section")
        instructions = Mock()
        page = panel.section_pages[0]
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_TAB
        event.ControlDown.return_value = event.AltDown.return_value = event.ShiftDown.return_value = False
        with patch.object(panel.sections, "SetFocus") as tabs_focus, patch.object(page.filter_choice, "SetFocus") as filter_focus:
            self.assertTrue(panel.handle_section_tab(event, instructions, instructions))
            tabs_focus.assert_called_once()
            self.assertTrue(panel.handle_section_tab(event, panel.sections, instructions))
            filter_focus.assert_called_once()
            event.ShiftDown.return_value = True
            self.assertTrue(panel.handle_section_tab(event, page.filter_choice, instructions))
            self.assertEqual(tabs_focus.call_count, 2)
            self.assertTrue(panel.handle_section_tab(event, panel.sections, instructions))
            instructions.SetFocus.assert_called_once()

    def test_folder_lesson_message_menu_matches_production_order_and_availability(self) -> None:
        from accessible_mail.mail_page import MailPage
        from types import SimpleNamespace
        panel, _ = self.practice("organize_folder_create")
        callbacks = [Mock() for _ in range(8)]
        production = MailPage(self.frame, "الرسائل الواردة", *callbacks,
                              on_forward=Mock(), on_archive=Mock())
        self.addCleanup(production.Destroy)
        summary = panel.messages[2]
        captured = []

        def popup(menu):
            captured.append([(item.GetItemLabelText(), item.IsEnabled())
                             for item in menu.GetMenuItems() if not item.IsSeparator()])

        for page in (production, panel.page):
            with patch.object(page, "focused_summary", return_value=summary), patch.object(page, "selected_summary", return_value=summary), patch.object(page, "selected_summaries", return_value=[summary]), patch.object(page, "context_menu_popup_owner", return_value=SimpleNamespace(PopupMenu=popup)), patch.object(page, "schedule_context_focus_restore"), patch("accessible_mail.mail_page.announce_context_menu"):
                page.show_message_context_menu(page.list, False)
        self.assertEqual(captured[0], captured[1])
        self.assertEqual([label for label, _ in captured[1]], [
            "رد", "تعليم كمقروءة", "إعادة توجيه",
            "تمييز بنجمة", "التثبيت في الأعلى",
            "الحذف والنقل إلى سلة المحذوفات", "أرشفة الرسالة", "إنشاء مجلد للرسائل",
            "إضافة الرسالة إلى مجلد أو قسم", "إزالة الرسالة من المجلد دون حذفها",
        ])

    def test_revised_instructions_remove_category_extra_and_explain_section_dialog(self) -> None:
        instructions = {action: text for _title, text, action, _idea in ORGANIZATION_LESSONS}
        self.assertNotIn("لا تحتاج إلى كتابة بريد", instructions["organize_category"])
        self.assertIn("اضغط «إلى قسم»", instructions["organize_section"])
        self.assertIn("اختر «العمل» واضغط Enter", instructions["organize_section"])
        self.assertIn("Shift+Tab", instructions["organize_section"])
        for action, steps in (("organize_section", 7), ("organize_folder_create", 9)):
            for number in range(1, steps + 1):
                self.assertIn(f"\n\n{number}. ", instructions[action])

    def test_single_message_menu_shows_only_applicable_inverse_for_all_states(self) -> None:
        from itertools import product
        from types import SimpleNamespace
        panel, _ = self.practice("organize_folder_create")
        page = panel.page
        summary = panel.messages[0]
        pairs = [("تعليم كمقروءة", "تعليم كغير مقروءة"),
                 ("تمييز بنجمة", "إزالة التمييز بنجمة"),
                 ("التثبيت في الأعلى", "إلغاء التثبيت في الأعلى")]
        for states in product((False, True), repeat=3):
            with self.subTest(states=states):
                summary.is_read, summary.is_starred, summary.is_pinned = states
                captured = []

                def popup(menu, captured=captured):
                    captured.extend((item.GetItemLabelText(), item.IsEnabled())
                                    for item in menu.GetMenuItems() if not item.IsSeparator())

                with patch.object(page, "focused_summary", return_value=summary), patch.object(page, "selected_summary", return_value=summary), patch.object(page, "selected_summaries", return_value=[summary]), patch.object(page, "context_menu_popup_owner", return_value=SimpleNamespace(PopupMenu=popup)), patch.object(page, "schedule_context_focus_restore"), patch("accessible_mail.mail_page.announce_context_menu"):
                    page.show_message_context_menu(page.list, False)
                options = dict(captured)
                for state, pair in zip(states, pairs, strict=True):
                    self.assertTrue(options[pair[int(state)]])
                    self.assertNotIn(pair[int(not state)], options)

    def test_escape_viewer_returns_to_list_without_leaving_folder(self) -> None:
        panel, _ = self.practice("organize_folder_create")
        panel.make_folder("تدريب", {"1", "2"})
        panel.open_folder("training-folder")
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_ESCAPE
        event.AltDown.return_value = event.ControlDown.return_value = event.ShiftDown.return_value = False
        with patch.object(panel.page, "focus_message_list") as focus:
            self.assertTrue(panel.handle_navigation(event, panel.page.viewer))
        focus.assert_called_once()
        self.assertTrue(panel.in_folder)


if __name__ == "__main__":
    unittest.main()
