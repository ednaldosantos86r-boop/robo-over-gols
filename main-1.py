import subprocess
subprocess.run(["pip", "install", "pyTelegramBotAPI", "requests"])

import telebot
import requests
import time
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8905271121:AAG_mv76V_QVKACvDR51v_5mGK4ajECkURY"
API_KEY = "1233c27be0dc44339b8721ba5a1e9838"
API_URL = "https://api.football-data.org/v4"
CHAT = "6590354226"

JANELA_MIN = 55
JANELA_MAX = 80
MIN_GOLS = 1
MAX_GOLS = 2

bot = telebot.TeleBot(TOKEN)
jogos_sinalizados = set()

def get_matches():
    try:
        r = requests.get(
            f"{API_URL}/matches",
            headers={"X-Auth-Token": API_KEY},
            params={"status": "LIVE"},
            timeout=15
        )
        data = r.json()
        return data.get("matches", [])
    except Exception as e:
        logger.error(f"Erro API: {e}")
        return []

def calcular_pontos(elapsed, total_gols):
    pontos = 0
    if JANELA_MIN <= elapsed <= JANELA_MAX:
        pontos += 40
    if MIN_GOLS <= total_gols <= MAX_GOLS:
        pontos += 35
    if elapsed >= 65:
        pontos += 15
    return pontos

def determinar_sinal(pontos):
    if pontos >= 80: return "🔴 ALTO"
    elif pontos >= 60: return "🟡 MÉDIO"
    elif pontos >= 40: return "🟢 BAIXO"
    return None

def check():
    while True:
        try:
            partidas = get_matches()
            logger.info(f"Partidas ao vivo: {len(partidas)}")

            for f in partidas:
                try:
                    fid = f.get("id")
                    elapsed = f.get("minute") or 0
                    score = f.get("score", {})
                    ft = score.get("fullTime", {})
                    hg = ft.get("home") or 0
                    ag = ft.get("away") or 0
                    total_gols = hg + ag

                    liga = f.get("competition", {}).get("name", "Liga")
                    home = f.get("homeTeam", {}).get("name", "Casa")
                    away = f.get("awayTeam", {}).get("name", "Fora")

                    if not (JANELA_MIN <= elapsed <= JANELA_MAX):
                        continue
                    if not (MIN_GOLS <= total_gols <= MAX_GOLS):
                        continue

                    chave = f"{fid}_{elapsed // 5}"
                    if chave in jogos_sinalizados:
                        continue

                    pontos = calcular_pontos(elapsed, total_gols)
                    sinal = determinar_sinal(pontos)

                    if not sinal:
                        continue

                    msg = (
                        f"🤖 *ROBÔ OVER GOLS*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🏆 {liga}\n"
                        f"⚽ *{home} v {away}*\n"
                        f"⏱ {elapsed}' | 🔢 {hg}-{ag} | 🎯 {pontos}pts\n\n"
                        f"🚨 *{sinal}: MAIS 1 GOL*\n"
                        f"✅ Janela ideal ({JANELA_MIN}-{JANELA_MAX}min)\n"
                        f"✅ Placar aberto\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )

                    bot.send_message(CHAT, msg, parse_mode="Markdown")
                    jogos_sinalizados.add(chave)
                    logger.info(f"Sinal: {home} vs {away} ({elapsed}')")

                except Exception as e:
                    logger.error(f"Erro partida: {e}")

        except Exception as e:
            logger.error(f"Erro loop: {e}")

        time.sleep(60)

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m,
        "🤖 *ROBÔ OVER GOLS*\n\n"
        "Bot ativo e monitorando!\n\n"
        "/start - Iniciar\n"
        "/status - Ver status\n"
        "/aovivo - Partidas ao vivo",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["status"])
def status(m):
    bot.reply_to(m,
        f"✅ *Bot ativo!*\n\n"
        f"⏱ Verificando a cada 60s\n"
        f"🎯 Janela: {JANELA_MIN}-{JANELA_MAX} min\n"
        f"📊 Sinais emitidos: {len(jogos_sinalizados)}",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["aovivo"])
def aovivo(m):
    bot.reply_to(m, "🔍 Buscando partidas ao vivo...")
    partidas = get_matches()
    if not partidas:
        bot.reply_to(m, "❌ Nenhuma partida ao vivo no momento.")
        return
    msg = f"⚽ *{len(partidas)} partidas ao vivo:*\n\n"
    for f in partidas[:15]:
        h = f.get("homeTeam", {}).get("name", "")
        a = f.get("awayTeam", {}).get("name", "")
        ft = f.get("score", {}).get("fullTime", {})
        hg = ft.get("home") or 0
        ag = ft.get("away") or 0
        el = f.get("minute") or 0
        msg += f"• {h} {hg}-{ag} {a} ({el}')\n"
    bot.reply_to(m, msg, parse_mode="Markdown")

logger.info("🤖 Bot iniciado!")
threading.Thread(target=check, daemon=True).start()
bot.infinity_polling()
