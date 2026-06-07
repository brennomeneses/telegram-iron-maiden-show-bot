#!/bin/bash
# setup.sh – Cria o ambiente virtual e instala as dependências

set -e

echo "🤘 Iron Maiden Ticket Monitor – Setup"
echo "======================================"

# Verifica Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado. Instale em: https://python.org"
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# Cria o venv se não existir
if [ ! -d "venv" ]; then
    echo "📦 Criando ambiente virtual..."
    python3 -m venv venv
else
    echo "♻️  Ambiente virtual já existe, reutilizando..."
fi

# Ativa o venv
source venv/bin/activate

# Atualiza pip
pip install --upgrade pip -q

# Instala dependências Python
echo "📥 Instalando dependências Python..."
pip install -r requirements.txt -q

# Instala o Chromium do Playwright (necessário para scraping da Livepass)
echo "🌐 Instalando Chromium (Playwright)..."
playwright install chromium

# Cria o .env se não existir
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚙️  Arquivo .env criado. Edite e coloque seu token:"
    echo "   nano .env"
else
    echo "✅ Arquivo .env já existe."
fi

echo ""
echo "======================================"
echo "✅ Setup concluído!"
echo ""
echo "Para rodar o bot:"
echo "  source venv/bin/activate"
echo "  python bot.py"