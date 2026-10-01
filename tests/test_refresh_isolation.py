from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail.main_frame import MainFrame
from accessible_mail.email_service import MailSyncResult
from accessible_mail.models import Account, MessageSummary


class RefreshIsolationTests(unittest.TestCase):
    def frame(self):
        account = Account(id="account-a", email_address="a@example.com", spam_mailbox="SPAM", sent_mailbox="SENT")
        selection = {"account": account}
        jobs = []
        pages = {key: Mock(messages=[]) for key in ("inbox", "spam", "sent", "all")}
        frame = SimpleNamespace(
            selected_account=lambda: selection["account"], ensure_password=lambda _account: True,
            displayed_account_id=account.id, _account_switch_target_id=None,
            _all_mailboxes_by_account={account.id: "ALL"}, pages=pages, service=Mock(),
            set_transfer_progress=Mock(), SetStatusText=Mock(), _visible_category_ids=[],
            load_selected_folder=Mock(), load_custom_sections=Mock(),
            load_selected_custom_category=Mock(),
            refresh_local_category_visibility=Mock(), remember_inbox_messages=Mock(),
            new_inbox_count=lambda *_args: 0, finish_account_switch=Mock(),
            run_worker=lambda _status, work, done, failed=None: jobs.append((work, done, failed)),
        )
        frame.service.cached_messages.return_value = []
        frame.service.list_messages.return_value = []
        return frame, selection, jobs

    def result(self, uid):
        return ([MessageSummary(uid=uid, mailbox="INBOX")], [], [], [], "SPAM", "SENT", "ALL", set(),
                {"spam": "SPAM", "sent": "SENT", "all": "ALL"})

    def test_older_refresh_cannot_replace_the_latest_refresh(self):
        frame, _selection, jobs = self.frame()
        MainFrame.refresh_all(frame)
        MainFrame.refresh_all(frame)
        jobs[1][1](self.result("new"))
        jobs[0][1](self.result("old"))
        calls = frame.pages["inbox"].reconcile_recent_messages.call_args_list
        self.assertEqual([call.args[0][0].uid for call in calls], ["new"])

    def test_account_a_b_a_cannot_reuse_first_account_a_refresh(self):
        frame, selection, jobs = self.frame()
        first = selection["account"]
        MainFrame.refresh_all(frame)
        second = Account(id="account-b", email_address="b@example.com")
        selection["account"] = second
        frame.displayed_account_id = second.id
        MainFrame.refresh_all(frame)
        selection["account"] = first
        frame.displayed_account_id = first.id
        MainFrame.refresh_all(frame)
        jobs[0][1](self.result("old-account-a"))
        frame.pages["inbox"].reconcile_recent_messages.assert_not_called()

    @patch("accessible_mail.main_frame.call_after_if_open")
    def test_delayed_cached_results_and_progress_are_invalidated(self, queued):
        frame, _selection, jobs = self.frame()
        frame.service.cached_messages.return_value = [MessageSummary(uid="cached", mailbox="INBOX")]
        MainFrame.refresh_all(frame)
        jobs[0][0]()
        delayed = list(queued.call_args_list)
        MainFrame.refresh_all(frame)
        frame.set_transfer_progress.reset_mock()
        for call in delayed:
            call.args[1](*call.args[2:])
        frame.pages["inbox"].merge_messages.assert_not_called()
        frame.set_transfer_progress.assert_not_called()

    def test_obsolete_error_is_handled_without_affecting_new_refresh(self):
        frame, _selection, jobs = self.frame()
        MainFrame.refresh_all(frame)
        MainFrame.refresh_all(frame)
        self.assertTrue(jobs[0][2](OSError("synthetic old error")))
        self.assertFalse(jobs[1][2](OSError("synthetic current error")))

    def test_handled_obsolete_error_does_not_erase_active_worker_progress(self):
        frame = SimpleNamespace(_active_worker_count=2, set_busy=Mock(),
                                SetStatusText=Mock(), reset_transfer_progress=Mock())
        MainFrame.on_worker_error(frame, OSError("old error"), lambda _exc: True)
        self.assertEqual(frame._active_worker_count, 1)
        frame.set_busy.assert_not_called()
        frame.SetStatusText.assert_not_called()
        frame.reset_transfer_progress.assert_not_called()

    def test_last_handled_error_does_not_replace_status_from_its_callback(self):
        frame = SimpleNamespace(_active_worker_count=1, set_busy=Mock(),
                                SetStatusText=Mock(), reset_transfer_progress=Mock())
        MainFrame.on_worker_error(frame, OSError("old error"), lambda _exc: True)
        self.assertEqual(frame._active_worker_count, 0)
        frame.set_busy.assert_not_called()
        frame.SetStatusText.assert_not_called()
        frame.reset_transfer_progress.assert_called_once()

    def older_frame(self):
        frame, selection, jobs = self.frame()
        page = frame.pages["inbox"]
        page.selected_filter_key.return_value = "all"
        frame.current_page = lambda: page
        frame.page_key_for_page = lambda _page: "inbox"
        frame.mailbox_for_page_key = lambda *_args: "INBOX"
        frame._loading_older_keys = set()
        frame._older_messages_exhausted = set()
        frame._syncing_page_keys = set()
        frame._account_view_generation = 0
        frame.reset_transfer_progress = Mock()
        frame.progress_percent = lambda *_args: 50
        return frame, selection, jobs

    def test_older_messages_reject_previous_account_visit_and_clean_busy_key(self):
        frame, _selection, jobs = self.older_frame()
        MainFrame.load_older_messages(frame, automatic=False)
        frame._account_view_generation += 2  # A -> B -> A
        jobs[0][1](("inbox", [MessageSummary(uid="old", mailbox="INBOX")], "INBOX"))
        frame.pages["inbox"].merge_messages.assert_not_called()
        self.assertEqual(frame._loading_older_keys, set())

    def test_older_messages_reject_changed_selection_before_display_switch(self):
        frame, selection, jobs = self.older_frame()
        MainFrame.load_older_messages(frame, automatic=False)
        selection["account"] = Account(id="account-b")
        jobs[0][1](("inbox", [MessageSummary(uid="old", mailbox="INBOX")], "INBOX"))
        frame.pages["inbox"].merge_messages.assert_not_called()
        self.assertTrue(jobs[0][2](OSError("old error")))

    @patch("accessible_mail.main_frame.call_after_if_open")
    def test_sync_is_scoped_to_account_and_drops_obsolete_progress(self, queued):
        frame, selection, jobs = self.older_frame()
        frame.service.sync_all_older_messages.return_value = MailSyncResult("INBOX", [], 0, 0)
        MainFrame.on_sync_all_messages(frame)
        jobs[0][0]()
        progress = frame.service.sync_all_older_messages.call_args.kwargs["on_progress"]
        progress([MessageSummary(uid="old", mailbox="INBOX")], 1, 1, 1, 2)
        update = queued.call_args.args[1]
        frame._account_view_generation += 2
        update()
        jobs[0][1](("inbox", MailSyncResult("INBOX", [], 0, 0), "INBOX"))
        frame.pages["inbox"].merge_messages.assert_not_called()
        self.assertTrue(jobs[0][2](OSError("old sync error")))
        # A's background synchronization must not block a new B synchronization.
        selection["account"] = Account(id="account-b")
        frame.displayed_account_id = "account-b"
        MainFrame.on_sync_all_messages(frame)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(frame._syncing_page_keys, {("account-a", "inbox"), ("account-b", "inbox")})

    def test_new_mail_poll_rejects_previous_account_visit(self):
        frame, selection, _jobs = self.older_frame()
        frame._account_view_generation = 2
        frame._polling_new_mail = True
        frame.notify_new_mail = Mock()
        MainFrame.finish_new_mail_poll(frame, selection["account"],
                                      [MessageSummary(uid="old", mailbox="INBOX")], 1, True, 0)
        self.assertFalse(frame._polling_new_mail)
        frame.pages["inbox"].reconcile_recent_messages.assert_not_called()
        frame.notify_new_mail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
