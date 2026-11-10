#!/bin/bash
set -e

if [ "$SERVICE" = "api" ]; then
    exec uvicorn app.api:app --host 0.0.0.0 --port 8000
elif [ "$SERVICE" = "ui" ]; then
    exec streamlit run ui.py --server.port 8501 --server.address 0.0.0.0
else
    echo "Set SERVICE=api or SERVICE=ui"
    exit 1
fi
