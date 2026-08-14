from __future__ import annotations

from pathlib import Path

import wx

from .config import app_dir
from .i18n import is_rtl, tr


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

    def localize_menu(menu: wx.Menu) -> None:
        for item in menu.GetMenuItems():
            if item.IsSeparator():
                continue
            item.SetItemLabel(tr(item.GetItemLabel()))
            submenu = item.GetSubMenu()
            if submenu is not None:
                localize_menu(submenu)

    for menu_index in range(menu_bar.GetMenuCount()):
        menu_bar.SetMenuLabel(menu_index, tr(menu_bar.GetMenuLabel(menu_index)))
        localize_menu(menu_bar.GetMenu(menu_index))


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
