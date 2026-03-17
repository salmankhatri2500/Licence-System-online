"""
handlers/registration.py  –  FOS v2
/start, registration flow, cancel.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config import REG_NAME, REG_PHONE
from keyboards import kb_admin, kb_agent, kb_client, kb_operator, REMOVE
from db import (agent_by_id, agent_by_tid, find_client, add_client,
                detect_role, agent_active, operator_by_tid,
                operator_by_phone, set_operator_field, operators_enabled)
from utils import user_data, gen_client_code, valid_phone

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    args = ctx.args or []

    # ── Referral registration ────────────────────────────────
    if args and args[0].startswith("register_"):
        agent_id = args[0].replace("register_", "")
        agent    = agent_by_id(agent_id)

        if not agent or not agent_active(agent):
            await update.message.reply_text(
                "❌ *Link invalid ya agent active nahi.*\n"
                "Agent se naya link maango.",
                parse_mode="Markdown")
            return ConversationHandler.END

        c, _ = find_client(tid)
        if c:
            await update.message.reply_text(
                f"✅ *Already Registered!*\n"
                f"🆔 Client ID: `{c.get('client_code')}`",
                parse_mode="Markdown",
                reply_markup=kb_client())
            return ConversationHandler.END

        ud = user_data(tid)
        ud["reg_agent_id"] = agent_id
        ud.pop("full_name", None)

        await update.message.reply_text(
            f"🏢 *Faiz Online Service*\n\n"
            f"👔 Agent: *{agent.get('agent_name')}*\n\n"
            f"📝 Step 1/2 – Apna poora naam likhiye:",
            parse_mode="Markdown",
            reply_markup=REMOVE)
        return REG_NAME

    # ── Operator link ────────────────────────────────────────
    if args and args[0].startswith("operator_"):
        phone = args[0].replace("operator_", "")
        op    = operator_by_phone(phone)
        if not op:
            await update.message.reply_text(
                "❌ Operator link invalid.\nAdmin se contact karo.")
            return ConversationHandler.END
        if str(op.get("telegram_id","")).strip() not in ("", "0"):
            await update.message.reply_text(
                "✅ Aap pehle se registered operator hain.",
                reply_markup=kb_operator())
            return ConversationHandler.END
        # Bind TID
        set_operator_field(op["op_id"], "telegram_id", str(tid))
        set_operator_field(op["op_id"], "op_name",
                           update.effective_user.first_name or "Operator")
        await update.message.reply_text(
            f"✅ *Operator Panel Access Mila!*\n\n"
            f"Welcome {update.effective_user.first_name or ''}!\n"
            f"Aap ab queue process kar sakte hain.",
            parse_mode="Markdown",
            reply_markup=kb_operator())
        return ConversationHandler.END

    # ── Normal /start ────────────────────────────────────────
    role = detect_role(tid)

    if role == "admin":
        await update.message.reply_text(
            f"👑 *Welcome Admin!*\n"
            f"🏢 Faiz Online Service\n\n"
            f"Sabhi features niche ke buttons se use karein.",
            parse_mode="Markdown",
            reply_markup=kb_admin())

    elif role == "agent":
        ag = agent_by_tid(tid)
        if not agent_active(ag):
            await update.message.reply_text(
                "⛔ *Account Block Hai*\nAdmin se contact karo.",
                parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"👔 *Welcome {ag.get('agent_name')}!*\n"
                f"Aapka agent panel ready hai.",
                parse_mode="Markdown",
                reply_markup=kb_agent())

    elif role == "client":
        c, _ = find_client(tid)
        await update.message.reply_text(
            f"👤 *Welcome {c.get('full_name')}!*\n"
            f"🆔 ID: `{c.get('client_code')}`",
            parse_mode="Markdown",
            reply_markup=kb_client())

    elif role == "operator":
        op = operator_by_tid(tid)
        await update.message.reply_text(
            f"🔧 *Welcome Operator {op.get('op_name','') or ''}!*\n"
            f"Queue process karne ke liye niche ke buttons use karein.",
            parse_mode="Markdown",
            reply_markup=kb_operator())

    else:
        await update.message.reply_text(
            "🏢 *Faiz Online Service*\n\n"
            "Register karne ke liye apne Agent se\n"
            "referral link maango.\n\n"
            "📩 Agent aapko link bhejega –\n"
            "us par click karke register karein.",
            parse_mode="Markdown")

    return ConversationHandler.END


async def reg_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text(
            "❌ Sahi naam likhiye (minimum 2 characters):")
        return REG_NAME
    user_data(tid)["full_name"] = name
    await update.message.reply_text(
        f"✅ Naam: *{name}*\n\n"
        f"📱 Step 2/2 – 10 digit Phone Number:",
        parse_mode="Markdown")
    return REG_PHONE


async def reg_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    phone = update.message.text.strip()
    if not valid_phone(phone):
        await update.message.reply_text(
            "❌ 10 digit phone number daalo (e.g. 9712643710):")
        return REG_PHONE
    ud    = user_data(tid)
    agent = agent_by_id(ud.get("reg_agent_id",""))
    if not agent:
        await update.message.reply_text(
            "❌ Agent nahi mila. Dobara referral link use karo.")
        return ConversationHandler.END

    code = gen_client_code(agent["agent_id"])
    ok   = add_client(agent, {
        "client_code": code,
        "full_name":   ud["full_name"],
        "phone":       phone,
        "telegram_id": str(tid),
    })
    logger.info(f"add_client ok={ok} tid={tid} agent={agent['agent_id']}")
    if not ok:
        await update.message.reply_text(
            "❌ Registration fail. Dobara try karo.")
        return ConversationHandler.END

    ud.pop("reg_agent_id", None)
    name = ud.pop("full_name", "")

    await update.message.reply_text(
        f"🎉 *Registration Successful!*\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"🆔 Client ID: `{code}`\n"
        f"👤 Naam: {name}\n"
        f"📱 Phone: {phone}\n"
        f"👔 Agent: {agent.get('agent_name')}\n"
        f"💰 Rate: Rs{agent.get('rate_per_app')}/app\n"
        f"━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=kb_client())
    try:
        await ctx.bot.send_message(
            int(agent["telegram_id"]),
            f"🆕 *New Client Registered!*\n\n"
            f"🆔 ID: `{code}`\n"
            f"👤 {name}\n"
            f"📱 {phone}",
            parse_mode="Markdown")
    except: pass
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    ud   = user_data(tid)
    # Clear all session keys
    for k in list(ud.keys()):
        ud.pop(k, None)
    role = detect_role(tid)
    kb   = (kb_admin()    if role == "admin"    else
            kb_agent()    if role == "agent"    else
            kb_client()   if role == "client"   else
            kb_operator() if role == "operator" else None)
    await update.message.reply_text("❌ Cancelled.", reply_markup=kb)
    return ConversationHandler.END
