# ui_theme.py
# -*- coding: utf-8 -*-
"""
NekoLink 全局 UI 视觉规范。
仅颜色 / 字体 / 间距 / 控件外观，不含业务逻辑。
后续页面可直接 from ui_theme import ... 复用。
"""
from __future__ import annotations

from typing import Any

# ---------- 全局颜色 ----------
MAIN_BG = "#F3F7FC"
PAGE_BG_COLOR = MAIN_BG  # 别名：页面/滚动容器背景
CARD_BG = "#FFFFFF"
CARD_HOVER_BG = "#E8F0FC"
CARD_RADIUS = 14
SIDEBAR_WIDTH = 220
SIDEBAR_ACTIVE_BG = "#E8F0FC"
PRIMARY_BLUE = "#2382dd"
TEXT_MAIN = "#1C1C1C"
TEXT_SECONDARY = "#6B7280"
TEXT_GRAY = "#9CA3AF"
BORDER_COLOR = "#e5e7eb"
HOVER_BLUE = "#1d92c7"
DANGER_RED = "#ef4444"
WARNING_ORANGE = "#f59e0b"
SUCCESS_GREEN = "#22c55e"

# ---------- 全局字体 ----------
FONT_FAMILY = "微软雅黑"
FONT_TITLE = (FONT_FAMILY, 11, "bold")
FONT_NORMAL = (FONT_FAMILY, 10, "normal")
FONT_SMALL = (FONT_FAMILY, 9, "normal")
FONT_SMALL_GRAY = (FONT_FAMILY, 9, "normal")
# 顶栏大标题（同族，略大）
FONT_HEADER = (FONT_FAMILY, 16, "bold")
# 顶部品牌标题：比导航标签（FONT_NORMAL=10）稍大
FONT_BRAND = (FONT_FAMILY, 12, "bold")

# ---------- 全局间距 ----------
PAGE_PADX = 16
PAGE_PADY = 14
CARD_PADX = 14
CARD_PADY = 12
ITEM_SPACE_Y = 10
SECTION_SPACE_Y = 16

# ---------- 控件默认（经典 tk 控件可用；ttk 走 Style） ----------
FRAME_DEFAULT = {
    "relief": "flat",
    "bd": 0,
    "bg": MAIN_BG,
}
LABEL_DEFAULT = {
    "relief": "flat",
    "bd": 0,
    "bg": MAIN_BG,
    "fg": TEXT_MAIN,
    "font": FONT_NORMAL,
}
ENTRY_DEFAULT = {
    "bg": "#ffffff",
    "fg": TEXT_MAIN,
    "insertbackground": PRIMARY_BLUE,
    "relief": "flat",
    "bd": 1,
    "highlightthickness": 1,
    "highlightbackground": BORDER_COLOR,
    "highlightcolor": PRIMARY_BLUE,
    "font": FONT_NORMAL,
}
BUTTON_PRIMARY = {
    "bg": PRIMARY_BLUE,
    "fg": "#ffffff",
    "activebackground": HOVER_BLUE,
    "activeforeground": "#ffffff",
    "relief": "flat",
    "bd": 0,
    "cursor": "hand2",
    "font": FONT_NORMAL,
}
BUTTON_SECONDARY = {
    "bg": "#f3f4f6",
    "fg": TEXT_MAIN,
    "activebackground": "#e5e7eb",
    "activeforeground": TEXT_MAIN,
    "relief": "flat",
    "bd": 0,
    "cursor": "hand2",
    "font": FONT_NORMAL,
}
BUTTON_DANGER = {
    "bg": DANGER_RED,
    "fg": "#ffffff",
    "activebackground": "#dc2626",
    "activeforeground": "#ffffff",
    "relief": "flat",
    "bd": 0,
    "cursor": "hand2",
    "font": FONT_NORMAL,
}


def _safe_configure(style: Any, style_name: str, **kwargs) -> None:
    try:
        style.configure(style_name, **kwargs)
    except Exception:
        pass


def _safe_map(style: Any, style_name: str, **kwargs) -> None:
    try:
        style.map(style_name, **kwargs)
    except Exception:
        pass


