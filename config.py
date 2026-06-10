import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing in environment variables.")

CHANNEL_ID = os.getenv("CHANNEL_ID")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID is missing in environment variables.")
CHANNEL_ID = int(CHANNEL_ID)

ROOT_ID = os.getenv("ROOT_ID", "1316030158")
try:
    ROOT_ID = int(ROOT_ID)
except ValueError:
    ROOT_ID = 1316030158

DB_PATH = os.getenv("DB_PATH", "data/database.db")
