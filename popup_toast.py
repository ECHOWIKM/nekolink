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
from collections import deque
from typing import Callable, Deque, List, Optional, Tuple

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
NOTIFICATION_FONT_SIZE = 10
DEFAULT_NOTIFICATION_FONT_SIZE = 10
PRIVACY_SHOW_TITLE = True
PRIVACY_SHOW_MSG = True
DEFAULT_MAX_PREVIEW_CHARS = 50
MAX_PREVIEW_CHARS = 50

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
_BAR_H = 36
_BAR_GAP = 8
_CARD_GAP = 14
_MARGIN = 20
_AVATAR = 48  # 通知卡片左上角图标统一显示尺寸
_PAD = _PAD_X
_RADIUS = 16  # 通知卡片四周圆角
_BAR_RADIUS = 12  # 「全部隐藏」按钮圆角
_TOP_BAR_FONT_SIZE = 15  # 「全部隐藏」文字字号
_SHADOW_PAD = 8
_CARD_OUTLINE = (209, 213, 219)  # #d1d5db
_DURATION_MS = 8000  # 默认 8 秒；运行时以 NotificationManager.duration_ms 为准
_SLIDE_MS = 250
_FADE_MS = 400
# 屏幕最多同时可见弹窗数量（超额进入 ui_pop_queue 排队，关闭后依次弹出）
DEFAULT_MAX_POP_NOTIFICATION = 3
MAX_POP_NOTIFICATION = 3
# ui_pop_queue 兜底上限（与历史内存上限量级一致，防异常堆积）
_UI_POP_QUEUE_MAX = 2000

DEFAULT_AUTO_CLOSE_SECONDS = 8
MIN_AUTO_CLOSE_SECONDS = 3
MAX_AUTO_CLOSE_SECONDS = 120


def _lanczos_resample():
    """高质量抗锯齿插值；禁止 NEAREST。"""
    if Image is None:
        return None
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return getattr(Image, "LANCZOS", Image.BICUBIC)


def _remove_white_edge(img):
    """弱化半透明白边/白点，不过度处理实心白色内容。"""
    if img is None or img.mode != "RGBA":
        return img
    try:
        data = img.getdata()
        new_data = []
        for r, g, b, a in data:
            if r > 240 and g > 240 and b > 240 and a < 180:
                new_data.append((r, g, b, 0))
            else:
                new_data.append((r, g, b, a))
        img.putdata(new_data)
    except Exception:
        pass
    return img


def _fit_icon_on_white(src, size: int):
    """
    等比例 LANCZOS 缩放 → 居中到 size×size 透明画布 → alpha 合成到白底。
    消除透明杂边/白点；禁止拉伸变形与 NEAREST。
    """
    img = src.convert("RGBA") if src.mode != "RGBA" else src.copy()
    img.thumbnail((size, size), _lanczos_resample())
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    paste_x = (size - img.width) // 2
    paste_y = (size - img.height) // 2
    canvas.paste(img, (paste_x, paste_y), mask=img)
    canvas = _remove_white_edge(canvas)
    white_bg = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    return Image.alpha_composite(white_bg, canvas)


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
    # 旧档位 14/16/18 迁移到 12；其它回落到默认 10
    if s in (14, 16, 18):
        return 12
    return DEFAULT_NOTIFICATION_FONT_SIZE


def normalize_max_preview_chars(n) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError):
        return DEFAULT_MAX_PREVIEW_CHARS
    if v <= 0:
        return DEFAULT_MAX_PREVIEW_CHARS
    return v


def normalize_max_pop_notification(n) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError):
        return DEFAULT_MAX_POP_NOTIFICATION
    return max(1, min(10, v))


def normalize_notification_auto_close_seconds(n) -> int:
    """弹窗自动关闭秒数，钳位到 3–120；非法输入回退默认 8。"""
    try:
        v = int(str(n).strip())
    except (TypeError, ValueError):
        return DEFAULT_AUTO_CLOSE_SECONDS
    return max(MIN_AUTO_CLOSE_SECONDS, min(MAX_AUTO_CLOSE_SECONDS, v))


