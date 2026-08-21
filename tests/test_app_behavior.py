from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import wx

from accessible_mail.accessibility import message_box, should_announce_status
from accessible_mail.account_dialog import (
    SignInResultDialog,
    sanitize_sign_in_diagnostic,
    sign_in_error_details,
)
from accessible_mail.address_book_dialog import AddressBookDialog
from accessible_mail.dialogs import SettingsDialog, SpokenNotificationsDialog
from accessible_mail.email_service import MailError
from accessible_mail.app import (
    AccountDialog,
    BULK_ACTION_DELETE,
    BulkDeleteDialog,
    ComposeDialog,
    FILTER_CHOICES,
    FILTER_STARRED,
    MANUAL_PROVIDER_GOOGLE,
    MANUAL_PROVIDER_MICROSOFT,
    MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS,
    MailPage,
    MainFrame,
    UpdateAvailableDialog,
    UpdateDownloadDialog,
    announce_to_screen_reader,
    run,
    run_bulk_operations,
)
from accessible_mail.main_frame import call_after_if_open
from accessible_mail.config import (
    LANGUAGE_ENGLISH,
    MESSAGE_READ_MANUAL,
    MESSAGE_READ_ON_VIEWER_ENTER,
    THEME_LIGHT,
    TRANSLATION_INLINE,
    VIEWER_HTML,
    VIEWER_SIMPLE,
    ProgramSettings,
)
from accessible_mail.models import Account, LinkItem, MessageContent, MessageSummary
from accessible_mail.oauth import OAuthFlowResult, OAuthReauthenticationRequired
from accessible_mail.notification_preferences import (
    NOTIFICATION_LEVEL_NONE,
    preset_event_ids,
)
from accessible_mail.update_checker import UpdateCheckResult


