#!/bin/bash
# setup.sh – Cria o ambiente virtual e instala as dependências

set -e

echo "🤘 Iron Maiden Ticket Monitor – Setup"
echo "======================================"

# Verifica Python 3
if ! command -v python &> /dev/null; then
    echo "❌ Python 3 não encontrado. Instale em: https://python.org"
    exit 1
fi
echo "✅ Python: $(python --version)"

# ── Dependências do sistema para Playwright/Chromium no Ubuntu 24.04 ──
echo ""
echo "📦 Instalando dependências do sistema (Ubuntu 24.04)..."
sudo apt-get update -qq
sudo apt-get install -y \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0t64 \
    libatk-bridge2.0-0t64 \
    libcups2t64 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2t64 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0t64 \
    libglib2.0-0t64 \
    libgtk-3-0t64 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxext6 \
    2>/dev/null || true
echo "✅ Dependências do sistema instaladas."

# ── Ambiente virtual ──
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Criando ambiente virtual..."
    python -m venv venv
else
    echo "♻️  Ambiente virtual já existe, reutilizando..."
fi

source venv/bin/activate

pip install --upgrade pip -q

echo "📥 Instalando dependências Python..."
pip install -r requirements.txt -q

# ── Playwright Chromium ──
echo "🌐 Instalando Chromium (Playwright)..."
# --with-deps tenta instalar deps, mas no Ubuntu 24 pode falhar — já instalamos acima
playwright install chromium --with-deps 2>/dev/null || playwright install chromium
echo "✅ Chromium instalado."

# ── Arquivo .env ──
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