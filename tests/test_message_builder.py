from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from accessible_mail.message_builder import build_outgoing_message
from accessible_mail.models import Account, MessageSummary


class MessageBuilderTests(unittest.TestCase):
    def test_reply_message_contains_headers_needed_for_threading_and_return_path(self) -> None:
        account = Account(email_address="me@example.com")
        original = MessageSummary(
            uid="1",
            mailbox="INBOX",
            sender_email="friend@example.com",
            message_id="<original@example.com>",
            references="<root@example.com>",
        )

        message = build_outgoing_message(
            account,
            "friend@example.com",
            "Re: hello",
            "reply body",
            original,
        )

        self.assertEqual(message["From"], "me@example.com")
        self.assertEqual(message["Reply-To"], "me@example.com")
        self.assertEqual(message["To"], "friend@example.com")
        self.assertEqual(message["In-Reply-To"], "<original@example.com>")
        self.assertEqual(
            message["References"],
            "<root@example.com> <original@example.com>",
        )

    def test_new_message_contains_reply_to_for_recipient_replies(self) -> None:
        account = Account(email_address="me@example.com")

        message = build_outgoing_message(
            account,
            "friend@example.com",
            "hello",
            "body",
        )

        self.assertEqual(message["Reply-To"], "me@example.com")
        self.assertIsNotNone(message["Message-ID"])

    def test_outgoing_message_contains_selected_attachments(self) -> None:
        account = Account(email_address="me@example.com")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_attachment = root / "notes.txt"
            binary_attachment = root / "archive.bin"
            text_attachment.write_text("attachment text", encoding="utf-8")
            binary_attachment.write_bytes(b"\x00\x01\x02")

            message = build_outgoing_message(
                account,
                "friend@example.com",
                "attachments",
                "body",
                attachments=[text_attachment, binary_attachment],
            )

        attachments = list(message.iter_attachments())
        self.assertEqual(
            [part.get_filename() for part in attachments],
            ["notes.txt", "archive.bin"],
        )
        self.assertEqual(attachments[0].get_content_type(), "text/plain")
        self.assertEqual(attachments[0].get_payload(decode=True), b"attachment text")
        self.assertEqual(
            attachments[1].get_content_type(),
            "application/octet-stream",
        )
        self.assertEqual(attachments[1].get_payload(decode=True), b"\x00\x01\x02")


if __name__ == "__main__":
    unittest.main()
