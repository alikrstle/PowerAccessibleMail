from __future__ import annotations

import base64
import math
from dataclasses import asdict, dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import uuid4

from .date_format import format_message_date
from .i18n import is_rtl, tr


@dataclass(slots=True)
class Account:
    id: str = field(default_factory=lambda: str(uuid4()))
    display_name: str = ""
    email_address: str = ""
    username: str = ""
    auth_method: str = "oauth2"
    password: str = ""
    save_password: bool = False
    oauth_provider: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_access_token: str = ""
    oauth_refresh_token: str = ""
    oauth_token_expiry: float = 0.0
    save_oauth_tokens: bool = True
    imap_server: str = ""
    imap_port: int = 993
    imap_ssl: bool = True
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_ssl: bool = False
    smtp_starttls: bool = True
    spam_mailbox: str = ""
    sent_mailbox: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Account":
        account = cls()
        for field_name in cls.__dataclass_fields__:
            if field_name not in data or data[field_name] is None:
                continue
            current = getattr(account, field_name)
            value = data[field_name]
            if isinstance(current, bool):
                value = cls._boolean_value(value, current)
            elif isinstance(current, int):
                value = cls._integer_value(value, current)
            elif isinstance(current, float):
                value = cls._float_value(value, current)
            elif isinstance(current, str):
                value = value if isinstance(value, str) else current
            setattr(account, field_name, value)

        account.id = account.id.strip() or str(uuid4())
        account.imap_port = cls._port_value(account.imap_port, 993)
        account.smtp_port = cls._port_value(account.smtp_port, 587)
        if not math.isfinite(account.oauth_token_expiry):
            account.oauth_token_expiry = 0.0
        else:
            account.oauth_token_expiry = max(0.0, account.oauth_token_expiry)
        if account.auth_method not in {"oauth2", "password"}:
            account.auth_method = "oauth2"
        return account

    @staticmethod
    def _boolean_value(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _integer_value(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _float_value(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _port_value(value: int, default: int) -> int:
        return value if 1 <= value <= 65535 else default

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["password"] = ""
        data["save_password"] = False
        if not self.save_oauth_tokens:
            data["oauth_access_token"] = ""
            data["oauth_refresh_token"] = ""
            data["oauth_token_expiry"] = 0.0
        return data

    @property
    def label(self) -> str:
        if self.display_name and self.email_address:
            return f"{self.display_name} <{self.email_address}>"
        return self.email_address or self.display_name or tr("حساب بدون اسم")

    @property
    def login_name(self) -> str:
        return self.username or self.email_address

    @property
    def uses_oauth(self) -> bool:
        return self.auth_method == "oauth2"


@dataclass(slots=True)
class LinkItem:
    text: str
    url: str = ""
    kind: str = "link"
    filename: str = ""
    content_type: str = ""
    size: int = 0
    data: str = ""
    activation_text: str = ""
    activation_start: int = -1
    activation_end: int = -1
    activation_marker: str = ""
    content_id: str = ""

    @property
    def label(self) -> str:
        if self.is_attachment:
            filename = self.filename.strip() or self.text.strip() or tr("مرفق بدون اسم")
            details = [filename]
            if self.content_type:
                details.append(self.content_type)
            if self.size:
                details.append(self.format_size(self.size))
            return " - ".join(details)
        if self.is_image:
            description = self.text.strip() or self.filename.strip() or tr("صورة بدون وصف")
            if self.url.casefold().startswith(("http://", "https://")):
                return f"{description} - {self.url}"
            return description
        text = self.text.strip() or self.url
        if text == self.url:
            return self.url
        return f"{text} - {self.url}"

    @property
    def is_attachment(self) -> bool:
        return self.kind == "attachment"

    @property
    def is_button(self) -> bool:
        return self.kind == "button"

    @property
    def is_image(self) -> bool:
        return self.kind == "image"

    def attachment_bytes(self) -> bytes:
        if not self.data:
            return b""
        try:
            return base64.b64decode(self.data)
        except Exception:
            return b""

    @staticmethod
    def format_size(size: int) -> str:
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} bytes"


@dataclass(slots=True)
class MessageSummary:
    uid: str
    mailbox: str
    sender: str = ""
    sender_email: str = ""
    subject: str = ""
    date: str = ""
    received_at: float = 0.0
    is_read: bool = False
    message_id: str = ""
    references: str = ""
    in_reply_to: str = ""
    has_attachments: bool = False
    is_starred: bool = False
    is_pinned: bool = False

    @property
    def status_label(self) -> str:
        labels: list[str] = []
        if self.is_pinned:
            labels.append(tr("مثبتة"))
        if self.is_starred:
            labels.append(tr("مميزة بنجمة"))
        labels.append(tr("مقروءة") if self.is_read else tr("غير مقروءة"))
        return ("، " if is_rtl() else ", ").join(labels)

    @property
    def display_subject(self) -> str:
        return self.subject or tr("بدون موضوع")

    @property
    def display_date(self) -> str:
        return format_message_date(self.sort_timestamp, self.date)

    @property
    def sort_timestamp(self) -> float:
        if self.received_at:
            return self.received_at
        if not self.date:
            return 0.0
        try:
            parsed = parsedate_to_datetime(self.date)
        except (TypeError, ValueError, IndexError, OverflowError):
            return 0.0
        if parsed is None:
            return 0.0
        try:
            return float(parsed.timestamp())
        except (OverflowError, ValueError, OSError):
            return 0.0


@dataclass(slots=True)
class MessageContent:
    summary: MessageSummary
    text: str
    links: list[LinkItem]
