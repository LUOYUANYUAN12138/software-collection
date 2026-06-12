@echo off
chcp 65001 >nul 2>&1

echo ==========================================
echo   Claude Code Services Launcher
echo ==========================================
echo.

:: Service 1: claude-code-proxy
echo [1/2] Starting claude-code-proxy ...
start "claude-code-proxy" cmd /k "cd /d D:\claudecode安装\claude-code-proxy && python start_proxy.py"

:: Wait 2 seconds before starting the second service
timeout /t 2 /nobreak >nul 2>&1

:: Service 2: hw-llm-adapter
echo [2/2] Starting hw-llm-adapter ...
start "hw-llm-adapter" cmd /k "cd /d D:\claudecode安装\hw-llm-adapter && hw-llm-adapter.exe --zone green --enable-codemate-api --port 8088"

echo.
echo ==========================================
echo   Both services launched!
echo   Close the windows to stop them.
echo ==========================================
timeout /t 5 /nobreak >nul 2>&1
