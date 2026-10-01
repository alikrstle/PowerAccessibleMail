from __future__ import annotations

import base64
from contextlib import nullcontext
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from accessible_mail.attachment_stream import AttachmentDownloadError
from accessible_mail.email_service import EmailService, MailError
from accessible_mail.imap_parts import (
    ImapPart, bounded_literal_reads, fetch_structure, iter_part_chunks, leaf_parts, read_part_chunk,
)
from accessible_mail.models import Account, LinkItem, MessageSummary


class FakeImap:
    def __init__(self, body=b"hello", attachment=b"attachment", declared_size=None, encoding="base64"):
        self.body = body
        self.attachment = base64.b64encode(attachment) if encoding == "base64" else attachment
        self.size = len(self.attachment) if declared_size is None else declared_size
        self.encoding = encoding
        self.queries = []

    def read(self, size):
        raise AssertionError("Unexpected literal read")

    def uid(self, command, uid, query):
        self.queries.append(query)
        if query == "(UID RFC822.SIZE)":
            return "OK", [b"1 (UID 42 RFC822.SIZE 7000000000)"]
        if query == "(UID BODYSTRUCTURE)":
            return "OK", [(
                f'1 (UID 42 BODYSTRUCTURE (("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "8BIT" {len(self.body)} 1)'
                f'("APPLICATION" "OCTET-STREAM" NIL NIL NIL "{self.encoding.upper()}" {self.size}'
                ' NIL ("ATTACHMENT" ("FILENAME" "file.bin"))) "MIXED"))'
            ).encode()]
        match = re.fullmatch(r"\(UID BODY.PEEK\[([12])\]<(\d+)\.(\d+)>\)", query)
        if not match:
            raise AssertionError(f"Unexpected/unbounded query: {query}")
        part, offset, count = match.groups()
        offset, count = int(offset), int(count)
        data = (self.body if part == "1" else self.attachment)[offset:offset + count]
        metadata = f"1 (UID 42 BODY[{part}]<{offset}> {{{len(data)}}}".encode()
        return "OK", [(metadata, data), b")"]


