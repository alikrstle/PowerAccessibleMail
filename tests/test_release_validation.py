from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from accessible_mail.release_validation import private_payload_name, validate_release_directory


class ReleaseValidationTests(unittest.TestCase):
    def test_private_data_backups_and_sqlite_journals_are_rejected(self):
        for name in ("accounts.json", "accounts.json.bak", "accounts.pre-unified-backup.json",
                     ".accounts.json.123.tmp", "folders.db", "folders.db-wal", "folders.db-journal",
                     "address_book.json.bak", "settings.json", "messages.sqlite3-shm",
                     "messages.corrupt-20261001-1234.sqlite3", "folders.corrupt-1234.db-journal"):
            with self.subTest(name=name):
                self.assertTrue(private_payload_name(name))
        for name in ("oauth_clients.json", "README_AR.txt", "Power Accessible Mail.exe", "صورة القفل.jpg"):
            self.assertFalse(private_payload_name(name))

    def test_nested_profile_is_rejected_without_reading_or_deleting_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            internal = root / "_internal"
            internal.mkdir()
            private = internal / "address_book.json"
            private.write_bytes(b"synthetic fixture")
            (internal / "oauth_clients.json").write_bytes(b"{}")
            self.assertEqual(validate_release_directory(root), [private])
            self.assertEqual(private.read_bytes(), b"synthetic fixture")

    def test_private_directories_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".mail_store").mkdir()
            (root / "backgrounds").mkdir()
            self.assertEqual(validate_release_directory(root), [root / ".mail_store"])
