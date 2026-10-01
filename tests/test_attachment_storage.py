from __future__ import annotations

import os
import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import tempfile
import unittest
from unittest.mock import Mock, patch

from accessible_mail.email_service import EmailService, MailError
from accessible_mail.gmail_api_service import GmailApiService
from accessible_mail.models import Account, LinkItem, MessageSummary

from accessible_mail.attachment_storage import (
    cleanup_opened_attachment_session,
    cleanup_stale_opened_attachments,
    opened_attachment_session_dir,
)


class AttachmentStorageTests(unittest.TestCase):
    def test_parallel_downloads_have_independent_temporary_files(self) -> None:
        for service_class in (EmailService, GmailApiService):
            with self.subTest(service=service_class.__name__), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "attachment.txt"
                service = service_class(cache=Mock())
                data = [b"first complete file", b"second complete file"]
                barrier = threading.Barrier(2)

                def download(content, service=service, destination=destination, barrier=barrier):
                    item = LinkItem(text="file", kind="attachment", data=base64.b64encode(content).decode("ascii"))
                    return service.download_attachment(Account(), MessageSummary(uid="1", mailbox="INBOX"), item,
                                                       destination, lambda _current, _total: barrier.wait(timeout=10))

                with ThreadPoolExecutor(max_workers=2) as workers:
                    self.assertEqual(list(workers.map(download, data)), [destination, destination])
                self.assertIn(destination.read_bytes(), data)
                self.assertEqual(list(Path(directory).glob("*.part")), [])

    def test_failed_download_keeps_existing_destination_and_removes_temporary_file(self) -> None:
        for service_class in (EmailService, GmailApiService):
            with self.subTest(service=service_class.__name__), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "keep.txt"
                destination.write_bytes(b"keep this file")
                with self.assertRaises(MailError):
                    service_class(cache=Mock()).download_attachment(Account(), MessageSummary(uid="1", mailbox="INBOX"),
                                                                   LinkItem(text="invalid", kind="attachment"), destination)
                self.assertEqual(destination.read_bytes(), b"keep this file")
                self.assertEqual(list(Path(directory).glob("*.part")), [])

    def test_session_cleanup_removes_only_the_current_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "accessible_mail.attachment_storage.tempfile.gettempdir",
                    return_value=directory,
                ),
                patch(
                    "accessible_mail.attachment_storage._SESSION_NAME",
                    "current-session",
                ),
            ):
                current = opened_attachment_session_dir()
                (current / "message.txt").write_text("private", encoding="utf-8")
                other = current.parent / "other-session"
                other.mkdir()
                (other / "still-open.txt").write_text("keep", encoding="utf-8")

                cleanup_opened_attachment_session()

                self.assertFalse(current.exists())
                self.assertTrue(other.exists())

    def test_stale_cleanup_removes_old_sessions_and_legacy_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "accessible_mail.attachment_storage.tempfile.gettempdir",
                    return_value=directory,
                ),
                patch(
                    "accessible_mail.attachment_storage._SESSION_NAME",
                    "current-session",
                ),
            ):
                root = opened_attachment_session_dir().parent
                stale_session = root / "stale-session"
                stale_session.mkdir()
                (stale_session / "old.txt").write_text("old", encoding="utf-8")
                recent_session = root / "recent-session"
                recent_session.mkdir()
                legacy_file = root / "legacy.txt"
                legacy_file.write_text("legacy", encoding="utf-8")
                os.utime(stale_session, (100.0, 100.0))
                os.utime(legacy_file, (100.0, 100.0))
                os.utime(recent_session, (950.0, 950.0))

                cleanup_stale_opened_attachments(
                    now=1000.0,
                    max_age_seconds=100,
                )

                self.assertFalse(stale_session.exists())
                self.assertFalse(legacy_file.exists())
                self.assertTrue(recent_session.exists())
                self.assertTrue((root / "current-session").exists())


if __name__ == "__main__":
    unittest.main()
