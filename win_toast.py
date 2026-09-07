# win_toast.py
# -*- coding: utf-8 -*-
"""Windows 10/11 右下角 Toast 通知（类似 Telegram 桌面推送）。"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
import winreg
from pathlib import Path
from typing import Callable, Optional

_APP_ID = "NekoLink"
_TOAST_GROUP = "NekoLinkAlerts"
_MAX_TITLE = 120
_MAX_MSG = 500
_registered = False
_app_script_path = ""


def _set_app_script_path(path: str) -> None:
    global _app_script_path
    if path:
        _app_script_path = os.path.abspath(path)


def _truncate(s: str, limit: int) -> str:
    s = (s or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _log(log: Optional[Callable[[str], None]], msg: str) -> None:
    if log:
        log(msg)
    else:
        print(msg, flush=True)


def _default_icon_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    for name in ("icon.ico", "icon.png"):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""


def _pythonw_path() -> str:
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pw = exe[:-10] + "pythonw.exe"
        if os.path.isfile(pw):
            return pw
    if exe.lower().endswith("pythonw.exe"):
        return exe
    return exe


def _start_menu_lnk() -> str:
    appdata = os.getenv("APPDATA", "")
    return os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\NekoLink.lnk")


def _ensure_notification_settings() -> None:
    """写入通知权限注册表，确保允许横幅 + 通知中心。"""
    key_path = rf"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\{_APP_ID}"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "Enabled", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ShowInActionCenter", 0, winreg.REG_DWORD, 1)
            try:
                winreg.SetValueEx(key, "ShowNotificationBanners", 0, winreg.REG_DWORD, 1)
            except OSError:
                pass
    except OSError:
        pass


def register_windows_notifications(
    app_script_path: str,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    为 py 直接启动创建「开始菜单快捷方式 + AppUserModelID」，
    使 NekoLink 出现在 Windows 通知设置里，并正常弹出桌面横幅。
    """
    global _registered
    if _registered:
        return True

    app_script_path = os.path.abspath(app_script_path)
    _set_app_script_path(app_script_path)
    work_dir = os.path.dirname(app_script_path)
    lnk_path = _start_menu_lnk()
    target = _pythonw_path()
    args = f'"{app_script_path}"'
    icon = _default_icon_path()

    try:
        import pythoncom
        from win32com.propsys import propsys
        from win32com.shell import shell as sh

        os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
        link = pythoncom.CoCreateInstance(
            sh.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, sh.IID_IShellLink
        )
        link.SetPath(target)
        link.SetArguments(args)
        link.SetWorkingDirectory(work_dir)
        link.SetDescription("NekoLink iPhone Notification Forwarder")
        if icon:
            link.SetIconLocation(icon, 0)

        store = link.QueryInterface(propsys.IID_IPropertyStore)
        key = propsys.PSGetPropertyKeyFromName("System.AppUserModel.ID")
        store.SetValue(key, propsys.PROPVARIANTType(_APP_ID))
        store.Commit()

        pf = link.QueryInterface(pythoncom.IID_IPersistFile)
        pf.Save(lnk_path, 1)

        _ensure_notification_settings()
        _registered = True
        _log(log, f"[TOAST] registered AUMID={_APP_ID}")
        return True
    except ImportError:
        _log(log, "[TOAST] pywin32 not installed, run: pip install pywin32")
        return False
    except Exception as e:
        _log(log, f"[TOAST] register failed: {e}")
        return False


def ensure_toast_ready(
    app_script_path: str = "",
    log: Optional[Callable[[str], None]] = None,
) -> None:
    if not app_script_path:
        app_script_path = os.path.join(os.path.dirname(__file__), "app_gui.py")
    register_windows_notifications(app_script_path, log=log)


def show_notification_toast(
    app_name: str,
    title: str,
    msg: str,
    icon_path: str = "",
    log: Optional[Callable[[str], None]] = None,
) -> None:
    ensure_toast_ready(_app_script_path, log=log)
    app_name = _truncate(app_name or "通知", 40)
    title = _truncate(title, _MAX_TITLE)
    msg = _truncate(msg, _MAX_MSG)
    icon = (icon_path or "").strip() or _default_icon_path()
    unique = f"nk-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    # 每条通知独立 group，避免 Win11 合并后只进通知中心、不弹横幅
    group = f"{_TOAST_GROUP}-{unique}"

    threading.Thread(
        target=_show_toast_safe,
        args=(app_name, title, msg),
        kwargs={"icon_path": icon, "unique_id": unique, "group": group, "log": log},
        daemon=True,
    ).start()


def show_toast(title: str, body: str, app_id: str = _APP_ID, log: Optional[Callable[[str], None]] = None) -> None:
    lines = body.split("\n", 1)
    sub = lines[0] if lines else ""
    rest = lines[1] if len(lines) > 1 else ""
    show_notification_toast(title, sub, rest, log=log)


def test_desktop_toast(log: Optional[Callable[[str], None]] = None) -> bool:
    ensure_toast_ready(_app_script_path, log=log)
    ok = False
    uid = f"test-{uuid.uuid4().hex[:8]}"

    def _run():
        nonlocal ok
        ok = _show_toast_safe(
            "NekoLink",
            "桌面弹窗测试",
            "✅ 请看屏幕右下角横幅。\n若只在通知中心出现，请关闭专注助手。",
            icon_path=_default_icon_path(),
            unique_id=uid,
            group=f"{_TOAST_GROUP}-{uid}",
            log=log,
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=8)
    return ok


