import telebot
import requests
import time
import threading
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN     = "8687365697:AAGWA-YkMoWTDkO9dvfjiBGxydEmOWnigP0"
CHANNEL_ID    = "6590354226"
SCAN_INTERVAL = 300

bot = telebot.TeleBot(BOT_TOKEN)
sinais_enviados: dict = {}

RAPID_KEY  = "c5dc120af4mshc53e95e29360e7bp110eccjsn521bdeca1caa"
HEADERS    = {
    "x-rapidapi-key":  RAPID_KEY,
    "x-rapidapi-host": "free-api-live-football-data.p.rapidapi.com",
}
API_BASE = "https://free-api-live-football-data.p.rapidapi.com"

# ─── API ──────────────────────────────────────────────────────────────────────
def get_live_fixtures():
    try:
        r = requests.get(f"{API_BASE}/football-current-live",
                         headers=HEADERS,
                         timeout=15)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception as e:
        print(f"[ERRO] get_live_fixtures: {e}")
        return []


def get_fixture_stats(fixture_id):
    try:
        r = requests.get(f"{API_BASE}/football-get-match-live-stats",
                         headers=HEADERS,
                         params={"match_id": fixture_id},
                         timeout=15)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception as e:
        print(f"[ERRO] get_stats: {e}")
        return []

# ─── EXTRAÇÃO DE STATS ────────────────────────────────────────────────────────
def safe_int(val) -> int:
    try:
        return int(str(val).replace("%", "").strip())
    except:
        return 0


def parse_stat(stats_list, stat_name, team_index):
    try:
        for s in stats_list[team_index]["statistics"]:
            if s["type"] == stat_name:
                return safe_int(s["value"] or 0)
        return 0
    except:
        return 0


def extract_stats(stats_response):
    if len(stats_response) < 2:
        return None
    return {
        "shots_on":   (parse_stat(stats_response, "Shots on Goal", 0),   parse_stat(stats_response, "Shots on Goal", 1)),
        "shots_off":  (parse_stat(stats_response, "Shots off Goal", 0),  parse_stat(stats_response, "Shots off Goal", 1)),
        "corners":    (parse_stat(stats_response, "Corner Kicks", 0),     parse_stat(stats_response, "Corner Kicks", 1)),
        "dangerous":  (parse_stat(stats_response, "Dangerous Attacks", 0),parse_stat(stats_response, "Dangerous Attacks", 1)),
        "possession": (parse_stat(stats_response, "Ball Possession", 0),  parse_stat(stats_response, "Ball Possession", 1)),
        "red_cards":  (parse_stat(stats_response, "Red Cards", 0),        parse_stat(stats_response, "Red Cards", 1)),
    }

# ─── SCORE ENGINE ─────────────────────────────────────────────────────────────
def calcular_score(st, minuto, total_gols):
    score = 0
    razoes = []

    shots_on_total  = st["shots_on"][0]  + st["shots_on"][1]
    shots_off_total = st["shots_off"][0] + st["shots_off"][1]
    corners_total   = st["corners"][0]   + st["corners"][1]
    danger_total    = st["dangerous"][0] + st["dangerous"][1]
    danger_home     = st["dangerous"][0]
    danger_away     = st["dangerous"][1]
    posse_home      = st["possession"][0]
    red_total       = st["red_cards"][0] + st["red_cards"][1]

    if red_total > 0: score -= 20

    if shots_on_total >= 8:
        score += 22; razoes.append(f"🎯 {shots_on_total} chutes ao gol")
    elif shots_on_total >= 5:
        score += 14; razoes.append(f"🎯 {shots_on_total} chutes ao gol")
    elif shots_on_total >= 3:
        score += 7

    if shots_off_total >= 10:
        score += 12; razoes.append(f"📐 {shots_off_total} chutes fora")
    elif shots_off_total >= 6:
        score += 7
    elif shots_off_total >= 3:
        score += 3

    if corners_total >= 10:
        score += 18; razoes.append(f"🚩 {corners_total} escanteios")
    elif corners_total >= 7:
        score += 12; razoes.append(f"🚩 {corners_total} escanteios")
    elif corners_total >= 4:
        score += 6

    if danger_total >= 60:
        score += 20; razoes.append(f"⚡ {danger_total} ataques perigosos")
    elif danger_total >= 40:
        score += 14; razoes.append(f"⚡ {danger_total} ataques perigosos")
    elif danger_total >= 25:
        score += 8

    if danger_home > 0 and danger_away > 0:
        ratio = max(danger_home, danger_away) / min(danger_home, danger_away)
        if ratio >= 3.0:
            score += 10; razoes.append(f"📊 Pressão unilateral ({danger_home}-{danger_away})")
        elif ratio >= 2.0:
            score += 5

    if posse_home >= 65 or (100 - posse_home) >= 65:
        score += 8; razoes.append(f"⚽ Posse dominante {max(posse_home, 100-posse_home)}%")

    if 55 <= minuto <= 70:
        score += 10; razoes.append(f"⏱️ Janela crítica ({minuto}')")
    elif 70 < minuto <= 80:
        score += 14; razoes.append(f"⏱️ Reta final ({minuto}')")
    elif 80 < minuto <= 89:
        score += 8

    if total_gols == 0:
        score += 10; razoes.append("🔒 Jogo sem gols – pressão crescente")
    elif total_gols == 1:
        score += 5

    return min(score, 100), razoes


