@echo off
chcp 65001 >nul
echo ============================================
echo   医美价目表批量维护工具 - 启动脚本
echo ============================================
echo.

cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "venv" (
    echo [信息] 首次启动，正在创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

if not exist "venv\Lib\site-packages\PySide6" (
    echo [信息] 正在安装依赖包（首次可能需要几分钟）...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if %errorlevel% neq 0 (
        echo [警告] 使用国内源安装失败，尝试官方源...
        pip install -r requirements.txt
    )
)

echo [信息] 启动应用...
python main.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序异常退出，错误码：%errorlevel%
    pause
)
