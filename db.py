# ================================================================
# db.py  —  FOS v4 Database
#
# FOS_Master              →  agents tab + logs tab
# <sheet_name>            →  agent ki manually banai sheet
#                            tabs: clients, applications, payments,
#                                  agent_payments, settings, queue
#
# QUEUE SYSTEM:
#   - Client application submit kare → queue mein PENDING
#   - Admin directly process kare → DONE
#   - Client + Agent ko notification
#
# BALANCE SYSTEM:
#   - Client → Agent (client balance)
#   - Agent  → Admin (agent balance)
# ================================================================

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound

from config import GOOGLE_CREDS, SCOPES, MASTER_SHEET, TRIAL_DAYS, ADMIN_GMAIL
from utils import now_ist, safe_float, safe_int, IST

logger = logging.getLogger(__name__)

# ── Tab Headers ───────────────────────────────────────────────
HDR = {
    "agents": [
        "agent_id","agent_name","phone","telegram_id","sheet_name",
        "rate_per_app","qr_file_id","joined_at","status",
        "total_apps","total_clients","trial_end","balance"
    ],
    "logs":    ["event","agent","detail","timestamp"],
    "clients": [
        "client_code","full_name","phone","telegram_id",
        "joined_at","status","total_apps","balance"
    ],
    "queue": [
        "queue_id","app_no","dob","password","client_code","client_name",
        "agent_id","agent_name","submitted_at","status","done_at","priority"
    ],
    "applications": [
        "app_id","app_no","dob","password","client_code",
        "agent_id","created_at","status","done_at","balance_deducted"
    ],
    "payments": [
        "payment_id","client_code","amount_paid","balance_added",
        "payment_date","payment_time","status","approved_by","approved_at"
    ],
    "agent_payments": [
        "payment_id","agent_id","amount_paid","balance_added",
        "payment_date","payment_time","status","approved_by","approved_at"
    ],
    "settings": ["key","value"],
}

COL_WIDTHS = {
    "agents":        [120,180,130,150,200,110,80,160,90,90,100,130,100],
    "clients":       [130,180,130,150,160,80,80,100],
    "queue":         [130,120,100,140,120,160,120,160,160,90,160,80],
    "applications":  [130,120,100,140,130,120,160,90,160,80],
    "payments":      [130,130,110,110,110,100,90,130,160],
    "agent_payments":[130,130,110,110,110,100,90,130,160],
    "settings":      [180,300],
    "logs":          [160,180,350,160],
}

HEADER_BG = {"red":0.13,"green":0.29,"blue":0.53}
HEADER_FG = {"red":1.0, "green":1.0, "blue":1.0}
ROW_BG = {
    "active":   {"red":0.72,"green":0.96,"blue":0.73},
    "trial":    {"red":1.0, "green":0.98,"blue":0.80},
    "pending":  {"red":1.0, "green":0.98,"blue":0.80},
    "done":     {"red":0.72,"green":0.96,"blue":0.73},
    "paid":     {"red":0.72,"green":0.96,"blue":0.73},
    "blocked":  {"red":1.0, "green":0.80,"blue":0.80},
    "expired":  {"red":1.0, "green":0.80,"blue":0.80},
    "rejected": {"red":1.0, "green":0.80,"blue":0.80},
    "high":     {"red":1.0, "green":0.85,"blue":0.70},
}