def _show_toast_safe(
    app_name: str,
    title: str,
    msg: str,
    icon_path: str = "",
    unique_id: str = "",
    group: str = "",
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    uid = unique_id or uuid.uuid4().hex
    grp = group or f"{_TOAST_GROUP}-{uid}"
    # winotify 对 py 直接启动时横幅成功率更高，优先尝试
    if _show_via_winotify(app_name, title, msg, icon_path, log):
        return True
    if _show_via_powershell(app_name, title, msg, icon_path, uid, grp, log):
        return True
    if _show_via_winrt(app_name, title, msg, icon_path, uid, grp, log):
        return True
    _log(log, "[TOAST] all methods failed")
    return False


def _cdata(s: str) -> str:
    return (s or "").replace("]]>", "]]]]><![CDATA[>")


def _build_toast_xml(app_name: str, title: str, msg: str, icon_path: str) -> str:
    icon_xml = ""
    if icon_path and os.path.isfile(icon_path):
        uri = Path(icon_path).resolve().as_uri()
        icon_xml = f'      <image placement="appLogoOverride" hint-crop="circle" src="{uri}"/>\n'

    parts = []
    if app_name:
        parts.append(f'      <text hint-maxLines="1"><![CDATA[{_cdata(app_name)}]]></text>')
    if title:
        parts.append(f'      <text hint-maxLines="2"><![CDATA[{_cdata(title)}]]></text>')
    if msg:
        parts.append(f'      <text hint-style="body" hint-maxLines="8"><![CDATA[{_cdata(msg)}]]></text>')
    if not parts:
        parts.append('      <text hint-maxLines="2"><![CDATA[（无内容）]]></text>')

    texts = "\n".join(parts)
    return (
        '<toast activationType="foreground" duration="long" scenario="reminder">\n'
        "  <visual>\n"
        '    <binding template="ToastGeneric">\n'
        f"{icon_xml}"
        f"{texts}\n"
        "    </binding>\n"
        "  </visual>\n"
        '  <audio src="ms-winsoundevent:Notification.Default"/>\n'
        "</toast>"
    )


def _show_via_powershell(
    app_name: str,
    title: str,
    msg: str,
    icon_path: str,
    unique_id: str,
    group: str,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    xml_content = _build_toast_xml(app_name, title, msg, icon_path)
    xml_path = Path(os.getenv("TEMP", ".")) / f"nekolink_toast_{unique_id}.xml"
    ps_path = Path(os.getenv("TEMP", ".")) / f"nekolink_toast_{unique_id}.ps1"
    try:
        xml_path.write_text(xml_content, encoding="utf-8-sig")
        xml_esc = str(xml_path.resolve()).replace("'", "''")
        tag_esc = unique_id.replace("'", "''")
        group_esc = group.replace("'", "''")
        app_esc = _APP_ID.replace("'", "''")
        ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.Load('{xml_esc}')
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$toast.Tag = '{tag_esc}'
$toast.Group = '{group_esc}'
try {{
  $toast.Priority = [Windows.UI.Notifications.ToastNotificationPriority]::High
}} catch {{ }}
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_esc}')
$notifier.Show($toast)
"""
        ps_path.write_text(ps_script, encoding="utf-8")
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        r = subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(ps_path)],
            capture_output=True,
            text=True,
            timeout=10,
            startupinfo=si,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            _log(log, f"[TOAST] powershell failed: {err}")
            return False
        return True
    except Exception as e:
        _log(log, f"[TOAST] powershell failed: {e}")
        return False
    finally:
        try:
            xml_path.unlink(missing_ok=True)
            ps_path.unlink(missing_ok=True)
        except Exception:
            pass


def _show_via_winrt(
    app_name: str,
    title: str,
    msg: str,
    icon_path: str,
    unique_id: str,
    group: str,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    try:
        from winrt.windows.ui.notifications import (
            ToastNotification,
            ToastNotificationManager,
            ToastNotificationPriority,
        )
        from winrt.windows.data.xml.dom import XmlDocument
    except Exception as e:
        _log(log, f"[TOAST] winrt import failed: {e}")
        return False
    try:
        xml = XmlDocument()
        xml.load_xml(_build_toast_xml(app_name, title, msg, icon_path))
        toast = ToastNotification(xml)
        toast.tag = unique_id
        toast.group = group
        try:
            toast.priority = ToastNotificationPriority.HIGH
        except Exception:
            pass
        notifier = ToastNotificationManager.create_toast_notifier(_APP_ID)
        notifier.show(toast)
        return True
    except Exception as e:
        _log(log, f"[TOAST] winrt failed: {e}")
        return False


def _show_via_winotify(
    app_name: str,
    title: str,
    msg: str,
    icon_path: str,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """兜底：winotify 通常能弹出桌面横幅。"""
    try:
        from winotify import Notification, audio
    except Exception as e:
        _log(log, f"[TOAST] winotify import failed: {e}")
        return False
    try:
        body = "\n".join(x for x in (title, msg) if x) or "（无内容）"
        icon = icon_path if icon_path and os.path.isfile(icon_path) else ""
        toast = Notification(
            app_id=_APP_ID,
            title=app_name,
            msg=body,
            icon=icon,
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        return True
    except Exception as e:
        _log(log, f"[TOAST] winotify failed: {e}")
        return False
