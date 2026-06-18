import os
import asyncio
import logging
from datetime import datetime
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
import aiohttp

# ============================================================
# CONFIGURAÇÕES - EDITE AQUI
# ============================================================
TELEGRAM_TOKEN = "8905271121:AAG_mv76V_QVKACvDR51v_5mGK4ajECkURY"
API_FOOTBALL_KEY = "15d971190e1b52fde7cf428428faa376"
API_FOOTBALL_URL = "https://v3.football.api-sports.io"

# Canais/grupos para enviar os sinais (adicione os IDs)
# Ex: CHAT_IDS = ["-1001234567890", "-1009876543210"]
CHAT_IDS = ["6590354226"]

# Intervalo de verificação em segundos (padrão: 60s)
CHECK_INTERVAL = 60

# ============================================================
# CONFIGURAÇÕES DOS SINAIS
# ============================================================
JANELA_MIN = 55       # Minuto mínimo para sinal
JANELA_MAX = 80       # Minuto máximo para sinal
MIN_GOLS = 1          # Mínimo de gols no jogo para sinal
MAX_GOLS = 2          # Máximo de gols (placar aberto)

# Pontuação mínima para emitir sinal
PONTOS_MINIMO_ALTO = 70    # Sinal ALTO
PONTOS_MINIMO_MEDIO = 50   # Sinal MÉDIO
PONTOS_MINIMO_BAIXO = 30   # Sinal BAIXO

# ============================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Controle de jogos já sinalizados (evita duplicatas)
jogos_sinalizados = set()

# ============================================================
# FUNÇÕES DA API
# ============================================================

async def get_live_matches(session):
    """Busca partidas ao vivo na API-Football"""
    headers = {
        "x-apisports-key": API_FOOTBALL_KEY
    }
    try:
        async with session.get(
            f"{API_FOOTBALL_URL}/fixtures",
            headers=headers,
            params={"live": "all"}
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("response", [])
            else:
                logger.error(f"Erro API: {response.status}")
                return []
    except Exception as e:
        logger.error(f"Erro ao buscar partidas: {e}")
        return []

def calcular_pontuacao(fixture):
    """Calcula pontuação do jogo para determinar força do sinal"""
    pontos = 0
    stats = fixture.get("statistics", [])
    
    # Dicionário para facilitar acesso às stats
    stats_dict = {}
    for team_stats in stats:
        team_id = team_stats.get("team", {}).get("id")
        for stat in team_stats.get("statistics", []):
            key = stat.get("type", "")
            value = stat.get("value") or 0
            if isinstance(value, str):
                value = int(value.replace("%", "")) if "%" in value else 0
            if key not in stats_dict:
                stats_dict[key] = 0
            stats_dict[key] += value

    # Critérios de pontuação
    total_chutes = stats_dict.get("Total Shots", 0)
    chutes_gol = stats_dict.get("Shots on Goal", 0)
    escanteios = stats_dict.get("Corner Kicks", 0)
    pressao = stats_dict.get("Ball Possession", 0)

    # Chutes (máx 30 pts)
    if total_chutes >= 20:
        pontos += 30
    elif total_chutes >= 15:
        pontos += 20
    elif total_chutes >= 10:
        pontos += 10

    # Chutes no alvo (máx 25 pts)
    if chutes_gol >= 8:
        pontos += 25
    elif chutes_gol >= 5:
        pontos += 15
    elif chutes_gol >= 3:
        pontos += 10

    # Escanteios (máx 25 pts)
    if escanteios >= 10:
        pontos += 25
    elif escanteios >= 7:
        pontos += 15
    elif escanteios >= 4:
        pontos += 10

    # Posse equilibrada (máx 20 pts) - indica jogo aberto
    if 40 <= pressao <= 60:
        pontos += 20
    elif 35 <= pressao <= 65:
        pontos += 10

    return pontos, stats_dict

def determinar_sinal(pontos):
    """Determina nível do sinal baseado na pontuação"""
    if pontos >= PONTOS_MINIMO_ALTO:
        return "🔴 SINAL ALTO", pontos
    elif pontos >= PONTOS_MINIMO_MEDIO:
        return "🟡 SINAL MÉDIO", pontos
    elif pontos >= PONTOS_MINIMO_BAIXO:
        return "🟢 SINAL BAIXO", pontos
    return None, pontos

def formatar_mensagem(fixture, sinal, pontos, stats_dict):
    """Formata a mensagem de sinal para envio"""
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
    
    # Posse de bola por time
    posse_home = 50
    posse_away = 50
    for team_stats in fixture.get("statistics", []):
        for stat in team_stats.get("statistics", []):
            if stat.get("type") == "Ball Possession":
                val = stat.get("value", "50%")
                if val and "%" in str(val):
                    val_num = int(str(val).replace("%", ""))
                    if team_stats.get("team", {}).get("id") == teams.get("home", {}).get("id"):
                        posse_home = val_num
                        posse_away = 100 - val_num

    mensagem = f"""
🤖 *ROBÔ OVER GOLS*
━━━━━━━━━━━━━━━━━━━━
🏆 {league_name}
⚽ *{home_team} v {away_team}*
⏱ {elapsed}' | 🔢 {home_goals} - {away_goals} | 🎯 {pontos}pts

📊 *ESTATÍSTICAS:*
• Arremates: {total_chutes}
• No Alvo: {chutes_gol}
• Escanteios: {escanteios}
• Posse: {posse_home}%-{posse_away}%

🚨 *{sinal}: MAIS 1 GOL*
✅ Janela ideal ({JANELA_MIN}-{JANELA_MAX}min)
✅ Placar aberto
━━━━━━━━━━━━━━━━━━━━
"""
    return mensagem

# ============================================================
# LÓGICA PRINCIPAL
# ============================================================

async def verificar_partidas(bot):
    """Verifica partidas ao vivo e envia sinais"""
    async with aiohttp.ClientSession() as session:
        partidas = await get_live_matches(session)
        
        if not partidas:
            logger.info("Nenhuma partida ao vivo encontrada")
            return

        logger.info(f"Partidas ao vivo: {len(partidas)}")

        for fixture in partidas:
            try:
                fixture_id = fixture.get("fixture", {}).get("id")
                elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed", 0)
                goals = fixture.get("goals", {})
                home_goals = goals.get("home", 0) or 0
                away_goals = goals.get("away", 0) or 0
                total_gols = home_goals + away_goals

                # Verificar janela de tempo
                if not (JANELA_MIN <= elapsed <= JANELA_MAX):
                    continue

                # Verificar total de gols (placar aberto)
                if total_gols < MIN_GOLS or total_gols > MAX_GOLS:
                    continue

                # Evitar sinalizar o mesmo jogo mais de uma vez
                chave = f"{fixture_id}_{elapsed // 5}"  # Agrupa em janelas de 5 min
                if chave in jogos_sinalizados:
                    continue

                # Calcular pontuação
                pontos, stats_dict = calcular_pontuacao(fixture)

                # Determinar sinal
                sinal, _ = determinar_sinal(pontos)
                if not sinal:
                    continue

                # Formatar e enviar mensagem
                mensagem = formatar_mensagem(fixture, sinal, pontos, stats_dict)
                
                for chat_id in CHAT_IDS:
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=mensagem,
                            parse_mode="Markdown"
                        )
                        logger.info(f"Sinal enviado: {fixture_id} para {chat_id}")
                    except Exception as e:
                        logger.error(f"Erro ao enviar para {chat_id}: {e}")

                jogos_sinalizados.add(chave)

            except Exception as e:
                logger.error(f"Erro ao processar partida: {e}")

