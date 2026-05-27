"""
AI Traffic Light - Windows 桌面浮窗 (Glassmorphism 毛玻璃风格)
=========================================================
基于 Apple Design Language，支持浅色/深色主题、单灯/三灯模式、
右键设置面板、Windows Acrylic 毛玻璃效果。

状态说明:
  red    -> AI 正在思考 (Thinking) — 呼吸动画
  yellow -> 等待用户确认 (Waiting) — 闪烁动画
  green  -> 任务完成 (Done) — 常亮

API:
  POST /api/status   Body: {"color": "red|yellow|green"}
  GET  /api/status   返回当前状态
  POST /api/blink    Body: {"color": "red|yellow|green", "times": N}

启动:
  python traffic_light_glass.py [--port 9527] [--size 80] [--theme dark]
"""

import tkinter as tk
from tkinter import ttk
import json
import threading
import time
import math
import sys
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import ctypes
from ctypes import wintypes, POINTER, c_int, c_uint, c_size_t, Structure

# ============================================================
# Windows API - Acrylic / Glass Effect
# ============================================================

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Window styles
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20
GWL_STYLE = -16

# Accent policy for SetWindowCompositionAttribute
class ACCENT_POLICY(Structure):
    _fields_ = [
        ("AccentState", c_uint),
        ("AccentFlags", c_uint),
        ("GradientColor", c_uint),
        ("AnimationId", c_uint),
    ]

class WINDOWCOMPOSITIONATTRIBDATA(Structure):
    _fields_ = [
        ("Attrib", c_int),
        ("pvData", POINTER(ACCENT_POLICY)),
        ("cbData", c_size_t),
    ]

WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

# DWM blur behind
class DWM_BLURBEHIND(Structure):
    _fields_ = [
        ("dwFlags", c_uint),
        ("fEnable", ctypes.c_bool),
        ("hRgnBlur", wintypes.HRGN),
        ("fTransitionOnMaximized", ctypes.c_bool),
    ]

DWM_BB_ENABLE = 0x00000001
DWM_BB_BLURREGION = 0x00000002
DWM_BB_TRANSITIONONMAXIMIZED = 0x00000004

def set_acrylic_effect(hwnd, enable=True, color=0x00000000):
    """设置 Windows Acrylic 毛玻璃效果"""
    try:
        accent = ACCENT_POLICY()
        accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND if enable else 0
        accent.AccentFlags = 2  # Draw all borders
        accent.GradientColor = color  # ARGB format
        accent.AnimationId = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attrib = WCA_ACCENT_POLICY
        data.pvData = ctypes.byref(accent)
        data.cbData = ctypes.sizeof(accent)

        user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
    except Exception as e:
        print(f"[Warning] Acrylic effect not available: {e}")
        return False
    return True

def set_dwm_blur(hwnd, enable=True):
    """备用: DWM 模糊效果"""
    try:
        bb = DWM_BLURBEHIND()
        bb.dwFlags = DWM_BB_ENABLE
        bb.fEnable = enable
        bb.hRgnBlur = None
        bb.fTransitionOnMaximized = False
        dwmapi.DwmEnableBlurBehindWindow(hwnd, ctypes.byref(bb))
    except Exception:
        pass

def extend_frame_into_client(hwnd, margins=(-1, -1, -1, -1)):
    """扩展 DWM 框架到客户区（实现玻璃边缘）"""
    try:
        class MARGINS(Structure):
            _fields_ = [("cxLeftWidth", c_int), ("cxRightWidth", c_int),
                        ("cyTopHeight", c_int), ("cyBottomHeight", c_int)]
        m = MARGINS(*margins)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))
    except Exception:
        pass

def get_hwnd(tk_widget):
    """获取 tkinter 窗口的 HWND"""
    return ctypes.c_void_p(int(tk_widget.winfo_id()))

def set_window_rounded(hwnd, width, height, radius=20):
    """设置窗口圆角"""
    try:
        from ctypes import windll
        # Create rounded rect region
        rgn = windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
        user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass

# ============================================================
# 配置参数
# ============================================================

DEFAULT_PORT = 9527
DEFAULT_SIZE = 16           # 灯泡直径 (像素)
DEFAULT_THEME = "dark"
WINDOW_PADDING = 8          # 内边距
LIGHT_SPACING = 6           # 灯间距
UPDATE_INTERVAL = 40        # 渲染帧间隔(ms), 约25fps
BLINK_INTERVAL = 400        # 闪烁间隔(ms) - ON/OFF 各 400ms
API_HOST = "127.0.0.1"

