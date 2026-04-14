import argparse
import logging
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from neocfo_core import SheetsClient, parse_json_payload

load_dotenv(override=True)

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a NeoCFO task run")
    parser.add_argument("task_key", help="TaskDefinitions.TaskKey to enqueue")
    parser.add_argument("--input-payload", default="{}", help="JSON object payload passed to the task run")
    parser.add_argument("--requested-by", default="cli", help="Operator or system label for the run")
    parser.add_argument("--dispatch-if-runnable", action="store_true", help="Start dispatcher immediately if approval is not needed.")
    args = parser.parse_args()

    parse_json_payload(args.input_payload)

    sheets = SheetsClient()
    run = sheets.create_task_run(task_key=args.task_key, input_payload=args.input_payload, requested_by=args.requested_by)
    print(f"Created run {run['RunID']} for task {run['TaskKey']} with approval={run['ApprovalStatus']}")

    if args.dispatch_if_runnable and run["ApprovalStatus"] == "NotNeeded":
        base_dir = Path(__file__).resolve().parent
        log_dir = base_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        dispatch_log = log_dir / f"dispatch-{run['RunID']}.log"
        with dispatch_log.open("w", encoding="utf-8") as handle:
            subprocess.Popen(
                [sys.executable, str(base_dir / "task_dispatcher.py"), "--run-id", run["RunID"]],
                cwd=base_dir,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        print(f"Dispatcher started in background. Follow progress with: tail -f {dispatch_log}")


if __name__ == "__main__":
    main()
