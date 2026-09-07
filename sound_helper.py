# sound_helper.py
# -*- coding: utf-8 -*-
"""
通知提示音：仅播放 assets/sound/*.wav（不引入 pydub / ffmpeg）。

播放后端：
1. simpleaudio（优先）
2. Windows winmm waveOut（simpleaudio 不可用时，如 Python 3.14 无 wheel；仍只播 wav PCM）

音量：在本进程对 PCM 做缩放（simpleaudio 无 set_volume），可选 pycaw 对齐合成器会话。
"""
from __future__ import annotations

import array
import ctypes
import os
import struct
import sys
import threading
import time
import wave
from ctypes import wintypes
from pathlib import Path
from typing import Callable, List, Optional, Tuple

try:
    import audioop  # Python < 3.13
except ImportError:
    audioop = None  # type: ignore

DEFAULT_SOUND_ENABLE = True
DEFAULT_SOUND_VOLUME = 80
DEFAULT_SOUND_SELECTED_FILE = "notify.wav"
MIN_SOUND_VOLUME = 0
MAX_SOUND_VOLUME = 100

SOUND_DIR_REL = Path("assets") / "sound"

_simpleaudio = None
_AudioUtilities = None
_ISimpleAudioVolume = None
_SOUND_IMPORT_ERROR = ""
_BACKEND = ""  # "simpleaudio" | "winmm" | ""

try:
    import simpleaudio as _simpleaudio  # type: ignore
except Exception as e:
    _simpleaudio = None
    _SOUND_IMPORT_ERROR = f"simpleaudio: {e}"

try:
    import comtypes  # noqa: F401
    from pycaw.pycaw import AudioUtilities as _AudioUtilities  # type: ignore
    from pycaw.pycaw import ISimpleAudioVolume as _ISimpleAudioVolume  # type: ignore
except Exception as e:
    _AudioUtilities = None
    _ISimpleAudioVolume = None
    if _SOUND_IMPORT_ERROR:
        _SOUND_IMPORT_ERROR += f"; pycaw/comtypes: {e}"
    else:
        _SOUND_IMPORT_ERROR = f"pycaw/comtypes: {e}"

_WINMM_OK = False
_winmm = None
if sys.platform == "win32":
    try:
        _winmm = ctypes.WinDLL("winmm")
        _WINMM_OK = True
    except Exception as e:
        _WINMM_OK = False
        if _SOUND_IMPORT_ERROR:
            _SOUND_IMPORT_ERROR += f"; winmm: {e}"
        else:
            _SOUND_IMPORT_ERROR = f"winmm: {e}"

if _simpleaudio is not None:
    _BACKEND = "simpleaudio"
    SOUND_AVAILABLE = True
elif _WINMM_OK:
    # 仍只播放用户 wav，不做格式转换；保证无 simpleaudio 时也能验收
    _BACKEND = "winmm"
    SOUND_AVAILABLE = True
else:
    _BACKEND = ""
    SOUND_AVAILABLE = False

_runtime_config = {
    "sound_enable": DEFAULT_SOUND_ENABLE,
    "sound_volume": DEFAULT_SOUND_VOLUME,
    "sound_selected_file": DEFAULT_SOUND_SELECTED_FILE,
}

_active_plays: List[object] = []
_play_lock = threading.Lock()
_last_play_at = 0.0


def sound_deps_error() -> str:
    if SOUND_AVAILABLE:
        return ""
    return _SOUND_IMPORT_ERROR or "no audio backend"


def sound_backend() -> str:
    return _BACKEND


def normalize_sound_volume(n) -> int:
    try:
        v = int(float(str(n).strip()))
    except (TypeError, ValueError):
        return DEFAULT_SOUND_VOLUME
    return max(MIN_SOUND_VOLUME, min(MAX_SOUND_VOLUME, v))


def normalize_sound_selected_file(name) -> str:
    s = str(name or "").strip()
    if not s:
        return DEFAULT_SOUND_SELECTED_FILE
    # 只允许文件名，禁止路径穿越
    s = Path(s).name
    if not s.lower().endswith(".wav"):
        return DEFAULT_SOUND_SELECTED_FILE
    return s


def get_runtime_sound_config() -> dict:
    return dict(_runtime_config)


