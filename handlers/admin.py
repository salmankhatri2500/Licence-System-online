"""
handlers/admin.py  –  FOS v2
Admin + Operator management.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from config import (SUPER_ADMIN_ID, AA_NAME, AA_PHONE, AA_TID,
                    AA_RATE, AA_SHEET, ABC_TYPE, ABC_MSG, ADD_OP_PHONE)
from keyboards import (kb_admin, REMOVE, ik_queue_item, ik_agent_actions,
                       ik_broadcast_type, ik_admin_settings, ik_agent_payment_review,
                       ik_operator_remove)
from db import (all_agents, agent_by_id, add_agent, set_agent_field, remove_agent,
                master_log, all_agent_payments, setup_manual_sheet,
                agent_by_tid, agent_active, queue_pending, queue_all,
                queue_today_count, add_agent_balance, get_admin_qr,
                get_admin_rate, set_admin_setting, queue_release_held,
                all_operators, add_operator, remove_operator,
                operator_by_phone, operators_enabled, reminders_enabled,
                agent_by_phone, queue_stats_range)
from utils import (user_data, now_ist, today_ist, month_ist, ts_to_display,
                   safe_float, safe_int, gen_agent_id, gen_op_id,
                   valid_phone, div, progress_bar)

logger = logging.getLogger(__name__)


def is_admin(tid): return tid == SUPER_ADMIN_ID


# ════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════
async def dashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    agents  = all_agents()
    active  = sum(1 for a in agents if agent_active(a))
    q       = queue_today_count()
    rate    = get_admin_rate()
    t_cl    = sum(safe_int(a.get("total_clients",0)) for a in agents)
    t_apps  = sum(safe_int(a.get("total_apps",0))    for a in agents)
    ops     = all_operators()
    bar     = progress_bar(q["done"], q["total"]) if q["total"] else "▱"*10

    await update.message.reply_text(
        f"📊 *Dashboard*  –  {today_ist()}\n"
        f"━━━━━━━━━━━━━━\n"
        f"👔 Agents: {len(agents)}  ({active} active)\n"
        f"👤 Clients: {t_cl}   📋 Total Apps: {t_apps}\n"
        f"💰 Admin Rate: Rs{rate}/app\n"
        f"🖼 QR: {'✅' if get_admin_qr() else '❌ Not set'}\n"
        f"👥 Operators: {len(ops)}  ({'ON' if operators_enabled() else 'OFF'})\n"
        f"━━━━━━━━━━━━━━\n"
        f"*📅 Aaj ki Queue:*\n"
        f"📥 Total: {q['total']}  |  ✅ Done: {q['done']}\n"
        f"⏳ Pending: {q['pending']}  |  🔒 Held: {q['held']}\n"
        f"{bar}  {q['done']}/{q['total']}",
        parse_mode="Markdown",
        reply_markup=kb_admin())


# ════════════════════════════════════════════════════════════════
# QUEUE
# ════════════════════════════════════════════════════════════════
async def show_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    pending = queue_pending()
    if not pending:
        await update.message.reply_text(
            "✅ Queue khali hai!", reply_markup=kb_admin())
        return
    await update.message.reply_text(
        f"⏳ *Pending Queue: {len(pending)}*",
        parse_mode="Markdown")
    for ap in pending[:30]:
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
            logger.warning(f"show_queue: {e}")
    if len(pending) > 30:
        await update.message.reply_text(
            f"…aur {len(pending)-30} more.", reply_markup=kb_admin())
    else:
        await update.message.reply_text("━━━━━━━━━━━━━━", reply_markup=kb_admin())


async def show_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    all_q = queue_all()
    done  = [r for r in all_q if r.get("status","").upper() == "DONE"]
    today = [r for r in done  if r.get("done_at","").startswith(today_ist())]
    await update.message.reply_text(
        f"✅ *Done Apps*\n"
        f"━━━━━━━━━━━━━━\n"
        f"📅 Aaj: {len(today)}\n"
        f"📊 Total: {len(done)}",
        parse_mode="Markdown", reply_markup=kb_admin())


# ════════════════════════════════════════════════════════════════
# AGENTS
# ════════════════════════════════════════════════════════════════
async def all_agents_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    agents = all_agents()
    if not agents:
        await update.message.reply_text("Koi agent nahi.", reply_markup=kb_admin())
        return
    await update.message.reply_text(
        f"👔 *All Agents ({len(agents)})*", parse_mode="Markdown")
    for a in agents:
        bal = safe_float(a.get("balance",0))
        st  = agent_active(a)
        try:
            await update.message.reply_text(
                f"{'✅' if st else '🚫'} *{a.get('agent_name')}*\n"
                f"🆔 `{a.get('agent_id')}`  📱 {a.get('phone')}\n"
                f"💰 Rs{a.get('rate_per_app')}/app  |  Bal: Rs{bal}\n"
                f"📋 Apps: {a.get('total_apps',0)}  👤 Clients: {a.get('total_clients',0)}\n"
                f"📄 {a.get('sheet_name')}",
                parse_mode="Markdown",
                reply_markup=ik_agent_actions(a["agent_id"], st))
        except Exception as e:
            logger.warning(f"all_agents: {e}")
    await update.message.reply_text("━━━━━━━━━━━━━━", reply_markup=kb_admin())


# ════════════════════════════════════════════════════════════════
# AGENT PAYMENTS
# ════════════════════════════════════════════════════════════════
async def agent_payments_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    pending = []
    for ag in all_agents():
        for p in all_agent_payments(ag):
            if p.get("status","").upper() == "PENDING":
                p["_ag"] = ag
                pending.append(p)
    if not pending:
        await update.message.reply_text(
            "✅ Koi pending agent payment nahi.", reply_markup=kb_admin())
        return
    await update.message.reply_text(
        f"💳 *Agent Payments ({len(pending)} pending)*",
        parse_mode="Markdown")
    for p in pending:
        ag = p["_ag"]
        try:
            await update.message.reply_text(
                f"👔 *{ag.get('agent_name')}*\n"
                f"💰 Rs{p.get('amount')}\n"
                f"🆔 `{p.get('payment_id')}`\n"
                f"📅 {p.get('date')} {p.get('time')}",
                parse_mode="Markdown",
                reply_markup=ik_agent_payment_review(p["payment_id"], ag["agent_id"]))
        except: pass
    await update.message.reply_text("━━━━━━━━━━━━━━", reply_markup=kb_admin())


# ════════════════════════════════════════════════════════════════
# SETTINGS
# ════════════════════════════════════════════════════════════════
async def admin_settings_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    rate = get_admin_rate()
    qr   = get_admin_qr()
    ops  = operators_enabled()
    rem  = reminders_enabled()
    await update.message.reply_text(
        f"⚙️ *Admin Settings*\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 App Rate: Rs{rate}/app\n"
        f"🖼 QR: {'✅ Set' if qr else '❌ Not set'}\n"
        f"👥 Operators: {'✅ ON' if ops else '❌ OFF'}\n"
        f"🔔 Reminders: {'✅ ON' if rem else '❌ OFF'}\n"
        f"━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=ik_admin_settings())


async def admin_qr_receive(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    tid = update.effective_user.id
    if not is_admin(tid): return False
    ud  = user_data(tid)
    if not ud.get("awaiting_admin_qr"): return False
    if not update.message or not update.message.photo:
        await update.message.reply_text(
            "❌ Photo bhejiye.", reply_markup=kb_admin())
        return True
    file_id = update.message.photo[-1].file_id
    set_admin_setting("qr_file_id", file_id)
    ud.pop("awaiting_admin_qr", None)
    await update.message.reply_text(
        "✅ *Admin QR saved!*\nAgents Pay Admin karte waqt yeh QR dekhenge.",
        parse_mode="Markdown", reply_markup=kb_admin())
    return True


# ════════════════════════════════════════════════════════════════
# MONTHLY REPORT
# ════════════════════════════════════════════════════════════════
async def monthly_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    mon    = month_ist()
    all_q  = queue_all()
    mq     = [r for r in all_q if r.get("submitted_at","").startswith(mon)]
    done   = sum(1 for r in mq if r.get("status") == "DONE")
    held   = sum(1 for r in mq if r.get("status") == "HELD")
    pend   = sum(1 for r in mq if r.get("status") == "PENDING")
    agents = all_agents()
    rate   = get_admin_rate()
    earned = done * rate

    # Top agents this month
    agent_counts = {}
    for r in mq:
        if r.get("status") == "DONE":
            aid = r.get("agent_id","")
            agent_counts[aid] = agent_counts.get(aid, 0) + 1
    top = sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_txt = ""
    for i, (aid, cnt) in enumerate(top, 1):
        ag = agent_by_id(aid)
        nm = ag.get("agent_name","?") if ag else aid
        top_txt += f"  {i}. {nm}: {cnt} apps\n"

    await update.message.reply_text(
        f"📊 *Monthly Report – {mon}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"📥 Total: {len(mq)}\n"
        f"✅ Done: {done}  ⏳ Pending: {pend}  🔒 Held: {held}\n"
        f"💵 Admin Earned: Rs{earned}\n"
        f"━━━━━━━━━━━━━━\n"
        f"👔 Agents: {len(agents)} ({sum(1 for a in agents if agent_active(a))} active)\n"
        + (f"\n🏆 *Top Agents:*\n{top_txt}" if top_txt else ""),
        parse_mode="Markdown", reply_markup=kb_admin())


# ════════════════════════════════════════════════════════════════
# ADD AGENT  ConversationHandler
# ════════════════════════════════════════════════════════════════
async def add_agent_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    tid = update.effective_user.id
    ud  = user_data(tid)
    for k in ("aa_name","aa_phone","aa_tid","aa_rate"):
        ud.pop(k, None)
    await update.message.reply_text(
        "➕ *New Agent*\n\nStep 1/5 – Agent ka Naam:",
        parse_mode="Markdown", reply_markup=REMOVE)
    return AA_NAME

async def aa_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Valid naam daalo:")
        return AA_NAME
    user_data(tid)["aa_name"] = name
    await update.message.reply_text(
        f"✅ Naam: *{name}*\n\nStep 2/5 – Phone (10 digit):",
        parse_mode="Markdown")
    return AA_PHONE

async def aa_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    phone = update.message.text.strip()
    if not valid_phone(phone):
        await update.message.reply_text("❌ 10 digit phone daalo:")
        return AA_PHONE
    # Unique phone check
    if agent_by_phone(phone):
        await update.message.reply_text(
            "❌ Yeh phone number already registered hai!\nDusra number daalo:")
        return AA_PHONE
    user_data(tid)["aa_phone"] = phone
    await update.message.reply_text(
        f"✅ Phone: *{phone}*\n\nStep 3/5 – Telegram ID:",
        parse_mode="Markdown")
    return AA_TID

async def aa_tid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    raw = update.message.text.strip()
    if not raw.lstrip("-").isdigit():
        await update.message.reply_text("❌ Sirf number daalo:")
        return AA_TID
    user_data(tid)["aa_tid"] = raw
    await update.message.reply_text(
        f"✅ TID: *{raw}*\n\nStep 4/5 – Rate per App (Rs):",
        parse_mode="Markdown")
    return AA_RATE

async def aa_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    try:
        rate = float(update.message.text.strip())
        if rate <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Valid number daalo (e.g. 30):")
        return AA_RATE
    user_data(tid)["aa_rate"] = rate
    await update.message.reply_text(
        f"✅ Rate: *Rs{rate}/app*\n\n"
        f"Step 5/5 – Google Sheet ka exact naam:",
        parse_mode="Markdown")
    return AA_SHEET

async def aa_sheet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid        = update.effective_user.id
    sheet_name = update.message.text.strip()
    d          = user_data(tid)
    rate       = d.get("aa_rate", 0)
    agent_name = d.get("aa_name", "")
    agent_id   = gen_agent_id()

    await update.message.reply_text("⏳ Setting up…")

    try:
        ok_sheet = setup_manual_sheet(sheet_name, agent_id, agent_name, rate)
    except Exception as e:
        logger.error(f"setup_manual_sheet: {e}")
        ok_sheet = False

    if not ok_sheet:
        await update.message.reply_text(
            f"❌ Sheet *'{sheet_name}'* nahi mili!\n\n"
            f"1️⃣ Naam exactly match karo\n"
            f"2️⃣ Service account ko Editor access do\n\n"
            f"Sahi naam daalo:",
            parse_mode="Markdown", reply_markup=kb_admin())
        return AA_SHEET

    try:
        ok = add_agent({
            "agent_id":    agent_id,
            "agent_name":  agent_name,
            "phone":       d.get("aa_phone",""),
            "telegram_id": int(d.get("aa_tid",0)),
            "sheet_name":  sheet_name,
            "rate":        rate,
        })
    except Exception as e:
        logger.error(f"add_agent: {e}")
        ok = False

    if not ok:
        await update.message.reply_text(
            "❌ FOS_Master mein save nahi hua.",
            reply_markup=kb_admin())
        return ConversationHandler.END

    try:
        bot_me   = await ctx.bot.get_me()
        ref_link = f"https://t.me/{bot_me.username}?start=register_{agent_id}"
    except:
        ref_link = "N/A"

    for k in ("aa_name","aa_phone","aa_tid","aa_rate"):
        d.pop(k, None)

    await update.message.reply_text(
        f"🎉 *Agent Added!*\n\n"
        f"🆔 `{agent_id}`\n"
        f"👤 {agent_name}\n"
        f"📱 {d.get('aa_phone','')}\n"
        f"📄 {sheet_name}\n"
        f"💰 Rs{rate}/app\n\n"
        f"🔗 Referral Link:\n{ref_link}",
        parse_mode="Markdown", reply_markup=kb_admin())
    try:
        await ctx.bot.send_message(
            int(d.get("aa_tid",0)),
            f"🎉 *Aapko FOS Agent banaya gaya!*\n\n"
            f"🆔 `{agent_id}`\n💰 Rs{rate}/app\n\n"
            f"/start bhejiye.",
            parse_mode="Markdown")
    except: pass
    return ConversationHandler.END


async def find_agent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: /find_agent <naam ya ID>",
                                        reply_markup=kb_admin())
        return
    q   = " ".join(args).lower()
    res = [a for a in all_agents()
           if q in a.get("agent_name","").lower() or q in a.get("agent_id","").lower()]
    if not res:
        await update.message.reply_text("❌ Nahi mila.", reply_markup=kb_admin())
        return
    for a in res:
        await update.message.reply_text(
            f"👔 {a['agent_name']}  |  {'✅' if agent_active(a) else '🚫'}\n"
            f"🆔 `{a['agent_id']}`  📱 {a['phone']}\n"
            f"📄 {a['sheet_name']}",
            parse_mode="Markdown", reply_markup=kb_admin())


# ════════════════════════════════════════════════════════════════
# OPERATOR MANAGEMENT
# ════════════════════════════════════════════════════════════════
async def operators_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    ops  = all_operators()
    on   = operators_enabled()

    toggle_label = "🔴 Turn OFF Operators" if on else "🟢 Turn ON Operators"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data="TOGGLE_OPS")],
        [InlineKeyboardButton("➕ Add Operator",   callback_data="ADD_OP")],
        [InlineKeyboardButton("📋 List Operators", callback_data="LIST_OPS")],
    ])
    await update.message.reply_text(
        f"👥 *Operator Panel*\n"
        f"━━━━━━━━━━━━━━\n"
        f"Status: {'✅ ON' if on else '❌ OFF'}\n"
        f"Total Operators: {len(ops)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"Operators ON hone par multiple log\n"
        f"queue process kar sakte hain.",
        parse_mode="Markdown", reply_markup=kb)


async def add_op_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Called from callback."""
    tid = update.effective_user.id
    await ctx.bot.send_message(
        tid,
        "➕ *Add Operator*\n\n"
        "Operator ka 10 digit phone number daalo:",
        parse_mode="Markdown",
        reply_markup=REMOVE)
    user_data(tid)["awaiting_op_phone"] = True