def parse_notification_auto_close_seconds(raw) -> Tuple[Optional[int], Optional[str]]:
    """
    解析用户输入的自动关闭秒数。
    返回 (seconds, error)：非整数时 seconds=None 且 error 有文案；越界则钳位后返回。
    """
    s = str(raw if raw is not None else "").strip()
    if not s or not re.fullmatch(r"-?\d+", s):
        return None, "invalid"
    try:
        v = int(s)
    except (TypeError, ValueError):
        return None, "invalid"
    return normalize_notification_auto_close_seconds(v), None


def _preview_msg(msg: str, max_chars: int) -> str:
    msg = msg or ""
    limit = normalize_max_preview_chars(max_chars)
    if len(msg) > limit:
        return msg[:limit] + "…"
    return msg


def _content_wrap_width(card_width: int) -> int:
    """右侧文字列可用宽度：扣除阴影垫层、圆角安全边距、内边距与头像。"""
    corner_inset = max(8, _RADIUS - 4)
    return max(
        80,
        int(card_width)
        - _SHADOW_PAD * 2
        - corner_inset * 2
        - _PAD_X * 2
        - _AVATAR
        - 12,
    )


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
    max_preview_chars: int = DEFAULT_MAX_PREVIEW_CHARS,
) -> Optional[tk.Misc]:
    """
    上下分行排版（禁止 side=left 并排）：
    第1行 title 蓝色加粗；第2行 msg 灰色自动换行。
    title 继续用 Canvas.create_text(fill="#2382dd")，避免透明窗体下 Label 丢色。
    """
    display_title, display_msg, single_blue = _resolve_display_texts(
        title, msg, privacy_show_title, privacy_show_msg
    )
    # 仅对真实消息正文做预览截断；隐私占位文案不截断
    if privacy_show_title and privacy_show_msg and display_msg:
        display_msg = _preview_msg(display_msg, max_preview_chars)

    wrap_w = _content_wrap_width(card_width)
    title_font = (_FONT_FAMILY, font_size, "bold")
    body_font = (_FONT_FAMILY, font_size)

    block = tk.Frame(parent, bg="#ffffff", bd=0, highlightthickness=0)
    block.pack(anchor="w", fill=tk.X, pady=(2, 0))

    def _title_canvas(text: str) -> tk.Canvas:
        cv = tk.Canvas(
            block,
            bg="#ffffff",
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
            width=wrap_w,
        )
        cv.pack(anchor="w")
        # 左右各留 1px，避免末字被 Canvas 裁切
        text_w = max(40, wrap_w - 2)
        tid = cv.create_text(
            1,
            0,
            text=text,
            fill="#2382dd",
            font=title_font,
            anchor="nw",
            width=text_w,
        )
        bbox = cv.bbox(tid)
        if bbox:
            cv.configure(width=wrap_w, height=max(1, bbox[3] - bbox[1] + 2))
        else:
            cv.configure(width=wrap_w, height=font_size + 6)
        return cv

    def _msg_label(text: str) -> tk.Label:
        lbl = tk.Label(
            block,
            text=text,
            fg="#333333",
            foreground="#333333",
            font=body_font,
            bg="#ffffff",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
            anchor="w",
            justify=tk.LEFT,
            wraplength=max(40, wrap_w - 2),
        )
        lbl.pack(anchor="w", fill=tk.X, pady=(2, 0))
        return lbl

    if single_blue or not privacy_show_title:
        _title_canvas("您有一条新消息")
        return block

    if not display_title and not display_msg:
        block.destroy()
        return None

    if display_title:
        _title_canvas(display_title)

    if display_msg:
        _msg_label(display_msg)

    return block


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
    """已废弃：提示音改由 sound_helper 本进程播放，不再 MessageBeep。"""
    return


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
    content_w: int, content_h: int, outer_w: int
) -> Tuple[Optional["ImageTk.PhotoImage"], int, int, int, int]:
    """
    绘制单层白色圆角卡片 + 外侧浅灰柔影（RGB 色键底 #010101）。
    content_h 为白色圆角区域高度（应已含内容四周安全边距）。
    返回 (photo, outer_w, outer_h, content_offset_x, content_offset_y)。
    """
    pad = _SHADOW_PAD
    card_w = max(40, outer_w - pad * 2)
    card_h = max(40, content_h)
    # 柔影右下偏移；浅灰禁止黑块/白垫层
    sh_x, sh_y = 2, 6
    outer_h = card_h + pad * 2 + sh_y
    if Image is None or ImageDraw is None or ImageTk is None:
        return None, outer_w, outer_h, pad, pad

    key_rgb = (1, 1, 1)
    img = Image.new("RGB", (outer_w, outer_h), key_rgb)
    draw = ImageDraw.Draw(img)

    # 浅灰柔影
    draw.rounded_rectangle(
        [pad + sh_x, pad + sh_y, pad + sh_x + card_w - 1, pad + sh_y + card_h - 1],
        radius=_RADIUS,
        fill=(224, 226, 230),
    )
    # 唯一白色圆角卡片（四角 radius=16）
    draw.rounded_rectangle(
        [pad, pad, pad + card_w - 1, pad + card_h - 1],
        radius=_RADIUS,
        fill=(255, 255, 255),
    )
    draw.rounded_rectangle(
        [pad, pad, pad + card_w - 1, pad + card_h - 1],
        radius=_RADIUS,
        outline=_CARD_OUTLINE,
        width=1,
    )
    return ImageTk.PhotoImage(img), outer_w, outer_h, pad, pad


