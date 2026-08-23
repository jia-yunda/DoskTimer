# DeskTimer 代码架构说明（ARCHITECTURE）

> 文档版本：1.1 ｜ 适用版本：DeskTimer 1.1（含 exe 打包）｜ 更新日期：2026-08-23

## 1. 项目概览

DeskTimer 是一个基于 **Python 3 + Tkinter** 的 Windows 桌面小组件，提供 **时钟 / 秒表 / 倒计时** 三种模式，倒计时结束时触发「声音提醒 + 闪烁变色 + 左上/右上角烟花绽放」三重反馈。支持 PyInstaller 打包为**单文件 exe**，双击即可运行。

| 项目 | 内容 |
|------|------|
| 运行平台 | Windows（依赖 winsound、`-transparentcolor`、命名互斥锁等特性） |
| 运行环境 | Python 3.x（内置 tkinter）或打包后的独立 exe |
| 交付形态 | 源码运行 或 单文件 exe（`dist\DeskTimer.exe`，约 12MB） |
| 单实例 | ✅ 内置 Windows 命名互斥锁，重复双击只运行一个实例 |

## 2. 目录结构

```
DeskTimer/
├── main.py          # 入口 + 主窗口 + 三种模式 + 主题 + 配置 + 事件 + 单实例（约 536 行）
├── fireworks.py     # 烟花粒子动画（透明覆盖层，约 136 行）
├── themes.py        # 深/浅主题配色定义（约 28 行）
├── _selftest.py     # 功能回归自测脚本
├── DeskTimer.spec   # PyInstaller 打包配置（可复用于重新打包）
├── config.json      # 运行时自动生成：主题 + 窗口位置
├── README.md        # 快速上手
├── docs/            # 架构/实现/使用手册/QA 报告
└── dist/
    ├── DeskTimer.exe   # 打包产物：单文件可执行程序
    └── config.json     # exe 运行后生成在 exe 同目录
```

## 3. 模块划分与依赖关系

```
                ┌──────────────────────────┐
                │         main.py          │
                │  DeskTimer 主类（UI/逻辑） │
                │  时钟 · 秒表 · 倒计时     │
                │  主题 · 配置 · 事件       │
                │  单实例 · 打包路径适配    │
                └──────┬───────┬───────┬───┘
                       │       │       │
              import   │       │       │ import
          ┌────────────┘       │       └────────────┐
          ▼                    ▼                     ▼
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
   │  themes.py  │      │  fireworks.py│     │  标准库      │
   │  THEMES 字典 │      │ Fireworks 类 │     │ tkinter      │
   │  (纯数据)   │      │  (动画渲染)  │     │ winsound     │
   └─────────────┘      └─────────────┘      │ time/json    │
                                             │ datetime/math│
                                             │ ctypes/os/sys│
                                             └─────────────┘
```

- **themes.py**：纯数据模块，`THEMES` 字典定义两套配色，被 main.py 引用。
- **fireworks.py**：独立动画模块，`Fireworks` 类接收主窗口 `master`，创建透明覆盖层播放烟花。
- **main.py**：唯一业务中枢，其余模块被它单向引用，无循环依赖；同时承载**打包路径适配**与**单实例互斥锁**两项平台级逻辑。

## 4. 类与函数设计

### 4.1 顶层函数（main.py）

| 函数 | 职责 |
|------|------|
| `fmt_time(seconds)` | 秒数格式化 `MM:SS.d` / `H:MM:SS.d`（0.1s 精度） |
| `parse_duration(text)` | 解析 `MM:SS` / `H:MM:SS` / 纯秒数，非法返回 None |
| `_single_instance_guard()` | **单实例保护**：创建命名互斥锁，已存在实例则返回 True |
| `main()` | 入口：单实例检查 → DPI 感知 → 参数解析 → 启动 Tk 主循环 |

### 4.2 `DeskTimer` 类（按职责 8 区）

| 分区 | 方法组 | 职责 |
|------|--------|------|
| 窗口初始化 | `__init__` | 无边框/置顶/半透明窗口、Canvas 背景、布局、菜单、事件绑定 |
| 界面构建 | `_rounded_rect` / `apply_theme` / `_mk_button` / `_build_controls` | 圆角面板绘制、主题全量刷新、按模式动态生成底部控制区 |
| 模式切换 | `switch_mode` / `set_mode` | 单按钮循环切换 clock→stopwatch→countdown |
| 主刷新循环 | `tick` / `_refresh_now` | 50ms 周期调度，按当前模式刷新显示 |
| 秒表逻辑 | `_sw_total` / `toggle_stopwatch` / `reset_stopwatch` / `_update_stopwatch` | 基于 `time.monotonic()` 的累加计时 |
| 倒计时逻辑 | `set_countdown` / `toggle_countdown` / `reset_countdown` / `_update_countdown` | 基于绝对完成时刻 `cd_finish_at` 的倒计时 |
| 到点提醒 | `_finish_countdown` / `_play_alarm` / `_flash` / `show_fireworks` | 声音（异步）+ 闪烁（after 定时器）+ 烟花（Fireworks） |
| 主题/配置/事件 | `toggle_theme` / `load_config` / `save_config` / 拖拽/菜单/快捷键处理 | 外观持久化、窗口拖动、右键菜单、快捷键 |

