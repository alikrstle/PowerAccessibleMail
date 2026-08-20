from __future__ import annotations

import unittest

from accessible_mail.launch_request import (
    MAX_MAILTO_LENGTH,
    mailto_request_from_arguments,
    parse_mailto_uri,
)


class MailtoRequestTests(unittest.TestCase):
    def test_parses_recipient_subject_and_multiline_body(self) -> None:
        request = parse_mailto_uri(
            "mailto:first%40example.com?"
            "to=second%40example.com&subject=Hello%20world&"
            "body=First%20line%0D%0ASecond%20line"
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(
            request.to_address,
            "first@example.com, second@example.com",
        )
        self.assertEqual(request.subject, "Hello world")
        self.assertEqual(request.body, "First line\nSecond line")

    def test_finds_mailto_argument_among_launcher_arguments(self) -> None:
        request = mailto_request_from_arguments(
            ["--ignored", "mailto:person@example.com?subject=Question"]
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.to_address, "person@example.com")
        self.assertEqual(request.subject, "Question")

    def test_rejects_non_mailto_fragment_and_oversized_requests(self) -> None:
        self.assertIsNone(parse_mailto_uri("https://example.com"))
        self.assertIsNone(parse_mailto_uri("mailto:user@example.com#fragment"))
        self.assertIsNone(parse_mailto_uri("mailto:" + "a" * MAX_MAILTO_LENGTH))

    def test_removes_header_line_breaks_and_nul_characters(self) -> None:
        request = parse_mailto_uri(
            "mailto:user%40example.com%0D%0ABcc%3Ahidden%40example.com?"
            "subject=Hello%0D%0AInjected&body=Safe%00body"
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertNotIn("\r", request.to_address)
        self.assertNotIn("\n", request.to_address)
        self.assertNotIn("\r", request.subject)
        self.assertNotIn("\n", request.subject)
        self.assertEqual(request.body, "Safebody")

    def test_ignores_cc_and_bcc_until_the_compose_window_supports_them(self) -> None:
        request = parse_mailto_uri(
            "mailto:user@example.com?cc=copy@example.com&bcc=hidden@example.com"
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.to_address, "user@example.com")


if __name__ == "__main__":
    unittest.main()