class DB:
    def __init__(self):
        self._gc  = None
        self._msh = None

    def connect(self) -> bool:
        try:
            creds    = Credentials.from_service_account_info(GOOGLE_CREDS, scopes=SCOPES)
            self._gc = gspread.authorize(creds)
            self._msh = None
            logger.info("db: Google Sheets connected")
            return True
        except Exception as e:
            logger.error(f"db: connect: {e}")
            return False

    def _gc_client(self):
        if not self._gc:
            self.connect()
        return self._gc

    def open(self, name: str):
        try:
            return self._gc_client().open(name)
        except SpreadsheetNotFound:
            return None
        except Exception:
            try:
                self.connect()
                return self._gc_client().open(name)
            except Exception as e:
                logger.error(f"db: open({name}): {e}")
                return None

    def master(self):
        if self._msh:
            try:
                _ = self._msh.title
                return self._msh
            except Exception:
                self._msh = None
        sh = self.open(MASTER_SHEET)
        if sh:
            self._msh = sh
            return sh
        logger.error("db: FOS_Master not found!")
        return None

    def ws(self, sh, name: str):
        if sh is None:
            return None
        try:
            return sh.worksheet(name)
        except WorksheetNotFound:
            return None

    def _ensure(self, sh, tab: str):
        try:
            return sh.worksheet(tab)
        except WorksheetNotFound:
            pass
        try:
            w = sh.add_worksheet(title=tab, rows=2000, cols=25)
            if tab in HDR:
                w.append_row(HDR[tab])
                self._fmt(w, tab)
            return w
        except Exception as e:
            logger.error(f"db: _ensure({tab}): {e}")
            return None

    def _fmt(self, ws, tab: str):
        try:
            ws_id = ws.id
            n     = len(HDR.get(tab, []))
            reqs  = []
            reqs.append({"repeatCell": {
                "range": {"sheetId":ws_id,"startRowIndex":0,"endRowIndex":1,
                          "startColumnIndex":0,"endColumnIndex":n},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": HEADER_BG,
                    "textFormat": {"foregroundColor":HEADER_FG,"bold":True,"fontSize":10},
                    "horizontalAlignment":"CENTER","verticalAlignment":"MIDDLE"
                }},
                "fields":"userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }})
            reqs.append({"updateSheetProperties": {
                "properties": {"sheetId":ws_id,"gridProperties":{"frozenRowCount":1}},
                "fields":"gridProperties.frozenRowCount"
            }})
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId":ws_id,"dimension":"ROWS","startIndex":0,"endIndex":2000},
                "properties": {"pixelSize":22},
                "fields":"pixelSize"
            }})
            for i, px in enumerate(COL_WIDTHS.get(tab, [])):
                if i >= n:
                    break
                reqs.append({"updateDimensionProperties": {
                    "range": {"sheetId":ws_id,"dimension":"COLUMNS",
                              "startIndex":i,"endIndex":i+1},
                    "properties": {"pixelSize":px},
                    "fields":"pixelSize"
                }})
            ws.spreadsheet.batch_update({"requests": reqs})
        except Exception as e:
            logger.warning(f"db: _fmt({tab}): {e}")

    def color_row(self, ws, row_idx: int, status: str):
        try:
            bg = ROW_BG.get(str(status).lower())
            if not bg:
                return
            ws.spreadsheet.batch_update({"requests": [{"repeatCell": {
                "range": {"sheetId":ws.id,
                          "startRowIndex":row_idx-1,"endRowIndex":row_idx,
                          "startColumnIndex":0,"endColumnIndex":ws.col_count},
                "cell": {"userEnteredFormat": {"backgroundColor":bg}},
                "fields":"userEnteredFormat.backgroundColor"
            }}]})
        except Exception as e:
            logger.warning(f"db: color_row: {e}")

    def rows_to_dicts(self, ws) -> list:
        try:
            rows = ws.get_all_values()
            if len(rows) < 2:
                return []
            headers = rows[0]
            out = []
            for row in rows[1:]:
                while len(row) < len(headers):
                    row.append("")
                if any(v.strip() for v in row):
                    out.append(dict(zip(headers, row)))
            return out
        except Exception:
            return []

    def find_row(self, ws, key_col: int, key_val: str):
        try:
            rows = ws.get_all_values()
            if not rows:
                return None, None
            headers = rows[0]
            for i, row in enumerate(rows[1:], start=2):
                while len(row) < len(headers):
                    row.append("")
                if row[key_col].strip() == str(key_val).strip():
                    return i, dict(zip(headers, row))
        except Exception:
            pass
        return None, None

    def update_field(self, ws, key_col: int, key_val: str, field: str, value) -> bool:
        try:
            rows = ws.get_all_values()
            if not rows:
                return False
            headers = rows[0]
            if field not in headers:
                return False
            col = headers.index(field) + 1
            for i, row in enumerate(rows[1:], start=2):
                if len(row) > key_col and row[key_col].strip() == str(key_val).strip():
                    ws.update_cell(i, col, value)
                    return True
        except Exception as e:
            logger.error(f"db: update_field({field}): {e}")
        return False


db = DB()


# ── Sheet helpers ─────────────────────────────────────────────
def _sh(agent: dict):
    sn = agent.get("sheet_name","")
    return db.open(sn) if sn else None

