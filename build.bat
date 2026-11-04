@echo off
chcp 65001 >nul
setlocal

if not exist .venv (
    echo [1/3] 创建虚拟环境
    python -m venv .venv || goto :fail
)

echo [2/3] 安装依赖
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
python -m pip install -q nuitka || goto :fail

echo [3/3] 打包
python -m nuitka ^
    --standalone ^
    --assume-yes-for-downloads ^
    --enable-plugin=pyside6 ^
    --windows-console-mode=disable ^
    --output-dir=build ^
    run.py || goto :fail

echo.
echo 完成：build\run.dist\run.exe
exit /b 0

:fail
echo.
echo 打包失败，看上面报错。
exit /b 1