def apply_global_theme(window: Any) -> None:
    """
    应用到主窗口：背景色、微软雅黑、扁平 ttk 样式。
    不改布局结构与业务回调。
    """
    try:
        window.configure(bg=MAIN_BG)
    except Exception:
        pass

    # 经典 tk 默认字体
    try:
        window.option_add("*Font", FONT_NORMAL)
        window.option_add("*Label.Font", FONT_NORMAL)
        window.option_add("*Button.Font", FONT_NORMAL)
        window.option_add("*Entry.Font", FONT_NORMAL)
        window.option_add("*Text.Font", FONT_NORMAL)
        window.option_add("*TCombobox*Listbox.font", FONT_NORMAL)
    except Exception:
        pass

    style = getattr(window, "style", None)
    if style is None:
        try:
            import ttkbootstrap as tb

            style = tb.Style()
        except Exception:
            return

    # 尝试对齐主题色板（若 API 可用）
    try:
        colors = style.colors
        for key, val in (
            ("primary", PRIMARY_BLUE),
            ("secondary", TEXT_SECONDARY),
            ("success", SUCCESS_GREEN),
            ("info", HOVER_BLUE),
            ("warning", WARNING_ORANGE),
            ("danger", DANGER_RED),
            ("bg", MAIN_BG),
            ("fg", TEXT_MAIN),
            ("selectbg", PRIMARY_BLUE),
            ("selectfg", "#ffffff"),
            ("border", BORDER_COLOR),
            ("inputfg", TEXT_MAIN),
            ("inputbg", CARD_BG),
        ):
            try:
                colors.set(key, val)
            except Exception:
                try:
                    setattr(colors, key, val)
                except Exception:
                    pass
    except Exception:
        pass

    # Frame / Label
    _safe_configure(style, "TFrame", background=MAIN_BG)
    _safe_configure(
        style,
        "TLabelframe",
        background=MAIN_BG,
        foreground=TEXT_MAIN,
        bordercolor=BORDER_COLOR,
    )
    _safe_configure(
        style,
        "TLabelframe.Label",
        background=MAIN_BG,
        foreground=TEXT_MAIN,
        font=FONT_TITLE,
    )
    _safe_configure(
        style,
        "TLabel",
        background=MAIN_BG,
        foreground=TEXT_MAIN,
        font=FONT_NORMAL,
        borderwidth=0,
        relief="flat",
    )
    _safe_configure(
        style,
        "secondary.TLabel",
        background=MAIN_BG,
        foreground=TEXT_SECONDARY,
        font=FONT_SMALL,
    )
    _safe_configure(
        style,
        "info.TLabel",
        background=MAIN_BG,
        foreground=HOVER_BLUE,
        font=FONT_NORMAL,
    )
    _safe_configure(
        style,
        "success.TLabel",
        background=MAIN_BG,
        foreground=SUCCESS_GREEN,
        font=FONT_NORMAL,
    )
    _safe_configure(
        style,
        "danger.TLabel",
        background=MAIN_BG,
        foreground=DANGER_RED,
        font=FONT_NORMAL,
    )
    _safe_configure(
        style,
        "warning.TLabel",
        background=MAIN_BG,
        foreground=WARNING_ORANGE,
        font=FONT_NORMAL,
    )

    # Entry / Combobox（扁平、白底）
    _safe_configure(
        style,
        "TEntry",
        fieldbackground=CARD_BG,
        foreground=TEXT_MAIN,
        insertcolor=PRIMARY_BLUE,
        bordercolor=BORDER_COLOR,
        lightcolor=PRIMARY_BLUE,
        darkcolor=BORDER_COLOR,
        borderwidth=1,
        relief="flat",
        padding=5,
        font=FONT_NORMAL,
    )
    _safe_map(
        style,
        "TEntry",
        bordercolor=[("focus", PRIMARY_BLUE), ("!focus", BORDER_COLOR)],
        lightcolor=[("focus", PRIMARY_BLUE)],
    )
    _safe_configure(
        style,
        "TCombobox",
        fieldbackground=CARD_BG,
        foreground=TEXT_MAIN,
        background=CARD_BG,
        bordercolor=BORDER_COLOR,
        lightcolor=PRIMARY_BLUE,
        darkcolor=BORDER_COLOR,
        arrowcolor=TEXT_SECONDARY,
        borderwidth=1,
        relief="flat",
        padding=4,
        font=FONT_NORMAL,
    )
    _safe_map(
        style,
        "TCombobox",
        bordercolor=[("focus", PRIMARY_BLUE), ("!focus", BORDER_COLOR)],
        fieldbackground=[("readonly", CARD_BG)],
        foreground=[("readonly", TEXT_MAIN)],
    )

    # Buttons（扁平主色 / 次要 / 危险）
    _safe_configure(
        style,
        "TButton",
        font=FONT_NORMAL,
        borderwidth=0,
        relief="flat",
        focusthickness=0,
        padding=(10, 6),
    )
    for name, bg, hover in (
        ("primary.TButton", PRIMARY_BLUE, HOVER_BLUE),
        ("secondary.TButton", "#f3f4f6", "#e5e7eb"),
        ("danger.TButton", DANGER_RED, "#dc2626"),
        ("success.TButton", SUCCESS_GREEN, "#16a34a"),
        ("warning.TButton", WARNING_ORANGE, "#d97706"),
        ("info.TButton", HOVER_BLUE, PRIMARY_BLUE),
    ):
        fg = TEXT_MAIN if name.startswith("secondary") else "#ffffff"
        _safe_configure(
            style,
            name,
            background=bg,
            foreground=fg,
            bordercolor=bg,
            focusthickness=0,
            font=FONT_NORMAL,
            relief="flat",
            borderwidth=0,
        )
        _safe_map(
            style,
            name,
            background=[("active", hover), ("pressed", hover)],
            foreground=[("active", fg)],
        )

    # Checkbutton / toggle
    _safe_configure(
        style,
        "TCheckbutton",
        background=MAIN_BG,
        foreground=TEXT_MAIN,
        font=FONT_NORMAL,
        focuscolor=MAIN_BG,
    )
    _safe_configure(
        style,
        "Roundtoggle.Toolbutton",
        background=MAIN_BG,
        foreground=TEXT_MAIN,
        font=FONT_NORMAL,
    )
    _safe_configure(
        style,
        "Toolbutton",
        background=MAIN_BG,
        foreground=TEXT_MAIN,
        font=FONT_NORMAL,
    )

    # Notebook
    _safe_configure(style, "TNotebook", background=MAIN_BG, borderwidth=0, relief="flat")
    _safe_configure(
        style,
        "TNotebook.Tab",
        background="#eef2f7",
        foreground=TEXT_SECONDARY,
        font=FONT_NORMAL,
        padding=(12, 6),
        borderwidth=0,
    )
    _safe_map(
        style,
        "TNotebook.Tab",
        background=[("selected", CARD_BG), ("active", "#e8eef6")],
        foreground=[("selected", PRIMARY_BLUE), ("active", TEXT_MAIN)],
    )

    # Scale（不碰 Scrollbar，避免 ttkbootstrap 重复创建 element）
    _safe_configure(
        style,
        "TScale",
        background=MAIN_BG,
        troughcolor=BORDER_COLOR,
        bordercolor=BORDER_COLOR,
        lightcolor=PRIMARY_BLUE,
        darkcolor=PRIMARY_BLUE,
    )

    # Treeview（仅视觉）
    _safe_configure(
        style,
        "Treeview",
        background=CARD_BG,
        fieldbackground=CARD_BG,
        foreground=TEXT_MAIN,
        bordercolor=BORDER_COLOR,
        rowheight=26,
        font=FONT_NORMAL,
        relief="flat",
        borderwidth=1,
    )
    _safe_configure(
        style,
        "Treeview.Heading",
        background="#f3f4f6",
        foreground=TEXT_MAIN,
        font=FONT_TITLE,
        relief="flat",
        borderwidth=0,
    )
    _safe_map(
        style,
        "Treeview",
        background=[("selected", PRIMARY_BLUE)],
        foreground=[("selected", "#ffffff")],
    )
