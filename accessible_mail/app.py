from __future__ import annotations

import html
import json
import os
import sys
import tempfile
import threading
import time
import webbrowser
import imaplib
import smtplib
import urllib.parse
import urllib.request
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import wx
import wx.adv
import wx.html2

from .config import (
    APP_TITLE,
    APP_VERSION,
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    THEME_DARK,
    THEME_LIGHT,
    TRANSLATION_DIALOG,
    TRANSLATION_INLINE,
    VIEWER_HTML,
    VIEWER_SIMPLE,
    ProgramSettings,
    app_dir,
    load_accounts,
    load_oauth_clients,
    load_settings,
    save_accounts,
    save_settings,
)
from .i18n import is_rtl, set_language, tr
from .screen_reader import interrupt_and_speak
from .email_service import MailError, MailSyncResult
from .email_utils import normalize_message_text
from .mail_service_router import MailServiceRouter
from .models import Account, LinkItem, MessageContent, MessageSummary
from .oauth import (
    OAuthError,
    OAuthReauthenticationRequired,
    apply_provider_settings,
    google_provider_id,
    provider_display_names,
    provider_id_from_name,
    run_browser_oauth_flow,
)
from .update_checker import UpdateCheckResult, check_for_updates, updates_configured
from .updater import (
    UpdateDownloadCancelled,
    can_install_update,
    download_update_installer,
    launch_update_installer,
)


INITIAL_MESSAGE_LIMIT = 50
MAX_MEMORY_MESSAGE_CONTENTS = 20
MESSAGE_SELECTION_DELAY_MS = 140
FILTER_ALL = "الكل"
FILTER_STARRED = "الرسائل المميزة بنجمة"
FILTER_UNREAD = "غير مقروءة"
FILTER_READ = "مقروءة"
FILTER_TRASH = "سلة المحذوفات"
FILTER_CHOICES = [FILTER_ALL, FILTER_STARRED, FILTER_UNREAD, FILTER_READ, FILTER_TRASH]
BULK_ACTION_MARK_READ = "mark_read"
BULK_ACTION_MARK_UNREAD = "mark_unread"
BULK_ACTION_STAR = "star"
BULK_ACTION_UNSTAR = "unstar"
BULK_ACTION_PIN = "pin"
BULK_ACTION_UNPIN = "unpin"
BULK_ACTION_DELETE = "delete"
LANGUAGE_CHOICES = {
    "العربية": LANGUAGE_ARABIC,
    "الإنجليزية": LANGUAGE_ENGLISH,
}
VIEWER_CHOICES = {
    "مستعرض HTML": VIEWER_HTML,
    "المستعرض السهل": VIEWER_SIMPLE,
}
THEME_CHOICES = {
    "الوضع الفاتح": THEME_LIGHT,
    "الوضع المظلم": THEME_DARK,
}
TRANSLATION_MODE_CHOICES = {
    "ترجمة داخل مستعرض الرسالة": TRANSLATION_INLINE,
    "ترجمة في نافذة مستقلة": TRANSLATION_DIALOG,
}
MANUAL_PROVIDER_GOOGLE = "google"
MANUAL_PROVIDER_MICROSOFT = "microsoft"
MANUAL_PROVIDER_CHOICES = (
    (MANUAL_PROVIDER_GOOGLE, "Google / Gmail"),
    (MANUAL_PROVIDER_MICROSOFT, "Microsoft / Outlook"),
)
MANUAL_PROVIDER_SETTINGS = {
    MANUAL_PROVIDER_GOOGLE: {
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
        "spam_mailbox": "",
    },
    MANUAL_PROVIDER_MICROSOFT: {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_server": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
        "spam_mailbox": "Junk Email",
    },
}
INLINE_GENERIC_LINK_TEXTS = (
    "اضغط هنا",
    "إضغط هنا",
    "انقر هنا",
    "هنا",
    "افتح",
    "فتح",
    "click here",
    "here",
)

_native_message_box = wx.MessageBox


def set_accessible(control: wx.Window, name: str, description: str = "") -> None:
    control.SetName(tr(name))
    if description:
        control.SetToolTip(tr(description))


def announce_to_screen_reader(control: wx.Window, message: str) -> bool:
    localized = tr(message)
    if interrupt_and_speak(localized):
        return True
    try:
        wx.Accessible.NotifyEvent(
            wx.ACC_EVENT_SYSTEM_ALERT,
            control,
            wx.OBJID_CLIENT,
            0,
        )
        return True
    except Exception:
        return False


def message_box(
    message: str,
    caption: str,
    style: int = wx.OK,
    parent: wx.Window | None = None,
) -> int:
    return _native_message_box(tr(message), tr(caption), style, parent)


wx.MessageBox = message_box


