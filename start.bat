@echo off
echo === Confluence PDF Exporter 시작 중... (Windows) ===
echo.

:: conda 환경 우선 확인
where conda >nul 2>&1
if %ERRORLEVEL% == 0 (
    call conda activate confluence 2>nul
    if %ERRORLEVEL% == 0 (
        echo [환경] Conda ^(confluence^)
        goto :run
    )
)

:: conda 없거나 confluence 환경 없으면 venv 사용
if exist venv\Scripts\activate (
    call venv\Scripts\activate
    echo [환경] Python venv
    goto :run
)

echo [오류] 실행 환경을 찾을 수 없습니다.
echo setup.bat 을 먼저 실행해주세요.
pause
exit /b 1

:run
echo.
start /b cmd /c "timeout /t 2 >nul && start http://localhost:5001"
python app.py
