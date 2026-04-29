@echo off
echo === Confluence PDF Exporter - 초기 설정 (Windows) ===
echo.

:: conda 설치 여부 확인
where conda >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [환경] Conda 감지됨 → Conda 환경으로 설정합니다.
    echo.
    call conda create -n confluence python=3.11 -y
    call conda activate confluence
    pip install -r requirements.txt
    playwright install chromium
    echo.
    echo === 설정 완료! start.bat 을 실행하세요 ===
    echo [실행 환경] Conda ^(confluence^)
) else (
    echo [환경] Conda 없음 → Python venv 환경으로 설정합니다.
    echo.
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
    playwright install chromium
    echo.
    echo === 설정 완료! start.bat 을 실행하세요 ===
    echo [실행 환경] Python venv
)

pause
