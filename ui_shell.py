# ui_shell.py
# -*- coding: utf-8 -*-
"""
NekoLink 侧边栏导航与设置卡片 UI 组件（纯视觉 + 布局，不含业务逻辑）。
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional, Tuple

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, BOTTOM, E, LEFT, RIGHT, W, X, Y

import i18n
from ui_theme import (
    CARD_BG,
    CARD_HOVER_BG,
    CARD_RADIUS,
    FONT_BRAND,
    FONT_FAMILY,
    FONT_NORMAL,
    FONT_SMALL,
    FONT_TITLE,
    MAIN_BG,
    PRIMARY_BLUE,
    SIDEBAR_ACTIVE_BG,
    SIDEBAR_WIDTH,
    TEXT_MAIN,
    TEXT_SECONDARY,
)

APP_VERSION = "v1.0.0"

# 导航项：(key, i18n_key, icon)
NAV_ITEMS: List[Tuple[str, str, str]] = [
    ("main", "nav_home", "🏠"),
    ("history", "nav_history", "💬"),
    ("dest", "nav_dest", "🎯"),
    ("template", "nav_template", "📝"),
    ("settings", "nav_settings", "⚙"),
    ("logs", "nav_logs", "📋"),
]

# 设置卡片：(key, i18n_title, i18n_desc, icon)
SETTING_CARDS: List[Tuple[str, str, str, str]] = [
    ("notification", "card_notification", "card_notification_desc", "🔔"),
    ("desktop", "card_desktop", "card_desktop_desc", "🖥"),
    ("push", "card_push", "card_push_desc", "✈"),
    ("ble", "card_ble", "card_ble_desc", "📱"),
    ("data", "card_data", "card_data_desc", "💾"),
    ("sound", "card_sound", "card_sound_desc", "🔊"),
    ("about", "card_about", "card_about_desc", "ℹ"),
]


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class SettingCard(tk.Frame):
    """可点击的设置卡片：圆角白底、hover 高亮、右侧箭头。"""

    def __init__(
        self,
        parent,
        icon: str,
        title: str,
        desc: str,
        command: Callable[[], None],
        extra_right: str = "",
        **kwargs,
    ):
        super().__init__(parent, bg=MAIN_BG, **kwargs)
        self._command = command
        self._hover = False
        self._extra_right = extra_right

        self._canvas = tk.Canvas(
            self,
            bg=MAIN_BG,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._canvas.pack(fill=BOTH, expand=True)

        self._icon = icon
        self._title = title
        self._desc = desc

        self._canvas.bind("<Configure>", self._redraw)
        for seq in ("<Enter>", "<Leave>", "<Button-1>"):
            self._canvas.bind(seq, self._on_event)
        self.bind("<Configure>", lambda _e: self._redraw())

    def update_text(self, icon: str, title: str, desc: str, extra_right: str = "") -> None:
        self._icon = icon
        self._title = title
        self._desc = desc
        self._extra_right = extra_right
        self._redraw()

    def _on_event(self, event):
        if event.type == "7":  # Enter
            self._hover = True
            self._redraw()
        elif event.type == "8":  # Leave
            self._hover = False
            self._redraw()
        elif event.type == "4":  # Button-1
            if self._command:
                self._command()

    def _redraw(self, _evt=None):
        c = self._canvas
        c.delete("all")
        w = max(c.winfo_width(), 200)
        h = max(c.winfo_height(), 100)
        if w <= 1 or h <= 1:
            return

        bg = CARD_HOVER_BG if self._hover else CARD_BG
        r = CARD_RADIUS
        pad = 2
        _round_rect(c, pad, pad, w - pad, h - pad, r, fill=bg, outline="#E8EDF4", width=1)

        # 图标
        c.create_text(28, h // 2 - 14, text=self._icon, font=(FONT_FAMILY, 18), anchor=W, fill=PRIMARY_BLUE)

        # 标题
        c.create_text(56, h // 2 - 10, text=self._title, font=(FONT_FAMILY, 11, "bold"), anchor=W, fill=TEXT_MAIN)

        # 描述（单行截断）
        desc = self._desc
        if len(desc) > 36:
            desc = desc[:34] + "…"
        c.create_text(56, h // 2 + 12, text=desc, font=(FONT_FAMILY, 9), anchor=W, fill=TEXT_SECONDARY)

        # 箭头 + 可选右侧文字
        right_x = w - 20
        if self._extra_right:
            c.create_text(
                right_x - 30, h // 2,
                text=self._extra_right,
                font=(FONT_FAMILY, 9),
                anchor=E,
                fill=TEXT_SECONDARY,
            )
            right_x -= 10
        c.create_text(right_x, h // 2, text="›", font=(FONT_FAMILY, 16, "bold"), anchor=E, fill=PRIMARY_BLUE)


class Sidebar(tb.Frame):
    """固定宽度左侧导航栏。"""

    def __init__(self, parent, on_nav: Callable[[str], None], **kwargs):
        super().__init__(parent, width=SIDEBAR_WIDTH, bootstyle="secondary", **kwargs)
        self.pack_propagate(False)
        self._on_nav = on_nav
        self._nav_btns: Dict[str, tk.Frame] = {}
        self._current = "main"
        self._ui: Dict[str, tk.Widget] = {}

        self.configure(style="Sidebar.TFrame")
        try:
            self["padding"] = (0, 0)
        except Exception:
            pass

        header = tb.Frame(self, padding=(16, 20, 16, 12))
        header.pack(fill=X)
        self._ui["lbl_brand"] = tb.Label(
            header,
            text="NekoLink",
            font=(FONT_FAMILY, 16, "bold"),
            foreground=TEXT_MAIN,
        )
        self._ui["lbl_brand"].pack(anchor=W)
        self._ui["lbl_subtitle"] = tb.Label(
            header,
            text="",
            font=FONT_SMALL,
            foreground=TEXT_SECONDARY,
        )
        self._ui["lbl_subtitle"].pack(anchor=W, pady=(2, 0))

        nav_wrap = tb.Frame(self, padding=(8, 8))
        nav_wrap.pack(fill=BOTH, expand=True)

        for key, i18n_key, icon in NAV_ITEMS:
            row = tk.Frame(nav_wrap, bg=MAIN_BG, cursor="hand2")
            row.pack(fill=X, pady=2)
            inner = tk.Frame(row, bg=MAIN_BG, cursor="hand2")
            inner.pack(fill=X, padx=4, pady=6)

            bar = tk.Frame(inner, bg=MAIN_BG, width=3)
            bar.pack(side=LEFT, fill=Y)

            icon_lbl = tk.Label(inner, text=icon, bg=MAIN_BG, fg=PRIMARY_BLUE, font=(FONT_FAMILY, 12), cursor="hand2")
            icon_lbl.pack(side=LEFT, padx=(8, 8))

            text_lbl = tk.Label(inner, text="", bg=MAIN_BG, fg=TEXT_MAIN, font=FONT_NORMAL, anchor=W, cursor="hand2")
            text_lbl.pack(side=LEFT, fill=X, expand=True)

            def _bind_all(widget, k=key):
                widget.bind("<Button-1>", lambda _e: self._on_nav(k))
                widget.bind("<Enter>", lambda _e: self._hover_row(k, True))
                widget.bind("<Leave>", lambda _e: self._hover_row(k, False))

            for w in (row, inner, bar, icon_lbl, text_lbl):
                _bind_all(w)

            self._nav_btns[key] = row
            self._ui[f"nav_{key}"] = text_lbl
            self._ui[f"nav_icon_{key}"] = icon_lbl
            self._ui[f"nav_bar_{key}"] = bar
            self._ui[f"nav_inner_{key}"] = inner

        footer = tb.Frame(self, padding=(16, 12))
        footer.pack(fill=X, side=BOTTOM)
        self._ui["lbl_run_status"] = tb.Label(footer, text="", font=FONT_SMALL, bootstyle="success")
        self._ui["lbl_run_status"].pack(anchor=W)
        self._ui["lbl_ble_status"] = tb.Label(footer, text="", font=FONT_SMALL, bootstyle="secondary")
        self._ui["lbl_ble_status"].pack(anchor=W, pady=(2, 0))
        self._ui["lbl_version"] = tb.Label(footer, text=APP_VERSION, font=FONT_SMALL, bootstyle="secondary")
        self._ui["lbl_version"].pack(anchor=W, pady=(6, 0))

    def _hover_row(self, key: str, enter: bool) -> None:
        if key == self._current:
            return
        inner = self._ui.get(f"nav_inner_{key}")
        if not inner:
            return
        bg = SIDEBAR_ACTIVE_BG if enter else MAIN_BG
        self._paint_row(key, bg, PRIMARY_BLUE if enter else TEXT_MAIN)

    def _paint_row(self, key: str, bg: str, fg: str) -> None:
        for suffix in ("", "_icon", "_inner"):
            w = self._ui.get(f"nav_{key}{suffix}" if suffix else f"nav_{key}")
            if w and isinstance(w, (tk.Label, tk.Frame)):
                try:
                    w.configure(bg=bg)
                    if isinstance(w, tk.Label):
                        w.configure(fg=fg if "icon" not in (suffix or "") else PRIMARY_BLUE)
                except Exception:
                    pass
        bar = self._ui.get(f"nav_bar_{key}")
        if bar:
            try:
                bar.configure(bg=PRIMARY_BLUE if key == self._current else bg)
            except Exception:
                pass
        row = self._nav_btns.get(key)
        if row:
            try:
                row.configure(bg=bg)
            except Exception:
                pass

    def set_active(self, key: str) -> None:
        self._current = key
        for k in self._nav_btns:
            if k == key:
                self._paint_row(k, SIDEBAR_ACTIVE_BG, PRIMARY_BLUE)
            else:
                self._paint_row(k, MAIN_BG, TEXT_MAIN)
        bar = self._ui.get(f"nav_bar_{key}")
        if bar:
            try:
                bar.configure(bg=PRIMARY_BLUE)
            except Exception:
                pass

    def apply_i18n(self) -> None:
        self._ui["lbl_subtitle"].configure(text=i18n.t("sidebar_subtitle"))
        for key, i18n_key, _icon in NAV_ITEMS:
            lbl = self._ui.get(f"nav_{key}")
            if lbl:
                lbl.configure(text=i18n.t(i18n_key))

    def set_run_status(self, running: bool) -> None:
        lbl = self._ui.get("lbl_run_status")
        if not lbl:
            return
        if running:
            lbl.configure(text=i18n.t("status_running"), bootstyle="success")
        else:
            lbl.configure(text=i18n.t("status_stopped"), bootstyle="secondary")

    def set_ble_status(self, connected: bool, detail: str = "") -> None:
        lbl = self._ui.get("lbl_ble_status")
        if not lbl:
            return
        if connected:
            text = i18n.t("ble_connected")
            if detail:
                text = f"{text} · {detail}"
        else:
            text = i18n.t("ble_disconnected")
        lbl.configure(text=text)


def build_settings_card_grid(
    parent,
    on_card_click: Callable[[str], None],
) -> Tuple[tb.Frame, Dict[str, SettingCard]]:
    """构建 2 列自适应设置卡片网格，返回容器与卡片 dict。"""
    outer = tb.Frame(parent)
    outer.pack(fill=BOTH, expand=True)

    grid_host = tb.Frame(outer)
    grid_host.pack(fill=BOTH, expand=True, padx=24, pady=(0, 16))
    grid_host.columnconfigure(0, weight=1, uniform="cards")
    grid_host.columnconfigure(1, weight=1, uniform="cards")

    cards: Dict[str, SettingCard] = {}
    for idx, (key, title_key, desc_key, icon) in enumerate(SETTING_CARDS):
        row, col = divmod(idx, 2)
        extra = APP_VERSION if key == "about" else ""
        card = SettingCard(
            grid_host,
            icon=icon,
            title=i18n.t(title_key),
            desc=i18n.t(desc_key),
            command=lambda k=key: on_card_click(k),
            extra_right=extra,
            height=108,
        )
        card.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)
        card.configure(height=108)
        try:
            card.pack_propagate(False)
            card.grid_propagate(False)
        except Exception:
            pass
        grid_host.rowconfigure(row, weight=0, minsize=116)
        cards[key] = card

    return outer, cards


def apply_sidebar_styles(window) -> None:
    """注册 Sidebar 专用 ttk 样式。"""
    style = getattr(window, "style", None)
    if style is None:
        return
    try:
        style.configure("Sidebar.TFrame", background=MAIN_BG)
    except Exception:
        pass
