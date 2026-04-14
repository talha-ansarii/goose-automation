This repository now uses task definitions and task runs instead of a single hardcoded execution prompt.

Use `prompt://linkedin_outreach_executor.md` in the `TaskDefinitions.Instructions` column for the execution task.

Recommended task definition:
- `TaskKey`: `linkedin_outreach_executor`
- `TaskName`: `LinkedIn Outreach Executor`
- `RequiresApproval`: `true`
- `Enabled`: `true`

Approve the target `RunID` through Telegram with `APPROVE <RunID>` or `YES <RunID>`, then let `task_dispatcher.py` execute that run.
