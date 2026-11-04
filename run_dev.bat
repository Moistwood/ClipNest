@echo off
chcp 65001 >nul
title ClipNest 本地运行
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 没有找到虚拟环境 .venv
    echo 先在项目目录执行:  python -m venv .venv
    echo 然后执行:  .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo 正在启动 ClipNest ...
echo.
echo 程序启动后会缩到右下角托盘，按 Ctrl+Alt+V 呼出面板。
echo 要退出，右键托盘图标选「退出」，直接关这个黑窗口是不会退出的。
echo 如果启动时报错，下面会打印原因，把内容发给我。
echo.

".venv\Scripts\python.exe" run.py

echo.
echo 程序已退出，返回码 %ERRORLEVEL%
pause
