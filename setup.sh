#!/bin/bash
# Confluence PDF Exporter - 초기 설정 (macOS)
cd "$(dirname "$0")"

echo "=== Confluence PDF Exporter - 초기 설정 (macOS) ==="
echo

# conda 설치 여부 확인
if command -v conda &>/dev/null; then
    echo "[환경] Conda 감지됨 → Conda 환경으로 설정합니다."
    echo
    eval "$(conda shell.bash hook)"
    conda create -n confluence python=3.11 -y
    conda activate confluence
    pip install -r requirements.txt
    playwright install chromium
    echo
    echo "=== 설정 완료! start.sh 또는 'Conf. Exporter.command' 를 실행하세요 ==="
    echo "[실행 환경] Conda (confluence)"
else
    echo "[환경] Conda 없음 → Python venv 환경으로 설정합니다."
    echo
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium
    echo
    echo "=== 설정 완료! start.sh 를 실행하세요 ==="
    echo "[실행 환경] Python venv"
fi
