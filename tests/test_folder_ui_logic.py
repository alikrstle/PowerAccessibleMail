from __future__ import annotations

import unittest
import inspect
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wx

from accessible_mail.address_book import AddressEntry
from accessible_mail.custom_categories import CustomCategory
from accessible_mail.address_book_dialog import AddressBookDialog
from accessible_mail.folder_store import FOLDER_CONVERSATIONS, Folder, FolderStore, message_folder_key
from accessible_mail.main_frame import MainFrame
from accessible_mail.mail_page import FolderRow, MailPage
from accessible_mail.models import Account, MessageSummary
from accessible_mail.ui_constants import BULK_ACTION_ARCHIVE, BULK_ACTION_RESTORE_ARCHIVED


class FolderUiLogicTests(unittest.TestCase):
    @patch("accessible_mail.main_frame.wx.Window.FindFocus")
    def test_section_context_key_only_works_on_notebook_tabs(self, find_focus) -> None:
        frame = SimpleNamespace(notebook=object(), on_section_notebook_context=Mock())
        for key, shift in ((wx.WXK_MENU, False), (wx.WXK_F10, True)):
            event = Mock()
            event.GetKeyCode.return_value = key
            event.ShiftDown.return_value = shift
            find_focus.return_value = object()
            MainFrame.on_section_notebook_key(frame, event)
            frame.on_section_notebook_context.assert_not_called()
            event.Skip.assert_called_once()
            find_focus.return_value = frame.notebook
            MainFrame.on_section_notebook_key(frame, event)
            frame.on_section_notebook_context.assert_called_once()
            frame.on_section_notebook_context.reset_mock()

    @patch("accessible_mail.main_frame.call_after_if_open")
    @patch("accessible_mail.main_frame.wx.Window.FindFocus")
    def test_context_accelerator_routes_only_to_focused_area(self, find_focus, queued) -> None:
        page = SimpleNamespace(**{name: object() for name in ("list", "viewer", "filter_choice", "actions_button", "link_list")},
                               html_viewer=Mock(), show_item_menu=Mock(), show_message_context_menu=Mock(),
                               has_translatable_content=lambda: True)
        page.html_viewer.IsDescendant.return_value = False
        frame = SimpleNamespace(current_page=lambda: page, notebook=object(),
                                on_section_notebook_context=Mock(), on_category_notebook_context=Mock())
        for control in (page.list, page.viewer, page.html_viewer):
            find_focus.return_value = control
            MainFrame.on_context_menu_accelerator(frame)
            queued.assert_called_once_with(frame, page.show_message_context_menu, control, control is not page.list)
            queued.reset_mock()
        for control in (page.link_list, page.actions_button):
            find_focus.return_value = control
            MainFrame.on_context_menu_accelerator(frame)
            queued.assert_called_once_with(frame, page.show_item_menu, control)
            queued.reset_mock()
        find_focus.return_value = object()
        MainFrame.on_context_menu_accelerator(frame)
        queued.assert_not_called()
        find_focus.return_value = frame.notebook
        MainFrame.on_context_menu_accelerator(frame)
        frame.on_section_notebook_context.assert_called_once()
        find_focus.return_value = page.filter_choice
        MainFrame.on_context_menu_accelerator(frame)
        frame.on_category_notebook_context.assert_called_once()

    def test_section_menu_rejects_context_event_bubbled_from_messages(self) -> None:
        event = wx.ContextMenuEvent(wx.EVT_CONTEXT_MENU.typeId)
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        event.SetEventObject(wx.ListCtrl(parent))
        frame = SimpleNamespace(notebook=object(), selected_account=Mock())
        MainFrame.on_section_notebook_context(frame, event)
        self.assertTrue(event.GetSkipped())
        frame.selected_account.assert_not_called()

    def test_locked_section_background_replaces_content_and_restores_layout(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        page = MailPage(parent, "اختبار", *(Mock() for _ in range(8)))
        self.assertTrue(page.locked_section_panel.bitmap.IsOk())
        original = [(item, item.IsShown()) for item in page.GetSizer().GetChildren()
                    if item.GetWindow() != page.locked_section_panel]
        page.set_section_locked(True)
        self.assertTrue(page.IsEnabled())
        self.assertTrue(page.locked_section_panel.IsShown())
        self.assertFalse(page.list.IsShown())
        self.assertFalse(page.viewer.IsShown())
        self.assertFalse(page.html_viewer.IsShown())
        page.show_plain_viewer()
        page.update_link_panel_visibility()
        page.layout_viewer_area()
        self.assertFalse(page.viewer.IsShown())
        self.assertFalse(page.link_panel.IsShown())
        page.set_section_locked(False)
        self.assertFalse(page.locked_section_panel.IsShown())
        for item, shown in original:
            self.assertEqual(item.IsShown(), shown)

    @patch("accessible_mail.main_frame.wx.Window.FindFocus")
    def test_folder_escape_returns_one_level_then_main(self, find_focus: Mock) -> None:
        page = SimpleNamespace(viewer=object(), html_viewer=object(), link_list=object(),
                               actions_button=object(), item_filter_choice=object(),
                               list=object(), multi_select_mode=False, is_message_folder_page=True,
                               _html_viewer_active=False)
        frame = SimpleNamespace(current_page=lambda: page, on_focus_command_list_shortcut=Mock(),
                                on_escape_message_viewer=Mock(), show_notification=Mock(),
                                on_leave_message_folder=Mock(side_effect=lambda: setattr(page, "is_message_folder_page", False)))
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_ESCAPE
        event.ControlDown.return_value = event.AltDown.return_value = event.ShiftDown.return_value = event.CmdDown.return_value = False
        find_focus.return_value = page.list
        MainFrame.on_frame_char_hook(frame, event)
        frame.on_leave_message_folder.assert_called_once()
        frame.show_notification.assert_called_once_with("اضغط Escape مرة ثانية للعودة إلى واجهة البرنامج.")
        frame.on_focus_command_list_shortcut.assert_not_called()
        MainFrame.on_frame_char_hook(frame, event)
        frame.on_focus_command_list_shortcut.assert_called_once()

    def test_conversation_escape_returns_one_level_then_main(self) -> None:
        state = {"folder": "friends"}
        dialog = SimpleNamespace(folder_selection_list=SimpleNamespace(IsShown=lambda: False),
                                 selected_folder_id=lambda: state["folder"],
                                 on_leave_conversation_folder=Mock(side_effect=lambda: state.update(folder="")),
                                 return_to_main=Mock(), announce_event=Mock())
        AddressBookDialog.on_escape_navigation(dialog)
        dialog.on_leave_conversation_folder.assert_called_once()
        dialog.return_to_main.assert_not_called()
        dialog.announce_event.assert_called_once_with("اضغط Escape مرة ثانية للعودة إلى واجهة البرنامج.")
        AddressBookDialog.on_escape_navigation(dialog)
        dialog.return_to_main.assert_called_once()

    @patch("accessible_mail.main_frame.wx.Window.FindFocus")
    def test_escape_accelerator_returns_to_main_outside_viewer(self, find_focus: Mock) -> None:
        page = SimpleNamespace(
            exit_search=lambda: False, list=object(), viewer=object(),
            html_viewer=object(), link_list=object(), actions_button=object(),
            item_filter_choice=object(), _html_viewer_active=False,
        )
        frame = SimpleNamespace(
            current_page=lambda: page,
            on_focus_command_list_shortcut=Mock(),
        )
        find_focus.return_value = object()

        MainFrame.on_escape_message_viewer(frame)

        frame.on_focus_command_list_shortcut.assert_called_once_with()

    @patch("accessible_mail.main_frame.wx.Window.FindFocus")
    def test_backspace_moves_from_message_list_to_filter(self, find_focus: Mock) -> None:
        message_list = object()
        filter_choice = Mock()
        page = SimpleNamespace(
            list=message_list, filter_choice=filter_choice,
            is_message_folder_page=False,
            viewer=object(), html_viewer=object(), link_list=object(), actions_button=object(),
        )
        frame = SimpleNamespace(current_page=lambda: page)
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_BACK
        event.ControlDown.return_value = False
        event.ShiftDown.return_value = False
        event.AltDown.return_value = False
        event.CmdDown.return_value = False
        find_focus.return_value = message_list

        MainFrame.on_frame_char_hook(frame, event)

        filter_choice.SetFocus.assert_called_once_with()
        event.Skip.assert_not_called()

    @patch("accessible_mail.main_frame.wx.Window.FindFocus")
    def test_backspace_keeps_text_editing_native(self, find_focus: Mock) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        text_control = wx.TextCtrl(parent, value="draft")
        find_focus.return_value = text_control
        frame = SimpleNamespace(current_page=lambda: None)
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_BACK
        event.ControlDown.return_value = False
        event.ShiftDown.return_value = False
        event.AltDown.return_value = False
        event.CmdDown.return_value = False

        MainFrame.on_frame_char_hook(frame, event)

        event.Skip.assert_called_once_with()

    def test_lock_action_is_on_sections_not_categories(self) -> None:
        section_source = inspect.getsource(MainFrame.on_section_notebook_context)
        category_source = inspect.getsource(MainFrame.on_category_notebook_context)
        self.assertIn("قفل القسم بكلمة مرور", section_source)
        self.assertNotIn("قفل التصنيف", category_source)

    def test_locked_section_selection_does_not_prompt_or_block_navigation(self) -> None:
        section_page = Mock()
        store = SimpleNamespace(is_locked=Mock(return_value=True), is_open=Mock(return_value=False),
                                unlock_target=Mock(), close_target=Mock())
        notebook = SimpleNamespace(GetPageCount=lambda: 1, GetPage=lambda _index: section_page)
        event = Mock()
        event.GetSelection.return_value = 0
        event.GetOldSelection.return_value = -1
        frame = SimpleNamespace(
            selected_account=lambda: SimpleNamespace(id="account-a"), notebook=notebook,
            pages={"section:section-a": section_page},
            page_key_for_page=lambda _page: "section:section-a", folder_store=lambda: store,
            ask_local_lock_password=Mock(return_value=None),
            load_custom_sections=Mock(), refresh_section_folder_choices=Mock(),
            refresh_local_category_visibility=Mock(),
        )
        MainFrame.on_locked_section_changing(frame, event)
        event.Veto.assert_not_called()
        event.Skip.assert_called_once_with()
        store.unlock_target.assert_not_called()
        frame.ask_local_lock_password.assert_not_called()
        section_page.set_section_locked.assert_called_once_with(True)
        section_page.set_messages.assert_called_once_with([])
        self.assertEqual(section_page.folder_rows, [])
        self.assertEqual(section_page.archive_messages, [])
        self.assertEqual(section_page.trash_messages, [])

    def test_locked_section_enter_cancel_wrong_password_and_success(self) -> None:
        page = Mock()
        store = Mock()
        store.is_locked.return_value = True
        store.is_open.return_value = False
        frame = SimpleNamespace(selected_account=lambda: SimpleNamespace(id="account-a"),
                                current_page=lambda: page, page_key_for_page=lambda _page: "section:section-a",
                                folder_store=lambda: store, ask_local_lock_password=Mock(return_value=None),
                                load_custom_sections=Mock(), refresh_section_folder_choices=Mock(),
                                refresh_local_category_visibility=Mock())
        self.assertTrue(MainFrame.open_selected_locked_section(frame))
        store.unlock_target.assert_not_called()
        frame.load_custom_sections.assert_not_called()
        frame.ask_local_lock_password.return_value = "wrong"
        store.unlock_target.side_effect = ValueError("incorrect password")
        with patch("accessible_mail.main_frame.wx.MessageBox"):
            self.assertTrue(MainFrame.open_selected_locked_section(frame))
        frame.load_custom_sections.assert_not_called()
        store.unlock_target.side_effect = None
        frame.ask_local_lock_password.return_value = "passphrase-123"
        with patch("accessible_mail.main_frame.call_after_if_open") as focus:
            self.assertTrue(MainFrame.open_selected_locked_section(frame))
        store.unlock_target.assert_called_with("account-a", "section", "section-a", "passphrase-123")
        frame.load_custom_sections.assert_called_once()
        frame.refresh_section_folder_choices.assert_called_once()
        frame.refresh_local_category_visibility.assert_called_once()
        focus.assert_called_once_with(frame, page.focus_message_list)

    @patch("accessible_mail.main_frame.wx.Window.FindFocus")
    def test_locked_section_enter_is_only_handled_on_tabs(self, find_focus) -> None:
        frame = SimpleNamespace(notebook=object(), open_selected_locked_section=Mock(return_value=True))
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_RETURN
        event.ControlDown.return_value = event.AltDown.return_value = event.ShiftDown.return_value = False
        find_focus.return_value = object()
        MainFrame.on_section_notebook_key(frame, event)
        frame.open_selected_locked_section.assert_not_called()
        event.Skip.assert_called_once()
        find_focus.return_value = frame.notebook
        MainFrame.on_section_notebook_key(frame, event)
        frame.open_selected_locked_section.assert_called_once()

    def test_bulk_context_menu_groups_star_and_pin_options(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        labels: list[str] = []
        submenu_labels: dict[str, list[str]] = {}

        def inspect_menu(menu: wx.Menu) -> None:
            for item in menu.GetMenuItems():
                label = item.GetItemLabelText()
                labels.append(label)
                if item.GetSubMenu() is not None:
                    submenu = item.GetSubMenu()
                    submenu_labels[label] = [child.GetItemLabelText() for child in submenu.GetMenuItems()]
                    if label == "خيارات تثبيت الرسالة":
                        submenu.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU, submenu.GetMenuItems()[0].GetId()))

        page = SimpleNamespace(
            context_return_control=lambda control: control,
            context_menu_popup_owner=lambda _control: SimpleNamespace(PopupMenu=inspect_menu),
            selected_filter_key=lambda: "all", on_bulk_action=Mock(),
            focus_message_list=Mock(), restore_context_focus=Mock(),
        )
        with patch("accessible_mail.mail_page.announce_context_menu"), patch("accessible_mail.mail_page.wx.CallAfter") as call_after:
            MailPage.show_multi_message_context_menu(page, object(), [MessageSummary(uid="1", mailbox="INBOX")])
        self.assertIn("خيارات تمييز الرسائل بنجمة", labels)
        self.assertIn("خيارات تثبيت الرسالة", labels)
        self.assertIn("خيارات حالة قراءة الرسائل", labels)
        self.assertIn("خيارات المجلد", labels)
        self.assertEqual(len(submenu_labels["خيارات تمييز الرسائل بنجمة"]), 2)
        self.assertEqual(len(submenu_labels["خيارات تثبيت الرسالة"]), 2)
        self.assertEqual(len(submenu_labels["خيارات حالة قراءة الرسائل"]), 2)
        self.assertIn("إزالة الرسائل من المجلد دون حذفها", submenu_labels["خيارات المجلد"])
        self.assertIn("pin", [call.args[2] for call in call_after.call_args_list if len(call.args) >= 3])

    def test_bulk_context_menu_offers_archive_and_restore_for_selected_messages(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        summary = MessageSummary(uid="1", mailbox="INBOX")
        for filter_key, label, action, enabled in (
            ("all", "أرشفة الرسائل", BULK_ACTION_ARCHIVE, True),
            ("archive", "إعادة الرسائل إلى الوارد", BULK_ACTION_RESTORE_ARCHIVED, True),
            ("trash", "أرشفة الرسائل", BULK_ACTION_ARCHIVE, False),
        ):
            with self.subTest(filter_key=filter_key):
                captured = {}

                def inspect_menu(menu: wx.Menu, label=label, captured=captured, enabled=enabled) -> None:
                    item = next(item for item in menu.GetMenuItems() if item.GetItemLabelText() == label)
                    captured["enabled"] = item.IsEnabled()
                    if enabled:
                        menu.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU, item.GetId()))

                page = SimpleNamespace(
                    context_return_control=lambda control: control,
                    context_menu_popup_owner=lambda _control: SimpleNamespace(PopupMenu=inspect_menu),
                    selected_filter_key=lambda filter_key=filter_key: filter_key,
                    on_archive=Mock(), on_bulk_action=Mock(),
                    focus_message_list=Mock(), restore_context_focus=Mock(),
                )
                with (
                    patch("accessible_mail.mail_page.announce_context_menu"),
                    patch("accessible_mail.mail_page.wx.CallAfter") as call_after,
                ):
                    MailPage.show_multi_message_context_menu(page, object(), [summary])
                self.assertEqual(captured["enabled"], enabled)
                if enabled:
                    self.assertIn(
                        action,
                        [call.args[2] for call in call_after.call_args_list if len(call.args) >= 3],
                    )

    def test_bulk_archive_updates_only_successful_messages(self) -> None:
        first = MessageSummary(uid="1", mailbox="INBOX")
        second = MessageSummary(uid="2", mailbox="INBOX")
        account = SimpleNamespace(id="account-a", oauth_provider="google_gmail_api")
        service = Mock()
        service.archive_message.side_effect = lambda _account, summary: (
            None if summary.uid == "1" else (_ for _ in ()).throw(RuntimeError("failed"))
        )
        page = SimpleNamespace(
            selected_filter_key=lambda: "all", selected_indices=lambda: [0, 1],
            messages=[first, second], archive_messages=[], remove_message=Mock(),
            exit_multi_selection_mode=Mock(), previous_message_index=lambda index: index,
            focus_list_index=Mock(), focus_message_list=Mock(),
        )
        frame = SimpleNamespace(
            selected_account=lambda: account, displayed_account_id="account-a",
            service=service, pages={"all": page}, _search_dialog=None,
            SetStatusText=Mock(), refresh_all=Mock(),
            run_worker=lambda _message, work, done: done(work()),
        )
        with patch("accessible_mail.main_frame.wx.MessageBox", return_value=wx.YES):
            MainFrame.on_archive_selected_messages(frame, page, [first, second], restoring=False)
        page.remove_message.assert_called_once_with(first)
        page.exit_multi_selection_mode.assert_called_once_with(restore_single_selection=False)
        frame.SetStatusText.assert_called_once()
        self.assertIn("1", frame.SetStatusText.call_args.args[0])
        frame.refresh_all.assert_not_called()

    def test_bulk_restore_refreshes_inbox_after_success(self) -> None:
        summary = MessageSummary(uid="1", mailbox="ARCHIVE")
        account = SimpleNamespace(id="account-a", oauth_provider="google_gmail_api")
        service = Mock()
        page = SimpleNamespace(
            selected_filter_key=lambda: "archive", selected_indices=lambda: [0],
            messages=[], archive_messages=[summary], apply_filter=Mock(),
            exit_multi_selection_mode=Mock(), previous_message_index=lambda index: index,
            focus_list_index=Mock(), focus_message_list=Mock(),
        )
        frame = SimpleNamespace(
            selected_account=lambda: account, displayed_account_id="account-a",
            service=service, pages={"all": page}, _search_dialog=None,
            SetStatusText=Mock(), refresh_all=Mock(),
            run_worker=lambda _message, work, done: done(work()),
        )
        with patch("accessible_mail.main_frame.wx.MessageBox", return_value=wx.YES):
            MainFrame.on_archive_selected_messages(frame, page, [summary], restoring=True)
        service.restore_archived_message.assert_called_once_with(account, summary)
        self.assertEqual(page.archive_messages, [])
        page.apply_filter.assert_called_once_with()
        frame.refresh_all.assert_called_once_with()

    def test_bulk_archive_cancel_does_not_contact_provider(self) -> None:
        summary = MessageSummary(uid="1", mailbox="INBOX")
        account = SimpleNamespace(id="account-a", oauth_provider="google_gmail_api")
        page = SimpleNamespace(
            selected_filter_key=lambda: "all", focus_message_list=Mock(),
        )
        frame = SimpleNamespace(
            selected_account=lambda: account, service=Mock(), run_worker=Mock(),
        )
        with (
            patch("accessible_mail.main_frame.wx.MessageBox", return_value=wx.NO),
            patch("accessible_mail.main_frame.wx.CallAfter") as call_after,
        ):
            MainFrame.on_archive_selected_messages(frame, page, [summary], restoring=False)
        frame.run_worker.assert_not_called()
        frame.service.archive_message.assert_not_called()
        call_after.assert_called_once()

    def test_select_all_visible_messages_skips_folder_rows(self) -> None:
        messages = [MessageSummary(uid="1", mailbox="INBOX"),
                    FolderRow(Folder("folder-1", "account-a", "messages", "متابعة")),
                    MessageSummary(uid="2", mailbox="INBOX")]
        checked: set[int] = set()
        list_control = SimpleNamespace(
            IsItemChecked=lambda index: index in checked,
            CheckItem=lambda index, value: checked.add(index) if value else checked.discard(index),
        )
        page = SimpleNamespace(
            visible_messages=messages, multi_select_mode=True, list=list_control,
            message_key=lambda item: (item.mailbox, item.uid),
            update_multi_selection_status=Mock(), announce_accessible=Mock(), set_status=Mock(),
        )
        MailPage.select_all_visible_messages(page)
        self.assertEqual(checked, {0, 2})
        self.assertEqual(page._multi_selected_keys, {("INBOX", "1"), ("INBOX", "2")})
        page.announce_accessible.assert_called_once_with("تم تحديد كل الرسائل الظاهرة. عدد الرسائل المحددة: 2.")

    def test_ctrl_a_in_message_list_invokes_select_all(self) -> None:
        page = SimpleNamespace(select_all_visible_messages=Mock())
        event = Mock()
        event.GetKeyCode.return_value = ord("A")
        event.ControlDown.return_value = True
        event.AltDown.return_value = False
        event.ShiftDown.return_value = False
        MailPage.on_list_key(page, event)
        page.select_all_visible_messages.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_new_folder_shortcuts_follow_focused_item(self) -> None:
        account = Account(id="account-a")
        folder = FolderRow(Folder("folder-1", account.id, "messages", "متابعة"))
        message = MessageSummary(uid="42", mailbox="INBOX")
        page = SimpleNamespace(
            messages=[message], focused_summary=lambda: folder,
            selected_summaries=lambda: [message], selected_summary=lambda: message,
            begin_folder_creation=Mock(),
        )
        frame = SimpleNamespace(
            selected_account=lambda: account, current_page=lambda: page,
            selected_folder_id=lambda: "", SetStatusText=Mock(),
            delete_folder_by_id=Mock(), choose_folder_section=Mock(),
            on_add_messages_to_folder=Mock(),
        )
        MainFrame.on_create_folder_shortcut(frame)
        MainFrame.on_add_to_folder_shortcut(frame)
        MainFrame.on_delete_folder_shortcut(frame)
        MainFrame.on_move_to_section_shortcut(frame)
        page.begin_folder_creation.assert_called_once()
        frame.on_add_messages_to_folder.assert_called_once_with(account, [message])
        frame.delete_folder_by_id.assert_called_once_with("folder-1")
        frame.choose_folder_section.assert_called_once_with(account, "folder-1")

    def test_section_and_category_shortcuts_require_custom_target(self) -> None:
        page = SimpleNamespace(selected_filter_key=lambda: "custom:category-1")
        frame = SimpleNamespace(
            current_page=lambda: page, page_key_for_page=lambda _page: "section:section-1",
            edit_local_category_rules=Mock(), delete_local_category=Mock(),
            delete_local_section=Mock(), SetStatusText=Mock(),
        )
        MainFrame.on_edit_category_shortcut(frame)
        MainFrame.on_delete_category_shortcut(frame)
        MainFrame.on_delete_section_shortcut(frame)
        frame.edit_local_category_rules.assert_called_once_with("category-1")
        frame.delete_local_category.assert_called_once_with("category-1")
        frame.delete_local_section.assert_called_once_with("section-1")

    def test_folders_are_visible_in_all_messages_and_their_source_section(self) -> None:
        account = Account(id="account-a")
        inbox_folder = Folder("folder-1", account.id, "messages", "الوارد", section_key="inbox")
        custom_folder = Folder("folder-2", account.id, "messages", "العمل", section_id="section-1")
        store = Mock()
        store.list_folders.side_effect = lambda _account, _kind, **kwargs: (
            [inbox_folder, custom_folder] if "section_id" not in kwargs else
            [inbox_folder] if kwargs["section_id"] == "" and not kwargs.get("archived") else
            [custom_folder] if kwargs["section_id"] == "section-1" and not kwargs.get("archived") else []
        )
        store.list_section_folders.side_effect = lambda _account, key: [inbox_folder] if key == "inbox" else []
        pages = {
            key: SimpleNamespace(folder_rows=[], archive_messages=[], apply_filter=Mock())
            for key in ("inbox", "spam", "sent", "all", "folders", "section:section-1")
        }
        frame = SimpleNamespace(
            selected_account=lambda: account, selected_folder_id=lambda: "",
            folder_store=lambda: store, pages=pages,
        )
        MainFrame.refresh_section_folder_choices(frame)
        self.assertEqual([row.folder_id for row in pages["all"].folder_rows], ["folder-1", "folder-2"])
        self.assertEqual([row.folder_id for row in pages["inbox"].folder_rows], ["folder-1"])
        self.assertEqual([row.folder_id for row in pages["section:section-1"].folder_rows], ["folder-2"])

    def test_folder_row_is_not_treated_as_a_message_action_target(self) -> None:
        folder_row = FolderRow(Folder("folder-1", "account-a", "messages", "متابعة", item_count=3))
        message = MessageSummary(uid="42", mailbox="INBOX", subject="رسالة")
        page = SimpleNamespace(
            visible_messages=[folder_row, message],
            selected_indices=lambda: [0, 1],
            focused_index=lambda: 0,
            multi_select_mode=False,
            list=Mock(),
        )
        page.list.GetItemState.return_value = wx.LIST_STATE_SELECTED

        self.assertEqual(MailPage.selected_summaries(page), [message])
        self.assertIsNone(MailPage.selected_summary(page))
        self.assertTrue(folder_row.status_label.startswith("مجلد، متابعة، عدد الرسائل: 3، "))

    def test_new_category_filters_distinguish_locked_messages_and_folders(self) -> None:
        folder = FolderRow(Folder("folder-1", "account-a", "messages", "خاص", locked=True))
        regular = MessageSummary(uid="42", mailbox="INBOX")
        key_hash = FolderStore.locked_key_hash("account-a", message_folder_key(regular))
        self.assertTrue(MailPage.matches_custom_category(folder, ("message_folders",)))
        self.assertTrue(MailPage.matches_custom_category(folder, ("locked_messages",)))
        self.assertFalse(MailPage.matches_custom_category(regular, ("message_folders",)))
        self.assertTrue(MailPage.matches_custom_category(
            regular, ("locked_messages",), locked_account_id="account-a",
            locked_message_hashes=frozenset({key_hash}),
        ))
        self.assertFalse(MailPage.matches_custom_category(
            regular, ("locked_messages",), locked_account_id="account-a",
        ))

    def test_tab_from_folder_selection_reaches_create_button(self) -> None:
        button = Mock()
        page = SimpleNamespace(
            multi_select_mode=True,
            folder_creation_mode=True,
            viewer_mode="html",
            create_folder_button=button,
        )
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_TAB
        event.ControlDown.return_value = False
        event.ShiftDown.return_value = False
        event.AltDown.return_value = False

        MailPage.on_list_key(page, event)

        button.SetFocus.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_enter_on_folder_row_opens_folder_without_opening_message_viewer(self) -> None:
        folder_row = FolderRow(Folder("folder-1", "account-a", "messages", "متابعة"))
        page = SimpleNamespace(
            focused_summary=lambda: folder_row,
            multi_select_mode=False,
            on_folder_open=Mock(),
            focus_message_viewer_start=Mock(),
        )
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_RETURN

        MailPage.on_list_key(page, event)

        page.on_folder_open.assert_called_once_with("folder-1")
        page.focus_message_viewer_start.assert_not_called()

    def test_folder_row_context_menu_does_not_show_message_actions(self) -> None:
        folder_row = FolderRow(Folder("folder-1", "account-a", "messages", "متابعة"))
        page = SimpleNamespace(
            _message_context_menu_open=False,
            focused_summary=lambda: folder_row,
            list=object(), viewer=object(), html_viewer=object(), actions_button=object(),
            multi_select_mode=False,
            on_folder_context=Mock(),
            selected_summaries=Mock(),
        )

        MailPage.show_message_context_menu(page, page.list, False)

        page.on_folder_context.assert_called_once_with("folder-1")
        page.selected_summaries.assert_not_called()

    def test_created_folder_appears_in_folder_section(self) -> None:
        account = Account(id="account-a")
        summary = MessageSummary(uid="42", mailbox="INBOX")
        page = SimpleNamespace(exit_multi_selection_mode=Mock(), focus_message_list=Mock(),
                               selected_filter_key=lambda: "all")
        folder_page = SimpleNamespace(is_message_folder_page=False, filter_choice=Mock(),
                                      focus_message_list=Mock(), set_folder_collection_layout=Mock())
        store = Mock()
        store.create_folder.return_value = Folder(
            "folder-1", "account-a", "messages", "متابعة", section_key="inbox",
        )
        dialog = Mock()
        dialog.ShowModal.return_value = wx.ID_OK
        dialog.GetValue.return_value = "متابعة"
        frame = SimpleNamespace(
            page_key_for_page=lambda _page: "inbox",
            folder_store=lambda: store,
            refresh_folder_choices=Mock(),
            refresh_section_folder_choices=Mock(),
            refresh_local_category_visibility=Mock(),
            load_selected_custom_category=Mock(),
            pages={"inbox": page, "folders": folder_page},
            notebook=Mock(),
            SetStatusText=Mock(),
        )

        with patch("accessible_mail.main_frame.wx.TextEntryDialog", return_value=dialog):
            MainFrame.on_create_message_folder(frame, page, account, [summary])

        self.assertEqual(store.create_folder.call_args.kwargs["section_key"], "inbox")
        frame.refresh_section_folder_choices.assert_called_with("inbox", "folder-1")
        page.focus_message_list.assert_called_once_with()
        frame.notebook.SetSelection.assert_called_once_with(0)

    def test_escape_from_folder_returns_to_folder_collection(self) -> None:
        pages = {key: SimpleNamespace(focus_message_list=Mock()) for key in
                 ("inbox", "spam", "sent", "all", "folders")}
        pages["folders"].filter_choice = Mock()
        pages["folders"].filter_choice.GetCount.return_value = 4
        pages["folders"].set_messages = Mock()
        notebook = Mock()
        frame = SimpleNamespace(
            _folder_return_page_key="folders",
            notebook=notebook,
            pages=pages,
            refresh_section_folder_choices=Mock(),
        )
        pages["sent"].filter_choice = Mock()
        pages["sent"].filter_choice.GetCount.return_value = 6

        MainFrame.on_leave_message_folder(frame)

        notebook.SetSelection.assert_called_once_with(list(pages).index("folders"))
        pages["folders"].focus_message_list.assert_called_once_with()

    def test_open_folder_focuses_its_message_list_without_folder_selector(self) -> None:
        pages = {key: SimpleNamespace(focus_message_list=Mock()) for key in ("inbox", "folders")}
        pages["folders"].filter_choice = Mock()
        pages["inbox"].filter_choice = Mock()
        frame = SimpleNamespace(pages=pages, notebook=Mock(), refresh_folder_choices=Mock())

        MainFrame.open_section_folder(frame, "folders", "folder-1")

        frame.refresh_folder_choices.assert_called_once_with("folder-1", preserve=False)
        frame.notebook.SetSelection.assert_called_once_with(1)
        pages["folders"].focus_message_list.assert_called_once_with()

    def test_custom_category_loads_filter_rules(self) -> None:
        account = Account(id="account-a")
        page = SimpleNamespace(messages=[], apply_filter=Mock())
        store = Mock()
        store.list_categories.return_value = [CustomCategory("category-1", "مهم", ("specific_email",), ("user@example.com",))]
        store.recent_read_keys.return_value = []
        frame = SimpleNamespace(
            selected_account=lambda: account,
            _visible_category_ids=["category-1"],
            pages={"inbox": page},
            folder_store=lambda: store,
            service=SimpleNamespace(cache=Mock()),
            selected_folder_id=lambda: "",
        )

        MainFrame.load_selected_custom_category(frame)

        self.assertEqual(page.local_category_rules, {"category-1": ("specific_email",)})
        self.assertEqual(page.local_category_emails, {"category-1": ("user@example.com",)})
        page.apply_filter.assert_called_once_with()

    def test_frequent_sender_count_does_not_double_count_across_sections(self) -> None:
        account = Account(id="account-a", email_address="me@example.com")
        messages = [
            MessageSummary(uid=str(index), mailbox="INBOX", message_id=f"id-{index}", sender_email="news@example.org")
            for index in range(5)
        ]
        pages = {
            "inbox": SimpleNamespace(messages=messages, apply_filter=Mock()),
            "all": SimpleNamespace(messages=list(messages), apply_filter=Mock()),
        }
        store = Mock()
        store.list_categories.return_value = []
        store.recent_read_keys.return_value = []
        frame = SimpleNamespace(selected_account=lambda: account, pages=pages, folder_store=lambda: store)
        MainFrame.load_selected_custom_category(frame)
        for page in pages.values():
            self.assertEqual(page.sender_frequency, {"news@example.org": 5})

    def test_multi_selection_hides_message_viewer_and_restores_it(self) -> None:
        page = SimpleNamespace(
            viewer_label_sizer_item=Mock(),
            expanded_line_preview_sizer_item=Mock(),
            viewer_sizer_item=Mock(),
            html_viewer_sizer_item=Mock(),
            link_panel_sizer_item=Mock(),
            link_panel=Mock(),
            layout_viewer_area=Mock(),
            viewer_mode="simple",
            _html_viewer_active=False,
            show_plain_viewer=Mock(),
        )

        MailPage.set_multi_selection_layout(page, True)
        page.viewer_sizer_item.Show.assert_called_once_with(False)
        page.html_viewer_sizer_item.Show.assert_called_once_with(False)
        page.link_panel_sizer_item.Show.assert_called_once_with(False)
        page.link_panel.Hide.assert_called_once_with()

        MailPage.set_multi_selection_layout(page, False)
        page.show_plain_viewer.assert_called_once_with()

    def test_local_category_visibility_covers_all_standard_pages(self) -> None:
        account = Account(id="account-a", oauth_provider="google_gmail_api")
        store = Mock()
        store.message_folder_keys.return_value = [message_folder_key(MessageSummary(uid="42", mailbox="INBOX"))]
        store.section_message_keys.return_value = []
        store.category_message_keys.return_value = []
        pages = {key: SimpleNamespace(messages=[], apply_filter=Mock()) for key in
                 ("inbox", "spam", "sent", "all", "folders", "custom")}
        frame = SimpleNamespace(
            selected_account=lambda: account,
            folder_store=lambda: store,
            pages=pages,
        )

        MainFrame.refresh_local_category_visibility(frame)

        for key in ("inbox", "spam", "sent", "all"):
            self.assertEqual(pages[key].excluded_message_keys, {("INBOX", "42")})
            self.assertEqual(pages[key].excluded_message_uids, {"42"})
            pages[key].apply_filter.assert_called_once_with()
        self.assertFalse(hasattr(pages["folders"], "excluded_message_keys"))

    def test_moving_folder_to_custom_section_does_not_call_mail_service(self) -> None:
        account = Account(id="account-a")
        store = Mock()
        service = Mock()
        frame = SimpleNamespace(
            folder_store=lambda: store,
            refresh_section_folder_choices=Mock(),
            SetStatusText=Mock(),
            service=service,
        )

        MainFrame.move_folder_to_section(frame, account, "folder-1", "section-1")

        store.set_folder_section.assert_called_once_with("account-a", "folder-1", "section-1")
        service.assert_not_called()
        self.assertFalse(service.method_calls)
        frame.refresh_section_folder_choices.assert_called_once_with()

    def test_imap_local_category_matches_message_id_across_mailboxes(self) -> None:
        account = Account(id="account-a")
        store = Mock()
        store.message_folder_keys.return_value = [message_folder_key(MessageSummary(uid="42", mailbox="INBOX"))]
        store.section_message_keys.return_value = []
        store.category_message_keys.return_value = []
        original = MessageSummary(uid="42", mailbox="INBOX", message_id="<same@example.com>")
        duplicate = MessageSummary(uid="900", mailbox="All Mail", message_id="<same@example.com>")
        pages = {key: SimpleNamespace(messages=[], apply_filter=Mock()) for key in
                 ("inbox", "spam", "sent", "all", "folders", "custom")}
        pages["inbox"].messages = [original]
        pages["all"].messages = [duplicate]
        cache = Mock()
        frame = SimpleNamespace(
            selected_account=lambda: account,
            folder_store=lambda: store,
            pages=pages,
            service=SimpleNamespace(cache=cache),
        )

        MainFrame.refresh_local_category_visibility(frame)

        self.assertEqual(pages["all"].excluded_message_ids, {"<same@example.com>"})
        cache.summaries_by_uids.assert_not_called()

    def test_archived_results_in_custom_section_stay_inside_that_section(self) -> None:
        account = Account(id="account-a")
        original = MessageSummary(uid="42", mailbox="INBOX", message_id="<same@example.com>")
        archived = MessageSummary(uid="900", mailbox="Archive", message_id="<same@example.com>")
        unrelated = MessageSummary(uid="901", mailbox="Archive", message_id="<other@example.com>")
        page = SimpleNamespace(messages=[original])
        store = Mock()
        store.section_message_keys.return_value = [message_folder_key(original)]
        frame = SimpleNamespace(
            page_key_for_page=lambda _page: "section:local-1",
            folder_store=lambda: store,
            pages={"section:local-1": page},
        )

        result = MainFrame.filter_local_section_results(frame, account, page, [archived, unrelated])

        self.assertEqual(result, [archived])

    def test_conversation_folder_selection_stays_inside_address_book(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        store = Mock()
        store.locked_message_hashes.return_value = set()
        store.protected_address_hashes.return_value = set()
        store.folder_addresses.return_value = []
        store.is_locked.return_value = False
        store.list_folders.return_value = []
        with (
            patch("accessible_mail.address_book_dialog.load_address_book", return_value=[
                AddressEntry("sam@example.com", name="سام"),
            ]),
            patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
        ):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                dialog.on_create_conversation_folder()
                self.assertTrue(dialog.folder_selection_list.IsShown())
                self.assertFalse(dialog.address_list.IsShown())
                self.assertTrue(dialog.confirm_folder_button.IsShown())
                self.assertEqual(dialog.folder_selection_list.GetItemCount(), 1)
                self.assertEqual(dialog.selected_conversation_indices(), [])
                dialog.folder_selection_list.CheckItem(0, True)
                self.assertEqual(dialog.selected_conversation_indices(), [0])
                self.assertIn("1", dialog.folder_selection_status.GetLabel())
                dialog.folder_selection_list.CheckItem(0, False)
                select_all = Mock()
                select_all.GetKeyCode.return_value = ord("A")
                select_all.ControlDown.return_value = True
                select_all.ShiftDown.return_value = False
                select_all.AltDown.return_value = False
                dialog.on_folder_selection_key(select_all)
                self.assertEqual(dialog.selected_conversation_indices(), [0])
                tab = Mock()
                tab.GetKeyCode.return_value = wx.WXK_TAB
                tab.ControlDown.return_value = False
                tab.ShiftDown.return_value = False
                tab.AltDown.return_value = False
                dialog.on_folder_selection_key(tab)
                self.assertIs(wx.Window.FindFocus(), dialog.confirm_folder_button)
                dialog.on_cancel_conversation_folder()
                self.assertTrue(dialog.address_list.IsShown())
                self.assertFalse(dialog.folder_selection_list.IsShown())
            finally:
                dialog.Destroy()

    def test_conversation_context_menu_groups_three_folder_actions(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        store = Mock()
        store.locked_message_hashes.return_value = set()
        store.protected_address_hashes.return_value = set()
        store.folder_addresses.return_value = []
        store.is_locked.return_value = False
        store.list_folders.return_value = []
        with (
            patch("accessible_mail.address_book_dialog.load_address_book", return_value=[
                AddressEntry("sam@example.com", name="سام"),
            ]),
            patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
        ):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                captured = {}

                def capture_menu(menu):
                    captured["labels"] = [item.GetItemLabelText() for item in menu.GetMenuItems()]
                    folder_item = next(item for item in menu.GetMenuItems() if item.GetItemLabelText() == "خيارات المجلد")
                    captured["folder_labels"] = [item.GetItemLabelText() for item in folder_item.GetSubMenu().GetMenuItems()]

                with patch.object(dialog.address_list, "PopupMenu", side_effect=capture_menu):
                    dialog.show_context_menu()
                self.assertIn("خيارات المجلد", captured["labels"])
                self.assertIn("تعديل العنوان", captured["labels"])
                self.assertNotIn("إزالة المحادثة من المجلد دون حذفها", captured["labels"])
                self.assertEqual(captured["folder_labels"], [
                    "إنشاء مجلد",
                    "إضافة المحادثة إلى مجلد موجود",
                ])
            finally:
                dialog.Destroy()

    def test_remove_conversation_action_appears_only_inside_folder(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        store = Mock()
        store.locked_message_hashes.return_value = set()
        store.protected_address_hashes.return_value = set()
        store.folder_addresses.return_value = []
        store.is_locked.return_value = False
        store.list_folders.return_value = []
        store.list_items.return_value = ["sam@example.com"]
        with (
            patch("accessible_mail.address_book_dialog.load_address_book", return_value=[
                AddressEntry("sam@example.com", name="سام"),
            ]),
            patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
        ):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                dialog._open_folder_id = "folder-1"
                dialog.refresh_list()
                captured = {}

                def capture_menu(menu):
                    captured["labels"] = [item.GetItemLabelText() for item in menu.GetMenuItems()]
                    folder_item = next(item for item in menu.GetMenuItems() if item.GetItemLabelText() == "خيارات المجلد")
                    captured["folder_labels"] = [item.GetItemLabelText() for item in folder_item.GetSubMenu().GetMenuItems()]

                with patch.object(dialog.address_list, "PopupMenu", side_effect=capture_menu):
                    dialog.show_context_menu()
                self.assertNotIn("إزالة المحادثة من المجلد دون حذفها", captured["labels"])
                self.assertIn("إزالة المحادثة من المجلد دون حذفها", captured["folder_labels"])
                self.assertNotIn("العودة إلى جميع العناوين", captured["labels"])
            finally:
                dialog.Destroy()

    def test_conversation_folder_row_shows_management_actions_directly_once(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        store = Mock()
        store.locked_message_hashes.return_value = set()
        store.protected_address_hashes.return_value = set()
        store.folder_addresses.return_value = []
        store.is_locked.return_value = False
        store.list_folders.return_value = [
            Folder("folder-1", "account-a", "conversations", "الأصدقاء", item_count=1),
        ]
        store.get_folder.return_value = store.list_folders.return_value[0]
        with (
            patch("accessible_mail.address_book_dialog.load_address_book", return_value=[]),
            patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
        ):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                captured = {}

                def capture_menu(menu):
                    captured["labels"] = [item.GetItemLabelText() for item in menu.GetMenuItems()]

                with patch.object(dialog.address_list, "PopupMenu", side_effect=capture_menu):
                    dialog.on_folder_context_menu(folder_id_override="folder-1")
                self.assertEqual([label for label in captured["labels"] if label], [
                    "تثبيت المجلد في الأعلى",
                    "إعادة تسمية المجلد",
                    "قفل المجلد بكلمة مرور",
                    "حذف المجلد دون حذف المحادثات",
                ])
                self.assertFalse(any("أرشف" in label or "مؤرشف" in label for label in captured["labels"]))
            finally:
                dialog.Destroy()

    def test_second_conversation_folder_only_offers_unassigned_addresses(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        with tempfile.TemporaryDirectory() as directory:
            store = FolderStore(Path(directory) / "folders.db")
            first = store.create_folder(
                "account-a", FOLDER_CONVERSATIONS, "الأول", ["sam@example.com"],
            )
            with (
                patch("accessible_mail.address_book_dialog.load_address_book", return_value=[
                    AddressEntry("sam@example.com", name="سام"),
                    AddressEntry("ali@example.com", name="علي"),
                ]),
                patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
            ):
                dialog = AddressBookDialog(parent, account_id="account-a")
                try:
                    dialog.on_create_conversation_folder()
                    self.assertEqual(dialog.folder_selection_list.GetItemCount(), 1)
                    self.assertIn("علي", dialog.folder_selection_list.GetItemText(0))
                    dialog.folder_selection_list.CheckItem(0, True)
                    with patch("accessible_mail.address_book_dialog.wx.TextEntryDialog") as name_dialog:
                        name_dialog.return_value.ShowModal.return_value = wx.ID_OK
                        name_dialog.return_value.GetValue.return_value = "الثاني"
                        dialog.on_confirm_conversation_folder()
                    self.assertIn("الأول", dialog.address_list.GetString(0))
                    self.assertEqual(store.list_items("account-a", first.id), ["sam@example.com"])
                    second = next(
                        folder for folder in store.list_folders("account-a", FOLDER_CONVERSATIONS)
                        if folder.name == "الثاني"
                    )
                    self.assertEqual(store.list_items("account-a", second.id), ["ali@example.com"])
                finally:
                    dialog.Destroy()

    def test_new_address_inside_conversation_folder_is_saved_in_that_folder(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        with tempfile.TemporaryDirectory() as directory:
            store = FolderStore(Path(directory) / "folders.db")
            folder = store.create_folder("account-a", FOLDER_CONVERSATIONS, "الأصدقاء")
            with (
                patch("accessible_mail.address_book_dialog.load_address_book", return_value=[]),
                patch("accessible_mail.address_book_dialog.save_address_book") as save,
                patch("accessible_mail.address_book_dialog.request_custom_address_name", return_value="سام"),
                patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
            ):
                dialog = AddressBookDialog(parent, account_id="account-a")
                try:
                    dialog._open_folder_id = folder.id
                    dialog.refresh_list()
                    with (
                        patch.object(dialog, "request_email", return_value="sam@example.com"),
                        patch("accessible_mail.address_book_dialog.wx.CallAfter") as call_after,
                    ):
                        dialog.on_add(None)
                    self.assertEqual(store.list_items("account-a", folder.id), ["sam@example.com"])
                    save.assert_not_called()
                    self.assertEqual(store.folder_addresses("account-a", folder.id)[0].name, "سام")
                    self.assertIn("سام", dialog.address_list.GetString(dialog.address_list.GetSelection()))
                    call_after.assert_called_once_with(dialog.address_list.SetFocus)
                finally:
                    dialog.Destroy()

    def test_new_address_from_address_book_root_returns_to_address_list(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        store = Mock()
        store.locked_message_hashes.return_value = set()
        store.protected_address_hashes.return_value = set()
        store.folder_addresses.return_value = []
        store.is_locked.return_value = False
        store.list_folders.return_value = []
        with (
            patch("accessible_mail.address_book_dialog.load_address_book", return_value=[]),
            patch("accessible_mail.address_book_dialog.add_address", return_value=(True, "ali@example.com")) as add,
            patch("accessible_mail.address_book_dialog.request_custom_address_name", return_value="علي"),
            patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
        ):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                with (
                    patch.object(dialog, "request_email", return_value="ali@example.com"),
                    patch("accessible_mail.address_book_dialog.wx.CallAfter") as call_after,
                ):
                    dialog.on_add(None)
                add.assert_called_once_with("ali@example.com", "علي")
                self.assertIn("علي", dialog.address_list.GetString(dialog.address_list.GetSelection()))
                store.add_items.assert_not_called()
                call_after.assert_called_once_with(dialog.address_list.SetFocus)
            finally:
                dialog.Destroy()

    def test_conversation_multi_selection_has_its_own_context_menu(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        store = Mock()
        store.locked_message_hashes.return_value = set()
        store.protected_address_hashes.return_value = set()
        store.folder_addresses.return_value = []
        store.is_locked.return_value = False
        store.list_folders.return_value = []
        with (
            patch("accessible_mail.address_book_dialog.load_address_book", return_value=[
                AddressEntry("sam@example.com", name="سام"),
            ]),
            patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
        ):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                dialog.on_create_conversation_folder()
                captured = {}

                def capture_menu(menu):
                    captured["labels"] = [item.GetItemLabelText() for item in menu.GetMenuItems()]
                    captured["enabled"] = {item.GetItemLabelText(): item.IsEnabled() for item in menu.GetMenuItems()}

                with patch.object(dialog.folder_selection_list, "PopupMenu", side_effect=capture_menu):
                    dialog.show_folder_selection_context_menu()
                self.assertIn("تحديد كل المحادثات", captured["labels"])
                self.assertIn("إنشاء المجلد", captured["labels"])
                self.assertIn("إضافة المحادثات المحددة إلى مجلد موجود", captured["labels"])
                self.assertFalse(captured["enabled"]["إنشاء المجلد"])
                dialog.folder_selection_list.CheckItem(0, True)
                with patch.object(dialog.folder_selection_list, "PopupMenu", side_effect=capture_menu):
                    dialog.show_folder_selection_context_menu()
                self.assertTrue(captured["enabled"]["إنشاء المجلد"])
            finally:
                dialog.Destroy()

    def test_conversation_folders_are_rows_in_address_list(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        store = Mock()
        store.locked_message_hashes.return_value = set()
        store.protected_address_hashes.return_value = set()
        store.folder_addresses.return_value = []
        store.is_locked.return_value = False
        store.list_folders.return_value = [
            Folder("folder-1", "account-a", "conversations", "الأصدقاء", item_count=1),
        ]
        store.list_items.return_value = ["sam@example.com"]
        with (
            patch("accessible_mail.address_book_dialog.load_address_book", return_value=[
                AddressEntry("sam@example.com", name="سام"),
            ]),
            patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
        ):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                self.assertFalse(hasattr(dialog, "folder_choice"))
                self.assertFalse(hasattr(dialog, "show_archived_folders"))
                self.assertIn("الأصدقاء", dialog.address_list.GetString(0))
                dialog.address_list.SetSelection(0)
                dialog.on_activate(None)
                self.assertEqual(dialog.selected_folder_id(), "folder-1")
                self.assertEqual(dialog.address_list.GetCount(), 1)
                self.assertIn("سام", dialog.address_list.GetString(0))
                dialog.on_leave_conversation_folder()
                self.assertEqual(dialog.selected_folder_id(), "")
                self.assertIn("الأصدقاء", dialog.address_list.GetString(0))
            finally:
                dialog.Destroy()

    def test_conversation_addresses_move_out_of_root_and_return_when_removed(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        with tempfile.TemporaryDirectory() as directory:
            store = FolderStore(Path(directory) / "folders.db")
            first = store.create_folder(
                "account-a", FOLDER_CONVERSATIONS, "الأصدقاء", ["sam@example.com"],
            )
            with (
                patch("accessible_mail.address_book_dialog.load_address_book", return_value=[
                    AddressEntry("sam@example.com", name="سام"),
                    AddressEntry("ali@example.com", name="علي"),
                ]),
                patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
            ):
                dialog = AddressBookDialog(parent, account_id="account-a")
                try:
                    root_labels = dialog.address_list.GetStrings()
                    self.assertTrue(any("الأصدقاء" in label for label in root_labels))
                    self.assertTrue(any("علي" in label for label in root_labels))
                    self.assertFalse(any("سام" in label for label in root_labels))
                    dialog._open_folder_id = first.id
                    dialog.refresh_list()
                    self.assertEqual(dialog.address_list.GetCount(), 1)
                    self.assertIn("سام", dialog.address_list.GetString(0))
                    dialog.on_remove_conversation_from_folder()
                    dialog.on_leave_conversation_folder()
                    self.assertTrue(any("سام" in label for label in dialog.address_list.GetStrings()))
                finally:
                    dialog.Destroy()

    def test_archived_conversation_folder_can_be_reached_when_root_is_empty(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        with tempfile.TemporaryDirectory() as directory:
            store = FolderStore(Path(directory) / "folders.db")
            folder = store.create_folder(
                "account-a", FOLDER_CONVERSATIONS, "الأرشيف", ["sam@example.com"],
            )
            store.set_archived("account-a", folder.id, True)
            with (
                patch("accessible_mail.address_book_dialog.load_address_book", return_value=[
                    AddressEntry("sam@example.com", name="سام"),
                ]),
                patch("accessible_mail.address_book_dialog.FolderStore", return_value=store),
            ):
                dialog = AddressBookDialog(parent, account_id="account-a")
                try:
                    self.assertEqual(dialog.address_list.GetCount(), 1)
                    captured = {}

                    def capture_menu(menu):
                        captured["labels"] = [item.GetItemLabelText() for item in menu.GetMenuItems()]

                    with patch.object(dialog.address_list, "PopupMenu", side_effect=capture_menu):
                        dialog.show_context_menu()
                    self.assertFalse(any("أرشف" in label or "مؤرشف" in label for label in captured["labels"]))
                    self.assertIn("الأرشيف", dialog.address_list.GetString(0))
                finally:
                    dialog.Destroy()

    def test_folder_reads_live_and_cached_messages_without_changing_server(self) -> None:
        live = MessageSummary(uid="1", mailbox="INBOX", subject="live")
        cached = MessageSummary(uid="2", mailbox="Sent", subject="cached")
        store = Mock()
        store.list_items.return_value = [
            message_folder_key(live), message_folder_key(cached), "invalid"
        ]
        cache = Mock()
        cache.summaries_by_uids.return_value = {"2": cached}
        folder_page = SimpleNamespace(set_messages=Mock())
        pages = {
            "inbox": SimpleNamespace(messages=[live]),
            "spam": SimpleNamespace(messages=[]),
            "sent": SimpleNamespace(messages=[]),
            "all": SimpleNamespace(messages=[]),
            "folders": folder_page,
        }
        account = Account(id="account-a")
        frame = SimpleNamespace(
            selected_account=lambda: account,
            selected_folder_id=lambda: "folder-1",
            folder_store=lambda: store,
            pages=pages,
            service=SimpleNamespace(cache=cache),
            SetStatusText=Mock(),
        )

        MainFrame.load_selected_folder(frame)

        folder_page.set_messages.assert_called_once_with([live, cached])
        cache.summaries_by_uids.assert_called_once_with("account-a", "Sent", ["2"])
        frame.SetStatusText.assert_not_called()


if __name__ == "__main__":
    unittest.main()
