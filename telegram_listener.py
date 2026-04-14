import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from neocfo_core import SheetsClient
from neocfo_workflows import create_follow_on_run_for_approval

load_dotenv(override=True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
LOGGER = logging.getLogger(__name__)

sheets = SheetsClient()


def is_admin(update: Update) -> bool:
    message = update.effective_message
    user = message.from_user if message else None
    return bool(user and str(user.id) == str(ADMIN_ID))


def launch_dispatcher(run_id: str) -> None:
    log_path = BASE_DIR / "logs" / f"telegram-dispatch-{run_id}.log"
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        subprocess.Popen(
            [sys.executable, str(BASE_DIR / "task_dispatcher.py"), "--run-id", run_id],
            stdout=handle,
            stderr=handle,
            cwd=BASE_DIR,
            env=os.environ.copy(),
            text=True,
        )


def parse_run_id(text: str) -> str:
    parts = text.strip().split()
    if len(parts) < 2:
        return ""
    return parts[1].strip()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Unauthorized access.")
        return
    await update.effective_message.reply_text(
        "NeoCFO task bot is active. Use `APPROVE <RunID>`, `/status <RunID>`, or `/queue`."
    )


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Unauthorized access.")
        return
    queued = sheets.list_task_runs(status="Queued", approval_status="")
    if not queued:
        await update.effective_message.reply_text("No queued task runs.")
        return

    lines = []
    for run in queued[:10]:
        lines.append(
            f"{run['RunID']} | {run['TaskKey']} | status={run['Status']} | approval={run['ApprovalStatus']}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Unauthorized access.")
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /status <RunID>")
        return
    run_id = context.args[0]
    try:
        run = sheets.get_task_run(run_id)
    except Exception as exc:
        await update.effective_message.reply_text(str(exc))
        return

    message = (
        f"Run {run['RunID']}\n"
        f"Task: {run['TaskKey']}\n"
        f"Status: {run['Status']}\n"
        f"Approval: {run['ApprovalStatus']}\n"
        f"Created: {run['CreatedAt']}\n"
        f"Started: {run['StartedAt'] or '-'}\n"
        f"Finished: {run['FinishedAt'] or '-'}\n"
        f"Summary: {run['Summary'] or '-'}\n"
        f"Error: {run['Error'] or '-'}"
    )
    await update.effective_message.reply_text(message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Unauthorized access.")
        return

    text = (update.effective_message.text or "").strip()
    upper_text = text.upper()

    if upper_text.startswith("APPROVE ") or upper_text.startswith("YES "):
        run_id = parse_run_id(text)
        if not run_id:
            await update.effective_message.reply_text("Use `APPROVE <RunID>` or `YES <RunID>`.")
            return
        try:
            run = sheets.get_task_run(run_id)
            follow_on_run = create_follow_on_run_for_approval(sheets, run, requested_by=f"telegram:{ADMIN_ID}")
            if follow_on_run:
                launch_dispatcher(follow_on_run["RunID"])
                await update.effective_message.reply_text(
                    "Approved draft actions from planner run "
                    f"{run['RunID']}. Created executor run {follow_on_run['RunID']} and started dispatch."
                )
            else:
                approved_run = sheets.approve_task_run(run_id)
                launch_dispatcher(run_id)
                await update.effective_message.reply_text(
                    f"Approved run {approved_run['RunID']} for task {approved_run['TaskKey']}. Dispatcher started."
                )
        except Exception as exc:
            await update.effective_message.reply_text(f"Approval failed: {exc}")
        return

    if upper_text.startswith("REJECT "):
        run_id = parse_run_id(text)
        if not run_id:
            await update.effective_message.reply_text("Use `REJECT <RunID>`.")
            return
        try:
            run = sheets.reject_task_run(run_id)
            await update.effective_message.reply_text(f"Rejected run {run['RunID']} for task {run['TaskKey']}.")
        except Exception as exc:
            await update.effective_message.reply_text(f"Rejection failed: {exc}")
        return

    await update.effective_message.reply_text(
        "Unrecognized command. Use `APPROVE <RunID>`, `YES <RunID>`, `/status <RunID>`, or `/queue`."
    )


def main() -> None:
    if not TELEGRAM_TOKEN or not ADMIN_ID:
        LOGGER.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_ID in environment.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    LOGGER.info("Starting Telegram task listener.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
