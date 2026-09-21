from __future__ import annotations

import re
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import replace

import wx

from .accessibility import announce_to_screen_reader, restore_control_focus, set_accessible
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


_SIGN_IN_SECRET_PATTERNS = (
    re.compile(
        r"(?i)([?&](?:code|access_token|refresh_token|id_token|client_secret|password)=)[^&\s]+"
    ),
    re.compile(
        r"(?i)\b(access_token|refresh_token|id_token|client_secret|password|authorization)"
        r"\b\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s&,;]+)"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
)


def sanitize_sign_in_diagnostic(message: str, *, max_length: int = 4000) -> str:
    """Remove credentials from a sign-in error before showing or copying it."""
    sanitized = str(message or "").strip()
    sanitized = _SIGN_IN_SECRET_PATTERNS[2].sub("Bearer [محجوب]", sanitized)
    sanitized = _SIGN_IN_SECRET_PATTERNS[0].sub(r"\1[محجوب]", sanitized)
    sanitized = _SIGN_IN_SECRET_PATTERNS[1].sub(r"\1=[محجوب]", sanitized)
    return sanitized[:max_length] or tr("حدث خطأ غير معروف أثناء تسجيل الدخول.")


def sign_in_success_details(
    provider_id: str,
    email_address: str,
    *,
    renewed: bool = False,
) -> str:
    provider_name = "Google" if provider_id.startswith("google") else "Microsoft"
    heading = (
        tr("تم تجديد تسجيل الدخول بنجاح.")
        if renewed
        else tr("تم تسجيل الدخول وإضافة الحساب بنجاح.")
    )
    return "\n".join(
        (
            heading,
            "",
            f"{tr('الخدمة:')} {provider_name}",
            f"{tr('الحساب:')} {email_address}",
            "",
            tr("اضغط استمرار للعودة إلى البرنامج، أو نسخ لنسخ هذه النتيجة."),
        )
    )


def sign_in_error_details(error: Exception, provider_id: str = "") -> str:
    provider_name = ""
    if provider_id:
        provider_name = "Google" if provider_id.startswith("google") else "Microsoft"
    lines = [tr("تعذر تسجيل الدخول."), ""]
    if provider_name:
        lines.append(f"{tr('الخدمة:')} {provider_name}")
    lines.extend(
        (
            f"{tr('نوع الخطأ:')} {type(error).__name__}",
            f"{tr('تفاصيل الخطأ:')} {sanitize_sign_in_diagnostic(tr(str(error)))}",
            "",
            tr("اضغط نسخ لنسخ التفاصيل وإرسالها إلى المطور، أو استمرار للعودة."),
        )
    )
    return "\n".join(lines)


class SignInResultDialog(wx.Dialog):
    """Accessible, copyable result shown after a browser sign-in attempt."""

    def __init__(self, parent: wx.Window, title: str, details: str) -> None:
        super().__init__(parent, title=tr(title), size=(700, 430))
        self.details_text = details
        panel = wx.Panel(self)
        apply_layout_direction(panel)
        root = wx.BoxSizer(wx.VERTICAL)

        heading = wx.StaticText(panel, label=tr(title))
        heading.SetFont(heading.GetFont().Bold())
        root.Add(heading, 0, wx.EXPAND | wx.ALL, 12)

        self.details = wx.TextCtrl(
            panel,
            value=details,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
        )
        set_accessible(
            self.details,
            tr("تفاصيل نتيجة تسجيل الدخول"),
            tr("استخدم الأسهم لقراءة النتيجة، ثم Tab للوصول إلى استمرار أو نسخ."),
        )
        self.details.SetInsertionPoint(0)
        root.Add(self.details, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.continue_button = wx.Button(panel, wx.ID_OK, label=tr("استمرار"))
        self.copy_button = wx.Button(panel, label=tr("نسخ"))
        set_accessible(
            self.continue_button,
            tr("استمرار"),
            tr("إغلاق النتيجة والعودة إلى البرنامج"),
        )
        set_accessible(
            self.copy_button,
            tr("نسخ"),
            tr("نسخ نتيجة تسجيل الدخول إلى الحافظة"),
        )
        self.continue_button.SetDefault()
        self.copy_button.Bind(wx.EVT_BUTTON, self.on_copy)
        buttons.Add(self.continue_button, 0, wx.RIGHT, 8)
        buttons.Add(self.copy_button, 0)
        root.Add(buttons, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(root)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.CentreOnParent()
        wx.CallAfter(self.details.SetFocus)

    def on_copy(self, _event: wx.CommandEvent | None = None) -> None:
        copied = False
        if wx.TheClipboard.Open():
            try:
                copied = bool(wx.TheClipboard.SetData(wx.TextDataObject(self.details_text)))
                if copied:
                    wx.TheClipboard.Flush()
            finally:
                wx.TheClipboard.Close()
        message = (
            tr("تم نسخ نتيجة تسجيل الدخول إلى الحافظة.")
            if copied
            else tr("تعذر نسخ نتيجة تسجيل الدخول إلى الحافظة.")
        )
        announce_to_screen_reader(self.copy_button, message)
        if copied:
            self.copy_button.SetLabel(tr("تم النسخ"))
            set_accessible(self.copy_button, tr("تم النسخ"), message)


def show_sign_in_result_dialog(
    parent: wx.Window,
    title: str,
    details: str,
) -> None:
    dialog = SignInResultDialog(parent, title, details)
    try:
        dialog.ShowModal()
    finally:
        dialog.Destroy()


class GoogleAppPasswordWizard(wx.Dialog):
    STEP_TITLES = (
        "مرحبا بك في معالج كلمة مرور التطبيق",
        "حماية الحساب والتحقق بخطوتين",
        "إنشاء كلمة مرور التطبيق",
        "إدخال بيانات Gmail",
        "مراجعة الإعداد وإنهاؤه",
    )
    STEP_DESCRIPTIONS = (
        (
            "اقرأ الشرح بالأسهم، ثم اضغط Tab للوصول إلى التالي.\n"
            "سنضيف حساب Gmail بخطوات بسيطة.\n"
            "ستحتاج إلى بريدك وكلمة مرور تطبيق تنشئها من Google.\n"
            "لا تستخدم كلمة مرور حسابك العادية."
        ),
        (
            "يجب تفعيل التحقق بخطوتين في حساب Google أولا.\n"
            "تجده في إعدادات أمان حسابك. إذا كان مفعلا، اضغط التالي.\n"
            "قد لا تتوفر كلمات مرور التطبيقات لبعض حسابات العمل أو الدراسة أو الحماية المتقدمة."
        ),
        (
            "اضغط زر فتح صفحة Google الموجود بعد هذا الشرح.\n"
            "اختر حسابك، واكتب Power Accessible Mail اسما للتطبيق، ثم أنشئ كلمة المرور.\n"
            "انسخ كلمة المرور، وارجع إلى هذا المعالج واضغط التالي.\n"
            "لا تشارك كلمة المرور مع أحد.\n\n"
            "لدي كلمة مرور تطبيق لكنني نسيتها:\n"
            "لا تعرض Google كلمة مرور التطبيق مرة أخرى بعد إنشائها. "
            "افتح الصفحة بزر فتح صفحة إنشاء كلمة مرور التطبيق في Google وأنشئ كلمة مرور تطبيق جديدة، ثم انسخها واستخدمها في الخطوة القادمة.\n"
            "إذا كان حسابك يعمل بالفعل بكلمة مرور محفوظة في البرنامج، فلا تحتاج إلى تغييرها لمجرد نسيانها.\n"
            "لا تلغ كلمة المرور القديمة قبل التأكد من عدم استخدامها في برنامج أو جهاز آخر."
        ),
        (
            "اضغط Tab واكتب عنوان Gmail.\n"
            "اضغط Tab مرة أخرى والصق كلمة مرور التطبيق المكونة من 16 رمزا.\n"
            "لا تستخدم كلمة مرور حسابك العادية. لا تحتاج إلى إزالة المسافات.\n"
            "ثم اكتب الاسم الأول واسم العائلة، أو اتركهما فارغين لعرض البريد وحده.\n"
            "بعد إدخال البيانات، اضغط التالي."
        ),
        (
            "اضغط Tab لقراءة عنوان البريد ومراجعته. لن تظهر كلمة المرور هنا.\n"
            "إذا كان العنوان صحيحا، اضغط إنهاء لمتابعة إضافة الحساب.\n"
            "إذا أردت تصحيحه، اضغط السابق. يضبط البرنامج إعدادات الاتصال تلقائيا."
        ),
    )

    def __init__(
        self,
        parent: wx.Window,
        source_account: Account,
        account_builder: Callable[[Account, str, str], Account],
    ) -> None:
        super().__init__(
            parent, title=tr("معالج كلمة مرور تطبيق Google"), size=(680, 680),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.source_account = replace(source_account)
        self.account_builder = account_builder
        self.account: Account | None = None
        self.current_step = 0
        self.page_focus_targets: list[wx.Window] = []

        root = wx.BoxSizer(wx.VERTICAL)
        self.step_status = wx.StaticText(self)
        set_accessible(self.step_status, "تقدم معالج كلمة مرور التطبيق")
        root.Add(self.step_status, 0, wx.EXPAND | wx.ALL, 12)

        self.book = wx.Simplebook(self)
        for index, (title, description) in enumerate(
            zip(self.STEP_TITLES, self.STEP_DESCRIPTIONS, strict=True)
        ):
            page = wx.Panel(self.book)
            page_sizer = wx.BoxSizer(wx.VERTICAL)
            heading = wx.StaticText(page, label=tr(title))
            heading_font = heading.GetFont()
            heading_font.SetPointSize(15)
            heading_font.SetWeight(wx.FONTWEIGHT_BOLD)
            heading.SetFont(heading_font)
            set_accessible(heading, title)
            page_sizer.Add(heading, 0, wx.EXPAND | wx.ALL, 12)

            explanation = wx.TextCtrl(
                page,
                value=tr(description),
                style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
                size=(-1, 135),
            )
            set_accessible(explanation, title)
            page_sizer.Add(explanation, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
            focus_target: wx.Window = explanation

            if index == 2:
                self.open_google_button = wx.Button(
                    page,
                    label=tr("فتح صفحة إنشاء كلمة مرور التطبيق في Google"),
                )
                set_accessible(
                    self.open_google_button,
                    "فتح صفحة إنشاء كلمة مرور التطبيق في Google",
                    "يفتح صفحة Google الرسمية في المتصفح الافتراضي.",
                )
                self.open_google_button.Bind(
                    wx.EVT_BUTTON,
                    self.on_open_google_app_passwords,
                )
                page_sizer.Add(
                    self.open_google_button,
                    0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
                    12,
                )
            elif index == 3:
                page_sizer.Add(
                    wx.StaticText(page, label=tr("عنوان Gmail:")),
                    0,
                    wx.LEFT | wx.RIGHT | wx.TOP,
                    12,
                )
                self.email_control = wx.TextCtrl(page, style=wx.TE_PROCESS_ENTER)
                set_accessible(self.email_control, "عنوان Gmail")
                self.email_control.Bind(
                    wx.EVT_TEXT_ENTER,
                    lambda _event: self.password_control.SetFocus(),
                )
                page_sizer.Add(
                    self.email_control,
                    0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
                    12,
                )
                page_sizer.Add(
                    wx.StaticText(page, label=tr("كلمة مرور التطبيق:")),
                    0,
                    wx.LEFT | wx.RIGHT,
                    12,
                )
                self.password_control = wx.TextCtrl(
                    page,
                    style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER,
                )
                set_accessible(
                    self.password_control,
                    "كلمة مرور التطبيق",
                    "يمكن لصق كلمة مرور التطبيق مع المسافات وسيزيلها البرنامج تلقائيا.",
                )
                self.password_control.Bind(
                    wx.EVT_TEXT_ENTER,
                    lambda _event: self.first_name_control.SetFocus(),
                )
                page_sizer.Add(
                    self.password_control,
                    0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
                    12,
                )
                page_sizer.Add(
                    wx.StaticText(page, label=tr("الاسم الأول:")),
                    0, wx.LEFT | wx.RIGHT, 12,
                )
                self.first_name_control = wx.TextCtrl(
                    page, value=self.source_account.display_name,
                    style=wx.TE_PROCESS_ENTER,
                )
                set_accessible(self.first_name_control, "الاسم الأول:")
                self.first_name_control.Bind(
                    wx.EVT_TEXT_ENTER, lambda _event: self.last_name_control.SetFocus(),
                )
                page_sizer.Add(
                    self.first_name_control, 0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12,
                )
                # Existing display names are unstructured; do not guess how a
                # compound personal name should be split into family names.
                page_sizer.Add(
                    wx.StaticText(page, label=tr("اسم العائلة:")),
                    0, wx.LEFT | wx.RIGHT, 12,
                )
                self.last_name_control = wx.TextCtrl(page, style=wx.TE_PROCESS_ENTER)
                set_accessible(self.last_name_control, "اسم العائلة:")
                self.last_name_control.Bind(wx.EVT_TEXT_ENTER, self.on_next)
                page_sizer.Add(
                    self.last_name_control, 0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12,
                )
            elif index == 4:
                self.review_text = wx.TextCtrl(
                    page,
                    style=wx.TE_MULTILINE | wx.TE_READONLY,
                    size=(-1, 80),
                )
                set_accessible(
                    self.review_text,
                    "ملخص إعداد حساب Gmail",
                    "يعرض عنوان الحساب وطريقة الاتصال دون عرض كلمة مرور التطبيق.",
                )
                page_sizer.Add(
                    self.review_text,
                    0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
                    12,
                )

            page.SetSizer(page_sizer)
            self.book.AddPage(page, tr(title))
            self.page_focus_targets.append(focus_target)

        root.Add(self.book, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        navigation = wx.BoxSizer(wx.HORIZONTAL)
        navigation.AddStretchSpacer(1)
        self.back_button = wx.Button(self, label=tr("السابق"))
        set_accessible(self.back_button, "الخطوة السابقة")
        self.back_button.Bind(wx.EVT_BUTTON, self.on_back)
        navigation.Add(self.back_button, 0, wx.ALL, 6)
        self.next_button = wx.Button(self, label=tr("التالي"))
        self.next_button.SetDefault()
        set_accessible(self.next_button, "الخطوة التالية")
        self.next_button.Bind(wx.EVT_BUTTON, self.on_next)
        navigation.Add(self.next_button, 0, wx.ALL, 6)
        cancel_button = wx.Button(self, id=wx.ID_CANCEL, label=tr("إلغاء"))
        set_accessible(cancel_button, "إلغاء معالج كلمة مرور التطبيق")
        navigation.Add(cancel_button, 0, wx.ALL, 6)
        root.Add(navigation, 0, wx.EXPAND | wx.ALL, 6)

        self.SetSizer(root)
        apply_layout_direction(self)
        localize_window(self)
        self.show_step(0)

    def show_step(self, step: int) -> None:
        self.current_step = max(0, min(step, len(self.STEP_TITLES) - 1))
        self.book.SetSelection(self.current_step)
        title = tr(self.STEP_TITLES[self.current_step])
        self.step_status.SetLabel(
            tr("الخطوة {0} من {1}: {2}").format(
                self.current_step + 1,
                len(self.STEP_TITLES),
                title,
            )
        )
        self.back_button.Enable(self.current_step > 0)
        self.next_button.SetLabel(
            tr("إنهاء")
            if self.current_step == len(self.STEP_TITLES) - 1
            else tr("التالي")
        )
        set_accessible(
            self.next_button,
            "إنهاء إعداد حساب Gmail"
            if self.current_step == len(self.STEP_TITLES) - 1
            else "الخطوة التالية",
        )
        self.Layout()
        # Focus the native reading area instead of interrupting its speech with
        # a separate announcement or skipping ahead to an action button.
        self.page_focus_targets[self.current_step].SetInsertionPoint(0)
        wx.CallAfter(self.focus_step_description, self.current_step)

    def focus_step_description(self, step: int) -> None:
        if self and not self.IsBeingDeleted() and self.current_step == step:
            self.page_focus_targets[step].SetFocus()

    def on_back(self, _event: wx.CommandEvent) -> None:
        if self.current_step > 0:
            self.show_step(self.current_step - 1)

    def on_next(self, _event: wx.CommandEvent) -> None:
        if self.current_step == 3:
            try:
                self.account = self.account_builder(
                    self.source_account,
                    self.email_control.GetValue(),
                    self.password_control.GetValue(),
                )
                self.account.display_name = " ".join(
                    part for part in (
                        self.first_name_control.GetValue().strip(),
                        self.last_name_control.GetValue().strip(),
                    ) if part
                )
            except ValueError as exc:
                wx.MessageBox(
                    str(exc),
                    tr("بيانات غير مكتملة"),
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
                message = str(exc)
                wx.CallAfter(
                    self.email_control.SetFocus
                    if "Gmail" in message or "البريد" in message
                    else self.password_control.SetFocus
                )
                return
            self.review_text.SetValue(
                tr(
                    "عنوان Gmail: {0}\nطريقة الاتصال: IMAP وSMTP الآمنان\n"
                    "كلمة مرور التطبيق: محفوظة ولن تُعرض"
                ).format(self.account.email_address)
            )
        if self.current_step == len(self.STEP_TITLES) - 1:
            self.EndModal(wx.ID_OK)
            return
        self.show_step(self.current_step + 1)

    def on_open_google_app_passwords(self, _event: wx.CommandEvent) -> None:
        if not webbrowser.open("https://myaccount.google.com/apppasswords"):
            wx.MessageBox(
                tr("تعذر فتح صفحة كلمات مرور التطبيقات في المتصفح."),
                tr("تعذر فتح الرابط"),
                wx.OK | wx.ICON_ERROR,
                self,
            )


class FocusableSignInNotice(wx.StaticText):
    """Informational text that can receive keyboard focus without edit state."""

    def AcceptsFocus(self) -> bool:
        return True

    def AcceptsFocusFromKeyboard(self) -> bool:
        return True


class AccountDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        account: Account | None = None,
        startup: bool = False,
    ) -> None:
        title = "تسجيل الدخول" if startup else "إضافة حساب بريد"
        super().__init__(parent, title=title, size=(780, 620), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetSize(self.FromDIP(wx.Size(820, 680)))
        self.account = replace(account) if account else Account()
        self.startup = startup
        self.mode = ""
        self._destroyed = False
        self._oauth_login_active = False
        self._oauth_login_generation = 0
        self._oauth_cancel_event: threading.Event | None = None
        self.pending_sign_in_result: tuple[str, str] | None = None
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
        if self.mode == "startup":
            # Keep all four native actions reachable when the dialog is resized.
            self.SetMinClientSize(root.GetMinSize() + self.FromDIP(wx.Size(24, 24)))
        wx.CallAfter(restore_control_focus, focus)

    def show_startup_view(self) -> None:
        self.mode = "startup"
        root = self.clear_panel()
        content_panel = wx.Panel(self.panel)
        content_panel.visual_card = True
        content_background = wx.Colour(20, 27, 36)
        content_panel.SetBackgroundColour(content_background)
        center = wx.BoxSizer(wx.VERTICAL)

        google_notice = tr("تسجيل الدخول عبر Google محدود حاليا بـ100 مستخدم. إذا تعذر تسجيل الدخول، يرجى استخدام المتابعة لحساب Google بكلمة مرور التطبيق.")
        self.welcome_heading = wx.StaticText(
            content_panel,
            label=tr("مرحبا بكم في برنامج Power Accessible Mail"),
            style=wx.ALIGN_CENTER_HORIZONTAL,
        )
        heading = self.welcome_heading
        set_accessible(heading, "مرحبا بكم في برنامج Power Accessible Mail")
        heading_font = heading.GetFont()
        heading_font.SetPointSize(18)
        heading_font.SetWeight(wx.FONTWEIGHT_BOLD)
        heading.SetFont(heading_font)
        heading.SetForegroundColour(wx.WHITE)
        heading.SetBackgroundColour(content_background)
        center.Add(heading, 0, wx.EXPAND | wx.BOTTOM, 10)

        logo_path = app_logo_path()
        if logo_path:
            logo_bitmap = wx.Bitmap(str(logo_path), wx.BITMAP_TYPE_ANY)
            if logo_bitmap.IsOk():
                logo_size = self.FromDIP(72)
                logo_image = logo_bitmap.ConvertToImage()
                ratio = logo_size / max(logo_image.GetWidth(), logo_image.GetHeight())
                logo_bitmap = wx.Bitmap(logo_image.Scale(max(1, round(logo_image.GetWidth() * ratio)), max(1, round(logo_image.GetHeight() * ratio)), wx.IMAGE_QUALITY_HIGH))
                logo = wx.StaticBitmap(content_panel, bitmap=logo_bitmap)
                logo.SetBackgroundColour(content_background)
                set_accessible(logo, "شعار Power Accessible Mail")
                center.Add(logo, 0, wx.ALIGN_CENTER | wx.BOTTOM, 14)

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
        self.continue_microsoft_button.SetDefault()
        center.Add(self.continue_microsoft_button, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.app_password_wizard_button = wx.Button(
            content_panel,
            label="المتابعة لحساب Google بكلمة مرور التطبيق (موصى بها)",
            size=(360, 44),
        )
        set_accessible(
            self.app_password_wizard_button,
            "المتابعة لحساب Google بكلمة مرور التطبيق (موصى بها)",
            "فتح معالج تفاعلي يشرح إعداد كلمة مرور التطبيق خطوة بخطوة",
        )
        self.app_password_wizard_button.Bind(
            wx.EVT_BUTTON,
            self.on_google_app_password_wizard,
        )
        self.app_password_wizard_button.visual_recommended = True
        center.Add(
            self.app_password_wizard_button,
            0,
            wx.EXPAND | wx.BOTTOM,
            10,
        )

        self.continue_google_button = wx.Button(
            content_panel,
            label="تسجيل الدخول عبر Google (محدود بـ100 مستخدم)",
            size=(360, 44),
        )
        set_accessible(
            self.continue_google_button,
            "تسجيل الدخول عبر Google (محدود بـ100 مستخدم)",
            google_notice,
        )
        self.continue_google_button.Bind(wx.EVT_BUTTON, self.on_continue_with_google)
        center.Add(self.continue_google_button, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.continue_without_account_button = wx.Button(
            content_panel,
            label="المتابعة كزائر",
            size=(360, 44),
        )
        set_accessible(
            self.continue_without_account_button,
            "المتابعة كزائر",
            "الدخول إلى الواجهة الرئيسية بدون حساب",
        )
        self.continue_without_account_button.Bind(
            wx.EVT_BUTTON,
            self.on_continue_without_account,
        )
        center.Add(wx.StaticLine(content_panel), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, self.FromDIP(10))
        center.Add(self.continue_without_account_button, 0, wx.EXPAND)

        for button in (self.continue_microsoft_button, self.app_password_wizard_button,
                       self.continue_google_button, self.continue_without_account_button):
            button.SetMinSize(self.FromDIP(wx.Size(460, 44)))

        content_root = wx.BoxSizer(wx.VERTICAL)
        content_root.Add(center, 1, wx.EXPAND | wx.ALL, self.FromDIP(28))
        content_panel.SetSizer(content_root)
        root.Add(content_panel, 0, wx.ALIGN_CENTER)
        self.finish_panel(root, self.continue_microsoft_button)
        wx.CallAfter(self.announce_startup_welcome)

    def announce_startup_welcome(self) -> None:
        if (getattr(self, "_destroyed", False) or self.mode != "startup"
                or getattr(self, "_welcome_announced", False)):
            return
        self._welcome_announced = True
        announce_to_screen_reader(self, "مرحبا بكم في برنامج Power Accessible Mail")

    @staticmethod
    def google_app_password_account(
        source_account: Account,
        email_address: str,
        password: str,
    ) -> Account:
        normalized_email = email_address.strip()
        if not normalized_email or "@" not in normalized_email:
            raise ValueError("يرجى كتابة عنوان Gmail.")
        if not normalized_email.lower().endswith(("@gmail.com", "@googlemail.com")):
            raise ValueError("تسجيل كلمة مرور التطبيق مخصص لحسابات Gmail فقط.")
        normalized_password = "".join(password.split())
        if len(normalized_password) != 16:
            raise ValueError("يرجى كتابة كلمة مرور تطبيق Google المكونة من 16 رمزا.")

        account = replace(source_account)
        # App-password authentication does not provide an OAuth profile name.
        # Never invent one from the address or carry it to a different account.
        account.display_name = (
            source_account.display_name
            if source_account.email_address.strip().casefold() == normalized_email.casefold()
            else ""
        )
        account.email_address = normalized_email
        account.username = normalized_email
        account.auth_method = "password"
        account.password = normalized_password
        account.save_password = True
        account.oauth_provider = ""
        account.oauth_client_id = ""
        account.oauth_client_secret = ""
        account.oauth_access_token = ""
        account.oauth_refresh_token = ""
        account.oauth_token_expiry = 0.0
        account.save_oauth_tokens = False
        AccountDialog.configure_known_manual_provider(account)
        return account

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
            size=(420, 135),
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

    def on_google_app_password_wizard(
        self,
        _event: wx.CommandEvent | None = None,
    ) -> None:
        wizard = GoogleAppPasswordWizard(
            self,
            self.account,
            self.google_app_password_account,
        )
        try:
            if wizard.ShowModal() != wx.ID_OK or wizard.account is None:
                return
            self.account = wizard.account
        finally:
            wizard.Destroy()
        self.EndModal(wx.ID_OK)

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
        provider_names.append("المتابعة لحساب Google بكلمة مرور التطبيق (موصى بها)")
        self.oauth_provider_ids.append("google_app_password")
        self.oauth_provider_list = wx.ListBox(
            self.panel,
            choices=[
                tr(provider_name) + " — " + tr("محدودة بـ100 مستخدم فقط")
                if provider_id.startswith("google") and provider_id != "google_app_password"
                else tr(provider_name)
                for provider_name, provider_id in zip(
                    provider_names,
                    self.oauth_provider_ids,
                    strict=True,
                )
            ],
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
        self.add_google_sign_in_notice(center)

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
            self.google_limit_notice,
        )

    def on_browser_notice_focus(self, event: wx.FocusEvent) -> None:
        self._browser_notice_arrow_until = time.monotonic() + 3.0
        event.Skip()

    def on_browser_notice_key(self, event: wx.KeyEvent) -> None:
        if (event.GetKeyCode() == wx.WXK_DOWN
                and self.mode == "oauth2"
                and time.monotonic() <= getattr(self, "_browser_notice_arrow_until", 0.0)):
            self.oauth_provider_list.SetFocus()
            return
        event.Skip()

    def add_google_sign_in_notice(self, sizer: wx.BoxSizer) -> None:
        notice = FocusableSignInNotice(self.panel, label=tr("تسجيل الدخول عبر Google محدود حاليا بـ100 مستخدم. إذا تعذر تسجيل الدخول، يرجى استخدام المتابعة لحساب Google بكلمة مرور التطبيق."))
        notice.Wrap(self.FromDIP(420))
        notice.Bind(wx.EVT_SET_FOCUS, self.on_browser_notice_focus)
        notice.Bind(wx.EVT_KEY_DOWN, self.on_browser_notice_key)
        self.oauth_provider_list.MoveAfterInTabOrder(notice)
        sizer.Add(notice, 0, wx.EXPAND | wx.BOTTOM, 12)
        self.google_limit_notice = notice

    def on_oauth_provider_activate(self, _event: wx.Event | None = None) -> None:
        selection = self.oauth_provider_list.GetSelection()
        if 0 <= selection < len(self.oauth_provider_ids):
            provider_id = self.oauth_provider_ids[selection]
            if provider_id == "google_app_password":
                self.on_google_app_password_wizard()
            else:
                self.start_oauth_login(provider_id)

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
            show_sign_in_result_dialog(
                self,
                "تعذر تسجيل الدخول",
                sign_in_error_details(error, result.provider_id if result else ""),
            )
            return
        if result is None:
            return
        account = self.account
        if (
            result.provider_id == "google_gmail_api"
            and not result.refresh_token
            and not account.oauth_refresh_token
        ):
            missing_refresh_token_error = OAuthError(
                "اكتمل تفويض Google، لكن لم يصل رمز يسمح للبرنامج بالاحتفاظ "
                "بتسجيل الدخول. أزل وصول Power Accessible Mail من اتصالات حساب "
                "Google ثم حاول إضافته مرة أخرى، أو انسخ هذا الخطأ وأرسله إلى المطور."
            )
            record_handled_exception(
                missing_refresh_token_error,
                origin="OAuth account sign-in",
            )
            self.Raise()
            self.RequestUserAttention(wx.USER_ATTENTION_ERROR)
            show_sign_in_result_dialog(
                self,
                "تعذر حفظ تسجيل الدخول",
                sign_in_error_details(
                    missing_refresh_token_error,
                    result.provider_id,
                ),
            )
            return
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
        self.pending_sign_in_result = (
            "نجاح تسجيل الدخول",
            sign_in_success_details(result.provider_id, result.email_address),
        )
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
