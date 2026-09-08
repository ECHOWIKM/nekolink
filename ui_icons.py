# ui_icons.py
# -*- coding: utf-8 -*-
"""NekoLink 线性图标（Canvas 绘制，2px 线宽，圆角端点）。"""
from __future__ import annotations

import math
import tkinter as tk
from typing import Callable, Dict, List, Tuple

from ui_theme import MAIN_BG, PRIMARY_BLUE, TEXT_GRAY, TEXT_SECONDARY

STROKE = 2
ICON_BG = "#E8F0FC"
ICON_BLUE = PRIMARY_BLUE
ICON_GRAY = TEXT_SECONDARY
CHEVRON_GRAY = TEXT_GRAY

Point = Tuple[float, float]


def _scale_point(cx: float, cy: float, size: float, x: float, y: float) -> Point:
    s = size / 24.0
    return cx + (x - 12) * s, cy + (y - 12) * s


def _line(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    size: float,
    coords: List[float],
    color: str,
    width: int = STROKE,
    smooth: bool = False,
    **kwargs,
) -> None:
    pts: List[float] = []
    for i in range(0, len(coords), 2):
        x, y = _scale_point(cx, cy, size, coords[i], coords[i + 1])
        pts.extend((x, y))
    canvas.create_line(
        *pts,
        fill=color,
        width=width,
        capstyle=tk.ROUND,
        joinstyle=tk.ROUND,
        smooth=smooth,
        **kwargs,
    )


def _oval(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    size: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    **kwargs,
) -> None:
    ax, ay = _scale_point(cx, cy, size, x1, y1)
    bx, by = _scale_point(cx, cy, size, x2, y2)
    canvas.create_oval(ax, ay, bx, by, **kwargs)


def _arc(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    size: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    start: float,
    extent: float,
    color: str,
    width: int = STROKE,
    style: str = tk.ARC,
) -> None:
    ax, ay = _scale_point(cx, cy, size, x1, y1)
    bx, by = _scale_point(cx, cy, size, x2, y2)
    canvas.create_arc(
        ax, ay, bx, by,
        start=start,
        extent=extent,
        outline=color,
        width=width,
        style=style,
    )


def _poly(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    size: float,
    coords: List[float],
    color: str,
    fill: str = "",
) -> None:
    pts: List[float] = []
    for i in range(0, len(coords), 2):
        x, y = _scale_point(cx, cy, size, coords[i], coords[i + 1])
        pts.extend((x, y))
    canvas.create_polygon(*pts, fill=fill, outline=color, width=STROKE, smooth=True)


def draw_chevron_right(canvas: tk.Canvas, x: float, y: float, size: float = 10, color: str = CHEVRON_GRAY) -> None:
    """浅灰细右箭头。"""
    s = size / 10.0
    canvas.create_line(
        x - 4 * s, y - 5 * s,
        x + 1 * s, y,
        x - 4 * s, y + 5 * s,
        fill=color,
        width=1.5,
        capstyle=tk.ROUND,
        joinstyle=tk.ROUND,
        smooth=True,
    )


def draw_status_dot(canvas: tk.Canvas, x: float, y: float, color: str = "#22c55e", radius: float = 4) -> None:
    """圆润状态指示点。"""
    canvas.create_oval(
        x - radius, y - radius, x + radius, y + radius,
        fill=color,
        outline="#ffffff",
        width=1,
    )


def _draw_home(c, cx, cy, size, color):
    _poly(c, cx, cy, size, [12, 4, 20, 11, 20, 20, 4, 20, 4, 11], color, fill="")
    _line(c, cx, cy, size, [9, 20, 9, 13, 15, 13, 15, 20], color)


def _draw_history(c, cx, cy, size, color):
    _oval(c, cx, cy, size, 5, 6, 19, 18, outline=color, width=STROKE)
    _line(c, cx, cy, size, [8, 10, 16, 10], color)
    _line(c, cx, cy, size, [8, 14, 14, 14], color)


def _draw_dest(c, cx, cy, size, color):
    _poly(c, cx, cy, size, [4, 12, 20, 4, 14, 20], color, fill="")
    _line(c, cx, cy, size, [14, 20, 20, 4], color)


def _draw_template(c, cx, cy, size, color):
    _line(c, cx, cy, size, [5, 5, 19, 5, 19, 19, 5, 19, 5, 5], color)
    _line(c, cx, cy, size, [12, 5, 12, 19], color)
    _line(c, cx, cy, size, [5, 12, 19, 12], color)


def _draw_settings(c, cx, cy, size, color):
    _oval(c, cx, cy, size, 9, 9, 15, 15, outline=color, width=STROKE)
    for angle in (0, 60, 120, 180, 240, 300):
        rad = math.radians(angle)
        x1 = 12 + 7 * math.cos(rad)
        y1 = 12 + 7 * math.sin(rad)
        x2 = 12 + 10 * math.cos(rad)
        y2 = 12 + 10 * math.sin(rad)
        _line(c, cx, cy, size, [x1, y1, x2, y2], color)


