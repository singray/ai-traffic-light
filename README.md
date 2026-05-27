# AI Traffic Light

> **AI 状态红绿灯** — 桌面悬浮交通信号灯，实时显示 AI 助手运行状态

[![Electron](https://img.shields.io/badge/Electron-28+-blue.svg)](https://www.electronjs.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()

## 它是什么？

一个轻量级桌面悬浮工具，通过 **HTTP API** 接收状态指令，用红灯 / 黄灯 / 绿灯直观显示当前工作状态：

| 灯色 | 含义 | 动画效果 | 典型场景 |
|:----:|------|---------|---------|
| 🔴 **红灯** | THINKING — 思考中 | 呼吸渐变 | AI 正在生成代码、调用工具 |
| 🟡 **黄灯** | WAITING — 等待确认 | 闪烁提醒 | 需要用户做选择/确认 |
| 🟢 **绿灯** | DONE — 完成 | 常亮 | 一轮任务执行完毕 |

## 核心特性

- **Electron 桌面应用** — 完美 CSS 发光/动画效果，100% 还原原型设计
- **系统托盘图标** — 任务栏右下角显示红绿灯图标，方便判断是否运行
- **置顶透明悬浮窗** — 始终在最前，可拖拽到任意位置
- **呼吸 + 闪烁动画** — 红灯呼吸渐变，黄灯闪烁提醒
- **内置 HTTP API** — 供任何脚本/hook 调用切换状态
- **右键设置面板** — 单灯模式、深色/浅色模式、窗口置顶
- **单灯/三灯模式** — 切换只显示当前状态灯或三灯竖排

---

## 快速开始

### 1️⃣ 安装依赖

```bash
git clone https://github.com/singray/ai-traffic-light.git
cd ai-traffic-light/electron-app
npm install
```

### 2️⃣ 启动

```bash
# 深色主题（默认）
npm start

# 或指定参数
npx electron . --scale=2.5 --theme=dark --port=9527
```

启动后桌面右上角出现红绿灯，任务栏右下角出现托盘图标。

### 3️⃣ 验证 API

```bash
# 红灯（思考中）
curl -X POST http://localhost:9527/api/status \
  -H "Content-Type: application/json" \
  -d '{"color":"red"}'

# 黄灯（等待确认）
curl -X POST http://localhost:9527/api/status \
  -H "Content-Type: application/json" \
  -d '{"color":"yellow"}'

# 绿灯（完成）
curl -X POST http://localhost:9527/api/status \
  -H "Content-Type: application/json" \
  -d '{"color":"green"}'
```

---

## 🔗 与 Claude Code / AI 助手集成

### Hooks 配置（推荐 ⭐）

在 `~/.claude/settings.json` 中添加 hooks，Claude Code 会在对应生命周期自动调用红绿灯 API：

```jsonc
// ~/.claude/settings.json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "*",
      "hooks": [{ "type": "command", "command": "curl -s -X POST http://localhost:9527/api/status -H \"Content-Type: application/json\" -d \"{\\\"color\\\":\\\"red\\\"}\"" }]
    }],
    "PreToolUse": [{
      "matcher": "Bash|Write|Edit|Read|Glob|Grep",
      "hooks": [{ "type": "command", "command": "curl -s -X POST http://localhost:9527/api/status -H \"Content-Type: application/json\" -d \"{\\\"color\\\":\\\"red\\\"}\"" }]
    }],
    "Stop": [{
      "matcher": "*",
      "hooks": [{ "type": "command", "command": "curl -s -X POST http://localhost:9527/api/status -H \"Content-Type: application/json\" -d \"{\\\"color\\\":\\\"green\\\"}\"" }]
    }]
  }
}
```

### HTTP 快捷调用

```bash
# 加入 ~/.bashrc 或 ~/.zshrc
alias tl='curl -s -X POST http://localhost:9527/api/status -H "Content-Type: application/json" -d'

tl '{"color":"red"}'      # 思考中
tl '{"color":"yellow"}'   # 等待确认
tl '{"color":"green"}'    # 完成
```

```powershell
# PowerShell（加入 $PROFILE）
function Set-TrafficLight {
    param([ValidateSet("red","yellow","green")][string]$Color)
    Invoke-RestMethod -Uri "http://localhost:9527/api/status" -Method POST `
        -ContentType "application/json" -Body (@{color=$Color} | ConvertTo-Json)
}
```

---

## API 文档

| 方法 | 路径 | 说明 |
|:---:|------|------|
| `POST` | `/api/status` | 设置灯光颜色 |
| `GET` | `/api/status` | 获取当前状态 |
| `GET` | `/api/health` | 健康检查 |

### 设置灯光 `POST /api/status`

**请求：**
```json
{ "color": "red" }    // "red" | "yellow" | "green"
```

**响应：**
```json
{ "status": "ok", "color": "red", "text": "THINKING" }
```

---

## 操作说明

| 操作 | 功能 |
|:-----|------|
| **左键拖拽** | 移动红绿灯位置 |
| **右键** | 打开设置面板 |
| **左键点击其他地方** | 关闭设置面板 |
| **托盘图标单击** | 显示/隐藏红绿灯 |
| **托盘图标右键** | 切换灯色 / 退出 |
| `Escape` | 关闭设置面板 |

## 启动参数

| 参数 | 默认值 | 说明 |
|:-----|:------:|------|
| `--scale` | `2.5` | 灯泡缩放比例 |
| `--theme` | `dark` | 主题 (`dark` / `light`) |
| `--port` | `9527` | API 监听端口 |
| `--dev` | - | 打开 DevTools |

---

## 项目结构

```
ai-traffic-light/
├── electron-app/
│   ├── main.js          # 主进程（窗口 + 托盘 + HTTP API）
│   ├── preload.js       # IPC 桥接
│   ├── index.html       # 红绿灯 UI
│   ├── settings.html    # 设置面板 UI
│   ├── assets/
│   │   └── icon.ico     # 托盘图标
│   └── package.json
├── README.md
└── LICENSE
```

## 技术栈

| 层 | 技术 | 说明 |
|:--:|:----:|------|
| UI 渲染 | HTML + CSS | CSS box-shadow 发光 + @keyframes 动画 |
| 桌面框架 | Electron 28+ | 无边框透明悬浮窗 + 系统托盘 |
| HTTP API | Node.js `http` | 内置 API 服务 |
| 通信 | Electron IPC | 主进程 ↔ 渲染进程双向同步 |

## 兼容性

任何能发起 HTTP 请求的程序都可以驱动红绿灯：

| 工具 | 集成方式 |
|:-----|:--------|
| Claude Code | Hooks 配置自动调用 |
| Cursor | Cursor Rules / 自定义脚本 |
| Copilot | VS Code Task |
| Aider | `--message-callback` |
| CI/CD | pipeline 中 curl 调用 |
| 自定义 Agent | HTTP POST 到 localhost:9527 |

## License

MIT License — 随意使用、修改、分发。
