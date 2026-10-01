"""Bounded-memory decoding shared by received IMAP and Gmail attachments."""
from __future__ import annotations

import base64
import binascii
import json
import quopri
import re
import time
from collections.abc import Callable, Iterable
from typing import BinaryIO


# Decimal gigabytes, per decoded received attachment. Sending limits are separate.
MAX_RECEIVED_ATTACHMENT_BYTES = 5_000_000_000
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
JSON_CHUNK_BYTES = 64 * 1024
ATTACHMENT_LIMIT_ERROR = "حجم المرفق المستلم يتجاوز الحد المسموح وهو 5 غيغابايت."
INVALID_ATTACHMENT_ERROR = "تعذر تنزيل المرفق كاملاً؛ بيانات المرفق غير صالحة أو غير مكتملة."
ATTACHMENT_WRITE_ERROR = "تعذر حفظ المرفق. تحقق من المساحة المتاحة وصلاحية الكتابة ودعم القرص للملفات الكبيرة."


class AttachmentDownloadError(RuntimeError):
    pass


def check_attachment_size(size: int) -> None:
    if size < 0:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    if size > MAX_RECEIVED_ATTACHMENT_BYTES:
        raise AttachmentDownloadError(ATTACHMENT_LIMIT_ERROR)


class AttachmentSink:
    def __init__(self, output: BinaryIO, total: int = 0,
                 on_progress: Callable[[int, int], None] | None = None):
        self.output = output
        self.total = total
        self.received = 0
        self.on_progress = on_progress
        self._last_report = time.monotonic()

    def write(self, data: bytes) -> None:
        check_attachment_size(self.received + len(data))
        try:
            written = self.output.write(data)
        except OSError as exc:
            raise AttachmentDownloadError(ATTACHMENT_WRITE_ERROR) from exc
        if written != len(data):
            raise AttachmentDownloadError(ATTACHMENT_WRITE_ERROR)
        self.received += written
        now = time.monotonic()
        if self.on_progress and now - self._last_report >= 0.15:
            self.on_progress(self.received, self.total)
            self._last_report = now

    def finish(self, expected_size: int | None = None) -> None:
        if expected_size is not None and expected_size != self.received:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        if self.on_progress:
            self.on_progress(self.received, self.received)


class TransferDecoder:
    def __init__(self, sink: AttachmentSink, encoding: str, *, urlsafe: bool = False):
        self.sink = sink
        self.encoding = encoding.casefold()
        self.urlsafe = urlsafe
        self.carry = b""
        self.ended = False
        if self.encoding not in {"base64", "quoted-printable", "", "7bit", "8bit", "binary"}:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)

    def feed(self, data: bytes) -> None:
        if self.encoding == "base64":
            data = re.sub(rb"[ \t\r\n]", b"", data)
            if self.ended and data:
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            combined = self.carry + data
            usable = len(combined) - len(combined) % 4
            block, self.carry = combined[:usable], combined[usable:]
            if b"=" in block:
                self.ended = True
                if self.carry:
                    raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            if block:
                self.sink.write(self._decode_base64(block))
        elif self.encoding == "quoted-printable":
            combined = self.carry + data
            # Only an incomplete '=XX' or '=CRLF' can cross a chunk boundary.
            # Do not retain an entire line: binary attachments need not have LF.
            last = combined.rfind(b"=")
            cut = last if last >= 0 and len(combined) - last < 3 else len(combined)
            self.carry = combined[cut:]
            self.sink.write(quopri.decodestring(combined[:cut]))
        else:
            self.sink.write(data)

    def _decode_base64(self, block: bytes) -> bytes:
        try:
            return base64.b64decode(block, altchars=b"-_" if self.urlsafe else None, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR) from exc

    def finish(self) -> None:
        if self.carry:
            if self.encoding == "quoted-printable" and self.carry == b"=\n":
                self.carry = b""
                return
            if self.encoding != "base64" or len(self.carry) == 1 or self.ended:
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            self.sink.write(self._decode_base64(self.carry + b"=" * (-len(self.carry) % 4)))
            self.carry = b""


def write_embedded_attachment(data: str, output: BinaryIO,
                              on_progress: Callable[[int, int], None] | None = None) -> None:
    sink = AttachmentSink(output, on_progress=on_progress)
    decoder = TransferDecoder(sink, "base64")
    try:
        for offset in range(0, len(data), DOWNLOAD_CHUNK_BYTES):
            decoder.feed(data[offset:offset + DOWNLOAD_CHUNK_BYTES].encode("ascii"))
    except UnicodeEncodeError as exc:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR) from exc
    decoder.finish()
    sink.finish()


