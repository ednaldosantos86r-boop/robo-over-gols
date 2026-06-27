import os
import time
import requests

# Configurações obtidas das Variáveis de Ambiente do Railway
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

def enviar_sinal_telegram(mensagem):
    """Envia o alerta para o canal do Telegram de forma direta, sem travar webhook"""
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Sinal enviado com sucesso para o Telegram!")
        else:
            print(f"Erro ao enviar para o Telegram: {response.text}")
    except Exception as e:
        print(f"Falha na conexão com o Telegram: {e}")

def buscar_jogos_ao_vivo():
    """Busca as partidas em tempo real na API-Football"""
    url = "https://api-sports.io"
    headers = {
        "x-rapidapi-key": API_FOOTBALL_KEY,
        "x-rapidapi-host": "v3.football.api-sports.io"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("response", [])
        else:
            print(f"Erro na API-Football: {response.status_code}")
            return []
    except Exception as e:
        print(f"Falha ao conectar na API-Football: {e}")
        return []

def analisar_jogos():
    print("Iniciando monitoramento de jogos ao vivo...")
    while True:
        jogos = buscar_jogos_ao_vivo()
        
        for jogo in jogos:
            fixture = jogo.get("fixture", {})
            status = fixture.get("status", {})
            tempo_jogo = status.get("elapsed", 0) # Minutos decorridos
            
            teams = jogo.get("teams", {})
            casa = teams.get("home", {}).get("name", "Casa")
            fora = teams.get("away", {}).get("name", "Fora")
            
            goals = jogo.get("goals", {})
            gols_casa = goals.get("home", 0)
            gols_fora = goals.get("away", 0)
            
            # ESTRATÉGIA: Jogo empatado em 0x0 entre os minutos 15 e 30
            if tempo_jogo >= 15 and tempo_jogo <= 30 and gols_casa == 0 and gols_fora == 0:
                # Cria o texto do sinal
                mensagem = (
                    "🚨 *ALERTA DE GOLS - OVER LIVES* 🚨\n\n"
                    f"⚽ *Jogo:* {casa} x {fora}\n"
                    f"⏰ *Tempo:* {tempo_jogo}' minutos\n"
                    f"📊 *Placar atual:* {gols_casa}x{gols_fora}\n\n"
                    "🎯 *Entrada recomendada:* Over Gols no Primeiro Tempo!"
                )
                enviar_sinal_telegram(mensagem)
        
        # Espera 5 minutos (300 segundos) antes de checar os jogos novamente
        print("Aguardando próxima checagem...")
        time.sleep(300)

if __name__ == "__main__":
    analisar_jogos()