class ImapPartTests(unittest.TestCase):
    def test_large_message_is_opened_without_fetching_attachment_or_whole_body(self):
        conn = FakeImap(declared_size=5_000_000_000, encoding="binary")
        cache = Mock()
        cache.get_content.return_value = None
        service = EmailService(cache=cache)
        with patch.object(service, "_imap", return_value=nullcontext(conn)), patch.object(service, "_select"):
            content = service.fetch_message(Account(), MessageSummary(uid="42", mailbox="INBOX"), False)
        self.assertEqual(content.text, "hello")
        self.assertEqual(content.links[0].remote_id, "2")
        self.assertEqual(content.links[0].size, 5_000_000_000)
        self.assertEqual(content.links[0].data, "")
        self.assertFalse(any("BODY.PEEK[2]" in query or "BODY.PEEK[]" in query for query in conn.queries))

    def download(self, conn, destination, progress=None):
        service = EmailService(cache=Mock())
        with patch.object(service, "_imap", return_value=nullcontext(conn)), patch.object(service, "_select"):
            return service.download_attachment(Account(), MessageSummary(uid="42", mailbox="INBOX"),
                                               LinkItem(text="file", kind="attachment", remote_source="imap", remote_id="2"),
                                               destination, progress)

    def test_stream_download_encoding_and_final_decoded_progress(self):
        for encoding in ("base64", "binary", "8bit", "quoted-printable"):
            data = b"downloaded attachment" if encoding != "quoted-printable" else b"downloaded=20attachment"
            conn = FakeImap(attachment=data, encoding=encoding)
            with tempfile.TemporaryDirectory() as directory:
                progress = Mock()
                destination = Path(directory) / "file"
                with patch("accessible_mail.imap_parts.DOWNLOAD_CHUNK_BYTES", 5):
                    self.download(conn, destination, progress)
                self.assertEqual(destination.read_bytes(), b"downloaded attachment")
                progress.assert_called_once_with(21, 21)
                self.assertEqual(list(Path(directory).glob("*.part")), [])

    def test_truncated_extra_or_over_limit_download_keeps_existing_file(self):
        for size in (1, 100, None):
            conn = FakeImap(attachment=b"abc", declared_size=size)
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "file"
                destination.write_bytes(b"original")
                with patch("accessible_mail.attachment_stream.MAX_RECEIVED_ATTACHMENT_BYTES", 2), \
                        self.assertRaises(MailError):
                    self.download(conn, destination)
                self.assertEqual(destination.read_bytes(), b"original")
                self.assertEqual(list(Path(directory).glob("*.part")), [])

    def test_64_bit_partial_offsets_are_not_truncated(self):
        offset = 5_000_000_000
        conn = Mock()
        conn.uid.return_value = ("OK", [(f"1 (UID 42 BODY[2]<{offset}> {{1}}".encode(), b"x"), b")"])
        self.assertEqual(read_part_chunk(conn, b"42", "2", offset, 1), b"x")
        conn.uid.assert_called_once_with("fetch", b"42", "(UID BODY.PEEK[2]<5000000000.1>)")

    def test_wrong_uid_part_offset_duplicate_literal_or_overlong_chunk_fails(self):
        metadata = b"1 (UID 42 BODY[2]<0> {3}"
        replies = [[(metadata.replace(b"UID 42", b"UID 43"), b"abc")],
                   [(metadata.replace(b"[2]", b"[3]"), b"abc")],
                   [(metadata.replace(b"<0>", b"<1>"), b"abc")],
                   [(metadata, b"abc"), (metadata, b"abc")], [(metadata, b"ab")],
                   [(metadata, b"abcd")], [b"1 (UID 42 BODY[2] NIL)"], [None]]
        for reply in replies:
            conn = Mock()
            conn.uid.return_value = "OK", reply
            with self.subTest(reply=reply), self.assertRaises(AttachmentDownloadError):
                read_part_chunk(conn, b"42", "2", 0, 3)

    def test_oversized_literal_is_rejected_before_read_and_restores_reader(self):
        conn = Mock()
        original = conn.read
        with self.assertRaises(AttachmentDownloadError):
            with bounded_literal_reads(conn, 100):
                conn.read(101)
        original.assert_not_called()
        self.assertIs(conn.read, original)
        conn.shutdown.assert_called_once()
        self.assertEqual(conn.state, "LOGOUT")

    def test_many_small_literals_cannot_bypass_aggregate_read_budget(self):
        conn = Mock()
        original = conn.read
        with self.assertRaises(AttachmentDownloadError):
            with bounded_literal_reads(conn, 100):
                conn.read(60)
                conn.read(60)
        original.assert_called_once_with(60)

    def test_quoted_empty_eof_is_valid_but_nil_is_not(self):
        conn = Mock()
        conn.uid.return_value = "OK", [b'1 (UID 42 BODY[2]<50> "")']
        self.assertEqual(read_part_chunk(conn, b"42", "2", 50, 1), b"")
        conn.uid.return_value = "OK", [b'1 (UID 42 BODY[2]<50> NIL)']
        with self.assertRaises(AttachmentDownloadError):
            read_part_chunk(conn, b"42", "2", 50, 1)

    def test_unsolicited_other_uid_flags_are_ignored_not_mixed_with_body(self):
        conn = Mock()
        conn.uid.return_value = "OK", [b"1 (UID 43 FLAGS (\\Seen))",
                                      (b"2 (BODY[2]<0> {3}", b"abc"), b" UID 42)"]
        self.assertEqual(read_part_chunk(conn, b"42", "2", 0, 3), b"abc")

    def test_uid_inside_body_cannot_replace_uid_metadata(self):
        conn = Mock()
        for reply in ([b'1 (BODY[2]<0> "UID 42")'],
                      [(b'1 (BODY[2]<0> {3}', b'abc'), b')', b'2 (UID 42 FLAGS ())']):
            conn.uid.return_value = "OK", reply
            with self.assertRaises(AttachmentDownloadError):
                read_part_chunk(conn, b"42", "2", 0, 10)

    def test_nested_parts_numbering_charset_disposition_and_literal_filename(self):
        conn = Mock()
        conn.uid.return_value = "OK", [
            (b'1 (UID 42 BODYSTRUCTURE (("TEXT" "PLAIN" NIL NIL NIL "7BIT" 1 1)'
             b'(("APPLICATION" "PDF" NIL NIL NIL "BASE64" 8 NIL ("ATTACHMENT" ("FILENAME" {8}', b"file.pdf"),
            b'))) "MIXED") "MIXED"))',
        ]
        parts = leaf_parts(fetch_structure(conn, b"42"))
        self.assertEqual([part.number for part in parts], ["1", "2.1"])
        self.assertEqual(parts[1].message.get_filename(), "file.pdf")

    def test_bodystructure_bounds_missing_wrong_uid_and_duplicates(self):
        for reply in (b'1 (UID 43 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 1 1))',
                      b'1 (UID 42 UID 42 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 1 1))',
                      b'1 (UID 42 BODYSTRUCTURE ())', b'1 (UID 42 BODYSTRUCTURE (' + b'(' * 50 + b')' * 51 + b'))'):
            conn = Mock()
            conn.uid.return_value = "OK", [reply]
            with self.subTest(reply=reply), self.assertRaises(AttachmentDownloadError):
                fetch_structure(conn, b"42")

    def test_message_rfc822_attachment_remains_a_whole_part(self):
        structure = [b"MESSAGE", b"RFC822", None, None, None, b"7BIT", 100, [], [], 1,
                     None, [b"ATTACHMENT", [b"FILENAME", b"original.eml"]]]
        parts = leaf_parts(structure)
        self.assertEqual(parts[0].number, "1")
        self.assertEqual(parts[0].message.get_filename(), "original.eml")

    def test_extended_unicode_filename_parameters_are_decoded(self):
        structure = [b"APPLICATION", b"PDF", None, None, None, b"BASE64", 8, None,
                     [b"ATTACHMENT", [b"FILENAME*", b"utf-8''%CE%B1.pdf"]]]
        self.assertEqual(leaf_parts(structure)[0].message.get_filename(), "α.pdf")

    def test_selective_text_respects_utf8_charset(self):
        service = EmailService(cache=Mock())
        conn = FakeImap(body="رسالة تجريبية".encode("utf-8"), declared_size=5_000_000_000, encoding="binary")
        text, _links = service._fetch_selective_content(conn, b"42")
        self.assertEqual(text, "رسالة تجريبية")

    def test_invalid_part_identifier_never_reaches_server(self):
        conn = Mock()
        for number in ("0", "2] BODY[]", "", "1.0", "1." + "1" * 300):
            with self.assertRaises(AttachmentDownloadError):
                read_part_chunk(conn, b"42", number, 0, 3)
        conn.uid.assert_not_called()

    def test_empty_attachment(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "empty"
            self.download(FakeImap(attachment=b""), destination)
            self.assertEqual(destination.stat().st_size, 0)

    def test_huge_text_does_not_trigger_unbounded_viewer_read(self):
        conn = FakeImap(body=b"hello")
        service = EmailService(cache=Mock())
        structure = [b"TEXT", b"PLAIN", None, None, None, b"7BIT", 50_000_000, 1]
        with patch("accessible_mail.email_service.fetch_structure", return_value=structure), self.assertRaises(MailError):
            service._fetch_selective_content(conn, b"42")
        self.assertFalse(conn.queries)

    def test_part_size_underestimate_is_detected_by_eof_probe(self):
        conn = FakeImap(attachment=b"extra", encoding="binary")
        part = ImapPart("2", 2, "binary", Mock())
        with self.assertRaises(AttachmentDownloadError):
            list(iter_part_chunks(conn, b"42", part))


if __name__ == "__main__":
    unittest.main()
