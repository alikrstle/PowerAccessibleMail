from __future__ import annotations

import sqlite3
import hashlib
import hmac
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from accessible_mail.folder_store import (
    FOLDER_CONVERSATIONS,
    FOLDER_MESSAGES,
    FolderStore,
    message_folder_key,
    parse_message_folder_key,
)
from accessible_mail.models import MessageSummary


class FolderStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "folders.db"
        self.store = FolderStore(self.path)

    def use_test_crypto(self) -> None:
        def protect(data: bytes, entropy: bytes | None = None) -> bytes:
            assert entropy is not None
            stream = (hashlib.sha256(entropy + index.to_bytes(4, "big")).digest()
                      for index in range((len(data) + 31) // 32))
            mask = b"".join(stream)
            ciphertext = bytes(a ^ b for a, b in zip(data, mask, strict=False))
            return hmac.new(entropy, ciphertext, hashlib.sha256).digest() + ciphertext

        def unprotect(blob: bytes, entropy: bytes | None = None) -> bytes:
            assert entropy is not None
            ciphertext = blob[32:]
            if not hmac.compare_digest(blob[:32], hmac.new(entropy, ciphertext, hashlib.sha256).digest()):
                raise ValueError("wrong entropy")
            stream = (hashlib.sha256(entropy + index.to_bytes(4, "big")).digest()
                      for index in range((len(ciphertext) + 31) // 32))
            mask = b"".join(stream)
            return bytes(a ^ b for a, b in zip(ciphertext, mask, strict=False))

        self.enterContext(patch("accessible_mail.folder_store.protect_bytes", side_effect=protect))
        self.enterContext(patch("accessible_mail.folder_store.unprotect_bytes", side_effect=unprotect))

    def test_identity_batches_keep_account_scope_and_use_one_connection(self) -> None:
        summaries = [MessageSummary(mailbox="INBOX", uid=str(index), message_id=f"<m-{index}@example.test>")
                     for index in range(1001)]
        self.store.register_message_identities("account-a", summaries)
        self.store.register_message_identities("other-account", [
            MessageSummary(mailbox="Private", uid="other", message_id=summaries[0].message_id),
        ])
        keys = [message_folder_key(summary) for summary in summaries]
        with patch.object(self.store, "_connect", wraps=self.store._connect) as connect:
            hashes = self.store._indexed_hashes("account-a", keys)
            connect.assert_called_once()
        self.assertEqual(len(hashes), 2002)
        with patch.object(self.store, "_connect", wraps=self.store._connect) as connect:
            aliases = self.store.message_alias_pairs("account-a", keys)
            connect.assert_called_once()
        self.assertEqual(aliases, {("INBOX", str(index)) for index in range(1001)})

    def test_identity_batch_parameter_binding_handles_quoted_mailboxes(self) -> None:
        summary = MessageSummary(mailbox="Inbox'); DROP TABLE folders;--", uid="42", message_id="<safe@example.test>")
        self.store.register_message_identities("account-a", [summary])
        keys = [message_folder_key(summary)]
        self.assertEqual(self.store.message_alias_pairs("account-a", keys), {(summary.mailbox, "42")})
        self.assertEqual(len(self.store._indexed_hashes("account-a", keys)), 2)
        self.assertEqual(self.store.list_folders("account-a", FOLDER_MESSAGES), [])

    def test_old_conversation_stars_do_not_change_address_folder_order(self) -> None:
        starred = self.store.create_folder("account-a", FOLDER_CONVERSATIONS, "Z")
        first = self.store.create_folder("account-a", FOLDER_CONVERSATIONS, "A")
        self.store.set_starred("account-a", starred.id, True)
        self.assertEqual([folder.id for folder in self.store.list_folders("account-a", FOLDER_CONVERSATIONS)],
                         [first.id, starred.id])
        self.store.set_pinned("account-a", starred.id, True)
        self.assertEqual(self.store.list_folders("account-a", FOLDER_CONVERSATIONS)[0].id, starred.id)

    def test_create_folder_with_items_and_reopen(self) -> None:
        folder = self.store.create_folder(
            "account-a", FOLDER_MESSAGES, "  رسائل العمل  ", ["msg-1", "msg-2", "msg-1"]
        )
        self.assertEqual(folder.name, "رسائل العمل")
        self.assertEqual(folder.item_count, 2)
        self.assertEqual(self.store.list_items("account-a", folder.id), ["msg-1", "msg-2"])
        reopened = FolderStore(self.path)
        self.assertEqual(reopened.list_folders("account-a", FOLDER_MESSAGES), [folder])
        reopened.add_items("account-a", folder.id, ["msg-3"])
        self.assertEqual(reopened.get_folder("account-a", folder.id).item_count, 3)
        self.assertEqual(reopened.list_folders("account-b", FOLDER_MESSAGES), [])
        self.assertEqual(reopened.list_folders("account-a", FOLDER_CONVERSATIONS), [])

    def test_folder_lock_encrypts_membership_and_requires_password(self) -> None:
        self.use_test_crypto()
        key = '["INBOX","secret-42"]'
        folder = self.store.create_folder("account-a", FOLDER_MESSAGES, "خاص", [key])
        self.store.lock_target("account-a", "folder", folder.id, "passphrase-123")
        self.assertEqual(self.store.lock_context_for_message("account-a", "INBOX", "secret-42"), (True, None))
        self.assertTrue(self.store.get_folder("account-a", folder.id).locked)
        self.assertEqual(self.store.message_folder_keys("account-a"), [])
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM folder_items").fetchone()[0], 0)
            self.assertNotIn(b"secret-42", bytes(conn.execute("SELECT payload FROM local_locks").fetchone()[0]))
        reopened = FolderStore(self.path)
        with self.assertRaises(ValueError):
            reopened.list_items("account-a", folder.id)
        with self.assertRaises(ValueError):
            reopened.unlock_target("account-a", "folder", folder.id, "incorrect-password")
        reopened.unlock_target("account-a", "folder", folder.id, "passphrase-123")
        locked, entropy = reopened.lock_context_for_message("account-a", "INBOX", "secret-42")
        self.assertTrue(locked)
        self.assertIsInstance(entropy, bytes)
        self.assertEqual(reopened.list_items("account-a", folder.id), [key])
        with self.assertRaises(ValueError):
            reopened.remove_lock("account-b", "folder", folder.id)
        reopened.add_items("account-a", folder.id, ['["INBOX","43"]'])
        reopened.close_target("folder", folder.id)
        after_close = FolderStore(self.path)
        after_close.unlock_target("account-a", "folder", folder.id, "passphrase-123")
        self.assertEqual(len(after_close.list_items("account-a", folder.id)), 2)
        after_close.remove_lock("account-a", "folder", folder.id)
        self.assertFalse(after_close.get_folder("account-a", folder.id).locked)
        self.assertEqual(len(after_close.list_items("account-a", folder.id)), 2)

    def test_section_lock_encrypts_direct_and_nested_folder_membership(self) -> None:
        self.use_test_crypto()
        section = self.store.create_section("account-a", "خاص")
        folder = self.store.create_folder(
            "account-a", FOLDER_MESSAGES, "عمل", ['["INBOX","f1"]'], section_id=section.id,
        )
        self.store.move_items_to_section("account-a", section.id, ['["INBOX","s1"]'])
        self.store.lock_target("account-a", "section", section.id, "passphrase-123")
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM section_items").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM folder_items").fetchone()[0], 0)
        reopened = FolderStore(self.path)
        self.assertTrue(reopened.list_sections("account-a")[0].locked)
        with self.assertRaises(ValueError):
            reopened.list_items("account-a", folder.id)
        reopened.unlock_target("account-a", "section", section.id, "passphrase-123")
        self.assertEqual(reopened.list_items("account-a", folder.id), ['["INBOX","f1"]'])
        self.assertEqual(reopened.section_message_keys("account-a", section.id), ['["INBOX","s1"]'])
        reopened.close_target("section", section.id)
        with self.assertRaises(ValueError):
            reopened.list_items("account-a", folder.id)
        reopened.unlock_target("account-a", "section", section.id, "passphrase-123")
        reopened.remove_lock("account-a", "section", section.id)
        self.assertEqual(reopened.list_items("account-a", folder.id), ['["INBOX","f1"]'])

    def test_lock_crypto_failure_preserves_original_items(self) -> None:
        folder = self.store.create_folder("account-a", FOLDER_MESSAGES, "خاص", ['["INBOX","42"]'])
        with patch("accessible_mail.folder_store.protect_bytes", side_effect=PermissionError("access denied")):
            with self.assertRaises(PermissionError):
                self.store.lock_target("account-a", "folder", folder.id, "passphrase-123")
        self.assertFalse(self.store.is_locked("account-a", "folder", folder.id))
        self.assertEqual(self.store.list_items("account-a", folder.id), ['["INBOX","42"]'])

    def test_protected_section_write_failure_rolls_back_new_folder(self) -> None:
        self.use_test_crypto()
        section = self.store.create_section("account-a", "خاص")
        self.store.lock_target("account-a", "section", section.id, "passphrase-123")
        self.store.unlock_target("account-a", "section", section.id, "passphrase-123")
        with patch("accessible_mail.folder_store.protect_bytes", side_effect=PermissionError("access denied")):
            with self.assertRaises(PermissionError):
                self.store.create_folder(
                    "account-a", FOLDER_MESSAGES, "لن يحفظ", ["message"], section_id=section.id,
                )
        self.assertEqual(self.store.list_folders("account-a", FOLDER_MESSAGES, section_id=section.id), [])

    def test_message_cannot_leave_locked_section_without_removing_lock(self) -> None:
        self.use_test_crypto()
        first = self.store.create_section("account-a", "الأول")
        second = self.store.create_section("account-a", "الثاني")
        self.store.move_items_to_section("account-a", first.id, ["message-1"])
        self.store.lock_target("account-a", "section", first.id, "passphrase-123")
        self.store.unlock_target("account-a", "section", first.id, "passphrase-123")
        with self.assertRaises(ValueError):
            self.store.move_items_to_section("account-a", second.id, ["message-1"])
        self.assertEqual(self.store.section_message_keys("account-a", first.id), ["message-1"])
        self.assertEqual(self.store.section_message_keys("account-a", second.id), [])

    def test_folder_flags_and_archiving_preserve_items(self) -> None:
        folder = self.store.create_folder("account-a", FOLDER_MESSAGES, "متابعة", ["msg-1"])
        self.store.set_starred("account-a", folder.id, True)
        self.store.set_pinned("account-a", folder.id, True)
        self.store.set_archived("account-a", folder.id, True)
        self.assertEqual(self.store.list_folders("account-a", FOLDER_MESSAGES), [])
        archived = self.store.list_folders("account-a", FOLDER_MESSAGES, archived=True)
        self.assertTrue(archived[0].starred)
        self.assertTrue(archived[0].pinned)
        self.assertEqual(self.store.list_items("account-a", folder.id), ["msg-1"])

    def test_conversation_membership_moves_between_folders_and_includes_archived(self) -> None:
        first = self.store.create_folder(
            "account-a", FOLDER_CONVERSATIONS, "الأول", ["sam@example.com"],
        )
        second = self.store.create_folder("account-a", FOLDER_CONVERSATIONS, "الثاني")
        self.store.set_archived("account-a", first.id, True)
        self.assertEqual(self.store.conversation_item_keys("account-a"), {"sam@example.com"})
        self.store.add_items("account-a", second.id, ["sam@example.com"])
        self.assertEqual(self.store.list_items("account-a", first.id), [])
        self.assertEqual(self.store.list_items("account-a", second.id), ["sam@example.com"])
        third = self.store.create_folder(
            "account-a", FOLDER_CONVERSATIONS, "الثالث", ["sam@example.com"],
        )
        self.assertEqual(self.store.list_items("account-a", second.id), [])
        self.assertEqual(self.store.list_items("account-a", third.id), ["sam@example.com"])
        self.store.delete_folder("account-a", third.id)
        self.assertEqual(self.store.conversation_item_keys("account-a"), set())

    def test_rename_and_delete_do_not_touch_message_cache(self) -> None:
        folder = self.store.create_folder("account-a", FOLDER_MESSAGES, "قديم", ["msg-1"])
        self.store.rename_folder("account-a", folder.id, "جديد")
        self.assertEqual(self.store.get_folder("account-a", folder.id).name, "جديد")
        self.store.delete_folder("account-a", folder.id)
        self.assertEqual(self.store.list_folders("account-a", FOLDER_MESSAGES), [])
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM folder_items").fetchone()[0], 0)
        self.assertFalse(self.path.with_name("messages.db").exists())

    def test_account_scope_and_duplicate_names(self) -> None:
        folder = self.store.create_folder("account-a", FOLDER_CONVERSATIONS, "الأصدقاء")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_folder("account-a", FOLDER_CONVERSATIONS, "الأصدقاء")
        self.store.create_folder("account-b", FOLDER_CONVERSATIONS, "الأصدقاء")
        with self.assertRaises(ValueError):
            self.store.add_items("account-b", folder.id, ["sam@example.com"])
        with self.assertRaises(ValueError):
            self.store.delete_folder("account-b", folder.id)
        self.assertEqual(self.store.get_folder("account-a", folder.id), folder)

    def test_invalid_name_and_kind(self) -> None:
        for name in ("bad\nname", "x" * 101):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.create_folder("account-a", FOLDER_MESSAGES, name)
        with self.assertRaises(ValueError):
            self.store.create_folder("account-a", "unknown", "اختبار")

    def test_blank_name_uses_today_and_avoids_duplicates(self) -> None:
        first = self.store.create_folder("account-a", FOLDER_MESSAGES, "")
        second = self.store.create_folder("account-a", FOLDER_MESSAGES, "  ")
        self.assertTrue(first.name.startswith("مجلد جديد "))
        self.assertEqual(second.name, first.name + " (2)")

    def test_message_reference_preserves_mailbox_and_uid(self) -> None:
        summary = MessageSummary(uid="42", mailbox="العمل/رسائل")
        key = message_folder_key(summary)
        self.assertEqual(parse_message_folder_key(key), ("العمل/رسائل", "42"))
        self.assertIsNone(parse_message_folder_key("not-json"))
        self.assertIsNone(parse_message_folder_key('["INBOX"]'))

    def test_direct_category_items_are_local_and_account_scoped(self) -> None:
        category = self.store.create_category("account-a", "العمل")
        key = '["INBOX","42"]'
        self.store.add_category_items("account-a", category.id, [key, key])
        self.assertEqual(self.store.direct_category_message_keys("account-a", category.id), [key])
        self.assertEqual(self.store.category_message_keys("account-a", category.id), [key])
        self.assertEqual(self.store.category_message_keys("account-b"), [])
        with self.assertRaises(ValueError):
            self.store.add_category_items("account-b", category.id, [key])
        self.store.delete_category("account-a", category.id)
        self.assertEqual(self.store.category_message_keys("account-a"), [])

    def test_custom_sections_move_messages_and_folders_locally(self) -> None:
        first = self.store.create_section("account-a", "العمل")
        second = self.store.create_section("account-a", "العائلة")
        folder = self.store.create_folder("account-a", FOLDER_MESSAGES, "مراجعة", section_id=first.id)
        key = '["INBOX","42"]'
        self.store.move_items_to_section("account-a", first.id, [key])
        self.assertEqual(self.store.section_message_keys("account-a", first.id), [key])
        self.assertEqual(self.store.section_message_keys("account-b"), [])
        self.assertEqual(self.store.list_folders("account-a", FOLDER_MESSAGES, section_id=""), [])
        self.assertEqual(self.store.list_folders("account-a", FOLDER_MESSAGES, section_id=first.id), [folder])
        self.store.move_items_to_section("account-a", second.id, [key])
        self.assertEqual(self.store.section_message_keys("account-a", first.id), [])
        self.assertEqual(self.store.section_message_keys("account-a", second.id), [key])
        self.store.set_folder_section("account-a", folder.id, second.id)
        self.store.rename_section("account-a", second.id, "البيت")
        self.assertEqual(self.store.list_sections("account-a")[0].name, "البيت")
        with self.assertRaises(ValueError):
            self.store.move_items_to_section("account-b", second.id, [key])
        self.store.delete_section("account-a", second.id)
        self.assertEqual(self.store.section_message_keys("account-a"), [])
        self.assertIsNone(self.store.get_folder("account-a", folder.id).section_id)
        self.assertEqual([item.id for item in self.store.list_folders("account-a", FOLDER_MESSAGES, section_id="")], [folder.id])

    def test_all_folder_messages_are_hidden_from_section_lists_locally(self) -> None:
        key = '["INBOX","42"]'
        first = self.store.create_folder("account-a", FOLDER_MESSAGES, "عمل", [key], section_key="inbox")
        self.store.create_folder("account-a", FOLDER_CONVERSATIONS, "أصدقاء", ["sam@example.com"])
        self.assertEqual(self.store.message_folder_keys("account-a"), [key])
        self.assertEqual(self.store.message_folder_keys("account-b"), [])
        self.store.set_archived("account-a", first.id, True)
        self.assertEqual(self.store.message_folder_keys("account-a"), [key])
        self.assertEqual([folder.id for folder in self.store.list_section_folders("account-a", "all")], [first.id])
        self.store.remove_item("account-a", first.id, key)
        self.assertEqual(self.store.message_folder_keys("account-a"), [])

    def test_local_category_move_is_scoped_and_reversible(self) -> None:
        folder = self.store.create_folder("account-a", FOLDER_MESSAGES, "عمل", ['["INBOX","42"]'])
        category = self.store.create_category("account-a", "العمل")
        self.store.set_folder_category("account-a", folder.id, category.id)
        self.assertEqual(self.store.category_message_keys("account-a"), ['["INBOX","42"]'])
        self.assertEqual(self.store.category_message_keys("account-b"), [])
        self.assertEqual(self.store.category_message_keys("account-a", category.id), ['["INBOX","42"]'])
        with self.assertRaises(ValueError):
            self.store.set_folder_category("account-b", folder.id, category.id)
        self.store.delete_category("account-a", category.id)
        self.assertEqual(self.store.category_message_keys("account-a"), [])
        self.assertIsNone(self.store.get_folder("account-a", folder.id).category_id)
        self.assertEqual(self.store.list_items("account-a", folder.id), ['["INBOX","42"]'])

    def test_category_names_unique_per_account(self) -> None:
        self.store.create_category("account-a", "العمل")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_category("account-a", "العمل")
        self.assertEqual(len(self.store.list_categories("account-a")), 1)
        self.assertEqual(self.store.list_categories("account-b"), [])

    def test_custom_category_rules_are_saved_and_validated(self) -> None:
        category = self.store.create_category("account-a", "مهم", ("specific_email",), ("user@example.com",))
        self.assertEqual(self.store.list_categories("account-a"), [category])
        self.assertEqual(category.email_addresses, ("user@example.com",))
        self.store.set_category_rules("account-a", category.id, ("attachments",))
        self.assertEqual(self.store.list_categories("account-a")[0].rules, ("attachments",))
        with self.assertRaises(ValueError):
            self.store.set_category_rules("account-a", category.id, ("attachments", "no_attachments"))
        with self.assertRaises(ValueError):
            self.store.set_category_rules("account-a", category.id, ("specific_email",))
        with self.assertRaises(ValueError):
            self.store.create_category("account-a", "خطأ", ("unknown",))

    def test_recent_read_events_are_scoped_to_account(self) -> None:
        self.store.record_read_event("account-a", "message-1", True)
        self.assertEqual(self.store.recent_read_keys("account-a", since=0), ["message-1"])
        self.assertEqual(self.store.recent_read_keys("account-b", since=0), [])
        self.store.record_read_event("account-a", "message-1", False)
        self.assertEqual(self.store.recent_read_keys("account-a", since=0), [])

    def test_folder_appears_in_its_section_then_in_local_category(self) -> None:
        category = self.store.create_category("account-a", "العمل")
        folder = self.store.create_folder(
            "account-a", FOLDER_MESSAGES, "متابعة", ["message-1"], section_key="inbox",
        )
        self.assertEqual(self.store.list_section_folders("account-a", "inbox"), [folder])
        self.assertEqual(self.store.list_section_folders("account-a", "sent"), [])
        self.assertEqual(self.store.list_section_folders("account-b", "inbox"), [])
        self.store.set_folder_category("account-a", folder.id, category.id)
        self.assertEqual(self.store.list_section_folders("account-a", "inbox"), [])
        self.assertEqual(
            [item.id for item in self.store.list_section_folders("account-a", "custom", category_id=category.id)],
            [folder.id],
        )
        self.store.set_folder_category("account-a", folder.id, None)
        self.assertEqual([item.id for item in self.store.list_section_folders("account-a", "inbox")], [folder.id])

    def test_custom_section_folder_requires_owned_category(self) -> None:
        category = self.store.create_category("account-a", "العمل")
        with self.assertRaises(ValueError):
            self.store.create_folder("account-b", FOLDER_MESSAGES, "خطأ", section_key="custom", category_id=category.id)
        folder = self.store.create_folder(
            "account-a", FOLDER_MESSAGES, "رسائل العمل", section_key="custom", category_id=category.id,
        )
        self.assertEqual(self.store.list_section_folders("account-a", "custom", category_id=category.id), [folder])
        self.store.delete_category("account-a", category.id)
        self.assertEqual([item.id for item in self.store.list_section_folders("account-a", "all")], [folder.id])


if __name__ == "__main__":
    unittest.main()
