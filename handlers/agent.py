"""
handlers/agent.py  –  FOS v2
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config import BC_TYPE, BC_MSG, UR_RATE, SUPER_ADMIN_ID, AGENT_PAY_AMOUNT
from keyboards import (kb_agent, REMOVE, ik_broadcast_type,
                       ik_client_actions, ik_agent_settings)
from db import (agent_by_tid, all_clients, all_agent_payments,
                set_agent_field, put_setting, get_setting, agent_active,
                get_agent_balance, add_agent_payment, queue_all,
                queue_held_by_agent, get_admin_qr, get_admin_rate)
from utils import (user_data, today_ist, safe_float, safe_int,
                   gen_pay_id, div, ts_to_display, progress_bar)

logger = logging.getLogger(__name__)


async def my_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return
    all_q = queue_all()
    pend  = [r for r in all_q if r.get("agent_id") == agent["agent_id"]
             and r.get("status","").upper() == "PENDING"]
    held  = [r for r in all_q if r.get("agent_id") == agent["agent_id"]
             and r.get("status","").upper() == "HELD"]
    if not pend and not held:
        await update.message.reply_text(
            "✅ Koi pending app nahi!", reply_markup=kb_agent())
        return
    if pend:
        await update.message.reply_text(
            f"⏳ *Pending: {len(pend)}*", parse_mode="Markdown")
        for ap in pend[:15]:
            await update.message.reply_text(
                f"🆔 `{ap.get('queue_id')}`\n"
                f"📋 {ap.get('app_no')}  🎂 {ap.get('dob')}\n"
                f"👤 {ap.get('client_name')}\n"
                f"🕐 {ts_to_display(ap.get('submitted_at',''))}",
                parse_mode="Markdown")
    if held:
        await update.message.reply_text(
            f"🔒 *HELD: {len(held)}*\nBalance low. Pay Admin karo.",
            parse_mode="Markdown")
    await update.message.reply_text("━━━━━━━━━━━━━━", reply_markup=kb_agent())


async def today_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return
    today = today_ist()
    my_q  = [r for r in queue_all() if r.get("agent_id") == agent["agent_id"]
             and r.get("submitted_at","").startswith(today)]
    done  = sum(1 for r in my_q if r.get("status") == "DONE")
    pend  = sum(1 for r in my_q if r.get("status") == "PENDING")
    held  = sum(1 for r in my_q if r.get("status") == "HELD")
    rate  = safe_float(agent.get("rate_per_app",0))
    bal   = get_agent_balance(agent["agent_id"])
    bar   = progress_bar(done, len(my_q)) if my_q else "▱"*10

    await update.message.reply_text(
        f"📅 *Today – {today}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"{bar}\n"
        f"📥 {len(my_q)}  ✅ {done}  ⏳ {pend}  🔒 {held}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 Earnings: Rs{done*rate}\n"
        f"💰 Balance: Rs{bal}",
        parse_mode="Markdown", reply_markup=kb_agent())


async def my_clients(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid     = update.effective_user.id
    agent   = agent_by_tid(tid)
    if not agent: return
    clients = all_clients(agent)
    if not clients:
        await update.message.reply_text(
            "👤 Koi client nahi.", reply_markup=kb_agent())
        return
    await update.message.reply_text(
        f"👥 *My Clients ({len(clients)})*", parse_mode="Markdown")
    for c in clients:
        st   = c.get("status","active")
        icon = "✅" if st == "active" else "🚫"
        try:
            await update.message.reply_text(
                f"{icon} *{c.get('full_name')}*\n"
                f"🆔 `{c.get('client_code')}`  📱 {c.get('phone')}\n"
                f"💰 Rs{safe_float(c.get('balance',0))}  📋 Apps: {c.get('total_apps',0)}",
                parse_mode="Markdown",
                reply_markup=ik_client_actions(c["client_code"], agent["agent_id"]))
        except: pass
    try:
        bot_me   = await ctx.bot.get_me()
        ref_link = f"https://t.me/{bot_me.username}?start=register_{agent['agent_id']}"
        await update.message.reply_text(
            f"━━━━━━━━━━━━━━\n🔗 {ref_link}", reply_markup=kb_agent())
    except:
        await update.message.reply_text("━━━━━━━━━━━━━━", reply_markup=kb_agent())


async def my_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return
    my_q = [r for r in queue_all() if r.get("agent_id") == agent["agent_id"]]
    done = sum(1 for r in my_q if r.get("status") == "DONE")
    rate = safe_float(agent.get("rate_per_app",0))
    bal  = get_agent_balance(agent["agent_id"])
    held = queue_held_by_agent(agent["agent_id"])

    await update.message.reply_text(
        f"📊 *My Stats*\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 Clients: {agent.get('total_clients',0)}\n"
        f"📋 Total Apps: {len(my_q)}  ✅ Done: {done}\n"
        f"🔒 Held: {len(held)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 Total Earnings: Rs{done*rate}\n"
        f"💰 Balance: Rs{bal}\n"
        f"💰 Rate: Rs{rate}/app",
        parse_mode="Markdown", reply_markup=kb_agent())


async def my_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return
    bal        = get_agent_balance(agent["agent_id"])
    held       = queue_held_by_agent(agent["agent_id"])
    admin_rate = get_admin_rate()
    apps_poss  = int(bal // admin_rate) if admin_rate > 0 else "∞"

    await update.message.reply_text(
        f"💰 *My Balance*\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 Balance: Rs{bal}\n"
        f"📋 Apps possible: {apps_poss}\n"
        f"🔒 Held Apps: {len(held)}",
        parse_mode="Markdown", reply_markup=kb_agent())


async def referral_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return
    try:
        bot_me   = await ctx.bot.get_me()
        ref_link = f"https://t.me/{bot_me.username}?start=register_{agent['agent_id']}"
        await update.message.reply_text(
            f"🔗 *Referral Link:*\n\n`{ref_link}`\n\nIs link se clients register karein.",
            parse_mode="Markdown", reply_markup=kb_agent())
    except:
        await update.message.reply_text("❌ Link generate nahi hua.", reply_markup=kb_agent())


async def settings_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return
    rate = get_setting(agent,"rate_per_app") or agent.get("rate_per_app","N/A")
    qr   = get_setting(agent,"qr_file_id")
    await update.message.reply_text(
        f"⚙️ *Settings*\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Rate: Rs{rate}/app\n"
        f"🖼 QR: {'✅ Set' if qr else '❌ Not set'}",
        parse_mode="Markdown",
        reply_markup=ik_agent_settings(agent["agent_id"]))


async def qr_receive(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return False
    ud = user_data(tid)
    if not ud.get("awaiting_qr"): return False
    if not update.message or not update.message.photo:
        await update.message.reply_text("❌ Photo bhejiye.", reply_markup=kb_agent())
        return True
    file_id = update.message.photo[-1].file_id
    put_setting(agent, "qr_file_id", file_id)
    set_agent_field(agent["agent_id"], "qr_file_id", file_id)
    ud.pop("awaiting_qr", None)
    await update.message.reply_text(
        "✅ *QR saved!*\nClients Pay Agent karte waqt yeh QR dekhenge.",
        parse_mode="Markdown", reply_markup=kb_agent())
    return True


# ── Pay Admin ─────────────────────────────────────────────────
async def pay_admin_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return ConversationHandler.END
    bal   = get_agent_balance(agent["agent_id"])
    held  = queue_held_by_agent(agent["agent_id"])
    held_txt = (f"\n🔒 {len(held)} held – payment ke baad release" if held else "")
    caption  = (f"💳 *Pay Admin*\n\n"
                f"💰 Balance: Rs{bal}{held_txt}\n\n"
                f"UPI payment karo, phir amount type karo:")
    ud = user_data(tid)
    ud["agent_paying_admin"] = True
    ud["pay_agent_obj"]      = agent
    admin_qr = get_admin_qr()
    if admin_qr:
        try:
            await ctx.bot.send_photo(tid, admin_qr, caption=caption,
                                     parse_mode="Markdown")
        except:
            await update.message.reply_text(caption, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            caption + "\n\n_(Admin ne QR set nahi kiya)_",
            parse_mode="Markdown")
    return AGENT_PAY_AMOUNT


async def pay_admin_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    ud  = user_data(tid)
    try:
        amount = float(update.message.text.strip())
        if amount <= 0: raise ValueError
    except:
        await update.message.reply_text("❌ Valid amount daalo (e.g. 300):")
        return AGENT_PAY_AMOUNT
    agent = ud.get("pay_agent_obj")
    if not agent:
        await update.message.reply_text("❌ Session expire.", reply_markup=kb_agent())
        ud.pop("agent_paying_admin", None)
        return ConversationHandler.END
    pay_id = gen_pay_id()
    add_agent_payment(agent, {"pay_id": pay_id, "amount": amount})
    ud.pop("agent_paying_admin", None)
    ud.pop("pay_agent_obj", None)
    from keyboards import ik_agent_payment_review
    await update.message.reply_text(
        f"✅ *Payment Request Sent!*\n💰 Rs{amount}\n🆔 `{pay_id}`",
        parse_mode="Markdown", reply_markup=kb_agent())
    try:
        await ctx.bot.send_message(
            SUPER_ADMIN_ID,
            f"💳 *Agent Payment*\n👔 {agent.get('agent_name')}\n"
            f"💰 Rs{amount}\n🆔 `{pay_id}`",
            parse_mode="Markdown",
            reply_markup=ik_agent_payment_review(pay_id, agent["agent_id"]))
    except: pass
    return ConversationHandler.END


# ── Broadcast ─────────────────────────────────────────────────
async def broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📢 *Broadcast to Clients*\n\nType chuniye:",
        parse_mode="Markdown",
        reply_markup=ik_broadcast_type("BC"))
    return BC_TYPE

async def bc_type_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    t = q.data.replace("BC_","").lower()
    user_data(q.from_user.id)["bc_type"] = t
    await q.edit_message_text(f"📢 Type: *{t}*\n\nMessage bhejiye:", parse_mode="Markdown")
    return BC_MSG

async def bc_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid     = update.effective_user.id
    agent   = agent_by_tid(tid)
    bc_type = user_data(tid).get("bc_type","text")
    clients = all_clients(agent)
    sent = failed = 0
    for c in clients:
        try:
            ct = int(c.get("telegram_id",0))
            if not ct: continue
            if bc_type == "text":
                await ctx.bot.send_message(ct, update.message.text)
            elif bc_type == "image" and update.message.photo:
                await ctx.bot.send_photo(ct, update.message.photo[-1].file_id,
                                         caption=update.message.caption or "")
            elif bc_type == "voice" and update.message.voice:
                await ctx.bot.send_voice(ct, update.message.voice.file_id)
            sent += 1
        except:
            failed += 1
    user_data(tid).pop("bc_type", None)
    await update.message.reply_text(
        f"📢 *Done!*  ✅ {sent}  ❌ {failed}",
        parse_mode="Markdown", reply_markup=kb_agent())
    return ConversationHandler.END


# ── Update Rate ───────────────────────────────────────────────
async def rate_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return ConversationHandler.END
    user_data(tid)["rate_agent"] = agent
    await update.message.reply_text("💰 Naya rate (Rs/app):", reply_markup=REMOVE)
    return UR_RATE

async def rate_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    try:
        rate = float(update.message.text.strip())
        if rate <= 0: raise ValueError
    except:
        await update.message.reply_text("❌ Valid number daalo:")
        return UR_RATE
    agent = user_data(tid).get("rate_agent") or agent_by_tid(tid)
    if not agent:
        await update.message.reply_text("❌ Session expire.", reply_markup=kb_agent())
        return ConversationHandler.END
    set_agent_field(agent["agent_id"], "rate_per_app", rate)
    put_setting(agent, "rate_per_app", str(rate))
    user_data(tid).pop("rate_agent", None)
    await update.message.reply_text(
        f"✅ Rate: Rs{rate}/app", reply_markup=kb_agent())
    return ConversationHandler.END


async def work_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    agent = agent_by_tid(tid)
    if not agent: return
    my_q = [r for r in queue_all() if r.get("agent_id") == agent["agent_id"]]
    done = [r for r in my_q if r.get("status") == "DONE"]
    if not done:
        await update.message.reply_text("Koi done app nahi.", reply_markup=kb_agent())
        return
    recent = done[-10:]
    await update.message.reply_text(
        f"📋 *Work History (last {len(recent)})*", parse_mode="Markdown")
    for ap in reversed(recent):
        await update.message.reply_text(
            f"✅ `{ap.get('queue_id')}`\n"
            f"📋 {ap.get('app_no')}  👤 {ap.get('client_name')}\n"
            f"🕐 {ts_to_display(ap.get('done_at',''))}",
            parse_mode="Markdown")
    await update.message.reply_text("━━━━━━━━━━━━━━", reply_markup=kb_agent())
