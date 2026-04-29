#!/bin/bash
# Confluence PDF Exporter — One-click launcher (macOS)
# start.sh 에 실행을 위임합니다 (conda / venv 자동 감지)
cd "$(dirname "$0")"

if [ ! -x start.sh ]; then
    chmod +x start.sh
fi

bash start.sh
