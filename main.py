import subprocess
subprocess.run(["pip", "install", "python-telegram-bot==20.7", "requests", "httpx"])

import logging
import requests
import time
import threading
import asyncio
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update

TELEGRAM_TOKEN = "8905271121:AAG_mv76V_QVKACvDR51v_5mGK4ajECkURY"
API_KEY = "15d971190e1b52fde7cf428428faa376"
CHAT_IDS = ["6590354226"]

logging.basicConfig(level=logging.INFO)
jogos = set()

def get_matches():
    try:
        r = requests.get("https://v3.football.api-sports.io/fixtures", headers={"x-apisports-key": API_KEY}, params={"live": "all"}, timeout=10)
        return r.json().get("response", [])
    except:
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Robô Over Gols ativo!")

async def loop(bot):
    while True:
        for f in get_matches():
            try:
                fid = f["fixture"]["id"]
                el = f["fixture"]["status"]["elapsed"] or 0
                hg = f["goals"]["home"] or 0
                ag = f["goals"]["away"] or 0
                if 55 <= el <= 80 and 1 <= hg+ag <= 2 and fid not in jogos:
                    jogos.add(fid)
                    for c in CHAT_IDS:
                        await bot.send_message(c, f"⚽ SINAL: {f['teams']['home']['name']} {hg}-{ag} {f['teams']['away']['name']} ({el}')")
            except:
                pass
        await asyncio.sleep(60)

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    asyncio.create_task(loop(app.bot))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
