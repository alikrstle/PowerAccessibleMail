import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail.config import ProgramSettings, TRANSLATION_INLINE
from accessible_mail.main_frame import MainFrame, MessageSearchDialog, page_operation_is_current
from accessible_mail.models import Account, MessageSummary


class SearchOperationIsolationTests(unittest.TestCase):
    def test_real_search_collection_sorts_and_deduplicates(self):
        old = MessageSummary(uid="1", mailbox="INBOX")
        new = MessageSummary(uid="2", mailbox="INBOX")
        page = SimpleNamespace(messages=[old, new])
        frame = SimpleNamespace(
            selected_account=lambda: Account(),
            pages=dict.fromkeys(("inbox", "sent", "spam", "all"), page),
        )
        self.assertEqual(MainFrame.searchable_messages(frame), [new, old])

    def test_account_guard_checks_choice_before_refresh_finishes(self):
        frame = SimpleNamespace(displayed_account_id="a", selected_account=lambda: SimpleNamespace(id="b"))
        self.assertFalse(page_operation_is_current(frame, SimpleNamespace(), "a"))

    def test_closed_search_page_rejects_callbacks(self):
        self.assertFalse(page_operation_is_current(SimpleNamespace(), SimpleNamespace(_closed=True), "a"))

    def test_current_page_uses_active_search(self):
        page = object()
        frame = SimpleNamespace(_search_dialog=SimpleNamespace(IsActive=lambda: True, page=page))
        self.assertIs(MainFrame.current_page(frame), page)

    def test_search_escape_and_control_enter(self):
        import wx
        page = SimpleNamespace(focus_message_list=Mock(), toggle_message_and_link_viewers=Mock())
        dialog = SimpleNamespace(page=page, Close=Mock())
        event = Mock()
        event.ControlDown.return_value = False
        event.GetKeyCode.return_value = wx.WXK_ESCAPE
        MessageSearchDialog.on_char_hook(dialog, event)
        dialog.Close.assert_called_once()
        event.ControlDown.return_value = True
        event.AltDown.return_value = False
        event.ShiftDown.return_value = False
        event.GetKeyCode.return_value = wx.WXK_RETURN
        MessageSearchDialog.on_char_hook(dialog, event)
        page.toggle_message_and_link_viewers.assert_called_once()

    @patch("accessible_mail.main_frame.wx.Window.FindFocus", return_value=None)
    def test_translation_cannot_cross_accounts_folders_or_closed_windows(self, _focus):
        for change in ("account", "folder", "closed", "generation"):
            with self.subTest(change=change):
                summary = MessageSummary(uid="7", mailbox="INBOX")
                page = SimpleNamespace(
                    selected_summary=lambda summary=summary: summary,
                    translatable_item_descriptions=lambda: [],
                    show_translated_content=Mock(),
                )
                callbacks = []
                frame = SimpleNamespace(
                    current_page=lambda page=page: page,
                    can_translate_current_message=lambda p: True,
                    confirm_translation_data_transfer=lambda: True,
                    current_content=SimpleNamespace(summary=summary, text="Original"),
                    settings=ProgramSettings(
                        translation_mode=TRANSLATION_INLINE,
                        message_translation_language_selected=True,
                    ),
                    displayed_account_id="a", _message_load_generation=1,
                    run_worker=lambda message, work, done, failed, callbacks=callbacks: callbacks.append(done),
                    SetStatusText=Mock(),
                )
                frame.selected_account = lambda frame=frame: SimpleNamespace(
                    id=frame.displayed_account_id
                )
                MainFrame.on_translate_current_message(frame)
                if change == "account":
                    frame.displayed_account_id = "b"
                elif change == "folder":
                    summary.mailbox = "Sent"
                elif change == "closed":
                    page._closed = True
                else:
                    frame._message_load_generation += 1
                callbacks[0]("Translation")
                page.show_translated_content.assert_not_called()

    @patch("accessible_mail.main_frame.wx.MessageBox")
    def test_delete_completion_does_not_modify_new_account(self, message_box):
        import wx
        message_box.return_value = wx.YES
        account = Account(id="a", oauth_provider="google_gmail_api")
        summary = MessageSummary(uid="7", mailbox="INBOX")
        page = SimpleNamespace(
            selected_summary=lambda: summary,
            selected_filter_key=lambda: "all",
            list=SimpleNamespace(GetFirstSelected=lambda: 0),
            remove_message_by_uid=Mock(),
        )
        callbacks = []
        frame = SimpleNamespace(
            selected_account=lambda: account, displayed_account_id="a",
            pages={"inbox": page}, content_cache={}, current_content=None,
            run_worker=lambda message, work, done: callbacks.append(done),
        )
        MainFrame.on_delete_current_message(frame, page)
        frame.displayed_account_id = "b"
        callbacks[0](None)
        page.remove_message_by_uid.assert_not_called()
