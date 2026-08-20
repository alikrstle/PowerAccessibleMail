from __future__ import annotations

import base64
import json
import mimetypes
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Any

from .email_service import MailError, MailSyncResult
from .email_utils import (
    clean_message_text_for_display,
    header_to_text,
    html_to_text_and_links,
    is_plain_text_placeholder,
    looks_like_visual_markup_dump,
    organize_message_items,
)
from .message_builder import build_outgoing_message
from .models import Account, LinkItem, MessageContent, MessageSummary
from .oauth import OAuthError, OAuthReauthenticationRequired, ensure_access_token
from .secure_store import MessageCache


GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_METADATA_HEADERS = ("From", "To", "Subject", "Date", "Message-ID", "References", "In-Reply-To")
GMAIL_READ_RETRY_DELAYS = (0.35, 0.9)
GMAIL_TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}
GMAIL_CACHED_METADATA_REFRESH_COUNT = 8
GMAIL_LABELS = {
    "ALL": "ALL",
    "INBOX": "INBOX",
    "SPAM": "SPAM",
    "SENT": "SENT",
    "TRASH": "TRASH",
}


class GmailApiService:
    def __init__(
        self,
        on_account_updated: Callable[[Account], None] | None = None,
        cache: MessageCache | None = None,
    ) -> None:
        self.on_account_updated = on_account_updated
        self.cache = cache or MessageCache()
        self.next_page_tokens: dict[tuple[str, str], str] = {}
        self.estimated_totals: dict[tuple[str, str], int] = {}
        self._oauth_locks: dict[str, threading.Lock] = {}
        self._oauth_locks_guard = threading.Lock()

    def list_messages(
        self,
        account: Account,
        mailbox: str,
        limit: int = 50,
        batch_size: int = 50,
    ) -> list[MessageSummary]:
        label_id = self.mailbox_to_label(mailbox)
        cached = self.cache.list_summaries(account.id, label_id, limit)
        summaries, next_token, total_estimate = self._list_summary_page(
            account,
            label_id,
            max_results=batch_size,
        )
        self.next_page_tokens[(account.id, label_id)] = next_token
        self.estimated_totals[(account.id, label_id)] = total_estimate
        if not summaries and total_estimate == 0:
            return []

        cached_by_uid = {summary.uid: summary for summary in cached}
        for summary in summaries:
            old = cached_by_uid.get(summary.uid)
            if old and old.is_pinned:
                summary.is_pinned = True
        if summaries:
            try:
                self.cache.upsert_summaries(account, summaries)
            except Exception:
                pass

        live_uids = {summary.uid for summary in summaries}
        pinned_extras = [
            summary
            for summary in cached
            if summary.is_pinned and summary.uid not in live_uids
        ]
        return sorted(
            [*summaries, *pinned_extras],
            key=lambda summary: (summary.is_pinned, summary.sort_timestamp),
            reverse=True,
        )[:limit]

    def fetch_message(
        self,
        account: Account,
        summary: MessageSummary,
        mark_read: bool = True,
    ) -> MessageContent:
        cached = self.cache.get_content(account.id, summary.mailbox, summary.uid)
        if cached:
            cleaned_cached_text = clean_message_text_for_display(cached.text)
            if cleaned_cached_text != cached.text:
                cached.text = cleaned_cached_text or "لا يوجد نص قابل للعرض داخل هذه الرسالة."
                self.cache.upsert_content(account, cached)
        if (
            cached
            and not self._cached_content_needs_attachment_refresh(summary, cached)
            and not looks_like_visual_markup_dump(cached.text)
            and not is_plain_text_placeholder(cached.text)
        ):
            if mark_read and not cached.summary.is_read:
                self.set_message_read(account, summary, True)
                cached.summary.is_read = True
            else:
                cached.summary.is_read = summary.is_read
            return cached

        message = self._get_message(account, summary.uid, "full")
        content = self._content_from_message(account, summary, message)
        if mark_read and "UNREAD" in message.get("labelIds", []):
            self._modify_message_labels(account, summary.uid, remove=["UNREAD"])
            summary.is_read = True
            content.summary.is_read = True
        self.cache.upsert_content(account, content)
        return content

    def set_message_read(
        self,
        account: Account,
        summary: MessageSummary,
        is_read: bool,
    ) -> None:
        if is_read:
            self._modify_message_labels(account, summary.uid, remove=["UNREAD"])
        else:
            self._modify_message_labels(account, summary.uid, add=["UNREAD"])
        summary.is_read = is_read
        try:
            self.cache.update_summary_flags_by_uid(account, summary.uid, is_read=is_read)
        except Exception:
            pass

    def set_message_starred(
        self,
        account: Account,
        summary: MessageSummary,
        is_starred: bool,
    ) -> None:
        if is_starred:
            self._modify_message_labels(account, summary.uid, add=["STARRED"])
        else:
            self._modify_message_labels(account, summary.uid, remove=["STARRED"])
        summary.is_starred = is_starred
        self.cache.update_summary_flags_by_uid(account, summary.uid, is_starred=is_starred)

    def set_message_pinned(
        self,
        account: Account,
        summary: MessageSummary,
        is_pinned: bool,
    ) -> None:
        summary.is_pinned = is_pinned
        self.cache.update_summary_flags_by_uid(account, summary.uid, is_pinned=is_pinned)

    def move_message_to_trash(self, account: Account, summary: MessageSummary) -> None:
        self._request_json(
            account,
            "POST",
            f"{GMAIL_API_BASE}/messages/{summary.uid}/trash",
        )
        self.cache.delete_message_by_uid(account, summary.uid)

    def cached_messages(
        self,
        account: Account,
        mailbox: str,
        limit: int = 50,
    ) -> list[MessageSummary]:
        return self.cache.list_summaries(account.id, self.mailbox_to_label(mailbox), limit)

    def cached_message_count(self, account: Account, mailbox: str) -> int:
        return self.cache.count_summaries(account.id, self.mailbox_to_label(mailbox))

    def load_older_messages(
        self,
        account: Account,
        mailbox: str,
        batch_size: int = 50,
    ) -> list[MessageSummary]:
        label_id = self.mailbox_to_label(mailbox)
        token_key = (account.id, label_id)
        page_token = self.next_page_tokens.get(token_key)
        if not page_token:
            self.list_messages(account, label_id, batch_size, batch_size)
            total = max(batch_size, self.cached_message_count(account, label_id))
            return self.cache.list_summaries(account.id, label_id, total)

        summaries, next_token, total_estimate = self._list_summary_page(
            account,
            label_id,
            max_results=batch_size,
            page_token=page_token,
        )
        self.next_page_tokens[token_key] = next_token
        self.estimated_totals[token_key] = total_estimate
        if summaries:
            self.cache.upsert_summaries(account, summaries)
        total = max(batch_size, self.cached_message_count(account, label_id))
        return self.cache.list_summaries(account.id, label_id, total)

    def sync_all_older_messages(
        self,
        account: Account,
        mailbox: str,
        batch_size: int = 50,
        on_progress: Callable[[list[MessageSummary], int, int, int, int], None] | None = None,
    ) -> MailSyncResult:
        label_id = self.mailbox_to_label(mailbox)
        batch_size = max(1, batch_size)
        page_token = ""
        total_added = 0
        total_estimate = self.estimated_totals.get((account.id, label_id), 0)

        while True:
            before_count = self.cached_message_count(account, label_id)
            summaries, next_token, estimate = self._list_summary_page(
                account,
                label_id,
                max_results=batch_size,
                page_token=page_token,
            )
            if estimate:
                total_estimate = estimate
            if summaries:
                self.cache.upsert_summaries(account, summaries)
            cached_count = self.cached_message_count(account, label_id)
            added_count = max(0, cached_count - before_count)
            total_added += added_count
            if on_progress:
                on_progress(summaries, added_count, total_added, cached_count, total_estimate)
            if not next_token:
                break
            page_token = next_token

        self.next_page_tokens[(account.id, label_id)] = ""
        self.estimated_totals[(account.id, label_id)] = total_estimate
        cached_count = self.cached_message_count(account, label_id)
        return MailSyncResult(
            mailbox=label_id,
            messages=self.cache.list_summaries(account.id, label_id, cached_count),
            added_count=total_added,
            cached_count=cached_count,
            total_count=total_estimate,
        )

    def resolve_spam_mailbox(self, _account: Account) -> str:
        return "SPAM"

    def resolve_sent_mailbox(self, _account: Account) -> str:
        return "SENT"

    def resolve_trash_mailbox(self, _account: Account) -> str:
        return "TRASH"

    def resolve_all_mailbox(self, _account: Account) -> str:
        return "ALL"

    def resolve_refresh_mailboxes(self, _account: Account) -> tuple[str, str, str]:
        return "SPAM", "SENT", "ALL"

    def send_message(
        self,
        account: Account,
        to_address: str,
        subject: str,
        body: str,
        reply_to: MessageSummary | None = None,
        attachments: Sequence[Path] = (),
    ) -> None:
        if not to_address.strip():
            raise MailError("يرجى كتابة عنوان المستلم.")

        message = build_outgoing_message(
            account,
            to_address,
            subject,
            body,
            reply_to,
            attachments,
        )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
        self._request_json(
            account,
            "POST",
            f"{GMAIL_API_BASE}/messages/send",
            {"raw": raw},
        )

    def mailbox_to_label(self, mailbox: str) -> str:
        value = (mailbox or "INBOX").upper()
        return GMAIL_LABELS.get(value, value)

    def _list_summary_page(
        self,
        account: Account,
        label_id: str,
        max_results: int,
        page_token: str = "",
        refresh_cached_count: int = GMAIL_CACHED_METADATA_REFRESH_COUNT,
    ) -> tuple[list[MessageSummary], str, int]:
        query: dict[str, str] = {
            "maxResults": str(max(1, max_results)),
        }
        if label_id != "ALL":
            query["labelIds"] = label_id
        if label_id in {"SPAM", "TRASH"}:
            query["includeSpamTrash"] = "true"
        if page_token:
            query["pageToken"] = page_token
        query["fields"] = "messages(id),nextPageToken,resultSizeEstimate"
        payload = self._request_json(
            account,
            "GET",
            f"{GMAIL_API_BASE}/messages?{urllib.parse.urlencode(query)}",
        )
        message_refs = payload.get("messages", [])
        summaries: list[MessageSummary] = []
        if isinstance(message_refs, list):
            message_ids = [
                str(item.get("id", "")).strip()
                for item in message_refs
                if isinstance(item, dict) and str(item.get("id", "")).strip()
            ]

            cache = getattr(self, "cache", None)
            cached_by_id = (
                cache.summaries_by_uids(account.id, label_id, message_ids)
                if cache is not None
                else {}
            )
            refresh_limit = max(0, refresh_cached_count)
            network_ids = [
                message_id
                for index, message_id in enumerate(message_ids)
                if message_id not in cached_by_id or index < refresh_limit
            ]

            def fetch_summary(message_id: str) -> MessageSummary:
                message = self._get_message(account, message_id, "metadata")
                return self._summary_from_message(label_id, message)

            errors: list[Exception] = []
            fetched_by_id: dict[str, MessageSummary] = {}
            workers = min(6, len(network_ids))
            if workers:
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gmail-summary") as executor:
                    futures = {
                        message_id: executor.submit(fetch_summary, message_id)
                        for message_id in network_ids
                    }
                    for message_id, future in futures.items():
                        try:
                            fetched_by_id[message_id] = future.result()
                        except Exception as exc:
                            errors.append(exc)
            oauth_error = next((error for error in errors if isinstance(error, OAuthError)), None)
            if oauth_error:
                raise oauth_error
            summaries = [
                summary
                for message_id in message_ids
                if (summary := fetched_by_id.get(message_id) or cached_by_id.get(message_id)) is not None
            ]
            if errors and not summaries:
                raise errors[0]
        return (
            summaries,
            str(payload.get("nextPageToken", "") or ""),
            int(payload.get("resultSizeEstimate", 0) or 0),
        )

    def _get_message(self, account: Account, message_id: str, message_format: str) -> dict[str, Any]:
        query_items = [("format", message_format)]
        if message_format.lower() == "metadata":
            query_items.extend(("metadataHeaders", header) for header in GMAIL_METADATA_HEADERS)
        query = urllib.parse.urlencode(query_items)
        return self._request_json(account, "GET", f"{GMAIL_API_BASE}/messages/{message_id}?{query}")

    def _summary_from_message(self, mailbox: str, message: dict[str, Any]) -> MessageSummary:
        headers = self._headers_from_payload(message.get("payload", {}))
        sender = header_to_text(headers.get("from", ""))
        sender_name, sender_email = parseaddr(sender)
        recipients = [
            address
            for _name, address in getaddresses([header_to_text(headers.get("to", ""))])
            if address
        ]
        date_text = header_to_text(headers.get("date", ""))
        received_at = self._internal_date_timestamp(message)
        return MessageSummary(
            uid=str(message.get("id", "")),
            mailbox=mailbox,
            sender=sender_name or sender_email or sender,
            sender_email=sender_email,
            recipient_emails=recipients,
            subject=header_to_text(headers.get("subject", "")),
            date=date_text,
            received_at=received_at,
            is_read="UNREAD" not in message.get("labelIds", []),
            message_id=header_to_text(headers.get("message-id", "")),
            references=header_to_text(headers.get("references", "")),
            in_reply_to=header_to_text(headers.get("in-reply-to", "")),
            has_attachments=self._payload_has_attachment(message.get("payload", {})),
            is_starred="STARRED" in message.get("labelIds", []),
        )

    def _content_from_message(
        self,
        account: Account,
        summary: MessageSummary,
        message: dict[str, Any],
    ) -> MessageContent:
        text_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[LinkItem] = []
        self._collect_payload_parts(account, summary.uid, message.get("payload", {}), text_parts, html_parts, attachments)
        raw_plain_text = "\n".join(part.strip() for part in text_parts if part.strip())
        plain_text_has_visual_noise = looks_like_visual_markup_dump(raw_plain_text)
        plain_text = clean_message_text_for_display(raw_plain_text)
        text = plain_text
        html_links: list[LinkItem] = []
        html_text = ""
        if html_parts:
            html_text, html_links = html_to_text_and_links("\n".join(html_parts))
        if html_parts and (
            not plain_text
            or plain_text_has_visual_noise
            or is_plain_text_placeholder(raw_plain_text)
        ):
            if html_text:
                text = html_text
        if not text:
            text = "لا يوجد نص قابل للعرض داخل هذه الرسالة."
        links = organize_message_items(text, html_links + attachments)
        fresh_summary = self._summary_from_message(summary.mailbox, message)
        fresh_summary.is_read = summary.is_read
        fresh_summary.is_pinned = summary.is_pinned
        return MessageContent(summary=fresh_summary, text=text, links=links)

    def _collect_payload_parts(
        self,
        account: Account,
        message_id: str,
        payload: dict[str, Any],
        text_parts: list[str],
        html_parts: list[str],
        attachments: list[LinkItem],
    ) -> None:
        filename = header_to_text(payload.get("filename", "")) or ""
        mime_type = str(payload.get("mimeType", "") or "application/octet-stream")
        headers = self._headers_from_payload(payload)
        disposition = headers.get("content-disposition", "").lower()
        body = payload.get("body", {}) if isinstance(payload.get("body", {}), dict) else {}
        attachment_id = str(body.get("attachmentId", "") or "")
        data = str(body.get("data", "") or "")
        size = int(body.get("size", 0) or 0)
        is_text_part = mime_type in {"text/plain", "text/html"}
        content_id = headers.get("content-id", "").strip()
        normalized_content_id = content_id.strip("<>").casefold()
        inline_image = (
            mime_type.casefold().startswith("image/")
            and "inline" in disposition
            and bool(normalized_content_id)
        )
        if inline_image:
            image_bytes = self._payload_bytes(data)
            if not image_bytes and attachment_id:
                image_bytes = self._attachment_bytes(account, message_id, attachment_id)
            image_filename = filename or f"image{mimetypes.guess_extension(mime_type) or ''}"
            attachments.append(
                LinkItem(
                    text=image_filename,
                    kind="image",
                    filename=image_filename,
                    content_type=mime_type,
                    size=size or len(image_bytes),
                    data=base64.b64encode(image_bytes).decode("ascii") if image_bytes else "",
                    content_id=normalized_content_id,
                )
            )
            return
        inline_resource = "inline" in disposition and bool(content_id) and not filename
        is_attachment = bool(
            filename
            or "attachment" in disposition
            or (attachment_id and not is_text_part and not inline_resource)
        )

        if is_attachment:
            attachment_bytes = self._payload_bytes(data)
            if not attachment_bytes and attachment_id:
                attachment_bytes = self._attachment_bytes(account, message_id, attachment_id)
            attachments.append(
                LinkItem(
                    text=filename or "مرفق بدون اسم",
                    kind="attachment",
                    filename=filename or "مرفق بدون اسم",
                    content_type=mime_type,
                    size=size or len(attachment_bytes),
                    data=base64.b64encode(attachment_bytes).decode("ascii") if attachment_bytes else "",
                )
            )
            return

        parts = payload.get("parts")
        if isinstance(parts, list) and parts:
            for part in parts:
                if isinstance(part, dict):
                    self._collect_payload_parts(account, message_id, part, text_parts, html_parts, attachments)
            return

        content_bytes = self._payload_bytes(data)
        if not content_bytes and attachment_id and is_text_part:
            content_bytes = self._attachment_bytes(account, message_id, attachment_id)
        content = self._decode_payload_text(content_bytes, headers) if content_bytes else ""
        if not content:
            return
        if mime_type == "text/plain":
            text_parts.append(content)
        elif mime_type == "text/html":
            html_parts.append(content)

    def _attachment_bytes(self, account: Account, message_id: str, attachment_id: str) -> bytes:
        payload = self._request_json(
            account,
            "GET",
            f"{GMAIL_API_BASE}/messages/{message_id}/attachments/{attachment_id}",
        )
        return self._payload_bytes(str(payload.get("data", "") or ""))

    def _modify_message_labels(
        self,
        account: Account,
        message_id: str,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        self._request_json(
            account,
            "POST",
            f"{GMAIL_API_BASE}/messages/{message_id}/modify",
            {
                "addLabelIds": add or [],
                "removeLabelIds": remove or [],
            },
        )

    def _request_json(
        self,
        account: Account,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._oauth_token(account)
        data = None
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        attempts = 1 + len(GMAIL_READ_RETRY_DELAYS) if method.upper() == "GET" else 1
        raw = b""
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                lowered_detail = detail.lower()
                rate_limited = exc.code == 403 and any(
                    marker in lowered_detail
                    for marker in ("ratelimit", "quotaexceeded", "backenderror")
                )
                retryable = exc.code in GMAIL_TRANSIENT_HTTP_CODES or rate_limited
                if retryable and attempt + 1 < attempts:
                    time.sleep(self._read_retry_delay(exc, attempt))
                    continue
                scope_denied = exc.code == 403 and any(
                    marker in lowered_detail
                    for marker in (
                        "access_token_scope_insufficient",
                        "insufficientpermissions",
                        "insufficient permission",
                        "insufficient authentication scopes",
                    )
                )
                if scope_denied:
                    raise OAuthReauthenticationRequired(
                        "صلاحية حساب Gmail المحفوظة قديمة أو ناقصة. افتح خيارات "
                        "الحسابات وإدارتها ثم اختر إعادة تسجيل الدخول للحساب، ووافق "
                        "على صلاحية Gmail المطلوبة.",
                        account.id,
                    ) from exc
                authentication_denied = exc.code == 401 or (
                    exc.code == 403
                    and any(
                        marker in lowered_detail
                        for marker in (
                            "autherror",
                            "invalid credentials",
                            "invalid_token",
                            "unauthenticated",
                        )
                    )
                )
                if authentication_denied and not rate_limited:
                    raise OAuthReauthenticationRequired(
                        "رفضت Google صلاحية الوصول إلى Gmail. "
                        "افتح خيارات الحسابات وإدارتها ثم اختر إعادة تسجيل الدخول للحساب.",
                        account.id,
                    ) from exc
                raise MailError(f"تعذر الاتصال بـ Gmail API: {exc.code} {detail}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt + 1 < attempts:
                    time.sleep(GMAIL_READ_RETRY_DELAYS[attempt])
                    continue
                raise MailError(f"تعذر الاتصال بـ Gmail API: {exc}") from exc
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MailError("استجابة Gmail API غير صالحة.") from exc
        if not isinstance(payload, dict):
            raise MailError("استجابة Gmail API غير صالحة.")
        return payload

    def _read_retry_delay(self, exc: urllib.error.HTTPError, attempt: int) -> float:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            try:
                return max(0.0, min(5.0, float(retry_after)))
            except ValueError:
                pass
        return GMAIL_READ_RETRY_DELAYS[min(attempt, len(GMAIL_READ_RETRY_DELAYS) - 1)]

    def _oauth_token(self, account: Account) -> str:
        with self._oauth_locks_guard:
            lock = self._oauth_locks.setdefault(account.id, threading.Lock())
        with lock:
            changed = ensure_access_token(account)
            if changed and self.on_account_updated:
                self.on_account_updated(account)
            return account.oauth_access_token

    def _cached_content_needs_attachment_refresh(
        self,
        summary: MessageSummary,
        content: MessageContent,
    ) -> bool:
        if not summary.has_attachments:
            return False
        return not any(item.is_attachment for item in content.links)

    def _headers_from_payload(self, payload: Any) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        headers: dict[str, str] = {}
        for item in payload.get("headers", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).lower()
            value = str(item.get("value", ""))
            if name:
                headers[name] = value
        return headers

    def _payload_has_attachment(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        filename = str(payload.get("filename", "") or "")
        mime_type = str(payload.get("mimeType", "") or "application/octet-stream")
        headers = self._headers_from_payload(payload)
        disposition = headers.get("content-disposition", "").lower()
        body = payload.get("body", {}) if isinstance(payload.get("body", {}), dict) else {}
        if filename or "attachment" in disposition:
            return True
        if body.get("attachmentId") and mime_type not in {"text/plain", "text/html"}:
            return True
        parts = payload.get("parts")
        if isinstance(parts, list):
            return any(self._payload_has_attachment(part) for part in parts)
        return False

    def _payload_bytes(self, data: str) -> bytes:
        if not data:
            return b""
        padding = "=" * (-len(data) % 4)
        try:
            return base64.urlsafe_b64decode((data + padding).encode("ascii"))
        except Exception:
            return b""

    def _decode_payload_text(self, data: bytes, headers: dict[str, str]) -> str:
        content_type = headers.get("content-type", "")
        message = Message()
        if content_type:
            message["Content-Type"] = content_type
        charset = message.get_content_charset() or "utf-8"
        try:
            return data.decode(charset, errors="replace")
        except LookupError:
            return data.decode("utf-8", errors="replace")

    def _internal_date_timestamp(self, message: dict[str, Any]) -> float:
        try:
            return int(message.get("internalDate", 0) or 0) / 1000
        except (TypeError, ValueError):
            return time.time()
