#!/bin/bash

set -euo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

DEFAULT_PAYLOAD='{"keywords":"CFO OR \u0022Head of Finance\u0022 OR \u0022Finance Controller\u0022 OR \u0022CA Partner\u0022","location":"India","target_count":10}'

echo "[$(date)] Creating linkedin_outreach_planner task run..."
python3 create_task_run.py linkedin_outreach_planner \
  --input-payload "$DEFAULT_PAYLOAD" \
  --requested-by "run_agent.sh" \
  --dispatch-if-runnable

echo "[$(date)] Planner run created. Dispatcher is running in the background."
echo "If a follow-up execution task requires approval, approve it via Telegram with APPROVE <RunID>."
