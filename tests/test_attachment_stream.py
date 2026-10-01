from __future__ import annotations

import base64
import io
import json
import quopri
import tracemalloc
import unittest
from unittest.mock import Mock, patch

from accessible_mail.attachment_stream import (
    AttachmentDownloadError, AttachmentSink, MAX_RECEIVED_ATTACHMENT_BYTES,
    TransferDecoder, check_attachment_size, stream_gmail_attachment, write_embedded_attachment,
)


class SmallReads(io.BytesIO):
    def __init__(self, data, step=3):
        super().__init__(data)
        self.step = step
        self.read_sizes = []

    def read(self, count=-1):
        self.read_sizes.append(count)
        if count < 0:
            raise AssertionError("Unbounded HTTP read")
        return super().read(min(count, self.step))


class AttachmentStreamTests(unittest.TestCase):
    def test_five_decimal_gigabyte_limit_and_64_bit_counters(self):
        self.assertEqual(MAX_RECEIVED_ATTACHMENT_BYTES, 5_000_000_000)
        check_attachment_size(5_000_000_000)
        with self.assertRaises(AttachmentDownloadError):
            check_attachment_size(5_000_000_001)
        output = Mock()
        output.write.side_effect = len
        sink = AttachmentSink(output)
        sink.received = MAX_RECEIVED_ATTACHMENT_BYTES - 1
        sink.write(b"x")
        self.assertEqual(sink.received, MAX_RECEIVED_ATTACHMENT_BYTES)
        with self.assertRaises(AttachmentDownloadError):
            sink.write(b"x")
        output.write.assert_called_once_with(b"x")

    def test_base64_all_chunk_boundaries(self):
        original = bytes(range(256)) + b"last"
        encoded = base64.encodebytes(original)
        for step in (1, 2, 3, 4, 5, 77, 65536):
            with self.subTest(step=step):
                output = io.BytesIO()
                sink = AttachmentSink(output)
                decoder = TransferDecoder(sink, "base64")
                for offset in range(0, len(encoded), step):
                    decoder.feed(encoded[offset:offset + step])
                    self.assertLessEqual(len(decoder.carry), 3)
                decoder.finish()
                sink.finish(len(original))
                self.assertEqual(output.getvalue(), original)

    def test_quoted_printable_all_boundaries_and_no_newline_bounded_carry(self):
        original = bytes(range(256)) * 3
        encoded = quopri.encodestring(original) + b"=\r\n"
        for step in (1, 2, 3, 5, 17):
            output = io.BytesIO()
            decoder = TransferDecoder(AttachmentSink(output), "quoted-printable")
            for offset in range(0, len(encoded), step):
                decoder.feed(encoded[offset:offset + step])
                self.assertLessEqual(len(decoder.carry), 2)
            decoder.finish()
            self.assertEqual(output.getvalue(), original)
        decoder = TransferDecoder(AttachmentSink(io.BytesIO()), "quoted-printable")
        for _ in range(20):
            decoder.feed(b"x" * 65536)
            self.assertFalse(decoder.carry)

    def test_corrupt_base64_padding_and_unknown_encoding_fail(self):
        for encoded in (b"x", b"a!bc", b"YQ==YQ==", b"YQ==x", b"YQ=xx"):
            with self.subTest(encoded=encoded), self.assertRaises(AttachmentDownloadError):
                decoder = TransferDecoder(AttachmentSink(io.BytesIO()), "base64")
                for byte in encoded:
                    decoder.feed(bytes([byte]))
                decoder.finish()
        with self.assertRaises(AttachmentDownloadError):
            TransferDecoder(AttachmentSink(io.BytesIO()), "unknown")

    def test_embedded_data_uses_decoder_not_full_attachment_bytes(self):
        output = io.BytesIO()
        progress = Mock()
        write_embedded_attachment(base64.b64encode(b"hello").decode(), output, progress)
        self.assertEqual(output.getvalue(), b"hello")
        progress.assert_called_once_with(5, 5)

    def test_gmail_urlsafe_unpadded_and_both_key_orders(self):
        original = bytes(range(256))
        data = base64.urlsafe_b64encode(original).decode().rstrip("=")
        for payload in ({"data": data, "size": 256}, {"size": 256, "attachmentId": "id", "data": data}):
            for step in (1, 2, 3, 7, 64 * 1024):
                output = io.BytesIO()
                response = SmallReads(json.dumps(payload).encode(), step)
                progress = Mock()
                stream_gmail_attachment(response, output, 256, progress)
                self.assertEqual(output.getvalue(), original)
                progress.assert_called_once_with(256, 256)
                self.assertTrue(all(0 < size <= 64 * 1024 for size in response.read_sizes))

    def test_gmail_json_escape_at_chunk_boundary(self):
        output = io.BytesIO()
        stream_gmail_attachment(SmallReads(br'{"size":3,"data":"Y\u0057Jj"}', 1), output)
        self.assertEqual(output.getvalue(), b"abc")

    def test_invalid_or_truncated_json_and_size_mismatch_fail(self):
        invalid = [b"", b"{}", b'{"data":"YQ=="}', b'{"size":1}',
                   b'{"size":1,"data":"YQ=="', b'{"size":1,"data":"YQ=="}x',
                   b'{"size":1,"data":"YQ==","data":"Yg=="}',
                   b'{"size":1,"data":"YQ==","size":1}', b'{"size":2,"data":"YQ=="}',
                   b'{"size":-1,"data":"YQ=="}', b'{"size":01,"data":"YQ=="}',
                   b'{"size":1e0,"data":"YQ=="}', b'{"size":true,"data":"YQ=="}',
                   b'{"size":1,"data":"Y Q=="}', b'{"size":1,"data":"YQ==",}',
                   b'{"size":1,"data":"YQ==","extra":{}}', b'{"size":1,"data":"YQ\\"}']
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(AttachmentDownloadError):
                stream_gmail_attachment(SmallReads(data, 1), io.BytesIO())
        with self.assertRaises(AttachmentDownloadError):
            stream_gmail_attachment(SmallReads(b'{"size":1,"data":"YQ=="}'), io.BytesIO(), 2)

    def test_data_first_cannot_bypass_limit_by_false_size(self):
        with patch("accessible_mail.attachment_stream.MAX_RECEIVED_ATTACHMENT_BYTES", 2):
            with self.assertRaises(AttachmentDownloadError):
                stream_gmail_attachment(SmallReads(b'{"data":"YWJj","size":1}'), io.BytesIO())
            with self.assertRaises(AttachmentDownloadError):
                stream_gmail_attachment(SmallReads(b'{"size":3,"data":"YWJj"}'), io.BytesIO())

    def test_empty_attachment_is_valid(self):
        output = io.BytesIO()
        stream_gmail_attachment(SmallReads(b'{"size":0,"data":""}'), output)
        self.assertEqual(output.getvalue(), b"")

    def test_disk_full_or_short_write_raises_clear_error(self):
        for writer in (Mock(side_effect=OSError("disk full")), Mock(return_value=0)):
            output = Mock(write=writer)
            with self.assertRaisesRegex(AttachmentDownloadError, "المساحة"):
                AttachmentSink(output).write(b"data")

    def test_gmail_wire_budget_and_metadata_token_budget(self):
        for payload in (b'{"attachmentId":"' + b"x" * 65537 + b'","size":0,"data":""}',
                        b'{"size":' + b"9" * 100 + b',"data":""}'):
            with self.assertRaises(AttachmentDownloadError):
                stream_gmail_attachment(SmallReads(payload, 65536), io.BytesIO())
        with patch("accessible_mail.attachment_stream.MAX_RECEIVED_ATTACHMENT_BYTES", 1), \
                self.assertRaises(AttachmentDownloadError):
            stream_gmail_attachment(SmallReads(b" " * (128 * 1024 + 5), 65536), io.BytesIO())

    def test_64_mb_gmail_stream_has_bounded_memory_without_storing_payload(self):
        class GeneratedResponse:
            def __init__(self):
                self.prefix = b'{"size":67108863,"data":"'
                self.remaining = 4 * (67_108_863 // 3)
                self.suffix = b'"}'

            def read(self, count):
                self.assert_count(count)
                if self.prefix:
                    value, self.prefix = self.prefix, b""
                    return value
                if self.remaining:
                    size = min(self.remaining, count)
                    self.remaining -= size
                    return b"YWFh" * (size // 4)
                value, self.suffix = self.suffix, b""
                return value

            @staticmethod
            def assert_count(count):
                if not 0 < count <= 65536:
                    raise AssertionError("Unbounded stream read")

        # Mock call history itself would retain every decoded chunk, unlike a
        # file, so use a counting sink without history for the memory benchmark.
        class CountingOutput:
            count = 0

            def write(self, block):
                self.count += len(block)
                return len(block)

        output = CountingOutput()
        tracemalloc.start()
        try:
            stream_gmail_attachment(GeneratedResponse(), output)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(output.count, 67_108_863)
        self.assertLess(peak, 2 * 1024 * 1024)

    def test_new_download_errors_are_translated_in_all_interface_languages(self):
        from accessible_mail.download_text import DOWNLOAD_TRANSLATIONS, _KEYS
        from accessible_mail.i18n import get_language, set_language, tr

        previous = get_language()
        self.addCleanup(set_language, previous)
        for language in DOWNLOAD_TRANSLATIONS:
            set_language(language)
            for key in _KEYS:
                self.assertNotEqual(tr(key), key, (language, key))

    def test_large_attachment_label_uses_gigabytes(self):
        from accessible_mail.models import LinkItem
        self.assertEqual(LinkItem.format_size(5_000_000_000), "5.0 GB")


if __name__ == "__main__":
    unittest.main()
