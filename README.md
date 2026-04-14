# NeoCFO Multi-Task Automation Platform

This project now runs as a small task orchestration platform instead of a single hardcoded outreach agent.

## Architecture
- `TaskDefinitions` in Google Sheets define reusable automations.
- `TaskRuns` enqueue isolated executions of those automations.
- `TaskActions` store draft and execution-level audit rows for tasks that create multiple actions.
- `task_dispatcher.py` is the single dispatcher that locks one runnable run and executes it with Goose.
- `telegram_listener.py` is the admin approval surface for run-scoped approvals.
- `agent_skills.py` exposes the Sheets, Unipile, and Telegram tools to Goose via MCP.

## Required Sheets Tabs And Headers
Deploy `apps_script.js` as the Google Apps Script Web App attached to your spreadsheet. The script will ensure these tabs exist and will reset their headers if they differ:

- `Leads`
  - `ProfileID`, `Name`, `Headline`, `Location`, `Status`, `LastContactAt`, `LastActionType`, `LastActionResult`, `Notes`
- `TaskDefinitions`
  - `TaskKey`, `TaskName`, `Description`, `Instructions`, `Toolset`, `InputSchemaHint`, `RequiresApproval`, `Enabled`
- `TaskRuns`
  - `RunID`, `TaskKey`, `InputPayload`, `Status`, `ApprovalStatus`, `CreatedAt`, `StartedAt`, `FinishedAt`, `Summary`, `Error`, `RequestedBy`
- `TaskActions`
  - `ActionID`, `RunID`, `EntityID`, `ActionType`, `Content`, `DraftStatus`, `ExecutionStatus`, `ExecutionError`, `CreatedAt`, `ExecutedAt`

## Bootstrap Task Definitions
Add these rows to `TaskDefinitions`:

1. `linkedin_outreach_planner`
   - `TaskName`: `LinkedIn Outreach Planner`
   - `Description`: `Search prospects and draft outreach actions`
   - `Instructions`: `prompt://linkedin_outreach_planner.md`
   - `Toolset`: `search_linkedin,create_task_action,get_leads_by_status,notify_human_for_approval`
   - `InputSchemaHint`: `{"keywords":"string","location":"string","target_count":"number"}`
   - `RequiresApproval`: `false`
   - `Enabled`: `true`
2. `linkedin_outreach_executor`
   - `TaskName`: `LinkedIn Outreach Executor`
   - `Description`: `Execute approved outreach actions for one run`
   - `Instructions`: `prompt://linkedin_outreach_executor.md`
   - `Toolset`: `list_task_actions,send_connection_request,send_linkedin_message,mark_task_action_result,update_lead_status,notify_human_for_approval`
   - `InputSchemaHint`: `{"source_run_id":"string"}`
   - `RequiresApproval`: `true`
   - `Enabled`: `true`

## Environment
Copy `.env.example` to `.env` and fill in:
- `UNIPILE_DSN`
- `UNIPILE_ACCESS_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_ID`
- `GOOGLE_APPS_SCRIPT_URL`
- optional Goose overrides: `GOOSE_BIN`, `GOOSE_PROVIDER`, `GOOSE_MODEL`

## Local Startup Order
1. Install dependencies:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
2. Start the Telegram approval bot:
   - `python3 telegram_listener.py`
3. Create and dispatch a planner run:
   - `./run_agent.sh`
   - or `python3 create_task_run.py linkedin_outreach_planner --input-payload '{"keywords":"CFO","location":"India","target_count":10}' --requested-by "manual" --dispatch-if-runnable`
4. If a run requires approval, approve it in Telegram with:
   - `APPROVE <RunID>`

## Creating New Tasks
To add a new automation:
1. Add a new row to `TaskDefinitions`.
2. Set `Instructions` either to inline text or a repo prompt reference like `prompt://my_task.md`.
3. Set `RequiresApproval` and `Enabled`.
4. Create a run using `create_task_run.py` or the Apps Script API.

The dispatcher does not need code changes for a new task definition as long as the required tools already exist.

## Approval And Execution
- A new run enters `TaskRuns` with `Status=Queued`.
- If the task definition requires approval, `ApprovalStatus=Pending`; otherwise it is `NotNeeded`.
- The dispatcher only executes runs that are `Queued` and either `Approved` or `NotNeeded`.
- Planner-style tasks can create draft `TaskActions`.
- Approving a run also approves its draft actions.
- The executor task should only process `TaskActions` for its own `RunID` with `DraftStatus=Approved` and `ExecutionStatus=Pending`.
- The LinkedIn executor sends a Telegram alert after each successful invite, and a final summary at the end of the run.

## Failure Handling
- Use `/queue` in Telegram to inspect queued runs.
- Use `/status <RunID>` to inspect one run.
- Dispatcher logs are written to `logs/task-run-<RunID>.log`.
- Telegram-triggered dispatch writes `logs/telegram-dispatch-<RunID>.log`.
- Failed task runs store the final error in `TaskRuns.Error`.
- Failed task actions store the execution reason in `TaskActions.ExecutionError`.

## Tests
Run the local test suite with:

```bash
python3 -m unittest discover -s tests
```
