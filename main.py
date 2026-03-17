import os, logging

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN set nahi hai!")
    exit(1)

import json
_creds = os.environ.get("GOOGLE_CREDS_JSON", "")
if not _creds:
    print("ERROR: GOOGLE_CREDS_JSON set nahi hai!")
    exit(1)
try:
    json.loads(_creds)
except:
    print("ERROR: GOOGLE_CREDS_JSON valid JSON nahi hai!")
    exit(1)

from telegram.ext import (Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters)
from config import (SUPER_ADMIN_ID, REG_NAME, REG_PHONE,
    AA_NAME, AA_PHONE, AA_TID, AA_RATE, AA_SHEET,
    APP_NO, APP_DOB, APP_PASS, PAY_AMOUNT, AGENT_PAY_AMOUNT,
    BC_TYPE, BC_MSG, ABC_TYPE, ABC_MSG, UR_RATE)
from db import db
from handlers.registration import cmd_start, reg_name, reg_phone, cmd_cancel
from handlers.admin import (add_agent_start, aa_name, aa_phone, aa_tid, aa_rate, aa_sheet,
    find_agent, admin_bc_start, admin_bc_type_cb, admin_bc_send)
from handlers.agent import (broadcast_start, bc_type_cb, bc_content,
    rate_start, rate_save, pay_admin_start, pay_admin_amount)
from handlers.client import new_app_start, app_no, app_dob, app_pass
from handlers.callbacks import callback_router
from handlers.message_router import message_router, photo_router

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def debug_cmd(update, ctx):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return
    from db import all_agents, _aws, queue_today_count
    lines = ["🔧 DEBUG\n"]
    try:
        w    = _aws()
        rows = w.get_all_values() if w else []
        lines.append(f"agents tab: {len(rows)} rows")
        agents = all_agents()
        lines.append(f"all_agents(): {len(agents)}")
        for a in agents[:3]:
            lines.append(f"  {a.get('agent_name')} | {a.get('agent_id')} | {a.get('status')}")
    except Exception as e:
        lines.append(f"ERROR: {e}")
    try:
        q = queue_today_count()
        lines.append(f"Queue today: {q}")
    except Exception as e:
        lines.append(f"Queue error: {e}")
    await update.message.reply_text("\n".join(lines))


async def post_init(app):
    from jobs import register_jobs
    register_jobs(app)

def build_app():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # /start + registration
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            REG_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_phone)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # Add Agent
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^➕ Add Agent$"), add_agent_start)],
        states={
            AA_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_name)],
            AA_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_phone)],
            AA_TID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_tid)],
            AA_RATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_rate)],
            AA_SHEET: [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_sheet)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # New Application
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📋 New Application$"), new_app_start)],
        states={
            APP_NO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, app_no)],
            APP_DOB:  [MessageHandler(filters.TEXT & ~filters.COMMAND, app_dob)],
            APP_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, app_pass)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # Agent Broadcast
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📢 Broadcast$"), broadcast_start)],
        states={
            BC_TYPE: [CallbackQueryHandler(bc_type_cb, pattern=r"^BC_")],
            BC_MSG:  [MessageHandler(filters.TEXT & ~filters.COMMAND, bc_content),
                      MessageHandler(filters.PHOTO, bc_content)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # Admin Broadcast
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📢 Broadcast All$"), admin_bc_start)],
        states={
            ABC_TYPE: [CallbackQueryHandler(admin_bc_type_cb, pattern=r"^ABC_")],
            ABC_MSG:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bc_send),
                       MessageHandler(filters.PHOTO, admin_bc_send),
                       MessageHandler(filters.VOICE, admin_bc_send)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # Agent Pay Admin
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^💰 Pay Admin$"), pay_admin_start)],
        states={AGENT_PAY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pay_admin_amount)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # Update Rate
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^💰 Update Rate$"), rate_start)],
        states={UR_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rate_save)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    app.add_handler(CommandHandler("find_agent", find_agent))
    app.add_handler(CommandHandler("debug",      debug_cmd))
    app.add_handler(CommandHandler("cancel",     cmd_cancel))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, photo_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    return app


def main():
    logger.info("Connecting to Google Sheets...")
    if not db.connect():
        logger.error("Google Sheets connect nahi hua!")
        exit(1)
    logger.info("Starting FOS Bot v4...")
    app = build_app()
    logger.info("FOS Bot chal raha hai!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
