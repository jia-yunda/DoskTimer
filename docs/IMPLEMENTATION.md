# DeskTimer 实现方式说明（IMPLEMENTATION）

> 文档版本：1.1 ｜ 适用版本：DeskTimer 1.1（含 exe 打包）｜ 更新日期：2026-08-23

## 1. 技术栈与依赖

| 类别 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.14 | 内置 tkinter 8.6 |
| GUI | Tkinter | 标准库，零第三方依赖 |
| 声音 | winsound（Windows） | `PlaySound` 异步播放系统提示音 |
| 计时 | `time.monotonic()` | 单调时钟，防系统时间调整干扰 |
| 配置 | JSON（config.json） | 主题 + 窗口位置；路径随 `sys.frozen` 切换 |
| 单实例 | ctypes 命名互斥锁 | `CreateMutexW` + `ERROR_ALREADY_EXISTS` |
| 打包 | PyInstaller 6.22.2 | `-F -w` 单文件无控制台 exe |

## 2. 窗口外观实现

### 2.1 无边框 + 置顶 + 半透明
```python
root.overrideredirect(True)          # 去掉系统标题栏/边框
root.attributes("-topmost", True)    # 始终置顶（小组件悬浮）
root.attributes("-alpha", 0.93)      # 整窗半透明
```

### 2.2 真·透明圆角（核心技巧）
1. 设置**透明键色**：`root.attributes("-transparentcolor", KEY)`，其中 `KEY = "#010203"`。
2. Canvas 背景设为该键色；在画布上绘制圆角面板，**圆角外侧区域保留键色 → 完全透明**。
3. 圆角面板用**密集多边形近似**（每角 12 采样点，`smooth=False`），避免 `smooth=True` 样条将直边向内弯折导致左侧镂空。

```python
def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
    pts = []
    def arc(cx, cy, start_deg, end_deg):
        for i in range(13):
            ang = math.radians(start_deg + (end_deg - start_deg) * i / 12)
            pts += [cx + r * math.cos(ang), cy + r * math.sin(ang)]
    arc(x2 - r, y1 + r, -90, 0)    # 右上角
    arc(x2 - r, y2 - r, 0, 90)     # 右下角
    arc(x1 + r, y2 - r, 90, 180)   # 左下角
    arc(x1 + r, y1 + r, 180, 270)  # 左上角
    return self.canvas.create_polygon(pts, smooth=False, **kw)
```

> 验证结论：`-transparentcolor` 与 `-alpha` 可同时生效——键色像素**完全透明**（红底验证实测 R255,0,0），非键色像素按 alpha 混合（实测 R35,19,26，理论 R35,20,26）。

### 2.3 窗口拖动（无边框窗口需自实现）
```python
def _start_drag(self, e):
    self._dx = e.x_root - self.root.winfo_x()
    self._dy = e.y_root - self.root.winfo_y()
def _drag(self, e):
    self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")
```
对 root/canvas/各 label 绑定 `<ButtonPress-1>/<B1-Motion>/<ButtonRelease-1>`，利用 Tk bindtags 冒泡机制实现整窗可拖。

## 3. 三种模式实现

### 3.1 时钟
- `datetime.now().strftime("%H:%M:%S")` 显示时间，`%Y-%m-%d` + 星期映射显示日期，由 50ms `tick()` 刷新。

### 3.2 秒表（无漂移累加）
- 状态：`sw_running`、`sw_elapsed`（已累计）、`sw_start`（本次开始时刻）。
- 显示值：`sw_elapsed + (monotonic() - sw_start)`（运行中）；暂停时把增量固化进 `sw_elapsed`。
- **不做逐帧累加，长时间运行无误差**；精度 0.1 秒，`MM:SS.d`（超 1 小时变 `H:MM:SS.d`）。

### 3.3 倒计时（绝对完成时刻）
- 状态：`cd_total`（设定总长）、`cd_remaining`、`cd_finish_at`（绝对完成时刻）。
- 运行中 `remaining = cd_finish_at - monotonic()`；到点置 `cd_running=False`，**只触发一次** `_finish_countdown()`。
- 时长设置：预设按钮（1/3/5/10/25 分钟）或输入框（`MM:SS` / `H:MM:SS` / 纯秒数），回车即设置并开始。

## 4. 倒计时到点三重反馈

```python
def _finish_countdown(self):
    self._play_alarm()      # ① 声音
    self._flash(10)         # ② 时间大字红白闪烁 10 次（150ms 间隔）
    self.show_fireworks()   # ③ 左上/右上角烟花
```

