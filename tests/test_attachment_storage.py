from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from accessible_mail.attachment_storage import (
    cleanup_opened_attachment_session,
    cleanup_stale_opened_attachments,
    opened_attachment_session_dir,
)


class AttachmentStorageTests(unittest.TestCase):
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
