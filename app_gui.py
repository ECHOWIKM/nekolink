# app_gui.py
import csv
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, filedialog
from typing import Callable, Dict, Optional, Tuple
from ttkbootstrap.scrolled import ScrolledFrame
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import i18n
from ancs_bridge import (
    BridgeConfig,
    BridgeManager,
    PUSH_TEMPLATE_PRESETS,
    PUSH_TEMPLATE_VARS,
    build_test_push_payload,
    format_ancs_date,
    get_app_display_name,
    get_device_display_name,
    get_config_path,
    get_ellipsis_text,
    load_config,
    render_push_template,
    resolve_raw_msg,
    resolve_raw_title,
    save_config,
    send_bark,
    send_custom_http,
    send_dingtalk_text,
    send_email,
    send_feishu,
    send_gotify,
    send_ntfy,
    send_pushdeer,
    send_pushover,
    send_pushplus,
    send_serverchan,
    send_telegram,
    send_wecom,
    send_wxpusher,
)
from tray_helper import TrayController
from popup_toast import (
    NotificationManager,
    normalize_popup_position,
    POPUP_POSITION_LABELS,
    normalize_notification_width,
    normalize_notification_font_size,
    normalize_max_preview_chars,
    normalize_max_pop_notification,
    normalize_notification_auto_close_seconds,
    normalize_popup_card_gap,
    parse_notification_auto_close_seconds,
    NOTIFICATION_WIDTH_LABELS,
    NOTIFICATION_FONT_LABELS,
)
from sound_helper import (
    SOUND_AVAILABLE,
    DEFAULT_SOUND_SELECTED_FILE,
    list_wav_filenames,
    normalize_app_sound_map,
    normalize_sound_selected_file,
    normalize_sound_volume,
    resolve_sound_path,
    sound_deps_error,
    update_runtime_sound_config,
)
from ui_theme import (
    FONT_BRAND,
    FONT_TITLE,
    MAIN_BG,
    PAGE_BG_COLOR,
    PAGE_PADX,
    PAGE_PADY,
    TEXT_MAIN,
    TEXT_SECONDARY,
    apply_global_theme,
)
from ui_shell import (
    APP_VERSION,
    SETTING_CARDS,
    Sidebar,
    apply_sidebar_styles,
    build_settings_card_grid,
)

CONFIG_PATH = get_config_path()
ICON_PATH = "icon.ico"
DEFAULT_TRAY_ICON_REL = "assets/icon.ico"

# 推送目标页 UI 色板（仅展示）
DEST_CARD_BG = "#FAFCFF"
DEST_CARD_BORDER = "#E8ECF5"
DEST_PRIMARY = "#5b8def"
DEST_TEXT = "#111827"
DEST_TEXT_SEC = "#6b7280"
DEST_SUCCESS = "#22c55e"
DEST_CARD_ACTIVE_BG = "#E8F0FC"
# 左右分栏：左栏宽度随卡片尺寸自动适配（3 列 × 150 + 间距）
DEST_CARD_SIZE = 150          # 卡片宽高（px），改这里
DEST_CARD_PAD = 10
DEST_ICON_EMOJI_SIZE = 36       # emoji 字号（px）；改这里调图标大小
DEST_ICON_TEXT_GAP = 4        # 图标与文字间距（px）
DEST_CARD_INNER_PAD = 12      # 卡片内边距（px）
DEST_LEFT_W = DEST_CARD_SIZE * 3 + DEST_CARD_PAD * 4 + 16  # 150×3 网格 + 边距
DEST_RIGHT_MIN_W = 400
DEST_RIGHT_MAX_W = 420
DEST_FORM_SHELL_W = 420
DEST_FORM_MAX_W = 360       # 表单字段最大可用宽度（px 级约束靠 grid EW）
DEST_FORM_ENTRY_W = 36      # Text 等仍用字符宽时的参考值
DEST_FORM_ROW_PAD = 10
DEST_BTN_W = 8
DEST_BTN_GAP = 12

DEST_SERVICES = (
    ("telegram", "✈️", "Telegram"),
    ("dingtalk", "🔔", "DingTalk"),
    ("ntfy", "🔕", "ntfy.sh"),
    ("webhook", "🌐", "Webhook"),
    ("gotify", "📤", "Gotify"),
    ("custom_http", "🔗", "HTTP POST"),
    ("feishu", "🦅", "飞书"),
    ("pushdeer", "🦌", "PushDeer"),
    ("bark", "🐶", "Bark"),
    ("pushplus", "➕", "PushPlus"),
    ("wxpusher", "💬", "WxPusher"),
    ("serverchan", "📢", "Server酱"),
    ("pushover", "🐾", "Pushover"),
    ("wecom", "🏢", "企业微信"),
)

DEST_TITLES = {
    "telegram": "Telegram",
    "dingtalk": "DingTalk",
    "ntfy": "ntfy.sh",
    "webhook": "Webhook",
    "gotify": "Gotify",
    "custom_http": "HTTP POST",
    "feishu": "飞书群机器人",
    "pushdeer": "PushDeer",
    "bark": "Bark",
    "pushplus": "PushPlus",
    "wxpusher": "WxPusher",
    "serverchan": "ServerChan",
    "pushover": "Pushover",
    "wecom": "企业微信群机器人",
}

# ---------------------------------------------------------------------------
# 历史消息内存 / 磁盘评估（注释说明，非自动备份业务）
# 场景：约 1 分钟 50 条推送 → 1 小时约 3000 条。
# 内存：单条几十~200 字符，3000 条仅数 MB，压力很小；但若无限保留几十万条会持续上涨。
# 磁盘：单条 csv/json 约 150 字节；50 条/分钟 ≈ 7.5KB/分；1 小时 ≈ 450KB；全天约 10MB 级。
# 保护：① 内存历史上限 MAX_HISTORY_COUNT，超限丢弃最旧；② 自动备份可选，默认关闭。
# ---------------------------------------------------------------------------
MAX_HISTORY_COUNT = 2000
_HISTORY_CSV_HEADER = ["时间", "设备", "APP名称", "APP包名", "通知标题", "通知内容"]


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _backup_dir() -> Path:
    d = _app_dir() / "backup"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_auto_backup_path() -> Path:
    return _backup_dir() / "notification_auto_backup.csv"


def resolve_tray_icon_path(cfg: Optional[BridgeConfig] = None) -> Optional[str]:
    """
    按 config.tray_icon_path 解析托盘图标；文件不存在则回退默认 icon。
    返回绝对路径字符串，或 None（最终由 TrayController 画占位图）。
    """
    candidates = []
    raw = ""
    if cfg is not None:
        raw = str(getattr(cfg, "tray_icon_path", "") or "").strip()
    if raw:
        p = Path(raw)
        if p.is_absolute():
            candidates.append(p)
        else:
            candidates.append(_app_dir() / raw)
            candidates.append(Path.cwd() / raw)
    # 默认回退
    for rel in (DEFAULT_TRAY_ICON_REL, ICON_PATH, "assets/icon.png", "icon.png"):
        candidates.append(_app_dir() / rel)
    seen = set()
    for c in candidates:
        try:
            key = str(c.resolve())
        except Exception:
            key = str(c)
        if key in seen:
            continue
        seen.add(key)
        try:
            if c.is_file():
                return str(c.resolve())
        except Exception:
            continue
    return None


def _autostart_task_command() -> str:
    """构造开机自启任务 /TR 命令行。"""
    from win_autostart import build_task_command_for_python

    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return build_task_command_for_python(str(Path(__file__).resolve()))


