# Traffic Light helper for Claude Code hooks
# Usage:
#   tl.ps1 ensure                # 启动 electron 红绿灯（已存在则跳过），切绿灯
#   tl.ps1 red | yellow | green  # 直接切灯
#   tl.ps1 yellow blink          # 黄灯闪烁
#   tl.ps1 <clawd-state>         # 接受 Clawd-on-Desk 状态名自动映射
#                                  如 thinking / working / notification / attention 等
# All errors are swallowed silently.

param(
    [string]$ColorOrState = "",
    [string]$Mode  = ""
)

$ErrorActionPreference = "SilentlyContinue"

# 改成你本地 traffic-light/electron-app 的绝对路径
$TL_APP_DIR = "C:\path\to\traffic-light\electron-app"
$TL_EXE     = Join-Path $TL_APP_DIR "node_modules\electron\dist\electron.exe"

# Clawd-on-Desk 状态 -> 红绿灯颜色映射
$CLAWD_STATE_MAP = @{
    'idle'         = @{ color = 'green';  blink = $false }
    'thinking'     = @{ color = 'red';    blink = $false }
    'working'      = @{ color = 'red';    blink = $false }
    'typing'       = @{ color = 'red';    blink = $false }
    'juggling'     = @{ color = 'red';    blink = $false }
    'building'     = @{ color = 'red';    blink = $false }
    'headphones'   = @{ color = 'red';    blink = $false }
    'notification' = @{ color = 'yellow'; blink = $true  }
    'permission'   = @{ color = 'yellow'; blink = $true  }
    'attention'    = @{ color = 'green';  blink = $false }
    'happy'        = @{ color = 'green';  blink = $false }
    'error'        = @{ color = 'yellow'; blink = $true  }
    'sweeping'     = @{ color = 'red';    blink = $false }
    'carrying'     = @{ color = 'red';    blink = $false }
    'sleeping'     = @{ color = 'green';  blink = $false }

    # Claude Code 原始事件名也支持直接传入
    'SessionStart'   = @{ color = 'green';  blink = $false }
    'SessionEnd'     = @{ color = 'green';  blink = $false }
    'UserPromptSubmit'= @{ color = 'red';   blink = $false }
    'PreToolUse'     = @{ color = 'red';    blink = $false }
    'PostToolUse'    = @{ color = 'red';    blink = $false }
    'PostToolUseFailure' = @{ color = 'yellow'; blink = $true }
    'PermissionRequest'  = @{ color = 'yellow'; blink = $true }
    'Stop'           = @{ color = 'green';  blink = $false }
    'StopFailure'    = @{ color = 'yellow'; blink = $true }
    'SubagentStart'  = @{ color = 'red';    blink = $false }
    'SubagentStop'   = @{ color = 'red';    blink = $false }
    'PreCompact'     = @{ color = 'red';    blink = $false }
    'PostCompact'    = @{ color = 'green';  blink = $false }
    'WorktreeCreate' = @{ color = 'red';    blink = $false }
}

function Test-TLPort {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", 9527)
        $c.Close()
        return $true
    } catch {
        return $false
    }
}

function Set-TLColor([string]$col, [bool]$blink) {
    if ([string]::IsNullOrEmpty($col)) { return }
    if (-not (Test-TLPort)) { return }
    try {
        $body = @{ color = $col; blink = $blink } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri "http://127.0.0.1:9527/api/status" `
            -Method POST -ContentType "application/json" `
            -Body $body -TimeoutSec 2 | Out-Null
    } catch {}
}

function Resolve-TLState([string]$inputState) {
    $key = $inputState.Trim().ToLower()
    if ($CLAWD_STATE_MAP.ContainsKey($key)) {
        return $CLAWD_STATE_MAP[$key]
    }
    # 兼容原始大小写的 Claude Code 事件名
    if ($CLAWD_STATE_MAP.ContainsKey($inputState)) {
        return $CLAWD_STATE_MAP[$inputState]
    }
    # 兜底：按原始颜色处理
    if (@('red','yellow','green') -contains $key) {
        return @{ color = $key; blink = ($Mode -eq 'blink') }
    }
    return $null
}

try {
    if ($ColorOrState -eq "ensure") {
        if (-not (Test-TLPort)) {
            try {
                Start-Process `
                    -FilePath $TL_EXE `
                    -ArgumentList ".","--scale=2.5","--theme=dark","--port=9527" `
                    -WorkingDirectory $TL_APP_DIR
            } catch {}

            for ($i = 0; $i -lt 20; $i++) {
                Start-Sleep -Milliseconds 500
                if (Test-TLPort) { break }
            }
        }
        Set-TLColor "green" $false
        return
    }

    $resolved = Resolve-TLState $ColorOrState
    if ($resolved -eq $null) { return }

    Set-TLColor $resolved.color $resolved.blink
} catch {}
