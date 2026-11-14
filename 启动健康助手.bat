@echo off
chcp 65001 >nul
title 知衡 · 个人健康助手
cd /d "%~dp0"

rem ---- 找到 Python ----
set "PY=python"
where python >nul 2>nul
if %errorlevel% neq 0 (
  where py >nul 2>nul
  if %errorlevel% neq 0 (
    echo.
    echo  [错误] 没有找到 Python。
    echo  请先安装 Python 3.x（python.org 下载），安装时务必勾选
    echo  "Add python.exe to PATH"，然后重新双击本文件。
    echo.
    pause
    exit /b 1
  )
  set "PY=py -3"
)

echo.
echo  正在启动「知衡」...
echo  启动后会自动打开浏览器；关闭本黑色窗口即可退出程序。
echo.

%PY% server.py

echo.
pause
