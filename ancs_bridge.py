# ancs_bridge.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests
from bleak import BleakClient, BleakScanner

try:
    from win_toast import show_notification_toast, show_toast
except Exception:
    show_notification_toast = None  # type: ignore
    show_toast = None  # type: ignore


# 应用映射 / 设备别名 / webhook 黑名单请在 GUI 配置并保存到 config.json


def _default_app_bundle_map() -> Dict[str, str]:
    return {
        "com.tencent.xin": "微信",
        "com.alibaba.DingTalkTalk": "钉钉",
        "com.tencent.mqq": "QQ",
        "com.tencent.WeChatWork": "企业微信",
        "com.apple.MobileSMS": "短信",
        "com.netease.cloudmusic": "网易云音乐",
        "com.xiaojukeji.didi": "滴滴",
    }


def get_app_display_name(bundle_id: str, cfg: Optional["BridgeConfig"] = None) -> str:
    """根据 bundle_id 返回映射后的应用名，未映射则原样返回。"""
    bundle_id = bundle_id or ""
    mapping = _default_app_bundle_map()
    if cfg is not None:
        mapping = {**mapping, **(cfg.app_bundle_map or {})}
    return mapping.get(bundle_id, bundle_id)


def get_device_display_name(device: str, cfg: Optional["BridgeConfig"] = None) -> str:
    """根据 BLE 地址返回设备别名，未设置则原样返回 MAC。"""
    device = device or ""
    if cfg is None:
        return device
    return (cfg.device_aliases or {}).get(device, device)


def is_blocked_bundle(bundle_id: str, cfg: "BridgeConfig") -> bool:
    return bundle_id in set(cfg.block_bundle or [])


def _icons_cache_dir() -> Path:
    appdata = Path(os.getenv("APPDATA", str(Path.home())))
    d = appdata / "NekoLink" / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_app_icon(bundle_id: str, app_name: str, cfg: Optional["BridgeConfig"] = None) -> str:
    """返回 Toast 用图标路径：优先用户配置，否则自动生成字母图标。"""
    bundle_id = (bundle_id or "").strip()
    app_name = (app_name or bundle_id or "?").strip()

    if cfg is not None:
        custom = (cfg.app_icon_map or {}).get(bundle_id, "").strip()
        if custom and os.path.isfile(custom):
            return os.path.abspath(custom)

    if bundle_id:
        safe = re.sub(r"[^\w.\-]+", "_", bundle_id)
        cache = _icons_cache_dir() / f"{safe}.png"
        if cache.is_file():
            return str(cache)
        generated = _generate_app_icon(app_name, cache)
        if generated:
            return generated

    base = _base_dir()
    for name in ("icon.ico", "icon.png"):
        p = base / name
        if p.is_file():
            return str(p.resolve())
    return ""


def _generate_app_icon(app_name: str, out_path: Path) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont

        size = 128
        letter = (app_name or "?")[0].upper()
        seed = sum(ord(c) for c in app_name)
        color = (
            80 + seed % 120,
            80 + (seed // 7) % 120,
            80 + (seed // 13) % 120,
        )
        img = Image.new("RGBA", (size, size), color + (255,))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("segoeui.ttf", 64)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), letter, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((size - tw) / 2, (size - th) / 2 - 4), letter, fill="white", font=font)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, "PNG")
        return str(out_path)
    except Exception:
        return ""


def _default_push_template() -> str:
    return (
        "设备：{device}\n"
        "【{app}】\n"
        "标题：{title}\n"
        "内容：{msg}\n"
        "时间：{date}\n"
        "电量：{battery}"
    )


# 推送模板可用变量（SMS Forwarder 风格，可重复插入）
PUSH_TEMPLATE_VARS: List[Tuple[str, str]] = [
    ("device", "设备名（别名）"),
    ("device_mac", "BLE 地址"),
    ("app", "应用名（映射后）"),
    ("app_id", "Bundle ID"),
    ("title", "标题"),
    ("msg", "内容"),
    ("date", "通知时间（格式化）"),
    ("date_raw", "通知时间（原始）"),
    ("battery", "电量"),
    ("codes", "验证码"),
    ("receive_time", "接收时间"),
]

