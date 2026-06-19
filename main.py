import subprocess
subprocess.run(["pip", "install", "python-telegram-bot==13.15", "requests"])

import logging
import requests
import time
import threading
from telegram.ext import Updater, CommandHandler

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

def start(update, context):
    update.message.reply_text("🤖 Robô Over Gols ativo!")

def loop(bot):
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
                        bot.send_message(c, f"⚽ SINAL: {f['teams']['home']['name']} {hg}-{ag} {f['teams']['away']['name']} ({el}')")
            except:
                pass
        time.sleep(60)

def main():
    u = Updater(TELEGRAM_TOKEN, use_context=True)
    u.dispatcher.add_handler(CommandHandler("start", start))
    threading.Thread(target=loop, args=(u.bot,), daemon=True).start()
    u.start_polling()
    u.idle()

main()