class _AttachmentJsonReader:
    """Incremental reader for the documented flat Gmail MessagePartBody object.

    Only the data string can be large. All other tokens and the aggregate wire
    length are bounded; duplicate fields, trailing data and truncated JSON fail.
    """
    def __init__(self, response: BinaryIO):
        self.response = response
        self.buffer = b""
        self.position = 0
        self.wire_bytes = 0
        self.eof = False

    def peek(self) -> int | None:
        if self.position == len(self.buffer):
            if self.eof:
                return None
            self.buffer = self.response.read(JSON_CHUNK_BYTES)
            self.eof = not self.buffer
            self.position = 0
            self.wire_bytes += len(self.buffer)
            if self.wire_bytes > ((MAX_RECEIVED_ATTACHMENT_BYTES + 2) // 3 * 4) + 128 * 1024:
                raise AttachmentDownloadError(ATTACHMENT_LIMIT_ERROR)
        return self.buffer[self.position] if self.buffer else None

    def expect(self, value: int) -> None:
        self.whitespace()
        if self.peek() != value:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        self.position += 1

    def whitespace(self) -> None:
        while self.peek() in (9, 10, 13, 32):
            self.position += 1

    def string_blocks(self) -> Iterable[bytes]:
        self.expect(34)
        while self.peek() is not None:
            start = self.position
            # Scan a buffer in C, rather than doing Python work for every byte
            # of a multi-gigabyte base64url field.
            quote = self.buffer.find(b'"', start)
            escape = self.buffer.find(b"\\", start)
            stops = [value for value in (quote, escape) if value >= 0]
            stop = min(stops) if stops else len(self.buffer)
            block = self.buffer[start:stop]
            self.position = stop
            if block:
                if re.search(rb"[\x00-\x1f]", block):
                    raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
                yield block
            marker = self.peek()
            if marker == 34:
                self.position += 1
                return
            if marker == 92:
                self.position += 1
                escaped = self.peek()
                if escaped is None:
                    break
                self.position += 1
                token = bytes([92, escaped])
                if escaped == ord("u"):
                    for _ in range(4):
                        digit = self.peek()
                        if digit is None:
                            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
                        token += bytes([digit])
                        self.position += 1
                try:
                    yield json.loads(b'"' + token + b'"').encode("utf-8")
                except (ValueError, UnicodeError) as exc:
                    raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR) from exc
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)

    def small_string(self) -> str:
        value = bytearray()
        for block in self.string_blocks():
            value.extend(block)
            if len(value) > 64 * 1024:
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        try:
            return value.decode("utf-8")
        except UnicodeError as exc:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR) from exc

    def size(self) -> int:
        self.whitespace()
        digits = bytearray()
        while (value := self.peek()) is not None and ord("0") <= value <= ord("9"):
            digits.append(value)
            self.position += 1
            if len(digits) > 12:
                raise AttachmentDownloadError(ATTACHMENT_LIMIT_ERROR)
        if not digits or (len(digits) > 1 and digits[0] == ord("0")):
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        size = int(digits)
        check_attachment_size(size)
        return size


def stream_gmail_attachment(response: BinaryIO, output: BinaryIO, expected_size: int = 0,
                            on_progress: Callable[[int, int], None] | None = None) -> None:
    check_attachment_size(expected_size)
    reader = _AttachmentJsonReader(response)
    sink = AttachmentSink(output, expected_size, on_progress)
    decoder = TransferDecoder(sink, "base64", urlsafe=True)
    seen: set[str] = set()
    announced_size = None
    reader.expect(ord("{"))
    while True:
        key = reader.small_string()
        if key in seen:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        seen.add(key)
        reader.expect(ord(":"))
        if key == "data":
            for block in reader.string_blocks():
                # JSON whitespace is not legal inside the base64url value.
                if re.search(rb"[^A-Za-z0-9_+=/\-]", block):
                    raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
                decoder.feed(block)
            decoder.finish()
        elif key == "size":
            announced_size = reader.size()
            sink.total = announced_size
        elif key == "attachmentId":
            reader.small_string()
        else:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        reader.whitespace()
        marker = reader.peek()
        if marker == ord("}"):
            reader.position += 1
            break
        reader.expect(ord(","))
    reader.whitespace()
    if reader.peek() is not None or not {"data", "size"}.issubset(seen):
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    if expected_size and expected_size != announced_size:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    sink.finish(announced_size)
