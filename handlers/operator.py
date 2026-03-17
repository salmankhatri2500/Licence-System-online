"""
handlers/operator.py  –  FOS v2
Operator can view + mark done queue items.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from keyboards import kb_operator, ik_queue_item
from db import (queue_pending, queue_all, queue_today_count,
                operator_by_tid, operators_enabled)
from utils import today_ist, ts_to_display, div

logger = logging.getLogger(__name__)


def _get_op(tid):
    if not operators_enabled():
        return None
    return operator_by_tid(tid)


async def op_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    op  = _get_op(tid)
    if not op:
        await update.message.reply_text("❌ Operator access nahi hai.")
        return
    pending = queue_pending()
    if not pending:
        await update.message.reply_text(
            "✅ Queue khali hai!", reply_markup=kb_operator())
        return
    await update.message.reply_text(
        f"⏳ *Pending Queue: {len(pending)}*",
        parse_mode="Markdown")
    for ap in pending[:20]:
        kb = ik_queue_item(ap["queue_id"], ap["client_code"],
                           ap["agent_id"], ap.get("agent_tid",0),
                           ap.get("client_tid",0))
        try:
            await update.message.reply_text(
                f"🆔 `{ap.get('queue_id')}`\n"
                f"📋 App No: *{ap.get('app_no')}*\n"
                f"🎂 DOB: {ap.get('dob')}\n"
                f"🔑 Password: `{ap.get('password')}`\n"
                f"━━━━━━━━━━━━━━\n"
                f"👤 {ap.get('client_name')} | `{ap.get('client_code')}`\n"
                f"👔 {ap.get('agent_name')}\n"
                f"🕐 {ts_to_display(ap.get('submitted_at',''))}",
                parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logger.warning(f"op_queue: {e}")
    await update.message.reply_text("━━━━━━━━━━━━━━", reply_markup=kb_operator())


async def op_done_apps(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    op  = _get_op(tid)
    if not op:
        await update.message.reply_text("❌ Operator access nahi hai.")
        return
    all_q = queue_all()
    done  = [r for r in all_q if r.get("status","").upper() == "DONE"]
    today = [r for r in done if r.get("done_at","").startswith(today_ist())]
    await update.message.reply_text(
        f"✅ *Done Apps*\n"
        f"━━━━━━━━━━━━━━\n"
        f"📅 Aaj: {len(today)}\n"
        f"📊 Total: {len(done)}",
        parse_mode="Markdown", reply_markup=kb_operator())


async def op_today_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    op  = _get_op(tid)
    if not op:
        await update.message.reply_text("❌ Operator access nahi hai.")
        return
    q = queue_today_count()
    await update.message.reply_text(
        f"📊 *Aaj ki Stats – {today_ist()}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"📥 Total: {q['total']}\n"
        f"✅ Done: {q['done']}  ⏳ Pending: {q['pending']}  🔒 Held: {q['held']}",
        parse_mode="Markdown", reply_markup=kb_operator())
