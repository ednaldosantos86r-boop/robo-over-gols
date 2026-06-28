import os
import time
import requests
import telebot
from telebot import apihelper

# ── Configurações ──────────────────────────────────────────
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
API_KEY        = os.environ.get("API_FOOTBALL_KEY", "")
CHAT_ID        = os.environ.get("CHAT_ID", "6590354226")
SCAN_INTERVAL  = 60   # segundos entre cada varredura
MIN_MINUTE     = 55
MAX_MINUTE     = 89
MAX_GOALS      = 2

bot = telebot.TeleBot(BOT_TOKEN)
apihelper.RETRY_ON_ERROR = True

sinais_enviados = set()   # evita duplicatas na mesma sessão

# ── Busca jogos ao vivo ────────────────────────────────────
def get_live_matches():
    url = "https://v3.football.api-sports.io/fixtures?live=all"
    headers = {
        "x-apisports-key": API_KEY
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        data = resp.json()
        return data.get("response", [])
    except Exception as e:
        print(f"[ERRO] get_live_matches: {e}")
        return []

# ── Motor de pontuação 0-100 ───────────────────────────────
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

    minuto   = fixture["fixture"]["status"].get("elapsed", 0) or 0
    gols_h   = fixture["goals"].get("home") or 0
    gols_a   = fixture["goals"].get("away") or 0
    total_g  = gols_h + gols_a

    shots_on  = stats.get("Shots on Goal", 0)
    shots_off = stats.get("Shots off Goal", 0)
    corners   = stats.get("Corner Kicks", 0)
    dangerous = stats.get("Dangerous Attacks", 0)
    poss_str  = stats.get("Ball Possession", "50%")
    red_cards = stats.get("Red Cards", 0)

    try:
        poss = int(str(poss_str).replace("%", ""))
    except:
        poss = 50

    score = 0

    # Chutes a gol (max 25 pts)
    score += min(shots_on * 3, 25)

    # Chutes fora (max 10 pts)
    score += min(shots_off * 1, 10)

    # Escanteios (max 15 pts)
    score += min(corners * 2, 15)

    # Ataques perigosos (max 20 pts)
    score += min(dangerous // 5, 20)

    # Posse de bola (max 10 pts)
    if poss >= 60:
        score += 10
    elif poss >= 50:
        score += 5

    # Minuto avançado (max 10 pts)
    if minuto >= 80:
        score += 10
    elif minuto >= 70:
        score += 7
    elif minuto >= 60:
        score += 4

    # Cartão vermelho (pressão extra, +10)
    if red_cards > 0:
        score += 10

    return min(score, 100)

# ── Classificação do sinal ─────────────────────────────────
def classificar(score):
    if score >= 70:
        return "🔴 ALTO"
    elif score >= 45:
        return "🟡 MÉDIO"
    else:
        return "🟢 BAIXO"

# ── Formata e envia mensagem ───────────────────────────────
def enviar_sinal(fixture, score):
    fid      = fixture["fixture"]["id"]
    home     = fixture["teams"]["home"]["name"]
    away     = fixture["teams"]["away"]["name"]
    gols_h   = fixture["goals"].get("home") or 0
    gols_a   = fixture["goals"].get("away") or 0
    minuto   = fixture["fixture"]["status"].get("elapsed", 0)
    nivel    = classificar(score)

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
        print(f"[SINAL] Enviado — {home} x {away} | Score {score} | {nivel}")
    except Exception as e:
        print(f"[ERRO] Envio Telegram: {e}")

# ── Ciclo de varredura ─────────────────────────────────────
def varrer():
    matches = get_live_matches()
    hora    = time.strftime("%H:%M")
    print(f"[SCAN] {hora} — {len(matches)} jogo(s) ao vivo")

    for fixture in matches:
        fid    = fixture["fixture"]["id"]
        minuto = fixture["fixture"]["status"].get("elapsed", 0) or 0
        gols_h = fixture["goals"].get("home") or 0
        gols_a = fixture["goals"].get("away") or 0
        total  = gols_h + gols_a

        if not (MIN_MINUTE <= minuto <= MAX_MINUTE):
            continue
        if total > MAX_GOALS:
            continue
        if fid in sinais_enviados:
            continue

        score = calcular_score(fixture)

        if score >= 45:   # envia apenas MÉDIO ou ALTO
            enviar_sinal(fixture, score)
            sinais_enviados.add(fid)

# ── Loop principal com reconexão automática ────────────────
def main():
    print("[INFO] Robô Over Gols iniciado.")
    while True:
        try:
            varrer()
        except Exception as e:
            print(f"[ERRO] Varredura: {e}")
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    main()