# ============================================================
# 设计令牌 - 色彩系统 (V2 Glassmorphism)
# ============================================================

THEME_COLORS = {
    "light": {
        # 背景
        "bg_widget": (255, 255, 255),
        "bg_widget_alpha": 0.72,
        "bg_surface": (255, 255, 255),
        "bg_surface_alpha": 0.82,
        # 边框
        "border_default": (255, 255, 255),
        "border_default_alpha": 0.40,
        "border_subtle": (210, 210, 215),
        "border_subtle_alpha": 0.30,
        # 文字
        "text_primary": (29, 29, 31),
        "text_primary_alpha": 0.92,
        "text_secondary": (110, 110, 115),
        "text_secondary_alpha": 0.85,
        "text_tertiary": (161, 161, 166),
        "text_tertiary_alpha": 0.70,
        # 灯光 - Red
        "red_on": (255, 59, 48),
        "red_on_alpha": 0.95,
        "red_off": (255, 229, 227),
        "red_off_alpha": 0.45,
        "red_glow": (255, 107, 100),
        "red_glow_alpha": 0.90,
        # 灯光 - Yellow
        "yellow_on": (255, 204, 0),
        "yellow_on_alpha": 0.95,
        "yellow_off": (255, 248, 225),
        "yellow_off_alpha": 0.45,
        "yellow_glow": (255, 224, 102),
        "yellow_glow_alpha": 0.90,
        # 灯光 - Green
        "green_on": (52, 199, 89),
        "green_on_alpha": 0.95,
        "green_off": (227, 247, 232),
        "green_off_alpha": 0.45,
        "green_glow": (95, 212, 122),
        "green_glow_alpha": 0.90,
        # Switch
        "switch_active": (52, 199, 89),
        "switch_active_alpha": 0.95,
        "switch_inactive": (142, 142, 147),
        "switch_inactive_alpha": 0.35,
        # 阴影
        "shadow_widget": (0, 8, 32, 0, 0, 0, 0.12),
        "shadow_panel": (0, 12, 40, 0, 0, 0, 0.15),
        # 内发光
        "inner_highlight": (255, 255, 255),
        "inner_highlight_alpha": 0.25,
    },
    "dark": {
        # 背景
        "bg_widget": (44, 44, 46),
        "bg_widget_alpha": 0.65,
        "bg_surface": (44, 44, 46),
        "bg_surface_alpha": 0.78,
        # 边框
        "border_default": (142, 142, 147),
        "border_default_alpha": 0.25,
        "border_subtle": (72, 72, 74),
        "border_subtle_alpha": 0.30,
        # 文字
        "text_primary": (245, 245, 247),
        "text_primary_alpha": 0.95,
        "text_secondary": (161, 161, 166),
        "text_secondary_alpha": 0.85,
        "text_tertiary": (110, 110, 115),
        "text_tertiary_alpha": 0.70,
        # 灯光 - Red
        "red_on": (255, 69, 58),
        "red_on_alpha": 0.95,
        "red_off": (58, 15, 12),
        "red_off_alpha": 0.50,
        "red_glow": (255, 107, 100),
        "red_glow_alpha": 0.90,
        # 灯光 - Yellow
        "yellow_on": (255, 214, 10),
        "yellow_on_alpha": 0.95,
        "yellow_off": (61, 51, 0),
        "yellow_off_alpha": 0.50,
        "yellow_glow": (255, 228, 77),
        "yellow_glow_alpha": 0.90,
        # 灯光 - Green
        "green_on": (48, 209, 88),
        "green_on_alpha": 0.95,
        "green_off": (10, 46, 20),
        "green_off_alpha": 0.50,
        "green_glow": (95, 212, 122),
        "green_glow_alpha": 0.90,
        # Switch
        "switch_active": (48, 209, 88),
        "switch_active_alpha": 0.95,
        "switch_inactive": (142, 142, 147),
        "switch_inactive_alpha": 0.30,
        # 阴影
        "shadow_widget": (0, 8, 32, 0, 0, 0, 0.28),
        "shadow_panel": (0, 12, 40, 0, 0, 0, 0.40),
        # 内发光
        "inner_highlight": (255, 255, 255),
        "inner_highlight_alpha": 0.08,
    },
}