def _w(agent: dict, tab: str):
    sh = _sh(agent)
    return db._ensure(sh, tab) if sh else None

def _aws():
    sh = db.master()
    return db._ensure(sh, "agents") if sh else None

def _mlws():
    sh = db.master()
    return db._ensure(sh, "logs") if sh else None

def _qws():
    """Global queue in FOS_Master"""
    sh = db.master()
    return db._ensure(sh, "queue") if sh else None


# ================================================================
# AGENTS
# ================================================================

def all_agents() -> list:
    w = _aws()
    return db.rows_to_dicts(w) if w else []

def agent_by_tid(tid: int):
    s = str(tid).strip()
    for a in all_agents():
        if str(a.get("telegram_id","")).strip() == s:
            return a
    return None

def agent_by_id(aid: str):
    for a in all_agents():
        if a.get("agent_id","").strip() == aid.strip():
            return a
    return None

def add_agent(data: dict) -> bool:
    try:
        w  = _aws()
        if w is None:
            return False
        row = [data["agent_id"], data["agent_name"], data["phone"],
               str(data["telegram_id"]), data["sheet_name"], data["rate"],
               "", now_ist(), "active", 0, 0, "", 0]
        w.append_row(row)
        n = len(w.get_all_values())
        db.color_row(w, n, "active")
        master_log("AGENT_ADDED", data["agent_name"], f"ID:{data['agent_id']}")
        return True
    except Exception as e:
        logger.error(f"add_agent: {e}")
        return False

def set_agent_field(agent_id: str, field: str, value) -> bool:
    w = _aws()
    return db.update_field(w, 0, agent_id, field, value) if w else False

def remove_agent(agent_id: str) -> bool:
    try:
        w = _aws()
        if w is None:
            return False
        ri, _ = db.find_row(w, 0, agent_id)
        if ri:
            w.delete_rows(ri)
            return True
    except Exception as e:
        logger.error(f"remove_agent: {e}")
    return False

def agent_status(agent: dict) -> str:
    st = str(agent.get("status","active")).strip()
    if st in ("blocked","deleted"):
        return st
    return "active"

def trial_end_date(days=TRIAL_DAYS) -> str:
    return (datetime.now(IST) + timedelta(days=days)).strftime("%Y-%m-%d")

def master_log(event: str, agent: str, detail: str):
    try:
        w = _mlws()
        if w:
            w.append_row([event, agent, detail, now_ist()])
    except Exception:
        pass

def agent_log(agent: dict, event: str, user: str, role: str, detail: str = ""):
    master_log(event, user, detail)

# Agent balance
def get_agent_balance(agent_id: str) -> float:
    for a in all_agents():
        if a.get("agent_id","") == agent_id:
            return safe_float(a.get("balance", 0))
    return 0.0

def add_agent_balance(agent_id: str, amount: float) -> bool:
    cur = get_agent_balance(agent_id)
    return set_agent_field(agent_id, "balance", round(cur + amount, 2))

def deduct_agent_balance(agent_id: str, amount: float) -> bool:
    cur = get_agent_balance(agent_id)
    if cur < amount:
        return False
    return set_agent_field(agent_id, "balance", round(cur - amount, 2))


# ================================================================
# SETUP MANUAL SHEET
# ================================================================

def setup_manual_sheet(sheet_name: str, agent_id: str, agent_name: str, rate: float) -> bool:
    sh = db.open(sheet_name)
    if sh is None:
        logger.error(f"setup_manual_sheet: '{sheet_name}' not found")
        return False
    for tab in ("clients","applications","payments","agent_payments","settings"):
        try:
            existing = db.ws(sh, tab)
            if existing is None:
                db._ensure(sh, tab)
            else:
                rows = existing.get_all_values()
                if not rows or rows[0] != HDR[tab]:
                    existing.clear()
                    existing.append_row(HDR[tab])
                    db._fmt(existing, tab)
        except Exception as e:
            logger.warning(f"setup_manual_sheet {tab}: {e} (continuing)")
    try:
        sw   = db.ws(sh, "settings")
        rows = db.rows_to_dicts(sw)
        keys = {r.get("key","") for r in rows}
        for k, v in [("rate_per_app",str(rate)),("qr_file_id",""),
                     ("agent_name",agent_name),("agent_id",agent_id)]:
            if k not in keys:
                sw.append_row([k, v])
    except Exception as e:
        logger.error(f"setup_manual_sheet settings: {e}")
    return True


