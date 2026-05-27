"""
Claude Code 状态红绿灯 - Windows 桌面浮窗
==========================================
一个轻量级桌面交通信号灯，通过 HTTP API 接收状态切换指令。

状态说明:
  red    -> 空闲/停止（红灯亮）
  yellow -> 思考中/做选择题/运行中（黄灯闪烁）
  green  -> 完成/成功（绿灯亮）

API:
  POST /api/status   Body: {"color": "red|yellow|green"}
  GET  /api/status   返回当前状态
  POST /api/blink    Body: {"color": "red|yellow|green", "times": N}

启动:
  python traffic_light.py [--port 9527] [--size 80] [--opacity 0.95]
"""

import tkinter as tk
import json
import threading
import time
import math
import sys
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ============================================================
# 配置参数
# ============================================================

DEFAULT_PORT = 9527
DEFAULT_SIZE = 80          # 灯泡直径
DEFAULT_OPACITY = 0.92     # 窗口透明度
WINDOW_PADDING = 20        # 内边距
LIGHT_SPACING = 8          # 灯间距
UPDATE_INTERVAL = 16       # 渲染帧间隔(ms), 约60fps
BLINK_INTERVAL = 500       # 闪烁间隔(ms)
API_HOST = "127.0.0.1"

# 颜色定义 (RGB)
COLORS = {
    "red": {
        "on": "#FF3333", "off": "#440000",
        "glow": "#FF6666", "border": "#CC0000"
    },
    "yellow": {
        "on": "#FFD700", "off": "#443300",
        "glow": "#FFE44D", "border": "#CC9900"
    },
    "green": {
        "on": "#33FF66", "off": "#004400",
        "glow": "#66FF99", "border": "#00CC33"
    },
}

STATUS_TEXT = {
    "red": "IDLE",
    "yellow": "THINKING...",
    "green": "DONE",
}


