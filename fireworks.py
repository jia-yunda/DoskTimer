"""烟花庆祝效果 —— 倒计时结束时，从窗口左上/右上角绽放彩色粒子烟花。

实现：在主窗口上方叠加一个无边框透明 Toplevel 覆盖层，
在 Canvas 上逐帧绘制粒子（受重力与空气阻力影响，颜色渐隐至透明键色）。
仅依赖 tkinter，无第三方库。
"""
import math
import random
import tkinter as tk

# 烟花配色
PALETTE = [
    "#ff6b6b",  # 红
    "#ffd166",  # 金
    "#06d6a0",  # 绿
    "#4cc9f0",  # 蓝
    "#f72585",  # 粉
    "#ff9f1c",  # 橙
    "#8d6ffa",  # 紫
    "#ffffff",  # 白
]
GRAVITY = 0.10     # 每帧重力加速度（px/frame^2）
FRICTION = 0.985   # 空气阻力系数
FRAME_MS = 20      # 每帧间隔
MAX_FRAMES = 170   # 最长动画时长（约 3.4 秒）
KEY = "#010203"    # 透明键色，与 themes 中 key 保持一致


class Fireworks:
    """从窗口左上角和右上角绽放的烟花粒子动画。"""

    def __init__(self, master):
        self.master = master
        self.top = tk.Toplevel(master)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=KEY)
        self.top.attributes("-transparentcolor", KEY)

        # 覆盖在主窗口正上方，与主窗口同尺寸同位置
        self.W = master.winfo_width() or 380
        self.H = master.winfo_height() or 172
        x = master.winfo_rootx()
        y = master.winfo_rooty()
        self.top.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self.cv = tk.Canvas(self.top, bg=KEY, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        self.parts = []
        self._frame = 0
        self._job = None
        self._burst(55)   # 初始双角齐放
        self._tick()

    # ---- 粒子生成 ----
    def _burst(self, count):
        """从左上角 (0,0) 与右上角 (W,0) 同时向窗口内部喷射 count 个粒子。"""
        for corner in ("tl", "tr"):
            sx = 0 if corner == "tl" else self.W
            for _ in range(count):
                if corner == "tl":
                    # 方向指向右下象限（窗口内部）
                    ang = random.uniform(0.05, math.pi - 0.05)
                else:
                    ang = random.uniform(math.pi * 0.5, math.pi * 1.5)
                speed = random.uniform(2.0, 7.2)
                self.parts.append({
                    "x": float(sx),
                    "y": 0.0,
                    "vx": math.cos(ang) * speed,
                    "vy": math.sin(ang) * speed,
                    "color": random.choice(PALETTE),
                    "r": random.uniform(1.0, 2.6),
                    "life": random.uniform(24, 40),
                    "max": 40.0,
                })

    # ---- 帧循环 ----
    def _tick(self):
        self._frame += 1
        self.cv.delete("all")

        # 中途二次喷射，让烟花更饱满
        if self._frame == 24:
            self._burst(35)

        alive = []
        for p in self.parts:
            p["vx"] *= FRICTION
            p["vy"] = p["vy"] * FRICTION + GRAVITY
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["life"] -= 1
            if p["life"] <= 0:
                continue
            if p["x"] < 0 or p["x"] > self.W or p["y"] > self.H:
                continue
            t = 1.0 - p["life"] / p["max"]
            r = max(0.3, p["r"] * (1.0 - t * 0.4))
            color = self._fade(p["color"], t)
            self.cv.create_oval(
                p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r,
                fill=color, outline=color,
            )
            alive.append(p)
        self.parts = alive

        if self._frame < MAX_FRAMES and self.parts:
            self._job = self.top.after(FRAME_MS, self._tick)
        else:
            self.destroy()

    # ---- 工具 ----
    @staticmethod
    def _fade(hex_color, t):
        """将颜色按比例渐隐至透明键色，实现粒子淡出。"""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        nr = int(r * (1 - t) + 1 * t)
        ng = int(g * (1 - t) + 2 * t)
        nb = int(b * (1 - t) + 3 * t)
        return f"#{nr:02x}{ng:02x}{nb:02x}"

    def destroy(self):
        if self._job:
            try:
                self.top.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        try:
            self.top.destroy()
        except Exception:
            pass
