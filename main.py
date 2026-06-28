import telebot
import requests
import time
import threading
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN     = "8687365697:AAGWA-YkMoWTDkO9dvfjiBGxydEmOWnigP0"
CHANNEL_ID    = "6590354226"
SCAN_INTERVAL = 60

bot = telebot.TeleBot(BOT_TOKEN)
sinais_enviados: dict = {}

HEADERS_SOFA = {
    "User-Agent": "Mozilla/5.0 (Android 10; Mobile) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}

# ─── API SOFASCORE ────────────────────────────────────────────────────────────
def get_live_fixtures():
    try:
        url = "https://api.sofascore.com/api/v1/sport/football/events/live"
        r = requests.get(url, headers=HEADERS_SOFA, timeout=15)
        r.raise_for_status()
        return r.json().get("events", [])
    except Exception as e:
        print(f"[ERRO] get_live_fixtures: {e}")
        return []


def get_fixture_stats(event_id: int):
    try:
        url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
        r = requests.get(url, headers=HEADERS_SOFA, timeout=15)
        r.raise_for_status()
        return r.json().get("statistics", [])
    except Exception as e:
        print(f"[ERRO] get_fixture_stats: {e}")
        return []

# ─── EXTRAÇÃO DE ESTATÍSTICAS ─────────────────────────────────────────────────
def parse_sofa_stat(stats: list, stat_key: str, period: str = "ALL") -> tuple:
    """Extrai estatística (home, away) do Sofascore pelo key."""
    for block in stats:
        if block.get("period") != period:
            continue
        for group in block.get("groups", []):
            for item in group.get("statisticsItems", []):
                if item.get("key") == stat_key:
                    h = item.get("homeValue") or item.get("home") or 0
                    a = item.get("awayValue") or item.get("away") or 0
                    try:
                        return (int(str(h).replace("%","")),
                                int(str(a).replace("%","")))
                    except:
                        return (0, 0)
    return (0, 0)


def extract_stats(stats_response: list) -> dict | None:
    if not stats_response:
        return None
    s = stats_response
    return {
        "shots_on":   parse_sofa_stat(s, "shotsOnTarget"),
        "shots_off":  parse_sofa_stat(s, "shotsOffTarget"),
        "corners":    parse_sofa_stat(s, "cornerKicks"),
        "dangerous":  parse_sofa_stat(s, "dangerousAttacks"),
        "possession": parse_sofa_stat(s, "ballPossession"),
        "red_cards":  parse_sofa_stat(s, "redCards"),
        "fouls":      parse_sofa_stat(s, "fouls"),
    }

# ─── SCORE ENGINE ─────────────────────────────────────────────────────────────
def calcular_score(st: dict, minuto: int, total_gols: int) -> tuple[int, list[str]]:
    score = 0
    razoes = []

    shots_on_total  = st["shots_on"][0]  + st["shots_on"][1]
    shots_off_total = st["shots_off"][0] + st["shots_off"][1]
    corners_total   = st["corners"][0]   + st["corners"][1]
    danger_total    = st["dangerous"][0] + st["dangerous"][1]
    danger_home     = st["dangerous"][0]
    danger_away     = st["dangerous"][1]
    posse_home      = st["possession"][0]
    red_cards_total = st["red_cards"][0] + st["red_cards"][1]

    if red_cards_total > 0:
        score -= 20

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


def classificar_sinal(score: int) -> str | None:
    if score >= 88: return "🔴 ALTO"
    if score >= 75: return "🟡 MÉDIO"
    if score >= 60: return "🟢 BAIXO"
    return None


def tipo_sinal(score: int) -> str:
    if score >= 88: return "ALTO"
    if score >= 75: return "MEDIO"
    return "BAIXO"

# ─── FORMATAÇÃO ───────────────────────────────────────────────────────────────
def montar_mensagem(home, away, league, minuto, gols_str,
                    st, classificacao, razoes, score) -> str:
    linhas_razoes = "\n".join(f"  {r}" for r in razoes) if razoes else "  📊 Estatísticas favoráveis"
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
        f"🎯 *Razões do sinal:*\n{linhas_razoes}\n\n"
        f"📡 Força do sinal: {score}/100\n\n"
        f"🚨 *ALERTA DE ENTRADA*\n"
        f"Over limite — {classificacao}\n\n"
        f"⚠️ Jogue com responsabilidade 🔞"
    )

# ─── ENVIO ────────────────────────────────────────────────────────────────────
def enviar_sinal(mensagem: str):
    try:
        bot.send_message(CHANNEL_ID, mensagem, parse_mode="Markdown")
        print(f"[OK] Sinal enviado: {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[ERRO] enviar_sinal: {e}")

