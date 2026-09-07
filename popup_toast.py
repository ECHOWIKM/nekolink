# popup_toast.py
# -*- coding: utf-8 -*-
"""
Telegram Desktop 风格自定义通知（tkinter 独立无边框窗口）。
"""
from __future__ import annotations

import os
import re
import time
import tkinter as tk
import ctypes
from ctypes import wintypes
from typing import Callable, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageTk = None

_TRANSPARENT = "#010101"
_LINE_RE = re.compile(r"^(.+?[：:])(.*)$")
_BRACKET_RE = re.compile(r"^【.+】$")

# 颜色
_CLR_APP = "#111111"
_CLR_TITLE = "#2382dd"
_CLR_BODY = "#333333"
_CLR_META = "#777777"
_CLR_CLOSE = "#b0b0b0"
_CLR_CLOSE_HOVER = "#e53935"
_CLR_BAR_HOVER = "#f5f7fa"

# 默认尺寸与隐私
NOTIFICATION_WIDTH = 420
DEFAULT_NOTIFICATION_WIDTH = 420
NOTIFICATION_FONT_SIZE = 8
DEFAULT_NOTIFICATION_FONT_SIZE = 8
PRIVACY_SHOW_TITLE = True
PRIVACY_SHOW_MSG = True

VALID_NOTIFICATION_WIDTHS = frozenset({300, 420, 480, 540})
VALID_NOTIFICATION_FONT_SIZES = frozenset({6, 8, 10, 12})

NOTIFICATION_WIDTH_LABELS = {
    300: "misc_notif_width_sm",
    420: "misc_notif_width_md",
    480: "misc_notif_width_lg",
    540: "misc_notif_width_xl",
}
NOTIFICATION_FONT_LABELS = {
    6: "misc_notif_font_xs",
    8: "misc_notif_font_sm",
    10: "misc_notif_font_md",
    12: "misc_notif_font_lg",
}

_FONT_FAMILY = "Microsoft YaHei UI"
_PAD_X = 12
_PAD_Y = 10

_WIDTH = DEFAULT_NOTIFICATION_WIDTH
_BAR_H = 32
_BAR_GAP = 8
_CARD_GAP = 14
_MARGIN = 20
_AVATAR = 44
_PAD = _PAD_X
_RADIUS = 10
_DURATION_MS = 5000
_SLIDE_MS = 250
_FADE_MS = 400
_MAX_VISIBLE = 3

# 可选值："top_left", "bottom_left", "top_right", "bottom_right"
POPUP_POSITION = "bottom_right"
DEFAULT_POPUP_POSITION = "bottom_right"
VALID_POSITIONS = frozenset({"top_left", "bottom_left", "top_right", "bottom_right"})

POPUP_POSITION_LABELS = {
    "bottom_right": "misc_popup_pos_br",
    "top_right": "misc_popup_pos_tr",
    "bottom_left": "misc_popup_pos_bl",
    "top_left": "misc_popup_pos_tl",
}

_AVATAR_COLORS = ["#3390ec", "#7fc579", "#e17076", "#a695e7", "#faa74a", "#5bc0de"]

BUNDLE_NAME_MAP = {
    "com.tencent.xin": "微信",
    "com.alibaba.DingTalkTalk": "钉钉",
    "com.tencent.mqq": "QQ",
    "com.tencent.WeChatWork": "企业微信",
    "com.apple.MobileSMS": "短信",
    "com.netease.cloudmusic": "网易云音乐",
    "com.xiaojukeji.didi": "滴滴",
}


