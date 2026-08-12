from __future__ import annotations

import imaplib
import smtplib
import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import wx
import wx.adv
import wx.html2

from .attachment_storage import (
    cleanup_opened_attachment_session,
    cleanup_stale_opened_attachments,
)
from .accessibility import (
    announce_to_screen_reader,
    focused_control,
    restore_control_focus,
    set_accessible,
)
from .account_dialog import AccountDialog
from .bulk_operations import run_bulk_operations
from .config import (
    APP_TITLE,
    APP_VERSION,
    LANGUAGE_ENGLISH,
    LANGUAGE_FRENCH,
    THEME_DARK,
    TRANSLATION_INLINE,
    load_accounts,
    load_oauth_clients,
    load_settings,
    save_accounts,
    save_settings,
)
from .dialogs import (
    BulkDeleteDialog,
    ComposeDialog,
    SettingsDialog,
    UpdateAvailableDialog,
    UpdateDownloadDialog,
)
from .email_service import MailError, MailSyncResult
from .email_utils import normalize_message_text
from .guide import load_program_guide
from .i18n import set_language, tr
from .mail_page import MailPage
from .mail_service_router import MailServiceRouter
from .models import Account, MessageContent, MessageSummary
from .oauth import (
    OAuthError,
    OAuthReauthenticationRequired,
    apply_provider_settings,
    run_browser_oauth_flow,
)
from .translation import translate_text_with_google
from .ui_constants import (
    BULK_ACTION_DELETE,
    BULK_ACTION_MARK_READ,
    BULK_ACTION_MARK_UNREAD,
    BULK_ACTION_PIN,
    BULK_ACTION_STAR,
    BULK_ACTION_UNPIN,
    BULK_ACTION_UNSTAR,
    INITIAL_MESSAGE_LIMIT,
    MAX_MEMORY_MESSAGE_CONTENTS,
    MESSAGE_SELECTION_DELAY_MS,
)
from .ui_helpers import (
    app_icon_path,
    apply_layout_direction,
    localize_menu_bar,
    localize_window,
    set_localized_items,
)
from .update_checker import UpdateCheckResult, check_for_updates, updates_configured
from .updater import (
    UpdateDownloadCancelled,
    can_install_update,
    download_update_installer,
    launch_update_installer,
)


def call_after_if_open(
    owner: object,
    callback: Callable[..., Any],
    *args: object,
) -> None:
    if getattr(owner, "_closing", False):
        return

    def invoke() -> None:
        if not getattr(owner, "_closing", False):
            callback(*args)

    wx.CallAfter(invoke)


