"""DeskTimer —— 简约桌面定时器（时钟 / 秒表 / 倒计时）

一个悬浮在桌角的半透明小部件：
  - 时钟模式：显示 年月日 + 时:分:秒
  - 秒表模式：开始/暂停/继续/清零，精度 0.1 秒
  - 倒计时模式：预设快捷时长 + 自定义输入，到点声音提醒 + 闪烁变色 + 烟花绽放

用法:
    python main.py                     正常启动
    python main.py --smoke 3           启动 3 秒后自动退出（自测用）
    python main.py --fireworks-test 2  2 秒后触发一次烟花（自测用）
"""
import ctypes
import json
import math
import os
import sys
import time
import tkinter as tk
import winsound
from datetime import datetime

from themes import THEMES
from fireworks import Fireworks

APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

MODES = ("clock", "stopwatch", "countdown")
MODE_NAMES = {"clock": "时钟", "stopwatch": "秒表", "countdown": "倒计时"}
PRESETS = ((60, "1分"), (180, "3分"), (300, "5分"), (600, "10分"), (1500, "25分"))

FONT_UI = "Microsoft YaHei UI"
FONT_DIGIT = "Consolas"

_instance_mutex_handle = None  # 单实例互斥锁句柄（进程存活期间保持打开）


def fmt_time(seconds):
    """格式化秒数 -> 'MM:SS.d' 或 'H:MM:SS.d'"""
    total = max(0, int(round(seconds * 10)))
    h, rem = divmod(total, 36000)
    m, rem = divmod(rem, 600)
    s, d = divmod(rem, 10)
    if h:
        return f"{h}:{m:02d}:{s:02d}.{d}"
    return f"{m:02d}:{s:02d}.{d}"


def parse_duration(text):
    """解析 'MM:SS' / 'H:MM:SS' / '秒数'，返回秒数；失败返回 None。"""
    text = (text or "").strip().strip(":")
    if not text:
        return None
    try:
        nums = [int(p) for p in text.split(":") if p != ""]
    except ValueError:
        return None
    if not nums:
        return None
    total = 0
    for n in nums:
        total = total * 60 + n
    return total


