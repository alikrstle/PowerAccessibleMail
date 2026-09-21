"""Offline message-action practice; never touches accounts or real mail."""
import wx

from .accessibility import set_accessible
from .i18n import tr

SAMPLES = (
    ("رسالة للحذف: إعلان قديم", "هذا إعلان قديم لم تعد بحاجة إليه."),
    ("رسالة للترجمة: موعد الاجتماع", "سيبدأ اجتماع الفريق غدا الساعة العاشرة صباحا."),
    ("رسالة للنسخ: ملاحظة مهمة", "يرجى إحضار دفتر الملاحظات إلى الاجتماع."),
)
ENGLISH_TEXT = "The team meeting will start tomorrow at ten in the morning."


class MessageActionsPractice(wx.Panel):
    def __init__(self, parent, completed):
        super().__init__(parent)
        self.completed = completed
        self.done = set()
        self.visible_ids = [0, 1, 2]
        self.current_id = None
        self.menu_open = False
        self.pending = False
        root = wx.BoxSizer(wx.VERTICAL)
        self.messages = wx.ListBox(self, choices=[tr(item[0]) for item in SAMPLES])
        self.messages.SetSelection(0)
        set_accessible(self.messages, "قائمة رسائل التدريب")
        root.Add(self.messages, 1, wx.EXPAND | wx.ALL, 4)
        self.viewer = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        set_accessible(self.viewer, "مستعرض رسالة التدريب")
        root.Add(self.viewer, 1, wx.EXPAND | wx.ALL, 4)
        self.viewer.Hide()
        self.status = wx.StaticText(self)
        root.Add(self.status, 0, wx.EXPAND | wx.ALL, 4)
        self.SetSizer(root)
        self.messages.Bind(wx.EVT_LISTBOX_DCLICK, self.open_message)
        self.messages.Bind(wx.EVT_CONTEXT_MENU, lambda event: self.context(False))
        self.viewer.Bind(wx.EVT_CONTEXT_MENU, lambda event: self.context(True))
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)

    def open_message(self, _event=None):
        index = self.messages.GetSelection()
        if index == wx.NOT_FOUND:
            return
        self.current_id = self.visible_ids[index]
        self.viewer.ChangeValue(ENGLISH_TEXT if self.current_id == 1 and "translate" in self.done
                                else tr(SAMPLES[self.current_id][1]))
        self.viewer.Show()
        self.Layout()
        self.viewer.SetInsertionPoint(0)
        self.viewer.SetFocus()

    def context(self, in_viewer):
        if self.menu_open or self.pending:
            return
        index = self.messages.GetSelection()
        message_id = self.current_id if in_viewer else self.visible_ids[index] if index != wx.NOT_FOUND else None
        if message_id is None:
            return
        menu = wx.Menu()
        selected = []
        options = (("copy", "نسخ"), ("translate", "ترجمة")) if in_viewer else (("delete", "حذف"),)
        for action, label in options:
            item = menu.Append(wx.ID_ANY, tr(label))
            menu.Bind(wx.EVT_MENU, lambda event, action=action: selected.append(action), id=item.GetId())
        self.menu_open = True
        try:
            (self.viewer if in_viewer else self.messages).PopupMenu(menu)
        finally:
            menu.Destroy()
            self.menu_open = False
        if selected:
            wx.CallAfter(self.apply_action, selected[0], message_id)

    def apply_action(self, action, message_id):
        if not self or self.IsBeingDeleted() or not self.IsShownOnScreen() or self.pending:
            return
        if action in ("copy", "translate") and (self.current_id != message_id or not self.viewer.IsShown()):
            return
        if {"delete": 0, "translate": 1, "copy": 2}.get(action) != message_id:
            wx.MessageBox(tr("نفذ الإجراء على الرسالة المخصصة له كما ورد في شرح المهمة."), tr("المرشد التفاعلي"), wx.OK, self)
            return
        if action == "delete":
            if message_id not in self.visible_ids:
                return
            answer = wx.MessageBox(tr("هل تريد نقل هذه الرسالة إلى سلة المحذوفات؟"), tr("تأكيد الحذف"),
                                   wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if answer != wx.YES:
                self.messages.SetFocus()
                return
            self.visible_ids.remove(message_id)
            self.messages.Set([tr(SAMPLES[i][0]) for i in self.visible_ids])
            self.messages.SetSelection(0)
            self.viewer.Hide()
            self.current_id = None
            self.Layout()
            self.messages.SetFocus()
        elif action == "translate":
            # A fixed local translation keeps training independent of accounts,
            # network availability and the user's actual translation preference.
            dialog = wx.SingleChoiceDialog(self, tr("اختر لغة الترجمة في التدريب"), tr("ترجمة"), ["English — الإنجليزية"])
            dialog.SetSelection(0)
            try:
                answer = dialog.ShowModal()
            finally:
                dialog.Destroy()
            if answer != wx.ID_OK:
                self.viewer.SetFocus()
                return
            self.viewer.ChangeValue(ENGLISH_TEXT)
            self.viewer.SetInsertionPoint(0)
            self.viewer.SetFocus()
        elif action == "copy":
            copied = False
            if wx.TheClipboard.Open():
                try:
                    copied = wx.TheClipboard.SetData(wx.TextDataObject(self.viewer.GetValue()))
                finally:
                    wx.TheClipboard.Close()
            if not copied:
                wx.MessageBox(tr("تعذر نسخ النص. حاول مرة أخرى."), tr("المرشد التفاعلي"), wx.OK, self)
                self.viewer.SetFocus()
                return
            self.viewer.SetFocus()
        self.done.add(action)
        self.status.SetLabel(tr("الإجراءات المنجزة:") + f" {len(self.done)} / 3")
        if self.done == {"delete", "translate", "copy"}:
            self.pending = True
            self.completed()

    def on_key(self, event):
        key, focus = event.GetKeyCode(), wx.Window.FindFocus()
        if focus is self.viewer and key == wx.WXK_ESCAPE:
            self.viewer.Hide()
            self.Layout()
            self.messages.SetFocus()
        elif focus is self.messages and key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.open_message()
        elif focus in (self.messages, self.viewer) and (key == wx.WXK_MENU or key == wx.WXK_F10 and event.ShiftDown()):
            self.context(focus is self.viewer)
        else:
            event.Skip()
