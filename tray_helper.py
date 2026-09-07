# tray_helper.py
# -*- coding: utf-8 -*-
import os
import threading
from PIL import Image
import pystray


class TrayController:
    def __init__(self, title, on_restore, on_exit, icon_path=None):
        self.title = title
        self.on_restore = on_restore
        self.on_exit = on_exit
        self.icon_path = icon_path

        self.icon = None
        self.thread = None

    # ----------------------------
    # Public API
    # ----------------------------

    def start(self):
        if self.thread and self.thread.is_alive():
            return

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass

    # ----------------------------
    # Internal
    # ----------------------------

    def _run(self):
        image = self._load_icon()

        menu = pystray.Menu(
            pystray.MenuItem("Restore", self._restore),
            pystray.MenuItem("Exit", self._exit)
        )

        self.icon = pystray.Icon(
            self.title,
            image,
            self.title,
            menu
        )

        # 关键：用默认 run，不搞私有 listener
        self.icon.run()

    def _restore(self, icon, item):
        try:
            self.on_restore()
        except Exception:
            pass

    def _exit(self, icon, item):
        try:
            self.on_exit()
        finally:
            icon.stop()

    def _load_icon(self):
        """加载托盘图标：支持 .ico/.png/.jpg；保留透明；缩放到 64（兼容 16/32/48 显示）。"""
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                img = Image.open(self.icon_path)
                # ICO 多尺寸时尽量选接近 64 的一帧
                try:
                    if getattr(img, "n_frames", 1) and img.n_frames > 1:
                        best = None
                        best_score = None
                        for i in range(img.n_frames):
                            img.seek(i)
                            frame = img.copy()
                            w, h = frame.size
                            score = abs(max(w, h) - 64)
                            if best_score is None or score < best_score:
                                best_score = score
                                best = frame
                        if best is not None:
                            img = best
                except Exception:
                    pass

                if img.mode not in ("RGBA", "LA"):
                    img = img.convert("RGBA")
                else:
                    img = img.convert("RGBA")

                # 等比缩放到最长边 64，再居中到 64x64 透明底
                img.thumbnail((64, 64), Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                ox = (64 - img.width) // 2
                oy = (64 - img.height) // 2
                canvas.paste(img, (ox, oy), img)
                return canvas
            except Exception:
                pass

        # fallback 简单图标
        from PIL import ImageDraw
        img = Image.new("RGBA", (64, 64), color=(40, 120, 200, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 18), "N", fill="white")
        return img
