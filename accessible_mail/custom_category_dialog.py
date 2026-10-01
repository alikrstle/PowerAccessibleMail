from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx

from .accessibility import set_accessible
from .custom_categories import CustomCategory
from .i18n import tr
from .folder_store import FolderStore
from .models import Account
from .ui_helpers import apply_layout_direction, localize_window


class CategoryRulesDialog(wx.Dialog):
    """Choose one filter by clicking it or pressing Enter."""

    def __init__(
        self, parent: wx.Window, options: tuple[tuple[str, str], ...],
        selected: tuple[str, ...] = (),
    ) -> None:
        super().__init__(parent, title=tr("شروط تصفية التصنيف"), size=(670, 410))
        self.options = options
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(
            wx.StaticText(self, label=tr("اختر مرشحاً واحداً بالنقر عليه أو بالضغط على Enter.")),
            0, wx.EXPAND | wx.ALL, 10,
        )
        self.rule_list = wx.ListBox(self, choices=[label for _key, label in options], style=wx.LB_SINGLE)
        set_accessible(
            self.rule_list, tr("قائمة مرشحات التصنيف"),
            tr("استخدم الأسهم للتنقل، ثم Enter لاختيار المرشح، أو انقر عليه بالفأرة. Escape للإلغاء."),
        )
        if options:
            initial_index = next((index for index, (key, _label) in enumerate(options) if key in selected), 0)
            self.rule_list.SetSelection(initial_index)
        self.rule_list.Bind(wx.EVT_CHAR_HOOK, self.on_rule_key)
        self.rule_list.Bind(wx.EVT_LEFT_UP, self.on_rule_click)
        root.Add(self.rule_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        root.Add(wx.Button(self, wx.ID_CANCEL, label=tr("إلغاء")), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(root)
        apply_layout_direction(self)
        localize_window(self)
        self.CentreOnParent()
        wx.CallAfter(self.rule_list.SetFocus)

    def on_rule_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE) and not event.HasModifiers():
            self._accept_current_rule()
            return
        event.Skip()

    def on_rule_click(self, event: wx.MouseEvent) -> None:
        index = self.rule_list.HitTest(event.GetPosition())
        event.Skip()
        if index != wx.NOT_FOUND:
            self.rule_list.SetSelection(index)
            wx.CallAfter(self._accept_current_rule)

    def _accept_current_rule(self) -> None:
        if self.rule_list.GetSelection() != wx.NOT_FOUND and self.IsModal():
            self.EndModal(wx.ID_OK)

    def selected_rules(self) -> tuple[str, ...]:
        index = self.rule_list.GetSelection()
        return (self.options[index][0],) if 0 <= index < len(self.options) else ()


class CustomCategoryDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        account: Account,
        store: FolderStore,
        run_worker: Callable[[str, Callable[[], Any], Callable[[Any], None], Callable[[Exception], bool | None] | None], None],
    ) -> None:
        super().__init__(parent, title=tr("التصنيفات المخصصة"), size=(620, 460))
        self.account = account
        self.store = store
        self.run_worker = run_worker
        self.categories: list[CustomCategory] = []
        self._closed = False
        self._busy = False
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(wx.StaticText(self, label=tr("فلاتر محلية لهذا الحساب، لا تنقل الرسائل ولا تغيّر البريد لدى المزوّد:")), 0, wx.ALL, 10)
        self.category_list = wx.ListBox(self)
        set_accessible(self.category_list, "التصنيفات المخصصة", "اختر تصنيفاً لإعادة تسميته أو تعديل شروط تصفيته أو حذفه.")
        root.Add(self.category_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.create_button = wx.Button(self, label=tr("إنشاء تصنيف"))
        self.rules_button = wx.Button(self, label=tr("تعديل شروط تصفية التصنيف"))
        self.rename_button = wx.Button(self, label=tr("إعادة تسمية التصنيف"))
        self.delete_button = wx.Button(self, label=tr("حذف التصنيف"))
        self.close_button = wx.Button(self, wx.ID_CANCEL, label=tr("إغلاق"))
        for button in (self.create_button, self.rules_button, self.rename_button, self.delete_button, self.close_button):
            buttons.Add(button, 0, wx.ALL, 5)
        root.Add(buttons, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        self.SetSizer(root)
        self.create_button.Bind(wx.EVT_BUTTON, self.on_create)
        self.rules_button.Bind(wx.EVT_BUTTON, self.on_edit_rules)
        self.rename_button.Bind(wx.EVT_BUTTON, self.on_rename)
        self.delete_button.Bind(wx.EVT_BUTTON, self.on_delete)
        self.close_button.Bind(wx.EVT_BUTTON, self.on_close)
        self.category_list.Bind(wx.EVT_LISTBOX, self.on_selection)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        apply_layout_direction(self)
        localize_window(self)
        self._update_buttons()
        wx.CallAfter(self.refresh)

    def selected_category(self) -> CustomCategory | None:
        index = self.category_list.GetSelection()
        return self.categories[index] if 0 <= index < len(self.categories) else None

    def _update_buttons(self) -> None:
        self.create_button.Enable(not self._busy)
        selected = self.selected_category() is not None
        self.rename_button.Enable(not self._busy and selected)
        self.rules_button.Enable(not self._busy and selected)
        self.delete_button.Enable(not self._busy and selected)

    def _dispatch(
        self,
        message: str,
        work: Callable[[], Any],
        after: Callable[[Any], None],
    ) -> None:
        if self._busy or self._closed:
            return
        self._busy = True
        self._update_buttons()

        def done(result: Any) -> None:
            if self._closed:
                return
            self._busy = False
            after(result)
            self._update_buttons()

        def failed(_exc: Exception) -> bool:
            if not self._closed:
                self._busy = False
                self._update_buttons()
            return False

        self.run_worker(message, work, done, failed)

    def refresh(self, preferred_id: str = "") -> None:
        def display(categories: list[CustomCategory]) -> None:
            self.categories = categories
            self.category_list.Set([category.name for category in categories])
            selection = next(
                (index for index, category in enumerate(categories) if category.id == preferred_id),
                0 if categories else -1,
            )
            if selection >= 0:
                self.category_list.SetSelection(selection)
            self._update_buttons()

        self._dispatch(
            "جار تحميل التصنيفات المخصصة...",
            lambda: self.store.list_categories(self.account.id),
            display,
        )

    def on_selection(self, _event: wx.Event) -> None:
        self._update_buttons()

    def _ask_name(self, title: str, current: str = "") -> str | None:
        dialog = wx.TextEntryDialog(self, tr("اسم التصنيف:"), tr(title), value=current)
        try:
            return dialog.GetValue() if dialog.ShowModal() == wx.ID_OK else None
        finally:
            dialog.Destroy()

    def on_create(self, _event: wx.Event) -> None:
        chooser = getattr(self.GetParent(), "choose_custom_category_rules", None)
        selection = chooser() if chooser else None
        if selection is None:
            return
        rules, email_addresses = selection
        name = self._ask_name("إنشاء تصنيف")
        if name is None:
            return
        self._dispatch(
            "جار إنشاء التصنيف...",
            lambda: self.store.create_category(self.account.id, name, rules, email_addresses),
            lambda category: self.refresh(category.id),
        )

    def on_edit_rules(self, _event: wx.Event) -> None:
        category = self.selected_category()
        chooser = getattr(self.GetParent(), "choose_custom_category_rules", None)
        if category is None or chooser is None:
            return
        selection = chooser(category.rules, category.email_addresses)
        if selection is None:
            return
        rules, email_addresses = selection
        self._dispatch(
            "جار تعديل شروط التصنيف...",
            lambda: self.store.set_category_rules(self.account.id, category.id, rules, email_addresses),
            lambda _result: self.refresh(category.id),
        )

    def on_rename(self, _event: wx.Event) -> None:
        category = self.selected_category()
        if category is None:
            return
        name = self._ask_name("إعادة تسمية التصنيف", category.name)
        if name is None:
            return
        self._dispatch(
            "جار إعادة تسمية التصنيف...",
            lambda: self.store.rename_category(self.account.id, category.id, name),
            lambda _result: self.refresh(category.id),
        )

    def on_delete(self, _event: wx.Event) -> None:
        category = self.selected_category()
        if category is None:
            return
        answer = wx.MessageBox(
            tr("هل تريد حذف التصنيف {name}؟ سيُحذف الفلتر فقط، ولن تُنقل الرسائل أو تتغير لدى مزوّد البريد.").format(name=category.name),
            tr("حذف التصنيف"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self,
        )
        if answer != wx.YES:
            return
        self._dispatch(
            "جار حذف التصنيف...",
            lambda: self.store.delete_category(self.account.id, category.id),
            lambda _result: self.refresh(),
        )

    def on_close(self, _event: wx.Event) -> None:
        self._closed = True
        self.EndModal(wx.ID_CANCEL)
