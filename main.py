import telebot
import requests
import time
import threading
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN    = "8687365697:AAGWA-YkMoWTDkO9dvfjiBGxydEmOWnigP0"
API_KEY      = "15d971190e1b52fde7cf428428faa376"
CHANNEL_ID   = "6590354226"              # chat pessoal
API_BASE     = "https://v3.football.api-sports.io"
HEADERS      = {"x-apisports-key": API_KEY}
SCAN_INTERVAL = 60                       # segundos entre cada varredura

bot = telebot.TeleBot(BOT_TOKEN)
# @santossover_bot

# ─── CONTROLE DE SINAIS JÁ ENVIADOS ──────────────────────────────────────────
sinais_enviados: dict[int, set] = {}     # fixture_id -> set de tipos de sinal já emitidos

# ─── FUNÇÕES DE API ───────────────────────────────────────────────────────────
def get_live_fixtures():
    """Retorna todas as partidas ao vivo."""
    try:
        r = requests.get(f"{API_BASE}/fixtures", headers=HEADERS,
                         params={"live": "all"}, timeout=15)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception as e:
        print(f"[ERRO] get_live_fixtures: {e}")
        return []


def get_fixture_stats(fixture_id: int):
    """Retorna estatísticas detalhadas de uma partida."""
    try:
        r = requests.get(f"{API_BASE}/fixtures/statistics", headers=HEADERS,
                         params={"fixture": fixture_id}, timeout=15)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception as e:
        print(f"[ERRO] get_fixture_stats: {e}")
        return []


def get_fixture_events(fixture_id: int):
    """Retorna eventos (gols, cartões, etc.) de uma partida."""
    try:
        r = requests.get(f"{API_BASE}/fixtures/events", headers=HEADERS,
                         params={"fixture": fixture_id}, timeout=15)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception as e:
        print(f"[ERRO] get_fixture_events: {e}")
        return []

# ─── EXTRAÇÃO DE ESTATÍSTICAS ─────────────────────────────────────────────────
def parse_stat(stats_list: list, stat_name: str, team_index: int) -> int:
    """Extrai valor inteiro de estatística por nome e índice de time."""
    try:
        for s in stats_list[team_index]["statistics"]:
            if s["type"] == stat_name:
                v = s["value"]
                return int(v) if v is not None else 0
        return 0
    except Exception:
        return 0


def extract_stats(stats_response: list) -> dict | None:
    """Monta dict padronizado de estatísticas (casa e fora)."""
    if len(stats_response) < 2:
        return None
    home, away = 0, 1
    return {
        "shots_on":      (parse_stat(stats_response, "Shots on Goal",          home),
                          parse_stat(stats_response, "Shots on Goal",          away)),
        "shots_off":     (parse_stat(stats_response, "Shots off Goal",         home),
                          parse_stat(stats_response, "Shots off Goal",         away)),
        "corners":       (parse_stat(stats_response, "Corner Kicks",           home),
                          parse_stat(stats_response, "Corner Kicks",           away)),
        "dangerous":     (parse_stat(stats_response, "Dangerous Attacks",      home),
                          parse_stat(stats_response, "Dangerous Attacks",      away)),
        "possession":    (parse_stat(stats_response, "Ball Possession",        home),
                          parse_stat(stats_response, "Ball Possession",        away)),
        "yellow_cards":  (parse_stat(stats_response, "Yellow Cards",           home),
                          parse_stat(stats_response, "Yellow Cards",           away)),
        "red_cards":     (parse_stat(stats_response, "Red Cards",              home),
                          parse_stat(stats_response, "Red Cards",              away)),
        "fouls":         (parse_stat(stats_response, "Fouls",                  home),
                          parse_stat(stats_response, "Fouls",                  away)),
    }

