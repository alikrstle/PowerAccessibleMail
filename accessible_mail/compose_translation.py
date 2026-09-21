from __future__ import annotations

import threading
import wx

from .accessibility import announce_context_menu, announce_to_screen_reader, set_accessible
from .config import load_settings, save_settings
from .i18n import tr
from .notification_preferences import EVENT_TRANSLATION_STARTED, EVENT_TRANSLATION, EVENT_TRANSLATION_ERRORS
from .translation import translate_text_with_google
from .translation_languages import language_name, ordered_language_codes
from .ui_helpers import localize_window


class TranslationLanguageDialog(wx.Dialog):
    def __init__(self, parent, saved):
        super().__init__(parent, title=tr("إضافة لغة للتحويل إليها"), size=(480, 540))
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(wx.StaticText(self, label=tr("اختر لغة:")), 0, wx.ALL, 8)
        self.codes = ordered_language_codes(saved)
        self.languages = wx.ListBox(self, choices=[language_name(code) for code in self.codes])
        set_accessible(self.languages, "لغات تحويل النص")
        root.Add(self.languages, 1, wx.EXPAND | wx.ALL, 8)
        row = wx.BoxSizer(wx.HORIZONTAL)
        add = wx.Button(self, wx.ID_OK, tr("إضافة اللغة"))
        close = wx.Button(self, wx.ID_CANCEL, tr("إغلاق"))
        row.Add(add, 0, wx.ALL, 8)
        row.Add(close, 0, wx.ALL, 8)
        root.Add(row, 0, wx.ALIGN_RIGHT)
        add.Enable(bool(self.codes))
        if self.codes:
            self.languages.SetSelection(0)
        self.languages.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.SetSizer(root)
        localize_window(self)
        self.CentreOnParent()
        wx.CallAfter(self.languages.SetFocus)

    def on_key(self, event):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and self.languages.GetSelection() != wx.NOT_FOUND:
            self.EndModal(wx.ID_OK)
        else:
            event.Skip()

    def selected_code(self):
        index = self.languages.GetSelection()
        return self.codes[index] if 0 <= index < len(self.codes) else ""


class ComposeTranslationMixin:
    def install_text_translation(self):
        self._translation_closed = False
        self._translation_pending = set()
        self._text_revisions = {self.subject: 0, self.body: 0}
        for control in (self.subject, self.body):
            control.Bind(wx.EVT_TEXT, lambda event, c=control: self.on_compose_text_changed(event, c))
            control.Bind(wx.EVT_CONTEXT_MENU, lambda event, c=control: self.show_compose_text_menu(c))
            control.Bind(wx.EVT_CHAR_HOOK, lambda event, c=control: self.on_compose_menu_key(event, c))
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_translation_destroy)

    def on_translation_destroy(self, event):
        if event.GetEventObject() is self:
            self._translation_closed = True
        event.Skip()

    def on_compose_text_changed(self, event, control):
        self._text_revisions[control] += 1
        event.Skip()

    def on_compose_menu_key(self, event, control):
        if event.GetKeyCode() == wx.WXK_MENU or (event.GetKeyCode() == wx.WXK_F10 and event.ShiftDown()):
            self.show_compose_text_menu(control)
        else:
            event.Skip()

    def translation_settings(self):
        return getattr(self.GetParent(), "settings", None) or load_settings()

    def add_translation_language(self, control):
        settings = self.translation_settings()
        dialog = TranslationLanguageDialog(self, settings.compose_translation_languages)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                code = dialog.selected_code()
                if code and code not in settings.compose_translation_languages:
                    previous = list(settings.compose_translation_languages)
                    settings.compose_translation_languages.append(code)
                    try:
                        save_settings(settings)
                    except Exception as exc:
                        settings.compose_translation_languages = previous
                        wx.MessageBox(str(exc), tr("تعذر حفظ اللغة"), wx.OK | wx.ICON_ERROR, self)
        finally:
            dialog.Destroy()
            control.SetFocus()

    def show_compose_text_menu(self, control):
        menu = wx.Menu()
        languages = wx.Menu()
        for code in self.translation_settings().compose_translation_languages:
            item = languages.Append(wx.ID_ANY, language_name(code))
            item.Enable(bool(control.GetValue().strip()) and control not in self._translation_pending)
            languages.Bind(wx.EVT_MENU, lambda event, c=code: wx.CallAfter(self.start_compose_translation, control, c), item)
        add = languages.Append(wx.ID_ANY, tr("إضافة لغة للتحويل إليها"))
        languages.Bind(wx.EVT_MENU, lambda event: wx.CallAfter(self.add_translation_language, control), add)
        menu.AppendSubMenu(languages, tr("تحويل النص إلى لغة أخرى"))
        copy = menu.Append(wx.ID_ANY, tr("نسخ"))
        paste = menu.Append(wx.ID_ANY, tr("لصق"))
        clear = menu.Append(wx.ID_ANY, tr("محو المكتوب"))
        copy.Enable(control.CanCopy())
        paste.Enable(control.CanPaste())
        clear.Enable(bool(control.GetValue()))
        menu.Bind(wx.EVT_MENU, lambda event: control.Copy(), copy)
        menu.Bind(wx.EVT_MENU, lambda event: control.Paste(), paste)
        menu.Bind(wx.EVT_MENU, lambda event: control.Clear(), clear)
        announce_context_menu(control)
        try:
            control.PopupMenu(menu)
        finally:
            menu.Destroy()
            control.SetFocus()

    def start_compose_translation(self, control, code):
        if self._translation_closed or control in self._translation_pending:
            return
        original = control.GetValue()
        if not original.strip():
            return
        confirm = getattr(self.GetParent(), "confirm_translation_data_transfer", None)
        if not callable(confirm) or not confirm():
            return
        revision = self._text_revisions[control]
        self._translation_pending.add(control)
        announce_to_screen_reader(control, "جار ترجمة النص...", EVENT_TRANSLATION_STARTED)

        def work():
            try:
                result = translate_text_with_google(original, code)
            except Exception as exc:
                wx.CallAfter(self.finish_compose_translation, control, original, revision, "", str(exc))
            else:
                wx.CallAfter(self.finish_compose_translation, control, original, revision, result, "")
        threading.Thread(target=work, daemon=True).start()

    def finish_compose_translation(self, control, original, revision, result, error):
        if self._translation_closed:
            return
        self._translation_pending.discard(control)
        if error:
            announce_to_screen_reader(control, "تعذرت ترجمة النص.", EVENT_TRANSLATION_ERRORS)
            wx.MessageBox(error, tr("تعذرت ترجمة النص"), wx.OK | wx.ICON_ERROR, self)
            return
        if self._text_revisions[control] != revision or control.GetValue() != original:
            announce_to_screen_reader(control, "اكتملت الترجمة، ولم يُستبدل النص لأنك عدّلته أثناء الترجمة.", EVENT_TRANSLATION)
            return
        # Replace through the editing API so Ctrl+Z can recover the original.
        control.Replace(0, control.GetLastPosition(), result)
        announce_to_screen_reader(control, "تمت ترجمة النص.", EVENT_TRANSLATION)
