from __future__ import annotations

from typing import Any

import wx
import wx.html2

from .ui_helpers import theme_palette


FONT_SCALES = (100, 125, 150, 175, 200)
CURSOR_SIZES = ("normal", "large", "extra_large")
DEFAULT_TEXT_COLOUR = "#FFFFFF"
DEFAULT_BACKGROUND_COLOUR = "#000000"
FOCUS_BACKGROUND = "#FFD54F"
FOCUS_FOREGROUND = "#000000"

_CURSOR_CACHE: dict[tuple[str, str], wx.Cursor] = {}


def valid_html_colour(value: object, fallback: str) -> str:
    text = str(value or "").strip().upper()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
        except ValueError:
            pass
        else:
            return text
    return fallback


def visual_palette(settings: Any) -> tuple[wx.Colour, wx.Colour, wx.Colour]:
    if bool(getattr(settings, "low_vision_high_contrast", False)):
        return wx.Colour("#000000"), wx.Colour("#FFFFFF"), wx.Colour("#000000")
    if bool(getattr(settings, "low_vision_custom_colours", False)):
        background = wx.Colour(
            valid_html_colour(
                getattr(settings, "low_vision_background_colour", ""),
                DEFAULT_BACKGROUND_COLOUR,
            )
        )
        foreground = wx.Colour(
            valid_html_colour(
                getattr(settings, "low_vision_text_colour", ""),
                DEFAULT_TEXT_COLOUR,
            )
        )
        return background, foreground, background
    return theme_palette(getattr(settings, "theme", "dark"))


def apply_visual_accessibility(window: wx.Window, settings: Any) -> None:
    background, foreground, surface = visual_palette(settings)
    font_scale = int(getattr(settings, "low_vision_font_scale", 100) or 100)
    cursor_size = str(getattr(settings, "low_vision_cursor_size", "normal"))
    focus_highlight = bool(
        getattr(settings, "low_vision_focus_highlight", False)
    )

    def apply(control: wx.Window) -> None:
        if isinstance(control, wx.html2.WebView):
            return
        try:
            base_size = getattr(control, "_pam_base_font_size", None)
            font = wx.Font(control.GetFont())
            if base_size is None:
                base_size = max(1, font.GetPointSize())
                control._pam_base_font_size = base_size
            font.SetPointSize(max(1, round(base_size * font_scale / 100)))
            control.SetFont(font)
        except Exception:
            pass

        field = isinstance(
            control,
            (wx.TextCtrl, wx.ListBox, wx.ListCtrl, wx.Choice, wx.RadioBox),
        )
        card = bool(getattr(control, "visual_card", False))
        inherited = background
        if isinstance(control, (wx.StaticText, wx.CheckBox)) and control.GetParent():
            inherited = control.GetParent().GetBackgroundColour()
        try:
            control.SetBackgroundColour(surface if field or card else inherited)
            control.SetForegroundColour(foreground)
        except Exception:
            pass

        if isinstance(control, wx.Button):
            try:
                size = control.GetMinSize()
                control.SetMinSize(
                    wx.Size(size.width, max(size.height, control.FromDIP(32)))
                )
                if getattr(control, "visual_recommended", False):
                    control.SetBackgroundColour(
                        wx.Colour("#FFFFFF" if background.GetLuminance() < 0.5 else "#12354E")
                    )
                    control.SetForegroundColour(
                        wx.Colour("#000000" if background.GetLuminance() < 0.5 else "#FFFFFF")
                    )
            except Exception:
                pass

        _apply_cursor(control, cursor_size)
        if focus_highlight and _can_receive_focus(control):
            _bind_focus_highlight(control)
        elif getattr(control, "_pam_focus_highlight_bound", False):
            _restore_control_palette(control)

        for child in control.GetChildren():
            apply(child)
        try:
            control.Refresh()
        except Exception:
            pass

    apply(window)


def _can_receive_focus(control: wx.Window) -> bool:
    return isinstance(
        control,
        (
            wx.Button,
            wx.CheckBox,
            wx.Choice,
            wx.ListBox,
            wx.ListCtrl,
            wx.RadioBox,
            wx.RadioButton,
            wx.TextCtrl,
        ),
    )


