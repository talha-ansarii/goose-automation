import os
import logging
import subprocess
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load env variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")

# Setup logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip().upper()
    
    # Security: Only listen to the designated admin
    if user_id != ADMIN_ID:
        await update.message.reply_text("Unauthorized access.")
        return

    if text in ["YES", "APPROVE"]:
        await update.message.reply_text("Approval received! Updating Google Sheet status and waking up Goose Executive Agent...")
        
        # 1. Update the 'Pending' status to 'Approved' in Google Sheets
        # In a full implementation, you would use gspread here to mark the tab rows.
        # For now, we assume the execution agent just processes everything.

        # 2. Trigger Goose Execution in a subprocess
        logger.info("Executing Goose Runner...")
        try:
            my_env = os.environ.copy()
            my_env["GOOSE_PROVIDER"] = "google"
            my_env["GOOSE_MODEL"] = "gemini-3-flash-preview"
            
            log_file = open("execution.log", "w")
            
            subprocess.Popen(
                ["/opt/homebrew/bin/goose", "run", "--instructions", "execution_runner.md"],
                stdout=log_file,
                stderr=log_file,
                text=True,
                env=my_env,
                cwd=os.getcwd()  # Ensure it runs in the same directory
            )
            await update.message.reply_text("Goose execution sequence has been initiated in the background.")
        except Exception as e:
            await update.message.reply_text(f"Failed to start Goose: {str(e)}")
            
    else:
        await update.message.reply_text("Unrecognized command. Reply YES to approve pending drafts.")

async def strt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("NeoCFO Tele-Daemon is active. Listening for approvals...")

def main() -> None:
    if not TELEGRAM_TOKEN or not ADMIN_ID:
        logger.error("Missing TELEGRAM vars in .env")
        return
        
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", strt))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram daemon...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
