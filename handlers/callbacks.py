"""
handlers/callbacks.py  –  FOS v2
All inline keyboard callback handlers.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import SUPER_ADMIN_ID
from keyboards import (kb_admin, kb_agent, kb_client, kb_operator,
                       ik_queue_item, ik_operator_remove)
from db import (agent_by_id, set_client_field, remove_agent,
                get_setting, put_setting,
                approve_payment, reject_payment, add_balance, get_payment_amount,
                approve_agent_payment, reject_agent_payment,
                add_agent_balance, get_agent_payment_amount,
                queue_mark_done, queue_get, mark_app_done,
                queue_release_held, get_admin_rate, deduct_agent_balance,
                set_admin_setting, set_agent_field, agent_active,
                all_operators, remove_operator, operators_enabled,
                set_operator_field, operator_by_tid, client_by_code)
from utils import user_data, safe_float, div

logger = logging.getLogger(__name__)


async def callback_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    tid  = q.from_user.id

    # ── QDONE (Admin or Operator) ─────────────────────────────
    if data.startswith("QDONE|"):
        # Allow admin OR active operators
        from db import detect_role, operator_by_tid
        role = detect_role(tid)
        if role not in ("admin", "operator"):
            await q.answer("❌ Access denied!", show_alert=True)
            return

        parts       = data.split("|")
        queue_id    = parts[1]
        client_code = parts[2]
        agent_id    = parts[3]
        agent_tid   = int(parts[4]) if parts[4] not in ("0","") else 0
        client_tid  = int(parts[5]) if len(parts) > 5 and parts[5] not in ("0","") else 0

        done_by = "admin" if role == "admin" else f"op:{tid}"
        queue_mark_done(queue_id, done_by=done_by)

        qitem      = queue_get(queue_id)
        app_no     = qitem.get("app_no","N/A")
        client_name= qitem.get("client_name","N/A")

        admin_rate = get_admin_rate()
        if admin_rate > 0:
            deduct_agent_balance(agent_id, admin_rate)

        agent = agent_by_id(agent_id)
        if agent:
            mark_app_done(agent, queue_id)

        try:
            old = q.message.text or ""
            await q.edit_message_text(
                old + f"\n\n✅ DONE by {done_by}")
        except: pass

        # Notify agent
        if agent_tid:
            try:
                await ctx.bot.send_message(
                    agent_tid,
                    f"✅ *App Done!*\n\n"
                    f"🆔 `{queue_id}`  📋 {app_no}\n"
                    f"👤 {client_name}\n"
                    f"💰 Rs{admin_rate} deducted.",
                    parse_mode="Markdown", reply_markup=kb_agent())
            except: pass

        # Notify client
        notified = False
        if client_tid:
            try:
                await ctx.bot.send_message(
                    client_tid,
                    f"🎉 *Application Successful!*\n\n"
                    f"🆔 `{queue_id}`  📋 {app_no}\n\n"
                    f"Aapki application process ho gayi!",
                    parse_mode="Markdown", reply_markup=kb_client())
                notified = True
            except: pass
        if not notified and client_code and agent:
            try:
                c = client_by_code(agent, client_code)
                if c and c.get("telegram_id"):
                    await ctx.bot.send_message(
                        int(c["telegram_id"]),
                        f"🎉 *Application Successful!*\n\n"
                        f"🆔 `{queue_id}`  📋 {app_no}",
                        parse_mode="Markdown", reply_markup=kb_client())
            except: pass

    # ── Client Payment ────────────────────────────────────────
    elif data.startswith("PAY_APP|"):
        _, pay_id, client_code, agent_id, client_tid_s = data.split("|")
        client_tid = int(client_tid_s) if client_tid_s not in ("0","") else 0
        agent  = agent_by_id(agent_id)
        if not agent:
            try: await q.edit_message_text("❌ Agent nahi mila.")
            except: pass
            return
        amount = get_payment_amount(agent, pay_id)
        approve_payment(agent, pay_id, q.from_user.first_name)
        add_balance(agent, client_code, amount)
        try:
            await q.edit_message_text(
                f"✅ Payment Approved!\nRs{amount} → `{client_code}`",
                parse_mode="Markdown")
        except: pass
        if client_tid:
            try:
                await ctx.bot.send_message(
                    client_tid,
                    f"✅ *Payment Approved!*\n💰 Rs{amount} balance add ho gaya!",
                    parse_mode="Markdown", reply_markup=kb_client())
            except: pass

    elif data.startswith("PAY_REJ|"):
        _, pay_id, client_code, agent_id, client_tid_s = data.split("|")
        client_tid = int(client_tid_s) if client_tid_s not in ("0","") else 0
        agent = agent_by_id(agent_id)
        if agent: reject_payment(agent, pay_id)
        try: await q.edit_message_text(f"❌ Payment Rejected: `{pay_id}`",
                                       parse_mode="Markdown")
        except: pass
        if client_tid:
            try:
                await ctx.bot.send_message(
                    client_tid,
                    "❌ Payment Rejected. Agent se contact karo.",
                    reply_markup=kb_client())
            except: pass

    # ── Agent Payment ─────────────────────────────────────────
    elif data.startswith("AGPAY_APP|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True)
            return
        _, pay_id, agent_id = data.split("|")
        agent = agent_by_id(agent_id)
        if not agent:
            try: await q.edit_message_text("❌ Agent nahi mila.")
            except: pass
            return
        amount   = get_agent_payment_amount(agent, pay_id)
        approve_agent_payment(agent, pay_id)
        add_agent_balance(agent_id, amount)
        released = queue_release_held(agent_id)
        try:
            await q.edit_message_text(
                f"✅ Approved! Rs{amount} → *{agent.get('agent_name')}*",
                parse_mode="Markdown")
        except: pass
        msg = f"✅ *Payment Approved!*\n💰 Rs{amount} balance added."
        if released:
            msg += f"\n🔓 {len(released)} held apps released!"
        try:
            await ctx.bot.send_message(
                int(agent["telegram_id"]), msg,
                parse_mode="Markdown", reply_markup=kb_agent())
        except: pass
        # Forward released to admin
        for item in released:
            try:
                await ctx.bot.send_message(
                    SUPER_ADMIN_ID,
                    f"🔓 *Released*\n"
                    f"🆔 `{item['queue_id']}`  📋 {item.get('app_no','')}\n"
                    f"🎂 {item.get('dob','')}  🔑 `{item.get('password','')}`\n"
                    f"👤 {item.get('client_name','')} | `{item['client_code']}`\n"
                    f"👔 {agent.get('agent_name')}",
                    parse_mode="Markdown",
                    reply_markup=ik_queue_item(
                        item["queue_id"], item["client_code"],
                        agent_id, agent.get("telegram_id",0),
                        item.get("client_tid",0)))
            except: pass

    elif data.startswith("AGPAY_REJ|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True)
            return
        _, pay_id, agent_id = data.split("|")
        agent = agent_by_id(agent_id)
        if agent: reject_agent_payment(agent, pay_id)
        try: await q.edit_message_text("❌ Agent payment rejected.")
        except: pass
        if agent:
            try:
                await ctx.bot.send_message(
                    int(agent["telegram_id"]),
                    "❌ Payment Rejected. Admin se contact karo.",
                    reply_markup=kb_agent())
            except: pass

    # ── Remove Agent ──────────────────────────────────────────
    elif data.startswith("REMOVE_AGENT|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True)
            return
        agent_id = data.split("|")[1]
        agent    = agent_by_id(agent_id)
        name     = agent.get("agent_name", agent_id) if agent else agent_id
        remove_agent(agent_id)
        try: await q.edit_message_text(f"🗑 Agent *{name}* removed.",
                                       parse_mode="Markdown")
        except: pass

    elif data.startswith("AGENT_BLOCK|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True)
            return
        agent_id = data.split("|")[1]
        agent    = agent_by_id(agent_id)
        if agent:
            new_st = "blocked" if agent_active(agent) else "active"
            set_agent_field(agent_id, "status", new_st)
            icon = "🚫 Blocked" if new_st == "blocked" else "✅ Unblocked"
            try: await q.edit_message_text(f"{icon}: {agent.get('agent_name')}")
            except: pass

    elif data.startswith("AGENT_BAL|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True)
            return
        agent_id = data.split("|")[1]
        agent    = agent_by_id(agent_id)
        name     = agent.get("agent_name", agent_id) if agent else agent_id
        ud = user_data(tid)
        ud["adding_agent_bal_id"] = agent_id
        ud["awaiting_agent_bal"]  = True
        try:
            await q.edit_message_text(
                f"💰 *{name}* – kitna balance add karna hai?\nAmount type karo:",
                parse_mode="Markdown")
        except: pass

    # ── Client Block/Unblock ──────────────────────────────────
    elif data.startswith("C_BLOCK|"):
        _, code, agent_id = data.split("|")
        agent = agent_by_id(agent_id)
        if agent: set_client_field(agent, code, "status", "blocked")
        try: await q.edit_message_text(f"🚫 Client `{code}` blocked.",
                                       parse_mode="Markdown")
        except: pass

    elif data.startswith("C_UNBLK|"):
        _, code, agent_id = data.split("|")
        agent = agent_by_id(agent_id)
        if agent: set_client_field(agent, code, "status", "active")
        try: await q.edit_message_text(f"✅ Client `{code}` unblocked.",
                                       parse_mode="Markdown")
        except: pass

    # ── Admin Settings ────────────────────────────────────────
    elif data == "ADMIN_SET_QR":
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True); return
        user_data(tid)["awaiting_admin_qr"] = True
        try: await q.edit_message_text(
            "🖼 *Admin QR*\n\nUPI QR code ki photo bhejiye:",
            parse_mode="Markdown")
        except: pass

    elif data == "ADMIN_SET_RATE":
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True); return
        user_data(tid)["awaiting_admin_rate"] = True
        try: await q.edit_message_text(
            "💰 *Rate Update*\n\nNaya rate daalo (Rs/app):",
            parse_mode="Markdown")
        except: pass

    # ── Operator Management ───────────────────────────────────
    elif data == "TOGGLE_OPS":
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True); return
        current = operators_enabled()
        set_admin_setting("operators_enabled", "0" if current else "1")
        status = "❌ OFF" if current else "✅ ON"
        try: await q.edit_message_text(
            f"👥 Operators: {status}\n\nSettings se manage karo.",
            parse_mode="Markdown")
        except: pass

    elif data == "ADD_OP":
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True); return
        from handlers.admin import add_op_start
        await add_op_start(update, ctx)

    elif data == "LIST_OPS":
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True); return
        ops = all_operators()
        if not ops:
            try: await q.edit_message_text("Koi operator nahi.")
            except: pass
            return
        msg = f"👥 *Operators ({len(ops)})*\n━━━━━━━━━━━━━━\n"
        for op in ops:
            linked = "✅" if op.get("telegram_id","") not in ("","0") else "❌ Not linked"
            msg += (f"\n🆔 `{op['op_id']}`  📱 {op['phone']}\n"
                    f"   {op.get('op_name','No name')} | {linked}\n")
        try: await q.edit_message_text(msg, parse_mode="Markdown")
        except: pass

    elif data.startswith("REMOVE_OP|"):
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True); return
        op_id = data.split("|")[1]
        remove_operator(op_id)
        try: await q.edit_message_text(f"🗑 Operator `{op_id}` removed.",
                                       parse_mode="Markdown")
        except: pass

    elif data == "MANAGE_OPS":
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True); return
        from handlers.admin import operators_cmd
        # Create a fake update to reuse
        try: await q.message.delete()
        except: pass
        await operators_cmd(update, ctx)

    elif data == "TOGGLE_REMINDERS":
        if tid != SUPER_ADMIN_ID:
            await q.answer("❌ Only admin!", show_alert=True); return
        from db import reminders_enabled
        current = reminders_enabled()
        set_admin_setting("reminders_enabled", "0" if current else "1")
        status = "❌ OFF" if current else "✅ ON"
        try: await q.edit_message_text(
            f"🔔 Reminders: {status}", parse_mode="Markdown")
        except: pass

    # ── Agent Settings ────────────────────────────────────────
    elif data.startswith("SET_RATE|"):
        agent_id = data.split("|")[1]
        ud = user_data(tid)
        ud["awaiting_rate"]  = True
        ud["rate_agent_id"]  = agent_id
        try: await q.edit_message_text("💰 Naya rate type karo (Rs/app):")
        except: pass

    elif data.startswith("SET_QR|"):
        user_data(tid)["awaiting_qr"] = True
        try: await q.edit_message_text(
            "🖼 *QR Upload*\n\nUPI QR code ki photo bhejiye:",
            parse_mode="Markdown")
        except: pass

    # ── Broadcast ─────────────────────────────────────────────
    elif data.startswith("BC_"):
        from handlers.agent import bc_type_cb
        await bc_type_cb(update, ctx)

    elif data.startswith("ABC_"):
        from handlers.admin import admin_bc_type_cb
        await admin_bc_type_cb(update, ctx)
