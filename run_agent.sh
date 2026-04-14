#!/bin/bash

# Configuration and path setup
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Source environment variables automatically if .env exists
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# 2. Start Goose with the daily planner
echo "[$(date)] Starting NeoCFO Autonomous Daily Planner..."
export GOOSE_PROVIDER="google"
export GOOSE_MODEL="gemini-3-flash-preview"
/opt/homebrew/bin/goose run --instructions daily_planner.md

echo "[$(date)] Planning completed. Agent is paused pending human approval via Telegram."
