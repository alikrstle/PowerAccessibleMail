from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
