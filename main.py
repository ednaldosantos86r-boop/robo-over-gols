import os
import time
import threading
import requests
import telebot
from telebot import apihelper

# ── Configurações ──────────────────────────────────────────
BOT_TOKEN     = os.environ.get("BOT_TOKEN", "")
API_KEY       = os.environ.get("API_FOOTBALL_KEY", "")
CHAT_ID       = os.environ.get("CHAT_ID", "6590354226")
SCAN_INTERVAL = 300   # 5 min = ~288 req/dia (plano free: 100/dia → use 900s)
MIN_MINUTE    = 55
MAX_MINUTE    = 89
MAX_GOALS     = 2

bot = telebot.TeleBot(BOT_TOKEN)
apihelper.RETRY_ON_ERROR = True

sinais_enviados = set()

# ── Busca jogos ao vivo com diagnóstico completo ───────────
def get_live_matches(verbose=False):
    url = "https://v3.football.api-sports.io/fixtures?live=all"
    headers = {"x-apisports-key": API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=20)

        # Checa se a chave existe
        if not API_KEY:
            if verbose:
                return [], "❌ API_FOOTBALL_KEY não configurada no Railway."
            return []

        data = resp.json()

        # Erros retornados pela API (ex: chave inválida, limite atingido)
        errors = data.get("errors", {})
        if errors:
            msg = f"❌ Erro da API: {errors}"
            print(f"[ERRO API] {errors}")
            if verbose:
                return [], msg
            return []

        remaining = resp.headers.get("x-ratelimit-requests-remaining", "?")
        used      = resp.headers.get("x-ratelimit-requests-limit", "?")
        matches   = data.get("response", [])

        print(f"[API] Jogos ao vivo: {len(matches)} | Req restantes: {remaining}/{used}")

        if verbose:
            info = (
                f"🔑 Chave: ...{API_KEY[-6:] if API_KEY else 'N/A'}\n"
                f"📡 Jogos ao vivo agora: {len(matches)}\n"
                f"📊 Requisições restantes hoje: {remaining}/{used}\n"
                f"🕐 Horário da consulta: {time.strftime('%H:%M:%S')} BRT"
            )
            return matches, info

        return matches

    except Exception as e:
        msg = f"❌ Erro de conexão: {e}"
        print(f"[ERRO] get_live_matches: {e}")
        if verbose:
            return [], msg
        return []