class MainFrame(wx.Frame):
    def __init__(self) -> None:
        settings = load_settings()
        set_language(settings.language)
        super().__init__(None, title=APP_TITLE, size=(1000, 760))
        icon_path = app_icon_path()
        if icon_path:
            icon = wx.Icon(str(icon_path), wx.BITMAP_TYPE_ICO)
            if icon.IsOk():
                self.SetIcon(icon)
        self.settings = settings
        self.service = MailServiceRouter(self.on_account_updated)
        self.accounts = load_accounts()
        self.content_cache: OrderedDict[tuple[str, str, str], MessageContent] = OrderedDict()
        self.current_content: MessageContent | None = None
        self.displayed_account_id: str | None = None
        self._syncing_page_keys: set[str] = set()
        self._known_inbox_uids: dict[str, set[str]] = {}
        self._all_mailboxes_by_account: dict[str, str] = {}
        self._trash_mailboxes_by_account: dict[str, str] = {}
        self._polling_new_mail = False
        self._message_load_generation = 0
        self._message_load_call: wx.CallLater | None = None
        self._notification_timer: wx.CallLater | None = None
        self._startup_update_call: wx.CallLater | None = None
        self._startup_update_check_started = False
        self._update_dialog_open = False
        self._update_download_active = False
        self._update_progress_dialog: UpdateDownloadDialog | None = None
        self._update_cancel_event: threading.Event | None = None
        self._startup_login_shown = False
        self._reauthentication_active = False
        self._active_worker_count = 0
        self._closing = False
        self.pages: dict[str, MailPage] = {}
        cleanup_stale_opened_attachments()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self._build()
        self.apply_settings()
        self._load_accounts_to_choice()
        self._start_new_mail_timer()
        self._startup_update_call = wx.CallLater(2500, self.start_startup_update_check)
        self.Centre()
        call_after_if_open(self, self.show_welcome_notification)
        call_after_if_open(self, self.show_initial_login_if_needed)

    def on_close(self, event: wx.CloseEvent) -> None:
        if self._closing:
            event.Skip()
            return
        self._closing = True
        for call in (
            self._message_load_call,
            self._notification_timer,
            self._startup_update_call,
        ):
            if call is not None and call.IsRunning():
                call.Stop()
        if hasattr(self, "new_mail_timer"):
            self.new_mail_timer.Stop()
        if self._update_cancel_event is not None:
            self._update_cancel_event.set()
        cleanup_opened_attachment_session()
        event.Skip()

    def _build(self) -> None:
        panel = wx.Panel(self)
        self.main_panel = panel
        apply_layout_direction(panel)

        root = wx.BoxSizer(wx.VERTICAL)
        self.notification_bar = wx.InfoBar(panel)
        set_accessible(self.notification_bar, "إشعارات البرنامج")
        root.Add(self.notification_bar, 0, wx.EXPAND)
        top_row = wx.BoxSizer(wx.HORIZONTAL)

        account_row = wx.BoxSizer(wx.HORIZONTAL)
        account_row.Add(wx.StaticText(panel, label="الحساب:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.account_choice = wx.Choice(panel)
        self.account_choice.SetMinSize((360, -1))
        set_accessible(self.account_choice, "اختيار حساب البريد")
        account_row.Add(self.account_choice, 1, wx.EXPAND | wx.ALL, 6)
        top_row.Add(account_row, 1, wx.EXPAND)

        command_column = wx.BoxSizer(wx.VERTICAL)
        command_column.Add(
            wx.StaticText(panel, label="الأوامر:"),
            0,
            wx.LEFT | wx.RIGHT | wx.TOP,
            6,
        )
        self.command_list = wx.ListBox(
            panel,
            choices=[tr(label) for label in self.command_labels()],
            style=wx.LB_SINGLE,
        )
        self.command_list.SetSelection(0)
        self.command_list.SetMinSize((280, 150))
        set_accessible(
            self.command_list,
            "قائمة أوامر البرنامج",
            "استخدم السهم للأعلى والأسفل ثم Enter أو Space لتنفيذ الأمر المحدد",
        )
        command_column.Add(self.command_list, 1, wx.EXPAND | wx.ALL, 6)
        top_row.Add(command_column, 0, wx.EXPAND | wx.ALL, 6)
        root.Add(top_row, 0, wx.EXPAND)

        self.notebook = wx.Notebook(panel)
        inbox_page = MailPage(
            self.notebook,
            "الرسائل الواردة",
            self.on_message_selected,
            self.on_toggle_message_read,
            self.on_translate_current_message,
            self.on_reply,
            self.on_toggle_star_current_message,
            self.on_toggle_pin_current_message,
            self.on_delete_current_message,
            self.on_bulk_message_action,
            self.on_mail_page_filter_changed,
        )
        spam_page = MailPage(
            self.notebook,
            "الرسائل غير المرغوب بها",
            self.on_message_selected,
            self.on_toggle_message_read,
            self.on_translate_current_message,
            self.on_reply,
            self.on_toggle_star_current_message,
            self.on_toggle_pin_current_message,
            self.on_delete_current_message,
            self.on_bulk_message_action,
            self.on_mail_page_filter_changed,
        )
        sent_page = MailPage(
            self.notebook,
            "الرسائل المرسلة",
            self.on_message_selected,
            self.on_toggle_message_read,
            self.on_translate_current_message,
            self.on_reply,
            self.on_toggle_star_current_message,
            self.on_toggle_pin_current_message,
            self.on_delete_current_message,
            self.on_bulk_message_action,
            self.on_mail_page_filter_changed,
        )
        all_mail_page = MailPage(
            self.notebook,
            "كل الرسائل",
            self.on_message_selected,
            self.on_toggle_message_read,
            self.on_translate_current_message,
            self.on_reply,
            self.on_toggle_star_current_message,
            self.on_toggle_pin_current_message,
            self.on_delete_current_message,
            self.on_bulk_message_action,
            self.on_mail_page_filter_changed,
        )
        self.pages["inbox"] = inbox_page
        self.pages["spam"] = spam_page
        self.pages["sent"] = sent_page
        self.pages["all"] = all_mail_page
        self.notebook.AddPage(inbox_page, tr("الرسائل الواردة"))
        self.notebook.AddPage(spam_page, tr("الرسائل غير المرغوب بها"))
        self.notebook.AddPage(sent_page, tr("الرسائل المرسلة"))
        self.notebook.AddPage(all_mail_page, tr("كل الرسائل"))
        set_accessible(self.notebook, "أقسام البريد")
        root.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 8)

        progress_row = wx.BoxSizer(wx.HORIZONTAL)
        self.transfer_progress_label = wx.StaticText(panel, label="تقدم استلام الرسائل: 0%")
        progress_row.Add(self.transfer_progress_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.transfer_progress = wx.Gauge(panel, range=100)
        set_accessible(
            self.transfer_progress,
            "نسبة تقدم استلام الرسائل",
            "تعرض نسبة تقدم جلب الرسائل من خادم البريد",
        )
        progress_row.Add(self.transfer_progress, 1, wx.EXPAND | wx.ALL, 6)
        root.Add(progress_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(root)
        self.CreateStatusBar()
        self.SetStatusText("جاهز")

        self.command_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_command_activated)
        self.command_list.Bind(wx.EVT_CHAR_HOOK, self.on_command_key)
        self.account_choice.Bind(wx.EVT_CHOICE, self.on_account_changed)

        self._create_menu()
        self._create_accelerators()
        localize_window(self)
        localize_menu_bar(self.GetMenuBar())

    @staticmethod
    def command_labels() -> list[str]:
        return [
            "تحديث المحتوى المعروض",
            "مزامنة كل الرسائل",
            "تحميل رسائل أقدم",
            "خيارات الحسابات وإدارتها",
            "إنشاء بريد إلكتروني",
            "الإعدادات",
        ]

    def SetStatusText(self, text: str, number: int = 0) -> None:
        super().SetStatusText(tr(text), number)

    def _create_menu(self) -> None:
        menu_bar = wx.MenuBar()
        file_menu = wx.Menu()
        account_options_item = file_menu.Append(wx.ID_ANY, "خيارات الحسابات وإدارتها\tCtrl+A")
        settings_item = file_menu.Append(wx.ID_ANY, "الإعدادات")
        compose_item = file_menu.Append(wx.ID_ANY, "إنشاء بريد\tCtrl+N")
        refresh_item = file_menu.Append(wx.ID_ANY, "تحديث\tF5")
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, "خروج\tAlt+F4")
        menu_bar.Append(file_menu, "ملف")

        message_menu = wx.Menu()
        reply_item = message_menu.Append(wx.ID_ANY, "رد\tCtrl+R")
        translate_item = message_menu.Append(wx.ID_ANY, "ترجمة الرسالة\tCtrl+T")
        self.translate_menu_item = translate_item
        menu_bar.Append(message_menu, "رسالة")

        help_menu = wx.Menu()
        guide_item = help_menu.Append(wx.ID_ANY, "عرض دليل البرنامج\tF1")
        update_item = help_menu.Append(wx.ID_ANY, "تحديث البرنامج")
        menu_bar.Append(help_menu, "المساعدة")
        self.SetMenuBar(menu_bar)

        self.Bind(wx.EVT_MENU, self.on_account_options, account_options_item)
        self.Bind(wx.EVT_MENU, self.on_settings, settings_item)
        self.Bind(wx.EVT_MENU, self.on_compose, compose_item)
        self.Bind(wx.EVT_MENU, self.on_refresh, refresh_item)
        self.Bind(wx.EVT_MENU, lambda _event: self.Close(), exit_item)
        self.Bind(wx.EVT_MENU, self.on_reply, reply_item)
        self.Bind(wx.EVT_MENU, self.on_translate_current_message, translate_item)
        self.Bind(wx.EVT_MENU, self.on_show_guide, guide_item)
        self.Bind(wx.EVT_MENU, self.on_check_updates, update_item)
        self.Bind(wx.EVT_MENU_OPEN, self.on_menu_open)

    def _create_accelerators(self) -> None:
        self.accel_add = wx.NewIdRef()
        self.accel_compose = wx.NewIdRef()
        self.accel_reply = wx.NewIdRef()
        self.accel_refresh = wx.NewIdRef()
        self.accel_translate = wx.NewIdRef()
        self.accel_close = wx.NewIdRef()
        self.accel_guide = wx.NewIdRef()
        self.accel_focus_items = wx.NewIdRef()
        self.accel_context_menu = wx.NewIdRef()
        entries = [
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("A"), self.accel_add),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("N"), self.accel_compose),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("R"), self.accel_reply),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F5, self.accel_refresh),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("T"), self.accel_translate),
            wx.AcceleratorEntry(wx.ACCEL_ALT, wx.WXK_F4, self.accel_close),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F1, self.accel_guide),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, wx.WXK_RETURN, self.accel_focus_items),
            wx.AcceleratorEntry(wx.ACCEL_SHIFT, wx.WXK_F10, self.accel_context_menu),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_MENU, self.accel_context_menu),
            wx.AcceleratorEntry(
                wx.ACCEL_NORMAL,
                wx.WXK_WINDOWS_MENU,
                self.accel_context_menu,
            ),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))
        self.Bind(wx.EVT_MENU, self.on_account_options, id=self.accel_add)
        self.Bind(wx.EVT_MENU, self.on_compose, id=self.accel_compose)
        self.Bind(wx.EVT_MENU, self.on_reply, id=self.accel_reply)
        self.Bind(wx.EVT_MENU, self.on_refresh, id=self.accel_refresh)
        self.Bind(wx.EVT_MENU, self.on_translate_current_message, id=self.accel_translate)
        self.Bind(wx.EVT_MENU, lambda _event: self.Close(), id=self.accel_close)
        self.Bind(wx.EVT_MENU, self.on_show_guide, id=self.accel_guide)
        self.Bind(wx.EVT_MENU, self.on_focus_items_accelerator, id=self.accel_focus_items)
        self.Bind(wx.EVT_MENU, self.on_context_menu_accelerator, id=self.accel_context_menu)

    def on_menu_open(self, _event: wx.MenuEvent) -> None:
        if hasattr(self, "translate_menu_item"):
            self.translate_menu_item.Enable(self.can_translate_current_message())

    def on_focus_items_accelerator(self, _event: wx.Event | None = None) -> None:
        page = self.current_page()
        if not page:
            return
        call_after_if_open(self, page.toggle_message_and_link_viewers)

    def on_context_menu_accelerator(self, _event: wx.Event | None = None) -> None:
        page = self.current_page()
        if not page:
            return
        focus = wx.Window.FindFocus()
        if focus is page.actions_button:
            control = page.actions_button
        elif focus is page.viewer:
            control = page.viewer
        elif focus is page.link_list:
            return
        elif focus is page.list:
            control = page.list
        else:
            control = page.html_viewer
        call_after_if_open(
            self,
            page.show_message_context_menu,
            control,
            page.has_translatable_content() and control in {page.viewer, page.html_viewer, page.actions_button},
        )

    def _load_accounts_to_choice(
        self,
        preferred_account_id: str | None = None,
    ) -> None:
        focus_owner = focused_control()
        self.account_choice.Set([account.label for account in self.accounts])
        if self.accounts:
            selection = next(
                (
                    index
                    for index, account in enumerate(self.accounts)
                    if account.id == preferred_account_id
                ),
                0,
            )
            self.account_choice.SetSelection(selection)
            restore_control_focus(focus_owner)
            call_after_if_open(self, self.refresh_all)
        else:
            restore_control_focus(focus_owner)
            self.SetStatusText("لا يوجد حساب. افتح خيارات الحسابات وإدارتها للبدء.")

    def show_initial_login_if_needed(self) -> None:
        if self.accounts:
            call_after_if_open(self, self.account_choice.SetFocus)
            return
        if self._startup_login_shown:
            return
        self._startup_login_shown = True
        dialog = AccountDialog(self, startup=True)
        account_added = self.finish_account_dialog(dialog)
        if not account_added and not self.accounts:
            call_after_if_open(self, self.account_choice.SetFocus)

    def show_welcome_notification(self) -> None:
        self.show_notification("مرحبا بكم في برنامج Power Accessible Mail")

    def selected_account(self) -> Account | None:
        index = self.account_choice.GetSelection()
        if 0 <= index < len(self.accounts):
            return self.accounts[index]
        return None

    def page_key_for_page(self, page: MailPage) -> str:
        if page is self.pages["spam"]:
            return "spam"
        if page is self.pages["sent"]:
            return "sent"
        if page is self.pages["all"]:
            return "all"
        return "inbox"

    def mailbox_for_page_key(self, account: Account, page_key: str) -> str:
        if page_key == "spam":
            return account.spam_mailbox
        if page_key == "sent":
            return account.sent_mailbox
        if page_key == "all":
            return ""
        return "INBOX"

    def resolve_mailbox_for_page_key(self, account: Account, page_key: str) -> str:
        mailbox = self.mailbox_for_page_key(account, page_key)
        if mailbox:
            return mailbox
        if page_key == "spam":
            return self.service.resolve_spam_mailbox(account)
        if page_key == "sent":
            return self.service.resolve_sent_mailbox(account)
        if page_key == "all":
            return self.service.resolve_all_mailbox(account)
        return "INBOX"

    def on_mail_page_filter_changed(self, page: MailPage) -> None:
        if page.selected_filter_key() == "trash":
            self.load_trash_messages(page)
            return
        page.apply_filter()

    def load_trash_messages(self, page: MailPage) -> None:
        account = self.selected_account()
        if not account:
            wx.MessageBox("أضف حساب بريد أولا.", "لا يوجد حساب", wx.OK | wx.ICON_INFORMATION, self)
            page.apply_filter()
            return
        if not self.ensure_password(account):
            page.apply_filter()
            return

        page.apply_filter()
        page.set_viewer_text(tr("جار تحميل سلة المحذوفات..."))
        page.set_links([])
        self.set_transfer_progress(0, "بدء فحص سلة المحذوفات")

        def work() -> tuple[str, list[MessageSummary], str]:
            trash_mailbox = self._trash_mailboxes_by_account.get(account.id, "")
            if not trash_mailbox:
                trash_mailbox = self.service.resolve_trash_mailbox(account)
            if not trash_mailbox:
                return "", [], ""

            cached = self.service.cached_messages(account, trash_mailbox, INITIAL_MESSAGE_LIMIT)
            call_after_if_open(
                self,
                self.set_transfer_progress,
                45,
                "جار استلام رسائل سلة المحذوفات من الخادم",
            )
            try:
                messages = self.service.list_messages(account, trash_mailbox, INITIAL_MESSAGE_LIMIT, 50)
            except OAuthError:
                raise
            except (MailError, OSError, imaplib.IMAP4.error, smtplib.SMTPException) as exc:  # type: ignore[name-defined]
                if cached:
                    return trash_mailbox, cached, str(exc)
                raise
            call_after_if_open(
                self,
                self.set_transfer_progress,
                100,
                "انتهى فحص سلة المحذوفات",
            )
            return trash_mailbox, messages or cached, ""

        def done(result: tuple[str, list[MessageSummary], str]) -> None:
            if self.displayed_account_id != account.id:
                return
            trash_mailbox, messages, warning = result
            if not trash_mailbox:
                page.set_trash_messages([])
                self.reset_transfer_progress()
                self.SetStatusText("لم يتم العثور على صندوق سلة المحذوفات لهذا الحساب.")
                return
            self._trash_mailboxes_by_account[account.id] = trash_mailbox
            page.set_trash_messages(messages, trash_mailbox)
            self.set_transfer_progress(100, "اكتمل فحص سلة المحذوفات")
            if warning:
                self.SetStatusText(
                    f"تعذر تحديث سلة المحذوفات من الخادم، فتم عرض {len(messages)} رسالة محفوظة محليا. السبب: {warning}"
                )
            else:
                self.SetStatusText(f"تم عرض {len(messages)} رسالة من سلة المحذوفات.")

        self.run_worker("جار تحميل سلة المحذوفات...", work, done)

    def on_account_updated(self, _account: Account) -> None:
        save_accounts(self.accounts)

    def on_command_activated(self, _event: wx.Event) -> None:
        command = self.command_list.GetSelection()
        if command == 0:
            self.on_refresh()
        elif command == 1:
            self.on_sync_all_messages()
        elif command == 2:
            self.on_load_older()
        elif command == 3:
            self.on_account_options()
        elif command == 4:
            self.on_compose(wx.CommandEvent())
        elif command == 5:
            self.on_settings()

    def on_command_key(self, event: wx.KeyEvent) -> None:
        key_code = event.GetKeyCode()
        if key_code in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_command_activated(event)
            return
        event.Skip()

    def set_transfer_progress(self, percent: int, message: str = "") -> None:
        percent = max(0, min(100, int(percent)))
        self.transfer_progress.SetValue(percent)
        self.transfer_progress_label.SetLabel(tr(f"تقدم استلام الرسائل: {percent}%"))
        if message:
            self.SetStatusText(f"{message} ({percent}%).")

    def reset_transfer_progress(self) -> None:
        self.set_transfer_progress(0)

    @staticmethod
    def progress_percent(done_count: int, total_count: int) -> int:
        if total_count <= 0:
            return 0
        return max(0, min(100, round((done_count / total_count) * 100)))

    def on_account_options(self, _event: wx.Event | None = None) -> None:
        menu = wx.Menu()
        add_item = menu.Append(wx.ID_ANY, tr("إضافة حساب"))
        reauthenticate_item = menu.Append(wx.ID_ANY, tr("إعادة تسجيل الدخول للحساب"))
        remove_item = menu.Append(wx.ID_ANY, tr("إزالة حساب"))
        self.Bind(wx.EVT_MENU, self.on_add_account, add_item)
        self.Bind(wx.EVT_MENU, self.on_reauthenticate_account, reauthenticate_item)
        self.Bind(wx.EVT_MENU, self.on_remove_account, remove_item)
        self.command_list.PopupMenu(menu, wx.Point(0, self.command_list.GetSize().GetHeight()))
        menu.Destroy()

    def on_settings(self, _event: wx.Event | None = None) -> None:
        page = self.current_page()
        if page:
            self.settings.message_viewer = page.viewer_mode
        dialog = SettingsDialog(self, self.settings)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            self.settings = dialog.selected_settings()
            save_settings(self.settings)
            self.apply_settings()
            self.SetStatusText(tr("تم حفظ الإعدادات."))
        finally:
            dialog.Destroy()

    def apply_settings(self) -> None:
        set_language(self.settings.language)
        set_localized_items(self.command_list, self.command_labels())
        page_labels = ("الرسائل الواردة", "الرسائل غير المرغوب بها", "الرسائل المرسلة", "كل الرسائل")
        for index, label in enumerate(page_labels):
            self.notebook.SetPageText(index, tr(label))
        for page in self.pages.values():
            page.set_theme(self.settings.theme)
            page.set_viewer_mode(self.settings.message_viewer)
            page.localize_ui()
        localize_window(self)
        localize_menu_bar(self.GetMenuBar())
        apply_layout_direction(self.main_panel)
        self.apply_theme_to_window(self.main_panel)
        self.Refresh()
        self.Layout()

    def apply_theme_to_window(self, window: wx.Window) -> None:
        background, foreground, field_background = self.theme_colours()
        if not isinstance(window, wx.html2.WebView):
            try:
                window.SetBackgroundColour(field_background if self.is_field_control(window) else background)
                window.SetForegroundColour(foreground)
            except Exception:
                pass
        for child in window.GetChildren():
            self.apply_theme_to_window(child)
        try:
            window.Refresh()
        except Exception:
            pass

    def theme_colours(self) -> tuple[wx.Colour, wx.Colour, wx.Colour]:
        if self.settings.theme == THEME_DARK:
            return wx.Colour(32, 33, 36), wx.Colour(245, 245, 245), wx.Colour(43, 44, 48)
        return (
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK),
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT),
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW),
        )

    def is_field_control(self, window: wx.Window) -> bool:
        return isinstance(
            window,
            (
                wx.TextCtrl,
                wx.ListBox,
                wx.ListCtrl,
                wx.Choice,
                wx.RadioBox,
            ),
        )

    def on_add_account(self, _event: wx.Event | None = None) -> None:
        dialog = AccountDialog(self)
        self.finish_account_dialog(dialog)

    def finish_account_dialog(self, dialog: AccountDialog) -> bool:
        account_saved = False
        if dialog.ShowModal() == wx.ID_OK:
            new_account = dialog.account
            account_added = True
            for index, account in enumerate(self.accounts):
                if account.email_address.lower() == new_account.email_address.lower():
                    new_account.id = account.id
                    self.accounts[index] = new_account
                    account_added = False
                    break
            else:
                self.accounts.append(new_account)
            save_accounts(self.accounts)
            self._load_accounts_to_choice(new_account.id)
            message = "تمت إضافة الحساب بنجاح." if account_added else "تم تحديث الحساب بنجاح."
            self.show_notification(message)
            call_after_if_open(self, self.account_choice.SetFocus)
            account_saved = True
        dialog.Destroy()
        return account_saved

    def show_notification(self, message: str, timeout_ms: int = 8000) -> None:
        focus_owner = focused_control()
        if self._notification_timer and self._notification_timer.IsRunning():
            self._notification_timer.Stop()
        localized = tr(message)
        self.notification_bar.SetName(localized)
        self.notification_bar.ShowMessage(localized, wx.ICON_INFORMATION)
        self.SetStatusText(message)
        self.main_panel.Layout()
        restore_control_focus(focus_owner)
        announce_to_screen_reader(self.notification_bar, message)
        self._notification_timer = wx.CallLater(timeout_ms, self.dismiss_notification)

    def dismiss_notification(self) -> None:
        focus_owner = focused_control()
        if self.notification_bar.IsShown():
            self.notification_bar.Dismiss()
            self.main_panel.Layout()
        restore_control_focus(focus_owner)
        self._notification_timer = None

    def on_reauthenticate_account(self, _event: wx.Event | None = None) -> None:
        if self._reauthentication_active:
            self.show_notification("إعادة تسجيل الدخول قيد التنفيذ بالفعل.")
            return
        account = self.selected_account()
        if not account:
            wx.MessageBox("اختر حسابا أولا.", "لا يوجد حساب", wx.OK | wx.ICON_INFORMATION, self)
            return
        if not account.uses_oauth:
            wx.MessageBox(
                "هذا الحساب يستخدم التسجيل اليدوي، ولا يحتاج OAuth.",
                "إعادة تسجيل الدخول",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        provider_id = account.oauth_provider or "google_gmail_api"
        oauth_clients = load_oauth_clients()
        provider_client = oauth_clients.get(provider_id, {})
        client_id = provider_client.get("client_id", "") or account.oauth_client_id
        client_secret = provider_client.get("client_secret", "") or account.oauth_client_secret
        if not client_id:
            wx.MessageBox(
                "لا توجد مفاتيح OAuth لهذا الحساب داخل هذه النسخة.",
                "إعادة تسجيل الدخول غير جاهزة",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        self._reauthentication_active = True

        def work() -> object:
            return run_browser_oauth_flow(provider_id, client_id, client_secret)

        def done(result: object) -> None:
            self._reauthentication_active = False
            account.oauth_provider = result.provider_id
            account.oauth_client_id = client_id
            account.oauth_client_secret = client_secret
            account.oauth_access_token = result.access_token
            if result.refresh_token:
                account.oauth_refresh_token = result.refresh_token
            account.oauth_token_expiry = result.expires_at
            account.save_oauth_tokens = True
            account.email_address = result.email_address
            account.username = result.email_address
            account.display_name = result.display_name
            apply_provider_settings(account, result.provider_id)
            save_accounts(self.accounts)
            self.content_cache.clear()
            self.SetStatusText("تم تجديد تسجيل الدخول. جار تحديث الرسائل...")
            self.refresh_all()

        def failed(_exc: Exception) -> None:
            self._reauthentication_active = False

        self.run_worker(
            "جار انتظار تسجيل الدخول عبر المتصفح...",
            work,
            done,
            failed,
        )

    def on_remove_account(self, _event: wx.Event | None = None) -> None:
        account = self.selected_account()
        if not account:
            wx.MessageBox("اختر حسابا أولا.", "لا يوجد حساب", wx.OK | wx.ICON_INFORMATION, self)
            return

        answer = wx.MessageBox(
            (
                f"هل تريد إزالة الحساب التالي من البرنامج؟\n{account.label}\n\n"
                "لن يتم حذف حساب البريد نفسه من Google أو Microsoft، لكن ستتم إزالة بياناته المحفوظة محليا من هذا البرنامج."
            ),
            "إزالة حساب",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        )
        if answer != wx.YES:
            return

        remove_index = self.account_choice.GetSelection()
        if 0 <= remove_index < len(self.accounts) and self.accounts[remove_index].id == account.id:
            del self.accounts[remove_index]
        else:
            self.accounts = [existing for existing in self.accounts if existing.id != account.id]
        save_accounts(self.accounts)

        cache_error = ""
        try:
            self.service.delete_cached_account(account)
        except Exception as exc:
            cache_error = str(exc)

        self.content_cache.clear()
        self._known_inbox_uids.pop(account.id, None)
        if self.displayed_account_id == account.id:
            self.displayed_account_id = None
            self.current_content = None
            for page in self.pages.values():
                page.set_messages([])

        next_account_id = (
            self.accounts[
                min(max(remove_index, 0), len(self.accounts) - 1)
            ].id
            if self.accounts
            else None
        )
        self._load_accounts_to_choice(next_account_id)
        call_after_if_open(self, self.account_choice.SetFocus)
        if cache_error:
            wx.MessageBox(
                f"تمت إزالة الحساب، لكن تعذر حذف كاش الرسائل المحلي:\n{cache_error}",
                "تنبيه",
                wx.OK | wx.ICON_WARNING,
                self,
            )
        else:
            self.SetStatusText("تمت إزالة الحساب من البرنامج.")

    def on_refresh(self, _event: wx.Event | None = None) -> None:
        self.refresh_all()

    def on_account_changed(self, _event: wx.Event | None = None) -> None:
        self.refresh_all()
        self.account_choice.SetFocus()

    def refresh_all(self) -> None:
        account = self.selected_account()
        if not account:
            wx.MessageBox("أضف حساب بريد أولا.", "لا يوجد حساب", wx.OK | wx.ICON_INFORMATION, self)
            return
        if not self.ensure_password(account):
            return
        account_changed = self.displayed_account_id != account.id
        if account_changed:
            self.cancel_pending_message_load()
            self.displayed_account_id = account.id
            self.content_cache.clear()
            self.current_content = None
            for page in self.pages.values():
                page.deactivate_html_viewer()
                page.set_messages([])
                page.set_trash_messages([])

        all_mailbox = self._all_mailboxes_by_account.get(account.id, "")
        self.set_transfer_progress(0, "بدء تحديث الرسائل")

        def show_cached(
            cached_inbox: list[MessageSummary],
            cached_spam: list[MessageSummary],
            cached_sent: list[MessageSummary],
            cached_all: list[MessageSummary],
        ) -> None:
            if self.displayed_account_id != account.id:
                return
            if not (cached_inbox or cached_spam or cached_sent or cached_all):
                return
            self.pages["inbox"].merge_messages(cached_inbox)
            self.pages["spam"].merge_messages(cached_spam)
            self.pages["sent"].merge_messages(cached_sent)
            self.pages["all"].merge_messages(cached_all)
            self.SetStatusText(
                f"تم عرض الرسائل المحفوظة محليا. الوارد {len(cached_inbox)}، غير المرغوب {len(cached_spam)}، المرسلة {len(cached_sent)}، كل الرسائل {len(cached_all)}."
            )

        def work() -> tuple[
            list[MessageSummary],
            list[MessageSummary],
            list[MessageSummary],
            list[MessageSummary],
            str,
            str,
            str,
            set[str],
            dict[str, str],
        ]:
            cached_inbox = self.service.cached_messages(account, "INBOX", INITIAL_MESSAGE_LIMIT)
            cached_all = (
                self.service.cached_messages(account, all_mailbox, INITIAL_MESSAGE_LIMIT)
                if all_mailbox
                else []
            )
            cached_spam = (
                self.service.cached_messages(account, account.spam_mailbox, INITIAL_MESSAGE_LIMIT)
                if account.spam_mailbox
                else []
            )
            cached_sent = (
                self.service.cached_messages(account, account.sent_mailbox, INITIAL_MESSAGE_LIMIT)
                if account.sent_mailbox
                else []
            )
            call_after_if_open(
                self,
                show_cached,
                cached_inbox,
                cached_spam,
                cached_sent,
                cached_all,
            )

            call_after_if_open(
                self,
                self.set_transfer_progress,
                10,
                "جار استلام رسائل الوارد من الخادم",
            )
            inbox = self.service.list_messages(account, "INBOX")
            if not (all_mailbox and account.spam_mailbox and account.sent_mailbox):
                try:
                    spam_mailbox, sent_mailbox, resolved_all_mailbox = (
                        self.service.resolve_refresh_mailboxes(account)
                    )
                except MailError:
                    resolved_all_mailbox = ""
                    spam_mailbox = account.spam_mailbox
                    sent_mailbox = account.sent_mailbox
            else:
                resolved_all_mailbox = all_mailbox
                spam_mailbox = account.spam_mailbox
                sent_mailbox = account.sent_mailbox

            mailbox_jobs = {
                "all": resolved_all_mailbox
                if resolved_all_mailbox and resolved_all_mailbox.lower() != "inbox"
                else "",
                "spam": spam_mailbox,
                "sent": sent_mailbox,
            }
            mailbox_results: dict[str, list[MessageSummary]] = {
                "all": [],
                "spam": [],
                "sent": [],
            }
            failed_mailboxes: set[str] = set()

            def load_optional_mailbox(
                key: str,
                mailbox: str,
            ) -> tuple[str, list[MessageSummary], bool]:
                try:
                    return key, self.service.list_messages(account, mailbox), True
                except MailError:
                    return key, [], False

            active_jobs = [(key, mailbox) for key, mailbox in mailbox_jobs.items() if mailbox]
            call_after_if_open(
                self,
                self.set_transfer_progress,
                45,
                "جار فحص بقية أقسام الرسائل بالتوازي",
            )
            if active_jobs:
                with ThreadPoolExecutor(
                    max_workers=min(3, len(active_jobs)),
                    thread_name_prefix="mailbox-refresh",
                ) as executor:
                    futures = {
                        key: executor.submit(load_optional_mailbox, key, mailbox)
                        for key, mailbox in active_jobs
                    }
                    for key, future in futures.items():
                        result_key, messages, succeeded = future.result()
                        mailbox_results[result_key] = messages
                        if not succeeded:
                            failed_mailboxes.add(key)

            all_messages = mailbox_results["all"]
            spam = mailbox_results["spam"]
            sent = mailbox_results["sent"]
            if "all" in failed_mailboxes:
                resolved_all_mailbox = ""
            if "spam" in failed_mailboxes:
                spam_mailbox = ""
            if "sent" in failed_mailboxes:
                sent_mailbox = ""
            call_after_if_open(
                self,
                self.set_transfer_progress,
                100,
                "انتهى استلام أحدث الرسائل",
            )
            return (
                inbox,
                spam,
                sent,
                all_messages,
                spam_mailbox,
                sent_mailbox,
                resolved_all_mailbox,
                failed_mailboxes,
                mailbox_jobs,
            )

        def done(result: tuple[
            list[MessageSummary],
            list[MessageSummary],
            list[MessageSummary],
            list[MessageSummary],
            str,
            str,
            str,
            set[str],
            dict[str, str],
        ]) -> None:
            if self.displayed_account_id != account.id:
                return
            (
                inbox,
                spam,
                sent,
                all_messages,
                spam_mailbox,
                sent_mailbox,
                all_mailbox,
                failed_mailboxes,
                mailbox_jobs,
            ) = result
            new_inbox_count = self.new_inbox_count(account, inbox, account_changed)
            self.pages["inbox"].reconcile_recent_messages(inbox)
            if mailbox_jobs["spam"] and "spam" not in failed_mailboxes:
                self.pages["spam"].reconcile_recent_messages(spam)
            if mailbox_jobs["sent"] and "sent" not in failed_mailboxes:
                self.pages["sent"].reconcile_recent_messages(sent)
            if mailbox_jobs["all"] and "all" not in failed_mailboxes:
                self.pages["all"].reconcile_recent_messages(all_messages)
            self.remember_inbox_messages(account, self.pages["inbox"].messages)
            inbox_count = len(self.pages["inbox"].messages)
            spam_count = len(self.pages["spam"].messages)
            sent_count = len(self.pages["sent"].messages)
            all_count = len(self.pages["all"].messages)
            details = []
            if spam_mailbox:
                details.append(f"مجلد غير مرغوب: {spam_mailbox}")
            if sent_mailbox:
                details.append(f"مجلد المرسلة: {sent_mailbox}")
            if all_mailbox:
                self._all_mailboxes_by_account[account.id] = all_mailbox
                details.append(f"كل البريد: {all_mailbox}")
            detail = "، " + "، ".join(details) if details else ""
            self.SetStatusText(f"تم تحديث الرسائل. الوارد {inbox_count}، غير المرغوب {spam_count}، المرسلة {sent_count}، كل الرسائل {all_count}{detail}.")
            if new_inbox_count:
                self.notify_new_mail(new_inbox_count)

        self.run_worker("جار تحديث الرسائل...", work, done)

    def on_load_older(self, _event: wx.Event | None = None) -> None:
        account = self.selected_account()
        page = self.current_page()
        if not account or not page:
            wx.MessageBox("اختر حسابا وقسم رسائل أولا.", "لا يوجد قسم", wx.OK | wx.ICON_INFORMATION, self)
            return
        if not self.ensure_password(account):
            return

        page_key = self.page_key_for_page(page)
        mailbox = self.mailbox_for_page_key(account, page_key)
        self.set_transfer_progress(0, "بدء تحميل رسائل أقدم")

        def work() -> tuple[str, list[MessageSummary], str]:
            resolved_mailbox = mailbox or self.resolve_mailbox_for_page_key(account, page_key)
            if not resolved_mailbox:
                return page_key, [], ""
            call_after_if_open(
                self,
                self.set_transfer_progress,
                35,
                "جار طلب دفعة أقدم من الخادم",
            )
            messages = self.service.load_older_messages(account, resolved_mailbox)
            call_after_if_open(
                self,
                self.set_transfer_progress,
                100,
                "انتهى تحميل الدفعة",
            )
            return page_key, messages, resolved_mailbox

        def done(result: tuple[str, list[MessageSummary], str]) -> None:
            if self.displayed_account_id != account.id:
                return
            result_page_key, messages, resolved_mailbox = result
            target_page = self.pages[result_page_key]
            before_count = len(target_page.messages)
            target_page.merge_messages(messages)
            after_count = len(target_page.messages)
            added_count = max(0, after_count - before_count)
            if not resolved_mailbox:
                self.reset_transfer_progress()
                self.SetStatusText("لا يوجد مجلد مناسب لتحميل رسائل أقدم.")
            elif added_count:
                self.set_transfer_progress(100, "اكتمل تحميل رسائل أقدم")
                self.SetStatusText(f"تم تحميل {added_count} رسالة أقدم. العدد المعروض الآن {after_count}.")
            else:
                self.set_transfer_progress(100, "اكتمل تحميل رسائل أقدم")
                self.SetStatusText("لا توجد رسائل أقدم جديدة في هذا القسم.")

        self.run_worker("جار تحميل رسائل أقدم...", work, done)

    def on_sync_all_messages(self, _event: wx.Event | None = None) -> None:
        account = self.selected_account()
        page = self.current_page()
        if not account or not page:
            wx.MessageBox("اختر حسابا وقسم رسائل أولا.", "لا يوجد قسم", wx.OK | wx.ICON_INFORMATION, self)
            return
        if not self.ensure_password(account):
            return

        page_key = self.page_key_for_page(page)
        if page_key in self._syncing_page_keys:
            self.SetStatusText("المزامنة الكاملة تعمل بالفعل لهذا القسم.")
            return

        mailbox = self.mailbox_for_page_key(account, page_key)
        self._syncing_page_keys.add(page_key)
        self.set_transfer_progress(0, "بدء مزامنة كل الرسائل")

        def progress(
            summaries: list[MessageSummary],
            added_count: int,
            total_added: int,
            cached_count: int,
            total_count: int,
        ) -> None:
            def update() -> None:
                if self.displayed_account_id != account.id:
                    return
                target_page = self.pages[page_key]
                before_count = len(target_page.messages)
                target_page.merge_messages(summaries)
                after_count = len(target_page.messages)
                shown_added = max(added_count, after_count - before_count)
                percent = self.progress_percent(cached_count, total_count)
                self.set_transfer_progress(
                    percent,
                    f"مزامنة {target_page.title}: تم استلام {cached_count} من {total_count} رسالة",
                )
                if shown_added:
                    self.SetStatusText(
                        f"تم تحميل {total_added} رسالة حتى الآن. العدد المحفوظ {cached_count}. النسبة {percent}%."
                    )
                else:
                    self.SetStatusText(
                        f"جار المزامنة... العدد المحفوظ {cached_count}. النسبة {percent}%."
                    )

            call_after_if_open(self, update)

        def work() -> tuple[str, MailSyncResult, str]:
            try:
                resolved_mailbox = mailbox or self.resolve_mailbox_for_page_key(account, page_key)
                if not resolved_mailbox:
                    return page_key, MailSyncResult("", [], 0, 0), ""
                result = self.service.sync_all_older_messages(
                    account,
                    resolved_mailbox,
                    batch_size=50,
                    on_progress=progress,
                )
                return page_key, result, resolved_mailbox
            finally:
                call_after_if_open(self, self._syncing_page_keys.discard, page_key)

        def done(result: tuple[str, MailSyncResult, str]) -> None:
            if self.displayed_account_id != account.id:
                return
            result_page_key, sync_result, resolved_mailbox = result
            target_page = self.pages[result_page_key]
            if sync_result.messages:
                target_page.merge_messages(sync_result.messages)
            if not resolved_mailbox:
                self.reset_transfer_progress()
                self.SetStatusText("لا يوجد مجلد مناسب لمزامنة الرسائل.")
            elif sync_result.added_count:
                self.set_transfer_progress(100, "اكتملت مزامنة كل الرسائل")
                self.SetStatusText(
                    f"اكتملت المزامنة. تم تحميل {sync_result.added_count} رسالة. العدد المحفوظ {sync_result.cached_count}."
                )
            else:
                self.set_transfer_progress(100, "اكتملت مزامنة كل الرسائل")
                self.SetStatusText(
                    f"اكتملت المزامنة. لا توجد رسائل أقدم جديدة. العدد المحفوظ {sync_result.cached_count}."
                )

        self.run_worker("جار مزامنة كل الرسائل...", work, done)

    def on_message_selected(self, page: MailPage, summary: MessageSummary) -> None:
        account = self.selected_account()
        if not account:
            return
        self.current_content = None
        self._message_load_generation += 1
        generation = self._message_load_generation
        if self._message_load_call and self._message_load_call.IsRunning():
            self._message_load_call.Stop()
        self._message_load_call = None
        cache_key = (account.id, summary.mailbox, summary.uid)
        content = self.content_cache.get(cache_key)
        if content:
            self.content_cache.move_to_end(cache_key)
            if not (
                summary.has_attachments
                and not any(item.is_attachment for item in content.links)
            ):
                content.summary.is_read = summary.is_read
                page.show_content(content)
                self.current_content = content
                return
            self.content_cache.pop(cache_key, None)

        self._message_load_call = wx.CallLater(
            MESSAGE_SELECTION_DELAY_MS,
            self.start_message_load,
            page,
            account,
            summary,
            cache_key,
            generation,
        )

    def start_message_load(
        self,
        page: MailPage,
        account: Account,
        summary: MessageSummary,
        cache_key: tuple[str, str, str],
        generation: int,
    ) -> None:
        self._message_load_call = None
        if not self.message_load_is_current(page, account, summary, generation):
            return
        page.begin_message_load()

        def work() -> MessageContent:
            return self.service.fetch_message(account, summary, mark_read=False)

        def done(content: MessageContent) -> None:
            self.remember_message_content(cache_key, content)
            if not self.message_load_is_current(page, account, summary, generation):
                return
            self.current_content = content
            page.show_content(content)
            self.SetStatusText("تم تحميل الرسالة.")

        def failed(exc: Exception) -> None:
            if not self.message_load_is_current(page, account, summary, generation):
                return
            if isinstance(exc, OAuthReauthenticationRequired):
                message = (
                    "تعذر تحميل محتوى الرسالة لأن صلاحية تسجيل الدخول انتهت. "
                    "أعد تسجيل الدخول للحساب ثم اختر الرسالة مرة أخرى."
                )
            else:
                message = "تعذر تحميل محتوى الرسالة. اختر الرسالة مرة أخرى بعد التحقق من الاتصال."
            page.set_links([])
            page.current_content_key = None
            page.set_viewer_text(tr(message))

        self.run_worker("جار تحميل الرسالة...", work, done, failed)

    def message_load_is_current(
        self,
        page: MailPage,
        account: Account,
        summary: MessageSummary,
        generation: int,
    ) -> bool:
        if generation != self._message_load_generation or self.displayed_account_id != account.id:
            return False
        selected = page.selected_summary()
        return bool(selected and page.message_key(selected) == page.message_key(summary))

    def cancel_pending_message_load(self) -> None:
        self._message_load_generation += 1
        if self._message_load_call and self._message_load_call.IsRunning():
            self._message_load_call.Stop()
        self._message_load_call = None

    def remember_message_content(
        self,
        cache_key: tuple[str, str, str],
        content: MessageContent,
    ) -> None:
        self.content_cache[cache_key] = content
        self.content_cache.move_to_end(cache_key)
        while len(self.content_cache) > MAX_MEMORY_MESSAGE_CONTENTS:
            self.content_cache.popitem(last=False)

    def on_toggle_message_read(self, page: MailPage, summary: MessageSummary) -> None:
        account = self.selected_account()
        if not account:
            return
        old_state = summary.is_read
        new_state = not old_state

        def update_local_state(is_read: bool) -> None:
            summary.is_read = is_read
            cache_key = (account.id, summary.mailbox, summary.uid)
            cached = self.content_cache.get(cache_key)
            if cached:
                cached.summary.is_read = is_read
            if self.current_content and self.current_content.summary.uid == summary.uid:
                self.current_content.summary.is_read = is_read
            page.update_message_read_state(summary, is_read)
            self.sync_gmail_message_flags(account, summary, source_page=page)

        update_local_state(new_state)

        def work() -> bool:
            self.service.set_message_read(account, summary, new_state)
            return new_state

        def done(is_read: bool) -> None:
            if self.displayed_account_id != account.id:
                return
            state_label = "مقروءة" if is_read else "غير مقروءة"
            self.SetStatusText(f"تم حفظ حالة الرسالة كـ {state_label}.")

        def failed(_exc: Exception) -> None:
            if self.displayed_account_id != account.id or summary.is_read != new_state:
                return
            update_local_state(old_state)

        self.run_worker("جار حفظ حالة الرسالة...", work, done, failed)
        state_label = "مقروءة" if new_state else "غير مقروءة"
        self.SetStatusText(f"تم تغيير الحالة فوراً إلى {state_label}، جار الحفظ في الخادم.")

    def on_toggle_star_current_message(self, page: MailPage) -> None:
        account = self.selected_account()
        summary = page.selected_summary()
        if not account or not summary:
            return
        new_state = not summary.is_starred

        def work() -> bool:
            self.service.set_message_starred(account, summary, new_state)
            return new_state

        def done(is_starred: bool) -> None:
            summary.is_starred = is_starred
            self.update_cached_summary_flags(account, summary)
            page.update_message_flags(summary)
            self.sync_gmail_message_flags(account, summary, source_page=page)
            state = "تم تمييز الرسالة بنجمة." if is_starred else "تمت إزالة النجمة من الرسالة."
            self.SetStatusText(state)

        self.run_worker("جار تحديث تمييز الرسالة...", work, done)

    def on_toggle_pin_current_message(self, page: MailPage) -> None:
        account = self.selected_account()
        summary = page.selected_summary()
        if not account or not summary:
            return
        old_state = summary.is_pinned
        new_state = not summary.is_pinned

        def update_local_state(is_pinned: bool) -> None:
            summary.is_pinned = is_pinned
            self.update_cached_summary_flags(account, summary)
            page.update_message_flags(summary)
            self.sync_gmail_message_flags(account, summary, source_page=page)
            page.focus_list_index(0)

        update_local_state(new_state)

        def work() -> bool:
            self.service.set_message_pinned(account, summary, new_state)
            return new_state

        def done(is_pinned: bool) -> None:
            state = "تم تثبيت الرسالة في الأعلى." if is_pinned else "تم إلغاء تثبيت الرسالة."
            self.SetStatusText(state)

        def failed(_exc: Exception) -> None:
            if self.displayed_account_id != account.id or summary.is_pinned != new_state:
                return
            update_local_state(old_state)

        self.run_worker("جار تحديث تثبيت الرسالة...", work, done, failed)

    def on_delete_current_message(self, page: MailPage) -> None:
        account = self.selected_account()
        summary = page.selected_summary()
        if not account or not summary:
            return
        deleted_index = max(0, page.list.GetFirstSelected())
        if page.selected_filter_key() == "trash":
            wx.MessageBox(
                "هذه الرسالة موجودة بالفعل في سلة المحذوفات.",
                "سلة المحذوفات",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        if (
            wx.MessageBox(
                "هل تريد حذف الرسالة ونقلها إلى سلة المحذوفات؟",
                "تأكيد الحذف",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                self,
            )
            != wx.YES
        ):
            return

        def work() -> None:
            self.service.move_message_to_trash(account, summary)

        def done(_result: None) -> None:
            for cache_key in list(self.content_cache):
                if cache_key[0] == account.id and cache_key[2] == summary.uid:
                    self.content_cache.pop(cache_key, None)
            if self.current_content and self.current_content.summary.uid == summary.uid:
                self.current_content = None
            if account.oauth_provider == "google_gmail_api":
                for target_page in self.pages.values():
                    target_page.remove_message_by_uid(summary.uid)
            else:
                page.remove_message(summary)
            page.focus_list_index(page.previous_message_index(deleted_index))
            self.SetStatusText("تم نقل الرسالة إلى سلة المحذوفات.")

        self.run_worker("جار نقل الرسالة إلى سلة المحذوفات...", work, done)

    def on_bulk_message_action(
        self,
        page: MailPage,
        action: str,
        summaries: list[MessageSummary],
    ) -> None:
        account = self.selected_account()
        unique_summaries = list(
            {
                page.message_key(summary): summary
                for summary in summaries
            }.values()
        )
        if not account or not unique_summaries:
            page.announce_selection_count()
            return
        if action == BULK_ACTION_DELETE:
            self.on_delete_selected_messages(page, unique_summaries)
            return

        action_settings: dict[str, tuple[str, bool, str, str]] = {
            BULK_ACTION_MARK_READ: (
                "read",
                True,
                f"جار تعليم {len(unique_summaries)} رسالة كمقروءة...",
                f"تم تعليم {len(unique_summaries)} رسالة كمقروءة.",
            ),
            BULK_ACTION_MARK_UNREAD: (
                "read",
                False,
                f"جار تعليم {len(unique_summaries)} رسالة كغير مقروءة...",
                f"تم تعليم {len(unique_summaries)} رسالة كغير مقروءة.",
            ),
            BULK_ACTION_STAR: (
                "starred",
                True,
                f"جار تمييز {len(unique_summaries)} رسالة بنجمة...",
                f"تم تمييز {len(unique_summaries)} رسالة بنجمة.",
            ),
            BULK_ACTION_UNSTAR: (
                "starred",
                False,
                f"جار إزالة النجمة من {len(unique_summaries)} رسالة...",
                f"تمت إزالة النجمة من {len(unique_summaries)} رسالة.",
            ),
            BULK_ACTION_PIN: (
                "pinned",
                True,
                f"جار تثبيت {len(unique_summaries)} رسالة في الأعلى...",
                f"تم تثبيت {len(unique_summaries)} رسالة في الأعلى.",
            ),
            BULK_ACTION_UNPIN: (
                "pinned",
                False,
                f"جار إلغاء تثبيت {len(unique_summaries)} رسالة...",
                f"تم إلغاء تثبيت {len(unique_summaries)} رسالة.",
            ),
        }
        settings = action_settings.get(action)
        if not settings:
            return
        flag_name, target_state, progress_message, success_message = settings
        old_states = {
            page.message_key(summary): (
                summary.is_read,
                summary.is_starred,
                summary.is_pinned,
            )
            for summary in unique_summaries
        }

        def operation(summary: MessageSummary) -> None:
            if flag_name == "read":
                self.service.set_message_read(account, summary, target_state)
            elif flag_name == "starred":
                self.service.set_message_starred(account, summary, target_state)
            else:
                self.service.set_message_pinned(account, summary, target_state)

        def work() -> tuple[
            list[MessageSummary],
            list[tuple[MessageSummary, Exception]],
        ]:
            return run_bulk_operations(unique_summaries, operation)

        def done(
            result: tuple[
                list[MessageSummary],
                list[tuple[MessageSummary, Exception]],
            ],
        ) -> None:
            succeeded, failed = result
            for summary, _exc in failed:
                old_read, old_starred, old_pinned = old_states[
                    page.message_key(summary)
                ]
                summary.is_read = old_read
                summary.is_starred = old_starred
                summary.is_pinned = old_pinned
            for summary in succeeded:
                self.update_cached_summary_flags(account, summary)

            match_uid = account.oauth_provider == "google_gmail_api"
            target_pages = self.pages.values() if match_uid else (page,)
            for target_page in target_pages:
                target_page.update_message_flags_bulk(
                    unique_summaries,
                    match_uid=match_uid,
                )
            if succeeded:
                self.SetStatusText(
                    success_message
                    if not failed
                    else (
                        f"اكتمل الإجراء على {len(succeeded)} رسالة وتعذر تطبيقه "
                        f"على {len(failed)} رسالة."
                    )
                )
            if failed:
                wx.MessageBox(
                    f"تعذر تطبيق الإجراء على {len(failed)} رسالة. بقيت هذه الرسائل محددة للمحاولة مرة أخرى.",
                    "تعذر إكمال الإجراء",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            page.focus_message_list()

        self.run_worker(progress_message, work, done)

    def on_delete_selected_messages(
        self,
        page: MailPage,
        summaries: list[MessageSummary],
    ) -> None:
        account = self.selected_account()
        if not account or not summaries:
            return
        if page.selected_filter_key() == "trash":
            wx.MessageBox(
                "الرسائل المحددة موجودة بالفعل في سلة المحذوفات.",
                "سلة المحذوفات",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        dialog = BulkDeleteDialog(self, len(summaries))
        try:
            if dialog.ShowModal() != wx.ID_OK:
                call_after_if_open(self, page.focus_message_list)
                return
        finally:
            dialog.Destroy()

        selected_indices = page.selected_indices()
        first_deleted_index = min(selected_indices) if selected_indices else 0

        def operation(summary: MessageSummary) -> None:
            self.service.move_message_to_trash(account, summary)

        def work() -> tuple[
            list[MessageSummary],
            list[tuple[MessageSummary, Exception]],
        ]:
            return run_bulk_operations(summaries, operation)

        def done(
            result: tuple[
                list[MessageSummary],
                list[tuple[MessageSummary, Exception]],
            ],
        ) -> None:
            succeeded, failed = result
            if not succeeded:
                wx.MessageBox(
                    f"تعذر نقل {len(failed)} رسالة إلى سلة المحذوفات. لم تُحذف أي رسالة من القائمة.",
                    "تعذر حذف الرسائل",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
                page.focus_message_list()
                return

            deleted_uids = {summary.uid for summary in succeeded}
            for cache_key in list(self.content_cache):
                if cache_key[0] == account.id and cache_key[2] in deleted_uids:
                    self.content_cache.pop(cache_key, None)
            if (
                self.current_content
                and self.current_content.summary.uid in deleted_uids
            ):
                self.current_content = None

            match_uid = account.oauth_provider == "google_gmail_api"
            target_pages = self.pages.values() if match_uid else (page,)
            for target_page in target_pages:
                target_page.remove_messages_bulk(
                    succeeded,
                    match_uid=match_uid,
                )

            page.exit_multi_selection_mode(restore_single_selection=False)
            page.focus_list_index(
                page.previous_message_index(first_deleted_index)
            )
            if failed:
                self.SetStatusText(
                    f"تم نقل {len(succeeded)} رسالة إلى سلة المحذوفات وتعذر نقل {len(failed)} رسالة."
                )
                wx.MessageBox(
                    f"تم حذف {len(succeeded)} رسالة، وتعذر حذف {len(failed)} رسالة.",
                    "اكتمل الحذف جزئيا",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
            else:
                self.SetStatusText(
                    f"تم نقل {len(succeeded)} رسالة إلى سلة المحذوفات."
                )

        self.run_worker(
            f"جار نقل {len(summaries)} رسالة إلى سلة المحذوفات...",
            work,
            done,
        )

    def update_cached_summary_flags(self, account: Account, summary: MessageSummary) -> None:
        matching_keys = [
            key
            for key in self.content_cache
            if key[0] == account.id
            and key[2] == summary.uid
            and (account.oauth_provider == "google_gmail_api" or key[1] == summary.mailbox)
        ]
        for cache_key in matching_keys:
            cached = self.content_cache.get(cache_key)
            if cached:
                cached.summary.is_read = summary.is_read
                cached.summary.is_starred = summary.is_starred
                cached.summary.is_pinned = summary.is_pinned
        if self.current_content and self.current_content.summary.uid == summary.uid:
            self.current_content.summary.is_read = summary.is_read
            self.current_content.summary.is_starred = summary.is_starred
            self.current_content.summary.is_pinned = summary.is_pinned

    def sync_gmail_message_flags(
        self,
        account: Account,
        summary: MessageSummary,
        source_page: MailPage | None = None,
    ) -> None:
        if account.oauth_provider != "google_gmail_api":
            return
        for target_page in self.pages.values():
            if target_page is source_page:
                continue
            target_page.update_message_flags_by_uid(summary)

    def on_compose(self, _event: wx.Event) -> None:
        account = self.selected_account()
        if not account:
            wx.MessageBox("أضف حساب بريد أولا.", "لا يوجد حساب", wx.OK | wx.ICON_INFORMATION, self)
            return
        if not self.ensure_password(account):
            return
        dialog = ComposeDialog(self)
        if dialog.ShowModal() == wx.ID_OK:
            to_address, subject, body, attachments = dialog.values()
            self.send_message(
                account,
                to_address,
                subject,
                body,
                None,
                attachments,
            )
        dialog.Destroy()

    def on_reply(self, _event: wx.Event | None = None) -> None:
        account = self.selected_account()
        page = self.current_page()
        summary = page.selected_summary() if page else None
        if not account or not summary:
            wx.MessageBox("اختر رسالة للرد عليها.", "لا توجد رسالة", wx.OK | wx.ICON_INFORMATION, self)
            return
        subject = summary.display_subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        quoted = ""
        if self.current_content and self.current_content.summary.uid == summary.uid:
            quoted = "\n\n----- الرسالة الأصلية -----\n" + self.current_content.text
        dialog = ComposeDialog(
            self,
            title="رد على رسالة",
            to_address=summary.sender_email,
            subject=subject,
            body=quoted,
        )
        if dialog.ShowModal() == wx.ID_OK:
            to_address, new_subject, body, attachments = dialog.values()
            self.send_message(
                account,
                to_address,
                new_subject,
                body,
                summary,
                attachments,
            )
        dialog.Destroy()

    def send_message(
        self,
        account: Account,
        to_address: str,
        subject: str,
        body: str,
        reply_to: MessageSummary | None,
        attachments: list[Path] | None = None,
    ) -> None:
        if not self.ensure_password(account):
            return

        def work() -> None:
            self.service.send_message(
                account,
                to_address,
                subject,
                body,
                reply_to,
                attachments or [],
            )

        def done(_result: None) -> None:
            self.SetStatusText("تم إرسال الرسالة.")
            wx.MessageBox("تم إرسال الرسالة بنجاح.", "تم الإرسال", wx.OK | wx.ICON_INFORMATION, self)
            self.refresh_all()

        self.run_worker("جار إرسال الرسالة...", work, done)

    def on_translate_current_message(self, _event: wx.Event | MailPage | None = None) -> None:
        page = self.current_page()
        summary = page.selected_summary() if page else None
        if not isinstance(_event, MailPage) and not self.can_translate_current_message(page):
            self.SetStatusText("الترجمة متاحة فقط أثناء وجود التركيز داخل مستعرض الرسالة.")
            return
        text = ""
        if self.current_content and summary and self.current_content.summary.uid == summary.uid:
            text = self.current_content.text
        elif page:
            text = page.viewer.GetValue()
        text = text.strip()
        if not text or text == tr("جار تحميل الرسالة..."):
            wx.MessageBox("اختر رسالة وانتظر تحميل نصها أولا.", "لا توجد رسالة للترجمة", wx.OK | wx.ICON_INFORMATION, self)
            return
        source_uid = summary.uid if summary else ""
        return_control = page.take_translation_return_control() if isinstance(_event, MailPage) else wx.Window.FindFocus()

        def work() -> str:
            return translate_text_with_google(text, target_language=self.settings.language)

        def done(translated: str) -> None:
            if self.settings.translation_mode == TRANSLATION_INLINE and page:
                current_summary = page.selected_summary()
                if not current_summary or current_summary.uid != source_uid:
                    self.SetStatusText("اكتملت ترجمة الرسالة السابقة دون تغيير الرسالة الحالية.")
                    return
                page.set_viewer_action_ranges(translated, [])
                page.set_viewer_text(normalize_message_text(translated))
                self.SetStatusText("تمت ترجمة الرسالة داخل المستعرض.")
                return
            self.show_translation_dialog(translated)
            if page:
                call_after_if_open(self, page.restore_context_focus, return_control)

        def failed(_exc: Exception) -> None:
            if page:
                call_after_if_open(self, page.restore_context_focus, return_control)

        self.run_worker("جار ترجمة الرسالة...", work, done, failed)
        if page:
            call_after_if_open(self, page.restore_context_focus, return_control)

    def can_translate_current_message(self, page: MailPage | None = None) -> bool:
        page = page or self.current_page()
        if not page or not page.selected_summary():
            return False
        focus = wx.Window.FindFocus()
        return focus in {page.viewer, page.html_viewer}

    def show_translation_dialog(self, translated_text: str) -> None:
        dialog = wx.Dialog(self, title="ترجمة الرسالة", size=(760, 620))
        root = wx.BoxSizer(wx.VERTICAL)
        viewer = wx.TextCtrl(
            dialog,
            value=translated_text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
        )
        set_accessible(viewer, "مستعرض نص الترجمة")
        root.Add(viewer, 1, wx.EXPAND | wx.ALL, 8)
        close_button = wx.Button(dialog, wx.ID_CLOSE, "إغلاق")
        set_accessible(close_button, "إغلاق نافذة الترجمة")
        close_button.Bind(wx.EVT_BUTTON, lambda _event: dialog.EndModal(wx.ID_CLOSE))
        root.Add(close_button, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        dialog.SetSizer(root)
        localize_window(dialog)
        viewer.SetFocus()
        dialog.ShowModal()
        dialog.Destroy()

    def on_show_guide(self, _event: wx.Event) -> None:
        dialog = wx.Dialog(self, title="دليل Power Accessible Mail", size=(760, 620))
        root = wx.BoxSizer(wx.VERTICAL)
        guide = wx.TextCtrl(
            dialog,
            value=self.program_guide_text(),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
        )
        set_accessible(guide, "نص دليل البرنامج")
        root.Add(guide, 1, wx.EXPAND | wx.ALL, 10)
        buttons = dialog.CreateSeparatedButtonSizer(wx.OK)
        if buttons:
            root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        dialog.SetSizer(root)
        localize_window(dialog)
        dialog.CentreOnParent()
        call_after_if_open(self, guide.SetFocus)
        dialog.ShowModal()
        dialog.Destroy()

    def program_guide_text(self) -> str:
        try:
            return load_program_guide(self.settings.language, APP_VERSION)
        except OSError:
            pass
        if self.settings.language == LANGUAGE_FRENCH:
            from .guide_fr import french_program_guide

            return french_program_guide(APP_VERSION)
        if self.settings.language == LANGUAGE_ENGLISH:
            return f"""Power Accessible Mail
Version: {APP_VERSION}
Developed by Soljan.AlSharq.
Soljan.AlSharq. is owned by Ali Al-Amir

Welcome to your email
Power Accessible Mail is built to make reading, writing, organizing, and updating email comfortable from the keyboard. Native Windows lists and fields give screen readers predictable controls, while messages are arranged vertically so moving through your mail feels direct and familiar.

Add your account in the way that suits you
When the application starts without an account, you can continue with Google, continue with Microsoft, sign in manually, or open the main interface without adding an account.

From Account options and management, choose Add account. The sign-in methods appear as a real list. Select browser sign-in or manual sign-in, then press Enter, right-click the selected item, or use the OK button beside Cancel.

Browser sign-in opens the official Google or Microsoft consent page and never asks the application to read your browser password. Manual sign-in begins with an Email service choice. Select Google or Microsoft and the application fills the matching IMAP and SMTP settings while keeping the fields available for review. Gmail manual sign-in normally requires an app password. For Microsoft, browser sign-in is the recommended method because password-based IMAP access may be restricted by the account policy.

Your mail sections
Inbox reads the real Inbox folder. Spam reads Spam or Junk. Sent holds the messages you sent. All Mail opens Gmail All Mail when it is available, which can reveal recent messages that do not carry the Inbox label.

Inside each section, the filter lets you show all messages, starred messages, unread messages, read messages, or the real Trash folder. Press F5 whenever you want the newest messages. Synchronize all messages retrieves older mail in batches, and Load older messages adds one older batch from the current section.

Read each message in the viewer you prefer
The HTML viewer keeps links and buttons in their natural positions as real page elements. Use Tab or your screen reader's browsing commands to reach them, then press Enter or Space to activate them. Press Ctrl+Enter to move between the message viewer and the item viewer. Press Escape to return directly to the message list.

The easy viewer removes repeated blank lines and presents a clean text version. Its item viewer collects links, buttons, images, and attachments under clear names. Selecting a message does not mark it as read automatically; press Space in the normal message list to switch the focused message between read and unread.

Work with several messages at once
In normal mode, messages are list items without check boxes. Press Ctrl+Shift+Space to enter multiple-selection mode, where every message becomes a check box. Move with the arrow keys and press Space to check or uncheck a message, or use the mouse.

The application announces entry into or exit from this mode after 150 milliseconds. Press Control by itself to hear the selected count after the same delay. Press Escape or Ctrl+Shift+Space again to leave the mode. Trying to move above the first item or below the last item announces the boundary. The context menu provides suitable bulk read, star, pin, and Trash commands. Delete asks for confirmation and states the number of affected messages.

Write and act without leaving the keyboard
Compose email opens a complete message window. Reply, Star, Translate, Pin to top, and move to the provider's Trash are available from the message context menu. The item viewer list has no context menu, while the Item actions button displays attachment, image, and link commands directly without a submenu.

Translation when you need it
Ctrl+T translates the current message into the application language. In Settings, choose whether the translation replaces the content inside the HTML or easy viewer, or opens in a separate window. Translation becomes available only while you are inside the message viewer. It requires an internet connection and sends the selected message text to Google Translate only when you request it.

Make the application yours
Settings lets you choose Arabic, English, or French, the HTML or easy message viewer, translation inside the page or in a separate window, and light or dark appearance. Your choices are saved for the next launch.

Updates without opening a browser
The application checks GitHub Releases after startup, and you can check manually from Help, Check for updates. When a release is available, Update now opens an internal progress window showing its version, release date, progress bar, and percentage. The correct installer is downloaded, its SHA-256 digest is verified, and the direct update starts before the application restarts.

Useful keyboard commands
Ctrl+A opens account options and management.
Ctrl+N composes a new message.
Ctrl+R replies to the focused message.
Ctrl+T translates the current message.
F5 refreshes messages.
F1 opens this guide.
Escape returns to the message list from the message or item viewer.
Ctrl+Enter switches between message and item viewers.
Shift+F10 opens the context and actions menu.
Alt+F4 closes the application.

Your privacy stays part of the design
OAuth access begins only after your approval on the provider's official page. Locally cached messages, tokens, and saved credentials are protected by Windows DPAPI for the current Windows account. Distribution packages do not contain user accounts or messages. Removing an account from the application also removes its locally stored application data.

Power Accessible Mail
An accessible email experience developed by Soljan.AlSharq.
"""
        return f"""Power Accessible Mail
الإصدار: {APP_VERSION}
تطوير صولجان الشرق
شركة صولجان الشرق تابعة للمالك علي الأمير

مرحبا بك في بريدك
Power Accessible Mail برنامج صمم ليجعل قراءة البريد وكتابته وتنظيمه وتحديثه تجربة مريحة من لوحة المفاتيح. يعتمد على قوائم وحقول Windows الأصلية حتى يجد قارئ الشاشة عناصر واضحة ومتوقعة، ويرتب الرسائل عموديا لتتنقل بينها بالسهم للأعلى والأسفل من دون تعقيد.

أضف حسابك بالطريقة التي تناسبك
عندما يفتح البرنامج من دون حساب تستطيع المتابعة مع Google أو Microsoft أو التسجيل يدويا أو دخول الواجهة الرئيسية من دون إضافة حساب.

من خيارات الحسابات وإدارتها اختر إضافة حساب. تظهر طريقتا التسجيل داخل قائمة حقيقية. حدد التسجيل عبر المتصفح أو التسجيل اليدوي ثم اضغط Enter أو انقر على العنصر بالنقر الأيمن أو استخدم زر موافق الموجود بجوار إلغاء.

التسجيل عبر المتصفح يفتح صفحة Google أو Microsoft الرسمية ولا يطلب من البرنامج قراءة كلمة مرور المتصفح. أما التسجيل اليدوي فيبدأ بصندوق خدمة البريد. اختر Google أو Microsoft ليملأ البرنامج إعدادات IMAP وSMTP المناسبة، وتبقى الحقول أمامك للمراجعة. يحتاج Gmail عادة إلى كلمة مرور تطبيق عند التسجيل اليدوي، وينصح باستخدام التسجيل عبر المتصفح مع Microsoft لأن سياسة الحساب قد تمنع الدخول التقليدي بكلمة المرور.

أقسام بريدك أمامك
الرسائل الواردة تقرأ صندوق الوارد الحقيقي. الرسائل غير المرغوب بها تقرأ Spam أو Junk. الرسائل المرسلة تعرض ما أرسلته. قسم كل الرسائل يفتح صندوق كل البريد في Gmail عند توفره، وهو مفيد للرسائل الحديثة التي لا تحمل تصنيف الوارد.

داخل كل قسم تستطيع عرض جميع الرسائل أو المميزة بنجمة أو غير المقروءة أو المقروءة أو الرسائل الموجودة فعليا في سلة المحذوفات. اضغط F5 متى أردت جلب الأحدث. مزامنة كل الرسائل تجلب البريد القديم على دفعات، وتحميل رسائل أقدم يضيف دفعة واحدة إلى القسم الحالي.

اقرأ الرسالة بالمستعرض الذي يناسبك
مستعرض HTML يبقي الروابط والأزرار في مواضعها الطبيعية كعناصر حقيقية. استخدم Tab أو أوامر التصفح في قارئ الشاشة للوصول إليها ثم Enter أو Space لتفعيلها. ينقلك Ctrl+Enter بين مستعرض الرسالة ومستعرض العناصر، ويعيدك Escape مباشرة إلى قائمة الرسائل.

المستعرض السهل ينظف تكرار الأسطر الخالية ويعرض نصا مرتبا. ويجمع مستعرض العناصر الروابط والأزرار والصور والمرفقات تحت أسماء واضحة. مجرد اختيار الرسالة لا يجعلها مقروءة؛ اضغط Space في قائمة الرسائل العادية للتبديل بين مقروءة وغير مقروءة.

تعامل مع عدة رسائل في خطوة واحدة
في الوضع العادي تظهر الرسائل كعناصر قائمة من دون مربعات اختيار. اضغط Ctrl+Shift+Space للدخول إلى وضع التحديد المتعدد، وعندها تتحول الرسائل إلى مربعات اختيار. تنقل بالأسهم واضغط Space لتحديد الرسالة أو إلغاء تحديدها، أو استخدم الفأرة.

ينطق البرنامج الدخول إلى هذا الوضع أو الخروج منه بعد 150 مللي ثانية. اضغط Control وحده لسماع عدد الرسائل المحددة بعد المهلة نفسها. اخرج بالضغط على Escape أو Ctrl+Shift+Space مرة أخرى. وعند محاولة تجاوز أول عنصر أو آخر عنصر ينطق البرنامج بداية القائمة أو نهايتها. تعرض قائمة السياق أوامر القراءة والنجمة والتثبيت والحذف المناسبة للمجموعة، ويطلب Delete تأكيدا يذكر عدد الرسائل.

اكتب ونفذ الأوامر من لوحة المفاتيح
إنشاء بريد إلكتروني يفتح نافذة كاملة لكتابة رسالتك. تتوفر أوامر الرد والتمييز بنجمة والترجمة والتثبيت في الأعلى والنقل إلى سلة مزود البريد من قائمة سياق الرسالة. لا توجد قائمة سياق داخل قائمة مستعرض العناصر، بينما يعرض زر إجراءات العنصر أوامر المرفقات والصور والروابط مباشرة من دون قائمة فرعية.

ترجمة في مكانها أو في نافذة مستقلة
يترجم Ctrl+T الرسالة الحالية إلى لغة البرنامج. ومن الإعدادات تستطيع اختيار عرض الترجمة مباشرة داخل مستعرض HTML أو المستعرض السهل، أو فتحها في نافذة مستقلة. لا تتفعل الترجمة إلا وأنت داخل مستعرض الرسالة. تحتاج الميزة إلى الإنترنت ولا يرسل النص إلى Google Translate إلا عندما تطلب الترجمة.

اجعل البرنامج أقرب إلى طريقتك
تتيح الإعدادات اختيار العربية أو الإنجليزية أو الفرنسية، ومستعرض HTML أو المستعرض السهل، والترجمة داخل الصفحة أو في نافذة مستقلة، والوضع الفاتح أو المظلم. يحفظ البرنامج اختياراتك ليستخدمها عند التشغيل التالي.

تحديث من داخل البرنامج
يفحص البرنامج GitHub Releases بعد التشغيل، ويمكنك الفحص يدويا من قائمة المساعدة ثم تحديث البرنامج. عند توفر إصدار جديد يفتح زر تحديث الآن نافذة تعرض الإصدار وتاريخ إطلاقه وشريط التقدم والنسبة المئوية. ينزل البرنامج المثبت الصحيح ويتحقق من بصمة SHA-256 ثم يبدأ التحديث المباشر ويعيد تشغيل التطبيق من دون فتح المتصفح.

اختصارات مفيدة
Ctrl+A يفتح خيارات الحسابات وإدارتها.
Ctrl+N ينشئ رسالة جديدة.
Ctrl+R يرد على الرسالة المحددة.
Ctrl+T يترجم الرسالة الحالية.
F5 يحدث الرسائل.
F1 يفتح هذا الدليل.
Escape يرجع إلى قائمة الرسائل من مستعرض الرسالة أو مستعرض العناصر.
Ctrl+Enter يتنقل بين مستعرض الرسالة ومستعرض العناصر.
Shift+F10 يفتح قائمة السياق والإجراءات.
Alt+F4 يغلق البرنامج.

خصوصيتك جزء من تصميم البرنامج
لا يبدأ وصول OAuth إلا بعد موافقتك في الصفحة الرسمية لمزود البريد. يحمي Windows DPAPI الرسائل المخزنة محليا والرموز وبيانات الدخول المحفوظة لحساب Windows الحالي. لا تحتوي ملفات التوزيع على حسابات المستخدمين أو رسائلهم. وعند إزالة حساب من البرنامج تزال بياناته المحلية التابعة للتطبيق.

Power Accessible Mail
تجربة بريد إلكتروني ميسرة من تطوير صولجان الشرق
"""

    def on_check_updates(self, _event: wx.Event) -> None:
        def work() -> UpdateCheckResult:
            return check_for_updates(APP_VERSION)

        def done(result: UpdateCheckResult) -> None:
            if not result.configured:
                wx.MessageBox(
                    tr(result.message),
                    tr("تحديث البرنامج"),
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
                return
            if not result.available:
                wx.MessageBox(
                    tr(result.message),
                    tr("تحديث البرنامج"),
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
                return
            if can_install_update(result):
                self.show_update_available(result)
                return
            wx.MessageBox(
                tr(result.message)
                + "\n\n"
                + tr("يوجد تحديث لكن لا يتوفر مثبت مباشر موثق ببصمة SHA-256."),
                tr("تحديث متاح"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

        self.run_worker(tr("جار فحص التحديثات..."), work, done)

    def start_startup_update_check(self) -> None:
        self._startup_update_call = None
        if self._startup_update_check_started or not updates_configured():
            return
        self._startup_update_check_started = True

        def target() -> None:
            result = check_for_updates(APP_VERSION, timeout=8)
            if result.available and can_install_update(result):
                call_after_if_open(self, self.show_update_available, result)

        threading.Thread(target=target, daemon=True).start()

    def show_update_available(self, result: UpdateCheckResult) -> None:
        if self._update_dialog_open:
            return
        self._update_dialog_open = True
        dialog = UpdateAvailableDialog(self, result)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.start_internal_update(result)
        finally:
            dialog.Destroy()
            self._update_dialog_open = False

    def start_internal_update(self, result: UpdateCheckResult) -> None:
        if self._update_download_active:
            return
        if not can_install_update(result):
            wx.MessageBox(
                tr("تعذر بدء التحديث لأن المثبت أو بصمة SHA-256 غير صالحين."),
                tr("تحديث البرنامج"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        self._update_download_active = True
        cancel_event = threading.Event()
        self._update_cancel_event = cancel_event
        dialog = UpdateDownloadDialog(
            self,
            result.latest_version,
            result.release_date,
            cancel_event.set,
        )
        self._update_progress_dialog = dialog
        dialog.Show()
        self.SetStatusText(tr("جار تنزيل التحديث داخل البرنامج."))

        def progress(downloaded: int, total: int) -> None:
            call_after_if_open(
                self,
                self.update_internal_download_progress,
                downloaded,
                total,
            )

        def target() -> None:
            try:
                installer = download_update_installer(
                    result,
                    progress=progress,
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                call_after_if_open(self, self.finish_internal_update, None, exc)
            else:
                call_after_if_open(self, self.finish_internal_update, installer, None)

        threading.Thread(target=target, daemon=True).start()

    def update_internal_download_progress(
        self,
        downloaded: int,
        total: int,
    ) -> None:
        if self._update_progress_dialog is not None:
            self._update_progress_dialog.set_progress(downloaded, total)

    def finish_internal_update(
        self,
        installer: Path | None,
        error: Exception | None,
    ) -> None:
        dialog = self._update_progress_dialog
        self._update_progress_dialog = None
        self._update_cancel_event = None
        self._update_download_active = False
        if dialog is not None:
            dialog.Destroy()

        if isinstance(error, UpdateDownloadCancelled):
            self.show_notification("تم إلغاء تنزيل التحديث.")
            return
        if error is not None:
            wx.MessageBox(
                tr(str(error)),
                tr("تعذر تحديث البرنامج"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            self.SetStatusText(tr("فشل تنزيل التحديث."))
            return
        if installer is None:
            return
        try:
            launch_update_installer(installer)
        except Exception as exc:
            wx.MessageBox(
                tr(str(exc)),
                tr("تعذر تشغيل مثبت التحديث"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self.show_notification(
            "اكتمل تنزيل التحديث والتحقق منه. سيظهر المثبت بواجهة مرئية "
            "وسيغلق البرنامج لإكمال التحديث."
        )
        self.SetStatusText(tr("جار بدء تثبيت التحديث."))
        wx.CallLater(500, self.Close)

    def current_page(self) -> MailPage | None:
        page = self.notebook.GetCurrentPage()
        if isinstance(page, MailPage):
            return page
        return None

    def ensure_password(self, account: Account) -> bool:
        if account.uses_oauth:
            return True
        if account.password:
            return True
        dialog = wx.PasswordEntryDialog(
            self,
            tr("اكتب كلمة مرور الحساب اليدوي للمتابعة."),
            tr("كلمة مرور الحساب"),
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return False
            password = dialog.GetValue()
        finally:
            dialog.Destroy()
        if not password:
            return False
        account.password = password
        account.save_password = True
        save_accounts(self.accounts)
        return True

    def _start_new_mail_timer(self) -> None:
        self.new_mail_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_new_mail_timer, self.new_mail_timer)
        self.new_mail_timer.Start(120000)

    def on_new_mail_timer(self, _event: wx.TimerEvent) -> None:
        account = self.selected_account()
        if (
            not account
            or self.displayed_account_id != account.id
            or self._polling_new_mail
            or not account.uses_oauth and not account.password
        ):
            return
        self._polling_new_mail = True

        def work() -> None:
            try:
                messages = self.service.list_messages(account, "INBOX")
            except Exception:
                call_after_if_open(
                    self,
                    self.finish_new_mail_poll,
                    account,
                    [],
                    0,
                    False,
                )
                return
            new_count = self.new_inbox_count(account, messages, False)
            call_after_if_open(
                self,
                self.finish_new_mail_poll,
                account,
                messages,
                new_count,
                True,
            )

        threading.Thread(target=work, daemon=True).start()

    def finish_new_mail_poll(
        self,
        account: Account,
        messages: list[MessageSummary],
        new_count: int,
        success: bool,
    ) -> None:
        self._polling_new_mail = False
        if not success or self.displayed_account_id != account.id:
            return
        self.pages["inbox"].reconcile_recent_messages(messages)
        self.remember_inbox_messages(account, self.pages["inbox"].messages)
        if new_count:
            self.notify_new_mail(new_count)

    def remember_inbox_messages(
        self,
        account: Account,
        messages: list[MessageSummary],
    ) -> None:
        self._known_inbox_uids[account.id] = {message.uid for message in messages}

    def new_inbox_count(
        self,
        account: Account,
        messages: list[MessageSummary],
        suppress_notification: bool,
    ) -> int:
        known = self._known_inbox_uids.get(account.id, set())
        if suppress_notification or not known:
            return 0
        return sum(1 for message in messages if message.uid not in known)

    def notify_new_mail(self, count: int) -> None:
        title = "رسالة جديدة" if count == 1 else "رسائل جديدة"
        message = "وصلت رسالة جديدة إلى الوارد." if count == 1 else f"وصلت {count} رسائل جديدة إلى الوارد."
        self.SetStatusText(message)
        try:
            notification = wx.adv.NotificationMessage(tr(title), tr(message), parent=self)
            notification.Show(timeout=8)
        except Exception:
            wx.Bell()

    def run_worker(
        self,
        message: str,
        work: Callable[[], Any],
        done: Callable[[Any], None],
        failed: Callable[[Exception], None] | None = None,
    ) -> None:
        self._active_worker_count += 1
        self.set_busy(True, message)

        def target() -> None:
            try:
                result = work()
            except (MailError, OSError, imaplib.IMAP4.error, smtplib.SMTPException) as exc:  # type: ignore[name-defined]
                call_after_if_open(self, self.on_worker_error, exc, failed)
            except Exception as exc:
                call_after_if_open(self, self.on_worker_error, exc, failed)
            else:
                call_after_if_open(self, self.on_worker_done, done, result)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def on_worker_done(self, done: Callable[[Any], None], result: Any) -> None:
        self._active_worker_count = max(0, self._active_worker_count - 1)
        if self._active_worker_count == 0:
            self.set_busy(False, "جاهز")
        done(result)

    def on_worker_error(
        self,
        exc: Exception,
        failed: Callable[[Exception], None] | None = None,
    ) -> None:
        self._active_worker_count = max(0, self._active_worker_count - 1)
        if self._active_worker_count == 0:
            self.set_busy(False, "حدث خطأ")
        else:
            self.SetStatusText("حدث خطأ")
        if failed:
            try:
                failed(exc)
            except Exception:
                pass
        self.reset_transfer_progress()
        if isinstance(exc, OAuthReauthenticationRequired):
            self.handle_oauth_reauthentication_required(exc)
            return
        wx.MessageBox(str(exc), "خطأ", wx.OK | wx.ICON_ERROR, self)
        self.SetStatusText(f"خطأ: {exc}")

    def handle_oauth_reauthentication_required(
        self,
        exc: OAuthReauthenticationRequired,
    ) -> None:
        account_id = getattr(exc, "account_id", "")
        account = next(
            (
                candidate
                for candidate in self.accounts
                if account_id and candidate.id == account_id
            ),
            None,
        )
        if account is None:
            account = self.selected_account()
        if account and account.uses_oauth:
            changed = bool(
                account.oauth_access_token
                or account.oauth_refresh_token
                or account.oauth_token_expiry
            )
            account.oauth_access_token = ""
            account.oauth_refresh_token = ""
            account.oauth_token_expiry = 0.0
            if changed:
                save_accounts(self.accounts)
        message = tr(str(exc))
        self.show_notification(message, timeout_ms=15000)
        self.SetStatusText(message)

    def set_busy(self, busy: bool, message: str) -> None:
        self.SetStatusText(tr(message))
