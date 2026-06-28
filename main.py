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

RAPID_KEY  = "c5dc120af4mshc53e95e29360e7bp110eccjsn521bdeca1caa"
RAPID_HOST = "free-api-live-football-data.p.rapidapi.com"
HEADERS    = {
    "x-rapidapi-key":  RAPID_KEY,
    "x-rapidapi-host": RAPID_HOST,
}
API_BASE = f"https://{RAPID_HOST}"

# ─── API ──────────────────────────────────────────────────────────────────────
def get_live_fixtures():
    try:
        r = requests.get(f"{API_BASE}/futebol-atual-ao-vivo",
                         headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("response", data.get("data", data.get("matches", [])))
    except Exception as e:
        print(f"[ERRO] get_live_fixtures: {e}")
        return []


def get_fixture_stats(match_id):
    try:
        r = requests.get(f"{API_BASE}/football-get-match-statistics",
                         headers=HEADERS,
                         params={"match_id": match_id},
                         timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("response", data.get("data", data.get("statistics", [])))
    except Exception as e:
        print(f"[ERRO] get_fixture_stats: {e}")
        return []

# ─── EXTRAÇÃO DE STATS ────────────────────────────────────────────────────────
def safe_int(val) -> int:
    try:
        return int(str(val).replace("%", "").strip())
    except:
        return 0


def extract_stats(stats) -> dict | None:
    """Tenta extrair stats de vários formatos possíveis da API."""
    if not stats:
        return None

    # Formato lista de times [{team, statistics:[]}]
    if isinstance(stats, list) and len(stats) >= 2:
        def get_val(team_stats, key):
            for s in team_stats:
                if s.get("type", "").lower().replace(" ", "") == key.lower().replace(" ", ""):
                    return safe_int(s.get("value", 0))
            return 0

        h_stats = stats[0].get("statistics", [])
        a_stats = stats[1].get("statistics", [])

        return {
            "shots_on":   (get_val(h_stats, "ShotsonGoal"),   get_val(a_stats, "ShotsonGoal")),
            "shots_off":  (get_val(h_stats, "ShotsoffGoal"),  get_val(a_stats, "ShotsoffGoal")),
            "corners":    (get_val(h_stats, "CornerKicks"),    get_val(a_stats, "CornerKicks")),
            "dangerous":  (get_val(h_stats, "DangerousAttacks"), get_val(a_stats, "DangerousAttacks")),
            "possession": (get_val(h_stats, "BallPossession"), get_val(a_stats, "BallPossession")),
            "red_cards":  (get_val(h_stats, "RedCards"),       get_val(a_stats, "RedCards")),
        }

    # Formato dict com home/away direto
    if isinstance(stats, dict):
        def gv(d, k):
            return safe_int(d.get(k, 0))
        h = stats.get("home", stats.get("homeTeam", {}))
        a = stats.get("away", stats.get("awayTeam", {}))
        return {
            "shots_on":   (gv(h, "shotsOnTarget"),   gv(a, "shotsOnTarget")),
            "shots_off":  (gv(h, "shotsOffTarget"),  gv(a, "shotsOffTarget")),
            "corners":    (gv(h, "corners"),          gv(a, "corners")),
            "dangerous":  (gv(h, "dangerousAttacks"), gv(a, "dangerousAttacks")),
            "possession": (gv(h, "possession"),       gv(a, "possession")),
            "red_cards":  (gv(h, "redCards"),         gv(a, "redCards")),
        }

    return None

# ─── SCORE ENGINE ─────────────────────────────────────────────────────────────
def calcular_score(st: dict, minuto: int, total_gols: int):
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

    if red_total > 0:
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

# ─── ENVIO ────────────────────────────────────────────────────────────────────
def enviar_sinal(msg):
    try:
        bot.send_message(CHANNEL_ID, msg, parse_mode="Markdown")
        print(f"[OK] {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[ERRO enviar] {e}")

# ─── VARREDURA ────────────────────────────────────────────────────────────────
def extrair_campo(ev, *keys):
    """Tenta extrair campo de dict com múltiplas chaves possíveis."""
    for k in keys:
        if k in ev and ev[k] is not None:
            return ev[k]
    return None


def varredura():
    print(f"[SCAN] {datetime.now().strftime('%H:%M:%S')}")
    eventos = get_live_fixtures()
    print(f"[INFO] {len(eventos)} jogos")

    for ev in eventos:
        try:
            # Extrai campos com fallback
            event_id   = extrair_campo(ev, "id", "match_id", "fixture_id")
            home       = extrair_campo(ev, "home_name", "homeTeam", "home_team", "home")
            away       = extrair_campo(ev, "away_name", "awayTeam", "away_team", "away")
            minuto     = safe_int(extrair_campo(ev, "minute", "elapsed", "match_elapsed") or 0)
            home_score = safe_int(extrair_campo(ev, "home_score", "homeGoals", "score_home") or 0)
            away_score = safe_int(extrair_campo(ev, "away_score", "awayGoals", "score_away") or 0)
            league     = extrair_campo(ev, "league_name", "competition", "tournament", "league") or "?"
            status     = str(extrair_campo(ev, "status", "match_status") or "").lower()

            if isinstance(home, dict): home = home.get("name", "?")
            if isinstance(away, dict): away = away.get("name", "?")
            if isinstance(league, dict): league = league.get("name", "?")

            total_gols = home_score + away_score
            gols_str   = f"{home_score} - {away_score}"

            # Filtros
            if "half" not in status and "live" not in status and "progress" not in status and "2h" not in status:
                continue
            if not (55 <= minuto <= 89):
                continue
            if total_gols > 2:
                continue

            # Stats
            stats_raw = get_fixture_stats(event_id)
            st = extract_stats(stats_raw)
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

            msg = montar_mensagem(home, away, league, minuto, gols_str,
                                  st, classificacao, razoes, score)
            print(f"[SINAL {tipo}] {home} x {away} {minuto}' score={score}")
            enviar_sinal(msg)
            time.sleep(2)

        except Exception as e:
            print(f"[ERRO ev] {e}")

    ids = {extrair_campo(e, "id", "match_id", "fixture_id") for e in eventos}
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
    eventos = get_live_fixtures()
    if not eventos:
        bot.reply_to(msg, "❌ Nenhum jogo encontrado.")
        return
    linhas = [f"⚽ {len(eventos)} jogos:\n"]
    for ev in eventos[:15]:
        home = extrair_campo(ev, "home_name", "homeTeam", "home_team", "home") or "?"
        away = extrair_campo(ev, "away_name", "awayTeam", "away_team", "away") or "?"
        if isinstance(home, dict): home = home.get("name", "?")
        if isinstance(away, dict): away = away.get("name", "?")
        min_ = safe_int(extrair_campo(ev, "minute", "elapsed") or 0)
        hs   = safe_int(extrair_campo(ev, "home_score", "homeGoals") or 0)
        as_  = safe_int(extrair_campo(ev, "away_score", "awayGoals") or 0)
        linhas.append(f"• {home} x {away} | {min_}' | {hs}-{as_}")
    bot.reply_to(msg, "\n".join(linhas))


@bot.message_handler(commands=["forcasinal"])
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
    print("🤖 ROBÔ OVER GOLS — RapidAPI")
    threading.Thread(target=loop_continuo, daemon=True).start()
    bot.infinity_polling(timeout=30, long_polling_timeout=20)







