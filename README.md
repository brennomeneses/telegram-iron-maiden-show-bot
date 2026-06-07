# 🤘 Iron Maiden Ticket Monitor Bot

Bot do Telegram que monitora disponibilidade de ingressos para:

**Iron Maiden – Run For Your Lives World Tour 2026**  
📅 28/10/2026 | 🏟️ Arena da Baixada – Curitiba/PR

## 📡 O que ele monitora

| Site | Tipo | O que verifica |
|------|------|----------------|
| **BuyTicket** | Mercado secundário | Aparecimento de ingressos à venda por revendedores |
| **Livepass** | Venda oficial | Abertura de novo lote ou início das vendas gerais |

---

## ⚙️ Configuração

### 1. Crie seu bot no Telegram

1. Abra o Telegram e procure por `@BotFather`
2. Envie `/newbot` e siga as instruções
3. Copie o **token** gerado (formato: `123456789:ABCdef...`)

### 2. Instale as dependências

```bash
# Clone ou baixe os arquivos do bot
cd iron_maiden_bot

# Crie um ambiente virtual (recomendado)
python -m venv venv
source venv/bin/activate        # Linux/Mac
# ou
venv\Scripts\activate           # Windows

# Instale as dependências
pip install -r requirements.txt
```

### 3. Configure o token

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite o .env e coloque seu token
TELEGRAM_BOT_TOKEN=seu_token_aqui
CHECK_INTERVAL_SECONDS=300
```

### 4. Execute o bot

```bash
# Opção A: exportar variável de ambiente e rodar
export TELEGRAM_BOT_TOKEN="seu_token_aqui"
python bot.py

# Opção B: usar o arquivo .env com python-dotenv
pip install python-dotenv
# e adicione ao início do bot.py:
# from dotenv import load_dotenv; load_dotenv()
python bot.py
```

---

## 🤖 Comandos disponíveis

| Comando | Descrição |
|---------|-----------|
| `/start` | Menu principal com botões |
| `/check` | Verificar disponibilidade agora |
| `/subscribe` | Ativar alertas automáticos |
| `/unsubscribe` | Desativar alertas |
| `/status` | Ver se seus alertas estão ativos |
| `/links` | Links diretos para compra |
| `/help` | Lista de comandos |

---

## ☁️ Rodando 24/7 (servidor)

Para o bot funcionar continuamente, você precisa de um servidor.
Opções gratuitas ou baratas:

### Opção A – Railway (fácil, gratuito com limites)
1. Acesse [railway.app](https://railway.app)
2. Crie um novo projeto → "Deploy from GitHub" ou suba os arquivos
3. Adicione a variável de ambiente `TELEGRAM_BOT_TOKEN` nas configurações

### Opção B – VPS (DigitalOcean, Contabo, etc.)
```bash
# Instale como serviço systemd
sudo nano /etc/systemd/system/ironmaiden-bot.service
```
```ini
[Unit]
Description=Iron Maiden Ticket Monitor Bot
After=network.target

[Service]
Type=simple
User=seu_usuario
WorkingDirectory=/home/seu_usuario/iron_maiden_bot
Environment=TELEGRAM_BOT_TOKEN=seu_token_aqui
Environment=CHECK_INTERVAL_SECONDS=300
ExecStart=/home/seu_usuario/iron_maiden_bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable ironmaiden-bot
sudo systemctl start ironmaiden-bot
sudo systemctl status ironmaiden-bot
```

### Opção C – PM2 (Node.js process manager com suporte a Python)
```bash
npm install -g pm2
pm2 start bot.py --interpreter python3 --name "ironmaiden-bot"
pm2 save
pm2 startup
```

---

## ⚠️ Observações importantes

- **BuyTicket** é um mercado *secundário* (revendedores). Pode ter ingressos acima do preço oficial.
- **Livepass** é a venda *oficial*. O bot detecta quando novos lotes abrirem.
- O bot verifica a cada **5 minutos** por padrão. Reduza para 2 minutos (`120`) se quiser mais agilidade, mas não menos que isso para não ser bloqueado pelos sites.
- Os arquivos `subscribers.json` e `bot.log` são criados automaticamente na primeira execução.
- A Livepass usa bastante JavaScript; o bot captura o que está no HTML estático e tenta a API interna. Em alguns casos pode indicar "status indefinido" — sinal para verificar manualmente.

---

## 🛠️ Estrutura dos arquivos

```
iron_maiden_bot/
├── bot.py           # Bot do Telegram (handlers, alertas)
├── monitor.py       # Scraping do BuyTicket e Livepass
├── requirements.txt # Dependências Python
├── .env.example     # Modelo de configuração
├── subscribers.json # Gerado automaticamente (lista de usuários)
└── bot.log          # Gerado automaticamente (logs)
```