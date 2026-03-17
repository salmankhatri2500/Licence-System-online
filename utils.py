import random, string
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
_user_data: dict = {}

def user_data(tid: int) -> dict:
    if tid not in _user_data:
        _user_data[tid] = {}
    return _user_data[tid]

def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

def today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")

def month_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m")

def gen_agent_id() -> str:
    return f"AGT-{random.randint(1000,9999)}"

def gen_client_code(agent_id: str) -> str:
    tag  = agent_id.replace("AGT-","").replace("-","")
    rand = ''.join(random.choices(string.digits, k=3))
    return f"FOS-{tag}-{rand}"

def gen_app_id() -> str:
    return f"APP-{''.join(random.choices(string.ascii_uppercase+string.digits, k=6))}"

def gen_pay_id() -> str:
    return f"PAY-{''.join(random.choices(string.ascii_uppercase+string.digits, k=6))}"

def valid_phone(p: str) -> bool:
    return p.isdigit() and len(p) == 10

def valid_dob(d: str) -> bool:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            datetime.strptime(d, fmt)
            return True
        except:
            pass
    return False

def safe_float(v) -> float:
    try:
        return float(str(v).replace(",","").strip())
    except:
        return 0.0

def safe_int(v) -> int:
    try:
        return int(float(str(v).strip()))
    except:
        return 0

def divider() -> str:
    return "─" * 28
