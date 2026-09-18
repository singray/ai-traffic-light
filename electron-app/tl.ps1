# Traffic Light helper for Claude Code hooks
# Usage:
#   tl.ps1 ensure                # ensure electron app running (single-instance via named mutex), then set green
#   tl.ps1 red | yellow | green  # just set color
#   tl.ps1 yellow blink          # yellow + blinking
#   tl.ps1 <state-name>          # Clawd-on-Desk / Claude Code event name, auto-mapped
#                                # e.g. thinking / working / notification / UserPromptSubmit ...
# All errors are swallowed silently.
#
# Concurrency design (avoid "port 9527 in use" and process storms):
#   - Every socket op has a hard timeout (port probe 500ms, HTTP 2s).
#   - Only ONE session may start the app: a named mutex guards the
#     "probe -> start -> wait-ready" sequence. Other sessions just wait
#     for the port, they never spawn the app.
#   - A cooldown file records the last start attempt: if the app was
#     already started recently (e.g. it is still initializing slowly),
#     no duplicate is launched even after the mutex window closes.
#   - App side also has requestSingleInstanceLock() as the last line of defense.
#   - Log: %TEMP%\claude-tl.log (append-only, tiny).

param(
    [string]$Color = "",
    [string]$Mode  = ""
)

$ErrorActionPreference = "SilentlyContinue"

# ============================================================
# CONFIG - change this ONE line to your local electron-app path
# ============================================================
$TL_DIR           = "C:\path\to\traffic-light\electron-app"

$TL_EXE           = Join-Path $TL_DIR "node_modules\electron\dist\electron.exe"
$TL_PORT          = 9527
$TL_MUTEX         = "Local\ClaudeTrafficLightStart"
$TL_WAIT_SEC      = 10
$TL_COOLDOWN_SEC  = 180
$TL_STARTMARK     = Join-Path $env:TEMP "claude-tl-start.tick"

# ============================================================
# Clawd-on-Desk state -> traffic light color mapping
# Claude Code raw event names are also accepted directly.
# ============================================================
$CLAWD_STATE_MAP = @{
    'idle'         = @{ color = 'green';  blink = $false }
    'thinking'     = @{ color = 'red';    blink = $false }
    'working'      = @{ color = 'red';    blink = $false }
    'typing'       = @{ color = 'red';    blink = $false }
    'juggling'     = @{ color = 'red';    blink = $false }
    'building'     = @{ color = 'red';    blink = $false }
    'headphones'   = @{ color = 'red';    blink = $false }
    'sweeping'     = @{ color = 'red';    blink = $false }
    'carrying'     = @{ color = 'red';    blink = $false }
    'notification' = @{ color = 'yellow'; blink = $true  }
    'permission'   = @{ color = 'yellow'; blink = $true  }
    'error'        = @{ color = 'yellow'; blink = $true  }
    'attention'    = @{ color = 'green';  blink = $false }
    'happy'        = @{ color = 'green';  blink = $false }
    'sleeping'     = @{ color = 'green';  blink = $false }

    # Claude Code raw event names
    'SessionStart'       = @{ color = 'green';  blink = $false }
    'SessionEnd'         = @{ color = 'green';  blink = $false }
    'UserPromptSubmit'   = @{ color = 'red';    blink = $false }
    'PreToolUse'         = @{ color = 'red';    blink = $false }
    'PostToolUse'        = @{ color = 'red';    blink = $false }
    'PostToolUseFailure' = @{ color = 'yellow'; blink = $true  }
    'PermissionRequest'  = @{ color = 'yellow'; blink = $true  }
    'Stop'               = @{ color = 'green';  blink = $false }
    'StopFailure'        = @{ color = 'yellow'; blink = $true  }
    'SubagentStart'      = @{ color = 'red';    blink = $false }
    'SubagentStop'       = @{ color = 'red';    blink = $false }
    'PreCompact'         = @{ color = 'red';    blink = $false }
    'PostCompact'        = @{ color = 'green';  blink = $false }
    'WorktreeCreate'     = @{ color = 'red';    blink = $false }
}

function Write-TLLog([string]$msg) {
    try {
        $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff') [PID $PID] $msg`r`n"
        [System.IO.File]::AppendAllText("$env:TEMP\claude-tl.log", $line, [System.Text.Encoding]::UTF8)
    } catch {}
}

