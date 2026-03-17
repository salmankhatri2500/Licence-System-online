"""
handlers/message_router.py  –  FOS v2

ARCHITECTURE:
  group=0 → ConversationHandlers (highest priority)
  group=1 → This router (only fires when NOT in a conversation)

Awaiting states MUST be checked first inside this router
to avoid double-firing with ConversationHandlers.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from db import detect_role, agent_by_tid, find_client, agent_active, operator_by_tid
from keyboards import kb_admin, kb_agent, kb_client, kb_operator
from utils import user_data, safe_float

from handlers.admin import (dashboard, all_agents_cmd, agent_payments_cmd,
                             admin_settings_cmd, show_queue, show_done,
                             monthly_report, operators_cmd, admin_qr_receive)
from handlers.agent import (my_queue, today_summary, work_history, my_clients,
                             my_stats, my_balance, referral_link, settings_cmd,
                             qr_receive)
from handlers.client import (my_apps, my_balance as client_balance, my_profile,
                              contact_agent, pay_start, handle_pay_amount_input)
from handlers.operator import op_queue, op_done_apps, op_today_stats

logger = logging.getLogger(__name__)


async def photo_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Route photo uploads to the right handler."""
    if await admin_qr_receive(update, ctx):
        return
    await qr_receive(update, ctx)


async def message_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    tid  = update.effective_user.id
    text = update.message.text.strip()
    ud   = user_data(tid)

    # ══════════════════════════════════════════════════════════
    # PRIORITY 1 – AWAITING STATE HANDLERS
    # These fire before role routing.
    # ══════════════════════════════════════════════════════════

    if ud.get("awaiting_pay_amount"):
        await handle_pay_amount_input(update, ctx)
        return

    if ud.get("awaiting_admin_rate"):
        try:
            rate = safe_float(text)
            if rate > 0:
                from db import set_admin_setting
                set_admin_setting("rate_per_app", str(rate))
                await update.message.reply_text(
                    f"✅ *Admin Rate Updated!*  Rs{rate}/app",
                    parse_mode="Markdown", reply_markup=kb_admin())
            else:
                await update.message.reply_text("❌ Valid number daalo (e.g. 25):")
                return
        except:
            await update.message.reply_text("❌ Valid number daalo:")
            return
        ud.pop("awaiting_admin_rate", None)
        return

    if ud.get("awaiting_agent_bal"):
        try:
            amount   = safe_float(text)
            agent_id = ud.get("adding_agent_bal_id","")
            if amount > 0 and agent_id:
                from db import add_agent_balance, agent_by_id
                add_agent_balance(agent_id, amount)
                ag   = agent_by_id(agent_id)
                name = ag.get("agent_name", agent_id) if ag else agent_id
                await update.message.reply_text(
                    f"✅ Rs{amount} added to *{name}*",
                    parse_mode="Markdown", reply_markup=kb_admin())
                if ag:
                    try:
                        await ctx.bot.send_message(
                            int(ag["telegram_id"]),
                            f"💰 *Rs{amount} Balance Added!*",
                            parse_mode="Markdown")
                    except: pass
            else:
                await update.message.reply_text("❌ Valid amount daalo:")
                return
        except:
            await update.message.reply_text("❌ Valid amount daalo:")
            return
        ud.pop("awaiting_agent_bal", None)
        ud.pop("adding_agent_bal_id", None)
        return

    if ud.get("awaiting_rate"):
        try:
            rate     = float(text)
            agent_id = ud.get("rate_agent_id","")
            if rate > 0:
                from db import set_agent_field, put_setting, agent_by_id
                ag = agent_by_id(agent_id) if agent_id else agent_by_tid(tid)
                if ag:
                    set_agent_field(ag["agent_id"], "rate_per_app", rate)
                    put_setting(ag, "rate_per_app", str(rate))
                    await update.message.reply_text(
                        f"✅ Rate: Rs{rate}/app",
                        reply_markup=kb_agent())
                else:
                    await update.message.reply_text("❌ Agent nahi mila.")
            else:
                await update.message.reply_text("❌ Valid number daalo:")
                return
        except:
            await update.message.reply_text("❌ Valid number daalo:")
            return
        ud.pop("awaiting_rate", None)
        ud.pop("rate_agent_id", None)
        return

    # Operator phone input
    if ud.get("awaiting_op_phone"):
        from handlers.admin import add_op_phone_msg
        await add_op_phone_msg(update, ctx)
        return

    # ══════════════════════════════════════════════════════════
    # PRIORITY 2 – ROLE-BASED ROUTING
    # ══════════════════════════════════════════════════════════
    role = detect_role(tid)

    # ── Admin ─────────────────────────────────────────────────
    if role == "admin":
        routes = {
            "📊 Dashboard":       dashboard,
            "👔 All Agents":      all_agents_cmd,
            "📋 Queue":            show_queue,
            "✅ Done Apps":        show_done,
            "💳 Agent Payments":  agent_payments_cmd,
            "⚙️ Settings":         admin_settings_cmd,
            "📊 Monthly Report":  monthly_report,
            "👥 Operators":        operators_cmd,
        }
        fn = routes.get(text)
        if fn:
            await fn(update, ctx)
        else:
            await update.message.reply_text(
                "👑 Admin Panel:", reply_markup=kb_admin())

    # ── Agent ─────────────────────────────────────────────────
    elif role == "agent":
        agent = agent_by_tid(tid)
        if not agent_active(agent):
            await update.message.reply_text("⛔ Account block. Admin se contact karo.")
            return

        if text == "🔄 Refresh":
            from handlers.registration import cmd_start
            await cmd_start(update, ctx)
            return

        routes = {
            "📋 My Queue":       my_queue,
            "📅 Today Summary":  today_summary,
            "📋 Work History":   work_history,
            "👥 My Clients":     my_clients,
            "📊 My Stats":       my_stats,
            "💰 My Balance":     my_balance,
            "🔗 Referral Link":  referral_link,
            "⚙️ Settings":        settings_cmd,
        }
        fn = routes.get(text)
        if fn:
            await fn(update, ctx)
        else:
            await update.message.reply_text(
                "👔 Agent Panel:", reply_markup=kb_agent())

    # ── Client ────────────────────────────────────────────────
    elif role == "client":
        c, ag = find_client(tid)
        if c and c.get("status") == "blocked":
            await update.message.reply_text("⛔ Account block. Agent se contact karo.")
            return

        routes = {
            "📋 My Apps":        my_apps,
            "💰 My Balance":     client_balance,
            "💳 Pay Agent":      pay_start,
            "👤 My Profile":     my_profile,
            "📞 Contact Agent":  contact_agent,
        }
        fn = routes.get(text)
        if fn:
            await fn(update, ctx)
        else:
            await update.message.reply_text(
                "👤 Apna Panel:", reply_markup=kb_client())

    # ── Operator ──────────────────────────────────────────────
    elif role == "operator":
        routes = {
            "📋 My Queue":    op_queue,
            "✅ Done Apps":   op_done_apps,
            "📊 Today Stats": op_today_stats,
        }
        fn = routes.get(text)
        if fn:
            await fn(update, ctx)
        else:
            await update.message.reply_text(
                "🔧 Operator Panel:", reply_markup=kb_operator())

    # ── Unknown ───────────────────────────────────────────────
    else:
        await update.message.reply_text(
            "🏢 *Faiz Online Service*\n\n"
            "Register karne ke liye apne Agent se referral link maango.",
            parse_mode="Markdown")
