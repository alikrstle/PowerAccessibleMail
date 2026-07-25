from __future__ import annotations

from collections.abc import Callable

from .email_service import EmailService, MailSyncResult
from .gmail_api_service import GmailApiService
from .models import Account, MessageContent, MessageSummary
from .secure_store import MessageCache


class MailServiceRouter:
    def __init__(self, on_account_updated: Callable[[Account], None] | None = None) -> None:
        self.cache = MessageCache()
        self.imap_service = EmailService(on_account_updated, self.cache)
        self.gmail_api_service = GmailApiService(on_account_updated, self.cache)

    def service_for(self, account: Account) -> EmailService | GmailApiService:
        if account.oauth_provider == "google_gmail_api":
            return self.gmail_api_service
        return self.imap_service

    def list_messages(
        self,
        account: Account,
        mailbox: str,
        limit: int = 50,
        batch_size: int = 50,
    ) -> list[MessageSummary]:
        return self.service_for(account).list_messages(account, mailbox, limit, batch_size)

    def fetch_message(
        self,
        account: Account,
        summary: MessageSummary,
        mark_read: bool = True,
    ) -> MessageContent:
        return self.service_for(account).fetch_message(account, summary, mark_read)

    def set_message_read(
        self,
        account: Account,
        summary: MessageSummary,
        is_read: bool,
    ) -> None:
        self.service_for(account).set_message_read(account, summary, is_read)

    def set_message_starred(
        self,
        account: Account,
        summary: MessageSummary,
        is_starred: bool,
    ) -> None:
        self.service_for(account).set_message_starred(account, summary, is_starred)

    def set_message_pinned(
        self,
        account: Account,
        summary: MessageSummary,
        is_pinned: bool,
    ) -> None:
        self.service_for(account).set_message_pinned(account, summary, is_pinned)

    def move_message_to_trash(self, account: Account, summary: MessageSummary) -> None:
        self.service_for(account).move_message_to_trash(account, summary)

    def cached_messages(
        self,
        account: Account,
        mailbox: str,
        limit: int = 50,
    ) -> list[MessageSummary]:
        return self.service_for(account).cached_messages(account, mailbox, limit)

    def cached_message_count(self, account: Account, mailbox: str) -> int:
        return self.service_for(account).cached_message_count(account, mailbox)

    def delete_cached_account(self, account: Account) -> None:
        cache = getattr(self, "cache", self.imap_service.cache)
        cache.delete_account(account.id)

    def load_older_messages(
        self,
        account: Account,
        mailbox: str,
        batch_size: int = 50,
    ) -> list[MessageSummary]:
        return self.service_for(account).load_older_messages(account, mailbox, batch_size)

    def sync_all_older_messages(
        self,
        account: Account,
        mailbox: str,
        batch_size: int = 50,
        on_progress: Callable[[list[MessageSummary], int, int, int, int], None] | None = None,
    ) -> MailSyncResult:
        return self.service_for(account).sync_all_older_messages(
            account,
            mailbox,
            batch_size,
            on_progress,
        )

    def resolve_spam_mailbox(self, account: Account) -> str:
        return self.service_for(account).resolve_spam_mailbox(account)

    def resolve_sent_mailbox(self, account: Account) -> str:
        return self.service_for(account).resolve_sent_mailbox(account)

    def resolve_all_mailbox(self, account: Account) -> str:
        service = self.service_for(account)
        resolver = getattr(service, "resolve_all_mailbox", None)
        if callable(resolver):
            return str(resolver(account))
        return ""

    def resolve_trash_mailbox(self, account: Account) -> str:
        service = self.service_for(account)
        resolver = getattr(service, "resolve_trash_mailbox", None)
        if callable(resolver):
            return str(resolver(account))
        return ""

    def resolve_refresh_mailboxes(self, account: Account) -> tuple[str, str, str]:
        service = self.service_for(account)
        resolver = getattr(service, "resolve_refresh_mailboxes", None)
        if callable(resolver):
            spam, sent, all_mail = resolver(account)
            return str(spam), str(sent), str(all_mail)
        return (
            self.resolve_spam_mailbox(account),
            self.resolve_sent_mailbox(account),
            self.resolve_all_mailbox(account),
        )

    def send_message(
        self,
        account: Account,
        to_address: str,
        subject: str,
        body: str,
        reply_to: MessageSummary | None = None,
    ) -> None:
        self.service_for(account).send_message(account, to_address, subject, body, reply_to)
