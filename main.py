import subprocess
subprocess.run(["pip", "install", "pyTelegramBotAPI", "requests"])
import telebot
import requests
import time

TOKEN = "8905271121:AAG_mv76V_QVKACvDR51v_5mGK4ajECkURY"
API_KEY = "15d971190e1b52fde7cf428428faa376"
CHAT = "6590354226"
bot = telebot.TeleBot(TOKEN)
jogos = set()

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m, "Robo Over Gols ativo!")

def check():
    while True:
        try:
            r = requests.get("https://v3.football.api-sports.io/fixtures", headers={"x-apisports-key": API_KEY}, params={"live": "all"}, timeout=10)
            for f in r.json().get("response", []):
                fid = f["fixture"]["id"]
                el = f["fixture"]["status"]["elapsed"] or 0
                hg = f["goals"]["home"] or 0
                ag = f["goals"]["away"] or 0
                if 55 <= el <= 80 and 1 <= hg+ag <= 2 and fid not in jogos:
                    jogos.add(fid)
                    h = f["teams"]["home"]["name"]
                    a = f["teams"]["away"]["name"]
                    bot.send_message(CHAT, f"SINAL: {h} {hg}-{ag} {a} ({el}')")
        except:
            pass
        time.sleep(60)

import threading
threading.Thread(target=check, daemon=True).start()
bot.infinity_polling()
