This repository now uses task definitions and task runs instead of a single hardcoded planner prompt.

Use `prompt://linkedin_outreach_planner.md` in the `TaskDefinitions.Instructions` column for the planning task.

Recommended task definition:
- `TaskKey`: `linkedin_outreach_planner`
- `TaskName`: `LinkedIn Outreach Planner`
- `RequiresApproval`: `false`
- `Enabled`: `true`

Create a run with `create_task_run.py` or directly through the Apps Script API, then let `task_dispatcher.py` execute it.
