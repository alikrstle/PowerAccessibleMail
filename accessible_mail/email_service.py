from __future__ import annotations

import base64
import imaplib
import re
import smtplib
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from .email_utils import (
    extract_body,
    header_to_text,
    is_plain_text_placeholder,
    looks_like_visual_markup_dump,
    strip_html_client_warning,
)
from .message_builder import build_outgoing_message
from .models import Account, MessageContent, MessageSummary
from .oauth import (
    OAuthError,
    OAuthReauthenticationRequired,
    ensure_access_token,
    xoauth2_auth_string,
)
from .secure_store import MessageCache


SPAM_CANDIDATES = (
    "[Gmail]/Spam",
    "Spam",
    "Junk",
    "Junk Email",
    "Bulk Mail",
    "البريد غير الهام",
    "غير مرغوب",
    "رسائل غير مرغوب فيها",
)

SENT_CANDIDATES = (
    "[Gmail]/Sent Mail",
    "Sent",
    "Sent Mail",
    "Sent Items",
    "Sent Messages",
    "Gesendet",
    "Envoyes",
    "العناصر المرسلة",
    "الرسائل المرسلة",
    "البريد المرسل",
)

ALL_MAIL_CANDIDATES = (
    "[Gmail]/All Mail",
    "[Google Mail]/All Mail",
    "All Mail",
    "كل البريد",
    "كل الرسائل",
)

TRASH_CANDIDATES = (
    "[Gmail]/Trash",
    "[Google Mail]/Trash",
    "Trash",
    "Deleted Messages",
    "Deleted Items",
    "Bin",
    "المهملات",
    "سلة المهملات",
    "العناصر المحذوفة",
)


class MailError(RuntimeError):
    pass


@dataclass(slots=True)
class MailboxInfo:
    name: str
    attributes: tuple[str, ...]


@dataclass(slots=True)
class MailSyncResult:
    mailbox: str
    messages: list[MessageSummary]
    added_count: int
    cached_count: int
    total_count: int = 0