def _draw_logs(c, cx, cy, size, color):
    _line(c, cx, cy, size, [7, 4, 17, 4, 17, 20, 7, 20, 7, 4], color)
    _line(c, cx, cy, size, [10, 9, 14, 9], color)
    _line(c, cx, cy, size, [10, 13, 14, 13], color)


def _draw_bell(c, cx, cy, size, color):
    _arc(c, cx, cy, size, 7, 6, 17, 16, 200, 140, color)
    _line(c, cx, cy, size, [7, 14, 17, 14], color)
    _line(c, cx, cy, size, [12, 16, 12, 18], color)
    _oval(c, cx, cy, size, 10.5, 18, 13.5, 20.5, outline=color, width=STROKE)


def _draw_monitor(c, cx, cy, size, color):
    _line(c, cx, cy, size, [5, 6, 19, 6, 19, 15, 5, 15, 5, 6], color)
    _line(c, cx, cy, size, [10, 15, 10, 18, 14, 18, 14, 15], color)
    _line(c, cx, cy, size, [8, 18, 16, 18], color)
    _oval(c, cx, cy, size, 15, 4, 19, 8, fill=color, outline="")


def _draw_plane(c, cx, cy, size, color):
    _poly(c, cx, cy, size, [4, 12, 20, 6, 14, 18], color, fill="")
    _line(c, cx, cy, size, [10, 12, 14, 18], color)


def _draw_phone_ble(c, cx, cy, size, color):
    _line(c, cx, cy, size, [9, 4, 15, 4, 15, 20, 9, 20, 9, 4], color)
    _line(c, cx, cy, size, [11, 17, 13, 17], color)
    _line(c, cx, cy, size, [4, 9, 4, 15, 7, 12, 4, 9], color)
    _line(c, cx, cy, size, [7, 12, 7, 9], color)
    _line(c, cx, cy, size, [7, 12, 7, 15], color)


def _draw_database(c, cx, cy, size, color):
    _oval(c, cx, cy, size, 6, 5, 18, 9, outline=color, width=STROKE)
    _line(c, cx, cy, size, [6, 7, 6, 17], color)
    _line(c, cx, cy, size, [18, 7, 18, 17], color)
    _oval(c, cx, cy, size, 6, 11, 18, 15, outline=color, width=STROKE)
    _oval(c, cx, cy, size, 6, 15, 18, 19, outline=color, width=STROKE)


def _draw_speaker(c, cx, cy, size, color):
    _poly(c, cx, cy, size, [6, 10, 10, 10, 14, 7, 14, 17, 10, 14, 6, 14], color, fill="")
    _arc(c, cx, cy, size, 14, 9, 20, 15, 270, 90, color)
    _arc(c, cx, cy, size, 14, 7, 21, 17, 270, 90, color)


def _draw_about(c, cx, cy, size, color):
    """简约猫咪头像。"""
    _oval(c, cx, cy, size, 6, 8, 18, 20, outline=color, width=STROKE)
    _poly(c, cx, cy, size, [7, 10, 9, 4, 11, 9], color, fill="")
    _poly(c, cx, cy, size, [13, 9, 15, 4, 17, 10], color, fill="")
    _oval(c, cx, cy, size, 9, 13, 11, 15, fill=color, outline="")
    _oval(c, cx, cy, size, 13, 13, 15, 15, fill=color, outline="")
    _line(c, cx, cy, size, [10, 17, 14, 17], color)


def _draw_building(c, cx, cy, size, color):
    _line(c, cx, cy, size, [6, 4, 6, 20, 18, 20, 18, 4, 6, 4], color)
    _line(c, cx, cy, size, [10, 8, 10, 10, 14, 10, 14, 8], color)
    _line(c, cx, cy, size, [10, 13, 10, 15, 14, 15, 14, 13], color)


def _draw_globe(c, cx, cy, size, color):
    _oval(c, cx, cy, size, 5, 5, 19, 19, outline=color, width=STROKE)
    _line(c, cx, cy, size, [5, 12, 19, 12], color)
    _line(c, cx, cy, size, [12, 5, 12, 19], color)


def _draw_outbox(c, cx, cy, size, color):
    _line(c, cx, cy, size, [5, 9, 19, 9, 19, 18, 5, 18, 5, 9], color)
    _line(c, cx, cy, size, [12, 5, 12, 9], color)
    _line(c, cx, cy, size, [10, 13, 12, 16, 14, 13], color)


def _draw_link(c, cx, cy, size, color):
    _arc(c, cx, cy, size, 5, 9, 11, 15, 60, 240, color)
    _arc(c, cx, cy, size, 13, 9, 19, 15, -120, 240, color)


def _draw_bird(c, cx, cy, size, color):
    _poly(c, cx, cy, size, [5, 14, 12, 6, 19, 14], color, fill="")
    _line(c, cx, cy, size, [8, 12, 16, 12], color)


def _draw_inbox(c, cx, cy, size, color):
    _line(c, cx, cy, size, [4, 9, 12, 15, 20, 9], color)
    _line(c, cx, cy, size, [4, 9, 4, 18, 20, 18, 20, 9], color)


