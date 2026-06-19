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
API_KEY = "15d971190e1b52fde7cf428428faa376"
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
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": API_KEY},
            params={"live": "all"},
            timeout=15
        )
        return r.json().get("response", [])
    except Exception as e:
        logger.error(f"Erro API: {e}")
        return []

def calcular_stats(fixture):
    stats = {}
    for team_stats in fixture.get("statistics", []):
        for stat in team_stats.get("statistics", []):
            key = stat.get("type", "")
            val = stat.get("value") or 0
            try:
                val = int(str(val).replace("%", ""))
            except:
                val = 0
            stats[key] = stats.get(key, 0) + val
    return stats

def calcular_pontos(stats, elapsed, total_gols):
    pontos = 0

    # Janela de tempo
    if JANELA_MIN <= elapsed <= JANELA_MAX:
        pontos += 25

    # Placar aberto
    if MIN_GOLS <= total_gols <= MAX_GOLS:
        pontos += 20

    # Arremates
    chutes = stats.get("Total Shots", 0)
    if chutes >= 20: pontos += 25
    elif chutes >= 15: pontos += 18
    elif chutes >= 10: pontos += 10
    elif chutes >= 5: pontos += 5

    # Chutes no alvo
    alvo = stats.get("Shots on Goal", 0)
    if alvo >= 8: pontos += 20
    elif alvo >= 5: pontos += 14
    elif alvo >= 3: pontos += 8

    # Escanteios
    escanteios = stats.get("Corner Kicks", 0)
    if escanteios >= 10: pontos += 15
    elif escanteios >= 7: pontos += 10
    elif escanteios >= 4: pontos += 6

    # Faltas (pressão)
    faltas = stats.get("Total passes", 0)
    if faltas >= 200: pontos += 10
    elif faltas >= 150: pontos += 6

    return pontos

def determinar_sinal(pontos):
    if pontos >= 75: return "🔴 ALTO"
    elif pontos >= 55: return "🟡 MÉDIO"
    elif pontos >= 35: return "🟢 BAIXO"
    return None

def check():
    while True:
        try:
            partidas = get_matches()
            logger.info(f"Partidas ao vivo: {len(partidas)}")

            for f in partidas:
                try:
                    fid = f["fixture"]["id"]
                    elapsed = f["fixture"]["status"]["elapsed"] or 0
                    hg = f["goals"]["home"] or 0
                    ag = f["goals"]["away"] or 0
                    total_gols = hg + ag
                    liga = f["league"]["name"]
                    home = f["teams"]["home"]["name"]
                    away = f["teams"]["away"]["name"]

                    if not (JANELA_MIN <= elapsed <= JANELA_MAX):
                        continue
                    if not (MIN_GOLS <= total_gols <= MAX_GOLS):
                        continue

                    chave = f"{fid}_{elapsed // 5}"
                    if chave in jogos_sinalizados:
                        continue

                    stats = calcular_stats(f)
                    pontos = calcular_pontos(stats, elapsed, total_gols)
                    sinal = determinar_sinal(pontos)

                    if not sinal:
                        continue

                    chutes = stats.get("Total Shots", 0)
                    alvo = stats.get("Shots on Goal", 0)
                    escanteios = stats.get("Corner Kicks", 0)

                    msg = (
                        f"🤖 *ROBÔ OVER GOLS*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🏆 {liga}\n"
                        f"⚽ *{home} v {away}*\n"
                        f"⏱ {elapsed}' | 🔢 {hg}-{ag} | 🎯 {pontos}pts\n\n"
                        f"📊 *ESTATÍSTICAS:*\n"
                        f"• Arremates: {chutes}\n"
                        f"• No Alvo: {alvo}\n"
                        f"• Escanteios: {escanteios}\n\n"
                        f"🚨 *{sinal}: MAIS 1 GOL*\n"
                        f"✅ Janela ideal ({JANELA_MIN}-{JANELA_MAX}min)\n"
                        f"✅ Placar aberto\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )

                    bot.send_message(CHAT, msg, parse_mode="Markdown")
                    jogos_sinalizados.add(chave)
                    logger.info(f"Sinal enviado: {home} vs {away} ({elapsed}')")

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
        "Comandos:\n"
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
        h = f.get("teams", {}).get("home", {}).get("name", "")
        a = f.get("teams", {}).get("away", {}).get("name", "")
        hg = f.get("goals", {}).get("home") or 0
        ag = f.get("goals", {}).get("away") or 0
        el = f.get("fixture", {}).get("status", {}).get("elapsed") or 0
        msg += f"• {h} {hg}-{ag} {a} ({el}')\n"
    bot.reply_to(m, msg, parse_mode="Markdown")

logger.info("🤖 Bot iniciado!")
threading.Thread(target=check, daemon=True).start()
bot.infinity_polling()