# ================================================================
# SETTINGS
# ================================================================

def get_setting(agent: dict, key: str) -> str:
    try:
        w = _w(agent, "settings")
        if w is None:
            return ""
        for r in db.rows_to_dicts(w):
            if r.get("key","").strip() == key:
                return r.get("value","")
    except Exception:
        pass
    return ""

def put_setting(agent: dict, key: str, value: str) -> bool:
    try:
        w = _w(agent, "settings")
        if w is None:
            return False
        rows = w.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            if row and row[0].strip() == key:
                w.update_cell(i, 2, value)
                return True
        w.append_row([key, value])
        return True
    except Exception as e:
        logger.error(f"put_setting: {e}")
        return False


# ================================================================
# CLIENTS
# ================================================================

def all_clients(agent: dict) -> list:
    w = _w(agent, "clients")
    return db.rows_to_dicts(w) if w else []

def find_client(tid: int):
    s = str(tid).strip()
    for ag in all_agents():
        if agent_status(ag) == "deleted":
            continue
        for c in all_clients(ag):
            if str(c.get("telegram_id","")).strip() == s:
                return c, ag
    return {}, {}

def client_by_code(agent: dict, code: str):
    for c in all_clients(agent):
        if c.get("client_code","").strip() == code.strip():
            return c
    return None

def add_client(agent: dict, data: dict) -> bool:
    try:
        w = _w(agent, "clients")
        if w is None:
            return False
        row = [data["client_code"], data["full_name"],
               str(data["phone"]), str(data["telegram_id"]),
               now_ist(), "active", 0, 0]
        w.append_row(row)
        n = len(w.get_all_values())
        db.color_row(w, n, "active")
        try:
            cur = safe_int(agent.get("total_clients",0))
            set_agent_field(agent["agent_id"], "total_clients", cur+1)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"add_client: {e}")
        return False

def set_client_field(agent: dict, client_code: str, field: str, value) -> bool:
    w = _w(agent, "clients")
    if w is None:
        return False
    ok = db.update_field(w, 0, client_code, field, value)
    if ok and field == "status":
        ri, _ = db.find_row(w, 0, client_code)
        if ri:
            db.color_row(w, ri, str(value))
    return ok

def get_balance(agent: dict, client_code: str) -> float:
    w = _w(agent, "clients")
    if w is None:
        return 0.0
    _, row = db.find_row(w, 0, client_code)
    return safe_float(row.get("balance",0)) if row else 0.0

def add_balance(agent: dict, client_code: str, amount: float) -> bool:
    cur = get_balance(agent, client_code)
    return set_client_field(agent, client_code, "balance", round(cur+amount, 2))

def deduct_balance(agent: dict, client_code: str, amount: float) -> bool:
    cur = get_balance(agent, client_code)
    if cur < amount:
        return False
    return set_client_field(agent, client_code, "balance", round(cur-amount, 2))

def inc_client_apps(agent: dict, client_code: str):
    w = _w(agent, "clients")
    if w is None:
        return
    _, row = db.find_row(w, 0, client_code)
    if row:
        db.update_field(w, 0, client_code, "total_apps",
                        safe_int(row.get("total_apps",0))+1)


# ================================================================
# QUEUE SYSTEM (Global — FOS_Master mein)
# ================================================================

def queue_add(data: dict) -> bool:
    try:
        w = _qws()
        if w is None:
            return False
        row = [
            data["queue_id"], data["app_no"], data["dob"], data["password"],
            data["client_code"], data["client_name"],
            data["agent_id"], data["agent_name"],
            now_ist(), "PENDING", "", data.get("priority","normal")
        ]
        w.append_row(row)
        n = len(w.get_all_values())
        db.color_row(w, n, "pending")
        return True
    except Exception as e:
        logger.error(f"queue_add: {e}")
        return False

def queue_pending() -> list:
    w = _qws()
    if w is None:
        return []
    all_rows = db.rows_to_dicts(w)
    pending  = [r for r in all_rows if r.get("status","").upper() == "PENDING"]
    # Sort: high priority first, then by time
    pending.sort(key=lambda x: (0 if x.get("priority","") == "high" else 1,
                                 x.get("submitted_at","")))
    return pending