### 4.3 `Fireworks` 类（fireworks.py）

| 成员 | 职责 |
|------|------|
| `__init__(master)` | 创建覆盖主窗口的透明 Toplevel + Canvas，初始双角喷射 |
| `_burst(count)` | 从左上 (0,0) / 右上 (W,0) 向窗口内生成粒子 |
| `_tick()` | 20ms 帧循环：物理更新 → 绘制 → 生命周期判定 → 自销毁 |
| `_fade(color, t)` | 颜色向透明键色插值，实现粒子渐隐 |
| `destroy()` | 取消定时器并销毁覆盖层 |

## 5. 核心状态机

### 5.1 模式状态
```
          ┌───────────────────────────────────────┐
          ▼                                       │
   ┌───────────┐  switch_mode / M / 按钮  ┌───────────┐
   │  clock    │ ────────────────────────► │ stopwatch │
   │  时钟      │ ◄────────────────────────  │  秒表     │
   └───────────┘                          └───────────┘
          ▲                                       │
          │              ┌───────────┐            │
          └──────────────┤ countdown │◄───────────┘
                         │  倒计时    │
                         └───────────┘
```

### 5.2 秒表状态
```
 idle ──开始──► running ──暂停──► paused ──开始──► running
   ▲              │                │                 │
   └────清零/复位──┴────────────────┴─────────────────┘
```
显示值 = `sw_elapsed + (monotonic() - sw_start)`，基于单调时钟计算，**无累计误差**。

### 5.3 倒计时状态
```
 未设置 ──预设/输入──► ready ──开始──► running ──到点──► finished（时间到！）
    ▲                   ▲             │                   │
    └────设置新时长──────┘  ──暂停──► paused              （重置回 ready）
                                     └─继续──► running
```

### 5.4 应用生命周期（含单实例）
```
启动 ─► _single_instance_guard()
         ├─ 已有实例 → sys.exit(0)（静默退出，不叠加窗口）
         └─ 首次运行 → DPI 感知 → DeskTimer() → mainloop() → 退出时 save_config()
```

## 6. 关键数据流

### 6.1 配置路径解析（源码 / 打包双模式）
```python
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
          else os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
```
- **源码运行**：config.json 位于项目目录；
- **exe 运行**（`sys.frozen`）：config.json 位于 **exe 同目录**，避免写入 onefile 临时解压目录（_MEIPASS）导致配置丢失。

### 6.2 显示刷新循环
```
root.after(50ms) ─► tick() ─► 按 mode 分派
  ├─ clock    : datetime.now() ─► time_label / sub_label
  ├─ stopwatch: monotonic() 累计 ─► fmt_time() ─► time_label
  └─ countdown: finish_at - now ─► 若<=0 触发 _finish_countdown ─► time_label
```

### 6.3 单实例互斥锁（关键实现）
```python
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_handle = kernel32.CreateMutexW(None, False, "Local\\DeskTimer_SingleInstance_7F3A2C")
already = ctypes.get_last_error() == 183   # ERROR_ALREADY_EXISTS
```
- 句柄保存到模块级 `_instance_mutex_handle`，进程存活期间保持打开；
- 已存在实例 → `main()` 直接 `sys.exit(0)`；
- 进程退出后系统自动释放互斥锁，可重新启动。

## 7. 关键设计决策

| 决策 | 原因 |
|------|------|
| 使用 `time.monotonic()` 而非逐帧累加 | 避免定时器误差累计，保证长时间计时准确 |
| 倒计时用绝对完成时刻而非剩余量递减 | 暂停/继续切换时不丢精度 |
| `-transparentcolor` + `-alpha 0.93` 组合 | 同时实现四角完全透明与整体半透明 |
| 圆角用密集多边形（`smooth=False`） | `smooth=True` 样条会使直边向内弯折，产生镂空条 |
| 烟花用独立透明 Toplevel 覆盖层 | 不污染主窗口 UI，粒子只显示在透明区域 |
| 每 50ms 统一 `after` 循环 | 单一定时器驱动全部模式，简单可控 |
| 右键菜单管理主题/退出 | 保持界面极简，无冗余常驻按钮 |
| PyInstaller `-F -w` 单文件无控制台打包 | 用户双击即用，无需安装 Python |
| 配置目录随 `sys.frozen` 切换 | onefile 模式临时目录不可持久，必须指向 exe 目录 |
| 单实例命名互斥锁（静默退出） | 防止多开叠加窗口，符合桌面小组件使用习惯 |
