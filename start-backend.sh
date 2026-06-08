#!/bin/bash
cd "$(dirname "$0")/backend"
source venv/bin/activate
mkdir -p logs
uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | tee logs/backend.log
