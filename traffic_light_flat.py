"""
AI Traffic Light - Windows 桌面浮窗 (Apple Flat 风格)
=======================================================
基于 HTML 原型 99% 还原，支持浅色/深色主题、单灯/三灯模式、右键设置面板。

状态说明:
  red    -> AI 正在思考 (Thinking) — 呼吸动画
  yellow -> 等待用户确认 (Waiting) — 闪烁动画
  green  -> 任务完成 (Done) — 常亮

API:
  POST /api/status   Body: {"color": "red|yellow|green"}
  GET  /api/status   返回当前状态
  POST /api/blink    Body: {"color": "red|yellow|green", "times": N}
  POST /api/stop-blink

启动:
  python traffic_light_flat.py [--port 9527] [--size 40] [--theme dark]
"""

import tkinter as tk
import json
import threading
import time
import math
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import ctypes

# ============================================================
# Windows API - 圆角窗口
# ============================================================
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


def set_window_rounded(hwnd, width, height, radius=20):
    try:
        rgn = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
        user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass


def get_hwnd(tk_widget):
    return ctypes.c_void_p(int(tk_widget.winfo_id()))


# ============================================================
# 配置参数
# ============================================================
DEFAULT_PORT = 9527
DEFAULT_SIZE = 40
DEFAULT_THEME = "dark"
API_HOST = "127.0.0.1"
UPDATE_INTERVAL = 16

# 基础尺寸 (HTML 原型值，按 size 比例缩放)
BASE_LIGHT_SIZE = 16
BASE_SINGLE_LIGHT_SIZE = 22
BASE_PADDING = 8
BASE_LIGHT_SPACING = 6
BASE_WIDGET_RADIUS = 20

# ============================================================
# 设计令牌 - 色彩系统 (与 HTML 原型完全一致)
# ============================================================
THEME_COLORS = {
    "light": {
        "bg_widget": "#FFFFFF",
        "bg_surface": "#F5F5F7",
        "border_default": "#D2D2D7",
        "text_primary": "#1D1D1F",
        "text_secondary": "#6E6E73",
        "red_on": "#FF3B30",
        "red_off": "#FFE5E3",
        "red_glow": "#FF6B64",
        "yellow_on": "#FFCC00",
        "yellow_off": "#FFF8E1",
        "yellow_glow": "#FFE066",
        "green_on": "#34C759",
        "green_off": "#E3F7E8",
        "green_glow": "#5FD47A",
        "switch_active": "#34C759",
        "switch_inactive": "#E5E5EA",
    },
    "dark": {
        "bg_widget": "#1D1D1F",
        "bg_surface": "#2C2C2E",
        "border_default": "#424245",
        "text_primary": "#F5F5F7",
        "text_secondary": "#86868B",
        "red_on": "#FF453A",
        "red_off": "#3A0F0C",
        "red_glow": "#FF6B64",
        "yellow_on": "#FFD60A",
        "yellow_off": "#3D3300",
        "yellow_glow": "#FFE44D",
        "green_on": "#30D158",
        "green_off": "#0A2E14",
        "green_glow": "#5FD47A",
        "switch_active": "#30D158",
        "switch_inactive": "#3A3A3C",
    },
}