def update_runtime_sound_config(
    sound_enable: Optional[bool] = None,
    sound_volume: Optional[int] = None,
    sound_selected_file: Optional[str] = None,
) -> None:
    """由 UI / reload_runtime_config 调用，刷新内存中的提示音配置。"""
    if sound_enable is not None:
        _runtime_config["sound_enable"] = bool(sound_enable)
    if sound_volume is not None:
        _runtime_config["sound_volume"] = normalize_sound_volume(sound_volume)
    if sound_selected_file is not None:
        _runtime_config["sound_selected_file"] = normalize_sound_selected_file(
            sound_selected_file
        )


def app_base_dir() -> Path:
    return Path(__file__).resolve().parent


def sound_dir() -> Path:
    return app_base_dir() / SOUND_DIR_REL


def list_wav_filenames(log: Optional[Callable[[str], None]] = None) -> List[str]:
    """扫描 assets/sound/*.wav，返回文件名列表（已排序）。"""
    d = sound_dir()
    if not d.is_dir():
        _log(log, f"[Sound] 音效目录不存在: {d}")
        return []
    names: List[str] = []
    try:
        for p in d.iterdir():
            try:
                if p.is_file() and p.suffix.lower() == ".wav":
                    names.append(p.name)
            except Exception:
                continue
    except Exception as e:
        _log(log, f"[Sound] 扫描音效目录失败: {e}")
        return []
    names.sort(key=lambda x: x.lower())
    if not names:
        _log(log, f"[Sound] 音效目录无 wav 文件: {d}")
    return names


def resolve_sound_path(filename: str) -> Path:
    return sound_dir() / normalize_sound_selected_file(filename)


def _log(log: Optional[Callable[[str], None]], msg: str) -> None:
    if log is not None:
        try:
            log(msg)
            return
        except Exception:
            pass
    print(msg)


# ---- WAV 解析：PCM + MS-ADPCM(format=2) ----
_WAVE_FORMAT_PCM = 1
_WAVE_FORMAT_ADPCM = 2  # Microsoft ADPCM
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE

_MS_ADPCM_ADAPTATION = [
    230, 230, 230, 230, 307, 409, 512, 614,
    768, 614, 512, 409, 307, 230, 230, 230,
]


def _parse_wav_chunks(path: Path) -> Tuple[bytes, bytes]:
    """返回 (fmt_chunk_payload, data_payload)。"""
    raw = path.read_bytes()
    if len(raw) < 12 or raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    pos = 12
    fmt = b""
    data = b""
    while pos + 8 <= len(raw):
        cid = raw[pos : pos + 4]
        csize = int.from_bytes(raw[pos + 4 : pos + 8], "little")
        pos += 8
        payload = raw[pos : pos + csize]
        pos += csize
        if csize & 1:
            pos += 1  # word align
        if cid == b"fmt ":
            fmt = payload
        elif cid == b"data":
            data = payload
            break
    if not fmt or data is None:
        raise ValueError("missing fmt/data chunk")
    return fmt, data