def _truncate(s: str, limit: int) -> str:
    s = (s or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def normalize_popup_position(pos: str) -> str:
    pos = (pos or "").strip().lower()
    return pos if pos in VALID_POSITIONS else DEFAULT_POPUP_POSITION


def normalize_notification_width(width) -> int:
    try:
        w = int(width)
    except (TypeError, ValueError):
        return DEFAULT_NOTIFICATION_WIDTH
    if w in VALID_NOTIFICATION_WIDTHS:
        return w
    # 旧档位迁移
    if w == 360:
        return 420
    return DEFAULT_NOTIFICATION_WIDTH


def normalize_notification_font_size(size) -> int:
    try:
        s = int(size)
    except (TypeError, ValueError):
        return DEFAULT_NOTIFICATION_FONT_SIZE
    if s in VALID_NOTIFICATION_FONT_SIZES:
        return s
    # 旧档位 14/16/18 迁移到 12；其它回落到默认 8
    if s in (14, 16, 18):
        return 12
    return DEFAULT_NOTIFICATION_FONT_SIZE


def _content_wrap_width(card_width: int) -> int:
    return max(80, card_width - _AVATAR - _PAD_X * 3 - 16)


def _resolve_display_texts(
    title: str,
    msg: str,
    privacy_show_title: bool,
    privacy_show_msg: bool,
) -> Tuple[str, str, bool]:
    """返回 (display_title, display_msg, single_blue_only)。"""
    title = (title or "").strip()
    msg = (msg or "").strip()
    if privacy_show_title and privacy_show_msg:
        return title, msg, False
    if privacy_show_title and not privacy_show_msg:
        return title or "通知", "您有一条新消息", False
    # not privacy_show_title
    return "", "您有一条新消息", True


def _make_title_msg_line(
    parent: tk.Frame,
    title: str,
    msg: str,
    privacy_show_title: bool,
    privacy_show_msg: bool,
    font_size: int,
    card_width: int,
) -> Optional[tk.Misc]:
    """
    行内双色渲染。
    Windows 透明窗体下 tk.Label 的 foreground 会被吞成黑色，改用 Canvas.create_text
    保证 #2382dd 生效；逻辑仍按双色分支：title 蓝加粗 / msg 灰。
    """
    display_title, display_msg, single_blue = _resolve_display_texts(
        title, msg, privacy_show_title, privacy_show_msg
    )
    wrap_w = _content_wrap_width(card_width)
    title_font = (_FONT_FAMILY, font_size, "bold")
    body_font = (_FONT_FAMILY, font_size)

    line_frame = tk.Frame(parent, bg="#ffffff", bd=0, highlightthickness=0)
    line_frame.pack(anchor="w", fill=tk.X, pady=(2, 0))

    canvas = tk.Canvas(
        line_frame,
        bg="#ffffff",
        highlightthickness=0,
        bd=0,
        relief=tk.FLAT,
    )
    canvas.pack(anchor="w")

    def _measure(text: str, font) -> Tuple[int, int]:
        tid = canvas.create_text(0, 0, text=text, font=font, anchor="nw")
        bbox = canvas.bbox(tid)
        canvas.delete(tid)
        if not bbox:
            return 0, font_size + 4
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    if single_blue or not privacy_show_title:
        text = "您有一条新消息"
        tw, th = _measure(text, title_font)
        canvas.configure(width=max(wrap_w, tw + 2), height=th + 2)
        canvas.create_text(
            0, 0, text=text, fill="#2382dd", font=title_font, anchor="nw", width=wrap_w
        )
        return line_frame

    if not display_title and not display_msg:
        line_frame.destroy()
        return None

    x = 0
    y = 0
    max_h = font_size + 4
    total_w = 0

    if display_title:
        tw, th = _measure(display_title, title_font)
        canvas.create_text(x, y, text=display_title, fill="#2382dd", font=title_font, anchor="nw")
        x += tw
        max_h = max(max_h, th)
        total_w = x

    if display_msg:
        msg_text = f": {display_msg}" if display_title else display_msg
        # 剩余宽度用于换行
        remain = max(40, wrap_w - x)
        mw, mh = _measure(msg_text, body_font)
        tid = canvas.create_text(
            x, y, text=msg_text, fill="#333333", font=body_font, anchor="nw", width=remain
        )
        bbox = canvas.bbox(tid)
        if bbox:
            max_h = max(max_h, bbox[3] - bbox[1])
            total_w = max(total_w, bbox[2])
        else:
            total_w = max(total_w, x + mw)
            max_h = max(max_h, mh)

    canvas.configure(width=min(wrap_w + 4, max(total_w + 2, 40)), height=max_h + 2)
    return line_frame


def _get_work_area(root: Optional[tk.Misc] = None) -> Tuple[int, int, int, int]:
    """Windows 工作区 (left, top, width, height)，排除任务栏。"""
    try:
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            left, top = int(rect.left), int(rect.top)
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width > 0 and height > 0:
                return left, top, width, height
    except Exception:
        pass
    try:
        if root is not None:
            root.update_idletasks()
            sw = int(root.winfo_screenwidth())
            sh = max(400, int(root.winfo_screenheight()) - 80)
            return 0, 0, sw, sh
    except tk.TclError:
        pass
    return 0, 0, 1920, 1000


_last_sound_at = 0.0


def _play_notify_sound() -> None:
    global _last_sound_at
    now = time.time()
    if now - _last_sound_at < 0.6:
        return
    _last_sound_at = now
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass


def _parse_fields(body_text: str) -> dict:
    fields = {"device": "", "date": "", "title": "", "msg": ""}
    for raw in (body_text or "").splitlines():
        line = raw.strip()
        if not line or _BRACKET_RE.match(line):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        label, value = m.group(1), m.group(2).strip()
        if not value:
            continue
        if "设备" in label:
            fields["device"] = value
        elif "时间" in label or "日期" in label:
            fields["date"] = value
        elif "标题" in label:
            fields["title"] = value
        elif "内容" in label:
            fields["msg"] = value
    return fields


def _compose_message(payload: dict) -> Tuple[str, str, str, str]:
    """返回 app_name, title字段, msg字段, meta。"""
    app_name = _truncate(payload.get("app_name") or "通知", 40)
    parsed = _parse_fields(payload.get("body_text") or "")
    device = (payload.get("device_name") or parsed["device"] or "").strip()
    ts = (payload.get("timestamp") or parsed["date"] or "").strip()
    title = _truncate((payload.get("title") or parsed["title"] or "").strip(), 120)
    msg = _truncate((payload.get("msg") or parsed["msg"] or "").strip(), 300)
    meta = " · ".join(x for x in (device, ts) if x)
    return app_name, title, msg, meta


def _make_card_image(
    inner_w: int, inner_h: int, canvas_w: int
) -> Tuple[Optional["ImageTk.PhotoImage"], int, int]:
    if Image is None or ImageDraw is None or ImageTk is None:
        return None, canvas_w, inner_h + 8
    oh = inner_h + 8
    canvas_h = oh + 5
    img = Image.new("RGBA", (canvas_w, canvas_h), (1, 1, 1, 0))
    draw = ImageDraw.Draw(img)
    ex, ey = inner_w, oh
    draw.rounded_rectangle([2, 3, ex + 2, ey + 3], radius=_RADIUS, fill=(0, 0, 0, 30))
    draw.rounded_rectangle([0, 0, ex, ey], radius=_RADIUS, fill=(255, 255, 255, 255))
    draw.rounded_rectangle([0, 0, ex, ey], radius=_RADIUS, outline=(220, 223, 228, 255), width=1)
    return ImageTk.PhotoImage(img), canvas_w, canvas_h


def _load_avatar(app_name: str, icon_path: str, cache: dict) -> Optional[tk.PhotoImage]:
    key = f"{icon_path or app_name}:{_AVATAR}"
    if key in cache:
        return cache[key]
    img = None
    if icon_path and os.path.isfile(icon_path) and Image is not None:
        try:
            src = Image.open(icon_path).convert("RGBA").resize((_AVATAR, _AVATAR), Image.Resampling.LANCZOS)
            mask = Image.new("L", (_AVATAR, _AVATAR), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, _AVATAR - 1, _AVATAR - 1), fill=255)
            img = Image.new("RGBA", (_AVATAR, _AVATAR), (0, 0, 0, 0))
            img.paste(src, (0, 0), mask)
        except Exception:
            img = None
    if img is None and Image is not None:
        letter = (app_name or "?").strip()[:1] or "?"
        idx = sum(ord(c) for c in app_name) % len(_AVATAR_COLORS)
        img = Image.new("RGBA", (_AVATAR, _AVATAR), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((0, 0, _AVATAR - 1, _AVATAR - 1), fill=_AVATAR_COLORS[idx])
        font = None
        for fp in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"):
            try:
                font = ImageFont.truetype(fp, 18)
                break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), letter, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((_AVATAR - tw) / 2, (_AVATAR - th) / 2 - 1), letter, fill="white", font=font)
    if img is None or ImageTk is None:
        return None
    photo = ImageTk.PhotoImage(img)
    cache[key] = photo
    return photo