STATUS_TEXT = {
    "red": "THINKING",
    "yellow": "WAITING",
    "green": "DONE",
}


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend_color(color1, color2, alpha):
    c1 = hex_to_rgb(color1)
    c2 = hex_to_rgb(color2)
    r = int(c1[0] * alpha + c2[0] * (1 - alpha))
    g = int(c1[1] * alpha + c2[1] * (1 - alpha))
    b = int(c1[2] * alpha + c2[2] * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"


# ============================================================
# 主应用
# ============================================================
class TrafficLightApp:
    def __init__(self, port=DEFAULT_PORT, size=DEFAULT_SIZE, theme=DEFAULT_THEME):
        self.port = port
        self.theme = theme

        # 计算缩放比例
        self.scale = size / BASE_LIGHT_SIZE

        # 计算实际尺寸
        self.light_size = int(BASE_LIGHT_SIZE * self.scale)
        self.single_light_size = int(BASE_SINGLE_LIGHT_SIZE * self.scale)
        self.padding = int(BASE_PADDING * self.scale)
        self.light_spacing = int(BASE_LIGHT_SPACING * self.scale)
        self.widget_radius = int(BASE_WIDGET_RADIUS * self.scale)

        # 状态
        self.current_color = "red"
        self.animation_time = 0.0

        # 设置
        self.single_light_mode = False
        self.always_on_top = True

        # 拖拽
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.dragging = False

        # 设置面板
        self.settings_window = None

        self._setup_window()
        self._start_api_server()
        self._bind_events()
        self._render_loop()

    # --------------------------------------------------------
    # 窗口初始化
    # --------------------------------------------------------
    def _setup_window(self):
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", self.always_on_top)

        self._update_window_size()

        # 窗口位置（默认右上角）
        screen_width = self.root.winfo_screenwidth()
        x = screen_width - self.win_width - 30
        y = 80
        self.root.geometry(f"{self.win_width}x{self.win_height}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.win_width,
            height=self.win_height,
            bg=THEME_COLORS[self.theme]["bg_widget"],
            highlightthickness=0,
        )
        self.canvas.pack()

        self.root.after(100, self._set_rounded_corners)

    def _update_window_size(self):
        if self.single_light_mode:
            self.win_width = self.single_light_size + self.padding * 2 + 4
            self.win_height = self.single_light_size + self.padding * 2 + 4
        else:
            self.win_width = self.light_size + self.padding * 2 + 4
            self.win_height = self.light_size * 3 + self.light_spacing * 2 + self.padding * 2 + 4

    def _set_rounded_corners(self):
        hwnd = get_hwnd(self.root)
        set_window_rounded(hwnd, self.win_width, self.win_height, self.widget_radius)

    def _rebuild_window(self):
        self._update_window_size()
        self.root.geometry(f"{self.win_width}x{self.win_height}")
        self.canvas.config(width=self.win_width, height=self.win_height)
        self.canvas.config(bg=THEME_COLORS[self.theme]["bg_widget"])
        self._set_rounded_corners()

    # --------------------------------------------------------
    # 事件绑定
    # --------------------------------------------------------
    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Button-3>", self._on_right_click)

    def _on_press(self, event):
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root
        self.dragging = False

    def _on_drag(self, event):
        self.dragging = True
        dx = event.x_root - self.drag_start_x
        dy = event.y_root - self.drag_start_y
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root

    def _on_release(self, event):
        pass

    def _on_right_click(self, event):
        if not self.dragging:
            self._show_settings_panel(event.x_root, event.y_root)

    # --------------------------------------------------------
    # 设置面板
    # --------------------------------------------------------
    def _show_settings_panel(self, x, y):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.settings_window = None
            return

        colors = THEME_COLORS[self.theme]

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.overrideredirect(True)
        self.settings_window.attributes("-topmost", True)

        panel_width = 220
        panel_height = 200

        # 计算位置，避免超出屏幕
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        panel_x = self.root.winfo_x() + self.win_width + 12
        panel_y = self.root.winfo_y()

        if panel_x + panel_width > screen_width:
            panel_x = self.root.winfo_x() - panel_width - 12
        if panel_y + panel_height > screen_height:
            panel_y = screen_height - panel_height - 20

        self.settings_window.geometry(f"{panel_width}x{panel_height}+{panel_x}+{panel_y}")

        settings_canvas = tk.Canvas(
            self.settings_window,
            width=panel_width,
            height=panel_height,
            bg=colors["bg_surface"],
            highlightthickness=1,
            highlightbackground=colors["border_default"],
        )
        settings_canvas.pack()

        # 圆角
        hwnd = get_hwnd(self.settings_window)
        self.settings_window.after(50, lambda: set_window_rounded(hwnd, panel_width, panel_height, 12))

        # 绘制内容
        self._draw_settings_content(settings_canvas, colors, panel_width)

        # 点击外部关闭
        self.settings_window.bind("<FocusOut>", lambda e: self._close_settings())
        self.settings_window.after(100, lambda: self.settings_window.focus_set())
        self.root.bind("<Button-1>", lambda e: self._close_settings())

    def _draw_settings_content(self, canvas, colors, width):
        text_color = colors["text_primary"]
        border_color = colors["border_default"]

        # 标题
        canvas.create_text(16, 16, text="设置", fill=text_color,
                           font=("Segoe UI", 12, "bold"), anchor="w")

        # 分隔线
        canvas.create_line(12, 36, width - 12, 36, fill=border_color, width=1)

        # Switch 行
        rows = [
            (55, "单灯模式", self.single_light_mode, self._toggle_single_light),
            (95, "深色模式", self.theme == "dark", self._toggle_theme),
            (135, "窗口置顶", self.always_on_top, self._toggle_topmost),
        ]
        for y, label, state, callback in rows:
            self._draw_switch_row(canvas, 16, y, width - 32, label, state, callback, colors)

        # 退出按钮 + 点击区域
        canvas.create_text(width // 2, 180, text="退出应用", fill="#FF453A",
                           font=("Segoe UI", 11), anchor="center")
        exit_hit = canvas.create_rectangle(width // 2 - 50, 170, width // 2 + 50, 190,
                                           fill="", outline="")
        canvas.tag_bind(exit_hit, "<Button-1>", lambda e: self._quit())

    def _draw_switch_row(self, canvas, x, y, width, label, is_on, callback, colors):
        text_color = colors["text_primary"]

        # 标签
        canvas.create_text(x, y, text=label, fill=text_color,
                           font=("Segoe UI", 11), anchor="w")

        # Switch 轨道
        switch_w = 36
        switch_h = 20
        track_x = x + width - switch_w
        track_y = y - 8
        track_color = colors["switch_active"] if is_on else colors["switch_inactive"]

        r = 10
        self._create_rounded_rect(canvas, track_x, track_y,
                                  track_x + switch_w, track_y + switch_h,
                                  r, fill=track_color, outline="")

        # 拨珠
        thumb_size = 16
        thumb_x = track_x + switch_w - thumb_size - 2 if is_on else track_x + 2
        thumb_y = track_y + 2

        # 阴影
        canvas.create_oval(thumb_x + 1, thumb_y + 1,
                           thumb_x + thumb_size + 1, thumb_y + thumb_size + 1,
                           fill="#00000030", outline="")
        # 拨珠主体
        canvas.create_oval(thumb_x, thumb_y,
                           thumb_x + thumb_size, thumb_y + thumb_size,
                           fill="#FFFFFF", outline="")

        # 可点击区域（整行）
        hit = canvas.create_rectangle(x, y - 12, x + width, y + 12,
                                      fill="", outline="")
        canvas.tag_bind(hit, "<Button-1>", lambda e: callback())

    def _close_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.settings_window = None
        try:
            self.root.unbind("<Button-1>")
        except Exception:
            pass

    # --------------------------------------------------------
    # 设置切换
    # --------------------------------------------------------
    def _toggle_single_light(self):
        self.single_light_mode = not self.single_light_mode
        self._rebuild_window()
        self._close_settings()
        print(f"[Settings] Single light mode: {self.single_light_mode}")

    def _toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.canvas.config(bg=THEME_COLORS[self.theme]["bg_widget"])
        self._close_settings()
        print(f"[Settings] Theme: {self.theme}")

    def _toggle_topmost(self):
        self.always_on_top = not self.always_on_top
        self.root.attributes("-topmost", self.always_on_top)
        self._close_settings()
        print(f"[Settings] Always on top: {self.always_on_top}")

    # --------------------------------------------------------
    # HTTP API 服务
    # --------------------------------------------------------
    def _start_api_server(self):
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
                            self._send_json({"error": f"Invalid color: {valid_colors}"}, 400)
                            return
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
        if color in ["red", "yellow", "green"]:
            self.current_color = color
            print(f"[TrafficLight] Status -> {color} ({STATUS_TEXT.get(color, '')})")

    def start_blink(self, color=None, times=0):
        self.current_color = color or self.current_color
        print(f"[TrafficLight] Blinking {self.current_color}")

    def stop_blink(self):
        print(f"[TrafficLight] Blink stopped")

    # --------------------------------------------------------
    # 渲染引擎
    # --------------------------------------------------------
    def _render_loop(self):
        self._draw()
        self.animation_time += UPDATE_INTERVAL / 1000.0
        self.root.after(UPDATE_INTERVAL, self._render_loop)

    def _draw(self):
        self.canvas.delete("all")
        colors = THEME_COLORS[self.theme]

        # 绘制外框
        self._draw_frame(colors)

        # 绘制灯光
        cx = self.win_width // 2
        if self.single_light_mode:
            cy = self.win_height // 2
            self._draw_single_light(cx, cy, colors)
        else:
            self._draw_three_lights(cx, colors)

    def _draw_frame(self, colors):
        w = self.win_width
        h = self.win_height
        r = self.widget_radius
        pad = 2

        # 圆角矩形背景
        self._create_rounded_rect(
            self.canvas, pad, pad, w - pad, h - pad, r,
            fill=colors["bg_widget"],
            outline=colors["border_default"],
            width=1,
        )

        # 顶部装饰线
        self.canvas.create_line(
            pad + r, pad + 1, w - pad - r, pad + 1,
            fill=colors["border_default"], width=1,
        )

    def _draw_three_lights(self, cx, colors):
        r = self.light_size // 2

        positions = [
            ("red", self.padding + r + 2),
            ("yellow", self.padding + self.light_size + self.light_spacing + r + 2),
            ("green", self.padding + self.light_size * 2 + self.light_spacing * 2 + r + 2),
        ]

        for color_name, cy in positions:
            is_active = (color_name == self.current_color)
            breath_alpha = 1.0

            # 呼吸效果（仅红灯）
            if is_active and color_name == "red":
                breath = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.animation_time * 2 * math.pi / 2.4))
                breath_alpha = breath

            # 闪烁效果（仅黄灯）
            if is_active and color_name == "yellow":
                cycle = (self.animation_time * 1000) % 800
                is_active = cycle < 400

            self._draw_light(cx, cy, r, color_name, is_active, colors, breath_alpha)

    def _draw_single_light(self, cx, cy, colors):
        r = self.single_light_size // 2
        color_name = self.current_color
        is_active = True
        breath_alpha = 1.0

        if color_name == "red":
            breath = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.animation_time * 2 * math.pi / 2.4))
            breath_alpha = breath
        elif color_name == "yellow":
            cycle = (self.animation_time * 1000) % 800
            is_active = cycle < 400

        self._draw_light(cx, cy, r, color_name, is_active, colors, breath_alpha)

    def _draw_light(self, cx, cy, r, color_name, is_active, colors, breath_alpha=1.0):
        on_color = colors[f"{color_name}_on"]
        off_color = colors[f"{color_name}_off"]
        glow_color = colors[f"{color_name}_glow"]

        # 计算实际颜色
        if is_active:
            if breath_alpha < 1.0:
                draw_color = blend_color(on_color, off_color, breath_alpha)
            else:
                draw_color = on_color
        else:
            draw_color = off_color

        # 外发光（亮灯时）
        if is_active:
            step = max(2, int(3 * self.scale))
            for i in range(3, 0, -1):
                glow_r = r + i * step
                self.canvas.create_oval(
                    cx - glow_r, cy - glow_r,
                    cx + glow_r, cy + glow_r,
                    outline=glow_color, width=1,
                )

        # 主体圆形
        self.canvas.create_oval(
            cx - r, cy - r,
            cx + r, cy + r,
            fill=draw_color, outline=draw_color, width=0,
        )

        # 高光反射（左上角）
        if is_active:
            hl_r = max(2, int(r * 0.3))
            hl_offset_x = int(r * 0.25)
            hl_offset_y = int(r * 0.25)

            # 主高光
            self.canvas.create_oval(
                cx - hl_offset_x - hl_r,
                cy - hl_offset_y - hl_r,
                cx - hl_offset_x + hl_r,
                cy - hl_offset_y + hl_r,
                fill="#FFFFFF", outline="",
            )

            # 小高光点
            tiny_r = max(1, int(r * 0.12))
            self.canvas.create_oval(
                cx - int(hl_offset_x * 0.5) - tiny_r,
                cy - int(hl_offset_y * 1.2) - tiny_r,
                cx - int(hl_offset_x * 0.5) + tiny_r,
                cy - int(hl_offset_y * 1.2) + tiny_r,
                fill="#FFFFFF", outline="",
            )

    def _create_rounded_rect(self, canvas, x1, y1, x2, y2, radius, **kwargs):
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
        print("[TrafficLight] AI Traffic Light Started (Apple Flat)")
        print(f"[TrafficLight] Red=Thinking | Yellow=Waiting | Green=Done")
        print(f"[TrafficLight] Right-click for settings | Drag to move")
        print(f"[TrafficLight] API: http://{API_HOST}:{self.port}")
        self.root.mainloop()

    def _quit(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        self.root.quit()
        self.root.destroy()


# ============================================================
# CLI 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="AI Traffic Light - Apple Flat Desktop Widget",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python traffic_light_flat.py                     # 默认端口 9527，尺寸 40，深色主题
  python traffic_light_flat.py --port 8080         # 自定义端口
  python traffic_light_flat.py --theme light       # 浅色主题
  python traffic_light_flat.py --size 32           # 小尺寸
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
