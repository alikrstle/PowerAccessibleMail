from __future__ import annotations

import unittest
from email.message import EmailMessage

from accessible_mail.email_utils import (
    canonical_url_key,
    clean_message_text_for_display,
    extract_body,
    is_plain_text_placeholder,
    normalize_message_text,
    organize_message_items,
    safe_external_url,
)
from accessible_mail.models import LinkItem


class EmailUtilsTests(unittest.TestCase):
    def test_clean_message_text_removes_css_rules_and_keeps_real_content(self) -> None:
        text = clean_message_text_for_display(
            """
            body { margin: 0; color: #fff; }
            .button { background: red; padding: 10px; }
            النص المهم في الرسالة.
            """
        )

        self.assertEqual(text, "النص المهم في الرسالة.")

    def test_clean_message_text_removes_standalone_style_declarations(self) -> None:
        text = clean_message_text_for_display(
            "font-family: Arial; font-size: 12px; color: #000;\nمحتوى الرسالة"
        )

        self.assertEqual(text, "محتوى الرسالة")

    def test_clean_message_text_ignores_hidden_html_and_programming_noise(self) -> None:
        text = clean_message_text_for_display(
            """
            <html><head><style>body { color: red; }</style></head><body>
            <script>alert('noise')</script>
            <p>الفقرة الأولى.</p>
            <span aria-hidden="true">نص مخفي</span>
            <div style="display: none">محتوى مخفي</div>
            <p>الفقرة الثانية.</p>
            </body></html>
            """
        )

        self.assertEqual(text, "الفقرة الأولى.\nالفقرة الثانية.")
        self.assertNotIn("alert", text)
        self.assertNotIn("مخفي", text)

    def test_clean_message_text_separates_table_cells_rows_and_list_items(self) -> None:
        text = clean_message_text_for_display(
            """
            <table><tr><td>Name</td><td>Ali</td></tr>
            <tr><td>Country</td><td>Iraq</td></tr></table>
            <ul><li>One</li><li>Two</li></ul>
            """
        )

        self.assertEqual(text, "Name Ali\nCountry Iraq\n• One\n• Two")

    def test_clean_message_text_preserves_prose_quotes_and_unicode_words(self) -> None:
        text = clean_message_text_for_display(
            "The chosen color: red is part of the report.\n\n"
            "> quoted first line\n> quoted second line\n\n"
            "مرحبا\u00a0بكم في مش\u00adروعنا"
        )

        self.assertIn("The chosen color: red is part of the report.", text)
        self.assertIn("> quoted first line\n> quoted second line", text)
        self.assertIn("مرحبا بكم في مشروعنا", text)

    def test_extract_body_cleans_css_when_no_html_alternative_exists(self) -> None:
        message = EmailMessage()
        message.set_content(
            "body { margin: 0; color: red; }\n"
            "font-family: Arial; font-size: 12px;\n"
            "Actual readable content."
        )

        text, _resources = extract_body(message)

        self.assertEqual(text, "Actual readable content.")

    def test_only_explicit_safe_external_url_schemes_can_be_opened(self) -> None:
        self.assertEqual(
            safe_external_url("https://example.com/message?id=1"),
            "https://example.com/message?id=1",
        )
        self.assertEqual(
            safe_external_url("mailto:support@example.com"),
            "mailto:support@example.com",
        )
        for unsafe in (
            "javascript:alert(1)",
            "file:///C:/Windows/System32/calc.exe",
            "data:text/html,unsafe",
            "https://",
            "https://example.com/\r\nX-Test: injected",
        ):
            self.assertEqual(safe_external_url(unsafe), "")

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

    def test_url_identity_normalizes_host_default_port_and_tracking_parameters(self) -> None:
        self.assertEqual(
            canonical_url_key("HTTPS://Example.COM:443/path?utm_source=news&id=4"),
            canonical_url_key("https://example.com/path?id=4"),
        )

    def test_duplicate_links_keep_first_position_and_best_explanatory_title(self) -> None:
        items = [
            LinkItem("Click here", "https://EXAMPLE.com:443/account?utm_source=email"),
            LinkItem("Account security settings", "https://example.com/account"),
        ]

        resources = organize_message_items("", items, discover_text_links=False)

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].text, "Account security settings")
        self.assertEqual(resources[0].url, items[0].url)

    def test_html_link_uses_aria_label_or_image_alt_as_its_title(self) -> None:
        message = EmailMessage()
        message.set_content(
            """
            <html><body>
              <a href="https://example.com/settings" aria-label="Account settings">
                <img src="cid:gear" alt="Settings icon">
              </a>
            </body></html>
            """,
            subtype="html",
        )

        _text, resources = extract_body(message)

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0].text, "Account settings")
        self.assertTrue(resources[1].is_image)
        self.assertEqual(resources[1].text, "Settings icon")

    def test_plain_www_link_is_discovered_and_opened_as_https(self) -> None:
        message = EmailMessage()
        message.set_content("Visit our website: www.example.com/help.")

        _text, resources = extract_body(message)

        self.assertEqual(resources[0].url, "https://www.example.com/help")
        self.assertEqual(resources[0].activation_text, "www.example.com/help")

    def test_duplicate_attachments_are_removed_without_merging_distinct_files(self) -> None:
        duplicate = LinkItem(
            "report.pdf",
            kind="attachment",
            filename="report.pdf",
            content_type="application/pdf",
            size=3,
            data="YWJj",
        )
        distinct = LinkItem(
            "report.pdf",
            kind="attachment",
            filename="report.pdf",
            content_type="application/pdf",
            size=3,
            data="eHl6",
        )

        resources = organize_message_items("", [duplicate, duplicate, distinct])

        self.assertEqual(len(resources), 2)
        self.assertTrue(all(item.is_attachment for item in resources))

    def test_resources_are_grouped_in_reading_order_with_attachments_last(self) -> None:
        attachment = LinkItem("file.txt", kind="attachment", filename="file.txt")
        image = LinkItem("Logo", "https://example.com/logo.png", kind="image")
        link = LinkItem("Website", "https://example.com")

        resources = organize_message_items("", [attachment, image, link], discover_text_links=False)

        self.assertEqual([item.kind for item in resources], ["link", "image", "attachment"])

    def test_html_images_are_deduplicated_and_tracking_pixels_are_ignored(self) -> None:
        message = EmailMessage()
        message.set_content(
            """
            <html><body>
              <img src="https://example.com/logo.png" alt="Company logo">
              <img src="https://EXAMPLE.com:443/logo.png?utm_source=email" title="Logo">
              <img src="https://tracker.example.com/pixel.gif" width="1" height="1">
            </body></html>
            """,
            subtype="html",
        )

        _text, resources = extract_body(message)

        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0].is_image)
        self.assertEqual(resources[0].text, "Company logo")

    def test_inline_cid_image_is_merged_with_its_mime_data(self) -> None:
        message = EmailMessage()
        message.set_content(
            '<html><body><img src="cid:logo" alt="Company logo"></body></html>',
            subtype="html",
        )
        message.add_related(
            b"png-data",
            maintype="image",
            subtype="png",
            cid="<logo>",
            disposition="inline",
        )

        _text, resources = extract_body(message)

        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0].is_image)
        self.assertEqual(resources[0].text, "Company logo")
        self.assertEqual(resources[0].attachment_bytes(), b"png-data")

    def test_lazy_and_embedded_html_images_can_be_saved(self) -> None:
        message = EmailMessage()
        message.set_content(
            """
            <html><body>
              <img src="data:image/gif;base64,R0lGODlh" data-src="//example.com/photo.jpg" alt="Photo">
              <img src="data:image/png;base64,cG5nLWRhdGE=" alt="Embedded chart">
            </body></html>
            """,
            subtype="html",
        )

        _text, resources = extract_body(message)

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0].url, "https://example.com/photo.jpg")
        self.assertEqual(resources[1].attachment_bytes(), b"png-data")
        self.assertEqual(resources[1].content_type, "image/png")

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
