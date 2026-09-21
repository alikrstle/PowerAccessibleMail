from __future__ import annotations

import mimetypes
from collections.abc import Sequence
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .models import Account, MessageSummary


MAX_OUTGOING_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_OUTGOING_ATTACHMENTS_TOTAL_BYTES = 50 * 1024 * 1024


def build_outgoing_message(
    account: Account,
    to_address: str,
    subject: str,
    body: str,
    reply_to: MessageSummary | None = None,
    attachments: Sequence[Path] = (),
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = account.email_address
    message["To"] = to_address.strip()
    message["Subject"] = subject.strip() or "بدون موضوع"
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    if account.email_address:
        message["Reply-To"] = account.email_address
    if reply_to:
        if reply_to.message_id:
            message["In-Reply-To"] = reply_to.message_id
        references = " ".join(
            value
            for value in [reply_to.references, reply_to.message_id]
            if value
        )
        if references:
            message["References"] = references
    message.set_content(body or "")
    total_attachment_bytes = 0
    for attachment in attachments:
        path = Path(attachment)
        attachment_size = path.stat().st_size
        if attachment_size > MAX_OUTGOING_ATTACHMENT_BYTES:
            raise ValueError("المرفق يتجاوز الحد المسموح وهو 25 ميغابايت.")
        total_attachment_bytes += attachment_size
        if total_attachment_bytes > MAX_OUTGOING_ATTACHMENTS_TOTAL_BYTES:
            raise ValueError(
                "إجمالي حجم المرفقات يتجاوز الحد المسموح وهو 50 ميغابايت."
            )
        content_type, _encoding = mimetypes.guess_type(path.name)
        maintype, subtype = (
            content_type.split("/", 1)
            if content_type and "/" in content_type
            else ("application", "octet-stream")
        )
        message.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )
    return message
