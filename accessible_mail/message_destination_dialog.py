"""Shared destination prompt for the application and isolated training."""
import wx

from .i18n import tr


def choose_message_destination(parent: wx.Window) -> str:
    dialog = wx.Dialog(parent, title=tr("إضافة الرسائل إلى مجلد أو قسم"))
    try:
        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(wx.StaticText(dialog, label=tr("أين تريد إضافة الرسائل؟")), 0, wx.ALL, 16)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        folder = wx.Button(dialog, label=tr("إلى مجلد"))
        section = wx.Button(dialog, label=tr("إلى قسم"))
        folder.Bind(wx.EVT_BUTTON, lambda _event: dialog.EndModal(1))
        section.Bind(wx.EVT_BUTTON, lambda _event: dialog.EndModal(2))
        buttons.Add(folder, 0, wx.ALL, 6)
        buttons.Add(section, 0, wx.ALL, 6)
        layout.Add(buttons, 0, wx.ALIGN_CENTER | wx.BOTTOM, 12)
        dialog.SetSizerAndFit(layout)
        folder.SetFocus()
        result = dialog.ShowModal()
        return {1: "folder", 2: "section"}.get(result, "")
    finally:
        dialog.Destroy()
