from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wx

from accessible_mail.address_book import AddressEntry, add_address, load_address_book, save_address_book
from accessible_mail.address_book_dialog import AddressBookDialog
from accessible_mail.address_book_storage import address_hash
from accessible_mail.folder_store import FOLDER_CONVERSATIONS, FolderStore, ProtectedAddressBookError
from accessible_mail.main_frame import MainFrame


def test_protect(data, entropy=None):
    # Test double only. Production uses Windows DPAPI, never this cipher.
    key = entropy or b"test-windows-user"
    mask = b"".join(hashlib.sha256(key + index.to_bytes(4, "big")).digest()
                    for index in range((len(data) + 31) // 32))
    blob = bytes(a ^ b for a, b in zip(data, mask, strict=False))
    return hmac.digest(key, blob, "sha256") + blob


def test_unprotect(blob, entropy=None):
    key = entropy or b"test-windows-user"
    if not hmac.compare_digest(blob[:32], hmac.digest(key, blob[32:], "sha256")):
        raise ValueError("wrong key")
    mask = b"".join(hashlib.sha256(key + index.to_bytes(4, "big")).digest()
                    for index in range((len(blob) - 32 + 31) // 32))
    return bytes(a ^ b for a, b in zip(blob[32:], mask, strict=False))


class AddressBookLockTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.directory / "folders.db"
        self.legacy = self.directory / "address_book.json"
        self.enterContext(patch("accessible_mail.address_book.address_book_path", return_value=self.legacy))
        self.enterContext(patch("accessible_mail.folder_store.protect_bytes", side_effect=test_protect))
        self.enterContext(patch("accessible_mail.folder_store.unprotect_bytes", side_effect=test_unprotect))
        self.store = FolderStore(self.path)
        self.private = AddressEntry("private-person@example.test", pinned=True, name="Private Contact Name")
        self.public = AddressEntry("public-person@example.test", name="Public Name")

    def make_folder(self):
        save_address_book([self.private, self.public])
        return self.store.create_folder("account-a", FOLDER_CONVERSATIONS, "People", [self.private.email])

    def lock_and_open(self, folder):
        self.store.lock_target("account-a", "folder", folder.id, "password-123")
        self.store.unlock_target("account-a", "folder", folder.id, "password-123")

    def test_lock_protects_contact_data_not_just_membership(self):
        folder = self.make_folder()
        self.store.lock_target("account-a", "folder", folder.id, "password-123")
        self.assertEqual(load_address_book(), [self.public])
        self.assertNotIn(self.private.email.encode(), self.path.read_bytes())
        self.assertNotIn(self.private.name.encode(), self.path.read_bytes())
        self.assertFalse(self.legacy.exists())
        self.assertFalse(self.legacy.with_suffix(".json.bak").exists())
        reopened = FolderStore(self.path)
        with self.assertRaises(ValueError):
            reopened.unlock_target("account-a", "folder", folder.id, "wrong-password")
        self.assertFalse(reopened.is_open("account-a", "folder", folder.id))
        reopened.unlock_target("account-a", "folder", folder.id, "password-123")
        self.assertEqual(reopened.folder_addresses("account-a", folder.id), [self.private])
        # Even an open session does not expose contacts to compose/forward pickers.
        self.assertEqual(load_address_book(), [self.public])

    def test_stale_public_save_cannot_expose_or_destroy_private_contact(self):
        folder = self.make_folder()
        self.store.lock_target("account-a", "folder", folder.id, "password-123")
        save_address_book([self.private, AddressEntry("other@example.test")])
        self.assertEqual([entry.email for entry in load_address_book()], ["other@example.test"])
        self.assertEqual(add_address(self.private.email.upper()), (False, "duplicate"))
        self.store.unlock_target("account-a", "folder", folder.id, "password-123")
        self.assertEqual(self.store.folder_addresses("account-a", folder.id), [self.private])

    def test_add_rename_pin_and_delete_are_inside_password_scope(self):
        folder = self.make_folder()
        self.lock_and_open(folder)
        second = AddressEntry("second@example.test", name="Second Private Name")
        self.store.save_folder_address("account-a", folder.id, second)
        renamed = AddressEntry("renamed@example.test", pinned=True, name="Renamed Private Name")
        self.store.save_folder_address("account-a", folder.id, renamed, previous_email=second.email)
        self.store.close_all_locks()
        self.assertEqual(load_address_book(), [self.public])
        for secret in (second.email, second.name, renamed.email, renamed.name):
            self.assertNotIn(secret.encode(), self.path.read_bytes())
        self.store.unlock_target("account-a", "folder", folder.id, "password-123")
        self.assertEqual(self.store.list_items("account-a", folder.id), [self.private.email, renamed.email])
        self.assertEqual(self.store.folder_addresses("account-a", folder.id), [self.private, renamed])
        self.store.delete_folder_address("account-a", folder.id, renamed.email)
        self.store.remove_lock("account-a", "folder", folder.id)
        self.assertEqual({entry.email for entry in load_address_book()}, {self.private.email, self.public.email})

    def test_removing_contact_from_folder_restores_it_without_deleting_it(self):
        folder = self.make_folder()
        self.lock_and_open(folder)
        self.store.remove_item("account-a", folder.id, self.private.email)
        self.assertIn(self.private, load_address_book())
        self.store.close_all_locks()
        self.store.unlock_target("account-a", "folder", folder.id, "password-123")
        self.assertEqual(self.store.folder_addresses("account-a", folder.id), [])

    def test_lock_failure_rolls_back_contact_and_membership(self):
        folder = self.make_folder()
        with self.store._connect() as conn:
            conn.execute("CREATE TRIGGER reject_lock BEFORE INSERT ON local_locks BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.lock_target("account-a", "folder", folder.id, "password-123")
        self.assertFalse(self.store.is_locked("account-a", "folder", folder.id))
        self.assertEqual(self.store.list_items("account-a", folder.id), [self.private.email])
        self.assertIn(self.private, load_address_book())

    def test_contact_edit_failure_does_not_leak_new_data_or_lose_old_data(self):
        folder = self.make_folder()
        self.lock_and_open(folder)
        with self.store._connect() as conn:
            conn.execute("CREATE TRIGGER reject_edit BEFORE UPDATE ON local_locks BEGIN SELECT RAISE(ABORT, 'denied'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_folder_address("account-a", folder.id, AddressEntry("new@example.test", name="New Secret"))
        self.assertEqual(self.store.folder_addresses("account-a", folder.id), [self.private])
        self.assertNotIn(b"new@example.test", self.path.read_bytes())
        self.assertEqual(load_address_book(), [self.public])

    def test_failed_lock_removal_preserves_encrypted_contact(self):
        folder = self.make_folder()
        self.lock_and_open(folder)
        with self.store._connect() as conn:
            conn.execute("CREATE TRIGGER reject_remove BEFORE DELETE ON local_locks BEGIN SELECT RAISE(ABORT, 'denied'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.remove_lock("account-a", "folder", folder.id)
        self.store.close_all_locks()
        self.assertEqual(load_address_book(), [self.public])
        self.store.unlock_target("account-a", "folder", folder.id, "password-123")
        self.assertEqual(self.store.folder_addresses("account-a", folder.id), [self.private])

    def test_stale_folder_session_cannot_overwrite_other_window_membership(self):
        folder = self.make_folder()
        self.lock_and_open(folder)
        second_store = FolderStore(self.path)
        second_store.unlock_target("account-a", "folder", folder.id, "password-123")
        self.store.save_folder_address("account-a", folder.id, AddressEntry("second@example.test"))
        with self.assertRaises(ValueError):
            second_store.save_folder_address("account-a", folder.id, AddressEntry("lost@example.test"))
        with self.assertRaises(ValueError):
            second_store.remove_lock("account-a", "folder", folder.id)
        self.assertEqual(self.store.list_items("account-a", folder.id), [self.private.email, "second@example.test"])

    def test_contact_shared_with_another_account_cannot_be_partially_locked(self):
        folder = self.make_folder()
        other = self.store.create_folder("account-b", FOLDER_CONVERSATIONS, "Other", [self.private.email])
        with self.assertRaises(ValueError):
            self.store.lock_target("account-a", "folder", folder.id, "password-123")
        self.assertIn(self.private, load_address_book())
        self.assertEqual(self.store.list_items("account-b", other.id), [self.private.email])

    def test_locked_contact_cannot_be_referenced_from_another_account_folder(self):
        folder = self.make_folder()
        self.lock_and_open(folder)
        other = self.store.create_folder("account-b", FOLDER_CONVERSATIONS, "Other")
        with self.assertRaises(ValueError):
            self.store.add_items("account-b", other.id, [self.private.email])
        with self.assertRaises(ValueError):
            self.store.create_folder("account-b", FOLDER_CONVERSATIONS, "Copy", [self.private.email])
        self.assertEqual(self.store.list_items("account-b", other.id), [])

    def test_deleting_account_cannot_orphan_encrypted_contacts(self):
        folder = self.make_folder()
        self.lock_and_open(folder)
        with self.assertRaises(ValueError):
            self.store.delete_account("account-a")
        self.store.remove_lock("account-a", "folder", folder.id)
        self.store.delete_account("account-a")
        self.assertIn(self.private, load_address_book())

    def test_corrupt_contact_ciphertext_does_not_open_a_session(self):
        folder = self.make_folder()
        self.store.lock_target("account-a", "folder", folder.id, "password-123")
        with self.store._connect() as conn:
            conn.execute("UPDATE address_records SET payload = ? WHERE entry_hash = ?", (b"corrupt", address_hash(self.private.email)))
        with self.assertRaises(ValueError):
            self.store.unlock_target("account-a", "folder", folder.id, "password-123")
        self.assertFalse(self.store.is_open("account-a", "folder", folder.id))

    def test_legacy_json_backup_and_temp_are_removed_only_after_import(self):
        payload = [{"email": self.private.email, "name": self.private.name, "pinned": True}]
        self.legacy.write_text(json.dumps(payload), encoding="utf-8")
        backup = self.legacy.with_suffix(".json.bak")
        backup.write_text(json.dumps(payload), encoding="utf-8")
        temporary = self.legacy.with_name(".address_book.json.123.tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        external_backup = self.directory / "user-backup.json"
        external_backup.write_text("keep", encoding="utf-8")
        self.assertEqual(load_address_book(), [self.private])
        self.assertFalse(self.legacy.exists())
        self.assertFalse(backup.exists())
        self.assertFalse(temporary.exists())
        self.assertTrue(external_backup.exists())

    def test_cleanup_failure_blocks_locking_but_keeps_imported_contacts(self):
        self.legacy.write_text(json.dumps([{"email": self.private.email, "name": self.private.name}]), encoding="utf-8")
        unlink = Path.unlink

        def deny(path, *args, **kwargs):
            if path == self.legacy:
                raise PermissionError("controlled folder access")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", deny), self.assertRaises(PermissionError):
            self.store.create_folder("account-a", FOLDER_CONVERSATIONS, "People", [self.private.email])
        self.assertTrue(self.legacy.exists())
        # Retry uses the committed import, not a newer/stale JSON replacement.
        self.legacy.write_text("[]", encoding="utf-8")
        self.assertEqual(load_address_book()[0].email, self.private.email)

    def test_migration_write_failure_preserves_json_and_retries(self):
        self.legacy.write_text(json.dumps([{"email": self.private.email, "name": self.private.name}]), encoding="utf-8")
        with patch("accessible_mail.address_book_storage.entry_payload", side_effect=PermissionError("denied")), self.assertRaises(PermissionError):
            load_address_book()
        self.assertTrue(self.legacy.exists())
        self.assertEqual(load_address_book()[0].name, self.private.name)

    def test_invalid_primary_recovers_from_valid_backup_before_cleanup(self):
        self.legacy.write_text("broken", encoding="utf-8")
        self.legacy.with_suffix(".json.bak").write_text(json.dumps([{"email": self.private.email}]), encoding="utf-8")
        self.assertEqual(load_address_book()[0].email, self.private.email)
        self.assertFalse(self.legacy.exists())

    def test_unreadable_legacy_data_is_not_replaced_with_an_empty_book(self):
        self.legacy.write_text("not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_address_book()
        self.assertEqual(self.legacy.read_text(encoding="utf-8"), "not json")

    def test_old_membership_only_lock_is_hidden_and_upgraded_after_password(self):
        salt = b"s" * 16
        entropy = self.store._lock_entropy("password-123", salt)
        payload = test_protect(json.dumps({"keys": [self.private.email], "folders": {}}).encode(), entropy)
        with self.store._connect() as conn:
            conn.execute("INSERT INTO folders(id, account_id, kind, name) VALUES ('old', 'account-a', 'conversations', 'Old')")
            conn.execute("INSERT INTO local_locks VALUES ('folder', 'old', 'account-a', ?, ?, 1)", (salt, payload))
            conn.execute("INSERT INTO local_lock_hashes VALUES ('folder', 'old', 'account-a', ?)",
                         (self.store.locked_key_hash("account-a", self.private.email),))
        self.legacy.write_text(json.dumps([{"email": self.private.email, "name": self.private.name}]), encoding="utf-8")
        self.assertEqual(load_address_book(), [])
        save_address_book([])
        self.store.unlock_target("account-a", "folder", "old", "password-123")
        self.assertEqual(self.store.folder_addresses("account-a", "old")[0].name, self.private.name)
        self.assertNotIn(self.private.name.encode(), self.path.read_bytes())

    def test_dialog_releases_decrypted_contacts_on_back_and_destroy(self):
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        folder = self.make_folder()
        self.store.lock_target("account-a", "folder", folder.id, "password-123")
        with patch("accessible_mail.address_book_dialog.FolderStore", return_value=self.store):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                self.assertEqual(dialog.entries, [self.public])
                with patch.object(dialog, "ask_local_lock_password", return_value="password-123"):
                    dialog.address_list.SetSelection(0)
                    dialog.on_activate(Mock())
                self.assertEqual(dialog.visible_entries, [self.private])
                dialog.on_leave_conversation_folder()
                self.assertEqual(dialog.entries, [self.public])
                self.assertEqual(dialog._folder_selection_entries, [])
                self.assertFalse(self.store.is_open("account-a", "folder", folder.id))
            finally:
                dialog.Destroy()

    def test_public_folder_contact_rename_updates_membership(self):
        folder = self.make_folder()
        renamed = AddressEntry("new@example.test", name="New Name")
        self.store.save_folder_address("account-a", folder.id, renamed, previous_email=self.private.email)
        self.assertEqual(self.store.list_items("account-a", folder.id), [renamed.email])
        self.assertNotIn(self.private, load_address_book())
        self.assertIn(renamed, load_address_book())

    def test_account_removal_is_blocked_before_oauth_revocation(self):
        folder = self.make_folder()
        self.lock_and_open(folder)
        account = SimpleNamespace(id="account-a")
        frame = SimpleNamespace(_folder_store=self.store, selected_account=lambda: account, run_worker=Mock())
        with patch("accessible_mail.main_frame.wx.MessageBox") as message_box:
            MainFrame.on_remove_account(frame)
        frame.run_worker.assert_not_called()
        message_box.assert_called_once()

    def test_account_callback_preserves_accounts_when_cleanup_is_blocked(self):
        account = SimpleNamespace(id="account-a")
        frame = SimpleNamespace(accounts=[account], service=SimpleNamespace(
            delete_cached_account=Mock(side_effect=ProtectedAddressBookError("locked"))))
        with patch("accessible_mail.main_frame.save_accounts") as save, patch("accessible_mail.main_frame.wx.MessageBox"):
            MainFrame._remove_account_locally(frame, account, 0)
        save.assert_not_called()
        self.assertEqual(frame.accounts, [account])

    def test_root_add_cannot_claim_a_protected_duplicate_was_added(self):
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        folder = self.make_folder()
        self.lock_and_open(folder)
        self.store.close_all_locks()
        with patch("accessible_mail.address_book_dialog.FolderStore", return_value=self.store):
            dialog = AddressBookDialog(parent, account_id="account-a")
            try:
                with patch.object(dialog, "request_email", return_value=self.private.email), \
                     patch("accessible_mail.address_book_dialog.request_custom_address_name", return_value="Replacement"), \
                     patch.object(dialog, "show_duplicate_message") as duplicate:
                    dialog.on_add(Mock())
                duplicate.assert_called_once()
                self.assertEqual(dialog.entries, [self.public])
            finally:
                dialog.Destroy()
        self.store.unlock_target("account-a", "folder", folder.id, "password-123")
        self.assertEqual(self.store.folder_addresses("account-a", folder.id), [self.private])


@unittest.skipUnless(os.environ.get("PAM_REAL_DPAPI_TEST") == "1", "requires real Windows DPAPI")
class RealAddressBookLockTests(unittest.TestCase):
    def test_real_encryption_reopen_edit_remove_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "folders.db"
            with patch("accessible_mail.address_book.address_book_path", return_value=path.with_name("address_book.json")):
                secret = AddressEntry("private@example.test", pinned=True, name="Private Person")
                save_address_book([secret])
                store = FolderStore(path)
                folder = store.create_folder("account", FOLDER_CONVERSATIONS, "Private", [secret.email])
                store.lock_target("account", "folder", folder.id, "password-123")
                self.assertEqual(load_address_book(), [])
                self.assertNotIn(secret.email.encode(), path.read_bytes())
                self.assertNotIn(secret.name.encode(), path.read_bytes())
                reopened = FolderStore(path)
                with self.assertRaises(ValueError):
                    reopened.unlock_target("account", "folder", folder.id, "wrong-password")
                reopened.unlock_target("account", "folder", folder.id, "password-123")
                self.assertEqual(reopened.folder_addresses("account", folder.id), [secret])
                second = AddressEntry("second@example.test", name="Second Person")
                reopened.save_folder_address("account", folder.id, second)
                reopened.close_all_locks()
                reopened.unlock_target("account", "folder", folder.id, "password-123")
                self.assertEqual(len(reopened.folder_addresses("account", folder.id)), 2)
                reopened.remove_item("account", folder.id, second.email)
                self.assertIn(second, load_address_book())
                reopened.remove_lock("account", "folder", folder.id)
                self.assertIn(secret, load_address_book())