def classificar_sinal(score):
    if score >= 88: return "🔴 ALTO"
    if score >= 75: return "🟡 MÉDIO"
    if score >= 60: return "🟢 BAIXO"
    return None

def tipo_sinal(score):
    if score >= 88: return "ALTO"
    if score >= 75: return "MEDIO"
    return "BAIXO"

# ─── MENSAGEM ─────────────────────────────────────────────────────────────────
def montar_mensagem(home, away, league, minuto, gols_str, st, classificacao, razoes, score):
    lr = "\n".join(f"  {r}" for r in razoes) if razoes else "  📊 Estatísticas favoráveis"
    return (
        f"🤖 *ROBÔ OVER GOLS*\n\n"
        f"⚽ *{home} x {away}*\n"
        f"🏆 {league}\n"
        f"⏱️ {minuto} minutos\n"
        f"📊 Placar {gols_str}\n\n"
        f"📈 *Estatísticas (Casa - Fora)*\n"
        f"Chutes ao gol: {st['shots_on'][0]} - {st['shots_on'][1]}\n"
        f"Chutes fora: {st['shots_off'][0]} - {st['shots_off'][1]}\n"
        f"Escanteios: {st['corners'][0]} - {st['corners'][1]}\n"
        f"Ataques perigosos: {st['dangerous'][0]} - {st['dangerous'][1]}\n"
        f"Posse de bola: {st['possession'][0]} - {st['possession'][1]}\n"
        f"Cartões vermelhos: {st['red_cards'][0]} - {st['red_cards'][1]}\n\n"
        f"🎯 *Razões do sinal:*\n{lr}\n\n"
        f"📡 Força do sinal: {score}/100\n\n"
        f"🚨 *ALERTA DE ENTRADA*\n"
        f"Over limite — {classificacao}\n\n"
        f"⚠️ Jogue com responsabilidade 🔞"
    )

def enviar_sinal(msg):
    try:
        bot.send_message(CHANNEL_ID, msg, parse_mode="Markdown")
        print(f"[OK] {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[ERRO enviar] {e}")

# ─── VARREDURA ────────────────────────────────────────────────────────────────
def varredura():
    print(f"[SCAN] {datetime.now().strftime('%H:%M:%S')}")
    fixtures = get_live_fixtures()
    print(f"[INFO] {len(fixtures)} jogos ao vivo")

    for fix in fixtures:
        try:
            fixture_id = fix["fixture"]["id"]
            minuto     = fix["fixture"]["status"].get("elapsed") or 0
            status     = fix["fixture"]["status"]["short"]
            home_gols  = fix["goals"]["home"] or 0
            away_gols  = fix["goals"]["away"] or 0
            total_gols = home_gols + away_gols
            gols_str   = f"{home_gols} - {away_gols}"
            home       = fix["teams"]["home"]["name"]
            away       = fix["teams"]["away"]["name"]
            league     = fix["league"]["name"]

            if status not in ("2H", "LIVE", "ET"):
                continue
            if not (55 <= minuto <= 89):
                continue
            if total_gols > 2:
                continue

            stats_resp = get_fixture_stats(fixture_id)
            st = extract_stats(stats_resp)
            if st is None:
                continue

            score, razoes = calcular_score(st, minuto, total_gols)
            classificacao = classificar_sinal(score)
            if classificacao is None:
                continue

            tipo = tipo_sinal(score)
            if fixture_id not in sinais_enviados:
                sinais_enviados[fixture_id] = set()
            if tipo in sinais_enviados[fixture_id]:
                continue
            sinais_enviados[fixture_id].add(tipo)

            msg = montar_mensagem(home, away, league, minuto, gols_str,
                                  st, classificacao, razoes, score)
            print(f"[SINAL {tipo}] {home} x {away} {minuto}' score={score}")
            enviar_sinal(msg)
            time.sleep(2)

        except Exception as e:
            print(f"[ERRO fix] {e}")

    ids = {f["fixture"]["id"] for f in fixtures}
    for fid in list(sinais_enviados.keys()):
        if fid not in ids:
            del sinais_enviados[fid]


