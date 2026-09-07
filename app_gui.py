# app_gui.py
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Optional
from ttkbootstrap.scrolled import ScrolledFrame
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import i18n
from ancs_bridge import (
    BridgeConfig,
    BridgeManager,
    PUSH_TEMPLATE_PRESETS,
    PUSH_TEMPLATE_VARS,
    format_ancs_date,
    get_app_display_name,
    get_device_display_name,
    get_config_path,
    load_config,
    render_push_template,
    save_config,
    send_dingtalk_text,
    send_email,
    send_telegram,
    send_gotify,
    send_ntfy,
)
from tray_helper import TrayController
from popup_toast import (
    NotificationManager,
    normalize_popup_position,
    POPUP_POSITION_LABELS,
    normalize_notification_width,
    normalize_notification_font_size,
    normalize_max_preview_chars,
    NOTIFICATION_WIDTH_LABELS,
    NOTIFICATION_FONT_LABELS,
)

CONFIG_PATH = get_config_path()
ICON_PATH = "icon.ico"


class App(tb.Window):
    def __init__(self):
        super().__init__(themename="flatly")

        self.log_q = queue.Queue()
        self.cfg = load_config(CONFIG_PATH)

        # i18n
        i18n.set_lang(getattr(self.cfg, "ui_lang", "zh"))

        self.title(i18n.t("app_title"))
        self.geometry("1100x720")
        self.minsize(980, 620)

        self.running = False
        self.history = []  # list of payload dict
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
        )
        self.manager = BridgeManager(
            self.cfg,
            self.log,
            self.on_notification,
            on_desktop_popup=self._show_desktop_popup,
        )

        icon_path = ICON_PATH if os.path.exists(ICON_PATH) else None
        self.tray = TrayController(
            title="NekoLink",
            on_restore=self.restore_from_tray,
            on_exit=self.exit_app,
            icon_path=icon_path,
        )
        self.tray.start()

        self.ui = {}  # widgets needing i18n refresh

        self._build_ui()
        self.apply_i18n()

        self._flush_logs()

        # close -> tray
        self.protocol("WM_DELETE_WINDOW", self.on_close_to_tray)

    # ---------- UI ----------
    def _build_ui(self):
        root = tb.Frame(self, padding=10)
        root.pack(fill=BOTH, expand=True)

        header = tb.Frame(root)
        header.pack(fill=X)

        self.ui["lbl_header"] = tb.Label(header, text="", font=("Segoe UI", 16, "bold"))
        self.ui["lbl_header"].pack(side=LEFT)

        # language selector (right)
        lang_frame = tb.Frame(header)
        lang_frame.pack(side=RIGHT, padx=(10, 0))

        self.ui["lbl_lang"] = tb.Label(lang_frame, text="Lang")
        self.ui["lbl_lang"].pack(side=LEFT, padx=(0, 6))

        self.var_lang = tk.StringVar(value=i18n.lang_label(i18n.get_lang()))
        self.cmb_lang = tb.Combobox(
            lang_frame,
            width=10,
            textvariable=self.var_lang,
            values=[i18n.lang_label("zh"), i18n.lang_label("en"), i18n.lang_label("ja")],
            state="readonly",
        )
        self.cmb_lang.pack(side=LEFT)

        def on_lang_change(_evt=None):
            label = self.var_lang.get().strip()
            code = "zh"
            for k, v in i18n.LANG_LABEL.items():
                if v == label:
                    code = k
                    break
            i18n.set_lang(code)
            self.cfg.ui_lang = code
            save_config(CONFIG_PATH, self.cfg)
            self.apply_i18n()

        self.cmb_lang.bind("<<ComboboxSelected>>", on_lang_change)

        # status + config path
        self.ui["lbl_status"] = tb.Label(header, text="", bootstyle="danger")
        self.ui["lbl_status"].pack(side=RIGHT)

        self.ui["lbl_cfg"] = tb.Label(header, text="", bootstyle="secondary")
        self.ui["lbl_cfg"].pack(side=RIGHT, padx=(0, 12))

        # notebook
        self.nb = tb.Notebook(root)
        self.nb.pack(fill=BOTH, expand=True, pady=(10, 0))

        self.tab_main = tb.Frame(self.nb)
        self.tab_devices = tb.Frame(self.nb)
        self.tab_dest = tb.Frame(self.nb)
        self.tab_filter = tb.Frame(self.nb)
        self.tab_misc = tb.Frame(self.nb)
        self.tab_history = tb.Frame(self.nb)
        self.tab_logs = tb.Frame(self.nb)

        self.nb.add(self.tab_main, text="Main")
        self.nb.add(self.tab_devices, text="Devices")
        self.nb.add(self.tab_dest, text="Destinations")
        self.nb.add(self.tab_filter, text="Block Keywords")
        self.nb.add(self.tab_misc, text="Misc")
        self.nb.add(self.tab_history, text="History")
        self.nb.add(self.tab_logs, text="Logs")

        self._build_main()
        self._build_devices()
        self._build_dest()     # ✅ scroll + bottom save
        self._build_filter()
        self._build_misc()
        self._build_history()
        self._build_logs()

    def apply_i18n(self):
        self.title(i18n.t("app_title"))
        self.ui["lbl_header"].config(text=i18n.t("header_line"))
        self.ui["lbl_cfg"].config(text=f"{i18n.t('config_path')}: {CONFIG_PATH}")

        if self.running:
            self.ui["lbl_status"].config(text=i18n.t("status_running"), bootstyle="success")
        else:
            self.ui["lbl_status"].config(text=i18n.t("status_stopped"), bootstyle="danger")

        self.nb.tab(self.tab_main, text=i18n.t("tab_main"))
        self.nb.tab(self.tab_devices, text=i18n.t("tab_devices"))
        self.nb.tab(self.tab_dest, text=i18n.t("tab_dest"))
        self.nb.tab(self.tab_filter, text=i18n.t("tab_filter"))
        self.nb.tab(self.tab_misc, text=i18n.t("tab_misc"))
        self.nb.tab(self.tab_history, text=i18n.t("tab_history"))
        self.nb.tab(self.tab_logs, text=i18n.t("tab_logs"))

        # main
        self.ui["lbl_run_control"].config(text=i18n.t("run_control"))
        self.ui["btn_save_all"].config(text=i18n.t("save_all"))
        self.ui["btn_start"].config(text=i18n.t("start"))
        self.ui["btn_stop"].config(text=i18n.t("stop"))
        self.ui["lbl_dedup"].config(text=i18n.t("dedup_sec"))
        self.ui["chk_code_on"].config(text=i18n.t("enable_code_detect"))
        self.ui["chk_code_sep"].config(text=i18n.t("send_code_sep"))
        self.ui["lbl_history_limit"].config(text=i18n.t("history_limit"))
        self.ui["lbl_preview"].config(text=i18n.t("latest_preview"))
        self.ui["lbl_push_preview"].config(text=i18n.t("push_preview"))
        self.ui["lbl_push_tpl"].config(text=i18n.t("push_template"))
        self.ui["lbl_tpl_preset"].config(text=i18n.t("tpl_preset"))
        self.ui["lbl_tpl_var"].config(text=i18n.t("tpl_var"))
        self.ui["btn_tpl_insert"].config(text=i18n.t("tpl_insert"))
        self.ui["lbl_tpl_hint"].config(text=i18n.t("tpl_hint"))
        preset_labels = [i18n.t("tpl_preset_default"), i18n.t("tpl_preset_simple"), i18n.t("tpl_preset_detail")]
        self.cmb_tpl_preset.config(values=preset_labels)
        if not self.var_tpl_preset.get():
            self.cmb_tpl_preset.set(preset_labels[0])
        self.ui["lbl_tip_tray"].config(text=i18n.t("tip_tray"))

        # devices
        self.ui["lbl_devices_title"].config(text=i18n.t("selected_ble"))
        self.ui["btn_scan"].config(text=i18n.t("scan"))
        self.ui["btn_add_addr"].config(text=i18n.t("add"))
        self.ui["btn_remove_addr"].config(text=i18n.t("remove_selected"))
        self.ui["txt_scan_hint"].config(text=i18n.t("scan_hint"))
        self.ui["btn_save_devices"].config(text=i18n.t("save"))
        self.ui["lbl_device_alias"].config(text=i18n.t("device_alias"))
        self.ui["btn_set_device_alias"].config(text=i18n.t("set_alias"))
        if "dev_tree" in self.ui:
            self.ui["dev_tree"].heading("addr", text=i18n.t("col_ble_addr"))
            self.ui["dev_tree"].heading("alias", text=i18n.t("col_alias"))

        # history / app map
        self.ui["lbl_app_map"].config(text=i18n.t("app_map_title"))
        self.ui["lbl_map_hint"].config(text=i18n.t("app_map_hint"))
        self.ui["lbl_map_bundle"].config(text=i18n.t("col_bundle_id"))
        self.ui["lbl_map_name"].config(text=i18n.t("col_app_name"))
        self.ui["btn_map_upsert"].config(text=i18n.t("map_upsert"))
        self.ui["btn_map_remove"].config(text=i18n.t("remove_selected"))
        self.ui["btn_save_history"].config(text=i18n.t("save"))
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
        self.ui["lbl_block_intro"].config(text=i18n.t("block_intro"))
        self.ui["chk_block_ci"].config(text=i18n.t("case_insensitive"))
        self.ui["btn_add_block"].config(text=i18n.t("add"))
        self.ui["btn_remove_block"].config(text=i18n.t("remove_selected"))
        self.ui["btn_save_filter"].config(text=i18n.t("save"))

        # misc
        self.ui["lbl_misc_title"].config(text=i18n.t("misc_title"))
        self.ui["chk_battery"].config(text=i18n.t("misc_battery"))
        self.ui["chk_toast"].config(text=i18n.t("misc_toast"))
        self.ui["lbl_toast_hint"].config(text=i18n.t("misc_toast_hint"))
        self.ui["btn_test_toast"].config(text=i18n.t("misc_toast_test"))
        self.ui["lbl_popup_position"].config(text=i18n.t("misc_popup_position"))
        if hasattr(self, "cmb_popup_pos"):
            cur = self._popup_pos_key_from_label(self.var_popup_pos.get())
            self.cmb_popup_pos.configure(values=[self._popup_pos_label_from_key(k) for k in self._popup_pos_keys])
            self.var_popup_pos.set(self._popup_pos_label_from_key(cur))
        self.ui["lbl_notif_font"].config(text=i18n.t("misc_notif_font"))
        if hasattr(self, "cmb_notif_font"):
            cur_font = self._notif_font_key_from_label(self.var_notif_font.get())
            font_values = list(dict.fromkeys(
                [self._notif_font_label_from_key(k) for k in self._notif_font_keys]
            ))
            self.cmb_notif_font.configure(values=font_values)
            self.var_notif_font.set(self._notif_font_label_from_key(cur_font))
        self.ui["lbl_notif_width"].config(text=i18n.t("misc_notif_width"))
        if hasattr(self, "cmb_notif_width"):
            cur_width = self._notif_width_key_from_label(self.var_notif_width.get())
            width_values = list(dict.fromkeys(
                [self._notif_width_label_from_key(k) for k in self._notif_width_keys]
            ))
            self.cmb_notif_width.configure(values=width_values)
            self.var_notif_width.set(self._notif_width_label_from_key(cur_width))
        if "lbl_max_preview" in self.ui:
            self.ui["lbl_max_preview"].config(text=i18n.t("misc_max_preview"))
        if hasattr(self, "privacy_frm"):
            self.privacy_frm.configure(text=i18n.t("privacy_title"))
        if "chk_privacy_show_title" in self.ui:
            self.ui["chk_privacy_show_title"].config(text=i18n.t("privacy_show_title"))
            self.ui["lbl_privacy_show_title_hint"].config(text=i18n.t("privacy_show_title_hint"))
            self.ui["chk_privacy_show_msg"].config(text=i18n.t("privacy_show_msg"))
            self.ui["lbl_privacy_show_msg_hint"].config(text=i18n.t("privacy_show_msg_hint"))
        self.ui["btn_save_misc"].config(text=i18n.t("save"))

        # history/logs
        self.ui["lbl_history_title"].config(text=i18n.t("history_title"))
        self.ui["btn_clear_history"].config(text=i18n.t("clear"))
        self.ui["btn_copy_history"].config(text=i18n.t("copy_selected"))
        self.ui["lbl_logs_title"].config(text=i18n.t("tab_logs"))
        self.ui["btn_clear_logs"].config(text=i18n.t("clear"))

        # destinations bottom save
        if "btn_save_dest" in self.ui:
            self.ui["btn_save_dest"].config(text=i18n.t("save"))

    # ---------- Tabs ----------
    def _build_main(self):
        frm = tb.Frame(self.tab_main, padding=12)
        frm.pack(fill=BOTH, expand=True)

        left = tb.Frame(frm)
        left.pack(side=LEFT, fill=Y, padx=(0, 16))

        self.ui["lbl_run_control"] = tb.Label(left, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_run_control"].pack(anchor=W, pady=(0, 8))

        btns = tb.Frame(left)
        btns.pack(anchor=W, pady=(0, 8))

        self.ui["btn_save_all"] = tb.Button(btns, text="", bootstyle="secondary", command=self.on_save)
        self.ui["btn_save_all"].pack(side=LEFT, padx=(0, 8))
        self.ui["btn_start"] = tb.Button(btns, text="", bootstyle="success", command=self.on_start)
        self.ui["btn_start"].pack(side=LEFT, padx=(0, 8))
        self.ui["btn_stop"] = tb.Button(btns, text="", bootstyle="danger", command=self.on_stop)
        self.ui["btn_stop"].pack(side=LEFT)

        tb.Separator(left).pack(fill=X, pady=10)

        self.var_dedup = tk.StringVar(value=str(getattr(self.cfg, "dedup_seconds", 8)))
        self.ui["lbl_dedup"] = tb.Label(left, text="")
        self.ui["lbl_dedup"].pack(anchor=W)
        tb.Entry(left, textvariable=self.var_dedup, width=10).pack(anchor=W, pady=(0, 10))

        self.var_code_on = tk.BooleanVar(value=self.cfg.enable_code_highlight)
        self.var_code_sep = tk.BooleanVar(value=self.cfg.code_send_separately)
        self.ui["chk_code_on"] = tb.Checkbutton(left, text="", variable=self.var_code_on, bootstyle="round-toggle")
        self.ui["chk_code_on"].pack(anchor=W, pady=(0, 6))
        self.ui["chk_code_sep"] = tb.Checkbutton(left, text="", variable=self.var_code_sep, bootstyle="round-toggle")
        self.ui["chk_code_sep"].pack(anchor=W)

        self.var_history_limit = tk.StringVar(value=str(self.cfg.history_limit))
        self.ui["lbl_history_limit"] = tb.Label(left, text="")
        self.ui["lbl_history_limit"].pack(anchor=W, pady=(10, 0))
        tb.Entry(left, textvariable=self.var_history_limit, width=10).pack(anchor=W)

        tb.Separator(left).pack(fill=X, pady=10)

        self.ui["lbl_push_tpl"] = tb.Label(left, text="推送模板", font=("Segoe UI", 11, "bold"))
        self.ui["lbl_push_tpl"].pack(anchor=W, pady=(0, 6))

        preset_row = tb.Frame(left)
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
        self.cmb_tpl_preset.pack(side=LEFT, fill=X, expand=True)
        self.cmb_tpl_preset.bind("<<ComboboxSelected>>", self._on_tpl_preset_change)

        self.txt_push_template = tk.Text(left, height=7, wrap="word", width=42)
        self.txt_push_template.pack(fill=X, pady=(0, 6))
        tpl_text = getattr(self.cfg, "push_template", "") or PUSH_TEMPLATE_PRESETS["default"]
        self.txt_push_template.insert("1.0", tpl_text)

        var_row = tb.Frame(left)
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
        self.ui["lbl_tpl_hint"] = tb.Label(left, text=hint, bootstyle="secondary", wraplength=380, justify=LEFT)
        self.ui["lbl_tpl_hint"].pack(anchor=W)

        right = tb.Frame(frm)
        right.pack(side=LEFT, fill=BOTH, expand=True)

        self.ui["lbl_preview"] = tb.Label(right, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_preview"].pack(anchor=W)

        self.preview = tk.Text(right, height=8, wrap="word")
        self.preview.pack(fill=X, pady=(8, 8))
        self.preview.insert("end", "（暂无）\n")

        self.ui["lbl_push_preview"] = tb.Label(right, text="推送预览", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_push_preview"].pack(anchor=W)

        self.push_preview = tk.Text(right, height=8, wrap="word")
        self.push_preview.pack(fill=X, pady=(8, 8))
        self.push_preview.insert("end", "（暂无）\n")

        self.ui["lbl_tip_tray"] = tb.Label(right, text="")
        self.ui["lbl_tip_tray"].pack(anchor=W)
        self._last_payload: Optional[dict] = None

    def _build_devices(self):
        frm = tb.Frame(self.tab_devices, padding=12)
        frm.pack(fill=BOTH, expand=True)

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

        self.ui["btn_save_devices"] = tb.Button(frm, text="", bootstyle="primary", command=self.on_save)
        self.ui["btn_save_devices"].pack(anchor=SE, pady=(10, 0))

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
        self._persist_config(show_msg=False)
        self.log(f"[UI] 设备别名已保存: {addr} -> {alias or '(空)'}")

    # ✅ Destinations: scrollable + fixed bottom Save
    def _build_dest(self):
        outer = tb.Frame(self.tab_dest, padding=12)
        outer.pack(fill=BOTH, expand=True)

        # scroll area
        sc = ScrolledFrame(outer, autohide=True)
        sc.pack(fill=BOTH, expand=True)

        frm = sc

        # Telegram
        tg = tb.Labelframe(frm, text="Telegram", padding=10)
        tg.pack(fill=X, pady=(0, 12))

        self.var_tg_on = tk.BooleanVar(value=self.cfg.enable_telegram)
        self.var_tg_token = tk.StringVar(value=self.cfg.telegram_bot_token)
        self.var_tg_chat = tk.StringVar(value=self.cfg.telegram_chat_id)

        tb.Checkbutton(tg, text="Enable Telegram", variable=self.var_tg_on, bootstyle="round-toggle").grid(
            row=0, column=0, sticky=W, pady=(0, 6)
        )
        tb.Label(tg, text="Bot Token").grid(row=1, column=0, sticky=W)
        self.ent_tg_token = tb.Entry(tg, textvariable=self.var_tg_token, width=70, show="•")
        self.ent_tg_token.grid(row=1, column=1, sticky=W, pady=2)
        self._tg_token_hidden = True

        def toggle_tg_token():
            self._tg_token_hidden = not self._tg_token_hidden
            self.ent_tg_token.config(show=("•" if self._tg_token_hidden else ""))

        tb.Button(tg, text="👁", width=3, bootstyle="secondary", command=toggle_tg_token).grid(
            row=1, column=2, sticky=W, padx=(6, 0)
        )

        tb.Label(tg, text="Chat ID").grid(row=2, column=0, sticky=W)
        tb.Entry(tg, textvariable=self.var_tg_chat, width=30).grid(row=2, column=1, sticky=W, pady=2)
        tb.Button(tg, text="Test", bootstyle="success", command=self.test_telegram).grid(
            row=3, column=1, sticky=W, pady=(8, 0)
        )

        # DingTalk
        dt = tb.Labelframe(frm, text="DingTalk (Robot)", padding=10)
        dt.pack(fill=X, pady=(0, 12))

        self.var_dt_on = tk.BooleanVar(value=getattr(self.cfg, "enable_dingtalk", False))
        self.var_dt_webhook = tk.StringVar(value=getattr(self.cfg, "dingtalk_webhook", ""))
        self.var_dt_secret = tk.StringVar(value=getattr(self.cfg, "dingtalk_secret", ""))

        tb.Checkbutton(dt, text="Enable DingTalk", variable=self.var_dt_on, bootstyle="round-toggle").grid(
            row=0, column=0, sticky=W, pady=(0, 6)
        )
        tb.Label(dt, text="Webhook").grid(row=1, column=0, sticky=W)
        tb.Entry(dt, textvariable=self.var_dt_webhook, width=78).grid(row=1, column=1, sticky=W, pady=2)

        tb.Label(dt, text="Secret (sign)").grid(row=2, column=0, sticky=W)
        self.ent_dt_secret = tb.Entry(dt, textvariable=self.var_dt_secret, width=36, show="•")
        self.ent_dt_secret.grid(row=2, column=1, sticky=W, pady=2)
        self._dt_secret_hidden = True

        def toggle_dt_secret():
            self._dt_secret_hidden = not self._dt_secret_hidden
            self.ent_dt_secret.config(show=("•" if self._dt_secret_hidden else ""))

        tb.Button(dt, text="👁", width=3, bootstyle="secondary", command=toggle_dt_secret).grid(
            row=2, column=2, sticky=W, padx=(6, 0)
        )
        tb.Button(dt, text="Test", bootstyle="success", command=self.test_dingtalk).grid(
            row=3, column=1, sticky=W, pady=(8, 0)
        )

        # ntfy
        nf = tb.Labelframe(frm, text="ntfy.sh", padding=10)
        nf.pack(fill=X, pady=(0, 12))

        self.var_ntfy_on = tk.BooleanVar(value=getattr(self.cfg, "enable_ntfy", False))
        self.var_ntfy_url = tk.StringVar(value=getattr(self.cfg, "ntfy_url", ""))

        tb.Checkbutton(nf, text="Enable ntfy", variable=self.var_ntfy_on, bootstyle="round-toggle").grid(
            row=0, column=0, sticky=W, pady=(0, 6)
        )
        tb.Label(nf, text="Topic URL").grid(row=1, column=0, sticky=W)
        tb.Entry(nf, textvariable=self.var_ntfy_url, width=78).grid(row=1, column=1, sticky=W, pady=2)
        tb.Button(nf, text="Test", bootstyle="success", command=self.test_ntfy).grid(
            row=2, column=1, sticky=W, pady=(8, 0)
        )

        # Gotify
        gf = tb.Labelframe(frm, text="Gotify", padding=10)
        gf.pack(fill=X, pady=(0, 12))

        self.var_gotify_on = tk.BooleanVar(value=getattr(self.cfg, "enable_gotify", False))
        self.var_gotify_url = tk.StringVar(value=getattr(self.cfg, "gotify_url", ""))
        self.var_gotify_token = tk.StringVar(value=getattr(self.cfg, "gotify_token", ""))
        self.var_gotify_prio = tk.StringVar(value=str(getattr(self.cfg, "gotify_priority", 5)))

        tb.Checkbutton(gf, text="Enable Gotify", variable=self.var_gotify_on, bootstyle="round-toggle").grid(
            row=0, column=0, sticky=W, pady=(0, 6)
        )
        tb.Label(gf, text="Server URL").grid(row=1, column=0, sticky=W)
        tb.Entry(gf, textvariable=self.var_gotify_url, width=60).grid(row=1, column=1, sticky=W, pady=2)

        tb.Label(gf, text="App Token").grid(row=2, column=0, sticky=W)
        self.ent_gotify_token = tb.Entry(gf, textvariable=self.var_gotify_token, width=36, show="•")
        self.ent_gotify_token.grid(row=2, column=1, sticky=W, pady=2)
        self._gotify_token_hidden = True

        def toggle_gotify_token():
            self._gotify_token_hidden = not self._gotify_token_hidden
            self.ent_gotify_token.config(show=("•" if self._gotify_token_hidden else ""))

        tb.Button(gf, text="👁", width=3, bootstyle="secondary", command=toggle_gotify_token).grid(
            row=2, column=2, sticky=W, padx=(6, 0)
        )

        tb.Label(gf, text="Priority").grid(row=3, column=0, sticky=W)
        tb.Entry(gf, textvariable=self.var_gotify_prio, width=8).grid(row=3, column=1, sticky=W, pady=2)
        tb.Button(gf, text="Test", bootstyle="success", command=self.test_gotify).grid(
            row=4, column=1, sticky=W, pady=(8, 0)
        )

        # Email
        mail = tb.Labelframe(frm, text="Email (SMTP)", padding=10)
        mail.pack(fill=X)

        self.var_mail_on = tk.BooleanVar(value=self.cfg.enable_email)
        self.var_smtp_host = tk.StringVar(value=self.cfg.smtp_host)
        self.var_smtp_port = tk.StringVar(value=str(self.cfg.smtp_port))
        self.var_smtp_user = tk.StringVar(value=self.cfg.smtp_user)
        self.var_smtp_pass = tk.StringVar(value=self.cfg.smtp_pass)
        self.var_email_from = tk.StringVar(value=self.cfg.email_from)
        self.var_email_to = tk.StringVar(value=self.cfg.email_to)

        tb.Checkbutton(mail, text="Enable Email", variable=self.var_mail_on, bootstyle="round-toggle").grid(
            row=0, column=0, sticky=W, pady=(0, 6)
        )
        tb.Label(mail, text="Host").grid(row=1, column=0, sticky=W)
        tb.Entry(mail, textvariable=self.var_smtp_host, width=36).grid(row=1, column=1, sticky=W, pady=2)
        tb.Label(mail, text="Port").grid(row=1, column=2, sticky=W)
        tb.Entry(mail, textvariable=self.var_smtp_port, width=8).grid(row=1, column=3, sticky=W, pady=2)

        tb.Label(mail, text="User").grid(row=2, column=0, sticky=W)
        tb.Entry(mail, textvariable=self.var_smtp_user, width=36).grid(row=2, column=1, sticky=W, pady=2)

        tb.Label(mail, text="Pass").grid(row=3, column=0, sticky=W)
        self.ent_smtp_pass = tb.Entry(mail, textvariable=self.var_smtp_pass, width=32, show="•")
        self.ent_smtp_pass.grid(row=3, column=1, sticky=W, pady=2)
        self._smtp_pass_hidden = True

        def toggle_smtp_pass():
            self._smtp_pass_hidden = not self._smtp_pass_hidden
            self.ent_smtp_pass.config(show=("•" if self._smtp_pass_hidden else ""))

        tb.Button(mail, text="👁", width=3, bootstyle="secondary", command=toggle_smtp_pass).grid(
            row=3, column=2, sticky=W, padx=(6, 0)
        )

        tb.Label(mail, text="From").grid(row=4, column=0, sticky=W)
        tb.Entry(mail, textvariable=self.var_email_from, width=36).grid(row=4, column=1, sticky=W, pady=2)
        tb.Label(mail, text="To").grid(row=5, column=0, sticky=W)
        tb.Entry(mail, textvariable=self.var_email_to, width=36).grid(row=5, column=1, sticky=W, pady=2)
        tb.Button(mail, text="Test", bootstyle="success", command=self.test_email).grid(
            row=6, column=1, sticky=W, pady=(8, 0)
        )

        # bottom fixed bar
        bottom = tb.Frame(outer)
        bottom.pack(fill=X, pady=(10, 0))
        tb.Separator(bottom).pack(fill=X, pady=(0, 8))

        self.ui["btn_save_dest"] = tb.Button(bottom, text="", bootstyle="primary", command=self.on_save)
        self.ui["btn_save_dest"].pack(side=RIGHT)

    def _build_filter(self):
        frm = tb.Frame(self.tab_filter, padding=12)
        frm.pack(fill=BOTH, expand=True)

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

        self.ui["btn_save_filter"] = tb.Button(frm, text="", bootstyle="primary", command=self.on_save)
        self.ui["btn_save_filter"].pack(anchor=SE, pady=(10, 0))

    def _build_misc(self):
        frm = tb.Frame(self.tab_misc, padding=10)
        frm.pack(fill=BOTH, expand=True)

        self.ui["lbl_misc_title"] = tb.Label(frm, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_misc_title"].pack(anchor=W, pady=(0, 4))

        self.var_show_battery = tk.BooleanVar(value=getattr(self.cfg, "show_battery_in_message", True))
        self.var_win_toast = tk.BooleanVar(value=getattr(self.cfg, "enable_windows_toast", True))

        self.ui["chk_battery"] = tb.Checkbutton(frm, text="", variable=self.var_show_battery, bootstyle="round-toggle")
        self.ui["chk_battery"].pack(anchor=W, pady=(0, 3))

        toast_row = tb.Frame(frm)
        toast_row.pack(fill=X, anchor=W, pady=(0, 2))
        self.ui["chk_toast"] = tb.Checkbutton(toast_row, text="", variable=self.var_win_toast, bootstyle="round-toggle")
        self.ui["chk_toast"].pack(side=LEFT)
        self.ui["btn_test_toast"] = tb.Button(toast_row, text="测试弹窗", bootstyle="info", command=self.test_desktop_toast)
        self.ui["btn_test_toast"].pack(side=LEFT, padx=(12, 0))

        self.ui["lbl_toast_hint"] = tb.Label(frm, text="", bootstyle="secondary", wraplength=520, justify=LEFT)
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
        self.var_notif_font = tk.StringVar(
            value=self._notif_font_label_from_key(getattr(self.cfg, "notification_font_size", 10))
        )
        font_values = [self._notif_font_label_from_key(k) for k in self._notif_font_keys]
        # 去重，防止下拉出现重复「默认」项
        font_values = list(dict.fromkeys(font_values))
        self.cmb_notif_font = tb.Combobox(
            font_row,
            textvariable=self.var_notif_font,
            values=font_values,
            state="readonly",
            width=14,
        )
        self.cmb_notif_font.pack(side=LEFT)

        width_row = tb.Frame(frm)
        width_row.pack(fill=X, anchor=W, pady=(0, 3))
        self._notif_width_keys = [300, 420, 480, 540]
        self.ui["lbl_notif_width"] = tb.Label(width_row, text="通知弹窗宽度")
        self.ui["lbl_notif_width"].pack(side=LEFT, padx=(0, 8))
        self.var_notif_width = tk.StringVar(
            value=self._notif_width_label_from_key(getattr(self.cfg, "notification_width", 420))
        )
        width_values = [self._notif_width_label_from_key(k) for k in self._notif_width_keys]
        width_values = list(dict.fromkeys(width_values))
        self.cmb_notif_width = tb.Combobox(
            width_row,
            textvariable=self.var_notif_width,
            values=width_values,
            state="readonly",
            width=14,
        )
        self.cmb_notif_width.pack(side=LEFT)

        preview_row = tb.Frame(frm)
        preview_row.pack(fill=X, anchor=W, pady=(0, 3))
        self.ui["lbl_max_preview"] = tb.Label(preview_row, text="消息最大预览字数：")
        self.ui["lbl_max_preview"].pack(side=LEFT, padx=(0, 8))
        self.var_max_preview = tk.StringVar(
            value=str(normalize_max_preview_chars(getattr(self.cfg, "max_preview_chars", 50)))
        )
        self.ent_max_preview = tb.Entry(preview_row, textvariable=self.var_max_preview, width=8)
        self.ent_max_preview.pack(side=LEFT)

        def _normalize_preview_entry():
            val = normalize_max_preview_chars(self.var_max_preview.get())
            self.var_max_preview.set(str(val))
            return val

        def _sync_popup_ui_settings(_evt=None):
            preview_chars = _normalize_preview_entry()
            self.popup_toast.apply_ui_settings(
                popup_position=self._popup_pos_key_from_label(self.var_popup_pos.get()),
                notification_font_size=self._notif_font_key_from_label(self.var_notif_font.get()),
                notification_width=self._notif_width_key_from_label(self.var_notif_width.get()),
                privacy_show_title=bool(self.var_privacy_show_title.get()),
                privacy_show_msg=bool(self.var_privacy_show_msg.get()),
                max_preview_chars=preview_chars,
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

        self.cmb_popup_pos.bind("<<ComboboxSelected>>", _sync_popup_ui_settings)
        self.cmb_notif_font.bind("<<ComboboxSelected>>", _sync_popup_ui_settings)
        self.cmb_notif_width.bind("<<ComboboxSelected>>", _sync_popup_ui_settings)
        self.ent_max_preview.bind("<FocusOut>", _sync_popup_ui_settings)
        self.ent_max_preview.bind("<Return>", _sync_popup_ui_settings)

        self.privacy_frm = tb.Labelframe(frm, text="隐私设置", padding=6)
        self.privacy_frm.pack(fill=X, anchor=W, pady=(4, 4))

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

        def _on_toast_toggle():
            if self.running and self.manager:
                self.manager.cfg.enable_windows_toast = bool(self.var_win_toast.get())

        self.var_win_toast.trace_add("write", lambda *_: _on_toast_toggle())

        self.ui["btn_save_misc"] = tb.Button(frm, text="", bootstyle="primary", command=self.on_save)
        self.ui["btn_save_misc"].pack(anchor=SE, pady=(6, 0))

    def _build_history(self):
        frm = tb.Frame(self.tab_history, padding=12)
        frm.pack(fill=BOTH, expand=True)

        top = tb.Frame(frm)
        top.pack(fill=X, pady=(0, 8))

        self.ui["lbl_history_title"] = tb.Label(top, text="", font=("Segoe UI", 12, "bold"))
        self.ui["lbl_history_title"].pack(side=LEFT)

        self.ui["btn_clear_history"] = tb.Button(top, text="", bootstyle="warning", command=self.clear_history)
        self.ui["btn_clear_history"].pack(side=RIGHT, padx=(8, 0))
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
        self.tree.pack(fill=BOTH, expand=True, pady=(0, 10))
        self.tree.bind("<Double-1>", self._on_history_dblclick)

        map_frm = tb.Labelframe(frm, text="应用名称映射", padding=10)
        map_frm.pack(fill=X)

        self.ui["lbl_app_map"] = tb.Label(map_frm, text="应用名称映射", font=("Segoe UI", 11, "bold"))
        self.ui["lbl_app_map"].pack(anchor=W)
        self.ui["lbl_map_hint"] = tb.Label(
            map_frm,
            text="双击上方历史记录可快速填入 Bundle ID。保存后写入 config.json。",
            bootstyle="secondary",
        )
        self.ui["lbl_map_hint"].pack(anchor=W, pady=(0, 8))

        self.map_tree = tb.Treeview(
            map_frm, columns=("bundle", "name", "block", "icon"), show="headings", height=5, selectmode="browse"
        )
        self.ui["map_tree"] = self.map_tree
        self.map_tree.heading("bundle", text="Bundle ID")
        self.map_tree.heading("name", text="显示名称")
        self.map_tree.heading("block", text="跳过 webhook")
        self.map_tree.heading("icon", text="图标")
        self.map_tree.column("bundle", width=220, anchor=W)
        self.map_tree.column("name", width=120, anchor=W)
        self.map_tree.column("block", width=90, anchor=W)
        self.map_tree.column("icon", width=100, anchor=W)
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
        tb.Entry(icon_row, textvariable=self.var_map_icon, width=52).pack(side=LEFT, padx=(0, 8))
        self.ui["btn_map_icon"] = tb.Button(icon_row, text="浏览...", bootstyle="secondary", command=self.browse_app_icon)
        self.ui["btn_map_icon"].pack(side=LEFT)
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
        self.ui["btn_save_history"] = tb.Button(map_frm, text="保存", bootstyle="primary", command=self.on_save)
        self.ui["btn_save_history"].pack(anchor=SE, pady=(10, 0))

    def _reload_app_map_tree(self):
        self.map_tree.delete(*self.map_tree.get_children())
        self._map_icon_paths = dict(getattr(self.cfg, "app_icon_map", {}) or {})
        block_set = set(getattr(self.cfg, "block_bundle", []) or [])
        for bundle_id, name in sorted((self.cfg.app_bundle_map or {}).items()):
            skip = i18n.t("yes") if bundle_id in block_set else i18n.t("no")
            icon = self._map_icon_paths.get(bundle_id, "")
            icon_show = os.path.basename(icon) if icon else ""
            self.map_tree.insert("", "end", values=(bundle_id, name, skip, icon_show))

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

    def _on_history_dblclick(self, _evt=None):
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

        found = None
        for iid in self.map_tree.get_children():
            if self.map_tree.item(iid, "values")[0] == bundle_id:
                found = iid
                break
        if found:
            self.map_tree.item(found, values=(bundle_id, name, skip_text, icon_show))
        else:
            self.map_tree.insert("", "end", values=(bundle_id, name, skip_text, icon_show))

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
                self._map_icon_paths.pop(str(vals[0]).strip(), None)
            self.map_tree.delete(iid)

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

        preview_text = (
            f"Device: {device_name}\n"
            f"Battery: {bat_text}\n"
            f"App: {app_name} ({app_raw})\n"
            f"Title: {payload.get('title')}\n"
            f"Msg: {payload.get('msg')}\n"
            f"Codes: {' '.join(payload.get('codes') or [])}\n"
            f"Date: {date_fmt}\n"
        )
        self.preview.delete("1.0", "end")
        self.preview.insert("end", preview_text)
        self._refresh_push_preview(payload)

        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(payload["ts"]))
        codes = " ".join(payload.get("codes") or [])
        iid = self.tree.insert(
            "", "end",
            values=(t, device_name, bat_text, app_name,
                    payload.get("title", ""), payload.get("msg", ""), codes)
        )
        self._hist_raw[iid] = {
            "app": app_raw,
            "device": device_raw,
            "notif_id": payload.get("notif_id") or "",
        }
        nid = payload.get("notif_id")
        if nid:
            self._notif_to_iid[nid] = iid

        # prune
        limit = int(self.safe_int(self.var_history_limit.get(), default=self.cfg.history_limit))
        children = self.tree.get_children()
        if len(children) > max(50, limit):
            for iid in children[: len(children) - limit]:
                raw = self._hist_raw.pop(iid, {})
                old_nid = raw.get("notif_id")
                if old_nid:
                    self._notif_to_iid.pop(old_nid, None)
                self.tree.delete(iid)

    def on_save(self):
        self._persist_config(show_msg=True)

    def _persist_config(self, show_msg: bool = True):
        cfg = self.collect_config()
        save_config(CONFIG_PATH, cfg)
        self.cfg = cfg
        self.manager.cfg = cfg
        self._sync_popup_toast_from_cfg(cfg)
        self._reload_app_map_tree()
        if show_msg:
            messagebox.showinfo(i18n.t("ok"), f"{i18n.t('saved_to')}\n{CONFIG_PATH}")

    def on_start(self):
        if self.running:
            return

        cfg = self.collect_config()
        save_config(CONFIG_PATH, cfg)
        self.cfg = cfg
        self.manager.cfg = cfg
        self._sync_popup_toast_from_cfg(cfg)

        addrs = cfg.ble_addresses or []
        if not addrs:
            messagebox.showwarning(i18n.t("no_devices"), i18n.t("add_device_warn"))
            return

        self.running = True
        self.apply_i18n()
        self.manager.start_all(addrs)
        self.log("[UI] started")

    def on_stop(self):
        if not self.running:
            return
        self.running = False
        self.apply_i18n()
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
        return i18n.t(NOTIFICATION_FONT_LABELS.get(key, "misc_notif_font_sm"))

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

    def _sync_popup_toast_from_cfg(self, cfg) -> None:
        self.popup_toast.apply_ui_settings(
            popup_position=getattr(cfg, "popup_position", "bottom_right"),
            notification_width=getattr(cfg, "notification_width", 420),
            notification_font_size=getattr(cfg, "notification_font_size", 10),
            privacy_show_title=getattr(cfg, "privacy_show_title", True),
            privacy_show_msg=getattr(cfg, "privacy_show_msg", True),
            max_preview_chars=getattr(cfg, "max_preview_chars", 50),
        )

    def clear_history(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._hist_raw.clear()
        self._notif_to_iid.clear()

    def _show_desktop_popup(
        self,
        app_name: str,
        title: str,
        msg: str,
        icon_path: str = "",
        notif_id: str = "",
        body_text: str = "",
    ) -> None:
        def _do():
            if not bool(self.var_win_toast.get()):
                return
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
        token = self.var_tg_token.get().strip()
        chat_id = self.var_tg_chat.get().strip()
        if not token or not chat_id:
            messagebox.showwarning(i18n.t("missing"), "Fill Telegram token & chat_id")
            return
        try:
            send_telegram(token, chat_id, "✅ Telegram Test: NekoLink OK")
            messagebox.showinfo(i18n.t("ok"), "Telegram test sent")
        except Exception as e:
            messagebox.showerror(i18n.t("fail"), f"Telegram failed: {e}")

    def test_dingtalk(self):
        webhook = self.var_dt_webhook.get().strip()
        secret = self.var_dt_secret.get().strip()
        if not webhook:
            messagebox.showwarning(i18n.t("missing"), "Fill DingTalk webhook")
            return
        try:
            send_dingtalk_text(webhook, secret, "✅ DingTalk Test: NekoLink OK")
            messagebox.showinfo(i18n.t("ok"), "DingTalk test sent")
        except Exception as e:
            messagebox.showerror(i18n.t("fail"), f"DingTalk failed: {e}")

    def test_ntfy(self):
        url = self.var_ntfy_url.get().strip()
        if not url:
            messagebox.showwarning(i18n.t("missing"), "Fill ntfy Topic URL")
            return
        try:
            send_ntfy(url, "✅ ntfy Test: NekoLink OK", "NekoLink Test")
            messagebox.showinfo(i18n.t("ok"), "ntfy test sent")
        except Exception as e:
            messagebox.showerror(i18n.t("fail"), f"ntfy failed: {e}")

    def test_gotify(self):
        url = self.var_gotify_url.get().strip()
        token = self.var_gotify_token.get().strip()
        prio = self.safe_int(self.var_gotify_prio.get(), 5)
        if not url or not token:
            messagebox.showwarning(i18n.t("missing"), "Fill Gotify Server URL & App Token")
            return
        try:
            send_gotify(url, token, "NekoLink", "✅ Gotify Test: NekoLink OK", priority=prio)
            messagebox.showinfo(i18n.t("ok"), "Gotify test sent")
        except Exception as e:
            messagebox.showerror(i18n.t("fail"), f"Gotify failed: {e}")

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
            autostart_enabled=self.cfg.autostart_enabled,

            show_battery_in_message=bool(self.var_show_battery.get()),
            enable_windows_toast=bool(self.var_win_toast.get()),
            popup_position=self._popup_pos_key_from_label(self.var_popup_pos.get()),
            notification_width=self._notif_width_key_from_label(self.var_notif_width.get()),
            notification_font_size=self._notif_font_key_from_label(self.var_notif_font.get()),
            max_preview_chars=normalize_max_preview_chars(self.var_max_preview.get()),
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