import os, json

BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "6806779180"))
MASTER_SHEET   = "FOS_Master"
ADMIN_GMAIL    = "salmankhatri299@gmail.com"
TRIAL_DAYS     = 0

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_raw = os.environ.get("GOOGLE_CREDS_JSON", "")
if _raw:
    try:
        GOOGLE_CREDS = json.loads(_raw)
    except Exception as e:
        print(f"GOOGLE_CREDS_JSON parse error: {e}")
        GOOGLE_CREDS = {}
else:
    GOOGLE_CREDS = {}

# ── Conversation States ──────────────────────────────────────
(REG_NAME, REG_PHONE)                      = range(2)
(AA_NAME, AA_PHONE, AA_TID, AA_RATE, AA_SHEET) = range(10, 15)
(APP_NO, APP_DOB, APP_PASS)                = range(20, 23)
(PAY_AMOUNT,)                              = range(30, 31)
(AGENT_PAY_AMOUNT,)                        = range(35, 36)
(BC_TYPE, BC_MSG)                          = range(40, 42)
(ABC_TYPE, ABC_MSG)                        = range(50, 52)
UR_RATE = 60