# ─── LÓGICA DE PONTUAÇÃO (SCORE ENGINE) ───────────────────────────────────────
def calcular_score(st: dict, minuto: int, total_gols: int) -> tuple[int, list[str]]:
    """
    Retorna (pontuação 0-100, lista de razões).
    Pontuação >= 60 → BAIXO | >= 75 → MÉDIO | >= 88 → ALTO
    """
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

    # Penalidade por cartão vermelho (jogo desequilibrado)
    if red_cards_total > 0:
        score -= 20

    # ── Chutes ao gol (pressão real)
    if shots_on_total >= 8:
        score += 22; razoes.append(f"🎯 {shots_on_total} chutes ao gol")
    elif shots_on_total >= 5:
        score += 14; razoes.append(f"🎯 {shots_on_total} chutes ao gol")
    elif shots_on_total >= 3:
        score += 7

    # ── Chutes fora (volume de jogo)
    if shots_off_total >= 10:
        score += 12; razoes.append(f"📐 {shots_off_total} chutes fora")
    elif shots_off_total >= 6:
        score += 7
    elif shots_off_total >= 3:
        score += 3

    # ── Escanteios
    if corners_total >= 10:
        score += 18; razoes.append(f"🚩 {corners_total} escanteios")
    elif corners_total >= 7:
        score += 12; razoes.append(f"🚩 {corners_total} escanteios")
    elif corners_total >= 4:
        score += 6

    # ── Ataques perigosos totais
    if danger_total >= 60:
        score += 20; razoes.append(f"⚡ {danger_total} ataques perigosos")
    elif danger_total >= 40:
        score += 14; razoes.append(f"⚡ {danger_total} ataques perigosos")
    elif danger_total >= 25:
        score += 8

    # ── Desequilíbrio ofensivo (um time muito mais ativo)
    if danger_home > 0 and danger_away > 0:
        ratio = max(danger_home, danger_away) / min(danger_home, danger_away)
        if ratio >= 3.0:
            score += 10; razoes.append(f"📊 Pressão unilateral ({danger_home}-{danger_away})")
        elif ratio >= 2.0:
            score += 5

    # ── Posse alta (time dominando)
    if posse_home >= 65 or (100 - posse_home) >= 65:
        score += 8; razoes.append(f"⚽ Posse dominante {max(posse_home, 100-posse_home)}%")

    # ── Janela de minuto (peso por fase)
    if 55 <= minuto <= 70:
        score += 10; razoes.append(f"⏱️ Janela crítica ({minuto}')")
    elif 70 < minuto <= 80:
        score += 14; razoes.append(f"⏱️ Reta final ({minuto}')")
    elif 80 < minuto <= 89:
        score += 8

    # ── Jogo sem gols = maior pressão esperada
    if total_gols == 0:
        score += 10; razoes.append("🔒 Jogo sem gols – pressão crescente")
    elif total_gols == 1:
        score += 5

    return min(score, 100), razoes


def classificar_sinal(score: int) -> str | None:
    if score >= 88:
        return "🔴 ALTO"
    if score >= 75:
        return "🟡 MÉDIO"
    if score >= 60:
        return "🟢 BAIXO"
    return None

# ─── TIPO DE SINAL ÚNICO POR PARTIDA ─────────────────────────────────────────
def tipo_sinal(score: int) -> str:
    if score >= 88: return "ALTO"
    if score >= 75: return "MEDIO"
    return "BAIXO"

# ─── FORMATAÇÃO DA MENSAGEM (estilo Robozão) ──────────────────────────────────
def montar_mensagem(fixture: dict, st: dict, minuto: int,
                    total_gols: int, gols_str: str,
                    classificacao: str, razoes: list[str],
                    league_name: str, score: int) -> str:

    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]

    linhas_razoes = "\n".join(f"  {r}" for r in razoes) if razoes else "  📊 Estatísticas favoráveis"

    msg = (
        f"🤖 **ROBÔ OVER GOLS**\n\n"
        f"⚽ **{home} x {away}**\n"
        f"🏆 {league_name}\n"
        f"⏱️ {minuto} minutos\n"
        f"📊 Placar {gols_str}\n\n"
        f"📈 **Estatísticas (Casa - Fora)**\n"
        f"Chutes ao gol: {st['shots_on'][0]} - {st['shots_on'][1]}\n"
        f"Chutes fora: {st['shots_off'][0]} - {st['shots_off'][1]}\n"
        f"Escanteios: {st['corners'][0]} - {st['corners'][1]}\n"
        f"Ataques perigosos: {st['dangerous'][0]} - {st['dangerous'][1]}\n"
        f"Posse de bola: {st['possession'][0]} - {st['possession'][1]}\n"
        f"Cartões vermelhos: {st['red_cards'][0]} - {st['red_cards'][1]}\n\n"
        f"🎯 **Razões do sinal:**\n{linhas_razoes}\n\n"
        f"📡 Força do sinal: {score}/100\n\n"
        f"🚨 **ALERTA DE ENTRADA**\n"
        f"Over limite — {classificacao}\n\n"
        f"⚠️ Jogue com responsabilidade 🔞"
    )
    return msg

# ─── ENVIO PARA O CANAL ───────────────────────────────────────────────────────
def enviar_sinal(mensagem: str):
    try:
        bot.send_message(CHANNEL_ID, mensagem, parse_mode="Markdown")
        print(f"[OK] Sinal enviado: {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[ERRO] enviar_sinal: {e}")

