import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail.mail_page import MailPage


class TranslationPopupLifecycleTests(unittest.TestCase):
    @patch('accessible_mail.mail_page.announce_context_menu')
    @patch('accessible_mail.mail_page.wx.CallAfter')
    @patch('accessible_mail.mail_page.wx.Menu')
    def test_translation_starts_after_popup_destroyed(self, menu_class, call_after, announce):
        menu = menu_class.return_value
        items = [Mock() for _ in range(10)]
        menu.Append.side_effect = items
        viewer = object()
        summary = SimpleNamespace(is_read=True, is_starred=False, is_pinned=False)
        page = SimpleNamespace(
            actions_button=object(), html_viewer=viewer, viewer=object(),
            multi_select_mode=False, selected_summaries=lambda: [summary],
            selected_summary=lambda: summary, context_return_control=lambda c: c,
            on_reply=Mock(), on_toggle_star=Mock(), on_toggle_read=Mock(),
            on_translate=Mock(), on_toggle_pin=Mock(), on_delete=Mock(),
            schedule_context_focus_restore=Mock(), _pending_html_context_menu=True,
        )

        def popup(_menu):
            handler = next(c.args[1] for c in menu.Bind.call_args_list if c.args[2] is items[2])
            handler(None)
            page.on_translate.assert_not_called()
            call_after.assert_not_called()
            self.assertTrue(page._message_context_menu_open)
            # A duplicate event arriving while the native popup unwinds is dropped.
            MailPage.request_html_context_menu(page)
            self.assertFalse(page._pending_html_context_menu)

        page.context_menu_popup_owner = lambda c: SimpleNamespace(PopupMenu=popup)

        def queued(callback, target):
            menu.Destroy.assert_called_once()
            self.assertFalse(page._message_context_menu_open)
            callback(target)

        call_after.side_effect = queued
        MailPage.show_message_context_menu(page, viewer, True)
        page.on_translate.assert_called_once_with(page)
        page.schedule_context_focus_restore.assert_not_called()
        self.assertFalse(page._pending_html_context_menu)

    def test_deferred_popup_is_discarded_while_menu_is_open(self):
        page = SimpleNamespace(_message_context_menu_open=True, _pending_html_context_menu=True)
        MailPage.show_pending_html_context_menu(page)
        self.assertFalse(page._pending_html_context_menu)


if __name__ == '__main__':
    unittest.main()
