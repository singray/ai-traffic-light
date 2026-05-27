#!/usr/bin/env python3
"""
Claude Code Hooks 集成脚本
==========================
将红绿灯状态与 Claude Code 运行生命周期绑定。

使用方式:
  1. 先启动 traffic_light.py
  2. 在 Claude Code 的 settings.json 或 hooks 中调用本脚本

示例:
  # 切换到思考状态（黄灯闪烁）
  python hooks_claude.py yellow

  # 切换到完成状态（绿灯）
  python hooks_claude.py green

  # 切换回空闲（红灯）
  python hooks_claude.py red

依赖:
  requests (可选, 用 urllib 也行)
"""

import sys
import json
import urllib.request
import urllib.error

DEFAULT_HOST = "http://127.0.0.1:9527"

VALID_COLORS = {"red", "yellow", "green"}


def set_traffic_light(color: str, host: str = "http://127.0.0.1:9527",
                      blink: bool = False) -> bool:
    """通过 HTTP API 切换红绿灯状态"""
    if color not in VALID_COLORS:
        print(f"[Error] Invalid color: '{color}'. Use: {VALID_COLORS}",
              file=sys.stderr)
        return False

    url = f"{host}/api/status"
    payload = json.dumps({"color": color, "blink": blink}).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            result = json.loads(resp.read().decode())
            print(f"✅ Traffic Light -> {color} ({result.get('text', '')})")
            return True
    except urllib.error.URLError:
        print(f"[Warning] Traffic Light not running at {host}", file=sys.stderr)
        print(f"[Hint] Start it first: python traffic_light.py", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print(f"\nUsage: python {sys.argv[0]} <red|yellow|green> [--blink]")
        print(f"\nExamples:")
        print(f"  python {sys.argv[0]} yellow --blink   # 黄灯闪烁(思考中)")
        print(f"  python {sys.argv[0]} green             # 绿灯亮(完成)")
        print(f"  python {sys.argv[0]} red               # 红灯亮(空闲)")
        sys.exit(1)

    color = sys.argv[1].lower()
    blink = "--blink" in sys.argv or "-b" in sys.argv

    host = DEFAULT_HOST
    for i, arg in enumerate(sys.argv):
        if arg in ("--host", "-h") and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]

    success = set_traffic_light(color, host, blink)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