def _decode_ms_adpcm_block(
    block: bytes,
    channels: int,
    samples_per_block: int,
    coefs: List[Tuple[int, int]],
) -> array.array:
    """解码单个 MS-ADPCM block -> 交错 int16 样本。"""
    if channels not in (1, 2):
        raise ValueError(f"unsupported ADPCM channels: {channels}")
    header_size = 7 * channels
    if len(block) < header_size:
        return array.array("h")

    predictors = [0] * channels
    deltas = [0] * channels
    sample1 = [0] * channels
    sample2 = [0] * channels
    off = 0
    for ch in range(channels):
        predictors[ch] = block[off]
        off += 1
    for ch in range(channels):
        deltas[ch] = int.from_bytes(block[off : off + 2], "little", signed=True)
        off += 2
    for ch in range(channels):
        sample1[ch] = int.from_bytes(block[off : off + 2], "little", signed=True)
        off += 2
    for ch in range(channels):
        sample2[ch] = int.from_bytes(block[off : off + 2], "little", signed=True)
        off += 2

    out = array.array("h")
    # 头里两样：先 samp2，再 samp1
    for ch in range(channels):
        out.append(sample2[ch])
    for ch in range(channels):
        out.append(sample1[ch])

    samples_done = 2
    nibble_bytes = block[header_size:]
    bi = 0

    def _one_nibble(ch: int, nibble: int) -> None:
        nonlocal sample1, sample2, deltas
        pred_idx = predictors[ch]
        if pred_idx >= len(coefs):
            pred_idx = 0
        coef1, coef2 = coefs[pred_idx]
        signed = nibble - 16 if (nibble & 0x8) else nibble
        pred = (sample1[ch] * coef1 + sample2[ch] * coef2) // 256
        sample = pred + signed * deltas[ch]
        if sample > 32767:
            sample = 32767
        elif sample < -32768:
            sample = -32768
        sample2[ch] = sample1[ch]
        sample1[ch] = sample
        deltas[ch] = (_MS_ADPCM_ADAPTATION[nibble & 0xF] * deltas[ch]) // 256
        if deltas[ch] < 16:
            deltas[ch] = 16
        out.append(sample)

    while samples_done < samples_per_block and bi < len(nibble_bytes):
        b = nibble_bytes[bi]
        bi += 1
        hi = (b >> 4) & 0xF
        lo = b & 0xF
        if channels == 1:
            _one_nibble(0, hi)
            samples_done += 1
            if samples_done >= samples_per_block:
                break
            _one_nibble(0, lo)
            samples_done += 1
        else:
            # stereo: 高半字节=左，低半字节=右
            _one_nibble(0, hi)
            _one_nibble(1, lo)
            samples_done += 1

    return out


def _load_ms_adpcm_wav(path: Path) -> Tuple[bytes, int, int, int]:
    fmt, data = _parse_wav_chunks(path)
    if len(fmt) < 16:
        raise ValueError("fmt chunk too short")
    (
        wFormatTag,
        nChannels,
        nSamplesPerSec,
        _avg,
        nBlockAlign,
        _bits,
    ) = struct.unpack_from("<HHIIHH", fmt, 0)
    if wFormatTag != _WAVE_FORMAT_ADPCM:
        raise ValueError(f"not MS-ADPCM: {wFormatTag}")
    if len(fmt) < 22:
        raise ValueError("MS-ADPCM fmt missing extra fields")
    _cb, samples_per_block, n_coef = struct.unpack_from("<HHH", fmt, 16)
    coefs: List[Tuple[int, int]] = []
    off = 22
    for _ in range(n_coef):
        if off + 4 > len(fmt):
            break
        c1, c2 = struct.unpack_from("<hh", fmt, off)
        coefs.append((c1, c2))
        off += 4
    if not coefs:
        coefs = [(256, 0), (512, -256), (0, 0), (192, 64), (240, 0), (460, -208), (392, -232)]

    pcm = array.array("h")
    pos = 0
    while pos < len(data):
        block = data[pos : pos + nBlockAlign]
        if len(block) < 7 * nChannels:
            break
        pos += nBlockAlign
        pcm.extend(
            _decode_ms_adpcm_block(block, nChannels, samples_per_block, coefs)
        )
    return pcm.tobytes(), nChannels, 2, nSamplesPerSec


def _load_pcm_from_wav(path: Path) -> Tuple[bytes, int, int, int]:
    """
    加载 wav 为可播放 PCM。
    支持：标准 PCM；Microsoft ADPCM(format=2，常见于旧 QQ 提示音)。
    """
    try:
        with wave.open(str(path), "rb") as wf:
            return (
                wf.readframes(wf.getnframes()),
                wf.getnchannels(),
                wf.getsampwidth(),
                wf.getframerate(),
            )
    except wave.Error as e:
        # unknown format: 2 → MS-ADPCM
        msg = str(e)
        if "unknown format" in msg or "2" in msg:
            return _load_ms_adpcm_wav(path)
        raise


def _play_via_winsound_file(path: Path) -> None:
    """系统解码播放（可播 ADPCM 等）；音量滑块对此路径不完全生效。"""
    import winsound

    winsound.PlaySound(
        str(path),
        winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
    )


