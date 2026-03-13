"""Configuration for cita extranjeria checker."""

# --- Website Settings ---
BASE_URL = "https://icp.administracionelectronica.gob.es/icpplustieb/citar?p=8&locale=es"

# Province is already Barcelona (p=8 in URL)
TRAMITE_VALUE = "4112"  # POLICÍA TARJETA CONFLICTO UCRANIA

# Office: "99" = Cualquier oficina, or pick a specific one
OFFICE_VALUE = "99"  # Cualquier oficina (any office)

# --- Personal Data (required to proceed past the form) ---
# Document type: "nie", "passport", or "dni"
DOC_TYPE = "nie"
DOC_NUMBER = ""  # e.g. "Y1234567X"
FULL_NAME = ""   # e.g. "IVAN PETROV"
# Country of nationality (Spain site value) - for Ukraine use "UCRANIA"
COUNTRY = "UCRANIA"

# --- Schedule ---
# Normal schedule: check at these minutes past each hour
CHECK_MINUTES = [2, 4, 6, 12, 17, 22, 32, 36, 42]

# Hot windows (optional): no special behavior, same pace as normal
HOT_WINDOWS = []

WAF_BACKOFF_SECONDS = 360  # wait this long if WAF blocks us

# --- Notification Settings ---
# macOS notifications + sound (always enabled)
# Telegram (optional - fill in to enable)
TELEGRAM_BOT_TOKEN = ""  # Get from @BotFather
TELEGRAM_CHAT_ID = ""    # Get from @userinfobot