# ─── LOOP PRINCIPAL ───────────────────────────────────────────────────────────
def varredura():
    print(f"[SCAN] {datetime.now().strftime('%H:%M:%S')} — varrendo partidas ao vivo...")
    fixtures = get_live_fixtures()
    print(f"[INFO] {len(fixtures)} partidas ao vivo encontradas")

    for fix in fixtures:
        try:
            fixture_id = fix["fixture"]["id"]
            minuto     = fix["fixture"]["status"].get("elapsed") or 0
            status     = fix["fixture"]["status"]["short"]
            home_gols  = fix["goals"]["home"] or 0
            away_gols  = fix["goals"]["away"] or 0
            total_gols = home_gols + away_gols
            gols_str   = f"{home_gols} - {away_gols}"
            league_name = fix["league"]["name"]
            season     = fix["league"].get("season", "")

            # ── Filtros base ──────────────────────────────────────────────────
            # Apenas 2ª metade (55-89') e jogos com 0-2 gols
            if status not in ("2H", "LIVE", "ET"):
                continue
            if not (55 <= minuto <= 89):
                continue
            if total_gols > 2:
                continue

            # ── Buscar estatísticas ───────────────────────────────────────────
            stats_resp = get_fixture_stats(fixture_id)
            st = extract_stats(stats_resp)
            if st is None:
                continue

            # ── Calcular score ────────────────────────────────────────────────
            score, razoes = calcular_score(st, minuto, total_gols)
            classificacao = classificar_sinal(score)
            if classificacao is None:
                continue

            # ── Evitar sinal duplicado (mesmo tipo para mesma partida) ────────
            tipo = tipo_sinal(score)
            if fixture_id not in sinais_enviados:
                sinais_enviados[fixture_id] = set()
            if tipo in sinais_enviados[fixture_id]:
                continue
            sinais_enviados[fixture_id].add(tipo)

            # ── Montar e enviar ───────────────────────────────────────────────
            mensagem = montar_mensagem(fix, st, minuto, total_gols,
                                       gols_str, classificacao,
                                       razoes, league_name, score)
            print(f"[SINAL {tipo}] {fix['teams']['home']['name']} x {fix['teams']['away']['name']}"
                  f" | {minuto}' | score={score}")
            enviar_sinal(mensagem)
            time.sleep(2)   # evitar flood

        except Exception as e:
            print(f"[ERRO] fixture loop: {e}")

    # Limpar partidas antigas do controle (fixtures que saíram do ao vivo)
    ids_vivos = {f["fixture"]["id"] for f in fixtures}
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

# ─── COMANDOS DO BOT ──────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    bot.reply_to(msg,
        "🤖 *Robô Over Gols* ativo!\n\n"
        "Varredura automática a cada 60 segundos.\n"
        "Sinais enviados direto no canal quando detectamos pressão alta.\n\n"
        "Use /status para ver o estado atual.",
        parse_mode="Markdown")


@bot.message_handler(commands=["status"])
def cmd_status(msg):
    bot.reply_to(msg,
        f"✅ Bot rodando\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"📡 Partidas monitoradas: {len(sinais_enviados)}",
        parse_mode="Markdown")


@bot.message_handler(commands=["teste"])
def cmd_teste(msg):
    bot.reply_to(msg, "🔍 Iniciando varredura manual...")
    threading.Thread(target=varredura, daemon=True).start()


@bot.message_handler(commands=["aovivo"])
def cmd_aovivo(msg):
    bot.reply_to(msg, "🔍 Buscando jogos ao vivo...")
    fixtures = get_live_fixtures()
    if not fixtures:
        bot.reply_to(msg, "❌ Nenhum jogo ao vivo encontrado na API.")
        return
    linhas = [f"⚽ {len(fixtures)} jogos ao vivo:\n"]
    for f in fixtures[:15]:
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        minuto = f["fixture"]["status"].get("elapsed") or 0
        status = f["fixture"]["status"]["short"]
        gols = f"{f['goals']['home'] or 0}-{f['goals']['away'] or 0}"
        linhas.append(f"• {home} x {away} | {minuto}' | {gols} | {status}")
    bot.reply_to(msg, "\n".join(linhas))


@bot.message_handler(commands=["forcasinal"])
def cmd_forcasinal(msg):
    mensagem = (
        "🤖 **ROBÔ OVER GOLS** — TESTE\n\n"
        "⚽ **Brasil x Argentina**\n"
        "🏆 Copa do Mundo 2026\n"
        "⏱️ 70 minutos\n"
        "📊 Placar 0 - 0\n\n"
        "📈 **Estatísticas (Casa - Fora)**\n"
        "Chutes ao gol: 6 - 3\n"
        "Chutes fora: 8 - 4\n"
        "Escanteios: 7 - 3\n"
        "Ataques perigosos: 45 - 22\n"
        "Posse de bola: 62 - 38\n"
        "Cartões vermelhos: 0 - 0\n\n"
        "📡 Força do sinal: 88/100\n\n"
        "🚨 **ALERTA DE ENTRADA**\n"
        "Over limite — 🔴 ALTO\n\n"
        "⚠️ Jogue com responsabilidade 🔞"
    )
    try:
        bot.send_message(CHANNEL_ID, mensagem, parse_mode="Markdown")
        bot.reply_to(msg, "✅ Sinal de teste enviado ao canal!")
    except Exception as e:
        bot.reply_to(msg, f"❌ Erro ao enviar: {e}")

# ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  🤖 ROBÔ OVER GOLS — iniciando")
    print(f"  Canal: {CHANNEL_ID}")
    print(f"  Intervalo de scan: {SCAN_INTERVAL}s")
    print("=" * 50)

    # Thread do loop de varredura
    t = threading.Thread(target=loop_continuo, daemon=True)
    t.start()

    # Polling do bot (comandos /start, /status, /teste)
    print("[BOT] Aguardando comandos...")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)