# ============================================================
# COMANDOS DO BOT
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *ROBÔ OVER GOLS*\n\n"
        "Bot de sinais ao vivo ativo!\n\n"
        "Comandos:\n"
        "/start - Iniciar bot\n"
        "/status - Ver status\n"
        "/aovivo - Ver partidas ao vivo agora",
        parse_mode="Markdown"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"✅ *Bot ativo!*\n\n"
        f"⏱ Verificando a cada {CHECK_INTERVAL}s\n"
        f"🎯 Janela: {JANELA_MIN}-{JANELA_MAX} min\n"
        f"📊 Sinais emitidos: {len(jogos_sinalizados)}",
        parse_mode="Markdown"
    )

async def aovivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Buscando partidas ao vivo...")
    
    async with aiohttp.ClientSession() as session:
        partidas = await get_live_matches(session)
    
    if not partidas:
        await update.message.reply_text("❌ Nenhuma partida ao vivo no momento.")
        return
    
    msg = f"⚽ *{len(partidas)} partidas ao vivo:*\n\n"
    for f in partidas[:10]:  # Limita a 10
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        elapsed = f.get("fixture", {}).get("status", {}).get("elapsed", 0)
        home = teams.get("home", {}).get("name", "")
        away = teams.get("away", {}).get("name", "")
        hg = goals.get("home", 0) or 0
        ag = goals.get("away", 0) or 0
        msg += f"• {home} {hg}-{ag} {away} ({elapsed}')\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

# ============================================================
# LOOP PRINCIPAL
# ============================================================

async def job_verificar(context: ContextTypes.DEFAULT_TYPE):
    """Job periódico para verificar partidas"""
    await verificar_partidas(context.bot)

def main():
    """Função principal"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("aovivo", aovivo))

    # Job periódico
    job_queue = app.job_queue
    job_queue.run_repeating(job_verificar, interval=CHECK_INTERVAL, first=10)

    logger.info("🤖 Robô Over Gols iniciado!")
    app.run_polling()

if __name__ == "__main__":
    main()