class DeskTimer:
    def __init__(self, root, smoke=None, fireworks_test=None):
        self.root = root
        self.smoke = smoke
        self.fireworks_test = fireworks_test

        self.W, self.H = 380, 172
        self.cfg = self.load_config()
        self.theme_name = self.cfg.get("theme", "dark")
        self.mode = "clock"
        self.fw = None
        self._flash_job = None

        # 秒表状态
        self.sw_running = False
        self.sw_elapsed = 0.0
        self.sw_start = 0.0
        # 倒计时状态
        self.cd_running = False
        self.cd_total = 0.0
        self.cd_remaining = 0.0
        self.cd_finish_at = 0.0

        # ---- 窗口形态：无边框、置顶、半透明 ----
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.93)
        pos = self.cfg.get("pos")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = pos[0] if pos else sw - self.W - 48
        y = pos[1] if pos else 48
        root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        # ---- 背景画布（圆角面板，四角用透明键色挖空）----
        self.canvas = tk.Canvas(root, bg=THEMES[self.theme_name]["key"],
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # ---- 顶栏 ----
        self.mode_label = tk.Label(root, font=(FONT_UI, 10), anchor="w")
        self.switch_btn = tk.Button(root, text="⇄ 模式", cursor="hand2",
                                    command=self.switch_mode)
        self.switch_btn.place(x=self.W - 16, y=15, anchor="e")
        self.mode_label.place(x=16, y=15, anchor="w")

        # ---- 主体 ----
        self.time_label = tk.Label(root, font=(FONT_DIGIT, 42, "bold"))
        self.time_label.place(x=self.W / 2, y=66, anchor="center")
        self.sub_label = tk.Label(root, font=(FONT_UI, 10))
        self.sub_label.place(x=self.W / 2, y=102, anchor="center")

        # ---- 底部控制区 ----
        self.controls_frame = tk.Frame(root)
        self.controls_frame.place(x=0, y=self.H - 58, width=self.W, height=58)
        self.btn_main = None
        self.btn_reset = None
        self.cd_entry = None

        # ---- 右键菜单 ----
        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="切换主题（深色/浅色）", command=self.toggle_theme)
        self.menu.add_command(label="复位窗口位置", command=self.reset_pos)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit)

        # ---- 事件：拖拽 / 右键菜单 / 快捷键 ----
        for w in (root, self.canvas, self.mode_label, self.time_label, self.sub_label):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._drag)
            w.bind("<ButtonRelease-1>", self._end_drag)
            w.bind("<Button-3>", self._popup)
        root.bind("<space>", self._on_key_space)
        root.bind("<m>", self._on_key_m)
        root.bind("<r>", self._on_key_r)
        root.bind("<Escape>", lambda e: self.quit())

        self.apply_theme()
        self.set_mode("clock")
        self.tick()

        # 自测模式
        if self.fireworks_test:
            root.after(int(self.fireworks_test * 1000), self.show_fireworks)
        if self.smoke:
            root.after(1200, self._print_geo)
            root.after(int(self.smoke * 1000), self.quit)

    def _print_geo(self):
        """自测用：输出窗口真实几何信息。"""
        try:
            print(f"DBG geometry={self.root.winfo_x()},{self.root.winfo_y()} "
                  f"{self.root.winfo_width()}x{self.root.winfo_height()} "
                  f"mapped={self.root.winfo_ismapped()} "
                  f"screen={self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()} "
                  f"alpha={self.root.attributes('-alpha')}")
        except Exception as e:
            print(f"DBG error: {e}")

    # ================= 界面构建 =================
    def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
        """圆角矩形：用密集多边形近似（smooth=False），四角精确、无样条变形。

        圆角以外的区域保持透明键色 -> 真正的透明圆角效果。
        """
        steps = 12  # 每个角采样点数
        pts = []

        def arc(cx, cy, start_deg, end_deg):
            for i in range(steps + 1):
                ang = math.radians(start_deg + (end_deg - start_deg) * i / steps)
                pts.append(cx + r * math.cos(ang))
                pts.append(cy + r * math.sin(ang))

        # 依序：右上角、右下角、左下角、左上角（角度制，y 向下为正）
        arc(x2 - r, y1 + r, -90, 0)
        arc(x2 - r, y2 - r, 0, 90)
        arc(x1 + r, y2 - r, 90, 180)
        arc(x1 + r, y1 + r, 180, 270)
        return self.canvas.create_polygon(pts, smooth=False, **kw)

    def apply_theme(self):
        self.t = THEMES[self.theme_name]
        self.root.configure(bg=self.t["key"])
        # 关键：设置透明键色，画布上与键色一致的像素（圆角外区域）将完全透明
        self.root.attributes("-transparentcolor", self.t["key"])
        self.canvas.configure(bg=self.t["key"])
        self.canvas.delete("bg")
        # 圆角矩形贴合窗口边界：四角以外的区域保持透明键色 -> 真正的圆角效果
        self._rounded_rect(0, 0, self.W, self.H, 18,
                           fill=self.t["bg"], outline="", tags="bg")
        bg = self.t["bg"]
        self.mode_label.configure(bg=bg, fg=self.t["fg"])
        self.time_label.configure(bg=bg, fg=self.t["fg"])
        self.sub_label.configure(bg=bg, fg=self.t["fg_dim"])
        self.switch_btn.configure(
            bg=self.t["btn_bg"], fg=self.t["btn_fg"],
            activebackground=self.t["btn_hover"], activeforeground=self.t["btn_fg"],
            relief="flat", bd=0, padx=10, pady=2,
            font=(FONT_UI, 9), highlightthickness=0)
        self._build_controls()

    def _mk_button(self, parent, text, cmd):
        return tk.Button(
            parent, text=text, command=cmd, cursor="hand2",
            bg=self.t["btn_bg"], fg=self.t["btn_fg"],
            activebackground=self.t["btn_hover"], activeforeground=self.t["btn_fg"],
            relief="flat", bd=0, highlightthickness=0,
            font=(FONT_UI, 9), padx=10, pady=3)

    def _build_controls(self):
        for w in self.controls_frame.winfo_children():
            w.destroy()
        self.btn_main = None
        self.btn_reset = None
        self.cd_entry = None
        self.controls_frame.configure(bg=self.t["bg"])
        c = self.controls_frame

        if self.mode == "clock":
            tk.Label(c, text="右键菜单 · 空格开始/暂停 · M 切换 · R 重置",
                     bg=self.t["bg"], fg=self.t["fg_dim"],
                     font=(FONT_UI, 9)).pack(pady=12)
        elif self.mode == "stopwatch":
            self.btn_main = self._mk_button(c, "开始", self.toggle_stopwatch)
            self.btn_reset = self._mk_button(c, "清零", self.reset_stopwatch)
            self.btn_main.pack(side="left", padx=8, pady=13)
            self.btn_reset.pack(side="left", padx=8, pady=13)
        elif self.mode == "countdown":
            for i, (sec, label) in enumerate(PRESETS):
                b = self._mk_button(c, label, lambda s=sec: self.set_countdown(s))
                b.grid(row=0, column=i, padx=3, pady=(8, 0))
            self.cd_entry = tk.Entry(c, width=7, justify="center",
                                     font=(FONT_DIGIT, 11), relief="flat", bd=0,
                                     highlightthickness=0,
                                     bg=self.t["entry_bg"], fg=self.t["fg"],
                                     insertbackground=self.t["fg"])
            self.cd_entry.insert(0, "05:00")
            self.cd_entry.grid(row=0, column=5, padx=4, pady=(8, 0))
            self.cd_entry.bind("<Return>", lambda e: self._apply_entry(start=True))
            self.btn_main = self._mk_button(c, "开始", self.toggle_countdown)
            self.btn_main.grid(row=0, column=6, padx=4, pady=(8, 0))
            self.btn_reset = self._mk_button(c, "重置", self.reset_countdown)
            self.btn_reset.grid(row=1, column=0, columnspan=7, pady=(2, 4))
        self._refresh_buttons()

    def _refresh_buttons(self):
        if self.mode == "stopwatch" and self.btn_main:
            self.btn_main.config(text="暂停" if self.sw_running else "开始")
        elif self.mode == "countdown" and self.btn_main:
            self.btn_main.config(text="暂停" if self.cd_running else "开始")

    # ================= 模式切换 =================
    def switch_mode(self):
        idx = MODES.index(self.mode)
        self.set_mode(MODES[(idx + 1) % len(MODES)])

    def set_mode(self, mode):
        if self._flash_job:
            try:
                self.root.after_cancel(self._flash_job)
            except Exception:
                pass
            self._flash_job = None
        self.mode = mode
        self.mode_label.config(text=MODE_NAMES[mode])
        self.time_label.config(fg=self.t["fg"])
        self._build_controls()
        self._refresh_now()

    # ================= 主刷新循环 =================
    def tick(self):
        if self.mode == "clock":
            self._refresh_now()
        elif self.mode == "stopwatch":
            self._update_stopwatch()
        elif self.mode == "countdown":
            self._update_countdown()
        self.root.after(50, self.tick)

    def _refresh_now(self):
        now = datetime.now()
        if self.mode == "clock":
            self.time_label.config(text=now.strftime("%H:%M:%S"))
            week = "一二三四五六日"[now.weekday()]
            self.sub_label.config(text=f"{now.strftime('%Y-%m-%d')} · 星期{week}")
        elif self.mode == "stopwatch":
            self.time_label.config(text=fmt_time(self._sw_total()))
        elif self.mode == "countdown":
            self.time_label.config(text=fmt_time(self.cd_remaining))

    # ================= 秒表 =================
    def _sw_total(self):
        return self.sw_elapsed + (time.monotonic() - self.sw_start if self.sw_running else 0)

    def toggle_stopwatch(self):
        if self.sw_running:
            self.sw_elapsed += time.monotonic() - self.sw_start
            self.sw_running = False
        else:
            self.sw_start = time.monotonic()
            self.sw_running = True
        self._refresh_buttons()

    def reset_stopwatch(self):
        self.sw_running = False
        self.sw_elapsed = 0.0
        self._refresh_buttons()

    def _update_stopwatch(self):
        self.time_label.config(text=fmt_time(self._sw_total()))
        if self.sw_running:
            self.sub_label.config(text="计时中…")
        elif self.sw_elapsed > 0:
            self.sub_label.config(text="已暂停")
        else:
            self.sub_label.config(text="点击开始计时")

    # ================= 倒计时 =================
    def set_countdown(self, seconds):
        self.cd_running = False
        self.cd_total = float(seconds)
        self.cd_remaining = float(seconds)
        self._refresh_buttons()

    def toggle_countdown(self):
        if self.cd_running:
            self.cd_remaining = self.cd_finish_at - time.monotonic()
            self.cd_running = False
        else:
            if self.cd_remaining <= 0:
                return
            self.cd_finish_at = time.monotonic() + self.cd_remaining
            self.cd_running = True
        self._refresh_buttons()

    def reset_countdown(self):
        self.cd_running = False
        self.cd_remaining = self.cd_total
        self._refresh_buttons()

    def _apply_entry(self, start=False):
        secs = parse_duration(self.cd_entry.get())
        if not secs or secs <= 0:
            return
        self.set_countdown(secs)
        if start:
            self.toggle_countdown()

    def _update_countdown(self):
        if self.cd_running:
            self.cd_remaining = max(0.0, self.cd_finish_at - time.monotonic())
            if self.cd_remaining <= 0:
                self.cd_running = False
                self._refresh_buttons()
                self._finish_countdown()
        self.time_label.config(text=fmt_time(self.cd_remaining))
        if self.cd_total <= 0:
            self.sub_label.config(text="选择预设或输入 MM:SS")
        elif self.cd_running:
            self.sub_label.config(text="倒计时中…")
        elif self.cd_remaining <= 0:
            self.sub_label.config(text="时间到！")
        else:
            self.sub_label.config(
                text="已暂停" if self.cd_remaining < self.cd_total else "准备就绪")

    # ================= 到点提醒：声音 + 闪烁 + 烟花 =================
    def _finish_countdown(self):
        self._play_alarm()
        self._flash(10)
        self.show_fireworks()

    def _play_alarm(self):
        try:
            winsound.PlaySound("SystemExclamation",
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

    def _flash(self, n):
        if self._flash_job:
            try:
                self.root.after_cancel(self._flash_job)
            except Exception:
                pass
            self._flash_job = None
        if n <= 0:
            self.time_label.config(fg=self.t["fg"])
            return
        self.time_label.config(fg=self.t["danger"] if n % 2 else self.t["fg"])
        self._flash_job = self.root.after(150, lambda: self._flash(n - 1))

    def show_fireworks(self):
        if self.fw:
            self.fw.destroy()
            self.fw = None
        try:
            self.fw = Fireworks(self.root)
        except Exception:
            self.fw = None

    # ================= 主题 / 配置 =================
    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.apply_theme()
        self.save_config()

    def load_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_config(self):
        data = {
            "theme": self.theme_name,
            "pos": [self.root.winfo_x(), self.root.winfo_y()],
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def reset_pos(self):
        sw, _ = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"+{sw - self.W - 48}+{48}")
        self.save_config()

    # ================= 事件处理 =================
    def _start_drag(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()
        if self.fw:
            self.fw.destroy()
            self.fw = None

    def _drag(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _end_drag(self, e):
        self.save_config()

    def _popup(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _focused_on_entry(self):
        return isinstance(self.root.focus_get(), tk.Entry)

    def _on_key_space(self, e):
        if self._focused_on_entry():
            return
        self.toggle_start_pause()

    def _on_key_m(self, e):
        if self._focused_on_entry():
            return
        self.switch_mode()

    def _on_key_r(self, e):
        if self._focused_on_entry():
            return
        self.reset_timer()

    def toggle_start_pause(self):
        if self.mode == "stopwatch":
            self.toggle_stopwatch()
        elif self.mode == "countdown":
            self.toggle_countdown()

    def reset_timer(self):
        if self.mode == "stopwatch":
            self.reset_stopwatch()
        elif self.mode == "countdown":
            self.reset_countdown()

    def quit(self):
        self.save_config()
        if self.fw:
            self.fw.destroy()
        self.root.destroy()


def _single_instance_guard():
    """单实例保护：已有 DeskTimer 实例运行时，本实例静默退出（Windows 命名互斥锁）。"""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        global _instance_mutex_handle
        _instance_mutex_handle = kernel32.CreateMutexW(
            None, False, "Local\\DeskTimer_SingleInstance_7F3A2C")
        return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def main():
    # 单实例保护
    if _single_instance_guard():
        sys.exit(0)
    # DPI 感知，避免高分屏文字模糊
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    args = sys.argv[1:]
    smoke = None
    fireworks_test = None
    if "--smoke" in args:
        smoke = float(args[args.index("--smoke") + 1])
    if "--fireworks-test" in args:
        fireworks_test = float(args[args.index("--fireworks-test") + 1])
        smoke = max(smoke or 0, fireworks_test + 4)

    root = tk.Tk()
    app = DeskTimer(root, smoke=smoke, fireworks_test=fireworks_test)
    root.mainloop()
    print("DeskTimer exit OK")


if __name__ == "__main__":
    main()
