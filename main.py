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
API_KEY = "bd6152b8255f5367d351055c441b518d"
API_URL = "https://v3.football.api-sports.io"
CHAT = "6590354226"

JANELA_MIN = 55
JANELA_MAX = 80
MIN_GOLS = 0
MAX_GOLS = 2

bot = telebot.TeleBot(TOKEN)
jogos_sinalizados = set()

def get_matches():
    try:
        r = requests.get(
            f"{API_URL}/fixtures",
            headers={"x-apisports-key": API_KEY},
            params={"live": "all"},
            timeout=15
        )
        return r.json().get("response", [])
    except Exception as e:
        logger.error(f"Erro API: {e}")
        return []

def get_stats(fixture_id):
    try:
        r = requests.get(
            f"{API_URL}/fixtures/statistics",
            headers={"x-apisports-key": API_KEY},
            params={"fixture": fixture_id},
            timeout=15
        )
        data = r.json().get("response", [])
        stats = {}
        for team in data:
            for s in team.get("statistics", []):
                key = s.get("type", "")
                val = s.get("value") or 0
                try:
                    val = int(str(val).replace("%", ""))
                except:
                    val = 0
                stats[key] = stats.get(key, 0) + val
        return stats
    except:
        return {}

def calcular_pontos(stats, elapsed, total_gols):
    pontos = 0
    if JANELA_MIN <= elapsed <= JANELA_MAX:
        pontos += 25
    if MIN_GOLS <= total_gols <= MAX_GOLS:
        pontos += 20

    chutes = stats.get("Total Shots", 0)
    if chutes >= 20: pontos += 25
    elif chutes >= 15: pontos += 18
    elif chutes >= 10: pontos += 10
    elif chutes >= 5: pontos += 5

    alvo = stats.get("Shots on Goal", 0)
    if alvo >= 8: pontos += 20
    elif alvo >= 5: pontos += 14
    elif alvo >= 3: pontos += 8

    escanteios = stats.get("Corner Kicks", 0)
    if escanteios >= 10: pontos += 15
    elif escanteios >= 7: pontos += 10
    elif escanteios >= 4: pontos += 6

    ataques = stats.get("Total attacks", 0)
    if ataques >= 100: pontos += 10
    elif ataques >= 60: pontos += 6

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
                    if total_gols > MAX_GOLS:
                        continue

                    chave = f"{fid}_{elapsed // 5}"
                    if chave in jogos_sinalizados:
                        continue

                    stats = get_stats(fid)
                    pontos = calcular_pontos(stats, elapsed, total_gols)
                    sinal = determinar_sinal(pontos)

                    if not sinal:
                        continue

                    chutes_gol = stats.get("Shots on Goal", 0)
                    chutes_fora = stats.get("Shots off Goal", 0)
                    escanteios = stats.get("Corner Kicks", 0)
                    ataques = stats.get("Total attacks", 0)
                    ataques_perigosos = stats.get("Dangerous Attacks", 0)
                    posse = stats.get("Ball Possession", 50)

                    # Posse por time
                    posse_home = 50
                    posse_away = 50
                    for team in f.get("statistics", []):
                        for s in team.get("statistics", []):
                            if s.get("type") == "Ball Possession":
                                val = str(s.get("value", "50%")).replace("%", "")
                                try:
                                    if team.get("team", {}).get("id") == f["teams"]["home"]["id"]:
                                        posse_home = int(val)
                                        posse_away = 100 - posse_home
                                except:
                                    pass

                    msg = (
                        f"🤖 *ROBÔ OVER GOLS*\n\n"
                        f"⚽ *{home} v {away}*\n"
                        f"🏆 {liga}\n"
                        f"⏱ {elapsed} minutos\n"
                        f"📊 Placar {hg} - {ag}\n\n"
                        f"📈 *Estatísticas (Casa - Fora):*\n"
                        f"Chutes ao gol: {chutes_gol}\n"
                        f"Chutes fora do gol: {chutes_fora}\n"
                        f"Escanteios: {escanteios}\n"
                        f"Ataques perigosos: {ataques_perigosos}\n"
                        f"Posse de bola: {posse_home}% - {posse_away}%\n\n"
                        f"🚨 *ALERTA DE ENTRADA*\n"
                        f"{sinal} - Over limite\n\n"
                        f"🎯 Pontuação: {pontos}pts"
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
