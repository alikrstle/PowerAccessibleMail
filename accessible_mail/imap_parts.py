"""Selective IMAP MIME reads, without downloading a large RFC822 literal."""
from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage

from .attachment_stream import AttachmentDownloadError, DOWNLOAD_CHUNK_BYTES, INVALID_ATTACHMENT_ERROR

MAX_STRUCTURE_BYTES = 1024 * 1024
MAX_BODY_PARTS = 256
# Quoted-printable can triple the bytes and add soft line breaks. This wire
# guard is distinct from the decoded 5 GB cap enforced by AttachmentSink.
MAX_ENCODED_PART_BYTES = 4 * 5_000_000_000


@contextmanager
def bounded_literal_reads(connection, limit: int):
    original = connection.read
    received = 0

    def read(size):
        nonlocal received
        received += size
        if size < 0 or received > limit:
            # Refuse the literal before imaplib allocates it. The connection is
            # unusable afterwards: do not attempt LOGOUT through unread bytes.
            connection.state = "LOGOUT"
            try:
                connection.shutdown()
            except OSError:
                pass
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        return original(size)

    connection.read = read
    try:
        yield
    finally:
        connection.read = original


class _StructureParser:
    def __init__(self, data: bytes):
        self.data = data
        self.position = 0
        self.tokens = 0

    def value(self, depth=0):
        self.tokens += 1
        if depth > 32 or self.tokens > 8192:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        self.space()
        if self.position >= len(self.data):
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        marker = self.data[self.position]
        self.position += 1
        if marker == ord("("):
            items = []
            while True:
                self.space()
                if self.position >= len(self.data):
                    raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
                if self.data[self.position] == ord(")"):
                    self.position += 1
                    return items
                items.append(self.value(depth + 1))
        if marker == ord('"'):
            result = bytearray()
            while self.position < len(self.data):
                char = self.data[self.position]
                self.position += 1
                if char == ord('"'):
                    return bytes(result)
                if char == ord("\\"):
                    if self.position == len(self.data):
                        break
                    char = self.data[self.position]
                    self.position += 1
                result.append(char)
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        if marker == ord("{"):
            match = re.match(rb"(\d{1,7})\}\r\n", self.data[self.position:])
            if not match:
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            start = self.position + match.end()
            end = start + int(match[1])
            if end > len(self.data):
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            self.position = end
            return self.data[start:end]
        self.position -= 1
        start = self.position
        while self.position < len(self.data) and self.data[self.position] not in b" ()\r\n\t":
            self.position += 1
        atom = self.data[start:self.position]
        if not atom:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        if atom.upper() == b"NIL":
            return None
        if atom.isdigit():
            if len(atom) > 20:
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            return int(atom)
        return atom

    def space(self):
        while self.position < len(self.data) and self.data[self.position] in b" \r\n\t":
            self.position += 1


def _response_wire(data, limit=MAX_STRUCTURE_BYTES) -> bytes:
    segments = []
    total = 0
    for piece in data:
        if isinstance(piece, tuple) and len(piece) == 2:
            if not all(isinstance(value, bytes) for value in piece):
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            literal = re.search(rb"\{(\d{1,12})\}$", piece[0])
            if not literal or int(literal[1]) != len(piece[1]):
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            segment = piece[0] + b"\r\n" + piece[1]
        elif isinstance(piece, bytes):
            segment = piece
        else:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        total += len(segment) + 1
        if total > limit:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        segments.append(segment)
    return b" ".join(segments)


def _fetch_records(data, limit=MAX_STRUCTURE_BYTES):
    parser = _StructureParser(_response_wire(data, limit))
    while True:
        parser.space()
        if parser.position == len(parser.data):
            return
        sequence, fields = parser.value(), parser.value()
        if not isinstance(sequence, int) or not isinstance(fields, list) or len(fields) % 2:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        if any(not isinstance(key, bytes) for key in fields[::2]):
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        keys = [key.upper() for key in fields[::2]]
        if len(set(keys)) != len(keys):
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        yield dict(zip(keys, fields[1::2], strict=True))