class AppBehaviorTests(unittest.TestCase):
    @patch("accessible_mail.app.wx.CallAfter")
    @patch("accessible_mail.app.MainFrame")
    @patch("accessible_mail.app.AccessibleMailApp")
    def test_mailto_launch_opens_a_prefilled_compose_window(
        self,
        app_class: Mock,
        frame_class: Mock,
        call_after: Mock,
    ) -> None:
        frame = frame_class.return_value

        run(
            [
                "mailto:person@example.com?"
                "subject=Hello&body=Message%20body"
            ]
        )

        frame.Show.assert_called_once_with()
        call_after.assert_called_once_with(
            frame.open_compose_dialog,
            "person@example.com",
            "Hello",
            "Message body",
        )
        app_class.return_value.MainLoop.assert_called_once_with()

    @patch("accessible_mail.main_frame.ComposeDialog")
    def test_compose_window_receives_all_supported_mailto_fields(
        self,
        dialog_class: Mock,
    ) -> None:
        account = Mock()
        dialog_class.return_value.ShowModal.return_value = wx.ID_CANCEL
        frame = SimpleNamespace(
            selected_account=Mock(return_value=account),
            ensure_password=Mock(return_value=True),
        )

        MainFrame.open_compose_dialog(
            frame,
            "person@example.com",
            "Prefilled subject",
            "Prefilled body",
        )

        dialog_class.assert_called_once_with(
            frame,
            to_address="person@example.com",
            subject="Prefilled subject",
            body="Prefilled body",
        )
        dialog_class.return_value.Destroy.assert_called_once_with()

    @patch("accessible_mail.main_frame.wx.CallAfter")
    def test_delayed_ui_callback_is_ignored_after_close(
        self,
        call_after: Mock,
    ) -> None:
        owner = SimpleNamespace(_closing=False)
        callback = Mock()

        call_after_if_open(owner, callback, "result")
        queued_callback = call_after.call_args.args[0]
        owner._closing = True
        queued_callback()

        callback.assert_not_called()

    @patch("accessible_mail.main_frame.cleanup_opened_attachment_session")
    def test_close_stops_background_activity_and_cleans_session(
        self,
        cleanup_attachments: Mock,
    ) -> None:
        delayed_calls = [
            SimpleNamespace(IsRunning=lambda: True, Stop=Mock())
            for _index in range(3)
        ]
        timer = SimpleNamespace(Stop=Mock())
        cancel_event = SimpleNamespace(set=Mock())
        event = SimpleNamespace(Skip=Mock())
        frame = SimpleNamespace(
            _closing=False,
            _message_load_call=delayed_calls[0],
            _notification_timer=delayed_calls[1],
            _startup_update_call=delayed_calls[2],
            new_mail_timer=timer,
            _update_cancel_event=cancel_event,
        )

        MainFrame.on_close(frame, event)

        self.assertTrue(frame._closing)
        for delayed_call in delayed_calls:
            delayed_call.Stop.assert_called_once_with()
        timer.Stop.assert_called_once_with()
        cancel_event.set.assert_called_once_with()
        cleanup_attachments.assert_called_once_with()
        event.Skip.assert_called_once_with()

    @patch("accessible_mail.app.wx.CallAfter", side_effect=lambda function, *args: function(*args))
    @patch("accessible_mail.app.wx.Window.FindFocus", return_value=None)
    @patch(
        "accessible_mail.main_frame.translate_text_with_google",
        return_value="Translated message",
    )
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
            translatable_item_descriptions=Mock(return_value=["Website"]),
            show_translated_content=Mock(return_value=7),
            restore_context_focus=Mock(),
        )
        frame = SimpleNamespace(
            current_page=lambda: page,
            can_translate_current_message=Mock(return_value=True),
            confirm_translation_data_transfer=Mock(return_value=True),
            current_content=SimpleNamespace(summary=summary, text="Original message"),
            settings=ProgramSettings(
                language=LANGUAGE_ENGLISH,
                translation_mode=TRANSLATION_INLINE,
            ),
            run_worker=lambda _message, work, done, _failed: done(work()),
            SetStatusText=Mock(),
            show_translation_dialog=Mock(),
            start_background_item_description_translation=Mock(),
        )

        MainFrame.on_translate_current_message(frame)

        translate.assert_called_once_with(
            "Original message", target_language=LANGUAGE_ENGLISH
        )
        page.show_translated_content.assert_called_once_with("Translated message")
        frame.start_background_item_description_translation.assert_called_once_with(
            page,
            "message-1",
            ["Website"],
            7,
        )
        frame.SetStatusText.assert_any_call(
            "تمت ترجمة نص الرسالة، وجار ترجمة أوصاف العناصر في الخلفية."
        )
        self.assertEqual(page.restore_context_focus.call_count, 2)
        frame.show_translation_dialog.assert_not_called()

    @patch("accessible_mail.app.wx.CallAfter", side_effect=lambda function, *args: function(*args))
    @patch("accessible_mail.app.wx.Window.FindFocus", return_value=None)
    @patch(
        "accessible_mail.main_frame.translate_text_with_google",
        return_value="Translated message",
    )
    def test_late_inline_translation_does_not_replace_another_message(
        self,
        _translate: Mock,
        _find_focus: Mock,
        _call_after: Mock,
    ) -> None:
        original_summary = SimpleNamespace(uid="message-1")
        current_summary = SimpleNamespace(uid="message-2")
        page = SimpleNamespace(
            selected_summary=Mock(side_effect=[original_summary, current_summary]),
            viewer=SimpleNamespace(GetValue=lambda: "Original message"),
            take_translation_return_control=Mock(return_value=None),
            translatable_item_descriptions=Mock(return_value=[]),
            show_translated_content=Mock(),
            restore_context_focus=Mock(),
        )
        frame = SimpleNamespace(
            current_page=lambda: page,
            can_translate_current_message=Mock(return_value=True),
            confirm_translation_data_transfer=Mock(return_value=True),
            current_content=SimpleNamespace(
                summary=original_summary,
                text="Original message",
            ),
            settings=ProgramSettings(
                language=LANGUAGE_ENGLISH,
                translation_mode=TRANSLATION_INLINE,
            ),
            run_worker=lambda _message, work, done, _failed: done(work()),
            SetStatusText=Mock(),
            show_translation_dialog=Mock(),
        )

        MainFrame.on_translate_current_message(frame)

        page.show_translated_content.assert_not_called()
        frame.SetStatusText.assert_any_call(
            "اكتملت ترجمة الرسالة السابقة دون تغيير الرسالة الحالية."
        )

    @patch("accessible_mail.main_frame.translate_text_with_google")
    def test_background_description_failure_preserves_original_description(
        self,
        translate: Mock,
    ) -> None:
        def translate_value(value: str, *, target_language: str) -> str:
            self.assertEqual(target_language, LANGUAGE_ENGLISH)
            if value == "Website":
                raise MailError("description failed")
            return "Translated button"

        translate.side_effect = translate_value
        summary = SimpleNamespace(uid="message-1")
        page = SimpleNamespace(
            selected_summary=lambda: summary,
            show_translated_item_descriptions=Mock(return_value=True),
        )
        frame = SimpleNamespace(
            settings=ProgramSettings(
                language=LANGUAGE_ENGLISH,
                translation_mode=TRANSLATION_INLINE,
            ),
            run_worker=lambda _message, work, done: done(work()),
            SetStatusText=Mock(),
        )

        MainFrame.start_background_item_description_translation(
            frame,
            page,
            "message-1",
            ["Website", "Button"],
            7,
        )

        page.show_translated_item_descriptions.assert_called_once_with(
            {"Website": "Website", "Button": "Translated button"},
            7,
        )
        frame.SetStatusText.assert_any_call(
            "اكتملت ترجمة أوصاف العناصر في الخلفية، وتعذر ترجمة بعضها."
        )

    def test_inline_translation_refreshes_items_and_preserves_attachments(self) -> None:
        link = LinkItem(
            "Website",
            "https://example.com",
            context_text="Visit the website to read all release details.",
        )
        attachment = LinkItem(
            "manual.pdf",
            kind="attachment",
            filename="manual.pdf",
            data="AA==",
        )
        page = SimpleNamespace(
            _translation_generation=0,
            links=[link, attachment],
            set_links=Mock(),
            set_viewer_action_ranges=Mock(),
            set_viewer_text=Mock(),
        )

        def update_links(items: list[LinkItem], *, message_text: str) -> None:
            self.assertEqual(message_text, "Translated message")
            page.links = items

        page.set_links.side_effect = update_links

        generation = MailPage.show_translated_content(
            page,
            "Translated message",
            {
                "Website": "Translated website",
                "Visit the website to read all release details.": "Translated context.",
            },
        )

        self.assertEqual(generation, 1)

        translated_items = page.set_links.call_args.args[0]
        self.assertEqual(translated_items[0].text, "Translated website")
        self.assertEqual(translated_items[0].context_text, "Translated context.")
        self.assertEqual(translated_items[0].url, "https://example.com")
        self.assertEqual(translated_items[1].filename, "manual.pdf")
        page.set_viewer_action_ranges.assert_called_once_with(
            "Translated message",
            translated_items,
        )
        page.set_viewer_text.assert_called_once_with("Translated message")
        self.assertEqual(page.links[1].attachment_bytes(), b"\x00")

    def test_background_item_translation_does_not_reload_message_viewer(self) -> None:
        page = SimpleNamespace(
            _translation_generation=2,
            links=[LinkItem("Website", "https://example.com")],
            viewer_text="Translated message",
            set_links=Mock(),
        )

        self.assertFalse(
            MailPage.show_translated_item_descriptions(
                page,
                {"Website": "Old translation"},
                1,
            )
        )
        page.set_links.assert_not_called()

        self.assertTrue(
            MailPage.show_translated_item_descriptions(
                page,
                {"Website": "Translated website"},
                2,
            )
        )
        translated_items = page.set_links.call_args.args[0]
        self.assertEqual(translated_items[0].text, "Translated website")
        self.assertEqual(translated_items[0].url, "https://example.com")
        self.assertEqual(
            page.set_links.call_args.kwargs["message_text"],
            "Translated message",
        )

    def test_only_human_item_descriptions_are_sent_for_translation(self) -> None:
        page = SimpleNamespace(
            links=[
                LinkItem(
                    "Project website",
                    "https://example.com",
                    activation_text="Open website",
                ),
                LinkItem("https://example.net", "https://example.net"),
                LinkItem(
                    "manual.pdf",
                    kind="attachment",
                    filename="manual.pdf",
                ),
                LinkItem("Company logo", "cid:logo", kind="image"),
                LinkItem(
                    "Release notes",
                    "https://example.org/release",
                    context_text="Read the complete release notes before updating.",
                ),
            ]
        )

        descriptions = MailPage.translatable_item_descriptions(page)

        self.assertEqual(
            descriptions,
            [
                "Project website",
                "Open website",
                "Company logo",
                "Release notes",
                "Read the complete release notes before updating.",
            ],
        )

    @patch("accessible_mail.main_frame.save_settings")
    @patch("accessible_mail.main_frame.wx.MessageDialog")
    def test_first_translation_consent_is_saved(
        self,
        dialog_class: Mock,
        save: Mock,
    ) -> None:
        dialog = dialog_class.return_value
        dialog.ShowModal.return_value = wx.ID_YES
        settings = ProgramSettings()
        frame = SimpleNamespace(settings=settings, SetStatusText=Mock())

        accepted = MainFrame.confirm_translation_data_transfer(frame)

        self.assertTrue(accepted)
        self.assertTrue(settings.translation_data_notice_accepted)
        dialog.SetYesNoLabels.assert_called_once_with(
            "السماح",
            "إلغاء",
        )
        dialog_style = dialog_class.call_args.args[3]
        consent_text = dialog_class.call_args.args[1]
        self.assertIn("أوصاف الروابط والأزرار والصور", consent_text)
        self.assertIn("لن تُرسل محتويات المرفقات", consent_text)
        self.assertFalse(dialog_style & wx.NO_DEFAULT)
        dialog.Destroy.assert_called_once_with()
        save.assert_called_once_with(settings)

    @patch("accessible_mail.main_frame.save_settings")
    @patch("accessible_mail.main_frame.wx.MessageDialog")
    def test_translation_consent_can_be_canceled_before_sending_text(
        self,
        dialog_class: Mock,
        save: Mock,
    ) -> None:
        dialog = dialog_class.return_value
        dialog.ShowModal.return_value = wx.ID_NO
        settings = ProgramSettings()
        frame = SimpleNamespace(settings=settings, SetStatusText=Mock())

        accepted = MainFrame.confirm_translation_data_transfer(frame)

        self.assertFalse(accepted)
        self.assertFalse(settings.translation_data_notice_accepted)
        save.assert_not_called()
        frame.SetStatusText.assert_called_once_with(
            "ألغيت ترجمة الرسالة قبل إرسال النص."
        )
        dialog.Destroy.assert_called_once_with()

    @patch("accessible_mail.main_frame.wx.MessageDialog")
    def test_saved_translation_consent_skips_the_dialog(
        self,
        dialog_class: Mock,
    ) -> None:
        frame = SimpleNamespace(
            settings=ProgramSettings(translation_data_notice_accepted=True)
        )

        self.assertTrue(MainFrame.confirm_translation_data_transfer(frame))
        dialog_class.assert_not_called()

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
        self.assertIn('pamSend("focus-list")', rendered)
        self.assertIn('event.key === "Escape"', rendered)
        self.assertNotIn('"Spacebar"', rendered)
        self.assertIn("}, true);", rendered)
        self.assertIn("EnableContextMenu(False)", inspect.getsource(MailPage._build))
        self.assertIn("request_html_context_menu", inspect.getsource(MailPage.on_html_context_menu))

    def test_html_viewer_routes_link_activation_through_the_application(self) -> None:
        page = SimpleNamespace(
            theme=THEME_LIGHT,
            message_html_content=lambda text: text,
        )

        rendered = MailPage.message_html(page, "message")

        self.assertIn('document.addEventListener("click"', rendered)
        self.assertIn('pamActionCommand("open-action", event.target)', rendered)
        self.assertIn('document.addEventListener("contextmenu"', rendered)
        self.assertIn('pamSend("context-menu:pointer")', rendered)
        self.assertNotIn('pamActionCommand("context-action"', rendered)
        self.assertIn('event.key === " "', rendered)
        self.assertIn("!event.repeat", rendered)

    def test_html_viewer_does_not_add_a_duplicate_links_and_items_section(self) -> None:
        page = SimpleNamespace(
            theme=THEME_LIGHT,
            message_html_content=lambda text: text,
        )

        rendered = MailPage.message_html(page, "نص الرسالة")

        self.assertNotIn('<nav class="message-actions"', rendered)
        self.assertNotIn('id="viewer-instructions"', rendered)
        self.assertNotIn("aria-describedby", rendered)
        self.assertNotIn("aria-keyshortcuts", rendered)
        self.assertNotIn("Tab وShift+Tab", rendered)
        self.assertNotIn("اضغط Enter أو Space", rendered)

    def test_html_viewer_places_only_the_item_shortcut_note_after_message(self) -> None:
        page = SimpleNamespace(
            theme=THEME_LIGHT,
            message_html_content=lambda text: text,
        )

        rendered = MailPage.message_html(page, "نص الرسالة")

        note = "يمكن الوصول إلى قائمة روابط وعناصر الرسالة بالضغط على Control مع Enter."
        self.assertIn(note, rendered)
        self.assertLess(
            rendered.index('<div class="message-content">نص الرسالة</div>'),
            rendered.index('<p class="items-shortcut-note">'),
        )

    def test_inline_html_link_has_program_action_without_spoken_shortcut_metadata(self) -> None:
        item = LinkItem("الموقع", "https://example.com")
        page = SimpleNamespace(links=[item])
        page.html_action_items = lambda: MailPage.html_action_items(page)
        page.html_action_index = lambda value: MailPage.html_action_index(page, value)

        rendered = MailPage.message_html_action(page, "الموقع", item)

        self.assertIn('data-pam-action="0"', rendered)
        self.assertNotIn("aria-keyshortcuts", rendered)

    @patch("accessible_mail.mail_page.wx.CallAfter")
    def test_html_open_action_command_validates_index_before_dispatch(
        self,
        call_after: Mock,
    ) -> None:
        item = LinkItem("الموقع", "https://example.com")
        page = SimpleNamespace(
            html_action_items=lambda: [item],
            open_html_action=Mock(),
            schedule_html_focus_action=Mock(),
            request_html_context_menu=Mock(),
        )
        page.parse_html_action_index = lambda value: MailPage.parse_html_action_index(
            page, value
        )

        self.assertTrue(MailPage.handle_html_command(page, "open-action:0"))
        call_after.assert_called_once_with(page.open_html_action, 0)

        call_after.reset_mock()
        self.assertFalse(MailPage.handle_html_command(page, "open-action:99"))
        self.assertFalse(MailPage.handle_html_command(page, "open-action:not-a-number"))
        call_after.assert_not_called()

    @patch("accessible_mail.mail_page.wx.CallAfter")
    def test_html_context_action_cannot_open_the_item_viewer_menu(
        self,
        call_after: Mock,
    ) -> None:
        item = LinkItem("الموقع", "https://example.com")
        page = SimpleNamespace(
            html_action_items=lambda: [item],
            open_html_action=Mock(),
            schedule_html_focus_action=Mock(),
            request_html_context_menu=Mock(),
        )
        page.parse_html_action_index = lambda value: MailPage.parse_html_action_index(
            page, value
        )

        self.assertFalse(MailPage.handle_html_command(page, "context-action:0"))

        call_after.assert_not_called()

    def test_open_html_action_uses_the_same_secure_item_handler(self) -> None:
        item = LinkItem("الموقع", "https://example.com")
        page = SimpleNamespace(
            html_action_items=lambda: [item],
            open_item=Mock(),
        )

        MailPage.open_html_action(page, 0)
        MailPage.open_html_action(page, 3)

        page.open_item.assert_called_once_with(item)

    def test_item_menu_requested_from_html_is_redirected_to_message_menu(self) -> None:
        item = LinkItem("الموقع", "https://example.com")
        html_viewer = object()
        link_list = object()
        actions_button = object()
        page = SimpleNamespace(
            link_list=link_list,
            actions_button=actions_button,
            show_message_context_menu=Mock(),
            has_translatable_content=Mock(return_value=True),
        )

        MailPage.show_item_menu(page, html_viewer, item)

        page.show_message_context_menu.assert_called_once_with(html_viewer, True)

    def test_message_text_urls_are_discovered_for_html_keyboard_navigation(self) -> None:
        link_list = Mock()
        page = SimpleNamespace(
            links=[],
            link_list=link_list,
            viewer_action_ranges=[],
            current_viewer_action_range=None,
            resource_labels=lambda links: [item.label for item in links],
        )

        MailPage.set_links(
            page,
            [],
            message_text="قم بزيارة https://example.com/help للحصول على المساعدة",
        )

        self.assertEqual(len(page.links), 1)
        self.assertEqual(page.links[0].url, "https://example.com/help")
        link_list.SetSelection.assert_called_once_with(0)

    @patch("accessible_mail.mail_page.time.monotonic", return_value=10.0)
    @patch("accessible_mail.mail_page.wx.CallAfter")
    def test_html_context_menu_request_uses_current_translation_state(
        self,
        call_after: Mock,
        _monotonic: Mock,
    ) -> None:
        html_viewer = object()
        page = SimpleNamespace(
            _last_context_menu_request_at=0.0,
            html_viewer=html_viewer,
            has_translatable_content=Mock(return_value=True),
            show_message_context_menu=Mock(),
        )

        MailPage.request_html_context_menu(page)

        call_after.assert_called_once_with(
            page.show_message_context_menu,
            html_viewer,
            True,
        )

    @patch("accessible_mail.mail_page.wx.CallAfter")
    @patch("accessible_mail.mail_page.announce_context_menu")
    @patch("accessible_mail.mail_page.wx.Menu")
    def test_html_context_menu_builds_and_restores_focus_without_native_menu(
        self,
        menu_class: Mock,
        announce_menu: Mock,
        call_after: Mock,
    ) -> None:
        summary = MessageSummary(uid="1", mailbox="INBOX")
        menu = menu_class.return_value
        items = [Mock() for _index in range(6)]
        menu.Append.side_effect = items
        html_viewer = object()
        popup_owner = SimpleNamespace(PopupMenu=Mock())
        page = SimpleNamespace(
            actions_button=object(),
            html_viewer=html_viewer,
            multi_select_mode=False,
            selected_summaries=lambda: [summary],
            selected_summary=lambda: summary,
            context_return_control=lambda control: control,
            context_menu_popup_owner=lambda _control: popup_owner,
            on_reply=Mock(),
            on_toggle_star=Mock(),
            on_toggle_read=Mock(),
            on_translate=Mock(),
            on_toggle_pin=Mock(),
            on_delete=Mock(),
            focus_message_list=Mock(),
            focus_list_index=Mock(),
            restore_context_focus=Mock(),
            _translation_return_control=None,
        )

        MailPage.show_message_context_menu(page, html_viewer, True)

        popup_owner.PopupMenu.assert_called_once_with(menu)
        announce_menu.assert_called_once_with(html_viewer)
        call_after.assert_called_once_with(page.restore_context_focus, html_viewer)
        menu.Destroy.assert_called_once_with()

    @patch("accessible_mail.mail_page.tr", side_effect=lambda value: value)
    @patch("accessible_mail.mail_page.wx.CallAfter")
    @patch("accessible_mail.mail_page.announce_context_menu")
    @patch("accessible_mail.mail_page.wx.Menu")
    def test_message_viewer_context_menu_starts_with_reply_copy_translate(
        self,
        menu_class: Mock,
        _announce_menu: Mock,
        _call_after: Mock,
        _translate: Mock,
    ) -> None:
        summary = MessageSummary(uid="1", mailbox="INBOX", is_read=True)
        menu = menu_class.return_value
        menu.Append.side_effect = lambda *_args: Mock()
        viewer = object()
        page = SimpleNamespace(
            actions_button=object(),
            viewer=viewer,
            html_viewer=object(),
            list=object(),
            viewer_text="نص الرسالة",
            multi_select_mode=False,
            selected_summaries=lambda: [summary],
            selected_summary=lambda: summary,
            context_return_control=lambda control: control,
            context_menu_popup_owner=lambda _control: SimpleNamespace(PopupMenu=Mock()),
            on_reply=Mock(),
            copy_message_viewer_text=Mock(),
            on_toggle_star=Mock(),
            on_toggle_read=Mock(),
            on_translate=Mock(),
            on_toggle_pin=Mock(),
            on_delete=Mock(),
            focus_message_list=Mock(),
            focus_list_index=Mock(),
            restore_context_focus=Mock(),
            _translation_return_control=None,
        )

        MailPage.show_message_context_menu(page, viewer, True)

        labels = [call.args[1] for call in menu.Append.call_args_list]
        self.assertEqual(labels[:3], ["رد", "نسخ", "ترجمة"])
        self.assertNotIn("التثبيت في الأعلى", labels)
        self.assertNotIn("إلغاء التثبيت في الأعلى", labels)

    @patch("accessible_mail.mail_page.tr", side_effect=lambda value: value)
    @patch("accessible_mail.mail_page.wx.CallAfter")
    @patch("accessible_mail.mail_page.announce_context_menu")
    @patch("accessible_mail.mail_page.wx.Menu")
    def test_message_list_context_menu_hides_copy_and_translation_but_keeps_pin(
        self,
        menu_class: Mock,
        _announce_menu: Mock,
        _call_after: Mock,
        _translate: Mock,
    ) -> None:
        summary = MessageSummary(uid="1", mailbox="INBOX", is_read=True)
        menu = menu_class.return_value
        menu.Append.side_effect = lambda *_args: Mock()
        message_list = object()
        page = SimpleNamespace(
            actions_button=object(),
            viewer=object(),
            html_viewer=object(),
            list=message_list,
            viewer_text="نص الرسالة",
            multi_select_mode=False,
            selected_summaries=lambda: [summary],
            selected_summary=lambda: summary,
            context_return_control=lambda control: control,
            context_menu_popup_owner=lambda _control: SimpleNamespace(PopupMenu=Mock()),
            on_reply=Mock(),
            on_toggle_star=Mock(),
            on_toggle_read=Mock(),
            on_translate=Mock(),
            on_toggle_pin=Mock(),
            on_delete=Mock(),
            focus_message_list=Mock(),
            focus_list_index=Mock(),
            restore_context_focus=Mock(),
            _translation_return_control=None,
        )

        MailPage.show_message_context_menu(page, message_list, False)

        labels = [call.args[1] for call in menu.Append.call_args_list]
        self.assertNotIn("نسخ", labels)
        self.assertNotIn("ترجمة", labels)
        self.assertIn("التثبيت في الأعلى", labels)

    @patch("accessible_mail.mail_page.wx.TheClipboard")
    def test_copy_from_simple_viewer_prefers_selected_text(
        self,
        clipboard: Mock,
    ) -> None:
        clipboard.Open.return_value = True
        clipboard.SetData.return_value = True
        viewer = SimpleNamespace(GetStringSelection=Mock(return_value="النص المحدد"))
        page = SimpleNamespace(
            viewer=viewer,
            html_viewer=object(),
            viewer_text="نص الرسالة الكامل",
            message_viewer_copy_text=lambda control: MailPage.message_viewer_copy_text(
                page, control
            ),
            set_status=Mock(),
        )

        MailPage.copy_message_viewer_text(page, viewer)

        copied_data = clipboard.SetData.call_args.args[0]
        self.assertEqual(copied_data.GetText(), "النص المحدد")
        page.set_status.assert_called_once_with(
            "تم نسخ النص المحدد إلى الحافظة."
        )

    @patch("accessible_mail.mail_page.wx.TheClipboard")
    def test_copy_from_html_viewer_falls_back_to_complete_message_text(
        self,
        clipboard: Mock,
    ) -> None:
        clipboard.Open.return_value = True
        clipboard.SetData.return_value = True
        html_viewer = SimpleNamespace(GetSelectedText=Mock(return_value=""))
        page = SimpleNamespace(
            viewer=object(),
            html_viewer=html_viewer,
            viewer_text="نص الرسالة الكامل",
            message_viewer_copy_text=lambda control: MailPage.message_viewer_copy_text(
                page, control
            ),
            set_status=Mock(),
        )

        MailPage.copy_message_viewer_text(page, html_viewer)

        copied_data = clipboard.SetData.call_args.args[0]
        self.assertEqual(copied_data.GetText(), "نص الرسالة الكامل")
        page.set_status.assert_called_once_with(
            "تم نسخ نص الرسالة إلى الحافظة."
        )

    @patch("accessible_mail.mail_page.wx.TheClipboard")
    def test_copy_message_reports_when_clipboard_cannot_be_opened(
        self,
        clipboard: Mock,
    ) -> None:
        clipboard.Open.return_value = False
        viewer = SimpleNamespace(GetStringSelection=Mock(return_value="نص"))
        page = SimpleNamespace(
            viewer=viewer,
            html_viewer=object(),
            viewer_text="نص الرسالة",
            message_viewer_copy_text=lambda control: MailPage.message_viewer_copy_text(
                page, control
            ),
            set_status=Mock(),
        )

        MailPage.copy_message_viewer_text(page, viewer)

        page.set_status.assert_called_once_with(
            "تعذر نسخ النص إلى الحافظة."
        )

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

    def test_active_html_viewer_schedules_new_content_refresh(self) -> None:
        schedule_html_refresh = Mock()
        page = SimpleNamespace(
            viewer_text="",
            viewer=SimpleNamespace(ChangeValue=Mock()),
            viewer_mode=VIEWER_HTML,
            _html_refresh_pending=False,
            _html_viewer_active=True,
            schedule_html_refresh=schedule_html_refresh,
        )

        MailPage.set_viewer_text(page, "message")

        schedule_html_refresh.assert_called_once_with(focus_start=True)

    @patch("accessible_mail.mail_page.wx.CallLater")
    def test_scheduled_html_refresh_keeps_active_viewer_visible_and_focused(
        self,
        call_later: Mock,
    ) -> None:
        page = SimpleNamespace(
            _html_focus_after_load=False,
            _html_refresh_call=None,
            run_scheduled_html_refresh=Mock(),
            show_plain_viewer=Mock(),
            viewer=SimpleNamespace(SetFocus=Mock()),
        )

        MailPage.schedule_html_refresh(page, focus_start=True)

        page.show_plain_viewer.assert_not_called()
        page.viewer.SetFocus.assert_not_called()
        call_later.assert_called_once_with(40, page.run_scheduled_html_refresh)

    def test_activating_html_viewer_loads_pending_content(self) -> None:
        schedule_html_refresh = Mock()
        page = SimpleNamespace(
            _html_viewer_active=False,
            _html_refresh_pending=True,
            schedule_html_refresh=schedule_html_refresh,
            focus_html_document_start=Mock(),
        )

        MailPage.activate_html_viewer(page)

        self.assertTrue(page._html_viewer_active)
        schedule_html_refresh.assert_called_once_with(focus_start=True)
        page.focus_html_document_start.assert_not_called()

    def test_html_focus_script_is_compatible_and_places_text_caret_at_start(self) -> None:
        run_script = Mock()
        page = SimpleNamespace(
            _html_viewer_active=True,
            _html_loading=False,
            _html_refresh_pending=False,
            html_viewer=SimpleNamespace(SetFocus=Mock(), RunScript=run_script),
        )

        MailPage.focus_html_document_start(page)

        script = run_script.call_args.args[0]
        self.assertNotIn("=>", script)
        self.assertNotIn("const ", script)
        self.assertIn("messageElement.focus()", script)
        self.assertIn("collapse(true)", script)

    def test_html_focus_waits_until_page_load_completes(self) -> None:
        page = SimpleNamespace(
            _html_viewer_active=True,
            _html_loading=True,
            _html_refresh_pending=False,
            _html_focus_after_load=False,
            html_viewer=SimpleNamespace(SetFocus=Mock(), RunScript=Mock()),
        )

        MailPage.focus_html_document_start(page)

        self.assertTrue(page._html_focus_after_load)
        page.html_viewer.SetFocus.assert_not_called()
        page.html_viewer.RunScript.assert_not_called()

    def test_reactivating_loaded_html_makes_viewer_visible(self) -> None:
        calls: list[str] = []
        page = SimpleNamespace(
            _html_viewer_active=False,
            _html_refresh_pending=False,
            _html_loading=False,
            show_html_viewer=lambda: calls.append("show_html"),
            focus_html_document_start=lambda: calls.append("focus_html"),
        )

        MailPage.activate_html_viewer(page)

        self.assertEqual(calls, ["show_html", "focus_html"])

    def test_pending_html_refresh_waits_for_current_load(self) -> None:
        page = SimpleNamespace(
            _html_loading=True,
            _html_refresh_pending=True,
            _html_viewer_active=True,
            _html_focus_after_load=True,
            _html_load_timeout_call=None,
            schedule_html_refresh=Mock(),
        )

        MailPage.on_html_viewer_loaded(page, SimpleNamespace())

        self.assertFalse(page._html_loading)
        page.schedule_html_refresh.assert_called_once_with(focus_start=True)

    @patch("accessible_mail.mail_page.LOGGER.warning")
    @patch("accessible_mail.mail_page.wx.CallAfter", side_effect=lambda action: action())
    def test_html_load_timeout_recovers_active_viewer_focus(
        self,
        _call_after: Mock,
        warning: Mock,
    ) -> None:
        page = SimpleNamespace(
            _html_load_timeout_call=object(),
            _html_loading=True,
            _html_refresh_pending=False,
            _html_viewer_active=True,
            _html_focus_after_load=True,
            focus_html_document_start=Mock(),
        )

        MailPage.on_html_viewer_load_timeout(page)

        self.assertFalse(page._html_loading)
        self.assertFalse(page._html_focus_after_load)
        self.assertIsNone(page._html_load_timeout_call)
        page.focus_html_document_start.assert_called_once_with()
        warning.assert_called_once()

    def test_read_filter_selects_replacement_when_current_message_disappears(self) -> None:
        current = MessageSummary(uid="1", mailbox="INBOX", is_read=False)
        replacement = MessageSummary(uid="2", mailbox="INBOX", is_read=False)
        page = SimpleNamespace(
            messages=[current, replacement],
            trash_messages=[],
            visible_messages=[current, replacement],
            message_key=lambda message: (message.mailbox, message.uid),
            selected_message_key=lambda: ("INBOX", "1"),
            selected_filter_key=lambda: "unread",
            apply_filter=Mock(),
            select_replacement_after_filter=Mock(),
        )

        def apply_filter(*, preserve_key: tuple[str, str]) -> None:
            self.assertEqual(preserve_key, ("INBOX", "1"))
            page.visible_messages = [replacement]

        page.apply_filter.side_effect = apply_filter

        MailPage.update_message_read_state(page, current, True)

        self.assertTrue(current.is_read)
        page.select_replacement_after_filter.assert_called_once_with(0)

    def test_filtered_replacement_is_selected_and_loaded_explicitly(self) -> None:
        replacement = MessageSummary(uid="2", mailbox="INBOX")
        list_control = SimpleNamespace(
            SetItemState=Mock(),
            EnsureVisible=Mock(),
        )
        page = SimpleNamespace(
            visible_messages=[replacement],
            list=list_control,
            _suppress_selection_event=False,
            on_selected=Mock(),
        )

        MailPage.select_replacement_after_filter(page, 4)

        list_control.EnsureVisible.assert_called_once_with(0)
        page.on_selected.assert_called_once_with(page, replacement)
        self.assertFalse(page._suppress_selection_event)

    def test_empty_filtered_view_clears_stale_message_content(self) -> None:
        page = SimpleNamespace(
            visible_messages=[],
            current_content_key=("INBOX", "1"),
            set_links=Mock(),
            set_viewer_text=Mock(),
        )

        MailPage.select_replacement_after_filter(page, 0)

        page.set_links.assert_called_once_with([])
        page.set_viewer_text.assert_called_once_with("")
        self.assertIsNone(page.current_content_key)

    def test_native_html_escape_returns_to_message_list(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_ESCAPE,
            ControlDown=lambda: False,
            AltDown=lambda: False,
            CmdDown=lambda: False,
            Skip=Mock(),
        )
        page = SimpleNamespace(focus_message_list=Mock())

        MailPage.on_html_viewer_key(page, event)

        page.focus_message_list.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_plain_viewer_escape_returns_to_message_list_before_opening_item(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_ESCAPE,
            ControlDown=lambda: False,
            AltDown=lambda: False,
            CmdDown=lambda: False,
        )
        page = SimpleNamespace(
            focus_message_list=Mock(),
            viewer_item_at_caret=Mock(),
            open_item=Mock(),
        )

        handled = MailPage.handle_viewer_key(page, event)

        self.assertTrue(handled)
        page.focus_message_list.assert_called_once_with()
        page.viewer_item_at_caret.assert_not_called()

    def test_control_space_is_not_a_message_viewer_shortcut(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_SPACE,
            ControlDown=lambda: True,
            AltDown=lambda: False,
            CmdDown=lambda: False,
        )
        page = SimpleNamespace(
            focus_message_list=Mock(),
            toggle_message_and_link_viewers=Mock(),
        )

        handled = MailPage.handle_viewer_key(page, event)

        self.assertFalse(handled)
        page.focus_message_list.assert_not_called()

    def test_control_space_does_not_open_an_item(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_SPACE,
            ControlDown=lambda: True,
            AltDown=lambda: False,
            CmdDown=lambda: False,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            focus_message_list=Mock(),
            toggle_message_and_link_viewers=Mock(),
            on_open_link=Mock(),
        )

        MailPage.on_link_key(page, event)

        page.focus_message_list.assert_not_called()
        page.on_open_link.assert_not_called()
        event.Skip.assert_called_once_with()

    def test_frame_accelerators_do_not_register_control_space(self) -> None:
        source = inspect.getsource(MainFrame._create_accelerators)

        self.assertNotIn("wx.ACCEL_CTRL, wx.WXK_SPACE", source)

    def test_help_menu_contains_accessible_contact_submenu(self) -> None:
        source = inspect.getsource(MainFrame._create_menu)

        self.assertIn('help_menu.Append(wx.ID_ANY, "سياسة الخصوصية")', source)
        self.assertIn('help_menu.Append(wx.ID_ANY, "شروط الاستخدام")', source)
        self.assertIn("PRIVACY_POLICY_URL", source)
        self.assertIn("TERMS_OF_USE_URL", source)
        self.assertNotIn(
            '"اختيار PowerAccessibleMail كتطبيق البريد الافتراضي"',
            source,
        )
        self.assertNotIn("self.on_open_default_apps", source)
        self.assertIn('AppendSubMenu(contact_menu, "تواصل معنا")', source)
        self.assertLess(
            source.index('AppendSubMenu(contact_menu, "تواصل معنا")'),
            source.index('help_menu.Append(wx.ID_ANY, "سياسة الخصوصية")'),
        )
        self.assertLess(
            source.index('help_menu.Append(wx.ID_ANY, "سياسة الخصوصية")'),
            source.index('help_menu.Append(wx.ID_ANY, "شروط الاستخدام")'),
        )
        for label in (
            "زيارة الموقع الرسمي",
            "إرسال رسالة إلى المطور عبر PowerAccessibleMail",
            "الاشتراك بقناة التليجرام للحصول على آخر المستجدات",
            "التواصل مع المطور عبر تليجرام",
        ):
            self.assertIn(label, source)

    def test_alt_menu_contains_only_general_actions_and_help(self) -> None:
        source = inspect.getsource(MainFrame._create_menu)

        self.assertEqual(source.count("menu_bar.Append("), 2)
        self.assertIn(
            'menu_bar.Append(general_actions_menu, "الإجراءات العامة")',
            source,
        )
        self.assertIn('menu_bar.Append(help_menu, "المساعدة")', source)
        self.assertNotIn("message_menu", source)
        self.assertNotIn('"رد\\tCtrl+R"', source)
        self.assertNotIn('"ترجمة الرسالة\\tCtrl+T"', source)

    def test_settings_expose_notification_level_customization_and_default_mail(self) -> None:
        build_source = inspect.getsource(SettingsDialog._build)
        selected_source = inspect.getsource(SettingsDialog.selected_settings)
        checklist_source = inspect.getsource(SpokenNotificationsDialog.__init__)

        self.assertIn("SPOKEN_NOTIFICATION_LEVEL_CHOICES", build_source)
        self.assertIn("self.customize_notifications_button", build_source)
        self.assertIn('label="تخصيص نطق الإجراءات وإدارتها"', build_source)
        self.assertIn("self.default_mail_button", build_source)
        self.assertIn("self.on_default_mail", build_source)
        self.assertIn("اضغط Space لفتح اختيار التطبيق", build_source)
        self.assertIn("spoken_notification_level", selected_source)
        self.assertIn("spoken_notification_events", selected_source)
        self.assertIn("MESSAGE_READ_MODE_CHOICES", build_source)
        self.assertIn("self.message_read_mode_box", build_source)
        self.assertIn("message_read_mode", selected_source)
        self.assertIn("wx.ListBox", checklist_source)
        self.assertIn("wx.EVT_LISTBOX", checklist_source)
        self.assertIn("wx.TAB_TRAVERSAL", checklist_source)
        self.assertNotIn("wx.Simplebook", checklist_source)
        self.assertNotIn("wx.CheckListBox", checklist_source)
        self.assertIn('label=tr("حفظ")', checklist_source)

        category_source = inspect.getsource(SpokenNotificationsDialog._show_category)
        self.assertIn("self.category_event_ids[category_index]", category_source)
        self.assertIn("wx.FlexGridSizer", category_source)
        self.assertIn("cols=2", category_source)
        self.assertIn("wx.CheckBox", category_source)
        self.assertIn("Clear(delete_windows=True)", category_source)

    def test_notification_level_choice_resets_the_custom_checklist_to_its_preset(self) -> None:
        dialog = SimpleNamespace(
            notification_level_box=Mock(),
            settings=ProgramSettings(),
            notification_event_ids={"ready"},
            value_for_index=Mock(return_value=NOTIFICATION_LEVEL_NONE),
        )

        SettingsDialog.on_notification_level_changed(dialog, Mock())

        self.assertEqual(
            dialog.notification_event_ids,
            preset_event_ids(NOTIFICATION_LEVEL_NONE),
        )

    def test_default_mail_button_opens_windows_settings_through_main_frame(self) -> None:
        event = Mock()
        parent = SimpleNamespace(on_open_default_apps=Mock())
        dialog = SimpleNamespace(GetParent=lambda: parent)

        SettingsDialog.on_default_mail(dialog, event)

        parent.on_open_default_apps.assert_called_once_with(event)

    def test_email_developer_uses_internal_composer(self) -> None:
        frame = SimpleNamespace(open_compose_dialog=Mock())

        MainFrame.on_email_developer(frame, None)

        frame.open_compose_dialog.assert_called_once_with(
            "support@soljan-alsharq.com"
        )

    @patch("accessible_mail.main_frame.webbrowser.open", return_value=True)
    def test_contact_link_opens_in_default_browser(self, open_url: Mock) -> None:
        MainFrame.open_contact_url(SimpleNamespace(), "https://t.me/SoljanAlSharq")

        open_url.assert_called_once_with("https://t.me/SoljanAlSharq")

    def test_application_key_is_registered_for_context_menus(self) -> None:
        source = inspect.getsource(MainFrame._create_accelerators)

        self.assertIn("wx.WXK_WINDOWS_MENU", source)
        self.assertIn("wx.WXK_MENU", source)

    def test_item_context_menu_is_available_only_in_item_viewer(self) -> None:
        build_source = inspect.getsource(MailPage._build)
        key_source = inspect.getsource(MailPage.on_link_key)
        accelerator_source = inspect.getsource(MainFrame.on_context_menu_accelerator)

        self.assertIn("link_list.Bind(wx.EVT_CONTEXT_MENU", build_source)
        self.assertIn("self.show_item_menu(self.link_list)", key_source)
        self.assertIn("page.show_item_menu", accelerator_source)
        self.assertTrue(hasattr(MailPage, "on_item_context_menu"))
        self.assertFalse(hasattr(MailPage, "append_item_management_submenu"))

    def test_item_actions_button_has_focused_item_commands(self) -> None:
        commands_source = inspect.getsource(MailPage.append_item_management_commands)

        for label in (
            "فتح المرفق المحدد",
            "حفظ المرفق المحدد",
            "حفظ جميع المرفقات دفعة واحدة",
            "فتح الرابط المحدد",
            "نسخ الرابط المحدد",
            "فتح الصورة",
            "حفظ الصورة",
        ):
            self.assertIn(label, commands_source)
        self.assertIn("safe_external_url", commands_source)
        self.assertIn("save_all_attachments", commands_source)
        self.assertLess(
            commands_source.index("فتح الرابط المحدد"),
            commands_source.index("فتح المرفق المحدد"),
        )
        self.assertLess(
            commands_source.index("فتح المرفق المحدد"),
            commands_source.index("فتح الصورة"),
        )

    def test_item_actions_button_opens_commands_without_submenu(self) -> None:
        source = inspect.getsource(MailPage.on_actions_button)
        actions_menu_source = inspect.getsource(MailPage.show_item_actions_menu)
        item_menu_source = inspect.getsource(MailPage.show_item_menu)

        self.assertIn("show_item_actions_menu", source)
        self.assertNotIn("show_message_context_menu", source)
        self.assertIn("show_item_menu", actions_menu_source)
        self.assertIn("append_item_management_commands", item_menu_source)
        self.assertNotIn("AppendSubMenu", item_menu_source)

        actions_button = object()
        page = SimpleNamespace(
            actions_button=actions_button,
            show_item_actions_menu=Mock(),
        )
        MailPage.on_actions_button(page, None)
        page.show_item_actions_menu.assert_called_once_with(actions_button)

        page.show_item_actions_menu.reset_mock()
        MailPage.show_message_context_menu(page, actions_button, False)
        page.show_item_actions_menu.assert_called_once_with(actions_button)

    def test_item_actions_button_uses_new_name(self) -> None:
        source = inspect.getsource(MailPage._build)

        self.assertIn('label="إجراءات العنصر"', source)
        self.assertNotIn('label="إجراءات الرسالة"', source)

    def test_item_viewer_numbers_images_independently(self) -> None:
        message_text = (
            "Visit Website to read the full accessibility release notes and learn what changed. "
            "The Logo identifies the project in messages and on its official pages. "
            "The Banner explains that the new accessible version is now available. "
            "Please review manual.pdf for complete setup and keyboard instructions."
        )
        labels = MailPage.resource_labels(
            SimpleNamespace(),
            [
                LinkItem("Website", "https://example.com"),
                LinkItem("Logo", "cid:logo", kind="image"),
                LinkItem("Banner", "https://example.com/banner.png", kind="image"),
                LinkItem(
                    "Manual",
                    kind="attachment",
                    filename="manual.pdf",
                    content_type="application/pdf",
                    size=2048,
                ),
            ],
            message_text=message_text,
        )

        self.assertIn("الوصف: Website", labels[0])
        self.assertIn("جزء من الرسالة: Visit Website to read the full accessibility", labels[0])
        self.assertIn("عنوان الرابط: https://example.com", labels[0])
        self.assertNotIn("نوع العنصر", labels[0])
        self.assertNotIn("النطاق", labels[0])
        self.assertIn("صورة 1:", labels[1])
        self.assertIn("الوصف: Logo", labels[1])
        self.assertIn("جزء من الرسالة: The Logo identifies the project", labels[1])
        self.assertIn("صورة 2:", labels[2])
        self.assertIn("الوصف: Banner", labels[2])
        self.assertIn("جزء من الرسالة: The Banner explains", labels[2])
        self.assertIn("اسم الملف: manual.pdf", labels[3])
        self.assertIn("جزء من الرسالة: Please review manual.pdf", labels[3])
        self.assertIn("نوع الملف: application/pdf", labels[3])
        self.assertIn("الحجم: 2.0 KB", labels[3])

    @patch("accessible_mail.mail_page.validate_and_scan_image", return_value=("image/png", ".png"))
    @patch("accessible_mail.mail_page.validate_public_http_url", side_effect=lambda value: value)
    @patch("accessible_mail.mail_page.public_http_opener")
    def test_external_image_is_downloaded_only_as_a_bounded_scanned_image(
        self,
        opener_factory: Mock,
        _validate_url: Mock,
        validate_image: Mock,
    ) -> None:
        response = Mock()
        response.geturl.return_value = "http://example.com/assets/logo.png"
        response.headers.get_content_type.return_value = "image/png"
        response.headers.get.return_value = ""
        response.read.return_value = b"png-data"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener_factory.return_value.open.return_value = response
        item = LinkItem(
            "Company logo",
            "http://example.com/assets/logo.png",
            kind="image",
        )

        result = MailPage.materialize_image(SimpleNamespace(), item)

        self.assertEqual(result.filename, "logo.png")
        self.assertEqual(result.content_type, "image/png")
        self.assertEqual(result.attachment_bytes(), b"png-data")
        response.read.assert_called_once_with(25 * 1024 * 1024 + 1)
        validate_image.assert_called_once_with(b"png-data", "image/png")

    def test_message_context_menu_excludes_item_management_and_mark_unread(self) -> None:
        source = inspect.getsource(MailPage.show_message_context_menu)

        self.assertIn("تعليم كمقروءة", source)
        self.assertNotIn("تعليم كغير مقروءة", source)
        self.assertNotIn("append_item_management_submenu", source)
        self.assertNotIn('tr("حفظ المرفقات")', source)

    @patch("accessible_mail.mail_page.wx.TheClipboard")
    def test_copy_selected_link_uses_windows_clipboard(
        self,
        clipboard: Mock,
    ) -> None:
        clipboard.Open.return_value = True
        clipboard.SetData.return_value = True
        page = SimpleNamespace(set_status=Mock(), link_list=Mock())

        MailPage.copy_link(
            page,
            LinkItem("Website", "https://example.com/message"),
        )

        clipboard.Open.assert_called_once_with()
        copied_data = clipboard.SetData.call_args.args[0]
        self.assertEqual(copied_data.GetText(), "https://example.com/message")
        clipboard.Flush.assert_called_once_with()
        clipboard.Close.assert_called_once_with()
        page.set_status.assert_called_once_with("تم نسخ الرابط إلى الحافظة.")

    @patch("accessible_mail.mail_page.wx.TheClipboard")
    def test_copy_selected_link_rejects_unsafe_url(self, clipboard: Mock) -> None:
        page = SimpleNamespace(set_status=Mock(), link_list=Mock())

        MailPage.copy_link(
            page,
            LinkItem("Unsafe", "javascript:alert(1)"),
        )

        clipboard.Open.assert_not_called()
        page.set_status.assert_not_called()

    def test_compose_dialog_places_attachment_controls_in_keyboard_order(self) -> None:
        source = inspect.getsource(ComposeDialog.__init__)

        body_position = source.index("self.body = wx.TextCtrl")
        list_position = source.index("self.attachment_list = wx.ListBox")
        button_position = source.index("self.add_attachment_button = wx.Button")
        send_position = source.index("send_button = wx.Button")
        self.assertLess(body_position, button_position)
        self.assertLess(button_position, list_position)
        self.assertLess(list_position, send_position)

    def test_compose_dialog_places_address_book_button_after_recipient_field(self) -> None:
        source = inspect.getsource(ComposeDialog._recipient_row)

        field_position = source.index("control = wx.TextCtrl")
        button_position = source.index("self.add_address_button = wx.Button")
        self.assertLess(field_position, button_position)
        self.assertIn("self.on_to_address_key", source)
        self.assertIn("إضافة البريد الإلكتروني إلى سجل العناوين", source)

    @patch("accessible_mail.dialogs.wx.MessageBox")
    def test_compose_address_button_rejects_an_empty_recipient(
        self,
        message_box: Mock,
    ) -> None:
        recipient = Mock()
        recipient.GetValue.return_value = ""
        dialog = SimpleNamespace(to_address=recipient)

        ComposeDialog.on_add_address(dialog, Mock())

        message_box.assert_called_once()
        self.assertIn("يرجى كتابة بريد إلكتروني أولاً", message_box.call_args.args[0])
        recipient.SetFocus.assert_called_once_with()

    @patch("accessible_mail.dialogs.announce_to_screen_reader")
    @patch("accessible_mail.dialogs.AddressPickerDialog")
    @patch("accessible_mail.dialogs.load_address_book")
    def test_down_arrow_replaces_recipient_with_saved_address(
        self,
        load_addresses: Mock,
        picker_class: Mock,
        announce: Mock,
    ) -> None:
        load_addresses.return_value = [SimpleNamespace(email="saved@example.com")]
        picker = picker_class.return_value
        picker.ShowModal.return_value = wx.ID_OK
        picker.selected_email.return_value = "saved@example.com"
        recipient = Mock()
        dialog = SimpleNamespace(to_address=recipient)
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_DOWN, Skip=Mock())

        ComposeDialog.on_to_address_key(dialog, event)

        recipient.SetValue.assert_called_once_with("saved@example.com")
        recipient.SetInsertionPointEnd.assert_called_once_with()
        recipient.SetFocus.assert_called_once_with()
        announce.assert_called_once()
        picker.Destroy.assert_called_once_with()

    def test_address_book_is_available_in_the_command_list(self) -> None:
        labels = MainFrame.command_labels()

        self.assertEqual(labels[5], "سجل العناوين")
        self.assertEqual(labels[6], "الإعدادات")

    def test_address_context_menu_changes_pin_label_for_pinned_entries(self) -> None:
        from accessible_mail.address_book_dialog import AddressBookDialog

        source = inspect.getsource(AddressBookDialog.show_context_menu)

        self.assertIn("تثبيت البريد الإلكتروني بالأعلى", source)
        self.assertIn("إلغاء تثبيت البريد الإلكتروني من الأعلى", source)

    def test_address_message_matches_include_sent_and_received(self) -> None:
        received = MessageSummary(
            uid="received",
            mailbox="INBOX",
            sender_email="friend@example.com",
            received_at=10,
        )
        sent = MessageSummary(
            uid="sent",
            mailbox="SENT",
            recipient_emails=["friend@example.com"],
            received_at=20,
        )
        pages = {
            "inbox": SimpleNamespace(messages=[received], trash_messages=[]),
            "spam": SimpleNamespace(messages=[], trash_messages=[]),
            "sent": SimpleNamespace(messages=[sent], trash_messages=[]),
            "all": SimpleNamespace(messages=[], trash_messages=[]),
        }
        frame = SimpleNamespace(pages=pages)

        matches = MainFrame.address_message_matches(frame, "FRIEND@example.com")

        self.assertEqual(
            [(match[1].uid, match[2]) for match in matches],
            [("sent", "مرسلة"), ("received", "مستلمة")],
        )

    def test_compose_dialog_adds_unique_existing_attachment_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.txt"
            path.write_text("content", encoding="utf-8")
            dialog = SimpleNamespace(
                attachment_paths=[],
                refresh_attachment_list=Mock(),
            )

            added = ComposeDialog.add_attachment_paths(dialog, [path, path])

        self.assertEqual(added, 1)
        self.assertEqual(dialog.attachment_paths, [path])
        dialog.refresh_attachment_list.assert_called_once_with()

    def test_html_message_root_is_keyboard_accessible_article(self) -> None:
        page = SimpleNamespace(
            viewer_action_ranges=[],
            theme=THEME_LIGHT,
            message_html_content=lambda text: text,
        )

        rendered = MailPage.message_html(page, "Message body")

        self.assertIn('<article id="message" tabindex="0"', rendered)
        self.assertNotIn('role="document"', rendered)

    def test_show_content_cleans_legacy_message_text_before_display(self) -> None:
        summary = MessageSummary(uid="message", mailbox="INBOX")
        content = MessageContent(
            summary=summary,
            text="body { color: red; margin: 0; }\nReadable message.",
            links=[],
        )
        page = SimpleNamespace(
            message_key=lambda value: (value.mailbox, value.uid),
            links=[],
            set_links=Mock(),
            set_viewer_action_ranges=Mock(),
            viewer_mode=VIEWER_SIMPLE,
            set_viewer_text=Mock(),
            update_message_row=Mock(),
        )

        MailPage.show_content(page, content)

        page.set_links.assert_called_once_with([], message_text="Readable message.")
        page.set_viewer_action_ranges.assert_called_once_with("Readable message.", [])
        page.set_viewer_text.assert_called_once_with("Readable message.")

    def test_stale_link_range_is_relocated_after_message_cleaning(self) -> None:
        link = LinkItem(
            "الموقع",
            "https://example.com",
            activation_text="Click here",
            activation_start=0,
            activation_end=10,
        )
        page = SimpleNamespace(
            viewer_action_ranges=[],
            current_viewer_action_range=None,
        )
        page.link_has_viewer_range = lambda value, item: MailPage.link_has_viewer_range(
            page, value, item
        )
        page.viewer_activation_candidates = (
            lambda value, item: MailPage.viewer_activation_candidates(page, value, item)
        )
        page.find_viewer_action_range = (
            lambda value, candidate, offsets: MailPage.find_viewer_action_range(
                page, value, candidate, offsets
            )
        )
        text = "Readable message. Click here"

        MailPage.set_viewer_action_ranges(page, text, [link])

        start = text.index("Click here")
        self.assertEqual(page.viewer_action_ranges, [(start, start + 10, link)])

    def test_html_message_uses_the_selected_french_language(self) -> None:
        page = SimpleNamespace(
            viewer_action_ranges=[],
            theme=THEME_LIGHT,
            message_html_content=lambda text: text,
        )

        with patch("accessible_mail.mail_page.get_language", return_value="fr"):
            rendered = MailPage.message_html(page, "Corps du message")

        self.assertIn('<html lang="fr" dir="auto">', rendered)

    def test_unsafe_message_links_are_not_rendered_as_clickable_actions(self) -> None:
        item = LinkItem("تشغيل", "javascript:alert(1)")

        rendered = MailPage.message_html_action(
            SimpleNamespace(),
            "تشغيل",
            item,
        )

        self.assertEqual(rendered, "تشغيل")

    def test_dangerous_attachments_require_confirmation(self) -> None:
        self.assertTrue(
            MailPage.attachment_requires_confirmation(
                LinkItem("invoice.exe", kind="attachment", filename="invoice.exe")
            )
        )
        self.assertFalse(
            MailPage.attachment_requires_confirmation(
                LinkItem("invoice.pdf", kind="attachment", filename="invoice.pdf")
            )
        )

    def test_windows_reserved_attachment_names_are_made_safe(self) -> None:
        item = LinkItem("CON.txt", kind="attachment", filename="CON.txt")

        filename = MailPage.safe_attachment_filename(SimpleNamespace(), item)

        self.assertEqual(filename, "_CON.txt")

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

    def test_enter_from_message_list_focuses_start_of_message_viewer(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_RETURN,
            ControlDown=lambda: False,
            ShiftDown=lambda: False,
            AltDown=lambda: False,
            Skip=Mock(),
        )
        page = SimpleNamespace(
            multi_select_mode=False,
            _control_pressed_alone=False,
            selected_summary=Mock(return_value=object()),
            focus_message_viewer_start=Mock(),
        )

        MailPage.on_list_key(page, event)

        page.focus_message_viewer_start.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_plain_message_viewer_focus_starts_at_first_character(self) -> None:
        summary = object()
        viewer = Mock()
        page = SimpleNamespace(
            viewer_mode=VIEWER_SIMPLE,
            selected_summary=Mock(return_value=summary),
            current_content_key=("Inbox", "1"),
            message_key=Mock(return_value=("Inbox", "1")),
            viewer=viewer,
            _focus_plain_start_after_content=False,
            set_status=Mock(),
        )

        MailPage.focus_message_viewer_start(page)

        viewer.SetInsertionPoint.assert_called_once_with(0)
        viewer.ShowPosition.assert_called_once_with(0)
        viewer.SetFocus.assert_called_once_with()
        self.assertFalse(page._focus_plain_start_after_content)

    def test_plain_message_focus_stays_at_start_when_content_finishes_loading(self) -> None:
        viewer = Mock()
        page = SimpleNamespace(
            viewer_mode=VIEWER_SIMPLE,
            viewer=viewer,
            viewer_text="",
            _focus_plain_start_after_content=True,
            show_plain_viewer=Mock(),
        )

        MailPage.set_viewer_text(page, "Message body")

        viewer.ChangeValue.assert_called_once_with("Message body")
        viewer.SetInsertionPoint.assert_called_once_with(0)
        viewer.ShowPosition.assert_called_once_with(0)
        viewer.SetFocus.assert_called_once_with()
        self.assertFalse(page._focus_plain_start_after_content)

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
    def test_mode_change_notification_is_delayed_150_milliseconds(
        self,
        call_later: Mock,
    ) -> None:
        page = SimpleNamespace(
            _multi_mode_notification_call=None,
            _show_multi_selection_mode_notification=Mock(),
        )

        MailPage.schedule_multi_selection_mode_notification(page, "تم التفعيل")

        call_later.assert_called_once_with(
            MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS,
            page._show_multi_selection_mode_notification,
            "تم التفعيل",
        )
        self.assertEqual(MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS, 150)

    @patch("accessible_mail.app.wx.CallLater")
    def test_selection_count_is_delayed_150_milliseconds(
        self,
        call_later: Mock,
    ) -> None:
        page = SimpleNamespace(
            _selection_count_announce_call=None,
            _announce_scheduled_selection_count=Mock(),
        )

        MailPage.schedule_selection_count_announcement(page)

        call_later.assert_called_once_with(
            MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS,
            page._announce_scheduled_selection_count,
        )
        self.assertEqual(MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS, 150)

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
    @patch("accessible_mail.accessibility.interrupt_and_speak", return_value=True)
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
    @patch("accessible_mail.accessibility.interrupt_and_speak", return_value=False)
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
            "تمييز الرسائل بنجمة",
            "إزالة النجمة من الرسائل",
            "تثبيت الرسائل في الأعلى",
            "إلغاء تثبيت الرسائل",
            "حذف الرسائل وإرسالها إلى سلة المحذوفات",
        ):
            self.assertIn(label, source)
        self.assertNotIn("تعليم كغير مقروءة", source)
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

    @patch("accessible_mail.main_frame.BulkDeleteDialog")
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

    def test_manual_read_mode_does_not_mark_message_on_viewer_focus(self) -> None:
        summary = MessageSummary(uid="1", mailbox="INBOX", is_read=False)
        page = SimpleNamespace(
            message_read_mode=MESSAGE_READ_MANUAL,
            selected_summary=lambda: summary,
            on_viewer_enter=Mock(),
        )

        MailPage.notify_message_viewer_entered(page)

        page.on_viewer_enter.assert_not_called()

    def test_automatic_read_mode_marks_loaded_message_on_viewer_focus(self) -> None:
        summary = MessageSummary(uid="1", mailbox="INBOX", is_read=False)
        page = SimpleNamespace(
            message_read_mode=MESSAGE_READ_ON_VIEWER_ENTER,
            selected_summary=lambda: summary,
            message_key=lambda value: (value.mailbox, value.uid),
            current_content_key=("INBOX", "1"),
            _pending_auto_read_key=None,
            on_viewer_enter=Mock(),
        )

        MailPage.notify_message_viewer_entered(page)

        page.on_viewer_enter.assert_called_once_with(page, summary)
        self.assertIsNone(page._pending_auto_read_key)

    def test_automatic_read_waits_until_full_message_has_loaded(self) -> None:
        summary = MessageSummary(uid="1", mailbox="INBOX", is_read=False)
        page = SimpleNamespace(
            message_read_mode=MESSAGE_READ_ON_VIEWER_ENTER,
            selected_summary=lambda: summary,
            message_key=lambda value: (value.mailbox, value.uid),
            current_content_key=None,
            _pending_auto_read_key=None,
            on_viewer_enter=Mock(),
        )

        MailPage.notify_message_viewer_entered(page)
        self.assertEqual(page._pending_auto_read_key, ("INBOX", "1"))
        page.on_viewer_enter.assert_not_called()

        page.current_content_key = ("INBOX", "1")
        MailPage.complete_pending_auto_read(page, summary)

        page.on_viewer_enter.assert_called_once_with(page, summary)

    def test_automatic_read_keeps_unread_filter_message_open_until_list_return(self) -> None:
        summary = MessageSummary(uid="1", mailbox="INBOX", is_read=False)
        list_control = SimpleNamespace(SetItem=Mock())
        page = SimpleNamespace(
            messages=[summary],
            trash_messages=[],
            visible_messages=[summary],
            list=list_control,
            message_key=lambda value: (value.mailbox, value.uid),
            selected_message_key=lambda: ("INBOX", "1"),
            selected_filter_key=lambda: "unread",
            apply_filter=Mock(),
            _deferred_filter_refresh=False,
        )

        MailPage.update_message_read_state(
            page,
            summary,
            True,
            preserve_open_message=True,
        )

        self.assertTrue(summary.is_read)
        self.assertTrue(page._deferred_filter_refresh)
        self.assertEqual(page._deferred_filter_previous_index, 0)
        page.apply_filter.assert_not_called()
        list_control.SetItem.assert_called_once_with(0, 0, summary.status_label)

    def test_returning_to_unread_list_refreshes_filter_and_selects_replacement(self) -> None:
        current = MessageSummary(uid="1", mailbox="INBOX", is_read=True)
        replacement = MessageSummary(uid="2", mailbox="INBOX", is_read=False)
        event = SimpleNamespace(Skip=Mock())
        page = SimpleNamespace(
            _deferred_filter_refresh=True,
            _deferred_filter_previous_index=1,
            visible_messages=[current, replacement],
            deactivate_html_viewer=Mock(),
            selected_summary=lambda: current,
            message_key=lambda value: (value.mailbox, value.uid),
            apply_filter=Mock(),
            select_replacement_after_filter=Mock(),
        )

        def refresh(*, preserve_key: tuple[str, str]) -> None:
            self.assertEqual(preserve_key, ("INBOX", "1"))
            page.visible_messages = [replacement]

        page.apply_filter.side_effect = refresh

        MailPage.on_message_list_focus(page, event)

        page.select_replacement_after_filter.assert_called_once_with(1)
        event.Skip.assert_called_once_with()

    def test_viewer_enter_marks_only_unread_messages(self) -> None:
        unread = MessageSummary(uid="1", mailbox="INBOX", is_read=False)
        read = MessageSummary(uid="2", mailbox="INBOX", is_read=True)
        page = object()
        frame = SimpleNamespace(set_message_read_state=Mock())

        MainFrame.on_message_viewer_enter(frame, page, unread)
        MainFrame.on_message_viewer_enter(frame, page, read)

        frame.set_message_read_state.assert_called_once_with(
            page,
            unread,
            True,
            preserve_open_message=True,
        )

    def test_deactivated_html_viewer_returns_to_plain_preview(self) -> None:
        page = SimpleNamespace(
            _html_viewer_active=True,
            _html_focus_after_load=True,
            _html_refresh_call=None,
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

    @patch("accessible_mail.main_frame.UpdateAvailableDialog")
    def test_update_now_starts_internal_updater(self, dialog_class: Mock) -> None:
        dialog = dialog_class.return_value
        dialog.ShowModal.return_value = wx.ID_OK
        result = UpdateCheckResult(
            configured=True,
            available=True,
            current_version="1.2.7",
            latest_version="1.2.8",
            download_url="https://example.com/PowerAccessibleMailSetup.exe",
        )
        frame = SimpleNamespace(
            _update_dialog_open=False,
            start_internal_update=Mock(),
        )

        MainFrame.show_update_available(frame, result)

        frame.start_internal_update.assert_called_once_with(result)
        dialog.Destroy.assert_called_once_with()
        self.assertFalse(frame._update_dialog_open)

    def test_internal_update_progress_window_exposes_requested_details(self) -> None:
        source = inspect.getsource(UpdateDownloadDialog.__init__)
        progress_source = inspect.getsource(UpdateDownloadDialog.set_progress)

        self.assertIn("الإصدار الجديد:", source)
        self.assertIn("تاريخ الإطلاق:", source)
        self.assertIn("wx.Gauge", source)
        self.assertIn("percent", progress_source)

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
        self.assertIn("UPDATEFROMAPP", source)
        self.assertIn("IsInternalUpdate", source)

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

    def test_installer_registers_power_accessible_mail_as_a_mailto_handler(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        installer = (project_root / "installer_power_accessible_mail.iss").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("[Registry]", installer)
        self.assertIn("Software\\RegisteredApplications", installer)
        self.assertIn("Software\\Clients\\Mail\\PowerAccessibleMail", installer)
        self.assertIn(
            'Subkey: "Software\\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"',
            installer,
        )
        self.assertIn("Software\\Clients\\Mail\\PowerAccessibleMail\\Capabilities\\Startmenu", installer)
        self.assertIn('ValueName: "mailto"; ValueData: "PowerAccessibleMail.mailto"', installer)
        self.assertIn("Software\\Classes\\PowerAccessibleMail.mailto", installer)
        self.assertIn("Software\\Classes\\mailto\\OpenWithProgids", installer)
        self.assertIn("ChangesAssociations=yes", installer)
        self.assertIn('ValueName: "FriendlyTypeName"', installer)
        self.assertIn('ValueName: "ApplicationName"; ValueData: "{#MyAppName}"', installer)
        self.assertIn('""%1""', installer)
        self.assertIn(
            'Filename: "ms-settings:defaultapps?registeredAppUser=Power%20Accessible%20Mail"',
            installer,
        )

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
        self.assertNotIn("french.ButtonBack=", source)
        self.assertNotIn("french.ButtonNext=", source)
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
    @patch("accessible_mail.main_frame.save_accounts")
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
        frame._load_accounts_to_choice.assert_called_once_with(account.id)
        dialog.Destroy.assert_called_once_with()

    def test_oauth_provider_button_starts_login_directly(self) -> None:
        dialog = SimpleNamespace(start_oauth_login=Mock())

        AccountDialog.on_oauth_provider_button(dialog, Mock(), "google_gmail_api")

        dialog.start_oauth_login.assert_called_once_with("google_gmail_api")

    @patch("accessible_mail.account_dialog.wx.BeginBusyCursor")
    @patch("accessible_mail.account_dialog.threading.Thread")
    @patch("accessible_mail.account_dialog.run_browser_oauth_flow")
    @patch(
        "accessible_mail.account_dialog.load_oauth_clients",
        return_value={
            "microsoft": {
                "client_id": "client-id",
                "client_secret": "",
            }
        },
    )
    def test_account_oauth_wait_runs_outside_the_ui_thread(
        self,
        _load_clients: Mock,
        oauth_flow: Mock,
        thread_class: Mock,
        _busy_cursor: Mock,
    ) -> None:
        dialog = SimpleNamespace(
            _oauth_login_active=False,
            _oauth_login_generation=0,
            _oauth_cancel_event=None,
            _destroyed=False,
            account=Account(),
            _select_oauth_provider=Mock(),
        )

        AccountDialog.start_oauth_login(dialog, "microsoft")

        thread_class.assert_called_once()
        thread_class.return_value.start.assert_called_once_with()
        oauth_flow.assert_not_called()
        self.assertTrue(dialog._oauth_login_active)

    def test_sign_in_diagnostic_redacts_oauth_secrets(self) -> None:
        diagnostic = sanitize_sign_in_diagnostic(
            "request failed?code=secret-code&state=ok "
            "access_token=secret-access refresh_token: secret-refresh "
            "Authorization: Bearer secret-bearer"
        )

        self.assertNotIn("secret-code", diagnostic)
        self.assertNotIn("secret-access", diagnostic)
        self.assertNotIn("secret-refresh", diagnostic)
        self.assertNotIn("secret-bearer", diagnostic)
        self.assertIn("[محجوب]", diagnostic)

    def test_sign_in_error_details_are_copyable_without_credentials(self) -> None:
        details = sign_in_error_details(
            RuntimeError("invalid_grant access_token=do-not-copy"),
            "google_gmail_api",
        )

        self.assertIn("RuntimeError", details)
        self.assertIn("invalid_grant", details)
        self.assertIn("Google", details)
        self.assertNotIn("do-not-copy", details)

    @patch("accessible_mail.account_dialog.set_accessible")
    @patch("accessible_mail.account_dialog.announce_to_screen_reader")
    @patch("accessible_mail.account_dialog.wx.TheClipboard")
    def test_sign_in_result_copy_button_keeps_dialog_open(
        self,
        clipboard: Mock,
        announce: Mock,
        _set_accessible: Mock,
    ) -> None:
        clipboard.Open.return_value = True
        clipboard.SetData.return_value = True
        dialog = SimpleNamespace(
            details_text="copyable diagnostic",
            copy_button=SimpleNamespace(SetLabel=Mock()),
        )

        SignInResultDialog.on_copy(dialog)

        copied_data = clipboard.SetData.call_args.args[0]
        self.assertEqual(copied_data.GetText(), "copyable diagnostic")
        clipboard.Flush.assert_called_once_with()
        clipboard.Close.assert_called_once_with()
        announce.assert_called_once_with("تم نسخ نتيجة تسجيل الدخول إلى الحافظة.")
        dialog.copy_button.SetLabel.assert_called_once_with("تم النسخ")

    @patch("accessible_mail.account_dialog.show_sign_in_result_dialog")
    @patch("accessible_mail.account_dialog.apply_provider_settings")
    @patch("accessible_mail.account_dialog.wx.IsBusy", return_value=False)
    def test_oauth_success_shows_copyable_result_before_closing_login(
        self,
        _is_busy: Mock,
        _apply_provider: Mock,
        show_result: Mock,
    ) -> None:
        result = OAuthFlowResult(
            provider_id="google_gmail_api",
            email_address="person@example.com",
            display_name="Person",
            access_token="access-secret",
            refresh_token="refresh-secret",
            expires_at=12345.0,
        )
        dialog = SimpleNamespace(
            _oauth_login_generation=4,
            _oauth_login_active=True,
            _oauth_cancel_event=object(),
            account=Account(),
            Raise=Mock(),
            RequestUserAttention=Mock(),
            EndModal=Mock(),
        )

        AccountDialog.finish_oauth_login(
            dialog,
            4,
            "client-id",
            "client-secret",
            result,
            None,
        )

        show_result.assert_called_once()
        title = show_result.call_args.args[1]
        details = show_result.call_args.args[2]
        self.assertEqual(title, "نجاح تسجيل الدخول")
        self.assertIn("person@example.com", details)
        self.assertNotIn("access-secret", details)
        self.assertNotIn("refresh-secret", details)
        dialog.EndModal.assert_called_once_with(wx.ID_OK)

    @patch("accessible_mail.main_frame.wx.MessageBox")
    def test_handled_worker_error_does_not_show_a_second_error_dialog(
        self,
        message_box: Mock,
    ) -> None:
        failed = Mock(return_value=True)
        frame = SimpleNamespace(
            _active_worker_count=1,
            set_busy=Mock(),
            SetStatusText=Mock(),
            reset_transfer_progress=Mock(),
        )

        MainFrame.on_worker_error(frame, RuntimeError("sign-in failed"), failed)

        failed.assert_called_once()
        frame.reset_transfer_progress.assert_called_once_with()
        message_box.assert_not_called()

    @patch(
        "accessible_mail.account_dialog.google_provider_id",
        return_value="google_gmail_api",
    )
    def test_startup_google_button_starts_gmail_api_provider(
        self,
        provider_id: Mock,
    ) -> None:
        dialog = SimpleNamespace(start_oauth_login=Mock())

        AccountDialog.on_continue_with_google(dialog, Mock())

        provider_id.assert_called_once_with()
        dialog.start_oauth_login.assert_called_once_with("google_gmail_api")

    def test_startup_microsoft_button_starts_microsoft_provider(self) -> None:
        dialog = SimpleNamespace(start_oauth_login=Mock())

        AccountDialog.on_continue_with_microsoft(dialog, Mock())

        dialog.start_oauth_login.assert_called_once_with("microsoft")

    def test_startup_login_uses_requested_accessible_control_order(self) -> None:
        source = inspect.getsource(AccountDialog.show_startup_view)
        ordered_labels = (
            "مرحبا بكم في برنامج Power Accessible Mail",
            "شعار Power Accessible Mail",
            "عنوان البريد الإلكتروني:",
            "كلمة المرور:",
            "تسجيل الدخول بالبريد وكلمة المرور",
            "الاستمرار مع Google",
            "الاستمرار مع Microsoft",
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

    def test_basic_microsoft_login_configures_manual_mail_servers(self) -> None:
        account = Account(email_address="person@msn.com")

        configured = AccountDialog.configure_known_manual_provider(account)

        self.assertTrue(configured)
        self.assertEqual(account.imap_server, "outlook.office365.com")
        self.assertEqual(account.smtp_server, "smtp-mail.outlook.com")
        self.assertEqual(account.spam_mailbox, "Junk Email")

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
    @patch("accessible_mail.main_frame.restore_control_focus")
    @patch("accessible_mail.main_frame.focused_control", return_value=None)
    def test_in_app_notification_uses_interrupting_screen_reader_path(
        self,
        _focused_control: Mock,
        restore_focus: Mock,
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
        frame.SetStatusText.assert_called_once_with("تم التفعيل")
        restore_focus.assert_called_once_with(None)
        call_later.assert_called_once_with(8000, frame.dismiss_notification)

    def test_every_status_message_routes_through_nvda(self) -> None:
        source = inspect.getsource(MainFrame.SetStatusText)

        self.assertIn("announce_to_screen_reader", source)
        self.assertIn("should_announce_status", source)
        self.assertIn("GetStatusBar", source)

    def test_obvious_or_repetitive_statuses_are_not_announced(self) -> None:
        for message in (
            "جاهز",
            "جار تحميل الرسالة...",
            "تم تحميل الرسالة.",
            "مستعرض العناصر.",
            "مستعرض الرسالة.",
            "قائمة الرسائل.",
            "جار استلام الرسائل (45%).",
        ):
            with self.subTest(message=message):
                self.assertFalse(should_announce_status(message))

    def test_meaningful_action_statuses_are_announced(self) -> None:
        for message in (
            "تم تثبيت البريد الإلكتروني بالأعلى.",
            "تم حذف عنوان البريد الإلكتروني.",
            "تم إرسال الرسالة.",
            "تعذر فتح الرابط في المتصفح الافتراضي.",
        ):
            with self.subTest(message=message):
                self.assertTrue(should_announce_status(message))

    def test_all_popup_context_menus_announce_opening_through_nvda(self) -> None:
        sources = (
            inspect.getsource(MainFrame.on_account_options),
            inspect.getsource(ComposeDialog.show_attachment_context_menu),
            inspect.getsource(AddressBookDialog.show_context_menu),
            inspect.getsource(MailPage.show_item_menu),
            inspect.getsource(MailPage.show_message_context_menu),
            inspect.getsource(MailPage.show_multi_message_context_menu),
        )

        for source in sources:
            self.assertIn("announce_context_menu", source)

    @patch("accessible_mail.accessibility.tr", side_effect=lambda value: value)
    @patch("accessible_mail.accessibility._native_message_box", return_value=wx.ID_OK)
    @patch("accessible_mail.accessibility.interrupt_and_speak", return_value=True)
    def test_message_boxes_are_passed_to_nvda_controller(
        self,
        speak: Mock,
        native_message_box: Mock,
        _translate: Mock,
    ) -> None:
        result = message_box("اكتملت العملية.", "نجاح")

        self.assertEqual(result, wx.ID_OK)
        speak.assert_called_once_with("اكتملت العملية.")
        native_message_box.assert_called_once_with(
            "اكتملت العملية.",
            "نجاح",
            wx.OK,
            None,
        )

    def test_both_builds_bundle_the_nvda_controller_client(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source = (project_root / "build_power_accessible_mail.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn('"--add-binary"', source)
        self.assertIn("$Architecture\\nvdaControllerClient.dll", source)
        self.assertIn("Expected exactly one bundled NVDA Controller", source)

    def test_portable_build_includes_both_user_guides(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source = (
            project_root / "build_release_power_accessible_mail.ps1"
        ).read_text(encoding="utf-8-sig")

        self.assertIn('"README_AR.txt"', source)
        self.assertIn('"README_EN.txt"', source)
        self.assertIn("The portable package guide does not match", source)

    def test_account_method_list_has_ok_and_cancel_buttons(self) -> None:
        dialog = SimpleNamespace(
            show_oauth_provider_view=Mock(),
            show_manual_view=Mock(),
        )

        AccountDialog.on_browser_method(dialog, Mock())
        AccountDialog.on_manual_method(dialog, Mock())

        dialog.show_oauth_provider_view.assert_called_once_with()
        dialog.show_manual_view.assert_called_once_with()
        method_source = inspect.getsource(AccountDialog.show_method_view)
        self.assertIn('label="موافق"', method_source)
        self.assertIn("ok_button.SetDefault()", method_source)
        self.assertIn("on_account_method_activate", method_source)
        self.assertIn('label="إلغاء"', method_source)
        self.assertIn("wx.ListBox", method_source)

    def test_account_method_list_activates_selected_item(self) -> None:
        dialog = SimpleNamespace(
            account_method_list=SimpleNamespace(GetSelection=lambda: 0),
            show_oauth_provider_view=Mock(),
            show_manual_view=Mock(),
        )

        AccountDialog.on_account_method_activate(dialog)

        dialog.show_oauth_provider_view.assert_called_once_with()
        dialog.account_method_list.GetSelection = lambda: 1
        AccountDialog.on_account_method_activate(dialog)
        dialog.show_manual_view.assert_called_once_with()

    def test_enter_activates_account_method_list_item(self) -> None:
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_RETURN, Skip=Mock())
        dialog = SimpleNamespace(on_account_method_activate=Mock())

        AccountDialog.on_account_method_key(dialog, event)

        dialog.on_account_method_activate.assert_called_once_with()
        event.Skip.assert_not_called()

    @patch("accessible_mail.app.wx.Window.FindFocus")
    def test_dialog_char_hook_activates_account_method_on_enter(
        self,
        find_focus: Mock,
    ) -> None:
        method_list = object()
        find_focus.return_value = method_list
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_RETURN, Skip=Mock())
        dialog = SimpleNamespace(
            mode="method",
            account_method_list=method_list,
            on_account_method_activate=Mock(),
        )

        AccountDialog.on_dialog_key(dialog, event)

        dialog.on_account_method_activate.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_right_click_selects_and_activates_account_method(self) -> None:
        control = SimpleNamespace(
            ScreenToClient=Mock(return_value=wx.Point(4, 8)),
            HitTest=Mock(return_value=1),
            SetSelection=Mock(),
        )
        event = SimpleNamespace(GetPosition=lambda: wx.Point(40, 80))
        dialog = SimpleNamespace(
            account_method_list=control,
            _select_context_list_item=AccountDialog._select_context_list_item,
            on_account_method_activate=Mock(),
        )

        AccountDialog.on_account_method_context(dialog, event)

        control.SetSelection.assert_called_once_with(1)
        dialog.on_account_method_activate.assert_called_once_with()

    def test_oauth_provider_list_activates_selected_service(self) -> None:
        dialog = SimpleNamespace(
            oauth_provider_list=SimpleNamespace(GetSelection=lambda: 1),
            oauth_provider_ids=["google_gmail_api", "microsoft"],
            start_oauth_login=Mock(),
        )

        AccountDialog.on_oauth_provider_activate(dialog)

        dialog.start_oauth_login.assert_called_once_with("microsoft")

    def test_enter_activates_oauth_provider_list_item(self) -> None:
        event = SimpleNamespace(
            GetKeyCode=lambda: wx.WXK_NUMPAD_ENTER,
            Skip=Mock(),
        )
        dialog = SimpleNamespace(on_oauth_provider_activate=Mock())

        AccountDialog.on_oauth_provider_key(dialog, event)

        dialog.on_oauth_provider_activate.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_right_click_selects_and_activates_oauth_service(self) -> None:
        control = SimpleNamespace(
            ScreenToClient=Mock(return_value=wx.Point(6, 12)),
            HitTest=Mock(return_value=1),
            SetSelection=Mock(),
        )
        event = SimpleNamespace(GetPosition=lambda: wx.Point(60, 120))
        dialog = SimpleNamespace(
            oauth_provider_list=control,
            _select_context_list_item=AccountDialog._select_context_list_item,
            on_oauth_provider_activate=Mock(),
        )

        AccountDialog.on_oauth_provider_context(dialog, event)

        control.SetSelection.assert_called_once_with(1)
        dialog.on_oauth_provider_activate.assert_called_once_with()

    @patch("accessible_mail.app.wx.Window.FindFocus")
    def test_dialog_char_hook_activates_oauth_service_on_enter(
        self,
        find_focus: Mock,
    ) -> None:
        provider_list = object()
        find_focus.return_value = provider_list
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_NUMPAD_ENTER, Skip=Mock())
        dialog = SimpleNamespace(
            mode="oauth2",
            oauth_provider_list=provider_list,
            on_oauth_provider_activate=Mock(),
        )

        AccountDialog.on_dialog_key(dialog, event)

        dialog.on_oauth_provider_activate.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_escape_from_account_dialog_returns_to_main_interface(self) -> None:
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_ESCAPE, Skip=Mock())
        dialog = SimpleNamespace(close_to_main_interface=Mock())

        AccountDialog.on_dialog_key(dialog, event)

        dialog.close_to_main_interface.assert_called_once_with()
        event.Skip.assert_not_called()

    @patch("accessible_mail.account_dialog.wx.Window.FindFocus", return_value=None)
    def test_backspace_returns_to_previous_account_view(self, _find_focus: Mock) -> None:
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_BACK, Skip=Mock())
        dialog = SimpleNamespace(mode="oauth2", on_back=Mock())

        AccountDialog.on_dialog_key(dialog, event)

        dialog.on_back.assert_called_once_with()
        event.Skip.assert_not_called()

    def test_backspace_edits_email_field_on_first_run_instead_of_leaving(self) -> None:
        class FakeTextCtrl:
            pass

        focus = FakeTextCtrl()
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_BACK, Skip=Mock())
        dialog = SimpleNamespace(mode="startup", on_back=Mock())

        with (
            patch("accessible_mail.account_dialog.wx.TextCtrl", FakeTextCtrl),
            patch(
                "accessible_mail.account_dialog.wx.Window.FindFocus",
                return_value=focus,
            ),
        ):
            AccountDialog.on_dialog_key(dialog, event)

        event.Skip.assert_called_once_with()
        dialog.on_back.assert_not_called()

    @patch("accessible_mail.app.wx.CallAfter", side_effect=lambda function, *args: function(*args))
    @patch("accessible_mail.main_frame.AccountDialog")
    def test_initial_login_is_shown_only_when_no_account_exists(
        self,
        dialog_class: Mock,
        _call_after: Mock,
    ) -> None:
        frame_with_account = SimpleNamespace(
            accounts=[Account(email_address="existing@example.com")],
            _startup_login_shown=False,
            account_choice=SimpleNamespace(SetFocus=Mock()),
        )
        MainFrame.show_initial_login_if_needed(frame_with_account)
        dialog_class.assert_not_called()
        frame_with_account.account_choice.SetFocus.assert_called_once_with()

        frame_without_account = SimpleNamespace(
            accounts=[],
            _startup_login_shown=False,
            finish_account_dialog=Mock(return_value=False),
            account_choice=SimpleNamespace(SetFocus=Mock()),
        )
        MainFrame.show_initial_login_if_needed(frame_without_account)

        dialog_class.assert_called_once_with(frame_without_account, startup=True)
        self.assertTrue(frame_without_account._startup_login_shown)
        frame_without_account.account_choice.SetFocus.assert_called_once_with()

    def test_busy_state_keeps_navigation_controls_enabled(self) -> None:
        frame = SimpleNamespace(
            SetStatusText=Mock(),
            account_choice=SimpleNamespace(Enable=Mock()),
            command_list=SimpleNamespace(Enable=Mock()),
        )

        MainFrame.set_busy(frame, True, "جار التحديث")

        frame.SetStatusText.assert_called_once_with("جار التحديث")
        frame.account_choice.Enable.assert_not_called()
        frame.command_list.Enable.assert_not_called()

    def test_account_change_refreshes_and_keeps_account_focus(self) -> None:
        frame = SimpleNamespace(
            refresh_all=Mock(),
            account_choice=SimpleNamespace(SetFocus=Mock()),
        )

        MainFrame.on_account_changed(frame)

        frame.refresh_all.assert_called_once_with()
        frame.account_choice.SetFocus.assert_called_once_with()

    def test_account_choice_reload_selects_requested_account(self) -> None:
        focus_owner = object()
        first = Account(id="first", email_address="first@example.com")
        second = Account(id="second", email_address="second@example.com")
        frame = SimpleNamespace(
            accounts=[first, second],
            account_choice=SimpleNamespace(Set=Mock(), SetSelection=Mock()),
            refresh_all=Mock(),
            SetStatusText=Mock(),
        )

        with (
            patch(
                "accessible_mail.main_frame.focused_control",
                return_value=focus_owner,
            ),
            patch("accessible_mail.main_frame.restore_control_focus") as restore_focus,
            patch("accessible_mail.app.wx.CallAfter") as call_after,
        ):
            MainFrame._load_accounts_to_choice(frame, second.id)
            call_after.call_args.args[0]()

        frame.account_choice.Set.assert_called_once_with([first.label, second.label])
        frame.account_choice.SetSelection.assert_called_once_with(1)
        restore_focus.assert_called_once_with(focus_owner)
        call_after.assert_called_once()
        frame.refresh_all.assert_called_once_with()

    def test_oauth_services_and_manual_form_have_ok_buttons(self) -> None:
        oauth_source = inspect.getsource(AccountDialog.show_oauth_provider_view)
        manual_source = inspect.getsource(AccountDialog.show_manual_view)

        self.assertIn('label="موافق"', oauth_source)
        self.assertIn("ok_button.SetDefault()", oauth_source)
        self.assertIn("wx.ListBox", oauth_source)
        self.assertIn("on_oauth_provider_activate", oauth_source)
        self.assertIn('label="رجوع"', oauth_source)
        self.assertIn('label="إلغاء"', oauth_source)
        self.assertIn('label="موافق"', manual_source)
        self.assertIn("on_manual_ok", manual_source)

    def test_manual_sign_in_starts_with_email_service_choice(self) -> None:
        manual_source = inspect.getsource(AccountDialog.show_manual_view)

        provider_position = manual_source.index("self.manual_provider = wx.Choice")
        account_name_position = manual_source.index("self.display_name = self._text")

        self.assertLess(provider_position, account_name_position)
        self.assertIn("self.finish_panel(root, self.manual_provider)", manual_source)

    def test_manual_provider_is_inferred_from_existing_account(self) -> None:
        google_account = Account(email_address="person@gmail.com")
        microsoft_account = Account(imap_server="outlook.office365.com")

        self.assertEqual(
            AccountDialog.manual_provider_index_for_account(google_account),
            0,
        )
        self.assertEqual(
            AccountDialog.manual_provider_index_for_account(microsoft_account),
            1,
        )

    def test_manual_provider_choice_fills_microsoft_servers(self) -> None:
        class TextValue:
            def __init__(self, value: str = "") -> None:
                self.value = value

            def GetValue(self) -> str:
                return self.value

            def SetValue(self, value: str) -> None:
                self.value = value

        class CheckValue:
            def __init__(self, value: bool = False) -> None:
                self.value = value

            def SetValue(self, value: bool) -> None:
                self.value = value

        dialog = SimpleNamespace(
            selected_manual_provider_id=lambda: MANUAL_PROVIDER_MICROSOFT,
            imap_server=TextValue(),
            imap_port=TextValue(),
            smtp_server=TextValue(),
            smtp_port=TextValue(),
            spam_mailbox=TextValue(),
            imap_ssl=CheckValue(),
            smtp_ssl=CheckValue(True),
            smtp_starttls=CheckValue(False),
        )

        AccountDialog.apply_selected_manual_provider_defaults(
            dialog,
            overwrite=True,
        )

        self.assertEqual(dialog.imap_server.value, "outlook.office365.com")
        self.assertEqual(dialog.smtp_server.value, "smtp-mail.outlook.com")
        self.assertEqual(dialog.spam_mailbox.value, "Junk Email")
        self.assertTrue(dialog.imap_ssl.value)
        self.assertFalse(dialog.smtp_ssl.value)
        self.assertTrue(dialog.smtp_starttls.value)

    def test_manual_provider_choice_fills_google_servers(self) -> None:
        def text_control() -> SimpleNamespace:
            return SimpleNamespace(
                value="",
                GetValue=lambda: "",
                SetValue=Mock(),
            )

        dialog = SimpleNamespace(
            selected_manual_provider_id=lambda: MANUAL_PROVIDER_GOOGLE,
            imap_server=text_control(),
            imap_port=text_control(),
            smtp_server=text_control(),
            smtp_port=text_control(),
            spam_mailbox=text_control(),
            imap_ssl=SimpleNamespace(SetValue=Mock()),
            smtp_ssl=SimpleNamespace(SetValue=Mock()),
            smtp_starttls=SimpleNamespace(SetValue=Mock()),
        )

        AccountDialog.apply_selected_manual_provider_defaults(
            dialog,
            overwrite=True,
        )

        dialog.imap_server.SetValue.assert_called_once_with("imap.gmail.com")
        dialog.smtp_server.SetValue.assert_called_once_with("smtp.gmail.com")

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

    @patch("accessible_mail.main_frame.save_accounts")
    def test_oauth_expiry_clears_the_account_that_failed_not_current_selection(
        self,
        save: Mock,
    ) -> None:
        failed_account = Account(
            id="failed",
            oauth_provider="microsoft",
            oauth_access_token="failed-access",
            oauth_refresh_token="failed-refresh",
            oauth_token_expiry=99.0,
        )
        selected_account = Account(
            id="selected",
            oauth_provider="microsoft",
            oauth_access_token="selected-access",
            oauth_refresh_token="selected-refresh",
            oauth_token_expiry=88.0,
        )
        frame = SimpleNamespace(
            accounts=[failed_account, selected_account],
            selected_account=lambda: selected_account,
            show_notification=Mock(),
            SetStatusText=Mock(),
        )
        error = OAuthReauthenticationRequired(
            "أعد تسجيل الدخول",
            account_id=failed_account.id,
        )

        MainFrame.handle_oauth_reauthentication_required(frame, error)

        self.assertEqual(failed_account.oauth_access_token, "")
        self.assertEqual(failed_account.oauth_refresh_token, "")
        self.assertEqual(failed_account.oauth_token_expiry, 0.0)
        self.assertEqual(selected_account.oauth_access_token, "selected-access")
        save.assert_called_once_with(frame.accounts)

    @patch("accessible_mail.main_frame.save_accounts")
    @patch("accessible_mail.main_frame.run_browser_oauth_flow")
    @patch(
        "accessible_mail.main_frame.load_oauth_clients",
        return_value={
            "microsoft": {
                "client_id": "client-id",
                "client_secret": "",
            }
        },
    )
    def test_reauthentication_uses_the_main_background_worker(
        self,
        _load_clients: Mock,
        oauth_flow: Mock,
        save: Mock,
    ) -> None:
        account = Account(
            id="account",
            oauth_provider="microsoft",
            email_address="old@example.com",
        )
        result = SimpleNamespace(
            provider_id="microsoft",
            access_token="new-access",
            refresh_token="new-refresh",
            expires_at=1234.0,
            email_address="new@example.com",
            display_name="New User",
        )
        oauth_flow.return_value = result
        run_worker = Mock()
        frame = SimpleNamespace(
            _reauthentication_active=False,
            selected_account=lambda: account,
            accounts=[account],
            run_worker=run_worker,
            content_cache={"old": object()},
            SetStatusText=Mock(),
            refresh_all=Mock(),
            show_notification=Mock(),
            show_sign_in_result=Mock(),
        )

        MainFrame.on_reauthenticate_account(frame)

        oauth_flow.assert_not_called()
        run_worker.assert_called_once()
        _message, work, done, _failed = run_worker.call_args.args
        done(work())

        oauth_flow.assert_called_once_with("microsoft", "client-id", "")
        self.assertFalse(frame._reauthentication_active)
        self.assertEqual(account.oauth_access_token, "new-access")
        self.assertEqual(account.email_address, "new@example.com")
        self.assertFalse(frame.content_cache)
        save.assert_called_once_with(frame.accounts)
        frame.show_sign_in_result.assert_called_once()
        result_title, result_details = frame.show_sign_in_result.call_args.args
        self.assertEqual(result_title, "نجاح تسجيل الدخول")
        self.assertIn("new@example.com", result_details)
        self.assertNotIn("new-access", result_details)
        self.assertNotIn("new-refresh", result_details)
        frame.refresh_all.assert_called_once_with()
