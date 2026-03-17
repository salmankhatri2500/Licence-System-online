# jobs.py — Scheduled Jobs
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)
IST    = ZoneInfo("Asia/Kolkata")


async def check_agent_balance_reminders(bot):
    """
    Har 2.5 ghante mein check karo:
    Agent ka balance agar 5 applications se kam bacha ho → reminder bhejo.
    """
    try:
        from db import all_agents, get_agent_balance, get_admin_rate, agent_status
        admin_rate = get_admin_rate()
        if admin_rate <= 0:
            return
        threshold = admin_rate * 5   # 5 apps ka balance
        for ag in all_agents():
            if agent_status(ag) != "active":
                continue
            bal    = get_agent_balance(ag["agent_id"])
            ag_tid = int(ag.get("telegram_id", 0))
            if not ag_tid:
                continue
            if bal < threshold:
                apps_left = int(bal // admin_rate) if admin_rate > 0 else 0
                try:
                    await bot.send_message(
                        ag_tid,
                        f"⚠️ *Low Balance Reminder!*\n\n"
                        f"💰 Current balance: Rs{bal}\n"
                        f"📋 Apps remaining: ~{apps_left}\n\n"
                        f"Please top-up your balance to continue processing applications.\n"
                        f"Use *💰 Pay Admin* button.",
                        parse_mode="Markdown")
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"check_agent_balance_reminders: {e}")


async def check_client_balance_reminders(bot):
    """
    Har 2.5 ghante mein check karo:
    Client ka balance agar 5 applications se kam bacha ho → reminder bhejo.
    """
    try:
        from db import all_agents, all_clients, get_balance, agent_status
        from utils import safe_float
        for ag in all_agents():
            if agent_status(ag) != "active":
                continue
            rate = safe_float(ag.get("rate_per_app", 0))
            if rate <= 0:
                continue
            threshold = rate * 5
            for c in all_clients(ag):
                if c.get("status") == "blocked":
                    continue
                bal    = get_balance(ag, c["client_code"])
                c_tid  = int(c.get("telegram_id", 0))
                if not c_tid:
                    continue
                if bal < threshold:
                    apps_left = int(bal // rate) if rate > 0 else 0
                    try:
                        await bot.send_message(
                            c_tid,
                            f"⚠️ *Balance Low!*\n\n"
                            f"💰 Balance: Rs{bal}\n"
                            f"📋 Apps possible: ~{apps_left}\n\n"
                            f"Recharge karo taaki applications submit kar sako.\n"
                            f"Use *💳 Pay / Get QR* button.",
                            parse_mode="Markdown")
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"check_client_balance_reminders: {e}")


def register_jobs(app):
    try:
        scheduler = AsyncIOScheduler(timezone=IST)

        # Agent balance check — har 2.5 ghante
        scheduler.add_job(
            check_agent_balance_reminders,
            "interval",
            minutes=150,
            args=[app.bot],
            id="agent_bal_reminder",
            replace_existing=True)

        # Client balance check — har 2.5 ghante (offset 75 min)
        scheduler.add_job(
            check_client_balance_reminders,
            "interval",
            minutes=150,
            args=[app.bot],
            id="client_bal_reminder",
            replace_existing=True)

        scheduler.start()
        logger.info("Jobs scheduler started — balance reminders active")
    except Exception as e:
        logger.warning(f"Jobs scheduler error: {e}")
