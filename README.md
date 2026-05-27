# claude-code-traffic-light

> **Claude Code 状态红绿灯** — 桌面悬浮交通信号灯，实时显示 AI 编程助手运行状态

[![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

![traffic-light-demo](docs/demo.png)

## 它是什么？

一个轻量级桌面浮窗工具，通过 **HTTP API** 接收状态指令，用**红灯 / 黄灯闪烁 / 绿灯** 直观显示当前工作状态：

| 灯色 | 含义 | 典型场景 |
|:----:|------|---------|
| 🔴 **红灯** | IDLE — 空闲 / 等待中 | Claude Code 启动后等待输入 |
| 🟡 **黄灯（闪烁）** | THINKING — 运行 / 思考中 | 正在调用工具、执行命令、生成代码 |
| 🟢 **绿灯** | DONE — 完成 / 成功 | 一轮任务执行完毕 |

## 核心特性

- **零依赖** — 纯 Python 标准库，无需 `pip install`
- **置顶透明悬浮窗** — 始终在最前，鼠标穿透不挡操作
- **可拖拽** — 按住左键拖到屏幕任意位置
- **呼吸发光 + 闪烁动画** — 黄灯自动闪烁提醒
- **内置 HTTP API** — 供任何脚本 / hook 调用切换状态
- **Web 控制面板** — 浏览器访问 `http://localhost:9527/`
- **右键菜单 / 双击闪烁** — 手动快捷操作
- **跨平台** — Windows / macOS / Linux

---

## 快速开始

### 1️⃣ 启动红绿灯

```bash
# 克隆仓库
git clone https://github.com/YOUR_USER/claude-code-traffic-light.git
cd claude-code-traffic-light

# 启动（默认端口 9527）
python traffic_light.py

# 或 Windows 双击启动
start.bat
```

启动后桌面右上角会出现红绿灯浮窗。打开浏览器访问：

```
http://localhost:9527/
```

即可看到 Web 控制面板，点击按钮就能手动切灯。

### 2️⃣ 验证 API 工作正常

```bash
# 黄灯（思考中）
curl -X POST http://localhost:9527/api/status \
  -H "Content-Type: application/json" \
  -d '{"color":"yellow"}'

# 绿灯（完成）
curl -X POST http://localhost:9527/api/status \
  -H "Content-Type: application/json" \
  -d '{"color":"green"}'

# 回到红灯（空闲）
curl -X POST http://localhost:9527/api/status \
  -H "Content-Type: application/json" \
  -d '{"color":"red"}'
```

---

## 🔗 与 Claude Code 集成（核心用法）

以下提供 **3 种方式** 从最简单到全自动，任选其一。

### 方式 A：Hooks 配置文件（推荐 ⭐）

在 `~/.claude/settings.json` 中添加 hooks，Claude Code 会在对应生命周期事件时**自动调用**红绿灯 API。

**完整可用配置：**

```jsonc
// ~/.claude/settings.json
{
  "hooks": {
    // ===== 用户提交问题时 → 黄灯闪烁（思考中）=====
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python /你的路径/hooks_claude.py yellow --blink"
          }
        ]
      }
    ],

    // ===== 一轮响应结束 → 绿灯（完成）=====
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python /你的路径/hooks_claude.py green"
          }
        ]
      }
    ],

    // ===== 开始使用工具时 → 确保黄灯亮起 =====
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit|Read|Glob|Grep|WebFetch|WebSearch",
        "hooks": [
          {
            "type": "command",
            "command": "python /你的路径/hooks_claude.py yellow --blink"
          }
        ]
      }
    ]
  }
}
```

> **如何找到 `/你的路径/`？**
>
> ```bash
> # 在项目目录下执行：
> pwd
> # 输出类似：C:/Users/你的用户名/projects/claude-code-traffic-light
> # 把反斜杠换成正斜杠填入上面的 command 即可
> ```

#### 配置步骤（给 Claude Code 看）

1. 确保 **红绿灯正在运行**（另开一个终端窗口 `python traffic_light.py`）
2. 编辑 `~/.claude/settings.json`（没有就新建），把上面 JSON 复制进去
3. 把 `/你的路径/` 替换为实际路径
4. 保存即可 — Claude Code 会自动检测配置变更（无需重启）

#### 验证是否生效

1. 打开 Claude Code，随便问一个问题
2. 观察桌面红绿灯 → 应该**立刻变黄并开始闪烁**
3. 等 Claude 回答完毕 → 应该**变绿**

如果没反应，检查：
- 红绿灯进程是否还在？终端有没有报错？
- settings.json 里路径对不对？
- 用 `curl` 手动测试一下 API 是否通

---

### 方式 B：自定义 Slash Command

创建一个自定义斜杠命令，让 Claude Code 在对话中主动控制红绿灯。

**创建命令文件：**

```bash
# 创建目录（如果没有的话）
mkdir -p ~/.claude/commands

# 写入命令定义
cat > ~/.claude/commands/traffic-light.md << 'EOF'
---
description: 切换桌面红绿灯状态
---

请根据用户意图切换交通信号灯状态：

- 用户说"开始"、"跑起来"、"思考"、"处理"、"执行"等 → 
  执行: python <TRAFFIC_LIGHT_PATH>/hooks_claude.py yellow --blink
  
- 用户说"好了"、"完成"、"done"、"成功"、"绿灯"等 → 
  执行: python <TRAFFIC_LIGHT_PATH>/hooks_claude.py green
  
- 用户说"停止"、"空闲"、"红灯"、"reset"等 → 
  执行: python <TRAFFIC_LIGHT_PATH>/hooks_claude.py red

先用 Bash 工具执行上述对应命令，然后简短告知用户状态已切换。
EOF
```

然后在 Claude Code 中输入 `/traffic-light yellow` 就能用了。

---

### 方式 C：直接 HTTP 调用

如果你有自己的脚本或自动化流程，可以直接调 REST API：

```bash
# 一行命令别名（加入 ~/.bashrc 或 ~/.zshrc）
alias tl='curl -s -X POST http://localhost:9527/api/status -H "Content-Type: application/json" -d'

tl '{"color":"yellow","blink":true}'   # 思考中（闪烁）
tl '{"color":"green"}'                   # 完成
tl '{"color":"red"}'                     # 空闲
```

```powershell
# PowerShell 函数（加入 $PROFILE）
function Set-TrafficLight {
    param([ValidateSet("red","yellow","green")][string]$Color, [switch]$Blink)
    $body = @{color=$Color; blink=!!$Blink} | ConvertTo-Json
    Invoke-RestMethod -Uri "http://localhost:9527/api/status" -Method POST `
        -ContentType "application/json" -Body $body
}

Set-TrafficLight yellow -Blink  # 思考中
Set-TrafficLight green           # 完成
Set-TrafficLight red             # 空闲
```

---

## API 完整文档

| 方法 | 路径 | 说明 |
|:---:|------|------|
| `POST` | `/api/status` | 设置灯光颜色 |
| `GET` | `/api/status` | 获取当前状态 |
| `POST` | `/api/blink` | 启动闪烁模式 |
| `POST` | `/api/stop-blink` | 停止闪烁 |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/` | Web 控制面板页面 |

### 设置灯光 `POST /api/status`

**请求：**
```json
{
  "color": "red",        // 必填: "red" | "yellow" | "green"
  "blink": false         // 可选: 是否闪烁（默认 false）
}
```

**响应：**
```json
{
  "status": "ok",
  "color": "red",
  "text": "IDLE"
}
```

### 闪烁控制 `POST /api/blink`

**请求：**
```json
{
  "color": "yellow",     // 可选: 闪烁颜色（默认当前色）
  "times": 0             // 可选: 闪烁次数（0 = 无限闪烁）
}
```

### 查询状态 `GET /api/status`

**响应：**
```json
{
  "status": "ok",
  "color": "green",
  "blinking": false,
  "text": "DONE"
}
```

---

## 操作说明

| 操作 | 功能 |
|:-----|------|
| **左键拖拽** | 移动窗口位置 |
| **双击窗口** | 切换当前灯的闪烁开关 |
| **右键** | 弹出菜单（手动选择红 / 黄 / 绿 / 退出） |
| `Ctrl+C` 终端 | 退出程序 |

## 启动参数

| 参数 | 默认值 | 说明 |
|:-----|:------:|------|
| `--port` | `9527` | API 监听端口号 |
| `--size` | `80` | 灯泡直径（像素） |
| `--opacity` | `0.92` | 窗口透明度（0.0 ~ 1.0） |

示例：

```bash
python traffic_light.py --port 8080 --size 100 --opacity 0.85
```

---

## 项目结构

```
claude-code-traffic-light/
├── traffic_light.py       # 主程序（UI + HTTP API 服务）
├── hooks_claude.py        # Claude Code Hook 调用脚本
├── start.bat              # Windows 一键启动脚本
├── README.md              # 本文档
└── LICENSE                # MIT 开源协议
```

## 技术栈

| 层 | 技术 | 说明 |
|:--:|:----:|------|
| UI 渲染 | Python `tkinter.Canvas` | 无第三方依赖 |
| HTTP API | Python `http.server` | 内置标准库 |
| 并发 | Python `threading` | API 后台线程运行 |
| 动画 | 主循环 ~60fps | 呼吸光晕 + 闪烁 |

**依赖：仅 Python 3.6+ 标准库，零 pip install。**

## 与其他 AI 编程助手兼容

本工具是**通用状态指示器**，不限于 Claude Code。任何能发起 HTTP 请求的程序都可以驱动它：

| 工具 | 集成方式 |
|:-----|:--------|
| Cursor | 通过 Cursor Rules / 自定义脚本调用 API |
| Windsurf / Codeium | 同上 |
| Copilot | VS Code Task 或 extension script |
| Aider | `--message-callback` / 自定义 hook |
| 任何 CI/CD | pipeline 步骤中 curl 调用 |
| 自定义 Agent | HTTP POST 到 localhost:9527 |

## License

MIT License — 随意使用、修改、分发。
