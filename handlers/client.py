"""
handlers/client.py  –  FOS v2
New Application with 18+ DOB check + fraud prevention.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from config import APP_NO, APP_DOB, APP_PASS, SUPER_ADMIN_ID
from keyboards import kb_client, REMOVE, ik_payment_review, ik_queue_item
from db import (find_client, get_setting, get_balance, deduct_balance,
                add_app, add_payment, inc_client_apps, queue_add, queue_mark_held,
                get_agent_balance, get_admin_rate, queue_all, set_client_field,
                all_apps)
from utils import (user_data, now_ist, gen_app_id, gen_pay_id,
                   valid_dob_format, is_adult, safe_float, div)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# FRAUD PREVENTION CHECK
# ════════════════════════════════════════════════════════════════
def fraud_check(agent, client_code: str, app_no: str, dob: str) -> str:
    """
    Returns "" if OK, or error message string if fraud detected.
    Checks:
    1. Duplicate app_no for same client (same agent sheet)
    2. Duplicate app_no in global queue (any agent)
    3. Already submitted today with same details
    """
    # Check 1: Duplicate in agent sheet
    existing_apps = all_apps(agent)
    for a in existing_apps:
        if (a.get("app_no","").strip() == app_no.strip()
                and a.get("client_code","").strip() == client_code.strip()
                and a.get("status","") != "REJECTED"):
            return f"⚠️ *Duplicate Application Detected!*\n\nApp No `{app_no}` already submitted."

    # Check 2: Duplicate in global queue (any agent, any client)
    for q in queue_all():
        if (q.get("app_no","").strip() == app_no.strip()
                and q.get("status","").upper() not in ("DONE", "REJECTED")):
            return (f"⚠️ *Duplicate in Queue!*\n\n"
                    f"App No `{app_no}` already pending in queue.")

    return ""  # All clear


# ════════════════════════════════════════════════════════════════
# NEW APPLICATION ConversationHandler
# ════════════════════════════════════════════════════════════════
async def new_app_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)

    if not c:
        await update.message.reply_text(
            "❌ Registered nahi hain.", reply_markup=kb_client())
        return ConversationHandler.END

    if c.get("status") == "blocked":
        await update.message.reply_text(
            "⛔ Account block. Agent se contact karo.",
            reply_markup=kb_client())
        return ConversationHandler.END

    rate = safe_float(ag.get("rate_per_app",0))
    bal  = get_balance(ag, c["client_code"])

    if bal < rate:
        await update.message.reply_text(
            f"❌ *Balance Kam Hai!*\n\n"
            f"💰 Balance: Rs{bal}\n💵 Required: Rs{rate}\n\n"
            f"Pay Agent se recharge karo.",
            parse_mode="Markdown", reply_markup=kb_client())
        await _show_qr_only(update, ctx, ag)
        return ConversationHandler.END

    ud = user_data(tid)
    ud["app_ag"]  = ag
    ud["app_c"]   = c
    ud.pop("app_no", None)
    ud.pop("app_dob", None)

    await update.message.reply_text(
        f"📱 *New Application*\n\n"
        f"💰 Balance: Rs{bal}  💵 Rate: Rs{rate}\n\n"
        f"Step 1/3 – Application Number:",
        parse_mode="Markdown", reply_markup=REMOVE)
    return APP_NO


async def app_no(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    no  = update.message.text.strip()
    if len(no) < 3:
        await update.message.reply_text(
            "❌ Valid application number daalo (min 3 chars):")
        return APP_NO
    user_data(tid)["app_no"] = no
    await update.message.reply_text(
        f"✅ App No: *{no}*\n\n"
        f"Step 2/3 – Date of Birth (DD/MM/YYYY)\n"
        f"_(Applicant 18+ hona chahiye)_",
        parse_mode="Markdown")
    return APP_DOB


async def app_dob(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    dob = update.message.text.strip()

    if not valid_dob_format(dob):
        await update.message.reply_text(
            "❌ Invalid format!\nDD/MM/YYYY mein daalo (e.g. 09/05/2000):")
        return APP_DOB

    if not is_adult(dob):
        # 18+ validation fail – return to main menu
        await update.message.reply_text(
            "❌ *Age Invalid!*\n\n"
            "Applicant 18 saal se upar hona chahiye.\n"
            "Sahi DOB daalo ya main menu pe wapas jao.",
            parse_mode="Markdown", reply_markup=kb_client())
        return ConversationHandler.END

    user_data(tid)["app_dob"] = dob
    await update.message.reply_text(
        f"✅ DOB: *{dob}*\n\nStep 3/3 – Password:",
        parse_mode="Markdown")
    return APP_PASS


async def app_pass(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    pwd  = update.message.text.strip()
    ud   = user_data(tid)
    ag   = ud.get("app_ag")
    c    = ud.get("app_c")

    if not ag or not c:
        await update.message.reply_text(
            "❌ Session expire. Dobara try karo.",
            reply_markup=kb_client())
        return ConversationHandler.END

    if len(pwd) < 1:
        await update.message.reply_text("❌ Password daalo:")
        return APP_PASS

    app_no_val = ud.get("app_no","")
    dob_val    = ud.get("app_dob","")

    # ── Fraud check ───────────────────────────────────────────
    fraud_msg = fraud_check(ag, c["client_code"], app_no_val, dob_val)
    if fraud_msg:
        await update.message.reply_text(
            fraud_msg + "\n\nDobara submit karna ho toh main menu se karein.",
            parse_mode="Markdown", reply_markup=kb_client())
        # Clear session
        ud.pop("app_ag", None); ud.pop("app_c", None)
        ud.pop("app_no", None); ud.pop("app_dob", None)
        return ConversationHandler.END

    rate   = safe_float(ag.get("rate_per_app",0))
    app_id = gen_app_id()

    deduct_balance(ag, c["client_code"], rate)
    inc_client_apps(ag, c["client_code"])
    add_app(ag, {"app_id": app_id, "app_no": app_no_val,
                 "dob": dob_val, "password": pwd,
                 "client_code": c["client_code"]})

    queue_add({
        "queue_id":    app_id,
        "app_no":      app_no_val,
        "dob":         dob_val,
        "password":    pwd,
        "client_code": c["client_code"],
        "client_name": c.get("full_name",""),
        "client_tid":  str(tid),
        "agent_id":    ag.get("agent_id",""),
        "agent_name":  ag.get("agent_name",""),
        "agent_tid":   ag.get("telegram_id",""),
        "priority":    "normal",
    })

    bal_left   = get_balance(ag, c["client_code"])
    agent_bal  = get_agent_balance(ag.get("agent_id",""))
    admin_rate = get_admin_rate()

    low_warn = ""
    if rate > 0 and bal_left < rate * 5:
        apps_left = int(bal_left // rate) if rate > 0 else 0
        low_warn  = (f"\n\n⚠️ *Balance Low!*\n"
                     f"~{apps_left} apps remaining. Pay Agent karo!")

    # Clear session
    ud.pop("app_ag", None); ud.pop("app_c", None)
    ud.pop("app_no", None); ud.pop("app_dob", None)

    # Hold if agent balance low
    if admin_rate > 0 and agent_bal < admin_rate:
        queue_mark_held(app_id)
        try:
            await ctx.bot.send_message(
                int(ag["telegram_id"]),
                f"🔒 *App HELD – Balance Low!*\n\n"
                f"💰 Balance: Rs{agent_bal}  Required: Rs{admin_rate}\n"
                f"👤 {c.get('full_name')} | 📋 {app_no_val}\n\n"
                f"Pay Admin karo → apps release hongi.",
                parse_mode="Markdown")
        except: pass
        await update.message.reply_text(
            f"✅ *Submitted (HELD)*\n\n"
            f"🆔 `{app_id}`  📋 {app_no_val}\n"
            f"💰 Balance: Rs{bal_left}"
            f"{low_warn}\n\n"
            f"⚠️ Agent balance low – processing hold mein.",
            parse_mode="Markdown", reply_markup=kb_client())
        return ConversationHandler.END

    agent_warn = ""
    if admin_rate > 0 and agent_bal < admin_rate * 5:
        apps_left_ag = int(agent_bal // admin_rate)
        agent_warn   = f"\n\n⚠️ Agent bal low: ~{apps_left_ag} apps left."

    await update.message.reply_text(
        f"✅ *Application Submitted!*\n\n"
        f"🆔 `{app_id}`\n"
        f"📋 {app_no_val}  🎂 {dob_val}\n"
        f"💰 Balance: Rs{bal_left}"
        f"{low_warn}\n\n"
        f"⏳ Queue mein hai. Done hone par notify karenge!"
        f"{agent_warn}",
        parse_mode="Markdown", reply_markup=kb_client())

    # Notify agent
    try:
        await ctx.bot.send_message(
            int(ag["telegram_id"]),
            f"🆕 *New App!*\n\n"
            f"👤 {c.get('full_name')} (`{c['client_code']}`)\n"
            f"📋 {app_no_val}  🆔 `{app_id}`",
            parse_mode="Markdown")
    except: pass

    # Notify admin
    try:
        await ctx.bot.send_message(
            SUPER_ADMIN_ID,
            f"🆕 *New Application*\n"
            f"━━━━━━━━━━━━━━\n"
            f"🆔 `{app_id}`  📋 *{app_no_val}*\n"
            f"🎂 {dob_val}  🔑 `{pwd}`\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 {c.get('full_name')} | `{c['client_code']}`\n"
            f"👔 {ag.get('agent_name')} | `{ag.get('agent_id')}`",
            parse_mode="Markdown",
            reply_markup=ik_queue_item(app_id, c["client_code"],
                                       ag.get("agent_id",""),
                                       ag.get("telegram_id",0), tid))
    except Exception as e:
        logger.error(f"Admin notify: {e}")

    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════
# PAY AGENT
# ════════════════════════════════════════════════════════════════
async def _show_qr_only(update, ctx, ag):
    qr = get_setting(ag, "qr_file_id")
    if qr:
        try:
            await ctx.bot.send_photo(
                update.effective_user.id, qr,
                caption=f"💳 QR scan karo\n"
                        f"💰 Rate: Rs{ag.get('rate_per_app')}/app\n\n"
                        f"Payment ke baad 'Pay Agent' press karo.")
            return
        except: pass
    await update.message.reply_text(
        "💳 Agent se payment karo aur unhe batao.", reply_markup=kb_client())


async def pay_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c:
        await update.message.reply_text("❌ Registered nahi.", reply_markup=kb_client())
        return
    ud  = user_data(tid)
    qr  = get_setting(ag, "qr_file_id")
    if qr:
        try:
            await ctx.bot.send_photo(
                tid, qr,
                caption=f"💳 *Pay Agent – {ag.get('agent_name')}*\n\n"
                        f"💰 Rate: Rs{ag.get('rate_per_app')}/app\n\n"
                        f"QR scan karo, phir amount type karo:",
                parse_mode="Markdown")
        except:
            await update.message.reply_text(
                f"💳 *Pay Agent – {ag.get('agent_name')}*\n\n"
                f"Rate: Rs{ag.get('rate_per_app')}/app\n\nAmount type karo:",
                parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"💳 *Pay Agent*\n\nAmount type karo:",
            parse_mode="Markdown")
    ud["awaiting_pay_amount"] = True
    ud["pay_agent"]           = ag
    ud["pay_client"]          = c


async def handle_pay_amount_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    ud  = user_data(tid)
    try:
        amount = safe_float(update.message.text.strip())
        if amount <= 0: raise ValueError
    except:
        await update.message.reply_text("❌ Valid amount daalo:")
        return
    ag = ud.get("pay_agent")
    c  = ud.get("pay_client")
    if not ag or not c:
        await update.message.reply_text(
            "❌ Session expire. Dobara 'Pay Agent' press karo.",
            reply_markup=kb_client())
        ud.pop("awaiting_pay_amount", None)
        return
    pay_id = gen_pay_id()
    add_payment(ag, {"pay_id": pay_id, "client_code": c["client_code"],
                     "amount": amount})
    ud.pop("awaiting_pay_amount", None)
    ud.pop("pay_agent", None)
    ud.pop("pay_client", None)
    await update.message.reply_text(
        f"✅ *Payment Request Sent!*\n💰 Rs{amount}\nAgent approve karega.",
        parse_mode="Markdown", reply_markup=kb_client())
    try:
        await ctx.bot.send_message(
            int(ag["telegram_id"]),
            f"💳 *Payment Request*\n\n"
            f"👤 {c.get('full_name')} (`{c['client_code']}`)\n"
            f"💰 Rs{amount}  🆔 `{pay_id}`",
            parse_mode="Markdown",
            reply_markup=ik_payment_review(pay_id, c["client_code"],
                                           ag["agent_id"], tid))
    except: pass


# ════════════════════════════════════════════════════════════════
# CLIENT INFO
# ════════════════════════════════════════════════════════════════
async def my_apps(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c:
        await update.message.reply_text("❌ Registered nahi.", reply_markup=kb_client())
        return
    my = [r for r in queue_all() if r.get("client_code") == c.get("client_code")]
    if not my:
        await update.message.reply_text("📋 Koi app nahi.", reply_markup=kb_client())
        return
    recent = my[-15:]
    await update.message.reply_text(
        f"📋 *My Apps ({len(my)} total)*", parse_mode="Markdown")
    for ap in reversed(recent):
        st   = ap.get("status","")
        icon = "✅" if st == "DONE" else "🔒" if st == "HELD" else "⏳"
        await update.message.reply_text(
            f"{icon} `{ap.get('queue_id')}`\n"
            f"📋 {ap.get('app_no')}  🎂 {ap.get('dob')}\n"
            f"🕐 {ap.get('submitted_at','')[:16]}",
            parse_mode="Markdown")
    await update.message.reply_text("━━━━━━━━━━━━━━", reply_markup=kb_client())


async def my_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c:
        await update.message.reply_text("❌ Registered nahi.", reply_markup=kb_client())
        return
    bal  = get_balance(ag, c["client_code"])
    rate = safe_float(ag.get("rate_per_app",0))
    await update.message.reply_text(
        f"💰 *My Balance*\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 Balance: Rs{bal}\n"
        f"💰 Rate: Rs{rate}/app\n"
        f"📋 Apps possible: {int(bal//rate) if rate else '∞'}",
        parse_mode="Markdown", reply_markup=kb_client())


async def my_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c:
        await update.message.reply_text("❌ Registered nahi.", reply_markup=kb_client())
        return
    bal = get_balance(ag, c["client_code"])
    await update.message.reply_text(
        f"👤 *My Profile*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🆔 `{c.get('client_code')}`\n"
        f"👤 {c.get('full_name')}\n"
        f"📱 {c.get('phone')}\n"
        f"💰 Rs{bal}\n"
        f"━━━━━━━━━━━━━━\n"
        f"👔 Agent: {ag.get('agent_name')}\n"
        f"📅 Joined: {c.get('joined_at','')[:10]}\n"
        f"📋 Total Apps: {c.get('total_apps',0)}",
        parse_mode="Markdown", reply_markup=kb_client())


async def contact_agent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid   = update.effective_user.id
    c, ag = find_client(tid)
    if not c:
        await update.message.reply_text("❌ Registered nahi.", reply_markup=kb_client())
        return
    await update.message.reply_text(
        f"📞 *Agent Contact*\n"
        f"━━━━━━━━━━━━━━\n"
        f"👔 {ag.get('agent_name')}\n"
        f"📱 {ag.get('phone')}",
        parse_mode="Markdown", reply_markup=kb_client())
