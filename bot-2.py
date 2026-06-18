import logging
import requests
from telegram import Bot
from telegram.ext import Updater, CommandHandler
import time
import threading

# ============================================================
# CONFIGURAÇÕES
# ============================================================
TELEGRAM_TOKEN = "8905271121:AAG_mv76V_QVKACvDR51v_5mGK4ajECkURY"
API_FOOTBALL_KEY = "15d971190e1b52fde7cf428428faa376"
API_FOOTBALL_URL = "https://v3.football.api-sports.io"

CHAT_IDS = ["6590354226"]

CHECK_INTERVAL = 60
JANELA_MIN = 55
JANELA_MAX = 80
MIN_GOLS = 1
MAX_GOLS = 2

PONTOS_MINIMO_ALTO = 70
PONTOS_MINIMO_MEDIO = 50
PONTOS_MINIMO_BAIXO = 30

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

jogos_sinalizados = set()

# ============================================================
# FUNÇÕES DA API
# ============================================================

def get_live_matches():
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    try:
        response = requests.get(
            f"{API_FOOTBALL_URL}/fixtures",
            headers=headers,
            params={"live": "all"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("response", [])
        else:
            logger.error(f"Erro API: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Erro ao buscar partidas: {e}")
        return []

def calcular_pontuacao(fixture):
    pontos = 0
    stats_dict = {}
    
    for team_stats in fixture.get("statistics", []):
        for stat in team_stats.get("statistics", []):
            key = stat.get("type", "")
            value = stat.get("value") or 0
            if isinstance(value, str):
                value = int(value.replace("%", "")) if "%" in value else 0
            if key not in stats_dict:
                stats_dict[key] = 0
            stats_dict[key] += int(value)

    total_chutes = stats_dict.get("Total Shots", 0)
    chutes_gol = stats_dict.get("Shots on Goal", 0)
    escanteios = stats_dict.get("Corner Kicks", 0)

    if total_chutes >= 20: pontos += 30
    elif total_chutes >= 15: pontos += 20
    elif total_chutes >= 10: pontos += 10

    if chutes_gol >= 8: pontos += 25
    elif chutes_gol >= 5: pontos += 15
    elif chutes_gol >= 3: pontos += 10

    if escanteios >= 10: pontos += 25
    elif escanteios >= 7: pontos += 15
    elif escanteios >= 4: pontos += 10

    pontos += 20

    return pontos, stats_dict

def determinar_sinal(pontos):
    if pontos >= PONTOS_MINIMO_ALTO:
        return "🔴 SINAL ALTO"
    elif pontos >= PONTOS_MINIMO_MEDIO:
        return "🟡 SINAL MÉDIO"
    elif pontos >= PONTOS_MINIMO_BAIXO:
        return "🟢 SINAL BAIXO"
    return None

def formatar_mensagem(fixture, sinal, pontos, stats_dict):
    league = fixture.get("league", {})
    teams = fixture.get("teams", {})
    goals = fixture.get("goals", {})
    elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed", 0)

    home_team = teams.get("home", {}).get("name", "Casa")
    away_team = teams.get("away", {}).get("name", "Fora")
    home_goals = goals.get("home", 0) or 0
    away_goals = goals.get("away", 0) or 0
    league_name = league.get("name", "Liga")

    total_chutes = stats_dict.get("Total Shots", 0)
    chutes_gol = stats_dict.get("Shots on Goal", 0)
    escanteios = stats_dict.get("Corner Kicks", 0)

    return f"""
🤖 *ROBÔ OVER GOLS*
━━━━━━━━━━━━━━━━━━━━
🏆 {league_name}
⚽ *{home_team} v {away_team}*
⏱ {elapsed}' | 🔢 {home_goals} - {away_goals} | 🎯 {pontos}pts

📊 *ESTATÍSTICAS:*
• Arremates: {total_chutes}
• No Alvo: {chutes_gol}
• Escanteios: {escanteios}
• Posse: 50%-50%

🚨 *{sinal}: MAIS 1 GOL*
✅ Janela ideal ({JANELA_MIN}-{JANELA_MAX}min)
✅ Placar aberto
━━━━━━━━━━━━━━━━━━━━
"""

# ============================================================
# LOOP PRINCIPAL
# ============================================================

def verificar_partidas(bot):
    partidas = get_live_matches()
    if not partidas:
        logger.info("Nenhuma partida ao vivo")
        return

    for fixture in partidas:
        try:
            fixture_id = fixture.get("fixture", {}).get("id")
            elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed", 0)
            goals = fixture.get("goals", {})
            home_goals = goals.get("home", 0) or 0
            away_goals = goals.get("away", 0) or 0
            total_gols = home_goals + away_goals

            if not (JANELA_MIN <= elapsed <= JANELA_MAX):
                continue
            if total_gols < MIN_GOLS or total_gols > MAX_GOLS:
                continue

            chave = f"{fixture_id}_{elapsed // 5}"
            if chave in jogos_sinalizados:
                continue

            pontos, stats_dict = calcular_pontuacao(fixture)
            sinal = determinar_sinal(pontos)
            if not sinal:
                continue

            mensagem = formatar_mensagem(fixture, sinal, pontos, stats_dict)

            for chat_id in CHAT_IDS:
                try:
                    bot.send_message(chat_id=chat_id, text=mensagem, parse_mode="Markdown")
                    logger.info(f"Sinal enviado: {fixture_id}")
                except Exception as e:
                    logger.error(f"Erro ao enviar: {e}")

            jogos_sinalizados.add(chave)

        except Exception as e:
            logger.error(f"Erro ao processar partida: {e}")

def loop_verificacao(bot):
    while True:
        try:
            verificar_partidas(bot)
        except Exception as e:
            logger.error(f"Erro no loop: {e}")
        time.sleep(CHECK_INTERVAL)

# ============================================================
# COMANDOS
# ============================================================

def start(update, context):
    update.message.reply_text(
        "🤖 *ROBÔ OVER GOLS*\n\nBot ativo! Monitorando partidas ao vivo.\n\n"
        "Comandos:\n/start - Iniciar\n/status - Ver status\n/aovivo - Partidas ao vivo",
        parse_mode="Markdown"
    )

def status(update, context):
    update.message.reply_text(
        f"✅ *Bot ativo!*\n\n⏱ Verificando a cada {CHECK_INTERVAL}s\n"
        f"🎯 Janela: {JANELA_MIN}-{JANELA_MAX} min\n"
        f"📊 Sinais emitidos: {len(jogos_sinalizados)}",
        parse_mode="Markdown"
    )

def aovivo(update, context):
    update.message.reply_text("🔍 Buscando partidas ao vivo...")
    partidas = get_live_matches()
    if not partidas:
        update.message.reply_text("❌ Nenhuma partida ao vivo no momento.")
        return
    msg = f"⚽ *{len(partidas)} partidas ao vivo:*\n\n"
    for f in partidas[:10]:
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        elapsed = f.get("fixture", {}).get("status", {}).get("elapsed", 0)
        home = teams.get("home", {}).get("name", "")
        away = teams.get("away", {}).get("name", "")
        hg = goals.get("home", 0) or 0
        ag = goals.get("away", 0) or 0
        msg += f"• {home} {hg}-{ag} {away} ({elapsed}')\n"
    update.message.reply_text(msg, parse_mode="Markdown")

# ============================================================
# MAIN
# ============================================================

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("aovivo", aovivo))

    bot = updater.bot
    t = threading.Thread(target=loop_verificacao, args=(bot,), daemon=True)
    t.start()

    logger.info("🤖 Robô Over Gols iniciado!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