class _HideAllBar:
    """白色通栏，文字始终蓝色 #2382dd。"""

    _BAR_TEXT = "全部隐藏"
    _BAR_FG = "#2382dd"

    def __init__(self, root: tk.Misc, on_click: Callable[[], None]):
        self.root = root
        self._on_click = on_click
        self.win: Optional[tk.Toplevel] = None
        self._frame: Optional[tk.Frame] = None
        self._canvas: Optional[tk.Canvas] = None
        self._text_id: Optional[int] = None
        self._bar_width = DEFAULT_NOTIFICATION_WIDTH

    def _ensure(self, width: int) -> None:
        if self.win and self.win.winfo_exists() and self._bar_width == width:
            return
        if self.win and self.win.winfo_exists():
            self.destroy_bar()
        self._bar_width = width
        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#ffffff")
        self.win.geometry(f"{width}x{_BAR_H}")
        self._frame = tk.Frame(self.win, bg="#ffffff", width=width, height=_BAR_H)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._frame.pack_propagate(False)
        self._canvas = tk.Canvas(
            self._frame,
            width=width,
            height=_BAR_H,
            bg="#ffffff",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._text_id = self._canvas.create_text(
            width // 2,
            _BAR_H // 2,
            text=self._BAR_TEXT,
            fill=self._BAR_FG,
            font=("Segoe UI", 9),
            anchor=tk.CENTER,
        )
        self._canvas.bind("<Button-1>", lambda _e: self._on_click())
        self._frame.bind("<Button-1>", lambda _e: self._on_click())

        def _enter(_e=None):
            if self._frame and self._canvas:
                self._frame.configure(bg=_CLR_BAR_HOVER)
                self._canvas.configure(bg=_CLR_BAR_HOVER)
                if self._text_id is not None:
                    self._canvas.itemconfigure(self._text_id, fill=self._BAR_FG)

        def _leave(_e=None):
            if self._frame and self._canvas:
                self._frame.configure(bg="#ffffff")
                self._canvas.configure(bg="#ffffff")
                if self._text_id is not None:
                    self._canvas.itemconfigure(self._text_id, fill=self._BAR_FG)

        self._frame.bind("<Enter>", _enter)
        self._frame.bind("<Leave>", _leave)
        self._canvas.bind("<Enter>", _enter)
        self._canvas.bind("<Leave>", _leave)

    def show_at(self, x: int, y: int, width: int) -> None:
        self._ensure(width)
        assert self.win is not None
        if self._canvas is not None and self._text_id is not None:
            self._canvas.itemconfigure(self._text_id, fill=self._BAR_FG)
        self.win.geometry(f"{width}x{_BAR_H}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()

    def destroy_bar(self) -> None:
        if self.win:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None
            self._frame = None
            self._canvas = None
            self._text_id = None


class CustomToastNotification:
    """单条 Telegram 风格通知窗口。"""

    def __init__(
        self,
        manager: "NotificationManager",
        payload: dict,
        app_name: str,
        title_text: str,
        msg_text: str,
        meta: str,
    ):
        self.manager = manager
        self.root = manager.root
        self.payload = payload
        self.notif_id = payload.get("notif_id") or ""
        self.card_width = manager.notification_width
        self.font_size = manager.notification_font_size
        self._destroyed = False
        self._hovering = False
        self._fading = False
        self._timer: Optional[str] = None
        self._shown_at = time.time()
        self.outer_w = self.card_width
        self.outer_h = 90
        self.target_x = 0
        self.target_y = 0
        inner_content_w = self.card_width - 8

        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.0)
        self.win.configure(bg=_TRANSPARENT)
        try:
            self.win.attributes("-transparentcolor", _TRANSPARENT)
        except tk.TclError:
            pass

        self._shell = tk.Frame(self.win, bg=_TRANSPARENT)
        self._shell.pack()

        self._bg_lbl = tk.Label(self._shell, bd=0, bg=_TRANSPARENT)
        inner_frame = tk.Frame(self._shell, bg="#ffffff", width=inner_content_w)
        inner_frame.pack_propagate(True)
        self._build_content(inner_frame, app_name, title_text, msg_text, meta)

        inner_frame.update_idletasks()
        # 高度完全由内容撑开，不写死固定 height
        inner_h = max(inner_frame.winfo_reqheight(), 1)

        photo, _cw, ch = _make_card_image(inner_content_w, inner_h, self.card_width)
        self.outer_w = self.card_width
        self.outer_h = ch
        self._bg_photo = photo
        if photo:
            self._bg_lbl.configure(image=photo)
            self._bg_lbl.image = photo
        self._bg_lbl.pack()
        inner_frame.place(x=0, y=4, width=inner_content_w, height=inner_h)

        self._bind_hover(self.win)
        self._bind_hover(self._shell)

    def _build_content(
        self,
        parent: tk.Frame,
        app_name: str,
        title_text: str,
        msg_text: str,
        meta: str,
    ) -> None:
        inner = tk.Frame(parent, bg="#ffffff")
        inner.pack(fill=tk.BOTH, expand=True, padx=_PAD_X, pady=_PAD_Y)
        meta_font_size = max(6, self.font_size - 2)

        row = tk.Frame(inner, bg="#ffffff")
        row.pack(fill=tk.X)

        av = tk.Label(row, bg="#ffffff", bd=0)
        av.pack(side=tk.LEFT, anchor=tk.N)
        photo = _load_avatar(app_name, self.payload.get("icon_path") or "", self.manager._icon_cache)
        if photo:
            av.configure(image=photo)
            av.image = photo

        right = tk.Frame(row, bg="#ffffff")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        title_row = tk.Frame(right, bg="#ffffff")
        title_row.pack(fill=tk.X)

        tk.Label(
            title_row,
            text=app_name,
            bg="#ffffff",
            fg=_CLR_APP,
            foreground=_CLR_APP,
            font=(_FONT_FAMILY, self.font_size),
            anchor=tk.W,
            bd=0,
            highlightthickness=0,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._close = tk.Label(
            title_row,
            text="✕",
            bg="#ffffff",
            fg=_CLR_CLOSE,
            foreground=_CLR_CLOSE,
            font=(_FONT_FAMILY, max(6, self.font_size - 1)),
            cursor="hand2",
            padx=2,
            bd=0,
            highlightthickness=0,
        )
        self._close.pack(side=tk.RIGHT)
        self._close.bind("<Button-1>", lambda _e: self.close(immediate=False))
        self._close.bind("<Enter>", lambda _e: self._close.configure(fg=_CLR_CLOSE_HOVER, foreground=_CLR_CLOSE_HOVER))
        self._close.bind("<Leave>", lambda _e: self._close.configure(fg=_CLR_CLOSE, foreground=_CLR_CLOSE))

        _make_title_msg_line(
            right,
            title_text,
            msg_text,
            self.manager.privacy_show_title,
            self.manager.privacy_show_msg,
            self.font_size,
            self.card_width,
        )

        if meta:
            tk.Label(
                right,
                text=meta,
                bg="#ffffff",
                fg=_CLR_META,
                foreground=_CLR_META,
                font=(_FONT_FAMILY, meta_font_size),
                anchor=tk.W,
                bd=0,
                highlightthickness=0,
            ).pack(fill=tk.X, pady=(3, 0))

        self._bind_body_click(inner)

    def _bind_body_click(self, widget: tk.Widget) -> None:
        if widget is getattr(self, "_close", None):
            return
        widget.bind("<Button-1>", lambda _e: self._on_body_click())
        for child in widget.winfo_children():
            if child is getattr(self, "_close", None):
                continue
            self._bind_body_click(child)

    def _on_body_click(self) -> None:
        if self.notif_id and self.manager.on_click:
            try:
                self.manager.on_click(self.notif_id)
            except Exception:
                pass

    def _bind_hover(self, widget: tk.Widget) -> None:
        widget.bind("<Enter>", lambda _e: self._set_hover(True))
        widget.bind("<Leave>", lambda _e: self._set_hover(False))

    def _set_hover(self, hovering: bool) -> None:
        if self._destroyed:
            return
        self._hovering = hovering
        if hovering:
            self._cancel_timer()
        else:
            self._schedule_dismiss()

    def _cancel_timer(self) -> None:
        if self._timer:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None

    def _schedule_dismiss(self) -> None:
        if self._destroyed or self._hovering or self._fading:
            return
        self._cancel_timer()
        elapsed = (time.time() - self._shown_at) * 1000
        remaining = max(500, int(_DURATION_MS - elapsed))
        self._timer = self.root.after(remaining, self._start_fade)

    def _start_fade(self) -> None:
        if self._destroyed or self._hovering:
            return
        self._fading = True
        self._cancel_timer()
        self._fade_step(1.0)

    def _fade_step(self, alpha: float) -> None:
        if self._destroyed:
            return
        if self._hovering:
            self._fading = False
            try:
                self.win.attributes("-alpha", 1.0)
            except tk.TclError:
                pass
            self._schedule_dismiss()
            return
        alpha -= 1.0 / max(1, int(_FADE_MS / 20))
        if alpha <= 0:
            self.close(immediate=True)
            return
        try:
            self.win.attributes("-alpha", max(0.0, alpha))
        except tk.TclError:
            self.close(immediate=True)
            return
        self.root.after(20, lambda: self._fade_step(alpha))

    def slide_in(self, target_x: int, target_y: int, slide_from: str) -> None:
        self.target_x = target_x
        self.target_y = target_y
        wa_left, _wa_top, wa_w, _wa_h = _get_work_area(self.root)
        if slide_from == "left":
            start_x = wa_left - self.outer_w - 20
        else:
            start_x = wa_left + wa_w + 20
        self.win.geometry(f"{self.outer_w}x{self.outer_h}+{start_x}+{target_y}")
        self.win.deiconify()
        self.win.lift()
        self._slide_step(start_x, target_x, 0)

    def _slide_step(self, x0: int, x1: int, elapsed: int) -> None:
        if self._destroyed:
            return
        if elapsed >= _SLIDE_MS:
            self.win.geometry(f"{self.outer_w}x{self.outer_h}+{x1}+{self.target_y}")
            try:
                self.win.attributes("-alpha", 1.0)
            except tk.TclError:
                pass
            self._shown_at = time.time()
            self._schedule_dismiss()
            return
        t = elapsed / _SLIDE_MS
        ease = 1 - (1 - t) ** 3
        x = int(x0 + (x1 - x0) * ease)
        try:
            self.win.geometry(f"{self.outer_w}x{self.outer_h}+{x}+{self.target_y}")
            self.win.attributes("-alpha", min(1.0, t * 1.15))
        except tk.TclError:
            pass
        self.root.after(16, lambda: self._slide_step(x0, x1, elapsed + 16))

    def move_to(self, x: int, y: int) -> None:
        if self._destroyed:
            return
        self.target_x = x
        self.target_y = y
        try:
            self.win.geometry(f"{self.outer_w}x{self.outer_h}+{x}+{y}")
        except tk.TclError:
            pass

    def close(self, immediate: bool = False) -> None:
        if self._destroyed:
            return
        if immediate:
            self._destroy()
            return
        self._start_fade()

    def _destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._cancel_timer()
        self.manager._on_toast_destroyed(self)
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class NotificationManager:
    """Telegram 风格通知队列管理器。"""

    POPUP_POSITION = POPUP_POSITION
    NOTIFICATION_WIDTH = NOTIFICATION_WIDTH
    NOTIFICATION_FONT_SIZE = NOTIFICATION_FONT_SIZE
    PRIVACY_SHOW_TITLE = PRIVACY_SHOW_TITLE
    PRIVACY_SHOW_MSG = PRIVACY_SHOW_MSG

    def __init__(
        self,
        root: tk.Misc,
        on_click: Optional[Callable[[str], None]] = None,
        duration_ms: int = _DURATION_MS,
        max_visible: int = _MAX_VISIBLE,
        popup_position: str = DEFAULT_POPUP_POSITION,
        notification_width: int = DEFAULT_NOTIFICATION_WIDTH,
        notification_font_size: int = DEFAULT_NOTIFICATION_FONT_SIZE,
        privacy_show_title: bool = True,
        privacy_show_msg: bool = True,
    ):
        self.root = root
        self.on_click = on_click
        self.duration_ms = duration_ms
        self.max_visible = min(max_visible, _MAX_VISIBLE)
        self.popup_position = normalize_popup_position(popup_position)
        self.notification_width = normalize_notification_width(notification_width)
        self.notification_font_size = normalize_notification_font_size(notification_font_size)
        self.privacy_show_title = bool(privacy_show_title)
        self.privacy_show_msg = bool(privacy_show_msg)
        self._items: List[CustomToastNotification] = []
        self._icon_cache: dict = {}
        self._hide_bar = _HideAllBar(root, self.dismiss_all)

    def apply_ui_settings(
        self,
        *,
        popup_position: Optional[str] = None,
        notification_width: Optional[int] = None,
        notification_font_size: Optional[int] = None,
        privacy_show_title: Optional[bool] = None,
        privacy_show_msg: Optional[bool] = None,
    ) -> None:
        if popup_position is not None:
            self.popup_position = normalize_popup_position(popup_position)
        if notification_width is not None:
            self.notification_width = normalize_notification_width(notification_width)
        if notification_font_size is not None:
            self.notification_font_size = normalize_notification_font_size(notification_font_size)
        if privacy_show_title is not None:
            self.privacy_show_title = bool(privacy_show_title)
        if privacy_show_msg is not None:
            self.privacy_show_msg = bool(privacy_show_msg)
        if self._items:
            try:
                self.root.after(0, lambda: self._layout(slide=None))
            except tk.TclError:
                pass

    def set_position(self, position: str) -> None:
        self.apply_ui_settings(popup_position=position)

    def show(
        self,
        app_name: str = "",
        title: str = "",
        msg: str = "",
        icon_path: str = "",
        notif_id: str = "",
        body_text: str = "",
        play_sound: bool = True,
        app_bundle_id: str = "",
        device_name: str = "",
        timestamp: str = "",
    ) -> None:
        if app_bundle_id and not app_name:
            app_name = BUNDLE_NAME_MAP.get(app_bundle_id, app_bundle_id)
        payload = {
            "app_name": app_name,
            "title": title,
            "msg": msg,
            "icon_path": icon_path,
            "notif_id": notif_id,
            "body_text": body_text,
            "play_sound": play_sound,
            "device_name": device_name,
            "timestamp": timestamp,
        }
        try:
            self.root.after(0, lambda: self._show_on_main(payload))
        except tk.TclError:
            pass

    def _show_on_main(self, payload: dict) -> None:
        app_name, title_text, msg_text, meta = _compose_message(payload)
        if not title_text and not msg_text:
            return

        toast = CustomToastNotification(self, payload, app_name, title_text, msg_text, meta)
        pos = self.popup_position

        # 顶部锚定：新消息在最上；底部锚定：新消息在最下
        if pos.startswith("top"):
            self._items.insert(0, toast)
        else:
            self._items.append(toast)

        while len(self._items) > self.max_visible:
            if pos.startswith("top"):
                self._items[-1].close(immediate=True)
            else:
                self._items[0].close(immediate=True)

        if payload.get("play_sound"):
            _play_notify_sound()

        self._layout(slide=toast)

    def test_popup(self) -> None:
        from datetime import datetime

        now = datetime.now().strftime("%Y年%m月%d日%H:%M:%S")
        self.show(
            app_bundle_id="com.tencent.xin",
            title="测试发件人",
            msg="这是一条测试消息",
            device_name="测试设备",
            timestamp=now,
            play_sound=False,
        )

    def dismiss_all(self) -> None:
        try:
            self.root.after(0, self._dismiss_all_on_main)
        except tk.TclError:
            pass

    def _dismiss_all_on_main(self) -> None:
        for item in list(self._items):
            item.close(immediate=True)

    def destroy_all(self) -> None:
        self._destroy_all_on_main()

    def _destroy_all_on_main(self) -> None:
        for item in list(self._items):
            item._destroyed = True
            item._cancel_timer()
            try:
                item.win.destroy()
            except tk.TclError:
                pass
        self._items.clear()
        self._hide_bar.destroy_bar()

    def _on_toast_destroyed(self, toast: CustomToastNotification) -> None:
        if toast in self._items:
            self._items.remove(toast)
        if self._items:
            self._layout(slide=None)
        else:
            self._hide_bar.destroy_bar()

    def _work_area(self) -> Tuple[int, int, int, int]:
        return _get_work_area(self.root)

    def _layout(self, slide: Optional[CustomToastNotification]) -> None:
        if not self._items:
            self._hide_bar.destroy_bar()
            return

        wa_left, wa_top, wa_w, wa_h = self._work_area()
        wa_bottom = wa_top + wa_h
        pos = self.popup_position
        m = _MARGIN
        card_w = self.notification_width

        if "right" in pos:
            x = wa_left + wa_w - card_w - m
            slide_from = "right"
        else:
            x = wa_left + m
            slide_from = "left"

        cards_h = sum(it.outer_h for it in self._items) + _CARD_GAP * max(0, len(self._items) - 1)
        cluster_h = _BAR_H + _BAR_GAP + cards_h

        if pos.startswith("bottom"):
            bar_y = wa_bottom - m - cluster_h
            order = list(self._items)
        else:
            bar_y = wa_top + m
            order = list(self._items)

        self._hide_bar.show_at(x, bar_y, card_w)
        y = bar_y + _BAR_H + _BAR_GAP

        for item in order:
            if y + item.outer_h > wa_bottom - m or y < wa_top + m:
                if item in self._items:
                    item.close(immediate=True)
                continue
            if item is slide:
                item.slide_in(x, y, slide_from)
            else:
                item.move_to(x, y)
            y += item.outer_h + _CARD_GAP


PopupToastManager = NotificationManager
