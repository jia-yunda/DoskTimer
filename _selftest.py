"""DeskTimer 功能自测：模式切换 / 秒表 / 倒计时→警报+烟花"""
import time
import tkinter as tk

from main import DeskTimer


def main():
    root = tk.Tk()
    app = DeskTimer(root, smoke=None)

    # 1. 模式循环切换
    app.switch_mode()            # clock -> stopwatch
    assert app.mode == "stopwatch", f"expected stopwatch, got {app.mode}"
    app.switch_mode()            # -> countdown
    assert app.mode == "countdown", f"expected countdown, got {app.mode}"
    app.switch_mode()            # -> clock
    assert app.mode == "clock", f"expected clock, got {app.mode}"
    print("PASS 模式切换")

    # 2. 秒表
    app.set_mode("stopwatch")
    app.toggle_stopwatch()
    time.sleep(1.05)
    app.toggle_stopwatch()
    total = app._sw_total()
    assert 1.0 <= total < 1.8, f"stopwatch total={total}"
    app.reset_stopwatch()
    assert app._sw_total() == 0.0
    print(f"PASS 秒表（累计 {total:.2f}s，清零 OK）")

    # 3. 倒计时 -> 到点触发警报 + 烟花
    app.set_mode("countdown")
    app.set_countdown(2)
    finished = {}

    def wrap():
        finished["ok"] = True
        return app._orig_finish()

    app._orig_finish = app._finish_countdown
    app._finish_countdown = wrap
    app.toggle_countdown()

    deadline = time.time() + 6
    while time.time() < deadline and "ok" not in finished:
        root.update()
        time.sleep(0.02)
    assert "ok" in finished, "倒计时未触发到点逻辑"
    assert app.fw is not None, "烟花对象未创建"
    # 再跑一会，确保烟花动画无异常
    t0 = time.time()
    while time.time() - t0 < 2.0:
        root.update()
        time.sleep(0.02)
    print("PASS 倒计时到点（警报+闪烁+烟花）")

    # 4. 主题切换
    app.toggle_theme()
    assert app.theme_name == "light"
    app.toggle_theme()
    assert app.theme_name == "dark"
    print("PASS 主题切换")

    root.destroy()
    print("SELFTEST ALL PASS")


if __name__ == "__main__":
    main()