class App(tb.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        # 全局视觉规范：背景 / 字体 / 扁平控件（不改业务）
        apply_global_theme(self)

        self.log_q = queue.Queue()
        self.cfg = load_config(CONFIG_PATH)

        # i18n
        i18n.set_lang(getattr(self.cfg, "ui_lang", "zh"))

        self.title(i18n.t("app_title"))
        self.geometry("1300x1000")
        self.minsize(1100, 850)

        self.running = False
        # 内存历史列表（供导出）；上限 MAX_HISTORY_COUNT，超限丢弃最旧
        self.history = []
        self._hist_raw: dict = {}  # tree iid -> {"app": bundle_id, "device": mac, "notif_id": ...}
        self._notif_to_iid: dict = {}
        self._map_icon_paths: dict = {}

        self.popup_toast = NotificationManager(
            self,
            on_click=self.open_history_for_notif,
            popup_position=getattr(self.cfg, "popup_position", "bottom_right"),
            notification_width=getattr(self.cfg, "notification_width", 420),
            notification_font_size=getattr(self.cfg, "notification_font_size", 10),
            privacy_show_title=getattr(self.cfg, "privacy_show_title", True),
            privacy_show_msg=getattr(self.cfg, "privacy_show_msg", True),
            max_preview_chars=getattr(self.cfg, "max_preview_chars", 50),
            max_pop_notification=getattr(self.cfg, "max_pop_notification", 3),
            notification_auto_close_seconds=getattr(
                self.cfg,
                "desktop_toast_auto_dismiss",
                getattr(self.cfg, "notification_auto_close_seconds", 10),
            ),
            popup_card_gap=getattr(self.cfg, "popup_card_gap", 12),
        )
        self.manager = BridgeManager(
            self.cfg,
            self.log,
            self.on_notification,
            on_desktop_popup=self._show_desktop_popup,
        )
        # 启动即把提示音配置写入 sound_helper 内存运行时
        try:
            update_runtime_sound_config(
                sound_enable=bool(getattr(self.cfg, "sound_enable", True)),
                sound_volume=normalize_sound_volume(getattr(self.cfg, "sound_volume", 80)),
                sound_selected_file=normalize_sound_selected_file(
                    getattr(self.cfg, "sound_selected_file", DEFAULT_SOUND_SELECTED_FILE)
                ),
                app_sound_map=normalize_app_sound_map(
                    getattr(self.cfg, "app_sound_map", {}) or {}
                ),
            )
        except Exception:
            pass

        # 启动即确保 backup 目录存在
        try:
            _backup_dir()
        except Exception as e:
            print(f"[backup] mkdir failed: {e}")

        icon_path = resolve_tray_icon_path(self.cfg)
        self.tray = TrayController(
            title="NekoLink",
            on_restore=self.restore_from_tray,
            on_exit=self.exit_app,
            icon_path=icon_path,
        )
        self.tray.start()

        self.ui = {}  # widgets needing i18n refresh

        self._build_ui()
        # 窗口图标（仅 .ico 可靠）
        try:
            if icon_path and str(icon_path).lower().endswith(".ico"):
                self.iconbitmap(icon_path)
        except Exception:
            pass
        self.apply_i18n()

        self._flush_logs()

        # close -> tray
        self.protocol("WM_DELETE_WINDOW", self.on_close_to_tray)

    # ---------- UI ----------
    def _make_hidden_scrolled(self, parent) -> ScrolledFrame:
        """可配置页：隐藏滚动条；页面/滚动容器背景与全局 MAIN_BG 一致。"""
        wrap = tb.Frame(parent)
        wrap.pack(fill=BOTH, expand=True, padx=PAGE_PADX, pady=PAGE_PADY)
        # 禁止 bootstyle=light（会刷成灰底）；内容区走全局 TFrame = PAGE_BG
        sc = ScrolledFrame(wrap, autohide=False)
        sc.pack(fill=BOTH, expand=True)
        self._paint_page_bg(wrap)
        self._paint_page_bg(sc)
        try:
            self._paint_page_bg(sc.container)
        except Exception:
            pass
        try:
            sc.hide_scrollbars()
        except Exception:
            pass
        return sc

    def _paint_page_bg(self, widget) -> None:
        """仅统一页面/滚动容器背景，不改按钮/输入框等控件色。"""
        if widget is None:
            return
        bg = PAGE_BG_COLOR
        try:
            widget.configure(style="TFrame")
        except Exception:
            pass
        for key in ("background", "bg"):
            try:
                widget.configure(**{key: bg})
                break
            except Exception:
                continue

    def _enable_hidden_scroll(self, sc: ScrolledFrame) -> None:
        """在子控件全部加入后再绑定滚轮，并再次对齐页面背景。"""
        try:
            sc.hide_scrollbars()
        except Exception:
            pass
        try:
            sc.enable_scrolling()
        except Exception:
            pass
        self._paint_page_bg(sc)
        try:
            self._paint_page_bg(sc.container)
        except Exception:
            pass

    def _show_page(self, key: str) -> None:
        if key not in self._pages:
            return
        self._current_page = key
        for k, fr in self._pages.items():
            if k == key:
                fr.pack(fill=BOTH, expand=True)
            else:
                fr.pack_forget()
        if hasattr(self, "sidebar"):
            self.sidebar.set_active(key)
        if key == "settings":
            self._show_settings_hub()

    def _show_tab(self, key: str) -> None:
        """兼容旧调用。"""
        self._show_page(key)

    def _on_sidebar_nav(self, key: str) -> None:
        self._show_page(key)

    def _show_settings_hub(self) -> None:
        self._current_setting_panel = None
        if hasattr(self, "_settings_hub_frame"):
            self._settings_hub_frame.pack(fill=BOTH, expand=True)
        for fr in getattr(self, "_setting_panel_frames", {}).values():
            fr.pack_forget()

    def _show_setting_panel(self, key: str) -> None:
        if key not in getattr(self, "_setting_panel_frames", {}):
            return
        self._current_setting_panel = key
        if hasattr(self, "_settings_hub_frame"):
            self._settings_hub_frame.pack_forget()
        for k, fr in self._setting_panel_frames.items():
            if k == key:
                fr.pack(fill=BOTH, expand=True)
            else:
                fr.pack_forget()

    def _build_ui(self):
        shell = tb.Frame(self)
        shell.pack(fill=BOTH, expand=True)
        self._paint_page_bg(shell)

        self.sidebar = Sidebar(shell, on_nav=self._on_sidebar_nav)
        self.sidebar.pack(side=LEFT, fill=Y)
        apply_sidebar_styles(self)

        self.content_host = tb.Frame(shell)
        self.content_host.pack(side=LEFT, fill=BOTH, expand=True)
        self._paint_page_bg(self.content_host)

        self.page_host = tb.Frame(self.content_host)
        self.page_host.pack(fill=BOTH, expand=True)
        self._paint_page_bg(self.page_host)

        self.tab_main = tb.Frame(self.page_host)
        self.tab_history = tb.Frame(self.page_host)
        self.tab_dest = tb.Frame(self.page_host)
        self.tab_template = tb.Frame(self.page_host)
        self.tab_settings = tb.Frame(self.page_host)
        self.tab_logs = tb.Frame(self.page_host)
        # 设置子面板宿主（devices/filter 仅作子页内嵌）
        self.tab_devices = tb.Frame(self)
        self.tab_filter = tb.Frame(self)

        self._pages = {
            "main": self.tab_main,
            "history": self.tab_history,
            "dest": self.tab_dest,
            "template": self.tab_template,
            "settings": self.tab_settings,
            "logs": self.tab_logs,
        }
        for fr in self._pages.values():
            self._paint_page_bg(fr)

        self._setting_panel_frames = {}
        self._settings_cards = {}
        self._current_page = "main"
        self._current_setting_panel = None

        self._build_main()
        self._build_dest()
        self._build_template()
        self._build_history()
        self._build_logs()
        self._build_settings_hub()
        self._build_settings_panels()

        class _NbCompat:
            def __init__(self, app: "App"):
                self._app = app

            def select(self, tab_frame):
                for k, fr in self._app._pages.items():
                    if fr is tab_frame:
                        self._app._show_page(k)
                        return
                # 兼容旧 tab_history 等直接引用
                legacy = {
                    getattr(self._app, "tab_history", None): "history",
                    getattr(self._app, "tab_main", None): "main",
                    getattr(self._app, "tab_dest", None): "dest",
                    getattr(self._app, "tab_logs", None): "logs",
                }
                key = legacy.get(tab_frame)
                if key:
                    self._app._show_page(key)

        self.nb = _NbCompat(self)

        apply_global_theme(self)
        self._paint_page_bg(self.page_host)
        for fr in self._pages.values():
            self._paint_page_bg(fr)
        self._show_page("main")
        self._update_sidebar_status()

    def _build_settings_hub(self):
        self._settings_hub_frame = tb.Frame(self.tab_settings)
        self._settings_hub_frame.pack(fill=BOTH, expand=True)

        header = tb.Frame(self._settings_hub_frame, padding=(24, 20, 24, 8))
        header.pack(fill=X)
        top_row = tb.Frame(header)
        top_row.pack(fill=X)

        title_col = tb.Frame(top_row)
        title_col.pack(side=LEFT, fill=X, expand=True)
        self.ui["lbl_settings_title"] = tb.Label(
            title_col, text=i18n.t("settings_title"), font=("Segoe UI", 18, "bold")
        )
        self.ui["lbl_settings_title"].pack(anchor=W)
        self.ui["lbl_settings_subtitle"] = tb.Label(
            title_col, text=i18n.t("settings_subtitle"), bootstyle="secondary"
        )
        self.ui["lbl_settings_subtitle"].pack(anchor=W, pady=(4, 0))

        right_bar = tb.Frame(top_row)
        right_bar.pack(side=RIGHT)
        self.ui["lbl_lang"] = tb.Label(right_bar, text="Lang")
        self.ui["lbl_lang"].pack(side=LEFT, padx=(0, 6))
        self.var_lang = tk.StringVar(value=i18n.lang_label(i18n.get_lang()))
        self.cmb_lang = tb.Combobox(
            right_bar,
            width=10,
            textvariable=self.var_lang,
            values=[i18n.lang_label("zh"), i18n.lang_label("en"), i18n.lang_label("ja")],
            state="readonly",
        )
        self.cmb_lang.pack(side=LEFT, padx=(0, 8))

        def on_lang_change(_evt=None):
            label = self.var_lang.get().strip()
            code = "zh"
            for k, v in i18n.LANG_LABEL.items():
                if v == label:
                    code = k
                    break
            i18n.set_lang(code)
            self.cfg.ui_lang = code
            self.apply_i18n()

        self.cmb_lang.bind("<<ComboboxSelected>>", on_lang_change)
        self.ui["btn_global_save"] = tb.Button(
            right_bar, text=i18n.t("save"), bootstyle="primary", command=self.on_save
        )
        self.ui["btn_global_save"].pack(side=LEFT)

        grid_wrap, self._settings_cards = build_settings_card_grid(
            self._settings_hub_frame, on_card_click=self._show_setting_panel
        )
        grid_wrap.pack(fill=BOTH, expand=True)

    def _create_setting_panel(self, key: str, title_key: str, builder) -> tb.Frame:
        panel = tb.Frame(self.tab_settings)
        top = tb.Frame(panel, padding=(24, 16, 24, 0))
        top.pack(fill=X)
        self.ui[f"btn_back_{key}"] = tb.Button(
            top, text=i18n.t("settings_back"), bootstyle="link", command=self._show_settings_hub
        )
        self.ui[f"btn_back_{key}"].pack(side=LEFT)
        self.ui[f"lbl_panel_{key}"] = tb.Label(
            top, text=i18n.t(title_key), font=("Segoe UI", 14, "bold")
        )
        self.ui[f"lbl_panel_{key}"].pack(side=LEFT, padx=(8, 0))
        frm = self._make_hidden_scrolled(panel)
        builder(frm)
        self._enable_hidden_scroll(frm)
        return panel

    def _build_settings_panels(self):
        self._setting_panel_frames["notification"] = self._create_setting_panel(
            "notification", "card_notification", self._build_panel_notification
        )
        self._setting_panel_frames["desktop"] = self._create_setting_panel(
            "desktop", "card_desktop", self._build_panel_desktop
        )
        self._setting_panel_frames["push"] = self._create_setting_panel(
            "push", "card_push", self._build_panel_push
        )
        self._setting_panel_frames["ble"] = self._create_setting_panel(
            "ble", "card_ble", self._build_panel_ble
        )
        self._setting_panel_frames["data"] = self._create_setting_panel(
            "data", "card_data", self._build_panel_data
        )
        self._setting_panel_frames["sound"] = self._create_setting_panel(
            "sound", "card_sound", self._build_panel_sound
        )
        self._setting_panel_frames["about"] = self._create_setting_panel(
            "about", "card_about", self._build_panel_about
        )

    def _update_sidebar_status(self) -> None:
        if not hasattr(self, "sidebar"):
            return
        self.sidebar.set_run_status(bool(self.running))
        connected = bool(self.running and (self.cfg.ble_addresses or []))
        detail = ""
        if connected and self.cfg.ble_addresses:
            addr = self.cfg.ble_addresses[0]
            detail = (self.cfg.device_aliases or {}).get(addr, addr)
            if len(detail) > 16:
                detail = detail[:14] + "…"
        self.sidebar.set_ble_status(connected, detail)


    def apply_i18n(self):
        self.title(i18n.t("app_title"))

        if hasattr(self, "sidebar"):
            self.sidebar.apply_i18n()
            self._update_sidebar_status()

        if "lbl_settings_title" in self.ui:
            self.ui["lbl_settings_title"].config(text=i18n.t("settings_title"))
            self.ui["lbl_settings_subtitle"].config(text=i18n.t("settings_subtitle"))
        if "btn_global_save" in self.ui:
            self.ui["btn_global_save"].config(text=i18n.t("save"))
        for key, _title_key, _desc_key, icon in SETTING_CARDS:
            card = getattr(self, "_settings_cards", {}).get(key)
            if card:
                extra = APP_VERSION if key == "about" else ""
                card.update_text(
                    icon,
                    i18n.t(_title_key),
                    i18n.t(_desc_key),
                    extra_right=extra,
                )
        for key, title_key, _d, _i in SETTING_CARDS:
            if f"btn_back_{key}" in self.ui:
                self.ui[f"btn_back_{key}"].config(text=i18n.t("settings_back"))
            if f"lbl_panel_{key}" in self.ui:
                self.ui[f"lbl_panel_{key}"].config(text=i18n.t(title_key))

        # main
        self.ui["lbl_run_control"].config(text=i18n.t("run_control"))
        self.ui["btn_start"].config(text=i18n.t("start"))
        self.ui["btn_stop"].config(text=i18n.t("stop"))
        self.ui["lbl_preview"].config(text=i18n.t("latest_preview"))
        self.ui["lbl_push_preview"].config(text=i18n.t("push_preview"))
        self.ui["lbl_tip_tray"].config(text=i18n.t("tip_tray"))
        if "lbl_tpl_page_title" in self.ui:
            self.ui["lbl_tpl_page_title"].config(text=i18n.t("nav_template"))
            self.ui["lbl_tpl_preset"].config(text=i18n.t("tpl_preset"))
            self.ui["lbl_tpl_var"].config(text=i18n.t("tpl_var"))
            self.ui["btn_tpl_insert"].config(text=i18n.t("tpl_insert"))
            self.ui["lbl_tpl_hint"].config(text=i18n.t("tpl_hint"))
            preset_labels = [
                i18n.t("tpl_preset_default"),
                i18n.t("tpl_preset_simple"),
                i18n.t("tpl_preset_detail"),
            ]
            self.cmb_tpl_preset.config(values=preset_labels)
            if not self.var_tpl_preset.get():
                self.cmb_tpl_preset.set(preset_labels[0])
        if "lbl_push_dedup" in self.ui:
            self.ui["lbl_push_dedup"].config(text=i18n.t("dedup_sec"))
            self.ui["chk_code_on"].config(text=i18n.t("enable_code_detect"))
            self.ui["chk_code_sep"].config(text=i18n.t("send_code_sep"))
        if "lbl_data_history" in self.ui:
            self.ui["lbl_data_history"].config(text=i18n.t("history_limit"))
            self.ui["lbl_data_clear_hint"].config(text=i18n.t("data_clear_hint"))
        if "lbl_about_version" in self.ui:
            self.ui["lbl_about_version"].config(
                text=f"{i18n.t('about_version')}: {APP_VERSION}"
            )
            self.ui["lbl_about_author"].config(text=i18n.t("about_author"))

        # devices (dest page uses card grid; BLE devices panel unchanged)
        if "lbl_dest_title" in self.ui:
            self.ui["lbl_dest_title"].config(text=i18n.t("nav_dest"))
            self.ui["lbl_dest_subtitle"].config(text=i18n.t("dest_subtitle"))
        self._refresh_dest_cards()
        if getattr(self, "selected_push_service", None):
            self._render_dest_detail_form(self.selected_push_service)
        else:
            self._show_dest_detail_placeholder()
        if "lbl_devices_title" in self.ui:
            self.ui["lbl_devices_title"].config(text=i18n.t("selected_ble"))
            self.ui["btn_scan"].config(text=i18n.t("scan"))
            self.ui["btn_add_addr"].config(text=i18n.t("add"))
            self.ui["btn_remove_addr"].config(text=i18n.t("remove_selected"))
            self.ui["txt_scan_hint"].config(text=i18n.t("scan_hint"))
            self.ui["lbl_device_alias"].config(text=i18n.t("device_alias"))
            self.ui["btn_set_device_alias"].config(text=i18n.t("set_alias"))
            if "dev_tree" in self.ui:
                self.ui["dev_tree"].heading("addr", text=i18n.t("col_ble_addr"))
                self.ui["dev_tree"].heading("alias", text=i18n.t("col_alias"))

        # history / app map
        if "lbl_app_map" in self.ui:
            self.ui["lbl_app_map"].config(text=i18n.t("app_map_title"))
            self.ui["lbl_map_hint"].config(text=i18n.t("app_map_hint"))
            self.ui["lbl_map_bundle"].config(text=i18n.t("col_bundle_id"))
            self.ui["lbl_map_name"].config(text=i18n.t("col_app_name"))
            self.ui["btn_map_upsert"].config(text=i18n.t("map_upsert"))
            self.ui["btn_map_remove"].config(text=i18n.t("remove_selected"))
        if "map_tree" in self.ui:
            self.ui["map_tree"].heading("bundle", text=i18n.t("col_bundle_id"))
            self.ui["map_tree"].heading("name", text=i18n.t("col_app_name"))
            self.ui["map_tree"].heading("block", text=i18n.t("col_skip_webhook"))
            self.ui["map_tree"].heading("icon", text=i18n.t("col_icon"))
        if hasattr(self, "ui") and "lbl_map_icon" in self.ui:
            self.ui["lbl_map_icon"].config(text=i18n.t("col_icon"))
            self.ui["btn_map_icon"].config(text=i18n.t("browse_icon"))
            self.ui["lbl_map_icon_hint"].config(text=i18n.t("map_icon_hint"))
        if "tree" in self.ui:
            self.ui["tree"].heading("device", text=i18n.t("col_alias"))
            self.ui["tree"].heading("app", text=i18n.t("col_app_name"))

        # filter
        if "lbl_block_intro" in self.ui:
            self.ui["lbl_block_intro"].config(text=i18n.t("block_intro"))
            self.ui["chk_block_ci"].config(text=i18n.t("case_insensitive"))
            self.ui["btn_add_block"].config(text=i18n.t("add"))
            self.ui["btn_remove_block"].config(text=i18n.t("remove_selected"))

        # settings panels
        if "chk_battery" in self.ui:
            self.ui["chk_battery"].config(text=i18n.t("misc_battery"))
        if "chk_toast" in self.ui:
            self.ui["chk_toast"].config(text=i18n.t("misc_toast"))
            self.ui["lbl_toast_hint"].config(text=i18n.t("misc_toast_hint"))
            self.ui["btn_test_toast"].config(text=i18n.t("misc_toast_test"))
        if "lbl_popup_position" in self.ui:
            self.ui["lbl_popup_position"].config(text=i18n.t("misc_popup_position"))
        if hasattr(self, "cmb_popup_pos"):
            cur = self._popup_pos_key_from_label(self.var_popup_pos.get())
            self.cmb_popup_pos.configure(values=[self._popup_pos_label_from_key(k) for k in self._popup_pos_keys])
            self.var_popup_pos.set(self._popup_pos_label_from_key(cur))
        if "lbl_notif_font" in self.ui:
            self.ui["lbl_notif_font"].config(text=i18n.t("misc_notif_font"))
        if hasattr(self, "cmb_notif_font"):
            cur_font = self._notif_font_key_from_label(self.var_notif_font.get())
            font_values = list(dict.fromkeys(
                [self._notif_font_label_from_key(k) for k in self._notif_font_keys]
            ))
            self.cmb_notif_font.configure(values=font_values)
            label = self._notif_font_label_from_key(cur_font)
            self.cmb_notif_font.set(label)
            self.var_notif_font.set(label)
        if "lbl_notif_font_restart" in self.ui:
            self.ui["lbl_notif_font_restart"].config(text=i18n.t("misc_restart_hint"))
        if "lbl_notif_width" in self.ui:
            self.ui["lbl_notif_width"].config(text=i18n.t("misc_notif_width"))
        if hasattr(self, "cmb_notif_width"):
            cur_width = self._notif_width_key_from_label(self.var_notif_width.get())
            width_values = list(dict.fromkeys(
                [self._notif_width_label_from_key(k) for k in self._notif_width_keys]
            ))
            self.cmb_notif_width.configure(values=width_values)
            self.var_notif_width.set(self._notif_width_label_from_key(cur_width))
        if "lbl_notif_width_restart" in self.ui:
            self.ui["lbl_notif_width_restart"].config(text=i18n.t("misc_restart_hint"))
        if "lbl_max_preview" in self.ui:
            self.ui["lbl_max_preview"].config(text=i18n.t("misc_max_preview"))
        if "lbl_max_pop" in self.ui:
            self.ui["lbl_max_pop"].config(text=i18n.t("misc_max_pop"))
        if "lbl_card_gap" in self.ui:
            self.ui["lbl_card_gap"].config(text=i18n.t("misc_card_gap"))
            self.ui["lbl_card_gap_hint"].config(text=i18n.t("misc_card_gap_hint"))
            self.ui["lbl_card_gap_restart"].config(text=i18n.t("misc_restart_hint"))
        if "lbl_auto_close" in self.ui:
            self.ui["lbl_auto_close"].config(text=i18n.t("misc_auto_close"))
            self.ui["lbl_auto_close_hint"].config(text=i18n.t("misc_auto_close_hint"))
        if "chk_sound_enable" in self.ui:
            self.ui["chk_sound_enable"].config(text=i18n.t("misc_sound_enable"))
            if "lbl_sound_file" in self.ui:
                self.ui["lbl_sound_file"].config(text=i18n.t("misc_sound_file"))
            self.ui["lbl_sound_volume"].config(text=i18n.t("misc_sound_volume"))
            self.ui["lbl_sound_hint"].config(text=i18n.t("misc_sound_hint"))
        if "chk_auto_backup" in self.ui:
            self.ui["chk_auto_backup"].config(text=i18n.t("misc_auto_backup"))
            self.ui["lbl_auto_backup_hint"].config(text=i18n.t("misc_auto_backup_hint"))
            self.ui["lbl_auto_backup_path"].config(text=i18n.t("misc_auto_backup_path"))
        if "chk_auto_start" in self.ui:
            self.ui["chk_auto_start"].config(text=i18n.t("misc_auto_start"))
            self.ui["lbl_auto_start_hint"].config(text=i18n.t("misc_auto_start_hint"))
        if "lbl_tray_icon" in self.ui:
            self.ui["lbl_tray_icon"].config(text=i18n.t("misc_tray_icon"))
            self.ui["btn_tray_icon_browse"].config(text=i18n.t("browse"))
            self.ui["lbl_tray_icon_hint"].config(text=i18n.t("misc_tray_icon_hint"))
        if hasattr(self, "privacy_frm"):
            self.privacy_frm.configure(text=i18n.t("privacy_title"))
        if "chk_privacy_show_title" in self.ui:
            self.ui["chk_privacy_show_title"].config(text=i18n.t("privacy_show_title"))
            self.ui["lbl_privacy_show_title_hint"].config(text=i18n.t("privacy_show_title_hint"))
            self.ui["chk_privacy_show_msg"].config(text=i18n.t("privacy_show_msg"))
            self.ui["lbl_privacy_show_msg_hint"].config(text=i18n.t("privacy_show_msg_hint"))

        # history/logs
        self.ui["lbl_history_title"].config(text=i18n.t("history_title"))
        self.ui["btn_clear_history"].config(text=i18n.t("clear"))
        self.ui["btn_copy_history"].config(text=i18n.t("copy_selected"))
        if "btn_export_history" in self.ui:
            self.ui["btn_export_history"].config(text=i18n.t("history_export_all"))
        self.ui["lbl_logs_title"].config(text=i18n.t("tab_logs"))
        self.ui["btn_clear_logs"].config(text=i18n.t("clear"))

    # ---------- Tabs ----------
    def _build_main(self):
        frm = tb.Frame(self.tab_main, padding=(PAGE_PADX, PAGE_PADY))
        frm.pack(fill=BOTH, expand=True)

        left = tb.Frame(frm)
        left.pack(side=LEFT, fill=Y, padx=(0, 16))

        self.ui["lbl_run_control"] = tb.Label(left, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_run_control"].pack(anchor=W, pady=(0, 8))

        btns = tb.Frame(left)
        btns.pack(anchor=W, pady=(0, 8))

        self.ui["btn_start"] = tb.Button(btns, text="", bootstyle="success", command=self.on_start)
        self.ui["btn_start"].pack(side=LEFT, padx=(0, 8))
        self.ui["btn_stop"] = tb.Button(btns, text="", bootstyle="danger", command=self.on_stop)
        self.ui["btn_stop"].pack(side=LEFT)

        self.ui["lbl_tip_tray"] = tb.Label(left, text="", bootstyle="secondary", wraplength=280, justify=LEFT)
        self.ui["lbl_tip_tray"].pack(anchor=W, pady=(16, 0))

        right = tb.Frame(frm)
        right.pack(side=LEFT, fill=BOTH, expand=True)

        self.ui["lbl_preview"] = tb.Label(right, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_preview"].pack(anchor=W)

        self.preview = tk.Text(right, height=10, wrap="word")
        self.preview.pack(fill=X, pady=(8, 8))
        self.preview.insert("end", "（暂无）\n")
        self.preview.bind("<Double-1>", lambda _e: self._show_last_notification_detail())

        self.ui["lbl_push_preview"] = tb.Label(right, text="推送预览", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_push_preview"].pack(anchor=W)

        self.push_preview = tk.Text(right, height=10, wrap="word")
        self.push_preview.pack(fill=X, pady=(8, 8))
        self.push_preview.insert("end", "（暂无）\n")
        self._last_payload: Optional[dict] = None

    def _build_template(self):
        frm = tb.Frame(self.tab_template, padding=(PAGE_PADX, PAGE_PADY))
        frm.pack(fill=BOTH, expand=True)

        self.ui["lbl_tpl_page_title"] = tb.Label(frm, text="", font=("Segoe UI", 14, "bold"))
        self.ui["lbl_tpl_page_title"].pack(anchor=W, pady=(0, 10))

        preset_row = tb.Frame(frm)
        preset_row.pack(fill=X, pady=(0, 6))
        self.ui["lbl_tpl_preset"] = tb.Label(preset_row, text="预设")
        self.ui["lbl_tpl_preset"].pack(side=LEFT, padx=(0, 8))
        self.var_tpl_preset = tk.StringVar()
        self.cmb_tpl_preset = tb.Combobox(
            preset_row,
            textvariable=self.var_tpl_preset,
            state="readonly",
            width=18,
        )
        self.cmb_tpl_preset.pack(side=LEFT)
        self.cmb_tpl_preset.bind("<<ComboboxSelected>>", self._on_tpl_preset_change)

        self.txt_push_template = tk.Text(frm, height=12, wrap="word")
        self.txt_push_template.pack(fill=BOTH, expand=True, pady=(0, 6))
        tpl_text = getattr(self.cfg, "push_template", "") or PUSH_TEMPLATE_PRESETS["default"]
        self.txt_push_template.insert("1.0", tpl_text)

        var_row = tb.Frame(frm)
        var_row.pack(fill=X, pady=(0, 6))
        self.ui["lbl_tpl_var"] = tb.Label(var_row, text="插入变量")
        self.ui["lbl_tpl_var"].pack(side=LEFT, padx=(0, 8))
        self.var_tpl_insert = tk.StringVar()
        var_keys = [f"{{{k}}}" for k, _ in PUSH_TEMPLATE_VARS]
        self.cmb_tpl_var = tb.Combobox(var_row, textvariable=self.var_tpl_insert, values=var_keys, width=18)
        self.cmb_tpl_var.pack(side=LEFT, padx=(0, 8))
        if var_keys:
            self.cmb_tpl_var.set(var_keys[0])
        self.ui["btn_tpl_insert"] = tb.Button(var_row, text="插入", bootstyle="secondary", command=self.insert_template_var)
        self.ui["btn_tpl_insert"].pack(side=LEFT)

        hint = "  ".join(f"{{{k}}}" for k, _ in PUSH_TEMPLATE_VARS)
        self.ui["lbl_tpl_hint"] = tb.Label(frm, text=hint, bootstyle="secondary", wraplength=640, justify=LEFT)
        self.ui["lbl_tpl_hint"].pack(anchor=W)

    def _build_devices(self, parent=None):
        host = parent if parent is not None else self.tab_devices
        if parent is None:
            frm = self._make_hidden_scrolled(host)
        else:
            frm = parent

        top = tb.Frame(frm)
        top.pack(fill=X, pady=(0, 10))

        self.ui["lbl_devices_title"] = tb.Label(top, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_devices_title"].pack(side=LEFT)

        self.ui["btn_scan"] = tb.Button(top, text="", bootstyle="info", command=self.scan_devices)
        self.ui["btn_scan"].pack(side=RIGHT)

        self.dev_tree = tb.Treeview(frm, columns=("addr", "alias"), show="headings", height=8, selectmode="browse")
        self.dev_tree.heading("addr", text="BLE 地址")
        self.dev_tree.heading("alias", text="别名")
        self.dev_tree.column("addr", width=220, anchor=W)
        self.dev_tree.column("alias", width=220, anchor=W)
        self.dev_tree.pack(fill=X, pady=(0, 10))
        self.ui["dev_tree"] = self.dev_tree
        self._reload_device_tree()

        alias_row = tb.Frame(frm)
        alias_row.pack(fill=X, pady=(0, 10))
        self.ui["lbl_device_alias"] = tb.Label(alias_row, text="设备别名")
        self.ui["lbl_device_alias"].pack(side=LEFT, padx=(0, 8))
        self.var_device_alias = tk.StringVar()
        tb.Entry(alias_row, textvariable=self.var_device_alias, width=32).pack(side=LEFT, padx=(0, 8))
        self.ui["btn_set_device_alias"] = tb.Button(
            alias_row, text="设置别名", bootstyle="secondary", command=self.set_device_alias
        )
        self.ui["btn_set_device_alias"].pack(side=LEFT)
        self.dev_tree.bind("<<TreeviewSelect>>", self._on_device_select)

        ctl = tb.Frame(frm)
        ctl.pack(fill=X)

        self.var_add_addr = tk.StringVar()
        tb.Entry(ctl, textvariable=self.var_add_addr, width=40).pack(side=LEFT, padx=(0, 8))
        self.ui["btn_add_addr"] = tb.Button(ctl, text="", bootstyle="secondary", command=self.add_addr)
        self.ui["btn_add_addr"].pack(side=LEFT, padx=(0, 8))
        self.ui["btn_remove_addr"] = tb.Button(ctl, text="", bootstyle="warning", command=self.remove_selected_addr)
        self.ui["btn_remove_addr"].pack(side=LEFT)

        tb.Separator(frm).pack(fill=X, pady=12)

        self.ui["txt_scan_hint"] = tb.Label(frm, text="", bootstyle="secondary")
        self.ui["txt_scan_hint"].pack(anchor=W, pady=(0, 6))

        self.scan_box = tk.Text(frm, height=8, wrap="word")
        self.scan_box.pack(fill=BOTH, expand=True)
        self.scan_box.insert("end", "")

        def on_dbl_click(_evt):
            try:
                sel = self.scan_box.get("insert linestart", "insert lineend").strip()
                if "addr=" in sel:
                    addr = sel.split("addr=")[1].split()[0].strip()
                    self.var_add_addr.set(addr)
            except Exception:
                pass

        self.scan_box.bind("<Double-Button-1>", on_dbl_click)
        self._enable_hidden_scroll(frm)

    def _reload_device_tree(self):
        self.dev_tree.delete(*self.dev_tree.get_children())
        aliases = getattr(self.cfg, "device_aliases", {}) or {}
        for addr in (self.cfg.ble_addresses or []):
            self.dev_tree.insert("", "end", values=(addr, aliases.get(addr, "")))

    def _on_device_select(self, _evt=None):
        sel = self.dev_tree.selection()
        if not sel:
            return
        vals = self.dev_tree.item(sel[0], "values")
        if len(vals) >= 2:
            self.var_device_alias.set(vals[1])

    def set_device_alias(self):
        sel = self.dev_tree.selection()
        if not sel:
            messagebox.showwarning(i18n.t("missing"), i18n.t("select_device_first"))
            return
        alias = self.var_device_alias.get().strip()
        vals = list(self.dev_tree.item(sel[0], "values"))
        if len(vals) < 1:
            return
        addr = vals[0]
        self.dev_tree.item(sel[0], values=(addr, alias))
        if not hasattr(self.cfg, "device_aliases") or self.cfg.device_aliases is None:
            self.cfg.device_aliases = {}
        if alias:
            self.cfg.device_aliases[addr] = alias
        else:
            self.cfg.device_aliases.pop(addr, None)
        # 仅更新界面与内存；点顶部【保存】才写入 config.json
        self.log(f"[UI] 设备别名已更新（未落盘）: {addr} -> {alias or '(空)'}")

    def _init_dest_vars(self) -> None:
        """初始化推送目标相关变量（业务字段名与 collect_config 保持一致）。"""
        self.var_tg_on = tk.BooleanVar(value=self.cfg.enable_telegram)
        self.var_tg_token = tk.StringVar(value=self.cfg.telegram_bot_token)
        self.var_tg_chat = tk.StringVar(value=self.cfg.telegram_chat_id)

        self.var_dt_on = tk.BooleanVar(value=getattr(self.cfg, "enable_dingtalk", False))
        self.var_dt_webhook = tk.StringVar(value=getattr(self.cfg, "dingtalk_webhook", ""))
        self.var_dt_secret = tk.StringVar(value=getattr(self.cfg, "dingtalk_secret", ""))

        self.var_ntfy_on = tk.BooleanVar(value=getattr(self.cfg, "enable_ntfy", False))
        self.var_ntfy_url = tk.StringVar(value=getattr(self.cfg, "ntfy_url", ""))

        self.var_webhook_full = tk.BooleanVar(
            value=bool(getattr(self.cfg, "webhook_use_full_message", True))
        )

        self.var_gotify_on = tk.BooleanVar(value=getattr(self.cfg, "enable_gotify", False))
        self.var_gotify_url = tk.StringVar(value=getattr(self.cfg, "gotify_url", ""))
        self.var_gotify_token = tk.StringVar(value=getattr(self.cfg, "gotify_token", ""))
        self.var_gotify_prio = tk.StringVar(value=str(getattr(self.cfg, "gotify_priority", 5)))

        self.var_custom_http_on = tk.BooleanVar(value=getattr(self.cfg, "enable_custom_http", False))
        self.var_custom_http_url = tk.StringVar(value=getattr(self.cfg, "custom_http_url", ""))
        self.var_custom_http_headers = tk.StringVar(
            value=getattr(self.cfg, "custom_http_headers_json", "{}")
        )
        self.var_custom_http_body = tk.StringVar(
            value=getattr(
                self.cfg,
                "custom_http_body_template",
                '{"title":"{{title}}","msg":"{{msg}}","app":"{{app_name}}",'
                '"device":"{{device_name}}","time":"{{date_time}}"}',
            )
        )

        self.var_feishu_on = tk.BooleanVar(value=getattr(self.cfg, "enable_feishu", False))
        self.var_feishu_webhook = tk.StringVar(value=getattr(self.cfg, "feishu_webhook_url", ""))

        self.var_pushdeer_on = tk.BooleanVar(value=getattr(self.cfg, "enable_pushdeer", False))
        self.var_pushdeer_key = tk.StringVar(value=getattr(self.cfg, "pushdeer_key", ""))

        self.var_bark_on = tk.BooleanVar(value=getattr(self.cfg, "enable_bark", False))
        self.var_bark_key = tk.StringVar(value=getattr(self.cfg, "bark_api_key", ""))
        self.var_bark_sound = tk.StringVar(value=getattr(self.cfg, "bark_sound", ""))

        self.var_pushplus_on = tk.BooleanVar(value=getattr(self.cfg, "enable_pushplus", False))
        self.var_pushplus_token = tk.StringVar(value=getattr(self.cfg, "pushplus_token", ""))

        self.var_wxpusher_on = tk.BooleanVar(value=getattr(self.cfg, "enable_wxpusher", False))
        self.var_wxpusher_token = tk.StringVar(value=getattr(self.cfg, "wxpusher_app_token", ""))
        self.var_wxpusher_topic = tk.StringVar(value=getattr(self.cfg, "wxpusher_topic_id", ""))

        self.var_serverchan_on = tk.BooleanVar(value=getattr(self.cfg, "enable_serverchan", False))
        self.var_serverchan_key = tk.StringVar(value=getattr(self.cfg, "serverchan_sendkey", ""))

        self.var_pushover_on = tk.BooleanVar(value=getattr(self.cfg, "enable_pushover", False))
        self.var_pushover_token = tk.StringVar(value=getattr(self.cfg, "pushover_api_token", ""))
        self.var_pushover_user = tk.StringVar(value=getattr(self.cfg, "pushover_user_key", ""))

        self.var_wecom_on = tk.BooleanVar(value=getattr(self.cfg, "enable_wecom", False))
        self.var_wecom_webhook = tk.StringVar(value=getattr(self.cfg, "wecom_webhook_url", ""))

        self._dest_text_syncers: list = []

        # Email：无卡片入口，保留变量供 collect_config / 全局保存
        self.var_mail_on = tk.BooleanVar(value=self.cfg.enable_email)
        self.var_smtp_host = tk.StringVar(value=self.cfg.smtp_host)
        self.var_smtp_port = tk.StringVar(value=str(self.cfg.smtp_port))
        self.var_smtp_user = tk.StringVar(value=self.cfg.smtp_user)
        self.var_smtp_pass = tk.StringVar(value=self.cfg.smtp_pass)
        self.var_email_from = tk.StringVar(value=self.cfg.email_from)
        self.var_email_to = tk.StringVar(value=self.cfg.email_to)

    def _dest_is_configured(self, key: str) -> bool:
        if key == "telegram":
            return bool(self.var_tg_token.get().strip() and self.var_tg_chat.get().strip())
        if key == "dingtalk":
            return bool(self.var_dt_webhook.get().strip())
        if key == "ntfy":
            return bool(self.var_ntfy_url.get().strip())
        if key == "webhook":
            return True
        if key == "gotify":
            return bool(self.var_gotify_url.get().strip() and self.var_gotify_token.get().strip())
        if key == "custom_http":
            return bool(self.var_custom_http_url.get().strip())
        if key == "feishu":
            return bool(self.var_feishu_webhook.get().strip())
        if key == "pushdeer":
            return bool(self.var_pushdeer_key.get().strip())
        if key == "bark":
            return bool(self.var_bark_key.get().strip())
        if key == "pushplus":
            return bool(self.var_pushplus_token.get().strip())
        if key == "wxpusher":
            return bool(self.var_wxpusher_token.get().strip())
        if key == "serverchan":
            return bool(self.var_serverchan_key.get().strip())
        if key == "pushover":
            return bool(self.var_pushover_token.get().strip() and self.var_pushover_user.get().strip())
        if key == "wecom":
            return bool(self.var_wecom_webhook.get().strip())
        return False

    def _dest_is_enabled(self, key: str) -> bool:
        mapping = {
            "telegram": self.var_tg_on,
            "dingtalk": self.var_dt_on,
            "ntfy": self.var_ntfy_on,
            "webhook": self.var_webhook_full,
            "gotify": self.var_gotify_on,
            "custom_http": self.var_custom_http_on,
            "feishu": self.var_feishu_on,
            "pushdeer": self.var_pushdeer_on,
            "bark": self.var_bark_on,
            "pushplus": self.var_pushplus_on,
            "wxpusher": self.var_wxpusher_on,
            "serverchan": self.var_serverchan_on,
            "pushover": self.var_pushover_on,
            "wecom": self.var_wecom_on,
        }
        var = mapping.get(key)
        return bool(var.get()) if var else False

    def _refresh_dest_cards(self) -> None:
        cards = getattr(self, "_dest_cards", {}) or {}
        for key, widgets in cards.items():
            cfg_lbl = widgets.get("cfg_lbl")
            en_lbl = widgets.get("en_lbl")
            if not cfg_lbl or not en_lbl:
                continue
            configured = self._dest_is_configured(key)
            enabled = self._dest_is_enabled(key)
            cfg_lbl.configure(
                text=i18n.t("dest_configured") if configured else i18n.t("dest_not_configured"),
                fg=DEST_SUCCESS if configured else DEST_TEXT_SEC,
            )
            en_lbl.configure(
                text=i18n.t("dest_enabled") if enabled else i18n.t("dest_disabled"),
                fg=DEST_SUCCESS if enabled else DEST_TEXT_SEC,
            )
        self._highlight_dest_card(getattr(self, "selected_push_service", None))

    def _highlight_dest_card(self, key: Optional[str]) -> None:
        """左栏卡片选中高亮：仅背景/边框色，严禁改宽高。"""
        cards = getattr(self, "_dest_cards", {}) or {}
        for k, widgets in cards.items():
            card = widgets.get("card")
            inner = widgets.get("inner")
            active = k == key
            bg = DEST_CARD_ACTIVE_BG if active else DEST_CARD_BG
            border = DEST_PRIMARY if active else DEST_CARD_BORDER
            if card:
                card.configure(bg=bg, highlightbackground=border)
            if inner:
                inner.configure(bg=bg)
                for child in inner.winfo_children():
                    try:
                        child.configure(bg=bg)
                    except Exception:
                        pass
            for lbl in (
                widgets.get("cfg_lbl"),
                widgets.get("en_lbl"),
                widgets.get("name_lbl"),
                widgets.get("icon_lbl"),
            ):
                if lbl:
                    lbl.configure(bg=bg)
            icon_zone = widgets.get("icon_zone")
            if icon_zone:
                icon_zone.configure(bg=bg)

    def _create_dest_service_card(self, parent, key: str, emoji: str, name: str) -> tk.Frame:
        # 150×150 正方形；emoji 负字号=像素；自上而下紧凑排版，避免图标区留白
        card = tk.Frame(
            parent,
            width=DEST_CARD_SIZE,
            height=DEST_CARD_SIZE,
            bg=DEST_CARD_BG,
            highlightthickness=1,
            highlightbackground=DEST_CARD_BORDER,
            cursor="hand2",
        )
        card.grid_propagate(False)
        card.pack_propagate(False)

        stack = tk.Frame(card, bg=DEST_CARD_BG, cursor="hand2")
        stack.pack(
            fill=BOTH,
            expand=True,
            padx=DEST_CARD_INNER_PAD,
            pady=DEST_CARD_INNER_PAD,
        )

        icon_lbl = tk.Label(
            stack,
            text=emoji,
            bg=DEST_CARD_BG,
            font=("Segoe UI Emoji", -DEST_ICON_EMOJI_SIZE),
            anchor=CENTER,
            justify=CENTER,
            cursor="hand2",
        )
        icon_lbl.pack(anchor=CENTER)

        name_lbl = tk.Label(
            stack,
            text=name,
            bg=DEST_CARD_BG,
            fg=DEST_TEXT,
            font=("Segoe UI", 10, "bold"),
            wraplength=DEST_CARD_SIZE - DEST_CARD_INNER_PAD * 2,
            justify=CENTER,
            anchor=CENTER,
            cursor="hand2",
        )
        name_lbl.pack(anchor=CENTER, pady=(DEST_ICON_TEXT_GAP, 0))

        cfg_lbl = tk.Label(
            stack,
            text="",
            bg=DEST_CARD_BG,
            fg=DEST_TEXT_SEC,
            font=("Segoe UI", 9),
            anchor=CENTER,
            justify=CENTER,
            cursor="hand2",
        )
        cfg_lbl.pack(anchor=CENTER, pady=(2, 0))
        en_lbl = tk.Label(
            stack,
            text="",
            bg=DEST_CARD_BG,
            fg=DEST_TEXT_SEC,
            font=("Segoe UI", 9),
            anchor=CENTER,
            justify=CENTER,
            cursor="hand2",
        )
        en_lbl.pack(anchor=CENTER, pady=(1, 0))

        self._dest_cards[key] = {
            "card": card,
            "inner": stack,
            "icon_zone": None,
            "icon_lbl": icon_lbl,
            "name_lbl": name_lbl,
            "cfg_lbl": cfg_lbl,
            "en_lbl": en_lbl,
        }

        def _select(_e=None, k=key):
            self._select_push_service(k)

        for w in (card, stack, icon_lbl, name_lbl, cfg_lbl, en_lbl):
            w.bind("<Button-1>", _select)
        return card

    def _hide_dest_form(self) -> None:
        """隐藏右侧表单，恢复占位提示。"""
        self.selected_push_service = None
        self._highlight_dest_card(None)
        self._show_dest_detail_placeholder()

    def _clear_dest_form_inner(self) -> None:
        """只销毁右栏【动态表单内层】子组件，保留外层 Frame。"""
        host = self.ui.get("dest_form_inner")
        if not host:
            return
        for w in host.winfo_children():
            w.destroy()

    def _show_dest_detail_placeholder(self) -> None:
        self._clear_dest_form_inner()
        host = self.ui.get("dest_form_inner")
        if not host:
            return
        wrap = tk.Frame(host, bg=DEST_CARD_BG)
        wrap.pack(fill=BOTH, expand=True)
        tk.Label(
            wrap,
            text=i18n.t("dest_select_hint"),
            bg=DEST_CARD_BG,
            fg=DEST_TEXT_SEC,
            font=("Segoe UI", 11),
            justify=CENTER,
            wraplength=DEST_FORM_MAX_W,
        ).place(relx=0.5, rely=0.5, anchor=CENTER)

    def _dest_form_secret_row(self, parent, row: int, label: str, var: tk.StringVar) -> int:
        pad = DEST_FORM_ROW_PAD
        tb.Label(parent, text=label).grid(row=row, column=0, sticky=W, pady=(0, 4))
        ent_row = tb.Frame(parent)
        ent_row.grid(row=row + 1, column=0, sticky=EW, pady=(0, pad))
        ent_row.grid_columnconfigure(0, weight=1)
        ent_row.grid_columnconfigure(1, weight=0)
        ent = tb.Entry(ent_row, textvariable=var, show="•")
        ent.grid(row=0, column=0, sticky=EW)
        hidden = {"v": True}

        def toggle():
            hidden["v"] = not hidden["v"]
            ent.configure(show="•" if hidden["v"] else "")

        tb.Button(ent_row, text="👁", width=3, bootstyle="secondary", command=toggle).grid(
            row=0, column=1, padx=(6, 0), sticky=E
        )
        return row + 2

    def _dest_form_add_actions(self, parent, row: int, test_cmd=None) -> None:
        btns = tb.Frame(parent)
        btns.grid(row=row, column=0, sticky=W, pady=(DEST_FORM_ROW_PAD, 0))

        def _save():
            self._sync_dest_text_widgets()
            self._persist_config(show_msg=True)
            self._refresh_dest_cards()

        if test_cmd:
            tb.Button(
                btns, text="测试", width=DEST_BTN_W, bootstyle="success", command=test_cmd
            ).pack(side=LEFT, padx=(0, DEST_BTN_GAP))
        tb.Button(
            btns, text=i18n.t("save"), width=DEST_BTN_W, bootstyle="primary", command=_save
        ).pack(side=LEFT, padx=(0, DEST_BTN_GAP))
        tb.Button(
            btns, text="隐藏", width=DEST_BTN_W, bootstyle="secondary", command=self._hide_dest_form
        ).pack(side=LEFT)

    def _sync_dest_text_widgets(self) -> None:
        for fn in getattr(self, "_dest_text_syncers", []) or []:
            try:
                fn()
            except Exception:
                pass

    def _dest_form_enable_row(self, shell, row: int, text: str, var: tk.BooleanVar, pad: int) -> int:
        tb.Checkbutton(shell, text=text, variable=var, bootstyle="round-toggle").grid(
            row=row, column=0, sticky=W, pady=(0, pad)
        )
        return row + 1

    def _dest_form_entry_row(
        self, shell, row: int, label: str, var: tk.StringVar, pad: int, *, width: int = DEST_FORM_ENTRY_W
    ) -> int:
        tb.Label(shell, text=label).grid(row=row, column=0, sticky=W, pady=(0, 4))
        tb.Entry(shell, textvariable=var, width=width).grid(
            row=row + 1, column=0, sticky=EW, pady=(0, pad)
        )
        return row + 2

    def _dest_form_text_area(
        self, shell, row: int, label: str, var: tk.StringVar, pad: int, *, height: int = 3
    ) -> int:
        tb.Label(shell, text=label).grid(row=row, column=0, sticky=NW, pady=(0, 4))
        txt = tk.Text(shell, width=DEST_FORM_ENTRY_W, height=height, wrap=WORD, font=("Segoe UI", 9))
        txt.grid(row=row + 1, column=0, sticky=EW, pady=(0, pad))
        txt.insert("1.0", var.get())

        def _sync(_e=None):
            var.set(txt.get("1.0", "end-1c"))

        txt.bind("<FocusOut>", _sync)
        self._dest_text_syncers.append(_sync)
        return row + 2

    def _dest_test_async(self, channel: str, validate, run_test: Callable[[], None]) -> None:
        """后台线程执行 Test，避免阻塞 UI。"""
        self._sync_dest_text_widgets()
        err = validate()
        if err:
            messagebox.showwarning(i18n.t("missing"), err)
            return

        def worker():
            try:
                run_test()
                self.after(0, lambda: messagebox.showinfo(i18n.t("ok"), f"{channel} test sent"))
            except Exception as e:
                self.log(f"[TEST:{channel}] failed: {e}")
                self.after(0, lambda: messagebox.showerror(i18n.t("fail"), f"{channel} failed: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _dest_test_content(self) -> Tuple[str, str, dict]:
        payload = build_test_push_payload()
        cfg = self.collect_config()
        title = "NekoLink Test"
        text = render_push_template(cfg.push_template, payload, cfg)
        return title, text, payload

    def _dest_build_form_telegram(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable Telegram", self.var_tg_on, pad)
        row = self._dest_form_secret_row(shell, row, "Bot Token", self.var_tg_token)
        row = self._dest_form_entry_row(shell, row, "Chat ID", self.var_tg_chat, pad)
        return row, self.test_telegram

    def _dest_build_form_dingtalk(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable DingTalk", self.var_dt_on, pad)
        row = self._dest_form_entry_row(shell, row, "Webhook", self.var_dt_webhook, pad)
        row = self._dest_form_secret_row(shell, row, "Secret (sign)", self.var_dt_secret)
        return row, self.test_dingtalk

    def _dest_build_form_ntfy(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable ntfy", self.var_ntfy_on, pad)
        row = self._dest_form_entry_row(shell, row, "Topic URL", self.var_ntfy_url, pad)
        return row, self.test_ntfy

    def _dest_build_form_webhook(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable Webhook", self.var_webhook_full, pad)
        tb.Label(
            shell,
            text="Webhook/TG/Gotify/邮件发送完整原文（关闭则发送预览省略文本）",
            wraplength=DEST_FORM_MAX_W,
            bootstyle="secondary",
            justify=LEFT,
        ).grid(row=row, column=0, sticky=W, pady=(0, pad))
        row += 1
        tb.Label(
            shell,
            text="机器人 Webhook URL 请在 DingTalk / 企业微信等卡片中配置。",
            wraplength=DEST_FORM_MAX_W,
            bootstyle="secondary",
            justify=LEFT,
        ).grid(row=row, column=0, sticky=W, pady=(0, pad))
        return row + 1, None

    def _dest_build_form_gotify(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable Gotify", self.var_gotify_on, pad)
        row = self._dest_form_entry_row(shell, row, "Server URL", self.var_gotify_url, pad)
        row = self._dest_form_secret_row(shell, row, "App Token", self.var_gotify_token)
        row = self._dest_form_entry_row(shell, row, "Priority", self.var_gotify_prio, pad, width=8)
        return row, self.test_gotify

    def _dest_build_form_custom_http(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable HTTP POST", self.var_custom_http_on, pad)
        row = self._dest_form_entry_row(shell, row, "POST URL", self.var_custom_http_url, pad)
        row = self._dest_form_text_area(shell, row, "Headers JSON", self.var_custom_http_headers, pad, height=3)
        row = self._dest_form_text_area(shell, row, "Body 模板", self.var_custom_http_body, pad, height=5)
        tb.Label(
            shell,
            text="Body 变量：{{title}} {{msg}} {{app_name}} {{device_name}} {{date_time}}",
            wraplength=DEST_FORM_MAX_W,
            bootstyle="secondary",
            justify=LEFT,
        ).grid(row=row, column=0, sticky=W, pady=(0, pad))
        return row + 1, self.test_custom_http

    def _dest_build_form_feishu(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable 飞书", self.var_feishu_on, pad)
        row = self._dest_form_entry_row(shell, row, "Webhook URL", self.var_feishu_webhook, pad)
        return row, self.test_feishu

    def _dest_build_form_pushdeer(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable PushDeer", self.var_pushdeer_on, pad)
        row = self._dest_form_entry_row(shell, row, "PushDeer Key", self.var_pushdeer_key, pad)
        return row, self.test_pushdeer

    def _dest_build_form_bark(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable Bark", self.var_bark_on, pad)
        row = self._dest_form_entry_row(shell, row, "API Key", self.var_bark_key, pad)
        row = self._dest_form_entry_row(shell, row, "Sound (可选)", self.var_bark_sound, pad)
        return row, self.test_bark

    def _dest_build_form_pushplus(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable PushPlus", self.var_pushplus_on, pad)
        row = self._dest_form_entry_row(shell, row, "Token", self.var_pushplus_token, pad)
        return row, self.test_pushplus

    def _dest_build_form_wxpusher(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable WxPusher", self.var_wxpusher_on, pad)
        row = self._dest_form_entry_row(shell, row, "App Token", self.var_wxpusher_token, pad)
        row = self._dest_form_entry_row(shell, row, "Topic ID", self.var_wxpusher_topic, pad)
        return row, self.test_wxpusher

    def _dest_build_form_serverchan(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable Server酱", self.var_serverchan_on, pad)
        row = self._dest_form_entry_row(shell, row, "SendKey", self.var_serverchan_key, pad)
        return row, self.test_serverchan

    def _dest_build_form_pushover(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable Pushover", self.var_pushover_on, pad)
        row = self._dest_form_entry_row(shell, row, "API Token", self.var_pushover_token, pad)
        row = self._dest_form_entry_row(shell, row, "User Key", self.var_pushover_user, pad)
        return row, self.test_pushover

    def _dest_build_form_wecom(self, shell, row: int, pad: int):
        row = self._dest_form_enable_row(shell, row, "Enable 企业微信", self.var_wecom_on, pad)
        row = self._dest_form_entry_row(shell, row, "Webhook URL", self.var_wecom_webhook, pad)
        return row, self.test_wecom

    def _select_push_service(self, key: str) -> None:
        """点击左栏卡片：切换右侧详情表单。"""
        self.selected_push_service = key
        self._highlight_dest_card(key)
        self._render_dest_detail_form(key)

    def _render_dest_detail_form(self, key: str) -> None:
        """在右栏【动态表单内层】渲染配置表单；外层 Frame 永不销毁。"""
        self._clear_dest_form_inner()
        self._dest_text_syncers = []
        host = self.ui.get("dest_form_inner")
        if not host:
            return

        builders = {
            "telegram": self._dest_build_form_telegram,
            "dingtalk": self._dest_build_form_dingtalk,
            "ntfy": self._dest_build_form_ntfy,
            "webhook": self._dest_build_form_webhook,
            "gotify": self._dest_build_form_gotify,
            "custom_http": self._dest_build_form_custom_http,
            "feishu": self._dest_build_form_feishu,
            "pushdeer": self._dest_build_form_pushdeer,
            "bark": self._dest_build_form_bark,
            "pushplus": self._dest_build_form_pushplus,
            "wxpusher": self._dest_build_form_wxpusher,
            "serverchan": self._dest_build_form_serverchan,
            "pushover": self._dest_build_form_pushover,
            "wecom": self._dest_build_form_wecom,
        }
        builder = builders.get(key)
        if not builder:
            self._show_dest_detail_placeholder()
            return

        pad = DEST_FORM_ROW_PAD
        form_wrap = tb.Frame(host, padding=(0, 0))
        form_wrap.pack(anchor=NW, fill=X)

        shell = tb.Frame(form_wrap)
        shell.pack(anchor=NW, fill=X)
        shell.grid_columnconfigure(0, weight=1)

        tb.Label(
            shell,
            text=f"{i18n.t('dest_config_title')} {DEST_TITLES.get(key, key)}",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, sticky=W, pady=(0, pad))

        row, test_cmd = builder(shell, 1, pad)
        self._dest_form_add_actions(shell, row, test_cmd)

    # ✅ Destinations: 左右分栏（左栏 width=DEST_LEFT_W）+ 右栏外层永久 / 内层动态
    def _build_dest(self):
        self._init_dest_vars()
        self._dest_cards: Dict[str, dict] = {}
        self.selected_push_service = None

        outer = tb.Frame(self.tab_dest, padding=(PAGE_PADX, PAGE_PADY))
        outer.pack(fill=BOTH, expand=True)

        head = tb.Frame(outer)
        head.pack(fill=X, pady=(0, 16))
        self.ui["lbl_dest_title"] = tb.Label(head, text=i18n.t("nav_dest"), font=("Segoe UI", 18, "bold"))
        self.ui["lbl_dest_title"].pack(anchor=W)
        self.ui["lbl_dest_subtitle"] = tb.Label(
            head, text=i18n.t("dest_subtitle"), bootstyle="secondary", font=("Segoe UI", 10)
        )
        self.ui["lbl_dest_subtitle"].pack(anchor=W, pady=(4, 0))

        scroll_host = tb.Frame(outer)
        scroll_host.pack(fill=BOTH, expand=True)

        # ── 主分栏 body：column0 锁左栏 DEST_LEFT_W；column1 weight=1 右栏留白 ──
        body = tb.Frame(scroll_host)
        body.pack(fill=BOTH, expand=True)
        body.grid_columnconfigure(0, weight=0, minsize=DEST_LEFT_W)
        body.grid_columnconfigure(1, weight=1, minsize=DEST_RIGHT_MIN_W)
        body.grid_rowconfigure(0, weight=1)

        # 左栏：固定 DEST_LEFT_W，禁止横向拉伸
        left = tk.Frame(
            body,
            width=DEST_LEFT_W,
            bg=DEST_CARD_BG,
            highlightthickness=1,
            highlightbackground=DEST_CARD_BORDER,
        )
        left.grid(row=0, column=0, sticky=NS, padx=(0, 12))
        left.grid_propagate(False)

        card_grid = tk.Frame(left, bg=DEST_CARD_BG)
        card_grid.pack(anchor=N, padx=8, pady=8)
        n_services = len(DEST_SERVICES)
        n_rows = (n_services + 2) // 3
        total_slots = n_rows * 3
        for c in range(3):
            card_grid.grid_columnconfigure(c, weight=0, minsize=DEST_CARD_SIZE)
        for r in range(n_rows):
            card_grid.grid_rowconfigure(r, weight=0, minsize=DEST_CARD_SIZE)

        for idx in range(total_slots):
            row_i, col_i = divmod(idx, 3)
            if idx < n_services:
                key, emoji, name = DEST_SERVICES[idx]
                card = self._create_dest_service_card(card_grid, key, emoji, name)
            else:
                card = tk.Frame(
                    card_grid,
                    width=DEST_CARD_SIZE,
                    height=DEST_CARD_SIZE,
                    bg=DEST_CARD_BG,
                )
                card.grid_propagate(False)
            card.grid(row=row_i, column=col_i, padx=DEST_CARD_PAD, pady=DEST_CARD_PAD)

        # 右栏【外层容器】：永久保留，切换服务时不销毁
        right_outer = tk.Frame(
            body,
            bg=DEST_CARD_BG,
            highlightthickness=1,
            highlightbackground=DEST_CARD_BORDER,
        )
        right_outer.grid(row=0, column=1, sticky=NSEW)

        right_pad = tk.Frame(right_outer, bg=DEST_CARD_BG)
        right_pad.pack(anchor=NW, fill=BOTH, expand=True, padx=16, pady=16)

        # 右栏内容区 max 420px，窗口放大时右侧仅多出空白
        right_shell = tk.Frame(right_pad, bg=DEST_CARD_BG, width=DEST_RIGHT_MAX_W)
        right_shell.pack(fill=BOTH, expand=True)

        # 右栏【动态表单内层】：仅 destroy 此层子组件
        form_inner = tk.Frame(right_shell, bg=DEST_CARD_BG)
        form_inner.pack(fill=BOTH, expand=True)

        self.ui["dest_detail_outer"] = right_outer
        self.ui["dest_form_inner"] = form_inner
        self.ui["dest_detail_host"] = form_inner  # 兼容旧引用

        self._show_dest_detail_placeholder()
        self._refresh_dest_cards()

    def _build_filter(self, parent=None):
        host = parent if parent is not None else self.tab_filter
        if parent is None:
            frm = self._make_hidden_scrolled(host)
        else:
            frm = parent

        self.ui["lbl_block_intro"] = tb.Label(frm, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_block_intro"].pack(anchor=W, pady=(0, 8))

        self.var_block_ci = tk.BooleanVar(value=self.cfg.block_case_insensitive)
        self.ui["chk_block_ci"] = tb.Checkbutton(frm, text="", variable=self.var_block_ci, bootstyle="round-toggle")
        self.ui["chk_block_ci"].pack(anchor=W, pady=(0, 10))

        self.lst_block = tk.Listbox(frm, height=10)
        self.lst_block.pack(fill=X, pady=(0, 10))
        for k in (self.cfg.block_keywords or []):
            self.lst_block.insert("end", k)

        ctl = tb.Frame(frm)
        ctl.pack(fill=X)

        self.var_block_input = tk.StringVar()
        tb.Entry(ctl, textvariable=self.var_block_input, width=40).pack(side=LEFT, padx=(0, 8))
        self.ui["btn_add_block"] = tb.Button(ctl, text="", bootstyle="secondary", command=self.add_block)
        self.ui["btn_add_block"].pack(side=LEFT, padx=(0, 8))
        self.ui["btn_remove_block"] = tb.Button(ctl, text="", bootstyle="warning", command=self.remove_block)
        self.ui["btn_remove_block"].pack(side=LEFT)
        self._enable_hidden_scroll(frm)

    def _build_panel_notification(self, frm):
        """通知设置：电量、验证码、屏蔽关键词。"""
        self.var_show_battery = tk.BooleanVar(value=getattr(self.cfg, "show_battery_in_message", True))
        self.ui["chk_battery"] = tb.Checkbutton(
            frm, text="", variable=self.var_show_battery, bootstyle="round-toggle"
        )
        self.ui["chk_battery"].pack(anchor=W, pady=(0, 8))

        self.var_code_on = tk.BooleanVar(value=self.cfg.enable_code_highlight)
        self.var_code_sep = tk.BooleanVar(value=self.cfg.code_send_separately)
        self.ui["chk_code_on"] = tb.Checkbutton(
            frm, text="", variable=self.var_code_on, bootstyle="round-toggle"
        )
        self.ui["chk_code_on"].pack(anchor=W, pady=(0, 6))
        self.ui["chk_code_sep"] = tb.Checkbutton(
            frm, text="", variable=self.var_code_sep, bootstyle="round-toggle"
        )
        self.ui["chk_code_sep"].pack(anchor=W, pady=(0, 12))

        tb.Separator(frm).pack(fill=X, pady=(4, 10))
        self._build_filter(parent=frm)

    def _build_panel_desktop(self, frm):
        """桌面通知：全部弹窗相关旧杂项控件。"""
        self.var_win_toast = tk.BooleanVar(value=getattr(self.cfg, "enable_windows_toast", True))

        toast_row = tb.Frame(frm)
        toast_row.pack(fill=X, anchor=W, pady=(0, 2))
        self.ui["chk_toast"] = tb.Checkbutton(
            toast_row, text="", variable=self.var_win_toast, bootstyle="round-toggle"
        )
        self.ui["chk_toast"].pack(side=LEFT)
        self.ui["btn_test_toast"] = tb.Button(
            toast_row, text="测试弹窗", bootstyle="info", command=self.test_desktop_toast
        )
        self.ui["btn_test_toast"].pack(side=LEFT, padx=(12, 0))

        self.ui["lbl_toast_hint"] = tb.Label(
            frm, text="", bootstyle="secondary", wraplength=520, justify=LEFT
        )
        self.ui["lbl_toast_hint"].pack(anchor=W, pady=(0, 4))

        pos_row = tb.Frame(frm)
        pos_row.pack(fill=X, anchor=W, pady=(0, 3))
        self._popup_pos_keys = ["bottom_right", "top_right", "bottom_left", "top_left"]
        self.ui["lbl_popup_position"] = tb.Label(pos_row, text="弹窗位置")
        self.ui["lbl_popup_position"].pack(side=LEFT, padx=(0, 8))
        self.var_popup_pos = tk.StringVar(
            value=self._popup_pos_label_from_key(getattr(self.cfg, "popup_position", "bottom_right"))
        )
        self.cmb_popup_pos = tb.Combobox(
            pos_row,
            textvariable=self.var_popup_pos,
            values=[self._popup_pos_label_from_key(k) for k in self._popup_pos_keys],
            state="readonly",
            width=14,
        )
        self.cmb_popup_pos.pack(side=LEFT)

        font_row = tb.Frame(frm)
        font_row.pack(fill=X, anchor=W, pady=(0, 3))
        self._notif_font_keys = [6, 8, 10, 12]
        self.ui["lbl_notif_font"] = tb.Label(font_row, text="通知字体大小")
        self.ui["lbl_notif_font"].pack(side=LEFT, padx=(0, 8))
        _font_size_cfg = normalize_notification_font_size(
            getattr(self.cfg, "notification_font_size", 10)
        )
        _font_label_cfg = self._notif_font_label_from_key(_font_size_cfg)
        self.var_notif_font = tk.StringVar(value=_font_label_cfg)
        font_values = list(
            dict.fromkeys([self._notif_font_label_from_key(k) for k in self._notif_font_keys])
        )
        self.cmb_notif_font = tb.Combobox(
            font_row,
            textvariable=self.var_notif_font,
            values=font_values,
            state="readonly",
            width=14,
        )
        self.cmb_notif_font.pack(side=LEFT)
        self.cmb_notif_font.set(_font_label_cfg)
        self.var_notif_font.set(_font_label_cfg)
        self.ui["lbl_notif_font_restart"] = tb.Label(
            font_row, text="修改后需要重启程序生效", bootstyle="secondary"
        )
        self.ui["lbl_notif_font_restart"].pack(side=LEFT, padx=(8, 0))

        width_row = tb.Frame(frm)
        width_row.pack(fill=X, anchor=W, pady=(0, 3))
        self._notif_width_keys = [300, 420, 480, 540]
        self.ui["lbl_notif_width"] = tb.Label(width_row, text="通知弹窗宽度")
        self.ui["lbl_notif_width"].pack(side=LEFT, padx=(0, 8))
        self.var_notif_width = tk.StringVar(
            value=self._notif_width_label_from_key(getattr(self.cfg, "notification_width", 420))
        )
        width_values = list(
            dict.fromkeys([self._notif_width_label_from_key(k) for k in self._notif_width_keys])
        )
        self.cmb_notif_width = tb.Combobox(
            width_row,
            textvariable=self.var_notif_width,
            values=width_values,
            state="readonly",
            width=14,
        )
        self.cmb_notif_width.pack(side=LEFT)
        self.ui["lbl_notif_width_restart"] = tb.Label(
            width_row, text="修改后需要重启程序生效", bootstyle="secondary"
        )
        self.ui["lbl_notif_width_restart"].pack(side=LEFT, padx=(8, 0))

        preview_row = tb.Frame(frm)
        preview_row.pack(fill=X, anchor=W, pady=(0, 3))
        self.ui["lbl_max_preview"] = tb.Label(preview_row, text="消息最大预览字数：")
        self.ui["lbl_max_preview"].pack(side=LEFT, padx=(0, 8))
        self.var_max_preview = tk.StringVar(
            value=str(normalize_max_preview_chars(getattr(self.cfg, "max_preview_chars", 50)))
        )
        self.ent_max_preview = tb.Entry(preview_row, textvariable=self.var_max_preview, width=8)
        self.ent_max_preview.pack(side=LEFT)

        self.ui["lbl_max_pop"] = tb.Label(
            frm,
            text="屏幕最多同时可见弹窗数量；超额消息排队，关闭现有弹窗后自动继续弹出。",
            wraplength=520,
            justify=LEFT,
        )
        self.ui["lbl_max_pop"].pack(anchor=W, pady=(0, 2))
        pop_row = tb.Frame(frm)
        pop_row.pack(fill=X, anchor=W, pady=(0, 3))
        self.var_max_pop = tk.IntVar(
            value=normalize_max_pop_notification(getattr(self.cfg, "max_pop_notification", 3))
        )
        self.ui["lbl_max_pop_val"] = tb.Label(pop_row, text=str(self.var_max_pop.get()), width=3)
        self.ui["lbl_max_pop_val"].pack(side=LEFT, padx=(0, 8))
        self.scl_max_pop = tb.Scale(
            pop_row,
            from_=1,
            to=10,
            orient=HORIZONTAL,
            length=180,
            command=lambda v: self._on_max_pop_scale(v),
        )
        self.scl_max_pop.set(self.var_max_pop.get())
        self.scl_max_pop.pack(side=LEFT, fill=X, expand=True)

        gap_row = tb.Frame(frm)
        gap_row.pack(fill=X, anchor=W, pady=(4, 1))
        self.ui["lbl_card_gap"] = tb.Label(gap_row, text="弹窗卡片垂直间距(px)")
        self.ui["lbl_card_gap"].pack(side=LEFT, padx=(0, 8))
        self.var_card_gap = tk.StringVar(
            value=str(normalize_popup_card_gap(getattr(self.cfg, "popup_card_gap", 12)))
        )
        self.ent_card_gap = tb.Entry(gap_row, textvariable=self.var_card_gap, width=8)
        self.ent_card_gap.pack(side=LEFT)
        self.ui["lbl_card_gap_hint"] = tb.Label(
            frm,
            text="范围4‑60，控制多个桌面弹窗互相之间的空隙。",
            bootstyle="secondary",
            wraplength=520,
            justify=LEFT,
        )
        self.ui["lbl_card_gap_hint"].pack(anchor=W, pady=(0, 1))
        self.ui["lbl_card_gap_restart"] = tb.Label(
            frm,
            text="修改后需要重启程序生效",
            bootstyle="secondary",
            wraplength=520,
            justify=LEFT,
        )
        self.ui["lbl_card_gap_restart"].pack(anchor=W, pady=(0, 3))

        close_row = tb.Frame(frm)
        close_row.pack(fill=X, anchor=W, pady=(0, 1))
        self.ui["lbl_auto_close"] = tb.Label(close_row, text="桌面弹窗自动关闭(秒)")
        self.ui["lbl_auto_close"].pack(side=LEFT, padx=(0, 8))
        self.var_auto_close = tk.StringVar(
            value=str(
                normalize_notification_auto_close_seconds(
                    getattr(
                        self.cfg,
                        "desktop_toast_auto_dismiss",
                        getattr(self.cfg, "notification_auto_close_seconds", 10),
                    )
                )
            )
        )
        self.ent_auto_close = tb.Entry(close_row, textvariable=self.var_auto_close, width=8)
        self.ent_auto_close.pack(side=LEFT)
        self.ui["lbl_auto_close_hint"] = tb.Label(
            frm,
            text="范围3‑120秒；仅控制桌面弹窗超时，与历史/主页列表无关",
            bootstyle="secondary",
            wraplength=520,
            justify=LEFT,
        )
        self.ui["lbl_auto_close_hint"].pack(anchor=W, pady=(0, 3))

        self.privacy_frm = tb.Labelframe(frm, text="隐私设置", padding=6)
        self.privacy_frm.pack(fill=X, anchor=W, pady=(4, 4))

        def _normalize_preview_entry():
            val = normalize_max_preview_chars(self.var_max_preview.get())
            self.var_max_preview.set(str(val))
            return val

        def _sync_popup_ui_settings(_evt=None):
            preview_chars = _normalize_preview_entry()
            max_pop = normalize_max_pop_notification(self.var_max_pop.get())
            self.var_max_pop.set(max_pop)
            self.ui["lbl_max_pop_val"].config(text=str(max_pop))
            self.popup_toast.apply_ui_settings(
                popup_position=self._popup_pos_key_from_label(self.var_popup_pos.get()),
                notification_font_size=self._notif_font_key_from_label(self.var_notif_font.get()),
                notification_width=self._notif_width_key_from_label(self.var_notif_width.get()),
                privacy_show_title=bool(self.var_privacy_show_title.get()),
                privacy_show_msg=bool(self.var_privacy_show_msg.get()),
                max_preview_chars=preview_chars,
                max_pop_notification=max_pop,
            )
            if self.running and self.manager:
                self.manager.cfg.popup_position = self._popup_pos_key_from_label(self.var_popup_pos.get())
                self.manager.cfg.notification_font_size = self._notif_font_key_from_label(
                    self.var_notif_font.get()
                )
                self.manager.cfg.notification_width = self._notif_width_key_from_label(
                    self.var_notif_width.get()
                )
                self.manager.cfg.privacy_show_title = bool(self.var_privacy_show_title.get())
                self.manager.cfg.privacy_show_msg = bool(self.var_privacy_show_msg.get())
                self.manager.cfg.max_preview_chars = preview_chars
                self.manager.cfg.max_pop_notification = max_pop

        self.var_privacy_show_title = tk.BooleanVar(value=getattr(self.cfg, "privacy_show_title", True))
        self.ui["chk_privacy_show_title"] = tb.Checkbutton(
            self.privacy_frm,
            text="显示通知标题（发件人/会话标题）",
            variable=self.var_privacy_show_title,
            bootstyle="round-toggle",
            command=_sync_popup_ui_settings,
        )
        self.ui["chk_privacy_show_title"].pack(anchor=W, pady=(0, 1))
        self.ui["lbl_privacy_show_title_hint"] = tb.Label(
            self.privacy_frm, text="", bootstyle="secondary", wraplength=520, justify=LEFT
        )
        self.ui["lbl_privacy_show_title_hint"].pack(anchor=W, pady=(0, 3))

        self.var_privacy_show_msg = tk.BooleanVar(value=getattr(self.cfg, "privacy_show_msg", True))
        self.ui["chk_privacy_show_msg"] = tb.Checkbutton(
            self.privacy_frm,
            text="显示通知消息内容（消息正文）",
            variable=self.var_privacy_show_msg,
            bootstyle="round-toggle",
            command=_sync_popup_ui_settings,
        )
        self.ui["chk_privacy_show_msg"].pack(anchor=W, pady=(0, 1))
        self.ui["lbl_privacy_show_msg_hint"] = tb.Label(
            self.privacy_frm, text="", bootstyle="secondary", wraplength=520, justify=LEFT
        )
        self.ui["lbl_privacy_show_msg_hint"].pack(anchor=W)

        self.cmb_popup_pos.bind("<<ComboboxSelected>>", _sync_popup_ui_settings)
        self.cmb_notif_font.bind("<<ComboboxSelected>>", _sync_popup_ui_settings)
        self.cmb_notif_width.bind("<<ComboboxSelected>>", _sync_popup_ui_settings)
        self.ent_max_preview.bind("<FocusOut>", _sync_popup_ui_settings)
        self.ent_max_preview.bind("<Return>", _sync_popup_ui_settings)

        def _on_toast_toggle():
            if self.running and self.manager:
                self.manager.cfg.enable_windows_toast = bool(self.var_win_toast.get())

        self.var_win_toast.trace_add("write", lambda *_: _on_toast_toggle())

    def _build_panel_push(self, frm):
        """推送行为：去重等全局参数；详细目标在推送目标页。"""
        self.var_dedup = tk.StringVar(value=str(getattr(self.cfg, "dedup_seconds", 8)))
        self.ui["lbl_push_dedup"] = tb.Label(frm, text="")
        self.ui["lbl_push_dedup"].pack(anchor=W)
        tb.Entry(frm, textvariable=self.var_dedup, width=10).pack(anchor=W, pady=(0, 10))

        tip = tb.Label(
            frm,
            text="转发目标（Telegram / 钉钉 / Gotify / 邮件等）请到左侧「推送目标」配置；消息模板请到「推送模板」。",
            bootstyle="secondary",
            wraplength=520,
            justify=LEFT,
        )
        tip.pack(anchor=W, pady=(4, 0))
        self.ui["lbl_push_behavior_tip"] = tip

    def _build_panel_ble(self, frm):
        """iPhone / BLE：设备扫描与地址。"""
        self._build_devices(parent=frm)

    def _build_panel_data(self, frm):
        """数据与历史。"""
        self.var_history_limit = tk.StringVar(value=str(self.cfg.history_limit))
        self.ui["lbl_data_history"] = tb.Label(frm, text="")
        self.ui["lbl_data_history"].pack(anchor=W)
        tb.Entry(frm, textvariable=self.var_history_limit, width=10).pack(anchor=W, pady=(0, 10))

        backup_frm = tb.Frame(frm)
        backup_frm.pack(fill=X, anchor=W, pady=(2, 3))
        self.var_auto_backup = tk.BooleanVar(value=bool(getattr(self.cfg, "auto_backup_enable", False)))
        self.ui["chk_auto_backup"] = tb.Checkbutton(
            backup_frm,
            text="开启自动备份通知",
            variable=self.var_auto_backup,
            bootstyle="round-toggle",
        )
        self.ui["chk_auto_backup"].pack(anchor=W)
        self.ui["lbl_auto_backup_hint"] = tb.Label(
            backup_frm, text="", bootstyle="secondary", wraplength=520, justify=LEFT
        )
        self.ui["lbl_auto_backup_hint"].pack(anchor=W, pady=(0, 2))
        path_row = tb.Frame(backup_frm)
        path_row.pack(fill=X, anchor=W)
        self.ui["lbl_auto_backup_path"] = tb.Label(path_row, text="备份文件路径（留空用默认）")
        self.ui["lbl_auto_backup_path"].pack(side=LEFT, padx=(0, 8))
        self.var_auto_backup_path = tk.StringVar(value=str(getattr(self.cfg, "auto_backup_path", "") or ""))
        self.ent_auto_backup_path = tb.Entry(path_row, textvariable=self.var_auto_backup_path)
        self.ent_auto_backup_path.pack(side=LEFT, fill=X, expand=True)

        # 开机自启动
        autostart_frm = tb.Frame(frm)
        autostart_frm.pack(fill=X, anchor=W, pady=(6, 3))
        _auto_on = bool(
            getattr(self.cfg, "auto_start", False)
            or getattr(self.cfg, "autostart_enabled", False)
        )
        self.var_auto_start = tk.BooleanVar(value=_auto_on)
        self.ui["chk_auto_start"] = tb.Checkbutton(
            autostart_frm,
            text="开机自动启动 NekoLink",
            variable=self.var_auto_start,
            bootstyle="round-toggle",
        )
        self.ui["chk_auto_start"].pack(anchor=W)
        self.ui["lbl_auto_start_hint"] = tb.Label(
            autostart_frm,
            text="开启后程序随系统开机自动运行",
            bootstyle="secondary",
            wraplength=520,
            justify=LEFT,
        )
        self.ui["lbl_auto_start_hint"].pack(anchor=W, pady=(0, 2))

        # 托盘图标
        tray_frm = tb.Frame(frm)
        tray_frm.pack(fill=X, anchor=W, pady=(4, 3))
        tray_row = tb.Frame(tray_frm)
        tray_row.pack(fill=X, anchor=W)
        self.ui["lbl_tray_icon"] = tb.Label(tray_row, text="状态栏图标")
        self.ui["lbl_tray_icon"].pack(side=LEFT, padx=(0, 8))
        self.var_tray_icon_path = tk.StringVar(
            value=str(getattr(self.cfg, "tray_icon_path", DEFAULT_TRAY_ICON_REL) or DEFAULT_TRAY_ICON_REL)
        )
        self.ent_tray_icon_path = tb.Entry(tray_row, textvariable=self.var_tray_icon_path)
        self.ent_tray_icon_path.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))

        def _browse_tray_icon():
            path = filedialog.askopenfilename(
                title=i18n.t("misc_tray_icon"),
                filetypes=[
                    ("Icons / Images", "*.ico;*.png;*.jpg;*.jpeg;*.bmp;*.webp"),
                    ("ICO", "*.ico"),
                    ("PNG", "*.png"),
                    ("All", "*.*"),
                ],
            )
            if path:
                self.var_tray_icon_path.set(path)

        self.ui["btn_tray_icon_browse"] = tb.Button(
            tray_row, text=i18n.t("browse"), bootstyle="secondary-outline", command=_browse_tray_icon
        )
        self.ui["btn_tray_icon_browse"].pack(side=LEFT)
        self.ui["lbl_tray_icon_hint"] = tb.Label(
            tray_frm,
            text="修改状态栏图标后需要重启程序生效",
            bootstyle="secondary",
            wraplength=520,
            justify=LEFT,
        )
        self.ui["lbl_tray_icon_hint"].pack(anchor=W, pady=(2, 0))

        self.ui["lbl_data_clear_hint"] = tb.Label(
            frm, text="", bootstyle="secondary", wraplength=520, justify=LEFT
        )
        self.ui["lbl_data_clear_hint"].pack(anchor=W, pady=(10, 0))

        def _sync_backup(_evt=None):
            if self.running and self.manager:
                self.manager.cfg.auto_backup_enable = bool(self.var_auto_backup.get())
                self.manager.cfg.auto_backup_path = self.var_auto_backup_path.get().strip()

        self.var_auto_backup.trace_add("write", lambda *_: _sync_backup())
        self.ent_auto_backup_path.bind("<FocusOut>", _sync_backup)

    def _build_panel_sound(self, frm):
        """声音与提醒。"""
        sound_frm = tb.Frame(frm)
        sound_frm.pack(fill=X, anchor=W, pady=(2, 3))
        self.var_sound_enable = tk.BooleanVar(value=bool(getattr(self.cfg, "sound_enable", True)))
        self.ui["chk_sound_enable"] = tb.Checkbutton(
            sound_frm,
            text="启用通知提示音",
            variable=self.var_sound_enable,
            bootstyle="round-toggle",
            command=self._on_sound_enable_toggle,
        )
        self.ui["chk_sound_enable"].pack(anchor=W)

        file_row = tb.Frame(sound_frm)
        file_row.pack(fill=X, anchor=W, pady=(2, 0))
        self.ui["lbl_sound_file"] = tb.Label(file_row, text="提示音音效文件:")
        self.ui["lbl_sound_file"].pack(side=LEFT, padx=(0, 8))
        self._sound_wav_list = list_wav_filenames(log=self.log)
        saved_sound = normalize_sound_selected_file(
            getattr(self.cfg, "sound_selected_file", DEFAULT_SOUND_SELECTED_FILE)
        )
        if self._sound_wav_list:
            if saved_sound not in self._sound_wav_list:
                if DEFAULT_SOUND_SELECTED_FILE in self._sound_wav_list:
                    saved_sound = DEFAULT_SOUND_SELECTED_FILE
                else:
                    saved_sound = self._sound_wav_list[0]
        else:
            saved_sound = ""
        self.var_sound_file = tk.StringVar(value=saved_sound)
        self.ui["cmb_sound_file"] = tb.Combobox(
            file_row,
            textvariable=self.var_sound_file,
            values=self._sound_wav_list,
            state="readonly" if self._sound_wav_list else "disabled",
            width=28,
        )
        self.ui["cmb_sound_file"].pack(side=LEFT, fill=X, expand=True)
        self.ui["cmb_sound_file"].bind(
            "<<ComboboxSelected>>", lambda _e: self._on_sound_file_selected()
        )

        vol_row = tb.Frame(sound_frm)
        vol_row.pack(fill=X, anchor=W, pady=(2, 0))
        self.ui["lbl_sound_volume"] = tb.Label(vol_row, text="提示音音量")
        self.ui["lbl_sound_volume"].pack(side=LEFT, padx=(0, 8))
        self.var_sound_volume = tk.IntVar(
            value=normalize_sound_volume(getattr(self.cfg, "sound_volume", 80))
        )
        self.ui["lbl_sound_volume_val"] = tb.Label(
            vol_row, text=str(self.var_sound_volume.get()), width=3
        )
        self.ui["lbl_sound_volume_val"].pack(side=LEFT, padx=(0, 8))
        self.scl_sound_volume = tb.Scale(
            vol_row,
            from_=0,
            to=100,
            orient=HORIZONTAL,
            length=180,
            command=lambda v: self._on_sound_volume_scale(v),
        )
        self.scl_sound_volume.set(self.var_sound_volume.get())
        self.scl_sound_volume.pack(side=LEFT, fill=X, expand=True)
        self._app_sound_map = normalize_app_sound_map(
            getattr(self.cfg, "app_sound_map", {}) or {}
        )
        update_runtime_sound_config(
            sound_enable=bool(self.var_sound_enable.get()),
            sound_volume=normalize_sound_volume(self.var_sound_volume.get()),
            sound_selected_file=normalize_sound_selected_file(
                self.var_sound_file.get() or DEFAULT_SOUND_SELECTED_FILE
            ),
            app_sound_map=dict(self._app_sound_map),
        )
        self.ui["lbl_sound_hint"] = tb.Label(
            sound_frm,
            text="提示：将 .wav 放入 assets/sound/ 后重启可出现在下拉框；按 App 专属音效请到「消息历史→应用名称映射」设置",
            bootstyle="secondary",
            wraplength=520,
            justify=LEFT,
        )
        self.ui["lbl_sound_hint"].pack(anchor=W, pady=(2, 0))
        if not SOUND_AVAILABLE or not self._sound_wav_list:
            try:
                self.ui["chk_sound_enable"].configure(state="disabled")
                self.scl_sound_volume.configure(state="disabled")
                if "cmb_sound_file" in self.ui:
                    self.ui["cmb_sound_file"].configure(state="disabled")
                if not SOUND_AVAILABLE:
                    self.log(
                        f"[sound] {i18n.t('misc_sound_deps_missing')} ({sound_deps_error()})"
                    )
                elif not self._sound_wav_list:
                    self.log("[Sound] assets/sound/ 无 wav，提示音静默")
            except Exception:
                pass

    def _build_panel_about(self, frm):
        self.ui["lbl_about_version"] = tb.Label(
            frm, text=f"{i18n.t('about_version')}: {APP_VERSION}", font=("Segoe UI", 12, "bold")
        )
        self.ui["lbl_about_version"].pack(anchor=W, pady=(8, 4))
        self.ui["lbl_about_author"] = tb.Label(
            frm, text=i18n.t("about_author"), bootstyle="secondary", wraplength=520, justify=LEFT
        )
        self.ui["lbl_about_author"].pack(anchor=W)

    def _build_history(self):
        frm = tb.Frame(self.tab_history, padding=12)
        frm.pack(fill=BOTH, expand=True)
        frm.grid_rowconfigure(1, weight=1)
        frm.grid_columnconfigure(0, weight=1)

        top = tb.Frame(frm)
        top.grid(row=0, column=0, sticky=EW, pady=(0, 8))

        self.ui["lbl_history_title"] = tb.Label(top, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_history_title"].pack(side=LEFT)

        self.ui["btn_clear_history"] = tb.Button(top, text="", bootstyle="warning", command=self.clear_history)
        self.ui["btn_clear_history"].pack(side=RIGHT, padx=(8, 0))
        self.ui["btn_history_global_save"] = tb.Button(
            top, text="💾全局保存", bootstyle="primary", command=self.save_app_map_global
        )
        self.ui["btn_history_global_save"].pack(side=RIGHT, padx=(8, 0))
        self.ui["btn_export_history"] = tb.Button(
            top, text="导出全部历史消息", bootstyle="info", command=self.export_all_history
        )
        self.ui["btn_export_history"].pack(side=RIGHT, padx=(8, 0))
        self.ui["btn_copy_history"] = tb.Button(top, text="", bootstyle="secondary", command=self.copy_selected_history)
        self.ui["btn_copy_history"].pack(side=RIGHT)

        cols = ("time", "device", "battery", "app", "title", "msg", "codes")
        self.tree = tb.Treeview(frm, columns=cols, show="headings", height=10)
        self.ui["tree"] = self.tree
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("time", width=150, anchor=W)
        self.tree.column("device", width=120, anchor=W)
        self.tree.column("battery", width=70, anchor=W)
        self.tree.column("app", width=120, anchor=W)
        self.tree.column("title", width=220, anchor=W)
        self.tree.column("msg", width=280, anchor=W)
        self.tree.column("codes", width=120, anchor=W)
        self.tree.grid(row=1, column=0, sticky=NSEW, pady=(0, 10))
        self.tree.bind("<<TreeviewSelect>>", self._on_history_row_click)
        self.tree.bind("<Double-1>", self._on_history_dblclick)

        map_frm = tb.Labelframe(frm, text="应用名称映射", padding=10)
        map_frm.grid(row=2, column=0, sticky=EW)

        self.ui["lbl_app_map"] = tb.Label(map_frm, text="应用名称映射", font=("Segoe UI", 11, "bold"))
        self.ui["lbl_app_map"].pack(anchor=W)
        self.ui["lbl_map_hint"] = tb.Label(
            map_frm,
            text="单击上方历史可填入 Bundle ID；可为每个 App 选定专属提示音。保存后写入 config.json。",
            bootstyle="secondary",
        )
        self.ui["lbl_map_hint"].pack(anchor=W, pady=(0, 8))

        self.map_tree = tb.Treeview(
            map_frm,
            columns=("bundle", "name", "block", "icon", "sound"),
            show="headings",
            height=5,
            selectmode="browse",
        )
        self.ui["map_tree"] = self.map_tree
        self.map_tree.heading("bundle", text="Bundle ID")
        self.map_tree.heading("name", text="显示名称")
        self.map_tree.heading("block", text="跳过 webhook")
        self.map_tree.heading("icon", text="图标")
        self.map_tree.heading("sound", text="提示音")
        self.map_tree.column("bundle", width=200, anchor=W)
        self.map_tree.column("name", width=100, anchor=W)
        self.map_tree.column("block", width=80, anchor=W)
        self.map_tree.column("icon", width=90, anchor=W)
        self.map_tree.column("sound", width=120, anchor=W)
        self.map_tree.pack(fill=X, pady=(0, 8))
        self.map_tree.bind("<<TreeviewSelect>>", self._on_map_select)
        self._reload_app_map_tree()

        edit = tb.Frame(map_frm)
        edit.pack(fill=X, pady=(0, 8))

        self.ui["lbl_map_bundle"] = tb.Label(edit, text="Bundle ID")
        self.ui["lbl_map_bundle"].grid(row=0, column=0, sticky=W, padx=(0, 8))
        self.var_map_bundle = tk.StringVar()
        tb.Entry(edit, textvariable=self.var_map_bundle, width=42).grid(row=0, column=1, sticky=W, padx=(0, 16))

        self.ui["lbl_map_name"] = tb.Label(edit, text="显示名称")
        self.ui["lbl_map_name"].grid(row=0, column=2, sticky=W, padx=(0, 8))
        self.var_map_name = tk.StringVar()
        tb.Entry(edit, textvariable=self.var_map_name, width=20).grid(row=0, column=3, sticky=W)

        self.var_map_block = tk.BooleanVar(value=False)
        tb.Checkbutton(
            edit, text="跳过 webhook（防循环）", variable=self.var_map_block, bootstyle="round-toggle"
        ).grid(row=1, column=1, sticky=W, pady=(8, 0))

        icon_row = tb.Frame(map_frm)
        icon_row.pack(fill=X, pady=(0, 8))
        self.ui["lbl_map_icon"] = tb.Label(icon_row, text="应用图标")
        self.ui["lbl_map_icon"].pack(side=LEFT, padx=(0, 8))
        self.var_map_icon = tk.StringVar()
        tb.Entry(icon_row, textvariable=self.var_map_icon, width=40).pack(side=LEFT, padx=(0, 8))
        self.ui["btn_map_icon"] = tb.Button(icon_row, text="浏览...", bootstyle="secondary", command=self.browse_app_icon)
        self.ui["btn_map_icon"].pack(side=LEFT)

        sound_row = tb.Frame(map_frm)
        sound_row.pack(fill=X, pady=(0, 4))
        self.ui["lbl_map_sound"] = tb.Label(sound_row, text="专属提示音")
        self.ui["lbl_map_sound"].pack(side=LEFT, padx=(0, 8))
        if not hasattr(self, "_sound_wav_list"):
            self._sound_wav_list = list_wav_filenames(log=self.log)
        if not hasattr(self, "_app_sound_map"):
            self._app_sound_map = normalize_app_sound_map(
                getattr(self.cfg, "app_sound_map", {}) or {}
            )
        self._map_sound_global_label = "(使用全局默认)"
        sound_values = [self._map_sound_global_label] + list(self._sound_wav_list or [])
        self.var_map_sound = tk.StringVar(value=self._map_sound_global_label)
        self.ui["cmb_map_sound"] = tb.Combobox(
            sound_row,
            textvariable=self.var_map_sound,
            values=sound_values,
            state="readonly" if self._sound_wav_list else "disabled",
            width=28,
        )
        self.ui["cmb_map_sound"].pack(side=LEFT)
        self.ui["lbl_map_sound_hint"] = tb.Label(
            map_frm,
            text="单击历史填入包名后，在此选定专属 wav；选「使用全局默认」则走杂项全局音效",
            bootstyle="secondary",
        )
        self.ui["lbl_map_sound_hint"].pack(anchor=W, pady=(0, 4))

        self.ui["lbl_map_icon_hint"] = tb.Label(
            map_frm,
            text="可选：自定义 .png/.ico；留空则自动生成彩色字母图标",
            bootstyle="secondary",
        )
        self.ui["lbl_map_icon_hint"].pack(anchor=W, pady=(0, 8))

        btns = tb.Frame(map_frm)
        btns.pack(fill=X)
        self.ui["btn_map_upsert"] = tb.Button(btns, text="添加/更新", bootstyle="secondary", command=self.upsert_app_map)
        self.ui["btn_map_upsert"].pack(side=LEFT, padx=(0, 8))
        self.ui["btn_map_remove"] = tb.Button(btns, text="删除所选", bootstyle="warning", command=self.remove_app_map)
        self.ui["btn_map_remove"].pack(side=LEFT)

    def _reload_app_map_tree(self):
        self.map_tree.delete(*self.map_tree.get_children())
        self._map_icon_paths = dict(getattr(self.cfg, "app_icon_map", {}) or {})
        if not hasattr(self, "_app_sound_map"):
            self._app_sound_map = normalize_app_sound_map(
                getattr(self.cfg, "app_sound_map", {}) or {}
            )
        block_set = set(getattr(self.cfg, "block_bundle", []) or [])
        global_lbl = getattr(self, "_map_sound_global_label", "(使用全局默认)")
        for bundle_id, name in sorted((self.cfg.app_bundle_map or {}).items()):
            skip = i18n.t("yes") if bundle_id in block_set else i18n.t("no")
            icon = self._map_icon_paths.get(bundle_id, "")
            icon_show = os.path.basename(icon) if icon else ""
            sound_show = (self._app_sound_map or {}).get(bundle_id, "") or global_lbl
            self.map_tree.insert(
                "", "end", values=(bundle_id, name, skip, icon_show, sound_show)
            )

    def _set_map_sound_var(self, bundle_id: str) -> None:
        global_lbl = getattr(self, "_map_sound_global_label", "(使用全局默认)")
        if not hasattr(self, "var_map_sound"):
            return
        fname = (getattr(self, "_app_sound_map", {}) or {}).get(bundle_id, "")
        if fname and fname in (self._sound_wav_list or []):
            self.var_map_sound.set(fname)
        else:
            self.var_map_sound.set(global_lbl)

    def _on_map_select(self, _evt=None):
        sel = self.map_tree.selection()
        if not sel:
            return
        vals = self.map_tree.item(sel[0], "values")
        bundle_id = vals[0] if len(vals) > 0 else ""
        name = vals[1] if len(vals) > 1 else ""
        skip = vals[2] if len(vals) > 2 else i18n.t("no")
        self.var_map_bundle.set(bundle_id)
        self.var_map_name.set(name)
        self.var_map_block.set(skip in (i18n.t("yes"), "是", "Yes", "yes"))
        self.var_map_icon.set(self._map_icon_paths.get(bundle_id, ""))
        self._set_map_sound_var(bundle_id)

    def _on_history_row_click(self, _evt=None):
        """单击历史行：将 Bundle ID 填入下方应用映射表单。"""
        sel = self.tree.selection()
        if not sel:
            return
        raw = self._hist_raw.get(sel[0], {})
        bundle_id = raw.get("app") or ""
        if not bundle_id:
            return
        self.var_map_bundle.set(bundle_id)
        self.var_map_name.set(get_app_display_name(bundle_id, self.cfg))
        block_set = set(getattr(self.cfg, "block_bundle", []) or [])
        self.var_map_block.set(bundle_id in block_set)
        self.var_map_icon.set((getattr(self.cfg, "app_icon_map", {}) or {}).get(bundle_id, ""))
        self._set_map_sound_var(bundle_id)

    def _on_history_dblclick(self, _evt=None):
        """双击历史行：弹出完整通知详情（与单击填入 Bundle ID 互不干扰）。"""
        sel = self.tree.selection()
        if not sel:
            return
        raw = self._hist_raw.get(sel[0], {})
        if not raw:
            return
        self._show_notification_detail(
            resolve_raw_title(raw),
            resolve_raw_msg(raw),
            meta={
                "time": raw.get("time") or "",
                "app": raw.get("app_name") or "",
                "device": raw.get("device_name") or "",
            },
        )

    def save_app_map_global(self):
        """消息历史页：将全部应用映射写入 config.json。"""
        if self.var_map_bundle.get().strip():
            self.upsert_app_map()
        try:
            cfg = self.collect_config()
            save_config(CONFIG_PATH, cfg)
            self.cfg = cfg
            self.reload_runtime_config(cfg)
            self._reload_app_map_tree()
            messagebox.showinfo("提示", "配置已全局保存到config.json")
        except Exception as e:
            messagebox.showerror(i18n.t("fail"), str(e))

    def _show_last_notification_detail(self, _evt=None):
        payload = getattr(self, "_last_payload", None) or {}
        if not payload:
            return
        self._show_notification_detail(
            resolve_raw_title(payload),
            resolve_raw_msg(payload),
            meta={"app": get_app_display_name(payload.get("app") or "", self.cfg)},
        )

    def _show_notification_detail(self, raw_title: str, raw_msg: str, meta: Optional[dict] = None):
        """详情弹窗：展示完整 raw 原文，不做截断。"""
        meta = meta or {}
        win = tk.Toplevel(self)
        win.title("通知详情（完整原文）")
        win.geometry("560x420")
        win.transient(self)
        frm = tb.Frame(win, padding=12)
        frm.pack(fill=BOTH, expand=True)
        bits = [f"{k}: {v}" for k, v in meta.items() if v]
        if bits:
            tb.Label(frm, text=" · ".join(bits), bootstyle="secondary").pack(anchor=W, pady=(0, 8))
        tb.Label(frm, text="标题（全文）", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        title_box = tk.Text(frm, height=3, wrap="word")
        title_box.pack(fill=X, pady=(2, 8))
        title_box.insert("end", raw_title or "")
        title_box.configure(state="disabled")
        tb.Label(frm, text="内容（全文）", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        msg_box = tk.Text(frm, height=12, wrap="word")
        msg_box.pack(fill=BOTH, expand=True, pady=(2, 8))
        msg_box.insert("end", raw_msg or "")
        msg_box.configure(state="disabled")
        tb.Label(
            frm,
            text=f"字符数：标题 {len(raw_title or '')} / 内容 {len(raw_msg or '')}",
            bootstyle="secondary",
        ).pack(anchor=W)
        tb.Button(frm, text="关闭", bootstyle="secondary", command=win.destroy).pack(anchor=E, pady=(8, 0))

    def upsert_app_map(self):
        bundle_id = self.var_map_bundle.get().strip()
        name = self.var_map_name.get().strip()
        if not bundle_id:
            messagebox.showwarning(i18n.t("missing"), i18n.t("fill_bundle_id"))
            return
        if not name:
            name = bundle_id
        skip = self.var_map_block.get()
        skip_text = i18n.t("yes") if skip else i18n.t("no")
        icon_path = self.var_map_icon.get().strip()
        if icon_path:
            self._map_icon_paths[bundle_id] = icon_path
        else:
            self._map_icon_paths.pop(bundle_id, None)
        icon_show = os.path.basename(icon_path) if icon_path else ""

        global_lbl = getattr(self, "_map_sound_global_label", "(使用全局默认)")
        sound_sel = (self.var_map_sound.get() if hasattr(self, "var_map_sound") else "") or ""
        sound_sel = sound_sel.strip()
        if not hasattr(self, "_app_sound_map") or self._app_sound_map is None:
            self._app_sound_map = {}
        if sound_sel and sound_sel != global_lbl:
            fname = normalize_sound_selected_file(sound_sel)
            if fname not in (self._sound_wav_list or []) or not resolve_sound_path(fname).is_file():
                messagebox.showwarning("提示", f"音效文件不存在：{fname}")
                return
            self._app_sound_map[bundle_id] = fname
            sound_show = fname
        else:
            self._app_sound_map.pop(bundle_id, None)
            sound_show = global_lbl
        self._sync_app_sound_map_runtime()

        found = None
        for iid in self.map_tree.get_children():
            if self.map_tree.item(iid, "values")[0] == bundle_id:
                found = iid
                break
        row = (bundle_id, name, skip_text, icon_show, sound_show)
        if found:
            self.map_tree.item(found, values=row)
        else:
            self.map_tree.insert("", "end", values=row)

    def browse_app_icon(self):
        path = filedialog.askopenfilename(
            title="选择应用图标",
            filetypes=[("Image", "*.png;*.ico;*.jpg;*.jpeg;*.webp"), ("All", "*.*")],
        )
        if path:
            self.var_map_icon.set(path)

    def remove_app_map(self):
        for iid in list(self.map_tree.selection()):
            vals = self.map_tree.item(iid, "values")
            if vals:
                bid = str(vals[0]).strip()
                self._map_icon_paths.pop(bid, None)
                if hasattr(self, "_app_sound_map"):
                    self._app_sound_map.pop(bid, None)
            self.map_tree.delete(iid)
        self._sync_app_sound_map_runtime()

    def _build_logs(self):
        frm = tb.Frame(self.tab_logs, padding=12)
        frm.pack(fill=BOTH, expand=True)

        top = tb.Frame(frm)
        top.pack(fill=X, pady=(0, 8))

        self.ui["lbl_logs_title"] = tb.Label(top, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_logs_title"].pack(side=LEFT)

        self.ui["btn_clear_logs"] = tb.Button(top, text="", bootstyle="warning", command=self.clear_logs)
        self.ui["btn_clear_logs"].pack(side=RIGHT)

        self.txt_logs = tk.Text(frm, wrap="word", height=10)
        self.txt_logs.pack(fill=BOTH, expand=True)
        self.txt_logs.insert("end", "Ready.\n")

    def insert_template_var(self):
        token = self.var_tpl_insert.get().strip()
        if not token:
            return
        self.txt_push_template.insert(tk.INSERT, token)
        self.txt_push_template.focus_set()

    def _on_tpl_preset_change(self, _evt=None):
        label = self.var_tpl_preset.get().strip()
        key = "default"
        if label == i18n.t("tpl_preset_simple"):
            key = "simple"
        elif label == i18n.t("tpl_preset_detail"):
            key = "detail"
        tpl = PUSH_TEMPLATE_PRESETS.get(key, PUSH_TEMPLATE_PRESETS["default"])
        self.txt_push_template.delete("1.0", "end")
        self.txt_push_template.insert("1.0", tpl)
        if self._last_payload:
            self._refresh_push_preview(self._last_payload)

    def _get_push_template_text(self) -> str:
        return self.txt_push_template.get("1.0", "end-1c")

    def _refresh_push_preview(self, payload: dict):
        tpl = self._get_push_template_text()
        cfg = self.collect_config()
        rendered = render_push_template(tpl, payload, cfg)
        self.push_preview.delete("1.0", "end")
        self.push_preview.insert("end", rendered + "\n")

    # ---------- Actions ----------
    def log(self, s: str):
        self.log_q.put(s)

    def on_notification(self, payload: dict):
        self._last_payload = payload
        bat = payload.get("battery")
        bat_text = f"{bat}%" if isinstance(bat, int) else "--"
        device_raw = payload.get("device") or ""
        app_raw = payload.get("app") or ""
        device_name = get_device_display_name(device_raw, self.cfg)
        app_name = get_app_display_name(app_raw, self.cfg)
        date_fmt = format_ancs_date(payload.get("date") or "")
        raw_title = resolve_raw_title(payload)
        raw_msg = resolve_raw_msg(payload)
        preview_n = normalize_max_preview_chars(
            getattr(self.cfg, "max_preview_chars", 50)
        )
        # 主页预览仅展示省略文本；详情/历史存储用 raw 全文
        preview_text = (
            f"Device: {device_name}\n"
            f"Battery: {bat_text}\n"
            f"App: {app_name} ({app_raw})\n"
            f"Title: {get_ellipsis_text(raw_title, preview_n)}\n"
            f"Msg: {get_ellipsis_text(raw_msg, preview_n)}\n"
            f"Codes: {' '.join(payload.get('codes') or [])}\n"
            f"Date: {date_fmt}\n"
            f"（双击此处查看完整原文）\n"
        )
        self.preview.delete("1.0", "end")
        self.preview.insert("end", preview_text)
        self._refresh_push_preview(payload)

        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(payload["ts"]))
        codes = " ".join(payload.get("codes") or [])

        # 写入内存历史（导出用），超限丢弃最旧 — 必须存完整 raw
        hist_row = {
            "time": t,
            "device": device_name,
            "app_name": app_name,
            "app_bundle": app_raw,
            "title": raw_title,
            "msg": raw_msg,
            "raw_title": raw_title,
            "raw_msg": raw_msg,
        }
        self.history.insert(0, hist_row)
        while len(self.history) > MAX_HISTORY_COUNT:
            self.history.pop()

        self._append_auto_backup_row(hist_row)

        iid = self.tree.insert(
            "",
            0,
            values=(
                t,
                device_name,
                bat_text,
                app_name,
                get_ellipsis_text(raw_title, preview_n),
                get_ellipsis_text(raw_msg, preview_n),
                codes,
            ),
        )
        self._hist_raw[iid] = {
            "app": app_raw,
            "device": device_raw,
            "notif_id": payload.get("notif_id") or "",
            "raw_title": raw_title,
            "raw_msg": raw_msg,
            "title": raw_title,
            "msg": raw_msg,
            "time": t,
            "app_name": app_name,
            "codes": codes,
            "battery": bat_text,
            "device_name": device_name,
        }
        nid = payload.get("notif_id")
        if nid:
            self._notif_to_iid[nid] = iid

        # prune tree UI（最新在顶部；超出上限时删除末尾最旧行）
        limit = int(self.safe_int(self.var_history_limit.get(), default=self.cfg.history_limit))
        children = self.tree.get_children()
        if len(children) > max(50, limit):
            for iid in children[max(50, limit):]:
                raw = self._hist_raw.pop(iid, {})
                old_nid = raw.get("notif_id")
                if old_nid:
                    self._notif_to_iid.pop(old_nid, None)
                self.tree.delete(iid)

    def on_save(self):
        self._persist_config(show_msg=True)

    def reload_runtime_config(self, cfg: Optional[BridgeConfig] = None) -> bool:
        """
        热加载 A 类配置到运行时内存：
        屏蔽关键词、icon 映射、预览字数、最大弹窗数、自动备份等。
        不重置历史、不销毁已弹出卡片；字号/宽度保持进程内原值（需重启）。
        """
        old_cfg = self.cfg
        try:
            if cfg is None:
                cfg = load_config(CONFIG_PATH)
            self.cfg = cfg
            if self.manager is not None:
                self.manager.apply_runtime_config(cfg)

            # 直接写 A 类字段，避免 apply_ui_settings 触发已有弹窗 re-layout
            self.popup_toast.max_preview_chars = normalize_max_preview_chars(
                getattr(cfg, "max_preview_chars", 50)
            )
            self.popup_toast.max_visible = normalize_max_pop_notification(
                getattr(cfg, "max_pop_notification", 3)
            )
            secs = normalize_notification_auto_close_seconds(
                getattr(
                    cfg,
                    "desktop_toast_auto_dismiss",
                    getattr(cfg, "notification_auto_close_seconds", 10),
                )
            )
            self.popup_toast.duration_ms = secs * 1000
            # 提示音：热加载写入 sound_helper 内存运行时（play 只读这里）
            update_runtime_sound_config(
                sound_enable=bool(getattr(cfg, "sound_enable", True)),
                sound_volume=normalize_sound_volume(getattr(cfg, "sound_volume", 80)),
                sound_selected_file=normalize_sound_selected_file(
                    getattr(cfg, "sound_selected_file", DEFAULT_SOUND_SELECTED_FILE)
                ),
                app_sound_map=normalize_app_sound_map(
                    getattr(cfg, "app_sound_map", {}) or {}
                ),
            )
            # 同步历史映射表中的专属音效列
            try:
                self._app_sound_map = normalize_app_sound_map(
                    getattr(cfg, "app_sound_map", {}) or {}
                )
                if hasattr(self, "map_tree"):
                    self._reload_app_map_tree()
            except Exception:
                pass
            # 上限调高时立刻从排队队列补弹
            try:
                self.popup_toast.drain_ui_pop_queue()
            except Exception:
                pass
            # 清 icon 缓存，下一条新通知用新映射；已弹出卡片不刷新
            try:
                self.popup_toast._icon_cache.clear()
            except Exception:
                pass

            self.log(
                "[CONFIG] hot-reload ok: "
                f"keywords={len(cfg.block_keywords or [])}, "
                f"icons={len(cfg.app_icon_map or {})}, "
                f"max_pop={getattr(cfg, 'max_pop_notification', 3)}, "
                f"preview={getattr(cfg, 'max_preview_chars', 50)}, "
                f"auto_close={secs}s, "
                f"sound={getattr(cfg, 'sound_enable', True)}/{getattr(cfg, 'sound_volume', 80)}/"
                f"{getattr(cfg, 'sound_selected_file', DEFAULT_SOUND_SELECTED_FILE)}/"
                f"app_sounds={len(getattr(cfg, 'app_sound_map', {}) or {})}"
            )
            return True
        except Exception as e:
            self.cfg = old_cfg
            if self.manager is not None:
                try:
                    self.manager.apply_runtime_config(old_cfg)
                except Exception:
                    pass
            self.log(f"[CONFIG] hot-reload failed, keep previous runtime config: {e}")
            return False

    def _apply_autostart(self, enabled: bool, prev_enabled: bool) -> Optional[str]:
        """
        根据 auto_start 写入/删除 Windows 计划任务。
        返回给用户看的提示文案；无变更返回 None；失败返回错误文案。
        """
        if enabled == prev_enabled:
            return None
        try:
            from win_autostart import disable, enable

            if enabled:
                res = enable(_autostart_task_command())
            else:
                res = disable()
            if res.ok:
                return i18n.t("auto_start_on") if enabled else i18n.t("auto_start_off")
            return res.message or str(res)
        except Exception as e:
            try:
                self.log(f"[autostart] failed: {e}")
            except Exception:
                pass
            return str(e)

    def _persist_config(self, show_msg: bool = True):
        secs, err = parse_notification_auto_close_seconds(
            self.var_auto_close.get() if hasattr(self, "var_auto_close") else "8"
        )
        if err or secs is None:
            if show_msg:
                messagebox.showwarning(i18n.t("missing"), i18n.t("misc_auto_close_invalid"))
                return
            secs = normalize_notification_auto_close_seconds(
                getattr(
                    self.cfg,
                    "desktop_toast_auto_dismiss",
                    getattr(self.cfg, "notification_auto_close_seconds", 10),
                )
            )
        self.var_auto_close.set(str(secs))
        # 垂直间距：非法输入回退默认 12 并回填输入框
        if hasattr(self, "var_card_gap"):
            gap = normalize_popup_card_gap(self.var_card_gap.get())
            self.var_card_gap.set(str(gap))
        prev_auto = bool(
            getattr(self.cfg, "auto_start", False)
            or getattr(self.cfg, "autostart_enabled", False)
        )
        cfg = self.collect_config()
        save_config(CONFIG_PATH, cfg)
        ok = self.reload_runtime_config(cfg)
        # 刷新映射表 UI 显示（不重建历史列表）
        self._reload_app_map_tree()
        auto_tip = None
        try:
            auto_tip = self._apply_autostart(bool(getattr(cfg, "auto_start", False)), prev_auto)
        except Exception as e:
            auto_tip = str(e)
            try:
                self.log(f"[autostart] sync error: {e}")
            except Exception:
                pass
        if show_msg:
            extra = f"\n{auto_tip}" if auto_tip else ""
            if ok:
                messagebox.showinfo(
                    i18n.t("ok"),
                    f"{i18n.t('config_saved')}\n{i18n.t('saved_restart_hint')}{extra}\n{CONFIG_PATH}",
                )
            else:
                messagebox.showwarning(
                    i18n.t("fail"),
                    f"{i18n.t('config_saved')}\n{CONFIG_PATH}\n(热加载失败，请查看日志){extra}",
                )

    def on_start(self):
        if self.running:
            return

        cfg = self.collect_config()
        save_config(CONFIG_PATH, cfg)
        self.cfg = cfg
        self.manager.apply_runtime_config(cfg)
        # 启动时完整同步弹窗参数（含字号/宽度）
        self._sync_popup_toast_from_cfg(cfg)

        addrs = cfg.ble_addresses or []
        if not addrs:
            messagebox.showwarning(i18n.t("no_devices"), i18n.t("add_device_warn"))
            return

        self.running = True
        self.apply_i18n()
        self._update_sidebar_status()
        self.manager.start_all(addrs)
        self.log("[UI] started")

    def on_stop(self):
        if not self.running:
            return
        self.running = False
        self.apply_i18n()
        self._update_sidebar_status()
        self.manager.stop_all()
        self.log("[UI] stopped")

    def scan_devices(self):
        self.scan_box.delete("1.0", "end")
        self.scan_box.insert("end", "Scanning...\n")

        def _work():
            try:
                results = asyncio_run(self.manager.scan_heart_rate(timeout=8))
                if not results:
                    self.log("[SCAN] none")
                    self.scan_box.insert("end", "No devices found.\n")
                    return
                for name, addr, rssi in results:
                    self.scan_box.insert("end", f"{name} | addr={addr} | rssi={rssi}\n")
            except Exception as e:
                self.scan_box.insert("end", f"Scan error: {e}\n")

        threading.Thread(target=_work, daemon=True).start()

    def add_addr(self):
        addr = self.var_add_addr.get().strip()
        if not addr:
            return
        for iid in self.dev_tree.get_children():
            if self.dev_tree.item(iid, "values")[0] == addr:
                self.var_add_addr.set("")
                return
        self.dev_tree.insert("", "end", values=(addr, ""))
        self.var_add_addr.set("")

    def remove_selected_addr(self):
        for iid in list(self.dev_tree.selection()):
            self.dev_tree.delete(iid)

    def add_block(self):
        s = self.var_block_input.get().strip()
        if not s:
            return
        self.lst_block.insert("end", s)
        self.var_block_input.set("")

    def remove_block(self):
        sel = list(self.lst_block.curselection())
        sel.reverse()
        for idx in sel:
            self.lst_block.delete(idx)

    def _popup_pos_label_from_key(self, key: str) -> str:
        key = normalize_popup_position(key)
        return i18n.t(POPUP_POSITION_LABELS.get(key, "misc_popup_pos_br"))

    def _popup_pos_key_from_label(self, label: str) -> str:
        label = (label or "").strip()
        for key in ("bottom_right", "top_right", "bottom_left", "top_left"):
            if i18n.t(POPUP_POSITION_LABELS[key]) == label:
                return key
        return normalize_popup_position(getattr(self.cfg, "popup_position", "bottom_right"))

    def _notif_font_label_from_key(self, key) -> str:
        key = normalize_notification_font_size(key)
        return i18n.t(NOTIFICATION_FONT_LABELS.get(key, "misc_notif_font_md"))

    def _notif_font_key_from_label(self, label: str) -> int:
        label = (label or "").strip()
        for key in (6, 8, 10, 12):
            if i18n.t(NOTIFICATION_FONT_LABELS[key]) == label:
                return key
        return normalize_notification_font_size(getattr(self.cfg, "notification_font_size", 10))

    def _notif_width_label_from_key(self, key) -> str:
        key = normalize_notification_width(key)
        return i18n.t(NOTIFICATION_WIDTH_LABELS.get(key, "misc_notif_width_md"))

    def _notif_width_key_from_label(self, label: str) -> int:
        label = (label or "").strip()
        for key in (300, 420, 480, 540):
            if i18n.t(NOTIFICATION_WIDTH_LABELS[key]) == label:
                return key
        return normalize_notification_width(getattr(self.cfg, "notification_width", 420))

    def _on_max_pop_scale(self, value) -> None:
        n = normalize_max_pop_notification(float(value))
        self.var_max_pop.set(n)
        if "lbl_max_pop_val" in self.ui:
            self.ui["lbl_max_pop_val"].config(text=str(n))
        self.popup_toast.apply_ui_settings(max_pop_notification=n)
        if self.running and self.manager:
            self.manager.cfg.max_pop_notification = n

    def _on_sound_enable_toggle(self) -> None:
        # ttkbootstrap toggle 有时在 command 触发瞬间 var 尚未翻转，延后一拍读取
        self.after(20, self._sync_sound_enable_from_ui)

    def _sync_sound_enable_from_ui(self) -> None:
        enable = bool(self.var_sound_enable.get())
        update_runtime_sound_config(sound_enable=enable)
        if self.manager is not None:
            self.manager.cfg.sound_enable = enable
        self.log(f"[Sound] UI enable -> runtime sound_enable={enable}")

    def _on_sound_file_selected(self) -> None:
        name = normalize_sound_selected_file(
            self.var_sound_file.get() or DEFAULT_SOUND_SELECTED_FILE
        )
        self.var_sound_file.set(name)
        update_runtime_sound_config(sound_selected_file=name)
        if self.manager is not None:
            self.manager.cfg.sound_selected_file = name
        self.log(f"[Sound] UI file -> runtime sound_selected_file={name}")

    def _on_sound_volume_scale(self, value) -> None:
        # ttkbootstrap Scale 可能给 0~1 或 0~100
        try:
            fv = float(value)
        except (TypeError, ValueError):
            fv = float(self.var_sound_volume.get())
        if 0.0 <= fv <= 1.0:
            fv = fv * 100.0
        n = normalize_sound_volume(fv)
        self.var_sound_volume.set(n)
        if "lbl_sound_volume_val" in self.ui:
            self.ui["lbl_sound_volume_val"].config(text=str(n))
        update_runtime_sound_config(sound_volume=n)
        if self.manager is not None:
            self.manager.cfg.sound_volume = n

    def _sync_app_sound_map_runtime(self) -> None:
        mapping = normalize_app_sound_map(getattr(self, "_app_sound_map", {}) or {})
        self._app_sound_map = mapping
        update_runtime_sound_config(app_sound_map=dict(mapping))
        if self.manager is not None:
            self.manager.cfg.app_sound_map = dict(mapping)

    def _resolve_auto_backup_path(self) -> Path:
        custom = (self.var_auto_backup_path.get() if hasattr(self, "var_auto_backup_path") else "") or ""
        custom = custom.strip()
        if custom:
            return Path(custom)
        return _default_auto_backup_path()

    def _append_auto_backup_row(self, row: dict) -> None:
        if not hasattr(self, "var_auto_backup") or not bool(self.var_auto_backup.get()):
            return
        try:
            path = self._resolve_auto_backup_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            write_header = not path.exists() or path.stat().st_size == 0
            with open(path, "a", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                if write_header:
                    writer.writerow(_HISTORY_CSV_HEADER)
                writer.writerow(
                    [
                        row.get("time", ""),
                        row.get("device", ""),
                        row.get("app_name", ""),
                        row.get("app_bundle", ""),
                        resolve_raw_title(row),
                        resolve_raw_msg(row),
                    ]
                )
        except Exception as e:
            self.log(f"[backup] auto append failed: {e}")

    def _sync_popup_toast_from_cfg(self, cfg) -> None:
        self.popup_toast.apply_ui_settings(
            popup_position=getattr(cfg, "popup_position", "bottom_right"),
            notification_width=getattr(cfg, "notification_width", 420),
            notification_font_size=getattr(cfg, "notification_font_size", 10),
            privacy_show_title=getattr(cfg, "privacy_show_title", True),
            privacy_show_msg=getattr(cfg, "privacy_show_msg", True),
            max_preview_chars=getattr(cfg, "max_preview_chars", 50),
            max_pop_notification=getattr(cfg, "max_pop_notification", 3),
            notification_auto_close_seconds=getattr(
                cfg,
                "desktop_toast_auto_dismiss",
                getattr(cfg, "notification_auto_close_seconds", 10),
            ),
        )

    def clear_history(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._hist_raw.clear()
        self._notif_to_iid.clear()
        self.history.clear()
        try:
            self.popup_toast.clear_ui_pop_queue()
        except Exception:
            pass

    def export_all_history(self):
        """手动导出内存中的历史列表为 CSV（写入 backup/，不覆盖旧文件）。"""
        if not self.history:
            messagebox.showwarning(i18n.t("missing"), i18n.t("history_export_empty"))
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = _backup_dir() / f"history_{stamp}.csv"
        try:
            with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(_HISTORY_CSV_HEADER)
                for row in self.history:
                    writer.writerow(
                        [
                            row.get("time", ""),
                            row.get("device", ""),
                            row.get("app_name", ""),
                            row.get("app_bundle", ""),
                            resolve_raw_title(row),
                            resolve_raw_msg(row),
                        ]
                    )
            messagebox.showinfo(
                i18n.t("ok"),
                f"{i18n.t('history_export_ok')}\n{out_path}",
            )
        except Exception as e:
            messagebox.showerror(i18n.t("fail"), f"{i18n.t('history_export_fail')}\n{e}")

    def _show_desktop_popup(
        self,
        app_name: str,
        title: str,
        msg: str,
        icon_path: str = "",
        notif_id: str = "",
        body_text: str = "",
    ) -> None:
        """弹出桌面自定义 toast。关闭该弹窗绝不能动 history / 任何主页列表。"""

        def _do():
            if not bool(self.var_win_toast.get()):
                return
            print(
                f"[DESKTOP-TOAST] show desktop toast "
                f"app={app_name!r} title={title!r} notif_id={notif_id!r}"
            )
            self.popup_toast.show(
                app_name,
                title,
                msg,
                icon_path=icon_path,
                notif_id=notif_id,
                body_text=body_text,
            )

        try:
            self.after(0, _do)
        except tk.TclError:
            pass

    def open_history_for_notif(self, notif_id: str) -> None:
        if not notif_id:
            self.restore_from_tray()
            self.nb.select(self.tab_history)
            return
        iid = self._notif_to_iid.get(notif_id)
        self.restore_from_tray()
        self.nb.select(self.tab_history)
        if not iid:
            return
        try:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
        except tk.TclError:
            pass

    def copy_selected_history(self):
        sel = self.tree.selection()
        if not sel:
            return
        lines = []
        for iid in sel:
            vals = self.tree.item(iid, "values")
            lines.append(" | ".join(str(v) for v in vals))
        text = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo(i18n.t("ok"), i18n.t("copied"))

    def clear_logs(self):
        self.txt_logs.delete("1.0", "end")

    # ---------- Tests ----------
    def test_desktop_toast(self):
        if not bool(self.var_win_toast.get()):
            messagebox.showwarning(i18n.t("missing"), i18n.t("misc_toast_test_disabled"))
            return
        self.popup_toast.test_popup()
        messagebox.showinfo(i18n.t("ok"), i18n.t("misc_toast_test_ok"))

    def test_telegram(self):
        def validate():
            if not self.var_tg_token.get().strip() or not self.var_tg_chat.get().strip():
                return "Fill Telegram token & chat_id"
            return None

        def run():
            send_telegram(self.var_tg_token.get().strip(), self.var_tg_chat.get().strip(), "✅ Telegram Test: NekoLink OK")

        self._dest_test_async("Telegram", validate, run)

    def test_dingtalk(self):
        def validate():
            if not self.var_dt_webhook.get().strip():
                return "Fill DingTalk webhook"
            return None

        def run():
            send_dingtalk_text(
                self.var_dt_webhook.get().strip(),
                self.var_dt_secret.get().strip(),
                "✅ DingTalk Test: NekoLink OK",
            )

        self._dest_test_async("DingTalk", validate, run)

    def test_ntfy(self):
        def validate():
            if not self.var_ntfy_url.get().strip():
                return "Fill ntfy Topic URL"
            return None

        def run():
            send_ntfy(self.var_ntfy_url.get().strip(), "✅ ntfy Test: NekoLink OK", "NekoLink Test")

        self._dest_test_async("ntfy", validate, run)

    def test_gotify(self):
        def validate():
            if not self.var_gotify_url.get().strip() or not self.var_gotify_token.get().strip():
                return "Fill Gotify Server URL & App Token"
            return None

        def run():
            send_gotify(
                self.var_gotify_url.get().strip(),
                self.var_gotify_token.get().strip(),
                "NekoLink",
                "✅ Gotify Test: NekoLink OK",
                priority=self.safe_int(self.var_gotify_prio.get(), 5),
            )

        self._dest_test_async("Gotify", validate, run)

    def test_custom_http(self):
        def validate():
            if not self.var_custom_http_url.get().strip():
                return "Fill HTTP POST URL"
            return None

        def run():
            title, text, payload = self._dest_test_content()
            send_custom_http(
                self.var_custom_http_url.get().strip(),
                self.var_custom_http_headers.get(),
                self.var_custom_http_body.get(),
                payload,
                self.collect_config(),
            )

        self._dest_test_async("HTTP POST", validate, run)

    def test_feishu(self):
        def validate():
            if not self.var_feishu_webhook.get().strip():
                return "Fill Feishu Webhook URL"
            return None

        def run():
            _, text, _ = self._dest_test_content()
            send_feishu(self.var_feishu_webhook.get().strip(), f"✅ Feishu Test\n{text}")

        self._dest_test_async("Feishu", validate, run)

    def test_pushdeer(self):
        def validate():
            if not self.var_pushdeer_key.get().strip():
                return "Fill PushDeer Key"
            return None

        def run():
            _, text, _ = self._dest_test_content()
            send_pushdeer(self.var_pushdeer_key.get().strip(), "NekoLink Test", f"✅ PushDeer Test\n{text}")

        self._dest_test_async("PushDeer", validate, run)

    def test_bark(self):
        def validate():
            if not self.var_bark_key.get().strip():
                return "Fill Bark API Key"
            return None

        def run():
            _, text, _ = self._dest_test_content()
            send_bark(
                self.var_bark_key.get().strip(),
                "NekoLink Test",
                f"✅ Bark Test\n{text}",
                sound=self.var_bark_sound.get().strip(),
            )

        self._dest_test_async("Bark", validate, run)

    def test_pushplus(self):
        def validate():
            if not self.var_pushplus_token.get().strip():
                return "Fill PushPlus token"
            return None

        def run():
            _, text, _ = self._dest_test_content()
            send_pushplus(self.var_pushplus_token.get().strip(), "NekoLink Test", f"✅ PushPlus Test\n{text}")

        self._dest_test_async("PushPlus", validate, run)

    def test_wxpusher(self):
        def validate():
            if not self.var_wxpusher_token.get().strip():
                return "Fill WxPusher appToken"
            return None

        def run():
            _, text, _ = self._dest_test_content()
            send_wxpusher(
                self.var_wxpusher_token.get().strip(),
                self.var_wxpusher_topic.get().strip(),
                "NekoLink Test",
                f"✅ WxPusher Test\n{text}",
            )

        self._dest_test_async("WxPusher", validate, run)

    def test_serverchan(self):
        def validate():
            if not self.var_serverchan_key.get().strip():
                return "Fill ServerChan SendKey"
            return None

        def run():
            _, text, _ = self._dest_test_content()
            send_serverchan(self.var_serverchan_key.get().strip(), "NekoLink Test", f"✅ ServerChan Test\n{text}")

        self._dest_test_async("ServerChan", validate, run)

    def test_pushover(self):
        def validate():
            if not self.var_pushover_token.get().strip() or not self.var_pushover_user.get().strip():
                return "Fill Pushover API Token & User Key"
            return None

        def run():
            _, text, _ = self._dest_test_content()
            send_pushover(
                self.var_pushover_token.get().strip(),
                self.var_pushover_user.get().strip(),
                "NekoLink Test",
                f"✅ Pushover Test\n{text}",
            )

        self._dest_test_async("Pushover", validate, run)

    def test_wecom(self):
        def validate():
            if not self.var_wecom_webhook.get().strip():
                return "Fill WeCom Webhook URL"
            return None

        def run():
            _, text, _ = self._dest_test_content()
            send_wecom(self.var_wecom_webhook.get().strip(), f"✅ WeCom Test\n{text}")

        self._dest_test_async("WeCom", validate, run)

    def test_email(self):
        cfg = self.collect_config()
        try:
            send_email(cfg, "NekoLink Email Test", "✅ Email Test: NekoLink OK")
            messagebox.showinfo(i18n.t("ok"), "Email test sent")
        except Exception as e:
            messagebox.showerror(i18n.t("fail"), f"Email failed: {e}")

    # ---------- Tray behavior ----------
    def on_close_to_tray(self):
        self.withdraw()
        self.log("[UI] minimized to tray")

    def restore_from_tray(self):
        try:
            self.deiconify()
            try:
                self.state("normal")
            except Exception:
                pass
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def exit_app(self):
        try:
            self.on_stop()
        except Exception:
            pass
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.popup_toast.destroy_all()
        except Exception:
            pass
        self.destroy()

    # ---------- Config ----------
    def collect_config(self) -> BridgeConfig:
        if hasattr(self, "_sync_dest_text_widgets"):
            self._sync_dest_text_widgets()
        addrs = []
        device_aliases: dict = {}
        for iid in self.dev_tree.get_children():
            vals = self.dev_tree.item(iid, "values")
            if not vals or not str(vals[0]).strip():
                continue
            addr = str(vals[0]).strip()
            alias = str(vals[1]).strip() if len(vals) > 1 else ""
            addrs.append(addr)
            if alias:
                device_aliases[addr] = alias

        app_bundle_map: dict = {}
        block_bundle: list = []
        for iid in self.map_tree.get_children():
            vals = self.map_tree.item(iid, "values")
            if not vals or not str(vals[0]).strip():
                continue
            bundle_id = str(vals[0]).strip()
            name = str(vals[1]).strip() if len(vals) > 1 else bundle_id
            skip = str(vals[2]).strip() if len(vals) > 2 else i18n.t("no")
            app_bundle_map[bundle_id] = name
            if skip in (i18n.t("yes"), "是", "Yes", "yes"):
                block_bundle.append(bundle_id)

        app_icon_map = {k: v for k, v in (self._map_icon_paths or {}).items() if v and str(v).strip()}

        blocks = [self.lst_block.get(i).strip() for i in range(self.lst_block.size()) if self.lst_block.get(i).strip()]

        # ui lang
        label = self.var_lang.get().strip()
        ui_lang = "zh"
        for k, v in i18n.LANG_LABEL.items():
            if v == label:
                ui_lang = k
                break

        return BridgeConfig(
            ui_lang=ui_lang,

            ble_addresses=addrs,
            device_aliases=device_aliases,
            auto_pick_heart_rate=False,

            app_bundle_map=app_bundle_map,
            app_icon_map=app_icon_map,
            block_bundle=block_bundle,

            enable_telegram=bool(self.var_tg_on.get()),
            telegram_bot_token=self.var_tg_token.get().strip(),
            telegram_chat_id=self.var_tg_chat.get().strip(),

            enable_dingtalk=bool(self.var_dt_on.get()),
            dingtalk_webhook=self.var_dt_webhook.get().strip(),
            dingtalk_secret=self.var_dt_secret.get().strip(),

            enable_ntfy=bool(self.var_ntfy_on.get()),
            ntfy_url=self.var_ntfy_url.get().strip(),

            enable_gotify=bool(self.var_gotify_on.get()),
            gotify_url=self.var_gotify_url.get().strip(),
            gotify_token=self.var_gotify_token.get().strip(),
            gotify_priority=self.safe_int(self.var_gotify_prio.get(), 5),

            webhook_use_full_message=bool(
                self.var_webhook_full.get() if hasattr(self, "var_webhook_full") else True
            ),

            enable_custom_http=bool(self.var_custom_http_on.get()) if hasattr(self, "var_custom_http_on") else False,
            custom_http_url=self.var_custom_http_url.get().strip() if hasattr(self, "var_custom_http_url") else "",
            custom_http_headers_json=self.var_custom_http_headers.get() if hasattr(self, "var_custom_http_headers") else "{}",
            custom_http_body_template=self.var_custom_http_body.get() if hasattr(self, "var_custom_http_body") else "",

            enable_feishu=bool(self.var_feishu_on.get()) if hasattr(self, "var_feishu_on") else False,
            feishu_webhook_url=self.var_feishu_webhook.get().strip() if hasattr(self, "var_feishu_webhook") else "",

            enable_pushdeer=bool(self.var_pushdeer_on.get()) if hasattr(self, "var_pushdeer_on") else False,
            pushdeer_key=self.var_pushdeer_key.get().strip() if hasattr(self, "var_pushdeer_key") else "",

            enable_bark=bool(self.var_bark_on.get()) if hasattr(self, "var_bark_on") else False,
            bark_api_key=self.var_bark_key.get().strip() if hasattr(self, "var_bark_key") else "",
            bark_sound=self.var_bark_sound.get().strip() if hasattr(self, "var_bark_sound") else "",

            enable_pushplus=bool(self.var_pushplus_on.get()) if hasattr(self, "var_pushplus_on") else False,
            pushplus_token=self.var_pushplus_token.get().strip() if hasattr(self, "var_pushplus_token") else "",

            enable_wxpusher=bool(self.var_wxpusher_on.get()) if hasattr(self, "var_wxpusher_on") else False,
            wxpusher_app_token=self.var_wxpusher_token.get().strip() if hasattr(self, "var_wxpusher_token") else "",
            wxpusher_topic_id=self.var_wxpusher_topic.get().strip() if hasattr(self, "var_wxpusher_topic") else "",

            enable_serverchan=bool(self.var_serverchan_on.get()) if hasattr(self, "var_serverchan_on") else False,
            serverchan_sendkey=self.var_serverchan_key.get().strip() if hasattr(self, "var_serverchan_key") else "",

            enable_pushover=bool(self.var_pushover_on.get()) if hasattr(self, "var_pushover_on") else False,
            pushover_api_token=self.var_pushover_token.get().strip() if hasattr(self, "var_pushover_token") else "",
            pushover_user_key=self.var_pushover_user.get().strip() if hasattr(self, "var_pushover_user") else "",

            enable_wecom=bool(self.var_wecom_on.get()) if hasattr(self, "var_wecom_on") else False,
            wecom_webhook_url=self.var_wecom_webhook.get().strip() if hasattr(self, "var_wecom_webhook") else "",

            enable_email=bool(self.var_mail_on.get()),
            smtp_host=self.var_smtp_host.get().strip(),
            smtp_port=self.safe_int(self.var_smtp_port.get(), 587),
            smtp_user=self.var_smtp_user.get().strip(),
            smtp_pass=self.var_smtp_pass.get().strip(),
            email_to=self.var_email_to.get().strip(),
            email_from=self.var_email_from.get().strip(),

            dedup_seconds=self.safe_int(self.var_dedup.get(), 8),

            block_keywords=blocks,
            block_case_insensitive=bool(self.var_block_ci.get()),

            enable_code_highlight=bool(self.var_code_on.get()),
            code_send_separately=bool(self.var_code_sep.get()),
            code_regex=self.cfg.code_regex,
            code_separate_prefix=self.cfg.code_separate_prefix,

            history_limit=self.safe_int(self.var_history_limit.get(), self.cfg.history_limit),
            auto_start=bool(self.var_auto_start.get()) if hasattr(self, "var_auto_start") else False,
            autostart_enabled=bool(self.var_auto_start.get()) if hasattr(self, "var_auto_start") else False,
            tray_icon_path=(
                self.var_tray_icon_path.get().strip()
                if hasattr(self, "var_tray_icon_path")
                else str(getattr(self.cfg, "tray_icon_path", DEFAULT_TRAY_ICON_REL) or DEFAULT_TRAY_ICON_REL)
            ),

            show_battery_in_message=bool(self.var_show_battery.get()),
            enable_windows_toast=bool(self.var_win_toast.get()),
            popup_position=self._popup_pos_key_from_label(self.var_popup_pos.get()),
            notification_width=self._notif_width_key_from_label(self.var_notif_width.get()),
            notification_font_size=self._notif_font_key_from_label(self.var_notif_font.get()),
            max_preview_chars=normalize_max_preview_chars(self.var_max_preview.get()),
            max_pop_notification=normalize_max_pop_notification(self.var_max_pop.get()),
            popup_card_gap=normalize_popup_card_gap(
                self.var_card_gap.get() if hasattr(self, "var_card_gap") else 12
            ),
            notification_auto_close_seconds=normalize_notification_auto_close_seconds(
                self.var_auto_close.get() if hasattr(self, "var_auto_close") else 10
            ),
            desktop_toast_auto_dismiss=normalize_notification_auto_close_seconds(
                self.var_auto_close.get() if hasattr(self, "var_auto_close") else 10
            ),
            sound_enable=bool(self.var_sound_enable.get()) if hasattr(self, "var_sound_enable") else True,
            sound_volume=normalize_sound_volume(
                self.var_sound_volume.get() if hasattr(self, "var_sound_volume") else 80
            ),
            sound_selected_file=normalize_sound_selected_file(
                self.var_sound_file.get()
                if hasattr(self, "var_sound_file")
                else DEFAULT_SOUND_SELECTED_FILE
            ),
            app_sound_map=normalize_app_sound_map(
                getattr(self, "_app_sound_map", {}) or {}
            ),
            auto_backup_enable=bool(self.var_auto_backup.get()),
            auto_backup_path=self.var_auto_backup_path.get().strip(),
            privacy_show_title=bool(self.var_privacy_show_title.get()),
            privacy_show_msg=bool(self.var_privacy_show_msg.get()),

            push_template=self._get_push_template_text(),
        )

    @staticmethod
    def safe_int(v, default=0):
        try:
            return int(str(v).strip())
        except Exception:
            return default

    # ---------- Log pump ----------
    def _flush_logs(self):
        try:
            while True:
                s = self.log_q.get_nowait()
                self.txt_logs.insert("end", s + "\n")
                self.txt_logs.see("end")
        except queue.Empty:
            pass
        self.after(120, self._flush_logs)


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        return loop.run_until_complete(coro)
    except RuntimeError:
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()


if __name__ == "__main__":
    App().mainloop()