def _scale_pcm(frames: bytes, sampwidth: int, volume: float) -> bytes:
    if volume >= 0.999:
        return frames
    if volume <= 0:
        return b"\x00" * len(frames)
    if audioop is not None:
        try:
            return audioop.mul(frames, sampwidth, volume)
        except Exception:
            pass
    try:
        if sampwidth == 2:
            samples = array.array("h")
            samples.frombytes(frames)
            for i in range(len(samples)):
                samples[i] = int(max(-32768, min(32767, samples[i] * volume)))
            return samples.tobytes()
        if sampwidth == 1:
            out = bytearray(len(frames))
            for i, b in enumerate(frames):
                centered = b - 128
                out[i] = int(max(0, min(255, centered * volume + 128)))
            return bytes(out)
    except Exception:
        pass
    return frames


def _apply_pycaw_session_volume(volume: float) -> bool:
    if _AudioUtilities is None or _ISimpleAudioVolume is None:
        return False
    try:
        pid = os.getpid()
        for session in _AudioUtilities.GetAllSessions():
            proc = session.Process
            if proc is None:
                continue
            try:
                if int(proc.pid) != pid:
                    continue
            except Exception:
                continue
            try:
                vol_iface = session._ctl.QueryInterface(_ISimpleAudioVolume)
                vol_iface.SetMasterVolume(max(0.0, min(1.0, float(volume))), None)
                return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _retain_play(play_obj) -> None:
    with _play_lock:
        _active_plays.append(play_obj)

    def _cleanup():
        try:
            if hasattr(play_obj, "wait_done"):
                play_obj.wait_done()
            elif hasattr(play_obj, "join"):
                play_obj.join()
        except Exception:
            pass
        with _play_lock:
            try:
                _active_plays.remove(play_obj)
            except ValueError:
                pass

    threading.Thread(target=_cleanup, daemon=True).start()


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.POINTER(ctypes.c_ulong)),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p),
    ]


WHDR_DONE = 0x00000001
WAVE_MAPPER = -1
WAVE_FORMAT_PCM = 1


