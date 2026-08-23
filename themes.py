"""DeskTimer 主题配色定义（深色 / 浅色）"""

THEMES = {
    "dark": {
        "name": "深色",
        "bg": "#12151c",        # 主背景（圆角面板）
        "fg": "#eef1f7",        # 主文字
        "fg_dim": "#8a93a6",    # 次要文字
        "btn_bg": "#232a3a",    # 按钮背景
        "btn_fg": "#cdd4e0",    # 按钮文字
        "btn_hover": "#2e3750", # 按钮悬停
        "entry_bg": "#0f1218",  # 输入框背景
        "danger": "#ff5c5c",    # 警告/闪烁色
        "key": "#010203",       # 透明键色（用于圆角挖空）
    },
    "light": {
        "name": "浅色",
        "bg": "#f6f7fb",
        "fg": "#232838",
        "fg_dim": "#7b8395",
        "btn_bg": "#e9edf5",
        "btn_fg": "#333a4d",
        "btn_hover": "#dce2ef",
        "entry_bg": "#ffffff",
        "danger": "#e5484d",
        "key": "#010203",
    },
}
