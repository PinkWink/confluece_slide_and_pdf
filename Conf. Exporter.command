#!/bin/bash
# Confluence PDF Exporter — One-click launcher
# Double-click this file to start the web GUI

cd "$(dirname "$0")"

# Initialize conda
eval "$(conda shell.bash hook)"
conda activate confluence

echo "Starting Confluence PDF Exporter..."
echo "Opening http://localhost:5001 in your browser..."
echo ""

# Open browser after a short delay (background)
(sleep 2 && open http://localhost:5001) &

# Start Flask server (foreground — closing this window stops the server)
python app.py