class TrafficLightApp:
    """红绿灯主应用"""

    def __init__(self, port=DEFAULT_PORT, size=DEFAULT_SIZE,
                 opacity=DEFAULT_OPACITY):
        self.port = port
        self.light_size = size
        self.opacity = opacity

        # 状态管理
        self.current_color = "red"      # 当前亮灯颜色
        self.target_color = "red"       # 目标颜色（用于过渡动画）
        self.blink_state = False        # 闪烁状态
        self.blinking = False           # 是否正在闪烁
        self.blink_color = None         # 闪烁的颜色
        self.animation_progress = 1.0    # 动画进度 0~1
        self.glow_phase = 0             # 发光相位（用于呼吸效果）

        # 拖拽相关
        self.drag_start_x = 0
        self.drag_start_y = 0

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
        """创建透明置顶悬浮窗"""
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # 无边框

        # 计算窗口尺寸
        width = self.light_size + WINDOW_PADDING * 2
        height = self.light_size * 3 + LIGHT_SPACING * 2 + WINDOW_PADDING * 2 + 28  # +28 for status text

        # 设置窗口位置（默认右上角）
        screen_width = self.root.winfo_screenwidth()
        x = screen_width - width - 20
        y = 60
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Windows 特有: 置顶 + 透明
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", "black")
            self.root.attributes("-alpha", self.opacity)
        except tk.TclError:
            pass  # Linux/macOS 可能不支持

        # 创建画布
        self.canvas = tk.Canvas(
            self.root,
            width=width,
            height=height,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.pack()

        # 设置鼠标穿透（点击非灯泡区域时穿透到下层窗口）
        self.root.bind("<ButtonPress-1>", self._on_press)

    # --------------------------------------------------------
    # 事件绑定
    # --------------------------------------------------------
    def _bind_events(self):
        """绑定鼠标和键盘事件"""
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Double-Button-1>", self._toggle_blink)
        self.root.bind("<Button-3>", lambda e: self._show_menu(e))

        # 右键菜单
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="红灯 (空闲)",
                              command=lambda: self.set_status("red"))
        self.menu.add_command(label="黄灯 (思考中)",
                              command=lambda: self.set_status("yellow"))
        self.menu.add_command(label="绿灯 (完成)",
                              command=lambda: self.set_status("green"))
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self._quit)

    def _on_press(self, event):
        """鼠标按下 - 记录拖拽起始位置"""
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root

    def _on_drag(self, event):
        """鼠标拖拽 - 移动窗口"""
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

    def _toggle_blink(self, event):
        """双击切换闪烁模式"""
        if self.blinking:
            self.stop_blink()
        else:
            self.start_blink(self.current_color)

    def _show_menu(self, event):
        """显示右键菜单"""
        self.menu.post(event.x_root, event.y_root)

    # --------------------------------------------------------
    # HTTP API 服务
    # --------------------------------------------------------
    def _start_api_server(self):
        """在后台线程启动 HTTP API 服务"""

        # 将自身引用传递给 handler（用于回调切换状态）
        app_ref = self

        class StatusHandler(BaseHTTPRequestHandler):
            """处理状态切换的 HTTP 请求"""

            def log_message(self, format, *args):
                """静默日志，避免刷屏"""
                pass

            def do_GET(self):
                """GET 请求 - 获取当前状态"""
                parsed = urlparse(self.path)

                if parsed.path == "/api/status":
                    self._send_json({
                        "status": "ok",
                        "color": app_ref.current_color,
                        "blinking": app_ref.blinking,
                        "text": STATUS_TEXT.get(app_ref.current_color, ""),
                    })
                elif parsed.path == "/api/health":
                    self._send_json({"status": "running", "port": app_ref.port})
                elif parsed.path == "/" or parsed.path == "/index.html":
                    self._send_html_dashboard(app_ref.port)
                else:
                    self.send_error(404)

            def do_POST(self):
                """POST 请求 - 切换状态"""
                parsed = urlparse(self.path)

                if parsed.path == "/api/status":
                    content_length = int(
                        self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)
                    try:
                        data = json.loads(body) if body else {}
                        color = data.get("color", "").lower().strip()

                        valid_colors = ["red", "yellow", "green"]
                        if color not in valid_colors:
                            self._send_json({
                                "error": f"Invalid color. Must be one of: {valid_colors}"
                            }, 400)
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
                    content_length = int(
                        self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)
                    try:
                        data = json.loads(body) if body else {}
                        color = data.get("color", app_ref.current_color).lower()
                        times = data.get("times", 0)  # 0 = 无限闪烁
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
                """发送 JSON 响应"""
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

            def _send_html_dashboard(self, port):
                """发送 HTML 控制面板"""
                html = ('<!DOCTYPE html>\n'
'<html><head><meta charset="utf-8">\n'
'<title>Traffic Light Control</title>\n'
'<style>\n'
'* { margin:0; padding:0; box-sizing:border-box; }\n'
'body { font-family:"Segoe UI",system-ui,sans-serif; background:#1a1a2e; color:#eee; display:flex; justify-content:center; align-items:center; min-height:100vh; }\n'
'.card { background:#16213e; border-radius:16px; padding:32px; text-align:center; box-shadow:0 8px 32px rgba(0,0,0,0.4); }\n'
'h1 { font-size:20px; margin-bottom:24px; color:#e94560; }\n'
'.lights { display:flex; flex-direction:column; gap:8px; margin:20px auto; width:80px; }\n'
'.light-btn { width:70px; height:70px; border-radius:50%; border:3px solid #333; cursor:pointer; transition:all 0.3s ease; opacity:0.25; }\n'
'.light-btn.red { background:#ff3333; }\n'
'.light-btn.yellow { background:#ffd700; }\n'
'.light-btn.green { background:#33ff66; }\n'
'.light-btn.active { opacity:1; box-shadow:0 0 20px currentColor; }\n'
'.light-btn.red.active { color:#ff3333; box-shadow:0 0 20px #ff3333,0 0 40px rgba(255,51,51,0.3); }\n'
'.light-btn.yellow.active { color:#ffd700; box-shadow:0 0 20px #ffd700,0 0 40px rgba(255,215,0,0.3); }\n'
'.light-btn.green.active { color:#33ff66; box-shadow:0 0 20px #33ff66,0 0 40px rgba(51,255,102,0.3); }\n'
'.status { font-size:18px; font-weight:bold; margin-top:16px; min-height:27px; }\n'
'.status.red { color:#ff3333; }\n'
'.status.yellow { color:#ffd700; }\n'
'.status.green { color:#33ff66; }\n'
'.info { margin-top:20px; font-size:12px; color:#666; }\n'
'.btn-row { display:flex; gap:8px; justify-content:center; margin-top:16px; }\n'
'.action-btn { padding:6px 16px; border:none; border-radius:8px; cursor:pointer; font-size:13px; background:#0f3460; color:#fff; transition:background 0.2s; }\n'
'.action-btn:hover { background:#e94560; }\n'
'</style></head><body>\n'
'<div class="card">\n'
'<h1>🚦 Traffic Light</h1>\n'
'<div class="lights">\n'
"<div id=\"btn-red\" class=\"light-btn red\" onclick=\"setColor('red')\"></div>\n"
"<div id=\"btn-yellow\" class=\"light-btn yellow\" onclick=\"setColor('yellow')\"></div>\n"
"<div id=\"btn-green\" class=\"light-btn green\" onclick=\"setColor('green')\"></div>\n"
'</div>\n'
'<div id="status" class="status">--</div>\n'
'<div class="btn-row">\n'
'<button class="action-btn" onclick="toggleBlink()">Toggle Blink</button>\n'
'<button class="action-btn" onclick="stopBlink()">Stop</button>\n'
'</div>\n'
'<p class="info">API: POST http://localhost:{port}/api/status<br/>{{"color":"red|yellow|green"}}</p>\n'
'</div>\n'
'<script>\n'
'let currentColor = "red";\n'
'async function setColor(c) {\n'
'    const r = await fetch("/api/status", {\n'
'        method:"POST", headers:{"Content-Type":"application/json"},\n'
'        body: JSON.stringify({color:c})\n'
'    });\n'
'    const d = await r.json();\n'
'    currentColor = d.color;\n'
'    updateUI();\n'
'}\n'
'async function toggleBlink() {\n'
'    await fetch("/api/blink", {\n'
'        method:"POST", headers:{"Content-Type":"application/json"},\n'
'        body: JSON.stringify({color:currentColor})\n'
'    });\n'
'    setTimeout(updateUI, 300);\n'
'}\n'
'async function stopBlink() {\n'
'    await fetch("/api/stop-blink", {method:"POST"});\n'
'    setTimeout(updateUI, 300);\n'
'}\n'
'function updateUI() {\n'
'    fetch("/api/status").then(r=>r.json()).then(d=>{\n'
'        document.querySelectorAll(".light-btn").forEach(function(b){b.classList.remove("active");});\n'
'        document.getElementById("btn-"+d.color).classList.add("active");\n'
'        const s = document.getElementById("status");\n'
'        s.textContent = d.text || d.color;\n'
'        s.className = "status "+d.color;\n'
'    });\n'
'}\n'
'updateUI();\n'
'setInterval(updateUI, 2000);\n'
'</script></body></html>').format(port=port)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())

        def do_OPTIONS(self):
            """CORS preflight"""
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def handle_error(self, code, message=None):
            if code == 404:
                self._send_json({"error": "Not Found"}, 404)
            else:
                super().handle_error(code, message)

        server = HTTPServer((API_HOST, app_ref.port), StatusHandler)

        def serve_forever():
            print(f"[TrafficLight] API Server running at http://{API_HOST}:{app_ref.port}")
            print(f"[TrafficLight] Dashboard: http://{API_HOST}:{app_ref.port}/")
            server.serve_forever()

        thread = threading.Thread(target=serve_forever, daemon=True)
        thread.start()
        print(f"[TrafficLight] API server started on port {app_ref.port}")

    # --------------------------------------------------------
    # 状态控制接口
    # --------------------------------------------------------
    def set_status(self, color):
        """
        设置灯光状态（供外部调用）

        Args:
            color: "red" | "yellow" | "green"
        """
        if color in COLORS:
            self.target_color = color
            self.current_color = color
            self.animation_progress = 0.0  # 触发过渡动画
            # 停止闪烁
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
        print(f"[TrafficLight] Blinking {self.blink_color} ({'infinite' if times == 0 else f'{times}x'})")

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
        self.glow_phase += 0.08  # 呼吸动画相位递增

        # 闪烁逻辑
        if self.blinking:
            elapsed = time.time() * 1000
            if int(elapsed / BLINK_INTERVAL) % 2 == 0:
                self.blink_state = True
            else:
                self.blink_state = False

            if self.blink_times > 0:
                self.blink_count = int(elapsed / (BLINK_INTERVAL * 2))
                if self.blink_count >= self.blink_times:
                    self.stop_blink()

        # 过渡动画进度
        if self.animation_progress < 1.0:
            self.animation_progress = min(1.0, self.animation_progress + 0.08)

        # 继续下一帧
        self.root.after(UPDATE_INTERVAL, self._render_loop)

    def _draw(self):
        """绘制整个界面"""
        self.canvas.delete("all")

        cx = self.canvas.winfo_width() // 2
        light_r = self.light_size // 2

        # 绘制外框背景（深色圆角矩形）
        self._draw_frame(cx)

        # 绘制三个灯
        positions = [
            ("red", WINDOW_PADDING + light_r),
            ("yellow", WINDOW_PADDING + light_r * 2 + LIGHT_SPACING + light_r),
            ("green", WINDOW_PADDING + light_r * 4 + LIGHT_SPACING * 2 + light_r),
        ]

        for i, (color_name, cy) in enumerate(positions):
            is_active = (color_name == self.current_color)
            is_blink_on = self.blinking and color_name == self.blink_color and self.blink_state

            # 如果正在闪烁且是目标色，用闪烁状态覆盖
            if self.blinking and color_name == self.blink_color:
                is_active = is_blink_on

            self._draw_light(cx, cy, light_r, color_name, is_active)

        # 底部状态文字
        status_text = STATUS_TEXT.get(self.current_color, "")
        if self.blinking:
            status_text = "⚡ " + STATUS_TEXT.get(self.blink_color, "") + " ⚡"

        self.canvas.create_text(
            cx, self.canvas.winfo_height() - 12,
            text=status_text,
            fill="#AAAAAA",
            font=("Consolas", 9, "bold"),
        )

    def _draw_frame(self, cx):
        """绘制外框"""
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        r = 12  # 圆角半径

        # 外框圆角矩形
        self.canvas.create_rectangle(
            2, 2, w - 2, h - 30,  # 留出底部文字空间
            outline="#333344",
            width=2,
            fill="#111122",
        )

        # 顶部装饰线
        self.canvas.create_line(
            8, 6, w - 8, 6,
            fill="#334",
            width=1,
        )

    def _draw_light(self, cx, cy, r, color_name, is_active):
        """绘制单个灯泡"""
        colors = COLORS[color_name]

        if is_active:
            # ===== 亮灯状态 =====
            glow_intensity = 0.5 + 0.5 * math.sin(self.glow_phase)  # 呼吸效果 0~1

            # 外发光（多层渐变模拟）
            for i in range(4, 0, -1):
                glow_r = r + i * 5
                alpha_hex = hex(int(25 * glow_intensity / i))[2:].zfill(2)
                try:
                    glow_color = colors["glow"]
                    self.canvas.create_oval(
                        cx - glow_r, cy - glow_r,
                        cx + glow_r, cy + glow_r,
                        outline=glow_color,
                        width=2,
                    )
                except tk.TclError:
                    pass

            # 主灯泡 - 亮色填充
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=colors["on"],
                outline=colors["border"],
                width=2,
            )

            # 高光（左上角反光点）
            highlight_r = r * 0.3
            highlight_offset = r * 0.3
            self.canvas.create_oval(
                cx - highlight_offset - highlight_r,
                cy - highlight_offset - highlight_r,
                cx - highlight_offset + highlight_r,
                cy - highlight_offset + highlight_r,
                fill="white",
                outline="",
            )
            # 小高光点
            tiny_r = r * 0.12
            self.canvas.create_oval(
                cx - highlight_offset * 0.5 - tiny_r,
                cy - highlight_offset * 1.5 - tiny_r,
                cx - highlight_offset * 0.5 + tiny_r,
                cy - highlight_offset * 1.5 + tiny_r,
                fill="white",
                outline="",
            )
        else:
            # ===== 灭灯状态 =====
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=colors["off"],
                outline="#222233",
                width=1,
            )

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def run(self):
        """启动应用主循环"""
        print("[TrafficLight] * Traffic Light Started")
        print(f"[Traffic Light] Red=Idle | Yellow=Thinking | Green=Done")
        print(f"[TrafficLight] Double-click to toggle blink | Right-click for menu")
        print(f"[TrafficLight] Dashboard: http://{API_HOST}:{self.port}/")
        self.root.mainloop()

    def _quit(self):
        """退出应用"""
        self.root.quit()
        self.root.destroy()


# ============================================================
# CLI 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Claude Code 状态红绿灯 - Windows 桌面浮窗",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python traffic_light.py                          # 默认端口 9527
  python traffic_light.py --port 8080              # 自定义端口
  python traffic_light.py --size 100 --opacity 0.9 # 大灯泡 + 更透明

API 用法 (curl):
  curl -X POST http://localhost:9527/api/status -d '{"color":"yellow"}'
  curl -X POST http://localhost:9527/api/status     -d '{"color":"green","blink":true}'
  curl -X POST httplocalhost:9527/api/blink         -d '{"color":"yellow"}'
  curl -X POST http://localhost:9527/api/stop-blink
        """,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"API 监听端口 (默认: {DEFAULT_PORT})")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE,
                        help=f"灯泡直径像素 (默认: {DEFAULT_SIZE})")
    parser.add_argument("--opacity", type=float, default=DEFAULT_OPACITY,
                        help=f"窗口透明度 0~1 (默认: {DEFAULT_OPACITY})")
    args = parser.parse_args()

    app = TrafficLightApp(
        port=args.port,
        size=args.size,
        opacity=args.opacity,
    )
    app.run()


if __name__ == "__main__":
    main()