| 反馈 | 实现 |
|------|------|
| 声音 | `winsound.PlaySound("SystemExclamation", SND_ALIAS \| SND_ASYNC)` 异步不卡界面 |
| 闪烁 | `root.after(150ms)` 链式回调，在 `fg` 与 `danger` 色间切换；切换模式/新闪烁会取消旧任务 |
| 烟花 | `Fireworks` 实例（见下节） |

## 5. 烟花粒子系统（fireworks.py）

- 在主窗口正上方创建**同尺寸、同位置的透明 Toplevel 覆盖层**（`-transparentcolor` 键色挖空），Canvas 逐帧绘制粒子。
- 物理模型（每帧 20ms）：
```
vx *= 0.985            # 空气阻力
vy = vy * 0.985 + 0.10 # 阻力 + 重力
x += vx; y += vy; life -= 1
半径 r = r0 * (1 - 0.4t)      # 逐渐缩小
颜色 = 插值(原色, 键色, t)     # 渐隐直至消失
```
- 初始：左上 `(0,0)`、右上 `(W,0)` 各 55 粒子，方向指向窗口内；第 24 帧二次喷射 35 粒子/角。
- 总时长上限约 3.4 秒，粒子消失或超时自动销毁；8 色 `PALETTE` 随机取色。
- 健壮性：窗口拖动时 `_start_drag` 先销毁烟花；`show_fireworks()` 用 try/except 包裹。

## 6. 主题系统与配置持久化

- `themes.py` 定义 `THEMES = {"dark": {...}, "light": {...}}`；`apply_theme()` 全量刷新面板、Label、Button、Entry 配色并重建控制区。
- `config.json` 保存 `theme` 与 `pos`；路径解析支持双模式：
```python
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
          else os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
```
- `save_config()` 在退出、拖动结束、切主题、复位位置时写入。

## 7. 单实例保护

```python
def _single_instance_guard():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    global _instance_mutex_handle
    _instance_mutex_handle = kernel32.CreateMutexW(
        None, False, "Local\\DeskTimer_SingleInstance_7F3A2C")
    return ctypes.get_last_error() == 183   # ERROR_ALREADY_EXISTS
```
- 首个实例创建互斥锁成功；后续实例检测到 `ERROR_ALREADY_EXISTS` 即 `sys.exit(0)` 静默退出。
- 句柄保存于模块级变量保持打开；进程退出后系统自动释放，可再次启动。

## 8. 打包发布（PyInstaller）

### 8.1 打包命令
```bash
pip install pyinstaller                    # 一次即可（PyInstaller 6.22.2）
python -m PyInstaller -F -w -n DeskTimer main.py --clean
```
| 参数 | 含义 |
|------|------|
| `-F` | 单文件模式（onefile），所有模块打入一个 exe |
| `-w` | 无控制台窗口（GUI 程序） |
| `-n DeskTimer` | 输出文件名 `DeskTimer.exe` |
| `--clean` | 清理缓存重新打包 |

### 8.2 打包前需注意的适配点
1. **路径**：onefile 运行时 `sys.frozen` 为真，`__file__` 指向临时解压目录（_MEIPASS），config 必须改指向 exe 目录（见 §6）。
2. **模块**：`fireworks.py` / `themes.py` 会被 PyInstaller 自动收集，无需额外 `--hidden-import`。
3. **字体/音效**：使用系统自带字体与系统提示音，无需捆绑资源。

### 8.3 产物
```
dist\DeskTimer.exe   # 约 12MB 单文件
dist\config.json     # exe 首次运行自动生成
```

## 9. 自测与调试机制

| 机制 | 用法 | 用途 |
|------|------|------|
| `--smoke N` | `python main.py --smoke 3` | 启动 N 秒自动退出，输出窗口几何（DBG 行） |
| `--fireworks-test N` | `python main.py --fireworks-test 2` | N 秒后强制触发一次烟花 |
| `_selftest.py` | `python _selftest.py` | 断言式回归：模式切换/秒表/倒计时→烟花/主题 |
| `python -m py_compile *.py` | 语法检查 | 打包前快速校验 |

## 10. DPI 适配

```python
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 系统级 DPI 感知
except Exception:
    pass
```
- 在创建 Tk 根窗口前调用，避免高分屏文字模糊、窗口坐标按物理像素计算。
