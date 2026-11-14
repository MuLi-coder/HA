@echo off
chcp 65001 >nul
title 知衡 · 一键放行手机访问
echo.
echo  ============================================
echo   知衡 · 让 Windows 防火墙允许手机连进来
echo  ============================================
echo.
echo  这个操作会给 8765 端口加一条「入站放行」规则，
echo  让手机通过局域网和 Tailscale 都能访问知衡。
echo.
echo  即将执行，如果弹出「用户账户控制」，点「是」。
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo  [!] 需要管理员权限。正在尝试以管理员身份重新启动...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall delete rule name="知衡-8765" >nul 2>&1
netsh advfirewall firewall add rule name="知衡-8765" dir=in action=allow protocol=TCP localport=8765 profile=any

if %errorlevel%==0 (
  echo.
  echo  [OK] 放行成功。
  echo.
  echo  现在用手机流量打开：  http://100.110.47.11:8765
  echo  （如果连不上，先确认手机上的 Tailscale 是打开状态）
) else (
  echo.
  echo  [X] 失败：请右键这个文件，选择「以管理员身份运行」。
)

echo.
pause
