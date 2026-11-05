@echo off
chcp 65001 >nul
setlocal

if not exist .venv (
    echo [1/4] 创建虚拟环境
    python -m venv .venv || goto :fail
)

echo [2/4] 安装依赖
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
python -m pip install -q nuitka || goto :fail

echo [3/4] 打包
python -m nuitka ^
    --standalone ^
    --assume-yes-for-downloads ^
    --enable-plugin=pyside6 ^
    --windows-console-mode=disable ^
    --output-dir=build ^
    run.py || goto :fail

echo [4/4] 整理产物
move /Y build\run.dist\run.exe build\run.dist\ClipNest.exe >nul || goto :fail
copy /Y LICENSE build\run.dist\ >nul
copy /Y README.md build\run.dist\ >nul

echo.
echo 完成：build\run.dist\ClipNest.exe（整个 run.dist 目录一起分发）
exit /b 0

:fail
echo.
echo 打包失败，看上面报错。
exit /b 1