def _settings_for(control: wx.Window) -> Any | None:
    owner: wx.Window | None = control
    while owner is not None:
        settings = getattr(owner, "settings", None)
        if settings is not None:
            return settings
        owner = owner.GetParent()
    return None


def _bind_focus_highlight(control: wx.Window) -> None:
    if getattr(control, "_pam_focus_highlight_bound", False):
        return
    control._pam_focus_highlight_bound = True

    def focused(event: wx.FocusEvent) -> None:
        settings = _settings_for(control)
        if bool(getattr(settings, "low_vision_focus_highlight", False)):
            try:
                control.SetBackgroundColour(wx.Colour(FOCUS_BACKGROUND))
                control.SetForegroundColour(wx.Colour(FOCUS_FOREGROUND))
                control.Refresh()
            except Exception:
                pass
        event.Skip()

    def blurred(event: wx.FocusEvent) -> None:
        _restore_control_palette(control)
        event.Skip()

    control.Bind(wx.EVT_SET_FOCUS, focused)
    control.Bind(wx.EVT_KILL_FOCUS, blurred)


def _restore_control_palette(control: wx.Window) -> None:
    settings = _settings_for(control)
    if settings is None:
        return
    background, foreground, surface = visual_palette(settings)
    field = isinstance(
        control,
        (wx.TextCtrl, wx.ListBox, wx.ListCtrl, wx.Choice, wx.RadioBox),
    )
    try:
        control.SetBackgroundColour(surface if field else background)
        control.SetForegroundColour(foreground)
        control.Refresh()
    except Exception:
        pass


def _apply_cursor(control: wx.Window, cursor_size: str) -> None:
    try:
        if cursor_size not in {"large", "extra_large"}:
            control.SetCursor(wx.NullCursor)
            return
        kind = "ibeam" if isinstance(control, wx.TextCtrl) else "arrow"
        control.SetCursor(_large_cursor(kind, cursor_size))
    except Exception:
        pass


def _large_cursor(kind: str, cursor_size: str) -> wx.Cursor:
    key = (kind, cursor_size)
    cached = _CURSOR_CACHE.get(key)
    if cached is not None:
        return cached
    size = 48 if cursor_size == "extra_large" else 32
    bitmap = wx.Bitmap(size, size, 32)
    dc = wx.MemoryDC(bitmap)
    mask = wx.Colour(255, 0, 255)
    dc.SetBackground(wx.Brush(mask))
    dc.Clear()
    dc.SetPen(wx.Pen(wx.Colour("#000000"), max(2, size // 12)))
    dc.SetBrush(wx.Brush(wx.Colour("#FFFFFF")))
    if kind == "ibeam":
        x = size // 2
        margin = size // 6
        dc.DrawLine(x, margin, x, size - margin)
        dc.DrawLine(size // 3, margin, size * 2 // 3, margin)
        dc.DrawLine(size // 3, size - margin, size * 2 // 3, size - margin)
        hotspot_x, hotspot_y = x, size // 2
    else:
        points = [
            wx.Point(size // 8, size // 10),
            wx.Point(size // 8, size * 4 // 5),
            wx.Point(size * 3 // 8, size * 3 // 5),
            wx.Point(size * 5 // 8, size * 9 // 10),
            wx.Point(size * 3 // 4, size * 4 // 5),
            wx.Point(size // 2, size // 2),
            wx.Point(size * 4 // 5, size // 2),
        ]
        dc.DrawPolygon(points)
        hotspot_x, hotspot_y = size // 8, size // 10
    dc.SelectObject(wx.NullBitmap)
    image = bitmap.ConvertToImage()
    image.SetMaskColour(mask.Red(), mask.Green(), mask.Blue())
    image.SetOption(wx.IMAGE_OPTION_CUR_HOTSPOT_X, hotspot_x)
    image.SetOption(wx.IMAGE_OPTION_CUR_HOTSPOT_Y, hotspot_y)
    cursor = wx.Cursor(image)
    _CURSOR_CACHE[key] = cursor
    return cursor