def _play_via_winmm(
    frames: bytes,
    nchannels: int,
    sampwidth: int,
    framerate: int,
) -> None:
    if not _WINMM_OK or _winmm is None:
        raise RuntimeError("winmm unavailable")

    wfx = WAVEFORMATEX()
    wfx.wFormatTag = WAVE_FORMAT_PCM
    wfx.nChannels = int(nchannels)
    wfx.nSamplesPerSec = int(framerate)
    wfx.wBitsPerSample = int(sampwidth * 8)
    wfx.nBlockAlign = int(nchannels * sampwidth)
    wfx.nAvgBytesPerSec = int(framerate * wfx.nBlockAlign)
    wfx.cbSize = 0

    hwo = wintypes.HANDLE()
    err = _winmm.waveOutOpen(
        ctypes.byref(hwo),
        WAVE_MAPPER,
        ctypes.byref(wfx),
        0,
        0,
        0,
    )
    if err != 0:
        raise RuntimeError(f"waveOutOpen failed: {err}")

    buf = ctypes.create_string_buffer(frames, len(frames))
    hdr = WAVEHDR()
    hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
    hdr.dwBufferLength = len(frames)
    hdr.dwFlags = 0
    hdr.dwLoops = 0

    try:
        err = _winmm.waveOutPrepareHeader(hwo, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        if err != 0:
            raise RuntimeError(f"waveOutPrepareHeader failed: {err}")
        err = _winmm.waveOutWrite(hwo, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        if err != 0:
            raise RuntimeError(f"waveOutWrite failed: {err}")
        while not (hdr.dwFlags & WHDR_DONE):
            time.sleep(0.02)
        _winmm.waveOutUnprepareHeader(hwo, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
    finally:
        _winmm.waveOutClose(hwo)


def _play_pcm(
    frames: bytes,
    nchannels: int,
    sampwidth: int,
    framerate: int,
    vol: float,
) -> None:
    frames = _scale_pcm(frames, sampwidth, vol)
    if _BACKEND == "simpleaudio" and _simpleaudio is not None:
        wave_obj = _simpleaudio.WaveObject(frames, nchannels, sampwidth, framerate)
        play_obj = wave_obj.play()
        _retain_play(play_obj)
        for _ in range(15):
            if _apply_pycaw_session_volume(1.0):
                break
            time.sleep(0.02)
        return

    if _BACKEND == "winmm":
        _play_via_winmm(frames, nchannels, sampwidth, framerate)
        for _ in range(10):
            if _apply_pycaw_session_volume(1.0):
                break
            time.sleep(0.02)
        return

    raise RuntimeError("no audio backend")


def play_notify_wav(
    *,
    sound_enable: Optional[bool] = None,
    sound_volume: Optional[int] = None,
    sound_selected_file: Optional[str] = None,
    log: Optional[Callable[[str], None]] = None,
    base_dir: Optional[Path] = None,  # 兼容旧调用，忽略
) -> None:
    """
    去重后的新通知调用：读取内存 runtime_config，播放选中的 wav。
    simpleaudio 优先；不可用时回退 winmm（仍只播 wav，无格式转换）。
    """
    global _last_play_at
    _ = base_dir

    if (
        sound_enable is not None
        or sound_volume is not None
        or sound_selected_file is not None
    ):
        update_runtime_sound_config(
            sound_enable=sound_enable if sound_enable is not None else None,
            sound_volume=sound_volume if sound_volume is not None else None,
            sound_selected_file=sound_selected_file
            if sound_selected_file is not None
            else None,
        )

    enable = bool(_runtime_config.get("sound_enable", True))
    vol_percent = normalize_sound_volume(_runtime_config.get("sound_volume", 80))
    selected = normalize_sound_selected_file(
        _runtime_config.get("sound_selected_file", DEFAULT_SOUND_SELECTED_FILE)
    )
    _log(
        log,
        f"[Sound] sound_enable={enable}, vol={vol_percent}, "
        f"file={selected}, backend={_BACKEND}",
    )

    if not enable:
        _log(log, "[Sound] 已关闭提示音，跳过播放")
        return
    if not SOUND_AVAILABLE:
        _log(log, f"[Sound] 无可用后端，跳过: {sound_deps_error()}")
        return

    vol = max(0.0, min(100.0, float(vol_percent))) / 100.0
    if vol <= 0:
        _log(log, "[Sound] volume=0，跳过播放")
        return

    now = time.time()
    if now - _last_play_at < 0.15:
        return
    _last_play_at = now

    def _worker():
        try:
            sound_path = resolve_sound_path(selected)
            play_name = selected
            if not sound_path.is_file():
                _log(log, f"[Sound] 选中音效不存在，回退默认: {sound_path}")
                play_name = DEFAULT_SOUND_SELECTED_FILE
                sound_path = resolve_sound_path(DEFAULT_SOUND_SELECTED_FILE)
                if not sound_path.is_file():
                    _log(log, "[Sound] 默认音效缺失，取消播放")
                    return

            # 优先 simpleaudio.from_wave_file（仅 PCM）；音量需自缩放时走 PCM 路径
            if _BACKEND == "simpleaudio" and _simpleaudio is not None and vol >= 0.999:
                try:
                    wave_obj = _simpleaudio.WaveObject.from_wave_file(str(sound_path))
                    play_obj = wave_obj.play()
                    _retain_play(play_obj)
                    _log(log, f"[Sound] 播放音效:{play_name} 音量:{vol:.2f}")
                    for _ in range(15):
                        if _apply_pycaw_session_volume(1.0):
                            break
                        time.sleep(0.02)
                    return
                except Exception as e:
                    _log(log, f"[Sound] simpleaudio 直播失败，改 PCM 播放: {e}")

            try:
                frames, nchannels, sampwidth, framerate = _load_pcm_from_wav(sound_path)
                _play_pcm(frames, nchannels, sampwidth, framerate, vol)
                _log(log, f"[Sound] 播放音效:{play_name} 音量:{vol:.2f}")
            except Exception as e_pcm:
                # 仍失败：用 Windows 系统解码（兼容旧 QQ ADPCM 等）
                _log(log, f"[Sound] PCM 路径失败({e_pcm})，改用系统播放")
                if sys.platform != "win32":
                    raise
                _play_via_winsound_file(sound_path)
                _log(
                    log,
                    f"[Sound] 播放音效:{play_name} 音量:{vol:.2f} (系统播放，滑块可能不完全生效)",
                )
        except Exception as e:
            _log(log, f"[Sound] 播放异常: {e}")

    threading.Thread(target=_worker, daemon=True).start()
