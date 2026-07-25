from __future__ import annotations

import unittest
from email.message import EmailMessage

from accessible_mail.email_utils import extract_body, is_plain_text_placeholder, normalize_message_text


class EmailUtilsTests(unittest.TestCase):
    def test_arabic_empty_body_message_is_treated_as_a_refetchable_placeholder(self) -> None:
        self.assertTrue(is_plain_text_placeholder("لا يوجد نص قابل للعرض داخل هذه الرسالة."))

    def test_normalize_message_text_removes_empty_lines_and_unwraps_paragraphs(self) -> None:
        text = normalize_message_text(
            "مرحبا\n\n\nهذا سطر أول\n   وهذا استمرار لنفس الفقرة\n\n\n- عنصر أول\n\n- عنصر ثاني\n"
        )

        self.assertEqual(
            text,
            "مرحبا\nهذا سطر أول وهذا استمرار لنفس الفقرة\n- عنصر أول\n- عنصر ثاني",
        )

    def test_extract_body_includes_links_and_attachments(self) -> None:
        message = EmailMessage()
        message["From"] = "sender@example.com"
        message["To"] = "user@example.com"
        message["Subject"] = "with attachment"
        message.set_content("افتح الرابط https://example.com")
        message.add_attachment(
            b"hello attachment",
            maintype="text",
            subtype="plain",
            filename="note.txt",
        )

        text, resources = extract_body(message)

        self.assertIn("https://example.com", text)
        self.assertEqual(len(resources), 2)
        self.assertFalse(resources[0].is_attachment)
        self.assertTrue(resources[1].is_attachment)
        self.assertEqual(resources[1].filename, "note.txt")
        self.assertEqual(resources[1].attachment_bytes(), b"hello attachment")

    def test_plain_url_title_uses_message_context(self) -> None:
        message = EmailMessage()
        message["From"] = "sender@example.com"
        message["To"] = "user@example.com"
        message["Subject"] = "link context"
        message.set_content("صفحة متابعة الطلب https://example.com/status\n")

        _text, resources = extract_body(message)

        self.assertEqual(resources[0].text, "صفحة متابعة الطلب")
        self.assertEqual(resources[0].url, "https://example.com/status")

    def test_extract_body_lists_html_buttons_and_contextual_link_titles(self) -> None:
        message = EmailMessage()
        message["From"] = "sender@example.com"
        message["To"] = "user@example.com"
        message["Subject"] = "buttons"
        message.set_content(
            """
            <html>
              <body>
                <p>للدخول إلى لوحة التحكم</p>
                <a href="https://example.com/dashboard">اضغط هنا</a>
                <button formaction="https://example.com/confirm">تأكيد الحضور</button>
                <form action="https://example.com/send">
                  <input type="submit" value="إرسال الطلب">
                </form>
              </body>
            </html>
            """,
            subtype="html",
        )

        text, resources = extract_body(message)

        self.assertNotIn("PAM-ACTION", text)
        self.assertEqual(resources[0].text, "للدخول إلى لوحة التحكم")
        self.assertEqual(resources[0].url, "https://example.com/dashboard")
        self.assertEqual(resources[0].activation_text, "اضغط هنا")
        self.assertEqual(text[resources[0].activation_start : resources[0].activation_end], "اضغط هنا")
        self.assertEqual(resources[1].kind, "button")
        self.assertEqual(resources[1].text, "تأكيد الحضور")
        self.assertEqual(resources[1].url, "https://example.com/confirm")
        self.assertEqual(resources[1].activation_text, "تأكيد الحضور")
        self.assertEqual(text[resources[1].activation_start : resources[1].activation_end], "تأكيد الحضور")
        self.assertEqual(resources[2].kind, "button")
        self.assertEqual(resources[2].text, "إرسال الطلب")
        self.assertEqual(resources[2].url, "https://example.com/send")
        self.assertEqual(resources[2].activation_text, "إرسال الطلب")
        self.assertEqual(text[resources[2].activation_start : resources[2].activation_end], "إرسال الطلب")

    def test_extract_body_ignores_html_visual_styles(self) -> None:
        message = EmailMessage()
        message["From"] = "sender@example.com"
        message["To"] = "user@example.com"
        message["Subject"] = "html"
        message.set_content(
            """
            <html>
              <head>
                <style>
                  body { margin: 0 auto; padding: 0; -webkit-text-size-adjust: 100% !important; }
                  img { border: 0 !important; outline: none !important; }
                </style>
              </head>
              <body>
                <p>هذا هو محتوى الرسالة الأصلي.</p>
                <a href="https://example.com/read">افتح التفاصيل</a>
              </body>
            </html>
            """,
            subtype="html",
        )

        text, resources = extract_body(message)

        self.assertIn("هذا هو محتوى الرسالة الأصلي.", text)
        self.assertNotIn("margin: 0 auto", text)
        self.assertNotIn("-webkit-text-size-adjust", text)
        self.assertEqual(resources[0].url, "https://example.com/read")

    def test_extract_body_prefers_clean_html_over_css_plain_dump(self) -> None:
        message = EmailMessage()
        message["From"] = "sender@example.com"
        message["To"] = "user@example.com"
        message["Subject"] = "alternative"
        message.set_content(
            """
            body { margin: 0 auto; padding: 0; -webkit-text-size-adjust: 100% !important; }
            img { border: 0 !important; outline: none !important; }
            p { Margin: 0px !important; Padding: 0px !important; }
            """
        )
        message.add_alternative(
            """
            <html>
              <head><style>body { margin: 0; }</style></head>
              <body><p>النص المهم في الرسالة.</p></body>
            </html>
            """,
            subtype="html",
        )

        text, _resources = extract_body(message)

        self.assertIn("النص المهم في الرسالة.", text)
        self.assertNotIn("-webkit-text-size-adjust", text)

    def test_extract_body_prefers_html_over_plain_text_placeholder(self) -> None:
        message = EmailMessage()
        message.set_content("Plain text version not available")
        message.add_alternative(
            "<html><body><p>هذا هو محتوى الرسالة الحقيقي.</p></body></html>",
            subtype="html",
        )

        text, _resources = extract_body(message)

        self.assertTrue(is_plain_text_placeholder("Plain text version not available"))
        self.assertIn("هذا هو محتوى الرسالة الحقيقي.", text)
        self.assertNotIn("Plain text version not available", text)

    def test_extract_body_ignores_arabic_html_client_warning(self) -> None:
        warning = (
            "لسوء الحظ، لا يستطيع برنامج البريد الإلكتروني الخاص بك عرض HTML، "
            "أو تم إيقاف إعداداتك. لعرض هذه الرسالة الإلكترونية، يرجى النقر "
            "على الرابط أعلاه، أو نسخها ولصقها في متصفحك."
        )
        message = EmailMessage()
        message.set_content(warning)
        message.add_alternative(
            "<html><body><p>هذا هو محتوى الرسالة الفعلي.</p></body></html>",
            subtype="html",
        )

        text, _resources = extract_body(message)

        self.assertTrue(is_plain_text_placeholder(warning))
        self.assertEqual(text, "هذا هو محتوى الرسالة الفعلي.")

    def test_extract_body_removes_english_html_client_warning_embedded_in_html(self) -> None:
        warning = (
            "Email client cannot display HTML, or your settings are turned off. "
            "To view this email, please click the link above, or copy and paste it into your browser."
        )
        message = EmailMessage()
        message.set_content("Plain text version not available")
        message.add_alternative(
            f"<html><body><p>Actual message content.</p><div>{warning}</div></body></html>",
            subtype="html",
        )

        text, _resources = extract_body(message)

        self.assertEqual(text, "Actual message content.")
        self.assertNotIn("cannot display HTML", text)

    def test_extract_body_removes_warning_without_discarding_adjacent_content(self) -> None:
        warning = (
            "Email client cannot display HTML, or your settings are turned off. "
            "To view this email, please click the link above, or copy and paste it into your browser."
        )
        message = EmailMessage()
        message.set_content(f"Important message text. {warning}")

        text, _resources = extract_body(message)

        self.assertEqual(text, "Important message text.")


if __name__ == "__main__":
    unittest.main()
