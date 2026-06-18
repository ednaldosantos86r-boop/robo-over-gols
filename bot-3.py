import logging
import requests
import time
import threading
from telegram.ext import Updater, CommandHandler

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
PONTOS_MINIMO_BAIXO = 30
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
jogos_sinalizados = set()

def get_live_matches():
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    try:
        r = requests.get(f"{API_FOOTBALL_URL}/fixtures", headers=headers, params={"live": "all"}, timeout=10)
        return r.json().get("response", []) if r.status_code == 200 else []
    except Exception as e:
        logger.error(f"Erro API: {e}")
        return []

def calcular_pontuacao(fixture):
    stats_dict = {}
    for team_stats in fixture.get("statistics", []):
        for stat in team_stats.get("statistics", []):
            key = stat.get("type", "")
            value = stat.get("value") or 0
            try:
                value = int(str(value).replace("%", ""))
            except:
                value = 0
            stats_dict[key] = stats_dict.get(key, 0) + value

    pontos = 20
    chutes = stats_dict.get("Total Shots", 0)
    no_alvo = stats_dict.get("Shots on Goal", 0)
    escanteios = stats_dict.get("Corner Kicks", 0)

    if chutes >= 20: pontos += 30
    elif chutes >= 15: pontos += 20
    elif chutes >= 10: pontos += 10

    if no_alvo >= 8: pontos += 25
    elif no_alvo >= 5: pontos += 15
    elif no_alvo >= 3: pontos += 10

    if escanteios >= 10: pontos += 25
    elif escanteios >= 7: pontos += 15
    elif escanteios >= 4: pontos += 10

    return pontos, stats_dict

def verificar_partidas(bot):
    for fixture in get_live_matches():
        try:
            fid = fixture.get("fixture", {}).get("id")
            elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed", 0)
            goals = fixture.get("goals", {})
            total_gols = (goals.get("home") or 0) + (goals.get("away") or 0)

            if not (JANELA_MIN <= elapsed <= JANELA_MAX): continue
            if not (MIN_GOLS <= total_gols <= MAX_GOLS): continue

            chave = f"{fid}_{elapsed // 5}"
            if chave in jogos_sinalizados: continue

            pontos, stats = calcular_pontuacao(fixture)
            if pontos < PONTOS_MINIMO_BAIXO: continue

            if pontos >= 70: sinal = "🔴 SINAL ALTO"
            elif pontos >= 50: sinal = "🟡 SINAL MÉDIO"
            else: sinal = "🟢 SINAL BAIXO"

            league = fixture.get("league", {}).get("name", "Liga")
            home = fixture.get("teams", {}).get("home", {}).get("name", "Casa")
            away = fixture.get("teams", {}).get("away", {}).get("name", "Fora")
            hg = goals.get("home") or 0
            ag = goals.get("away") or 0

            msg = (
                f"🤖 *ROBÔ OVER GOLS*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🏆 {league}\n"
                f"⚽ *{home} v {away}*\n"
                f"⏱ {elapsed}' | 🔢 {hg} - {ag} | 🎯 {pontos}pts\n\n"
                f"📊 *ESTATÍSTICAS:*\n"
                f"• Arremates: {stats.get('Total Shots',0)}\n"
                f"• No Alvo: {stats.get('Shots on Goal',0)}\n"
                f"• Escanteios: {stats.get('Corner Kicks',0)}\n\n"
                f"🚨 *{sinal}: MAIS 1 GOL*\n"
                f"✅ Janela ideal ({JANELA_MIN}-{JANELA_MAX}min)\n"
                f"✅ Placar aberto\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )

            for chat_id in CHAT_IDS:
                try:
                    bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    logger.info(f"Sinal enviado: {fid}")
                except Exception as e:
                    logger.error(f"Erro envio: {e}")

            jogos_sinalizados.add(chave)
        except Exception as e:
            logger.error(f"Erro partida: {e}")

def loop(bot):
    while True:
        try:
            verificar_partidas(bot)
        except Exception as e:
            logger.error(f"Erro loop: {e}")
        time.sleep(CHECK_INTERVAL)

def start(update, context):
    update.message.reply_text("🤖 *ROBÔ OVER GOLS*\n\nBot ativo!\n\n/status - Ver status\n/aovivo - Partidas ao vivo", parse_mode="Markdown")

def status(update, context):
    update.message.reply_text(f"✅ *Bot ativo!*\n📊 Sinais emitidos: {len(jogos_sinalizados)}", parse_mode="Markdown")

def aovivo(update, context):
    partidas = get_live_matches()
    if not partidas:
        update.message.reply_text("❌ Nenhuma partida ao vivo.")
        return
    msg = f"⚽ *{len(partidas)} partidas ao vivo:*\n\n"
    for f in partidas[:10]:
        h = f.get("teams",{}).get("home",{}).get("name","")
        a = f.get("teams",{}).get("away",{}).get("name","")
        hg = f.get("goals",{}).get("home",0) or 0
        ag = f.get("goals",{}).get("away",0) or 0
        el = f.get("fixture",{}).get("status",{}).get("elapsed",0)
        msg += f"• {h} {hg}-{ag} {a} ({el}')\n"
    update.message.reply_text(msg, parse_mode="Markdown")

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("aovivo", aovivo))

    threading.Thread(target=loop, args=(updater.bot,), daemon=True).start()

    logger.info("🤖 Bot iniciado!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