async def add_op_phone_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handles operator phone input (called from message_router)."""
    tid   = update.effective_user.id
    phone = update.message.text.strip()
    ud    = user_data(tid)

    if not valid_phone(phone):
        await update.message.reply_text("❌ 10 digit phone daalo:")
        return

    if operator_by_phone(phone):
        await update.message.reply_text(
            "❌ Yeh phone already operator hai!",
            reply_markup=kb_admin())
        ud.pop("awaiting_op_phone", None)
        return

    op_id = gen_op_id()
    ok    = add_operator({"op_id": op_id, "phone": phone})
    if not ok:
        await update.message.reply_text("❌ Save nahi hua.", reply_markup=kb_admin())
        ud.pop("awaiting_op_phone", None)
        return

    # Generate link for operator to activate
    try:
        bot_me   = await ctx.bot.get_me()
        op_link  = f"https://t.me/{bot_me.username}?start=operator_{phone}"
    except:
        op_link  = "N/A"

    ud.pop("awaiting_op_phone", None)
    await update.message.reply_text(
        f"✅ *Operator Added!*\n\n"
        f"📱 Phone: {phone}\n"
        f"🆔 ID: `{op_id}`\n\n"
        f"🔗 *Activation Link:*\n{op_link}\n\n"
        f"Yeh link operator ko bhejo.\n"
        f"Link click karne ke baad unka panel activate ho jayega.",
        parse_mode="Markdown", reply_markup=kb_admin())


# ════════════════════════════════════════════════════════════════
# BROADCAST (Admin → All Agents)
# ════════════════════════════════════════════════════════════════
async def admin_bc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "📢 *Broadcast to All Agents*\n\nType chuniye:",
        parse_mode="Markdown",
        reply_markup=ik_broadcast_type("ABC"))
    return ABC_TYPE

async def admin_bc_type_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    t = q.data.replace("ABC_","").lower()
    user_data(q.from_user.id)["abc_type"] = t
    await q.edit_message_text(
        f"📢 Type: *{t}*\n\nAb message bhejiye:",
        parse_mode="Markdown")
    return ABC_MSG

async def admin_bc_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid     = update.effective_user.id
    bc_type = user_data(tid).get("abc_type","text")
    agents  = [a for a in all_agents() if agent_active(a)]
    sent = failed = 0
    for ag in agents:
        try:
            at = int(ag.get("telegram_id",0))
            if not at: continue
            if bc_type == "text":
                await ctx.bot.send_message(at, update.message.text)
            elif bc_type == "image" and update.message.photo:
                await ctx.bot.send_photo(at, update.message.photo[-1].file_id,
                                         caption=update.message.caption or "")
            elif bc_type == "voice" and update.message.voice:
                await ctx.bot.send_voice(at, update.message.voice.file_id)
            sent += 1
        except:
            failed += 1
    user_data(tid).pop("abc_type", None)
    await update.message.reply_text(
        f"📢 *Broadcast Done!*\n✅ {sent}  |  ❌ {failed}",
        parse_mode="Markdown", reply_markup=kb_admin())
    return ConversationHandler.END
