import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail.mail_page import MailPage


class ExternalNavigationTests(unittest.TestCase):
    @patch('accessible_mail.mail_page.wx.CallAfter')
    def test_only_exact_pending_generated_document_is_allowed_once(self, later):
        url = 'data:text/html;charset=utf-8;base64,VEVTVA=='
        page = SimpleNamespace(_html_expected_navigation=url)
        first = self.event(url)
        MailPage.on_html_viewer_navigating(page, first)
        first.Veto.assert_not_called()
        self.assertIsNone(page._html_expected_navigation)
        replay = self.event(url)
        MailPage.on_html_viewer_navigating(page, replay)
        replay.Veto.assert_called_once()
        other = self.event(url + 'untrusted')
        MailPage.on_html_viewer_navigating(page, other)
        other.Veto.assert_called_once()
        later.assert_not_called()

    def event(self, url):
        return SimpleNamespace(GetURL=lambda: url, Veto=Mock())

    @patch('accessible_mail.mail_page.wx.CallAfter')
    def test_web_links_are_external_without_navigation_classification(self, later):
        page = SimpleNamespace(handle_html_command=Mock())
        for url in ('https://example.com/path', 'http://example.com/'):
            event = self.event(url)
            MailPage.on_html_viewer_navigating(page, event)
            event.Veto.assert_called_once()
            self.assertEqual(later.call_args.args[1], url)

    @patch('accessible_mail.mail_page.wx.CallAfter')
    def test_new_window_links_are_external(self, later):
        event = self.event('https://example.com/new')
        MailPage.on_html_viewer_new_window(SimpleNamespace(), event)
        event.Veto.assert_called_once()
        self.assertEqual(later.call_args.args[1], event.GetURL())

    @patch('accessible_mail.mail_page.wx.CallAfter')
    def test_document_and_anchors_stay_local(self, later):
        for url in ('about:blank', 'about:blank#message', '#message'):
            event = self.event(url)
            MailPage.on_html_viewer_navigating(SimpleNamespace(), event)
            event.Veto.assert_not_called()
        later.assert_not_called()

    @patch('accessible_mail.mail_page.wx.CallAfter')
    def test_unsafe_navigation_is_blocked_even_without_user_action(self, later):
        for url in ('javascript:alert(1)', 'file:///C:/Windows/test.exe', 'data:text/html,test', 'about:config'):
            event = self.event(url)
            MailPage.on_html_viewer_navigating(SimpleNamespace(), event)
            event.Veto.assert_called_once()
        later.assert_not_called()

    @patch('accessible_mail.mail_page.wx.CallAfter')
    def test_commands_are_vetoed_before_dispatch_even_if_unknown(self, later):
        event = self.event('pam:unknown')
        page = SimpleNamespace(handle_html_command=Mock(return_value=False))
        MailPage.on_html_viewer_navigating(page, event)
        event.Veto.assert_called_once()
        page.handle_html_command.assert_called_once_with('unknown')
        later.assert_not_called()