def loop_continuo():
    while True:
        try:
            varredura()
        except Exception as e:
            print(f"[ERRO GERAL] {e}")
        time.sleep(SCAN_INTERVAL)

# ─── COMANDOS ─────────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    bot.reply_to(msg, "🤖 *Robô Over Gols* ativo!\nUse /aovivo ou /status.", parse_mode="Markdown")

@bot.message_handler(commands=["status"])
def cmd_status(msg):
    bot.reply_to(msg, f"✅ Rodando\n🕐 {datetime.now().strftime('%d/%m %H:%M')}\n📡 {len(sinais_enviados)} partidas")

@bot.message_handler(commands=["teste"])
def cmd_teste(msg):
    bot.reply_to(msg, "🔍 Iniciando varredura manual...")
    threading.Thread(target=varredura, daemon=True).start()

@bot.message_handler(commands=["aovivo"])
def cmd_aovivo(msg):
    bot.reply_to(msg, "🔍 Buscando jogos ao vivo...")
    fixtures = get_live_fixtures()
    if not fixtures:
        bot.reply_to(msg, "❌ Nenhum jogo encontrado.")
        return
    linhas = [f"⚽ {len(fixtures)} jogos:\n"]
    for f in fixtures[:15]:
        home  = f["teams"]["home"]["name"]
        away  = f["teams"]["away"]["name"]
        min_  = f["fixture"]["status"].get("elapsed") or 0
        hs    = f["goals"]["home"] or 0
        as_   = f["goals"]["away"] or 0
        linhas.append(f"• {home} x {away} | {min_}' | {hs}-{as_}")
    bot.reply_to(msg, "\n".join(linhas))

@bot.message_handler(commands=["debug"])
def cmd_debug(msg):
    bot.reply_to(msg, "🔍 Testando endpoints...")
    endpoints = [
        "/football-get-all-live-matches-scores",
        "/football-live-matches",
        "/football-live-scores",
        "/football-matches-live",
        "/live-scores",
        "/football-current-matches",
        "/football-live-fixtures",
        "/livematches",
    ]
    resultados = []
    for ep in endpoints:
        try:
            url = f"https://free-api-live-football-data.p.rapidapi.com{ep}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            resultados.append(f"{'✅' if r.status_code == 200 else '⚠️'} {ep} → {r.status_code}")
        except Exception as e:
            resultados.append(f"❌ {ep} → erro")
    bot.reply_to(msg, "\n".join(resultados))
def cmd_forcasinal(msg):
    mensagem = (
        "🤖 *ROBÔ OVER GOLS* — TESTE\n\n"
        "⚽ *Brasil x Argentina*\n🏆 Copa do Mundo 2026\n"
        "⏱️ 70 minutos\n📊 Placar 0 - 0\n\n"
        "📡 Força do sinal: 88/100\n\n"
        "🚨 *ALERTA DE ENTRADA*\nOver limite — 🔴 ALTO\n\n"
        "⚠️ Jogue com responsabilidade 🔞"
    )
    try:
        bot.send_message(CHANNEL_ID, mensagem, parse_mode="Markdown")
        bot.reply_to(msg, "✅ Sinal de teste enviado!")
    except Exception as e:
        bot.reply_to(msg, f"❌ Erro: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 ROBÔ OVER GOLS — API-Football via RapidAPI")
    threading.Thread(target=loop_continuo, daemon=True).start()
    bot.infinity_polling(timeout=30, long_polling_timeout=20)