def _load_avatar(app_name: str, icon_path: str, cache: dict) -> Optional[tk.PhotoImage]:
    """
    Pillow：RGBA + thumbnail(LANCZOS) 等比例缩放 → 居中 → 白底 alpha_composite。
    禁止 tk subsample/zoom / NEAREST；结果固定 size×size，避免撑大卡片。
    """
    size = _AVATAR
    key = f"{icon_path or app_name}:{size}:thumb-white-v2"
    if key in cache:
        return cache[key]

    img = None
    if icon_path and os.path.isfile(icon_path) and Image is not None and ImageTk is not None:
        try:
            src = Image.open(icon_path).convert("RGBA")
            img = _fit_icon_on_white(src, size)
        except Exception as e:
            print(f"[toast] icon load failed ({icon_path}): {e}")
            img = None

    if img is None and Image is not None and ImageDraw is not None:
        # 字母圆形头像：超采样后缩小，再合成到白底（与自定义图标流程一致）
        try:
            letter = (app_name or "?").strip()[:1] or "?"
            idx = sum(ord(c) for c in (app_name or "")) % len(_AVATAR_COLORS)
            color = _AVATAR_COLORS[idx]
            scale = 4
            big = size * scale
            canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
            draw = ImageDraw.Draw(canvas)
            draw.ellipse((0, 0, big - 1, big - 1), fill=color)
            font = None
            font_px = max(20, int(big * 0.42))
            for fp in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"):
                try:
                    font = ImageFont.truetype(fp, font_px)
                    break
                except Exception:
                    pass
            if font is None:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), letter, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                ((big - tw) / 2, (big - th) / 2 - big * 0.02),
                letter,
                fill="white",
                font=font,
            )
            letter_rgba = canvas.resize((size, size), _lanczos_resample())
            white_bg = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            img = Image.alpha_composite(white_bg, letter_rgba)
        except Exception as e:
            print(f"[toast] letter avatar failed: {e}")
            img = None

    if img is None or ImageTk is None:
        return None
    photo = ImageTk.PhotoImage(img)
    cache[key] = photo
    return photo


