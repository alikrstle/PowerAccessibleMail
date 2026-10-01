from __future__ import annotations

import hashlib
import hmac
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wx
from accessible_mail.address_book import AddressEntry
from accessible_mail.address_book_dialog import AddressBookDialog

from accessible_mail.folder_store import FolderStore, FOLDER_MESSAGES, FOLDER_CONVERSATIONS, message_folder_key
from accessible_mail.models import Account, MessageSummary, MessageContent
from accessible_mail.secure_store import MessageCache
from accessible_mail.main_frame import MainFrame
from accessible_mail.mail_service_router import MailServiceRouter


class LockRegressionTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.store = FolderStore(Path(directory) / "folders.db")
        self.cache = MessageCache(Path(directory) / "messages.db")
        self.cache.set_lock_store(self.store)
        self.account = Account(id="a", email_address="a@example.com")
        self.store.configure_account(self.account)

        def protect(data, entropy=None):
            key = entropy or b"Windows-user"
            mask = b"".join(hashlib.sha256(key + i.to_bytes(4, "big")).digest()
                            for i in range((len(data) + 31) // 32))
            encrypted = bytes(a ^ b for a, b in zip(data, mask, strict=False))
            return hmac.digest(key, encrypted, "sha256") + encrypted

        def unprotect(data, entropy=None):
            key = entropy or b"Windows-user"
            if not hmac.compare_digest(data[:32], hmac.digest(key, data[32:], "sha256")):
                raise ValueError("wrong password")
            mask = b"".join(hashlib.sha256(key + i.to_bytes(4, "big")).digest()
                            for i in range((len(data) - 32 + 31) // 32))
            return bytes(a ^ b for a, b in zip(data[32:], mask, strict=False))

        for module in ("folder_store", "secure_store"):
            self.enterContext(patch(f"accessible_mail.{module}.protect_bytes", side_effect=protect))
            self.enterContext(patch(f"accessible_mail.{module}.unprotect_bytes", side_effect=unprotect))
        self.first = MessageSummary(uid="42", mailbox="INBOX", subject="private", sender_email="friend@example.com")
        self.second = MessageSummary(uid="42", mailbox="Sent", subject="unrelated")
        self.cache.upsert_content(self.account, MessageContent(self.first, "body", []))
        self.cache.upsert_content(self.account, MessageContent(self.second, "sent body", []))
        self.folder = self.store.create_folder("a", FOLDER_MESSAGES, "Private", [message_folder_key(self.first)])

    def lock(self):
        self.store.lock_target("a", "folder", self.folder.id, "password-123")

    def test_conversation_folder_lock_lifecycle_and_membership_encryption(self):
        folder = self.store.create_folder("a", FOLDER_CONVERSATIONS, "People", ["sam@example.com"])
        self.store.lock_target("a", "folder", folder.id, "password-123")
        with self.assertRaises(ValueError):
            self.store.create_folder("a", FOLDER_CONVERSATIONS, "Copy", ["sam@example.com"])
        with self.assertRaises(ValueError):
            self.store.list_items("a", folder.id)
        with self.store._connect() as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM folder_items WHERE folder_id = ?", (folder.id,)).fetchone())
            payload = conn.execute("SELECT payload FROM local_locks WHERE target_id = ?", (folder.id,)).fetchone()[0]
            self.assertNotIn(b"sam@example.com", bytes(payload))
        with self.assertRaises(ValueError):
            self.store.unlock_target("a", "folder", folder.id, "wrong-password")
        self.store.unlock_target("a", "folder", folder.id, "password-123")
        self.assertEqual(self.store.list_items("a", folder.id), ["sam@example.com"])
        self.store.add_items("a", folder.id, ["ali@example.com"])
        self.store.close_target("folder", folder.id)
        self.store.unlock_target("a", "folder", folder.id, "password-123")
        self.assertEqual(self.store.list_items("a", folder.id), ["sam@example.com", "ali@example.com"])
        self.store.remove_item("a", folder.id, "ali@example.com")
        self.store.remove_lock("a", "folder", folder.id)
        self.assertEqual(self.store.list_items("a", folder.id), ["sam@example.com"])

    def test_address_book_locked_folder_requires_explicit_entry_and_relocks_on_back(self):
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        folder = self.store.create_folder("a", FOLDER_CONVERSATIONS, "People", ["sam@example.com"])
        self.store.lock_target("a", "folder", folder.id, "password-123")
        with patch("accessible_mail.address_book_dialog.load_address_book", return_value=[AddressEntry("sam@example.com")]), patch("accessible_mail.address_book_dialog.FolderStore", return_value=self.store):
            dialog = AddressBookDialog(parent, account_id="a")
            try:
                self.assertEqual(dialog.visible_entries, [])
                self.assertIn("Enter", dialog.address_list.GetString(0))
                with patch.object(dialog, "ask_local_lock_password", return_value=None) as ask:
                    dialog.address_list.SetSelection(0)
                    ask.assert_not_called()
                    dialog.on_activate(Mock())
                    self.assertEqual(dialog.selected_folder_id(), "")
                with patch.object(dialog, "ask_local_lock_password", return_value="wrong-password"), patch("accessible_mail.address_book_dialog.wx.MessageBox"):
                    dialog.on_activate(Mock())
                    self.assertEqual(dialog.visible_entries, [])
                with patch.object(dialog, "ask_local_lock_password", return_value="password-123"):
                    dialog.on_activate(Mock())
                    self.assertEqual(dialog.visible_entries[0].email, "sam@example.com")
                    dialog.on_leave_conversation_folder()
                    self.assertEqual(dialog.visible_entries, [])
                    self.assertFalse(self.store.is_open("a", "folder", folder.id))
            finally:
                dialog.Destroy()
                parent.Destroy()
    def open(self):
        self.store.unlock_target("a", "folder", self.folder.id, "password-123")

    def test_imap_uid_is_mailbox_scoped(self):
        self.lock()
        self.assertIsNone(self.cache.get_content("a", "INBOX", "42"))
        self.assertEqual(self.cache.get_content("a", "Sent", "42").text, "sent body")
        self.assertEqual(self.store.lock_context_for_message("a", "Sent", "42"), (False, None))

    def test_gmail_uid_aliases_are_sealed(self):
        self.account.oauth_provider = "google_gmail_api"
        self.store.configure_account(self.account)
        self.lock()
        self.assertIsNone(self.cache.get_content("a", "Sent", "42"))
        self.assertEqual(self.store.lock_context_for_message("a", "Sent", "42"), (True, None))
        self.open()
        self.assertEqual(self.cache.get_content("a", "Sent", "42").text, "sent body")

    def test_failed_creation_rolls_back_membership_and_encryption(self):
        original = self.cache.transform_locked_rows

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise PermissionError("controlled folder access")

        with patch.object(self.cache, "transform_locked_rows", side_effect=fail):
            with self.assertRaises(PermissionError):
                self.lock()
        self.assertFalse(self.store.is_locked("a", "folder", self.folder.id))
        self.assertEqual(self.store.list_items("a", self.folder.id), [message_folder_key(self.first)])
        self.assertEqual(self.cache.get_content("a", "INBOX", "42").text, "body")

    def test_failed_removal_preserves_lock_and_content(self):
        self.lock()
        self.open()
        original = self.cache.transform_locked_rows

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise PermissionError("disk denied")

        with patch.object(self.cache, "transform_locked_rows", side_effect=fail):
            with self.assertRaises(PermissionError):
                self.store.remove_lock("a", "folder", self.folder.id)
        self.store.close_all_locks()
        self.assertTrue(self.store.is_locked("a", "folder", self.folder.id))
        self.assertIsNone(self.cache.get_content("a", "INBOX", "42"))
        self.open()
        self.assertEqual(self.cache.get_content("a", "INBOX", "42").text, "body")
        self.store.remove_lock("a", "folder", self.folder.id)
        self.assertEqual(self.cache.get_content("a", "INBOX", "42").text, "body")

    def test_membership_changes_preserve_offline_content(self):
        self.lock()
        self.open()
        self.store.add_items("a", self.folder.id, [message_folder_key(self.second)])
        self.assertEqual(self.cache.get_content("a", "Sent", "42").text, "sent body")
        self.store.close_all_locks()
        self.assertIsNone(self.cache.get_content("a", "Sent", "42"))
        self.open()
        self.store.remove_item("a", self.folder.id, message_folder_key(self.second))
        self.store.close_all_locks()
        self.assertEqual(self.cache.get_content("a", "Sent", "42").text, "sent body")

    def test_closed_messages_are_absent_from_search_and_address_matches(self):
        self.lock()
        page = SimpleNamespace(messages=[self.first, self.second], trash_messages=[], allowed_locked_hashes=set())
        frame = SimpleNamespace(_folder_store=self.store, selected_account=lambda: self.account,
                                pages={key: page for key in ("inbox", "sent", "spam", "all")})
        self.assertEqual(MainFrame.searchable_messages(frame), [self.second])
        self.assertEqual(MainFrame.address_message_matches(frame, "friend@example.com"), [])
        # Opening a session alone must not make it accessible outside its folder.
        self.open()
        self.assertEqual(MainFrame.searchable_messages(frame), [self.second])

    def test_router_rejects_closed_message_before_network_access(self):
        self.lock()
        router = SimpleNamespace(cache=self.cache, service_for=lambda _account: self.fail("network reached"))
        with self.assertRaises(ValueError):
            MailServiceRouter.fetch_message(router, self.account, self.first)

    def test_delete_account_removes_organization_and_cache_not_other_accounts(self):
        self.lock()
        self.store.create_section("a", "Work")
        self.store.create_category("a", "Filter", ["attachments"])
        self.store.create_folder("b", FOLDER_MESSAGES, "Other", [])
        self.store.delete_account("a")
        with self.store._connect() as conn:
            for table in ("folders", "local_sections", "local_categories", "local_locks", "local_lock_hashes", "read_events"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE account_id = 'a'").fetchone()[0], 0)
        self.assertEqual(len(self.store.list_folders("b", FOLDER_MESSAGES)), 1)
        self.assertEqual(self.cache.count_summaries("a", "INBOX"), 0)

    def test_both_databases_use_rollback_journals_for_atomic_attach(self):
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            self.assertEqual(conn.execute("PRAGMA message_cache.journal_mode").fetchone()[0], "delete")
            self.assertEqual(conn.execute("PRAGMA message_cache.synchronous").fetchone()[0], 2)

    def test_migration_preserves_locked_membership_and_cached_body(self):
        self.lock()
        self.open()
        self.store.migrate_message_reference("a", "INBOX", "42", "Archive", "87")
        self.assertEqual(self.store.list_items("a", self.folder.id), ['["Archive","87"]'])
        content = self.cache.get_content("a", "Archive", "87")
        self.assertEqual(content.text, "body")
        self.assertEqual(content.summary.mailbox, "Archive")
        self.assertEqual(content.summary.uid, "87")
        self.store.close_all_locks()
        self.assertIsNone(self.cache.get_content("a", "Archive", "87"))
        self.assertFalse(self.store.lock_context_for_message("a", "INBOX", "42")[0])

    def test_imap_copyuid_response_identifies_destination(self):
        from accessible_mail.email_service import EmailService
        connection = SimpleNamespace(response=lambda _name: ("COPYUID", [b"777 42 87"]))
        self.assertEqual(EmailService._copyuid_destination(connection, [b"Moved"], "42"), "87")
        self.assertEqual(EmailService._copyuid_destination(connection, [], "99"), "")

    def test_imap_same_message_with_different_uid_is_protected(self):
        self.first.message_id = "<private@example.com>"
        alias = MessageSummary(uid="99", mailbox="All", message_id=self.first.message_id)
        self.cache.upsert_content(self.account, MessageContent(self.first, "body", []))
        self.cache.upsert_content(self.account, MessageContent(alias, "alias body", []))
        self.lock()
        self.assertIsNone(self.cache.get_content("a", "All", "99"))
        self.assertEqual(self.store.lock_context_for_message("a", "All", "99"), (True, None))
        self.open()
        self.store.add_items("a", self.folder.id, [message_folder_key(alias)])
        self.store.remove_item("a", self.folder.id, message_folder_key(self.first))
        self.store.close_all_locks()
        self.assertIsNone(self.cache.get_content("a", "INBOX", "42"))
        self.assertIsNone(self.cache.get_content("a", "All", "99"))
        self.open()
        self.store.remove_lock("a", "folder", self.folder.id)
        self.assertEqual(self.cache.get_content("a", "All", "99").text, "alias body")

    def test_reused_imap_uid_cannot_replace_protected_content(self):
        self.first.message_id = "<private@example.com>"
        self.cache.upsert_content(self.account, MessageContent(self.first, "body", []))
        self.lock()
        self.open()
        other = MessageSummary(uid="42", mailbox="INBOX", message_id="<other@example.com>")
        self.cache.upsert_content(self.account, MessageContent(other, "wrong body", []))
        self.assertEqual(self.cache.get_content("a", "INBOX", "42").text, "body")
        with self.assertRaises(ValueError):
            self.cache.require_message_access(self.account, other)

    def test_uidvalidity_change_is_rejected_even_without_message_id(self):
        from accessible_mail.email_service import EmailService, MailError
        self.first.uid_validity = "100"
        self.cache.upsert_content(self.account, MessageContent(self.first, "body", []))
        self.lock()
        self.open()
        other = MessageSummary(uid="42", mailbox="INBOX", uid_validity="101")
        self.cache.upsert_content(self.account, MessageContent(other, "wrong body", []))
        self.assertEqual(self.cache.get_content("a", "INBOX", "42").text, "body")
        with self.assertRaises(ValueError):
            self.cache.require_message_access(self.account, other)
        with self.assertRaises(MailError):
            EmailService._validate_uid_validity(SimpleNamespace(_pam_uid_validity="101"), self.first)

    def test_missing_local_summaries_are_refetched_without_deleting_membership(self):
        page = SimpleNamespace(messages=[], _local_backfill_generation=0, allowed_locked_hashes=set())
        page.set_messages = lambda summaries: setattr(page, "messages", summaries)
        calls = []
        service = SimpleNamespace(fetch_summary=lambda _account, mailbox, uid: self.first)
        frame = SimpleNamespace(service=service, selected_account=lambda: self.account,
                                _folder_store=self.store, displayed_account_id="a")
        frame.run_worker = lambda _status, work, done: (calls.append("worker"), done(work()))
        MainFrame.backfill_local_summaries(frame, page, self.account, [("INBOX", "42")], {})
        self.assertEqual(calls, ["worker"])
        self.assertEqual(page.messages, [self.first])
        self.assertEqual(self.store.list_items("a", self.folder.id), [message_folder_key(self.first)])

    def test_unlocked_membership_does_not_cross_account_boundaries(self):
        self.lock()
        self.open()
        self.assertEqual(self.store.message_folder_keys("b"), [])

    def test_failed_membership_edit_preserves_original_content(self):
        self.lock()
        self.open()
        original = self.cache.transform_locked_rows
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise PermissionError("denied")
        with patch.object(self.cache, "transform_locked_rows", side_effect=fail):
            with self.assertRaises(PermissionError):
                self.store.add_items("a", self.folder.id, [message_folder_key(self.second)])
        self.assertEqual(self.store.list_items("a", self.folder.id), [message_folder_key(self.first)])
        self.store.close_all_locks()
        self.assertEqual(self.cache.get_content("a", "Sent", "42").text, "sent body")
