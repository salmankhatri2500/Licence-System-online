from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

REMOVE = ReplyKeyboardRemove()

def kb_admin():
    return ReplyKeyboardMarkup([
        ["📊 Dashboard",      "👥 All Agents"],
        ["➕ Add Agent",      "🔍 Find Agent"],
        ["📋 Queue",          "✅ Done Apps"],
        ["💰 Agent Payments", "⚙️ Settings"],
        ["📢 Broadcast All",  "📈 Monthly Report"],
    ], resize_keyboard=True)

def kb_agent():
    return ReplyKeyboardMarkup([
        ["📥 My Queue",      "📊 Today Summary"],
        ["👥 My Clients",    "📈 My Stats"],
        ["💳 My Balance",    "💰 Pay Admin"],
        ["🔗 Referral Link", "⚙️ Settings"],
        ["📢 Broadcast",     "🔄 Refresh"],
    ], resize_keyboard=True)

def kb_client():
    return ReplyKeyboardMarkup([
        ["📋 New Application"],
        ["📊 My Apps",       "📜 My History"],
        ["💳 Pay / Get QR",  "💰 My Balance"],
        ["ℹ️ My Profile",    "📞 Contact Agent"],
    ], resize_keyboard=True)
