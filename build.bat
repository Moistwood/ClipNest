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
python -m pip install -q pyinstaller==6.22.3 || goto :fail

echo [3/4] 打包
python -m PyInstaller ^
    --noconfirm --clean --onedir --noconsole ^
    --name ClipNest ^
    --distpath dist ^
    --workpath build\pyinstaller ^
    --specpath build\pyinstaller ^
    run.py || goto :fail

echo [4/4] 整理产物
copy /Y LICENSE dist\ClipNest\ >nul
copy /Y README.md dist\ClipNest\ >nul

echo.
echo 完成：dist\ClipNest\ClipNest.exe（整个 ClipNest 目录一起分发）
exit /b 0

:fail
echo.
echo 打包失败，看上面报错。
exit /b 1