# ── Motor de pontuação 0–100 ───────────────────────────────
def calcular_score(fixture):
    stats_raw = fixture.get("statistics", [])
    stats = {}
    for team_stat in stats_raw:
        for s in team_stat.get("statistics", []):
            tipo = s.get("type", "")
            val  = s.get("value") or 0
            try:
                val = int(val)
            except:
                val = 0
            stats[tipo] = stats.get(tipo, 0) + val

    minuto    = fixture["fixture"]["status"].get("elapsed", 0) or 0
    shots_on  = stats.get("Shots on Goal", 0)
    shots_off = stats.get("Shots off Goal", 0)
    corners   = stats.get("Corner Kicks", 0)
    dangerous = stats.get("Dangerous Attacks", 0)
    red_cards = stats.get("Red Cards", 0)
    poss_str  = stats.get("Ball Possession", "50%")

    try:
        poss = int(str(poss_str).replace("%", ""))
    except:
        poss = 50

    score = 0
    score += min(shots_on * 3, 25)
    score += min(shots_off, 10)
    score += min(corners * 2, 15)
    score += min(dangerous // 5, 20)
    score += 10 if poss >= 60 else (5 if poss >= 50 else 0)
    score += 10 if minuto >= 80 else (7 if minuto >= 70 else 4)
    score += 10 if red_cards > 0 else 0

    return min(score, 100)

def classificar(score):
    if score >= 70:
        return "🔴 ALTO"
    elif score >= 45:
        return "🟡 MÉDIO"
    else:
        return "🟢 BAIXO"

# ── Envia sinal ────────────────────────────────────────────
def enviar_sinal(fixture, score):
    home   = fixture["teams"]["home"]["name"]
    away   = fixture["teams"]["away"]["name"]
    gols_h = fixture["goals"].get("home") or 0
    gols_a = fixture["goals"].get("away") or 0
    minuto = fixture["fixture"]["status"].get("elapsed", 0)
    nivel  = classificar(score)

    texto = (
        f"⚽ *SINAL OVER GOLS*\n"
        f"🏟 {home} {gols_h} x {gols_a} {away}\n"
        f"⏱ Minuto: {minuto}'\n"
        f"📊 Score: {score}/100\n"
        f"📶 Nível: {nivel}\n"
        f"💡 Aposte: *Over 2.5 gols*"
    )
    try:
        bot.send_message(CHAT_ID, texto, parse_mode="Markdown")
        print(f"[SINAL] {home} x {away} | {score}pts | {nivel}")
    except Exception as e:
        print(f"[ERRO] Telegram: {e}")

# ── Varredura automática ───────────────────────────────────
def varrer():
    matches    = get_live_matches()
    hora       = time.strftime("%H:%M")
    total_vivo = len(matches)
    print(f"[SCAN] {hora} — {total_vivo} jogo(s) ao vivo")

    candidatos = 0
    for fixture in matches:
        fid    = fixture["fixture"]["id"]
        minuto = fixture["fixture"]["status"].get("elapsed", 0) or 0
        total  = (fixture["goals"].get("home") or 0) + (fixture["goals"].get("away") or 0)

        if not (MIN_MINUTE <= minuto <= MAX_MINUTE):
            continue
        if total > MAX_GOALS:
            continue
        candidatos += 1
        if fid in sinais_enviados:
            continue

        score = calcular_score(fixture)
        if score >= 45:
            enviar_sinal(fixture, score)
            sinais_enviados.add(fid)

    if total_vivo == 0:
        print("[INFO] API retornou 0 jogos ao vivo")
    elif candidatos == 0:
        print(f"[INFO] {total_vivo} jogos mas nenhum no filtro {MIN_MINUTE}-{MAX_MINUTE}' / <= {MAX_GOALS} gols")

# ── Comandos Telegram ──────────────────────────────────────
@bot.message_handler(commands=["start", "ajuda"])
def cmd_start(message):
    bot.reply_to(message,
        "🤖 *Robô Over Gols* ativo!\n\n"
        "Comandos:\n"
        "/aovivo — jogos ao vivo agora\n"
        "/status — diagnóstico da API\n"
        "/ajuda  — esta mensagem",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["status"])
def cmd_status(message):
    bot.reply_to(message, "🔍 Verificando API...")
    matches, info = get_live_matches(verbose=True)
    bot.send_message(message.chat.id,
        f"📋 *Status da API*\n\n{info}",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["aovivo"])
def cmd_aovivo(message):
    bot.reply_to(message, "🔍 Buscando jogos ao vivo...")
    matches, info = get_live_matches(verbose=True)

    if not matches:
        bot.send_message(message.chat.id,
            f"❌ Nenhum jogo encontrado.\n\n{info}",
            parse_mode="Markdown"
        )
        return

    # Lista todos os jogos ao vivo (sem filtro de minuto)
    linhas = [f"📋 *{len(matches)} jogos ao vivo:*\n"]
    for f in matches[:15]:  # máx 15 para não estourar mensagem
        h  = f["teams"]["home"]["name"]
        a  = f["teams"]["away"]["name"]
        gh = f["goals"].get("home") or 0
        ga = f["goals"].get("away") or 0
        mn = f["fixture"]["status"].get("elapsed", "?")
        linhas.append(f"⚽ {h} {gh}x{ga} {a} | {mn}'")

    linhas.append(f"\n{info}")
    bot.send_message(message.chat.id, "\n".join(linhas), parse_mode="Markdown")

# ── Loop de varredura em thread separada ───────────────────
def loop_varredura():
    while True:
        try:
            varrer()
        except Exception as e:
            print(f"[ERRO] Loop varredura: {e}")
        time.sleep(SCAN_INTERVAL)

# ── Main ───────────────────────────────────────────────────
def main():
    print("[INFO] Robô Over Gols iniciado.")
    t = threading.Thread(target=loop_varredura, daemon=True)
    t.start()

    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERRO] Polling: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()