class _HideAllBar:
    """四周圆角的「全部隐藏」栏（PIL 圆角图 + 色键透明，禁止直角白底）。"""

    _BAR_TEXT = "全部隐藏"
    _BAR_FG = "#2382dd"

    def __init__(self, root: tk.Misc, on_click: Callable[[], None]):
        self.root = root
        self._on_click = on_click
        self.win: Optional[tk.Toplevel] = None
        self._lbl: Optional[tk.Label] = None
        self._photo_normal: Optional[tk.PhotoImage] = None
        self._photo_hover: Optional[tk.PhotoImage] = None
        self._bar_width = DEFAULT_NOTIFICATION_WIDTH

    def _render_bar_photo(self, width: int, fill_rgb: Tuple[int, int, int]) -> Optional[tk.PhotoImage]:
        if Image is None or ImageDraw is None or ImageTk is None:
            return None
        h = _BAR_H
        key_rgb = (1, 1, 1)
        img = Image.new("RGB", (width, h), key_rgb)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [0, 0, width - 1, h - 1],
            radius=_BAR_RADIUS,
            fill=fill_rgb,
        )
        draw.rounded_rectangle(
            [0, 0, width - 1, h - 1],
            radius=_BAR_RADIUS,
            outline=_CARD_OUTLINE,
            width=1,
        )
        font = None
        if ImageFont is not None:
            for fp in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf", "C:/Windows/Fonts/segoeui.ttf"):
                try:
                    font = ImageFont.truetype(fp, _TOP_BAR_FONT_SIZE)
                    break
                except Exception:
                    pass
            if font is None:
                try:
                    font = ImageFont.load_default()
                except Exception:
                    font = None
        if font is not None:
            bbox = draw.textbbox((0, 0), self._BAR_TEXT, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                ((width - tw) / 2, (h - th) / 2 - 1),
                self._BAR_TEXT,
                fill=self._BAR_FG,
                font=font,
            )
        return ImageTk.PhotoImage(img)

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
        self.win.configure(bg=_TRANSPARENT)
        try:
            self.win.attributes("-transparentcolor", _TRANSPARENT)
        except tk.TclError:
            pass
        self.win.geometry(f"{width}x{_BAR_H}")

        self._photo_normal = self._render_bar_photo(width, (255, 255, 255))
        self._photo_hover = self._render_bar_photo(width, (245, 247, 250))

        self._lbl = tk.Label(
            self.win,
            image=self._photo_normal,
            bg=_TRANSPARENT,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        if self._photo_normal is not None:
            self._lbl.configure(image=self._photo_normal)
            self._lbl.image = self._photo_normal
        self._lbl.pack()
        self._lbl.bind("<Button-1>", lambda _e: self._on_click())

        def _enter(_e=None):
            if self._lbl is not None and self._photo_hover is not None:
                self._lbl.configure(image=self._photo_hover)
                self._lbl.image = self._photo_hover

        def _leave(_e=None):
            if self._lbl is not None and self._photo_normal is not None:
                self._lbl.configure(image=self._photo_normal)
                self._lbl.image = self._photo_normal

        self._lbl.bind("<Enter>", _enter)
        self._lbl.bind("<Leave>", _leave)

    def show_at(self, x: int, y: int, width: int) -> None:
        self._ensure(width)
        assert self.win is not None
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
            self._lbl = None
            self._photo_normal = None
            self._photo_hover = None


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
        # 创建时快照时长：热加载只影响后续新卡片，已弹出卡片沿用本值
        self.duration_ms = max(1000, int(getattr(manager, "duration_ms", _DURATION_MS) or _DURATION_MS))
        self.outer_w = self.card_width
        self.outer_h = 90
        self.target_x = 0
        self.target_y = 0
        # 圆角安全边距：白底内容矩形不得盖住四角圆弧
        corner_inset = max(8, _RADIUS - 4)
        # 内容布局宽度 = 白卡片内宽 - 两侧安全边距
        content_w = max(80, self.card_width - _SHADOW_PAD * 2 - corner_inset * 2)

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

        self._shell = tk.Frame(self.win, bg=_TRANSPARENT, bd=0, highlightthickness=0)
        self._shell.pack()

        self._bg_lbl = tk.Label(self._shell, bd=0, highlightthickness=0, bg=_TRANSPARENT)
        # 内容白底 Frame：尺寸小于圆角白卡片，四周留给圆弧
        inner_frame = tk.Frame(
            self._shell, bg="#ffffff", width=content_w, bd=0, highlightthickness=0
        )
        inner_frame.pack_propagate(True)
        self._build_content(inner_frame, app_name, title_text, msg_text, meta)

        inner_frame.update_idletasks()
        content_h = max(inner_frame.winfo_reqheight(), 1)
        # 白卡片高度 = 内容 + 上下圆角安全边距，保证直角内容盖不到四角
        card_h = content_h + corner_inset * 2
        card_w = content_w + corner_inset * 2
        # outer 宽仍用 notification_width；白区居中于阴影垫层内
        photo, ow, oh, ox, oy = _make_card_image(card_w, card_h, self.card_width)
        self.outer_w = ow
        self.outer_h = oh
        self._bg_photo = photo
        if photo:
            self._bg_lbl.configure(image=photo)
            self._bg_lbl.image = photo
        self._bg_lbl.pack()
        # 内容置于白卡片内侧（ox/oy 为白卡片左上角）
        white_w = max(40, self.card_width - _SHADOW_PAD * 2)
        # 水平居中内容于白卡片
        place_x = ox + max(0, (white_w - content_w) // 2)
        place_y = oy + corner_inset
        inner_frame.place(
            x=place_x,
            y=place_y,
            width=content_w,
            height=content_h,
        )

        self._bind_hover(self.win)
        self._bind_hover(self._shell)
        self._install_swipe_dismiss()

    def _install_swipe_dismiss(self) -> None:
        """左右滑清除：只关掉本桌面弹窗，与主页 UI 列表无关。"""
        state = {
            "armed": False,
            "swiping": False,
            "press_x": 0,
            "press_y": 0,
            "ox": 0,
            "oy": 0,
            "dx": 0,
        }
        threshold = 60

        def _is_close_target(event) -> bool:
            try:
                w = self.win.winfo_containing(event.x_root, event.y_root)
                return w is self._close
            except Exception:
                return False

        def _on_press(event):
            if self._destroyed or _is_close_target(event):
                return
            state["armed"] = True
            state["swiping"] = False
            state["press_x"] = event.x_root
            state["press_y"] = event.y_root
            state["dx"] = 0
            try:
                state["ox"] = self.win.winfo_x()
                state["oy"] = self.win.winfo_y()
            except tk.TclError:
                state["armed"] = False
            print(f"[DESKTOP-TOAST] press notif_id={self.notif_id!r}")

        def _on_motion(event):
            if not state["armed"] or self._destroyed:
                return
            dx = event.x_root - state["press_x"]
            dy = event.y_root - state["press_y"]
            if not state["swiping"]:
                if abs(dy) > abs(dx) and abs(dy) > 8:
                    state["armed"] = False
                    print("[DESKTOP-TOAST] swipe abort (vertical)")
                    return
                if abs(dx) < 10:
                    return
                state["swiping"] = True
                self._hovering = True
                self._cancel_timer()
                print(f"[DESKTOP-TOAST] swipe start dx={dx}")
            state["dx"] = dx
            try:
                alpha = max(0.35, 1.0 - min(1.0, abs(dx) / 160.0) * 0.55)
                self.win.geometry(
                    f"{self.outer_w}x{self.outer_h}+{state['ox'] + dx}+{state['oy']}"
                )
                self.win.attributes("-alpha", alpha)
            except tk.TclError:
                pass

        def _on_release(_event=None):
            if not state["armed"] or self._destroyed:
                return
            was = state["swiping"]
            dx = state["dx"]
            state["armed"] = False
            state["swiping"] = False
            print(f"[DESKTOP-TOAST] release swiping={was} dx={dx}")
            if was and abs(dx) >= threshold:
                print(f"[DESKTOP-TOAST] swipe dismiss notif_id={self.notif_id!r}")
                self.close(immediate=True)
                return
            if was:
                try:
                    self.win.geometry(
                        f"{self.outer_w}x{self.outer_h}+{state['ox']}+{state['oy']}"
                    )
                    self.win.attributes("-alpha", 1.0)
                except tk.TclError:
                    pass
                self._hovering = False
                self._schedule_dismiss()
                print("[DESKTOP-TOAST] swipe rebound")
                return
            if abs(dx) < 6:
                self._on_body_click()

        def _bind_swipe(widget: tk.Widget) -> None:
            if widget is getattr(self, "_close", None):
                return
            widget.bind("<ButtonPress-1>", _on_press, add="+")
            widget.bind("<B1-Motion>", _on_motion, add="+")
            widget.bind("<ButtonRelease-1>", _on_release, add="+")
            for child in widget.winfo_children():
                if child is getattr(self, "_close", None):
                    continue
                _bind_swipe(child)

        _bind_swipe(self._shell)
        self._close.unbind("<ButtonPress-1>")
        self._close.unbind("<B1-Motion>")
        self._close.unbind("<ButtonRelease-1>")
        self._close.bind("<Button-1>", self._on_close_click)
        try:
            self._close.lift()
        except tk.TclError:
            pass

    def _on_body_click(self) -> None:
        if self.notif_id and self.manager.on_click:
            try:
                print(f"[DESKTOP-TOAST] body click -> open history notif_id={self.notif_id!r}")
                self.manager.on_click(self.notif_id)
            except Exception:
                pass

    def _build_content(
        self,
        parent: tk.Frame,
        app_name: str,
        title_text: str,
        msg_text: str,
        meta: str,
    ) -> None:
        # 内容区强制白底，避免透出黑底
        inner = tk.Frame(parent, bg="#ffffff", bd=0, highlightthickness=0)
        inner.pack(fill=tk.BOTH, expand=True, padx=_PAD_X, pady=_PAD_Y)
        meta_font_size = max(6, self.font_size - 2)
        wrap_w = _content_wrap_width(self.card_width)

        row = tk.Frame(inner, bg="#ffffff", bd=0, highlightthickness=0)
        row.pack(fill=tk.X)

        av = tk.Label(
            row,
            bg="#ffffff",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
            width=_AVATAR,
            height=_AVATAR,
        )
        av.pack(side=tk.LEFT, anchor=tk.N)
        # 有图时用像素尺寸固定；禁止自动撑大
        av.configure(width=_AVATAR, height=_AVATAR)
        photo = _load_avatar(app_name, self.payload.get("icon_path") or "", self.manager._icon_cache)
        if photo:
            av.configure(image=photo, width=_AVATAR, height=_AVATAR)
            av.image = photo
            self._avatar_photo = photo
        else:
            self._avatar_photo = None

        right = tk.Frame(row, bg="#ffffff", bd=0, highlightthickness=0)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        title_row = tk.Frame(right, bg="#ffffff", bd=0, highlightthickness=0)
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
            wraplength=max(40, wrap_w - 20),
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
        self._close.bind("<Button-1>", self._on_close_click)
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
            max_preview_chars=self.manager.max_preview_chars,
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
                wraplength=max(40, wrap_w - 2),
            ).pack(anchor=tk.W, pady=(3, 0))

        # 正文点击打开历史：由滑动手势「轻点松开」触发，避免与左右滑冲突
        # （不再对 body 绑定 Button-1，防止点 × 时父级抢走语义）

    def _on_close_click(self, _event=None):
        """仅关闭桌面弹窗；绝不触碰主页通知列表 / history。"""
        print(f"[DESKTOP-TOAST] close click notif_id={self.notif_id!r}")
        self.close(immediate=True)
        return "break"

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
        remaining = max(500, int(self.duration_ms - elapsed))
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
        """关闭本桌面弹窗。禁止在此操作主页通知列表。"""
        if self._destroyed:
            return
        # 点 × 时鼠标仍在窗内，_hovering 会挡住淡出；用户主动关闭时强制清掉
        self._hovering = False
        print(
            f"[DESKTOP-TOAST] close immediate={immediate} notif_id={self.notif_id!r}"
        )
        if immediate:
            self._destroy()
            return
        self._start_fade()

    def _destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._cancel_timer()
        print(
            f"[DESKTOP-TOAST] destroyed notif_id={self.notif_id!r} "
            f"(home UI list untouched)"
        )
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
    MAX_PREVIEW_CHARS = MAX_PREVIEW_CHARS
    MAX_POP_NOTIFICATION = MAX_POP_NOTIFICATION

    def __init__(
        self,
        root: tk.Misc,
        on_click: Optional[Callable[[str], None]] = None,
        duration_ms: int = _DURATION_MS,
        max_visible: int = DEFAULT_MAX_POP_NOTIFICATION,
        popup_position: str = DEFAULT_POPUP_POSITION,
        notification_width: int = DEFAULT_NOTIFICATION_WIDTH,
        notification_font_size: int = DEFAULT_NOTIFICATION_FONT_SIZE,
        privacy_show_title: bool = True,
        privacy_show_msg: bool = True,
        max_preview_chars: int = DEFAULT_MAX_PREVIEW_CHARS,
        max_pop_notification: Optional[int] = None,
        notification_auto_close_seconds: Optional[int] = None,
    ):
        self.root = root
        self.on_click = on_click
        if notification_auto_close_seconds is not None:
            secs = normalize_notification_auto_close_seconds(notification_auto_close_seconds)
            self.duration_ms = secs * 1000
        else:
            self.duration_ms = max(1000, int(duration_ms or _DURATION_MS))
        # max_pop_notification 优先；兼容旧参数 max_visible
        pop_n = DEFAULT_MAX_POP_NOTIFICATION if max_pop_notification is None else max_pop_notification
        if max_pop_notification is None and max_visible != DEFAULT_MAX_POP_NOTIFICATION:
            pop_n = max_visible
        self.max_visible = normalize_max_pop_notification(pop_n)
        self.popup_position = normalize_popup_position(popup_position)
        self.notification_width = normalize_notification_width(notification_width)
        self.notification_font_size = normalize_notification_font_size(notification_font_size)
        self.privacy_show_title = bool(privacy_show_title)
        self.privacy_show_msg = bool(privacy_show_msg)
        self.max_preview_chars = normalize_max_preview_chars(max_preview_chars)
        self._items: List[CustomToastNotification] = []
        # 可视化弹窗等待队列（FIFO）；与 BLE notify_queue 无关，仅管界面展示
        self._ui_pop_queue: Deque[dict] = deque()
        self._suppress_queue_drain = 0
        self._icon_cache: dict = {}
        self._hide_bar = _HideAllBar(root, self.dismiss_all)

    @property
    def active_pop_count(self) -> int:
        """当前屏幕上正在显示的弹窗卡片数量。"""
        return len(self._items)

    def clear_ui_pop_queue(self) -> None:
        """清空弹窗等待队列（退出 / 清空历史 / 全部隐藏时调用）。"""
        self._ui_pop_queue.clear()

    def apply_ui_settings(
        self,
        *,
        popup_position: Optional[str] = None,
        notification_width: Optional[int] = None,
        notification_font_size: Optional[int] = None,
        privacy_show_title: Optional[bool] = None,
        privacy_show_msg: Optional[bool] = None,
        max_preview_chars: Optional[int] = None,
        max_pop_notification: Optional[int] = None,
        notification_auto_close_seconds: Optional[int] = None,
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
        if max_preview_chars is not None:
            self.max_preview_chars = normalize_max_preview_chars(max_preview_chars)
        if notification_auto_close_seconds is not None:
            # 只更新 Manager 默认时长；已创建卡片各自持有 duration_ms 快照，不受影响
            secs = normalize_notification_auto_close_seconds(notification_auto_close_seconds)
            self.duration_ms = secs * 1000
        max_pop_changed = False
        if max_pop_notification is not None:
            self.max_visible = normalize_max_pop_notification(max_pop_notification)
            max_pop_changed = True
        if self._items:
            try:
                self.root.after(0, lambda: self._layout(slide=None))
            except tk.TclError:
                pass
        # 提高同时可见上限时，立刻从排队队列补弹
        if max_pop_changed:
            try:
                self.root.after(0, self.drain_ui_pop_queue)
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
        play_sound: bool = False,
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

    def _enqueue_ui_pop(self, payload: dict) -> None:
        self._ui_pop_queue.append(payload)
        while len(self._ui_pop_queue) > _UI_POP_QUEUE_MAX:
            self._ui_pop_queue.popleft()

    def _show_on_main(self, payload: dict) -> None:
        app_name, title_text, msg_text, meta = _compose_message(payload)
        if not title_text and not msg_text:
            return

        # 已达同时可见上限：进入 ui_pop_queue 排队（历史/webhook 由上层已处理，不丢）
        if self.active_pop_count >= self.max_visible:
            self._enqueue_ui_pop(payload)
            return

        self._spawn_toast(payload, app_name, title_text, msg_text, meta)

    def _spawn_toast(
        self,
        payload: dict,
        app_name: str,
        title_text: str,
        msg_text: str,
        meta: str,
    ) -> CustomToastNotification:
        toast = CustomToastNotification(self, payload, app_name, title_text, msg_text, meta)
        print(
            f"[DESKTOP-TOAST] show desktop toast "
            f"app={app_name!r} title={title_text!r} notif_id={payload.get('notif_id')!r}"
        )
        pos = self.popup_position

        # 顶部锚定：新消息在最上；底部锚定：新消息在最下
        if pos.startswith("top"):
            self._items.insert(0, toast)
        else:
            self._items.append(toast)

        if payload.get("play_sound"):
            # 已禁用：提示音统一由 sound_helper.play_notify_wav 处理，禁止 MessageBeep/双重发声
            pass

        self._layout(slide=toast)
        return toast

    def drain_ui_pop_queue(self) -> None:
        """在可见名额有空时，从 ui_pop_queue FIFO 取出并弹出（无 sleep，主线程回调）。"""
        while self._ui_pop_queue and self.active_pop_count < self.max_visible:
            payload = self._ui_pop_queue.popleft()
            app_name, title_text, msg_text, meta = _compose_message(payload)
            if not title_text and not msg_text:
                continue
            self._spawn_toast(payload, app_name, title_text, msg_text, meta)
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
        # 全部隐藏：清空排队，避免关完现有又立刻补弹队列
        self.clear_ui_pop_queue()
        for item in list(self._items):
            item.close(immediate=True)

    def destroy_all(self) -> None:
        self._destroy_all_on_main()

    def _destroy_all_on_main(self) -> None:
        self.clear_ui_pop_queue()
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
        # 手动关闭 / 超时消失：尝试弹出排队中的下一条（layout 内部关闭溢出时不 drain，防循环）
        if self._suppress_queue_drain == 0:
            self.drain_ui_pop_queue()

    def _work_area(self) -> Tuple[int, int, int, int]:
        return _get_work_area(self.root)

    def _layout(self, slide: Optional[CustomToastNotification]) -> None:
        if not self._items:
            self._hide_bar.destroy_bar()
            return

        self._suppress_queue_drain += 1
        try:
            self._layout_impl(slide)
        finally:
            self._suppress_queue_drain = max(0, self._suppress_queue_drain - 1)
    def _layout_impl(self, slide: Optional[CustomToastNotification]) -> None:
        wa_left, wa_top, wa_w, wa_h = self._work_area()
        wa_bottom = wa_top + wa_h
        pos = self.popup_position
        m = _MARGIN
        # 外层窗口宽（含阴影垫层）；白卡片可视宽 = 外宽 - 两侧阴影
        outer_w = self.notification_width
        if self._items:
            outer_w = max(40, int(getattr(self._items[0], "outer_w", outer_w) or outer_w))
        pad = _SHADOW_PAD
        visual_w = max(40, outer_w - pad * 2)

        if "right" in pos:
            x = wa_left + wa_w - outer_w - m
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

        # 「全部隐藏」与白卡片左右齐平：同 inset，同可视宽度（禁止用整窗宽导致比卡片更宽）
        self._hide_bar.show_at(x + pad, bar_y, visual_w)
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