# ─── VARREDURA ────────────────────────────────────────────────────────────────
def varredura():
    print(f"[SCAN] {datetime.now().strftime('%H:%M:%S')} — varrendo...")
    eventos = get_live_fixtures()
    print(f"[INFO] {len(eventos)} jogos ao vivo")

    for ev in eventos:
        try:
            event_id   = ev["id"]
            status     = ev.get("status", {})
            minuto     = status.get("clock", {}).get("initial", 0) or 0
            status_code = status.get("type", {}).get("state", "")
            home_score = ev.get("homeScore", {}).get("current", 0) or 0
            away_score = ev.get("awayScore", {}).get("current", 0) or 0
            total_gols = home_score + away_score
            gols_str   = f"{home_score} - {away_score}"
            home       = ev["homeTeam"]["name"]
            away       = ev["awayTeam"]["name"]
            league     = ev.get("tournament", {}).get("name", "Desconhecido")

            # Filtros
            if status_code not in ("inprogress",):
                continue
            if not (55 <= minuto <= 89):
                continue
            if total_gols > 2:
                continue

            # Estatísticas
            stats_resp = get_fixture_stats(event_id)
            st = extract_stats(stats_resp)
            if st is None:
                continue

            # Score
            score, razoes = calcular_score(st, minuto, total_gols)
            classificacao = classificar_sinal(score)
            if classificacao is None:
                continue

            # Dedup
            tipo = tipo_sinal(score)
            if event_id not in sinais_enviados:
                sinais_enviados[event_id] = set()
            if tipo in sinais_enviados[event_id]:
                continue
            sinais_enviados[event_id].add(tipo)

            mensagem = montar_mensagem(home, away, league, minuto,
                                       gols_str, st, classificacao, razoes, score)
            print(f"[SINAL {tipo}] {home} x {away} | {minuto}' | score={score}")
            enviar_sinal(mensagem)
            time.sleep(2)

        except Exception as e:
            print(f"[ERRO] evento: {e}")

    # Limpa eventos antigos
    ids_vivos = {e["id"] for e in eventos}
    for fid in list(sinais_enviados.keys()):
        if fid not in ids_vivos:
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
    bot.reply_to(msg,
        "🤖 *Robô Over Gols* ativo!\n\nVarredura automática a cada 60s.\nUse /status ou /aovivo.",
        parse_mode="Markdown")


@bot.message_handler(commands=["status"])
def cmd_status(msg):
    bot.reply_to(msg,
        f"✅ Bot rodando\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"📡 Partidas monitoradas: {len(sinais_enviados)}")


@bot.message_handler(commands=["teste"])
def cmd_teste(msg):
    bot.reply_to(msg, "🔍 Iniciando varredura manual...")
    threading.Thread(target=varredura, daemon=True).start()


@bot.message_handler(commands=["aovivo"])
def cmd_aovivo(msg):
    bot.reply_to(msg, "🔍 Buscando jogos ao vivo...")
    eventos = get_live_fixtures()
    if not eventos:
        bot.reply_to(msg, "❌ Nenhum jogo ao vivo encontrado.")
        return
    linhas = [f"⚽ {len(eventos)} jogos ao vivo:\n"]
    for ev in eventos[:15]:
        home  = ev["homeTeam"]["name"]
        away  = ev["awayTeam"]["name"]
        min_  = ev.get("status", {}).get("clock", {}).get("initial", 0) or 0
        hs    = ev.get("homeScore", {}).get("current", 0) or 0
        as_   = ev.get("awayScore", {}).get("current", 0) or 0
        linhas.append(f"• {home} x {away} | {min_}' | {hs}-{as_}")
    bot.reply_to(msg, "\n".join(linhas))


@bot.message_handler(commands=["forcasinal"])
def cmd_forcasinal(msg):
    mensagem = (
        "🤖 *ROBÔ OVER GOLS* — TESTE\n\n"
        "⚽ *Brasil x Argentina*\n"
        "🏆 Copa do Mundo 2026\n"
        "⏱️ 70 minutos\n"
        "📊 Placar 0 - 0\n\n"
        "📡 Força do sinal: 88/100\n\n"
        "🚨 *ALERTA DE ENTRADA*\n"
        "Over limite — 🔴 ALTO\n\n"
        "⚠️ Jogue com responsabilidade 🔞"
    )
    try:
        bot.send_message(CHANNEL_ID, mensagem, parse_mode="Markdown")
        bot.reply_to(msg, "✅ Sinal de teste enviado!")
    except Exception as e:
        bot.reply_to(msg, f"❌ Erro: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  🤖 ROBÔ OVER GOLS — Sofascore")
    print(f"  Chat: {CHANNEL_ID}")
    print("=" * 50)
    threading.Thread(target=loop_continuo, daemon=True).start()
    bot.infinity_polling(timeout=30, long_polling_timeout=20)