function Test-TLPort {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $task = $c.ConnectAsync("127.0.0.1", $TL_PORT)
        if (-not $task.Wait(500)) {
            $c.Close()
            return $false
        }
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
        Invoke-RestMethod -Uri "http://127.0.0.1:$TL_PORT/api/status" `
            -Method POST -ContentType "application/json" `
            -Body $body -TimeoutSec 2 | Out-Null
    } catch {}
}

function Wait-TLPort([int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
        if (Test-TLPort) { return $true }
    }
    return $false
}

function Get-LastStartSecAgo {
    try {
        $raw = [System.IO.File]::ReadAllText($TL_STARTMARK)
        $ticks = 0L
        if ([long]::TryParse($raw, [ref]$ticks)) {
            return [TimeSpan]::FromTicks([DateTime]::UtcNow.Ticks - $ticks).TotalSeconds
        }
    } catch {}
    return [double]::MaxValue
}

function Mark-StartAttempt {
    try {
        [System.IO.File]::WriteAllText($TL_STARTMARK, [string][DateTime]::UtcNow.Ticks, [System.Text.Encoding]::ASCII)
    } catch {}
}

function Start-TLApp {
    Write-TLLog "starting traffic-light electron app"
    try {
        Start-Process `
            -FilePath $TL_EXE `
            -ArgumentList ".","--scale=2.5","--theme=dark","--port=$TL_PORT" `
            -WorkingDirectory $TL_DIR
    } catch {
        Write-TLLog "start failed: $_"
    }
}

function Resolve-TLState([string]$inputState) {
    $key = $inputState.Trim().ToLower()
    if ($CLAWD_STATE_MAP.ContainsKey($key)) {
        return $CLAWD_STATE_MAP[$key]
    }
    # exact-case Claude Code event names
    if ($CLAWD_STATE_MAP.ContainsKey($inputState)) {
        return $CLAWD_STATE_MAP[$inputState]
    }
    # fallback: treat as raw color
    if (@('red','yellow','green') -contains $key) {
        return @{ color = $key; blink = ($Mode -eq 'blink') }
    }
    return $null
}

try {
    if ($Color -eq "ensure") {
        if (Test-TLPort) {
            Write-TLLog "service already up, skip start"
            Set-TLColor "green" $false
            return
        }

        # Named mutex: only ONE concurrent session may start the app.
        $mutex = $null
        $ownsMutex = $false
        try {
            $mutex = New-Object System.Threading.Mutex($false, $TL_MUTEX)
        } catch {}

        if ($null -ne $mutex) {
            try {
                $ownsMutex = $mutex.WaitOne(0)
            } catch [System.Threading.AbandonedMutexException] {
                # previous owner died without releasing; we now own it
                $ownsMutex = $true
            } catch {}
        }

        if ($ownsMutex) {
            try {
                # double-check inside the lock: the port may have come up
                # between our probe and acquiring the mutex
                if (-not (Test-TLPort)) {
                    $ago = Get-LastStartSecAgo
                    if ($ago -gt $TL_COOLDOWN_SEC) {
                        Mark-StartAttempt
                        Start-TLApp
                    } else {
                        Write-TLLog ("cooldown active (last start " + [math]::Round($ago,0) + "s ago), skip start")
                    }
                }
                # hold the lock until the port is ready or we time out,
                # so no other session can start a duplicate meanwhile
                [void](Wait-TLPort $TL_WAIT_SEC)
            } finally {
                try { $mutex.ReleaseMutex() } catch {}
            }
        } else {
            # another session is starting the app; just wait for the port
            Write-TLLog "another session is starting the app, waiting"
            [void](Wait-TLPort $TL_WAIT_SEC)
        }

        if (Test-TLPort) {
            Write-TLLog "service ready"
        } else {
            Write-TLLog "service not ready after wait, giving up"
        }
        Set-TLColor "green" $false
        return
    }

    # Clawd state / event name / raw color
    $resolved = Resolve-TLState $Color
    if ($null -eq $resolved) { return }

    Set-TLColor $resolved.color $resolved.blink
} catch {}