STATUS_TEXT = {
    "red": "THINKING",
    "yellow": "WAITING",
    "green": "DONE",
}


def rgb_to_hex(rgb, alpha=1.0):
    """RGB 元组转 HEX 颜色"""
    r, g, b = rgb
    if alpha < 1.0:
        # 混合到背景色（简化：假设背景为黑或白）
        pass
    return f"#{r:02x}{g:02x}{b:02x}"

def rgba_to_hex(rgb, alpha):
    """RGBA 转 tkinter 可用的颜色（纯 HEX，alpha 用于逻辑判断）"""
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"

def blend_color(color1, color2, alpha):
    """混合两个颜色"""
    r = int(color1[0] * alpha + color2[0] * (1 - alpha))
    g = int(color1[1] * alpha + color2[1] * (1 - alpha))
    b = int(color1[2] * alpha + color2[2] * (1 - alpha))
    return (r, g, b)


# ============================================================
# 主应用
# ============================================================

class TrafficLightApp:
    """红绿灯主应用 - Glassmorphism 风格"""

    def __init__(self, port=DEFAULT_PORT, size=DEFAULT_SIZE, theme=DEFAULT_THEME):
        self.port = port
        self.light_size = size
        self.theme = theme

        # 状态管理
        self.current_color = "red"
        self.target_color = "red"
        self.blink_state = False
        self.blinking = False
        self.blink_color = None
        self.animation_progress = 1.0
        self.glow_phase = 0.0

        # 设置
        self.single_light_mode = False
        self.always_on_top = True

        # 拖拽相关
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.dragging = False

        # 设置面板
        self.settings_window = None

        # 创建主窗口
        self._setup_window()

        # 启动 HTTP API 服务
        self._start_api_server()

        # 绑定事件
        self._bind_events()

        # 开始渲染循环
        self._render_loop()

    # --------------------------------------------------------
    # 窗口初始化
    # --------------------------------------------------------
    def _setup_window(self):
        """创建毛玻璃风格悬浮窗"""
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)

        # 计算窗口尺寸
        self._update_window_size()

        # 设置窗口位置（默认右上角）
        screen_width = self.root.winfo_screenwidth()
        x = screen_width - self.win_width - 30
        y = 80
        self.root.geometry(f"{self.win_width}x{self.win_height}+{x}+{y}")

        # 置顶
        self.root.attributes("-topmost", True)

        # 创建画布
        self.canvas = tk.Canvas(
            self.root,
            width=self.win_width,
            height=self.win_height,
            bg="#000000",
            highlightthickness=0,
        )
        self.canvas.pack()

        # 应用毛玻璃效果
        self._apply_glass_effect()

        # 设置圆角
        self.root.after(100, self._set_rounded_corners)

    def _update_window_size(self):
        """根据模式计算窗口尺寸"""
        if self.single_light_mode:
            self.win_width = self.light_size + WINDOW_PADDING * 2 + 4
            self.win_height = self.light_size + WINDOW_PADDING * 2 + 4
        else:
            self.win_width = self.light_size + WINDOW_PADDING * 2 + 4
            self.win_height = self.light_size * 3 + LIGHT_SPACING * 2 + WINDOW_PADDING * 2 + 4

    def _apply_glass_effect(self):
        """应用 Windows 毛玻璃效果"""
        hwnd = get_hwnd(self.root)

        # 设置窗口为分层窗口（支持透明和模糊）
        try:
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED | WS_EX_TOOLWINDOW)
        except Exception:
            pass

        # 应用 Acrylic 效果
        colors = THEME_COLORS[self.theme]
        bg = colors["bg_widget"]
        alpha = colors["bg_widget_alpha"]
        # ARGB 格式
        gradient_color = (int(alpha * 255) << 24) | (bg[2] << 16) | (bg[1] << 8) | bg[0]

        if not set_acrylic_effect(hwnd, enable=True, color=gradient_color):
            # 备用: DWM 模糊
            set_dwm_blur(hwnd, enable=True)

        # 扩展框架
        extend_frame_into_client(hwnd, margins=(-1, -1, -1, -1))

    def _set_rounded_corners(self):
        """设置窗口圆角"""
        hwnd = get_hwnd(self.root)
        set_window_rounded(hwnd, self.win_width, self.win_height, radius=20)

    def _update_glass_color(self):
        """更新毛玻璃颜色（主题切换时）"""
        hwnd = get_hwnd(self.root)
        colors = THEME_COLORS[self.theme]
        bg = colors["bg_widget"]
        alpha = colors["bg_widget_alpha"]
        gradient_color = (int(alpha * 255) << 24) | (bg[2] << 16) | (bg[1] << 8) | bg[0]
        set_acrylic_effect(hwnd, enable=True, color=gradient_color)

    # --------------------------------------------------------
    # 事件绑定
    # --------------------------------------------------------
    def _bind_events(self):
        """绑定鼠标和键盘事件"""
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Button-3>", self._on_right_click)
        self.root.bind("<Double-Button-1>", self._toggle_blink)

    def _on_press(self, event):
        """鼠标按下 - 记录拖拽起始位置"""
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root
        self.dragging = False

    def _on_drag(self, event):
        """鼠标拖拽 - 移动窗口"""
        self.dragging = True
        dx = event.x_root - self.drag_start_x
        dy = event.y_root - self.drag_start_y
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root

    def _on_release(self, event):
        """鼠标释放"""
        pass

    def _on_right_click(self, event):
        """右键点击 - 打开设置面板"""
        if not self.dragging:
            self._show_settings_panel(event.x_root, event.y_root)

    def _toggle_blink(self, event):
        """双击切换闪烁模式"""
        if self.blinking:
            self.stop_blink()
        else:
            self.start_blink(self.current_color)

    # --------------------------------------------------------
    # 设置面板
    # --------------------------------------------------------
    def _show_settings_panel(self, x, y):
        """显示设置面板"""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.settings_window = None
            return

        colors = THEME_COLORS[self.theme]

        # 创建设置窗口
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.overrideredirect(True)
        self.settings_window.attributes("-topmost", True)
        self.settings_window.geometry(f"220x200+{x}+{y}")

        # 毛玻璃效果
        hwnd = get_hwnd(self.settings_window)
        try:
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED | WS_EX_TOOLWINDOW)
        except Exception:
            pass

        bg_s = colors["bg_surface"]
        alpha_s = colors["bg_surface_alpha"]
        gradient_color = (int(alpha_s * 255) << 24) | (bg_s[2] << 16) | (bg_s[1] << 8) | bg_s[0]
        set_acrylic_effect(hwnd, enable=True, color=gradient_color)
        extend_frame_into_client(hwnd, margins=(-1, -1, -1, -1))

        # 画布
        settings_canvas = tk.Canvas(
            self.settings_window,
            width=220,
            height=200,
            bg="#000000",
            highlightthickness=0,
        )
        settings_canvas.pack()

        # 圆角
        self.settings_window.after(50, lambda: set_window_rounded(hwnd, 220, 200, 16))

        # 绘制内容
        self._draw_settings_panel(settings_canvas, colors)

        # 点击外部关闭
        self.settings_window.bind("<FocusOut>", lambda e: self._close_settings())
        self.settings_window.after(100, lambda: self.settings_window.focus_set())

    def _draw_settings_panel(self, canvas, colors):
        """绘制设置面板内容"""
        text_color = rgba_to_hex(colors["text_primary"], colors["text_primary_alpha"])
        text_secondary = rgba_to_hex(colors["text_secondary"], colors["text_secondary_alpha"])
        border_color = rgba_to_hex(colors["border_default"], colors["border_default_alpha"])

        # 标题
        canvas.create_text(20, 20, text="设置", fill=text_color,
                          font=("Segoe UI", 12, "bold"), anchor="w")

        # 分隔线
        canvas.create_line(12, 38, 208, 38, fill=border_color, width=1)

        # Switch 1: 单灯模式
        self._draw_switch(canvas, 20, 55, "单灯模式", self.single_light_mode,
                         lambda: self._toggle_single_light())

        # Switch 2: 深色模式
        is_dark = self.theme == "dark"
        self._draw_switch(canvas, 20, 95, "深色模式", is_dark,
                         lambda: self._toggle_theme())

        # Switch 3: 窗口置顶
        self._draw_switch(canvas, 20, 135, "窗口置顶", self.always_on_top,
                         lambda: self._toggle_topmost())

        # 退出按钮
        canvas.create_text(110, 180, text="退出应用", fill="#FF453A",
                          font=("Segoe UI", 11), anchor="center")
        canvas.bind("<Button-1>", lambda e: self._check_exit_click(e, canvas))

    def _draw_switch(self, canvas, x, y, label, is_on, callback):
        """绘制自定义 Switch 开关"""
        colors = THEME_COLORS[self.theme]
        text_color = rgba_to_hex(colors["text_primary"], colors["text_primary_alpha"])

        # 标签
        canvas.create_text(x, y, text=label, fill=text_color,
                          font=("Segoe UI", 11), anchor="w")

        # Switch 轨道
        track_x = x + 160
        track_y = y - 8
        track_width = 36
        track_height = 20
        radius = 10

        # 轨道背景
        if is_on:
            track_color = rgba_to_hex(colors["switch_active"], colors["switch_active_alpha"])
        else:
            track_color = rgba_to_hex(colors["switch_inactive"], colors["switch_inactive_alpha"])

        self._create_rounded_rect(canvas, track_x, track_y,
                                  track_x + track_width, track_y + track_height,
                                  radius, fill=track_color, outline="")

        # 拨珠
        thumb_size = 16
        if is_on:
            thumb_x = track_x + track_width - thumb_size - 2
        else:
            thumb_x = track_x + 2
        thumb_y = track_y + 2

        # 拨珠阴影
        canvas.create_oval(thumb_x + 1, thumb_y + 1,
                          thumb_x + thumb_size + 1, thumb_y + thumb_size + 1,
                          fill="rgba(0,0,0,0.15)", outline="")
        # 拨珠本体
        canvas.create_oval(thumb_x, thumb_y,
                          thumb_x + thumb_size, thumb_y + thumb_size,
                          fill="#FFFFFF", outline="")

        # 绑定点击
        switch_id = canvas.create_rectangle(track_x, track_y,
                                            track_x + track_width, track_y + track_height,
                                            fill="", outline="")
        canvas.tag_bind(switch_id, "<Button-1>", lambda e: callback())
        # 绑定标签点击
        label_id = canvas.create_rectangle(x, y - 10, x + 150, y + 10,
                                          fill="", outline="")
        canvas.tag_bind(label_id, "<Button-1>", lambda e: callback())

    def _check_exit_click(self, event, canvas):
        """检查是否点击了退出"""
        if 80 <= event.x <= 140 and 170 <= event.y <= 190:
            self._quit()

    def _close_settings(self):
        """关闭设置面板"""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.settings_window = None

    # --------------------------------------------------------
    # 设置切换
    # --------------------------------------------------------
    def _toggle_single_light(self):
        """切换单灯/三灯模式"""
        self.single_light_mode = not self.single_light_mode
        self._update_window_size()
        self.root.geometry(f"{self.win_width}x{self.win_height}")
        self.canvas.config(width=self.win_width, height=self.win_height)
        self._set_rounded_corners()
        # 关闭设置面板
        self._close_settings()
        print(f"[Settings] Single light mode: {self.single_light_mode}")

    def _toggle_theme(self):
        """切换浅色/深色主题"""
        self.theme = "dark" if self.theme == "light" else "light"
        self._update_glass_color()
        self._close_settings()
        print(f"[Settings] Theme: {self.theme}")

    def _toggle_topmost(self):
        """切换置顶/非置顶"""
        self.always_on_top = not self.always_on_top
        self.root.attributes("-topmost", self.always_on_top)
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.attributes("-topmost", self.always_on_top)
        self._close_settings()
        print(f"[Settings] Always on top: {self.always_on_top}")

    # --------------------------------------------------------
    # HTTP API 服务
    # --------------------------------------------------------
    def _start_api_server(self):
        """在后台线程启动 HTTP API 服务"""
        app_ref = self

        class StatusHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/api/status":
                    self._send_json({
                        "status": "ok",
                        "color": app_ref.current_color,
                        "blinking": app_ref.blinking,
                        "text": STATUS_TEXT.get(app_ref.current_color, ""),
                        "theme": app_ref.theme,
                        "single_light": app_ref.single_light_mode,
                        "always_on_top": app_ref.always_on_top,
                    })
                elif parsed.path == "/api/health":
                    self._send_json({"status": "running", "port": app_ref.port})
                else:
                    self.send_error(404)

            def do_POST(self):
                parsed = urlparse(self.path)
                if parsed.path == "/api/status":
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)
                    try:
                        data = json.loads(body) if body else {}
                        color = data.get("color", "").lower().strip()
                        valid_colors = ["red", "yellow", "green"]
                        if color not in valid_colors:
                            self._send_json({"error": f"Invalid color. Must be one of: {valid_colors}"}, 400)
                            return
                        blink = data.get("blink", False)
                        if blink:
                            app_ref.start_blink(color)
                        else:
                            app_ref.set_status(color)
                        self._send_json({
                            "status": "ok",
                            "color": app_ref.current_color,
                            "text": STATUS_TEXT.get(color, ""),
                        })
                    except json.JSONDecodeError:
                        self._send_json({"error": "Invalid JSON"}, 400)
                elif parsed.path == "/api/blink":
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)
                    try:
                        data = json.loads(body) if body else {}
                        color = data.get("color", app_ref.current_color).lower()
                        times = data.get("times", 0)
                        app_ref.start_blink(color, times)
                        self._send_json({"status": "blinking", "color": color})
                    except Exception as e:
                        self._send_json({"error": str(e)}, 400)
                elif parsed.path == "/api/stop-blink":
                    app_ref.stop_blink()
                    self._send_json({"status": "blink stopped"})
                else:
                    self.send_error(404)

            def _send_json(self, data, status_code=200):
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

        server = HTTPServer((API_HOST, self.port), StatusHandler)

        def serve_forever():
            print(f"[TrafficLight] API Server running at http://{API_HOST}:{self.port}")
            server.serve_forever()

        thread = threading.Thread(target=serve_forever, daemon=True)
        thread.start()
        print(f"[TrafficLight] API server started on port {self.port}")

    # --------------------------------------------------------
    # 状态控制接口
    # --------------------------------------------------------
    def set_status(self, color):
        """设置灯光状态"""
        if color in ["red", "yellow", "green"]:
            self.target_color = color
            self.current_color = color
            self.animation_progress = 0.0
            if self.blinking and self.blink_color != color:
                self.stop_blink()
            print(f"[TrafficLight] Status -> {color} ({STATUS_TEXT.get(color, '')})")

    def start_blink(self, color=None, times=0):
        """开始闪烁"""
        self.blinking = True
        self.blink_color = color or self.current_color
        self.blink_times = times
        self.blink_count = 0
        self.blink_state = True
        print(f"[TrafficLight] Blinking {self.blink_color}")

    def stop_blink(self):
        """停止闪烁"""
        self.blinking = False
        self.blink_color = None
        self.blink_state = False
        self.set_status(self.target_color)

    # --------------------------------------------------------
    # 渲染引擎
    # --------------------------------------------------------
    def _render_loop(self):
        """主渲染循环"""
        self._draw()
        self.glow_phase += 0.026  # ~2400ms cycle at 40ms interval

        # 闪烁逻辑 (800ms cycle: 400ms ON, 400ms OFF)
        if self.blinking:
            elapsed = time.time() * 1000
            cycle_pos = (elapsed % 800) / 800
            self.blink_state = cycle_pos < 0.5

            if self.blink_times > 0:
                self.blink_count = int(elapsed / 800)
                if self.blink_count >= self.blink_times:
                    self.stop_blink()

        # 过渡动画进度
        if self.animation_progress < 1.0:
            self.animation_progress = min(1.0, self.animation_progress + 0.04)

        self.root.after(UPDATE_INTERVAL, self._render_loop)

    def _draw(self):
        """绘制整个界面"""
        self.canvas.delete("all")
        colors = THEME_COLORS[self.theme]
        cx = self.win_width // 2

        # 绘制外框（圆角矩形）
        self._draw_frame(colors)

        # 绘制灯光
        if self.single_light_mode:
            self._draw_single_light(cx, colors)
        else:
            self._draw_three_lights(cx, colors)

    def _draw_frame(self, colors):
        """绘制外框背景"""
        w = self.win_width
        h = self.win_height
        r = 20

        # 在分层窗口模式下，背景由 Windows DWM 处理
        # 这里只绘制内容层

    def _draw_three_lights(self, cx, colors):
        """绘制三灯模式"""
        light_r = self.light_size // 2

        positions = [
            ("red", WINDOW_PADDING + light_r + 2),
            ("yellow", WINDOW_PADDING + light_r * 3 + LIGHT_SPACING + 2),
            ("green", WINDOW_PADDING + light_r * 5 + LIGHT_SPACING * 2 + 2),
        ]

        for color_name, cy in positions:
            is_active = (color_name == self.current_color)
            is_blink_on = self.blinking and color_name == self.blink_color and self.blink_state

            if self.blinking and color_name == self.blink_color:
                is_active = is_blink_on

            self._draw_light(cx, cy, light_r, color_name, is_active, colors)

    def _draw_single_light(self, cx, colors):
        """绘制单灯模式"""
        light_r = self.light_size // 2 + 3
        cy = self.win_height // 2
        self._draw_light(cx, cy, light_r, self.current_color, True, colors)

    def _draw_light(self, cx, cy, r, color_name, is_active, colors):
        """绘制单个灯泡"""
        on_key = f"{color_name}_on"
        off_key = f"{color_name}_off"
        glow_key = f"{color_name}_glow"

        on_color = colors[on_key]
        off_color = colors[off_key]
        glow_color = colors[glow_key]

        # 计算呼吸效果
        if is_active and color_name == "red" and not self.blinking:
            # 呼吸动画: opacity 1.0 -> 0.55 -> 1.0
            breath = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.glow_phase))
            draw_color = blend_color(on_color, off_color, breath)
        elif is_active:
            draw_color = on_color
        else:
            draw_color = off_color

        draw_hex = rgb_to_hex(draw_color)
        off_hex = rgb_to_hex(off_color)

        # 外发光（仅亮灯状态）
        if is_active:
            glow_r = r + 6
            glow_hex = rgb_to_hex(glow_color)
            for i in range(3, 0, -1):
                gr = glow_r + i * 2
                alpha = int(20 / i)
                glow_color_faded = f"#{glow_color[0]:02x}{glow_color[1]:02x}{glow_color[2]:02x}"
                self.canvas.create_oval(
                    cx - gr, cy - gr, cx + gr, cy + gr,
                    outline=glow_color_faded, width=1,
                )

        # 主灯泡
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=draw_hex,
            outline=draw_hex,
            width=0,
        )

        # 内阴影（灭灯状态）
        if not is_active:
            self.canvas.create_oval(
                cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1,
                fill=draw_hex,
                outline="",
            )

        # 高光反射（左上角）
        if is_active:
            highlight_r = r * 0.3
            highlight_offset = r * 0.25
            self.canvas.create_oval(
                cx - highlight_offset - highlight_r,
                cy - highlight_offset - highlight_r,
                cx - highlight_offset + highlight_r,
                cy - highlight_offset + highlight_r,
                fill="#FFFFFF",
                outline="",
            )
            # 小高光点
            tiny_r = r * 0.12
            self.canvas.create_oval(
                cx - highlight_offset * 0.5 - tiny_r,
                cy - highlight_offset * 1.2 - tiny_r,
                cx - highlight_offset * 0.5 + tiny_r,
                cy - highlight_offset * 1.2 + tiny_r,
                fill="#FFFFFF",
                outline="",
            )

    def _create_rounded_rect(self, canvas, x1, y1, x2, y2, radius, **kwargs):
        """绘制圆角矩形"""
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def run(self):
        """启动应用主循环"""
        print("[TrafficLight] AI Traffic Light Started (Glassmorphism)")
        print(f"[TrafficLight] Red=Thinking | Yellow=Waiting | Green=Done")
        print(f"[TrafficLight] Right-click for settings | Double-click to blink")
        print(f"[TrafficLight] API: http://{API_HOST}:{self.port}")
        self.root.mainloop()

    def _quit(self):
        """退出应用"""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        self.root.quit()
        self.root.destroy()


# ============================================================
# CLI 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="AI Traffic Light - Glassmorphism Desktop Widget",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python traffic_light_glass.py                    # 默认端口 9527，深色主题
  python traffic_light_glass.py --port 8080        # 自定义端口
  python traffic_light_glass.py --theme light      # 浅色主题
  python traffic_light_glass.py --size 20          # 大灯泡
        """,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"API 监听端口 (默认: {DEFAULT_PORT})")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE,
                        help=f"灯泡直径像素 (默认: {DEFAULT_SIZE})")
    parser.add_argument("--theme", type=str, default=DEFAULT_THEME,
                        choices=["light", "dark"],
                        help=f"主题 (默认: {DEFAULT_THEME})")
    args = parser.parse_args()

    app = TrafficLightApp(
        port=args.port,
        size=args.size,
        theme=args.theme,
    )
    app.run()


if __name__ == "__main__":
    main()