class EmailService:
    def __init__(
        self,
        on_account_updated: Callable[[Account], None] | None = None,
        cache: MessageCache | None = None,
    ) -> None:
        self.on_account_updated = on_account_updated
        self.cache = cache or MessageCache()
        self._oauth_locks: dict[str, threading.Lock] = {}
        self._oauth_locks_guard = threading.Lock()

    def list_messages(
        self,
        account: Account,
        mailbox: str,
        limit: int = 50,
        batch_size: int = 50,
    ) -> list[MessageSummary]:
        cached = self._safe_cached_summaries(account.id, mailbox, limit)
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self._list_messages_from_server(
                    account,
                    mailbox,
                    limit,
                    batch_size,
                    cached,
                )
            except Exception as exc:
                if self._is_auth_failure(exc) or not self._is_transient_receive_error(exc) or attempt == 1:
                    last_error = exc
                    break
                time.sleep(getattr(self, "receive_retry_delay_seconds", 0.8))

        if last_error:
            raise last_error
        return cached

    def _list_messages_from_server(
        self,
        account: Account,
        mailbox: str,
        limit: int,
        batch_size: int,
        cached: list[MessageSummary],
    ) -> list[MessageSummary]:
        fetched_summaries: list[MessageSummary] = []
        try:
            with self._imap(account) as conn:
                message_count = self._select(conn, mailbox, readonly=True)
                if message_count <= 0:
                    return cached
                fetch_count = max(1, limit, batch_size)
                start = max(1, message_count - fetch_count + 1)
                fetched_summaries = self._fetch_summary_batch(conn, mailbox, f"{start}:*")
                if fetched_summaries:
                    try:
                        self.cache.upsert_summaries(account, fetched_summaries)
                    except Exception:
                        return self._merge_summaries(fetched_summaries, cached, limit)
        except Exception as exc:
            if self._is_auth_failure(exc):
                raise
            if cached:
                raise MailError(
                    "تعذر استلام رسائل جديدة من الخادم. الرسائل المعروضة الآن محفوظة محليا فقط. "
                    f"سبب المشكلة: {exc}"
                ) from exc
            raise
        return (
            self._safe_cached_summaries(account.id, mailbox, limit)
            or self._merge_summaries(fetched_summaries, cached, limit)
            or cached
        )

    def _safe_cached_summaries(
        self,
        account_id: str,
        mailbox: str,
        limit: int,
    ) -> list[MessageSummary]:
        try:
            return self.cache.list_summaries(account_id, mailbox, limit)
        except Exception:
            return []

    def _merge_summaries(
        self,
        primary: list[MessageSummary],
        fallback: list[MessageSummary],
        limit: int,
    ) -> list[MessageSummary]:
        merged_by_key: dict[tuple[str, str], MessageSummary] = {}
        for summary in [*fallback, *primary]:
            merged_by_key[(summary.mailbox, summary.uid)] = summary
        return sorted(
            merged_by_key.values(),
            key=lambda summary: self._summary_sort_key(summary),
            reverse=True,
        )[:limit]

    def _summary_sort_key(self, summary: MessageSummary) -> tuple[float, int, str]:
        try:
            uid_value = int(summary.uid)
        except ValueError:
            uid_value = 0
        return summary.sort_timestamp, uid_value, summary.date

    def fetch_message(
        self,
        account: Account,
        summary: MessageSummary,
        mark_read: bool = True,
    ) -> MessageContent:
        cached = self.cache.get_content(account.id, summary.mailbox, summary.uid)
        if cached:
            cleaned_cached_text = strip_html_client_warning(cached.text)
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

        with self._imap(account) as conn:
            self._select(conn, summary.mailbox, readonly=not mark_read)
            fetched = self._uid_fetch(conn, summary.uid.encode("ascii"), "(BODY.PEEK[])")
            if not fetched:
                raise MailError("تعذر تحميل الرسالة.")
            _flags_blob, raw_message = fetched
            message = BytesParser(policy=policy.default).parsebytes(raw_message)
            text, links = extract_body(message)
            if not text:
                text = "لا يوجد نص قابل للعرض داخل هذه الرسالة."
            if mark_read and not summary.is_read:
                self._set_message_flag(conn, summary.uid, "\\Seen", True)
                summary.is_read = True
            content = MessageContent(summary=summary, text=text, links=links)
            self.cache.upsert_content(account, content)
            return content

    def set_message_read(
        self,
        account: Account,
        summary: MessageSummary,
        is_read: bool,
    ) -> None:
        with self._imap(account) as conn:
            self._select(conn, summary.mailbox, readonly=False)
            self._set_message_flag(conn, summary.uid, "\\Seen", is_read)
        summary.is_read = is_read
        try:
            self.cache.mark_read(account, summary.mailbox, summary.uid, is_read)
        except Exception:
            pass

    def set_message_starred(
        self,
        account: Account,
        summary: MessageSummary,
        is_starred: bool,
    ) -> None:
        with self._imap(account) as conn:
            self._select(conn, summary.mailbox, readonly=False)
            self._set_message_flag(conn, summary.uid, "\\Flagged", is_starred)
        summary.is_starred = is_starred
        self.cache.update_summary_flags(account, summary.mailbox, summary.uid, is_starred=is_starred)

    def set_message_pinned(
        self,
        account: Account,
        summary: MessageSummary,
        is_pinned: bool,
    ) -> None:
        summary.is_pinned = is_pinned
        self.cache.update_summary_flags(account, summary.mailbox, summary.uid, is_pinned=is_pinned)

    def move_message_to_trash(self, account: Account, summary: MessageSummary) -> None:
        with self._imap(account) as conn:
            trash_mailbox = self.resolve_trash_mailbox(account, conn)
            if not trash_mailbox:
                raise MailError(
                    "تعذر العثور على مجلد سلة المهملات. لم تُحذف الرسالة."
                )
            self._select(conn, summary.mailbox, readonly=False)
            typ, _data = conn.uid("copy", summary.uid, f'"{trash_mailbox}"')
            if typ != "OK":
                typ, _data = conn.uid("copy", summary.uid, trash_mailbox)
            if typ != "OK":
                raise MailError("تعذر نقل الرسالة إلى سلة المهملات.")
            self._set_message_flag(conn, summary.uid, "\\Deleted", True)
            try:
                conn.uid("expunge", summary.uid)
            except (OSError, imaplib.IMAP4.error):
                pass
        self.cache.delete_message(account, summary.mailbox, summary.uid)

    def cached_messages(
        self,
        account: Account,
        mailbox: str,
        limit: int = 50,
    ) -> list[MessageSummary]:
        return self._safe_cached_summaries(account.id, mailbox, limit)

    def cached_message_count(self, account: Account, mailbox: str) -> int:
        try:
            return self.cache.count_summaries(account.id, mailbox)
        except Exception:
            return 0

    def load_older_messages(
        self,
        account: Account,
        mailbox: str,
        batch_size: int = 50,
    ) -> list[MessageSummary]:
        oldest_uid = self.cache.oldest_uid(account.id, mailbox)
        with self._imap(account) as conn:
            message_count = self._select(conn, mailbox, readonly=True)
            if message_count <= 0:
                total = self.cached_message_count(account, mailbox)
                return self.cache.list_summaries(account.id, mailbox, total)

            sequence_set = ""
            if oldest_uid:
                oldest_sequence = self._sequence_for_uid(conn, oldest_uid)
                if oldest_sequence > 1:
                    start = max(1, oldest_sequence - max(1, batch_size))
                    end = oldest_sequence - 1
                    sequence_set = f"{start}:{end}"
            if not sequence_set:
                start = max(1, message_count - max(1, batch_size) + 1)
                sequence_set = f"{start}:{message_count}"

            summaries = self._fetch_summary_batch(conn, mailbox, sequence_set)
            if summaries:
                self.cache.upsert_summaries(account, summaries)

        total = self.cached_message_count(account, mailbox)
        return self.cache.list_summaries(account.id, mailbox, total)

    def sync_all_older_messages(
        self,
        account: Account,
        mailbox: str,
        batch_size: int = 50,
        on_progress: Callable[[list[MessageSummary], int, int, int, int], None] | None = None,
    ) -> MailSyncResult:
        batch_size = max(1, batch_size)
        total_added = 0

        with self._imap(account) as conn:
            message_count = self._select(conn, mailbox, readonly=True)
            if message_count <= 0:
                cached_count = self.cached_message_count(account, mailbox)
                return MailSyncResult(
                    mailbox=mailbox,
                    messages=self.cache.list_summaries(account.id, mailbox, cached_count),
                    added_count=0,
                    cached_count=cached_count,
                    total_count=message_count,
                )

            end = message_count
            while end >= 1:
                start = max(1, end - batch_size + 1)
                sequence_set = f"{start}:{end}"

                before_count = self.cached_message_count(account, mailbox)
                summaries = self._fetch_summary_batch(conn, mailbox, sequence_set)
                if not summaries:
                    break

                self.cache.upsert_summaries(account, summaries)
                cached_count = self.cached_message_count(account, mailbox)
                added_count = max(0, cached_count - before_count)
                total_added += added_count
                if on_progress:
                    on_progress(summaries, added_count, total_added, cached_count, message_count)

                if start == 1:
                    break
                end = start - 1

        cached_count = self.cached_message_count(account, mailbox)
        return MailSyncResult(
            mailbox=mailbox,
            messages=self.cache.list_summaries(account.id, mailbox, cached_count),
            added_count=total_added,
            cached_count=cached_count,
            total_count=message_count,
        )

    def resolve_spam_mailbox(self, account: Account) -> str:
        saved = account.spam_mailbox.strip()
        if saved:
            return saved
        with self._imap(account) as conn:
            mailboxes = self.list_mailboxes(conn)
        mailbox = self._find_special_mailbox(
            mailboxes,
            ("\\junk",),
            SPAM_CANDIDATES,
            ("spam", "junk", "bulk", "غير مرغوب"),
        )
        return self._remember_spam_mailbox(account, mailbox)

    def _remember_spam_mailbox(self, account: Account, mailbox: str) -> str:
        if mailbox and account.spam_mailbox != mailbox:
            account.spam_mailbox = mailbox
            if self.on_account_updated:
                self.on_account_updated(account)
        return mailbox

    def resolve_sent_mailbox(self, account: Account) -> str:
        saved = account.sent_mailbox.strip()
        if saved:
            return saved
        with self._imap(account) as conn:
            mailboxes = self.list_mailboxes(conn)
        mailbox = self._find_special_mailbox(
            mailboxes,
            ("\\sent",),
            SENT_CANDIDATES,
            ("sent", "مرسل"),
        )
        return self._remember_sent_mailbox(account, mailbox)

    def resolve_all_mailbox(self, account: Account) -> str:
        with self._imap(account) as conn:
            mailboxes = self.list_mailboxes(conn)
        return self._find_special_mailbox(
            mailboxes,
            ("\\all", "\\allmail"),
            ALL_MAIL_CANDIDATES,
            ("all mail", "كل البريد", "كل الرسائل"),
        )

    def resolve_refresh_mailboxes(self, account: Account) -> tuple[str, str, str]:
        with self._imap(account) as conn:
            mailboxes = self.list_mailboxes(conn)
        spam_mailbox = account.spam_mailbox.strip() or self._find_special_mailbox(
            mailboxes,
            ("\\junk",),
            SPAM_CANDIDATES,
            ("spam", "junk", "bulk", "غير مرغوب"),
        )
        sent_mailbox = account.sent_mailbox.strip() or self._find_special_mailbox(
            mailboxes,
            ("\\sent",),
            SENT_CANDIDATES,
            ("sent", "مرسل"),
        )
        all_mailbox = self._find_special_mailbox(
            mailboxes,
            ("\\all", "\\allmail"),
            ALL_MAIL_CANDIDATES,
            ("all mail", "كل البريد", "كل الرسائل"),
        )
        changed = False
        if spam_mailbox and account.spam_mailbox != spam_mailbox:
            account.spam_mailbox = spam_mailbox
            changed = True
        if sent_mailbox and account.sent_mailbox != sent_mailbox:
            account.sent_mailbox = sent_mailbox
            changed = True
        if changed and self.on_account_updated:
            self.on_account_updated(account)
        return spam_mailbox, sent_mailbox, all_mailbox

    def resolve_trash_mailbox(self, account: Account, conn: imaplib.IMAP4 | None = None) -> str:
        if conn is None:
            with self._imap(account) as new_conn:
                mailboxes = self.list_mailboxes(new_conn)
        else:
            mailboxes = self.list_mailboxes(conn)
        return self._find_special_mailbox(
            mailboxes,
            ("\\trash",),
            TRASH_CANDIDATES,
            ("trash", "deleted", "مهمل", "محذوف"),
        )

    def _find_special_mailbox(
        self,
        mailboxes: list[MailboxInfo],
        special_attributes: tuple[str, ...],
        candidates: tuple[str, ...],
        name_fragments: tuple[str, ...],
    ) -> str:
        wanted_attributes = {attribute.lower() for attribute in special_attributes}
        for mailbox in mailboxes:
            attributes = {attribute.lower() for attribute in mailbox.attributes}
            if wanted_attributes.intersection(attributes):
                return mailbox.name

        lower_map = {mailbox.name.lower(): mailbox.name for mailbox in mailboxes}
        for candidate in candidates:
            found = lower_map.get(candidate.lower())
            if found:
                return found

        for mailbox in mailboxes:
            lower_name = mailbox.name.lower()
            if any(fragment in lower_name for fragment in name_fragments):
                return mailbox.name
        return ""

    def _remember_sent_mailbox(self, account: Account, mailbox: str) -> str:
        if mailbox and account.sent_mailbox != mailbox:
            account.sent_mailbox = mailbox
            if self.on_account_updated:
                self.on_account_updated(account)
        return mailbox

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

        if account.smtp_ssl:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                account.smtp_server,
                account.smtp_port,
                timeout=30,
            )
        else:
            smtp = smtplib.SMTP(account.smtp_server, account.smtp_port, timeout=30)

        with smtp:
            smtp.ehlo()
            if account.smtp_starttls and not account.smtp_ssl:
                smtp.starttls()
                smtp.ehlo()
            self._smtp_login(smtp, account)
            smtp.send_message(message)

    def list_mailboxes(self, conn: imaplib.IMAP4) -> list[MailboxInfo]:
        typ, data = conn.list()
        if typ != "OK" or not data:
            return []
        result: list[MailboxInfo] = []
        for item in data:
            if not item:
                continue
            text = item.decode("utf-8", errors="replace")
            match = re.match(r"\((?P<attrs>[^)]*)\)\s+\".*?\"\s+(?P<name>.+)$", text)
            if match:
                attributes = tuple(match.group("attrs").split())
                name_blob = match.group("name").strip()
            else:
                attributes = ()
                name_blob = text.rsplit(" ", 1)[-1].strip()
            if name_blob.startswith('"') and name_blob.endswith('"'):
                name = name_blob[1:-1].replace('\\"', '"')
            else:
                name = name_blob
            result.append(MailboxInfo(name=name, attributes=attributes))
        return result

    def _imap(self, account: Account) -> imaplib.IMAP4:
        if not account.imap_server:
            raise MailError("خادم IMAP غير مضبوط.")
        if account.imap_ssl:
            conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(
                account.imap_server,
                account.imap_port,
                timeout=30,
            )
        else:
            conn = imaplib.IMAP4(account.imap_server, account.imap_port, timeout=30)
        try:
            if account.uses_oauth:
                token = self._oauth_token(account)
                try:
                    conn.authenticate(
                        "XOAUTH2",
                        lambda _response: xoauth2_auth_string(account.login_name, token),
                    )
                except imaplib.IMAP4.error as exc:
                    raise OAuthReauthenticationRequired(
                        "رفض مزود البريد صلاحية تسجيل الدخول. افتح خيارات الحسابات "
                        "وإدارتها ثم اختر إعادة تسجيل الدخول للحساب.",
                        account.id,
                    ) from exc
            else:
                if not account.password:
                    raise MailError("كلمة مرور الحساب اليدوي غير محفوظة.")
                conn.login(account.login_name, account.password)
        except Exception:
            try:
                conn.logout()
            except (OSError, imaplib.IMAP4.error):
                pass
            raise
        return conn

    def _smtp_login(self, smtp: smtplib.SMTP, account: Account) -> None:
        if account.uses_oauth:
            token = self._oauth_token(account)
            encoded = base64.b64encode(
                xoauth2_auth_string(account.login_name, token)
            ).decode("ascii")
            code, response = smtp.docmd("AUTH", "XOAUTH2 " + encoded)
            if code not in {235, 503}:
                raise OAuthReauthenticationRequired(
                    "رفض مزود البريد صلاحية إرسال الرسائل. افتح خيارات الحسابات "
                    "وإدارتها ثم اختر إعادة تسجيل الدخول للحساب.",
                    account.id,
                )
            return
        if not account.password:
            raise MailError("كلمة مرور الحساب اليدوي غير محفوظة.")
        smtp.login(account.login_name, account.password)

    def _oauth_token(self, account: Account) -> str:
        with self._oauth_locks_guard:
            lock = self._oauth_locks.setdefault(account.id, threading.Lock())
        with lock:
            changed = ensure_access_token(account)
            if changed and self.on_account_updated:
                self.on_account_updated(account)
            return account.oauth_access_token

    def _set_message_flag(
        self,
        conn: imaplib.IMAP4,
        uid: str,
        flag: str,
        enabled: bool,
    ) -> None:
        operation = "+FLAGS" if enabled else "-FLAGS"
        typ, data = conn.uid("store", uid, operation, f"({flag})")
        if typ == "OK":
            return
        detail = data[0] if data else ""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        raise MailError(f"تعذر تحديث حالة الرسالة على الخادم: {detail}")

    def _is_auth_failure(self, exc: Exception) -> bool:
        if isinstance(exc, OAuthError):
            return True
        text = str(exc).lower()
        return any(
            marker in text
            for marker in (
                "authenticationfailed",
                "invalid credentials",
                "invalid_grant",
                "invalid_scope",
                "unauthorized",
                "xoauth2",
                "oauth",
            )
        )

    def _is_transient_receive_error(self, exc: Exception) -> bool:
        if isinstance(exc, MailError):
            text = str(exc).lower()
        elif isinstance(exc, (OSError, TimeoutError, imaplib.IMAP4.abort, imaplib.IMAP4.error)):
            return True
        else:
            text = str(exc).lower()
        return any(
            marker in text
            for marker in (
                "timed out",
                "timeout",
                "temporarily",
                "try again",
                "connection reset",
                "connection aborted",
                "connection closed",
                "socket",
                "bye",
                "server unavailable",
            )
        )

    def _select(self, conn: imaplib.IMAP4, mailbox: str, readonly: bool) -> int:
        value = mailbox.strip() or "INBOX"
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        quoted = f'"{escaped}"'
        if re.fullmatch(r"[A-Za-z0-9._/-]+", value):
            mailbox_arguments = [value, quoted]
        else:
            mailbox_arguments = [quoted, value]

        attempts = [readonly]
        if readonly:
            # Some Microsoft IMAP servers reject EXAMINE but accept SELECT.
            # Message reads still use BODY.PEEK, so this fallback does not mark mail read.
            attempts.append(False)

        last_detail = value
        for use_readonly in attempts:
            for mailbox_argument in dict.fromkeys(mailbox_arguments):
                try:
                    typ, data = conn.select(
                        mailbox_argument,
                        readonly=use_readonly,
                    )
                except imaplib.IMAP4.error as exc:
                    last_detail = str(exc) or value
                    continue
                if typ == "OK":
                    if data and data[0]:
                        try:
                            return int(data[0])
                        except (TypeError, ValueError):
                            return 0
                    return 0
                if data:
                    detail = data[0]
                    if isinstance(detail, bytes):
                        last_detail = detail.decode("utf-8", errors="replace")
                    else:
                        last_detail = str(detail)

        raise MailError(f"تعذر فتح مجلد البريد: {last_detail}")

    def _fetch_summary_batch(
        self,
        conn: imaplib.IMAP4,
        mailbox: str,
        sequence_set: str,
    ) -> list[MessageSummary]:
        typ, data = conn.fetch(
            sequence_set,
            "(UID FLAGS INTERNALDATE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID REFERENCES IN-REPLY-TO)])",
        )
        if typ != "OK" or not data:
            return []
        summaries: list[MessageSummary] = []
        for part in data:
            if not isinstance(part, tuple) or not isinstance(part[0], bytes):
                continue
            meta = part[0]
            header_bytes = part[1] if isinstance(part[1], bytes) else b""
            uid_match = re.search(rb"\bUID\s+(\d+)", meta)
            if (
                not uid_match
                or not header_bytes
                or re.search(rb"\\Deleted\b", meta, flags=re.IGNORECASE)
            ):
                continue
            summaries.append(
                self._summary_from_header(
                    uid=uid_match.group(1).decode("ascii", errors="ignore"),
                    mailbox=mailbox,
                    flags_blob=meta,
                    header_bytes=header_bytes,
                    has_attachments=self._fetch_meta_has_attachments(meta),
                )
            )
        return list(reversed(summaries))

    def _summary_from_header(
        self,
        uid: str,
        mailbox: str,
        flags_blob: bytes,
        header_bytes: bytes,
        has_attachments: bool = False,
    ) -> MessageSummary:
        message = BytesParser(policy=policy.default).parsebytes(header_bytes)
        sender = header_to_text(message.get("From"))
        sender_name, sender_email = parseaddr(sender)
        date_text = header_to_text(message.get("Date"))
        received_at = self._timestamp_from_internaldate(flags_blob)
        if not received_at:
            received_at = self._timestamp_from_header_date(date_text)
        return MessageSummary(
            uid=uid,
            mailbox=mailbox,
            sender=sender_name or sender_email or sender,
            sender_email=sender_email,
            subject=header_to_text(message.get("Subject")),
            date=date_text,
            received_at=received_at,
            is_read=b"\\Seen" in flags_blob,
            message_id=header_to_text(message.get("Message-ID")),
            references=header_to_text(message.get("References")),
            in_reply_to=header_to_text(message.get("In-Reply-To")),
            has_attachments=has_attachments,
            is_starred=b"\\Flagged" in flags_blob,
        )

    def _cached_content_needs_attachment_refresh(
        self,
        summary: MessageSummary,
        content: MessageContent,
    ) -> bool:
        if not summary.has_attachments:
            return False
        return not any(item.is_attachment for item in content.links)

    def _fetch_meta_has_attachments(self, meta: bytes) -> bool:
        upper = meta.upper()
        return any(
            marker in upper
            for marker in (
                b'"ATTACHMENT"',
                b" ATTACHMENT ",
                b'"FILENAME"',
                b" FILENAME ",
                b'"NAME"',
                b" NAME ",
            )
        )

    def _timestamp_from_internaldate(self, flags_blob: bytes) -> float:
        try:
            parsed = imaplib.Internaldate2tuple(flags_blob)
        except (TypeError, ValueError):
            return 0.0
        if not parsed:
            return 0.0
        try:
            return float(time.mktime(parsed))
        except (OverflowError, ValueError):
            return 0.0

    def _timestamp_from_header_date(self, date_text: str) -> float:
        if not date_text:
            return 0.0
        try:
            parsed = parsedate_to_datetime(date_text)
        except (TypeError, ValueError, IndexError, OverflowError):
            return 0.0
        if parsed is None:
            return 0.0
        try:
            return float(parsed.timestamp())
        except (OverflowError, ValueError, OSError):
            return 0.0

    def _next_older_sequence_set(
        self,
        conn: imaplib.IMAP4,
        account: Account,
        mailbox: str,
        message_count: int,
        batch_size: int,
    ) -> tuple[str, bool]:
        oldest_uid = self.cache.oldest_uid(account.id, mailbox)
        if oldest_uid:
            oldest_sequence = self._sequence_for_uid(conn, oldest_uid)
            if oldest_sequence > 1:
                start = max(1, oldest_sequence - batch_size)
                end = oldest_sequence - 1
                return f"{start}:{end}", start == 1
            if oldest_sequence == 1:
                return "", True

        start = max(1, message_count - batch_size + 1)
        return f"{start}:{message_count}", start == 1

    def _sequence_for_uid(self, conn: imaplib.IMAP4, uid: str) -> int:
        typ, data = conn.uid("fetch", uid, "(UID)")
        if typ != "OK" or not data:
            return 0
        for part in data:
            blob = b""
            if isinstance(part, tuple) and isinstance(part[0], bytes):
                blob = part[0]
            elif isinstance(part, bytes):
                blob = part
            match = re.match(rb"(\d+)\s+\(", blob)
            if match:
                return int(match.group(1))
        return 0

    def _uid_fetch(
        self,
        conn: imaplib.IMAP4,
        uid: bytes,
        query: str,
    ) -> tuple[bytes, bytes] | None:
        typ, data = conn.uid("fetch", uid, query)
        if typ != "OK" or not data:
            return None
        flags_blob = b" ".join(
            part[0]
            for part in data
            if isinstance(part, tuple) and isinstance(part[0], bytes)
        )
        payload = b"".join(
            part[1]
            for part in data
            if isinstance(part, tuple) and isinstance(part[1], bytes)
        )
        if not payload:
            return None
        return flags_blob, payload
