import json
from typing import Any, Dict, Optional


def create_follow_on_run_for_approval(sheets: Any, run: Dict[str, Any], requested_by: str) -> Optional[Dict[str, Any]]:
    task_key = run.get("TaskKey")
    status = run.get("Status")

    if task_key == "linkedin_outreach_planner" and status == "Completed":
        sheets.approve_task_run(run["RunID"])
        executor_run = sheets.create_task_run(
            task_key="linkedin_outreach_executor",
            input_payload=json.dumps({"source_run_id": run["RunID"]}, ensure_ascii=True),
            requested_by=requested_by,
        )
        sheets.approve_task_run(executor_run["RunID"])
        return sheets.get_task_run(executor_run["RunID"])

    return None