def fetch_structure(connection, uid: bytes) -> list:
    with bounded_literal_reads(connection, MAX_STRUCTURE_BYTES):
        status, data = connection.uid("fetch", uid, "(UID BODYSTRUCTURE)")
    if status != "OK" or not data:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    expected_uid = int(uid)
    found = None
    for metadata in _fetch_records(data):
        if metadata.get(b"UID") == expected_uid and b"BODYSTRUCTURE" in metadata:
            if found is not None:
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
            found = metadata[b"BODYSTRUCTURE"]
    if not isinstance(found, list) or not found:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    return found


def _text(value) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else ""


def _parameters(value) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, list) or len(value) % 2:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    return {_text(key).lower(): _text(item) for key, item in zip(value[::2], value[1::2], strict=True)}


@dataclass
class ImapPart:
    number: str
    encoded_size: int
    encoding: str
    message: EmailMessage


def leaf_parts(structure: list, prefix: str = "", depth: int = 0) -> list[ImapPart]:
    if depth > 24 or not structure:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    if isinstance(structure[0], list):
        result = []
        for index, child in enumerate(structure, 1):
            if not isinstance(child, list):
                break
            result.extend(leaf_parts(child, f"{prefix}.{index}" if prefix else str(index), depth + 1))
            if len(result) > MAX_BODY_PARTS:
                raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        return result
    if len(structure) < 7 or not isinstance(structure[6], int) or structure[6] < 0:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    message = EmailMessage(policy=policy.default)
    try:
        message.set_type(f"{_text(structure[0])}/{_text(structure[1])}".lower())
        for key, value in _parameters(structure[2]).items():
            message.set_param(key, value)
        if structure[3]:
            message["Content-ID"] = _text(structure[3])
        encoding = _text(structure[5]).lower()
        message["Content-Transfer-Encoding"] = encoding
        # TEXT adds a line count; MESSAGE/RFC822 adds envelope, body, lines.
        extra = 1 if _text(structure[0]).upper() == "TEXT" else 0
        if message.get_content_type() == "message/rfc822":
            extra = 3
        disposition_index = 8 + extra  # extension fields: MD5, disposition
        disposition = structure[disposition_index] if len(structure) > disposition_index else None
        if isinstance(disposition, list) and len(disposition) == 2:
            message["Content-Disposition"] = _text(disposition[0]).lower()
            for key, value in _parameters(disposition[1]).items():
                message.set_param(key, value, header="Content-Disposition")
    except (TypeError, ValueError, IndexError) as exc:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR) from exc
    return [ImapPart(prefix or "1", structure[6], encoding, message)]


def read_part_chunk(connection, uid: bytes, number: str, offset: int, count: int) -> bytes:
    if not re.fullmatch(r"[1-9]\d*(?:\.[1-9]\d*)*", number) or len(number) > 256:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    query = f"(UID BODY.PEEK[{number}]<{offset}.{count}>)"
    with bounded_literal_reads(connection, count):
        status, data = connection.uid("fetch", uid, query)
    if status != "OK" or not data:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    result = None
    expected_key = f"BODY[{number}]<{offset}>".encode("ascii")
    for metadata in _fetch_records(data, count + 64 * 1024):
        bodies = [key for key in metadata if key.startswith(b"BODY[")]
        if not bodies:
            continue
        if bodies != [expected_key] or metadata.get(b"UID") != int(uid):
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        chunk = metadata[expected_key]
        if result is not None or not isinstance(chunk, bytes) or len(chunk) > count:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        result = chunk
    if result is None:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    return result


def iter_part_chunks(connection, uid: bytes, part: ImapPart):
    if part.encoded_size > MAX_ENCODED_PART_BYTES:
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
    offset = 0
    while offset < part.encoded_size:
        count = min(DOWNLOAD_CHUNK_BYTES, part.encoded_size - offset)
        chunk = read_part_chunk(connection, uid, part.number, offset, count)
        if not chunk:
            raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
        yield chunk
        offset += len(chunk)
    # An underestimated size must not silently produce a truncated saved file.
    if read_part_chunk(connection, uid, part.number, offset, 1):
        raise AttachmentDownloadError(INVALID_ATTACHMENT_ERROR)