PUSH_TEMPLATE_PRESETS: Dict[str, str] = {
    "default": _default_push_template(),
    "simple": "【{app}】\n标题：{title}\n内容：{msg}",
    "detail": (
        "设备：{device}\n"
        "地址：{device_mac}\n"
        "应用：{app} ({app_id})\n"
        "标题：{title}\n"
        "内容：{msg}\n"
        "时间：{date}\n"
        "电量：{battery}\n"
        "验证码：{codes}\n"
        "接收：{receive_time}"
    ),
}


def format_ancs_date(date_str: str) -> str:
    """20260904T170513 -> 2026年9月4日17:05:13"""
    s = (date_str or "").strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$", s)
    if not m:
        return s
    y, mo, d, h, mi, se = m.groups()
    return f"{int(y)}年{int(mo)}月{int(d)}日{h}:{mi}:{se}"


def build_template_context(payload: dict, cfg: Optional["BridgeConfig"] = None) -> Dict[str, str]:
    device_raw = payload.get("device") or ""
    app_id = payload.get("app") or ""
    bat = payload.get("battery")
    bat_text = f"{bat}%" if isinstance(bat, int) else ""
    date_raw = payload.get("date") or ""
    ts = payload.get("ts") or time.time()
    return {
        "device": get_device_display_name(device_raw, cfg),
        "device_mac": device_raw,
        "app": get_app_display_name(app_id, cfg),
        "app_id": app_id,
        "title": payload.get("title") or "",
        "msg": payload.get("msg") or "",
        "date": format_ancs_date(date_raw),
        "date_raw": date_raw,
        "battery": bat_text,
        "codes": " ".join(payload.get("codes") or []),
        "receive_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
    }


def render_push_template(template: str, payload: dict, cfg: Optional["BridgeConfig"] = None) -> str:
    """按模板替换 {变量}，支持同一变量多次出现。"""
    tpl = template if template is not None else _default_push_template()
    if not tpl.strip():
        tpl = _default_push_template()
    ctx = build_template_context(payload, cfg)
    out = tpl
    for key, val in ctx.items():
        out = out.replace("{" + key + "}", val)
    return out


def _build_webhook_content(app_name: str, title: str, msg: str) -> str:
    return f"【{app_name}】\n标题：{title}\n内容：{msg}"


def _is_valid_http_url(url: str) -> bool:
    url = (url or "").strip()
    return url.startswith("http://") or url.startswith("https://")