def queue_all() -> list:
    w = _qws()
    return db.rows_to_dicts(w) if w else []

def queue_mark_done(queue_id: str) -> bool:
    w = _qws()
    if w is None:
        return False
    ok = db.update_field(w, 0, queue_id, "status", "DONE")
    db.update_field(w, 0, queue_id, "done_at", now_ist())
    if ok:
        ri, _ = db.find_row(w, 0, queue_id)
        if ri:
            db.color_row(w, ri, "done")
    return ok

def queue_get(queue_id: str) -> dict:
    w = _qws()
    if w is None:
        return {}
    _, row = db.find_row(w, 0, queue_id)
    return row or {}

def queue_today_count() -> dict:
    today = datetime.now(IST).strftime("%Y-%m-%d")
    all_q = queue_all()
    today_q = [r for r in all_q if r.get("submitted_at","").startswith(today)]
    return {
        "total":   len(today_q),
        "pending": sum(1 for r in today_q if r.get("status","").upper() == "PENDING"),
        "done":    sum(1 for r in today_q if r.get("status","").upper() == "DONE"),
    }


# ================================================================
# APPLICATIONS (agent sheet mein copy for records)
# ================================================================

def all_apps(agent: dict) -> list:
    w = _w(agent, "applications")
    return db.rows_to_dicts(w) if w else []

def add_app(agent: dict, data: dict) -> bool:
    try:
        w = _w(agent, "applications")
        if w is None:
            return False
        row = [data["app_id"], data["app_no"], data["dob"], data["password"],
               data["client_code"], agent.get("agent_id",""),
               now_ist(), "PENDING", "", ""]
        w.append_row(row)
        n = len(w.get_all_values())
        db.color_row(w, n, "pending")
        try:
            cur = safe_int(agent.get("total_apps",0))
            set_agent_field(agent["agent_id"], "total_apps", cur+1)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"add_app: {e}")
        return False

def mark_app_done(agent: dict, app_id: str) -> bool:
    w = _w(agent, "applications")
    if w is None:
        return False
    ok = db.update_field(w, 0, app_id, "status", "DONE")
    db.update_field(w, 0, app_id, "done_at", now_ist())
    if ok:
        ri, _ = db.find_row(w, 0, app_id)
        if ri:
            db.color_row(w, ri, "done")
    return ok


# ================================================================
# CLIENT PAYMENTS (Client → Agent)
# ================================================================

def all_payments(agent: dict) -> list:
    w = _w(agent, "payments")
    return db.rows_to_dicts(w) if w else []

def add_payment(agent: dict, data: dict) -> bool:
    try:
        w = _w(agent, "payments")
        if w is None:
            return False
        now = datetime.now(IST)
        row = [data["pay_id"], data["client_code"], data["amount"], "",
               now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
               "PENDING", "", ""]
        w.append_row(row)
        n = len(w.get_all_values())
        db.color_row(w, n, "pending")
        return True
    except Exception as e:
        logger.error(f"add_payment: {e}")
        return False

def approve_payment(agent: dict, pay_id: str, approved_by: str) -> bool:
    w = _w(agent, "payments")
    if w is None:
        return False
    for f, v in [("status","PAID"),("approved_by",approved_by),("approved_at",now_ist())]:
        db.update_field(w, 0, pay_id, f, v)
    ri, _ = db.find_row(w, 0, pay_id)
    if ri:
        db.color_row(w, ri, "paid")
    return True

def reject_payment(agent: dict, pay_id: str) -> bool:
    w = _w(agent, "payments")
    if w is None:
        return False
    db.update_field(w, 0, pay_id, "status", "REJECTED")
    ri, _ = db.find_row(w, 0, pay_id)
    if ri:
        db.color_row(w, ri, "rejected")
    return True


# ================================================================
# AGENT PAYMENTS (Agent → Admin)
# ================================================================

def all_agent_payments(agent: dict) -> list:
    w = _w(agent, "agent_payments")
    return db.rows_to_dicts(w) if w else []

def add_agent_payment(agent: dict, data: dict) -> bool:
    try:
        w = _w(agent, "agent_payments")
        if w is None:
            return False
        now = datetime.now(IST)
        row = [data["pay_id"], agent.get("agent_id",""), data["amount"], "",
               now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
               "PENDING", "", ""]
        w.append_row(row)
        n = len(w.get_all_values())
        db.color_row(w, n, "pending")
        return True
    except Exception as e:
        logger.error(f"add_agent_payment: {e}")
        return False

