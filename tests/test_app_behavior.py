from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import wx

from accessible_mail.app import (
    AccountDialog,
    BULK_ACTION_DELETE,
    BulkDeleteDialog,
    FILTER_CHOICES,
    FILTER_STARRED,
    MailPage,
    MainFrame,
    UpdateAvailableDialog,
    announce_to_screen_reader,
    run_bulk_operations,
)
from accessible_mail.config import (
    LANGUAGE_ENGLISH,
    THEME_LIGHT,
    TRANSLATION_INLINE,
    VIEWER_HTML,
    ProgramSettings,
)
from accessible_mail.models import Account, MessageSummary
from accessible_mail.oauth import OAuthReauthenticationRequired
from accessible_mail.update_checker import UpdateCheckResult


class AppBehaviorTests(unittest.TestCase):
    @patch("accessible_mail.app.wx.CallAfter", side_effect=lambda function, *args: function(*args))
    @patch("accessible_mail.app.wx.Window.FindFocus", return_value=None)
    @patch("accessible_mail.app.translate_text_with_google", return_value="Translated message")
    def test_inline_translation_updates_either_message_viewer(
        self,
        translate: Mock,
        _find_focus: Mock,
        _call_after: Mock,
    ) -> None:
        summary = SimpleNamespace(uid="message-1")
        page = SimpleNamespace(
            selected_summary=lambda: summary,
            viewer=SimpleNamespace(GetValue=lambda: "Original message"),
            take_translation_return_control=Mock(return_value=None),
            set_viewer_action_ranges=Mock(),
            set_viewer_text=Mock(),
            focus_message_viewer=Mock(),
            restore_context_focus=Mock(),
        )
        frame = SimpleNamespace(
            current_page=lambda: page,
            can_translate_current_message=Mock(return_value=True),
            current_content=SimpleNamespace(summary=summary, text="Original message"),
            settings=ProgramSettings(
                language=LANGUAGE_ENGLISH,
                translation_mode=TRANSLATION_INLINE,
            ),
            run_worker=lambda _message, work, done, _failed: done(work()),
            SetStatusText=Mock(),
            show_translation_dialog=Mock(),
        )

        MainFrame.on_translate_current_message(frame)

        translate.assert_called_once_with("Original message", target_language=LANGUAGE_ENGLISH)
        page.set_viewer_action_ranges.assert_called_once_with("Translated message", [])
        page.set_viewer_text.assert_called_once_with("Translated message")
        page.focus_message_viewer.assert_called_once_with()
        frame.show_translation_dialog.assert_not_called()

    def test_starred_filter_remains_second(self) -> None:
        self.assertEqual(FILTER_CHOICES[1], FILTER_STARRED)

    def test_html_viewer_routes_context_menu_to_application(self) -> None:
        page = SimpleNamespace(
            theme=THEME_LIGHT,
            message_html_content=lambda text: text,
        )

        rendered = MailPage.message_html(page, "message")

        self.assertIn('window.pamBridge.postMessage(command)', rendered)
        self.assertIn('pamSend("context-menu:keyboard")', rendered)
        self.assertIn("EnableContextMenu(False)", inspect.getsource(MailPage._build))
        self.assertIn("request_html_context_menu", inspect.getsource(MailPage.on_html_context_menu))

    def test_rapid_list_navigation_does_not_rebuild_html_before_debounce(self) -> None:
        summary = object()
        page = SimpleNamespace(
            _suppress_selection_event=False,
            visible_messages=[summary],
            on_selected=Mock(),
        )
        event = SimpleNamespace(GetIndex=lambda: 0)

        MailPage.on_item_selected(page, event)

        page.on_selected.assert_called_once_with(page, summary)

    def test_html_refresh_is_deferred_while_message_list_is_active(self) -> None:
        calls: list[str] = []
        refresh_html = Mock()
        page = SimpleNamespace(
            viewer_text="",
            viewer=SimpleNamespace(ChangeValue=lambda text: calls.append(f"text:{text}")),
            viewer_mode=VIEWER_HTML,
            show_plain_viewer=lambda: calls.append("show_plain"),
            _html_refresh_pending=False,
            _html_viewer_active=False,
            refresh_html_viewer=refresh_html,
        )

        MailPage.set_viewer_text(page, "message")

        self.assertEqual(calls, ["text:message", "show_plain"])
        self.assertTrue(page._html_refresh_pending)
        refresh_html.assert_not_called()

    def test_active_html_viewer_refreshes_new_content(self) -> None:
        refresh_html = Mock()
        page = SimpleNamespace(
            viewer_text="",
            viewer=SimpleNamespace(ChangeValue=Mock()),
            viewer_mode=VIEWER_HTML,
            show_html_viewer=Mock(),
            _html_refresh_pending=False,
            _html_viewer_active=True,
            refresh_html_viewer=refresh_html,
        )

        MailPage.set_viewer_text(page, "message")

        refresh_html.assert_called_once_with(focus_start=True)

    def test_activating_html_viewer_loads_pending_content(self) -> None:
        refresh_html = Mock()
        page = SimpleNamespace(
            _html_viewer_active=False,
            _html_refresh_pending=True,
            refresh_html_viewer=refresh_html,
            focus_html_document_start=Mock(),
        )

        MailPage.activate_html_viewer(page)

        self.assertTrue(page._html_viewer_active)
        refresh_html.assert_called_once_with(focus_start=True)
        page.focus_html_document_start.assert_not_called()

    def test_html_focus_script_is_compatible_and_places_text_caret_at_start(self) -> None:
        run_script = Mock()
        page = SimpleNamespace(
            _html_viewer_active=True,
            html_viewer=SimpleNamespace(SetFocus=Mock(), RunScript=run_script),
        )

        MailPage.focus_html_document_start(page)

        script = run_script.call_args.args[0]
        self.assertNotIn("=>", script)
        self.assertNotIn("const ", script)
        self.assertIn("messageElement.focus()", script)
        self.assertIn("collapse(true)", script)

    def test_html_message_root_is_keyboard_accessible_article(self) -> None:
        page = SimpleNamespace(
            viewer_action_ranges=[],
            theme=THEME_LIGHT,
            message_html_content=lambda text: text,
        )

        rendered = MailPage.message_html(page, "Message body")

        self.assertIn('<article id="message" tabindex="0"', rendered)
        self.assertNotIn('role="document"', rendered)

    def test_forward_tab_from_message_list_activates_html_viewer(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_TAB,
            ControlDown=lambda: False,
            ShiftDown=lambda: False,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            viewer_mode=VIEWER_HTML,
            focus_message_viewer=Mock(),
        )

        MailPage.on_list_key(page, event)

        page.focus_message_viewer.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_message_list_uses_native_multiple_selection(self) -> None:
        source = inspect.getsource(MailPage._build)

        self.assertIn("self.list = wx.ListCtrl(self, style=wx.LC_REPORT)", source)
        self.assertIn("self.list.EnableCheckBoxes(False)", source)
        self.assertNotIn("wx.LC_SINGLE_SEL", source)

    def test_checkboxes_are_shown_only_in_multiple_selection_mode(self) -> None:
        enter_source = inspect.getsource(MailPage.enter_multi_selection_mode)
        exit_source = inspect.getsource(MailPage.exit_multi_selection_mode)

        self.assertIn("self.set_multi_selection_checkboxes(True)", enter_source)
        self.assertIn("self.set_multi_selection_checkboxes(False)", exit_source)

    def test_ctrl_shift_space_toggles_multiple_selection_mode(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_SPACE,
            ControlDown=lambda: True,
            ShiftDown=lambda: True,
            AltDown=lambda: False,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            multi_select_mode=False,
            _control_pressed_alone=False,
            toggle_multi_selection_mode=Mock(),
        )

        MailPage.on_list_key(page, event)

        page.toggle_multi_selection_mode.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_space_toggles_focused_item_inside_multiple_selection_mode(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_SPACE,
            ControlDown=lambda: False,
            ShiftDown=lambda: False,
            AltDown=lambda: False,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            multi_select_mode=True,
            _control_pressed_alone=False,
            toggle_focused_message_selection=Mock(),
        )

        MailPage.on_list_key(page, event)

        page.toggle_focused_message_selection.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_control_release_announces_selected_message_count(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_CONTROL,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            multi_select_mode=True,
            _control_pressed_alone=True,
            schedule_selection_count_announcement=Mock(),
        )

        MailPage.on_list_key_up(page, event)

        page.schedule_selection_count_announcement.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_control_key_down_arms_selection_count_announcement(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_CONTROL,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            multi_select_mode=True,
            _control_pressed_alone=False,
        )

        MailPage.on_list_key_down(page, event)

        self.assertTrue(page._control_pressed_alone)
        event.Skip.assert_called_once_with()

    def test_non_control_key_down_cancels_control_only_announcement(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_DOWN,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            multi_select_mode=True,
            _control_pressed_alone=True,
        )

        MailPage.on_list_key_down(page, event)

        self.assertFalse(page._control_pressed_alone)
        event.Skip.assert_called_once_with()

    @patch("accessible_mail.app.wx.CallLater")
    def test_mode_change_notification_is_delayed_one_second(
        self,
        call_later: Mock,
    ) -> None:
        page = SimpleNamespace(
            _multi_mode_notification_call=None,
            _show_multi_selection_mode_notification=Mock(),
        )

        MailPage.schedule_multi_selection_mode_notification(page, "تم التفعيل")

        call_later.assert_called_once_with(
            1000,
            page._show_multi_selection_mode_notification,
            "تم التفعيل",
        )

    @patch("accessible_mail.app.wx.GetTopLevelParent")
    def test_mode_change_notification_uses_unified_in_app_notification(
        self,
        get_parent: Mock,
    ) -> None:
        parent = SimpleNamespace(show_notification=Mock())
        get_parent.return_value = parent
        page = SimpleNamespace(
            _multi_mode_notification_call=object(),
            announce_accessible=Mock(),
        )

        MailPage._show_multi_selection_mode_notification(page, "تم التفعيل")

        self.assertIsNone(page._multi_mode_notification_call)
        parent.show_notification.assert_called_once_with("تم التفعيل")
        page.announce_accessible.assert_not_called()

    @patch("accessible_mail.app.wx.Accessible.NotifyEvent")
    @patch("accessible_mail.app.interrupt_and_speak", return_value=True)
    def test_accessible_announcement_interrupts_nvda_directly(
        self,
        interrupt_and_speak: Mock,
        notify_event: Mock,
    ) -> None:
        control = object()

        announced = announce_to_screen_reader(control, "تم التفعيل")

        self.assertTrue(announced)
        interrupt_and_speak.assert_called_once_with("تم التفعيل")
        notify_event.assert_not_called()

    @patch("accessible_mail.app.wx.Accessible.NotifyEvent")
    @patch("accessible_mail.app.interrupt_and_speak", return_value=False)
    def test_accessible_announcement_falls_back_to_system_alert(
        self,
        interrupt_and_speak: Mock,
        notify_event: Mock,
    ) -> None:
        control = object()

        announced = announce_to_screen_reader(control, "تم التفعيل")

        self.assertTrue(announced)
        interrupt_and_speak.assert_called_once_with("تم التفعيل")
        notify_event.assert_called_once_with(
            wx.ACC_EVENT_SYSTEM_ALERT,
            control,
            wx.OBJID_CLIENT,
            0,
        )

    def test_checked_message_enters_multiple_selection_mode(self) -> None:
        summary = object()
        page = SimpleNamespace(
            _suppress_selection_event=False,
            multi_select_mode=False,
            _multi_selected_keys=set(),
            visible_messages=[summary],
            message_key=Mock(return_value=("INBOX", "1")),
            set_multi_selection_checkboxes=Mock(),
            update_multi_selection_status=Mock(),
            announce_accessible=Mock(),
        )

        MailPage.on_item_check_changed(page, 0, True)

        self.assertTrue(page.multi_select_mode)
        self.assertEqual(page._multi_selected_keys, {("INBOX", "1")})
        page.set_multi_selection_checkboxes.assert_called_once_with(True)
        page.update_multi_selection_status.assert_called_once_with()
        page.announce_accessible.assert_called_once()

    def test_multiple_selection_uses_checked_items_not_focused_row(self) -> None:
        page = SimpleNamespace(
            multi_select_mode=True,
            checked_indices=Mock(return_value=[0, 2]),
            row_selected_indices=Mock(return_value=[1]),
        )

        indices = MailPage.selected_indices(page)

        self.assertEqual(indices, [0, 2])
        page.checked_indices.assert_called_once_with()
        page.row_selected_indices.assert_not_called()

    def test_multiple_selection_announces_list_boundaries(self) -> None:
        list_control = SimpleNamespace(
            GetCountPerPage=lambda: 10,
            SetItemState=Mock(),
            EnsureVisible=Mock(),
        )
        page = SimpleNamespace(
            visible_messages=[object()],
            focused_index=lambda: 0,
            list=list_control,
            announce_accessible=Mock(),
            on_selected=Mock(),
        )

        MailPage.move_multi_selection_focus(page, wx.WXK_UP)
        MailPage.move_multi_selection_focus(page, wx.WXK_DOWN)

        self.assertEqual(
            page.announce_accessible.call_args_list,
            [
                call("بداية قائمة الرسائل."),
                call("نهاية قائمة الرسائل."),
            ],
        )
        list_control.SetItemState.assert_not_called()
        page.on_selected.assert_not_called()

    def test_delete_key_uses_bulk_delete_for_selected_messages(self) -> None:
        summaries = [object(), object()]
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_DELETE,
            ControlDown=lambda: False,
            ShiftDown=lambda: False,
            AltDown=lambda: False,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            multi_select_mode=True,
            _control_pressed_alone=False,
            selected_summaries=Mock(return_value=summaries),
            on_bulk_action=Mock(),
        )

        MailPage.on_list_key(page, event)

        page.on_bulk_action.assert_called_once_with(
            page,
            BULK_ACTION_DELETE,
            summaries,
        )
        event.Skip.assert_not_called()

    def test_multiple_selection_context_menu_contains_only_bulk_actions(self) -> None:
        source = inspect.getsource(MailPage.show_multi_message_context_menu)

        for label in (
            "تعليم كمقروءة",
            "تعليم كغير مقروءة",
            "تمييز الرسائل بنجمة",
            "إزالة النجمة من الرسائل",
            "تثبيت الرسائل في الأعلى",
            "إلغاء تثبيت الرسائل",
            "حذف الرسائل وإرسالها إلى سلة المحذوفات",
        ):
            self.assertIn(label, source)
        self.assertNotIn('tr("رد")', source)
        self.assertNotIn('tr("ترجمة")', source)

    def test_bulk_delete_dialog_has_safe_cancel_and_explicit_delete_buttons(self) -> None:
        source = inspect.getsource(BulkDeleteDialog.__init__)

        self.assertIn('label=tr("إلغاء")', source)
        self.assertIn('label=tr("حذف وإرسال إلى سلة المحذوفات")', source)
        self.assertIn("cancel_button.SetDefault()", source)

    def test_bulk_operations_report_partial_failures(self) -> None:
        summaries = [
            SimpleNamespace(uid="1"),
            SimpleNamespace(uid="2"),
            SimpleNamespace(uid="3"),
        ]

        def operation(summary) -> None:
            if summary.uid == "2":
                raise OSError("failed")

        succeeded, failed = run_bulk_operations(summaries, operation)

        self.assertEqual([summary.uid for summary in succeeded], ["1", "3"])
        self.assertEqual([summary.uid for summary, _exc in failed], ["2"])

    @patch("accessible_mail.app.BulkDeleteDialog")
    def test_bulk_delete_confirms_count_and_focuses_previous_message(
        self,
        dialog_class: Mock,
    ) -> None:
        summaries = [
            MessageSummary(uid="10", mailbox="INBOX"),
            MessageSummary(uid="11", mailbox="INBOX"),
        ]
        dialog_class.return_value.ShowModal.return_value = wx.ID_OK
        page = SimpleNamespace(
            selected_filter_key=lambda: "all",
            selected_indices=lambda: [3, 5],
            remove_messages_bulk=Mock(),
            exit_multi_selection_mode=Mock(),
            previous_message_index=MailPage.previous_message_index,
            focus_list_index=Mock(),
            focus_message_list=Mock(),
        )
        account = Account(id="account", oauth_provider="google_gmail_api")
        service = SimpleNamespace(move_message_to_trash=Mock())
        frame = SimpleNamespace(
            selected_account=lambda: account,
            service=service,
            content_cache={},
            current_content=None,
            pages={"inbox": page},
            SetStatusText=Mock(),
            run_worker=lambda _message, work, done: done(work()),
        )

        MainFrame.on_delete_selected_messages(frame, page, summaries)

        dialog_class.assert_called_once_with(frame, 2)
        self.assertEqual(service.move_message_to_trash.call_count, 2)
        page.remove_messages_bulk.assert_called_once_with(
            summaries,
            match_uid=True,
        )
        page.exit_multi_selection_mode.assert_called_once_with(
            restore_single_selection=False,
        )
        page.focus_list_index.assert_called_once_with(2)
        dialog_class.return_value.Destroy.assert_called_once_with()

    def test_message_list_focus_deactivates_html_viewer(self) -> None:
        event = SimpleNamespace(Skip=Mock())
        page = SimpleNamespace(deactivate_html_viewer=Mock())

        MailPage.on_message_list_focus(page, event)

        page.deactivate_html_viewer.assert_called_once_with()
        event.Skip.assert_called_once_with()

    def test_deactivated_html_viewer_returns_to_plain_preview(self) -> None:
        page = SimpleNamespace(
            _html_viewer_active=True,
            _html_focus_after_load=True,
            viewer_mode=VIEWER_HTML,
            show_plain_viewer=Mock(),
        )

        MailPage.deactivate_html_viewer(page)

        self.assertFalse(page._html_viewer_active)
        self.assertFalse(page._html_focus_after_load)
        page.show_plain_viewer.assert_called_once_with()

    def test_html_navigation_uses_current_wx_navigation_api(self) -> None:
        event = SimpleNamespace(
            GetURL=lambda: "about:blank",
            GetNavigationAction=lambda: 0,
        )
        page = SimpleNamespace(handle_html_command=Mock())

        MailPage.on_html_viewer_navigating(page, event)

        page.handle_html_command.assert_not_called()

    def test_update_dialog_exposes_update_and_close_buttons(self) -> None:
        source = inspect.getsource(UpdateAvailableDialog.__init__)

        self.assertIn('label=tr("تحديث الآن")', source)
        self.assertIn('label=tr("إغلاق")', source)

    @patch("accessible_mail.app.webbrowser.open")
    @patch("accessible_mail.app.UpdateAvailableDialog")
    def test_update_now_opens_installer_url(self, dialog_class: Mock, open_url: Mock) -> None:
        dialog = dialog_class.return_value
        dialog.ShowModal.return_value = wx.ID_OK
        result = UpdateCheckResult(
            configured=True,
            available=True,
            current_version="1.2.7",
            latest_version="1.2.8",
            download_url="https://example.com/PowerAccessibleMailSetup.exe",
        )
        frame = SimpleNamespace(_update_dialog_open=False, SetStatusText=Mock())

        MainFrame.show_update_available(frame, result)

        open_url.assert_called_once_with(result.download_url)
        dialog.Destroy.assert_called_once_with()
        self.assertFalse(frame._update_dialog_open)

    def test_update_mode_skips_normal_installer_pages(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source = (project_root / "installer_power_accessible_mail.iss").read_text(
            encoding="utf-8-sig"
        )
        for page_name in (
            "wpInfoBefore",
            "wpSelectDir",
            "wpSelectProgramGroup",
            "wpSelectTasks",
            "wpReady",
        ):
            self.assertIn(f"PageID = {page_name}", source)

    def test_release_installer_name_uses_target_architecture(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        installer = (project_root / "installer_power_accessible_mail.iss").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "OutputBaseFilename=PowerAccessibleMailSetup-{#MyAppVersion}-win-{#TargetArchitecture}",
            installer,
        )
        self.assertNotIn("FullSetup", installer)
        self.assertNotIn("GmailApiLimited", installer)

    def test_installer_navigation_buttons_use_native_localized_captions(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        installer_path = project_root / "installer_power_accessible_mail.iss"
        raw_source = installer_path.read_bytes()
        self.assertTrue(
            raw_source.startswith(b"\xef\xbb\xbf"),
            "The installer must use UTF-8 BOM so Inno Setup preserves Arabic captions",
        )
        source = raw_source.decode("utf-8-sig")
        self.assertNotIn("arabic.ButtonBack=", source)
        self.assertNotIn("arabic.ButtonNext=", source)
        self.assertNotIn("english.ButtonBack=", source)
        self.assertNotIn("english.ButtonNext=", source)
        self.assertNotIn("NormalNextCaption", source)
        self.assertNotIn("NormalCancelCaption", source)
        for line in source.splitlines():
            if ".ButtonBack=" in line or ".ButtonNext=" in line:
                self.assertNotIn("&", line)
                self.assertNotIn("<", line)
                self.assertNotIn(">", line)

    def test_focus_message_list_deactivates_html_before_returning(self) -> None:
        calls: list[str] = []
        page = SimpleNamespace(
            deactivate_html_viewer=lambda: calls.append("deactivate"),
            list=SimpleNamespace(SetFocus=lambda: calls.append("focus_list")),
            set_status=lambda text: calls.append(text),
        )

        MailPage.focus_message_list(page)

        self.assertEqual(calls, ["deactivate", "focus_list", "قائمة الرسائل."])

    def test_loaded_message_enables_translation_from_actions(self) -> None:
        page = SimpleNamespace(
            viewer_text="نص الرسالة",
            selected_summary=lambda: object(),
        )

        self.assertTrue(MailPage.has_translatable_content(page))

    @patch("accessible_mail.app.wx.CallAfter", side_effect=lambda function, *args: function(*args))
    @patch("accessible_mail.app.save_accounts")
    def test_account_success_uses_in_app_notification(
        self,
        _save_accounts: Mock,
        _call_after: Mock,
    ) -> None:
        account = Account(email_address="new@example.com")
        dialog = SimpleNamespace(
            ShowModal=lambda: wx.ID_OK,
            account=account,
            Destroy=Mock(),
        )
        frame = SimpleNamespace(
            accounts=[],
            _load_accounts_to_choice=Mock(),
            show_notification=Mock(),
            account_choice=SimpleNamespace(SetFocus=Mock()),
        )

        MainFrame.finish_account_dialog(frame, dialog)

        frame.show_notification.assert_called_once_with("تمت إضافة الحساب بنجاح.")
        dialog.Destroy.assert_called_once_with()

    def test_oauth_provider_button_starts_login_directly(self) -> None:
        dialog = SimpleNamespace(start_oauth_login=Mock())

        AccountDialog.on_oauth_provider_button(dialog, Mock(), "google_gmail_api")

        dialog.start_oauth_login.assert_called_once_with("google_gmail_api")

    @patch("accessible_mail.app.google_provider_id", return_value="google_gmail_api")
    def test_startup_google_button_starts_gmail_api_provider(
        self,
        provider_id: Mock,
    ) -> None:
        dialog = SimpleNamespace(start_oauth_login=Mock())

        AccountDialog.on_continue_with_google(dialog, Mock())

        provider_id.assert_called_once_with()
        dialog.start_oauth_login.assert_called_once_with("google_gmail_api")

    def test_startup_login_uses_requested_accessible_control_order(self) -> None:
        source = inspect.getsource(AccountDialog.show_startup_view)
        ordered_labels = (
            "مرحبا بكم في برنامج Power Accessible Mail",
            "شعار Power Accessible Mail",
            "عنوان البريد الإلكتروني:",
            "كلمة المرور:",
            "تسجيل الدخول بالبريد وكلمة المرور",
            "الاستمرار مع Google",
            "الاستمرار بدون إضافة حساب",
        )
        positions = [source.index(label) for label in ordered_labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("self.finish_panel(root, self.startup_email)", source)

    def test_basic_gmail_login_configures_manual_mail_servers(self) -> None:
        account = Account(email_address="person@gmail.com")

        configured = AccountDialog.configure_known_manual_provider(account)

        self.assertTrue(configured)
        self.assertEqual(account.imap_server, "imap.gmail.com")
        self.assertEqual(account.smtp_server, "smtp.gmail.com")
        self.assertEqual(account.smtp_port, 587)

    def test_unknown_manual_provider_requires_detailed_server_view(self) -> None:
        account = Account(email_address="person@example.org")

        self.assertFalse(AccountDialog.configure_known_manual_provider(account))

    def test_valid_startup_email_and_password_finish_account_login(self) -> None:
        account = Account()
        dialog = SimpleNamespace(
            startup_email=SimpleNamespace(GetValue=lambda: "person@gmail.com"),
            startup_password=SimpleNamespace(GetValue=lambda: "app-password"),
            account=account,
            configure_known_manual_provider=AccountDialog.configure_known_manual_provider,
            EndModal=Mock(),
        )

        AccountDialog.on_startup_manual_login(dialog, Mock())

        self.assertEqual(account.auth_method, "password")
        self.assertEqual(account.email_address, "person@gmail.com")
        self.assertTrue(account.save_password)
        dialog.EndModal.assert_called_once_with(wx.ID_OK)

    def test_startup_welcome_uses_in_app_notification(self) -> None:
        frame = SimpleNamespace(show_notification=Mock())

        MainFrame.show_welcome_notification(frame)

        frame.show_notification.assert_called_once_with(
            "مرحبا بكم في برنامج Power Accessible Mail"
        )

    @patch("accessible_mail.app.wx.CallLater")
    @patch("accessible_mail.app.announce_to_screen_reader")
    def test_in_app_notification_uses_interrupting_screen_reader_path(
        self,
        announce: Mock,
        call_later: Mock,
    ) -> None:
        frame = SimpleNamespace(
            _notification_timer=None,
            notification_bar=SimpleNamespace(
                SetName=Mock(),
                ShowMessage=Mock(),
            ),
            SetStatusText=Mock(),
            main_panel=SimpleNamespace(Layout=Mock()),
            dismiss_notification=Mock(),
        )

        MainFrame.show_notification(frame, "تم التفعيل")

        frame.notification_bar.SetName.assert_called_once_with("تم التفعيل")
        frame.notification_bar.ShowMessage.assert_called_once_with(
            "تم التفعيل",
            wx.ICON_INFORMATION,
        )
        announce.assert_called_once_with(
            frame.notification_bar,
            "تم التفعيل",
        )
        call_later.assert_called_once_with(8000, frame.dismiss_notification)

    def test_both_builds_bundle_the_nvda_controller_client(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source = (project_root / "build_power_accessible_mail.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn('"--add-binary"', source)
        self.assertIn("$Architecture\\nvdaControllerClient.dll", source)
        self.assertIn("Expected exactly one bundled NVDA Controller", source)

    def test_account_method_buttons_activate_without_ok_button(self) -> None:
        dialog = SimpleNamespace(
            show_oauth_provider_view=Mock(),
            show_manual_view=Mock(),
        )

        AccountDialog.on_browser_method(dialog, Mock())
        AccountDialog.on_manual_method(dialog, Mock())

        dialog.show_oauth_provider_view.assert_called_once_with()
        dialog.show_manual_view.assert_called_once_with()
        method_source = inspect.getsource(AccountDialog.show_method_view)
        self.assertNotIn('label="موافق"', method_source)

    def test_escape_from_account_dialog_returns_to_main_interface(self) -> None:
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_ESCAPE, Skip=Mock())
        dialog = SimpleNamespace(close_to_main_interface=Mock())

        AccountDialog.on_dialog_key(dialog, event)

        dialog.close_to_main_interface.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_backspace_returns_to_previous_account_view(self) -> None:
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_BACK, Skip=Mock())
        dialog = SimpleNamespace(mode="oauth2", on_back=Mock())

        AccountDialog.on_dialog_key(dialog, event)

        dialog.on_back.assert_called_once_with()
        event.Skip.assert_not_called()

    @patch("accessible_mail.app.wx.CallAfter", side_effect=lambda function, *args: function(*args))
    @patch("accessible_mail.app.AccountDialog")
    def test_initial_login_is_shown_only_when_no_account_exists(
        self,
        dialog_class: Mock,
        _call_after: Mock,
    ) -> None:
        frame_with_account = SimpleNamespace(
            accounts=[Account(email_address="existing@example.com")],
            _startup_login_shown=False,
        )
        MainFrame.show_initial_login_if_needed(frame_with_account)
        dialog_class.assert_not_called()

        frame_without_account = SimpleNamespace(
            accounts=[],
            _startup_login_shown=False,
            finish_account_dialog=Mock(return_value=False),
            command_list=SimpleNamespace(SetFocus=Mock()),
        )
        MainFrame.show_initial_login_if_needed(frame_without_account)

        dialog_class.assert_called_once_with(frame_without_account, startup=True)
        self.assertTrue(frame_without_account._startup_login_shown)
        frame_without_account.command_list.SetFocus.assert_called_once_with()

    def test_oauth_services_have_no_ok_button_but_manual_form_keeps_it(self) -> None:
        oauth_source = inspect.getsource(AccountDialog.show_oauth_provider_view)
        manual_source = inspect.getsource(AccountDialog.show_manual_view)

        self.assertNotIn('label="موافق"', oauth_source)
        self.assertIn("on_oauth_provider_button", oauth_source)
        self.assertIn('label="موافق"', manual_source)
        self.assertIn("on_manual_ok", manual_source)

    def test_html_context_menu_uses_page_as_popup_owner(self) -> None:
        html_viewer = object()
        other_control = object()
        page = SimpleNamespace(html_viewer=html_viewer)

        self.assertIs(MailPage.context_menu_popup_owner(page, html_viewer), page)
        self.assertIs(MailPage.context_menu_popup_owner(page, other_control), other_control)

    def test_returning_to_html_viewer_hides_items_panel(self) -> None:
        calls: list[str] = []
        page = SimpleNamespace(
            viewer_mode=VIEWER_HTML,
            link_panel_visible_in_html=True,
            update_link_panel_visibility=lambda: calls.append("visibility"),
            layout_viewer_area=lambda: calls.append("layout"),
            activate_html_viewer=lambda: calls.append("activate_html"),
            viewer=SimpleNamespace(SetFocus=lambda: calls.append("focus_text")),
            set_status=lambda text: calls.append(text),
        )

        MailPage.focus_message_viewer(page)

        self.assertFalse(page.link_panel_visible_in_html)
        self.assertEqual(
            calls,
            [
                "visibility",
                "layout",
                "activate_html",
                "مستعرض الرسالة.",
            ],
        )

    def test_deleted_message_focuses_previous_index(self) -> None:
        self.assertEqual(MailPage.previous_message_index(8), 7)
        self.assertEqual(MailPage.previous_message_index(0), 0)

    @patch("accessible_mail.app.wx.MessageBox")
    def test_expired_oauth_is_handled_without_error_dialog(self, message_box: Mock) -> None:
        frame = SimpleNamespace(
            _active_worker_count=1,
            set_busy=Mock(),
            SetStatusText=Mock(),
            reset_transfer_progress=Mock(),
            handle_oauth_reauthentication_required=Mock(),
        )
        error = OAuthReauthenticationRequired("أعد تسجيل الدخول")

        MainFrame.on_worker_error(frame, error)

        frame.handle_oauth_reauthentication_required.assert_called_once_with(error)
        message_box.assert_not_called()
