# i18n.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict

SUPPORTED = ["zh", "en", "ja"]

LANG_LABEL = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
}

DICT: Dict[str, Dict[str, str]] = {
    "app_title": {
        "zh": "NekoLink · iPhone 通知转发器（Windows）",
        "en": "NekoLink · iPhone Notification Bridge (Windows)",
        "ja": "NekoLink · iPhone 通知ブリッジ（Windows）",
    },
    "header_line": {
        "zh": "🐾 NekoLink",
        "en": "🐾 NekoLink",
        "ja": "🐾 NekoLink",
    },
    "header_brand": {
        "zh": "🐾 NekoLink",
        "en": "🐾 NekoLink",
        "ja": "🐾 NekoLink",
    },
    "misc_auto_start": {
        "zh": "开机自动启动 NekoLink",
        "en": "Start NekoLink with Windows",
        "ja": "起動時に NekoLink を自動実行",
    },
    "misc_auto_start_hint": {
        "zh": "开启后程序随系统开机自动运行",
        "en": "Launch automatically when Windows starts",
        "ja": "Windows 起動時に自動実行します",
    },
    "auto_start_on": {"zh": "已开启开机自启动", "en": "Auto-start enabled", "ja": "自動起動を有効にしました"},
    "auto_start_off": {"zh": "已关闭开机自启动", "en": "Auto-start disabled", "ja": "自動起動を無効にしました"},
    "misc_tray_icon": {"zh": "状态栏图标", "en": "Tray icon", "ja": "トレイアイコン"},
    "misc_tray_icon_hint": {
        "zh": "修改状态栏图标后需要重启程序生效",
        "en": "Restart required after changing tray icon",
        "ja": "トレイアイコン変更後は再起動が必要です",
    },
    "browse": {"zh": "浏览", "en": "Browse", "ja": "参照"},
    "status_stopped": {"zh": "● 已停止", "en": "● Stopped", "ja": "● 停止中"},
    "status_running": {"zh": "● 运行中", "en": "● Running", "ja": "● 実行中"},
    "config_path": {"zh": "配置", "en": "Config", "ja": "設定"},

    "tab_main": {"zh": "主页", "en": "Main", "ja": "メイン"},
    "tab_devices": {"zh": "设备", "en": "Devices", "ja": "デバイス"},
    "tab_dest": {"zh": "转发目标", "en": "Destinations", "ja": "転送先"},
    "tab_filter": {"zh": "屏蔽关键词", "en": "Block Keywords", "ja": "ブロック"},
    "tab_misc": {"zh": "杂项", "en": "Misc", "ja": "その他"},
    "tab_history": {"zh": "历史", "en": "History", "ja": "履歴"},
    "tab_logs": {"zh": "日志", "en": "Logs", "ja": "ログ"},

    "sidebar_subtitle": {
        "zh": "iPhone 通知转发器",
        "en": "iPhone Notification Bridge",
        "ja": "iPhone 通知ブリッジ",
    },
    "nav_home": {"zh": "首页", "en": "Home", "ja": "ホーム"},
    "nav_history": {"zh": "消息历史", "en": "Message History", "ja": "メッセージ履歴"},
    "nav_dest": {"zh": "推送目标", "en": "Push Targets", "ja": "転送先"},
    "nav_template": {"zh": "推送模板", "en": "Push Templates", "ja": "プッシュテンプレート"},
    "nav_settings": {"zh": "设置", "en": "Settings", "ja": "設定"},
    "nav_logs": {"zh": "日志", "en": "Logs", "ja": "ログ"},
    "settings_title": {"zh": "设置", "en": "Settings", "ja": "設定"},
    "settings_subtitle": {
        "zh": "NekoLink 的运行、通知与数据设置",
        "en": "Runtime, notification and data settings for NekoLink",
        "ja": "NekoLink の実行・通知・データ設定",
    },
    "settings_back": {"zh": "← 返回", "en": "← Back", "ja": "← 戻る"},
    "ble_connected": {"zh": "BLE 已连接", "en": "BLE connected", "ja": "BLE 接続済み"},
    "ble_disconnected": {"zh": "BLE 未连接", "en": "BLE disconnected", "ja": "BLE 未接続"},
    "card_notification": {"zh": "通知设置", "en": "Notifications", "ja": "通知設定"},
    "card_notification_desc": {
        "zh": "通知接收、去重与验证码过滤",
        "en": "Reception, dedup and verification-code filters",
        "ja": "受信・重複排除・認証コードフィルタ",
    },
    "card_desktop": {"zh": "桌面通知", "en": "Desktop Notifications", "ja": "デスクトップ通知"},
    "card_desktop_desc": {
        "zh": "Windows 桌面弹窗与显示方式",
        "en": "Windows desktop popups and display",
        "ja": "Windows デスクトップ通知と表示",
    },
    "card_push": {"zh": "推送行为", "en": "Push Behavior", "ja": "プッシュ動作"},
    "card_push_desc": {
        "zh": "通知转发策略与规则",
        "en": "Forwarding strategy and rules",
        "ja": "転送戦略とルール",
    },
    "card_ble": {"zh": "iPhone / BLE", "en": "iPhone / BLE", "ja": "iPhone / BLE"},
    "card_ble_desc": {
        "zh": "iPhone 蓝牙 ANCS 连接与通信设置",
        "en": "iPhone BLE ANCS connection settings",
        "ja": "iPhone BLE ANCS 接続設定",
    },
    "card_data": {"zh": "数据与历史", "en": "Data & History", "ja": "データと履歴"},
    "card_data_desc": {
        "zh": "历史记录与数据管理",
        "en": "History retention and data management",
        "ja": "履歴保持とデータ管理",
    },
    "card_sound": {"zh": "声音与提醒", "en": "Sound & Alerts", "ja": "サウンドと通知"},
    "card_sound_desc": {
        "zh": "通知音效与提醒方式",
        "en": "Notification sounds and alerts",
        "ja": "通知音とアラート",
    },
    "card_about": {"zh": "关于 NekoLink", "en": "About NekoLink", "ja": "NekoLink について"},
    "card_about_desc": {
        "zh": "查看软件版本、作者信息等",
        "en": "Version, author and app info",
        "ja": "バージョン・作者情報",
    },
    "about_version": {"zh": "版本", "en": "Version", "ja": "バージョン"},
    "about_author": {
        "zh": "NekoLink · iPhone 通知转发器（Windows）",
        "en": "NekoLink · iPhone Notification Bridge (Windows)",
        "ja": "NekoLink · iPhone 通知ブリッジ（Windows）",
    },
    "data_clear_hint": {
        "zh": "清除历史请前往「消息历史」页使用清除按钮。",
        "en": "Use Clear on the Message History page to wipe history.",
        "ja": "履歴削除は「メッセージ履歴」ページのクリアを使用してください。",
    },

    "save": {"zh": "保存", "en": "Save", "ja": "保存"},
    "save_all": {"zh": "保存", "en": "Save", "ja": "保存"},
    "config_saved": {"zh": "配置已保存", "en": "Configuration saved", "ja": "設定を保存しました"},
    "saved_restart_hint": {
        "zh": "部分设置（字体大小、弹窗宽度）需重启程序生效。",
        "en": "Some settings (font size, popup width) require a restart.",
        "ja": "一部の設定（フォント/幅）は再起動後に有効です。",
    },
    "saved_hot_reload": {
        "zh": "配置已保存。关键词/图标/弹窗数量等已立即生效；字号与弹窗宽度需重启后生效。",
        "en": "Saved. Keywords/icons/popup limits apply now; font size and width need restart.",
        "ja": "保存しました。キーワード等は即時反映。フォント/幅は再起動後に有効。",
    },
    "start": {"zh": "启动", "en": "Start", "ja": "開始"},
    "stop": {"zh": "停止", "en": "Stop", "ja": "停止"},
    "scan": {"zh": "扫描", "en": "Scan", "ja": "スキャン"},
    "add": {"zh": "添加", "en": "Add", "ja": "追加"},
    "remove_selected": {"zh": "删除所选", "en": "Remove selected", "ja": "選択削除"},
    "clear": {"zh": "清空", "en": "Clear", "ja": "クリア"},
    "copy_selected": {"zh": "复制所选", "en": "Copy selected", "ja": "選択コピー"},

    "tip_tray": {
        "zh": "提示：点击关闭按钮会最小化到托盘。退出请在托盘菜单中操作。",
        "en": "Tip: Close button will minimize to tray. Exit from tray menu.",
        "ja": "ヒント：閉じるとトレイに最小化されます。終了はトレイメニューから。",
    },

    "run_control": {"zh": "运行控制", "en": "Run Control", "ja": "実行制御"},
    "dedup_sec": {"zh": "去重（秒）", "en": "Dedup (sec)", "ja": "重複排除(秒)"},
    "enable_code_detect": {"zh": "启用验证码识别", "en": "Enable code detect", "ja": "コード検出を有効化"},
    "send_code_sep": {"zh": "验证码单独发送", "en": "Send code separately", "ja": "コードを別送信"},
    "history_limit": {"zh": "历史条数上限", "en": "History limit", "ja": "履歴上限"},
    "latest_preview": {"zh": "最新通知预览", "en": "Latest notification preview", "ja": "最新通知プレビュー"},
    "push_preview": {"zh": "推送预览（钉钉/ntfy）", "en": "Push preview (DingTalk/ntfy)", "ja": "転送プレビュー"},
    "push_template": {"zh": "推送模板", "en": "Push template", "ja": "転送テンプレート"},
    "tpl_preset": {"zh": "预设", "en": "Preset", "ja": "プリセット"},
    "tpl_preset_default": {"zh": "默认（含设备+时间）", "en": "Default (device+time)", "ja": "標準（端末+時間）"},
    "tpl_preset_simple": {"zh": "简洁", "en": "Simple", "ja": "簡潔"},
    "tpl_preset_detail": {"zh": "详细", "en": "Detailed", "ja": "詳細"},
    "tpl_var": {"zh": "插入变量", "en": "Insert variable", "ja": "変数を挿入"},
    "tpl_insert": {"zh": "插入", "en": "Insert", "ja": "挿入"},
    "tpl_hint": {
        "zh": "可用变量（可重复）：{device} {device_mac} {app} {app_id} {title} {msg} {date} {date_raw} {battery} {codes} {receive_time}",
        "en": "Variables (repeatable): {device} {device_mac} {app} {app_id} {title} {msg} {date} {date_raw} {battery} {codes} {receive_time}",
        "ja": "利用可能な変数: {device} {device_mac} {app} {app_id} {title} {msg} {date} {date_raw} {battery} {codes} {receive_time}",
    },

    "selected_ble": {"zh": "已选择的 BLE 地址", "en": "Selected BLE addresses", "ja": "選択されたBLEアドレス"},
    "device_alias": {"zh": "设备别名", "en": "Device alias", "ja": "デバイス別名"},
    "set_alias": {"zh": "设置别名", "en": "Set alias", "ja": "別名を設定"},
    "select_device_first": {"zh": "请先在列表中选择一个设备", "en": "Select a device in the list first", "ja": "先にデバイスを選択してください"},
    "col_ble_addr": {"zh": "BLE 地址", "en": "BLE address", "ja": "BLEアドレス"},
    "col_alias": {"zh": "别名", "en": "Alias", "ja": "別名"},
    "col_bundle_id": {"zh": "Bundle ID", "en": "Bundle ID", "ja": "Bundle ID"},
    "col_app_name": {"zh": "显示名称", "en": "Display name", "ja": "表示名"},
    "col_skip_webhook": {"zh": "跳过 webhook", "en": "Skip webhook", "ja": "Webhook除外"},
    "col_icon": {"zh": "应用图标", "en": "App icon", "ja": "アイコン"},
    "browse_icon": {"zh": "浏览...", "en": "Browse...", "ja": "参照..."},
    "map_icon_hint": {
        "zh": "可选：自定义 .png/.ico 路径；留空则按应用名自动生成彩色字母图标",
        "en": "Optional custom .png/.ico; auto letter icon if empty",
        "ja": "任意：.png/.ico を指定。空なら自動生成",
    },
    "app_map_title": {"zh": "应用名称映射", "en": "App name mapping", "ja": "アプリ名マッピング"},
    "app_map_hint": {
        "zh": "单击上方历史记录可快速填入 Bundle ID。保存后写入 config.json。",
        "en": "Click a history row to fill Bundle ID. Saved to config.json.",
        "ja": "履歴行をクリックして Bundle ID を入力。config.json に保存されます。",
    },
    "map_upsert": {"zh": "添加/更新", "en": "Add / Update", "ja": "追加/更新"},
    "fill_bundle_id": {"zh": "请填写 Bundle ID", "en": "Please enter Bundle ID", "ja": "Bundle ID を入力してください"},
    "yes": {"zh": "是", "en": "Yes", "ja": "はい"},
    "no": {"zh": "否", "en": "No", "ja": "いいえ"},
    "scan_hint": {
        "zh": "扫描结果会显示在这里。双击一行可填入地址输入框。",
        "en": "Scan results will appear here. Double-click a line to fill the address input.",
        "ja": "スキャン結果がここに表示されます。行をダブルクリックすると入力欄に反映します。",
    },

    "block_intro": {
        "zh": "屏蔽关键词：通知文本包含任意关键词就会被忽略。",
        "en": "Block keywords: if notification contains any of these, it will be ignored.",
        "ja": "ブロック語句：通知に含まれる場合は無視されます。",
    },
    "case_insensitive": {"zh": "忽略大小写", "en": "Case-insensitive match", "ja": "大文字小文字を無視"},

    "misc_title": {"zh": "杂项设置", "en": "Misc Settings", "ja": "その他設定"},
    "misc_battery": {
        "zh": "每条消息附带电量",
        "en": "Include battery in every message",
        "ja": "各メッセージにバッテリーを付与",
    },
    "misc_toast": {
        "zh": "启用桌面弹窗通知",
        "en": "Enable desktop popup notifications",
        "ja": "デスクトップポップアップ通知を有効化",
    },
    "misc_toast_hint": {
        "zh": "Telegram 风格桌面弹窗：最多 3 条，顶部「全部隐藏」，支持左上/左下/右上/右下四方向。点击卡片跳转历史。",
        "en": "Telegram-style popups (max 3). Hide All on top. Four corner positions. Click card for History.",
        "ja": "Telegram 風ポップアップ（最大3件）。四方向配置可。",
    },
    "misc_toast_test": {"zh": "测试弹窗", "en": "Test popup", "ja": "テスト"},
    "misc_toast_test_ok": {
        "zh": "已发送测试弹窗，请查看屏幕对应角落。",
        "en": "Test popup sent. Check the configured screen corner.",
        "ja": "テストポップアップを送信しました。",
    },
    "misc_toast_test_disabled": {
        "zh": "请先开启「启用桌面弹窗通知」开关。",
        "en": "Enable desktop popup notifications first.",
        "ja": "先にポップアップ通知を有効にしてください。",
    },
    "misc_toast_test_fail": {
        "zh": "弹窗发送失败，请查看「日志」页。",
        "en": "Popup failed. Check Logs tab.",
        "ja": "ポップアップ送信に失敗しました。",
    },
    "misc_popup_position": {"zh": "弹窗位置", "en": "Popup position", "ja": "ポップアップ位置"},
    "misc_popup_pos_br": {"zh": "右下", "en": "Bottom right", "ja": "右下"},
    "misc_popup_pos_tr": {"zh": "右上", "en": "Top right", "ja": "右上"},
    "misc_popup_pos_bl": {"zh": "左下", "en": "Bottom left", "ja": "左下"},
    "misc_popup_pos_tl": {"zh": "左上", "en": "Top left", "ja": "左上"},
    "misc_notif_font": {"zh": "通知字体大小", "en": "Notification font size", "ja": "通知フォントサイズ"},
    "misc_notif_font_xs": {"zh": "极小 (6)", "en": "Tiny (6)", "ja": "極小 (6)"},
    "misc_notif_font_sm": {"zh": "很小 (8)", "en": "Very small (8)", "ja": "とても小 (8)"},
    "misc_notif_font_md": {"zh": "默认 (10)", "en": "Default (10)", "ja": "標準 (10)"},
    "misc_notif_font_lg": {"zh": "较大 (12)", "en": "Larger (12)", "ja": "大きめ (12)"},
    "misc_notif_width": {"zh": "通知弹窗宽度", "en": "Notification width", "ja": "通知幅"},
    "misc_notif_width_sm": {"zh": "小 (300)", "en": "Small (300)", "ja": "小 (300)"},
    "misc_notif_width_md": {"zh": "默认 (420)", "en": "Default (420)", "ja": "標準 (420)"},
    "misc_notif_width_lg": {"zh": "大 (480)", "en": "Large (480)", "ja": "大 (480)"},
    "misc_notif_width_xl": {"zh": "超大 (540)", "en": "Extra large (540)", "ja": "特大 (540)"},
    "misc_max_preview": {"zh": "消息最大预览字数：", "en": "Max preview chars:", "ja": "プレビュー最大文字数："},
    "misc_max_pop": {
        "zh": "屏幕最多同时可见弹窗数量；超额消息排队，关闭现有弹窗后自动继续弹出。",
        "en": "Max visible toasts; extras queue and show as others close.",
        "ja": "同時表示上限；超過分は待機し、閉じると順に表示。",
    },
    "misc_card_gap": {"zh": "弹窗卡片垂直间距(px)", "en": "Toast card gap (px)", "ja": "通知カード縦間隔(px)"},
    "misc_card_gap_hint": {
        "zh": "范围4‑60，控制多个桌面弹窗互相之间的空隙。",
        "en": "Range 4–60; vertical gap between stacked desktop toasts.",
        "ja": "範囲4〜60。デスクトップ通知の縦間隔。",
    },
    "misc_auto_close": {
        "zh": "通知弹窗自动显示时长(秒)",
        "en": "Toast auto-close (seconds)",
        "ja": "通知の自動表示時間(秒)",
    },
    "misc_auto_close_hint": {
        "zh": "范围3‑120秒，到时间弹窗自动关闭",
        "en": "Range 3–120s; toast closes automatically when time is up",
        "ja": "範囲3〜120秒。時間経過で自動的に閉じます",
    },
    "misc_auto_close_invalid": {
        "zh": "自动显示时长必须是整数秒（3‑120）。",
        "en": "Auto-close must be an integer between 3 and 120 seconds.",
        "ja": "自動表示時間は3〜120の整数秒で入力してください。",
    },
    "misc_sound_enable": {
        "zh": "启用通知提示音",
        "en": "Enable notification sound",
        "ja": "通知音を有効化",
    },
    "misc_sound_file": {
        "zh": "提示音音效文件:",
        "en": "Notification sound file:",
        "ja": "通知音ファイル:",
    },
    "misc_sound_volume": {
        "zh": "提示音音量",
        "en": "Notification volume",
        "ja": "通知音量",
    },
    "misc_sound_hint": {
        "zh": "提示：将 .wav 放入 assets/sound/ 后重启可出现在下拉框；发声时音量合成器会出现 NekoLink 滑块",
        "en": "Tip: Put .wav files in assets/sound/ and restart to list them; Volume Mixer shows NekoLink while playing.",
        "ja": "assets/sound/ に .wav を入れ再起動すると一覧に出ます。再生中のみミキサーにNekoLinkが出ます。",
    },
    "misc_sound_deps_missing": {
        "zh": "当前环境无可用音频后端，提示音已禁用。",
        "en": "No audio backend available; notification sound disabled.",
        "ja": "利用可能な音声バックエンドがなく、通知音は無効です。",
    },
    "misc_auto_backup": {"zh": "开启自动备份通知", "en": "Enable auto backup", "ja": "自動バックアップを有効化"},
    "misc_auto_backup_hint": {
        "zh": "自动写入 CSV 备份文件，新消息实时追加。",
        "en": "Append each notification to a CSV backup file in real time.",
        "ja": "新しい通知をCSVへリアルタイム追記します。",
    },
    "misc_auto_backup_path": {"zh": "备份文件路径（留空用默认）", "en": "Backup path (empty = default)", "ja": "バックアップパス（空=既定）"},
    "misc_restart_hint": {
        "zh": "修改后需要重启程序生效",
        "en": "Restart required for this change",
        "ja": "変更後は再起動が必要です",
    },
    "privacy_title": {"zh": "隐私设置", "en": "Privacy", "ja": "プライバシー"},
    "privacy_show_title": {
        "zh": "显示通知标题（发件人/会话标题）",
        "en": "Show notification title",
        "ja": "通知タイトルを表示",
    },
    "privacy_show_title_hint": {
        "zh": "取消勾选后：标题与消息全部预览隐藏，仅显示「您有一条新消息」。",
        "en": "Unchecked: hide title and message, show a generic notice only.",
        "ja": "オフ時：タイトルと本文を隠し、汎用メッセージのみ表示。",
    },
    "privacy_show_msg": {
        "zh": "显示通知消息内容（消息正文）",
        "en": "Show notification message",
        "ja": "通知本文を表示",
    },
    "privacy_show_msg_hint": {
        "zh": "取消勾选后：保留标题，消息替换为「您有一条新消息」。",
        "en": "Unchecked: keep title, replace message with a generic notice.",
        "ja": "オフ時：タイトルは残し、本文を汎用メッセージに置換。",
    },

    "history_title": {"zh": "通知历史", "en": "Notification History", "ja": "通知履歴"},
    "history_export_all": {"zh": "导出全部历史消息", "en": "Export all history", "ja": "履歴をすべてエクスポート"},
    "history_export_ok": {"zh": "导出成功，文件已保存到：", "en": "Export succeeded. Saved to:", "ja": "エクスポート成功。保存先:"},
    "history_export_fail": {"zh": "导出失败", "en": "Export failed", "ja": "エクスポート失敗"},
    "history_export_empty": {"zh": "当前没有可导出的历史消息。", "en": "No history to export.", "ja": "エクスポートする履歴がありません。"},
    "copied": {"zh": "已复制到剪贴板", "en": "Copied to clipboard", "ja": "クリップボードにコピーしました"},
    "saved_to": {"zh": "已保存到：", "en": "Saved to:", "ja": "保存先:"},
    "missing": {"zh": "缺少信息", "en": "Missing", "ja": "未入力"},
    "ok": {"zh": "成功", "en": "OK", "ja": "OK"},
    "fail": {"zh": "失败", "en": "Fail", "ja": "失敗"},
    "no_devices": {"zh": "没有设备", "en": "No devices", "ja": "デバイスなし"},
    "add_device_warn": {
        "zh": "请先在 Devices 里添加至少一个地址，或先 Scan 再添加。",
        "en": "Add at least one address in Devices tab or Scan to add.",
        "ja": "Devicesでアドレスを追加するか、Scanで見つけて追加してください。",
    },
}

_current_lang = "zh"


def set_lang(lang: str):
    global _current_lang
    lang = (lang or "").strip().lower()
    if lang not in SUPPORTED:
        lang = "zh"
    _current_lang = lang


def get_lang() -> str:
    return _current_lang


def lang_label(lang: str) -> str:
    return LANG_LABEL.get(lang, lang)


def t(key: str, fallback: str | None = None) -> str:
    key = key or ""
    row = DICT.get(key)
    if not row:
        return fallback if fallback is not None else key
    return row.get(_current_lang) or row.get("en") or fallback or key