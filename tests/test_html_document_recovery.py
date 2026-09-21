import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from accessible_mail.mail_page import MailPage


class HtmlDocumentRecoveryTests(unittest.TestCase):
    def page(self):
        return SimpleNamespace(
            _closed=False, _html_viewer_active=True, _html_loading=False,
            _html_refresh_pending=False, _html_focus_after_load=True,
            html_viewer=SimpleNamespace(RunScript=Mock(), RunScriptAsync=Mock()),
            focus_html_document_start=Mock(),
            message_html=Mock(return_value='<article id="message">test</article>'),
            viewer_text='test', viewer=Mock(), show_plain_viewer=Mock())

    @patch('accessible_mail.mail_page.wx.CallLater')
    def test_loaded_message_is_not_replaced(self, later):
        page = self.page()
        MailPage.verify_html_document(page)
        page.focus_html_document_start.assert_not_called()
        page.html_viewer.RunScript.assert_not_called()
        token = page._html_verify_token
        page.html_viewer.RunScriptAsync.assert_called_once_with(
            f"'pam-verify:{token}:' + Boolean(document.getElementById('message'))")
        MailPage.complete_html_verification(page, token, True)
        page.focus_html_document_start.assert_called_once()
        MailPage.on_html_verification_timeout(page, token)
        page.message_html.assert_not_called()
        page.show_plain_viewer.assert_not_called()

    @patch('accessible_mail.mail_page.wx.CallLater')
    def test_blank_document_recovery_is_bounded(self, later):
        page = self.page()
        MailPage.verify_html_document(page)
        page.html_viewer.RunScript.assert_not_called()
        page.html_viewer.RunScriptAsync.assert_called_once()
        later.assert_called_once()
        MailPage.on_html_verification_timeout(page, page._html_verify_token)
        page.show_plain_viewer.assert_called_once()
        self.assertFalse(page._html_viewer_active)

    def test_closed_or_replaced_document_is_ignored(self):
        for field in ('_closed', '_html_loading', '_html_refresh_pending'):
            page = self.page()
            setattr(page, field, True)
            MailPage.verify_html_document(page)
            page.html_viewer.RunScript.assert_not_called()
            page.html_viewer.RunScriptAsync.assert_not_called()

    @patch('accessible_mail.mail_page.wx.CallLater')
    def test_old_result_does_not_steal_focus(self, later):
        page = self.page()
        MailPage.verify_html_document(page)
        token = page._html_verify_token
        page._html_verify_token = None
        MailPage.complete_html_verification(page, token, True)
        page.focus_html_document_start.assert_not_called()

    @patch('accessible_mail.mail_page.wx.CallAfter')
    def test_result_defers_focus_outside_webview_callback(self, call_after):
        page = self.page()
        event = SimpleNamespace(GetString=lambda: 'pam-verify:12:true', GetInt=lambda: 1)
        MailPage.on_html_script_result(page, event)
        call_after.assert_called_once_with(MailPage.complete_html_verification, page, 12, True)
        page.focus_html_document_start.assert_not_called()

    @patch('accessible_mail.mail_page.wx.CallAfter')
    def test_unrelated_script_result_does_not_move_focus(self, call_after):
        page = self.page()
        event = SimpleNamespace(GetString=lambda: 'undefined')
        MailPage.on_html_script_result(page, event)
        call_after.assert_not_called()
