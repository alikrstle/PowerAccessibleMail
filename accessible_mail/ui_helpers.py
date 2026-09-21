from __future__ import annotations

from pathlib import Path

import wx
import wx.html2

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
    if isinstance(window, wx.TopLevelWindow):
        apply_window_style(window)


def theme_palette(theme: str) -> tuple[wx.Colour, wx.Colour, wx.Colour]:
    """Background, foreground and field/card surface, shared by native windows."""
    if theme == "dark":
        return wx.Colour("#17202D"), wx.Colour("#F2F5FA"), wx.Colour("#233044")
    return wx.Colour("#F3F5F8"), wx.Colour("#182235"), wx.Colour("#FFFFFF")


def apply_window_style(window: wx.Window) -> None:
    """Keep native widgets and their accessibility while sharing a palette."""
    owner = window
    settings = None
    while owner is not None:
        settings = getattr(owner, "settings", None)
        if settings is not None:
            break
        owner = owner.GetParent()
    dark = getattr(settings, "theme", "dark") == "dark"
    background, text, surface = theme_palette("dark" if dark else "light")

    def apply(control):
        # Embedded browser rendering is managed by the message renderer.
        if isinstance(control, wx.html2.WebView):
            return
        if isinstance(control, (wx.Panel, wx.Dialog, wx.Frame, wx.StaticText, wx.TextCtrl, wx.ListBox, wx.ListCtrl, wx.CheckBox, wx.Choice, wx.RadioBox, wx.RadioButton, wx.StaticBox)):
            field = isinstance(control, (wx.TextCtrl, wx.ListBox, wx.ListCtrl, wx.Choice))
            card = getattr(control, "visual_card", False)
            inherited = control.GetParent().GetBackgroundColour() if isinstance(control, (wx.StaticText, wx.CheckBox)) and control.GetParent() else background
            control.SetBackgroundColour(surface if field or card else inherited)
            control.SetForegroundColour(text)
        if isinstance(control, wx.Button):
            size = control.GetMinSize()
            control.SetMinSize(wx.Size(size.width, max(size.height, control.FromDIP(32))))
            if getattr(control, "visual_recommended", False):
                control.SetBackgroundColour(wx.Colour("#C9E8FF"))
                control.SetForegroundColour(wx.Colour("#12354E"))
        for child in control.GetChildren():
            apply(child)
    apply(window)


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
        self._scaled_bitmap = wx.NullBitmap
        self._scaled_size = None
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
        if self._scaled_size != (width, height):
            image = self.bitmap.ConvertToImage()
            ratio = max(width / image.GetWidth(), height / image.GetHeight())
            scaled = image.Scale(max(width, round(image.GetWidth() * ratio)), max(height, round(image.GetHeight() * ratio)), wx.IMAGE_QUALITY_HIGH)
            cropped = scaled.GetSubImage(wx.Rect((scaled.GetWidth() - width) // 2, (scaled.GetHeight() - height) // 2, width, height))
            self._scaled_bitmap = wx.Bitmap(cropped)
            self._scaled_size = (width, height)
        dc.DrawBitmap(self._scaled_bitmap, 0, 0)
