#!/bin/bash
# Confluence PDF Exporter - 런처 (macOS)
cd "$(dirname "$0")"

echo "=== Confluence PDF Exporter 시작 중... (macOS) ==="
echo

# conda 환경 우선 확인
if command -v conda &>/dev/null; then
    eval "$(conda shell.bash hook)"
    conda activate confluence 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "[환경] Conda (confluence)"
        (sleep 2 && open http://localhost:5001) &
        python app.py
        exit 0
    fi
fi

# venv 확인
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
    echo "[환경] Python venv"
    (sleep 2 && open http://localhost:5001) &
    python app.py
    exit 0
fi

echo "[오류] 실행 환경을 찾을 수 없습니다."
echo "setup.sh 를 먼저 실행해주세요."
echo "  chmod +x setup.sh && ./setup.sh"