def run_bulk_operations(
    summaries: list[MessageSummary],
    operation: Callable[[MessageSummary], None],
    max_workers: int = 4,
) -> tuple[list[MessageSummary], list[tuple[MessageSummary, Exception]]]:
    if not summaries:
        return [], []
    worker_count = max(1, min(max_workers, len(summaries)))
    succeeded: list[MessageSummary] = []
    failed: list[tuple[MessageSummary, Exception]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        jobs = [(summary, executor.submit(operation, summary)) for summary in summaries]
        for summary, job in jobs:
            try:
                job.result()
            except Exception as exc:
                failed.append((summary, exc))
            else:
                succeeded.append(summary)
    return succeeded, failed


def apply_layout_direction(window: wx.Window) -> None:
    direction = wx.Layout_RightToLeft if is_rtl() else wx.Layout_LeftToRight
    try:
        window.SetLayoutDirection(direction)
    except Exception:
        pass


def localize_window(window: wx.Window) -> None:
    apply_layout_direction(window)
    if isinstance(window, wx.TopLevelWindow):
        try:
            window.SetTitle(tr(window.GetTitle()))
        except Exception:
            pass
    if isinstance(window, (wx.StaticText, wx.Button, wx.CheckBox, wx.RadioBox)):
        try:
            window.SetLabel(tr(window.GetLabel()))
        except Exception:
            pass
    try:
        name = window.GetName()
        if name:
            window.SetName(tr(name))
    except Exception:
        pass
    try:
        tooltip = window.GetToolTipText()
        if tooltip:
            window.SetToolTip(tr(tooltip))
    except Exception:
        pass
    for child in window.GetChildren():
        localize_window(child)


def set_localized_items(control: wx.Choice | wx.ListBox | wx.RadioBox, labels: list[str]) -> None:
    selection = control.GetSelection()
    translated = [tr(label) for label in labels]
    if isinstance(control, wx.RadioBox):
        for index, label in enumerate(translated):
            control.SetString(index, label)
    else:
        control.Set(translated)
    if 0 <= selection < len(translated):
        control.SetSelection(selection)


def localize_menu_bar(menu_bar: wx.MenuBar | None) -> None:
    if not menu_bar:
        return
    for menu_index in range(menu_bar.GetMenuCount()):
        menu_bar.SetMenuLabel(menu_index, tr(menu_bar.GetMenuLabel(menu_index)))
        menu = menu_bar.GetMenu(menu_index)
        for item in menu.GetMenuItems():
            if not item.IsSeparator():
                item.SetItemLabel(tr(item.GetItemLabel()))


def text_chunks(text: str, max_length: int = 4500) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        next_line = line if not current else f"{current}\n{line}"
        if len(next_line) <= max_length:
            current = next_line
            continue
        if current:
            chunks.append(current)
        while len(line) > max_length:
            chunks.append(line[:max_length])
            line = line[max_length:]
        current = line
    if current:
        chunks.append(current)
    return chunks or [text[:max_length]]


def translate_text_with_google(text: str, target_language: str = "ar") -> str:
    text = text.strip()
    if not text:
        return ""
    translated_parts: list[str] = []
    for chunk in text_chunks(text):
        data = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": "auto",
                "tl": target_language,
                "dt": "t",
                "q": chunk,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://translate.googleapis.com/translate_a/single",
            data=data,
            headers={"User-Agent": "Power Accessible Mail"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload or not isinstance(payload[0], list):
            continue
        translated_parts.append("".join(str(part[0]) for part in payload[0] if part and part[0]))
    translated = "\n".join(part for part in translated_parts if part.strip()).strip()
    if not translated:
        raise MailError("تعذر الحصول على ترجمة من Google.")
    return translated


def login_background_path() -> Path | None:
    image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    search_dirs = [app_dir() / "backgrounds", app_dir()]
    for folder in search_dirs:
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if (
                path.is_file()
                and path.suffix.lower() in image_extensions
                and "خلفية" in path.stem
                and "تسجيل" in path.stem
            ):
                return path
    return None


def app_icon_path() -> Path | None:
    path = app_dir() / "assets" / "branding" / "power_accessible_mail.ico"
    return path if path.is_file() else None


def app_logo_path() -> Path | None:
    for filename in (
        "power_accessible_mail_oauth_120.png",
        "power_accessible_mail_logo_512.png",
    ):
        path = app_dir() / "assets" / "branding" / filename
        if path.is_file():
            return path
    return None


class BackgroundPanel(wx.Panel):
    def __init__(self, parent: wx.Window, image_path: Path | None) -> None:
        super().__init__(parent)
        self.bitmap = wx.NullBitmap
        if image_path and image_path.exists():
            bitmap = wx.Bitmap(str(image_path), wx.BITMAP_TYPE_ANY)
            if bitmap.IsOk():
                self.bitmap = bitmap
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)

    def on_size(self, event: wx.SizeEvent) -> None:
        self.Refresh()
        event.Skip()

    def on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        width, height = self.GetClientSize()
        if width <= 0 or height <= 0 or not self.bitmap.IsOk():
            return
        image = self.bitmap.ConvertToImage()
        if not image.IsOk():
            return
        scaled = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
        dc.DrawBitmap(wx.Bitmap(scaled), 0, 0)


class AccountDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        account: Account | None = None,
        startup: bool = False,
    ) -> None:
        title = "تسجيل الدخول" if startup else "إضافة حساب بريد"
        super().__init__(parent, title=title, size=(780, 620))
        self.account = replace(account) if account else Account()
        self.startup = startup
        self.mode = ""
        self._build()

    def _build(self) -> None:
        self.panel = BackgroundPanel(self, login_background_path())
        apply_layout_direction(self.panel)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_dialog_key)
        if self.startup:
            self.show_startup_view()
        else:
            self.show_method_view()

    def clear_panel(self) -> wx.BoxSizer:
        self.panel.DestroyChildren()
        root = wx.BoxSizer(wx.VERTICAL)
        root.AddStretchSpacer(1)
        self.panel.SetSizer(root)
        return root

    def finish_panel(self, root: wx.BoxSizer, focus: wx.Window) -> None:
        root.AddStretchSpacer(1)
        localize_window(self)
        self.panel.Layout()
        self.Layout()
        wx.CallAfter(focus.SetFocus)

    def show_startup_view(self) -> None:
        self.mode = "startup"
        root = self.clear_panel()
        content_panel = wx.Panel(self.panel)
        content_background = wx.Colour(20, 27, 36)
        content_panel.SetBackgroundColour(content_background)
        center = wx.BoxSizer(wx.VERTICAL)

        heading = wx.StaticText(
            content_panel,
            label="مرحبا بكم في برنامج Power Accessible Mail",
            style=wx.ALIGN_CENTER_HORIZONTAL,
        )
        heading_font = heading.GetFont()
        heading_font.SetPointSize(19)
        heading_font.SetWeight(wx.FONTWEIGHT_BOLD)
        heading.SetFont(heading_font)
        heading.SetForegroundColour(wx.WHITE)
        center.Add(heading, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        logo_path = app_logo_path()
        if logo_path:
            logo_bitmap = wx.Bitmap(str(logo_path), wx.BITMAP_TYPE_ANY)
            if logo_bitmap.IsOk():
                logo = wx.StaticBitmap(content_panel, bitmap=logo_bitmap)
                logo.SetBackgroundColour(content_background)
                set_accessible(logo, "شعار Power Accessible Mail")
                center.Add(logo, 0, wx.ALIGN_CENTER | wx.BOTTOM, 14)

        email_label = wx.StaticText(content_panel, label="عنوان البريد الإلكتروني:")
        email_label.SetForegroundColour(wx.WHITE)
        center.Add(email_label, 0, wx.EXPAND | wx.BOTTOM, 4)
        self.startup_email = wx.TextCtrl(content_panel, size=(360, 34), style=wx.TE_PROCESS_ENTER)
        set_accessible(self.startup_email, "عنوان البريد الإلكتروني")
        self.startup_email.Bind(
            wx.EVT_TEXT_ENTER,
            lambda _event: self.startup_password.SetFocus(),
        )
        center.Add(self.startup_email, 0, wx.EXPAND | wx.BOTTOM, 9)

        password_label = wx.StaticText(content_panel, label="كلمة المرور:")
        password_label.SetForegroundColour(wx.WHITE)
        center.Add(password_label, 0, wx.EXPAND | wx.BOTTOM, 4)
        self.startup_password = wx.TextCtrl(
            content_panel,
            size=(360, 34),
            style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER,
        )
        set_accessible(self.startup_password, "كلمة المرور")
        self.startup_password.Bind(wx.EVT_TEXT_ENTER, self.on_startup_manual_login)
        center.Add(self.startup_password, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.sign_in_button = wx.Button(
            content_panel,
            label="تسجيل الدخول",
            size=(360, 44),
        )
        set_accessible(self.sign_in_button, "تسجيل الدخول بالبريد وكلمة المرور")
        self.sign_in_button.SetDefault()
        self.sign_in_button.Bind(wx.EVT_BUTTON, self.on_startup_manual_login)
        center.Add(self.sign_in_button, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.continue_google_button = wx.Button(
            content_panel,
            label="الاستمرار مع Google",
            size=(360, 44),
        )
        set_accessible(
            self.continue_google_button,
            "الاستمرار مع Google",
            "فتح تسجيل الدخول إلى Google",
        )
        self.continue_google_button.Bind(wx.EVT_BUTTON, self.on_continue_with_google)
        center.Add(self.continue_google_button, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.continue_microsoft_button = wx.Button(
            content_panel,
            label="الاستمرار مع Microsoft",
            size=(360, 44),
        )
        set_accessible(
            self.continue_microsoft_button,
            "الاستمرار مع Microsoft",
            "فتح تسجيل الدخول إلى Microsoft",
        )
        self.continue_microsoft_button.Bind(
            wx.EVT_BUTTON,
            self.on_continue_with_microsoft,
        )
        center.Add(self.continue_microsoft_button, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.continue_without_account_button = wx.Button(
            content_panel,
            label="الاستمرار بدون إضافة حساب",
            size=(360, 44),
        )
        set_accessible(
            self.continue_without_account_button,
            "الاستمرار بدون إضافة حساب",
            "الدخول إلى الواجهة الرئيسية بدون حساب",
        )
        self.continue_without_account_button.Bind(
            wx.EVT_BUTTON,
            self.on_continue_without_account,
        )
        center.Add(self.continue_without_account_button, 0, wx.EXPAND)

        content_root = wx.BoxSizer(wx.VERTICAL)
        content_root.Add(center, 1, wx.EXPAND | wx.ALL, 20)
        content_panel.SetSizer(content_root)
        root.Add(content_panel, 0, wx.ALIGN_CENTER)
        self.finish_panel(root, self.startup_email)

    def on_startup_manual_login(self, _event: wx.CommandEvent) -> None:
        email_address = self.startup_email.GetValue().strip()
        password = self.startup_password.GetValue()
        if not email_address or "@" not in email_address:
            wx.MessageBox(
                "يرجى كتابة عنوان البريد.",
                "بيانات غير مكتملة",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            wx.CallAfter(self.startup_email.SetFocus)
            return
        if not password:
            wx.MessageBox(
                "يرجى كتابة كلمة المرور.",
                "بيانات غير مكتملة",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            wx.CallAfter(self.startup_password.SetFocus)
            return

        account = self.account
        account.display_name = email_address.split("@", 1)[0]
        account.email_address = email_address
        account.username = email_address
        account.auth_method = "password"
        account.password = password
        account.save_password = True
        account.oauth_provider = ""
        account.oauth_client_id = ""
        account.oauth_client_secret = ""
        account.oauth_access_token = ""
        account.oauth_refresh_token = ""
        account.oauth_token_expiry = 0.0
        account.save_oauth_tokens = False

        if self.configure_known_manual_provider(account):
            self.EndModal(wx.ID_OK)
            return

        self.show_manual_view()
        wx.CallAfter(self.imap_server.SetFocus)

    @staticmethod
    def configure_known_manual_provider(account: Account) -> bool:
        email_address = account.email_address.lower()
        if email_address.endswith(("@gmail.com", "@googlemail.com")):
            account.imap_server = "imap.gmail.com"
            account.imap_port = 993
            account.imap_ssl = True
            account.smtp_server = "smtp.gmail.com"
            account.smtp_port = 587
            account.smtp_ssl = False
            account.smtp_starttls = True
            return True
        if email_address.endswith(
            ("@outlook.com", "@hotmail.com", "@live.com", "@msn.com")
        ):
            account.imap_server = "outlook.office365.com"
            account.imap_port = 993
            account.imap_ssl = True
            account.smtp_server = "smtp-mail.outlook.com"
            account.smtp_port = 587
            account.smtp_ssl = False
            account.smtp_starttls = True
            account.spam_mailbox = "Junk Email"
            return True
        return False

    def on_continue_with_google(self, _event: wx.CommandEvent) -> None:
        self.start_oauth_login(google_provider_id())

    def on_continue_with_microsoft(self, _event: wx.CommandEvent) -> None:
        self.start_oauth_login("microsoft")

    def on_continue_without_account(self, _event: wx.CommandEvent | None = None) -> None:
        self.close_to_main_interface()

    def show_method_view(self) -> None:
        self.mode = "method"
        root = self.clear_panel()
        center = wx.BoxSizer(wx.VERTICAL)
        center.Add(
            wx.StaticText(self.panel, label="طريقة إضافة الحساب:"),
            0,
            wx.ALIGN_CENTER | wx.BOTTOM,
            14,
        )

        self.account_method_list = wx.ListBox(
            self.panel,
            choices=[
                tr("تسجيل الدخول عبر المتصفح"),
                tr("تسجيل الدخول اليدوي"),
            ],
            size=(360, 110),
            style=wx.LB_SINGLE,
        )
        self.account_method_list.SetSelection(0)
        set_accessible(
            self.account_method_list,
            "طريقة إضافة الحساب",
            "اختر طريقة إضافة الحساب واضغط Enter",
        )
        self.account_method_list.Bind(
            wx.EVT_LISTBOX_DCLICK,
            self.on_account_method_activate,
        )
        self.account_method_list.Bind(
            wx.EVT_KEY_DOWN,
            self.on_account_method_key,
        )
        self.account_method_list.Bind(
            wx.EVT_CONTEXT_MENU,
            self.on_account_method_context,
        )
        center.Add(self.account_method_list, 0, wx.EXPAND | wx.BOTTOM, 10)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        ok_button = wx.Button(self.panel, label="موافق")
        set_accessible(ok_button, "موافق لاختيار طريقة إضافة الحساب")
        ok_button.SetDefault()
        ok_button.Bind(wx.EVT_BUTTON, self.on_account_method_activate)
        buttons.Add(ok_button, 0, wx.ALL, 6)
        cancel_button = wx.Button(self.panel, id=wx.ID_CANCEL, label="إلغاء")
        set_accessible(cancel_button, "إلغاء إضافة الحساب")
        buttons.Add(cancel_button, 0, wx.ALL, 6)
        center.Add(buttons, 0, wx.ALIGN_CENTER)
        root.Add(center, 0, wx.ALIGN_CENTER)
        self.finish_panel(root, self.account_method_list)

    def on_account_method_activate(self, _event: wx.Event | None = None) -> None:
        selection = self.account_method_list.GetSelection()
        if selection == 0:
            self.show_oauth_provider_view()
        elif selection == 1:
            self.show_manual_view()

    def on_account_method_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER}:
            self.on_account_method_activate()
            return
        event.Skip()

    def on_account_method_context(self, event: wx.ContextMenuEvent) -> None:
        self._select_context_list_item(self.account_method_list, event)
        self.on_account_method_activate()

    def on_browser_method(self, _event: wx.CommandEvent) -> None:
        self.show_oauth_provider_view()

    def on_manual_method(self, _event: wx.CommandEvent) -> None:
        self.show_manual_view()

    def show_oauth_provider_view(self) -> None:
        self.mode = "oauth2"
        root = self.clear_panel()
        center = wx.BoxSizer(wx.VERTICAL)
        center.Add(wx.StaticText(self.panel, label="اختر خدمة البريد:"), 0, wx.ALIGN_CENTER | wx.ALL, 8)

        provider_names = provider_display_names()
        self.oauth_provider_ids = [
            provider_id_from_name(provider_name)
            for provider_name in provider_names
        ]
        self.oauth_provider_list = wx.ListBox(
            self.panel,
            choices=[tr(provider_name) for provider_name in provider_names],
            size=(360, 120),
            style=wx.LB_SINGLE,
        )
        if provider_names:
            self.oauth_provider_list.SetSelection(0)
        set_accessible(
            self.oauth_provider_list,
            "اختر خدمة البريد",
            "اختر خدمة البريد واضغط Enter لفتح تسجيل الدخول",
        )
        self.oauth_provider_list.Bind(
            wx.EVT_LISTBOX_DCLICK,
            self.on_oauth_provider_activate,
        )
        self.oauth_provider_list.Bind(
            wx.EVT_KEY_DOWN,
            self.on_oauth_provider_key,
        )
        self.oauth_provider_list.Bind(
            wx.EVT_CONTEXT_MENU,
            self.on_oauth_provider_context,
        )
        center.Add(self.oauth_provider_list, 0, wx.EXPAND | wx.BOTTOM, 10)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        ok_button = wx.Button(self.panel, label="موافق")
        set_accessible(ok_button, "موافق لاختيار خدمة البريد")
        ok_button.SetDefault()
        ok_button.Bind(wx.EVT_BUTTON, self.on_oauth_provider_activate)
        buttons.Add(ok_button, 0, wx.ALL, 6)
        back_button = wx.Button(self.panel, label="رجوع")
        set_accessible(back_button, "رجوع إلى اختيار طريقة إضافة الحساب")
        back_button.Bind(wx.EVT_BUTTON, self.on_back)
        buttons.Add(back_button, 0, wx.ALL, 6)
        cancel_button = wx.Button(self.panel, id=wx.ID_CANCEL, label="إلغاء")
        set_accessible(cancel_button, "إلغاء إضافة الحساب")
        buttons.Add(cancel_button, 0, wx.ALL, 6)
        center.Add(buttons, 0, wx.ALIGN_CENTER)
        root.Add(center, 0, wx.ALIGN_CENTER)
        self.finish_panel(
            root,
            self.oauth_provider_list if provider_names else back_button,
        )

    def on_oauth_provider_activate(self, _event: wx.Event | None = None) -> None:
        selection = self.oauth_provider_list.GetSelection()
        if 0 <= selection < len(self.oauth_provider_ids):
            self.start_oauth_login(self.oauth_provider_ids[selection])

    def on_oauth_provider_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER}:
            self.on_oauth_provider_activate()
            return
        event.Skip()

    def on_oauth_provider_context(self, event: wx.ContextMenuEvent) -> None:
        self._select_context_list_item(self.oauth_provider_list, event)
        self.on_oauth_provider_activate()

    def on_oauth_provider_button(
        self,
        _event: wx.CommandEvent,
        provider_id: str,
    ) -> None:
        self.start_oauth_login(provider_id)

    def show_manual_view(self) -> None:
        self.mode = "password"
        root = self.clear_panel()
        scroll = wx.ScrolledWindow(self.panel)
        scroll.SetScrollRate(0, 20)
        apply_layout_direction(scroll)

        form_root = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        grid.AddGrowableCol(1, 1)

        manual_provider_label = wx.StaticText(scroll, label="خدمة البريد:")
        self.manual_provider_ids = [
            provider_id for provider_id, _label in MANUAL_PROVIDER_CHOICES
        ]
        self.manual_provider = wx.Choice(
            scroll,
            choices=[tr(label) for _provider_id, label in MANUAL_PROVIDER_CHOICES],
        )
        self.manual_provider.SetSelection(
            self.manual_provider_index_for_account(self.account)
        )
        set_accessible(
            self.manual_provider,
            "خدمة البريد",
            "اختر Google أو Microsoft لتعبئة إعدادات الخادم المناسبة",
        )
        self.manual_provider.Bind(
            wx.EVT_CHOICE,
            self.on_manual_provider_changed,
        )
        grid.Add(manual_provider_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.manual_provider, 1, wx.EXPAND)

        self.display_name = self._text(scroll, grid, "اسم الحساب:")
        self.email_address = self._text(scroll, grid, "عنوان البريد الإلكتروني:")
        self.username = self._text(scroll, grid, "اسم المستخدم:")
        self.password = self._text(scroll, grid, "كلمة المرور:", wx.TE_PASSWORD)

        self.imap_server = self._text(scroll, grid, "خادم IMAP:")
        self.imap_port = self._text(scroll, grid, "منفذ IMAP:")
        self.imap_ssl = wx.CheckBox(scroll, label="استخدام SSL مع IMAP")
        set_accessible(self.imap_ssl, "استخدام SSL مع IMAP")
        grid.Add(wx.StaticText(scroll, label="تشفير IMAP:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.imap_ssl, 0, wx.EXPAND)

        self.smtp_server = self._text(scroll, grid, "خادم SMTP:")
        self.smtp_port = self._text(scroll, grid, "منفذ SMTP:")
        self.smtp_ssl = wx.CheckBox(scroll, label="استخدام SSL مباشر مع SMTP")
        set_accessible(self.smtp_ssl, "استخدام SSL مباشر مع SMTP")
        grid.Add(wx.StaticText(scroll, label="SSL SMTP:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.smtp_ssl, 0, wx.EXPAND)

        self.smtp_starttls = wx.CheckBox(scroll, label="استخدام STARTTLS مع SMTP")
        set_accessible(self.smtp_starttls, "استخدام STARTTLS مع SMTP")
        grid.Add(wx.StaticText(scroll, label="STARTTLS SMTP:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.smtp_starttls, 0, wx.EXPAND)

        self.spam_mailbox = self._text(scroll, grid, "مجلد غير مرغوب:")
        self.save_password = wx.CheckBox(scroll, label="حفظ كلمة المرور محليا بشكل مشفر")
        self.save_password.SetValue(True)
        set_accessible(self.save_password, "حفظ كلمة المرور محليا بشكل مشفر")
        grid.Add(wx.StaticText(scroll, label="حفظ كلمة المرور:"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.save_password, 0, wx.EXPAND)

        form_root.Add(grid, 1, wx.EXPAND | wx.ALL, 14)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        ok_button = wx.Button(scroll, label="موافق")
        set_accessible(ok_button, "حفظ الحساب اليدوي")
        ok_button.Bind(wx.EVT_BUTTON, self.on_manual_ok)
        buttons.Add(ok_button, 0, wx.ALL, 6)
        back_button = wx.Button(scroll, label="رجوع")
        set_accessible(back_button, "رجوع إلى اختيار طريقة إضافة الحساب")
        back_button.Bind(wx.EVT_BUTTON, self.on_back)
        buttons.Add(back_button, 0, wx.ALL, 6)
        cancel_button = wx.Button(scroll, id=wx.ID_CANCEL, label="إلغاء")
        set_accessible(cancel_button, "إلغاء إضافة الحساب")
        buttons.Add(cancel_button, 0, wx.ALL, 6)
        form_root.Add(buttons, 0, wx.ALIGN_CENTER | wx.ALL, 6)

        scroll.SetSizer(form_root)
        root.Add(scroll, 0, wx.ALIGN_CENTER | wx.ALL, 20)
        self._fill_manual(self.account)
        self.apply_selected_manual_provider_defaults(
            overwrite=not bool(self.account.imap_server or self.account.smtp_server)
        )
        self.finish_panel(root, self.manual_provider)

    def on_back(self, _event: wx.CommandEvent | None = None) -> None:
        if self.mode in {"oauth2", "password"}:
            self.show_method_view()
            return
        self.close_to_main_interface()

    def close_to_main_interface(self) -> None:
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Close()

    def on_dialog_key(self, event: wx.KeyEvent) -> None:
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_ESCAPE:
            self.close_to_main_interface()
            return
        if key_code == wx.WXK_BACK:
            if self.mode == "password":
                focus = wx.Window.FindFocus()
                if isinstance(focus, wx.TextCtrl):
                    event.Skip()
                    return
            self.on_back()
            return
        if key_code in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER}:
            focus = wx.Window.FindFocus()
            if self.mode == "method" and focus is self.account_method_list:
                self.on_account_method_activate()
                return
            if self.mode == "oauth2" and focus is self.oauth_provider_list:
                self.on_oauth_provider_activate()
                return
        event.Skip()

    @staticmethod
    def _select_context_list_item(
        control: wx.ListBox,
        event: wx.ContextMenuEvent,
    ) -> None:
        position = event.GetPosition()
        if position == wx.DefaultPosition:
            return
        hit = control.HitTest(control.ScreenToClient(position))
        if isinstance(hit, tuple):
            hit = hit[0]
        if hit != wx.NOT_FOUND:
            control.SetSelection(hit)

    def _text(
        self,
        parent: wx.Window,
        grid: wx.FlexGridSizer,
        label: str,
        style: int = 0,
    ) -> wx.TextCtrl:
        text_label = wx.StaticText(parent, label=label)
        control = wx.TextCtrl(parent, style=style)
        set_accessible(control, label.replace(":", ""))
        grid.Add(text_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(control, 1, wx.EXPAND)
        return control

    def _fill_manual(self, account: Account) -> None:
        self.display_name.SetValue(account.display_name)
        self.email_address.SetValue(account.email_address)
        self.username.SetValue(account.username)
        self.password.SetValue(account.password)
        self.imap_server.SetValue(account.imap_server)
        self.imap_port.SetValue(str(account.imap_port))
        self.imap_ssl.SetValue(account.imap_ssl)
        self.smtp_server.SetValue(account.smtp_server)
        self.smtp_port.SetValue(str(account.smtp_port))
        self.smtp_ssl.SetValue(account.smtp_ssl)
        self.smtp_starttls.SetValue(account.smtp_starttls)
        self.spam_mailbox.SetValue(account.spam_mailbox)
        self.save_password.SetValue(account.save_password or not account.password)

    @staticmethod
    def manual_provider_index_for_account(account: Account) -> int:
        email_address = account.email_address.lower()
        server_names = f"{account.imap_server} {account.smtp_server}".lower()
        microsoft_domains = ("@outlook.com", "@hotmail.com", "@live.com", "@msn.com")
        if email_address.endswith(microsoft_domains) or any(
            marker in server_names for marker in ("outlook.", "office365.")
        ):
            return 1
        return 0

    def selected_manual_provider_id(self) -> str:
        selection = self.manual_provider.GetSelection()
        if not 0 <= selection < len(self.manual_provider_ids):
            return MANUAL_PROVIDER_GOOGLE
        return self.manual_provider_ids[selection]

    def on_manual_provider_changed(self, _event: wx.CommandEvent) -> None:
        self.apply_selected_manual_provider_defaults(overwrite=True)

    def apply_selected_manual_provider_defaults(self, overwrite: bool) -> None:
        settings = MANUAL_PROVIDER_SETTINGS[self.selected_manual_provider_id()]
        text_controls = {
            "imap_server": self.imap_server,
            "imap_port": self.imap_port,
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "spam_mailbox": self.spam_mailbox,
        }
        for key, control in text_controls.items():
            if overwrite or not control.GetValue().strip():
                control.SetValue(str(settings[key]))
        check_controls = {
            "imap_ssl": self.imap_ssl,
            "smtp_ssl": self.smtp_ssl,
            "smtp_starttls": self.smtp_starttls,
        }
        for key, control in check_controls.items():
            if overwrite:
                control.SetValue(bool(settings[key]))

    def on_oauth_login(self, _event: wx.CommandEvent) -> None:
        provider_id = self.ask_oauth_provider()
        if not provider_id:
            return
        self.start_oauth_login(provider_id)

    def start_oauth_login(self, provider_id: str) -> None:
        self._select_oauth_provider(provider_id)
        oauth_clients = load_oauth_clients()
        provider_client = oauth_clients.get(provider_id, {})
        client_id = provider_client.get("client_id", "") or self.account.oauth_client_id
        client_secret = provider_client.get("client_secret", "") or self.account.oauth_client_secret
        if not client_id:
            wx.MessageBox(
                "تسجيل الدخول عبر المتصفح لم يتم تجهيزه بعد في هذه النسخة. "
                "بعد تجهيز OAuth من مطور البرنامج سيظهر للمستخدم اختيار الحساب "
                "ورسالة الموافقة مباشرة.",
                "تسجيل الدخول غير جاهز",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        try:
            wx.BeginBusyCursor()
            result = run_browser_oauth_flow(provider_id, client_id, client_secret)
        except OAuthError as exc:
            wx.MessageBox(tr(str(exc)), tr("تعذر تسجيل الدخول"), wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()

        account = self.account
        account.auth_method = "oauth2"
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
        self.EndModal(wx.ID_OK)

    def ask_oauth_provider(self) -> str | None:
        names = provider_display_names()
        dialog = wx.SingleChoiceDialog(
            self,
            tr("اختر خدمة البريد"),
            tr("تسجيل الدخول عبر المتصفح"),
            names,
        )
        try:
            if hasattr(self, "oauth_provider_list"):
                current_selection = self.oauth_provider_list.GetSelection()
                if 0 <= current_selection < len(names):
                    dialog.SetSelection(current_selection)
            if dialog.ShowModal() != wx.ID_OK:
                return None
            return provider_id_from_name(dialog.GetStringSelection())
        finally:
            dialog.Destroy()

    def selected_oauth_provider_id(self) -> str:
        selection = self.oauth_provider_list.GetSelection()
        if not 0 <= selection < len(self.oauth_provider_ids):
            raise OAuthError("مزود OAuth غير معروف.")
        return self.oauth_provider_ids[selection]

    def _select_oauth_provider(self, provider_id: str) -> None:
        if not hasattr(self, "oauth_provider_list"):
            return
        try:
            index = self.oauth_provider_ids.index(provider_id)
        except ValueError:
            index = 0
        if self.oauth_provider_ids:
            self.oauth_provider_list.SetSelection(index)

    def on_ok(self, event: wx.CommandEvent) -> None:
        try:
            self.account = self.to_account()
        except ValueError as exc:
            wx.MessageBox(str(exc), "بيانات غير مكتملة", wx.OK | wx.ICON_WARNING, self)
            return
        event.Skip()

    def on_manual_ok(self, _event: wx.CommandEvent) -> None:
        try:
            self.account = self.to_account()
        except ValueError as exc:
            wx.MessageBox(str(exc), "بيانات غير مكتملة", wx.OK | wx.ICON_WARNING, self)
            return
        self.EndModal(wx.ID_OK)

    def to_account(self) -> Account:
        email_address = self.email_address.GetValue().strip()
        if not email_address:
            raise ValueError("يرجى كتابة عنوان البريد.")
        account = self.account
        account.display_name = self.display_name.GetValue().strip()
        account.email_address = email_address
        account.username = self.username.GetValue().strip() or email_address
        account.auth_method = "password"
        account.password = self.password.GetValue()
        account.save_password = self.save_password.GetValue()
        if not account.password:
            raise ValueError("يرجى كتابة كلمة المرور.")
        account.oauth_provider = ""
        account.oauth_client_id = ""
        account.oauth_client_secret = ""
        account.oauth_access_token = ""
        account.oauth_refresh_token = ""
        account.oauth_token_expiry = 0.0
        account.save_oauth_tokens = False
        self.apply_manual_defaults(account)
        if not self.imap_server.GetValue().strip():
            raise ValueError("يرجى كتابة خادم IMAP.")
        if not self.smtp_server.GetValue().strip():
            raise ValueError("يرجى كتابة خادم SMTP.")
        account.imap_server = self.imap_server.GetValue().strip()
        account.imap_port = self.port_value(self.imap_port, "IMAP")
        account.imap_ssl = self.imap_ssl.GetValue()
        account.smtp_server = self.smtp_server.GetValue().strip()
        account.smtp_port = self.port_value(self.smtp_port, "SMTP")
        account.smtp_ssl = self.smtp_ssl.GetValue()
        account.smtp_starttls = self.smtp_starttls.GetValue()
        account.spam_mailbox = self.spam_mailbox.GetValue().strip()
        return account

    def apply_manual_defaults(self, account: Account) -> None:
        self.apply_selected_manual_provider_defaults(overwrite=False)

    def port_value(self, control: wx.TextCtrl, label: str) -> int:
        try:
            value = int(control.GetValue().strip())
        except ValueError:
            raise ValueError(f"منفذ {label} يجب أن يكون رقما.") from None
        if not 1 <= value <= 65535:
            raise ValueError(f"منفذ {label} يجب أن يكون بين 1 و 65535.")
        return value


class ComposeDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        title: str = "إنشاء بريد إلكتروني",
        to_address: str = "",
        subject: str = "",
        body: str = "",
    ) -> None:
        super().__init__(parent, title=title, size=(680, 560))
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        self.to_address = self._row(panel, root, "إلى:", to_address)
        self.subject = self._row(panel, root, "الموضوع:", subject)

        root.Add(wx.StaticText(panel, label="المحتوى:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.body = wx.TextCtrl(panel, value=body, style=wx.TE_MULTILINE)
        set_accessible(self.body, "محتوى الرسالة", "اكتب محتوى البريد الإلكتروني هنا")
        root.Add(self.body, 1, wx.EXPAND | wx.ALL, 8)

        send_button = wx.Button(panel, id=wx.ID_OK, label="إرسال")
        cancel_button = wx.Button(panel, id=wx.ID_CANCEL, label="إلغاء")
        set_accessible(send_button, "إرسال الرسالة")
        set_accessible(cancel_button, "إلغاء")
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer(1)
        buttons.Add(send_button, 0, wx.ALL, 6)
        buttons.Add(cancel_button, 0, wx.ALL, 6)
        root.Add(buttons, 0, wx.EXPAND)

        panel.SetSizer(root)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        localize_window(self)

    def _row(
        self,
        parent: wx.Window,
        root: wx.BoxSizer,
        label: str,
        value: str,
    ) -> wx.TextCtrl:
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        control = wx.TextCtrl(parent, value=value)
        set_accessible(control, label.replace(":", ""))
        row.Add(control, 1, wx.EXPAND | wx.ALL, 8)
        root.Add(row, 0, wx.EXPAND)
        return control

    def values(self) -> tuple[str, str, str]:
        return (
            self.to_address.GetValue().strip(),
            self.subject.GetValue().strip(),
            self.body.GetValue(),
        )


class BulkDeleteDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, message_count: int) -> None:
        super().__init__(parent, title=tr("تأكيد حذف الرسائل"), size=(620, 230))
        root = wx.BoxSizer(wx.VERTICAL)
        question = wx.StaticText(
            self,
            label=tr(
                f"هل تريد حذف {message_count} رسالة وإرسالها إلى سلة المحذوفات؟"
            ),
        )
        question.Wrap(580)
        set_accessible(question, f"تأكيد حذف {message_count} رسالة")
        root.Add(question, 1, wx.EXPAND | wx.ALL, 16)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        cancel_button = wx.Button(self, wx.ID_CANCEL, label=tr("إلغاء"))
        delete_button = wx.Button(
            self,
            wx.ID_OK,
            label=tr("حذف وإرسال إلى سلة المحذوفات"),
        )
        set_accessible(cancel_button, "إلغاء حذف الرسائل")
        set_accessible(delete_button, f"حذف {message_count} رسالة وإرسالها إلى سلة المحذوفات")
        cancel_button.SetDefault()
        buttons.Add(cancel_button, 0, wx.ALL, 8)
        buttons.Add(delete_button, 0, wx.ALL, 8)
        root.Add(buttons, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)

        self.SetSizer(root)
        apply_layout_direction(self)
        self.CentreOnParent()
        wx.CallAfter(cancel_button.SetFocus)


class MailPage(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        title: str,
        on_selected: Callable[["MailPage", MessageSummary], None],
        on_toggle_read: Callable[["MailPage", MessageSummary], None],
        on_translate: Callable[["MailPage"], None],
        on_reply: Callable[[], None],
        on_toggle_star: Callable[["MailPage"], None],
        on_toggle_pin: Callable[["MailPage"], None],
        on_delete: Callable[["MailPage"], None],
        on_bulk_action: Callable[["MailPage", str, list[MessageSummary]], None],
        on_filter_changed: Callable[["MailPage"], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.messages: list[MessageSummary] = []
        self.trash_messages: list[MessageSummary] = []
        self.trash_mailbox = ""
        self.visible_messages: list[MessageSummary] = []
        self.links: list[LinkItem] = []
        self.viewer_text = ""
        self.viewer_mode = VIEWER_HTML
        self.theme = THEME_LIGHT
        self.link_panel_visible_in_html = False
        self.viewer_action_ranges: list[tuple[int, int, LinkItem]] = []
        self.current_viewer_action_range: tuple[int, int, LinkItem] | None = None
        self.current_content_key: tuple[str, str] | None = None
        self._translation_return_control: wx.Window | None = None
        self._last_items_toggle_at = 0.0
        self._last_context_menu_request_at = 0.0
        self._html_focus_call: wx.CallLater | None = None
        self._html_viewer_active = False
        self._html_refresh_pending = True
        self._html_focus_after_load = False
        self._suppress_selection_event = False
        self.multi_select_mode = False
        self._multi_selected_keys: set[tuple[str, str]] = set()
        self._control_pressed_alone = False
        self._selection_count_announce_call: wx.CallLater | None = None
        self._multi_mode_notification_call: wx.CallLater | None = None
        self.on_selected = on_selected
        self.on_toggle_read = on_toggle_read
        self.on_translate = on_translate
        self.on_reply = on_reply
        self.on_toggle_star = on_toggle_star
        self.on_toggle_pin = on_toggle_pin
        self.on_delete = on_delete
        self.on_bulk_action = on_bulk_action
        self.on_filter_changed = on_filter_changed
        self._build()

    def _build(self) -> None:
        root = wx.BoxSizer(wx.VERTICAL)
        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        filter_row.Add(wx.StaticText(self, label="التصنيف:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.filter_choice = wx.Choice(self, choices=[tr(label) for label in FILTER_CHOICES])
        self.filter_choice.SetSelection(0)
        set_accessible(self.filter_choice, f"تصنيف {self.title}")
        self.filter_choice.Bind(wx.EVT_CHOICE, self.on_filter)
        filter_row.Add(self.filter_choice, 1, wx.EXPAND | wx.ALL, 6)
        root.Add(filter_row, 0, wx.EXPAND)

        self.list = wx.ListCtrl(self, style=wx.LC_REPORT)
        self.list.EnableCheckBoxes(False)
        self.list.InsertColumn(0, tr("الحالة"), width=120)
        self.list.InsertColumn(1, tr("المرسل"), width=220)
        self.list.InsertColumn(2, tr("الموضوع"), width=300)
        self.list.InsertColumn(3, tr("التاريخ"), width=220)
        set_accessible(
            self.list,
            f"قائمة {self.title}",
            "استخدم الأسهم لاختيار رسالة. اضغط Control وShift وSpace لإظهار مربعات الاختيار وتفعيل التحديد المتعدد.",
        )
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_item_deselected)
        self.list.Bind(wx.EVT_LIST_ITEM_CHECKED, self.on_item_checked)
        self.list.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.on_item_unchecked)
        self.list.Bind(wx.EVT_CHAR_HOOK, self.on_list_key)
        self.list.Bind(wx.EVT_KEY_DOWN, self.on_list_key_down)
        self.list.Bind(wx.EVT_KEY_UP, self.on_list_key_up)
        self.list.Bind(wx.EVT_SET_FOCUS, self.on_message_list_focus)
        root.Add(self.list, 2, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.selection_status = wx.StaticText(self, label="")
        set_accessible(self.selection_status, "حالة التحديد المتعدد")
        self.selection_status.Hide()
        root.Add(self.selection_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        root.Add(wx.StaticText(self, label="نص الرسالة:"), 0, wx.LEFT | wx.RIGHT, 8)
        self.viewer = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
        )
        self.viewer.Hide()
        self.html_viewer = wx.html2.WebView.New(self)
        self._html_message_bridge = False
        try:
            self.html_viewer.EnableContextMenu(False)
        except (AttributeError, NotImplementedError):
            pass
        try:
            self._html_message_bridge = bool(
                self.html_viewer.AddScriptMessageHandler("pamBridge")
            )
        except (AttributeError, NotImplementedError):
            pass
        set_accessible(
            self.html_viewer,
            f"مستعرض نص {self.title}",
            "مستعرض HTML للرسالة. استخدم أوامر قارئ الشاشة أو Tab للتنقل بين الروابط والأزرار، وEnter أو Space لفتح العنصر.",
        )
        self.viewer.Bind(wx.EVT_CHAR_HOOK, self.on_viewer_key)
        self.viewer.Bind(wx.EVT_KEY_DOWN, self.on_viewer_key)
        self.viewer.Bind(wx.EVT_CHAR, self.on_viewer_key)
        self.html_viewer.Bind(wx.html2.EVT_WEBVIEW_NAVIGATING, self.on_html_viewer_navigating)
        self.html_viewer.Bind(wx.html2.EVT_WEBVIEW_LOADED, self.on_html_viewer_loaded)
        self.html_viewer.Bind(wx.EVT_LEFT_DOWN, self.on_html_viewer_pointer_focus)
        self.html_viewer.Bind(wx.EVT_CONTEXT_MENU, self.on_html_context_menu)
        if self._html_message_bridge:
            self.html_viewer.Bind(
                wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED,
                self.on_html_script_message,
            )
        self.viewer.Bind(wx.EVT_CONTEXT_MENU, self.on_message_context_menu)
        self.list.Bind(wx.EVT_CONTEXT_MENU, self.on_message_context_menu)
        self.viewer_sizer_item = root.Add(self.viewer, 3, wx.EXPAND | wx.ALL, 8)
        self.html_viewer_sizer_item = root.Add(self.html_viewer, 3, wx.EXPAND | wx.ALL, 8)

        self.link_panel = wx.Panel(self)
        link_row = wx.BoxSizer(wx.HORIZONTAL)
        link_row.Add(
            wx.StaticText(self.link_panel, label="مستعرض العناصر:"),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.ALL,
            6,
        )
        self.link_list = wx.ListBox(self.link_panel)
        set_accessible(
            self.link_list,
            f"مستعرض العناصر {self.title}",
            "اضغط Enter أو Space لفتح الرابط أو الزر أو فتح المرفق المحدد محليا",
        )
        self.link_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_link)
        self.link_list.Bind(wx.EVT_CHAR_HOOK, self.on_link_key)
        self.link_list.Bind(wx.EVT_CONTEXT_MENU, self.on_message_context_menu)
        link_row.Add(self.link_list, 1, wx.EXPAND | wx.ALL, 6)
        self.actions_button = wx.Button(self.link_panel, label="إجراءات الرسالة")
        set_accessible(self.actions_button, f"قائمة إجراءات رسالة {self.title}")
        self.actions_button.Bind(wx.EVT_BUTTON, self.on_actions_button)
        link_row.Add(self.actions_button, 0, wx.ALL, 6)
        self.link_panel.SetSizer(link_row)
        root.Add(self.link_panel, 1, wx.EXPAND)

        self.SetSizer(root)
        self.localize_ui()

    def localize_ui(self) -> None:
        self.title = tr(self.title)
        localize_window(self)
        set_localized_items(self.filter_choice, FILTER_CHOICES)
        for index, label in enumerate(("الحالة", "المرسل", "الموضوع", "التاريخ")):
            column = self.list.GetColumn(index)
            column.SetText(tr(label))
            self.list.SetColumn(index, column)
        self.apply_filter()

    def selected_filter_key(self) -> str:
        keys = ("all", "starred", "unread", "read", "trash")
        selection = self.filter_choice.GetSelection()
        return keys[selection] if 0 <= selection < len(keys) else "all"

    def set_messages(self, messages: list[MessageSummary]) -> None:
        self.messages = self.sort_newest_first(messages)
        self.apply_filter()
        self.set_viewer_text("")
        self.set_links([])
        self.current_content_key = None

    def set_trash_messages(self, messages: list[MessageSummary], mailbox: str = "") -> None:
        self.trash_messages = self.sort_newest_first(messages)
        self.trash_mailbox = mailbox
        self.apply_filter()
        if self.current_content_key and self.current_content_key not in self.all_message_keys():
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def merge_messages(self, messages: list[MessageSummary]) -> bool:
        if not messages and self.messages:
            return False

        selected_key = self.selected_message_key()
        existing_by_key = {self.message_key(message): message for message in self.messages}
        merged: list[MessageSummary] = []
        seen: set[tuple[str, str]] = set()

        for message in messages:
            key = self.message_key(message)
            old = existing_by_key.get(key)
            if old and old.is_pinned:
                message.is_pinned = True
            merged.append(message)
            seen.add(key)

        for message in self.messages:
            key = self.message_key(message)
            if key not in seen:
                merged.append(message)

        self.messages = self.sort_newest_first(merged)
        self.apply_filter(preserve_key=selected_key)
        if self.current_content_key and self.current_content_key not in self.all_message_keys():
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None
        return True

    def reconcile_recent_messages(self, recent_messages: list[MessageSummary]) -> None:
        selected_key = self.selected_message_key()
        incoming_keys = {self.message_key(message) for message in recent_messages}
        if recent_messages:
            oldest_recent = min(message.sort_timestamp for message in recent_messages)
            older_messages = [
                message
                for message in self.messages
                if self.message_key(message) not in incoming_keys
                and message.sort_timestamp < oldest_recent
            ]
        else:
            older_messages = []
        self.messages = self.sort_newest_first([*recent_messages, *older_messages])
        self.apply_filter(preserve_key=selected_key)
        if self.current_content_key and self.current_content_key not in self.all_message_keys():
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def apply_filter(self, preserve_key: tuple[str, str] | None = None) -> None:
        if preserve_key is None:
            preserve_key = self.focused_message_key() or self.selected_message_key()
        selected_keys = (
            set(self._multi_selected_keys) | self.selected_message_keys()
            if self.multi_select_mode
            else set()
        )
        selected = self.selected_filter_key()
        if selected == "trash":
            self.visible_messages = list(self.trash_messages)
        elif selected == "starred":
            self.visible_messages = [message for message in self.messages if message.is_starred]
        elif selected == "unread":
            self.visible_messages = [message for message in self.messages if not message.is_read]
        elif selected == "read":
            self.visible_messages = [message for message in self.messages if message.is_read]
        else:
            self.visible_messages = list(self.messages)
        self.visible_messages = self.sort_newest_first(self.visible_messages)
        visible_keys = {self.message_key(message) for message in self.visible_messages}
        self._multi_selected_keys = selected_keys & visible_keys

        self._suppress_selection_event = True
        self.list.Freeze()
        try:
            self.list.DeleteAllItems()
            restore_index = -1
            for index, message in enumerate(self.visible_messages):
                row = self.list.InsertItem(index, message.status_label)
                self.list.SetItem(row, 1, message.sender)
                self.list.SetItem(row, 2, message.display_subject)
                self.list.SetItem(row, 3, message.date)
                key = self.message_key(message)
                if self.multi_select_mode and key in self._multi_selected_keys:
                    self.list.CheckItem(row, True)
                if preserve_key == key:
                    restore_index = index
            if restore_index >= 0:
                state = wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED
                self.list.SetItemState(
                    restore_index,
                    state,
                    wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                )
                self.list.EnsureVisible(restore_index)
            elif self.multi_select_mode and self.visible_messages:
                self.list.SetItemState(
                    0,
                    wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED,
                    wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED,
                )
        finally:
            self.list.Thaw()
            self._suppress_selection_event = False
        if getattr(self, "multi_select_mode", False):
            self.update_multi_selection_status()

    def on_filter(self, _event: wx.CommandEvent) -> None:
        if self.on_filter_changed and self.selected_filter_key() == "trash":
            self.on_filter_changed(self)
            return
        self.apply_filter()

    def on_list_key(self, event: wx.KeyEvent) -> None:
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_CONTROL:
            self._control_pressed_alone = getattr(self, "multi_select_mode", False)
            event.Skip()
            return
        if event.ControlDown():
            self._control_pressed_alone = False

        if (
            key_code == wx.WXK_SPACE
            and event.ControlDown()
            and event.ShiftDown()
        ):
            self.toggle_multi_selection_mode()
            return

        if getattr(self, "multi_select_mode", False):
            if key_code == wx.WXK_ESCAPE:
                self.exit_multi_selection_mode()
                return
            if key_code in {
                wx.WXK_UP,
                wx.WXK_DOWN,
                wx.WXK_HOME,
                wx.WXK_END,
                wx.WXK_PAGEUP,
                wx.WXK_PAGEDOWN,
            }:
                self.move_multi_selection_focus(key_code)
                return
            if (
                key_code == wx.WXK_SPACE
                and not event.ControlDown()
                and not event.AltDown()
            ):
                self.toggle_focused_message_selection()
                return
            if key_code == wx.WXK_DELETE:
                summaries = self.selected_summaries()
                if summaries:
                    self.on_bulk_action(self, BULK_ACTION_DELETE, summaries)
                else:
                    self.announce_selection_count()
                return

        if key_code == wx.WXK_DELETE:
            if self.selected_summary():
                self.on_delete(self)
                return
        if key_code == wx.WXK_TAB:
            if self.viewer_mode == VIEWER_HTML and not event.ShiftDown():
                self.focus_message_viewer()
                return
            event.Skip()
            return
        if (
            key_code == wx.WXK_SPACE
            and not event.ControlDown()
            and not event.ShiftDown()
            and not event.AltDown()
        ):
            summary = self.selected_summary()
            if summary:
                self.on_toggle_read(self, summary)
                return
        event.Skip()

    def on_list_key_down(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_CONTROL:
            self._control_pressed_alone = getattr(self, "multi_select_mode", False)
        else:
            self._control_pressed_alone = False
        event.Skip()

    def on_list_key_up(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_CONTROL:
            should_announce = self._control_pressed_alone and self.multi_select_mode
            self._control_pressed_alone = False
            if should_announce:
                self.schedule_selection_count_announcement()
                return
        event.Skip()

    def on_message_list_focus(self, event: wx.FocusEvent) -> None:
        self.deactivate_html_viewer()
        event.Skip()

    def on_item_selected(self, event: wx.ListEvent) -> None:
        if self._suppress_selection_event:
            return
        index = event.GetIndex()
        if 0 <= index < len(self.visible_messages):
            row_indices = (
                self.row_selected_indices()
                if hasattr(self, "row_selected_indices")
                else [index]
            )
            selected_count = len(row_indices)
            multi_select_mode = getattr(self, "multi_select_mode", False)
            if selected_count > 1 and not multi_select_mode:
                self.multi_select_mode = True
                self.set_multi_selection_checkboxes(True)
                self._suppress_selection_event = True
                try:
                    for row_index in row_indices:
                        self.list.CheckItem(row_index, True)
                finally:
                    self._suppress_selection_event = False
                self._multi_selected_keys = {
                    self.message_key(self.visible_messages[row_index])
                    for row_index in row_indices
                    if 0 <= row_index < len(self.visible_messages)
                }
                self.update_multi_selection_status()
                self.schedule_multi_selection_mode_notification(
                    f"تم تفعيل وضع التحديد المتعدد. عدد الرسائل المحددة: {selected_count}."
                )
            if (
                not getattr(self, "multi_select_mode", False)
                or not hasattr(self, "focused_index")
                or index == self.focused_index()
            ):
                self.on_selected(self, self.visible_messages[index])

    def on_item_deselected(self, event: wx.ListEvent) -> None:
        if not self._suppress_selection_event:
            event.Skip()

    def on_item_checked(self, event: wx.ListEvent) -> None:
        self.on_item_check_changed(event.GetIndex(), True)

    def on_item_unchecked(self, event: wx.ListEvent) -> None:
        self.on_item_check_changed(event.GetIndex(), False)

    def on_item_check_changed(self, index: int, checked: bool) -> None:
        if self._suppress_selection_event:
            return
        if not 0 <= index < len(self.visible_messages):
            return
        if not self.multi_select_mode:
            self.multi_select_mode = True
            self._multi_selected_keys.clear()
            self.set_multi_selection_checkboxes(True)
        key = self.message_key(self.visible_messages[index])
        if checked:
            self._multi_selected_keys.add(key)
            action = "تم تحديد الرسالة."
        else:
            self._multi_selected_keys.discard(key)
            action = "تم إلغاء تحديد الرسالة."
        self.update_multi_selection_status()
        self.announce_accessible(
            f"{action} عدد الرسائل المحددة: {len(self._multi_selected_keys)}."
        )

    def row_selected_indices(self) -> list[int]:
        indices: list[int] = []
        index = self.list.GetFirstSelected()
        while index >= 0:
            indices.append(index)
            index = self.list.GetNextSelected(index)
        return indices

    def checked_indices(self) -> list[int]:
        return [
            index
            for index in range(len(self.visible_messages))
            if self.list.IsItemChecked(index)
        ]

    def selected_indices(self) -> list[int]:
        if self.multi_select_mode:
            return self.checked_indices()
        return self.row_selected_indices()

    def selected_summaries(self) -> list[MessageSummary]:
        return [
            self.visible_messages[index]
            for index in self.selected_indices()
            if 0 <= index < len(self.visible_messages)
        ]

    def selected_count(self) -> int:
        return len(self.selected_indices())

    def selected_message_keys(self) -> set[tuple[str, str]]:
        return {self.message_key(summary) for summary in self.selected_summaries()}

    def focused_index(self) -> int:
        index = self.list.GetFocusedItem()
        return index if 0 <= index < len(self.visible_messages) else -1

    def focused_summary(self) -> MessageSummary | None:
        index = self.focused_index()
        return self.visible_messages[index] if index >= 0 else None

    def focused_message_key(self) -> tuple[str, str] | None:
        summary = self.focused_summary()
        return self.message_key(summary) if summary else None

    def selected_summary(self) -> MessageSummary | None:
        focused_index = self.focused_index()
        if self.multi_select_mode and focused_index >= 0:
            return self.visible_messages[focused_index]
        if focused_index >= 0 and self.list.GetItemState(
            focused_index,
            wx.LIST_STATE_SELECTED,
        ):
            return self.visible_messages[focused_index]
        index = self.list.GetFirstSelected()
        if 0 <= index < len(self.visible_messages):
            return self.visible_messages[index]
        return None

    def toggle_multi_selection_mode(self) -> None:
        if self.multi_select_mode:
            self.exit_multi_selection_mode()
        else:
            self.enter_multi_selection_mode()

    def set_multi_selection_checkboxes(self, enabled: bool) -> None:
        self.list.EnableCheckBoxes(enabled)
        if enabled:
            description = (
                "وضع التحديد المتعدد. تنقل بالأسهم واضغط Space لتحديد مربع "
                "الرسالة أو إلغاء تحديده. اضغط Control وحده لسماع العدد."
            )
        else:
            description = (
                "قائمة الرسائل. استخدم الأسهم لاختيار رسالة. اضغط Control "
                "وShift وSpace لإظهار مربعات الاختيار وتفعيل التحديد المتعدد."
            )
        self.list.SetToolTip(tr(description))

    def enter_multi_selection_mode(self) -> None:
        focused_index = self.focused_index()
        if focused_index < 0:
            focused_index = self.list.GetFirstSelected()
        if focused_index < 0 and self.visible_messages:
            focused_index = 0
        self.multi_select_mode = True
        self._multi_selected_keys.clear()
        self.set_multi_selection_checkboxes(True)
        self._suppress_selection_event = True
        try:
            for index in range(len(self.visible_messages)):
                if self.list.IsItemChecked(index):
                    self.list.CheckItem(index, False)
            self.list.SetItemState(
                -1,
                0,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            if focused_index >= 0:
                state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
                self.list.SetItemState(
                    focused_index,
                    state,
                    state,
                )
                self.list.EnsureVisible(focused_index)
        finally:
            self._suppress_selection_event = False
        self.update_multi_selection_status()
        self.schedule_multi_selection_mode_notification(
            "تم تفعيل وضع التحديد المتعدد. لا توجد رسائل محددة."
        )

    def exit_multi_selection_mode(self, restore_single_selection: bool = True) -> None:
        focused_index = self.focused_index()
        self.multi_select_mode = False
        self._multi_selected_keys.clear()
        self._control_pressed_alone = False
        if self._selection_count_announce_call is not None:
            self._selection_count_announce_call.Stop()
            self._selection_count_announce_call = None
        self._suppress_selection_event = True
        try:
            for index in range(len(self.visible_messages)):
                if self.list.IsItemChecked(index):
                    self.list.CheckItem(index, False)
            self.set_multi_selection_checkboxes(False)
            self.list.SetItemState(
                -1,
                0,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            if (
                restore_single_selection
                and 0 <= focused_index < len(self.visible_messages)
            ):
                state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
                self.list.SetItemState(focused_index, state, state)
                self.list.EnsureVisible(focused_index)
        finally:
            self._suppress_selection_event = False
        self.schedule_multi_selection_mode_notification(
            "تم إنهاء وضع التحديد المتعدد."
        )
        if (
            restore_single_selection
            and 0 <= focused_index < len(self.visible_messages)
        ):
            self.on_selected(self, self.visible_messages[focused_index])

    def move_multi_selection_focus(self, key_code: int) -> None:
        item_count = len(self.visible_messages)
        if item_count <= 0:
            return
        current = self.focused_index()
        if current < 0:
            current = 0
        page_size = max(1, self.list.GetCountPerPage())
        if key_code == wx.WXK_UP:
            target = current - 1
        elif key_code == wx.WXK_DOWN:
            target = current + 1
        elif key_code == wx.WXK_HOME:
            target = 0
        elif key_code == wx.WXK_END:
            target = item_count - 1
        elif key_code == wx.WXK_PAGEUP:
            target = current - page_size
        else:
            target = current + page_size
        target = max(0, min(target, item_count - 1))
        if target == current:
            if key_code in {wx.WXK_UP, wx.WXK_HOME, wx.WXK_PAGEUP}:
                self.announce_accessible("بداية قائمة الرسائل.")
            else:
                self.announce_accessible("نهاية قائمة الرسائل.")
            return
        self._suppress_selection_event = True
        try:
            self.list.SetItemState(
                -1,
                0,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
            self.list.SetItemState(target, state, state)
        finally:
            self._suppress_selection_event = False
        self.list.EnsureVisible(target)
        self.on_selected(self, self.visible_messages[target])

    def toggle_focused_message_selection(self) -> None:
        index = self.focused_index()
        if index < 0:
            self.announce_selection_count()
            return
        summary = self.visible_messages[index]
        key = self.message_key(summary)
        new_state = not self.list.IsItemChecked(index)
        self._suppress_selection_event = True
        try:
            self.list.CheckItem(index, new_state)
        finally:
            self._suppress_selection_event = False
        if new_state:
            self._multi_selected_keys.add(key)
            action = "تم تحديد الرسالة."
        else:
            self._multi_selected_keys.discard(key)
            action = "تم إلغاء تحديد الرسالة."
        self.announce_accessible(
            f"{action} عدد الرسائل المحددة: {len(self._multi_selected_keys)}."
        )

    def update_multi_selection_status(self) -> None:
        if not self.multi_select_mode:
            return
        self._multi_selected_keys = self.selected_message_keys()
        count = len(self._multi_selected_keys)
        message = tr(f"وضع التحديد المتعدد. عدد الرسائل المحددة: {count}.")
        self.selection_status.SetLabel(message)
        self.selection_status.SetName(message)
        if not self.selection_status.IsShown():
            self.selection_status.Show()
            self.Layout()

    def announce_selection_count(self) -> None:
        self._multi_selected_keys = self.selected_message_keys()
        self.announce_accessible(
            f"عدد الرسائل المحددة: {len(self._multi_selected_keys)}."
        )

    def schedule_selection_count_announcement(self) -> None:
        if self._selection_count_announce_call is not None:
            self._selection_count_announce_call.Stop()
        self._selection_count_announce_call = wx.CallLater(
            250,
            self._announce_scheduled_selection_count,
        )

    def _announce_scheduled_selection_count(self) -> None:
        self._selection_count_announce_call = None
        if self.multi_select_mode and self.list.HasFocus():
            self.announce_selection_count()

    def schedule_multi_selection_mode_notification(self, message: str) -> None:
        if self._multi_mode_notification_call is not None:
            self._multi_mode_notification_call.Stop()
        self._multi_mode_notification_call = wx.CallLater(
            300,
            self._show_multi_selection_mode_notification,
            message,
        )

    def _show_multi_selection_mode_notification(self, message: str) -> None:
        self._multi_mode_notification_call = None
        parent = wx.GetTopLevelParent(self)
        if parent and hasattr(parent, "show_notification"):
            parent.show_notification(message)
        else:
            self.announce_accessible(message)

    def announce_accessible(self, message: str) -> None:
        localized = tr(message)
        self.selection_status.SetLabel(localized)
        self.selection_status.SetName(localized)
        if not self.selection_status.IsShown():
            self.selection_status.Show()
            self.Layout()
        self.set_status(message)
        announce_to_screen_reader(self.selection_status, message)

    def show_content(self, content: MessageContent) -> None:
        self.current_content_key = self.message_key(content.summary)
        body = normalize_message_text(content.text)
        self.set_links(content.links)
        self.set_viewer_action_ranges(body, content.links)
        if self.viewer_mode == VIEWER_HTML:
            self.link_panel_visible_in_html = False
            self.update_link_panel_visibility()
        self.set_viewer_text(body)
        self.update_message_row(content.summary)

    def set_viewer_text(self, text: str) -> None:
        self.viewer_text = text
        try:
            self.viewer.ChangeValue(text)
        except AttributeError:
            self.viewer.SetValue(text)
        if self.viewer_mode == VIEWER_SIMPLE:
            self.show_plain_viewer()
            return
        self._html_refresh_pending = True
        if self._html_viewer_active:
            self.refresh_html_viewer(focus_start=True)
        else:
            self.show_plain_viewer()

    def refresh_html_viewer(self, *, focus_start: bool) -> None:
        self.show_html_viewer()
        self._html_focus_after_load = focus_start
        try:
            self.html_viewer.SetPage(self.message_html(self.viewer_text), "about:blank")
        except Exception:
            self._html_refresh_pending = True
            self._html_viewer_active = False
            self._html_focus_after_load = False
            self.show_plain_viewer()
            return
        self._html_refresh_pending = False

    def activate_html_viewer(self) -> None:
        self._html_viewer_active = True
        if self._html_refresh_pending:
            self.refresh_html_viewer(focus_start=True)
            return
        self.focus_html_document_start()

    def deactivate_html_viewer(self) -> None:
        self._html_viewer_active = False
        self._html_focus_after_load = False
        if self.viewer_mode == VIEWER_HTML:
            self.show_plain_viewer()

    def focus_html_document_start(self) -> None:
        if not self._html_viewer_active:
            return
        self.html_viewer.SetFocus()
        try:
            self.html_viewer.RunScript(
                "var messageElement = document.getElementById('message'); "
                "if (messageElement) { "
                "messageElement.focus(); "
                "if (document.body && document.body.createTextRange) { "
                "var textRange = document.body.createTextRange(); "
                "textRange.moveToElementText(messageElement); "
                "textRange.collapse(true); textRange.select(); "
                "} else if (document.createRange && window.getSelection) { "
                "var textSelection = window.getSelection(); "
                "var textRangeModern = document.createRange(); "
                "textRangeModern.selectNodeContents(messageElement); "
                "textRangeModern.collapse(true); "
                "textSelection.removeAllRanges(); "
                "textSelection.addRange(textRangeModern); "
                "} } window.scrollTo(0, 0);"
            )
        except (AttributeError, RuntimeError):
            pass

    def set_viewer_mode(self, mode: str) -> None:
        self.viewer_mode = VIEWER_SIMPLE if mode == VIEWER_SIMPLE else VIEWER_HTML
        self.deactivate_html_viewer()
        self._html_refresh_pending = True
        self.link_panel_visible_in_html = False
        self.update_link_panel_visibility()
        self.set_viewer_text(self.viewer_text)

    def set_theme(self, theme: str) -> None:
        self.theme = THEME_DARK if theme == THEME_DARK else THEME_LIGHT
        self.apply_viewer_colours()
        self.set_viewer_text(self.viewer_text)

    def apply_viewer_colours(self) -> None:
        if self.theme == THEME_DARK:
            background = wx.Colour(32, 33, 36)
            foreground = wx.Colour(245, 245, 245)
        else:
            background = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            foreground = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        self.viewer.SetBackgroundColour(background)
        self.viewer.SetForegroundColour(foreground)

    def show_html_viewer(self) -> None:
        self.viewer.Show(False)
        self.html_viewer.Show(True)
        self.viewer_sizer_item.Show(False)
        self.html_viewer_sizer_item.Show(True)
        self.update_link_panel_visibility()
        self.layout_viewer_area()

    def show_plain_viewer(self) -> None:
        self.html_viewer.Show(False)
        self.viewer.Show(True)
        self.html_viewer_sizer_item.Show(False)
        self.viewer_sizer_item.Show(True)
        self.update_link_panel_visibility()
        self.layout_viewer_area()

    def layout_viewer_area(self) -> None:
        self.Layout()
        parent = self.GetParent()
        if parent:
            parent.Layout()

    def update_link_panel_visibility(self) -> None:
        if self.viewer_mode == VIEWER_HTML:
            self.link_panel.Show(bool(self.link_panel_visible_in_html))
        else:
            self.link_panel.Show(True)

    def toggle_link_panel_from_viewer(self) -> None:
        if self.viewer_mode != VIEWER_HTML:
            return
        self.link_panel_visible_in_html = not self.link_panel_visible_in_html
        self.update_link_panel_visibility()
        self.layout_viewer_area()
        if self.link_panel_visible_in_html:
            self.deactivate_html_viewer()
            self.link_list.SetFocus()
            self.set_status("تم إظهار مستعرض العناصر.")
        else:
            self.activate_html_viewer()
            self.set_status("تم إخفاء مستعرض العناصر.")

    def toggle_message_and_link_viewers(self) -> None:
        now = time.monotonic()
        if now - self._last_items_toggle_at < 0.2:
            return
        self._last_items_toggle_at = now
        focus = wx.Window.FindFocus()
        if focus in {self.link_panel, self.link_list, self.actions_button}:
            self.focus_message_viewer()
            return
        self.focus_link_panel()

    def focus_link_panel(self) -> None:
        self.deactivate_html_viewer()
        if self.viewer_mode == VIEWER_HTML and not self.link_panel_visible_in_html:
            self.link_panel_visible_in_html = True
            self.update_link_panel_visibility()
            self.layout_viewer_area()
        self.link_list.SetFocus()
        self.set_status("مستعرض العناصر.")

    def focus_message_viewer(self) -> None:
        if self.viewer_mode == VIEWER_HTML:
            if self.link_panel_visible_in_html:
                self.link_panel_visible_in_html = False
                self.update_link_panel_visibility()
                self.layout_viewer_area()
            self.activate_html_viewer()
        else:
            self.viewer.SetFocus()
        self.set_status("مستعرض الرسالة.")

    def focus_message_list(self) -> None:
        self.deactivate_html_viewer()
        self.list.SetFocus()
        self.set_status("قائمة الرسائل.")

    def focus_list_index(self, index: int) -> None:
        item_count = self.list.GetItemCount()
        if item_count <= 0:
            self.focus_message_list()
            return
        target_index = max(0, min(index, item_count - 1))
        state_mask = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
        self.list.SetItemState(-1, 0, state_mask)
        self.list.SetItemState(target_index, state_mask, state_mask)
        self.list.EnsureVisible(target_index)
        self.focus_message_list()

    @staticmethod
    def previous_message_index(deleted_index: int) -> int:
        return max(0, deleted_index - 1)

    def message_html(self, text: str) -> str:
        content = self.message_html_content(text)
        message_label = html.escape(tr("نص الرسالة"), quote=True)
        if self.theme == THEME_DARK:
            background = "#202124"
            foreground = "#f5f5f5"
            link_colour = "#8ab4f8"
            button_background = "#303134"
            button_foreground = "#f5f5f5"
            button_border = "#8a8a8a"
        else:
            background = "#fff"
            foreground = "#111"
            link_colour = "#0645ad"
            button_background = "#f3f4f6"
            button_foreground = "#111"
            button_border = "#767676"
        return f"""<!doctype html>
<html lang="{LANGUAGE_ENGLISH if not is_rtl() else LANGUAGE_ARABIC}" dir="auto">
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: "Segoe UI", Tahoma, Arial, sans-serif;
    font-size: 18px;
    line-height: 1.65;
    margin: 12px;
    color: {foreground};
    background: {background};
}}
article {{
    white-space: pre-wrap;
}}
a, button {{
    font: inherit;
}}
a {{
    color: {link_colour};
}}
a[role="button"], button {{
    display: inline;
    color: {button_foreground};
    background: {button_background};
    border: 1px solid {button_border};
    padding: 1px 6px;
}}
a:focus, button:focus {{
    outline: 3px solid #005fcc;
    outline-offset: 2px;
}}
</style>
</head>
<body>
<article id="message" tabindex="0" aria-label="{message_label}">{content}</article>
<script>
function pamSend(command) {{
    if (window.pamBridge && typeof window.pamBridge.postMessage === "function") {{
        window.pamBridge.postMessage(command);
        return;
    }}
    window.location.href = "pam:" + command;
}}
document.addEventListener("keydown", function (event) {{
    if (event.ctrlKey && !event.altKey && !event.metaKey && event.code === "Space") {{
        event.preventDefault();
        pamSend("focus-list");
    }} else if (event.ctrlKey && !event.altKey && !event.metaKey && (event.code === "Enter" || event.code === "NumpadEnter")) {{
        event.preventDefault();
        pamSend("toggle-items");
    }} else if ((event.shiftKey && event.code === "F10") || event.key === "ContextMenu") {{
        event.preventDefault();
        pamSend("context-menu:keyboard");
    }}
}});
</script>
</body>
</html>"""

    def message_html_content(self, text: str) -> str:
        pieces: list[str] = []
        position = 0
        for start, end, item in self.viewer_action_ranges:
            if start < position or end > len(text):
                continue
            pieces.append(html.escape(text[position:start]))
            label = html.escape(text[start:end] or item.text or item.url)
            pieces.append(self.message_html_action(label, item))
            position = end
        pieces.append(html.escape(text[position:]))
        return "".join(pieces) or tr("لا يوجد نص قابل للعرض داخل هذه الرسالة.")

    def message_html_action(self, label: str, item: LinkItem) -> str:
        kind = "button" if item.is_button else "link"
        if item.url:
            href = html.escape(item.url, quote=True)
            role = ' role="button"' if item.is_button else ""
            css_class = "pam-button" if item.is_button else "pam-link"
            return f'<a class="{css_class}" data-pam-kind="{kind}" href="{href}"{role}>{label}</a>'
        if item.is_button:
            return f'<button type="button" data-pam-kind="button">{label}</button>'
        return label

    def on_html_viewer_navigating(self, event: wx.html2.WebViewEvent) -> None:
        url = event.GetURL()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "pam" and self.handle_html_command(parsed.path):
            event.Veto()
            return
        try:
            navigation_action = event.GetNavigationAction()
        except AttributeError:
            navigation_action = event.GetNavigationType()
        if navigation_action != wx.html2.WEBVIEW_NAV_ACTION_USER:
            return
        if parsed.scheme in {"http", "https", "mailto"}:
            event.Veto()
            webbrowser.open(url)
            return
        if parsed.scheme and parsed.scheme not in {"about"}:
            event.Veto()

    def on_html_viewer_loaded(self, _event: wx.html2.WebViewEvent) -> None:
        if not self._html_viewer_active or not self._html_focus_after_load:
            return
        self._html_focus_after_load = False
        wx.CallAfter(self.focus_html_document_start)

    def on_html_viewer_pointer_focus(self, event: wx.MouseEvent) -> None:
        if not self._html_viewer_active:
            self.activate_html_viewer()
        event.Skip()

    def on_html_script_message(self, event: wx.html2.WebViewEvent) -> None:
        if event.GetMessageHandler() != "pamBridge":
            return
        self.handle_html_command(event.GetString())

    def handle_html_command(self, command: str) -> bool:
        action = command.partition(":")[0].partition("?")[0]
        if action == "focus-list":
            self.schedule_html_focus_action(self.focus_message_list)
            return True
        if action == "toggle-items":
            self.schedule_html_focus_action(self.toggle_message_and_link_viewers)
            return True
        if action == "context-menu":
            self.request_html_context_menu()
            return True
        return False

    def schedule_html_focus_action(self, action: Callable[[], None]) -> None:
        if self._html_focus_call and self._html_focus_call.IsRunning():
            self._html_focus_call.Stop()
        self._html_focus_call = wx.CallLater(75, action)

    def on_html_context_menu(self, _event: wx.ContextMenuEvent) -> None:
        self.request_html_context_menu()

    def request_html_context_menu(self) -> None:
        now = time.monotonic()
        if now - self._last_context_menu_request_at < 0.3:
            return
        self._last_context_menu_request_at = now
        wx.CallAfter(
            self.show_message_context_menu,
            self.html_viewer,
            self.has_translatable_content(),
        )

    def begin_message_load(self) -> None:
        self.set_links([])
        self.current_content_key = None
        self.set_viewer_text(tr("جار تحميل الرسالة..."))

    def set_viewer_action_ranges(self, text: str, links: list[LinkItem]) -> None:
        self.viewer_action_ranges = []
        self.current_viewer_action_range = None
        offsets: dict[str, int] = {}
        for link in links:
            if link.is_attachment:
                continue
            if self.link_has_viewer_range(text, link):
                self.viewer_action_ranges.append((link.activation_start, link.activation_end, link))
                continue
            for candidate in self.viewer_activation_candidates(text, link):
                found = self.find_viewer_action_range(text, candidate, offsets)
                if found is None:
                    continue
                start, end = found
                self.viewer_action_ranges.append((start, end, link))
                break
        self.viewer_action_ranges.sort(key=lambda action_range: action_range[0])

    def link_has_viewer_range(self, text: str, link: LinkItem) -> bool:
        return (
            0 <= link.activation_start < link.activation_end <= len(text)
            and bool(text[link.activation_start : link.activation_end].strip())
        )

    def viewer_activation_candidates(self, text: str, link: LinkItem) -> list[str]:
        candidates: list[str] = []
        if link.activation_text:
            candidates.append(link.activation_text)
        else:
            nearby_generic = self.nearby_generic_activation_text(text, link.text)
            if nearby_generic:
                candidates.append(nearby_generic)
        candidates.extend([link.text, link.url])
        unique_candidates: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            candidate = " ".join(candidate.split()).strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)
        return unique_candidates

    def nearby_generic_activation_text(self, text: str, title: str) -> str:
        title = " ".join(title.split()).strip()
        if not title:
            return ""
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if title not in line:
                continue
            for neighbor in (index, index + 1, index - 1):
                if 0 <= neighbor < len(lines):
                    candidate_line = lines[neighbor]
                    for generic_text in INLINE_GENERIC_LINK_TEXTS:
                        if generic_text in candidate_line:
                            return generic_text
        return ""

    def find_viewer_action_range(
        self,
        text: str,
        candidate: str,
        offsets: dict[str, int],
    ) -> tuple[int, int] | None:
        start = text.find(candidate, offsets.get(candidate, 0))
        if start == -1:
            start = text.find(candidate)
        if start == -1:
            return None
        end = start + len(candidate)
        offsets[candidate] = end
        return start, end

    def update_message_row(self, summary: MessageSummary) -> None:
        key = self.message_key(summary)
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                if self.message_key(message) == key:
                    message.is_read = summary.is_read
                    message.is_starred = summary.is_starred
                    message.is_pinned = summary.is_pinned
                    break
        for index, message in enumerate(self.visible_messages):
            if self.message_key(message) == key:
                message.is_read = summary.is_read
                message.is_starred = summary.is_starred
                message.is_pinned = summary.is_pinned
                self.list.SetItem(index, 0, message.status_label)
                self.list.SetItem(index, 1, message.sender)
                self.list.SetItem(index, 2, message.display_subject)
                self.list.SetItem(index, 3, message.date)
                break

    def update_message_read_state(self, summary: MessageSummary, is_read: bool) -> None:
        key = self.message_key(summary)
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                if self.message_key(message) == key:
                    message.is_read = is_read
                    summary = message
                    break
        selected_filter = self.selected_filter_key()
        if selected_filter in {"unread", "read"}:
            self.apply_filter(preserve_key=key)
            return
        for index, message in enumerate(self.visible_messages):
            if self.message_key(message) == key:
                self.list.SetItem(index, 0, message.status_label)
                break

    def selected_message_key(self) -> tuple[str, str] | None:
        summary = self.selected_summary()
        return self.message_key(summary) if summary else None

    def message_key(self, summary: MessageSummary) -> tuple[str, str]:
        return summary.mailbox, summary.uid

    def all_message_keys(self) -> set[tuple[str, str]]:
        return {
            self.message_key(message)
            for messages in (self.messages, self.trash_messages)
            for message in messages
        }

    def sort_newest_first(self, messages: list[MessageSummary]) -> list[MessageSummary]:
        return sorted(messages, key=self.message_sort_key, reverse=True)

    def message_sort_key(self, message: MessageSummary) -> tuple[float, float, int, str]:
        try:
            uid_value = int(message.uid)
        except ValueError:
            uid_value = 0
        return float(message.is_pinned), message.sort_timestamp, uid_value, message.date

    def set_links(self, links: list[LinkItem]) -> None:
        self.links = links
        self.link_list.Set(self.resource_labels(links))
        if links:
            self.link_list.SetSelection(0)
        else:
            self.viewer_action_ranges = []
            self.current_viewer_action_range = None

    def update_message_flags(self, summary: MessageSummary) -> None:
        key = self.message_key(summary)
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                if self.message_key(message) == key:
                    message.is_read = summary.is_read
                    message.is_starred = summary.is_starred
                    message.is_pinned = summary.is_pinned
                    break
        self.messages = self.sort_newest_first(self.messages)
        self.trash_messages = self.sort_newest_first(self.trash_messages)
        self.apply_filter(preserve_key=key)

    def update_message_flags_by_uid(self, summary: MessageSummary) -> None:
        selected_key = self.selected_message_key()
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                if message.uid != summary.uid:
                    continue
                message.is_read = summary.is_read
                message.is_starred = summary.is_starred
                message.is_pinned = summary.is_pinned
        self.messages = self.sort_newest_first(self.messages)
        self.trash_messages = self.sort_newest_first(self.trash_messages)
        self.apply_filter(preserve_key=selected_key)

    def update_message_flags_bulk(
        self,
        summaries: list[MessageSummary],
        match_uid: bool = False,
    ) -> None:
        preserve_key = self.focused_message_key() or self.selected_message_key()
        by_key = {self.message_key(summary): summary for summary in summaries}
        by_uid = {summary.uid: summary for summary in summaries}
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                source = (
                    by_uid.get(message.uid)
                    if match_uid
                    else by_key.get(self.message_key(message))
                )
                if not source:
                    continue
                message.is_read = source.is_read
                message.is_starred = source.is_starred
                message.is_pinned = source.is_pinned
        self.messages = self.sort_newest_first(self.messages)
        self.trash_messages = self.sort_newest_first(self.trash_messages)
        self.apply_filter(preserve_key=preserve_key)

    def remove_message(self, summary: MessageSummary) -> None:
        key = self.message_key(summary)
        self.messages = [message for message in self.messages if self.message_key(message) != key]
        self.trash_messages = [message for message in self.trash_messages if self.message_key(message) != key]
        self.visible_messages = [message for message in self.visible_messages if self.message_key(message) != key]
        self.apply_filter()
        if self.current_content_key == key:
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def remove_messages_bulk(
        self,
        summaries: list[MessageSummary],
        match_uid: bool = False,
    ) -> None:
        keys = {self.message_key(summary) for summary in summaries}
        uids = {summary.uid for summary in summaries}

        def keep(message: MessageSummary) -> bool:
            if match_uid:
                return message.uid not in uids
            return self.message_key(message) not in keys

        self.messages = [message for message in self.messages if keep(message)]
        self.trash_messages = [
            message for message in self.trash_messages if keep(message)
        ]
        if match_uid:
            self._multi_selected_keys = {
                key for key in self._multi_selected_keys if key[1] not in uids
            }
        else:
            self._multi_selected_keys.difference_update(keys)
        self.apply_filter()
        if self.current_content_key and (
            self.current_content_key in keys
            or match_uid
            and self.current_content_key[1] in uids
        ):
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def remove_message_by_uid(self, uid: str) -> None:
        self.messages = [message for message in self.messages if message.uid != uid]
        self.trash_messages = [message for message in self.trash_messages if message.uid != uid]
        self.visible_messages = [message for message in self.visible_messages if message.uid != uid]
        self.apply_filter()
        if self.current_content_key and self.current_content_key[1] == uid:
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def on_open_link(self, _event: wx.CommandEvent) -> None:
        link = self.selected_link()
        if not link:
            return
        self.open_item(link)

    def on_viewer_key(self, event: wx.KeyEvent) -> None:
        if self.handle_viewer_key(event):
            return
        event.Skip()

    def handle_viewer_key(self, event: wx.KeyEvent) -> bool:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            item = self.viewer_item_at_caret()
            if item:
                self.open_item(item)
                return True
        return False

    def viewer_shortcut_key(self, event: wx.KeyEvent) -> str:
        if event.ControlDown() or event.AltDown() or event.CmdDown():
            return ""
        key_code = event.GetUnicodeKey()
        if key_code in {wx.WXK_NONE, 0}:
            key_code = event.GetKeyCode()
        try:
            return chr(key_code).lower()
        except (OverflowError, ValueError):
            return ""

    def move_to_viewer_action(self, buttons: bool, direction: int) -> None:
        ranges = [
            action_range
            for action_range in self.viewer_action_ranges
            if action_range[2].is_button == buttons
        ]
        item_name = self.viewer_action_group_name(buttons)
        if not ranges:
            self.set_status(f"لا يوجد {item_name} في الرسالة الحالية.")
            return

        current_index = self.current_viewer_action_index(ranges)
        if current_index is not None:
            target = ranges[(current_index + direction) % len(ranges)]
        elif direction > 0:
            position = self.current_viewer_position()
            target = next((action_range for action_range in ranges if action_range[0] >= position), ranges[0])
        else:
            position = self.current_viewer_position()
            target = next((action_range for action_range in reversed(ranges) if action_range[1] <= position), ranges[-1])
        self.select_viewer_action(target, self.viewer_action_item_name(target[2]))

    def current_viewer_action_index(self, ranges: list[tuple[int, int, LinkItem]]) -> int | None:
        position = self.current_viewer_position()
        for index, (start, end, _item) in enumerate(ranges):
            if start <= position <= end:
                return index
        if self.current_viewer_action_range in ranges:
            return ranges.index(self.current_viewer_action_range)
        return None

    def viewer_action_group_name(self, buttons: bool) -> str:
        return tr("زر") if buttons else tr("رابط")

    def viewer_action_item_name(self, item: LinkItem) -> str:
        return tr("زر") if item.is_button else tr("رابط")

    def select_viewer_action(self, action_range: tuple[int, int, LinkItem], item_name: str) -> None:
        start, end, item = action_range
        self.current_viewer_action_range = action_range
        self.viewer.SetFocus()
        self.viewer.ShowPosition(start)
        self.viewer.SetInsertionPoint(start)
        self.set_status(f"{item_name}: {item.text or item.url}")

    def viewer_item_at_caret(self) -> LinkItem | None:
        position = self.current_viewer_position()
        for start, end, item in self.viewer_action_ranges:
            if start <= position <= end:
                return item

        line_start, line_end = self.current_viewer_line_bounds(position)
        line_items = [
            item
            for start, end, item in self.viewer_action_ranges
            if line_start <= start and end <= line_end
        ]
        if len(line_items) == 1:
            return line_items[0]
        return None

    def current_viewer_position(self) -> int:
        text = self.viewer.GetValue()
        return max(0, min(self.viewer.GetInsertionPoint(), len(text)))

    def current_viewer_line_bounds(self, position: int) -> tuple[int, int]:
        text = self.viewer.GetValue()
        start = text.rfind("\n", 0, position) + 1
        end = text.find("\n", position)
        if end == -1:
            end = len(text)
        return start, end

    def open_item(self, link: LinkItem) -> None:
        if link.is_attachment:
            self.open_attachment(link)
            return
        if link.url:
            webbrowser.open(link.url)
            return
        if link.is_button:
            self.set_status("هذا الزر لا يحتوي على رابط قابل للفتح.")

    def on_link_key(self, event: wx.KeyEvent) -> None:
        if event.ControlDown() and event.GetKeyCode() == wx.WXK_SPACE:
            self.focus_message_list()
            return
        if event.ControlDown() and event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER}:
            self.toggle_message_and_link_viewers()
            return
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_open_link(wx.CommandEvent())
            return
        event.Skip()

    def resource_labels(self, links: list[LinkItem]) -> list[str]:
        link_index = 0
        button_index = 0
        attachment_index = 0
        labels: list[str] = []
        for link in links:
            if link.is_attachment:
                attachment_index += 1
                labels.append(tr(f"مرفق {attachment_index}: {link.label}"))
            elif link.is_button:
                button_index += 1
                labels.append(tr(f"زر {button_index}: {link.label}"))
            else:
                link_index += 1
                labels.append(tr(f"رابط {link_index}: {link.label}"))
        return labels

    def open_attachment(self, item: LinkItem) -> None:
        try:
            path = self.write_attachment_to_folder(item, self.opened_attachments_dir())
            if hasattr(os, "startfile"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                webbrowser.open(path.as_uri())
        except OSError as exc:
            wx.MessageBox(str(exc), "تعذر فتح المرفق", wx.OK | wx.ICON_ERROR, self)
            return
        except RuntimeError as exc:
            wx.MessageBox(str(exc), "تعذر فتح المرفق", wx.OK | wx.ICON_INFORMATION, self)
            return
        self.set_status(f"تم فتح المرفق محليا: {path.name}")

    def save_attachment(self, item: LinkItem) -> None:
        default_name = Path(item.filename or item.text or "attachment").name or "attachment"
        dialog = wx.FileDialog(
            self,
            tr("حفظ المرفق"),
            defaultFile=default_name,
            wildcard=tr("كل الملفات (*.*)|*.*"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            self.write_attachment_to_path(item, Path(dialog.GetPath()))
        except (OSError, RuntimeError) as exc:
            wx.MessageBox(str(exc), "خطأ في حفظ المرفق", wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            dialog.Destroy()
        wx.MessageBox("تم حفظ المرفق.", "تم الحفظ", wx.OK | wx.ICON_INFORMATION, self)

    def save_all_attachments(self) -> None:
        attachments = self.attachment_items()
        if not attachments:
            wx.MessageBox("لا توجد مرفقات في الرسالة الحالية.", "حفظ المرفقات", wx.OK | wx.ICON_INFORMATION, self)
            return
        dialog = wx.DirDialog(
            self,
            tr("اختر مجلدا لحفظ المرفقات"),
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            folder = Path(dialog.GetPath())
            saved_count = 0
            for item in attachments:
                self.write_attachment_to_folder(item, folder)
                saved_count += 1
        except (OSError, RuntimeError) as exc:
            wx.MessageBox(str(exc), "خطأ في حفظ المرفقات", wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            dialog.Destroy()
        wx.MessageBox(f"تم حفظ {saved_count} مرفق.", "تم الحفظ", wx.OK | wx.ICON_INFORMATION, self)

    def on_actions_button(self, _event: wx.CommandEvent) -> None:
        self.show_message_context_menu(
            self.actions_button,
            translation_enabled=self.has_translatable_content(),
        )

    def on_message_context_menu(self, event: wx.ContextMenuEvent) -> None:
        source = event.GetEventObject()
        translation_enabled = (
            source in {self.viewer, self.html_viewer}
            and self.has_translatable_content()
        )
        control = source if isinstance(source, wx.Window) else self
        self.show_message_context_menu(control, translation_enabled)

    def has_translatable_content(self) -> bool:
        text = self.viewer_text.strip()
        return bool(
            self.selected_summary()
            and text
            and text
            not in {
                tr("جار تحميل الرسالة..."),
                tr("لا يوجد نص قابل للعرض داخل هذه الرسالة."),
            }
        )

    def show_message_context_menu(self, control: wx.Window, translation_enabled: bool) -> None:
        selected_summaries = self.selected_summaries()
        if self.multi_select_mode or len(selected_summaries) > 1:
            self.show_multi_message_context_menu(control, selected_summaries)
            return
        summary = self.selected_summary()
        menu = wx.Menu()
        action_invoked = False
        return_control = self.context_return_control(control)

        def reply_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self.on_reply()
            wx.CallAfter(self.focus_message_list)

        def star_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self.on_toggle_star(self)
            wx.CallAfter(self.focus_message_list)

        def translate_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self._translation_return_control = return_control
            self.on_translate(self)
            wx.CallAfter(self.restore_context_focus, return_control)

        def pin_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self.on_toggle_pin(self)
            wx.CallAfter(self.focus_list_index, 0)

        def delete_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self.on_delete(self)
            wx.CallAfter(self.focus_message_list)

        try:
            reply_item = menu.Append(wx.ID_ANY, tr("رد"))
            star_label = "إزالة التمييز بنجمة" if summary and summary.is_starred else "تمييز بنجمة"
            star_item = menu.Append(wx.ID_ANY, tr(star_label))
            translate_item = menu.Append(wx.ID_ANY, tr("ترجمة"))
            pin_label = "إلغاء التثبيت في الأعلى" if summary and summary.is_pinned else "التثبيت في الأعلى"
            pin_item = menu.Append(wx.ID_ANY, tr(pin_label))
            delete_item = menu.Append(wx.ID_ANY, tr("الحذف والنقل إلى سلة المحذوفات"))

            has_message = summary is not None
            reply_item.Enable(has_message)
            star_item.Enable(has_message)
            translate_item.Enable(has_message and translation_enabled)
            pin_item.Enable(has_message)
            delete_item.Enable(has_message)

            menu.Bind(wx.EVT_MENU, reply_action, reply_item)
            menu.Bind(wx.EVT_MENU, star_action, star_item)
            menu.Bind(wx.EVT_MENU, translate_action, translate_item)
            menu.Bind(wx.EVT_MENU, pin_action, pin_item)
            menu.Bind(wx.EVT_MENU, delete_action, delete_item)
            self.context_menu_popup_owner(control).PopupMenu(menu)
        finally:
            menu.Destroy()
        if not action_invoked:
            wx.CallAfter(self.restore_context_focus, return_control)

    def show_multi_message_context_menu(
        self,
        control: wx.Window,
        summaries: list[MessageSummary],
    ) -> None:
        menu = wx.Menu()
        action_invoked = False
        return_control = self.context_return_control(control)

        def invoke(action: str) -> Callable[[wx.CommandEvent], None]:
            def handler(_event: wx.CommandEvent) -> None:
                nonlocal action_invoked
                action_invoked = True
                self.on_bulk_action(self, action, list(summaries))
                wx.CallAfter(self.focus_message_list)

            return handler

        try:
            count_item = menu.Append(
                wx.ID_ANY,
                tr(f"عدد الرسائل المحددة: {len(summaries)}."),
            )
            count_item.Enable(False)
            menu.AppendSeparator()
            read_item = menu.Append(wx.ID_ANY, tr("تعليم كمقروءة"))
            unread_item = menu.Append(wx.ID_ANY, tr("تعليم كغير مقروءة"))
            star_item = menu.Append(wx.ID_ANY, tr("تمييز الرسائل بنجمة"))
            unstar_item = menu.Append(wx.ID_ANY, tr("إزالة النجمة من الرسائل"))
            pin_item = menu.Append(wx.ID_ANY, tr("تثبيت الرسائل في الأعلى"))
            unpin_item = menu.Append(wx.ID_ANY, tr("إلغاء تثبيت الرسائل"))
            menu.AppendSeparator()
            delete_item = menu.Append(
                wx.ID_ANY,
                tr("حذف الرسائل وإرسالها إلى سلة المحذوفات"),
            )

            has_messages = bool(summaries)
            for item in (
                read_item,
                unread_item,
                star_item,
                unstar_item,
                pin_item,
                unpin_item,
            ):
                item.Enable(has_messages)
            delete_item.Enable(
                has_messages and self.selected_filter_key() != "trash"
            )

            menu.Bind(
                wx.EVT_MENU,
                invoke(BULK_ACTION_MARK_READ),
                read_item,
            )
            menu.Bind(
                wx.EVT_MENU,
                invoke(BULK_ACTION_MARK_UNREAD),
                unread_item,
            )
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_STAR), star_item)
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_UNSTAR), unstar_item)
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_PIN), pin_item)
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_UNPIN), unpin_item)
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_DELETE), delete_item)
            self.context_menu_popup_owner(control).PopupMenu(menu)
        finally:
            menu.Destroy()
        if not action_invoked:
            wx.CallAfter(self.restore_context_focus, return_control)

    def context_menu_popup_owner(self, control: wx.Window) -> wx.Window:
        return self if control is self.html_viewer else control

    def context_return_control(self, control: wx.Window) -> wx.Window:
        if control is self.actions_button:
            return self.actions_button
        if control is self.html_viewer:
            return self.html_viewer
        if control is self.viewer:
            return self.viewer
        return control

    def take_translation_return_control(self) -> wx.Window | None:
        control = self._translation_return_control
        self._translation_return_control = None
        return control

    def restore_context_focus(self, control: wx.Window | None) -> None:
        target = control
        if target is self.html_viewer and self.viewer_mode != VIEWER_HTML:
            target = self.viewer
        try:
            if target and target.IsShownOnScreen() and target.IsEnabled():
                target.SetFocus()
                return
        except Exception:
            pass
        self.focus_message_list()

    def selected_link(self) -> LinkItem | None:
        index = self.link_list.GetSelection()
        if 0 <= index < len(self.links):
            return self.links[index]
        return None

    def attachment_items(self) -> list[LinkItem]:
        return [item for item in self.links if item.is_attachment]

    def opened_attachments_dir(self) -> Path:
        root = Path(tempfile.gettempdir()) / "PowerAccessibleMail" / "opened_attachments"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def write_attachment_to_folder(self, item: LinkItem, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        filename = self.safe_attachment_filename(item)
        path = self.unique_path(folder / filename)
        self.write_attachment_to_path(item, path)
        return path

    def write_attachment_to_path(self, item: LinkItem, path: Path) -> None:
        data = item.attachment_bytes()
        if not data:
            raise RuntimeError("لا توجد بيانات محفوظة لهذا المرفق.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def safe_attachment_filename(self, item: LinkItem) -> str:
        raw_name = Path(item.filename or item.text or "attachment").name.strip() or "attachment"
        invalid_chars = '<>:"/\\|?*'
        cleaned = "".join("_" if char in invalid_chars or ord(char) < 32 else char for char in raw_name)
        cleaned = cleaned.strip(" .") or "attachment"
        return cleaned[:180]

    def unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem or "attachment"
        suffix = path.suffix
        for index in range(2, 1000):
            candidate = path.with_name(f"{stem} ({index}){suffix}")
            if not candidate.exists():
                return candidate
        return path.with_name(f"{stem}-{os.getpid()}{suffix}")

    def set_status(self, message: str) -> None:
        parent = wx.GetTopLevelParent(self)
        if parent and hasattr(parent, "SetStatusText"):
            parent.SetStatusText(message)


class SettingsDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, settings: ProgramSettings) -> None:
        super().__init__(parent, title="الإعدادات", size=(560, 500))
        self.settings = replace(settings)
        self._build()

    def _build(self) -> None:
        apply_layout_direction(self)
        root = wx.BoxSizer(wx.VERTICAL)

        self.focus_intro = wx.TextCtrl(
            self,
            value=tr("لغة البرنامج:"),
            style=wx.TE_READONLY | wx.BORDER_NONE,
        )
        set_accessible(self.focus_intro, "لغة البرنامج")
        root.Add(self.focus_intro, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.language_box = wx.Choice(
            self,
            choices=[tr(label) for label in LANGUAGE_CHOICES],
        )
        self.language_box.SetSelection(self.index_for_value(LANGUAGE_CHOICES, self.settings.language))
        set_accessible(self.language_box, "لغة البرنامج")
        root.Add(self.language_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(wx.StaticText(self, label="مستعرض الرسائل:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.viewer_box = wx.Choice(
            self,
            choices=[tr(label) for label in VIEWER_CHOICES],
        )
        self.viewer_box.SetSelection(self.index_for_value(VIEWER_CHOICES, self.settings.message_viewer))
        set_accessible(
            self.viewer_box,
            "نوع مستعرض الرسائل",
            "مستعرض HTML يعطي الروابط والأزرار كعناصر صفحة، والمستعرض السهل يعرض الرسالة كنص عادي.",
        )
        root.Add(self.viewer_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(wx.StaticText(self, label="نمط الترجمة:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.translation_mode_box = wx.Choice(
            self,
            choices=[tr(label) for label in TRANSLATION_MODE_CHOICES],
        )
        self.translation_mode_box.SetSelection(
            self.index_for_value(TRANSLATION_MODE_CHOICES, self.settings.translation_mode)
        )
        set_accessible(self.translation_mode_box, "نمط الترجمة")
        root.Add(self.translation_mode_box, 0, wx.EXPAND | wx.ALL, 10)

        self.theme_box = wx.RadioBox(
            self,
            label="الوضع الشكلي",
            choices=[tr(label) for label in THEME_CHOICES],
            majorDimension=1,
            style=wx.RA_SPECIFY_ROWS,
        )
        self.theme_box.SetSelection(1 if self.settings.theme == THEME_DARK else 0)
        set_accessible(self.theme_box, "الوضع الشكلي")
        root.Add(self.theme_box, 0, wx.EXPAND | wx.ALL, 10)

        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        if buttons:
            root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(root)
        localize_window(self)
        wx.CallAfter(self.focus_intro.SetFocus)

    def selected_settings(self) -> ProgramSettings:
        return ProgramSettings(
            language=self.value_for_index(self.language_box, LANGUAGE_CHOICES, self.settings.language),
            message_viewer=self.value_for_index(self.viewer_box, VIEWER_CHOICES, self.settings.message_viewer),
            theme=THEME_DARK if self.theme_box.GetSelection() == 1 else THEME_LIGHT,
            translation_mode=self.value_for_index(
                self.translation_mode_box,
                TRANSLATION_MODE_CHOICES,
                self.settings.translation_mode,
            ),
        )

    def value_for_index(self, choice: wx.Choice, mapping: dict[str, str], fallback: str) -> str:
        values = list(mapping.values())
        index = choice.GetSelection()
        return values[index] if 0 <= index < len(values) else fallback

    def index_for_value(self, mapping: dict[str, str], value: str) -> int:
        values = list(mapping.values())
        return values.index(value) if value in values else 0


class UpdateAvailableDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, result: UpdateCheckResult) -> None:
        super().__init__(parent, title=tr("تحديث متاح"), size=(620, 340))
        root = wx.BoxSizer(wx.VERTICAL)
        details = tr(result.message)
        if result.notes:
            details += f"\n\n{tr('ملاحظات الإصدار:')}\n{result.notes}"
        self.details = wx.TextCtrl(
            self,
            value=details,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
        )
        set_accessible(self.details, "تفاصيل التحديث")
        root.Add(self.details, 1, wx.EXPAND | wx.ALL, 12)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.update_button = wx.Button(self, wx.ID_OK, label=tr("تحديث الآن"))
        set_accessible(self.update_button, "تنزيل التحديث وتثبيته")
        self.update_button.SetDefault()
        buttons.Add(self.update_button, 0, wx.ALL, 8)
        self.close_button = wx.Button(self, wx.ID_CANCEL, label=tr("إغلاق"))
        buttons.Add(self.close_button, 0, wx.ALL, 8)
        root.Add(buttons, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)

        self.SetSizer(root)
        apply_layout_direction(self)
        self.CentreOnParent()
        wx.CallAfter(self.update_button.SetFocus)


class UpdateDownloadDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        version: str,
        release_date: str,
        cancel_callback: Callable[[], None],
    ) -> None:
        super().__init__(parent, title=tr("تحديث البرنامج"), size=(560, 280))
        self.cancel_callback = cancel_callback
        root = wx.BoxSizer(wx.VERTICAL)

        self.version_label = wx.StaticText(
            self,
            label=tr(f"الإصدار الجديد: {version}"),
        )
        set_accessible(self.version_label, f"الإصدار الجديد: {version}")
        root.Add(self.version_label, 0, wx.EXPAND | wx.ALL, 12)

        displayed_date = (
            release_date.split("T", 1)[0]
            if release_date
            else tr("غير متوفر")
        )
        update_summary = tr(
            f"الإصدار الجديد: {version}. تاريخ الإطلاق: {displayed_date}."
        )
        self.release_date_label = wx.StaticText(
            self,
            label=tr(f"تاريخ الإطلاق: {displayed_date}"),
        )
        set_accessible(
            self.release_date_label,
            f"تاريخ الإطلاق: {displayed_date}",
        )
        root.Add(
            self.release_date_label,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )

        self.status = wx.StaticText(self, label=tr("جار تنزيل التحديث: 0%."))
        set_accessible(self.status, "حالة تنزيل التحديث")
        root.Add(
            self.status,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )

        self.progress = wx.Gauge(self, range=100)
        self.progress.SetValue(0)
        set_accessible(self.progress, "تقدم تنزيل التحديث")
        root.Add(
            self.progress,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            14,
        )

        self.cancel_button = wx.Button(self, label=tr("إلغاء"))
        set_accessible(self.cancel_button, "إلغاء تنزيل التحديث")
        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
        root.Add(self.cancel_button, 0, wx.ALIGN_CENTER | wx.BOTTOM, 12)

        self.SetSizer(root)
        apply_layout_direction(self)
        self.CentreOnParent()
        self.Bind(wx.EVT_CLOSE, self.on_cancel)
        wx.CallAfter(announce_to_screen_reader, self, update_summary)
        wx.CallAfter(self.cancel_button.SetFocus)

    def set_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            percent = max(0, min(100, round((downloaded / total) * 100)))
            self.progress.SetValue(percent)
            message = tr(f"جار تنزيل التحديث: {percent}%.")
        else:
            self.progress.Pulse()
            megabytes = downloaded / (1024 * 1024)
            message = tr(f"جار تنزيل التحديث: {megabytes:.1f} ميغابايت.")
        self.status.SetLabel(message)
        self.status.SetName(message)
        self.progress.SetName(message)

    def on_cancel(self, event: wx.Event) -> None:
        self.cancel_callback()
        self.cancel_button.Disable()
        message = tr("جار إلغاء تنزيل التحديث.")
        self.status.SetLabel(message)
        self.status.SetName(message)
        if isinstance(event, wx.CloseEvent) and event.CanVeto():
            event.Veto()


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
        self._active_worker_count = 0
        self.pages: dict[str, MailPage] = {}
        self._build()
        self.apply_settings()
        self._load_accounts_to_choice()
        self._start_new_mail_timer()
        self._startup_update_call = wx.CallLater(2500, self.start_startup_update_check)
        self.Centre()
        wx.CallAfter(self.show_welcome_notification)
        wx.CallAfter(self.show_initial_login_if_needed)

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
        self.account_choice.Bind(wx.EVT_CHOICE, self.on_refresh)

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
        self.accel_focus_list = wx.NewIdRef()
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
            wx.AcceleratorEntry(wx.ACCEL_CTRL, wx.WXK_SPACE, self.accel_focus_list),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, wx.WXK_RETURN, self.accel_focus_items),
            wx.AcceleratorEntry(wx.ACCEL_SHIFT, wx.WXK_F10, self.accel_context_menu),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))
        self.Bind(wx.EVT_MENU, self.on_account_options, id=self.accel_add)
        self.Bind(wx.EVT_MENU, self.on_compose, id=self.accel_compose)
        self.Bind(wx.EVT_MENU, self.on_reply, id=self.accel_reply)
        self.Bind(wx.EVT_MENU, self.on_refresh, id=self.accel_refresh)
        self.Bind(wx.EVT_MENU, self.on_translate_current_message, id=self.accel_translate)
        self.Bind(wx.EVT_MENU, lambda _event: self.Close(), id=self.accel_close)
        self.Bind(wx.EVT_MENU, self.on_show_guide, id=self.accel_guide)
        self.Bind(wx.EVT_MENU, self.on_focus_list_accelerator, id=self.accel_focus_list)
        self.Bind(wx.EVT_MENU, self.on_focus_items_accelerator, id=self.accel_focus_items)
        self.Bind(wx.EVT_MENU, self.on_context_menu_accelerator, id=self.accel_context_menu)

    def on_menu_open(self, _event: wx.MenuEvent) -> None:
        if hasattr(self, "translate_menu_item"):
            self.translate_menu_item.Enable(self.can_translate_current_message())

    def on_focus_list_accelerator(self, _event: wx.Event | None = None) -> None:
        page = self.current_page()
        if not page:
            return
        wx.CallAfter(page.focus_message_list)

    def on_focus_items_accelerator(self, _event: wx.Event | None = None) -> None:
        page = self.current_page()
        if not page:
            return
        wx.CallAfter(page.toggle_message_and_link_viewers)

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
            control = page.link_list
        elif focus is page.list:
            control = page.list
        else:
            control = page.html_viewer
        wx.CallAfter(
            page.show_message_context_menu,
            control,
            page.has_translatable_content() and control in {page.viewer, page.html_viewer, page.actions_button},
        )

    def _load_accounts_to_choice(self) -> None:
        self.account_choice.Set([account.label for account in self.accounts])
        if self.accounts:
            self.account_choice.SetSelection(0)
            wx.CallAfter(self.refresh_all)
        else:
            self.SetStatusText("لا يوجد حساب. افتح خيارات الحسابات وإدارتها للبدء.")

    def show_initial_login_if_needed(self) -> None:
        if self.accounts or self._startup_login_shown:
            return
        self._startup_login_shown = True
        dialog = AccountDialog(self, startup=True)
        account_added = self.finish_account_dialog(dialog)
        if not account_added and not self.accounts:
            wx.CallAfter(self.command_list.SetFocus)

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
            wx.CallAfter(self.set_transfer_progress, 45, "جار استلام رسائل سلة المحذوفات من الخادم")
            try:
                messages = self.service.list_messages(account, trash_mailbox, INITIAL_MESSAGE_LIMIT, 50)
            except OAuthError:
                raise
            except (MailError, OSError, imaplib.IMAP4.error, smtplib.SMTPException) as exc:  # type: ignore[name-defined]
                if cached:
                    return trash_mailbox, cached, str(exc)
                raise
            wx.CallAfter(self.set_transfer_progress, 100, "انتهى فحص سلة المحذوفات")
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
            self.SetStatusText("تم حفظ الإعدادات.")
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
            self._load_accounts_to_choice()
            message = "تمت إضافة الحساب بنجاح." if account_added else "تم تحديث الحساب بنجاح."
            self.show_notification(message)
            wx.CallAfter(self.account_choice.SetFocus)
            account_saved = True
        dialog.Destroy()
        return account_saved

    def show_notification(self, message: str, timeout_ms: int = 8000) -> None:
        if self._notification_timer and self._notification_timer.IsRunning():
            self._notification_timer.Stop()
        localized = tr(message)
        self.notification_bar.SetName(localized)
        self.notification_bar.ShowMessage(localized, wx.ICON_INFORMATION)
        self.SetStatusText(message)
        self.main_panel.Layout()
        announce_to_screen_reader(self.notification_bar, message)
        self._notification_timer = wx.CallLater(timeout_ms, self.dismiss_notification)

    def dismiss_notification(self) -> None:
        if self.notification_bar.IsShown():
            self.notification_bar.Dismiss()
            self.main_panel.Layout()
        self._notification_timer = None

    def on_reauthenticate_account(self, _event: wx.Event | None = None) -> None:
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

        try:
            wx.BeginBusyCursor()
            result = run_browser_oauth_flow(provider_id, client_id, client_secret)
        except OAuthError as exc:
            wx.MessageBox(
                tr(str(exc)),
                tr("تعذر إعادة تسجيل الدخول"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()

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

        self._load_accounts_to_choice()
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
            self.pages["inbox"].set_messages([])
            self.pages["spam"].set_messages([])
            self.pages["sent"].set_messages([])
            self.pages["all"].set_messages([])
            for page in self.pages.values():
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
            wx.CallAfter(show_cached, cached_inbox, cached_spam, cached_sent, cached_all)

            wx.CallAfter(self.set_transfer_progress, 10, "جار استلام رسائل الوارد من الخادم")
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
            wx.CallAfter(self.set_transfer_progress, 45, "جار فحص بقية أقسام الرسائل بالتوازي")
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
            wx.CallAfter(self.set_transfer_progress, 100, "انتهى استلام أحدث الرسائل")
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
            wx.CallAfter(self.set_transfer_progress, 35, "جار طلب دفعة أقدم من الخادم")
            messages = self.service.load_older_messages(account, resolved_mailbox)
            wx.CallAfter(self.set_transfer_progress, 100, "انتهى تحميل الدفعة")
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

            wx.CallAfter(update)

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
                wx.CallAfter(self._syncing_page_keys.discard, page_key)

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
                wx.CallAfter(page.focus_message_list)
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
            to_address, subject, body = dialog.values()
            self.send_message(account, to_address, subject, body, None)
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
            to_address, new_subject, body = dialog.values()
            self.send_message(account, to_address, new_subject, body, summary)
        dialog.Destroy()

    def send_message(
        self,
        account: Account,
        to_address: str,
        subject: str,
        body: str,
        reply_to: MessageSummary | None,
    ) -> None:
        if not self.ensure_password(account):
            return

        def work() -> None:
            self.service.send_message(account, to_address, subject, body, reply_to)

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
        return_control = page.take_translation_return_control() if isinstance(_event, MailPage) else wx.Window.FindFocus()

        def work() -> str:
            return translate_text_with_google(text, target_language=self.settings.language)

        def done(translated: str) -> None:
            if self.settings.translation_mode == TRANSLATION_INLINE and page:
                page.set_viewer_action_ranges(translated, [])
                page.set_viewer_text(normalize_message_text(translated))
                self.SetStatusText("تمت ترجمة الرسالة داخل المستعرض.")
                wx.CallAfter(page.focus_message_viewer)
                return
            self.show_translation_dialog(translated)
            if page:
                wx.CallAfter(page.restore_context_focus, return_control)

        def failed(_exc: Exception) -> None:
            if page:
                wx.CallAfter(page.restore_context_focus, return_control)

        self.run_worker("جار ترجمة الرسالة...", work, done, failed)
        if page:
            wx.CallAfter(page.restore_context_focus, return_control)

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
        wx.CallAfter(guide.SetFocus)
        dialog.ShowModal()
        dialog.Destroy()

    def program_guide_text(self) -> str:
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
The HTML viewer keeps links and buttons in their natural positions as real page elements. Use Tab or your screen reader's browsing commands to reach them, then press Enter or Space to activate them. Press Ctrl+Enter to move between the message viewer and the item viewer. Press Ctrl+Space to return directly to the message list.

The easy viewer removes repeated blank lines and presents a clean text version. Its item viewer collects links, buttons, and attachments under clear names. Selecting a message does not mark it as read automatically; press Space in the normal message list to switch the focused message between read and unread.

Work with several messages at once
In normal mode, messages are list items without check boxes. Press Ctrl+Shift+Space to enter multiple-selection mode, where every message becomes a check box. Move with the arrow keys and press Space to check or uncheck a message, or use the mouse.

The application announces entry into or exit from this mode after 300 milliseconds. Press Control by itself to hear the selected count. Press Escape or Ctrl+Shift+Space again to leave the mode. Trying to move above the first item or below the last item announces the boundary. The context menu provides suitable bulk read, star, pin, and Trash commands. Delete asks for confirmation and states the number of affected messages.

Write and act without leaving the keyboard
Compose email opens a complete message window. Message actions include Reply, Star, Translate, Pin to top, move to the provider's Trash, and save attachments whenever they are available. Open the actions menu from its button or with Shift+F10.

Translation when you need it
Ctrl+T translates the current message into the application language. In Settings, choose whether the translation replaces the content inside the HTML or easy viewer, or opens in a separate window. Translation becomes available only while you are inside the message viewer. It requires an internet connection and sends the selected message text to Google Translate only when you request it.

Make the application yours
Settings lets you choose Arabic or English, the HTML or easy message viewer, translation inside the page or in a separate window, and light or dark appearance. Your choices are saved for the next launch.

Updates without opening a browser
The application checks GitHub Releases after startup, and you can check manually from Help, Check for updates. When a release is available, Update now opens an internal progress window showing its version, release date, progress bar, and percentage. The correct installer is downloaded, its SHA-256 digest is verified, and the direct update starts before the application restarts.

Useful keyboard commands
Ctrl+A opens account options and management.
Ctrl+N composes a new message.
Ctrl+R replies to the focused message.
Ctrl+T translates the current message.
F5 refreshes messages.
F1 opens this guide.
Ctrl+Space returns to the message list.
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
مستعرض HTML يبقي الروابط والأزرار في مواضعها الطبيعية كعناصر حقيقية. استخدم Tab أو أوامر التصفح في قارئ الشاشة للوصول إليها ثم Enter أو Space لتفعيلها. ينقلك Ctrl+Enter بين مستعرض الرسالة ومستعرض العناصر، ويعيدك Ctrl+Space مباشرة إلى قائمة الرسائل.

المستعرض السهل ينظف تكرار الأسطر الخالية ويعرض نصا مرتبا. ويجمع مستعرض العناصر الروابط والأزرار والمرفقات تحت أسماء واضحة. مجرد اختيار الرسالة لا يجعلها مقروءة؛ اضغط Space في قائمة الرسائل العادية للتبديل بين مقروءة وغير مقروءة.

تعامل مع عدة رسائل في خطوة واحدة
في الوضع العادي تظهر الرسائل كعناصر قائمة من دون مربعات اختيار. اضغط Ctrl+Shift+Space للدخول إلى وضع التحديد المتعدد، وعندها تتحول الرسائل إلى مربعات اختيار. تنقل بالأسهم واضغط Space لتحديد الرسالة أو إلغاء تحديدها، أو استخدم الفأرة.

ينطق البرنامج الدخول إلى هذا الوضع أو الخروج منه بعد 300 مللي ثانية. اضغط Control وحده لسماع عدد الرسائل المحددة. اخرج بالضغط على Escape أو Ctrl+Shift+Space مرة أخرى. وعند محاولة تجاوز أول عنصر أو آخر عنصر ينطق البرنامج بداية القائمة أو نهايتها. تعرض قائمة السياق أوامر القراءة والنجمة والتثبيت والحذف المناسبة للمجموعة، ويطلب Delete تأكيدا يذكر عدد الرسائل.

اكتب ونفذ الأوامر من لوحة المفاتيح
إنشاء بريد إلكتروني يفتح نافذة كاملة لكتابة رسالتك. وتشمل إجراءات الرسالة الرد والتمييز بنجمة والترجمة والتثبيت في الأعلى والنقل إلى سلة مزود البريد وحفظ المرفقات عند توفرها. افتح القائمة من زر الإجراءات أو باستخدام Shift+F10.

ترجمة في مكانها أو في نافذة مستقلة
يترجم Ctrl+T الرسالة الحالية إلى لغة البرنامج. ومن الإعدادات تستطيع اختيار عرض الترجمة مباشرة داخل مستعرض HTML أو المستعرض السهل، أو فتحها في نافذة مستقلة. لا تتفعل الترجمة إلا وأنت داخل مستعرض الرسالة. تحتاج الميزة إلى الإنترنت ولا يرسل النص إلى Google Translate إلا عندما تطلب الترجمة.

اجعل البرنامج أقرب إلى طريقتك
تتيح الإعدادات اختيار العربية أو الإنجليزية، ومستعرض HTML أو المستعرض السهل، والترجمة داخل الصفحة أو في نافذة مستقلة، والوضع الفاتح أو المظلم. يحفظ البرنامج اختياراتك ليستخدمها عند التشغيل التالي.

تحديث من داخل البرنامج
يفحص البرنامج GitHub Releases بعد التشغيل، ويمكنك الفحص يدويا من قائمة المساعدة ثم تحديث البرنامج. عند توفر إصدار جديد يفتح زر تحديث الآن نافذة تعرض الإصدار وتاريخ إطلاقه وشريط التقدم والنسبة المئوية. ينزل البرنامج المثبت الصحيح ويتحقق من بصمة SHA-256 ثم يبدأ التحديث المباشر ويعيد تشغيل التطبيق من دون فتح المتصفح.

اختصارات مفيدة
Ctrl+A يفتح خيارات الحسابات وإدارتها.
Ctrl+N ينشئ رسالة جديدة.
Ctrl+R يرد على الرسالة المحددة.
Ctrl+T يترجم الرسالة الحالية.
F5 يحدث الرسائل.
F1 يفتح هذا الدليل.
Ctrl+Space يرجع إلى قائمة الرسائل.
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
                wx.CallAfter(self.show_update_available, result)

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
            wx.CallAfter(
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
                wx.CallAfter(self.finish_internal_update, None, exc)
            else:
                wx.CallAfter(self.finish_internal_update, installer, None)

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
            "اكتمل تنزيل التحديث. سيغلق البرنامج ويبدأ التثبيت الآن."
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
                wx.CallAfter(self.finish_new_mail_poll, account, [], 0, False)
                return
            new_count = self.new_inbox_count(account, messages, False)
            wx.CallAfter(self.finish_new_mail_poll, account, messages, new_count, True)

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
                wx.CallAfter(self.on_worker_error, exc, failed)
            except Exception as exc:
                wx.CallAfter(self.on_worker_error, exc, failed)
            else:
                wx.CallAfter(self.on_worker_done, done, result)

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
        self.SetStatusText(message)
        for control in [
            self.command_list,
            self.account_choice,
        ]:
            control.Enable(not busy)


def run() -> None:
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    app.MainLoop()