def send_dingtalk(
    webhook: str,
    secret: str,
    content_text: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """钉钉机器人标准 text 消息；读取 GUI 配置的 webhook/secret，失败不抛出。"""
    webhook = (webhook or "").strip()
    if not _is_valid_http_url(webhook):
        return
    try:
        send_dingtalk_text(webhook, secret or "", content_text)
    except Exception as e:
        msg = f"[DingTalk] failed: {e}"
        if log:
            log(msg)
        else:
            print(msg, flush=True)


def send_ntfy(
    url: str,
    content_text: str,
    title_text: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """ntfy.sh POST；title 走 query 参数以支持中文；失败不抛出。"""
    url = (url or "").strip()
    if not _is_valid_http_url(url):
        return
    try:
        sep = "&" if "?" in url else "?"
        post_url = f"{url}{sep}title={urllib.parse.quote(title_text or 'NekoLink')}"
        r = requests.post(
            post_url,
            data=content_text.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=10,
        )
        if r.status_code >= 400:
            msg = f"[ntfy] HTTP {r.status_code}: {r.text}"
            if log:
                log(msg)
            else:
                print(msg, flush=True)
    except Exception as e:
        msg = f"[ntfy] failed: {e}"
        if log:
            log(msg)
        else:
            print(msg, flush=True)


def _dispatch_webhooks(
    cfg: "BridgeConfig",
    content_text: str,
    title_text: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """按 GUI 开关并行发送 DingTalk / ntfy，单个失败不影响另一个。"""
    tasks: Dict[str, Callable[[], None]] = {}
    if cfg.enable_dingtalk:
        tasks["dingtalk"] = lambda: send_dingtalk(
            cfg.dingtalk_webhook, cfg.dingtalk_secret, content_text, log=log
        )
    if getattr(cfg, "enable_ntfy", False):
        tasks["ntfy"] = lambda: send_ntfy(
            getattr(cfg, "ntfy_url", ""), content_text, title_text, log=log
        )
    if not tasks:
        return
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                fut.result()
            except Exception as e:
                msg = f"[WEBHOOK:{name}] failed: {e}"
                if log:
                    log(msg)
                else:
                    print(msg, flush=True)


# -----------------------------
# UUIDs
# -----------------------------
ANCS_SERVICE = "7905f431-b5ce-4e99-a40f-4b1e122d00d0"
NOTIF_SRC = "9fbf120d-6301-42d9-8c58-25e699a21dbd"
CTRL_PT = "69d1d8f3-45e1-49a8-9821-9bbdfdaad9d9"
DATA_SRC = "22eac6e9-24d6-4bb5-be44-b36ace7c7bfb"

BATTERY_LEVEL_CHAR = "00002a19-0000-1000-8000-00805f9b34fb"

ATTR_APP_IDENTIFIER = 0
ATTR_TITLE = 1
ATTR_SUBTITLE = 2
ATTR_MESSAGE = 3
ATTR_DATE = 5


# -----------------------------
# Config location (portable-first, AppData fallback)
# -----------------------------
def _base_dir() -> Path:
    try:
        import sys
        if getattr(sys, "frozen", False):
            return Path(os.path.dirname(sys.executable)).resolve()
    except Exception:
        pass
    return Path(os.path.dirname(__file__)).resolve()


def _is_writable_dir(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        test = p / ".write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def get_config_path() -> str:
    """
    Rules:
      1) If config.json exists next to exe/script -> use it (portable)
      2) If dir not writable -> fallback to %APPDATA%\\NekoLink\\config.json
      3) Env NEKOLINK_PORTABLE=1 forces portable mode
    """
    base = _base_dir()
    portable = base / "config.json"
    force_portable = os.getenv("NEKOLINK_PORTABLE", "0").strip() == "1"

    if force_portable or portable.exists():
        if _is_writable_dir(base):
            return str(portable)

    appdata = Path(os.getenv("APPDATA", str(Path.home())))
    cfg_dir = appdata / "NekoLink"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return str(cfg_dir / "config.json")


def load_config(path: str) -> "BridgeConfig":
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        # 兼容旧字段 privacy_hide_* → privacy_show_*
        if "privacy_show_title" not in d and "privacy_hide_title" in d:
            d["privacy_show_title"] = not bool(d.get("privacy_hide_title"))
        if "privacy_show_msg" not in d and "privacy_hide_msg" in d:
            d["privacy_show_msg"] = not bool(d.get("privacy_hide_msg"))
        fields = {f.name for f in dataclasses.fields(BridgeConfig)}
        filtered = {k: v for k, v in d.items() if k in fields}
        return BridgeConfig(**filtered)
    except Exception:
        return BridgeConfig()


def save_config(path: str, cfg: "BridgeConfig"):
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(str(p), "w", encoding="utf-8") as f:
        json.dump(dataclasses.asdict(cfg), f, ensure_ascii=False, indent=2)


# -----------------------------
# Config
# -----------------------------
@dataclass
class BridgeConfig:
    # UI (NEW) - persisted language: "zh" | "en" | "ja"
    ui_lang: str = "zh"

    # devices
    ble_addresses: List[str] = field(default_factory=list)
    device_aliases: Dict[str, str] = field(default_factory=dict)
    auto_pick_heart_rate: bool = False

    # app display / webhook filter
    app_bundle_map: Dict[str, str] = field(default_factory=_default_app_bundle_map)
    app_icon_map: Dict[str, str] = field(default_factory=dict)
    block_bundle: List[str] = field(default_factory=lambda: ["com.alibaba.DingTalkTalk"])

    # telegram
    enable_telegram: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # email
    enable_email: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    email_to: str = ""
    email_from: str = ""

    # dingtalk
    enable_dingtalk: bool = False
    dingtalk_webhook: str = ""
    dingtalk_secret: str = ""

    # ntfy
    enable_ntfy: bool = False
    ntfy_url: str = ""

    # gotify
    enable_gotify: bool = False
    gotify_url: str = ""
    gotify_token: str = ""
    gotify_priority: int = 5

    # behavior
    dedup_seconds: int = 8

    # filter
    block_keywords: List[str] = field(default_factory=list)
    block_case_insensitive: bool = True

    # code
    enable_code_highlight: bool = True
    code_regex: str = r"\b\d{4,8}\b"
    code_send_separately: bool = True
    code_separate_prefix: str = "🔑 Code"

    # history
    history_limit: int = 300

    # autostart
    autostart_enabled: bool = False

    # misc
    show_battery_in_message: bool = True
    enable_windows_toast: bool = True
    popup_position: str = "bottom_right"
    notification_width: int = 420
    notification_font_size: int = 8
    privacy_show_title: bool = True
    privacy_show_msg: bool = True

    # push template (DingTalk / ntfy)
    push_template: str = field(default_factory=_default_push_template)


# -----------------------------
# Destinations
# -----------------------------
def send_telegram(token: str, chat_id: str, text: str, timeout: int = 10):
    if not token or not chat_id:
        raise ValueError("Missing Telegram token/chat_id")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if not j.get("ok", False):
        raise RuntimeError(str(j))


def send_email(cfg: BridgeConfig, subject: str, body: str):
    import smtplib
    from email.mime.text import MIMEText

    if not cfg.smtp_host or not cfg.smtp_user or not cfg.smtp_pass:
        raise ValueError("Missing SMTP settings")
    if not cfg.email_to or not cfg.email_from:
        raise ValueError("Missing email_to/email_from")

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg.email_from
    msg["To"] = cfg.email_to

    server = smtplib.SMTP(cfg.smtp_host, int(cfg.smtp_port), timeout=10)
    server.ehlo()
    server.starttls()
    server.login(cfg.smtp_user, cfg.smtp_pass)
    server.send_message(msg)
    server.quit()


def _dingtalk_signed_url(webhook: str, secret: str) -> str:
    webhook = (webhook or "").strip()
    if not webhook:
        raise ValueError("Missing DingTalk webhook")

    secret = (secret or "").strip()
    if not secret:
        return webhook

    timestamp = str(int(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"

    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"{webhook}&timestamp={timestamp}&sign={sign}"


def send_dingtalk_text(webhook: str, secret: str, text: str, timeout: int = 10):
    url = _dingtalk_signed_url(webhook, secret)
    data = {"msgtype": "text", "text": {"content": text}}
    r = requests.post(url, json=data, timeout=timeout)

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")

    try:
        j = r.json()
    except Exception:
        raise RuntimeError(f"Bad response: {r.text}")

    if j.get("errcode", 0) != 0:
        raise RuntimeError(str(j))


def send_gotify(gotify_url: str, token: str, title: str, message: str, priority: int = 5, timeout: int = 10):
    """
    FIX: Use JSON payload (more compatible). Also surface response body when failed.
    """
    gotify_url = (gotify_url or "").strip()
    token = (token or "").strip()
    if not gotify_url or not token:
        raise ValueError("Missing Gotify url/token")

    base = gotify_url.rstrip("/")
    url = f"{base}/message?token={token}"
    payload = {"title": title, "message": message, "priority": int(priority)}

    r = requests.post(url, json=payload, timeout=timeout)
    if r.status_code >= 400:
        # raise but keep body for debugging
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    # gotify normally returns JSON; ignore content here


# -----------------------------
# Helpers
# -----------------------------
def _now_ts() -> float:
    return time.time()


def _contains_block_keyword(text: str, keywords: List[str], case_insensitive: bool) -> bool:
    if not keywords:
        return False
    hay = text or ""
    if case_insensitive:
        hay = hay.lower()
        kws = [k.lower() for k in keywords if k]
    else:
        kws = [k for k in keywords if k]
    for k in kws:
        if k and k in hay:
            return True
    return False


def _extract_codes(text: str, regex: str) -> List[str]:
    try:
        return re.findall(regex, text or "")
    except Exception:
        return []


def _format_message(payload: dict, cfg: BridgeConfig) -> str:
    lines = []
    lines.append("📲 iPhone 通知")
    if payload.get("device"):
        lines.append(f"Device: {payload.get('device')}")
    if cfg.show_battery_in_message:
        bat = payload.get("battery")
        if isinstance(bat, int):
            lines.append(f"Battery: {bat}%")
    if payload.get("app"):
        lines.append(f"App: {payload.get('app')}")
    if payload.get("title"):
        lines.append(f"Title: {payload.get('title')}")
    if payload.get("msg"):
        lines.append(f"Msg: {payload.get('msg')}")
    if payload.get("date"):
        lines.append(f"Date: {payload.get('date')}")
    return "\n".join(lines)


# -----------------------------
# ANCS Session
# -----------------------------
class _ANCSSession:
    def __init__(
        self,
        addr: str,
        cfg: BridgeConfig,
        log: Callable[[str], None],
        on_payload: Callable[[dict], None],
    ):
        self.addr = addr
        self.cfg = cfg
        self.log = log
        self.on_payload = on_payload

        self.client: Optional[BleakClient] = None
        self._stop = asyncio.Event()

        self._ds_buf: bytearray = bytearray()
        self._await_uid: Optional[int] = None
        self._last_battery_read: float = 0.0
        self._battery_cache: Optional[int] = None

    async def stop(self):
        self._stop.set()
        try:
            if self.client and self.client.is_connected:
                await self.client.disconnect()
        except Exception:
            pass

    async def run(self):
        while not self._stop.is_set():
            try:
                await self._connect_and_listen()
            except Exception as e:
                self.log(f"[{self.addr}] session error: {e}")
            await asyncio.sleep(1.5)

    async def _connect_and_listen(self):
        self.log(f"[{self.addr}] connecting...")
        async with BleakClient(self.addr) as client:
            self.client = client
            self.log(f"[{self.addr}] connected={client.is_connected}")

            await client.start_notify(NOTIF_SRC, self._on_notif_src)
            await client.start_notify(DATA_SRC, self._on_data_src)

            while client.is_connected and not self._stop.is_set():
                await asyncio.sleep(0.25)

            try:
                await client.stop_notify(NOTIF_SRC)
            except Exception:
                pass
            try:
                await client.stop_notify(DATA_SRC)
            except Exception:
                pass

    async def _read_battery(self) -> Optional[int]:
        if self._battery_cache is not None and (_now_ts() - self._last_battery_read) < 5.0:
            return self._battery_cache
        if not self.client or not self.client.is_connected:
            return self._battery_cache
        try:
            val = await self.client.read_gatt_char(BATTERY_LEVEL_CHAR)
            if val and len(val) >= 1:
                b = int(val[0])
                if 0 <= b <= 100:
                    self._battery_cache = b
                    self._last_battery_read = _now_ts()
                    return b
        except Exception:
            return self._battery_cache
        return self._battery_cache

    def _on_notif_src(self, _sender: int, data: bytearray):
        if not data or len(data) < 8:
            return
        event_id = data[0]
        uid = int.from_bytes(data[4:8], byteorder="little", signed=False)
        if event_id != 0:
            return
        self._await_uid = uid
        self._ds_buf = bytearray()
        asyncio.create_task(self._request_attributes(uid))

    async def _request_attributes(self, uid: int):
        if not self.client or not self.client.is_connected:
            return
        try:
            title_len = 64
            msg_len = 256

            payload = bytearray()
            payload.append(0x00)
            payload += uid.to_bytes(4, "little")

            payload.append(ATTR_APP_IDENTIFIER)

            payload.append(ATTR_TITLE)
            payload += int(title_len).to_bytes(2, "little")

            payload.append(ATTR_MESSAGE)
            payload += int(msg_len).to_bytes(2, "little")

            payload.append(ATTR_DATE)

            await self.client.write_gatt_char(CTRL_PT, payload, response=True)
            self.log(f"[{self.addr}] [CP] requested attributes for uid={uid}")
        except Exception as e:
            self.log(f"[{self.addr}] [CP] error: {e}")

    def _on_data_src(self, _sender: int, chunk: bytearray):
        if not chunk:
            return
        self._ds_buf += chunk
        self._try_parse_ds()

    def _try_parse_ds(self):
        while True:
            if len(self._ds_buf) < 5:
                return

            cmd_id = self._ds_buf[0]
            uid = int.from_bytes(self._ds_buf[1:5], "little", signed=False)
            if cmd_id != 0x00:
                self._ds_buf = bytearray()
                return

            pos = 5
            attrs: Dict[int, str] = {}
            while True:
                if len(self._ds_buf) < pos + 3:
                    return
                attr_id = self._ds_buf[pos]
                attr_len = int.from_bytes(self._ds_buf[pos + 1: pos + 3], "little", signed=False)
                pos += 3
                if len(self._ds_buf) < pos + attr_len:
                    return
                raw = bytes(self._ds_buf[pos: pos + attr_len])
                pos += attr_len
                try:
                    attrs[attr_id] = raw.decode("utf-8", errors="ignore")
                except Exception:
                    attrs[attr_id] = ""

                if pos >= len(self._ds_buf):
                    break

            self._ds_buf = bytearray()
            asyncio.create_task(self._emit_notification(uid, attrs))
            return

    async def _emit_notification(self, uid: int, attrs: Dict[int, str]):
        try:
            app = attrs.get(ATTR_APP_IDENTIFIER, "") or ""
            title = attrs.get(ATTR_TITLE, "") or ""
            msg = attrs.get(ATTR_MESSAGE, "") or ""
            date = attrs.get(ATTR_DATE, "") or ""

            merged_text = "\n".join([app, title, msg, date]).strip()
            if _contains_block_keyword(merged_text, self.cfg.block_keywords, self.cfg.block_case_insensitive):
                self.log(f"[{self.addr}] [FILTER] blocked")
                return

            bat = await self._read_battery()

            codes: List[str] = []
            if self.cfg.enable_code_highlight:
                codes = _extract_codes(merged_text, self.cfg.code_regex)

            payload = {
                "ts": _now_ts(),
                "uid": uid,
                "device": self.addr,
                "battery": bat,
                "app": app,
                "title": title,
                "msg": msg,
                "date": date,
                "codes": codes,
            }
            self.on_payload(payload)

        except Exception as e:
            self.log(f"[{self.addr}] emit error: {e}")


# -----------------------------
# BridgeManager
# -----------------------------
class BridgeManager:
    def __init__(
        self,
        cfg: BridgeConfig,
        log_func: Callable[[str], None],
        on_notification: Callable[[dict], None],
        on_desktop_popup: Optional[Callable[..., None]] = None,
    ):
        self.cfg = cfg
        self.log = log_func
        self.on_notification = on_notification
        self.on_desktop_popup = on_desktop_popup

        self._threads: Dict[str, threading.Thread] = {}
        self._loops: Dict[str, asyncio.AbstractEventLoop] = {}
        self._sessions: Dict[str, _ANCSSession] = {}

        self._dedup: Dict[str, float] = {}
        self._lock = threading.Lock()

    async def scan_heart_rate(self, timeout: int = 8) -> List[Tuple[str, str, int]]:
        devices = await BleakScanner.discover(timeout=timeout)
        out: List[Tuple[str, str, int]] = []
        for d in devices:
            name = (d.name or "").strip() or "(no name)"
            addr = d.address
            rssi = getattr(d, "rssi", None)
            if rssi is None:
                rssi = -999
            if "heart" in name.lower() or "rate" in name.lower():
                out.append((name, addr, int(rssi)))
        if not out:
            for d in devices:
                name = (d.name or "").strip() or "(no name)"
                addr = d.address
                rssi = getattr(d, "rssi", None)
                if rssi is None:
                    rssi = -999
                out.append((name, addr, int(rssi)))
        out.sort(key=lambda x: x[2], reverse=True)
        return out

    def start_all(self, addrs: List[str]):
        addrs = [a.strip() for a in (addrs or []) if a.strip()]
        if not addrs:
            return
        for addr in addrs:
            if addr in self._threads and self._threads[addr].is_alive():
                continue
            self._start_one(addr)

    def stop_all(self):
        for addr in list(self._threads.keys()):
            self._stop_one(addr)

    def _start_one(self, addr: str):
        def _runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loops[addr] = loop

            session = _ANCSSession(addr, self.cfg, self.log, self._on_payload_internal)
            self._sessions[addr] = session

            async def _main():
                await session.run()

            try:
                loop.run_until_complete(_main())
            except Exception as e:
                self.log(f"[{addr}] loop error: {e}")
            finally:
                try:
                    loop.stop()
                except Exception:
                    pass
                try:
                    loop.close()
                except Exception:
                    pass

        t = threading.Thread(target=_runner, daemon=True)
        self._threads[addr] = t
        t.start()
        self.log(f"[MANAGER] started {addr}")

    def _stop_one(self, addr: str):
        try:
            loop = self._loops.get(addr)
            session = self._sessions.get(addr)
            if loop and session:
                asyncio.run_coroutine_threadsafe(session.stop(), loop)
        except Exception:
            pass
        self.log(f"[MANAGER] stopping {addr}")

    def _dedup_ok(self, payload: dict) -> bool:
        window = int(getattr(self.cfg, "dedup_seconds", 8) or 8)
        key = f"{payload.get('device')}|{payload.get('app')}|{payload.get('title')}|{payload.get('msg')}|{payload.get('date')}"
        now = _now_ts()
        with self._lock:
            last = self._dedup.get(key)
            if last is not None and (now - last) < window:
                return False
            self._dedup[key] = now
        return True

    def _on_payload_internal(self, payload: dict):
        if not self._dedup_ok(payload):
            return

        if not payload.get("notif_id"):
            payload["notif_id"] = f"nk-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

        try:
            self._forward(payload)
        except Exception as e:
            self.log(f"[FORWARD] error: {e}")

        try:
            self._forward_webhooks(payload)
        except Exception as e:
            self.log(f"[WEBHOOK] error: {e}")

        try:
            self.on_notification(payload)
        except Exception:
            pass

    def _forward_webhooks(self, payload: dict) -> None:
        """精简模板转发至 GUI 中启用的 DingTalk / ntfy；block_bundle 内应用跳过。"""
        app_id = payload.get("app") or ""
        if is_blocked_bundle(app_id, self.cfg):
            return

        app_name = get_app_display_name(app_id, self.cfg)
        template = getattr(self.cfg, "push_template", "") or _default_push_template()
        content_text = render_push_template(template, payload, self.cfg)
        _dispatch_webhooks(self.cfg, content_text, app_name, log=self.log)

    def _forward(self, payload: dict):
        cfg = self.cfg
        text = _format_message(payload, cfg)

        if cfg.enable_windows_toast:
            try:
                app_id = payload.get("app") or ""
                app_name = get_app_display_name(app_id, cfg)
                notif_title = payload.get("title") or ""
                notif_msg = payload.get("msg") or ""
                icon_path = resolve_app_icon(app_id, app_name, cfg)
                notif_id = payload.get("notif_id") or ""
                template = getattr(cfg, "push_template", "") or _default_push_template()
                body_text = render_push_template(template, payload, cfg)
                if self.on_desktop_popup is not None:
                    self.on_desktop_popup(
                        app_name,
                        notif_title,
                        notif_msg,
                        icon_path=icon_path,
                        notif_id=notif_id,
                        body_text=body_text,
                    )
                elif show_notification_toast is not None:
                    show_notification_toast(
                        app_name,
                        notif_title,
                        notif_msg,
                        icon_path=icon_path,
                        log=self.log,
                    )
                elif show_toast is not None:
                    show_toast(app_name, _build_webhook_content(app_name, notif_title, notif_msg), log=self.log)
            except Exception as e:
                self.log(f"[TOAST] failed: {e}")

        if cfg.enable_telegram:
            try:
                send_telegram(cfg.telegram_bot_token, cfg.telegram_chat_id, text)
            except Exception as e:
                self.log(f"[TG] failed: {e}")

        if cfg.enable_gotify:
            try:
                send_gotify(cfg.gotify_url, cfg.gotify_token, "NekoLink", text, priority=cfg.gotify_priority)
            except Exception as e:
                self.log(f"[GOTIFY] failed: {e}")

        if cfg.enable_email:
            try:
                send_email(cfg, "NekoLink Notification", text)
            except Exception as e:
                self.log(f"[MAIL] failed: {e}")

        if cfg.enable_code_highlight and cfg.code_send_separately:
            codes = payload.get("codes") or []
            if codes:
                code_text = f"{cfg.code_separate_prefix}: " + " ".join(codes)

                if cfg.enable_telegram:
                    try:
                        send_telegram(cfg.telegram_bot_token, cfg.telegram_chat_id, code_text)
                    except Exception as e:
                        self.log(f"[TG-code] failed: {e}")

                if cfg.enable_dingtalk:
                    try:
                        send_dingtalk_text(cfg.dingtalk_webhook, cfg.dingtalk_secret, code_text)
                    except Exception as e:
                        self.log(f"[DT-code] failed: {e}")

                if cfg.enable_gotify:
                    try:
                        send_gotify(
                            cfg.gotify_url,
                            cfg.gotify_token,
                            "NekoLink Code",
                            code_text,
                            priority=max(7, int(cfg.gotify_priority)),
                        )
                    except Exception as e:
                        self.log(f"[GOTIFY-code] failed: {e}")

                if cfg.enable_email:
                    try:
                        send_email(cfg, "NekoLink Code", code_text)
                    except Exception as e:
                        self.log(f"[MAIL-code] failed: {e}")


# -----------------------------
# Standalone CLI entry
# -----------------------------
if __name__ == "__main__":
    def _cli_log(msg: str) -> None:
        print(msg, flush=True)

    def _cli_on_notification(payload: dict) -> None:
        device = payload.get("device") or ""
        device_name = get_device_display_name(device, _cfg)
        app_id = payload.get("app") or ""
        app_name = get_app_display_name(app_id, _cfg)
        bat = payload.get("battery")
        bat_text = f"{bat}%" if isinstance(bat, int) else "--"
        _cli_log(
            f"[通知] 设备={device_name} | 电量={bat_text} | 应用={app_name}\n"
            f"  标题: {payload.get('title') or ''}\n"
            f"  内容: {payload.get('msg') or ''}"
        )

    _cfg_path = get_config_path()
    _cfg = load_config(_cfg_path)
    _cli_log(f"NekoLink ANCS Bridge (config: {_cfg_path})")

    _addrs = list(_cfg.ble_addresses or [])
    if not _addrs:
        _cli_log("错误: 请在 config.json 的 ble_addresses 中填入 iPhone 的 BLE 地址")
        raise SystemExit(1)

    _manager = BridgeManager(_cfg, _cli_log, _cli_on_notification)
    _manager.start_all(_addrs)
    _cli_log(f"已启动监听: {', '.join(_addrs)}（Ctrl+C 退出）")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _cli_log("正在停止...")
        _manager.stop_all()