from __future__ import annotations

import threading
from dataclasses import replace

import wx

from .accessibility import set_accessible
from .config import load_oauth_clients
from .error_logging import record_handled_exception
from .i18n import tr
from .models import Account
from .oauth import (
    OAuthError,
    OAuthFlowResult,
    apply_provider_settings,
    google_provider_id,
    provider_display_names,
    provider_id_from_name,
    run_browser_oauth_flow,
)
from .ui_constants import (
    MANUAL_PROVIDER_CHOICES,
    MANUAL_PROVIDER_GOOGLE,
    MANUAL_PROVIDER_SETTINGS,
)
from .ui_helpers import (
    BackgroundPanel,
    app_logo_path,
    apply_layout_direction,
    localize_window,
    login_background_path,
)


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
        self._destroyed = False
        self._oauth_login_active = False
        self._oauth_login_generation = 0
        self._oauth_cancel_event: threading.Event | None = None
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)
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
        self.cancel_oauth_login()
        if self.mode in {"oauth2", "password"}:
            self.show_method_view()
            return
        self.close_to_main_interface()

    def close_to_main_interface(self) -> None:
        self.cancel_oauth_login()
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Close()

    def on_close(self, event: wx.CloseEvent) -> None:
        self.cancel_oauth_login()
        event.Skip()

    def on_destroy(self, event: wx.WindowDestroyEvent) -> None:
        if event.GetEventObject() is self:
            self._destroyed = True
            self.cancel_oauth_login()
        event.Skip()

    def cancel_oauth_login(self) -> None:
        if self._oauth_cancel_event is not None:
            self._oauth_cancel_event.set()
        self._oauth_cancel_event = None
        self._oauth_login_generation += 1
        if self._oauth_login_active and wx.IsBusy():
            wx.EndBusyCursor()
        self._oauth_login_active = False

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
        if self._oauth_login_active:
            return
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
        self._oauth_login_active = True
        self._oauth_login_generation += 1
        generation = self._oauth_login_generation
        cancel_event = threading.Event()
        self._oauth_cancel_event = cancel_event
        wx.BeginBusyCursor()

        def work() -> None:
            try:
                result = run_browser_oauth_flow(
                    provider_id,
                    client_id,
                    client_secret,
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                result = None
                error: Exception | None = exc
            else:
                error = None

            def finish() -> None:
                if not self._destroyed:
                    self.finish_oauth_login(
                        generation,
                        client_id,
                        client_secret,
                        result,
                        error,
                    )

            wx.CallAfter(finish)

        threading.Thread(target=work, daemon=True).start()

    def finish_oauth_login(
        self,
        generation: int,
        client_id: str,
        client_secret: str,
        result: OAuthFlowResult | None,
        error: Exception | None,
    ) -> None:
        if generation != self._oauth_login_generation:
            return
        self._oauth_login_active = False
        self._oauth_cancel_event = None
        if wx.IsBusy():
            wx.EndBusyCursor()
        if error is not None:
            record_handled_exception(error, origin="OAuth account sign-in")
            self.Raise()
            self.RequestUserAttention(wx.USER_ATTENTION_ERROR)
            wx.MessageBox(
                tr(str(error)),
                tr("تعذر تسجيل الدخول"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        if result is None:
            return
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
        self.Raise()
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