def approve_agent_payment(agent: dict, pay_id: str) -> bool:
    w = _w(agent, "agent_payments")
    if w is None:
        return False
    for f, v in [("status","PAID"),("approved_by","admin"),("approved_at",now_ist())]:
        db.update_field(w, 0, pay_id, f, v)
    ri, _ = db.find_row(w, 0, pay_id)
    if ri:
        db.color_row(w, ri, "paid")
    return True

def reject_agent_payment(agent: dict, pay_id: str) -> bool:
    w = _w(agent, "agent_payments")
    if w is None:
        return False
    db.update_field(w, 0, pay_id, "status", "REJECTED")
    ri, _ = db.find_row(w, 0, pay_id)
    if ri:
        db.color_row(w, ri, "rejected")
    return True


# ================================================================
# detect_role
# ================================================================

def detect_role(tid: int) -> str:
    from config import SUPER_ADMIN_ID
    if tid == SUPER_ADMIN_ID:
        return "admin"
    if agent_by_tid(tid):
        return "agent"
    c, _ = find_client(tid)
    if c:
        return "client"
    return "unknown"


# ================================================================
# HELD QUEUE — Agent balance kam hone par apps hold hoti hain
# ================================================================

def queue_held_by_agent(agent_id: str) -> list:
    """Get all HELD apps for this agent."""
    w = _qws()
    if w is None:
        return []
    return [r for r in db.rows_to_dicts(w)
            if r.get("agent_id") == agent_id and r.get("status","").upper() == "HELD"]

def queue_mark_held(queue_id: str) -> bool:
    w = _qws()
    if w is None:
        return False
    ok = db.update_field(w, 0, queue_id, "status", "HELD")
    if ok:
        ri, _ = db.find_row(w, 0, queue_id)
        if ri:
            db.color_row(w, ri, "blocked")
    return ok

def queue_release_held(agent_id: str) -> list:
    """Release all HELD apps for agent → set back to PENDING. Returns released list."""
    w = _qws()
    if w is None:
        return []
    held     = queue_held_by_agent(agent_id)
    released = []
    for item in held:
        qid = item.get("queue_id","")
        if qid:
            db.update_field(w, 0, qid, "status", "PENDING")
            ri, _ = db.find_row(w, 0, qid)
            if ri:
                db.color_row(w, ri, "pending")
            released.append(item)
    return released


# ================================================================
# ADMIN QR
# ================================================================

def get_admin_qr() -> str:
    """Get admin QR file_id from FOS_Master settings tab."""
    sh = db.master()
    if sh is None:
        return ""
    try:
        w = db._ensure(sh, "admin_settings")
        for r in db.rows_to_dicts(w):
            if r.get("key","").strip() == "qr_file_id":
                return r.get("value","")
    except Exception:
        pass
    return ""

def set_admin_qr(file_id: str) -> bool:
    """Save admin QR to FOS_Master admin_settings tab."""
    sh = db.master()
    if sh is None:
        return False
    try:
        w    = db._ensure(sh, "admin_settings")
        rows = w.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            if row and row[0].strip() == "qr_file_id":
                w.update_cell(i, 2, file_id)
                return True
        w.append_row(["qr_file_id", file_id])
        return True
    except Exception as e:
        logger.error(f"set_admin_qr: {e}")
        return False


def get_admin_setting(key: str) -> str:
    sh = db.master()
    if sh is None:
        return ""
    try:
        w = db._ensure(sh, "admin_settings")
        for r in db.rows_to_dicts(w):
            if r.get("key","").strip() == key:
                return r.get("value","")
    except Exception:
        pass
    return ""

def set_admin_setting(key: str, value: str) -> bool:
    sh = db.master()
    if sh is None:
        return False
    try:
        w    = db._ensure(sh, "admin_settings")
        rows = w.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            if row and row[0].strip() == key:
                w.update_cell(i, 2, value)
                return True
        w.append_row([key, value])
        return True
    except Exception as e:
        logger.error(f"set_admin_setting({key}): {e}")
        return False

def get_admin_rate() -> float:
    """Admin ka per-application rate (jo agent se charge hoga)."""
    val = get_admin_setting("rate_per_app")
    return safe_float(val) if val else 0.0
