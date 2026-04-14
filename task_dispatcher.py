import argparse
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from neocfo_core import SheetsClient, create_temp_instructions_file, parse_json_payload, resolve_instructions_text

load_dotenv(override=True)

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def select_run(sheets: SheetsClient, run_id: str = "") -> Optional[Dict[str, Any]]:
    if run_id:
        run = sheets.get_task_run(run_id)
        approval_status = run.get("ApprovalStatus")
        status = run.get("Status")
        if status != "Queued":
            raise ValueError(f"Run {run_id} is not queued; current status is {status}.")
        if approval_status not in {"Approved", "NotNeeded"}:
            raise ValueError(f"Run {run_id} is not runnable; approval status is {approval_status}.")
        return run

    runnable = sheets.list_runnable_task_runs()
    if not runnable:
        return None
    runnable.sort(key=lambda item: item.get("CreatedAt", ""))
    return runnable[0]


def goose_binary() -> str:
    configured = os.getenv("GOOSE_BIN", "").strip()
    if configured:
        return configured
    found = shutil.which("goose")
    if found:
        return found
    return "/opt/homebrew/bin/goose"


def logs_dir() -> Path:
    path = Path(__file__).resolve().parent / "logs"
    path.mkdir(exist_ok=True)
    return path


def build_summary(task_key: str, run_id: str, log_path: Path) -> str:
    return f"Task {task_key} completed for run {run_id}. See dispatcher log at {log_path.name}."


def run_goose_for_task(run: Dict[str, Any]) -> Dict[str, Any]:
    run_id = run["RunID"]
    task_key = run["TaskKey"]
    task_definition = run.get("TaskDefinition", {})
    input_payload = parse_json_payload(run.get("InputPayload", "{}"))

    instructions_text = resolve_instructions_text(task_definition.get("Instructions", ""))
    instructions_path = create_temp_instructions_file(
        run_id=run_id,
        task_key=task_key,
        instructions_text=instructions_text,
        input_payload=input_payload,
    )

    goose_cmd = [
        goose_binary(),
        "run",
        "--instructions",
        instructions_path,
    ]

    env = os.environ.copy()
    env["GOOSE_PROVIDER"] = os.getenv("GOOSE_PROVIDER", "google")
    env["GOOSE_MODEL"] = os.getenv("GOOSE_MODEL", "gemini-3-flash-preview")
    env["NEOCFO_RUN_ID"] = run_id
    env["NEOCFO_TASK_KEY"] = task_key
    env["NEOCFO_INPUT_PAYLOAD"] = json.dumps(input_payload, ensure_ascii=True)

    log_path = logs_dir() / f"task-run-{run_id}.log"
    LOGGER.info("Starting Goose for run %s (%s). Live log: %s", run_id, task_key, log_path)

    with log_path.open("w", encoding="utf-8") as handle:
        try:
            completed = subprocess.run(
                goose_cmd,
                cwd=Path(__file__).resolve().parent,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        finally:
            Path(instructions_path).unlink(missing_ok=True)

    return {
        "returncode": completed.returncode,
        "log_path": log_path,
        "stdout": "",
        "stderr": "",
    }


def process_one_run(sheets: SheetsClient, run_id: str = "") -> bool:
    run = select_run(sheets, run_id)
    if not run:
        LOGGER.info("No runnable task runs found.")
        return False

    run_id = run["RunID"]
    task_key = run["TaskKey"]

    sheets.start_task_run(run_id)
    try:
        result = run_goose_for_task(run)
        if result["returncode"] != 0:
            error = f"Goose exited with status {result['returncode']}. See {result['log_path'].name}."
            sheets.fail_task_run(run_id, error)
            LOGGER.error("Run %s failed: %s", run_id, error)
            return True
        summary = build_summary(task_key, run_id, result["log_path"])
        sheets.complete_task_run(run_id, summary)
        LOGGER.info("Run %s completed.", run_id)
        return True
    except Exception as exc:
        sheets.fail_task_run(run_id, str(exc))
        LOGGER.exception("Run %s failed unexpectedly.", run_id)
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="NeoCFO single-dispatch task runner")
    parser.add_argument("--run-id", help="Process a specific run id if it is runnable.")
    parser.add_argument("--loop", action="store_true", help="Keep polling for new runnable runs.")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between loop polls.")
    args = parser.parse_args()

    sheets = SheetsClient()
    if not sheets.configured():
        raise SystemExit("GOOGLE_APPS_SCRIPT_URL is required.")

    if args.loop:
        while True:
            processed = process_one_run(sheets, run_id=args.run_id or "")
            if args.run_id:
                break
            if not processed:
                time.sleep(args.poll_interval)
    else:
        process_one_run(sheets, run_id=args.run_id or "")


if __name__ == "__main__":
    main()