def _draw_phone(c, cx, cy, size, color):
    _line(c, cx, cy, size, [8, 4, 16, 4, 16, 20, 8, 20, 8, 4], color)
    _line(c, cx, cy, size, [11, 17, 13, 17], color)


def _draw_plus_badge(c, cx, cy, size, color):
    _oval(c, cx, cy, size, 6, 6, 18, 18, outline=color, width=STROKE)
    _line(c, cx, cy, size, [12, 8, 12, 16], color)
    _line(c, cx, cy, size, [8, 12, 16, 12], color)


def _draw_chat(c, cx, cy, size, color):
    _line(c, cx, cy, size, [4, 6, 20, 6, 20, 13, 10, 13, 7, 17, 7, 13, 4, 13, 4, 6], color)


def _draw_wechat(c, cx, cy, size, color):
    _oval(c, cx, cy, size, 4, 7, 13, 16, outline=color, width=STROKE)
    _oval(c, cx, cy, size, 11, 8, 20, 17, outline=color, width=STROKE)


def _draw_paw(c, cx, cy, size, color):
    _oval(c, cx, cy, size, 9, 11, 15, 17, outline=color, width=STROKE)
    for x, y in ((6, 7), (16, 7), (8, 4), (14, 4)):
        _oval(c, cx, cy, size, x, y, x + 3, y + 3, fill=color, outline="")


_DEST_SERVICE_DRAWERS: Dict[str, Callable] = {
    "telegram": _draw_plane,
    "dingtalk": _draw_bell,
    "ntfy": _draw_bell,
    "webhook": _draw_globe,
    "gotify": _draw_outbox,
    "custom_http": _draw_link,
    "feishu": _draw_bird,
    "pushdeer": _draw_inbox,
    "bark": _draw_phone,
    "pushplus": _draw_plus_badge,
    "wxpusher": _draw_chat,
    "serverchan": _draw_wechat,
    "pushover": _draw_paw,
    "wecom": _draw_building,
}

DEST_ICON_COLOR = "#374151"


def draw_dest_service_icon(
    canvas: tk.Canvas,
    service_key: str,
    cx: float,
    cy: float,
    size: float = 28,
    color: str = DEST_ICON_COLOR,
) -> None:
    """推送目标卡片：简洁线性图标（32px 视觉，48px 容器内居中）。"""
    drawer = _DEST_SERVICE_DRAWERS.get(service_key, _draw_dest)
    drawer(canvas, cx, cy, size, color)


class DestServiceIcon(tk.Canvas):
    """推送目标卡片图标：48×48 Canvas，线性 2px 描边。"""

    def __init__(self, parent, service_key: str, bg: str = ICON_BG, **kwargs):
        super().__init__(
            parent,
            width=48,
            height=48,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            **kwargs,
        )
        self._service_key = service_key
        self._bg = bg
        self._color = DEST_ICON_COLOR
        self.bind("<Configure>", lambda _e: self.redraw())
        self.redraw()

    def set_style(self, bg: str, color: str | None = None) -> None:
        self._bg = bg
        if color is not None:
            self._color = color
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        self.configure(bg=self._bg)
        draw_dest_service_icon(self, self._service_key, 24, 24, 28, self._color)


_ICON_DRAWERS: Dict[str, Callable] = {
    "main": _draw_home,
    "history": _draw_history,
    "dest": _draw_dest,
    "template": _draw_template,
    "settings": _draw_settings,
    "logs": _draw_logs,
    "notification": _draw_bell,
    "desktop": _draw_monitor,
    "push": _draw_plane,
    "ble": _draw_phone_ble,
    "data": _draw_database,
    "sound": _draw_speaker,
    "about": _draw_about,
}


def draw_icon(
    canvas: tk.Canvas,
    name: str,
    cx: float,
    cy: float,
    size: float = 22,
    color: str = ICON_BLUE,
) -> None:
    drawer = _ICON_DRAWERS.get(name)
    if drawer:
        drawer(canvas, cx, cy, size, color)


def draw_card_icon_badge(
    canvas: tk.Canvas,
    name: str,
    cx: float,
    cy: float,
    *,
    circle_r: float = 20,
    icon_size: float = 22,
    bg: str = ICON_BG,
    color: str = ICON_BLUE,
) -> None:
    """设置卡片：浅蓝圆底 + 线性图标。"""
    canvas.create_oval(
        cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r,
        fill=bg,
        outline="",
    )
    draw_icon(canvas, name, cx, cy, icon_size, color)


class NavIcon(tk.Canvas):
    """侧栏导航小图标（固定尺寸，随背景重绘）。"""

    def __init__(self, parent, icon_name: str, bg: str = MAIN_BG, **kwargs):
        super().__init__(
            parent,
            width=24,
            height=24,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            **kwargs,
        )
        self._icon_name = icon_name
        self._bg = bg
        self._color = ICON_GRAY
        self.bind("<Configure>", lambda _e: self.redraw())
        self.redraw()

    def set_style(self, bg: str, color: str | None = None) -> None:
        self._bg = bg
        if color is not None:
            self._color = color
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        self.configure(bg=self._bg)
        draw_icon(self, self._icon_name, 12, 12, 18, self._color)
