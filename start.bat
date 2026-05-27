@echo off
chcp 65001 >nul
title 🚦 Traffic Light - Claude Code Status
echo ============================================
echo   Claude Code 状态红绿灯
echo ==================================
echo.
echo   API: http://localhost:9527
echo   控制面板: http://localhost:9527/
echo.
echo   红灯 = 空闲  |  黄灯 = 思考中  |  绿灯 = 完成
echo   双击切换闪烁  |  右键菜单
echo   Ctrl+C 退出
echo ============================================
echo.

cd /d "%~dp0"
python traffic_light.py %*

pause
